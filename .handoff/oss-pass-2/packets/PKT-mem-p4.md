# PKT-MEM-P4 — Product-boundary test + contamination backstop (was plan MEM-P2)

Tier: **opus**   Milestone: **M3**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MEM-P4** — Product-boundary test + contamination backstop (was plan MEM-P2).

## 2. User problem

Memory promotion is the boundary where conversation content becomes durable machine memory, and today nothing pins the security property that boundary is supposed to guarantee. Three residual gaps survive R-14's merge (verified against the code at this commit): (1) No test asserts the actual harm case end to end — a raw secret stored in a conversation turn must not survive into promoted memory, and a clean candidate must still promote (a test that fails on over-suppression too). Promotion signals are fed by `tools/recall_memory.py:122` (`_record_promotion_signal` → `get_promotion_store().record_recall`) and `agents/threads.py:1212`, and nothing between a stored turn and a promoted row is asserted anywhere in `halbert_core/tests/`. (2) The recall-loop hygiene guard is dead code: `continuity/promotion.py:454-457` accepts `provenance: str = "agent_query"` and returns early on `provenance == "recalled_content"`, but no caller in the tree ever passes `"recalled_content"` — the only provenance-passing callers are `tools/executor.py:733,765`, whose `_provenance_of(tool_name)` (executor.py:66) returns only `"mcp"` or `"halbert"`. Content derived from recalled material can therefore re-enter the signal store unimpeded, and there is no content-shaped backstop catching a caller that forgot or mislabelled. (3) No check verifies that write-path stores never receive prompt-assembled text — envelope/transport metadata (system-reminder tags, assembled-prompt wrappers) could land in a stored row and nothing would notice. The deep-eval (group1, MEM-P2, verdict RESHAPE) ruled everything else in the original packet — the A01-G1..G14 mechanics — is R-14's merged territory: verify, don't rebuild. The backlog verdict line: "Promotion/recall boundaries — keep the boundary check, drop the curator."

## 3. What to build

Three items, and only three.

1. Product-boundary test — new file `halbert_core/tests/test_memory_product_boundary.py` (the deep-eval names it `test_redaction_product_boundary.py`; use the target filename the packet assigns). Two halves:
   (a) Secret-in-transcript: register a canary secret in the `SecretVariantRegistry` (`ingestion/redaction_registry.py`, placeholder `<secret>`), drive a turn whose stored content carries the raw canary through the promotion-signal path (`get_promotion_store().record_recall` as called from `tools/recall_memory.py:122` and `agents/threads.py:1212`), run the promotion/consolidation path, and assert the canary string appears in NO promoted/persisted row — neither in the `PromotionStore` SQLite tables nor in any interest/candidate row written by `Consolidator._write_candidate` (`continuity/consolidation.py:294`, which already scrubs via `redact_text(topic, prose=True)` and refuses on change at consolidation.py:305-307).
   (b) Four-candidate promotion: seed a clean candidate with signals clearing the merged R-14 gates (`MIN_SCORE`, `MIN_RECALL_COUNT`, `MIN_QUERY_DIVERSITY`, `MAX_AGE_DAYS` — asserted in `tests/test_promotion_gates.py`) alongside suppressed ones, and assert the clean candidate IS present in `rank_candidates` output with its marker — the test fails on over-suppression, not just under-suppression.

2. Contamination backstop in `halbert_core/halbert_core/continuity/promotion.py`:
   (a) Fix the dead `provenance` parameter: since no caller passes `"recalled_content"`, replace the string-equality guard with a deterministic content-shape detector — a disjunctive filter matching Halbert's own consolidation-marker shapes (the summary/branch-summary marker formats emitted by `continuity/branch_summary.py` and the consolidator's reason/evidence shapes), applied inside `PromotionStore.record_recall` (promotion.py:454) and at the read side in `rank_candidates` (promotion.py:223) so recall-derived text is refused as a signal regardless of what the caller remembered to pass. Keep it deterministic — no model, per standing rule "never a model where a template suffices".
   (b) Decide the parameter's fate explicitly: either wire the real callers to pass it meaningfully or remove the parameter and rely on the content-shape detector; do not leave a guard no caller can trip.

3. Envelope strip check — one test in the same new file asserting no stored row carries prompt-assembled tags: after driving turns through the write path, scan the conversation store and promotion store rows for envelope/transport markers (system-reminder tags and the assembled-prompt wrapper shapes) and assert zero hits. This is OC20-C9: a verification that no write-path store receives prompt-assembled text.

## 4. What NOT to build

All of the following is R-14's merged work — verify it is present, do not rebuild it: the ranker consumer / Consolidator `promotion_store` consumer (A01-G1 — `rank_candidates` currently has no production consumer, and wiring one is R-14's row), recency decay from `updated_at`/`last_recalled_at` (A01-G2, covered by `tests/test_promotion_decay.py`), the reload-collapse fix for `recall_count` (A01-G3), origin class on signals (A01-G4), forget reaching promotion tables (`forget_request`/`forget_request_signals`, promotion.py:513,576 — A01-G5), caps on per-key hash/day sets (A01-G6), the hard gates themselves (A01-G7, `_is_eligible` at promotion.py:188), the memory event journal (`_record_event`, promotion.py:270 — A01-G9), query hash normalisation (`normalize_query`, promotion.py:71 — A01-G11), the malformed-day-row load fix (A01-G12), the dangling-signal audit/liveness predicate (A01-G13), and avg_score zero-weight (A01-G14).
Also not this unit: the promotion inspector UI (the "Queued for promotion" table in `Memory.tsx` fed by `rank_candidates` output) — that was deep-eval MEM-P4's other half, DEFERRED per its RESHAPE ("defer the inspector until there's a reason to look at it beyond the founder's own curiosity"). The continuity doctor `audit()`/`repair()` from the same deep-eval packet is also not this unit — it is gated on MEM-P3's `integrity_check` helper and belongs to the doctor's own dispatch. No new store, no new column beyond what MEM-P1 lands, no migration.

## 5. Target files
- `halbert_core/tests/test_memory_product_boundary.py` [new file]
- `halbert_core/halbert_core/continuity/promotion.py`

## 6. Dependencies

MEM-P1

## 7. Effort

**S-M** — S-M. One new test file plus a contained change to one module. The test work is the bulk: the secret-in-transcript leg needs the `SecretVariantRegistry` canary, a driven turn, and a promotion run; the four-candidate leg needs signals seeded to clear the R-14 gates; the envelope check is a scan assertion. The production change is small and deterministic: a marker-shape matcher (a fixed set of consolidation-marker prefixes/patterns, substring/regex — no model) consulted at two existing choke points (`record_recall` and `rank_candidates`), plus resolving the dead parameter. Everything heavy — the gates, decay, journal, forget plumbing — already exists on main from R-14 and only needs verifying against, not building. No UI work, no schema migration, no new infrastructure. Opus tier because the boundary assertion is security-shaped: getting "fails on over-suppression too" right, and choosing marker shapes that catch Halbert's own consolidation output without false-positiving ordinary recalled text, is judgement work, not transcription.

## 8. UX rationale

No user-facing surface. This unit is a test file plus an internal filter in `continuity/promotion.py`; nothing ships to the dashboard, CLI output, or any engaged surface. The only observable behaviour change is fail-silent in the correct direction: a recall signal whose content matches Halbert's own consolidation-marker shapes is refused entry into the promotion store (and filtered from ranking), exactly as the dead `provenance="recalled_content"` guard always intended. No wording, no colour, no indicator. If logging is added for refused signals, it follows the existing pattern in the module (`logger.debug`, fail-soft, never eating a tool answer) and names no AI model.

## 9. Acceptance criteria

1. `halbert_core/tests/test_memory_product_boundary.py` exists with both halves: the secret-in-transcript leg proves a canary registered in the redaction registry never appears in any promoted/persisted row, and the four-candidate leg proves a clean gate-clearing candidate IS present in `rank_candidates` output with its marker (over-suppression fails the test).
2. The contamination backstop is live in `continuity/promotion.py`: `record_recall` refuses, and `rank_candidates` filters, signal content matching Halbert's consolidation-marker shapes — demonstrated by a test that feeds recalled-consolidation-shaped text in as a signal and asserts it does not count toward `recall_count`/`query_diversity` and does not appear in ranked output.
3. The dead `provenance` parameter is resolved — either wired so a real caller can trip it, or removed in favour of the content-shape detector; no unreachable guard remains.
4. The envelope strip check asserts zero stored rows (conversation store + promotion store) carrying prompt-assembled tags after driven turns.
5. R-14's merged mechanics are verified present, not rebuilt: the A01-G2/G4 decay tests (`tests/test_promotion_decay.py`) and the A01-G7/G11/G12/G13 gate tests (`tests/test_promotion_gates.py`) still pass unmodified.

## 10. Verification (measured state, not model judgment)

arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_memory_product_boundary.py halbert_core/tests/test_promotion_gates.py halbert_core/tests/test_promotion_decay.py -x -q
The new file must pass in full (both boundary halves, the contamination-filter legs, the envelope strip check), and the two R-14 suites must pass unmodified, proving nothing merged was rebuilt or regressed. Exit code 0 is the measured gate. Then a full-suite spot check that the promotion.py change did not break neighbours: arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "promotion or memory or consolidation" -q — compare failures against the known nonzero main baseline (get a baseline run on the merge-base first; main is not green) and require zero NEW failures attributable to this change. (Run from the main checkout; from a worktree use `arch -arm64 ./wt_pytest.py` with the same args.)

## 11. Exclusions

Dropped per RESHAPE (deep-eval group1 MEM-P2, verdict line "strip R-14 duplicates, keep product-boundary test + contamination backstop"; backlog line "keep the boundary check, drop the curator"):
- All A01 mechanics (G1 ranker consumer, G2 decay, G3 reload collapse, G4 origin class, G5 forget plumbing, G6 hash/day caps, G7 gates, G9 event journal, G11 query-hash normalisation, G12 malformed-day load, G13 dangling-signal audit, G14 avg_score weight) — R-14's merged territory; verify presence via the existing test suites, never rebuild.
- The Consolidator `promotion_store` consumer wiring (A01-G1) — R-14.
Deferred to other destinations:
- The promotion inspector UI (`Memory.tsx` "Queued for promotion" table with clamped score components, origin class, liveness flag) — DEFERRED per deep-eval MEM-P4's own RESHAPE ("defer the inspector until there's a reason to look at it beyond the founder's own curiosity"); not any M3 unit; revisit only if a consumer beyond founder curiosity appears (M5b tail at earliest).
- The continuity doctor `audit()`/`repair()` (typed findings: corrupt artifacts, liveness predicate, self-ingestion count, injection-shape count, FTS-degraded breadcrumbs, missing-embedding-backend finding; repair renames into `.repair/`) — deep-eval MEM-P4's accepted half, gated on MEM-P2 (this unit's clamped/detector pieces) and MEM-P3's `integrity_check` helper; it is its own dispatch unit, built after P1/P2/P3, not in parallel.
- The untrusted-candidate leg of the boundary test that needs MEM-P1's origin-class column — sequence MEM-P1 first (declared dependency); land that leg xfail until P1 merges, per the deep-eval's explicit opportunity note.

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
