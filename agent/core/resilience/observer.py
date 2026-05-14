from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("cloud_agent.resilience")


def log_dependency_event(
    *,
    dependency: str,
    operation: str,
    status: str,
    duration_ms: int | None = None,
    attempts: int | None = None,
    error_code: str | None = None,
    fallback_used: bool | None = None,
    request_id: str | None = None,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    event = {
        "dependency": dependency,
        "operation": operation,
        "status": status,
        "duration_ms": duration_ms,
        "attempts": attempts,
        "error_code": error_code,
        "fallback_used": fallback_used,
        "request_id": request_id,
        "detail": detail,
        **(extra or {}),
    }
    clean_event = {key: value for key, value in event.items() if value is not None}
    logger.info(json.dumps(clean_event, ensure_ascii=False, default=str))
