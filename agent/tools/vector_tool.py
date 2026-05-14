import os
import json
from dotenv import load_dotenv
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_milvus import Milvus
from pymilvus import connections
from langchain_core.tools import tool

from agent.core.resilience import (
    ToolStatus,
    classify_exception,
    log_dependency_event,
    make_error_result,
    make_success_result,
    result_to_json,
)

# ==============================================================================
# 修复 pymilvus 2.6.x 与 langchain-milvus 0.3.x 之间的兼容性问题
#这段代码实现了一个**“猴子补丁”（Monkey Patch），用于修复 pymilvus（Milvus 的 Python 客户端库）在特定版本或复杂环境下可能出现的连接获取失败**问题。
#简单来说，它是在给 Milvus 的连接管理器打一个“备用方案”
# ==============================================================================
original_fetch = connections._fetch_handler
def patched_fetch(alias):
    try:
        return original_fetch(alias)
    except Exception:
        from pymilvus.client.connection_manager import ConnectionManager
        mgr = ConnectionManager.get_instance()
        for mc in mgr._registry.values():
            if f"cm-{id(mc.handler)}" == alias:
                return mc.handler
        for mc in mgr._dedicated.values():
            if f"cm-{id(mc.handler)}" == alias:
                return mc.handler
        raise
connections._fetch_handler = patched_fetch
# ==============================================================================

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)
#用来存放 Milvus 客户端对象的“公共储物柜”
#目的 = 只连一次数据库，到处都能用（单例模式）。
#单例模式：确保一个类在整个程序运行期间，只有一个实例（对象），并提供一个全局访问点。
_milvus_instance = None

def _get_milvus_store():
    global _milvus_instance
    if _milvus_instance is not None:
        return _milvus_instance

    api_key = os.getenv("DASHSCOPE_API_KEY")
    milvus_host = os.getenv("MILVUS_HOST", "localhost")
    milvus_port = os.getenv("MILVUS_PORT", "19530")
    milvus_uri = f"http://{milvus_host}:{milvus_port}"

    print(f"🔌 [Init] 正在连接 Milvus 向量数据库: {milvus_uri}")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=api_key,
        model="text-embedding-v2"
    )

    _milvus_instance = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": milvus_uri},
        collection_name="cloud_product_docs",
        auto_id=True,
        drop_old=False
    )
    return _milvus_instance

@tool
def query_vector_db(query: str) -> str:
    """
    通过语义搜索查询云产品的说明文档（RAG）。
    当用户询问大段的概念、操作步骤、详细规则（例如：退款规则、什么是专有网络VPC、如何创建实例）时，使用此工具。
    """
    try:
        store = _get_milvus_store()
        results = store.similarity_search_with_score(query, k=3)
        """
        results = [
    (
        Document(
            page_content="VPC（Virtual Private Cloud）是专有网络...", 
            metadata={'source': 'ecs_network.md', 'product': 'VPC'}
        ), 
        0.95  # 相似度分数（越接近 1 或 0 取决于算法，通常 Milvus 余弦相似度越接近 1 越相似）
    ),
    (
        Document(
            page_content="VPC 支持跨可用区部署...", 
            metadata={'source': 'vpc_guide.md', 'zone': 'cn-beijing'}
        ), 
        0.88
    ),
    (
        Document(
            page_content="如何在 VPC 中创建交换机...", 
            metadata={'source': 'vswitch_doc.md'}
        ), 
        0.82
    )
]"""
        
        if not results:
            return result_to_json(
                make_success_result(
                    tool_name="query_vector_db",
                    data={"documents": []},
                    message="未在文档中检索到相关信息。",
                    status=ToolStatus.PARTIAL,
                )
            )
            return "未在文档中检索到相关信息。"

        formatted_results = []
        for i, (doc, score) in enumerate(results):
            #这行代码的作用是从文档的元数据中提取文件名，并去掉前面的路径，只保留最核心的文件名部分。
            source = os.path.basename(doc.metadata.get('source', 'Unknown'))
            content = doc.page_content.strip()
            formatted_results.append(f"【来源: {source}】\n{content}")
            
        answer = "\n\n".join(formatted_results)
        return result_to_json(
            make_success_result(
                tool_name="query_vector_db",
                data={"answer": answer, "documents": formatted_results},
                message="已完成向量检索。",
            )
        )
    except Exception as e:
        code = classify_exception(e)
        log_dependency_event(
            dependency="milvus",
            operation="query_vector_db",
            status="fallback",
            error_code=code.value,
            fallback_used=True,
            detail=str(e),
        )
        return result_to_json(
            make_error_result(
                tool_name="query_vector_db",
                code=code,
                message="向量知识库暂时没有检索成功，可基于其他可用知识源继续回答。",
                detail=str(e),
                fallback={"used": True, "source": "alternate_tool_or_static", "reason": "vector_search_failed"},
                status=ToolStatus.FALLBACK,
            )
        )
        return f"查询向量数据库时发生错误: {str(e)}"
