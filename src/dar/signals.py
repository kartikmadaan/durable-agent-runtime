from typing import Any
from .journal import Event, append, next_seq


def send_signal(run_id: str, name: str, data: Any) -> None:
    append(Event(run_id, next_seq(run_id), "signal", name, {"data": data}))
