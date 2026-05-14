from __future__ import annotations

import json
import socket
import time
from enum import StrEnum
from typing import Any


class ToolStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FALLBACK = "fallback"
    ERROR = "error"


class ErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    HTTP_5XX = "HTTP_5XX"
    MCP_INIT_FAILED = "MCP_INIT_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN = "UNKNOWN"


RETRYABLE_ERROR_CODES = {
    ErrorCode.TIMEOUT,
    ErrorCode.NETWORK_ERROR,
    ErrorCode.HTTP_5XX,
    ErrorCode.MCP_INIT_FAILED,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def is_retryable_error(code: ErrorCode | str) -> bool:
    try:
        normalized = ErrorCode(code)
    except ValueError:
        return False
    return normalized in RETRYABLE_ERROR_CODES


def classify_exception(exc: BaseException, *, default: ErrorCode = ErrorCode.UNKNOWN) -> ErrorCode:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()

    if isinstance(exc, TimeoutError) or "timeout" in name or "timed out" in message:
        return ErrorCode.TIMEOUT
    if isinstance(exc, (ConnectionError, socket.timeout, OSError)):
        return ErrorCode.NETWORK_ERROR
    if "connection" in message or "network" in message or "unavailable" in message:
        return ErrorCode.NETWORK_ERROR
    return default


def classify_http_status(status_code: int) -> ErrorCode:
    if 500 <= status_code < 600:
        return ErrorCode.HTTP_5XX
    if status_code == 404:
        return ErrorCode.NOT_FOUND
    if status_code in {401, 403}:
        return ErrorCode.PERMISSION_DENIED
    if 400 <= status_code < 500:
        return ErrorCode.VALIDATION_ERROR
    return ErrorCode.UNKNOWN


def make_success_result(
    *,
    tool_name: str,
    data: Any = None,
    message: str = "",
    status: ToolStatus = ToolStatus.SUCCESS,
    fallback: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .schema import ToolResultEnvelope

    return ToolResultEnvelope(
        status=status,
        data=data,
        message=message,
        error=None,
        fallback=fallback or {"used": False, "source": None, "reason": None},
        meta={"tool_name": tool_name, **(meta or {})},
    ).model_dump()


def make_error_result(
    *,
    tool_name: str,
    code: ErrorCode | str,
    message: str,
    detail: str = "",
    fallback: dict[str, Any] | None = None,
    data: Any = None,
    meta: dict[str, Any] | None = None,
    status: ToolStatus = ToolStatus.ERROR,
) -> dict[str, Any]:
    from .schema import ToolResultEnvelope, make_tool_error_payload

    normalized_code = ErrorCode(code) if not isinstance(code, ErrorCode) else code
    return ToolResultEnvelope(
        status=status,
        data=data,
        message=message,
        error=make_tool_error_payload(normalized_code, detail),
        fallback=fallback or {"used": False, "source": None, "reason": None},
        meta={"tool_name": tool_name, **(meta or {})},
    ).model_dump()


def result_to_json(result: dict[str, Any]) -> str:
    from .schema import ToolResultEnvelope

    return ToolResultEnvelope.model_validate(result).model_dump_json()
