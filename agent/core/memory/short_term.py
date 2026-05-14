"""Redis-backed short-term conversation memory."""

import json
import logging
import time
from typing import Any

try:
    from agent.core.resilience import log_dependency_event
except Exception:  # pragma: no cover - optional observability dependency
    log_dependency_event = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

COMPRESSION_THRESHOLD = 10
DEFAULT_TTL = 1800
KEY_PREFIX = "cloud_agent:v1:memory:short"
SUMMARY_PREFIX = "[会话摘要]"
DEFAULT_LIST_MAX_MESSAGES = 32

_APPEND_MESSAGES_LUA = """
local messages_key = KEYS[1]
local summary_key = KEYS[2]
local ttl = tonumber(ARGV[1])
local max_messages = tonumber(ARGV[2])

for i = 3, #ARGV do
    redis.call("RPUSH", messages_key, ARGV[i])
end

if max_messages and max_messages > 0 then
    redis.call("LTRIM", messages_key, -max_messages, -1)
end

redis.call("EXPIRE", messages_key, ttl)
redis.call("EXPIRE", summary_key, ttl)

return redis.call("LLEN", messages_key)
"""


class ShortTermMemory:
    """Short-term memory stored as Redis List + String keys.

    New storage layout:
    - cloud_agent:v1:memory:short:{user_id}:{session_id}:messages -> Redis List
    - cloud_agent:v1:memory:short:{user_id}:{session_id}:summary  -> Redis String

    Public reads still return list[dict] as [summary_message] + raw_messages.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = DEFAULT_TTL) -> None:
        self._redis_url = redis_url
        self._ttl = ttl
        self._client: Any = None
        self._available: bool = False

    async def initialize(self) -> None:
        """Connect to Redis; sets _available=False on failure."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            self._client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
                retry_on_timeout=True,
            )
            await self._client.ping()
            self._available = True
            logger.info("ShortTermMemory: Redis connected at %s", self._redis_url)
            self._log_event("connect", "success")
        except Exception as exc:
            logger.warning(
                "ShortTermMemory: Redis unavailable (%s) - short-term memory disabled.", exc
            )
            self._available = False
            self._log_event("connect", "fallback", detail=str(exc), fallback_used=True)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass

    async def get_messages(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        """Return [summary_message] + recent raw messages for a user/session."""
        if not self._available:
            return []

        start = time.perf_counter()
        try:
            summary, raw_messages = await self._read_summary_and_raw(user_id, session_id)
            messages: list[dict[str, Any]] = []
            if summary:
                messages.append({"role": "system", "content": f"{SUMMARY_PREFIX}\n{summary}"})
            messages.extend(raw_messages)
            self._log_event(
                "memory_read",
                "success",
                duration_ms=self._duration_ms(start),
                extra={
                    "message_count": len(messages),
                    "raw_message_count": len(raw_messages),
                    "has_summary": bool(summary),
                    "key_prefix": KEY_PREFIX,
                },
            )
            return messages
        except Exception as exc:
            logger.warning("ShortTermMemory.get_messages failed: %s", exc)
            self._available = False
            self._log_event(
                "memory_read",
                "fallback",
                duration_ms=self._duration_ms(start),
                detail=str(exc),
                fallback_used=True,
            )
            return []

    async def get_raw_messages(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        """Return recent raw user/assistant messages without the rolling summary."""
        if not self._available:
            return []
        try:
            values = await self._client.lrange(self._messages_key(user_id, session_id), 0, -1)
            return [msg for value in values if (msg := self._loads_message(value))]
        except Exception as exc:
            logger.warning("ShortTermMemory.get_raw_messages failed: %s", exc)
            self._available = False
            self._log_event("memory_read_raw", "fallback", detail=str(exc), fallback_used=True)
            return []

    async def get_summary(self, user_id: str, session_id: str) -> str | None:
        """Return the rolling summary text, without SUMMARY_PREFIX."""
        if not self._available:
            return None
        try:
            summary = await self._client.get(self._summary_key(user_id, session_id))
            return str(summary) if summary else None
        except Exception as exc:
            logger.warning("ShortTermMemory.get_summary failed: %s", exc)
            self._available = False
            self._log_event("memory_read_summary", "fallback", detail=str(exc), fallback_used=True)
            return None

    async def append_messages(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        max_messages: int = DEFAULT_LIST_MAX_MESSAGES,
    ) -> int:
        """Atomically append JSON messages to the Redis List via Lua."""
        if not self._available or not messages:
            return 0

        start = time.perf_counter()
        try:
            payloads = [json.dumps(message, ensure_ascii=False) for message in messages]
            length = await self._client.eval(
                _APPEND_MESSAGES_LUA,
                2,
                self._messages_key(user_id, session_id),
                self._summary_key(user_id, session_id),
                self._ttl,
                max_messages,
                *payloads,
            )
            stored_count = int(length)
            self._log_event(
                "memory_append",
                "success",
                duration_ms=self._duration_ms(start),
                extra={
                    "message_count": len(messages),
                    "stored_count": stored_count,
                    "max_messages": max_messages,
                    "key_prefix": KEY_PREFIX,
                },
            )
            return stored_count
        except Exception as exc:
            logger.warning("ShortTermMemory.append_messages failed: %s", exc)
            self._available = False
            self._log_event(
                "memory_append",
                "fallback",
                duration_ms=self._duration_ms(start),
                detail=str(exc),
                fallback_used=True,
            )
            return 0

    async def save_summary(self, user_id: str, session_id: str, summary: str) -> None:
        """Persist the rolling summary string."""
        if not self._available:
            return

        start = time.perf_counter()
        try:
            await self._client.set(self._summary_key(user_id, session_id), summary, ex=self._ttl)
            self._log_event(
                "memory_summary_write",
                "success",
                duration_ms=self._duration_ms(start),
                extra={"summary_chars": len(summary), "key_prefix": KEY_PREFIX},
            )
        except Exception as exc:
            logger.warning("ShortTermMemory.save_summary failed: %s", exc)
            self._available = False
            self._log_event(
                "memory_summary_write",
                "fallback",
                duration_ms=self._duration_ms(start),
                detail=str(exc),
                fallback_used=True,
            )

    async def trim_messages(self, user_id: str, session_id: str, max_messages: int) -> int:
        """Trim raw messages list to the newest max_messages entries."""
        if not self._available:
            return 0

        try:
            key = self._messages_key(user_id, session_id)
            pipe = self._client.pipeline()
            pipe.ltrim(key, -max_messages, -1)
            pipe.expire(key, self._ttl)
            pipe.expire(self._summary_key(user_id, session_id), self._ttl)
            pipe.llen(key)
            result = await pipe.execute()
            stored_count = int(result[-1])
            self._log_event(
                "memory_trim",
                "success",
                extra={"stored_count": stored_count, "max_messages": max_messages},
            )
            return stored_count
        except Exception as exc:
            logger.warning("ShortTermMemory.trim_messages failed: %s", exc)
            self._available = False
            self._log_event("memory_trim", "fallback", detail=str(exc), fallback_used=True)
            return 0

    async def save_messages(
        self, user_id: str, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Replace stored short-term memory using the new List + summary format."""
        if not self._available:
            return

        summary_msgs = [m for m in messages if self._is_summary_message(m)]
        raw_messages = [m for m in messages if not self._is_summary_message(m)]
        if len(raw_messages) > COMPRESSION_THRESHOLD:
            raw_messages = self._trim(raw_messages)

        try:
            messages_key = self._messages_key(user_id, session_id)
            summary_key = self._summary_key(user_id, session_id)
            pipe = self._client.pipeline()
            pipe.delete(messages_key)
            if raw_messages:
                pipe.rpush(
                    messages_key,
                    *[json.dumps(message, ensure_ascii=False) for message in raw_messages],
                )
            pipe.expire(messages_key, self._ttl)
            if summary_msgs:
                summary = str(summary_msgs[-1].get("content", "")).removeprefix(SUMMARY_PREFIX).strip()
                pipe.set(summary_key, summary, ex=self._ttl)
            else:
                pipe.delete(summary_key)
            await pipe.execute()
            self._log_event(
                "memory_replace",
                "success",
                extra={"message_count": len(raw_messages), "has_summary": bool(summary_msgs)},
            )
        except Exception as exc:
            logger.warning("ShortTermMemory.save_messages failed: %s", exc)
            self._available = False
            self._log_event("memory_replace", "fallback", detail=str(exc), fallback_used=True)

    async def append_message(
        self, user_id: str, session_id: str, role: str, content: str
    ) -> None:
        """Append a single message."""
        await self.append_messages(user_id, session_id, [{"role": role, "content": content}])

    async def clear(self, user_id: str, session_id: str) -> None:
        """Delete all short-term memory keys for a user/session."""
        if not self._available:
            return
        try:
            await self._client.delete(
                self._messages_key(user_id, session_id),
                self._summary_key(user_id, session_id),
                self._legacy_key(user_id, session_id),
            )
            self._log_event("memory_clear", "success", extra={"key_prefix": KEY_PREFIX})
        except Exception as exc:
            logger.error("ShortTermMemory.clear failed: %s", exc)
            self._log_event("memory_clear", "fallback", detail=str(exc), fallback_used=True)

    def record_event(
        self,
        operation: str,
        status: str,
        *,
        duration_ms: int | None = None,
        detail: str | None = None,
        fallback_used: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record a memory-related observability event."""
        self._log_event(
            operation,
            status,
            duration_ms=duration_ms,
            detail=detail,
            fallback_used=fallback_used,
            extra=extra,
        )

    @property
    def available(self) -> bool:
        """True if Redis is reachable."""
        return self._available

    async def _read_summary_and_raw(
        self, user_id: str, session_id: str
    ) -> tuple[str | None, list[dict[str, Any]]]:
        pipe = self._client.pipeline()
        pipe.get(self._summary_key(user_id, session_id))
        pipe.lrange(self._messages_key(user_id, session_id), 0, -1)
        summary, values = await pipe.execute()
        raw_messages = [msg for value in values if (msg := self._loads_message(value))]
        return (str(summary) if summary else None), raw_messages

    @staticmethod
    def _loads_message(value: str) -> dict[str, Any] | None:
        try:
            message = json.loads(value)
        except Exception:
            logger.warning("ShortTermMemory: skipped malformed message payload")
            return None
        if isinstance(message, dict):
            return message
        logger.warning("ShortTermMemory: skipped non-object message payload")
        return None

    @staticmethod
    def _messages_key(user_id: str, session_id: str) -> str:
        return f"{KEY_PREFIX}:{{{user_id}}}:{{{session_id}}}:messages"

    @staticmethod
    def _summary_key(user_id: str, session_id: str) -> str:
        return f"{KEY_PREFIX}:{{{user_id}}}:{{{session_id}}}:summary"

    @staticmethod
    def _legacy_key(user_id: str, session_id: str) -> str:
        return f"memory:short:{user_id}:{session_id}"

    @staticmethod
    def _is_summary_message(message: dict[str, Any]) -> bool:
        return (
            message.get("role") == "system"
            and isinstance(message.get("content"), str)
            and message["content"].startswith(SUMMARY_PREFIX)
        )

    @staticmethod
    def _trim(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep system messages plus the 8 most recent non-system messages."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        return system_msgs + other_msgs[-8:]

    @staticmethod
    def _duration_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    @staticmethod
    def _log_event(
        operation: str,
        status: str,
        *,
        duration_ms: int | None = None,
        detail: str | None = None,
        fallback_used: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if log_dependency_event is None:
            return
        log_dependency_event(
            dependency="redis_short_term_memory",
            operation=operation,
            status=status,
            duration_ms=duration_ms,
            detail=detail,
            fallback_used=fallback_used,
            extra=extra,
        )
