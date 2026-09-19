# durable-agent-runtime

A crash-consistent, durable-execution runtime for LLM agents built from first principles in Python. Runs locally against Ollama with zero external runtime dependencies.

## Overview

Most agent loops keep state in process memory: a crash or timeout mid-run loses progress or re-fires non-idempotent side effects. `durable-agent-runtime` separates the **deterministic orchestration loop** from **non-deterministic activities** behind an append-only SQLite write-ahead log (WAL).

```
                         goal / prompt
                              │
                              ▼
        ┌───────────────────────────────────────────────┐
        │  RUNNER (src/dar/runner.py)                    │
        │  - loads event history for run_id              │
        │  - drives agent_loop() under WorkflowContext   │
        │  - on Suspend: persist & exit (0-compute wait) │
        │  - on crash: fresh worker replays & resumes    │
        └───────────────────────┬───────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────┐
        │  WORKFLOW agent_loop() (DETERMINISTIC)         │
        │  ReAct: plan → act → observe → repeat          │
        │  no direct I/O; only calls ctx.activity/signal │
        └───────┬───────────────────────────────┬───────┘
                │ ctx.activity(...)             │ ctx.wait_for_signal(...)
                ▼                               ▼
   ┌────────────────────────┐       ┌────────────────────────┐
   │  ACTIVITIES (once-only)│       │  SIGNALS (HITL gate)   │
   │  - llm_call (Ollama)   │       │  approve:<call_id>     │
   │  - tool_call:          │       └───────────┬────────────┘
   │    * search_kb         │                   │
   │    * calculator        │                   │
   │    * charge_card       │                   │
   └───────────┬────────────┘                   │
               │ append event                   │ append event
               ▼                                ▼
        ┌───────────────────────────────────────────────┐
        │  JOURNAL (SQLite WAL, append-only event log)  │
        │  events(run_id, seq, type, key, payload, ts)  │
        └───────────────────────────────────────────────┘
```

## Durability Guarantees

1. **Persistence across crashes**: Every state transition (`run_started`, `activity_result`, `signal`, `run_finished`) is committed to an append-only SQLite WAL journal keyed by `(run_id, seq)`.
2. **Deterministic replay**: `agent_loop` performs no direct I/O. Re-executing a run folds over its recorded journal events and reconstructs identical in-memory message state before executing the next unrecorded step.
3. **Exactly-once side effects**: Activities are indexed deterministically per run (`llm_call#0`, `tool_call#0`, ...). On replay after a post-journal crash, recorded outputs are served from the journal without re-running the activity. For pre-journal crashes (process killed after an external side effect executes but before the SQLite write commits), `WorkflowContext` injects a deterministic `idempotency_key` (`<run_id>:<activity_key>`) into tools so external ledgers deduplicate retries.
4. **Zero-compute suspend/resume**: Irreversible tools (`charge_card`, `http_post`, `send_email`) call `ctx.wait_for_signal("approve:<call_id>")`, unwinding the process via `Suspend` and resuming from the journal once an external signal is recorded.

## Quickstart

Start Ollama with a tool-capable local model (`qwen2.5:7b` by default):

```bash
ollama serve
ollama pull qwen2.5:7b
pip install -e .
```

### 1. Run an agent workflow

```bash
python3 scripts/run_agent.py start "What do the indexed papers say about universal approximation? Then compute 12*12."
```

### 2. Human-in-the-loop (suspend & resume)

```bash
# Suspends before executing the gated charge_card tool
python3 scripts/run_agent.py start "Book a flight and charge $200 to my card"
# -> {'status': 'suspended', 'waiting_for': 'approve:<call_id>'}

# Send approval signal and resume
python3 scripts/run_agent.py signal <run_id> approve:<call_id> approved
python3 scripts/run_agent.py resume <run_id>
```

### 3. Chaos test (`SIGKILL` mid-run)

```bash
# Kill worker with exit code 137 right after step 2 (charge_card), then resume in a fresh worker
python3 scripts/chaos.py "Charge $75 to card" 2

# Kill worker after side effect executes but BEFORE journal commit; idempotency_key prevents double-charge
python3 scripts/chaos.py "Charge $90 to card" 2 --before-journal
```

### 4. Inspect run timeline & token/latency totals

```bash
python3 scripts/run_agent.py view <run_id>
```

### 5. Run trajectory evaluation & test suite

```bash
# Deterministic offline test suite (no GPU/Ollama required)
DAR_FAKE_LLM=1 PYTHONPATH=src python3 -m unittest discover -s tests -v

# Trajectory evaluation harness
python3 scripts/eval.py
```

## Prior Art & Production Trade-offs

This repository implements the core event-sourced replay mechanism behind [Temporal](https://temporal.io/), [DBOS](https://www.dbos.dev/), and [Restate](https://restate.dev/) in ~350 lines of standard-library Python. Moving from this single-node engine to a multi-worker distributed runtime requires:

- Replacing the single SQLite WAL file with a shared transactional store (e.g., PostgreSQL or a partitioned log) with per-run heartbeat leases so concurrent workers cannot drive the same `run_id`.
- Adding explicit workflow versioning (`patched()` markers) so changes to activity call order do not invalidate in-flight journals.
