# PKT-CSC-02 — Deterministic context reclaim + window-relative budgets

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **A**   Merge order: **3/9 in A**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**CSC-02** — Deterministic context reclaim + window-relative budgets.

## 2. User problem

Three independent context-management defects in Halbert's turn path, all measured and code-anchored in the OSS pass-2 deep-eval (verdict ACCEPT, deep-eval-group1 CSC-02; FINAL-CRITICAL-DISCOVERY-BACKLOG row 110 ACCEPT). (1) The tool-result cap is one flat 2000-char prefix cut (`agents/state_machine.py:53` `_TOOL_RESULT_CHARS = 2000`, applied once at arrival in `_format_tool_observation` at `:186-191`) with no re-pass over accumulated `ctx.observations` — the exit code and match count, the only pieces that tell the model whether a command succeeded, are cut first. (2) The context budget tier is picked by `detect_model_tier` (`intake/budget.py:132`) from a parameter-size regex (`_SIZE_RE`/`_MOE_RE`) on the model NAME, while `num_ctx_for_model` (`model/client.py:1143`) already discovers the real window per endpoint/model — the two are unconnected, and the name regex is a soft form of the banned "bake model names" pattern. (3) When the assembled prompt exceeds the resolved window, `model/client.py:735-746` detects the Ollama overflow, logs "Ollama will truncate the head of the prompt", and sends anyway — silently losing messages[0] (identity sheet plus thread receipt) from a steward whose entire value is continuity. Supporting defects: `ctx.images` is appended uncapped (`state_machine.py:3295-3296`, `:4330-4332`) and the whole list re-sent on every LLM call in the turn; `end_turn` lists every row and hands all of them to `build_receipt` (`agents/threads.py:1044-1049`, receipt at `:470`) — O(thread length) on the turn-finalisation path, and `threads.py:645-647` already names the cost ("up to 200 closes, each an unbounded list_messages plus a full build_receipt"); and the near-limit warning (`context/assembler.py:588-603` `_log_budget_drop`) fires every turn with no cross-turn signature memory and only after truncation. Under Halbert's one-seamless-conversation direction, subject threads run very long, so every one of these costs compounds.

## 3. What to build

Minimum viable slice per the deep-eval (build order: budget first, then summariser, then cursor; the section doc at `.handoff/oss-pass-2/section_conversation-session-compaction.md` Theme 2 is authoritative for each item's task text):

1. **Window-relative budget derivation (OC15-C8 + OC15-C17, build FIRST — everything below consumes this number).** Add a derivation in `intake/budget.py` that takes the resolved window from `num_ctx_for_model` (the value already computed per endpoint/model and cached in `_NUM_CTX_CACHE`, `model/client.py:1143-1200`) and returns the tier, the per-bucket `ContextBudget` allocations, a tool-result share (named constant, e.g. base-ratio/min-ratio/safety-margin with rationale comments, in the style of the origin's `BASE_CHUNK_RATIO=0.4`/`MIN_CHUNK_RATIO=0.15`/`SAFETY_MARGIN=1.2`), and a reserved summarisation overhead. Wire it where `get_context_budget` is consulted today. Do NOT port the origin's tier numbers — Halbert's TINY total is 400 tokens; port the ratio discipline. Keep the raw-weight double-check for dense non-ASCII text from OC15-C17. Delete the `_SIZE_RE`/`_MOE_RE` name-regex path in `detect_model_tier`; keep the explicit `tier:` override (`_coerce_tier`) — a models.yml `tier:` is an operator statement, not a name parse.

2. **Per-tool-type deterministic one-line summariser (HM02-C3 + HM02-M6).** New `halbert_core/halbert_core/context/tool_summaries.py` keyed on tool name (terminal, `execute_code`, search/grep, file-write, vision capture): terminal → "ran `…` -> exit 0, 42 lines", file-write → "wrote … (12 lines)", search → "… -> 7 matches". Every summariser wrapped in a never-raises guard that degrades to a byte count on a malformed historical call. In `_format_tool_observation` (`state_machine.py:183-191`), results over the cap go through the summariser instead of the prefix cut. Add a cheap re-trigger: when the accumulated `ctx.observations` total crosses a fraction of the window (the share from item 1 supplies the number), re-run the summariser over the OLDEST observation entries so the newest results stay verbatim. Invariant from the deep-eval: exit code, match count, line count survive reclaim; reclaim costs zero model tokens. Tier-2 rule applied to compaction — a template where a template suffices, never a model.

3. **Reactive compress-and-retry on actual overflow (HM01-C14).** In the model-call error branch of `state_machine.py`, when the error classifies as context-overflow (`agents/error_recovery.py:26,130` already names `CONTEXT_OVERFLOW`), run the deterministic reclaim from item 2 against the accumulated observations, compare the fully-assembled request size before/after, and retry at most N times and only while each attempt makes measurable progress; on no progress, exit the turn with a typed reason instead of sending the head-truncated prompt. This replaces the log-and-send at `model/client.py:735-746` from the turn side. (The `error_recovery.py:81-85` mapping of CONTEXT_OVERFLOW to `truncate_context` is on a manager the turn loop never calls — wire the real path, don't revive that one.)

4. **Absorption cursor for the receipt (HM02-M3).** Store an absorption cursor plus accumulated Commands/Files/entities sets on the receipt; `end_turn` (`threads.py:1044-1049`) folds only rows after the cursor instead of re-listing the whole thread; recover the cursor from the stored receipt on cold start (scan for the last summary marker; a later pass merges rather than replaces). D-1 §1.4 (supersession vs append-only for receipt columns) governs where the cursor lives — read it before adding a column. No migration: new column default NULL, unread old data stays on disk.

Target files for this packet per the dispatch index: `agents/state_machine.py` primary, with `context/tool_summaries.py` (new), `intake/budget.py`, `agents/threads.py` + `agents/receipt.py` (cursor), and read-only reference to `model/client.py` (`num_ctx_for_model`). Founder decision Q2 (deterministic compaction v0) gates only the LLM-summariser half, which is NOT in this packet — the packet ships fully deterministic without waiting.

## 4. What NOT to build

No LLM-based compaction/summariser anywhere (founder decision Q2 gates it; R-12's rotation writer consumes this packet's summariser and cursor but is built elsewhere). No model-name menus or model names on any user-facing surface — the regex deletion must not replace name-parsing with name-display. No changes to `context/watermark.py` — its docstring (`:20-31`) says `should_compact` has no production caller and the reader's original aim there was wrong; leave the documented no-op alone. No new test for `error_recovery.py`'s `truncate_context` strategy — it stays uncalled. No persisted image-eviction machinery (Halbert never persists images in history; `ctx.images` is rebuilt per `process()`), no touching of user-uploaded images. No receipt recency window inside `build_receipt` — `receipt.py:196-206` says a window there would silently drop earlier Commands/Files entries; the cursor is the mechanism, not a window. No prompt-cache economics work, no compaction eval/scorecard (R5 is a different workstream). No HM02-C7 side-question shape (founder decision 4, deferred). No `sanitize_title` (HM13-M6 — that rider belongs to CSC-04's workstream). No migrations or back-compat shims — new receipt column default NULL only, per the no-users rule.

## 5. Target files
- `halbert_core/halbert_core/agents/state_machine.py`

## 6. Dependencies

CH-A

## 7. Effort

**M** — M — four mechanisms across five files, but three are individually S-sized and the largest (budget derivation) is a rewiring of numbers that already exist, not new discovery. The summariser is S (C3) + S (M6): a keyed template module plus one call-site swap and an oldest-first re-pass. The budget derivation is M: `num_ctx_for_model` already resolves and caches the window per endpoint (`_NUM_CTX_CACHE`, `model/client.py:1183`); the work is deriving named ratios, replacing the regex path in `detect_model_tier`, and keeping every consumer of `get_context_budget` honest. The compress-and-retry is M: the classifier exists (`error_recovery.py:130`); the work is the progress check against assembled request size and the typed bail. The absorption cursor is M: `end_turn`'s fold path and cold-start recovery, with a parity pin test. Deep-eval justification, verbatim: "The flat prefix cut loses the exit code — the one piece of information that tells the model whether the command succeeded. The absorption cursor is a real O(n) cost on every `end_turn`. The reactive compress-and-retry replaces silently losing the head of the prompt." The minimum viable version (summariser + window-relative budgets + cursor) is the bulk of the value; the retry and image cap are explicitly the lower-priority half per the deep-eval.

## 8. UX rationale

Nothing new appears on any surface — this is trust-preservation machinery under the one seamless conversation. What the user notices is what stops happening: (1) The machine stops misreporting whether a command it staged actually worked — today the exit code is the first thing the 2000-char cut removes, so a long `npm test` output reads as success-shaped text with the "exit 1" trimmed off; after the summariser, the one-liner the model re-reads carries "-> exit 1, 42 lines" verbatim. (2) The machine stops silently forgetting its own identity and the thread receipt on long turns — the current behaviour logs a warning and sends the prompt with messages[0] truncated, so mid-conversation the steward quietly loses the continuity it exists to provide; the reclaim-and-retry keeps the head intact or says, in first person, that the turn could not be fit. (3) Long single conversations stop slowing down at turn-finalisation — under the no-conversation-list direction a subject thread runs very long, and the O(thread length) receipt rebuild is a stall the user feels as end-of-turn lag. (4) Budget warnings stop repeating every turn once a bucket crosses threshold (cross-turn dedupe). All voice stays first-person-computer; no model names, no new settings, no indicators, no emoji.

## 9. Acceptance criteria

All of the following pass as new tests under `halbert_core/tests/`, runnable via `arch -arm64 ./wt_pytest.py` from the worktree:

1. **Template pin tests (one per tool type)** in a new `test_tool_summaries.py`: each summariser template is pinned against the real `ToolResultBlock` shapes from `agents/blocks.py` — a stale template silently degrading to the byte-count fallback must FAIL a test (the verifier's named drift risk). Terminal result with exit code → one-liner contains the exit code and line count; file-write → contains path and line count; search → contains match count. A malformed historical call degrades to a byte count and never raises.

2. **Re-trigger test**: a simulated 10-tool turn keeps the newest results verbatim and shows the oldest entries as one-liners after the observation total crosses the derived fraction of the window.

3. **Budget derivation tests** in `test_intake_budget.py`: two endpoints serving the same model name with different discovered windows get different budgets; a window change re-derives the caps. The `tier:` override path (`_coerce_tier`) still wins when set.

4. **Overflow retry test**: a forced context-overflow classification in the turn's model-call error branch runs the reclaim, and the retry succeeds on the second attempt; a no-progress reclaim stops after one attempt and exits with the typed reason (no send of a head-truncated prompt).

5. **Receipt cursor parity pin** in `test_receipt.py`/`test_threads.py`: the receipt after N incremental folds equals the receipt built from scratch over the same rows; a cold start with a stale cursor merges rather than duplicates.

6. **Images cap test**: five captures in one turn result in at most N images on the sixth LLM call's outbound payload, with a placeholder line in the observation for evicted frames.

7. **Budget warning dedupe test**: a bucket crossing the 0.85 near-limit ratio warns once across two turns with the same (bucket, size) signature.

No regressions against the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures on main @ 2026-09-11): a failure is this packet's iff absent from that baseline. In particular test_num_ctx.py stays red-or-not exactly as before — this packet consumes `num_ctx_for_model`, it does not change it.

## 10. Verification (measured state, not model judgment)

From this worktree (`/Volumes/4TB-BAD/Halbert/.claude/worktrees/oss-pass2-step0`), run the new and touched test modules with the worktree wrapper (never bare pytest — the editable install pins halbert_core to the main tree):

```
arch -arm64 ./wt_pytest.py halbert_core/tests/test_tool_summaries.py halbert_core/tests/test_intake_budget.py halbert_core/tests/test_receipt.py halbert_core/tests/test_threads.py -x -q
```

Measured end-states to confirm: (a) exit code 0 from the run; (b) the template-pin tests fail when a summariser is deliberately drifted (run one with the template mutated to confirm the pin bites — a pin that cannot fail is not a pin); (c) the overflow retry test asserts the second-attempt send happened with messages[0] intact (assert on the captured payload's first message content, not on a log line); (d) the cursor parity test asserts byte-equality of the two receipts. Then a broader regression slice to prove no baseline drift:

```
arch -arm64 ./wt_pytest.py halbert_core/tests -k "budget or receipt or threads or num_ctx or conversation_window" -q
```

Compare failures against the known-red baseline list in the packet's repo traps (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures); any failure outside that list is this packet's. Never diagnose an `ImportError: … incompatible architecture (have 'arm64', need 'x86_64')` — that is the missing `arch -arm64` prefix, not a broken venv.

## 11. Exclusions

Named exclusions and where each goes:

1. **LLM-summariser compaction half** → gated on founder decision Q2 (deterministic v0 ratified as acceptable), consumed later by R-12's rotation writer Phase B/C — another unit, not M5b. This packet builds the deterministic blocks R-12 will call; if R-12's Phases B/C have not merged when this lands, the summariser and cursor must still land first (deep-eval Opportunities ordering).

2. **HM02-C4's persisted-vs-outbound image eviction machinery** → dropped per the verifier's shrink: Halbert never persists images in history (`ctx.images` rebuilt per `process()`), so only the keep-newest-N cap on `ctx.images` survives, and the deep-eval demoted even that to priority low. If the M slice runs hot, this is the first item to shed — shed it to the M5b tail, not to a silent skip.

3. **OC15-C18's per-file bootstrap override (user.md cap)** → the near-limit warning with cross-turn dedupe is in scope as the S-sized rider; the per-file override half is already satisfied by `intake/budget.py`'s per-bucket caps (verifier corrected absent→partial) — no new work, dropped as duplicate.

4. **HM02-C7 side-question shape** → founder decision 4, deferred to M5b (recommended default recorded: ephemeral hidden thread).

5. **HM13-M6 `sanitize_title`** → CSC-04's packet (state-store hardening), not this one — it shares the section doc's sanitizer extraction but owns different files.

6. **`error_recovery.py` `truncate_context` strategy rewiring** → dropped per RESHAPE-style minimum: the mapping lives on a manager the turn loop never calls; the packet wires the real path in `state_machine.py` and leaves the dead strategy unread, not revived.

7. **Prompt-cache economics and the R5 compaction eval/scorecard** → other workstreams entirely (models-providers, evaluation); this packet's invariant is zero model tokens spent on reclaim, so no eval harness is needed to ship it.

8. **`context/watermark.py` anything** → documented no-op with no production caller; the reader's original aim was corrected by the verifier. Left untouched — no packet.

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
