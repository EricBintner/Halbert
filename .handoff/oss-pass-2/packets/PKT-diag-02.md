# PKT-DIAG-02 — Read-only SQLite opener + store integrity + FTS corruption classifier fix

Tier: **fable**   Milestone: **M0**   Effort: **M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**DIAG-02** — Read-only SQLite opener + store integrity + FTS corruption classifier fix.

## 2. User problem

Two confirmed defects live on the conversation store's diagnostics seam, and a missing primitive blocks four other packets. (1) A08-G1 / HM11-M1: `SqliteConversationStore._is_fts_write_corruption_error` (halbert_core/halbert_core/agents/conversation_sqlite.py:1186) returns True for ANY exception whose message merely contains the substring `malformed` (line 1206: `if "corrupt structure" in msg or "malformed" in msg: return True`). Its own docstring claims it "Mirrors Hermes" and catches only structural index corruption, but the bare-`malformed` arm is a fail-open: any `DatabaseError` carrying that word (a transient read of a torn page, a WAL edge, an unrelated shadow-table hiccup) routes through `_enter_fts_fail_open` (line 1224), which persists the `fts_degraded` breadcrumb IN THE SAME TRANSACTION and lets the canonical `append_message` write COMMIT into a store whose index it has just declared untrustworthy. That is a silent data-integrity gap, not a theoretical one — the deep-eval (group4 §DIAG-02) calls it "a data-loss bug," and the section file lists it as "the first A08 confirmed bug... identical to HM11-M1; fix once." R-04 (conversation store + state-ledger hardening, merged) rewrote the surrounding open path (`is_structural_corruption` at line 585, `quarantine_unreadable_db` at 614, `_last_init_error` at 886/1045) but did NOT close this specific line — the `malformed` arm survives verbatim. (2) There is no sanctioned read-only way to open a Halbert SQLite store. DIAG-01's readiness probes, DIAG-02's own store probes, T5's SQLite bloat check, and OTHER-P1's backup-snapshot inventory all need to inspect stores without risking a write, a WAL checkpoint, or a schema migration firing on open. Today every consumer either opens the store read-write (running `_ensure_schema`, taking the writer lock, checkpointing the WAL) or re-implements its own ad-hoc guard. The registry note for this unit pins the shape: `mode=ro` + `PRAGMA query_only=ON` + an `integrity_check` probe, built once in `halbert_core/halbert_core/utils/sqlite_safety.py` (a new module — it does not exist yet) and reused everywhere.

## 3. What to build

Two pieces, in dependency order. (A) Fix the FTS corruption classifier in place. In `conversation_sqlite.py`, narrow `_is_fts_write_corruption_error` so the message arm matches only `fts5: ... corrupt structure` (the SQLITE_CORRUPT_VTAB error-code arm and the `no such table: messages_fts` / `no column named ... messages_fts` OperationalError arm stay — they are the real signals). DELETE the bare `"malformed" in msg` clause at line 1206. A bare malformed image on the CANONICAL tables is not an index-write problem and must never enter the index fail-open; it is structural database corruption and belongs to the `is_structural_corruption` path (which already halts writes sticky at open, line 972-977). Update the docstring so it no longer claims a bare malformed image is structural — that sentence is the bug's own cover story. Keep the existing fail-open contract tests green: `test_failed_append_rolls_back_and_returns_none` pins that an `IntegrityError` still rolls back, and `_corrupt_fts_for_test` pins that a genuine `fts5: corrupt structure` still trips fail-open. (B) Create `halbert_core/halbert_core/utils/sqlite_safety.py` with three publics: `open_read_only(path) -> sqlite3.Connection` opening `file:{path}?mode=ro` with `uri=True`, then `PRAGMA query_only = ON`, raising a typed `StoreUnreadable` (not creating, not migrating, never taking the writer lock); `store_integrity(path) -> IntegrityReport` running `PRAGMA integrity_check` (bounded, first-N-rows) plus `PRAGMA journal_mode`, `PRAGMA page_count`, `PRAGMA freelist_count`, and the SQLite version, returning a plain dataclass a doctor check serializes to JSON; and `sqlite_wal_reset_vulnerable()` re-exported/aliased here so DIAG-01/T5 stop importing the private constant from the store module. This module is the single choke point the four consumers route through — per the repo invariant rule, build the opener here once, not four times.

## 4. What NOT to build

The divert/spool/replay path for a replaced or quarantined store handle (HM11-M5) is explicitly DEFERRED per the deep-eval verdict — the section file itself marks it "priority low... becomes real the day a restore-from-backup flow exists," and there is no restore flow and no users, so it is infrastructure for a consumer that does not exist. Do not build it here. Do not touch the divert/quarantine machinery beyond what R-04 already shipped (`quarantine_unreadable_db` at line 614 is merged and stays). Do not change the WAL journal mode or add a DELETE-mode fallback — `warn_if_wal_vulnerable` (line 74) records the founder-ratified FD-11 rationale for leaving the journal mode alone, and the upstream remediation ("ship a newer SQLite") is a packaging concern, not this packet. Do not re-implement `integrity_check` per consumer, do not add a second `_endpoint_is_local`-style delegate, and do not add any model call anywhere on this path — integrity classification is a deterministic pragma read, never an LLM judgment (repo rule: never a model where a template suffices). No UI surface: `/health` surfacing of `last_init_error` is DIAG-01's job, not this unit's.

## 5. Target files
- `halbert_core/halbert_core/utils/sqlite_safety.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M is right, and it is mostly part (B), not part (A). Part (A) is a two-line surgical fix (delete the `or "malformed" in msg` arm, correct the docstring) plus reading the existing fail-open and recovery tests to confirm the narrowed predicate still trips on genuine corruption — that alone is S. The M comes from part (B): a new module with a typed exception, a dataclass report, four pragmas with bounded integrity_check output, the read-only URI dance (`uri=True`, `mode=ro`, `query_only`) that has real failure modes to get right (a missing file, a zeroed file, a file mid-migration by a live writer, a path that is a directory), and the re-export seam so three downstream packets stop importing a private constant. The registry already pins this as M and names four consumers (DIAG-01, MEM-P3-backup, T5, OTHER-P1), which is why the opener must be built once here rather than discovered piecemeal in each. Effort is NOT L because the divert/spool/replay machinery — the only genuinely large item the original packet carried — is deferred per the verdict, and because R-04 already absorbed the store-open hardening, the init-error record, and the quarantine path, leaving this unit with a classifier fix and one new well-scoped module.

## 8. UX rationale

No user-facing surface ships in this unit — it is plumbing on the diagnostics seam, and that is correct. The operator-visible effect arrives through its consumers: once DIAG-01 wires `store_integrity()` into `halbert doctor --json` and `/api/diagnostics`, a degraded or structurally corrupt conversation store becomes a measured, first-person line the system can speak about itself ("my conversation store at <path> failed an integrity check; I have moved it aside and started a fresh one — nothing was deleted") rather than a silent thin-search or a boot that bricks. The classifier fix removes a worse invisible behavior today: a store that hits a stray `malformed` keeps accepting canonical writes while its index quietly stops syncing, so recall goes thin with no signal — the exact kind of measured-data gap Halbert's grounding contract forbids. When any of this does surface, it obeys the standing rules: the voice is the computer's own first person grounded in the pragma readings, never an assistant narrating; no AI model is named; the read-only opener and integrity report carry no colour or emoji because they emit JSON, not UI; and the quarantine-rename message already in the tree is the template, so new copy follows its shape. Commands remain staged, never executed — this unit changes no command path.

## 9. Acceptance criteria

(1) The narrowed classifier: feeding `_is_fts_write_corruption_error` an exception whose message contains `malformed` but NOT `corrupt structure` and NOT the SQLITE_CORRUPT_VTAB code returns False, while an `fts5: ... corrupt structure` message or a `SQLITE_CORRUPT_VTAB` code still returns True, and an `IntegrityError` still returns False (the atomicity contract holds). (2) `open_read_only` opens an existing store with `PRAGMA query_only` in effect — a subsequent `INSERT` attempt on that connection raises `sqlite3.OperationalError: attempt to write a readonly database` — and raises the typed `StoreUnreadable` on a missing path, a zeroed file, or a non-database file, without creating anything on disk. (3) `store_integrity` returns a populated report (integrity_check result string, journal_mode, page/freelist counts, sqlite version) for a healthy store and reports the corruption for a deliberately damaged one, all without opening the store read-write. (4) The four named consumers can import the opener from `utils/sqlite_safety.py` and no longer reach into `conversation_sqlite` internals. (5) No regression in the existing store suite.

## 10. Verification (measured state, not model judgment)

Run the store suite plus the new module's tests with the arch prefix (the venv is universal2 and dies x86_64 unprefixed): `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "sqlite_safety or fts or conversation_sqlite" -q`. From a worktree use `arch -arm64 ./wt_pytest.py` instead of bare pytest. Measured checks the run must prove: a new `test_classifier_bare_malformed_does_not_fail_open` asserting `_is_fts_write_corruption_error(sqlite3.DatabaseError("database disk image is malformed")) is False` and `_is_fts_write_corruption_error(sqlite3.DatabaseError("fts5: corrupt structure")) is True`; the pre-existing `test_failed_append_rolls_back_and_returns_none` still green (IntegrityError rolls back, no fail-open); the pre-existing fail-open pin driven by `_corrupt_fts_for_test` still green (genuine corruption still degrades and `rebuild_fts()` recovers); a new `test_open_read_only_refuses_writes` asserting an `INSERT` on the returned connection raises `OperationalError` with exit-by-exception (not a silent success); and `test_store_integrity_reports_freelist_and_version` asserting the dataclass fields are populated for a tmp_path store. Primary measured signal: pytest exit code 0 on that `-k` selection, with the baseline-failure caveat from CLAUDE.md (main carries a known nonzero baseline — get a baseline run on the merge-base first; only the tests in this selection need pass for this unit).

## 11. Exclusions

HM11-M5 (divert/spool/replay path for a replaced or quarantined store handle) — DEFERRED per the deep-eval RESHAPE note, routed to the M5b tail of the diagnostics milestone to land only when a restore-from-backup flow exists; it is infrastructure for a consumer that does not yet exist and must not be built speculatively. Surfacing `last_init_error` and the integrity report on `/health` and in `halbert doctor --json` — that wiring is DIAG-01's scope (DIAG-01 owns the doctor registry and the `/api/diagnostics` route); this unit only ships the probe DIAG-01 calls. The SQLite bloat check (freelist-threshold alerting as a doctor check) — T5's scope; this unit ships the `freelist_count` field T5 reads, not the threshold policy. The backup-snapshot inventory — OTHER-P1's scope; this unit ships the read-only opener OTHER-P1 reuses. The WAL-reset SQLite version-gate as a doctor check — listed under DIAG-02's consumers in the backlog (§3.11) but the *check* itself belongs to DIAG-01's registry; this unit only re-exports `sqlite_wal_reset_vulnerable()` so the private constant stops being imported across a module boundary. The SQLite upgrade itself (ship 3.51.3+) — a packaging/DIST-01 concern, not engineering here, per the FD-11 rationale recorded in `warn_if_wal_vulnerable`.

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
