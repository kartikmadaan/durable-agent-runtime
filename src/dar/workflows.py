import json
import os
from typing import Any
from .activities import llm_call, tool_call
from .context import WorkflowContext

SYSTEM = """You are a careful task agent. Use tools when they help.
When you have the final answer, reply with plain text and no tool calls.
Before any irreversible or costly action, you may be asked for human approval."""

MAX_STEPS = 8
GATED_TOOLS = {"charge_card", "http_post", "send_email"}


def _active_gated_tools() -> set[str]:
    override = os.getenv("DAR_GATED_TOOLS")
    if override is not None:
        return {t.strip() for t in override.split(",") if t.strip()}
    return GATED_TOOLS


def agent_loop(ctx: WorkflowContext, goal: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": goal},
    ]
    max_tokens = int(os.getenv("MAX_TOKENS_PER_RUN", "20000"))
    gated = _active_gated_tools()

    for _ in range(MAX_STEPS):
        turn = ctx.activity("llm_call", llm_call, messages)
        if int(ctx.totals()["completion_tokens"]) > max_tokens:
            return {"answer": "aborted: token budget exceeded", "status": "budget_abort"}

        messages.append(
            {
                "role": "assistant",
                "content": turn["content"] or "",
                "tool_calls": turn["tool_calls"] or None,
            }
        )

        if not turn["tool_calls"]:
            return {"answer": turn["content"], "status": "done"}

        for call in turn["tool_calls"]:
            name = call["name"]
            if name in gated:
                decision = ctx.wait_for_signal(f"approve:{call['id']}")
                if decision != "approved":
                    result = {"error": "rejected by human"}
                    messages.append(_tool_msg(call, result))
                    continue
            result = ctx.activity("tool_call", tool_call, name, call["arguments"])
            messages.append(_tool_msg(call, result))

    return {"answer": messages[-1].get("content", ""), "status": "max_steps"}


def _tool_msg(call: dict[str, Any], result: dict[str, Any]) -> dict[str, str]:
    return {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
