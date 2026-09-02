# DISPATCH OPUS-01 — Agent core: state-machine regressions (REV-06) and the test baseline

**Owner:** an Opus session. **Effort:** high care, small diffs. **Why Opus:** the prompt-assembly seams are subtle (REV-06 warned "read the exact seams before touching anything"); two of these bugs corrupt multi-turn planning in production.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §3.3, §4, §6.1. Evidence ids (area F2, all adversarially verified): `R06-F1`, `R06-F2`, `R06-F3`, `R06-F4`, `R06-F5`, `R06-F6`, `R06-F8`, `R06-O1`, `R06-O2`, `R06-X1`, `R04-F8`, `R06-BASE`; plus `SE-11`, `CC-05..09`. Full triage: `.handoff/audit-2026-09-01/PYTEST-BASELINE-TRIAGE.md`. Original report: `.handoff/REVIEW-RESULTS-REV-06-2026-08-31.md`.

## Shared rules
- Fresh worktree off main: `git -C /Volumes/4TB-BAD/Halbert worktree add ~/.config/superpowers/worktrees/Halbert/o01-agent-core -b fix/agent-core-rev06 main`. `git branch --show-current` before every commit (a concurrent session once switched a shared worktree's branch mid-task).
- Tests ONLY via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <paths>` (wrapper at repo root after SONNET-02; else copy from `.claude/worktrees/central-todo-batches/wt_pytest.py`). Plain pytest in a worktree tests MAIN's code silently.
- Baseline: 71 failures on `4a7bf71f` (`.handoff/audit-2026-09-01/pytest-main-failed-4a7bf71f.txt`). Run the full suite once at the end and diff the sorted FAILED list against the baseline — never eyeball a `tail`. Expected after this packet: ≈ 31–38 fewer failures, zero new.
- TDD; one finding = one focused commit. No `Co-Authored-By`/generation trailers. Never edit `MASTER-TODO.md`; results → `.handoff/RESULTS-OPUS-01-<date>.md`. No `prep*` MCP calls.
- Files you own: `halbert_core/halbert_core/agents/state_machine.py`, `agents/react_agent.py`, `agents/conversation_sqlite.py`, `context/assembler.py`, `findings/proposal_generator.py`, and the agent-core tests (`test_state_machine*.py`, `test_agent_memory.py`, `test_cognition_tick_once.py`, `test_thread_e2e.py`, `test_terminal_e2e.py`, `test_agent_integration.py`). Do NOT edit `capabilities.py`/`tests/conftest.py` (SONNET-03 adds the autouse registry reset), `integrations/**` or `audio/**` (OPUS-02), `federation/**`/`routes/agent.py` (OPUS-03), `streaming/**` (OPUS-04).

## Task 1 — `R06-F2` `response_modality` UnboundLocalError (P0, ~3 lines, clears 24–33 tests)
`state_machine.py:2743` `response_modality = "text"` sits inside `if self.prompts:` (`:2740`); the `else:` arm at `:2759-2762` calls `self._build_simple_response_prompt(response_modality=response_modality)` with the name unbound. Blame `2f595bc0` (2026-08-30). Production dashboard is safe only because `get_agent()` always wires an `AgentPromptBuilder` (`routes/agent.py:182`); Wyoming or any constructor without one hits it every turn. Fix: hoist `response_modality = "text"` and the `modality_ctx` resolution above the `if`. Verified on a scratch copy by the triage: `test_cognition_tick_once.py` 21/21, `test_agent_memory.py` 44/44, `test_state_machine.py` 37/37 with this hoist. Note: `test_cognition_tick_once` is NOT order-sensitive (a memory note and the singular-entity plan say it is — both wrong).

## Task 2 — `R06-F1` previous question leaks into the next PLANNING prompt (P0, ~1 line + test)
`:1519` `query = getattr(self, "_defanged_query", None) or self.ctx.user_query` is read by `_build_messages` (PLANNING via `:1702`); the reset `self._defanged_query = None` is at `:2701` (top of `_handle_responding`, blame `3d4b5a1b`) and the set at `:2724` (blame `0a2c3dfd`). So turn N+1 plans against turn N's question whenever the modality engine is importable — it is in this venv, and `test_thread_e2e.py` reproduces it with `-vv` (turn-2 planning's last user message ends with turn 1's "Set up a samba share…"). Fix: reset at the top of `process()` under the turn lock (next to `self.cancelled.pop`), or move the defanged query onto `StateContext` per turn. `test_thread_e2e.py` (2 tests) must go green; add an explicit regression test that turn 2's planning messages contain only turn 2's query.

## Task 3 — Test doubles and expectation drift (P1, ~10 lines)
- `R04-F8`: `fake_execute(tool_name, args, session_id=None, confirmed=False)` in `test_terminal_e2e.py:142`, `test_state_machine_turn_lock.py:308`, `test_state_machine_turn_persistence.py:119` lacks the `speaker_role` kwarg that `state_machine.py:2364` now passes (`58adce12`). Add `speaker_role="admin"` (or `**kwargs`). Then confirm `terminal_spawn` appears in the e2e event list (`test_terminal_e2e.py:168`) — the terminal bridge e2e guard has been dark.
- `R06-X1`: `test_state_machine_meta_tools.py:356` and `:550-552` pin CRAG overrides `{model_override, tier_override}`; the code intentionally also passes `secure=self.ctx.secure_context` (`:1739`, `:2578`, commit `4db888a9`). Add `"secure": False` to both expected dicts (verified to clear exactly those 3 tests).
- `SE-11` (if OPUS-03 has not): `test_peer_tool_proxy.py:268,282,297,311` use `asyncio.get_event_loop().run_until_complete` in sync tests under `asyncio_mode=auto`; use `asyncio.run` or mark async.

## Task 4 — `R06-F3` SEARCHING ignores `retrieval_scope` and skill scope (P1)
`state_machine.py:2199` `tasks.append(("rag", self.rag.search(search_query, limit=5)))` passes no scope/role; `retrieval_scope` is consumed only at `:1642` (PLANNING assemble). Routing `:1841` sends every non-greeting, no-tool-call first loop through SEARCHING, so the GPU deep-scan turn (`retrieval_scope="host"`) queries unscoped. Pass `scope=self.ctx.retrieval_scope` and the active skill's role/scope (or route SEARCHING through the assembler's `_search_retrieval`). Test: a turn with `retrieval_scope="host"` never issues an unscoped search. Related `R06-F8`: `context/assembler.py:599-604` catches a bare `TypeError` from a scope-aware adapter and silently retries unscoped — check the adapter signature with `inspect` once, or re-raise TypeErrors raised inside the adapter.

## Task 5 — `R06-F4` failed chmod excluded from rollback (P1)
`findings/proposal_generator.py:265-277` appends a rollback record only when `change.get("action") != "chmod"` (`:270`); `_apply_chmod` does `os.chmod` at `:561` then `write_audit` at `:563` with no try — an audit failure leaves the mode changed, un-rolled-back, while the proposal reports ROLLED_BACK. Re-stat after a failed chmod and append `{"kind":"chmod","path":…,"old_mode":…}` when the mode differs, or guard the audit write so it cannot fail the change after the side effect. Test both paths.

## Task 6 — `R06-F5` `merge_thread` orphans rows (P2)
`agents/conversation_sqlite.py:1820-1879` updates `messages`, `messages_fts`, `receipts_fts`, `conversations` only; `open_loops` (`thread_id TEXT NOT NULL`, schema `:437`) and `terminal_blocks` (`:392`) keep the merged thread's id. Add the two `UPDATE … SET thread_id=? WHERE thread_id=?` inside the transaction; store test.

## Task 7 — Remaining REV-06 items (P2/P3)
- `R06-O2`: `recall_memory` / `search_discoveries` tool calls are substituted with generic search and marked success — make the substitution explicit in the observation or implement the tools.
- `R06-F6`: Wyoming voice turn abandons `agent.process()` without `aclosing`, holding the turn lock until GC — the call site is `integrations/wyoming_agent.py` (OPUS-02 territory); the state-machine side (make `process()` release the lock on generator close) is yours. Coordinate.
- `R06-F7`: compression cascade unreachable on the agent path at TINY..LARGE; LLMLingua `FORCE_TOKENS` lacks `-` — decision item, note in results.
- `R06-O1`: `react_agent.py:300-313` attaches the LAST observation to every same-named tool call when the model calls the same tool twice in one response — dormant on the current path; fix if cheap.
- `R06-O3`: `spawn_subagent` / `await_subagent_completion` / `WAITING_FOR_EVENTS` have no callers — leave; note as built-unwired.

## Task 8 — Full-suite verification
Run the whole suite via the wrapper, sort the FAILED lines, `diff` against the baseline file. Report: failures removed, any new failure, and which of the remaining ones belong to SONNET-03 (registry pollution 6, auto-provision), SONNET-05 (cv2 13, licence 2, rot 4), OPUS-03 (peer_tool_proxy 4 if untouched).

## Results
`.handoff/RESULTS-OPUS-01-<date>.md`: commit shas per finding, before/after counts per file, the diff against the baseline, and any seam you deliberately left alone with the reason.
