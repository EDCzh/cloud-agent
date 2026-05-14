import asyncio
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.agents.mcp_client_cache import LazyMCPTools
from agent.core.resilience import (
    ToolStatus,
    make_success_result,
    result_to_json,
    validate_mcp_tool_result_json,
)
from agent.core.resilience.schema import ToolResultEnvelope


class SchemaValidationTests(unittest.TestCase):
    def test_standard_result_round_trips_through_pydantic_json(self):
        result = make_success_result(
            tool_name="query_user_orders",
            data={"orders": []},
            message="ok",
        )

        payload = json.loads(result_to_json(result))

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"], {"orders": []})
        self.assertEqual(payload["message"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["fallback"]["used"], False)
        self.assertEqual(payload["meta"]["tool_name"], "query_user_orders")

    def test_legacy_result_is_normalized_without_validating_data_payload(self):
        raw = json.dumps(
            {
                "status": "ok",
                "data": {"unexpected_nested_shape": object().__class__.__name__},
            }
        )

        payload = json.loads(validate_mcp_tool_result_json(raw, tool_name="legacy_tool"))

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["message"], "")
        self.assertEqual(payload["fallback"], {"used": False, "source": None, "reason": None})
        self.assertEqual(payload["meta"]["tool_name"], "legacy_tool")

    def test_invalid_result_becomes_fallback(self):
        payload = json.loads(validate_mcp_tool_result_json("not-json", tool_name="bad_tool"))

        self.assertEqual(payload["status"], "fallback")
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(payload["fallback"]["used"], True)
        self.assertEqual(payload["fallback"]["source"], "schema_validator")
        self.assertEqual(payload["meta"]["tool_name"], "bad_tool")

    def test_schema_model_can_be_used_directly_by_tools(self):
        result = ToolResultEnvelope(
            status=ToolStatus.PARTIAL,
            data={"items": [1, 2, 3]},
            message="partial",
            meta={"tool_name": "direct_tool"},
        )

        payload = json.loads(result.model_dump_json())

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["items"], [1, 2, 3])


@dataclass
class FakeTool:
    name: str
    raw_result: str

    def invoke(self, *args, **kwargs):
        return self.raw_result

    async def ainvoke(self, *args, **kwargs):
        await asyncio.sleep(0)
        return self.raw_result


class FakeMCPClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def get_tools(self):
        return [
            FakeTool("valid_tool", json.dumps({"status": "success", "data": [], "message": "ok"})),
            FakeTool("invalid_tool", "plain text"),
        ]


class MCPToolSchemaWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_lazy_mcp_tools_validates_tool_outputs(self):
        cache = LazyMCPTools(
            {},
            {"valid_tool", "invalid_tool"},
            client_factory=FakeMCPClient,
        )

        valid_tool, invalid_tool = await cache.get_tools()

        valid_payload = json.loads(valid_tool.invoke({}))
        invalid_payload = json.loads(await invalid_tool.ainvoke({}))

        self.assertEqual(valid_payload["status"], "success")
        self.assertEqual(valid_payload["meta"]["tool_name"], "valid_tool")
        self.assertEqual(invalid_payload["status"], "fallback")
        self.assertEqual(invalid_payload["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(invalid_payload["meta"]["tool_name"], "invalid_tool")


if __name__ == "__main__":
    unittest.main()
