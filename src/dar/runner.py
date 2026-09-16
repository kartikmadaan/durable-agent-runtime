from typing import Any
import uuid
from .context import Suspend, WorkflowContext
from .journal import Event, append, history, next_seq
from .workflows import agent_loop


def start_run(goal: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    append(Event(run_id, 0, "run_started", "", {"goal": goal}))
    return run_id


def drive(run_id: str) -> dict[str, Any]:
    hist = history(run_id)
    if not hist:
        raise ValueError(f"unknown run_id: {run_id}")

    for ev in reversed(hist):
        if ev.type == "run_finished":
            return ev.payload

    goal = next(e.payload["goal"] for e in hist if e.type == "run_started")
    ctx = WorkflowContext(run_id)
    try:
        result = agent_loop(ctx, goal)
    except Suspend as s:
        return {"status": "suspended", "waiting_for": s.signal_name}

    append(Event(run_id, next_seq(run_id), "run_finished", "", result))
    return result
