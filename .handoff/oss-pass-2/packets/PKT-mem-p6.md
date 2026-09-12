# PKT-MEM-P6 — Compaction gate follows real numbers

Tier: **opus**   Milestone: **M3**   Effort: **S**
Collision lane: **M**   Merge order: **2/2 in M**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MEM-P6** — Compaction gate follows real numbers.

## 2. User problem

Every context-sizing decision the turn makes is driven by a local chars-per-token guess while the provider's real number is in hand and discarded. `agents/llm_client.py:278-281` (Ollama) and `:490-492` (Anthropic-shaped) already parse the provider's usage into `LLMResponse.usage = {"prompt_tokens": data.get("prompt_eval_count", 0)}` / `data.get("usage", {}).get("input_tokens", 0)` — and a tree-wide grep for `.usage` consumers returns nothing outside tests. The gate that decides whether the conversation history is sent verbatim or hard-trimmed is `context/assembler.py::build_conversation_window` at `:1368-1369`: `used = _history_tokens(history, counter)` then `if used < wm.watermark * max_tokens: return ...` — `used` is a `TokenCounter` estimate (`context/tokens.py:24` CHARS_PER_TOKEN=4), never the real number. The same guess feeds `num_ctx_for_model` via `estimate_prompt_tokens` at `agents/llm_client.py:137, :216` and `dashboard/routes/agent.py:1344`. For a steward whose entire value is continuity, a deflated local estimate silently loses the head of the prompt (messages[0] — the instructions and thread receipt) on the exact turns where the provider's larger real count would have told the gate to trim from the other end. The deep-eval verdict is ACCEPT: "the gate stops using a guess when the real number is available." Minimum viable version per the verdict: persist the last real `prompt_tokens` per thread and use `max(estimate, last_real)` in the gate; the replay harness and the persistence-caught-up invariant are follow-ups.

## 3. What to build

Three concrete changes, all in the two named target files plus the one store file they force:

1. Persist the real number per thread. Add `last_real_prompt_tokens INTEGER` (nullable, no default, no backfill) to the `conversations` DDL in `agents/conversation_sqlite.py::_REFERENCE_SCHEMA["conversations"]` (the table runs `:230-257`) and to the `_THREAD_UPDATABLE` allowlist (`:403`) so `update_thread` can stamp it. The declarative reconciler (`_reconcile_columns` / `_reference_columns` at `:357-387`) ADDs the column to existing DBs on open with the clause parsed straight out of the DDL — no version bump, no row backfill, NULL on every existing thread. This is the "additive column, default NULL, no migration" path the verdict names; it is the same machinery packet 08 already uses for `compact_streak` / `compact_cooldown_until` / `compact_last_at`.

2. Stamp it on every model turn. In `agents/llm_client.py` the usage dict is already populated at `:278-281` (Ollama `prompt_eval_count`) and `:490-492` (Anthropic `input_tokens`). The change is not in llm_client's parsing — it is giving the caller a way to read it. The single consumer path is `agents/state_machine.py`: `response = await self._model_call(self.llm.chat(...))` at `:3375` and `:4803`. After each successful response, when `response.usage.get("prompt_tokens")` is a positive int, write it through to the current thread row: `self.ctx.thread_manager.store.update_thread(thread_id, last_real_prompt_tokens=response.usage["prompt_tokens"])` (or the ThreadManager's own update wrapper — follow the existing `threads.py` write pattern; route through the same choke point every other thread-column write uses). Do NOT add a new `.usage` reader anywhere else — the state machine is the one turn path.

3. Follow the real number at the gate. In `context/assembler.py::build_conversation_window` (`:1312`), the caller `state_machine.py:1249` must hand the persisted number in. Add an optional `last_real_prompt_tokens: Optional[int] = None` parameter. At `:1368` compute `estimated = _history_tokens(history, counter)`; then `used = max(estimated, last_real_prompt_tokens)` when `last_real_prompt_tokens` is a positive int, else `used = estimated`. The `wm.watermark * max_tokens` comparison and `_trim_to_budget` call below are unchanged. Wire the caller at `state_machine.py:1249-1256` to read the thread row's `last_real_prompt_tokens` (available on the `turn`/thread object already being split at `:1206`) and pass it through. `max()` — not replacement — because the estimate can exceed the last real count (a turn that grew since the provider last spoke), and the verdict is explicit: "use max(estimate, last_real) when a real number exists."

Keep the change inside the two named files plus the forced `conversation_sqlite.py` column/allowlist and the `state_machine.py` stamp-and-pass. Do not touch `model/client.py` (`num_ctx_for_model`/`estimate_prompt_tokens` are MP-4's lane), do not touch `dashboard/routes/agent.py` (that is MP-4's shared hot file, not this unit's), and do not touch `context/watermark.py` (`should_compact`/`detect_topic_change` have no production caller — re-wiring them is out of scope per the watermark module's own docstring).

## 4. What NOT to build

Not the replay harness. The deep-eval names `halbert_core/evals/replay_gates.py` — a fake Ollama and fake Anthropic-shaped server with scripted `usage.prompt_tokens`, across live / persisted / reloaded thread shapes, inflated-must-not-trim / deflated-must-trim — as valuable but a follow-up ("The replay harness and the persistence-caught-up invariant are follow-ups"). It goes to the M5b eval-harness tail (R-15's neighbourhood), not this unit.

Not the persistence-caught-up invariant (HM11-C9 — "a rotation TXN may only drop rows from the projected window after the boundary row and its summary are committed"). The verdict assigns that to the A16 rotation design as a design clause, not a standalone mechanism. It is not built here; it is recorded for the rotation writer.

Not the `num_ctx_for_model` / context-cache-keyed-by-model-name / LM-Studio-loaded fixes — those are MP-4 (dependency), which this unit builds on but does not absorb. Not the model-name-regex budget-tier derivation or the per-tool summariser or the absorption cursor — those are CSC-02. Not the `estimate_prompt_tokens` chars-per-token improvements or image-cost calibration (`ab_image_cost_calibration`) — origin-eval material, M5b tail.

Not re-wiring `context/watermark.py::should_compact` or `detect_topic_change` into the production path — the watermark module's own docstring says no production caller reaches them and Plan A's topic segmentation (`agents/thread_signals.py`) is a different mechanism; resurrecting them would add a second disagreeing opinion. Not touching `LLMResponse.usage` parsing — both sites already parse the right field; nothing to fix there.

## 5. Target files
- `halbert_core/halbert_core/context/assembler.py`
- `halbert_core/halbert_core/agents/llm_client.py`

## 6. Dependencies

MP-4

## 7. Effort

**S** — S. One additive nullable column on an existing DDL plus its allowlist entry (the reconciler does the migration work — no version gate, no backfill), one write after the two `chat()` call sites in the state machine, one new optional parameter and a `max()` in `build_conversation_window`, and the caller passing the value through. The verdict itself sizes it: "The fix is small (persist one number, use max(estimate, real)). The value is high." No new dependencies, no new files except tests, no model involvement, fully deterministic. The heavy artifacts (replay harness, A16 invariant) are explicitly deferred out of this unit, which is what keeps it at S rather than M.

## 8. UX rationale

No new surface, no copy, no settings. The only user-visible effect is that the system stops silently losing the head of the conversation on long threads — the seam where continuity is the product. When the gate now trims from the correct end because the provider's real count was higher than the local guess, the thread receipt and instructions survive; the user simply does not experience the model "forgetting" what the conversation was about. This is invisible-by-correctness work. It conforms to the one-seamless-conversation directive (no conversation list, recall by relevance) by making the single continuous thread trustworthy, and to "the system speaks as the computer itself, grounded in measured data" by driving a sizing decision off a measured provider number instead of a heuristic. No model is named anywhere; no colour, no emoji, no UI element is added.

## 9. Acceptance criteria

A thread that has completed at least one model turn carries a non-NULL `last_real_prompt_tokens` on its `conversations` row, equal to the provider's reported `prompt_eval_count` (Ollama) / `input_tokens` (Anthropic-shaped) from the most recent turn. `build_conversation_window` with `last_real_prompt_tokens` set uses `max(_history_tokens(history, counter), last_real_prompt_tokens)` as `used` at `assembler.py:1368`; with it None or non-positive the behaviour is byte-identical to today. The watermark branch at `:1369` fires (trims) when the real number crosses `wm.watermark * max_tokens` even though the local estimate alone would not have, and does not trim when the real number is below it even if the estimate overshoots. Existing DBs open cleanly: the reconciler ADDs the column on first open with no error and leaves every pre-existing thread's value NULL. No other consumer of `LLMResponse.usage` is introduced outside the state machine turn path. `num_ctx_for_model`, `estimate_prompt_tokens`, `dashboard/routes/agent.py`, and `context/watermark.py` are unchanged.

## 10. Verification (measured state, not model judgment)

Runnable, measured, no model judgment:

1. Column lands and reconciles. `arch -arm64 .venv/bin/python -c "import sqlite3; from halbert_core.agents.conversation_sqlite import ConversationStore; s=ConversationStore(':memory:'); print([r[1] for r in s._conn.execute('PRAGMA table_info(conversations)')])"` lists `last_real_prompt_tokens`. Against a pre-existing DB lacking the column, opening the store then `PRAGMA table_info(conversations)` shows the column added and every existing row's value NULL. Exit code 0 both runs.

2. Stamp lands per turn. A new pytest (e.g. `halbert_core/tests/agents/test_compaction_gate_real_tokens.py`) drives the state machine's turn path with a stubbed `llm.chat` returning `LLMResponse(usage={"prompt_tokens": 12345})`, then asserts `store` row for that thread reads `12345`. Command: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/agents/test_compaction_gate_real_tokens.py` — all tests pass (exit 0).

3. Gate follows max(). Same test file: build a history whose `_history_tokens` estimate is below `wm.watermark * max_tokens` but pass `last_real_prompt_tokens` above it — assert `build_conversation_window` returns a trimmed window (shorter than the input history). Inverse: estimate above the watermark, real number below — assert it returns the verbatim window (`_from_first_user`). And with `last_real_prompt_tokens=None` assert output equals the pre-change output for a fixed history (regression pin). All green.

4. Existing suite not regressed. `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/context halbert_core/tests/agents -k "window or watermark or conversation or thread"` — no new failures against the pre-change baseline on the merge-base (main is not green; compare to a baseline run, per the repo rule).

## 11. Exclusions

Replay harness (`halbert_core/evals/replay_gates.py`, fake Ollama + fake Anthropic-shaped server, scripted usage, live/persisted/reloaded shapes, image-cost calibration `ab_image_cost_calibration`) — explicitly a follow-up per the verdict; routed to the M5b eval-harness tail alongside R-15's consolidation-eval work, not built in this unit. Persistence-caught-up invariant (HM11-C9, rotation TXN ordering) — a design clause for the A16 rotation design, recorded there, not a mechanism built here. `num_ctx_for_model` sizing, context cache keyed by model name, LM Studio "loaded" semantics — MP-4's scope (the declared dependency, which lands first); this unit only consumes the thread row, it does not re-derive the window. Per-tool one-line summariser, window-relative budget derivation from `num_ctx_for_model`, absorption cursor, reactive compress-and-retry, `ctx.images` cap — CSC-02's scope, untouched. Re-wiring `context/watermark.py::should_compact` / `detect_topic_change` into production — dropped as a second disagreeing trigger; the watermark module's own docstring records that no production caller reaches them and Plan A's `thread_signals.py` owns topic segmentation. Any change to `LLMResponse.usage` parsing at `llm_client.py:278-281`/`:490-492` — already correct, nothing to fix. Note on the registry label: the FINAL backlog row labels this packet "Provenance and redaction determinism" — that label is a phantom from an earlier grouping; the unit builds the deep-eval's compaction-gate content (HM19-C3) and touches no provenance or redaction code.

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
