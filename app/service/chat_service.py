import asyncio
import json
import os
import re
import sys
import time
import traceback
import uuid

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent.core.memory.memory_manager import MemoryManager
from agent.core.resilience import ErrorCode, classify_exception, log_dependency_event
from agent.core.workflow.graph_manager import AgentGraphManager
from infra.cache import semantic_cache

graph = None
memory = None

PRIVATE_REALTIME_KEYWORDS = (
    "订单",
    "账单",
    "实例",
    "监控",
    "用量",
    "消费",
    "费用",
    "余额",
    "发票",
    "最近",
    "我的",
    "名下",
    "海报",
    "推广",
    "生成",
    "定制",
    "小红书",
    "朋友圈",
    "公众号",
)

UNCACHEABLE_RESPONSE_MARKERS = (
    "这次查询没有完整完成",
    "建议稍后重试",
    "转人工",
    "输入的内容似乎是一串问号",
    "可能发送时出现了乱码",
    "未表达清楚问题",
)


def _should_bypass_semantic_cache(query: str) -> bool:
    """Avoid semantic-cache reuse for user-private or real-time data queries."""
    return any(keyword in query for keyword in PRIVATE_REALTIME_KEYWORDS)


def _is_cacheable_response(query: str, response: str) -> bool:
    normalized = query.strip()
    if not normalized or normalized.count("?") >= max(3, len(normalized) // 2):
        return False
    return not any(marker in response for marker in UNCACHEABLE_RESPONSE_MARKERS)


def _extract_explicit_memory_items(query: str) -> list[tuple[str, str]]:
    """Capture simple explicit memory instructions without waiting for LLM extraction."""
    text = query.strip()
    if not text:
        return []

    stop_values = {"什么", "啥", "谁", "吗", "呢", "多少"}
    items: list[tuple[str, str]] = []
    patterns = [
        (
            r"(?:你|助手|AI|ai|机器人)(?:的?名字)?(?:叫|是|名叫)([\u4e00-\u9fffA-Za-z0-9_-]{1,20})",
            "explicit_assistant_name",
            "assistant_name",
        ),
        (
            r"(?:我|本人)(?:的?名字)?(?:叫|是|名叫)([\u4e00-\u9fffA-Za-z0-9_-]{1,20})",
            "explicit_user_name",
            "user_name",
        ),
    ]

    for pattern, memory_type, label in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip(" ，。！？,.!?:：；;、")
        if value and value not in stop_values:
            items.append((memory_type, f"{label}: {value}"))

    return items

    stop_values = {"什么", "啥", "谁", "吗", "呢", "多少"}
    items: list[tuple[str, str]] = []
    patterns = [
        (r"(?:你|助手|AI|ai|机器人)(?:的?名字)?(?:叫|是|名叫)([\u4e00-\u9fffA-Za-z0-9_-]{1,20})", "助手名字"),
        (r"(?:我|本人)(?:的?名字)?(?:叫|是|名叫)([\u4e00-\u9fffA-Za-z0-9_-]{1,20})", "用户名字"),
    ]

    for pattern, label in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip(" ，。！？,.!?:：；;、")
        if value and value not in stop_values:
            items.append(f"{label}: {value}")

    return items


def _is_memory_recall_query(query: str) -> bool:
    recall_keywords = ("记得", "还记得", "你叫", "我叫", "名字", "叫啥", "叫什么")
    return any(keyword in query for keyword in recall_keywords)


async def init_agent_system():
    global graph, memory
    if graph is None:
        print("Initializing Multi-Agent graph...")
        graph_manager = AgentGraphManager()
        graph = graph_manager.build_graph()

        print("Initializing Memory system...")
        from agent.config.settings import get_settings

        settings = get_settings()
        memory = MemoryManager(
            redis_url=settings.redis_url,
            redis_ttl=settings.redis_ttl,
            milvus_host=settings.milvus_host,
            milvus_port=settings.milvus_port,
            milvus_api_key=settings.milvus_api_key,
            embedding_api_key=settings.dashscope_api_key,
            memory_summary_model=settings.memory_summary_model,
            preference_extract_model=settings.preference_extract_model,
        )
        await memory.initialize()
        await semantic_cache.initialize()
        print("Agent system initialized.")


async def _extract_memory_context(user_id: str, session_id: str, query: str) -> str:
    context_parts = []
    if memory and memory.short_term.available:
        history = await memory.short_term.get_messages(user_id, session_id)
        if history:
            recent_history = history[-10:] if len(history) > 10 else history
            context_parts.append("[Recent conversation]")
            for msg in recent_history:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_parts.append(f"{role}: {msg['content']}")

    if memory and memory.long_term.available:
        prefs = await memory.long_term.retrieve_relevant(user_id, query)
        if _is_memory_recall_query(query):
            explicit_prefs = await memory.long_term.list_memories(
                user_id,
                memory_types=["explicit_assistant_name", "explicit_user_name"],
                limit=10,
            )
            prefs = list(dict.fromkeys(explicit_prefs + prefs))
        if prefs:
            context_parts.append("\n[用户长期记忆/偏好，请在回答中优先参考]")
            for pref in prefs:
                context_parts.append(f"- {pref}")

    return "\n".join(context_parts)


async def stream_chat(query: str, user_id: str, session_id: str):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    print(
        "[CHAT_DEBUG] "
        + json.dumps(
            {
                "event": "request_start",
                "request_id": request_id,
                "query": query,
                "user_id": user_id,
                "session_id": session_id,
            },
            ensure_ascii=False,
        )
    )
    try:
        cache_hit = None
        bypass_cache = _should_bypass_semantic_cache(query)
        if bypass_cache:
            print(
                "[CHAT_DEBUG] "
                + json.dumps(
                    {"event": "cache_bypass", "request_id": request_id, "reason": "private_realtime_query"},
                    ensure_ascii=False,
                )
            )
        else:
            try:
                cache_hit = await semantic_cache.get_cache(query, user_id)
            except Exception as exc:
                code = classify_exception(exc)
                log_dependency_event(
                    dependency="semantic_cache",
                    operation="get_cache",
                    status="fallback",
                    error_code=code.value,
                    fallback_used=True,
                    request_id=request_id,
                    detail=str(exc),
                )

        if cache_hit:
            response_text = cache_hit["answer"]
            print(
                "[CHAT_DEBUG] "
                + json.dumps(
                    {
                        "event": "cache_hit",
                        "request_id": request_id,
                        "level": cache_hit.get("level"),
                        "matched_question": cache_hit.get("matched_question"),
                        "distance": cache_hit.get("distance"),
                    },
                    ensure_ascii=False,
                )
            )
            log_dependency_event(
                dependency="semantic_cache",
                operation="get_cache",
                status="hit",
                request_id=request_id,
                extra={
                    "level": cache_hit.get("level"),
                    "matched_question": cache_hit.get("matched_question"),
                    "distance": cache_hit.get("distance"),
                },
            )
        else:
            print(
                "[CHAT_DEBUG] "
                + json.dumps(
                    {"event": "cache_miss", "request_id": request_id},
                    ensure_ascii=False,
                )
            )
            mem_context = await _extract_memory_context(user_id, session_id, query)
            state = {
                "messages": [("user", query)],
                "user_id": user_id,
                "session_id": session_id,
                "memory_context": mem_context,
                "next_agent": "",
                "metadata": {"request_id": request_id},
            }
            config = {"configurable": {"user_id": user_id, "request_id": request_id}}

            agent_start = time.perf_counter()
            try:
                if hasattr(graph, "ainvoke"):
                    result = await graph.ainvoke(state, config=config)
                else:
                    result = await asyncio.to_thread(
                        lambda: asyncio.run(graph.ainvoke(state, config=config))
                )
                response_text = result["messages"][-1].content
                print(
                    "[CHAT_DEBUG] "
                    + json.dumps(
                        {
                            "event": "agent_graph_success",
                            "request_id": request_id,
                            "duration_ms": int((time.perf_counter() - agent_start) * 1000),
                            "answer_prefix": response_text[:120],
                        },
                        ensure_ascii=False,
                    )
                )
                log_dependency_event(
                    dependency="agent_graph",
                    operation="ainvoke",
                    status="success",
                    duration_ms=int((time.perf_counter() - agent_start) * 1000),
                    request_id=request_id,
                )
            except Exception as exc:
                code = classify_exception(exc, default=ErrorCode.UNKNOWN)
                print(
                    "[CHAT_DEBUG] "
                    + json.dumps(
                        {
                            "event": "agent_graph_fallback",
                            "request_id": request_id,
                            "duration_ms": int((time.perf_counter() - agent_start) * 1000),
                            "error_code": code.value,
                            "detail": str(exc),
                        },
                        ensure_ascii=False,
                    )
                )
                log_dependency_event(
                    dependency="agent_graph",
                    operation="ainvoke",
                    status="fallback",
                    duration_ms=int((time.perf_counter() - agent_start) * 1000),
                    error_code=code.value,
                    fallback_used=True,
                    request_id=request_id,
                    detail=str(exc),
                )
                response_text = (
                    "这次查询没有完整完成。我已经保留了你的问题，建议稍后重试；"
                    "如果涉及订单、实例或账单等实时数据，也可以转人工进一步确认。"
                )

            if semantic_cache.available and not bypass_cache and _is_cacheable_response(query, response_text):
                try:
                    await semantic_cache.set_cache(query, response_text, user_id, scope="public")
                except Exception as exc:
                    code = classify_exception(exc)
                    log_dependency_event(
                        dependency="semantic_cache",
                        operation="set_cache",
                        status="fallback",
                        error_code=code.value,
                        fallback_used=True,
                        request_id=request_id,
                        detail=str(exc),
                    )

        if memory and memory.short_term.available:
            turn = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": response_text},
            ]
            try:
                await memory.save_conversation(user_id, session_id, turn)
                if memory.long_term.available:
                    explicit_items = _extract_explicit_memory_items(query)
                    for memory_type, item in explicit_items:
                        await memory.long_term.replace_memory(
                            user_id=user_id,
                            content=item,
                            memory_type=memory_type,
                        )
                    if explicit_items:
                        print(
                            "[CHAT_DEBUG] "
                            + json.dumps(
                                {
                                    "event": "explicit_memory_saved",
                                    "request_id": request_id,
                                    "items": explicit_items,
                                },
                                ensure_ascii=False,
                            )
                        )
                    asyncio.create_task(memory.extract_and_save_preferences(user_id, session_id))
            except Exception as exc:
                code = classify_exception(exc)
                log_dependency_event(
                    dependency="memory",
                    operation="save_conversation",
                    status="fallback",
                    error_code=code.value,
                    fallback_used=True,
                    request_id=request_id,
                    detail=str(exc),
                )

        chunk_size = 5
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i : i + chunk_size]
            yield f"data: {json.dumps({'content': chunk})}\n\n"
            await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'done': True})}\n\n"
        log_dependency_event(
            dependency="chat_service",
            operation="stream_chat",
            status="success",
            duration_ms=int((time.perf_counter() - start) * 1000),
            request_id=request_id,
        )

    except Exception as exc:
        code = classify_exception(exc)
        log_dependency_event(
            dependency="chat_service",
            operation="stream_chat",
            status="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error_code=code.value,
            request_id=request_id,
            detail=str(exc),
        )
        error_msg = "这次请求没有完整完成，请稍后重试；如果问题较紧急，可以转人工处理。"
        print(error_msg)
        print(traceback.format_exc())
        yield f"data: {json.dumps({'error': error_msg})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
