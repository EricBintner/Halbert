# PKT-MEM-P1 — Read-side memory trust (origin_class)

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **P**   Merge order: **1/2 in P**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MEM-P1** — Read-side memory trust (origin_class).

## 2. User problem

Memory rows are trusted or distrusted only by *who wrote them* at write time (continuity/ownership.py::route_write, Owner.HALBERT/GUEST/DROP) and by *how confidently they ranked* at read time (continuity/recall_gate.py::classify, the margin gate). Nothing classifies a row by *where its content came from* (owner speech, agent-generated, tool/sensor output, system text), and nothing re-checks the owner divide when a row is read back. Consequences, each verified in code: (1) Sensor/tool output lands in Halbert's own stores via the WORLD_KINDS writers (ownership.py:44-50) and reaches silent injection with only the recall_gate margin in front of it — no amount of recall frequency should turn third-party text into something the machine says in its own first-person voice, but today nothing stops it. (2) The guest-persona divide (founder ruling R2/R3, persona/guest.py) is enforced on write only; a single writer that forgot to classify — or a store added later — leaks guest rows into Halbert's psyche on read. conversation_sqlite.py's search paths carry no owner predicate ('owner' appears only in the schema and the write path). (3) promotion.py::forget_request (line 513) exists, but per audit A01-G5 nothing excludes a just-forgotten request from a recall or rank_candidates() scan that runs before the next reprojection, and provenance.py's ERASURE_LIMITS does not say so. (4) A recalled receipt carrying injection-shaped text ('ignore previous instructions', role-marker impersonation) is defanged at display, but nothing counts how often recalled material arrives pre-shaped as an attack — telemetry MEM-P4's doctor needs. Registry summary: origin_class column; untrusted rows stored but never silently injected. Verdict from the backlog: ACCEPT — 'Read-side memory trust and visibility — real gap, no overlap.'

## 3. What to build

Four mechanisms, all deterministic, no model anywhere, no migrations (additive columns with defaults only; old rows stay on disk unread).

1. origin_class column + eligibility predicate (the core). Add an `origin_class TEXT NOT NULL DEFAULT 'owner'` column via the existing `_THREAD_COLUMNS`/message-column ALTER TABLE pattern in agents/conversation_sqlite.py (messages + receipts) and to `promotion_signals`/`promotion_queries` in continuity/promotion.py (its CREATE TABLE IF NOT EXISTS block at :294-311 plus the additive-column helper those tables already use). Values: owner|agent|untrusted|system. Stamp at write time from the existing actor plumbing: `route_write`'s actor (ownership.py:81) maps owner speech→'owner', Halbert's own ticks/summaries→'agent', tool/sensor/world kinds (WORLD_KINDS, route_observation)→'untrusted', lifecycle/system rows→'system'; a writer with no classification writes 'untrusted' (fail closed, mirroring P3's write-side rule). Add `continuity/recall_gate.py::is_eligible_for_automatic_injection(hit_origin_class) -> bool` returning True only for owner|agent and False on None/unknown — the single choke-point predicate, composable with the existing margin `classify()` (origin class decides eligibility, margin decides confidence; they are separate axes). Call it at the two injection sites before `classify()` results are acted on: agents/threads.py:355-360 (the `strong is not None ... recalled.append(entry)` block) and tools/recall_memory.py's deterministic dispatch. Untrusted/system rows remain fully searchable — explicit recall returns them; they are never silently injected into a prompt.

2. Read-side visibility filter (ownership re-checked on read). Add `continuity/ownership.py::visible_to(owner_value, fronting) -> bool` encoding: a HALBERT-owned row is visible only when no guest fronts; a GUEST-owned row is visible only while that guest fronts; a NULL/unrecognised owner is visible to neither (P3 made unfalsifiable on read). Apply it inside conversation_sqlite.py's `search`, `search_receipts`, `search_snippets`, and `_fts_term_hits_map` before results leave the store — the same insertion point as the tombstone predicate (item 3); build them together as one row filter.

3. Forget tombstones on recall and promotion scans. Record `request_id` on `promotion_queries` rows (the `current_turn` ContextVar at continuity/provenance.py:59 already carries it). Extend `promotion.py::forget_request` to actually delete/tombstone across the promotion tables (fixing A01-G5) and update ERASURE_LIMITS text at provenance.py:316 to state the coverage. Add a forgotten-request-id predicate to the same read-side row filter from item 2 so a request forgotten moments ago surfaces in neither recall nor `rank_candidates()` before the next reprojection.

4. Injection-shape counter (telemetry, never a block). Next to `_defang_line_markers` (the existing defang in the display/recall path), add the deterministic regex set ('ignore previous instructions', role-marker impersonation shapes) that *counts* matches per recalled receipt via structured logging (obs/logging.py JsonFormatter), exposed as a counter MEM-P4's doctor audit can read. It does not replace or weaken the defang; the defang stays the boundary.

A08-G12 leg is VERIFY-ONLY: `_default_db_path()` (conversation_sqlite.py:123) already resolves per call through utils.paths.data_dir() and already refuses the production path under pytest when HALBERT_DATA_DIR is unset (:145-161). Confirm both behaviours with a test; do not rebuild. If verification shows a residual path that still computes at import, fold the fix in here.

## 4. What NOT to build

No model in any decision — eligibility, visibility, tombstones, and the counter are all deterministic predicates/arithmetic, consistent with the recall_gate's existing no-model contract. No migration or back-compat shim: columns are additive with defaults; pre-existing rows are not rewritten, re-read, or deleted (per the no-users directive — leave superseded data on disk, unread). No new origin scheme on the Haloysius side: memory_v2 rows reached through integrations/haloysius_memory_adapter.py keep the upstream PersonaMemory shape; origin class lives on Halbert's own rows (conversation_sqlite, promotion tables) only — the master plan's claim-keying rule forbids a third scheme, and Haloysius EN-1 provenance is a separate column set. No lifecycle machinery (decay, scoring, curation) — that is MEM-P2's RESHAPE scope. No changes to route_write's write-side classification logic itself — this packet reads the actor it already produces. No UI surface — the 'Queued for promotion' inspector is MEM-P4's deferred half; the only visible behaviour change is that previously-silent wrong-class injections stop happening, and weak matches keep landing on the existing weak-match question path. No blocking/redaction change — the defang and the R-05 redaction choke point are untouched; the counter only counts. No OpenClaw-style per-session opt-out toggle (dropped per section file: presupposes a conversation list, which contradicts the one-seamless-conversation directive).

## 5. Target files
- `halbert_core/halbert_core/integrations/haloysius_memory_adapter.py`
- `halbert_core/halbert_core/continuity/recall_gate.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M is right. The work is two ALTER TABLE column additions following patterns already in both files, one new predicate function in recall_gate.py (~15 lines, mirroring classify()'s shape), one new predicate in ownership.py (~10 lines) plus its application at four search methods in conversation_sqlite.py (a genuinely hot shared file — care and the file's own test suite required), the forget_request extension across three promotion tables plus request_id plumbing from the existing ContextVar, a small regex set plus a structured-log counter, and a verify-only pass on A08-G12 with one new test. Every mechanism is deterministic arithmetic or substring/regex work with the insertion points already identified (threads.py:355-360, tools/recall_memory.py, the four search methods, promotion.py:513). No founder decision gates any of it (the ownership divide is already founder-ruled R2/R3/D2; this enforces an existing boundary on the second side rather than creating policy). It is not S because conversation_sqlite.py is the workstream's named hot file and the read-side filter touches every search path through it; it is not L because nothing new is designed — each mechanism has a named origin reference and a named Halbert insertion point.

## 8. UX rationale

No new surface and nothing the founder operates. The user-visible effect is subtractive and in voice: when recall is confident but the winning row came from a sensor, a tool, or system text, Halbert no longer pastes it into its own context and speaks it in first person as if it were its own past — explicit recall still finds it on request ('the Samba one from July, or the NAS one from June?' stays exactly as the weak-match path behaves today). While a guest fronts, Halbert's later recollection simply does not contain the guest's evenings, and the guest's recollection does not contain Halbert's psyche — a boundary the founder already ruled on, now holding even if a future writer forgets to classify. A forgotten request stops resurfacing in 'you asked about...' recall immediately, not after the next reprojection. The injection-shape counter surfaces only in logs and, later, MEM-P4's doctor output — phrased in first person measured data when it does ('3 recalled receipts arrived injection-shaped this week'), never as an alarm surface. No colours, no emoji, no settings row.

## 9. Acceptance criteria

1. Origin class stamped: new conversation message/receipt rows and promotion rows carry origin_class in {owner, agent, untrusted, system}, derived from route_write's actor at write time; an unclassified writer produces 'untrusted'. 2. Eligibility predicate: `recall_gate.is_eligible_for_automatic_injection` returns True only for owner|agent and False for untrusted, system, None, and unrecognised values; both injection sites (agents/threads.py's recalled-append block, tools/recall_memory.py) consult it before acting on classify(). 3. Composed gate: seeding one owner row and one untrusted row with identical scores, only the owner row is injected; the untrusted row is still returned by explicit search. 4. Visibility: with a guest fronting, a HALBERT-owned row is not returned from search/search_receipts/search_snippets; with Halbert fronting, a GUEST-owned row is not returned; a NULL-owner row is returned to neither. 5. Tombstones: forget_request(request_id) reaches the promotion tables; immediately after a forget, neither recall nor rank_candidates() surfaces the forgotten request before any rebuild; ERASURE_LIMITS text states the coverage. 6. Counter: a recalled receipt matching the injection-shape regex set increments the structured-log counter and is still defanged exactly as before (no behavioural block). 7. A08-G12 verified: with HALBERT_DATA_DIR unset, constructing the store under pytest raises the refusal; with it set to a tmp dir, the store opens there — no import-time path computation remains. 8. No regressions in the existing recall_gate, ownership, promotion, and conversation store test files.

## 10. Verification (measured state, not model judgment)

Runnable, measured checks (from the worktree root, arch -arm64 prefix mandatory):

1. New unit tests, added as halbert_core/tests/test_recall_gate_eligibility.py and extensions to halbert_core/tests/test_ownership.py and the promotion tests: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_recall_gate_eligibility.py halbert_core/tests/test_ownership.py halbert_core/tests/test_recall_gate.py -x -q` — exit code 0. The composed-gate test (acceptance 3) seeds one owner and one untrusted row at identical scores and asserts injection selects only the owner row while explicit search returns both. The tombstone test (acceptance 5) calls forget_request then rank_candidates in the same session and asserts absence — fails today per A01-G5, passes after.

2. Existing suites that pin the touched hot files must stay green against their own baseline (main is not green — capture the merge-base baseline first and diff): `arch -arm64 ./wt_pytest.py halbert_core/tests/test_recall_gate.py halbert_core/tests/test_ownership.py halbert_core/tests/test_ownership_wiring.py halbert_core/tests/ -k "conversation_sqlite or promotion or recall" -q` — no new failures versus baseline.

3. A08-G12 measured check: `HALBERT_DATA_DIR= arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "default_db_path or production" -q` plus a direct probe `arch -arm64 .venv/bin/python -c "import os; os.environ.pop('HALBERT_DATA_DIR', None); os.environ['PYTEST_CURRENT_TEST']='probe'; from halbert_core.agents.conversation_sqlite import _default_db_path; _default_db_path()"` — must exit nonzero with the refusal message naming the production path.

4. Counter check: a scripted recall of a receipt containing 'ignore previous instructions' produces exactly one structured log record with the injection-shape counter incremented: run the probe under `arch -arm64 .venv/bin/python` with logging captured to a file and grep for the counter field — count goes 0→1, and the defanged output is byte-identical to before the change.

5. Column presence, measured not assumed: `arch -arm64 .venv/bin/python -c "import sqlite3,tempfile,os; os.environ['HALBERT_DATA_DIR']=tempfile.mkdtemp(); from halbert_core.agents.conversation_sqlite import ConversationStore; s=ConversationStore(); print([r[1] for r in s._conn().execute('PRAGMA table_info(messages)') if r[1]=='origin_class'])"` — prints ['origin_class'].

## 11. Exclusions

- The A08-G12 default-path fix and the OC20-C13 harness skip guard half: already merged on main (`_default_db_path()` at conversation_sqlite.py:123 resolves per call via utils.paths.data_dir(); the pytest refusal at :145-161). This packet carries a verify-only test leg; any residual import-time computation discovered folds back in here as a small fix. - The OC20-C13 other half (hashed per-session opt-out toggle): dropped per RESHAPE in the section file — it presupposes nameable conversations, contradicting the one-seamless-conversation directive; not assigned to any unit. - Lifecycle machinery (decay, recency, scoring consumers, the dead `provenance='recalled_content'` parameter, event journal, per-key caps): MEM-P2's RESHAPE scope, mostly R-14's merged territory — verify there, do not rebuild here. - The product-boundary test's untrusted-candidate leg: MEM-P2 (RESHAPED to three items) depends on this packet's origin_class column; sequence MEM-P1 first, MEM-P2 lands that leg xfail until this merges. - The doctor audit consuming the injection-shape counter and the 'Queued for promotion' inspector: MEM-P4 (doctor ACCEPT gated on P2/P3; inspector DEFERRED per deep-eval). This packet only emits the counter. - The shared 'what may reach the model' predicate pattern applied to file reads: MEM-P5's sensitive-file gate (deep-eval line 396-397 names the shared pattern; this packet builds the memory-recall application only). - Haloysius-side provenance (EN-1) on PersonaMemory rows: a separate upstream column set, explicitly not a third scheme to introduce; the adapter at integrations/haloysius_memory_adapter.py is untouched. - venv SQLite upgrade (3.39.4 WAL band): MEM-P3's doctor row + founder call, not this packet.

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
