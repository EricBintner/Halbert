# PKT-GW-A — Event replay ring + typed MCP error envelope

Tier: **opus**   Milestone: **M2**   Effort: **S-M**
Collision lane: **B**   Merge order: **2/4 in B**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**GW-A** — Event replay ring + typed MCP error envelope.

## 2. User problem

Two live seams drop or garble events on Halbert's real-time surfaces, and one error surface is untyped.

(1) Thrown-away PTY replay: `streaming/pty.py` already implements a bounded scrollback replay ring — `attach()` enqueues `("__replay__", self.get_buffer())` as the first queue item (pty.py:179) so a newly-attached consumer can render history. But the only consumer that matters, `PtySession.read_chunk()` (pty.py:331), explicitly skips that item (pty.py:348: `if isinstance(item, tuple) and item[0] == "__replay__": continue`) on the grounds that "callers that already consumed the buffer don't get a duplicate." The caller is `terminal_websocket` (`dashboard/routes/websocket.py:79`), whose `pump_stdout` iterates `session.read_chunk()` (websocket.py:106) — so a browser that reconnects to `/ws/terminal/{session_id}` after a network drop, a laptop sleep, or a Tauri reload sees only output produced after the reconnect. The watched-terminal story (founder direction: terminals watched by the machine, reattachable) loses exactly the history that makes reattach coherent. The ring exists; it is wired to discard itself one layer up.

(2) No resume on the dashboard event stream: the agent turn stream is SSE over fetch-POST (`routes/agent.py:1894,1967`, `StreamingResponse(media_type="text/event-stream")`) with no resume token, and the `/ws` broadcast channel (`routes/websocket.py:45`, fed by `ConnectionManager.broadcast` at `app.py:902` — approvals, job updates, decisions) has no sequence numbers at all. A dropped `/ws` connection silently loses every approval request and decision emitted during the gap; the UI cannot distinguish "nothing happened" from "events lost." There is no `since_seq` on reconnect and no per-session bounded ring to replay from.

(3) Untyped MCP tool errors: `mcp/server.py` has 18 sites that return `{"error": str(e)}` from bare `except Exception` handlers (e.g. `_tool_get_vitals` :166, `_tool_get_config_value` :310, `_tool_approve_proposal` :557). `str(e)` leaks raw exception text (filesystem paths, config internals) to any MCP client, gives callers nothing machine-checkable to retry against (transport-uncertainty vs definitive-rejection is indistinguishable), and bypasses the `display_transport` redaction choke point that every other user-facing surface routes through. The closed-reason vocabulary already exists one import away (`consent/denials.py:54` CLOSED_REASONS) but the MCP error surface doesn't use it.

## 3. What to build

Three deliverables, cheapest first (matches the deep-eval minimum-viable order).

DELIVERABLE 1 — Wire the existing PTY replay through the terminal WS (S). In `streaming/pty.py`, stop discarding the replay: give `read_chunk()` a parameter `include_replay: bool = False`; when True, yield the `("__replay__", buffer)` payload as the first bytes instead of `continue`-ing past it. In `dashboard/routes/websocket.py` `terminal_websocket.pump_stdout`, call `session.read_chunk(include_replay=True)` so every attach — first or re-attach — renders scrollback first, then live chunks. The protocol already copes: the frontend renders `{"type":"stdout","data":...}` frames in order; replay is just the first frame. Coordinate with the terminal workstream's HM18-M1 (PTY reattach contract) so the replay is wired once: this unit owns the `read_chunk` flag and the WS call site; if HM18-M1 has already touched the same lines, rebase onto it rather than duplicating.

DELIVERABLE 2 — `dashboard/event_replay.py` + seq/epoch + since_seq reconnect (S-M). New module `halbert_core/halbert_core/dashboard/event_replay.py` implementing `EventReplayBuffer`: per-session monotonic `seq` stamping (per-process `epoch` uuid minted at startup so a client can detect a server restart and reset its cursor), and a bounded ring (`collections.deque(maxlen=N)`, N configurable, default ~500 events) holding the stamped envelopes. Wrap `ConnectionManager.broadcast` (`app.py:902`) so every broadcast is stamped `{seq, epoch, type, data}` and appended to the ring before fan-out; apply the same stamping to the turn-event path that feeds the SSE stream in `routes/agent.py` (the tee point where `StreamEvent.to_sse()` dicts are emitted — stamp before serialization, ring per session_id). Extend `websocket_endpoint` (`routes/websocket.py:45`) to accept an optional `since_seq` query parameter (and `epoch`): on connect, if the client's epoch matches and `since_seq` is within the retained window, replay ring entries with `seq > since_seq` in order before live frames; if the epoch differs or the seq has fallen off the ring, send a single typed `{"type":"resync"}` control frame and start live — the client refetches state rather than receiving a partial replay. Frontend: the dashboard's `/ws` client remembers `last_seq`+`epoch` per connection and passes them on reconnect. Reference shape: openclaw's seqByRun (per-run sequence cursors), per registry notes — NOT warp (private repo).

DELIVERABLE 3 — Typed MCP error envelope through the display choke point (M, scoped as a finding-fix not a rewrite). In `mcp/server.py`, replace the 18 bare `return {"error": str(e)}` sites with a single helper `_tool_error(exc, *, tool: str) -> Dict[str, Any]` returning `{"error": {"code": <closed reason>, "message": <safe text>, "retryable": <bool>}}`. The `code` vocabulary is the existing closed set — reuse `consent/denials.py` CLOSED_REASONS where the failure maps to one (e.g. permission/config-scope failures), and add a small sibling closed set for transport/tool failures (e.g. `TOOL_UNAVAILABLE`, `TOOL_INPUT_INVALID`, `TOOL_INTERNAL`, `UPSTREAM_UNREACHABLE`) defined once in `mcp/server.py` with the same fail-closed discipline (constructing with an invented code raises). `message` is routed through `security/display_transport.py` (`_redact_display_text` / `verbose_block`) so exception text is scrubbed deterministically before it crosses the MCP boundary — never raw `str(e)`. `retryable` encodes the transport-uncertainty vs definitive-rejection rule (Deliverable 4).

DELIVERABLE 4 — Retry rule as docstring + test (S). Write the rule in `event_replay.py` and `mcp/server.py` docstrings, and as a test: transport-uncertainty (WS drop, SSE gap bridged by `since_seq`, MCP call that never got a response) is safe to retry/replay; a definitive typed rejection (`error.code` present in the closed set) must NOT be auto-retried by the client — it is a decision, not a gap. Test asserts a typed-rejection response carries a closed-set code and `retryable: false` for definitive failures.

## 4. What NOT to build

Not a protocol redesign: no WebSocket replacement of the SSE agent stream, no SSE→WS migration, no new transport library. The fetch-POST SSE stream in `routes/agent.py` stays; this unit adds stamping/replay around it, not a new channel.

Not 55 sites: the registry's authoritative count for bare `str(e)` error returns in `mcp/server.py` is 18 (the deep-eval's "55" was the pre-audit estimate from a broader grep). Scope Deliverable 3 to the 18 real sites; do not go hunting for a hypothetical 37 more.

Not the MCP client side: R-09 (merged) already owns the MCP client boundary (A17-G9). This unit touches the MCP *server* tool-error surface only. Do not re-open client framing, env, or process-group handling.

Not the interrupt/ordering work: R-01 (interrupt algebra) owns talk-door ordering; R-05 owns the redaction registry contents. This unit routes error text *through* the existing `display_transport` choke point; it does not modify the redaction registry or the interrupt path.

Not a conversation list or history UI: replay is per-connection, per-session, bounded, and in-memory. No persistence of the event ring to disk, no replay-across-restart beyond the `epoch` resync signal (a restart means refetch, not replay), no user-visible event log.

Not HM18-M1's reattach contract: the broader PTY reattach/session-resume contract belongs to the terminal workstream. This unit only flips the replay flag and wires the one WS call site.

No model involvement anywhere: seq stamping, replay, error codes, and the retry rule are deterministic. No AI model names on any surface; error `message` copy is shipped text, never synthesized.

## 5. Target files
- `halbert_core/halbert_core/streaming/pty.py` [new file]
- `halbert_core/halbert_core/dashboard/event_replay.py`
- `halbert_core/halbert_core/mcp/server.py`

## 6. Dependencies

CSC-06, reconnect_supervisor

## 7. Effort

**S-M** — S-M, as registered. Breakdown: Deliverable 1 is genuinely S — the ring already exists and is tested machinery; the work is one parameter on `read_chunk`, one call-site change in `websocket.py`, and tests (the deep-eval prices this as "S effort for a real improvement that already exists and is thrown away"). Deliverable 2 is the M heart: a new module with epoch/seq discipline, two integration points (`ConnectionManager.broadcast` and the SSE tee in `agent.py`), a `since_seq` handshake with resync fallback, and frontend cursor memory — bounded by the ring being per-session and in-memory (no persistence layer, no migration). Deliverable 3 is M-shaped but deliberately scoped down: a single helper plus 18 mechanical call-site replacements and the closed-code set — the deep-eval prices it "M effort but scoped as a B6 finding, not a parallel rewrite." Deliverable 4 is S (docstring + one test). Dependencies are cheap: CSC-06 (RESHAPE'd to the resume contract, no broad registry) supplies the resume-shape discipline this aligns with, and `reconnect_supervisor` (backlog §3.9, `net/reconnect_supervisor.py`, to be built once and shared with VMV-4/VMV-2/MCP-C) supplies the client-side backoff — this unit consumes that primitive rather than inventing its own backoff, so it should land after or alongside it. If `reconnect_supervisor` does not exist yet when this starts, the client reconnect uses a local minimal backoff and the supervisor adoption is a follow-up — do not block the ring on it.

## 8. UX rationale

Mostly invisible-when-working, which is the point. A browser that reconnects a watched terminal after a network drop or laptop sleep renders the scrollback it missed, then continues live — the terminal reads as one continuous watched session (founder direction: terminals watched by the machine, reattachable), not a blank pane that starts from the reconnect instant. On the dashboard, an approval request or decision emitted while the `/ws` connection was down appears on reconnect via `since_seq` replay instead of vanishing; if the gap is too old or the server restarted, the client gets the typed `resync` frame and refetches — the UI never silently shows a stale "nothing pending" state. No new chrome: no notification badges, no event-log panel, no conversation list. Any reconnect/resync indicator, if one is added at all, follows the founder's subtle indicator-light language (fill+outline), uses only `shared-tokens/tokens.css` colours (run `scripts/check_contrast.py`), and carries no emoji. MCP error messages surface in the machine's first-person voice as the computer itself ("I couldn't read that config value — …"), using shipped deterministic copy from the closed-code table — never raw exception text, never a synthesized explanation, never an AI model name. Commands remain staged, never executed; replay changes what the user *sees* of event history, never what runs.

## 9. Acceptance criteria

PTY replay: reconnecting a client to `/ws/terminal/{session_id}` after the session has produced output yields the full scrollback as the first stdout frame(s), then live chunks; a first-time attach behaves identically (replay-then-live), and `read_chunk()`'s default (`include_replay=False`) preserves the old skip behavior for any caller that already consumed the buffer.

Event replay: every `/ws` broadcast and every turn-event SSE emission carries a monotonically increasing `seq` and the server `epoch`; a reconnect with `since_seq=<last seen>` and matching epoch receives exactly the missed events in order (no duplicates, no gaps) before live frames; a reconnect with a stale epoch or an evicted seq receives exactly one `resync` control frame and then live frames only; ring overflow under a burst drops the oldest events and triggers the resync path, never unbounded memory growth (ring stays at its configured maxlen).

Typed MCP errors: all 18 former `{"error": str(e)}` sites return the envelope shape `{"error": {"code", "message", "retryable"}}`; every `code` is a member of the closed set (constructing an envelope with an off-list code raises); no envelope `message` contains raw exception text that `display_transport` would have redacted (paths, secrets); definitive rejections carry `retryable: false` and transport-uncertain failures `retryable: true`.

Retry discipline: a client-side reconnect helper (or the minimal stand-in pending `reconnect_supervisor`) retries only on transport uncertainty and never auto-retries a typed definitive rejection.

Standing-rule conformance: no AI model names on any added surface; all colours from tokens.css; no emoji; error copy is shipped text.

## 10. Verification (measured state, not model judgment)

Runnable, measured checks (all Python tests with the `arch -arm64` prefix per repo rule):

1. New unit tests, e.g. `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_event_replay.py -v` — assert: ring stamps strictly increasing seq per session; `events_since(seq)` returns exactly the tail; eviction past maxlen returns a resync sentinel; epoch mismatch returns resync.

2. PTY replay test (extend or add beside the existing terminal tests, e.g. `halbert_core/tests/test_terminal_e2e.py` or a new `test_pty_replay.py`): spawn a session via the terminal manager, write known output, attach a consumer with `include_replay=True`, assert the first yielded bytes equal `get_buffer()` content; attach with default and assert replay is skipped (exit-code-based assertions, no model judgment).

3. WebSocket integration: connect to `/ws` with the app's test client, trigger two broadcasts (e.g. via `ConnectionManager.broadcast`), disconnect, reconnect with `since_seq` of the first, assert exactly the second event arrives then a live third; reconnect with `since_seq=0` after forcing ring eviction (small maxlen in test config), assert exactly one `resync` frame.

4. MCP envelope test (beside `halbert_core/tests/test_mcp_findings_tools.py` etc.): force each of the 18 tool handlers to raise (monkeypatch the underlying call), assert the response matches the envelope schema, `code` is in the closed set, and `message` equals the `display_transport`-scrubbed text (compare against `_redact_display_text(str(e))`, not `str(e)`). A grep gate: `grep -c "error.*str(e)" halbert_core/halbert_core/mcp/server.py` returns 0.

5. Regression: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "websocket or terminal or mcp or streaming"` — compare against the known nonzero main baseline captured before the change; no new failures attributable to this unit.

6. Manual smoke (measured): `make dev-web`, open the dashboard, start a watched terminal, produce output, kill the browser tab's network (DevTools offline), produce more output via a second client, restore network — observe scrollback-then-live in the reconnected tab and the missed approval/decision event arriving via replay.

## 11. Exclusions

- Broad MCP server audit (the B6 audit of all 18 tools' behavior beyond the error envelope): stays with the app-UI-access workstream's B6 item per founder ruling (audit, not rebuild) — this unit fixes only the error-return shape as a B6 finding, as the deep-eval directs.
- Full PTY reattach contract (HM18-M1: session resume semantics, reattach authorization, cross-client attach policy): terminal workstream owns it; this unit coordinates the shared `streaming/pty.py` replay lines so the wiring lands once.
- Client-side reconnect backoff/jitter/stability-window: goes to the shared `reconnect_supervisor` primitive (backlog §3.9, `net/reconnect_supervisor.py`), built once and shared with VMV-4, VMV-2, MCP-C. If it isn't built when GW-A starts, GW-A ships a minimal local backoff and files the supervisor adoption as its follow-up; GW-A does not build the shared supervisor itself.
- Voice SSE reconnect and voice event tail replay: VMV-2 and VMV-4 respectively — they consume this unit's `EventReplayBuffer` but own their own stream wiring.
- The remaining closed-reason vocabulary extensions for non-MCP surfaces: stays with the permission/consent system (`consent/denials.py` owners); GW-A only adds the small MCP-transport sibling set.
- Persistent (on-disk) event history and replay-across-restart: dropped per scope — the `epoch`+`resync` contract makes restart a refetch, deliberately. No migration, no new on-disk store (no-users rule).
- The deep-eval's "55 bare error sites" framing: dropped per registry recount — the verified count is 18; the packet scopes to the 18.

---

## OSS reference

openclaw src/infra/agent-events.ts:265 (seqByRun) — NOT warp (private repo).

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
