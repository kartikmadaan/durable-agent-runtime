import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from chaos import run_with_kill  # noqa: E402
from dar.runner import drive, start_run  # noqa: E402
from dar.signals import send_signal  # noqa: E402


class ChaosTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "journal.db"
        self.ledger_path = Path(self._tmp.name) / "ledger.log"
        self._saved_env = {
            k: os.environ.get(k)
            for k in (
                "DAR_DB_PATH",
                "DAR_LEDGER_PATH",
                "DAR_FAKE_LLM",
                "DAR_QUIET",
                "DAR_GATED_TOOLS",
                "MAX_TOKENS_PER_RUN",
                "DAR_FAKE_TOKENS",
            )
        }
        os.environ["DAR_DB_PATH"] = str(self.db_path)
        os.environ["DAR_LEDGER_PATH"] = str(self.ledger_path)
        os.environ["DAR_FAKE_LLM"] = "1"
        os.environ["DAR_QUIET"] = "1"

    def tearDown(self) -> None:
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_exactly_once_after_post_journal_crash(self) -> None:
        rid, rc = run_with_kill("Charge $75 to card", kill_after=2, before_journal=False)
        self.assertEqual(rc, 137)
        os.environ["DAR_GATED_TOOLS"] = ""
        out = drive(rid)
        self.assertEqual(out["status"], "done")
        self.assertIn("75", out["answer"])
        self.assertEqual(self.ledger_path.read_text(encoding="utf-8").count("charge:75"), 1)

    def test_exactly_once_after_pre_journal_crash(self) -> None:
        rid, rc = run_with_kill("Charge $90 to card", kill_after=2, before_journal=True)
        self.assertEqual(rc, 137)
        self.assertEqual(self.ledger_path.read_text(encoding="utf-8").count("charge:90"), 1)
        os.environ["DAR_GATED_TOOLS"] = ""
        out = drive(rid)
        self.assertEqual(out["status"], "done")
        self.assertIn("90", out["answer"])
        self.assertEqual(self.ledger_path.read_text(encoding="utf-8").count("charge:90"), 1)

    def test_gated_tool_suspends_and_resumes_on_signal(self) -> None:
        os.environ.pop("DAR_GATED_TOOLS", None)
        rid = start_run("Book flight for $200")
        first = drive(rid)
        self.assertEqual(first["status"], "suspended")
        self.assertFalse(self.ledger_path.exists())

        send_signal(rid, first["waiting_for"], "approved")
        second = drive(rid)
        self.assertEqual(second["status"], "done")
        self.assertEqual(self.ledger_path.read_text(encoding="utf-8").count("charge:200"), 1)

    def test_token_budget_abort(self) -> None:
        os.environ["MAX_TOKENS_PER_RUN"] = "10"
        os.environ["DAR_FAKE_TOKENS"] = "25"
        rid = start_run("Compute (3+4)*5.")
        out = drive(rid)
        self.assertEqual(out["status"], "budget_abort")


if __name__ == "__main__":
    unittest.main()
