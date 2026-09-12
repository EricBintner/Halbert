# PKT-MEM-P3 — Forgotten-request tombstones (recall gate)

Tier: **opus**   Milestone: **M3**   Effort: **S**
Collision lane: **P**   Merge order: **2/2 in P**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MEM-P3** — Forgotten-request tombstones (recall gate).

## 2. User problem

When a person says "forget that" to Halbert, the words are erased from the change ledger, the audit log, and (if one exists) the vault — but the promotion evidence those words generated stays behind. `continuity/provenance.py::forget_request` (provenance.py:352) reaches exactly three planes (ledger via `StateStore.redact_request`, audit via `erase_audit_by_request`, vault via `VaultProjector().rebuild()`), and the conversation-message path (`agents/conversation_sqlite.py:2655 forget_request`, reached from `dashboard/routes/guest.py:643`) deletes messages — yet neither path touches the promotion tables. `continuity/promotion.py` already has the tombstone machinery: `PromotionStore.forget_request` (promotion.py:513) removes a request's rows from `promotion_signals`, `promotion_queries`, and `promotion_recall_days` together, and the module-level `forget_request_signals` (promotion.py:576) wraps it — but a full-tree grep confirms nothing in production calls either. So after a forget, the store still holds a durable, claim-keyed record that the forgotten words mattered — subject/predicate rows about the person who said them — and the recall-driven promotion scan (`rank_candidates`, promotion.py:223) plus the thread-recall injection path (`agents/threads.py:355`) have no forgotten-id exclusion, so the evidence can be ranked and re-injected into the one seamless conversation before any rebuild runs. Compounding it, the request-to-claim link (`PromotionStore._request_keys`, promotion.py:340) is in-process only, so signals a previous process recorded cannot be tombstoned by request at all — which `ERASURE_LIMITS` (provenance.py:332) is forced to half-confess ("signals a PREVIOUS process recorded are keyed by claim and outlive their run id"). Audit gap A01-G5 flagged this verbatim: `forget_request` does not reach the promotion tables. On Halbert's surface this is a first-person lie: the computer says "I've forgotten that" while its own memory still treats the forgotten request as evidence worth promoting.

## 3. What to build

Wire the existing promotion tombstone machinery into the forget choke point and close the read-side gap, all deterministically, no model anywhere:

1. Wire the tombstone into `provenance.forget_request` (the one plane-reporting choke point, called from `dashboard/routes/state.py:147`): after the ledger/audit/vault steps, call `continuity.promotion.forget_request_signals(request_id)` inside its own try/except (matching the existing per-plane pattern — never raises, failures append to `report["errors"]` and flip `complete` to False), and add a `promotion_signals` count key to the report dict so the response states what it actually erased. Do the same one-line wiring in the message-side path if the deep-eval's insertion point requires it (`agents/conversation_sqlite.py:2655 forget_request` is the other caller-facing entry; check at build time whether the guest path also needs the call — the report shape there differs).

2. Make the tombstone durable across processes: persist the request-to-claim link so a signal recorded by a previous run can be forgotten. The deep-eval's task is explicit — store `request_id` on `promotion_queries` rows (the `current_turn` ContextVar at `provenance.py:75` already carries it; `PromotionStore.record` at promotion.py:455 already accepts `request_id` and stashes it in `_request_keys`). Add an additive `request_id TEXT` column to `promotion_queries` (the `_ADDITIVE_COLUMNS` column-reconciliation pattern already used by the store hardening — no migration, old rows keep NULL and are simply not request-tombstoneable, which the honest report must keep saying), stamp it on the `INSERT OR IGNORE INTO promotion_queries` at promotion.py:433, and extend `PromotionStore.forget_request` to resolve keys from the persisted column when `_request_keys` has no in-process hit, then delete across all three tables as it already does.

3. Add the read-side exclusion at the recall gate: in `continuity/recall_gate.py`, add a small predicate — `is_forgotten(hit) -> bool` or a `forgotten: Callable[[str], bool]` parameter on `classify()` — so a hit whose request_id has been tombstoned never reaches STRONG/injection. The gate stays arithmetic and deterministic; the tombstone check is a set membership against the store's forgotten ids, called before margin classification. Wire it at the existing consumption points (`agents/thread_signals.py:20` imports `classify as _gate_classify`; `threads.py:355` is the injection site) so a just-forgotten thread is excluded from silent injection and from `rank_candidates` before the next reprojection.

4. Update `ERASURE_LIMITS` (provenance.py:332) so the text stops claiming the gap is permanent: it should say signals recorded under this request in any process are erased, and name only the genuinely unreached planes.

Tests: new `halbert_core/tests/continuity/test_forget_tombstones.py` — seed a promotion signal with a request_id (via `PromotionStore.record(..., request_id=...)` with a persisted conn on tmp_path), call `provenance.forget_request(request_id)`, then assert (a) the signal rows are gone from all three tables, (b) `rank_candidates` run immediately after forget does not surface the key, (c) a signal recorded in a *fresh* `PromotionStore` opened on the same db_path (simulating a previous process) is also tombstoned via the persisted column, (d) the report carries the promotion count and `complete` is True, (e) forget with a monkeypatched raising promotion store reports the error rather than raising.

## 4. What NOT to build

Do not port the OpenClaw line-surgery mechanism (`scrubMemoryContent`, marker-keyed edits) — the deep-eval says so verbatim; Halbert's redact-then-reproject model (`vault.py:379-400`) is cleaner and stays. Do not build the origin-class eligibility gate, the read-side ownership/visibility filter (`visible_to`), the injection-shape counter, or the harness skip guard — those are MEM-P1's scope (its column + predicate are the insertion point this unit's predicate composes with, which is why MEM-P1 lands first in lane P). Do not touch `conversation_sqlite.py` search methods, `ownership.py`, or the `_defang_continuity` choke point in `prompts/agent_prompts.py`. Do not rebuild `recall_gate.py`'s margin classification, threshold (`DEFAULT_MARGIN = 0.15`), or `MatchStrength` semantics — the tombstone is a pre-margin exclusion, not a score change. Do not add a model call anywhere in the forget or recall path — never a model where a template/predicate suffices. Do not build a general memory lifecycle/curator or decay machinery (MEM-P4/P5 scope, RESHAPE/DEFER). Do not add migrations or back-compat shims: additive column with NULL default, superseded rows left on disk unread. Do not touch `ERASURE_LIMITS` planes beyond the one sentence about promotion signals (timeline.db subject-erasure, Haloysius memory_v2 plaintext, backups — all stay named as unreached).

## 5. Target files
- `halbert_core/halbert_core/continuity/recall_gate.py`

## 6. Dependencies

MEM-P1

## 7. Effort

**S** — S. The mechanism already exists and is the small half of the work: `PromotionStore.forget_request` and `forget_request_signals` are written, correct, and delete across all three tables in one lock — this unit wires them into `provenance.forget_request` (one call site plus a report key, following the file's own per-plane try/except idiom), adds one additive column and one stamped INSERT parameter in `promotion.py`, extends the existing delete to resolve keys from that column, and adds a set-membership predicate ahead of the margin arithmetic in `recall_gate.py` (a ~104-line pure module with an existing test harness at `tests/test_recall_gate.py`). No new stores, no schema redesign, no founder decision, no concurrency model changes — the store already holds `self._lock`. The genuine sizing risks are bounded: keeping the never-raises report contract across a new plane, and the persisted-link test that must simulate a second process against tmp_path. Both are test-writing effort, not design effort. Not XS because three files plus a new test module are touched and the read-side predicate has two call sites to wire (`thread_signals.py`, `threads.py`); not M because no new mechanism is invented — the deep-eval itself scored the tombstones rider "Effort S on top of M2" and the wiring residue here is smaller than the mechanism that already landed.

## 8. UX rationale

Halbert speaks as the computer itself, in first person, grounded in measured data — and a forget response is a measured statement about the machine's own state. Today the response shown after "forget that" (`dashboard/routes/state.py:147` returns ledger_rows/audit_records/vault_rebuilt/complete) is silently incomplete: it claims erasure while the promotion tables still hold claim-keyed evidence that the forgotten words mattered, and that evidence can surface in the one seamless conversation as a promoted "remembered" fact — the worst possible failure, the machine appearing to recall what it just promised to forget. After this unit, the response's `complete: true` is true: the same report states the promotion rows removed, and `ERASURE_LIMITS` stops confessing a gap it no longer has. No new surface, no new copy beyond the report's existing honest-accounting idiom ("It does NOT reach: …"), no conversation list, no model names, no emoji. The recall-side effect is invisible when it works: a forgotten thread simply never wins the gate. The trust axis of the whole product — the computer's word about its own memory is worth believing — is what this protects.

## 9. Acceptance criteria

1. `provenance.forget_request(request_id)` erases the request's rows from `promotion_signals`, `promotion_queries`, and `promotion_recall_days`, and the returned report carries the promotion-erasure count with `complete` computed over it. 2. A promotion signal recorded under a request in a *different* `PromotionStore` instance on the same database (the previous-process case) is tombstoned by `forget_request` — the durable request link works, not just the in-process `_request_keys`. 3. `rank_candidates` executed after a forget, before any rebuild or reprojection, does not return the forgotten key. 4. The recall gate excludes a tombstoned hit from STRONG/silent injection while a non-forgotten hit with identical scores is still classified normally (margin semantics unchanged). 5. A failure in the promotion plane during forget is reported in `report["errors"]` with `complete: False` and never raises out of `forget_request`. 6. `ERASURE_LIMITS` no longer claims previous-process signals are out of reach. 7. The new test module passes and every test in `tests/continuity/test_promotion.py`, `tests/test_forget_request.py`, and `tests/test_recall_gate.py` that passed on the merge-base still passes.

## 10. Verification (measured state, not model judgment)

From the worktree root: `arch -arm64 ./wt_pytest.py halbert_core/tests/continuity/test_forget_tombstones.py -x -q` — all new tests pass (exit code 0). Then the regression ring: `arch -arm64 ./wt_pytest.py halbert_core/tests/continuity/test_promotion.py halbert_core/tests/continuity/test_promotion_wiring.py halbert_core/tests/test_forget_request.py halbert_core/tests/test_recall_gate.py -q` — exit code 0, or any failure diffed against the known-red main baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py; a failure is attributable to this unit iff absent from that baseline). Measured end-state asserted by the tests themselves: sqlite row counts on all three promotion tables drop to zero for the forgotten request_id (queried directly against the tmp_path DB), `rank_candidates` returns a list not containing the forgotten key, and the report dict carries the promotion count with `complete` True. Never bare pytest from the worktree (editable install pins halbert_core to the main tree), and never unprefixed python (universal2 launches x86_64 and dies in pydantic_core).

## 11. Exclusions

To MEM-P1 (lands first in lane P, merge order 1/2): the `origin_class` column and eligibility predicate, the read-side ownership/visibility filter (`visible_to` in `ownership.py`) and its application in `conversation_sqlite.py` search methods, the injection-shape counter, and the harness skip guard — MEM-P3's read-side predicate composes at MEM-P1's insertion point but must not build it. To OTHER-P1 (merged with the old plan-MEM-P3 backup scope — note the label collision: the deep-eval doc's "MEM-P3" was store durability, now OTHER-P1): PRAGMA integrity_check, `halbert backup`/`recover`, salvage, and the durable-write helper in `utils/atomic_write.py`/`run_receipts.py` consolidation — none of that is this unit. To MEM-P4 (RESHAPE): the promotion/recall product-boundary test and contamination backstop. To MEM-P5 (DEFER, gated on SK-6/founder memory-boundary decisions 1–5): memory lifecycle infrastructure, decay, curator. To M5b tail per the index: anything beyond the minimum viable slice above. Dropped per the deep-eval's own instruction: the OpenClaw `scrubMemoryContent` line-surgery port — explicitly rejected ("Do not port line surgery"). Timeline.db subject-level erasure, Haloysius memory_v2 plaintext erasure, and backup/snapshot erasure remain named in `ERASURE_LIMITS` as unreached — separate operations by subject, not by request, and out of scope here.

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
