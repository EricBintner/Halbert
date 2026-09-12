# Phase 4 follow-up: two items noticed during review

**Date**: 2026-09-11
**Status**: Open. Neither blocks Phase 4; both are follow-up items.
**Commit reviewed**: `019c953f` — feat(agent): Phase 4 background processes — detach, announce, port chip

---

## 1. No automated tests for the new functionality

The commit was manually verified (commit message: "full event chain fires... typecheck clean; terminal + e2e backend tests pass"), but there are no dedicated test files for any of the new code paths:

| New code | File:line | Test coverage |
|----------|-----------|---------------|
| `_run_command_background` | `executor.py:1036` | None |
| `StreamEvent.task_started` factory | `events.py:732` | None |
| `StreamEvent.port_discovered` factory | `events.py:760` | None |
| `state_machine._terminal_event` routing for both | `state_machine.py:4076,4084` | None |
| `useAgentStream` handlers | `useAgentStream.ts:441` | None |
| `TerminalSessionStore.addPort` | `useTerminalSessions.ts:263` | None |
| `TerminalSessionStore.markTaskStarted` | `useTerminalSessions.ts:276` | None |
| `TerminalTile` port chip render | `TerminalTile.tsx:369` | None |

The one grep hit in `test_pty_fanout.py:172` (`test_reader_task_started_on_attach`) is an unrelated PTY reader-task test — the name collides but the test is about `PTYSession.attach()`, not the Phase 4 `task_started` event.

**What to write:**
- Backend: a test that calls `_run_command_background` with a short-lived command (e.g. `echo listening on 127.0.0.1:8765; sleep 0.1`) and asserts the event sequence: `task_started` → `spawn` → `output` → `port_discovered` → `complete`, and that the method returns immediately (the turn does not block on the child's exit).
- Backend: a test that asserts `port_discovered` is deduped (same port printed twice → one event) and that a scheme-ful URL (`http://localhost:8765`) does not emit a chip.
- Frontend: a test that `addPort` dedupes, `markTaskStarted` is idempotent on `block_id`, and the `TerminalTile` chip renders for a session with `ports` and is absent without.

## 2. Port-sniff guard is per-chunk, not per-match

At `executor.py:1119`, the scheme guard is:

```python
if "http" not in text:
    for host, port_s in port_re.findall(text):
```

This checks whether the string `"http"` appears *anywhere* in the entire output chunk. If a single chunk contains both a full `http://localhost:8765` URL and a bare `127.0.0.1:3000` line (e.g. a multi-line server banner written in one `write()` call), the bare port chip is suppressed because `"http"` is present in the chunk — even though the bare `127.0.0.1:3000` line has no scheme.

In practice servers usually print these on separate chunks (separate `write()` calls), so the edge case is narrow. But a server that prints a multi-line banner in a single write could hit it.

**Fix (when addressed):** check per-match, not per-chunk. For each regex match, look at the characters immediately before the match in the chunk; if they are `http://` or `https://`, skip that match. This makes the guard local to the matched span rather than global to the chunk. Roughly:

```python
for m in port_re.finditer(text):
    # Skip if this match is part of a scheme-ful URL.
    start = m.start()
    if start >= 7 and text[start-7:start] == "http://":
        continue
    if start >= 8 and text[start-8:start] == "https://":
        continue
    host, port_s = m.group(1), m.group(2)
    ...
```

This also lets the guard drop the `if "http" not in text` pre-check entirely, simplifying the control flow.
