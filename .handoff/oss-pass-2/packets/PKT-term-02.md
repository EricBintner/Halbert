# PKT-TERM-02 — Watched-terminal read/close tools

Tier: **opus**   Milestone: **M2**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**TERM-02** — Watched-terminal read/close tools.

## 2. User problem

The watched-terminal direction is founder-ratified: user shells stay open but are WATCHED by the agent, and the agent reuses idle terminals (memory: halbert-terminal-direction-2026-08-26). Today the agent is blind to what it watches. `streaming/terminal_bridge.py` is one-way executor→SSE (its own docstring: the bridge "converts each payload into a StreamEvent on the live SSE stream" — nothing flows back), `streaming/session_manager.py:42 TerminalSessionManager` tracks PTY sessions with spawn/get/touch/list_active but exposes no agent-callable read of pane contents, and the frontend tiles (`components/agent/TerminalTile.tsx`, `InlineTerminals.tsx`) render xterm buffers no tool can reach. So the agent can start a command and watch its own tile, but cannot read a user-owned shell pane, cannot page scrollback, and cannot dismiss a finished tile. Separately, HM10-C17 names a general convention Halbert lacks: capability-gated tools are currently registered unconditionally and fail at call time, instead of being withdrawn from the tool list when the capability is absent. Two founder decisions gate the packet: FD-2 (may the agent read user shells — recommended default: own capability `terminal.read_user_pane`, on for owner, denied for guests) and FD-7 (HM09-C18, agent-proposed MCP install card — held out of scope). Verdict in deep-eval-group4: ACCEPT. Prioritization row 57: V/E 1.17, buildable=No only because the TERM-1 `YourShellRegion` consumer and the A05-G2 projection fix precede it.

## 3. What to build

One new module `halbert_core/halbert_core/tools/terminal_tools.py` plus registration in `tools/executor.py` (`_register_builtins`, pattern at :179+: name, coroutine, schema), with exactly two tools:

1. `read_terminal(session_id, start_line=0, count=200)` — returns scrollback from a watched pane. Two paths: (a) agent-owned PTY sessions registered in `TerminalSessionManager` (`streaming/session_manager.py`, `get(session_id)`) read server-side from the PTYSession's replay ring/buffer; (b) user-owned renderer panes round-trip over the existing WS: `dashboard/routes/websocket.py` gains a `read_buffer` request message type carrying a generated request id; the frontend handler (hook into `hooks/useTerminalSessions.ts` / the TerminalTile xterm instance) serializes `start_line..start_line+count` lines from the xterm buffer and replies on the same socket with the matching id. Backend awaits a per-request `asyncio.Future` with a bounded timeout (suggest 5s, constant next to `_QUEUE_MAXSIZE` in `streaming/terminal_bridge.py` for cohesion); on timeout return ok=False error="renderer_timeout" — never hang a turn. All returned text passes the display seam: `security/display_transport.py:_redact_display_text` (registry pass then pattern pass, in that order — the Tier-2 choke-point order) and then `security/echo_guard.py:EchoGuard.scan_outbound`/`redact` so a secret the user pasted into their own shell cannot round-trip into the model's context.

2. `close_terminal(session_id)` — hide-only. Sets a hidden flag on the tile (extend `TerminalSessionManager` state or, for renderer panes, send a `hide_tile` WS message consumed by `useTerminalSessions.ts`); never sends SIGTERM/SIGKILL, never calls `PTYSession.kill`. The process keeps running and the tile can be re-shown by user action. Record the hide in the audit log via the existing `obs/audit.write_audit` pattern from `tools/base.py`.

Withdraw-not-refuse (HM10-C17): registration in `executor.py` is conditional — `read_terminal`/`close_terminal` are only added to the tool catalog when `has_capability(CAP_TERMINAL)` (`capabilities.py:499`, constant `CAP_TERMINAL` at :81) is true AND a renderer/agent-session is attached (probe: `TerminalEventBus.has_subscribers` for the agent-owned path; the WS manager's connection count for the renderer path). When the gate fails, the tools are absent from the list presented to the model — not present-and-failing. Implement the gate as a small reusable helper in the registration path (e.g. `executor.register_if(name, fn, schema, predicate)`) so the convention is shared, and note it in the module docstring of `terminal_tools.py`.

Prerequisite check before starting: confirm whether R-06's merged display projection closed A05-G2 (timeline reload serving persisted tool blocks with raw args, in `dashboard/routes/agent.py` get_timeline). If not, land the small projection fix first in this same branch — the read seam and the timeline must share one projection so the agent reads the same redacted text the user sees. Read F17 (desktop RPC bridge reference, deep-eval line 469) for the request-id/response-matching pattern before writing the WS round-trip.

## 4. What NOT to build

- No command execution, injection, or keystroke sending into any pane — read-only plus hide-only. Commands staged from the UI are staged, never executed (standing rule).
- `close_terminal` never kills the process: no SIGTERM/SIGKILL, no `PTYSession.kill`, no session removal from `TerminalSessionManager._sessions`.
- HM09-C18 (agent-proposed MCP server install as a staged card) is held per FD-7 — not in this unit.
- No new WS endpoint: extend the existing `/ws` message envelope in `dashboard/routes/websocket.py`, do not add a third socket.
- No scrollback persistence, no terminal-content memory writes, no recall of pane text in later turns (that would need a memory-packet ruling).
- No frontend visual redesign of TerminalTile/InlineTerminals beyond consuming the `hide_tile` message; no new colours (any indicator uses shared-tokens only), no emoji.
- No PTY reattach, foreground-command guardrails, or bounded-wait work — that is TT-04a's packet (`streaming/session_manager.py`, `tools/safety.py`).
- No reconnect/backoff changes to the WS — GW-A owns the event-stream reconnect seam.

## 5. Target files
- `halbert_core/halbert_core/tools/terminal_tools.py` [new file]

## 6. Dependencies

TT-04a, GW-A

## 7. Effort

**S-M** — S-M, one branch. The plumbing all exists: `TerminalSessionManager` already keys sessions by id with a get/list surface; `/ws/terminal/{session_id}` and `/ws` already carry terminal traffic with auth (`websocket_authenticated`); the request-id/future pattern is a small addition modeled on F17. The genuinely new code is: one tools module (~250 lines with schemas), one conditional-registration helper in `executor.py`, one WS message pair (request/response) plus the frontend serializer reading the xterm buffer, the hide-flag plumbing, and the display-seam/echo-guard application (both functions already exist and are importable). The M rather than S comes from the two-pane duality (agent-owned PTY vs user renderer pane), the bounded-timeout round-trip needing careful cancellation so a dead renderer cannot hang a turn, and the possible A05-G2 pre-fix if R-06 did not close it (small, same branch). No state_machine.py touch, no hot-file contention beyond `executor.py` registration lines.

## 8. UX rationale

Agent-visible: the model's tool catalog gains `read_terminal` and `close_terminal` only when a terminal surface is actually attached; otherwise the tools simply are not there (withdraw, not refuse) so the model never attempts a doomed call. The agent, speaking as the computer in first person, can now ground terminal claims in measured pane content ("the dev server you started is still serving on port 5173") instead of guessing. User-visible: when the agent closes a tile, the tile disappears from `InlineTerminals` but the process keeps running — the user can re-show it, and nothing they were running dies. No conversation-list, no new surface, no notification chrome: this is tool-side capability only. Any hidden-tile indicator (if the frontend chooses to show one) uses shared-tokens colours and no emoji. Guest fronting: `read_terminal` on user panes is denied for guests per the FD-2 default — the tool is withdrawn from the guest tool list, consistent with the guest persona's execute-level deny posture.

## 9. Acceptance criteria

1. With a renderer attached and `has_capability("terminal")` true, the tool list presented to the model contains `read_terminal` and `close_terminal`; with no renderer attached (or capability off, or guest fronting), both names are absent from the catalog (asserted on the serialized tool list, not on a call failure).
2. `read_terminal` on an agent-owned PTY session returns the pane's buffered lines honouring `start_line`+`count`, with text demonstrably passed through `_redact_display_text` and `EchoGuard` (a planted registry secret in pane output appears redacted in the tool result).
3. `read_terminal` on a renderer pane completes the WS round-trip with matching request id; a renderer that never answers yields ok=False with the timeout error inside the bounded window, and the turn continues.
4. `close_terminal` hides the tile and the underlying `PTYSession` remains in `TerminalSessionManager._sessions` with the process still alive (pid still exists); no kill path is invoked.
5. The timeline projection and the read seam produce identical text for the same lines (A05-G2 precondition verified or fixed in-branch).

## 10. Verification (measured state, not model judgment)

Runnable, measured checks: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k terminal_tools -q` (new test module `halbert_core/tests/test_terminal_tools.py`) must pass, asserting: (a) tool-catalog membership flips with the capability/renderer gate — catalog list membership compared as exact string sets; (b) redaction — plant a value registered in `ingestion/redaction_registry` into a fake pane buffer, assert the tool output contains the redaction marker and not the plaintext (exit 0 on assert); (c) timeout — stub WS that never replies, assert the future resolves to ok=False within the bounded window using `asyncio.wait_for` in the test itself (wall-clock bound asserted < timeout+1s); (d) close-is-hide — spawn a real short-lived PTY (`sleep 30`) via `TerminalSessionManager.spawn`, call `close_terminal`, assert `manager.get(session_id) is not None` and `os.kill(pid, 0)` succeeds (process alive); then kill it in teardown. Plus the regression gate: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` shows no new failures beyond the known main baseline (capture baseline first per CLAUDE.md — `main` is not green). Frontend: `npm test -- --run useTerminalSessions` (or the TerminalTile suite) passes with the hide-tile handler covered. Every check is exit-code/stream/membership measured; none is a model judgment.

## 11. Exclusions

- HM09-C18 (agent-proposed MCP install staged card) — held per FD-7; goes to the B6 MCP-server audit follow-up (AUDIT existing mcp/server.py first), not this branch.
- PTY reattach contract, foreground-command guardrail (nudge `npm run dev` to background), progress labels, bounded wait — TT-04a owns those (`streaming/session_manager.py`, `tools/safety.py`); this unit only consumes the session registry TT-04a stabilizes.
- WS reconnect owner, typed error envelope, SSE/WS reconnect — GW-A owns the transport seam; TERM-02 assumes the socket stays up within one request window and only adds its message pair.
- Terminal-content persistence to conversation history / memory — belongs to the continuity/memory workstream (needs a founder ruling on retaining pane text); dropped here deliberately.
- TERM-1's `YourShellRegion` mounting — a separate packet's consumer; TERM-02 builds the tools against `TerminalSessionManager` + the existing tiles so it lands independent of that mount.
- Generalizing withdraw-not-refuse across every existing capability-gated tool — this unit establishes the helper and applies it to the two terminal tools; sweeping the rest of the catalog is a follow-up noted in the registration path, per the deep-eval "shared convention" opportunity (document once, here).

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
