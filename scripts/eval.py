import json
from dar.journal import history
from dar.runner import drive, start_run
from dar.trace import totals


def tool_sequence(run_id: str) -> list[str]:
    seq: list[str] = []
    for e in history(run_id):
        if e.type == "activity_result" and e.key.startswith("tool_call#"):
            tool_name = e.payload.get("tool")
            if tool_name:
                seq.append(str(tool_name))
    return seq


def run(path: str = "evals/goals.jsonl") -> None:
    with open(path, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    tool_acc = 0
    ans_acc = 0
    export = []
    for it in items:
        rid = start_run(it["goal"])
        out = drive(rid)
        called = tool_sequence(rid)
        stats = totals(rid)
        tools_ok = called == it["expect_tools"]
        ans_ok = all(s in (out.get("answer") or "") for s in it["answer_must_contain"])
        tool_acc += int(tools_ok)
        ans_acc += int(ans_ok)
        export.append(
            {
                "run_id": rid,
                "goal": it["goal"],
                "tools_called": called,
                "answer": out.get("answer"),
                "tools_ok": tools_ok,
                "ans_ok": ans_ok,
                "stats": stats,
            }
        )
    n = len(items)
    print(f"tool-call accuracy: {tool_acc}/{n}  answer accuracy: {ans_acc}/{n}")
    with open("evals/_judge_me.md", "w", encoding="utf-8") as f:
        for r in export:
            f.write(
                f"## Goal\n{r['goal']}\n\n"
                f"**Tools:** {r['tools_called']}\n\n"
                f"**Stats:** {r['stats']}\n\n"
                f"**Answer:**\n{r['answer']}\n\n---\n"
            )
    print("wrote evals/_judge_me.md")


if __name__ == "__main__":
    run()
