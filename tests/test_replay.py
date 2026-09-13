import os
import tempfile
import unittest
from dar.context import Suspend, WorkflowContext
from dar.signals import send_signal


class ReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("DAR_DB_PATH")
        os.environ["DAR_DB_PATH"] = os.path.join(self._tmp.name, "journal.db")

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("DAR_DB_PATH", None)
        else:
            os.environ["DAR_DB_PATH"] = self._prev_db
        self._tmp.cleanup()

    def test_activity_memoized_across_replays(self) -> None:
        calls = 0

        def expensive_step(x: int) -> dict:
            nonlocal calls
            calls += 1
            return {"val": x * 2, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        ctx1 = WorkflowContext("run-1")
        self.assertEqual(ctx1.activity("step", expensive_step, 21)["val"], 42)
        self.assertEqual(calls, 1)

        ctx2 = WorkflowContext("run-1")
        self.assertEqual(ctx2.activity("step", expensive_step, 21)["val"], 42)
        self.assertEqual(calls, 1)
        self.assertEqual(ctx2.totals()["completion_tokens"], 5)

    def test_signal_suspend_and_resume(self) -> None:
        ctx1 = WorkflowContext("run-sig")
        with self.assertRaises(Suspend) as exc:
            ctx1.wait_for_signal("approve:call_1")
        self.assertEqual(exc.exception.signal_name, "approve:call_1")

        send_signal("run-sig", "approve:call_1", "approved")

        ctx2 = WorkflowContext("run-sig")
        self.assertEqual(ctx2.wait_for_signal("approve:call_1"), "approved")

    def test_tool_idempotency_key_deduplicates_external_ledger(self) -> None:
        from dar.activities import tool_call

        ledger_file = os.path.join(self._tmp.name, "ledger.log")
        os.environ["DAR_LEDGER_PATH"] = ledger_file
        try:
            res1 = tool_call("charge_card", '{"amount": "50"}', idempotency_key="run-x:tool_call#0")
            res2 = tool_call("charge_card", '{"amount": "50"}', idempotency_key="run-x:tool_call#0")
            self.assertEqual(res1["charged"], "50")
            self.assertTrue(res2.get("deduplicated"))
            with open(ledger_file, encoding="utf-8") as f:
                self.assertEqual(f.read().count("charge:50"), 1)
        finally:
            os.environ.pop("DAR_LEDGER_PATH", None)

    def test_http_ollama_wire_format_and_memoization(self) -> None:
        import io
        import json
        from unittest.mock import patch
        from dar.activities import llm_call

        http_calls = 0

        class FakeHTTPResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        def fake_urlopen(req, timeout=120):
            nonlocal http_calls
            http_calls += 1
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["model"], "qwen2.5:7b")
            self.assertIn("tools", body)
            resp_payload = {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc_1",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": {"expr": "6*7"},
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 12},
            }
            return FakeHTTPResponse(json.dumps(resp_payload).encode("utf-8"))

        prev_fake = os.environ.pop("DAR_FAKE_LLM", None)
        os.environ["DAR_QUIET"] = "1"
        try:
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                ctx1 = WorkflowContext("run-http")
                out1 = ctx1.activity("llm_call", llm_call, [{"role": "user", "content": "6*7"}])
                self.assertEqual(http_calls, 1)
                self.assertEqual(out1["tool_calls"][0]["name"], "calculator")
                self.assertEqual(json.loads(out1["tool_calls"][0]["arguments"])["expr"], "6*7")

                ctx2 = WorkflowContext("run-http")
                out2 = ctx2.activity("llm_call", llm_call, [{"role": "user", "content": "6*7"}])
                self.assertEqual(http_calls, 1)
                self.assertEqual(out2, out1)
                self.assertEqual(ctx2.totals()["prompt_tokens"], 40)
        finally:
            if prev_fake is not None:
                os.environ["DAR_FAKE_LLM"] = prev_fake


if __name__ == "__main__":
    unittest.main()
