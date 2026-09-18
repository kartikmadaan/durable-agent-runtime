import os
from pathlib import Path
import subprocess
import sys
from dar.runner import drive, start_run

SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")


def run_with_kill(goal: str, kill_after: int, before_journal: bool = False) -> tuple[str, int]:
    rid = start_run(goal)
    kill_var = "DAR_KILL_BEFORE_JOURNAL" if before_journal else "DAR_KILL_AFTER"
    py_path = os.environ.get("PYTHONPATH", "")
    full_py_path = f"{SRC_DIR}{os.pathsep}{py_path}" if py_path else SRC_DIR
    env = {
        **os.environ,
        kill_var: str(kill_after),
        "DAR_RUN_ID": rid,
        "DAR_GATED_TOOLS": "",
        "PYTHONPATH": full_py_path,
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from dar.runner import drive; drive(os.environ['DAR_RUN_ID'])",
        ],
        env=env,
        check=False,
    )
    return rid, proc.returncode


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: chaos.py <goal> <kill_step> [--before-journal]")
        sys.exit(1)
    before = "--before-journal" in sys.argv[3:]
    run_id, rc = run_with_kill(sys.argv[1], int(sys.argv[2]), before_journal=before)
    print(f"worker exited with code {rc} (run_id={run_id}), resuming...")
    os.environ["DAR_GATED_TOOLS"] = ""
    print(drive(run_id))
