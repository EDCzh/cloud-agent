"""由 Milvus 向量数据库支持的长期内存。

用户偏好和关键事实作为密集向量嵌入进行存储。
检索使用余弦相似度搜索，并按 user_id 进行过滤，因此每个用户的记忆保持隔离。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_NAME = "long_term_memory"
EMBEDDING_DIM = 1536  

"""
用户说："我更喜欢中文界面"
   ↓
PreferenceExtractor 检测到偏好
   ↓
调用 save_preference("user123", "language", "Chinese")
   ↓
内部构造内容："User preference – language: Chinese"
   ↓
调用 save_memory("user123", content, memory_type="preference")
   ↓
生成文本嵌入向量（1536 维）
   ↓
插入 Milvus 向量数据库：
{
  "user_id": "user123",
  "content": "User preference – language: Chinese",
  "memory_type": "preference",
  "embedding": [0.1, 0.2, ..., 0.9]
}"""
class LongTermMemory:
    """用于用户偏好和事实的基于 Milvus 的长期内存。

    功能：
    - 通过 Milvus 进行密集向量搜索（余弦相似度）
    - 对 ``user_id`` 进行标量过滤，实现每用户隔离
    - 偏好助手：``save_preference(user_id, type, value)``
    - 优雅降级：如果 Milvus 不可用，操作将变为空操作

    用法::

        mem = LongTermMemory(embedding_api_key="sk-...")
        await mem.initialize()

        await mem.save_preference("user1", "language", "Chinese")
        results = await mem.retrieve_relevant("user1", "preferred language")
        await mem.close()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        api_key: str | None = None,
        embedding_api_key: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._api_key = api_key
        self._embedding_api_key = embedding_api_key
        self._client: Any = None
        self._embeddings: Any = None
        self._available: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to Milvus and ensure collection exists.

        Sets _available=False on failure (no exception raised).
        """
        try:
            await self._connect()
            self._available = True
            logger.info(
                "LongTermMemory: Milvus connected at %s:%s",
                self._host,
                self._port,
            )
            return
        except Exception as exc:
            logger.warning(
                "LongTermMemory: Milvus unavailable (%s) – long-term memory disabled.", exc
            )
            self._available = False

    async def close(self) -> None:
        """Close Milvus client."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
    ) -> None:
        """Embed and store a memory entry.

        Args:
            user_id: Owner of this memory.
            content: Text to embed and store.
            memory_type: Category label (e.g. "preference", "fact").
        """
        if not self._available:
            return
        try:
            embedding = await self._embeddings.aembed_query(content)
            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[
                    {
                        "user_id": user_id,
                        "content": content,
                        "memory_type": memory_type,
                        "embedding": embedding,
                    }
                ],
            )
            logger.debug(
                "LongTermMemory: stored %s memory for user %s: %s",
                memory_type, user_id, content[:60],
            )
        except Exception as exc:
            logger.error("LongTermMemory.save_memory failed: %s", exc)
    #这是一个便捷方法（Convenience Wrapper），用于保存用户的偏好设置到长期记忆中。
    async def replace_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str,
    ) -> None:
        """Replace memories of the same type for a user, then save the new value."""
        if not self._available:
            return
        try:
            safe_user = self._escape_filter_value(user_id)
            safe_type = self._escape_filter_value(memory_type)
            self._client.delete(
                collection_name=COLLECTION_NAME,
                filter=f'user_id == "{safe_user}" and memory_type == "{safe_type}"',
            )
        except Exception as exc:
            logger.warning("LongTermMemory.replace_memory delete failed: %s", exc)
        await self.save_memory(user_id, content, memory_type=memory_type)

    async def list_memories(
        self,
        user_id: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[str]:
        """List memories by scalar fields, without vector search."""
        if not self._available:
            return []
        try:
            return self._list_memories(user_id, memory_types=memory_types, limit=limit)
        except Exception as exc:
            logger.warning(
                "LongTermMemory.list_memories failed, retrying after reconnect: %s",
                exc,
            )
            try:
                await self._reconnect()
                return self._list_memories(user_id, memory_types=memory_types, limit=limit)
            except Exception as retry_exc:
                self._available = False
                logger.error("LongTermMemory.list_memories failed after reconnect: %s", retry_exc)
                return []

    async def save_preference(
        self, user_id: str, preference_type: str, value: str
    ) -> None:
        """Convenience wrapper for storing a user preference.

        Args:
            user_id: Owner of this preference.
            preference_type: Short label (e.g. "language", "city").
            value: Preference value (e.g. "Chinese", "Beijing").
        """
        content = f"User preference – {preference_type}: {value}"
        await self.save_memory(user_id, content, memory_type="preference")

    async def retrieve_relevant(
        self, user_id: str, query: str, top_k: int = 5
    ) -> list[str]:
        """Return the top-k most relevant memory entries for a query.

        Args:
            user_id: Filter results to this user only.
            query: Natural-language query text.
            top_k: Maximum number of results to return.

        Returns:
            List of content strings ordered by relevance.
        """
        if not self._available:
            return []
        try:
            query_embedding = await self._embeddings.aembed_query(query)
            results = self._client.search(
                collection_name=COLLECTION_NAME,
                data=[query_embedding],
                filter=f'user_id == "{user_id}"',
                limit=top_k,
                output_fields=["content", "memory_type"],
            )
            """
            results = [
    # 第一个查询向量的结果列表
    [
        {
            "id": 1001,
            "distance": 0.95,
            "entity": {
                "content": "User preference – language: Chinese",
                "memory_type": "preference"
            }
        },
        {
            "id": 1002,
            "distance": 0.87,
            "entity": {
                "content": "User preference – city: Beijing",
                "memory_type": "preference"
            }
        },
        {
            "id": 1003,
            "distance": 0.76,
            "entity": {
                "content": "User fact – works in IT industry",
                "memory_type": "fact"
            }
        }
    ]
]"""

            memories: list[str] = []
            for hits in results:
                for hit in hits:
                    memories.append(hit["entity"]["content"])
            return memories
        except Exception as exc:
            logger.warning(
                "LongTermMemory.retrieve_relevant failed, retrying after reconnect: %s",
                exc,
            )
            try:
                await self._reconnect()
                results = await self._search_memories(user_id, query, top_k)
                memories = []
                for hits in results:
                    for hit in hits:
                        memories.append(hit["entity"]["content"])
                return memories
            except Exception as retry_exc:
                self._available = False
                logger.error(
                    "LongTermMemory.retrieve_relevant failed after reconnect: %s",
                    retry_exc,
                )
            return []

    @property
    def available(self) -> bool:
        """True if Milvus is reachable."""
        return self._available

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        from pymilvus import MilvusClient  # type: ignore[import]
        from langchain_community.embeddings import DashScopeEmbeddings  # type: ignore[import]

        uri = f"http://{self._host}:{self._port}"
        connect_kwargs: dict[str, Any] = {"uri": uri}
        if self._api_key:
            connect_kwargs["token"] = self._api_key

        self._client = MilvusClient(**connect_kwargs)
        logger.info("[Init] Milvus client created; verifying collection...")

        if self._embeddings is None:
            self._embeddings = DashScopeEmbeddings(
                model="text-embedding-v2",
                dashscope_api_key=self._embedding_api_key,
            )
            logger.info("[Init] Embedding model initialized")

        self._ensure_collection()
        logger.info("[Init] Milvus collection checked/created")

    async def _reconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        await self._connect()
        self._available = True

    async def _search_memories(self, user_id: str, query: str, top_k: int) -> Any:
        query_embedding = await self._embeddings.aembed_query(query)
        return self._client.search(
            collection_name=COLLECTION_NAME,
            data=[query_embedding],
            filter=f'user_id == "{user_id}"',
            limit=top_k,
            output_fields=["content", "memory_type"],
        )

    def _list_memories(
        self,
        user_id: str,
        *,
        memory_types: list[str] | None,
        limit: int,
    ) -> list[str]:
        safe_user = self._escape_filter_value(user_id)
        filter_expr = f'user_id == "{safe_user}"'
        if memory_types:
            safe_types = [self._escape_filter_value(item) for item in memory_types]
            type_filter = " or ".join(f'memory_type == "{item}"' for item in safe_types)
            filter_expr = f"{filter_expr} and ({type_filter})"

        rows = self._client.query(
            collection_name=COLLECTION_NAME,
            filter=filter_expr,
            output_fields=["content", "memory_type"],
            limit=limit,
        )
        return [row["content"] for row in rows if row.get("content")]

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _ensure_collection(self) -> None:
        """Create the Milvus collection and index if they do not exist."""
        from pymilvus import DataType  # type: ignore[import]

        if self._client.has_collection(COLLECTION_NAME):
            return

        schema = self._client.create_schema()
        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("user_id", DataType.VARCHAR, max_length=128)
        schema.add_field("content", DataType.VARCHAR, max_length=2048)
        schema.add_field("memory_type", DataType.VARCHAR, max_length=64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            "embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )
        logger.info("LongTermMemory: created Milvus collection '%s'", COLLECTION_NAME)
