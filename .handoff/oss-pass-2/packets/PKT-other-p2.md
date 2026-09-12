# PKT-OTHER-P2 — Correlated redacted logging

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **Q**   Merge order: **2/2 in Q**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**OTHER-P2** — Correlated redacted logging.

## 2. User problem

MERGED INTO LOG-01 (same 66-line obs/logging.py hub) — accounted there, one commit.

## 3. What to build

MERGED INTO LOG-01 (same 66-line obs/logging.py hub) — accounted there, one commit.

## 4. What NOT to build

See the deep-eval RESHAPE line; build the minimum viable slice, not the origin mechanism.

## 5. Target files
- `halbert_core/halbert_core/obs/logging.py`

## 6. Dependencies

text_hygiene

## 7. Effort

**M** — see the deep-eval effort justification.

## 8. UX rationale

Improves trust / recoverability / clarity on the one-seamless-conversation surface.

## 9. Acceptance criteria

The verification in field 10 passes against measured state.

## 10. Verification (measured state, not model judgment)

Run the unit test(s) named above; confirm the OS-observable end-state.

## 11. Exclusions

Everything in field 4; tails deferred to M5b per the index.

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
