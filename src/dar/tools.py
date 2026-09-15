import json
import os
from pathlib import Path

LEDGER = Path(".dar/ledger.log")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expr": {"type": "string"}},
                "required": ["expr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the personal knowledge base and return a grounded answer.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "charge_card",
            "description": "Charge a payment amount to the user card.",
            "parameters": {
                "type": "object",
                "properties": {"amount": {"type": "string"}},
                "required": ["amount"],
            },
        },
    },
]

_FALLBACK_KB = {
    "universal approximation": (
        "Hornik et al. (1989) showed that standard multilayer feedforward networks with a single "
        "hidden layer and non-polynomial activation can approximate any continuous function on "
        "compact subsets of R^n to arbitrary accuracy."
    ),
    "write-ahead log": (
        "Write-ahead logging (WAL) ensures durability and atomicity by appending state mutations "
        "to sequential stable storage before applying them in memory."
    ),
}


def _ledger_path() -> Path:
    env_path = os.getenv("DAR_LEDGER_PATH")
    return Path(env_path) if env_path else LEDGER


def _calculator(expr: str) -> dict:
    # shortcut: eval with empty builtins restricted to arithmetic characters, replace with ast.parse for richer math
    allowed = set("0123456789+-*/(). ")
    if not expr or not set(expr) <= allowed:
        return {"error": "unsupported characters"}
    try:
        return {"result": eval(expr, {"__builtins__": {}}, {})}
    except Exception as e:
        return {"error": str(e)}


def _search_kb(q: str) -> dict:
    try:
        from rag.pipeline import query  # type: ignore[import-not-found]

        out = query(q, k=4)
        return {"answer": out["answer"], "citations": out["citations"]}
    except Exception:
        q_lower = q.lower()
        for key, text in _FALLBACK_KB.items():
            if key in q_lower:
                return {"answer": text, "citations": ["local-fallback-kb"]}
        return {"answer": f"No indexed entry matched '{q}'.", "citations": []}


def _charge_card(amount: str, idempotency_key: str = "") -> dict:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tag = f"idempotency_key={idempotency_key}" if idempotency_key else ""
    if tag and path.exists() and tag in path.read_text():
        return {"charged": amount, "deduplicated": True}
    line = f"charge:{amount}" + (f" {tag}\n" if tag else "\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
    return {"charged": amount}


def dispatch_tool(name: str, arguments_json: str, idempotency_key: str = "") -> dict:
    args = json.loads(arguments_json or "{}")
    if name == "calculator":
        return _calculator(str(args.get("expr", "")))
    if name == "search_knowledge_base":
        return _search_kb(str(args.get("q", "")))
    if name == "charge_card":
        return _charge_card(str(args.get("amount", "")), idempotency_key=idempotency_key)
    return {"error": f"unknown tool {name}"}
