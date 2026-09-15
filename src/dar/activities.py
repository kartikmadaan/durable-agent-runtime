import json
import os
import re
from typing import Any
import urllib.request
from .tools import TOOLS, dispatch_tool
from .trace import record_usage, span


def _fake_llm(messages: list[dict[str, Any]]) -> dict[str, Any]:
    goal = next((m["content"] for m in messages if m.get("role") == "user"), "")
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    fake_tokens = int(os.getenv("DAR_FAKE_TOKENS", "18"))
    usage = {"prompt_tokens": 32, "completion_tokens": fake_tokens}

    goal_lower = goal.lower()
    wants_kb = "indexed papers" in goal_lower or "universal approximation" in goal_lower
    expr_match = re.search(r"([0-9\(][0-9\(\)\+\-\*\/\s]*[\+\-\*\/][0-9\(\)\+\-\*\/\s]*[0-9\)])", goal)
    wants_charge = any(w in goal_lower for w in ("charge", "book", "flight", "pay"))

    if wants_kb and len(tool_msgs) == 0:
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_kb_0",
                    "name": "search_knowledge_base",
                    "arguments": json.dumps({"q": "universal approximation"}),
                }
            ],
            "usage": usage,
        }

    if expr_match and ((wants_kb and len(tool_msgs) == 1) or (not wants_kb and len(tool_msgs) == 0)):
        expr = expr_match.group(1).strip()
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_calc_0",
                    "name": "calculator",
                    "arguments": json.dumps({"expr": expr}),
                }
            ],
            "usage": usage,
        }

    if wants_charge and len(tool_msgs) == 0:
        amt_match = re.search(r"\$?([0-9]+)", goal)
        amount = amt_match.group(1) if amt_match else "100"
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_charge_0",
                    "name": "charge_card",
                    "arguments": json.dumps({"amount": amount}),
                }
            ],
            "usage": usage,
        }

    if tool_msgs:
        parts = []
        for tm in tool_msgs:
            data = json.loads(tm["content"])
            if "answer" in data:
                parts.append(str(data["answer"]))
            elif "result" in data:
                parts.append(str(data["result"]))
            elif "charged" in data:
                parts.append(f"Charged ${data['charged']}.")
            elif "error" in data:
                parts.append(f"Error: {data['error']}")
        return {"content": " ".join(parts), "tool_calls": [], "usage": usage}

    if "2018 world cup" in goal_lower:
        return {"content": "France won the 2018 World Cup.", "tool_calls": [], "usage": usage}

    return {"content": f"Completed: {goal}", "tool_calls": [], "usage": usage}


def llm_call(messages: list[dict[str, Any]]) -> dict[str, Any]:
    model = os.getenv("AGENT_MODEL", "qwen2.5:7b")
    with span("llm_call", model=model):
        if os.getenv("DAR_FAKE_LLM") == "1":
            out = _fake_llm(messages)
            record_usage(out["usage"])
            return out

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        clean_messages = []
        for m in messages:
            entry = {k: v for k, v in m.items() if v is not None}
            if entry.get("role") == "assistant" and "tool_calls" in entry:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in entry["tool_calls"]
                ]
            clean_messages.append(entry)

        body = json.dumps(
            {
                "model": model,
                "messages": clean_messages,
                "tools": TOOLS,
                "temperature": 0.1,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'ollama-local')}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        usage_raw = payload.get("usage") or {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
        }
        record_usage(usage)
        msg = payload["choices"][0]["message"]
        return {
            "content": msg.get("content") or "",
            "tool_calls": [
                {
                    "id": tc.get("id") or f"call_{i}",
                    "name": tc["function"]["name"],
                    "arguments": (
                        tc["function"]["arguments"]
                        if isinstance(tc["function"]["arguments"], str)
                        else json.dumps(tc["function"]["arguments"])
                    ),
                }
                for i, tc in enumerate(msg.get("tool_calls") or [])
            ],
            "usage": usage,
        }


def tool_call(name: str, arguments_json: str, idempotency_key: str = "") -> dict[str, Any]:
    with span("tool_call", tool=name):
        return dispatch_tool(name, arguments_json, idempotency_key=idempotency_key)
