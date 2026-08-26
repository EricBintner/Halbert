# Continuity Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [x]`) syntax for tracking.

**Goal:** Make Halbert's continuity mechanisms actually run — repair the two broken memory
seams, retire the dead one, and connect the 91% of `haloysius.memory_v2` that is installed,
working, and unwired.

**Architecture:** Halbert does not need a new memory system. It has eight stores and a
dependency (`haloysius.memory_v2`, 58 public capabilities) that already implements
supersession with bitemporal valid-time, semantic dedup at write, importance scoring, decay,
consolidation and reflection. Halbert wires four of those capabilities. This plan repairs
what is broken, deletes what never worked, and connects what already does — in that order,
because each phase makes the next one cheaper. Nothing here duplicates Plan A: Plan A owns
conversation memory (threads, receipts, FTS5 recall); this plan owns machine-state memory
(the ledger) and identity memory (the persona store).

**Tech Stack:** Python 3.10, pytest, SQLite (WAL), `haloysius.memory_v2`
(`TemporalStateLedger`, `PersonaMemoryStore`, `Consolidator`, `ImportanceScorer`).

**Evidence base:** `documentation/research/CONTINUITY-MECHANISM-AUDIT-2026-08-26.md`
(findings F1–F4, verified by execution) and
`documentation/research/CONTINUITY-DESIGN-STRATEGIES-2026-08-26.md` (rules R1/R2, §4).

**Worktree:** `~/.config/superpowers/worktrees/Halbert/continuity-wiring`, branch
`feat/continuity-wiring`, based on `main` at `481a58d`.

**Test command (from the worktree):**
```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest <path> -q -p no:cacheprovider
```
Run pytest from `halbert_core/`, never from the repo root — the root resolves `halbert_core`
as an outer namespace package and package-level imports fail.

**Phase 1 status (2026-08-26):** complete. Five commits on `feat/continuity-wiring`
(`a273309`, `7e543ef`, `a16dd06`, `a0119a5`, `faa5d2f`). Backend suite **1264 passed, 0
failed**. The "4 pre-existing failures" noted below were Plan A's worktree baseline from an
older commit; current `main` is fully green.

**Baseline to beat:** `tests/test_phase_d_integration.py` and
`tests/test_tool_calling_bridge.py` have 4 pre-existing failures on `main` (model-client
vision fallback, unrelated to this work). Do not try to fix them here; do not let the count
grow.

---

## Phase map

| Phase | What | Blocked by | Tasks |
|---|---|---|---|
| **1 — Repair** | Fix F2, retire F1's dead subsystem, resolve the vector-search warning | nothing — start now | 1–5 **DONE** |
| **2 — Plan A amendments** | Fold N1/N2/N3 into Plan A before A2 is written | Plan A A1 (done); must land before A2 | 6–8 |
| **3 — Connect** | Wire the semantic recall tier, scope enforcement, idle consolidation | Plan A A1–A13 | 9–12 |
| **4 — Quality** | Real `messages[]`, cumulative eval harness, abstain-and-probe | Plan A + Plan B §9.2 | 13–15 |

Phases 1 and 2 are fully specified below with code. Phases 3 and 4 are specified as scope,
files, acceptance criteria and design decisions, but **without line-exact diffs, because the
files they modify do not exist yet** — Plan A creates them. Writing exact diffs against
unwritten code would be fiction. Re-plan phases 3–4 against the real files once Plan A lands.

---

## File structure

**Phase 1 modifies:**
- `halbert_core/halbert_core/integrations/state_trackers.py` — 4 trackers, 8 broken
  `set_state()` calls → `record()`. Gains a shared `_record()` helper and a `persona_id`.
- `halbert_core/halbert_core/integrations/cognition_wiring.py:186,217` — pass a real ledger.
- `halbert_core/halbert_core/memory/__init__.py` — drop the retired exports.
- `halbert_core/halbert_core/dashboard/routes/memory.py` — drop `/stats` and `/search`.
- `Halbert/main.py` — drop the three memory CLI commands.
- `halbert_core/halbert_core/scheduler/executor.py:548-566` — `_log_outcome` loses its
  `MemoryWriter` call.

**Phase 1 deletes:**
- `halbert_core/halbert_core/memory/retrieval.py`
- `halbert_core/halbert_core/memory/writer.py`

**Phase 1 creates:**
- `halbert_core/tests/test_state_trackers_ledger.py`
- `halbert_core/tests/test_memory_retirement.py`

---

## Phase 1 — Repair

### Task 1: Ledger helper and the disk tracker

`TemporalStateLedger` has no `set_state`. Its real signature is
`record(persona_id, subject, predicate, object, source, confidence=1.0, priority='medium')`.
Recording a new value for an existing `(persona_id, subject, predicate)` automatically closes
the previous triple's `valid_to` — that is the supersession mechanism
`CONTINUITY-DESIGN-STRATEGIES` §4.3 called for.

**Files:**
- Modify: `halbert_core/halbert_core/integrations/state_trackers.py`
- Test: `halbert_core/tests/test_state_trackers_ledger.py` (new)

- [x] **Step 1: Write the failing test**

Create `halbert_core/tests/test_state_trackers_ledger.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert state trackers write to the Haloysius TemporalStateLedger (audit F2)."""

import pytest

from halbert_core.integrations.state_trackers import (
    AdminPresenceTracker,
    DiskHealthTracker,
    ServiceStatusTracker,
    SystemResourceTracker,
)


@pytest.fixture
def ledger(tmp_path):
    """A real TemporalStateLedger on a temp db — never the shared default."""
    from haloysius.memory_v2 import get_state_ledger

    led = get_state_ledger(str(tmp_path / "ledger.db"))
    yield led
    led.close()


def _current(ledger, persona_id="halbert"):
    return {(t.subject, t.predicate): t.object for t in ledger.get_current(persona_id)}


class TestDiskHealthTracker:
    def test_update_health_records_a_triple(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert _current(ledger)[("disk:/dev/sda1", "disk_health")] == "healthy"

    def test_new_value_supersedes_the_old_one(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        t.update_health("/dev/sda1", "failing")
        cur = ledger.get_current("halbert")
        assert len(cur) == 1
        assert cur[0].object == "failing"
        hist = ledger.get_history("halbert", "disk:/dev/sda1", "disk_health")
        assert [h.object for h in hist] == ["healthy", "failing"]
        assert hist[0].valid_to is not None   # old value closed out
        assert hist[1].valid_to is None       # new value is live

    def test_source_carries_provenance(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert ledger.get_current("halbert")[0].source == "state_tracker:disk_health"

    def test_no_ledger_is_a_silent_noop(self):
        t = DiskHealthTracker()          # ledger=None
        t.update_health("/dev/sda1", "healthy")   # must not raise

    def test_a_broken_ledger_never_propagates(self, caplog):
        class Boom:
            def record(self, *a, **k):
                raise RuntimeError("db gone")

        t = DiskHealthTracker(ledger=Boom())
        t.update_health("/dev/sda1", "healthy")   # must not raise
        assert "disk" in caplog.text.lower()
```

- [x] **Step 2: Run it, expect failure**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_trackers_ledger.py -q -p no:cacheprovider
```
Expected: failures — `AttributeError: 'TemporalStateLedger' object has no attribute 'set_state'`.

- [x] **Step 3: Add the shared helper**

In `state_trackers.py`, immediately after the `logger = ...` line, insert:

```python
DEFAULT_PERSONA_ID = "halbert"


def _record(ledger, persona_id: str, subject: str, predicate: str,
            obj: str, source: str) -> None:
    """Write one state triple, never raising.

    ``TemporalStateLedger.record`` closes the previous triple for the same
    (persona_id, subject, predicate) automatically, so callers get supersession
    and a valid-time history for free.
    """
    if ledger is None:
        return
    try:
        ledger.record(persona_id, subject, predicate, obj, source)
    except Exception as e:
        logger.warning(f"Failed to record {subject}/{predicate}: {e}")
```

- [x] **Step 4: Rewrite `DiskHealthTracker`**

Replace `DiskHealthTracker.__init__` and its `sync_to_ledger` with:

```python
    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._disk_states: dict[str, str] = {}  # device -> health status

    def sync_to_ledger(self) -> None:
        for device, status in self._disk_states.items():
            _record(self._ledger, self._persona_id, f"disk:{device}",
                    "disk_health", status, "state_tracker:disk_health")
```

- [x] **Step 5: Run the disk tests**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_trackers_ledger.py::TestDiskHealthTracker -q -p no:cacheprovider
```
Expected: 5 passed.

- [x] **Step 6: Commit**

```bash
git add halbert_core/halbert_core/integrations/state_trackers.py halbert_core/tests/test_state_trackers_ledger.py
git commit -m "fix(continuity): disk tracker records to the state ledger

TemporalStateLedger has no set_state; the real API is record(). Recording a
new value closes the previous triple's valid_to, so supersession and the
valid-time history come for free."
```

---

### Task 2: The remaining three trackers

**Files:**
- Modify: `halbert_core/halbert_core/integrations/state_trackers.py`
- Test: `halbert_core/tests/test_state_trackers_ledger.py`

- [x] **Step 1: Add the failing tests**

Append to `tests/test_state_trackers_ledger.py`:

```python
class TestServiceStatusTracker:
    def test_records_and_supersedes(self, ledger):
        t = ServiceStatusTracker(ledger=ledger)
        t.update_status("nginx", "running")
        t.update_status("nginx", "stopped")
        cur = ledger.get_current("halbert")
        assert len(cur) == 1 and cur[0].object == "stopped"
        assert cur[0].subject == "service:nginx"
        assert cur[0].source == "state_tracker:service_status"

    def test_two_services_are_independent(self, ledger):
        t = ServiceStatusTracker(ledger=ledger)
        t.update_status("nginx", "running")
        t.update_status("smbd", "stopped")
        assert _current(ledger) == {
            ("service:nginx", "service_status"): "running",
            ("service:smbd", "service_status"): "stopped",
        }


class TestSystemResourceTracker:
    def test_records_three_predicates(self, ledger):
        t = SystemResourceTracker(ledger=ledger)
        t.update_resources(cpu=42.4, mem=61.6, load=1.234)
        assert _current(ledger) == {
            ("system", "cpu_load"): "42%",
            ("system", "memory_usage"): "62%",
            ("system", "load_average"): "1.23",
        }

    def test_resample_supersedes_each_predicate(self, ledger):
        t = SystemResourceTracker(ledger=ledger)
        t.update_resources(cpu=10.0, mem=20.0, load=0.5)
        t.update_resources(cpu=90.0, mem=80.0, load=4.0)
        assert len(ledger.get_current("halbert")) == 3
        assert _current(ledger)[("system", "cpu_load")] == "90%"


class TestAdminPresenceTracker:
    def test_set_and_clear(self, ledger):
        t = AdminPresenceTracker(ledger=ledger)
        t.set_admin("eric")
        assert _current(ledger)[("user", "admin_presence")] == "present"
        t.clear_admin()
        assert _current(ledger)[("user", "admin_presence")] == "absent"
        assert len(ledger.get_current("halbert")) == 1

    def test_update_from_turn_marks_present(self, ledger):
        t = AdminPresenceTracker(ledger=ledger)
        t.update_from_turn(persona_id="halbert", user_message="check nginx", ai_response="")
        assert _current(ledger)[("user", "admin_presence")] == "present"
```

- [x] **Step 2: Run, expect failure**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_trackers_ledger.py -q -p no:cacheprovider
```
Expected: the three new classes fail on `set_state`.

- [x] **Step 3: Rewrite the three trackers**

`ServiceStatusTracker`:

```python
    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._service_states: dict[str, str] = {}

    def sync_to_ledger(self) -> None:
        for service, status in self._service_states.items():
            _record(self._ledger, self._persona_id, f"service:{service}",
                    "service_status", status, "state_tracker:service_status")
```

`SystemResourceTracker`:

```python
    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._cpu_percent: float = 0.0
        self._mem_percent: float = 0.0
        self._load_avg: float = 0.0

    def sync_to_ledger(self) -> None:
        src = "state_tracker:system_resources"
        _record(self._ledger, self._persona_id, "system", "cpu_load",
                f"{self._cpu_percent:.0f}%", src)
        _record(self._ledger, self._persona_id, "system", "memory_usage",
                f"{self._mem_percent:.0f}%", src)
        _record(self._ledger, self._persona_id, "system", "load_average",
                f"{self._load_avg:.2f}", src)
```

`AdminPresenceTracker`:

```python
    def __init__(self, ledger=None, persona_id: str = DEFAULT_PERSONA_ID):
        self._ledger = ledger
        self._persona_id = persona_id
        self._admin_present: bool = False
        self._admin_user: str = ""

    def sync_to_ledger(self) -> None:
        _record(self._ledger, self._persona_id, "user", "admin_presence",
                "present" if self._admin_present else "absent",
                "state_tracker:admin_presence")
```

- [x] **Step 4: Run the full file**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_trackers_ledger.py -q -p no:cacheprovider
```
Expected: 12 passed.

- [x] **Step 5: Confirm no regression in the existing protocol tests**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_phase_d_integration.py -q -p no:cacheprovider
```
Expected: the same pre-existing failures as on `main`, no new ones. `TestStateTrackers`
constructs every tracker with no arguments, which still works.

- [x] **Step 6: Commit**

```bash
git add halbert_core/halbert_core/integrations/state_trackers.py halbert_core/tests/test_state_trackers_ledger.py
git commit -m "fix(continuity): service, resource, and presence trackers record to the ledger"
```

---

### Task 3: Give the trackers a real ledger

`register_halbert_state_trackers(ledger=None)` is called with no argument at
`cognition_wiring.py:186` and `:217`, so every `sync_to_ledger()` was a no-op even before the
API mismatch. It must default to a real ledger.

**Use a Halbert-owned db_path.** The shared default
(`~/.local/share/haloysius/state_ledger/state_ledger.db`) currently holds 55 rows from
Haloysius's human-persona demo trackers (`clothing_sm`, `location_sm` — "wearing a leather
apron"). Queries are `persona_id`-scoped so mixing is not a correctness bug, but Halbert's
machine-state audit trail should be its own file: its own backup, its own retention, its own
security surface.

**Files:**
- Modify: `halbert_core/halbert_core/integrations/state_trackers.py`
- Modify: `halbert_core/halbert_core/integrations/cognition_wiring.py`
- Test: `halbert_core/tests/test_state_trackers_ledger.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_state_trackers_ledger.py`:

```python
class TestRegistration:
    def test_default_ledger_path_is_halbert_owned(self):
        from halbert_core.integrations.state_trackers import default_ledger_path

        p = str(default_ledger_path())
        assert "halbert" in p and p.endswith("state_ledger.db")
        assert "haloysius/state_ledger" not in p   # not the shared human-persona db

    def test_register_wires_a_live_ledger(self, tmp_path, monkeypatch):
        import halbert_core.integrations.state_trackers as st

        monkeypatch.setattr(st, "default_ledger_path", lambda: tmp_path / "l.db")
        trackers = st.register_halbert_state_trackers()
        assert set(trackers) == {
            "disk_health", "service_status", "system_resources", "admin_presence"}
        for t in trackers.values():
            assert t._ledger is not None

        trackers["service_status"].update_status("nginx", "running")
        cur = trackers["service_status"]._ledger.get_current("halbert")
        assert [(t.subject, t.object) for t in cur] == [("service:nginx", "running")]

    def test_explicit_ledger_wins(self, ledger):
        import halbert_core.integrations.state_trackers as st

        trackers = st.register_halbert_state_trackers(ledger=ledger)
        assert all(t._ledger is ledger for t in trackers.values())
```

- [x] **Step 2: Run, expect failure**

Expected: `ImportError: cannot import name 'default_ledger_path'`.

- [x] **Step 3: Add `default_ledger_path` and default the ledger**

In `state_trackers.py`, after the `_record` helper:

```python
def default_ledger_path():
    """Halbert's own state-ledger db.

    Deliberately not the shared Haloysius default, which carries other
    personas' state; Halbert's machine-state audit trail is its own file.
    """
    from pathlib import Path

    p = Path.home() / ".local" / "share" / "halbert" / "state_ledger.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _default_ledger():
    """Open the Halbert state ledger, or return None if unavailable."""
    try:
        from haloysius.memory_v2 import get_state_ledger

        return get_state_ledger(str(default_ledger_path()))
    except Exception as e:
        logger.warning(f"State ledger unavailable, trackers will not record: {e}")
        return None
```

Then in `register_halbert_state_trackers`, replace the signature and add one line before the
`trackers = {...}` dict:

```python
def register_halbert_state_trackers(ledger=None, persona_id: str = DEFAULT_PERSONA_ID) -> dict:
```

```python
    if ledger is None:
        ledger = _default_ledger()
```

and pass `persona_id=persona_id` alongside `ledger=ledger` in all four constructor calls:

```python
    trackers = {
        "disk_health": DiskHealthTracker(ledger=ledger, persona_id=persona_id),
        "service_status": ServiceStatusTracker(ledger=ledger, persona_id=persona_id),
        "system_resources": SystemResourceTracker(ledger=ledger, persona_id=persona_id),
        "admin_presence": AdminPresenceTracker(ledger=ledger, persona_id=persona_id),
    }
```

- [x] **Step 4: Run**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_trackers_ledger.py -q -p no:cacheprovider
```
Expected: 15 passed.

- [x] **Step 5: Verify the seam end to end**

`cognition_wiring.py:186,217` call `register_halbert_state_trackers()` with no argument;
after this task that call now opens the real ledger. No edit is required there — confirm it:

```
cd <worktree> && grep -n "register_halbert_state_trackers()" halbert_core/halbert_core/integrations/cognition_wiring.py
```
Expected: two hits, lines ~186 and ~217, both unchanged and now live.

- [x] **Step 6: Commit**

```bash
git add halbert_core/halbert_core/integrations/state_trackers.py halbert_core/tests/test_state_trackers_ledger.py
git commit -m "feat(continuity): trackers default to a Halbert-owned state ledger

register_halbert_state_trackers() was always called with ledger=None, so every
sync_to_ledger() was a no-op. Default to a real ledger on Halbert's own db path
rather than the shared Haloysius one, which holds other personas' state."
```

---

### Task 4: Retire the file memory (audit F1)

`MemoryWriter` writes any dict; `MemoryRetrieval` scores only on `entry['text']` /
`entry['summary']`. The one real writer, `scheduler/executor.py:_log_outcome`, writes
neither, so every entry is unreadable forever while `write_action_outcome()` returns `True`.
The live memory root holds **0 entries** and neither file has a test. Plan A owns
conversation memory and Haloysius owns identity memory, so this subsystem has no remaining
job. Delete rather than repair.

**Files:**
- Delete: `halbert_core/halbert_core/memory/retrieval.py`, `halbert_core/halbert_core/memory/writer.py`
- Modify: `halbert_core/halbert_core/memory/__init__.py`,
  `halbert_core/halbert_core/dashboard/routes/memory.py`,
  `halbert_core/halbert_core/scheduler/executor.py`, `Halbert/main.py`
- Test: `halbert_core/tests/test_memory_retirement.py` (new)

- [x] **Step 1: Write the failing test**

Create `halbert_core/tests/test_memory_retirement.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The unreadable file-memory subsystem is gone (audit F1)."""

import importlib

import pytest


def test_writer_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("halbert_core.memory.writer")


def test_retrieval_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("halbert_core.memory.retrieval")


def test_memory_package_no_longer_exports_them():
    import halbert_core.memory as m

    assert "MemoryWriter" not in m.__all__
    assert "MemoryRetrieval" not in m.__all__
    assert "HybridMemorySystem" in m.__all__   # the eval/browser path stays


def test_hybrid_memory_still_importable():
    from halbert_core.memory import HybridMemorySystem, MemoryType, get_hybrid_memory  # noqa: F401


def test_scheduler_no_longer_references_the_writer():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "halbert_core" / "scheduler" / "executor.py"
    assert "MemoryWriter" not in src.read_text()
```

- [x] **Step 2: Run, expect failure**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_memory_retirement.py -q -p no:cacheprovider
```
Expected: 4 failures (the modules still import; `__all__` still lists them).

- [x] **Step 3: Delete the two modules**

```bash
cd <worktree>
git rm halbert_core/halbert_core/memory/retrieval.py halbert_core/halbert_core/memory/writer.py
```

- [x] **Step 4: Rewrite `memory/__init__.py`**

Replace the whole file with:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Memory for Halbert.

Conversation memory belongs to the thread store (``agents/conversation_sqlite.py``);
identity and semantic memory belong to Haloysius ``memory_v2``. What remains here is
the ChromaDB-backed HybridMemorySystem, which is eval- and browser-only
(``documentation/design/the-being.md`` §9) and is deliberately not on the agent path.

The file-backed MemoryWriter/MemoryRetrieval pair was removed 2026-08-26: the writer
imposed no schema and the reader scored only on ``text``/``summary``, so nothing ever
written could be read back. See
``documentation/research/CONTINUITY-MECHANISM-AUDIT-2026-08-26.md`` finding F1.
"""

from .hybrid import (
    HybridMemorySystem,
    Memory,
    MemoryType,
    get_hybrid_memory,
)

__all__ = [
    'HybridMemorySystem',
    'Memory',
    'MemoryType',
    'get_hybrid_memory',
]
```

- [x] **Step 5: Drop the `MemoryWriter` call from the scheduler**

In `halbert_core/halbert_core/scheduler/executor.py`, replace the body of `_log_outcome`
with a log line — the outcome is already persisted by the scheduler's own job store:

```python
    def _log_outcome(self, result: JobResult):
        """Record a job outcome.

        The file-backed MemoryWriter was removed (audit F1): it wrote entries that
        MemoryRetrieval could never return. Job outcomes live in the scheduler's own
        store; durable cross-session state belongs in the TemporalStateLedger.
        """
        logger.info(
            f"Job {result.job_id} outcome: success={result.success} "
            f"confidence={result.confidence} time={result.execution_time_s}s"
        )
```

- [x] **Step 6: Drop the dashboard endpoints**

In `halbert_core/halbert_core/dashboard/routes/memory.py`, delete the `get_memory_stats`
and `search_memory` handlers (the `/stats` and `/search` routes) and update the module
docstring to:

```python
"""
Memory management API routes.

The ChromaDB collection browser (self_* collections: self_hwmon, self_journald,
self_dbus, discoveries, ...) backing the Memory dashboard page. These were moved
here from routes/chat.py as part of the chat endpoint retirement (T4b.1).

The former /stats and /search endpoints sat on the file-backed MemoryRetrieval,
which was removed 2026-08-26 (audit F1) — it could never return anything written.
"""
```

- [x] **Step 7: Drop the CLI commands**

In `Halbert/main.py`, remove the `MemoryRetrieval` / `MemoryWriter` imports at lines ~45-46
and their `None` fallbacks at ~78-79, the three command functions that use them
(`cmd_memory_*`, around lines 491, 517, 534), their `argparse` subparser registrations, and
the two instantiations at ~1734-1738. Locate every site first:

```bash
cd <worktree> && grep -n "MemoryRetrieval\|MemoryWriter\|memory_retrieval\|mem_writer" Halbert/main.py
```

- [x] **Step 8: Run the retirement tests plus the suite**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_memory_retirement.py -q -p no:cacheprovider
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -5
```
Expected: 5 passed; whole suite shows only the 4 pre-existing failures.

- [x] **Step 9: Confirm nothing still imports the deleted modules**

```bash
cd <worktree> && grep -rn "memory.writer\|memory.retrieval\|MemoryWriter\|MemoryRetrieval" --include=*.py . | grep -v node_modules | grep -v tests/test_memory_retirement.py
```
Expected: no output.

- [x] **Step 10: Commit**

```bash
git add -A halbert_core/halbert_core/memory halbert_core/halbert_core/dashboard/routes/memory.py halbert_core/halbert_core/scheduler/executor.py Halbert/main.py halbert_core/tests/test_memory_retirement.py
git commit -m "refactor(memory): retire the unreadable file-backed memory

MemoryWriter imposed no schema; MemoryRetrieval scored only on text/summary, so
the scheduler's outcome entries could never be returned. Zero entries existed and
neither module had a test. Conversation memory is the thread store, identity
memory is Haloysius memory_v2."
```

---

### Task 5: Resolve the vector-search warning

A probe logged `numpy not installed. Vector search disabled.` while numpy 2.2.6 was
importable in the same interpreter. If Haloysius retrieval is silently falling back to
keyword matching, every semantic claim in the audit and in Phase 3 is weaker than stated.

**Files:**
- Test: `halbert_core/tests/test_haloysius_vector_search.py` (new)

- [x] **Step 1: Locate the warning**

```bash
cd /Volumes/4TB-BAD/Haloysius && grep -rn "numpy not installed" src/ | head
```

- [x] **Step 2: Reproduce and identify the failing import**

```bash
.venv/bin/python -c "
import warnings, traceback
try:
    import numpy; print('numpy OK', numpy.__version__)
except Exception: traceback.print_exc()
from haloysius.memory_v2 import get_state_ledger
"
```

- [x] **Step 3: Write a characterisation test**

Create `halbert_core/tests/test_haloysius_vector_search.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Haloysius semantic search is actually semantic, not a keyword fallback."""

import uuid

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.store import PersonaMemoryStore

    return PersonaMemoryStore(f"vs_{uuid.uuid4().hex[:8]}")


def _mem(store, text):
    from haloysius.memory_v2 import MemoryType, PersonaMemory

    return PersonaMemory(id=str(uuid.uuid4()), persona_id=store.persona_id,
                         memory_type=MemoryType.SEMANTIC, content=text)


def test_finds_a_paraphrase_with_no_shared_content_words(store):
    """Keyword matching cannot do this; embeddings can."""
    store.smart_add(_mem(store, "The admin prefers explicit valid users on every share"))
    hits = store.search("who is allowed to access the folder", k=3)
    assert hits, "semantic search returned nothing — vector search is likely disabled"
    assert "valid users" in hits[0].content
```

- [x] **Step 4: Run it**

```
cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_haloysius_vector_search.py -q -p no:cacheprovider
```

- [x] **Step 5: Act on the result**

- **Passes** → vector search works; the warning is cosmetic and comes from an optional
  submodule. Record that in the audit doc and move on.
- **Fails** → semantic retrieval is degraded to keyword. Fix the import in Haloysius (a
  separate repo at `/Volumes/4TB-BAD/Haloysius`), then re-run. Until it passes, treat the
  Phase 3 semantic tier as keyword-only and say so in the plan.

- [x] **Step 6: Commit**

```bash
git add halbert_core/tests/test_haloysius_vector_search.py
git commit -m "test(continuity): pin that Haloysius semantic search is semantic"
```

---

## Phase 2 — Plan A amendments

These belong to Plan A, not to this branch. Plan A's A1 has landed
(`c311f47`); **A2 has not been written**, which is the cheap moment. Each item costs minutes
inside a task being authored now and a migration plus re-derivation from raw message history
afterwards. Apply them in the `continuous-conversation` worktree.

### Task 6: N1 — date-stamp `Last said`

A2's own fixture stores `Last said: The share mounts from the laptop at //nas/media (v3.1
client)` — a present-tense claim about mutable state, retrieved six weeks later as
`retrieved_context[0]`. Rule R2: memory holds what cannot be re-observed; anything that can
be re-derived must carry its date so it cannot be quoted as current.

- [ ] Amend A2's `build_receipt` so the sixth line renders `Last said (YYYY-MM-DD): …`,
      using the timestamp of the message the sentence came from.
- [ ] Amend A2's `test_lines` expectation to
      `"Last said (2026-07-14): The share mounts from the laptop at //nas/media (v3.1 client)."`
- [ ] Amend `receipt_one_liner` and its test to carry the stamp through.
- [ ] Amend A8's `<continuity>` component text to add: *"Recalled details are past
      observations with dates. Verify current state before asserting it."*

### Task 7: N2 — `open_loops` as rows, not prose

The `Open loop:` line is the most valuable durable output of a thread and is trapped inside a
text blob, so nothing can ask *what is outstanding on this machine*. The extractor is being
written in A2; the row costs one insert now and a full re-parse later. This is the only
capability in the parity matrix that every surveyed system except Nūr also lacks.

- [ ] Add to A1's migration:

```sql
CREATE TABLE IF NOT EXISTS open_loops (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id          TEXT NOT NULL,
    text               TEXT NOT NULL,
    domains            TEXT NOT NULL DEFAULT '[]',
    created_at         REAL NOT NULL,
    due_at             REAL,
    status             TEXT NOT NULL DEFAULT 'open',
    closed_by_thread_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_open_loops_status ON open_loops(status);
```

- [ ] In A2/A6b, when the receipt's `Open loop:` line is not `none recorded`, insert a row
      with the thread's `topic_domains`.
- [ ] Add store helpers `add_open_loop`, `list_open_loops(status='open', domains=None)`,
      `close_open_loop(id, closed_by_thread_id)`.
- [ ] In A5's continuity hint, add one line when open loops exist in the thread's domains:
      `Open loops (2): monitor disk for 24h · confirm guest access is off`. Cap at two, ~40
      tokens. This is cross-session continuity with no retrieval machinery at all.

### Task 8: N3 — record thread state into the ledger

*(Revised from the design doc's `superseded_by` column — Phase 1 Task 1 shows the ledger
already supersedes automatically.)*

- [ ] At thread close in A6b, for each `(subject, predicate, object)` the thread established,
      call `ledger.record(persona_id, subject, predicate, object, source=thread_id)`.
- [ ] Source the triples from the receipt's `Files written` and `Commands` lines plus the
      thread's canonical entities — never from `Last said` prose.
- [ ] Skip `ephemeral` threads and `origin=terminal` content, matching the spec's existing
      rule for the Haloysius episodic line.

**Depends on Phase 1 Task 3** (the ledger must actually be reachable).

---

## Phase 3 — Connect what is installed

Blocked on Plan A A1–A13. Specified as scope and acceptance criteria; the files do not exist
yet, so re-plan the steps against real code when Plan A lands.

### Task 9: Wire `PersonaMemoryStore.search()` as the semantic recall tier

The spec defers this as future work. It is not: `search()` works today and returned the right
memory first on all three audit probes. Rule R1 — *no memory write path merges without its
read path* — makes this a blocker on Plan A writing the Haloysius episodic line at all.

- **Files:** the recall path created by Plan A A3/A6b.
- **Scope:** after FTS5 receipt recall returns no strong match, query
  `PersonaMemoryStore.search(query, k=3)` and offer results as weak-match candidates.
- **Accept:** an admin question whose wording shares no content words with any receipt still
  recalls the right thread. Gated on Phase 1 Task 5 passing — if vector search is disabled,
  this tier adds nothing over FTS5.
- **Decision needed:** land this with the episodic-line write, or withhold the write. R1 says
  withhold.

### Task 10: Scope as a property of the query

Design doc §4.1: the session never declares scope; every recall query carries the open
thread's domains. Enforcement at the recall boundary is auditable and never user-visible.

- **Scope:** add a `domains` argument to Plan A's receipt search, defaulting to the open
  thread's `topic_domains`. Cross-domain candidates require an explicit `recall_thread` call
  or ≥2 canonical entity overlaps. Emit a `scope_crossed` telemetry event otherwise.
- **Accept:** a thread scoped to `disk` does not silently recall `network` receipts; nothing
  in the UI changes; no user-visible refusal ever occurs.

### Task 11: Consolidation at idle

Design doc §4.5. The hot path stays extractive; abstraction runs offline. Halbert *is* the
machine, so it knows when it is idle — `state_trackers` and the resource monitors already
report load, and `scheduler/executor.py` already exists.

- **Scope:** a scheduled job that calls `get_consolidator()`, `get_importance_scorer()` and
  `decay_unused()` over the persona store during low-load windows. Budgeted, interruptible,
  resumable.
- **Accept:** ten Samba threads produce one durable preference fact; unretrieved memories lose
  strength; the job never runs while load is high.
- **Decision needed:** which `llm_config` slot runs it. Not the chat slot.

### Task 12: Retire `HybridMemorySystem` from the agent path for good

Already the spec's decision; make it final and tested so it cannot drift back.

- **Scope:** keep `memory/hybrid.py` for the eval/browser path. Add a test asserting no agent
  path module imports it. Confirm A9a's removal of `memory.store_interaction` holds.
- **Accept:** grep of the agent path shows no `get_hybrid_memory` import; ChromaDB stays
  eval-only per `the-being.md` §9.

---

## Phase 4 — Quality

Blocked on Plan A **and** Plan B §9.2 (the OSC 133 block parser), because receipt provenance
fields are only as trustworthy as the block data behind them.

### Task 13: Real `messages[]` at the three call sites (audit F3)

- **Files:** `agents/state_machine.py:669`, `:1280`, `:1294`.
- **Scope:** replace `messages=[{"role": "user", "content": prompt}]` with a real array built
  from `ctx.conversation_history`, preserving `ToolResultBlock` content. `agents/blocks.py`
  and `states.py:246-267` already build the block-typed structure that is currently flattened
  away.
- **Accept:** a tool-heavy thread replays tool calls as structured turns;
  `ContextWatermark.micro_compact()` has live blocks to truncate; V-05 still passes.

### Task 14: Cumulative evaluation harness

Every Plan A test runs at one or two threads, so precision decay is invisible. ATANT's
cumulative mode exists precisely because this failure cannot be seen in isolated testing;
its own reference implementation drops from 100% isolated to 96% at 250-story cumulative
scale.

- **Scope:** generate N synthetic threads across the domain enum with known-correct recall
  targets. Measure recall precision and hit-rate at N=10, 100, 500. No LLM in the evaluation
  loop — assert over structured outputs (which thread was recalled, which domains crossed,
  whether a superseded receipt appeared).
- **Accept:** a committed baseline table, and a CI check that precision at N=100 does not
  regress. **This is the highest-value test to build and it can be built against Plan A
  alone**, before any of Phase 3.

### Task 15: Abstain-and-probe

Design doc §4.2, and the one behaviour that differentiates Halbert from every system
surveyed: it can always re-observe its world, so it should never answer from stale memory.

- **Scope:** when answering needs current machine state and only a dated receipt supports it,
  probe instead of asserting. Prefer `ledger.get_current()` — one query, no subprocess — and
  fall back to a command.
- **Accept:** the staleness suite passes — write a receipt asserting a state, change the state
  on the host, ask a question that would be answered wrongly from the receipt, and observe
  probe-then-answer rather than recall-then-assert.
- **Decision needed (founder, §8 Q3):** is *"we set that on 14 Jul; let me confirm it's still
  current"* the behaviour you want, or is the extra step friction?

---

## Self-review

**Spec coverage.** Audit §6 lists N1–N3 and W1–W9. Mapped: N1→Task 6, N2→Task 7, N3→Task 8,
W1→Tasks 1-3, W2→Task 4, W3→Task 9, W4→Task 5, W5→Task 13, W6→Task 14, W7→Task 10,
W8→Task 11, W9→Task 15. Plus Task 12 from design §4.7. No gaps.

**Type consistency.** `_record(ledger, persona_id, subject, predicate, obj, source)` is used
identically in Tasks 1-3. `DEFAULT_PERSONA_ID = "halbert"` matches
`PersonaCognition(persona_id="halbert")` in `cognition_wiring.py:33`. `default_ledger_path()`
is defined in Task 3 and referenced only there and in its tests.
`ledger.record(persona_id, subject, predicate, object, source)` matches the verified live
signature.

**Known gap, stated deliberately.** Phases 3-4 have no line-exact diffs because Plan A has
not created the files they modify. Re-plan those tasks against real code rather than treating
the scope bullets as implementation steps.

---

*End of plan.*
