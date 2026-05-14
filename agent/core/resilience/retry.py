from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .result import ErrorCode, classify_exception

T = TypeVar("T")


def _should_retry(exc: BaseException, retryable_codes: set[ErrorCode]) -> bool:
    return classify_exception(exc) in retryable_codes


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 2,
    base_delay: float = 0.2,
    retryable_codes: set[ErrorCode] | None = None,
) -> tuple[T, int]:
    retryable = retryable_codes or {
        ErrorCode.TIMEOUT,
        ErrorCode.NETWORK_ERROR,
        ErrorCode.HTTP_5XX,
        ErrorCode.MCP_INIT_FAILED,
    }
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation(), attempt
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not _should_retry(exc, retryable):
                raise
            await asyncio.sleep(base_delay * attempt)
    raise last_exc or RuntimeError("retry_async failed without exception")


def retry_sync(
    operation: Callable[[], T],
    *,
    attempts: int = 2,
    base_delay: float = 0.2,
    retryable_codes: set[ErrorCode] | None = None,
) -> tuple[T, int]:
    retryable = retryable_codes or {
        ErrorCode.TIMEOUT,
        ErrorCode.NETWORK_ERROR,
        ErrorCode.HTTP_5XX,
        ErrorCode.MCP_INIT_FAILED,
    }
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not _should_retry(exc, retryable):
                raise
            time.sleep(base_delay * attempt)
    raise last_exc or RuntimeError("retry_sync failed without exception")
