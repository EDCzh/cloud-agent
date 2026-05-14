import asyncio
import json
import unittest

from agent.core.resilience import ErrorCode, ToolStatus, make_error_result, retry_async


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_async_retries_retryable_error(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("timed out")
            return "ok"

        result, attempts = await retry_async(operation, attempts=2, base_delay=0)

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)

    async def test_retry_async_does_not_retry_non_retryable_error(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            await retry_async(operation, attempts=2, base_delay=0)

        self.assertEqual(calls, 1)

    def test_error_result_has_retryable_flag_and_fallback(self):
        result = make_error_result(
            tool_name="demo_tool",
            code=ErrorCode.TIMEOUT,
            message="temporary failure",
            fallback={"used": True, "source": "cache", "reason": "timeout"},
            status=ToolStatus.FALLBACK,
        )

        encoded = json.dumps(result, ensure_ascii=False)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["status"], "fallback")
        self.assertTrue(decoded["error"]["retryable"])
        self.assertEqual(decoded["fallback"]["source"], "cache")


if __name__ == "__main__":
    unittest.main()
