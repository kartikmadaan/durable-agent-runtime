from collections import defaultdict
import inspect
import os
import time
from typing import Any, Callable
from .journal import Event, append, history, next_seq


class Suspend(Exception):
    def __init__(self, signal_name: str):
        super().__init__(signal_name)
        self.signal_name = signal_name


class WorkflowContext:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._events = history(run_id)
        self._results: dict[str, Any] = {}
        self._signals: dict[str, Any] = {}
        for e in self._events:
            if e.type == "activity_result":
                self._results[e.key] = e.payload["result"]
            elif e.type == "signal":
                self._signals[e.key] = e.payload["data"]
        self._counter: dict[str, int] = defaultdict(int)

    def _key(self, name: str) -> str:
        # Workflow code must remain deterministic so call order maps to identical keys on replay.
        i = self._counter[name]
        self._counter[name] += 1
        return f"{name}#{i}"

    def _step_total(self) -> int:
        return sum(self._counter.values())

    def activity(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        key = self._key(name)
        if key in self._results:
            return self._results[key]

        if "idempotency_key" in inspect.signature(fn).parameters:
            kwargs = {**kwargs, "idempotency_key": f"{self.run_id}:{key}"}

        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        dt_ms = round((time.perf_counter() - t0) * 1000, 2)

        kill_before = os.getenv("DAR_KILL_BEFORE_JOURNAL")
        if kill_before is not None and self._step_total() >= int(kill_before):
            os._exit(137)

        payload: dict[str, Any] = {"result": result, "latency_ms": dt_ms}
        if name == "tool_call" and args:
            payload["tool"] = args[0]

        ev = Event(self.run_id, next_seq(self.run_id), "activity_result", key, payload)
        append(ev)
        self._events.append(ev)
        self._results[key] = result

        kill_after = os.getenv("DAR_KILL_AFTER")
        if kill_after is not None and self._step_total() >= int(kill_after):
            os._exit(137)

        return result

    def wait_for_signal(self, name: str) -> Any:
        if name in self._signals:
            return self._signals[name]
        raise Suspend(name)

    def totals(self) -> dict[str, float | int]:
        prompt_tokens = 0
        completion_tokens = 0
        wall_ms = 0.0
        for e in self._events:
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
