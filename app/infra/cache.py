"""
这是一个语义缓存模块
"""
from __future__ import annotations

import json
from typing import Any

from app_config.settings import settings

COLLECTION_NAME = "qa_semantic_cache"
EMBEDDING_DIM = 1536    #向量维度
L1_SEMANTIC_DISTANCE_THRESHOLD = 0.08  #语义相似度阈值

UNCACHEABLE_ANSWER_MARKERS = (
    "这次查询没有完整完成",
    "建议稍后重试",
    "转人工",
    "输入的内容似乎是一串问号",
    "可能发送时出现了乱码",
    "未表达清楚问题",
)


def _debug_cache_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print("[SEMANTIC_CACHE_DEBUG] " + json.dumps(payload, ensure_ascii=False, default=str))


def _is_usable_cached_answer(answer: str) -> bool:
    return not any(marker in answer for marker in UNCACHEABLE_ANSWER_MARKERS)


class SemanticCache:
    def __init__(self) -> None:
        self._client: Any = None
        self._embeddings: Any = None
        self._available: bool = False
#异步初始化原因：1. 嵌入模型调用是异步的 2.整个项目架构是FastAPI 异步架构 需手动调用
    async def initialize(self) -> None:
        try:
            from pymilvus import MilvusClient
            from langchain_community.embeddings import DashScopeEmbeddings

            connect_kwargs: dict[str, Any] = {
                "uri": f"http://{settings.milvus_host}:{settings.milvus_port}"
            }
            if settings.milvus_api_key:
                connect_kwargs["token"] = settings.milvus_api_key

            self._client = MilvusClient(**connect_kwargs)
            self._embeddings = DashScopeEmbeddings(
                model="text-embedding-v2",
                dashscope_api_key=settings.dashscope_api_key,
            )
            self._ensure_collection()
            self._available = True
        except Exception as exc:
            print(f"SemanticCache init failed: {exc}")
            self._available = False

    async def set_cache(
        self,
        query: str,
        response: str,
        user_id: str | None = None,
        scope: str = "public",
    ) -> None:
        if not self._available:
            return
        #标准化文本
        normalized = self._normalize(query)
        if not normalized or normalized.count("?") >= max(3, len(normalized) // 2):
            _debug_cache_event("skip_set_garbled_query", query=query, user_id=user_id)
            return
        owner = user_id or ""
        #cache_scope: 最终存入数据库的作用域字段
        cache_scope = "user" if owner else scope
        try:
            #aembed_query() 是 LangChain 中嵌入模型（Embeddings）的一个异步方法，它的作用是将文本字符串转换为向量（Vector）
            #embedding: 一个长度为 1536 的浮点数数组（根据你的 EMBEDDING_DIM = 1536 配置）。[0.012, -0.453, 0.891, ..., 0.234]
            embedding = await self._embeddings.aembed_query(normalized)
            #把所有的 " 替换成 \"（转义字符） 防止注入攻击
            safe_norm = normalized.replace('"', '\\"')
            safe_scope = cache_scope.replace('"', '\\"')
            safe_owner = owner.replace('"', '\\"')
            #构建删除过滤器 执行删除操作 避免数据库里出现重复的问题但答案不同的情况
            delete_filter = (
                f'question_norm == "{safe_norm}" and scope == "{safe_scope}" and user_id == "{safe_owner}"'
            )
            self._client.delete(collection_name=COLLECTION_NAME, filter=delete_filter)

            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[
                    {
                        "question": query.strip(),
                        "question_norm": normalized,
                        "answer": response,
                        "scope": cache_scope,
                        "user_id": owner,
                        "enabled": 1,
                        "embedding": embedding,
                    }
                ],
            )
        except Exception as exc:
            print(f"SemanticCache set_cache failed: {exc}")

    async def get_cache(self, query: str, user_id: str) -> dict[str, Any] | None:
        if not self._available:
            _debug_cache_event("skip_unavailable", query=query, user_id=user_id)
            return None
        normalized = self._normalize(query)
        safe_norm = normalized.replace('"', '\\"')
        safe_user = user_id.replace('"', '\\"')
        _debug_cache_event(
            "lookup_start",
            query=query,
            normalized=normalized,
            user_id=user_id,
            threshold=L1_SEMANTIC_DISTANCE_THRESHOLD,
        )

        user_filter = (
            f'enabled == 1 and question_norm == "{safe_norm}" and scope == "user" and user_id == "{safe_user}"'
        )
        public_filter = (
            f'enabled == 1 and question_norm == "{safe_norm}" and scope == "public"'
        )
        #用户私有精确匹配
        user_exact = self._query_one(user_filter)
        if user_exact:
            _debug_cache_event(
                "hit_exact_user",
                query=query,
                user_id=user_id,
                matched_question=user_exact.get("question"),
                scope=user_exact.get("scope"),
                owner=user_exact.get("user_id"),
            )
            return {
                "answer": user_exact["answer"],
                "matched_question": user_exact["question"],
                "level": "L1_EXACT",
                "distance": 0.0,
            }
        #公共精确匹配
        public_exact = self._query_one(public_filter)
        if public_exact:
            _debug_cache_event(
                "hit_exact_public",
                query=query,
                user_id=user_id,
                matched_question=public_exact.get("question"),
                scope=public_exact.get("scope"),
                owner=public_exact.get("user_id"),
            )
            return {
                "answer": public_exact["answer"],
                "matched_question": public_exact["question"],
                "level": "L1_EXACT",
                "distance": 0.0,
            }

        try:
            #语义模糊搜索
            query_embedding = await self._embeddings.aembed_query(normalized)
            scoped_filter = (
                f'enabled == 1 and (scope == "public" or (scope == "user" and user_id == "{safe_user}"))'
            )
            """results 是 Milvus 客户端执行向量搜索后返回的嵌套列表结构。
            results = [
    [
        {
            "distance": 0.05,          # 相似度距离（越小越相似）
            "id": 123456789,           # 数据库中的主键 ID
            "entity": {                # 你请求的 output_fields 字段
                "question": "什么是专有网络？",
                "answer": "VPC 是一个隔离的网络环境...",
                "scope": "public",
                "user_id": ""
            }
        },
        # 如果 limit > 1，这里会有更多匹配项
    ],
    # 如果你一次搜索多个向量（data=[vec1, vec2]），这里会有更多子列表
]"""
            results = self._client.search(
                collection_name=COLLECTION_NAME,
                data=[query_embedding],
                filter=scoped_filter,
                limit=1,
                output_fields=["question", "answer", "scope", "user_id"],
            )
            if not results:
                _debug_cache_event("miss_semantic_no_results", query=query, user_id=user_id)
                return None
            hit = results[0][0] if results[0] else None
            if not hit:
                _debug_cache_event("miss_semantic_empty_hits", query=query, user_id=user_id)
                return None
            distance = float(hit.get("distance", 1.0))
            entity = hit.get("entity", {})
            answer = entity.get("answer", "")
            _debug_cache_event(
                "semantic_top_hit",
                query=query,
                user_id=user_id,
                matched_question=entity.get("question", ""),
                scope=entity.get("scope", ""),
                owner=entity.get("user_id", ""),
                distance=distance,
                threshold=L1_SEMANTIC_DISTANCE_THRESHOLD,
                accepted=distance <= L1_SEMANTIC_DISTANCE_THRESHOLD,
            )
            if not _is_usable_cached_answer(answer):
                _debug_cache_event(
                    "miss_semantic_uncacheable_answer",
                    query=query,
                    user_id=user_id,
                    matched_question=entity.get("question", ""),
                    distance=distance,
                )
                return None
            if distance > L1_SEMANTIC_DISTANCE_THRESHOLD:
                _debug_cache_event(
                    "miss_semantic_threshold",
                    query=query,
                    user_id=user_id,
                    distance=distance,
                    threshold=L1_SEMANTIC_DISTANCE_THRESHOLD,
                )
                return None
            return {
                "answer": answer,
                "matched_question": entity.get("question", ""),
                "level": "L1_SEMANTIC", # 标记为语义匹配
                "distance": distance,
            }
        except Exception as exc:
            _debug_cache_event("lookup_error", query=query, user_id=user_id, error=str(exc))
            print(f"SemanticCache get_cache failed: {exc}")
            return None

    @property
    def available(self) -> bool:
        return self._available
    #这段代码是一个文本标准化（Normalization）函数，用于将用户输入的问题转换成统一的格式，以提高语义缓存的匹配准确率
    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().lower().split())


  #_query_one 方法是一个辅助工具函数，它的作用是从 Milvus 向量数据库中精确查找并返回第一条匹配的记录
    def _query_one(self, filter_expr: str) -> dict[str, Any] | None:
        try:
            rows = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=filter_expr,
                output_fields=["question", "answer", "scope", "user_id"],
                limit=1,
            )
            if rows:
                return rows[0]
            return None
        except Exception:
            return None

    def _ensure_collection(self) -> None:
        from pymilvus import DataType

        if self._client.has_collection(COLLECTION_NAME):
            return

        schema = self._client.create_schema()
        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("question", DataType.VARCHAR, max_length=2048)
        schema.add_field("question_norm", DataType.VARCHAR, max_length=2048)
        schema.add_field("answer", DataType.VARCHAR, max_length=8192)
        schema.add_field("scope", DataType.VARCHAR, max_length=16)
        schema.add_field("user_id", DataType.VARCHAR, max_length=128)
        schema.add_field("enabled", DataType.INT8)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        #创建一个用于配置向量索引参数的对象
        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",#索引字段
            index_type="IVF_FLAT",#索引类型 适用场景 中等规模数据
            metric_type="COSINE",#用于指定计算两个向量之间相似度或距离的具体算法：余弦相似度
            params={"nlist": 256},#nlist 表示将向量空间分成多少个簇（聚类中心）
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )


semantic_cache = SemanticCache()
