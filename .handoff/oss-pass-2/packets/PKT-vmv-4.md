# PKT-VMV-4 — Replayable event tail + duplicate suppression (post R-01/R-02)

Tier: **opus**   Milestone: **M5a**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-01/R-02 is merged, keep only the genuine residual.

---

## 1. Packet

**VMV-4** — Replayable event tail + duplicate suppression (post R-01/R-02).

## 2. User problem

VMV-4 covers voice/media ingress hardening and turn replay in Halbert. The final backlog (`.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md` line 156 and 520) already RESHAPEd this packet: R-01 (talk-door ordering / steer algebra) and R-02 (claims, admission graph, guest routes, voice provenance) are merged in opus batch `55ecef87`, so the voice-provenance and speaker-claim claims in the original packet are DONE and must not be rebuilt. Three real defects remain. (1) The replayable event tail (OC11-M1 + A09-G4): a turn runs inside the SSE generator in `dashboard/routes/agent.py`, so a dropped SSE, a reloaded tab, or a voice HUD attaching mid-turn sees nothing; the existing `turn_event_tee` (`agents/turn_event_tee.py`) is process-wide and observe-only — subscribers that attach late receive only future events, and reconnecting surfaces cannot recover the turn they dropped from. (2) A09-G2 duplicate-transcript suppression: called for in the packet-04 Hermes addendum, never built; a voice relay or HUD that reattaches re-publishes the same turn events and the consumer has no way to dedupe beyond a per-subscriber seq. (3) The reconnect supervisor (OC10-C9): `integrations/home_assistant/ha_event_stream.py` `_run_loop` is a flat 5s retry with no backoff, jitter, or stability window, and `mcp/health.py`'s budget counter resets on the first success, so a server that accepts then drops resets the budget every cycle — the same mechanism SCHED-P5's thaw reconnect needs, build once in a shared module.

## 3. What to build

Three residual deliverables, in order.

1. Replayable per-turn event tail inside `agents/turn_event_tee.py`. Extend `TurnEventTee` with a bounded ring buffer (per `session_id`, FIFO, drop-oldest; default cap ~64 events or ~256 KiB, whichever hits first, both constants named at the top of the file). Events are already stamped with the stream-wide monotonic `seq` (`itertools.count(1)` at line 116) and `ts` at line 165-166; the buffer stores the cleaned dict AFTER those stamps so replay preserves ordering. Add a `replay_since(session_id, last_seen_seq)` method that returns buffered events for that session with `seq > last_seen_seq`, in order, as a list. Subscribing callers pass an optional `last_seen_seq` to `subscribe()`; the tee delivers buffered replay first (synchronously, in order), then live events. Eviction is on the ephemeral tail only — the live subscriber path is untouched. The tee's three hard rules (echo-guard egress, observe-only, single loop no lock) are unchanged; replay carries the already-scrubbed payloads, so no second scrub pass is added.

2. Duplicate suppression at the consumer seam. The `seq` field already exists; what is missing is a documented consumer-side dedupe contract. Add a small helper class `SeqDedupe` in the same file: tracks `last_seen_seq`, `seen(seq) -> bool` returning True on first sight, False on replay or overlap, and `reset()` for tests. Document in the module docstring that any reconnecting consumer (the `/ws` bridge in `dashboard/app.py`, the future voice HUD) must run events through `SeqDedupe` before rendering so a replayed tail cannot double-render a turn. This closes A09-G2 without touching the publisher.

3. Reconnect supervisor primitive at `net/reconnect_supervisor.py` (new module, new directory `halbert_core/halbert_core/net/` with `__init__.py`). One class `ReconnectSupervisor` providing: exponential backoff with full jitter (`random.uniform(0, min(cap, base * 2**attempt))`), a stability window (a connection that stays up ≥ N seconds, default 30, resets the attempt counter and the backoff to base), and a bounded drop-oldest outbound queue (default cap 32) for events that arrive while disconnected. Pure primitive, sync, no I/O — it computes `next_delay_s()` and `record_success()` / `record_failure()`; the caller owns the actual socket. Constants named `DEFAULT_BASE_SECONDS`, `DEFAULT_CAP_SECONDS`, `DEFAULT_STABILITY_WINDOW_SECONDS`, `DEFAULT_QUEUE_CAP`. Do NOT wire it into `ha_event_stream.py` or `mcp/health.py` in this unit — that is a follow-up consumer (shared with SCHED-P5 thaw reconnect); this unit lands the primitive plus tests only.

Tests in `halbert_core/tests/agents/test_turn_event_tee.py` (extend the existing file if present, else create) and `halbert_core/tests/net/test_reconnect_supervisor.py` (new). Cover: buffer eviction order (drop-oldest preserves seq monotonicity), replay_since returns exactly the events newer than the watermark in order, replay does not re-scrub (a pre-scrubbed sentinel string passes through unchanged), `SeqDedupe` rejects a replayed seq and accepts the next, supervisor backoff doubles then caps, jitter stays within `[0, computed_max]`, stability window resets attempt counter, queue drops oldest when full.

## 4. What NOT to build

Do NOT rebuild A09-G1 (busy-verb talk-door ordering) or any voice-provenance / speaker-claim work — R-01 and R-02 are merged in `55ecef87`; this is a VERIFICATION-FIRST unit and re-doing that work is out of scope. Do NOT wire `ReconnectSupervisor` into `integrations/home_assistant/ha_event_stream.py` or `mcp/health.py` here — those consumers are shared with SCHED-P5 and land in a separate unit once this primitive exists. Do NOT build the three-axis budget (OC11-M2) — deferred by the deep-eval verdict pending a DECISIONS.md note. Do NOT build the fast-context shortcut for spoken what/when questions (OC11-C4) — deferred behind the memory packet's recall-decision log (OC11-M6). Do NOT add WS keepalive missed-pong diagnostics (OC17-C15) — flagged low priority, no flapping observed. Do NOT touch the reduced event set, the echo-guard scrub seam, or the observe-only contract — those are hard rules from the design. Do NOT introduce any lock into the tee — the single-loop contract stands. Do NOT build a session list, a conversation browser, or any UI affordance that turns the tail into a navigable history — recovery is for the one continuous conversation, not a list. No emoji anywhere. No AI-model naming on any surface.

## 5. Target files
- `halbert_core/halbert_core/agents/events.py`

## 6. Dependencies

reconnect_supervisor

## 7. Effort

**S-M** — S-M. The work is one bounded ring buffer plus one replay method inside an existing class that already has seq/ts stamping, one tiny consumer-side dedupe helper, one new pure-primitive module with no I/O, and tests. The tee is already scrubbed at fan-out (line 162) so replay needs no second security pass. The supervisor is deterministic math — backoff, jitter, stability window — no sockets, no async, no config. The deep-eval verdict explicitly narrowed the packet to these three residuals and deferred everything else, which caps scope. What keeps it out of the trivial band is the buffer-eviction ordering invariant (drop-oldest must preserve seq monotonicity per session) and the jitter/stability-window arithmetic that wants property-style tests, not just happy-path asserts.

## 8. UX rationale

No new user-visible surface in this unit — the tail and supervisor are primitives consumed by existing surfaces (`dashboard/app.py` `/ws` bridge, future voice HUD, HA event stream). What the user experiences downstream, once the follow-up consumer unit wires these in: a laptop that sleeps mid-turn, a tab that reloads, or wifi that flaps no longer loses the rest of the turn — the surface recovers the missed events in order and renders them once. The tee's existing contract is preserved: nothing on screen changes shape, no new panel, no settings toggle. The dashboard still speaks first-person as the machine, grounded in measured data; the reconnect supervisor's numbers (current backoff, attempts since last stable window, queue depth) are the kind of measured data that a future Presence-Pill or dashboard health row could surface in the machine's own voice ("my home-assistant link has been retrying for 40 seconds") — but that surface is a separate unit and is NOT built here.

## 9. Acceptance criteria

All of the following hold.

1. `TurnEventTee` in `halbert_core/halbert_core/agents/turn_event_tee.py` keeps a bounded per-session ring buffer; `replay_since(session_id, last_seen_seq)` returns buffered events newer than the watermark in ascending seq order; `subscribe()` accepts an optional `last_seen_seq` and replays before delivering live events.
2. Eviction is drop-oldest per session; the seq counter remains a single monotonic stream-wide `itertools.count(1)` — no per-session renumbering.
3. Replay delivers the already-scrubbed payload; no second scrub pass runs on replay.
4. `SeqDedupe` exists in the same module; `seen(seq)` returns True on first sight, False on any repeat or out-of-order earlier seq; `reset()` clears state.
5. New module `halbert_core/halbert_core/net/reconnect_supervisor.py` exists with `ReconnectSupervisor` exposing `next_delay_s()`, `record_success()`, `record_failure()`; backoff doubles per failure, capped; jitter is uniform in `[0, computed_max]`; a stable connection (≥ `DEFAULT_STABILITY_WINDOW_SECONDS`) resets attempts and delay to base; the outbound queue drops oldest past `DEFAULT_QUEUE_CAP`.
6. The tee's three hard rules still hold: echo-guard scrub at fan-out, observe-only (no verb on the hub), single event loop with no lock anywhere in the module.
7. No edits to `ha_event_stream.py`, `mcp/health.py`, `dashboard/routes/agent.py`, or any consumer — this unit is primitives plus tests only.
8. No emoji added anywhere; no AI model named on any surface; no new colour literals (no UI code touched at all).

## 10. Verification (measured state, not model judgment)

Run from a worktree: `arch -arm64 ./wt_pytest.py halbert_core/tests/agents/test_turn_event_tee.py halbert_core/tests/net/test_reconnect_supervisor.py -v` (from the main tree: `arch -arm64 .venv/bin/python -m pytest` with the same pathspec). The run must collect the new tests and pass. Specific test IDs that must exist and pass: a buffer-eviction test asserting drop-oldest preserves seq order; a `replay_since` watermark test; a `SeqDedupe` duplicate-rejection test; a supervisor backoff-capping test; a supervisor stability-window reset test (driving time via a patched clock, never `time.sleep`). Baseline: main carries a known nonzero failure count — capture a baseline run on the merge-base first (`arch -arm64 ./wt_pytest.py halbert_core/tests -x --co -q | tail -5` for collection sanity, then a full run on the merge-base if drift is suspected) and confirm this unit adds zero new failures outside its two new test files. Also verify with `grep -n "asyncio.Lock\|threading.Lock" halbert_core/halbert_core/agents/turn_event_tee.py` returning zero hits — the no-lock rule is mechanical.

## 11. Exclusions

A09-G1 (talk-door ordering / speaker-claim clamp) — already delivered by R-01 in merged opus batch `55ecef87`; verified, not rebuilt. Voice provenance and the admission graph — R-02 in the same merged batch; verified, not rebuilt. Wiring `ReconnectSupervisor` into `integrations/home_assistant/ha_event_stream.py` and `mcp/health.py` — goes to the SCHED-P5 consumer unit (the deep-eval cross-cutting opportunity #6 names the same primitive serving both packets; landing consumers separately keeps this unit primitives-only). Three-axis budget with maintained running footprint (OC11-M2) — deferred by the verdict; needs a DECISIONS.md note first, lives in a future unit if approved. Fast-context shortcut for spoken what/when questions (OC11-C4) — deferred behind the memory packet's recall-decision log (OC11-M6, re-homed to the memory packet). WS keepalive missed-pong diagnostics (OC17-C15) — deferred as low priority, no flapping observed. Any UI surface for the tail (no replay HUD, no event inspector, no history list) — out of scope; the one-seamless-conversation rule forbids a navigable list. Any change to the reduced event set, the scrub seam, or the echo guard — those are hard rules owned by earlier packets.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
