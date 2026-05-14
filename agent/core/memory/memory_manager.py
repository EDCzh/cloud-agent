"""协调短期和长期存储的统一内存管理器。

MemoryManager 是代理框架中所有内存操作的单一入口点。它委托给：

- :class:`ShortTermMemory`     – Redis，基于 TTL 的近期对话历史
- :class:`LongTermMemory`      – Milvus，基于向量的用户偏好/事实
- :class:`PreferenceExtractor` – 基于 LLM 的提取（在会话结束时注入）

当它们的服务不可用时，这两种存储后端都会优雅地降级。

会话生命周期
-----------------
1. **新会话，首次查询** – 调用 ``load_preferences(user_id)`` 从 Milvus 获取
   所有存储的偏好（缓存在调用者中）。
2. **每个查询轮次** – 调用 ``save_conversation(user_id, session_id, msgs)``
   将最近的消息持久化到 Redis。
3. **会话结束** – 调用 ``finalize_session(user_id, session_id, llm)``
   通过 LLM 提取偏好，保存到 Milvus，并清除 Redis。
"""

import logging
import os
import time
from typing import Any

from .short_term import COMPRESSION_THRESHOLD, SUMMARY_PREFIX, ShortTermMemory
from .long_term import LongTermMemory
from .preference_extractor import PreferenceExtractor

logger = logging.getLogger(__name__)

_TOP_K_PREFERENCES = 20   # max preferences to retrieve per user
_MAX_HISTORY_TURNS = 20   # max conversation turns used for extraction
_RECENT_RAW_MESSAGES = 8
_SUMMARY_MAX_INPUT_CHARS = 4000
_RAW_MESSAGE_LIST_LIMIT = 32

_SUMMARY_PROMPT_TEMPLATE = """\
你是云客服系统的短期记忆压缩器。请把下面的历史对话压缩为一段中文会话摘要，供后续客服 Agent 继续理解上下文。

要求：
- 只保留对继续对话有用的信息，不要复述寒暄。
- 重点保留用户目标、云产品、地域、实例/订单/工单/错误码、预算/规格/时间等约束。
- 保留已经尝试过的排查步骤、已经给出的关键结论、仍未解决的问题。
- 如果历史中有旧摘要，请把它和新对话合并为一份更新后的摘要。
- 不要编造历史中没有的信息。
- 控制在 200 字以内。

历史内容：
{conversation}

更新后的会话摘要：
"""


class MemoryManager:
    """协调短期 Redis 内存和长期 Milvus 内存。

    参数：
        redis_url: Redis 连接 URL。
        redis_ttl: 短期内存 TTL 秒数（默认 30 分钟）。
        milvus_host: Milvus 服务器主机名。
        milvus_port: Milvus 服务器端口。
        milvus_api_key: 可选的 Milvus 身份验证令牌。
        embedding_api_key: 用于 Milvus 嵌入的 DashScope API 密钥。

    示例::

        memory = MemoryManager(embedding_api_key="sk-...")
        await memory.initialize()

        # 每个查询轮次:
        await memory.save_conversation(user_id, session_id, messages)

        # 新会话 – 加载一次并缓存:
        prefs = await memory.load_preferences(user_id)

        # 会话结束:
        await memory.finalize_session(user_id, session_id, llm=chat_model)

        await memory.close()
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_ttl: int = 1800,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        milvus_api_key: str | None = None,
        embedding_api_key: str | None = None,
        memory_summary_model: str | None = None,
        preference_extract_model: str | None = None,
    ) -> None:
        self.short_term = ShortTermMemory(redis_url=redis_url, ttl=redis_ttl)
        self.long_term = LongTermMemory(
            host=milvus_host,
            port=milvus_port,
            api_key=milvus_api_key,
            embedding_api_key=embedding_api_key,
        )
        self._summary_api_key = embedding_api_key
        self._summary_model = memory_summary_model or os.getenv("MEMORY_SUMMARY_MODEL", "qwen-turbo")
        self._preference_model = preference_extract_model or os.getenv(
            "PREFERENCE_EXTRACT_MODEL", "qwen-turbo"
        )
        self._summary_llm: Any = None
        self._preference_llm: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    #initialize(): 并发初始化 Redis（短期记忆）和 Milvus（长期记忆）连接。
    async def initialize(self) -> None:
        """Initialize both storage backends concurrently."""
        import asyncio

        await asyncio.gather(
            self.short_term.initialize(),
            self.long_term.initialize(),
            return_exceptions=True,
        )
        logger.info(
            "MemoryManager ready – short_term=%s, long_term=%s",
            "✓" if self.short_term.available else "✗ (disabled)",
            "✓" if self.long_term.available else "✗ (disabled)",
        )

    async def close(self) -> None:
        """Close both storage backends."""
        import asyncio

        await asyncio.gather(
            self.short_term.close(),
            self.long_term.close(),
            return_exceptions=True,
        )
        logger.info("MemoryManager closed")

    # ------------------------------------------------------------------
    # Per-turn operations
    # ------------------------------------------------------------------
    #这是 MemoryManager 的核心方法之一，负责在每一轮对话后将用户的聊天记录保存到短期记忆（Redis）中。
    async def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Persist conversation messages to short-term (Redis) memory.

        Messages are appended to existing history. Only non-system messages
        are stored. Redis applies TTL automatically. When the message count
        exceeds the threshold, older messages are trimmed.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            messages: List of dicts with ``role`` and ``content`` keys.
        """
        non_system = [m for m in messages if m.get("role") != "system"]
        stored_count = await self.short_term.append_messages(
            user_id,
            session_id,
            non_system,
            max_messages=_RAW_MESSAGE_LIST_LIMIT,
        )
        await self._summarize_session_if_needed(user_id, session_id, stored_count)
        logger.debug(
            "[MEMORY] Appended %d messages (stored raw=%d) for %s:%s",
            len(non_system), stored_count, user_id, session_id,
        )

    async def _summarize_session_if_needed(
        self, user_id: str, session_id: str, raw_count: int
    ) -> None:
        """Compress older raw Redis List items into the rolling summary key."""
        if raw_count <= COMPRESSION_THRESHOLD:
            return

        raw_messages = await self.short_term.get_raw_messages(user_id, session_id)
        if len(raw_messages) <= COMPRESSION_THRESHOLD:
            return

        existing_summary = await self.short_term.get_summary(user_id, session_id)
        recent = raw_messages[-_RECENT_RAW_MESSAGES:]
        older = raw_messages[:-_RECENT_RAW_MESSAGES]
        summary_inputs = self._summary_text_to_messages(existing_summary) + older

        logger.info(
            "[MEMORY] Short-term summary triggered for %s:%s (raw=%d, older=%d)",
            user_id,
            session_id,
            len(raw_messages),
            len(older),
        )
        self.short_term.record_event(
            "memory_summary_triggered",
            "success",
            extra={
                "raw_message_count": len(raw_messages),
                "older_message_count": len(older),
                "recent_message_count": len(recent),
            },
        )
        start = time.perf_counter()
        summary_text = await self._generate_summary(summary_inputs)
        if not summary_text:
            logger.warning("[MEMORY] Summary failed; falling back to recent messages only")
            self.short_term.record_event(
                "memory_summary_failed",
                "fallback",
                duration_ms=int((time.perf_counter() - start) * 1000),
                fallback_used=True,
                extra={"fallback_kept_messages": _RECENT_RAW_MESSAGES},
            )
            await self.short_term.trim_messages(user_id, session_id, _RECENT_RAW_MESSAGES)
            return

        await self.short_term.save_summary(user_id, session_id, summary_text)
        await self.short_term.trim_messages(user_id, session_id, _RECENT_RAW_MESSAGES)
        self.short_term.record_event(
            "memory_summary_success",
            "success",
            duration_ms=int((time.perf_counter() - start) * 1000),
            extra={
                "summary_chars": len(summary_text),
                "compressed_message_count": len(older),
                "kept_message_count": len(recent),
            },
        )
        logger.info(
            "[MEMORY] Compressed %d older messages into short-term summary; kept %d recent messages",
            len(older),
            len(recent),
        )

    async def _generate_summary(self, messages: list[dict[str, Any]]) -> str | None:
        conversation = self._format_messages_for_summary(messages)
        if not conversation:
            return None

        llm = self._get_summary_llm()
        if llm is None:
            return None

        prompt = _SUMMARY_PROMPT_TEMPLATE.format(
            conversation=conversation[:_SUMMARY_MAX_INPUT_CHARS]
        )
        try:
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            summary = getattr(response, "content", str(response)).strip()
        except Exception as exc:
            logger.warning("[MEMORY] Short-term summary LLM call failed: %s", exc)
            return None

        if not summary:
            return None
        return summary.replace(SUMMARY_PREFIX, "").strip()

    def _get_summary_llm(self) -> Any | None:
        if self._summary_llm is not None:
            return self._summary_llm

        api_key = self._summary_api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            logger.warning("[MEMORY] DASHSCOPE_API_KEY missing; short-term summary disabled")
            return None

        try:
            from langchain_openai import ChatOpenAI

            self._summary_llm = ChatOpenAI(
                api_key=api_key,
                model=self._summary_model,
                base_url=os.getenv(
                    "BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
                temperature=0.1,
            )
            return self._summary_llm
        except Exception as exc:
            logger.warning("[MEMORY] Failed to initialize summary LLM: %s", exc)
            return None

    def _get_preference_llm(self) -> Any | None:
        if self._preference_llm is not None:
            return self._preference_llm

        api_key = self._summary_api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            logger.warning("[MEMORY] DASHSCOPE_API_KEY missing; preference extraction disabled")
            return None

        try:
            from langchain_openai import ChatOpenAI

            self._preference_llm = ChatOpenAI(
                api_key=api_key,
                model=self._preference_model,
                base_url=os.getenv(
                    "BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
                temperature=0.1,
            )
            return self._preference_llm
        except Exception as exc:
            logger.warning("[MEMORY] Failed to initialize preference extraction LLM: %s", exc)
            return None

    @staticmethod
    def _is_summary_message(message: dict[str, Any]) -> bool:
        return (
            message.get("role") == "system"
            and isinstance(message.get("content"), str)
            and message["content"].startswith(SUMMARY_PREFIX)
        )

    @staticmethod
    def _summary_text_to_messages(summary: str | None) -> list[dict[str, Any]]:
        if not summary:
            return []
        return [{"role": "system", "content": f"{SUMMARY_PREFIX}\n{summary}"}]

    @staticmethod
    def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            role = message.get("role", "unknown")
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            if role == "system" and content.startswith(SUMMARY_PREFIX):
                role_label = "已有摘要"
                content = content.removeprefix(SUMMARY_PREFIX).strip()
            elif role == "user":
                role_label = "用户"
            elif role == "assistant":
                role_label = "助手"
            else:
                role_label = str(role)
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)
#get_recent_messages(user_id, session_id): 从 Redis 读取最近的对话历史，供 Agent 生成回复时使用。
    async def get_recent_messages(
        self, user_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        """Return recent conversation messages from Redis.

        Args:
            user_id: User identifier.
            session_id: Session identifier.

        Returns:
            List of message dicts (may be empty if Redis is unavailable).
        """
        return await self.short_term.get_messages(user_id, session_id)

    # ------------------------------------------------------------------
    # Long-term preference operations
    # ------------------------------------------------------------------
#load_preferences(user_id, query, top_k): 根据语义查询从 Milvus 检索用户的历史偏好（如语言、预算），用于个性化回答。
    async def load_preferences(
        self,
        user_id: str,
        query: str = "用户偏好习惯个性特点",
        top_k: int = 3,
    ) -> list[str]:
        """Retrieve relevant preferences for a user from Milvus.

        Uses the caller-supplied query for semantic search so that the
        most contextually relevant preferences are returned first.
        Intended to be called once per new session (on the user's first
        query) and then cached by the caller.

        Args:
            user_id: User identifier.
            query: Semantic search query (use the user's first question
                   for best relevance).  Defaults to a broad Chinese phrase
                   that covers all preference types.
            top_k: Maximum number of preferences to return (default 3).

        Returns:
            List of preference strings (may be empty if Milvus unavailable).
        """
        if not self.long_term.available:
            logger.debug("[MEMORY] load_preferences skipped: Milvus unavailable")
            return []
        try:
            result = await self.long_term.retrieve_relevant(
                user_id=user_id,
                query=query,
                top_k=top_k,
            )
            logger.debug(
                "[MEMORY] load_preferences user='%s' query='%s' top_k=%d → %d results: %s",
                user_id, query[:40], top_k, len(result), result,
            )
            return result
        except Exception as exc:
            logger.warning("load_preferences failed for %s: %s", user_id, exc)
            return []
#save_preference(user_id, preference_type, value): 手动向 Milvus 存入一条特定的用户偏好。
    async def save_preference(self, user_id: str, preference_type: str, value: str) -> None:
        """Manually store a single user preference.
    
        Args:
            user_id: User identifier.
            preference_type: Category label (e.g. ``"language"``)
            value: Preference value (e.g. ``"Chinese"``)
        """
        await self.long_term.save_preference(user_id, preference_type, value)
 #background_extract(user_id, session_id, llm): 在会话进行中后台静默运行，利用 LLM 从当前对话中提取新偏好并存入 Milvus，不中断会话。
    async def background_extract(
        self, user_id: str, session_id: str, llm: Any | None = None
    ) -> list[str]:
        """Silently extract and save preferences without clearing Redis.
    
        Unlike ``finalize_session``, this method is designed to be called
        periodically during an active session (e.g., every N turns). It
        extracts new preferences from current Redis history and persists
        them to Milvus but leaves Redis intact so the session continues.
    
        Args:
            user_id: User identifier.
            session_id: Session identifier.
            llm: LangChain-compatible chat model for preference extraction.
        """
        if not self.long_term.available:
            return
        if not user_id or not session_id:
            return
    
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) < 4:  # need at least 2 full turns
            return

        preference_llm = self._get_preference_llm()
        if preference_llm is None:
            logger.warning("[MEMORY] Preference extraction skipped: LLM unavailable")
            return []
    
        recent = messages[-_MAX_HISTORY_TURNS:]
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )
    
        try:
            extractor = PreferenceExtractor(llm=preference_llm)
            existing = await self.load_preferences(user_id)
            new_items = await extractor.extract(
                conversation_text=conversation_text,
                existing=existing,
            )
            for item in new_items:
                await self.long_term.save_memory(
                    user_id=user_id,
                    content=item,
                    memory_type="preference",
                )
            if new_items:
                logger.info(
                    "[MEMORY] Background extract: saved %d new prefs for user '%s': %s",
                    len(new_items), user_id, new_items,
                )
                # Invalidate preference cache so next turn reloads fresh data
                return new_items
            else:
                logger.debug(
                    "[MEMORY] Background extract: no new prefs for user '%s'", user_id
                )
        except Exception as exc:
            logger.warning("[MEMORY] Background extract failed for %s: %s", user_id, exc)
    
        return []

    # ------------------------------------------------------------------
    # Session finalization
    # ------------------------------------------------------------------
    #finalize_session(user_id, session_id, llm): 会话收尾工作
    """
    1.调用 LLM 提取本轮会话产生的所有新偏好。
    2.去重后存入 Milvus（长期记忆）。
    3.清空 Redis 中的短期对话记录，释放空间。"""
    async def finalize_session(
        self, user_id: str, session_id: str, llm: Any | None = None
    ) -> None:
        """Finalize a session: extract preferences then clean up.

        Workflow:
        1. Read recent messages from Redis.
        2. Build conversation text from the last ``_MAX_HISTORY_TURNS`` turns.
        3. Use LLM (via :class:`PreferenceExtractor`) to extract new preferences.
        4. Load existing preferences from Milvus for deduplication.
        5. Save only genuinely new items to Milvus.
        6. Clear Redis short-term memory for this session.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            llm: LangChain-compatible chat model used for preference extraction.
        """
        if not user_id or not session_id:
            return

        # 1. Load recent conversation from Redis
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) < 2:
            logger.debug("Session too short, skipping extraction: %s:%s", user_id, session_id)
            await self.short_term.clear(user_id, session_id)
            return

        logger.info(
            "[MEMORY] Finalizing session %s:%s – %d messages in Redis history",
            user_id, session_id, len(messages),
        )

        # 2. Build conversation text (bounded to last N turns)
        recent = messages[-_MAX_HISTORY_TURNS:]
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )
        logger.debug(
            "[MEMORY] Conversation text sent to extractor (%d chars):\n%s",
            len(conversation_text), conversation_text[:600],
        )

        # 3. Extract preferences (LLM call)
        if self.long_term.available:
            preference_llm = self._get_preference_llm()
            if preference_llm is None:
                logger.warning("[MEMORY] Preference extraction skipped: LLM unavailable")
                await self.short_term.clear(user_id, session_id)
                return

            extractor = PreferenceExtractor(llm=preference_llm)
            existing = await self.load_preferences(user_id)
            logger.debug(
                "[MEMORY] Existing preferences (%d) for dedup: %s",
                len(existing), existing,
            )
            new_items = await extractor.extract(
                conversation_text=conversation_text,
                existing=existing,
            )

            # 4. Persist new items to Milvus
            for item in new_items:
                await self.long_term.save_memory(
                    user_id=user_id,
                    content=item,
                    memory_type="preference",
                )

            if new_items:
                logger.info(
                    "[MEMORY] Saved %d new preferences for user '%s': %s",
                    len(new_items), user_id, new_items,
                )
            else:
                logger.info("[MEMORY] No new preferences found for user '%s'", user_id)
        else:
            logger.info("[MEMORY] Milvus unavailable, skipping preference extraction")

        # 5. Clear Redis
        await self.short_term.clear(user_id, session_id)
        logger.info("[MEMORY] Short-term memory cleared for %s:%s", user_id, session_id)
