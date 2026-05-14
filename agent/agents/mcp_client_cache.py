import asyncio
import inspect
import time
from collections.abc import Callable, Iterable
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.core.resilience import (
    ErrorCode,
    coerce_tool_call_output,
    log_dependency_event,
    retry_async,
)


class LazyMCPTools:
    def __init__(
        self,
        connections: dict[str, Any],
        allowed_tool_names: Iterable[str],
        *,
        client_factory: Callable[..., Any] = MultiServerMCPClient,
        interceptors_factory: Callable[[], list[Any]] | None = None,
    ) -> None:
        self._connections = connections
        self._allowed_tool_names = set(allowed_tool_names)
        self._client_factory = client_factory
        self._interceptors_factory = interceptors_factory
        self._lock = asyncio.Lock()
        self._client: Any = None
        self._tools: list[Any] | None = None

    async def get_tools(self) -> list[Any]:
        if self._tools is not None:
            return self._tools

        async with self._lock:
            if self._tools is not None:
                return self._tools

            client_kwargs: dict[str, Any] = {"connections": self._connections}
            if self._interceptors_factory is not None:
                client_kwargs["tool_interceptors"] = self._interceptors_factory()

            client = self._client_factory(**client_kwargs)
            start = time.perf_counter()
            attempts = 1
            try:
                all_tools, attempts = await retry_async(
                    client.get_tools,
                    attempts=2,
                    base_delay=0.2,
                    retryable_codes={
                        ErrorCode.TIMEOUT,
                        ErrorCode.NETWORK_ERROR,
                        ErrorCode.MCP_INIT_FAILED,
                    },
                )
                duration_ms = int((time.perf_counter() - start) * 1000)
                log_dependency_event(
                    dependency="mcp",
                    operation="get_tools",
                    status="success",
                    duration_ms=duration_ms,
                    attempts=attempts,
                    extra={"allowed_tool_names": sorted(self._allowed_tool_names)},
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                log_dependency_event(
                    dependency="mcp",
                    operation="get_tools",
                    status="error",
                    duration_ms=duration_ms,
                    attempts=attempts,
                    error_code=ErrorCode.MCP_INIT_FAILED.value,
                    detail=str(exc),
                    extra={"allowed_tool_names": sorted(self._allowed_tool_names)},
                )
                await self._close_client(client)
                raise RuntimeError(f"MCP tool initialization failed: {exc}") from exc

            tools = [
                _install_schema_validation(tool)
                for tool in all_tools
                if getattr(tool, "name", None) in self._allowed_tool_names
            ]

            self._client = client
            self._tools = tools
            return tools

    async def close(self) -> None:
        client = self._client
        self._client = None
        self._tools = None
        if client is None:
            return

        await self._close_client(client)

    async def _close_client(self, client: Any) -> None:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is None:
            return

        result = close()
        if inspect.isawaitable(result):
            await result


def _install_schema_validation(tool: Any) -> Any:
    if getattr(tool, "_mcp_result_schema_validation_installed", False):
        return tool

    tool_name = getattr(tool, "name", "unknown_mcp_tool")

    original_invoke = getattr(tool, "invoke", None)
    if callable(original_invoke):
        def invoke_with_schema(*args: Any, **kwargs: Any) -> Any:
            output = original_invoke(*args, **kwargs)
            return coerce_tool_call_output(output, tool_name=tool_name)

        object.__setattr__(tool, "invoke", invoke_with_schema)

    original_run = getattr(tool, "run", None)
    if callable(original_run):
        def run_with_schema(*args: Any, **kwargs: Any) -> Any:
            output = original_run(*args, **kwargs)
            return coerce_tool_call_output(output, tool_name=tool_name)

        object.__setattr__(tool, "run", run_with_schema)

    original_ainvoke = getattr(tool, "ainvoke", None)
    if callable(original_ainvoke):
        async def ainvoke_with_schema(*args: Any, **kwargs: Any) -> Any:
            output = await original_ainvoke(*args, **kwargs)
            return coerce_tool_call_output(output, tool_name=tool_name)

        object.__setattr__(tool, "ainvoke", ainvoke_with_schema)

    object.__setattr__(tool, "_mcp_result_schema_validation_installed", True)
    return tool
