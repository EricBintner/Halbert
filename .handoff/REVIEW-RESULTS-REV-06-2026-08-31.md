# REV-06 Review Results — Core Agent Evolution, Intake Pipeline, Reactive Slices & SourcePrep RAG

**Date:** 2026-08-31
**Reviewer pass:** GLM-5.3 (REV-06, per MASTER-REVIEW-INDEX reassignment)
**Packet:** `.handoff/REVIEW-PACKET-06-AGENT-CORE-RAG-AND-REACTIVE-SLICES.md` (2026-08-29)
**Scope reviewed (current code, not packet-era):** `agents/state_machine.py`, `agents/states.py`, `agents/events.py`, `agents/threads.py`, `agents/conversation_sqlite.py`, `agents/error_recovery.py`, `agents/react_agent.py`, `agents/llm_client.py`, `agents/receipt.py`, `agents/conversation_status.py`, `intake/*`, `context/assembler.py`, `context/adapters.py`, `eval/crag.py`, `findings/*`, `proactive/*`, `integrations/sourceprep_*.py`, `dashboard/routes/agent.py` (LLM adapter + routes), `integrations/wyoming_agent.py`, `compression/*`.

**Method:** full read of the target modules, adversarial verification of every candidate (code-path trace end to end, discard of unsubstantiated candidates), and read-only test runs with `arch -arm64 .venv/bin/python wt_pytest.py`.

---

## 1. Verdict per area

| Area | Verdict |
|---|---|
| **Agent state machine (turn lifecycle, locks, cancellation)** | **FAIL — 2 confirmed regressions** (F1 stale `_defanged_query`, F2 `response_modality` UnboundLocalError) leave 30 tests red across the agent-core suites. The turn-lock/cancellation/supersede machinery itself is sound; the failures are in the prompt-assembly seams. |
| **Thread store & receipts (Plan A)** | **PASS with findings.** Locking discipline (`_locked`, per-close lock in `tick`), transactional `merge_thread`, receipt fencing/budgeting, and the superseded-turn recording are careful and tested. One confirmed data-loss gap on the merge path (F5). |
| **Intake pipeline & budget allocation** | **PASS.** Signals → complexity → skills → budget chain is clean; budget table sums to totals; greeting fast-path guard is correctly narrowed (prefix-match starvation avoided). |
| **Context assembler (window, receipt slot, budgets)** | **PASS with observations.** `build_conversation_window` / `receipt_allowance` / `fit_receipt` are coherent (one measurer, whole-line cuts, open-loop reservation). The compression cascade is effectively unreachable on the agent path at common tiers (F7). |
| **CRAG evaluator** | **PASS.** Thread receipts correctly excluded from retrieval voting; per-turn overrides and `secure` are threaded; parsing is robust. (Cost note: one extra LLM round-trip per evaluation site, up to two per loop.) |
| **SourcePrep scoped RAG** | **FAIL on one seam.** Scope resolution against the daemon's provisioned scope list (narrow-to-ancestor, role resolved locally, never sent as `role=`) is hardened and good. But the **SEARCHING state bypasses the per-turn/skill scope entirely** (F3). |
| **Findings engine & proposal rollback** | **PASS with one confirmed gap.** Stores, precedence, blast radius, dry-run coverage, idempotency guard against double-approval, and WriteConfig-backup file rollback are present. The chmod rollback set excludes a change that fails *after* `os.chmod` (F4) — the packet's "prove atomic restoration" directive is answered **no** for that window. |
| **Reactive slice / proactive bus / gate / morning report** | **PASS.** Bus thread-safety (loop attach, `call_soon_threadsafe`, closed-loop fallback) and the gate's fail-closed posture are correct; quiet-hours engine delegation is sound. |
| **Packet verification command** | **STALE.** `test_intake.py` / `test_findings_*.py` / `test_proactive_*.py` no longer exist; the suites are `test_intake_pipeline.py`, `test_findings.py`, `test_proactive_events.py`, `test_proactive_gate.py`, etc. (all green: 242 passed). |

---

## 2. Findings (most severe first)

### F1. CONFIRMED — Previous turn's question leaks into the next turn's planning prompt (`_defanged_query`)

- **Where:** `halbert_core/halbert_core/agents/state_machine.py:1511` (read), `:2693` (reset — too late), `:2716` (set).
- **Scenario:** `_defanged_query` lives on the shared `AgentStateMachine` instance, not on the per-turn `StateContext`. It is set in `_handle_responding` (turn 1) to `defang_user_input(MSG_1)` and reset to `None` only at the *top of the next RESPONDING* — which runs **after** turn 2's PLANNING. So turn 2's `_build_messages` reads `getattr(self, "_defanged_query", None) or self.ctx.user_query` and appends **turn 1's question** as the final user message of turn 2's planning prompt. From the second turn on, the model plans against the previous turn's question (RESPONDING is correct because the reset precedes the set within the same turn). This is precisely the cross-turn shared-state leak class the codebase's own E-2 comments warn about for the shared LLM adapter.
- **Evidence:** `halbert_core/tests/test_thread_e2e.py::test_second_message_sees_the_first` is red on this branch with the final message of `planning_2` ending in MSG_1 ("Set up a samba share…") instead of MSG_2 ("Can you also make that share read-only for guests?"); `test_past_reference_pulls_in_closed_thread_without_a_tool_call` fails the same way.
- **Suggested fix:** move the reset to the top of `process()` (under the turn lock, next to `self.cancelled.pop`), or store the defanged query on `StateContext` (per-turn) instead of `self`.

### F2. CONFIRMED — `response_modality` UnboundLocalError breaks the no-prompt-builder RESPONDING path

- **Where:** `halbert_core/halbert_core/agents/state_machine.py:2735` (assigned only inside `if self.prompts:`) vs `:2753` (referenced in the `else:` branch).
- **Scenario:** an agent constructed with `prompt_builder=None` — the documented fallback path (`_fallback_identity`'s docstring says it exists precisely for a broken prompts package) — raises `UnboundLocalError: local variable 'response_modality' referenced before assignment` on **every** RESPONDING entry. The `_drive` terminal guard then ends the session with a non-recoverable error: the turn produces no answer. Production `get_agent()` always wires a builder today, so the live dashboard is safe, but the defensive path is dead code and the CI signal is destroyed: ~27 of the 30 red agent-core tests fail on this exact error (`test_state_machine*.py`, `test_cognition_tick_once.py`, `test_agent_integration.py`, `test_agent_chat_off_the_event_loop.py`).
- **Suggested fix:** hoist `response_modality = "text"` above the `if self.prompts:` branch (compute once, use in both arms).

### F3. CONFIRMED — SEARCHING state bypasses per-turn and skill retrieval scopes

- **Where:** `halbert_core/halbert_core/agents/state_machine.py:2191` (`self.rag.search(search_query, limit=5)` — no scope/role), against `:1634` where PLANNING's `assemble(retrieval_scope=…)` is the *only* consumer of `ctx.retrieval_scope`.
- **Scenario:** the "Analyze" button and the GPU deep-scan route (`dashboard/routes/gpu.py:193-199`, `retrieval_scope="host"`) hardwire a scope for the turn. PLANNING's context assembly honors it (assembler → `SourcePrepAdapter.search(scope=…)` → hardened `resolve_scope`). But a typical turn then routes SEARCHING (loop 0, no tool calls, non-greeting), which calls `rag.search` positionally with **no scope** — `SourcePrepAdapter._route` falls back to the `scope_for_query` keyword heuristic, which returns `None` (unscoped global union) for anything ambiguous. The unscoped hits land in `retrieved_context` and compete for the `[:5]` slots RESPONDING renders, so a scoped turn can be answered out of the union of all corpora — the exact scoping violation `resolve_scope` exists to prevent. Skill role/scope is equally ignored on this path.
- **Evidence:** `grep retrieval_scope` — one consumption site (line 1634); `_handle_searching` has none. `test_gpu_routes.py` only asserts the parameter reaches `process()`, not that SEARCHING honors it.
- **Suggested fix:** thread `scope=self.ctx.retrieval_scope` (plus the active skill's role/scope, when intake carries one) into the `rag.search` call in `_handle_searching`; alternatively route SEARCHING through the same `_search_retrieval` helper the assembler uses.

### F4. CONFIRMED — chmod changes failing after `os.chmod` are excluded from the rollback set

- **Where:** `halbert_core/halbert_core/findings/proposal_generator.py:265-277` (exception handler appends to `applied` only when `change.get("action") != "chmod"`), `:561-563` (`os.chmod` then `write_audit`).
- **Scenario:** `_apply_chmod` performs `os.chmod(path, mode_int)` and *then* writes the audit record. `write_audit` (`obs/audit.py`) does raw file I/O (open/append under `log_subdir`, which mkdirs) and **can raise** (disk full, read-only fs, permission loss). If it raises, `_apply_change` propagates, and the exception handler in `execute_proposal` deliberately excludes chmod changes from the rollback list — so the already-applied mode change is **not** restored, while the proposal is marked `ROLLED_BACK` and the UI reports everything undone. Multi-change proposals (e.g. `permissions_hygiene` findings emit several chmod changes) make the window reachable in practice.
- **Suggested fix:** in the exception handler, for a chmod change that raised, re-`stat` the path and append `{"kind": "chmod", "path": …, "old_mode": <current mode if it differs from the recorded expectation>}`; or wrap the post-chmod audit write in its own try so an audit failure can never fail the change after its side effect landed. (Packet directive "prove previous file state and permissions are atomically restored": **not proven** — this is the gap; the WriteConfig-backup path and the reverse-order rollback are otherwise sound.)

### F5. CONFIRMED — `merge_thread` orphans the merged thread's open loops and terminal blocks

- **Where:** `halbert_core/halbert_core/agents/conversation_sqlite.py:1820-1879` (moves `messages`/`messages_fts`/`receipts_fts`/`conversations` only); `open_loops` (schema at `:437`, key `thread_id`) and `terminal_blocks.thread_id` are untouched.
- **Scenario:** a spurious split merged back via `resume_thread` → `merge_back` leaves the young thread's `open_loops` rows and `terminal_blocks` rows pointing at the `status='merged'` thread, which is never selected again. The surviving thread's `begin_turn` R2-N2 note (`list_open_loops(thread_id)`) and the watched-shell terminal hint (`WatchedShellProcessor.build_hint_text`) never see them — continuity data silently lost on every merge. Bounded by the grace window (only young threads merge), hence low severity, but it is a real thread-store consistency gap in the corruption class the packet asks about.
- **Suggested fix:** inside the `merge_thread` transaction, `UPDATE open_loops SET thread_id = dst WHERE thread_id = src` and the same for `terminal_blocks` (or record-and-sweep them like `receipts_fts`).

### F6. PLAUSIBLE (low) — Wyoming voice turns abandon the `process()` generator without `aclosing`

- **Where:** `halbert_core/halbert_core/integrations/wyoming_agent.py:168-187`.
- **Scenario:** the dashboard routes explicitly `aclosing()` the `process()` generator because "process() holds the agent's turn lock across every yield" and relying on the loop's async-generator finalizer delays the release (`routes/agent.py:1485-1502`). Wyoming's `_collect_turn` `break`s on `response_complete` (and `wait_for` cancels on timeout) with **no** `aclosing`: the generator is left suspended holding the turn lock until CPython's asyncgen finalizer hook schedules its `aclose` (usually the next loop tick, but not guaranteed — a concurrent chat turn in that window emits a spurious "waiting" status behind a turn that already finished). Mechanism confirmed; practical impact is a transient lock hold, hence PLAUSIBLE.
- **Suggested fix:** wrap the `async for` in `aclosing(agent.process(...))` exactly as `send_message`/`confirm_action` do.

### F7. CONFIRMED (dormancy) / PLAUSIBLE (content risk) — compression cascade unreachable at common tiers; LLMLingua force-tokens miss CLI flags

- **Where:** `context/assembler.py:314` (`combined_tokens > self._compressor_threshold` = 4000) vs `intake/budget.py` tier totals (MEDIUM total = 2000 — and `assemble` overrides `max_tokens` with `intake.context_budget.total`), and `compression/lingua_compressor.py:47-67` (`FORCE_TOKENS` has no `-`).
- **Scenario (a), confirmed arithmetic:** on the production planning path the assembled context is capped by the intake budget; for TINY/SMALL/MEDIUM/LARGE (400/800/2000/4000 totals) the 4000-token cascade trigger can never fire (LARGE needs >4000 to trigger, total is exactly 4000 with sources under it), so the "Phase 72 compression cascade" the packet credits is dead wiring on the agent path for every mainstream local tier — only XLARGE/MASSIVE (8000/16000) reach it.
- **Scenario (b), plausible:** when the cascade *does* run (XLARGE/MASSIVE), "standard" keeps 40% of tokens and `FORCE_TOKENS` preserves `/ = | > < $ \` #` but **not `-`**, so command flags (`-rf`, `--force`, `PermitRootLogin no` option names) inside Commands lines and log excerpts are prunable — the exact "critical syntax in system logs" the packet's retention directive names.
- **Suggested fix:** if the cascade is meant to be live, trigger on a fraction of the intake budget rather than a fixed 4000; add `-` (and `--`-aware tokens) to `FORCE_TOKENS`. If it is not meant to be live on the agent path, say so in the packet-facing docs.

### F8. PLAUSIBLE (low) — bare `TypeError` fallback silently de-scopes retrieval

- **Where:** `context/assembler.py:599-604` (`except TypeError: … return await self.retrieval.search(query, limit=5)`).
- **Scenario:** the retry-without-scope exists for adapters that don't take `scope`/`role` keywords, but it catches **any** `TypeError`, including one raised *inside* a scope-aware adapter after it received the scope. Today's `SourcePrepAdapter` catches its own internals broadly so the path is unlikely, but a future scoped adapter that raises `TypeError` mid-flight gets silently retried **unscoped** — a scoping violation with only a debug-level log. Fix: check the signature (`inspect`) once, or re-raise `TypeError`s that originate inside the call.

### Low-severity observations (verified, no immediate action forced)

- **O1.** `agents/react_agent.py:300-313` — when the model emits two calls to the *same tool* in one response, the reversed search for "the corresponding observation" attaches the **last** observation for that name to **both** `role:"tool"` messages; the first call's result is lost. Dormant code (no production constructor found), but it is exported from the package.
- **O2.** `state_machine.py:1814-2229` — tool calls named `search_discoveries` / `recall_memory` are never executed as such; `_handle_searching` substitutes the generic RAG/memory search and marks the call `success`. With production `memory_service=None` (R9 fence), `recall_memory` "succeeds" while recalling nothing — the model is told an action worked that did not.
- **O3.** `spawn_subagent` / `await_subagent_completion` and the `WAITING_FOR_EVENTS` status have **no callers** — the subagent manager is never wired into `AgentStateMachine` construction, so that entire status branch is unreachable (consistent with the earlier "orchestrator = stubs" audit).
- **O4.** Test drift, not production: one persistence test's `fake_execute` doesn't accept the new `speaker_role` kwarg added in 58adce12 (`ToolExecutor.execute` does, `executor.py:308-315`). Update the double.

---

## 3. Test evidence (read-only runs)

- Intake / compression / proactive / findings / sourceprep suites: **242 + 225 passed** (green).
- **Agent-core suites: 30 failed / 108 passed** — `test_state_machine.py`, `test_state_machine_meta_tools.py`, `test_state_machine_turn_lock.py`, `test_state_machine_turn_persistence.py`, `test_thread_e2e.py`, `test_cognition_tick_once.py`, `test_agent_integration.py`, `test_agent_chat_off_the_event_loop.py`. Breakdown: ~27 × F2 (`response_modality` UnboundLocalError), 2 × F1 (`_defanged_query` stale leak), 1 × O4 (speaker_role test double).
- CRAG scoring, thread store, conversation sqlite, receipt-window, assembler-secure, GPU-route suites: green.

The F1/F2 pair should be treated as **release blockers for the agent core**: one corrupts every multi-turn planning prompt, the other renders the fallback answer path dead and the CI red.

---

## 4. Packet claims now resolved (since the 2026-08-29 packet)

1. **Chat path retirement & unified agent loop** — confirmed: no `chat.py` route, `AgentRunner`-style unified state machine with the `LLMClientAdapter` (guide/specialist/vision routing, pinned-model support, secure-turn fail-closed) is the only path.
2. **CLARA removal** — confirmed (conversation summarization replaced by deterministic thread receipts; compression cascade ported but see F7).
3. **Plan A continuous conversation** — landed well beyond the packet: thread store, receipts, turn lock with bounded acquire, supersede/cancel lifecycle, per-model `history_budget`, `num_ctx` sizing with high-water-mark release, receipt slot budgeting (`receipt_allowance`/`fit_receipt`). The seams read as reviewed-hardened (explicit in-code review notes).
4. **Packet open item "unused `SendMessageRequest.context`"** — **resolved by removal**: the request model now carries `model`/`tier`/`endpoint_id`/`scope`/`images`, all consumed.
5. **Scoped retrieval hardening** — beyond the packet: `resolve_scope` (narrow-to-provisioned-ancestor), role→scope resolution done locally (never `role=` to the daemon), applied-scope warning checks, per-source-directory cap with score sort. F3 is the remaining seam.
6. **Variant gating (U6)** — confirmed: home/home-light variants get no SourcePrep at all (`retrieval_adapter_for_variant()` → None; `app_seam` `skip_retrieval`), with `HA` tools answering from live state.
7. **Speaker-role plumbing (58adce12)** — confirmed end-to-end: `process(speaker_role=…)` → `StateContext.speaker_role` → `_run_tool_streaming` → `ToolExecutor.execute(speaker_role=…)` → `RoleGate`; Wyoming passes `"unknown"`. Only test doubles lag (O4).
8. **GPU tools as agent tools (162f3965)** — confirmed registered Linux-only and routed through the agent specialist path with `retrieval_scope="host"` (see F3 for the scope seam).
9. **Still open from the packet:** role-scoped config harvesting runtime (design + TODO only), Personality Builder Phase 3 UI.

## 5. Discarded candidates (adversarially verified false)

- *`tool_call.function.arguments` as JSON string breaking SEARCHING/READING* — discarded: `model/client._normalise_tool_calls` and `routes/agent._as_tool_calls` both coerce to dicts.
- *`confirm_action` inheriting another turn's `max_tokens`/`temperature`* — discarded: any `/message` between a pause and its confirm supersedes the paused turn (evicting it), so the paused turn's own params are provably the last written when its confirm runs.
- *`_handle_error` unreachable conversation-status transitions* — discarded: `TRANSIENT_ERROR→IN_PROGRESS`, `IN_PROGRESS→ERROR`, `BLOCKED→IN_PROGRESS` all exist in the A2a table; terminal-status writes are guarded by `is_terminal()`.
- *turn-lock double-release / paused-turn double `end_turn`* — discarded: `_end_turn` is idempotent via `turn_context` clearing and both finallys check `AWAITING_CONFIRMATION`.
- *`_run_tool_streaming` event loss on the tool-finished path* — discarded: the `asyncio.wait` loop plus post-break queue flush covers the completion race.

---

**Bottom line:** the architecture (turn lifecycle, receipts, scoped retrieval, findings lifecycle) is in materially better shape than the packet describes, but two regressions in the state machine's prompt-assembly seams (F1, F2) currently break 30 agent-core tests and corrupt multi-turn planning; F3 and F4 each violate a guarantee this review was specifically asked to verify (retrieval scoping, rollback safety).