from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .result import ErrorCode, ToolStatus, is_retryable_error


DEFAULT_FALLBACK: dict[str, Any] = {"used": False, "source": None, "reason": None}


class ToolResultEnvelope(BaseModel):
    """MCP tool result envelope.

    Only the outer contract is validated. ``data`` remains intentionally
    untyped so individual tools can evolve their payloads independently.
    """

    status: ToolStatus
    data: Any = None
    message: str = ""
    error: dict[str, Any] | None = None
    fallback: dict[str, Any] = Field(default_factory=lambda: DEFAULT_FALLBACK.copy())
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_legacy_status(cls, value: Any) -> Any:
        if isinstance(value, str):
            legacy_statuses = {
                "ok": ToolStatus.SUCCESS,
                "not_found": ToolStatus.FALLBACK,
                "failed": ToolStatus.ERROR,
                "failure": ToolStatus.ERROR,
            }
            return legacy_statuses.get(value.lower(), value)
        return value

    @field_validator("fallback", mode="before")
    @classmethod
    def normalize_fallback(cls, value: Any) -> Any:
        if value is None:
            return DEFAULT_FALLBACK.copy()
        return value


def make_tool_error_payload(code: ErrorCode | str, detail: str = "") -> dict[str, Any]:
    normalized_code = ErrorCode(code) if not isinstance(code, ErrorCode) else code
    return {
        "code": normalized_code.value,
        "retryable": is_retryable_error(normalized_code),
        "detail": detail,
    }


def make_schema_fallback_result(
    *,
    tool_name: str,
    reason: str,
    detail: str = "",
) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        status=ToolStatus.FALLBACK,
        data=None,
        message="Tool result schema validation failed; fallback result is used.",
        error=make_tool_error_payload(ErrorCode.VALIDATION_ERROR, detail),
        fallback={"used": True, "source": "schema_validator", "reason": reason},
        meta={"tool_name": tool_name},
    )


def _load_tool_result(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, ToolResultEnvelope):
        return raw_result.model_dump()
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str):
        parsed = json.loads(raw_result)
        if not isinstance(parsed, dict):
            raise TypeError("tool result JSON must be an object")
        return parsed
    raise TypeError(f"unsupported tool result type: {type(raw_result).__name__}")


def validate_tool_result_envelope(raw_result: Any, *, tool_name: str) -> ToolResultEnvelope:
    payload = _load_tool_result(raw_result)
    envelope = ToolResultEnvelope.model_validate(payload)
    if "tool_name" not in envelope.meta:
        envelope.meta["tool_name"] = tool_name
    return envelope


def validate_mcp_tool_result_json(raw_result: Any, *, tool_name: str) -> str:
    try:
        envelope = validate_tool_result_envelope(raw_result, tool_name=tool_name)
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
        envelope = make_schema_fallback_result(
            tool_name=tool_name,
            reason="invalid_tool_result_schema",
            detail=str(exc),
        )
    return envelope.model_dump_json()


def _text_from_content_blocks(content: list[Any]) -> str | None:
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        return None
    return "\n".join(parts)


def coerce_tool_call_output(raw_output: Any, *, tool_name: str) -> Any:
    """Validate tool output while preserving ToolMessage-like containers."""

    content = getattr(raw_output, "content", None)
    if isinstance(content, (str, dict, ToolResultEnvelope)):
        validated_content = validate_mcp_tool_result_json(content, tool_name=tool_name)
        model_copy = getattr(raw_output, "model_copy", None)
        if callable(model_copy):
            return model_copy(update={"content": validated_content})
        try:
            object.__setattr__(raw_output, "content", validated_content)
            return raw_output
        except Exception:
            return validated_content
    if isinstance(content, list):
        text_content = _text_from_content_blocks(content)
        if text_content is not None:
            validated_content = validate_mcp_tool_result_json(text_content, tool_name=tool_name)
            model_copy = getattr(raw_output, "model_copy", None)
            if callable(model_copy):
                return model_copy(update={"content": validated_content})
            try:
                object.__setattr__(raw_output, "content", validated_content)
                return raw_output
            except Exception:
                return validated_content

    if isinstance(raw_output, tuple) and len(raw_output) == 2:
        content_part, artifact = raw_output
        if isinstance(content_part, list):
            text_content = _text_from_content_blocks(content_part)
            if text_content is not None:
                return validate_mcp_tool_result_json(text_content, tool_name=tool_name), artifact
        if isinstance(content_part, (str, dict, ToolResultEnvelope)):
            return validate_mcp_tool_result_json(content_part, tool_name=tool_name), artifact

    return validate_mcp_tool_result_json(raw_output, tool_name=tool_name)
