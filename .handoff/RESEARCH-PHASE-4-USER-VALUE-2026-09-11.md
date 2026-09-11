# RESEARCH & UX: Phase 4 — what does the user actually want?

**Date**: 2026-09-11
**Status**: Recommendation. Informs whether to build Phase 4 as designed, trim it, or drop parts.
**Scope**: The only un-built phase — Background Processes & Port Sniffing. The other four phases are committed (`fbd725e9`, `528425a6`).
**Question the founder asked**: why would a user want this, and what should it do? Not "how do we build it" (that's designed) but "is it worth building, and in what shape?"

---

## 1. The user story, in one breath

A user asks the computer to **start something that keeps running** — a dev server, a watcher, a sync job. Two things then matter to them:

1. **"Is it still alive, and what is it doing?"** — they want to glance and know it's running, see its output if they care, and be told when it stops.
2. **"Take me to it."** — if it opened a port, they want to open the thing in a browser, not read a port number off a log line and type it themselves.

Everything in Phase 4 serves one of those two wants. Anything that doesn't is a candidate to cut.

---

## 2. What already works today (do not rebuild)

This is the part the plan under-sold. Three pieces of the "user want" are **already live**:

| User want | Already shipped | Where |
|-----------|-----------------|-------|
| "Tell me when a command becomes a long-running thing" | A block still open after a delay is **auto-promoted to a task card** in the Tasks column | `agent_pool.py:108-124` (`_promote_after`) → `terminal_block_promote` (`events.py:663`) |
| "Let me see what it's doing" | The task card expands to a **live TerminalTile** with the full output stream | `TasksColumn.tsx` (Phase 5, committed) |
| "Take me to it" (partial) | URLs in terminal output are **already clickable** — xterm's `WebLinksAddon` detects `http://localhost:8765` in the byte stream and opens it on click | `TerminalTile.tsx:21,186` |
| "Tell me when it stops" | `terminal_complete` → `task_completed` → the task card flips to done with exit code + duration | `events.py:585,691`; `useAgentStream.ts:948-959` |

So the user can already: start a server, watch it promote to a task card, expand it to see live output, click the `localhost:PORT` URL it printed, and see it marked done when it dies. **That is most of the story.**

## 3. What is genuinely missing

Against the two wants, the real gaps are narrower than "build ProcessRegistry + two factories + port sniffing":

1. **The start is silent.** When a command goes long-running, the user is not *told* at the moment it promotes — the card just appears in the Tasks column on the next render. There is no `task_started` event, so nothing announces "this is now a background task." (Want #1 — awareness.)
2. **`background=true` is a lie.** `executor.py:893` accepts the flag and ignores it. If the model asks to run something "in the background," it is *not* detached — it runs in the PTY pool and the turn **blocks on it** (up to timeout) exactly like a foreground command. The model cannot actually fire-and-forget. (The core of want #1.)
3. **The port is discoverable only if the user reads it.** `WebLinksAddon` makes the URL clickable *if the server printed a full `http://...` URL*. Many servers print only `Listening on port 8765` or `127.0.0.1:8765` with no scheme — which `WebLinksAddon` does **not** linkify, so there is nothing to click. (Want #2 — "take me to it" breaks for scheme-less output.)

## 4. The recommendation, sized to the wants

Build **only what closes those three gaps**, in this order. This is a *smaller* Phase 4 than the plan's full packet.

### 4a. Make `background=true` actually detach — the real fix (do this)
This is the one true gap with no workaround. When the model says "run in the background," the turn must not block. The OSS reference (open-claude-code `runBackground`) is a detached subprocess, and that is the right shape for a fire-and-forget server — a PTY keeps a bash session alive the server never uses. **This is the founder-gated decision (§3.1 detached-spawn split).** Everything else in Phase 4 is optional polish; this is the only piece that changes *behavior the user can feel*.

**Smallest correct form:** a detached subprocess whose stdout/stderr are captured, reusing the existing `terminal_output`/`terminal_complete` event vocabulary so the task card and TerminalTile render it unchanged. No new event types needed for this alone. Returns `{block_id, pid, status:"running"}` immediately.

### 4b. Announce the start — `task_started` (cheap, do with 4a)
The promote-after-delay already creates the card; the gap is only that nothing *announces* it. `StreamEvent.task_started` (the symmetric twin of the existing `task_completed`) is a five-line factory plus a frontend handler that surfaces "started in the background" in the turn. Trivial once 4a exists, because 4a is what fires it.

### 4c. Surface the port — but only for scheme-less output (trim hard)
Do **not** build a general port-sniffing subsystem. The user want is "take me to it," and `WebLinksAddon` already covers the printed-a-URL case. The only gap is **scheme-less** output (`Listening on 8765`, `127.0.0.1:8765`). The minimal fix is a single regex over the output stream for `(localhost|127.0.0.1|0.0.0.0|::1):(\d{1,5})` (no scheme), deduplicated per block, emitting `port_discovered` → a small chip that **stages** `open http://localhost:PORT` into the composer (per the standing directive: staged, never executed).

**Cut from the plan:** `ProcessRegistry` as a named subsystem is over-scoped — 4a needs a spawn helper and a map, not a registry with its own lifecycle API. The plan's separate "ProcessRegistry" collapses into the detached-spawn helper.

## 5. What to NOT build (and why)

- **No general `ProcessRegistry` class.** The user want is "detach + see it," served by a spawn helper + the existing store. A registry is machinery for its own sake.
- **No port probing / lsof** (openclaw `ports-probe.ts`). That answers "is this port free / who owns it" — a question the user did not ask. They asked "take me to *my* server," which is the regex-over-stdout case only.
- **No persistence.** Background tasks are ephemeral; the user does not want last Tuesday's dev server resurrected on reload. No SQLite, no migrations.
- **No `port_discovered` for scheme-ful URLs.** `WebLinksAddon` already handles those; a duplicate chip is noise.

## 6. The one decision that is the founder's

§3.1 — the detached-spawn split. Everything else here is mechanical once that's ruled. The recommendation: **confirm it**, because it is the only piece that changes real behavior (the turn stops blocking on background work). The rest of Phase 4 shrinks to "wire `background=true` to a detached spawn, announce the start, chip the scheme-less port" — roughly a third of the packet the plan described, because most of the user-facing value is already shipped.

## 7. Bottom line for the founder

The user wants two things — *"is it alive and what's it doing"* and *"take me to it"* — and **most of that already works** (auto-promote to task card, live TerminalTile, clickable URLs, done-when-stops). Phase 4 should be **trimmed to the three real gaps**: actually detach on `background=true`, announce the start, and chip the scheme-less port. Confirm the detached-spawn split and this is a small, high-value build instead of a new subsystem.
