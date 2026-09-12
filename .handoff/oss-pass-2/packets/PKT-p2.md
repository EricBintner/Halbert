# PKT-P2 — Approval bound to artefact (device,inode,sha256)

Tier: **opus**   Milestone: **M2**   Effort: **M**
Collision lane: **I**   Merge order: **2/3 in I**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**P2** — Approval bound to artefact (device,inode,sha256).

## 2. User problem

An approval in Halbert today is bound to nothing on disk. `ApprovalRequest` (halbert_core/halbert_core/approval/engine.py:31-64) carries `task`, `action`, `affected_resources` (a list of path strings), and a dry-run `simulation_result` — but no content identity for any of those paths. The consume path makes this concrete: `ProposalExecutor.execute_proposal` (findings/proposal_generator.py:291) runs `_apply_config_change` (proposal_generator.py:553-586), which calls `WriteConfig.execute(confirm=True)` against whatever bytes are at `change["path"]` at execution time. Between the owner reading the dry-run diff in the dashboard and clicking Approve, any writer — another Halbert subsystem, a watched-terminal command, a sibling session — can replace the target file, and the approval silently authorizes a change to content the owner never saw. The chmod branch already has this class of guard: `_apply_chmod` records `expected_current_mode` at proposal time and skips with a drift warning (proposal_generator.py:618-622). Config writes have no equivalent. This is the approve-then-replace race: the consent shown is not the consent applied. R-08's consent lattice binds records to `text_shown_sha256` (the wording displayed, consent/copy.py) — it says nothing about the artefact on disk. SURFACE-01a adds expiry enforcement but does not bind content. Without this unit, every approved config write is a TOCTOU window measured in minutes-to-days (approvals sit pending in `data/approval/requests/` until acted on), and the audit ledger records "approved" for a change whose actual pre-image is unknown.

## 3. What to build

Build an artefact-binding primitive inside `approval/engine.py` plus its consumption at the one consume site that today applies approved writes blind.

1. **Fingerprint record** — new dataclass `ArtefactFingerprint` in engine.py: for each path in `ApprovalRequest.affected_resources` that is a file artefact, capture at request time `(path, st_dev, st_ino, st_size, sha256)` via a helper `fingerprint_artefact(path) -> ArtefactFingerprint | None`. Hash by streaming `hashlib.sha256` over 64KiB reads; cap at a constant `MAX_FINGERPRINT_BYTES` (e.g. 64 MiB) — over the cap, record `sha256=None` with `truncated=True` and bind on (dev,ino,size,mtime_ns) instead, never read unbounded. `os.stat` with `follow_symlinks=False`; a symlink or non-regular file binds as `kind='non_regular'` with no hash (the owner approved a path, not a redirect). Missing file binds as `kind='absent'` — approving creation is valid. Failure to stat binds as `kind='unstatable'` and the request still queues but can never auto-apply (consume fails closed, see 3).

2. **Stored on the request** — extend `ApprovalRequest` with `artefact_bindings: List[ArtefactFingerprint]` (default empty). `request_approval()` (engine.py:134) computes bindings before `_save_request()` so the JSON persisted under `data/approval/requests/` carries the pre-image identity next to the diff the dashboard showed. Serialization rides the existing dataclass-to-dict save path in `_save_request` (engine.py:388); old request files without the key load with empty bindings (no migration — leave superseded data unread per repo rule; a request with empty bindings simply cannot pass verification in 3 and must be re-requested).

3. **Consume-before-apply verification** — new public method `ApprovalEngine.verify_artefacts(request_id) -> ArtefactVerdict` where `ArtefactVerdict` is `{ok: bool, drifted: [{path, expected, observed}], absent_created: [...], unstatable: [...]}`. It re-fingerprints every bound path and compares field-by-field: any change in (dev,ino) — the replace case — any sha256 mismatch, or any absent→present / present→absent transition is drift. `unstatable` or `truncated` bindings where (dev,ino,size,mtime_ns) disagree are drift. This is a pure function of disk state; deterministic; no model anywhere in the path.

4. **Wire the one blind consumer** — `ProposalExecutor.execute_proposal` calls `verify_artefacts(proposal.linked_request_id)` once before the change loop (proposal_generator.py:353). Any drift → the proposal is not executed; it is marked with a new status `"DRIFTED"` (alongside APPLIED/ROLLED_BACK), the ledger gets a `write_audit` row naming the drifted paths, and the finding stays open so the next detector sweep re-surfaces it against current disk state (the owner re-reviews what is actually there). Zero drift → execution proceeds exactly as today. Note: `_apply_chmod`'s existing `expected_current_mode` drift check (proposal_generator.py:618) stays as-is — it is the same idea at mode granularity; this unit adds content identity, it does not replace the mode check.

5. **Durability** — the binding write in (2) and the DRIFTED status write in (4) go through `durable_write` (utils/durable_write.py, dependency) for temp+flush+fsync+os.replace, matching how other state in this directory is being hardened; do not hand-roll a second atomic-write path.

6. **Expiry ordering (SURFACE-01a dependency)** — `verify_artefacts` must refuse (`ok=False`, verdict reason `expired`) when the request is EXPIRED under SURFACE-01a's enforcement, so a stale approval cannot be revived by re-fingerprinting. Check expiry first, fingerprint second — binding an expired approval is binding a stale approval.

## 4. What NOT to build

- Do NOT build the approval-presentation builder, sanitised field rendering, fence sizing, countdown/command-span/keyboard-chord UI — that is the RESHAPEd P2-presentation residual tracked in the deep-eval (OC01-M1) and belongs to a separate presentation packet, not this one.
- Do NOT touch `mode='auto'` deletion, fail-closed-on-no-surface, or any expiry mechanics — SURFACE-01a owns expiry enforcement (lane I, merge order 1/3; this unit is 2/3). This unit only *consults* expiry in verify_artefacts.
- Do NOT build the authorisation-as-a-field tool-registration descriptor, the uniform blocked-event taxonomy, consent/permission explain surfaces, zero-tool first-contact, or presence/camera filtering — all named in the deep-eval as separate residuals or deferred items.
- Do NOT build hash-bound one-shot consume-before-apply *token* semantics (single-use approval tokens) — that is OC09-C7, a separate residual; this unit binds content identity, not use-count.
- Do NOT build the base-hash CAS guard on policy writes (routes/agent.py stored-diff application) — that is BIND-01a (M2, lanes N/O), which shares the durable_write dependency but not this code path.
- Do NOT refactor `_apply_chmod`, WriteConfig's backup/rollback machinery, the approval dashboard/CLI prompts (`_prompt_cli`/`_prompt_dashboard`), or `routes/approvals.py` emission — the approve/reject route stays untouched; verification is invoked by the executor, not the route.
- Do NOT wire verify_artefacts into TT-01's shell executor or BIND-01's config CAS — they are listed in §3.15 as future consumers of the same fingerprint shape; each wires itself in its own packet. Only the proposal-executor consume site is wired here because it is the live race.
- No migrations, no back-compat readers for old request JSON beyond treating a missing `artefact_bindings` key as empty-and-never-verifies; no deletion of superseded data.

## 5. Target files
- `halbert_core/halbert_core/approval/engine.py`

## 6. Dependencies

durable_write, SURFACE-01a

## 7. Effort

**M** — M (not S) because the work spans three real seams in one lane: (1) a new fingerprint dataclass + streaming hasher with the four edge kinds (regular/truncated/non-regular/absent/unstatable) inside engine.py, (2) persistence-shape extension of ApprovalRequest with fail-closed semantics for pre-existing requests, and (3) the consume-side wiring into execute_proposal with a new DRIFTED proposal status, audit row, and finding-left-open behavior that the rollback/idempotency tests (test_proposal_generator.py TestHandleApprovalDecision) must be extended to cover. The race itself is one line of thinking but the fail-closed matrix (drift × expiry × absent transitions × unstatable) is where the effort lives — each cell needs a test against real tmpdir files. It is not L because the surface is narrow: one file of substance (engine.py, 419 lines), one consume call site, no frontend, no new routes, and the durable_write + expiry primitives arrive from dependencies rather than being built here.

## 8. UX rationale

The user-visible change is that an approval means what it appears to mean. Today the dashboard shows a dry-run diff, the owner approves it, and Halbert applies *something* to that path — with this unit, what is applied is provably the same bytes the owner read. The only new surface moment is the drift case: instead of silently applying against replaced content, execution stops, the proposal shows a deterministic DRIFTED state naming the paths that changed underneath the approval, and the finding re-surfaces so the owner reviews the file as it actually is now. That message is first-person computer voice and data-grounded per the standing directive — e.g. "I did not apply this: /etc/ssh/sshd_config changed after you approved the diff (content hash no longer matches); here is the current state" — staged for review, never auto-retried, never executed past the drift. No new colours, no emoji, no model involvement: the verdict is a sha256 comparison, and the approve-then-replace window — currently as long as a request can sit pending — closes to zero. This is the consent version of the repo's existing chmod drift guard, extended from mode bits to content, and it is what makes "commands staged from the UI are staged, never executed" meaningful for approved writes: staging is only honest if what executes is what was staged.

## 9. Acceptance criteria

1. `ApprovalRequest` persists `artefact_bindings` and a request created against a real file round-trips its fingerprint through `data/approval/requests/*.json` (dev, ino, size, sha256 present for regular files).
2. `ApprovalEngine.verify_artefacts` returns `ok=True` when disk state is byte-identical to request time, and `ok=False` with the drifted path named when any of: content changed (same inode, different hash), file replaced (different dev/ino), file deleted, or absent file created.
3. `execute_proposal` on a drifted proposal does not call WriteConfig for the drifted path, marks the proposal DRIFTED, writes an audit row, and leaves the finding open (assert via the existing pstore/fstore fixtures).
4. An expired request (SURFACE-01a semantics) fails verification regardless of disk state.
5. Byte-identical proposals execute exactly as before — the existing TestHandleApprovalDecision suite (approve_chmod_applies_and_resolves_finding, multi_change_applies_all, approve_config_change_uses_write_config, execution_failure_rolls_back, chmod_drift_skipped_with_warning) still passes unmodified.
6. Files larger than MAX_FINGERPRINT_BYTES bind on (dev,ino,size,mtime_ns) and verify correctly without the hasher reading the whole file (assert read volume via a counter/patch in test).
7. Symlinks and non-regular files bind as non_regular and their replacement with a regular file (or vice versa) is drift.

## 10. Verification (measured state, not model judgment)

Runnable: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_proposal_generator.py halbert_core/tests/test_approval_artefact_binding.py -x -q` (from a worktree: `arch -arm64 ./wt_pytest.py ...`). test_approval_artefact_binding.py is new in this unit and must contain, at minimum: test_fingerprint_round_trip_through_request_json, test_verify_ok_when_bytes_unchanged, test_verify_drifts_on_content_change_same_inode (write in place), test_verify_drifts_on_replace_new_inode (os.replace a new file over the path), test_verify_drifts_on_delete_and_on_absent_created, test_expired_request_never_verifies (monkeypatch expiry per SURFACE-01a's landed mechanism), test_truncated_binding_uses_stat_tuple, test_symlink_replacement_is_drift. Measured end-state beyond pytest: after the drift test runs, `ls data/approval/requests/` shows the request JSON containing an `artefact_bindings` key with a 64-hex sha256 (grep it), and the proposal store row for the drifted proposal reads status `DRIFTED` (grep the proposals JSONL/SQLite row) — both OS-observable, both asserted in the test teardown. Also confirm exit code 0 for the pre-existing test_proposal_generator.py suite and that no failure appears that is absent from the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py).

## 11. Exclusions

To other units: expiry enforcement mechanics and EXPIRED-reader hardening → SURFACE-01a (M4-packet but dispatches first, lane I order 1/3 — this unit only consults it). Base-hash CAS guard on stored-diff policy writes (routes/agent.py:2172-2203) → BIND-01a (M2, lanes N/O). Shell-executor artefact binding (device/inode on staged commands) → TT-01 (M2, lane H), which consumes this unit's fingerprint shape. Approval-presentation builder with sanitised fields/fences (OC01-M1) → separate presentation residual from the P2 RESHAPE in the deep-eval. Hash-bound one-shot consume tokens (OC09-C7), authorisation-as-a-field registration descriptor (OC17-M1/C1), blocked-event taxonomy (OC14-C9/M4/C5) → the three kept residuals of the deep-eval's RESHAPEd P2, each its own later packet. To M5b tail: approval UI countdown, command-span highlighting, stale-resolution classing, keyboard chords; consent/permission explain surfaces; zero-tool first-contact turn; presence/camera session-visibility filtering. Dropped per RESHAPE: everything in the original 30-item P2 already covered by merged R-08 (ask axis, grant-scope persistence, consent narrowing to leases, lease expiry, widening-bar principals — A11-G1/G2/G3/G7/G9) and R-02 (admission-graph items A12-G1/G2/G3/G6); the broad lease registry (P3 RESHAPE keeps only the halt).

---

## OSS reference

openclaw packages/gateway-protocol/src/schema/exec-approvals.ts + system-run-approval-binding.ts — NOT open-claude-code.

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
