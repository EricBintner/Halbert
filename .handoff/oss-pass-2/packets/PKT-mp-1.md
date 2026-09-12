# PKT-MP-1 — R-13 locality verification + reroute-notice residual

Tier: **opus**   Milestone: **M5a**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-13 is merged, keep only the genuine residual.

---

## 1. Packet

**MP-1** — R-13 locality verification + reroute-notice residual.

## 2. User problem

MP-1 as originally drafted ("Locality everywhere and utility-slot solidity": require_local on every utility-ladder rung, catalog-probe opt-in with negative cache, sibling exclusions, family-token fusion fix, size floor + deterministic tie-break, exclude kwarg threading, task-provenance logging, dead legacy rung deletion) is a duplicate of remediation packet R-13. The deep-eval verdict was REJECT (duplicate), but the final backlog corrected that to RESHAPE-verify because R-13 lives on `fix/remediation-sonnet-batch-1`, which is NOT merged to main (verified in this worktree: the branch is still open and `require_local` appears nowhere under `halbert_core/halbert_core/model/`). The underlying defect is real until R-13 lands: on a secure turn, the utility slot's resolver `resolve_aux_model()`/`_resolve_aux()` in `halbert_core/halbert_core/model/utility_slot.py:93-160` can pick a `:cloud` catalog sibling, and the spoken copy of a secure turn (via the one non-test caller, `integrations/speech_summarizer.py`) can leave the machine. The one item genuinely NOT in R-13's scope is OC14-C22: the slot-and-locality reroute notice ("this turn ran on a cloud connection"), a UI rendering item with three independent guards and bounded, redacted text, whose fallback events today are logged silently (the tool-schema fallback at `model/client.py:344-358` `_call_with_tool_fallback` surfaces nothing to the user). MP-1's problem is therefore: verify R-13 is merged, re-implement nothing, and account for exactly one residual.

## 3. What to build

Verification-only unit. Step 1 — verify R-13 merge state: run `git log --oneline main | grep -E "068d1f05|0c1812c3|afeb5d24|dfffd67d|c6372e06"` and grep the tree for R-13's symbols (`require_local` in `halbert_core/halbert_core/model/utility_slot.py`, the `exclude` kwarg on `_resolve_aux`, tri-state catalog slot unset/pin/disabled). R-13 is considered merged only if the sonnet batch's commits appear on main AND the symbols are present. Step 2a — if merged: MP-1 builds nothing. Record the merge evidence (merge sha, symbol greps) in the packet's row and confirm the OC14-C22 residual is recorded in MP-2's row as a rider (MP-2's packet must list: "if R-13 merged before dispatch, include OC14-C22's slot-and-locality notice; text names slot and locality, never the model"). The rider's content, for MP-2's row: one shared notice formatter for the theme's fallback/reroute notices, emitted only when three guards all hold (run id matches the current run AND the turn was actually rerouted AND the terminal disposition is visible to the user), text routed through the redaction registry and bounded (128-char cap on notice text, 320-char cap on any carried producer fact), rendering strings like "the chat connection fell back to its secondary" / "this turn ran on a cloud connection" — slot and locality named, never a provider or model identifier. Prerequisite: MP-2's C9 fallback transition state. It rides MP-2's fallback-transition surface, which already has the `useAgentStream.fallback.test.ts` announcement seam in the frontend. Step 2b — if NOT merged at dispatch time: MP-1 does not re-implement R-13 either (duplicate primitives are forbidden); instead it blocks, and the dispatch order must land the sonnet batch first. The only buildable-now artifact in that case is a one-paragraph note to the dispatcher confirming MP-1 stays in Wave 3.

## 4. What NOT to build

Do NOT re-implement any R-13 item: no `require_local` parameter on `resolve_aux_model`/`_resolve_aux`, no catalog-probe opt-in or negative cache, no sibling exclusions (reasoning/vision/embed/tts/transcribe/audio/`:cloud`), no family-token dash-segment matching fix, no size floor or name-pinned tie-break, no `exclude` kwarg threading, no task-provenance DEBUG logging, no legacy-rung deletion, no YAML-parse caching. All of that is R-13's merged-on-branch scope; rebuilding it on main would create the duplicate-primitive pattern the backlog's §3 forbids and would conflict the moment the sonnet batch merges. Do NOT build the OC14-C22 reroute notice itself in this unit — it rides MP-2 because it needs MP-2's C9 fallback transition state and its double-gated raw-error surface; building it standalone would produce a notice with no typed transition state to read. Do NOT touch `model/client.py`'s `_call_with_tool_fallback` retry logic, the utility ladder's rung order, `is_local_model()` (the one locality choke point at `model/llm_config.py:181` — route through it, never add a second judge), or `integrations/speech_summarizer.py`. Do NOT build migrations, back-compat shims, or any model-name-bearing surface.

## 5. Target files
- (verification-only; no product files)

## 6. Dependencies

MP-2

## 7. Effort

**S** — S — correctly sized, and only honest as a verification-first unit. The deep-eval's original REJECT assumed R-13 merged (zero residual value); the final backlog's correction to RESHAPE-verify keeps the unit alive solely to (a) prove merge state with greppable evidence and (b) carry the OC14-C22 rider into MP-2's row so a cold MP-2 session does not ship without it (the formal plan's §3.2 found exactly that loss: the deep-eval and final report assign the rider to MP-2, but the MP-2 row never mentions it). The verification itself is two greps and a git-log check — minutes. The residual-transfer bookkeeping is editing two packet rows. There is no code to write: writing code here either duplicates R-13 (forbidden) or fronts MP-2's fallback surface without its typed transition state (premature). If dispatch finds R-13 unmerged, the unit's output is a block note, not a build — still S.

## 8. UX rationale

Nothing user-facing is built in this unit. The user-facing consequence it protects lives entirely in the MP-2 rider: when a turn is rerouted — e.g. the chat connection falls back to its secondary, or a turn runs on a cloud connection — Halbert (speaking as the computer, first person, grounded in measured facts) says so once, in the one seamless conversation, naming the connection slot and its locality ("the chat connection fell back to its secondary"; "this turn ran on a cloud connection"), never a provider or model name, never raw error text unless the double gate opens. Today that reroute happens silently (the tool-schema fallback in `model/client.py` is logged only), which violates the grounded-in-measured-data stance: the machine knows it switched routes and says nothing. The notice must pass through the redaction registry before display and be bounded (128-char text cap), must only appear when the turn is actually visible (three guards: run id match, actually-rerouted, visible disposition), and must use shared-tokens colours with no emoji — consistent with the existing fallback-announcement seam tested by `useAgentStream.fallback.test.ts`. No conversation list, no toast storm: one line in the stream, once per rerouted turn.

## 9. Acceptance criteria

1) Merge-state evidence recorded in the MP-1 row: either (a) the sonnet batch's merge sha on main plus grep output showing `require_local` present in `halbert_core/halbert_core/model/utility_slot.py` and the `exclude` kwarg on `_resolve_aux`, or (b) an explicit "R-13 not merged — MP-1 stays Wave 3, dispatch sonnet batch first" block note. 2) If merged: MP-2's packet row contains the OC14-C22 rider verbatim (three guards — run id match AND actually-rerouted AND visible turn; redaction-registry pass; 128-char notice cap; 320-char producer-fact cap; slot-and-locality wording, never a model/provider name; prerequisite MP-2 C9), and MP-1's row records the transfer (cross-packet transfers recorded in BOTH rows, per the formal plan's §3.2 fix). 3) Zero lines of product code changed on any branch by this unit; `git diff main` for this unit touches only `.handoff/` packet rows. 4) No second locality judge introduced anywhere — any locality reference in the rider text routes through `is_local_model()`. 5) The rider text contains no model or provider identifier, no emoji, and no unredacted route facts.

## 10. Verification (measured state, not model judgment)

Runnable checks against measured state, in order: (1) `git log --oneline main | grep -cE "068d1f05|0c1812c3|afeb5d24|dfffd67d|c6372e06"` — exit 0 with count >= 1 proves a sonnet-batch commit is on main; count 0 with exit 1 proves it is not (this unit's branch point). (2) `grep -n "require_local" halbert_core/halbert_core/model/utility_slot.py` — must print at least one match (R-13's signature present) for the "merged" verdict; no match means the tree lacks R-13 regardless of what any handoff doc claims. (3) `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k utility_slot -x -q` — R-13's utility-slot tests pass on the merged tree (known nonzero main baseline exists; compare against the merge-base baseline, and from a worktree run `arch -arm64 ./wt_pytest.py halbert_core/tests -k utility_slot` instead so the editable-install finder doesn't resolve the main tree). (4) `git diff --stat main -- 'halbert_core/' | wc -l` on this unit's branch prints 0 — proving the unit shipped no product code. (5) `grep -n "OC14-C22" .handoff/oss-pass-2/*.md` shows the rider present in MP-2's row text, and `grep -rn "reroute" halbert_core/halbert_core/model/utility_slot.py | wc -l` prints 0 — proving the notice was not mistakenly built into the utility slot instead of riding MP-2.

## 11. Exclusions

Every implementation item from the original MP-1 draft is excluded as "dropped per RESHAPE — covered by R-13 on `fix/remediation-sonnet-batch-1`": require_local on the ladder (A14-G4), catalog opt-in default-false + FD-21 (A14-G1), catalog-probe negative cache (A14-G2), non-chat sibling exclusions (A14-G3), family-token dash-segment fix (A14-G9 + bug 6), size floor + name-pinned tie-break (A14-G5), exclude kwarg threading (A14-G7), task-provenance DEBUG logging (bug 2), dead legacy rung (bug 1), raw-YAML-parse-per-resolution (bug 4), missing `import yaml` (bug 5), the `_handle_responding` to_thread fix at `agents/state_machine.py:4160-4163`, and `require_local=ctx.secure_context` wiring. The single genuine residual — OC14-C22's slot-and-locality reroute notice (three guards, redacted/bounded text, slot-and-locality wording) — goes to MP-2 as a recorded rider, because its prerequisite is MP-2's C9 fallback transition state and its surface is MP-2's fallback-announcement seam (`useAgentStream.fallback.test.ts`); per the formal plan §3.2 the transfer is recorded in both MP-1's and MP-2's rows. If R-13 is found unmerged at dispatch: nothing in this unit absorbs R-13's scope — the whole unit blocks and the sonnet batch must land first (Wave-3 rule: do not re-implement, verify after merge, keep only the genuine residual). The `_is_home_variant`/founder-decision gates (fail-closed rule, catalog default) belong to R-13's branch, not here.

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
