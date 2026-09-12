import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(".dar/journal.db")


@dataclass
class Event:
    run_id: str
    seq: int
    type: str
    key: str
    payload: dict
    ts: float = 0.0


def _db_path() -> Path:
    env_path = os.getenv("DAR_DB_PATH")
    return Path(env_path) if env_path else DB_PATH


def _conn() -> sqlite3.Connection:
    # shortcut: single-node SQLite WAL without worker leases, move to Postgres with per-run leases for multi-worker concurrency
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
               run_id  TEXT NOT NULL,
               seq     INTEGER NOT NULL,
               type    TEXT NOT NULL,
               key     TEXT NOT NULL DEFAULT '',
               payload TEXT NOT NULL,
               ts      REAL NOT NULL,
               PRIMARY KEY (run_id, seq)
           )"""
    )
    return conn


def append(ev: Event) -> None:
    ts = ev.ts if ev.ts > 0 else time.time()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO events (run_id, seq, type, key, payload, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (ev.run_id, ev.seq, ev.type, ev.key, json.dumps(ev.payload), ts),
        )
    finally:
        conn.close()


def history(run_id: str) -> list[Event]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT run_id, seq, type, key, payload, ts FROM events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return [Event(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5]) for r in rows]


def next_seq(run_id: str) -> int:
    conn = _conn()
    try:
        row = conn.execute("SELECT MAX(seq) FROM events WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    return (row[0] + 1) if row[0] is not None else 0
