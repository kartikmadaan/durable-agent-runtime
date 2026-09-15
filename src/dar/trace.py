from contextlib import contextmanager
import os
import time
from typing import Any
from .journal import history

_TOTAL: dict[str, float | int] = {"prompt_tokens": 0, "completion_tokens": 0, "wall_ms": 0.0}


@contextmanager
def span(name: str, **attrs: Any):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = (time.perf_counter() - t0) * 1000
        _TOTAL["wall_ms"] = round(float(_TOTAL["wall_ms"]) + dt, 2)
        if os.getenv("DAR_QUIET") != "1":
            print(f"[span] {name} {attrs} {dt:.0f}ms")


def record_usage(usage: dict[str, Any] | None) -> None:
    if usage:
        _TOTAL["prompt_tokens"] = int(_TOTAL["prompt_tokens"]) + int(usage.get("prompt_tokens") or 0)
        _TOTAL["completion_tokens"] = int(_TOTAL["completion_tokens"]) + int(
            usage.get("completion_tokens") or 0
        )


def totals(run_id: str | None = None) -> dict[str, float | int]:
    if run_id is None:
        return dict(_TOTAL)
    prompt_tokens = 0
    completion_tokens = 0
    wall_ms = 0.0
    for e in history(run_id):
        if e.type == "activity_result":
            wall_ms += float(e.payload.get("latency_ms", 0.0))
            res = e.payload.get("result")
            if isinstance(res, dict) and isinstance(res.get("usage"), dict):
                prompt_tokens += int(res["usage"].get("prompt_tokens", 0))
                completion_tokens += int(res["usage"].get("completion_tokens", 0))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "wall_ms": round(wall_ms, 2),
    }
