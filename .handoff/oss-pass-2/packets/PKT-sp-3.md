# PKT-SP-3 — Multi-tool dispatch loop (fix data-loss)

Tier: **fable**   Milestone: **M1**   Effort: **M**
Collision lane: **A**   Merge order: **1/9 in A**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Land immediately (step 0), by user directive.**

---

## 1. Packet

**SP-3** — Multi-tool dispatch loop (fix data-loss).

## 2. User problem

The PLANNING state at state_machine.py:3426 dispatches only `response.tool_calls[0]` and silently drops every additional tool call the model emitted. If a local model emits two tool calls (e.g., read_file + run_command), the second vanishes with no log, no observation to the model, and no error. This is silent data loss: the model believes both calls were issued, but only the first ran. The EXECUTING handler at :4211 reads `self.ctx.tool_calls[-1]` (the last recorded call), so even if PLANNING recorded all calls, only one would execute per PLANNING→EXECUTING cycle, and the confirmation path at :4257-4281 transitions to AWAITING_CONFIRMATION and returns, abandoning any unprocessed calls from the same response. Additionally, there is no seam at the RESPONDING/finalize edge for verification gates to intercept a model that stopped with a wrong answer and nudge it to try again — the stop-gate chain is the prerequisite for the entire verification/eval attach surface (HM04-C1/C2/C4).

## 3. What to build

Two changes in state_machine.py, shipped together since they touch the same hot file at two distinct anchor-sensitive points.

**Part 1 — Multi-tool dispatch loop (the data-loss fix).** Replace the single-call dispatch at PLANNING (~:3425-3501) with a sequential loop over `response.tool_calls`. Each call goes through the same gate path: meta-tool inline handling, `_already_called` dedup, `ToolCall` recording on `ctx.tool_calls`, routing to SEARCHING/READING/EXECUTING. The critical invariant: when call N returns `requires_confirmation` (the :4257 path), calls N+1..M must NOT be dropped. They are staged — recorded on `ctx.tool_calls` with status "pending" — and the turn transitions to AWAITING_CONFIRMATION for call N only. On confirmation resume (AWAITING_CONFIRMATION→EXECUTING), the executor picks up the NEXT pending call after the confirmed one completes. The OBSERVING→PLANNING loop re-entry already handles this if PLANNING is re-entered with staged calls: PLANNING must check for staged (un-executed) tool calls before making a new LLM round-trip, and dispatch the next staged call instead. One tool-result row per call, in order, each capped at _TOOL_RESULT_CHARS. The `_already_called` guard at :3521 already prevents re-running identical calls; it continues to work per-call within the loop.

**Part 2 — Stop-gate chain at the RESPONDING/finalize edge.** Add a `STOP_GATES: List[Callable]` class-level registry (empty at ship). At the RESPONDING state's finalize edge — after the stream completes and `full_response` is assembled (~:4811), before the echo guard at :4841 — iterate the registered gates. Each gate receives `(ctx, full_response)` and returns either `None` (pass, no nudge) or a string nudge. The first gate that returns a nudge: (a) persists the attempted answer as an interim assistant row via `ctx.add_observation`, (b) clears `ctx.response_chunks` and `ctx.final_response`, (c) adds the nudge as an observation, (d) transitions back to PLANNING for another attempt. Each gate is wrapped in try/except so a broken gate never blocks an answer — on exception, log at warning and treat as pass. The four honesty invariants: attempted answer kept (interim row persisted), final_response cleared, interim row visible to the model on the next PLANNING pass, each gate individually wrapped.

## 4. What NOT to build

No gates are registered — the stop-gate chain ships with `STOP_GATES = []` and zero consumers. Do not build any verification gate logic (that is HM04-C1/C2/C4's scope, deferred to the testing-evals packet). Do not change the confirmation UX flow (the tool card, the BLOCKED status, the pending_confirmation dict shape) — only the dispatch loop's behavior when confirmation interrupts a multi-call sequence. Do not change `_handle_meta_tool`'s inline thread meta-tool handling — meta-tools within a multi-call response are still handled inline per-call. Do not change `_run_tool_streaming`'s terminal event relay or the `_TOOL_RESULT_CHARS` cap. Do not change the `_already_called` dedup logic. Do not add parallel/concurrent tool execution — calls run sequentially, each individually gated. Do not build the typed `turn_exit_reason` vocabulary (MP-2's HM01-M2) — the stop-gate seam and the exit reason should share one typed surface, but that surface is designed together with MP-2, not in this packet. Do not change the AWAITING_CONFIRMATION resume path's confirmed-flag reading (:4238-4241).

## 5. Target files
- `halbert_core/halbert_core/agents/state_machine.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M. The multi-tool dispatch loop is a focused change in one hot file at one anchor-sensitive point (PLANNING's tool-call routing). The complexity is in the confirmation-resume invariant: when call N requires confirmation, calls N+1..M must be staged, not dropped, and the resume path must pick up the next staged call after the confirmed one completes. This requires a `pending_tool_calls` queue on `ctx` (or equivalent) that PLANNING checks before making a new LLM round-trip. The stop-gate chain is S for the seam (registry + iteration + wrap) plus S for the honesty invariants (interim row persistence, response_chunks clearing, PLANNING re-entry). The two parts touch the same file at two distinct points (PLANNING ~:3425 and RESPONDING ~:4811), so they ship together to avoid two separate hot-file conflicts. The state_machine.py file is lane A (hot file), so this packet must be sequenced against other state_machine.py work.

## 8. UX rationale

No visible UX change for single-tool-call turns — the common case is unchanged. For multi-tool-call turns (primarily local models that emit bracket-notation or multiple structured calls), the user now sees both tool cards render in sequence instead of only the first. If call N requires confirmation, the confirmation card appears for call N; after the user confirms, call N+1's card appears and runs. The user is never asked about N+1 before N completes — sequential staging, not parallel prompts. The stop-gate chain is invisible at ship (zero gates registered). When gates are later registered by the testing-evals packet, a gate nudge would appear as a brief thinking event ("trying again with a check") before the model re-attempts, with the interim answer visible in the conversation as a collapsed row. Commands remain staged, never executed — the confirmation path is unchanged in its UX, only in what happens to the calls that were waiting behind the confirmed one.

## 9. Acceptance criteria

1. A model response carrying two tool calls results in both executing in order, each producing its own tool_start/tool_complete event and its own observation row, capped at _TOOL_RESULT_CHARS.
2. A model response carrying two tool calls where the FIRST requires confirmation: the first's confirmation card renders, the second is staged (recorded on ctx.tool_calls with pending status), and after the user confirms the first, the second executes without a new LLM round-trip.
3. A model response carrying two tool calls where the SECOND requires confirmation: the first executes to completion, then the second's confirmation card renders, and no calls are lost.
4. The `_already_called` dedup still prevents re-running an identical call within the same turn, even across a multi-call sequence.
5. The stop-gate chain with zero gates registered is a no-op: the RESPONDING finalize edge behaves identically to the current code.
6. A gate that raises an exception is logged at warning and treated as pass — the answer is delivered normally.
7. Meta-tools (new_thread, recall_thread, resume_thread) within a multi-call response are still handled inline per-call, not dispatched to EXECUTING.

## 10. Verification (measured state, not model judgment)

Write a test at halbert_core/tests/agents/test_state_machine_dispatch.py with these test IDs:

- `test_multi_tool_dispatch_all_calls_execute` — mock llm_client.chat to return a response with `tool_calls=[call_a, call_b]`; mock tool_executor.execute to return success for both; drive the state machine through PLANNING; assert both tool calls appear on `ctx.tool_calls` with status "success", two `tool_start` and two `tool_complete` StreamEvents were yielded, and two observation rows were added.

- `test_multi_tool_dispatch_confirmation_stages_rest` — mock response with `tool_calls=[call_a, call_b]`; mock executor so call_a returns `requires_confirmation=True`; drive through PLANNING→EXECUTING; assert call_b is recorded on `ctx.tool_calls` with status "pending", the state transitions to AWAITING_CONFIRMATION, and call_b has NOT been executed (executor.execute called exactly once). Then simulate confirmation (set `ctx.pending_confirmation["confirmed"] = True`), resume through AWAITING_CONFIRMATION→EXECUTING; assert call_b executes and completes.

- `test_stop_gate_chain_zero_gates_is_noop` — with `STOP_GATES = []`, drive a simple turn to RESPONDING; assert the response is delivered identically to the pre-change behavior (same response_chunks, same StreamEvent sequence after the stream completes).

- `test_stop_gate_chain_broken_gate_passes` — register a gate that raises `RuntimeError`; drive a turn to RESPONDING; assert the answer is delivered normally and a warning was logged.

- `test_stop_gate_chain_nudge_replans` — register a gate that returns "check your arithmetic"; drive a turn to RESPONDING; assert the attempted answer was persisted as an observation, `ctx.response_chunks` was cleared, the nudge appears as an observation, and the state transitions back to PLANNING.

Run: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/agents/test_state_machine_dispatch.py -v` — all five tests pass. Also run the existing state machine tests to check for regressions: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/agents/ -k state_machine -v`.

## 11. Exclusions

The following items from the SP-3 section file are excluded from this packet:

- **Verification gate implementations (HM04-C1, C2, C4)** — deferred to the testing-evals packet (T-series). This packet builds the seam (the chain, the registry, the wrap); the gates themselves are separate units that attach to it.
- **Typed `turn_exit_reason` vocabulary (HM01-M2)** — belongs to MP-2 (provider failure semantics). The deep-eval notes the stop-gate chain and MP-2's exit reason share a typed surface at the finalize edge; they should be designed together, but the exit reason vocabulary is MP-2's scope.
- **Batching clause in the system prompt (SP-2 dependency)** — SP-2's batching clause tells the model it may emit multiple tool calls in one response. That clause is gated on this packet's dispatch loop landing first (otherwise the model is told to do something that silently drops calls). SP-2 rides after this packet merges.
- **Parallel/concurrent tool execution** — dropped. The founder-noted behavior change is sequential dispatch with individual gating, not parallel execution. Parallel execution would require a different confirmation UX (batch confirm) and a different observation model.
- **`_already_called` relaxation for multi-call sequences** — not changed. The dedup guard prevents re-running the identical call (same name, same args); a multi-call sequence with two DIFFERENT calls to the same tool (e.g., read_file on two paths) is unaffected because the args differ.

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
