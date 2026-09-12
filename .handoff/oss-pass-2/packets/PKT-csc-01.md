# PKT-CSC-01 — Turn-boundary trust + decode integrity

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **A,J**   Merge order: **2/9 in A; 1/3 in J**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**CSC-01** — Turn-boundary trust + decode integrity.

## 2. User problem

Turn boundaries are the trust seam of the one-seamless-conversation surface, and three measured defects sit exactly there. (1) Decode integrity: when a local model emits malformed tool-call arguments, `model/client.py:_normalise_tool_calls` (lines 458-465) logs one warning and silently substitutes `args = {}` — the tool then runs with no path, no command, no query, and neither the model nor the user is told the arguments were dropped. Quantized local models are precisely the population that emits trailing commas, unclosed braces, and control characters in JSON; the founder's posture is local-first, so this is the common case, not the edge. `agents/llm_client.py:258-267` does not decode at all — an OpenAI-compatible provider's JSON-string `arguments` reaches `ToolCall.function.arguments` typed `Dict[str, Any]` but holding a `str`, and a consumer expecting a dict gets a string. (2) Turn-boundary trust: the tool-observation string is built raw at `state_machine.py:183-191` (`_format_tool_observation`) with no in-band data-not-instruction marker — external-origin tool output (web fetches, file contents, terminal output) enters the prompt as bare text that a payload can steer. Internal executor results are deliberately NOT routed through `security/result_redaction.py:redact_result` (the parked 05-C question, documented at result_redaction.py:11-15), so a secret a tool prints lands in the observation string unredacted and is then persisted. Halbert carries the prompt-literal sanitizer THREE times with three different rule sets (`discovery/schema.py:sanitize_discovery_text`, `integrations/observation_text.py`, `prompts/agent_prompts.py:defang_system_text` used by state_machine.py:135-139) — exactly the drift the redaction registry exists to kill. No invisible-unicode, bidi-override, or homograph check exists anywhere in the prompt path, and titles are persisted unsanitised. (3) Crash recovery at the turn boundary: a process that dies mid-turn leaves its user row `in_progress` (`threads.py:409`); the heal is the boot sweep `conversation_sqlite.py:1722 mark_in_progress_interrupted`, which flips the persisted status to `interrupted` — the rekeyed rule is that the persisted status is the whole recovery: the turn heals to what the store says, and nothing re-submits the lost turn.

## 3. What to build

Build the deep-eval CSC-01 minimum viable slice plus the crash-heal guarantee, touching only the two target files and reusing existing cores.

1. Five-pass JSON repair ladder at the tool-call boundary, replacing the silent `{}` substitution. In `state_machine.py`, at the single point where `tool_call.function.arguments` is consumed (the PLANNING dispatch at state_machine.py:3425-3428 and the meta-tool path that shares it), run a deterministic repair before use: pass 1 strict parse; pass 2 strip trailing commas before `}`/`]`; pass 3 close unclosed braces/brackets by stack balance; pass 4 trim excess closing tokens; pass 5 escape raw control characters inside string literals. Every pass that fires records which repair ran; if all five fail, the turn does NOT silently run the tool — it records an observation stating the call's arguments could not be decoded (naming the tool, never the model) and routes to REFLECTING instead of EXECUTING. The same ladder normalizes a string-typed `arguments` (the llm_client.py:266 no-decode shape) into a dict before any consumer reads it. This is repair-then-fail-closed, never substitute-empty.

2. `<untrusted_tool_result>` wrapper in `_format_tool_observation` (state_machine.py:183-191). External-origin tool results (anything that crossed a process, network, or filesystem boundary — terminal output, file reads, web results) are wrapped in the delimiter block with delimiter neutralization applied to the payload first (any literal `<untrusted_tool_result>` or `</untrusted_tool_result>` substring in the content is defanged). There is NO "already wrapped" fast path — that check is attacker-forgeable, since the payload itself can contain the marker. Internal-only results stay unwrapped so the wrapper retains signal value. The wrapper cap derives from the existing `_TOOL_RESULT_CHARS` budget.

3. Route the observation string through `security/result_redaction.py:redact_result` at `_format_tool_observation` — this closes the parked 05-C question for the internal-executor path at the one choke point where results become prompt text (scrub deterministically BEFORE the model, per the standing invariant; the registry and choke point already exist from merged R-05).

4. Shared prompt-literal sanitizer extraction, consolidation not a fourth implementation: `_format_tool_observation` and the turn-boundary title writes in state_machine.py route through one sanitizer with one rule set (strip ANSI first, then escape C0/C1 controls, strip invisible-format code points — zero-width spaces, soft hyphens, bidi overrides, object-replacement — and lone surrogates; NFC normalize, never NFKC, matching observation_text.py:88-91's reasoning). Where consolidation would edit the other two implementations' files, do not touch them — expose the shared rule set from state_machine.py's import surface (import from `integrations/observation_text.py`, the strictest of the three) and apply it at the turn boundary only. Titles written via the thread meta-tool path (state_machine.py:3681/3796 `add_observation` title lines and the title persisted through `threads.py`) get the same invisible/bidi/surrogate pass before persistence.

5. Scoped threat-pattern check on RAW content (before any normalization) at the observation boundary: a small anchored library matching attack behaviour (chat-template special tokens, role-marker forgeries like a leading `system:` line inside tool output), never bossy English. A hit does not censor the content — it prefixes the observation with a first-person data-not-instruction note so the model reads the block as evidence, not orders.

6. Timeout-bounded reads for any file whose contents enter the prompt at the turn boundary in state_machine.py: wrap the read in a deadline; on expiry the observation records that the file could not be read in time (the repo lives on an external volume; a stalled mount must not wedge turn assembly).

7. Crash-heal guarantee, persisting the rekey rule "crashed turn heals to persisted status; no re-submit": keep `conversation_sqlite.py:mark_in_progress_interrupted` as the sole boot-time healer; in state_machine.py, ensure every terminal transition of a turn (complete, cancelled, error, interrupted) settles the persisted row's status in a `finally`-equivalent so no code path leaves a row `in_progress` across a process death except the genuinely-cut-off case the boot sweep owns. No re-queue, no re-dispatch, no auto-answer: the healed `interrupted` status IS the recovery, surfaced per existing status projection. Do not build the SIGTERM handler, `.clean_shutdown` marker, or first-person "I was cut off" line — those are CSC-03's.

## 4. What NOT to build

- No re-submit / re-queue / auto-retry of a crashed or interrupted turn, in any form. The persisted status after the boot sweep is final; the deep-eval registry note ("no re-submit") is a hard exclusion, and CSC-05 owns any turn-admission semantics.
- No SIGTERM/SIGINT handler, no `.clean_shutdown` marker, no crash-vs-clean startup sweep, no "I was cut off while …" first-person line — all of that is CSC-03's build, explicitly.
- Do NOT edit the other two sanitizer implementations (`discovery/schema.py:sanitize_discovery_text`, `prompts/agent_prompts.py:defang_system_text`) to unify them — the deep-eval says extract one shared sanitizer, but this packet's target-file boundary is state_machine.py + conversation_sqlite.py only; consolidation of the other two call sites goes to the text_hygiene unit (M0, lane L) which owns the cross-repo module.
- Do NOT modify `model/client.py:_normalise_tool_calls` or `agents/llm_client.py` — the repair ladder lives at the state_machine.py consumption point; the client-side decode sites are MP-5's lane (G/M).
- No schema migration, no backfill, no new columns — the messages.status vocabulary (`in_progress`/`interrupted`/`complete`/`cancelled`) already exists; additive-only per the no-migrations directive.
- No per-tool-type summariser, no window-relative budgets, no absorption cursor — CSC-02.
- No model in any path — every repair, sanitisation, and threat check is deterministic; no naming any model on any surface, including repair-failure observations.
- No new colours, no emoji, no UI surface changes — the status badge projection (`agents/events.py:494`) already exists.

## 5. Target files
- `halbert_core/halbert_core/agents/state_machine.py`
- `halbert_core/halbert_core/agents/conversation_sqlite.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M is the deep-eval's own rating and it holds under the rekey. The work is five mechanisms in two files: the repair ladder (~120 lines with per-pass instrumentation), the untrusted-result wrapper with neutralization (~40 lines at one choke point), the redact_result routing (a handful of lines at the same choke point — the registry and core already exist from merged R-05), the title/observation sanitisation (a rider on existing strictest implementation — import and apply, not re-author), the scoped threat-pattern check (~30 lines, anchored patterns on raw content), and the bounded-read wrapper (~20 lines). The crash-heal half is mostly verification: the boot sweep exists (conversation_sqlite.py:1722, tested at test_thread_store.py:547 and test_peer_conversation_store.py:174), so the state_machine.py work is auditing terminal transitions for status-settling gaps, not building a healer. What keeps it M rather than S: state_machine.py is the repo's hottest file (lane A, 9 packets, merge order 2/9 — SP-3 lands first), so every edit must re-anchor by grep and stay narrowly scoped to avoid colliding with CSC-02/CSC-03/CSC-05 edits queued behind it; and the fail-closed repair path needs care to route through REFLECTING without tripping the oscillation guard or the max-loops counter. What keeps it M rather than L: no new modules, no schema change, no cross-file consolidation, heavy reuse of merged primitives (redact_result, observation_text sanitizer, existing status vocabulary).

## 8. UX rationale

The user never sees any of this machinery — that is the point. On the one-seamless-conversation surface, the failures this packet kills are the ones that read as the computer being unreliable or being steered: a tool that "ran" but did nothing because its arguments were silently emptied (the model then confabulates why), tool output that quietly contained an API key and got persisted into the conversation record, a fetched page whose text the computer obeyed as if it were the user, and — after a crash — a conversation badge stuck on in_progress forever, or worse, a half-finished action silently re-attempted. After this lands: a malformed local-model tool call produces an honest in-conversation note that the call's details could not be read (first person, naming the tool, never the model); external content arrives visibly fenced as data; and a crashed turn simply shows its true persisted state — interrupted — with no phantom retry and no conversation-list ceremony. The computer's account of what happened matches what the store says happened, which is the foundation of the "speaks as the computer itself, grounded in measured data" voice. No new surfaces, no new colours, no emoji, no model names anywhere.

## 9. Acceptance criteria

1. A tool call whose arguments are malformed JSON in each of the five repair shapes (trailing comma, unclosed brace, excess closer, raw control char in a string, plus one clean-parse control) executes with the repaired arguments — verified by an instrumented fake tool recording the args it received — and each repair records which pass fired. 2. A tool call whose arguments fail all five passes does NOT execute the tool and does NOT substitute `{}`; the turn records an observation naming the tool and routes to REFLECTING, ending normally without tripping the oscillation guard. 3. A string-typed `arguments` payload (the llm_client no-decode shape) reaches the tool as a dict. 4. An external-origin tool result appears in the prompt-path observation wrapped in `<untrusted_tool_result>` with any payload-embedded delimiter defanged; wrapping is unconditional (no already-wrapped fast path — a payload pre-containing the marker is double-wrapped, not trusted). 5. An observation built from a tool result containing a registry-recognised secret carries the redacted form, not the secret. 6. Observation text and persisted thread titles contain no bidi-override, zero-width, object-replacement code points, or lone surrogates after sanitisation. 7. A simulated mid-turn kill (row left `in_progress`) is healed by `mark_in_progress_interrupted` to `interrupted` on next open, and no code path re-dispatches the turn — the store's row count and turn dispatch count are unchanged by the heal. 8. No file outside the two target files is modified.

## 10. Verification (measured state, not model judgment)

From a git worktree: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_state_machine_turn_persistence.py halbert_core/tests/test_conversation_sqlite.py halbert_core/tests/test_tool_calling_bridge.py halbert_core/tests/test_result_redaction.py -x -q` — exit code 0, with the packet's new tests added to test_state_machine_turn_persistence.py (repair-ladder pass/fail-closed cases, wrapper + neutralization, redaction-in-observation, title sanitisation) and test_conversation_sqlite.py (heal-to-interrupted-no-resubmit: insert `in_progress` row, close handle, reopen, call `mark_in_progress_interrupted`, assert status == 'interrupted' and assert no new rows / no dispatch side effects). The existing `test_cancelled_and_interrupted_statuses` (test_state_machine_turn_persistence.py:149) and the boot-sweep pins (test_thread_store.py:547, test_peer_conversation_store.py:174) must stay green. Measured OS-observable checks: (a) a pytest case asserting a payload containing the literal string `</untrusted_tool_result>` produces output where that exact substring count is 1 (the real wrapper's own closer), countable via str.count — no judgment involved; (b) a case asserting `redact_result`'s `<secret>` marker appears and the raw secret string does not (via `not in`) in the formatted observation; (c) `git diff --stat main...HEAD` shows changes only in `halbert_core/halbert_core/agents/state_machine.py`, `halbert_core/halbert_core/agents/conversation_sqlite.py`, and the two test files. Compare against the known-red 2026-09-11 baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures): a failure is this packet's iff absent from that baseline.

## 11. Exclusions

Field 4's exclusions each have a named destination. SIGTERM/SIGINT handler, `.clean_shutdown` marker, crash-vs-clean boot detection, the shutdown flush-to-spool, the loop-exception handler, and the first-person "I was cut off" surfacing line → CSC-03 (M3, lane AFJ, owns "conversation survives the process"; the deep-eval CSC-03 section names exactly these items). Consolidation of the other two sanitizer implementations into one shared module (`security/prompt_sanitizer.py` / text_hygiene) → the M0 text_hygiene unit (lane L, `prompts/agent_prompts.py`), which the deep-eval's Opportunities section names as the cross-cutting owner also serving P3's chat-template stripping and P4's OSC-133 marker stripping. Client-side decode repairs in `model/client.py:_normalise_tool_calls` and `agents/llm_client.py` → MP-5 (M1, lane AG, "local-model tool-call repair", depends on SP-3). The fd-pinned shared `utils/bounded_read.py` helper that P5 also wants → P5 owns the shared-helper extraction per the deep-eval Opportunities cross-reference; this packet inlines its own deadline-bounded read at the turn boundary rather than authoring the shared util. Per-tool summariser, window-relative budgets, absorption cursor, image cap → CSC-02. Turn admission/identity and any semantics of what an interrupted turn means for the NEXT turn → CSC-05. Anything beyond minimum-viable from the deep-eval's own rider list (broader homograph confusables tables, locale-specific bidi rules) → dropped per the deep-eval's minimum-viable-version line, not deferred.

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
