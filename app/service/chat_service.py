import asyncio
import json
import sys
import os
import traceback

# 将项目根目录加入 sys.path，以便正确识别 agent 包
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent.core.workflow.graph_manager import AgentGraphManager
from agent.core.memory.memory_manager import MemoryManager
from infra.cache import semantic_cache

# Global variables for graph and memory
graph = None
memory = None


async def init_agent_system():
    global graph, memory
    if graph is None:
        print("🚀 初始化 Multi-Agent 图编排...")
        graph_manager = AgentGraphManager()
        graph = graph_manager.build_graph()

        print("🧠 初始化 Memory 系统...")
        from agent.config.settings import get_settings
        settings = get_settings()
        memory = MemoryManager(
            redis_url=settings.redis_url,
            redis_ttl=settings.redis_ttl,
            milvus_host=settings.milvus_host,
            milvus_port=settings.milvus_port,
            milvus_api_key=settings.milvus_api_key,
            embedding_api_key=settings.dashscope_api_key,
        )
        await memory.initialize()
        await semantic_cache.initialize()
        print("✅ Agent 系统初始化完成！")


async def _extract_memory_context(user_id: str, session_id: str, query: str) -> str:
    context_parts = []
    if memory and memory.short_term.available:
        history = await memory.short_term.get_messages(user_id, session_id)
        if history:
            recent_history = history[-10:] if len(history) > 10 else history
            context_parts.append("【近期对话历史】:")
            for msg in recent_history:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_parts.append(f"{role}: {msg['content']}")

    if memory and memory.long_term.available:
        prefs = await memory.long_term.retrieve_relevant(user_id, query)
        if prefs:
            context_parts.append("\n【用户长期偏好/背景】:")
            for p in prefs:
                context_parts.append(f"- {p}")

    return "\n".join(context_parts)


async def stream_chat(query: str, user_id: str, session_id: str):
    try:
        cache_hit = await semantic_cache.get_cache(query, user_id)
        if cache_hit:
            response_text = cache_hit["answer"]
            print(
                f"⚡ 语义缓存命中: {cache_hit['level']} distance={cache_hit['distance']:.4f} matched='{cache_hit['matched_question']}'"
            )
        else:
            print("🏃 进入 Agent 工作流推理...")
            mem_context = await _extract_memory_context(user_id, session_id, query)
            state = {
                "messages": [("user", query)],
                "user_id": user_id,
                "session_id": session_id,
                "memory_context": mem_context,
                "next_agent": "",
                "metadata": {}
            }
            config = {"configurable": {"user_id": user_id}}

            # 简化调用逻辑
            if hasattr(graph, 'ainvoke'):
                result = await graph.ainvoke(state, config=config)
            else:
                result = await asyncio.to_thread(
                    lambda: asyncio.run(graph.ainvoke(state, config=config))
                )

            response_text = result["messages"][-1].content

        # 保存短时记忆
        if memory and memory.short_term.available:
            turn = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": response_text},
            ]
            await memory.save_conversation(user_id, session_id, turn)

        # 流式返回大模型结果
        chunk_size = 5
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            yield f"data: {json.dumps({'content': chunk})}\n\n"
            await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        error_msg = f"处理请求时发生错误: {str(e)}"
        print(f"❌ {error_msg}")
        print(traceback.format_exc())

        # 向前端发送错误信息
        yield f"data: {json.dumps({'error': error_msg})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
