# Results: Sovereign Host Shell & Dashboard Realignment

**Date:** 2026-08-25
**Executes:** [HANDOFF-SOVEREIGN-HOST-SHELL-AND-DASHBOARD-REALIGNMENT-2026-08-25.md](HANDOFF-SOVEREIGN-HOST-SHELL-AND-DASHBOARD-REALIGNMENT-2026-08-25.md)
**Closes:** [SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md](SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md) item #9 (terminal UI unreachable) and three of its minors
**Status:** All four tasks landed. Verified in a running app, not just in tests.

---

## The short version

The engine was real; the shell never mounted it. `Layout.tsx` now has two
surfaces and the app opens on the Sovereign Host one. A command Halbert runs
appears as a live terminal in the conversation while it is still running,
because the backend now *emits* the terminal events the frontend was told to
consume — nothing did before, which is why wiring the frontend alone would
have produced another empty screen.

The dashboard is untouched and one keystroke away.

---

## Task 1 — Dual-mode shell (`Layout.tsx`, `App.tsx`)

| Piece | Where |
|---|---|
| Mode state, persistence, `Cmd/Ctrl+B` | `contexts/ShellModeContext.tsx` (new) |
| Segmented switch in the top bar | `components/shell/ModeSwitch.tsx` (new) |
| Two-column engaged canvas | `components/shell/SovereignHostShell.tsx` (new) |
| Right-hand context stage | `components/shell/ContextStage.tsx` (new) |
| Live host vitals in the stage | `components/shell/HostVitals.tsx` (new) |
| Shell assembly | `components/Layout.tsx` (rewritten), `App.tsx` |

**Engaged** (the default): conversation spine left, context stage right —
host vitals permanently on screen above the terminal accordion dock.

**Browsing**: the 14-item navigation rail, every dashboard page, and the
`SidePanel` exactly as before. Verified by driving the real app: the rail, the
Dashboard page and the Agent/Chat/Terminal side panel all render unchanged.

One structural change was unavoidable: the sidebar moved from
`fixed inset-y-0 … ml-64` to a flex child, so a global top bar could span both
modes. The scan/index progress indicators and the version + debug toggle moved
from the sidebar footer into that bar — they are now visible in *both* modes
rather than disappearing with the sidebar.

The split is `flex-1` conversation / `w-1/2 max-w-[640px] min-w-[320px]` stage
rather than a hard 50/50: on a wide monitor a literal half-width stage is mostly
empty gutter. Below `md` the stage hides and the conversation takes the window.

## Task 2 — The dock's idle state (`TerminalAccordionDock.tsx`)

`if (sessions.length === 0) return null` is gone. With nothing running the dock
renders its header (`TERMINALS · idle`), the line *"No terminals running. PTY
bridge ready."*, and a `+ New Terminal` button that spawns an interactive login
shell through the real PTY manager.

Two review minors fixed while in there:

- `toggle()` no longer calls `setVisible` (an external store write) from inside
  a `useState` updater — updaters must be pure, StrictMode runs them twice.
- `MAX_VISIBLE` is now enforced: an expanded row mounts a live `TerminalTile`
  only when the store actually promoted it to visible. Rows over the cap show a
  "held headless" note, and their output keeps buffering.

## Task 3 — Terminal SSE wiring, end to end (E1f)

The handoff scoped this as a frontend change. It could not be: **nothing in the
backend ever emitted `terminal_spawn` / `terminal_output` / `terminal_complete`.**
`grep` across the repo found the three event names only in planning documents.
Wiring `useAgentStream` to events no one sends would have reproduced the exact
failure being complained about — a feature that exists everywhere except on
screen. So the emitter was built too.

```
tools/executor.py  ──publish──►  streaming/terminal_bridge.py  ──drain──►  agents/state_machine.py
   _run_command                       TerminalEventBus                    _run_tool_streaming
   (streams stdout/stderr)         (per-session queues)                   (yields StreamEvents)
                                                                                  │
                                                                            SSE ──┴──► useAgentStream
                                                                                        applyTerminalEvent
                                                                                              │
                                                                              useTerminalSessions store
                                                                                       │           │
                                                                              InlineTerminals   the dock
```

**`streaming/terminal_bridge.py` (new).** A per-agent-session pub/sub. Zero cost
when nobody is listening (`publish()` on an unsubscribed session is a dict
lookup and a return), never blocks the producer (bounded queues drop oldest),
and carries the session id in a `ContextVar` — tool handlers take only their
args dict, so threading a parameter would have broken every registered tool.

**`tools/executor.py`.** `_run_command` no longer waits on `proc.communicate()`;
it pumps both pipes incrementally, buffering for the return value *and*
publishing each chunk. The string the model sees is byte-identical to before.
`execute()` sets/resets the ContextVar around the handler call.

**`agents/state_machine.py`.** `_handle_executing` runs the tool as a task and
drains the bus concurrently, yielding `terminal_*` StreamEvents as output
arrives. Awaiting the tool first would only ever produce a finished transcript.

**Frontend.** `useAgentStream` gained `applyTerminalEvent`, which drives the
terminal store. It runs *outside* the `setSession` updater deliberately:
appending output from inside an updater would duplicate every chunk under
StrictMode. The store gained a `transport` discriminator:

- `'ws'` — a real PTY the backend session manager owns. Full duplex.
- `'sse'` — a command the agent is running, mirrored read-only. `TerminalTile`
  suppresses stdin/resize/terminate for these, and `kill()` no longer sends a
  `DELETE` for a session that has no server-side row.

`terminal_spawn` carries `attach: 'sse' | 'ws'` so a future PTY-backed agent
spawn attaches a socket instead, with no protocol change.

**Fable-track components wired.** `useIntersectionDock` and `TetherChip` — built
and left unwired by design — now drive `components/agent/InlineTerminals.tsx`:
scroll a tile out of view and it parks in the dock, leaving a chip that brings
it back. Docking is deliberately one-way; swapping a 200px tile for a 20px chip
moves the layout under the observer, so honouring every "back in view" callback
flips the tile in and out on a single scroll.

## Task 4 — Host embodiment replaces the cartoon

`components/agent/HostGreeting.tsx` replaces the robot avatar and *"Ask me
anything about your Linux environment"*. It speaks from live telemetry:

> **I am Erics-Mac-Studio.local** (macOS 26.5.1, Darwin 25.5.0). Uptime is 1 day.
> 5 of 6 storage pools healthy across 20 cores. What would you like to inspect
> or configure?

Backed by a new **`GET /api/identity`** (`dashboard/routes/system.py`) —
psutil + platform only, so it answers on first paint with no system scan, no
profile on disk and no model loaded. It returns structured facts *and* a
composed `first_person` line, and filters mounts down to pools a person would
recognise (no simulator volumes, no `/System/Volumes/*`, nothing under 1 GB).

The starter prompts are derived from the machine's actual condition, not canned:
a full pool produces *"Why is /Volumes/TimeMachineStudio full?"* in amber.

---

## Verification

- **Backend:** `1111 passed` (full suite). 23 new tests in
  `tests/test_terminal_stream_bridge.py`, 19 in `tests/test_host_identity_route.py`.
- **Frontend:** `tsc --noEmit` clean; `vitest` 35 passed, including 18 new tests
  across `useTerminalSessions.test.ts` and `useAgentStream.terminal.test.ts`.
- **Live app:** built and served from the backend, driven with Playwright at
  1600×1000 — zero console errors. Confirmed: the engaged surface renders the
  greeting and vitals; the mode switch and `Cmd+B` both work; browsing mode
  renders the full rail, the Dashboard page and the SidePanel; `+ New Terminal`
  spawns a real PTY (`1/1 running`, pid shown in the dock); expanding the row
  mounts a live xterm; typing `echo sovereign-host-live` into it round-trips
  through the PTY and prints.

Note for anyone running the suite on this machine: `python -m pytest` resolves
to an x86_64 process and fails to load arm64 C extensions (psutil, numpy).
Prefix with `arch -arm64`.

### Adversarial review

A 29-agent review (5 independent lenses, every finding sent to a refuter)
raised 20 findings; 18 were refuted, 2 survived and were fixed:

1. **MAJOR — regression I introduced.** `_run_command`'s timeout covered only
   pipe draining, not process exit. `proc.communicate()` bounded both for
   free; splitting it into `wait_for(pumps)` + `await proc.wait()` did not.
   A child that closes its std fds and keeps running (`exec 1>&- 2>&-; sleep
   600`, a daemonising helper) hit EOF immediately, so the timeout never
   fired and the SSE turn stalled for the child's full lifetime. Reproduced
   at 10.1s against a 1s timeout. Fixed by putting drain-then-reap inside one
   `wait_for`; regression test asserts the whole thing is bounded.
2. **MINOR.** `psutil.cpu_percent(interval=None)` compares against the calling
   thread's previous sample; the first call on a thread has none and psutil
   documents the 0.0 it returns as meaningless. The greeting card would have
   opened at "0%" on a busy machine and held it for 30s. Fixed with a
   per-thread prime (one 100 ms blocking sample, once).

The 18 refuted findings were mostly documented design decisions restated as
defects (drop-oldest queue overflow, one-way docking, keeping the last good
vitals across a failed poll) or pre-existing behaviour unchanged by this work.

---

## Not done, deliberately

- **`SidePanel`'s three tabs** (Agent / Chat / `>_ Terminal`). The handoff calls
  the split artificial, but Task 1 also says browsing mode renders "exactly as
  it exists today". Unifying that panel is a separate decision.
- **`Cmd+K` to summon a dashboard module into the stage.** `ContextStage` takes
  a `modules` prop and renders through `ModuleRenderer`, so the seam is there;
  the command palette that fills it is not built.
- **Agent commands do not run on a PTY.** They run as streamed subprocesses.
  Routing them through the PTY manager would give the agent sudo prompts and
  interactivity, but the manager caps at 2 concurrent sessions with a 60s idle
  reaper and applies its own sandbox wrapper — enough behaviour change to
  deserve its own task. `attach: 'ws'` is the seam that makes it a backend-only
  change when someone takes it.
- **Nothing was committed.** The working tree has concurrent sessions in it;
  these changes are staged for whoever wants to review them first.
