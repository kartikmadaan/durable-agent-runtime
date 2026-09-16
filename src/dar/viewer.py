import json
from .journal import history
from .trace import totals


def show(run_id: str) -> None:
    events = history(run_id)
    for e in events:
        head = f"#{e.seq:>3} {e.type:<16} {e.key:<20}"
        body = json.dumps(e.payload)
        if len(body) > 100:
            body = body[:97] + "..."
        print(f"{head} {body}")
    stats = totals(run_id)
    print(
        f"---\ntotals: prompt_tokens={stats['prompt_tokens']} "
        f"completion_tokens={stats['completion_tokens']} wall_ms={stats['wall_ms']}ms"
    )
