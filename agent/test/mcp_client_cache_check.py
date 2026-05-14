import asyncio
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.agents.mcp_client_cache import LazyMCPTools


@dataclass
class FakeTool:
    name: str


class FakeMCPClient:
    instances = []
    get_tools_calls = 0
    fail_next = False
    fail_count = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        FakeMCPClient.instances.append(self)

    async def get_tools(self):
        FakeMCPClient.get_tools_calls += 1
        await asyncio.sleep(0)
        if FakeMCPClient.fail_count > 0:
            FakeMCPClient.fail_count -= 1
            raise RuntimeError("MCP unavailable")
        if FakeMCPClient.fail_next:
            FakeMCPClient.fail_next = False
            raise RuntimeError("MCP unavailable")
        return [
            FakeTool("query_user_orders"),
            FakeTool("query_user_instances"),
            FakeTool("generate_ai_poster"),
        ]

    async def aclose(self):
        self.closed = True


class LazyMCPToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeMCPClient.instances.clear()
        FakeMCPClient.get_tools_calls = 0
        FakeMCPClient.fail_next = False
        FakeMCPClient.fail_count = 0

    async def test_get_tools_is_lazy_and_reused(self):
        cache = LazyMCPTools(
            {"cloud_billing": {"transport": "stdio"}},
            {"query_user_orders", "query_user_instances"},
            client_factory=FakeMCPClient,
            interceptors_factory=lambda: ["injector"],
        )

        first = await cache.get_tools()
        second = await cache.get_tools()

        self.assertIs(first, second)
        self.assertEqual([tool.name for tool in first], ["query_user_orders", "query_user_instances"])
        self.assertEqual(len(FakeMCPClient.instances), 1)
        self.assertEqual(FakeMCPClient.get_tools_calls, 1)
        self.assertEqual(FakeMCPClient.instances[0].kwargs["tool_interceptors"], ["injector"])

    async def test_concurrent_first_calls_initialize_once(self):
        cache = LazyMCPTools(
            {},
            {"query_user_orders"},
            client_factory=FakeMCPClient,
        )

        results = await asyncio.gather(cache.get_tools(), cache.get_tools(), cache.get_tools())

        self.assertTrue(all(result is results[0] for result in results))
        self.assertEqual(len(FakeMCPClient.instances), 1)
        self.assertEqual(FakeMCPClient.get_tools_calls, 1)

    async def test_failed_initialization_retries_and_succeeds(self):
        FakeMCPClient.fail_next = True
        cache = LazyMCPTools(
            {},
            {"query_user_orders"},
            client_factory=FakeMCPClient,
        )

        tools = await cache.get_tools()

        self.assertEqual([tool.name for tool in tools], ["query_user_orders"])
        self.assertEqual(len(FakeMCPClient.instances), 1)
        self.assertEqual(FakeMCPClient.get_tools_calls, 2)

    async def test_repeated_failed_initialization_is_not_cached(self):
        FakeMCPClient.fail_count = 2
        cache = LazyMCPTools(
            {},
            {"query_user_orders"},
            client_factory=FakeMCPClient,
        )

        with self.assertRaises(RuntimeError):
            await cache.get_tools()

        tools = await cache.get_tools()

        self.assertEqual([tool.name for tool in tools], ["query_user_orders"])
        self.assertEqual(len(FakeMCPClient.instances), 2)
        self.assertEqual(FakeMCPClient.get_tools_calls, 3)

    async def test_close_resets_cache_and_closes_client(self):
        cache = LazyMCPTools(
            {},
            {"query_user_orders"},
            client_factory=FakeMCPClient,
        )

        await cache.get_tools()
        client = FakeMCPClient.instances[0]
        await cache.close()
        await cache.get_tools()

        self.assertTrue(client.closed)
        self.assertEqual(len(FakeMCPClient.instances), 2)


if __name__ == "__main__":
    unittest.main()
