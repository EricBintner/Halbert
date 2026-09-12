# Deep Critical Evaluation — Group 1: Memory, Conversation-Session-Compaction, Permissions-Consent-Security

Written 2026-09-11. This is a judgment exercise, not a ranking. Every packet in the three workstreams is evaluated against: (a) what R-01..R-15 already fixed, (b) the standing rules in AGENTS.md, (c) whether the origin pattern fits Halbert's architecture, (d) whether a user or operator would notice its absence.

## Remediation overlap key

Already merged to main: R-01 (talk-door ordering, interrupt algebra), R-02 (claims, admission graph, guest routes, voice provenance), R-04 (conversation store + state ledger hardening), R-05 (redaction registry, Tier-2 choke point), R-06 (echo guard, display projection, turn digest), R-07 (execute_code hardening), R-08 (permission lattice: ask axis, approvals, leases, halt), R-09 (MCP client boundary), R-10 (speech egress), R-11 (skills plane), R-12 (session tree: deterministic compaction v0), R-14 (memory promotion follow-through). Pending-merge: R-03 (scheduler durability), R-13 (utility slot), R-15 (eval harness and verdict contract).

The discovery section files were written during the oss-pass-2 discovery pass, which ran before or during the remediation pass. Where a section file lists audit gaps (A01-Gn, A07-Gn, A08-Gn, A11-Gn, A12-Gn) as prerequisites for a packet, those gaps may already be fixed by the corresponding R-packet. Each verdict below accounts for this.

---

## Memory Workstream (MEM-P1 through MEM-P6)

### Packet: MEM-P1 — Read-side trust axis

**What it actually proposes:** Add an `origin_class` column (owner|agent|untrusted|system) to conversation and promotion rows, stamped at write time from the existing `route_write`/actor plumbing. Add a single eligibility predicate every recall/search hit must pass before reaching a prompt (untrusted/system content stays reachable by explicit search but is never silently injected). Add a read-side visibility filter enforcing the guest-vs-HALBERT ownership divide on search results. Add forget tombstones to promotion tables. Fix the conversation store default path to honour `HALBERT_DATA_DIR` (A08-G12 — pytest can open production conversations.db today). Add an injection-shape counter on recalled receipts.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes. The write side classifies by actor (`ownership.py`) and the recall gate classifies by confidence (`recall_gate.py`), but nothing classifies by *where content came from*, and nothing re-checks ownership when a row is read back. Sensor output and tool results reach Halbert's own stores with only a margin check. The guest-persona divide is enforced on write but not on read — a single writer that forgot to classify would leak guest rows into Halbert's psyche. The A08-G12 path bug (conversation store default path computed at import, ignoring `HALBERT_DATA_DIR`) means pytest can open the production database.
- Overlap with merged remediation: R-02 (claims, admission graph, guest routes, voice provenance) established the guest persona and ownership routing on the write side. R-04 (conversation store hardening) hardened the store. R-05 (redaction registry) established the choke point. This packet is the complementary read-side half that none of those built. The section file explicitly says "P3 says an unclassified writer fails closed while a guest fronts" — the write-side rule exists; the read-side enforcement does not.
- Standing rules: No violation. Deterministic throughout, no model in any decision. Additive columns (no migration, no back-compat shim). Uses existing `route_write` plumbing. Does not name models.
- Effort justified: Yes. A guest's rows staying out of Halbert's psyche only because writers classified them is a single point of failure. The read-side filter makes it enforced on both sides — "write-side and read-side owner gates are separate enforcement points, so a store or index added later that forgot to classify on write still cannot leak on read." The A08-G12 fix is a concrete bug. An operator (the founder) would notice if pytest corrupted the production conversation store.
- Minimum viable version: The origin-class column + the eligibility predicate + the A08-G12 path fix. The tombstones, the harness skip guard, and the injection-shape counter are small riders that compose at the same insertion point.

**Opportunities:** The read-side visibility filter and the forget-tombstone predicate share one insertion point in the search methods — build them together. The injection-shape counter feeds MEM-P4's doctor audit.

---

### Packet: MEM-P2 — Promotion mechanics and the product-boundary test

**What it actually proposes:** Fix the dead `provenance='recalled_content'` parameter (A01-G8 — no caller ever passes it). Add a disjunctive content-shape contamination filter to `record_recall` and `rank_candidates` matching Halbert's own consolidation-marker shapes. Add a product-boundary test asserting a raw secret in a stored turn does not survive into promoted memory (and that a clean candidate is present with its marker — the test fails on over-suppression too). Cap per-key hash/day sets (A01-G6). Fix recency decay (A01-G2 — derive from `updated_at` at read time). Fix the reload bug that collapses `recall_count` (A01-G3). Add the memory event journal (A01-G9). Fix the remaining A01 bugs (G1, G7, G11, G12, G13, G14). Give the Consolidator an optional `promotion_store` consumer (A01-G1).

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: The product-boundary test and the contamination backstop are genuine gaps. The section file confirms `provenance='recalled_content'` has no caller — the parameter is dead. The contamination guard is content-shaped and catches a caller that forgot or mislabelled. The product-boundary test is the one assertion that names the actual harm (a secret surviving into promoted memory).
- Overlap with merged remediation: R-14 (memory promotion follow-through) is merged. R-14's scope is "13 gaps + 10 bugs" — this is exactly A01-G1 through G14 and the ten A01 confirmed bugs. The section file lists these as gaps to fix, but it was written before R-14 merged. R-14 should have fixed: the ranker consumer (G1), recency decay (G2), reload collapse (G3), origin class on signals (G4), forget reaching promotion tables (G5), unbounded hash/day sets (G6), hard gates (G7), dead provenance parameter (G8), event journal (G9), query hash normalisation (G11), malformed day row (G12), dangling-signal audit (G13), avg_score zero weight (G14). If R-14 is merged, MEM-P2 is 80%+ duplicating R-14.
- Standing rules: No violation. The test is additive. The contamination filter is deterministic. No model.
- Effort justified: The residual value is the product-boundary test (OC20-M1 — genuinely new, a test that pins the security property end to end) and the contamination backstop (OC20-C1 — the disjunctive content-shape filter + fixing the dead parameter, if R-14 didn't fix it). The A01 mechanics are R-14's territory.
- What R-14 likely did NOT cover: the product-boundary test (it's a test, not a fix), the envelope/transport-metadata strip check (OC20-C9 — a verification that no write-path store receives prompt-assembled text), and the bounded promotion candidate store with deterministic eviction (OC20-C2 — caps per-key hash/day sets, which may or may not be in R-14's G6).

**If RESHAPE: what it should become:** Three items only: (1) the product-boundary test (`test_redaction_product_boundary.py` with both halves — secret-in-transcript and four-candidate promotion), (2) the contamination backstop (disjunctive content-shape filter + fix the dead `provenance` parameter if R-14 didn't), (3) the envelope strip check (one test asserting no stored row carries prompt-assembled tags). Everything else is R-14's merged work — verify, don't rebuild.

**Opportunities:** The product-boundary test needs MEM-P1's origin-class column for the untrusted-candidate leg — sequence MEM-P1 first, land the test with that leg xfail until P1 merges.

---

### Packet: MEM-P3 — Store durability: WAL gate, verified backup, salvage, one durable-write helper

**What it actually proposes:** Port the SQLite WAL-reset-bug version predicate (Halbert is in the band — SQLite 3.39.4 measured). Add a `halbert backup` command using the online backup API with `integrity_check` verification and a content-addressed manifest (rejecting symlinks/hardlinks). Add a `halbert recover` command with copy-first-never-over-live salvage (try `integrity_check` and SELECT copy, then `.recover` as a last resort). Add safe archive extraction for the restore side. Extract one durable file-publish helper (mkstemp + fsync file + os.replace + fsync dir + chmod 0600, with symlink refusal) and route the inconsistent writers through it. Canonicalise the file subject in the state ledger with `os.path.realpath` before building the claim key.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes. No `PRAGMA integrity_check` anywhere. No backup. No salvage. The SQLite is in a known-corrupting version band (3.39.4). The durable-write inconsistency is real and verified: `scheduler/run_receipts.py:110-132` does the full pattern including directory fsync, but `config/being_config.py:861-877` does mkstemp + chmod + `os.replace` with no fsync at all, and `mcp/config.py:780-802`, `scheduler/engine.py:57`, `scheduler/executor.py:313` fsync the file but not the directory. The `storage/chromadb_manager.py:862-872` raw-copies a live WAL-mode `chroma.sqlite3` with `shutil.copy2`. The provenance subject canonicalisation gap is real: `continuity/provenance.py:215-217` writes the state-ledger claim subject as `f"file:{path}"` with no canonicalisation, so a symlinked spelling and the real spelling become two ledger subjects.
- Overlap with merged remediation: R-04 (conversation store + state ledger hardening) is merged. R-04 hardened the store with fsync pragmas, FTS fail-open, column reconciliation, the one-open-leaf index. But R-04 did not add backup, salvage, the WAL-reset gate, or the durable-write helper consolidation. The section file says "These are new mechanisms (not in either 09-07 review)." The WAL-reset predicate overlaps with CSC-04's HM13-M2, but MEM-P3 focuses on the backup/salvage/durable-write side while CSC-04 focuses on the store-hardening side (corruption quarantine, error taxonomy, refcounted registry).
- Standing rules: No violation. The backup is additive (new command). The WAL gate is a doctor row + a log, not a silent journal-mode change — the section file explicitly says "do not silently switch journal mode on live stores as the origin does — log and bump." The durable-write helper consolidates existing patterns. No migration of existing data. The venv rebuild is a founder call.
- Effort justified: Yes. For a single-user system whose entire memory is SQLite, having no backup and no integrity check is a real risk. The founder runs this on an external volume (the repo path is `/Volumes/4TB-BAD/Halbert`). The durable-write helper is a consolidation that reduces drift, not new infrastructure.
- Minimum viable version: The WAL gate doctor row + the verified backup command + the durable-write helper consolidation + the provenance subject canonicalisation. The salvage and safe extraction are tail cases that follow.

**Opportunities:** The durable-write helper (`utils/durable_write.py`) is a cross-cutting mechanism — P3's atomic config writes and P6's live-SQLite-file handling both need it. Build once. The `integrity_check` helper feeds MEM-P4's doctor. The WAL-reset predicate is shared with CSC-04 — build once in `utils/sqlite_safety.py`.

---

### Packet: MEM-P4 — Continuity doctor and the promotion inspector

**What it actually proposes:** Add `continuity/doctor.py::audit()` returning typed findings — unreadable/corrupt artifacts (integrity_check per store), promotion rows whose claim key no longer resolves in the state store (A01-G13's liveness predicate), a self-ingestion count, an injection-shape count, FTS-degraded breadcrumbs standing with no rebuild, and the "recall needs an embedding backend that is not running" finding. Repair renames into a `.repair/` directory (never unlinks). Add a read-only "Queued for promotion" table in `Memory.tsx` fed by `rank_candidates()` output with clamped score components, origin class, and liveness flag.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: The doctor is genuinely useful — nothing inspects the promotion store artifacts today, and the section file confirms `grep 'def audit|def repair|def verify' continuity/` returns nothing. The inspector (OC23-C14) is a UI surface for internal scoring data.
- Overlap with merged remediation: R-14 (memory promotion follow-through) is merged. R-14 likely fixed A01-G1 (ranker consumer) and A01-G6 (unbounded hash/day sets). If so, the inspector's prerequisites ("A01-G1/G6 so the numbers mean something") are met. But the doctor itself is new infrastructure not in R-14's scope. R-15 (eval harness and verdict contract) is merged — it measures whether consolidation loses facts, but nothing inspects the artifacts themselves.
- Standing rules: The inspector must use shared colour tokens, no emoji, speak in first person ("recalled on 4 distinct days"). No violation. The doctor's repair renames into `.repair/` — never unlinks, consistent with "leave superseded data on disk, unread."
- Effort justified: The doctor is justified — it's the memory subsystem's own health check, and the founder is the consumer. The inspector is lower value — it's a read-only table showing internal scoring data. For a single-user system with no users, the founder can read CLI output. The section file itself narrows the inspector: "no risk taxonomy — that is new classification work with no consumer."
- Gate: The doctor depends on MEM-P2 (clamped scores, liveness predicate, content-shape detector) and MEM-P3 (integrity_check helper). The inspector depends on MEM-P2 and MEM-P1.

**If RESHAPE: what it should become:** Split: (1) the doctor's `audit()` function — ACCEPT, gated on MEM-P2 and MEM-P3. (2) the promotion inspector — DEFER until there's a reason to look at it beyond the founder's own curiosity. The doctor's `repair()` is a nice-to-have that can follow the audit.

**Opportunities:** The doctor's audit composes with MEM-P1's injection-shape counter and MEM-P3's integrity_check helper. The self-ingestion detector reuses MEM-P2's content-shape detector. Build the doctor after P1/P2/P3, not in parallel.

---

### Packet: MEM-P5 — Staged writes, the vault rule, and prospective memory on reflexes

**What it actually proposes:** Add an opt-in `continuity.write_approval` flag (default off) that stages autonomous memory writes under `pending/memory/` with a diff instead of committing directly, applied from a Settings surface. Record the vault eviction rule in DECISIONS.md (evict only what a structural marker proves the machine generated; preserve anything ambiguous). Add standing intents (durable, deterministic "fire this when the trigger recurs") with cooldown, max_fires, expiry, lifecycle state, and a turn-path trigger. Add a recall-intent classifier with future-vs-retrospective disambiguation.

**Verdict: DEFER**

**Reasoning:**
- Real problem: Mixed. The write-approval staging extends the "staged, never executed" posture to the machine's own autonomous writes — aligned with the standing directive, but gated on founder decision F-3 (whether there's an always-injected curated core to govern). The standing intents are a new capability — Halbert has the deterministic rule store (`proactive/reflexes.py`) but lacks cooldown, max_fires, expiry, and lifecycle state (an enabled reflex currently fires forever, which is a defect). The recall-intent classifier is explicitly parked with the heartbeat decision F-4.
- Overlap with merged remediation: R-11 (skills plane) is merged, which may touch skill-write staging. But the memory-write staging is a different surface. No merged R-packet covers standing intents or the recall-intent classifier.
- Standing rules: No violation. The staging is opt-in, default off. The vault rule is a DECISIONS.md row, not code. The standing intents are deterministic (no model in the matching path).
- Effort justified: The lifecycle bounds on reflexes (cooldown, max_fires, expiry) are defect-shaped — an enabled reflex firing forever is a real bug. But the turn-path trigger ("remind me when X comes up") is a new capability that needs the F-3 ruling. The write-approval staging needs the F-3 ruling. The recall-intent classifier is parked. The section file says "this packet does not start without the rulings."
- Gate: Founder decisions 2, 3, 4, and 6. The section file is explicit: "this packet does not start without the rulings."

**If RESHAPE: what it should become:** If the founder rules: (1) the reflex lifecycle bounds (cooldown, max_fires, expiry) are ACCEPT as a defect fix — an enabled reflex firing forever is a bug, no new surface needed. (2) The write-approval flag + pending store is ACCEPT if F-3 rules there's an always-injected core. (3) The turn-path trigger, the vault rule, and the recall-intent classifier remain DEFER, gated on F-3 and F-4.

**Opportunities:** The write-approval pending store shares its shape with P3's `approval/pending_store.py` — both are durable pending-write stores behind the "staged, never executed" directive. Build one pending-store mechanism and use it for both memory writes and skill writes.

---

### Packet: MEM-P6 — The compaction gate follows the real number

**What it actually proposes:** Persist the last real `prompt_tokens` per thread (a column on the thread row or the turn receipt — no migration, default NULL). In `build_conversation_window` use `max(estimate, last_real)` instead of discarding the provider's number. Add a replay harness proving the gate fires correctly across live/persisted/reload shapes. Carry the persistence-caught-up invariant into the A16 rotation design (a rotation TXN may only drop rows from the projected window after the boundary row and its summary are committed).

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes, and concrete. `llm_client.py:279, :491` store `prompt_tokens`/`input_tokens` into an `LLMResponse.usage` dict nothing reads. Every sizing decision calls `estimate_prompt_tokens()` with a chars-per-token guess. The compaction gate at `assembler.py:1368-1369` uses `_history_tokens(history, counter)` against a local estimate while the true number is in hand and discarded. The section file re-verified every cited line. For a steward whose value is continuity, silently losing the head of the prompt because the gate used a guess is the worst outcome.
- Overlap with merged remediation: R-12 (session tree: deterministic compaction v0) is merged (Phases B/C merged, Phase A pending-merge). R-12 is about the rotation writer and the session tree, not about the watermark gate's input. The gate-follows-real-number fix is not in R-12's scope. R-15 (eval harness and verdict contract) is merged — it measures consolidation quality, not the gate's input.
- Standing rules: No violation. No model involved. No migration (additive column, default NULL). The replay harness uses a fake server, not a real model.
- Effort justified: Yes. The fix is small (persist one number, use max(estimate, real)). The value is high (the gate stops using a guess when the real number is available). The replay harness is valuable but can follow.
- Minimum viable version: Persist the last real `prompt_tokens` per thread and use `max(estimate, last_real)` in the gate. The replay harness and the persistence-caught-up invariant are follow-ups.

**Opportunities:** The persistence-caught-up invariant (HM11-C9) belongs in the A16 rotation design — it's a design clause, not a standalone mechanism. The `ctx.last_activity` stamp that CSC-03/CSC-05 need is a different stamp but shares the "stamp on the ctx, read at the gate" pattern.

---

## Conversation-Session-Compaction Workstream (CSC-01 through CSC-06)

### Packet: CSC-01 — Turn-boundary trust and decode

**What it actually proposes:** Add a 5-pass JSON repair ladder for malformed tool-call arguments (strict=False, strip trailing commas, close unclosed braces, trim excess closers, escape control chars) instead of silently substituting `{}`. Wrap external-origin tool results in an `<untrusted_tool_result>` delimiter block with delimiter neutralization (no "already wrapped" fast path — that check is attacker-forgeable). Extract one shared prompt-literal sanitizer from the three existing implementations with different rules (`discovery/schema.py`, `integrations/observation_text.py`, `agents/state_machine.py`). Route internal tool results through `redact_result` (the parked 05-C question). Build one scoped threat-pattern library with invisible-unicode checks (on RAW content before NFKC). Sanitise titles against invisible/bidi/object-replacement code points and lone surrogates. Add timeout-bounded reads for files loaded into prompts.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes, multiple. `model/client.py:456-462` logs once and sets `args = {}` — a tool runs with no path or no command and neither model nor user is told. `agents/llm_client.py:258-267` does not decode at all — an OpenAI-compatible provider's JSON string reaches a consumer expecting a dict. The tool-observation string is built raw at `state_machine.py:153-163` with no in-band data-not-instruction marker. Halbert has the sanitizer THREE times with different rules — exactly the drift `security/result_redaction.py:5-8` exists to kill. No invisible-codepoint or homograph check anywhere in the prompt path. No timeout on file reads that feed prompts (the repo lives on an external volume — a stalled mount can wedge turn assembly).
- Overlap with merged remediation: R-05 (redaction registry) is merged — it established the registry and the choke point. R-06 (echo guard, display projection) is merged — it covers the display seam. R-09 (MCP client boundary) is merged — it covers MCP-side security. But the tool-call argument repair, the untrusted-result wrapper, the shared sanitizer extraction, the threat-pattern library, and the timeout-bounded read are all new — not covered by any merged R-packet. OC15-C7 (same redaction at every model-facing view) partially overlaps with R-05/R-06, but the specific finding is that internal executor results are "deliberately NOT" routed through the redaction core — this is the parked 05-C question (founder decision 6 in the CSC section). R-05 established the registry; this packet closes the gap.
- Standing rules: No violation. Deterministic throughout. No model. The sanitizer extraction consolidates existing implementations (reduces drift, doesn't add a fourth). The threat-pattern library is scoped (anchors on attack behaviour, never bossy English). The title sanitisation is a rider on the sanitizer extraction (same regexes).
- Effort justified: Yes. The silent `{}` substitution is a real defect that causes tools to run with no arguments on local models — "local-first posture is the whole reason; quantized local models are the population that emits this." The three-different-sanitizer drift is a security risk. The timeout-bounded read is justified — the repo is on an external volume.
- Minimum viable version: The JSON repair ladder + the shared sanitizer extraction + the untrusted-result wrapper + routing internal results through `redact_result`. The threat-pattern library and title sanitisation are riders on the same character classes. The timeout-bounded read is independent and cheap.

**Opportunities:** The shared sanitizer and the threat-pattern library are cross-cutting — P3's chat-template token stripping and P4's terminal-output marker stripping need the same character-class handling. Build one `security/prompt_sanitizer.py` and reuse. The timeout-bounded read (`utils/bounded_read.py`) is shared with P5's fd-pinned bounded read — same "open once, fstat, read bounded" pattern.

---

### Packet: CSC-02 — Deterministic context reclaim and window-relative budgets

**What it actually proposes:** Add a deterministic per-tool-type one-line result summariser (terminal → "ran … -> exit 0, 42 lines", file-write → "wrote … (12 lines)", search → "-> 7 matches") replacing the flat 2000-char prefix cut, with a never-raises guard and a cheap re-trigger over accumulated observations. Derive all context budgets from `num_ctx_for_model`'s resolved window (per-bucket allocations, tool-result share, reserved summarisation overhead) instead of a model-name regex. Add a reactive compress-and-retry on actual context-overflow errors (capped, progress-checked). Cap `ctx.images` at keep-newest-N. Add a near-limit budget warning with cross-turn dedupe. Add an absorption cursor so the receipt is folded incrementally instead of rebuilt from the whole thread on every `end_turn`.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes. The tool-result cap is a flat 2000-char prefix cut (`_TOOL_RESULT_CHARS = 2000`) applied once at arrival with no re-pass — the exit code and match count (the most important information) are lost. The budget tier is picked by `detect_model_tier` from a parameter-size regex on the model NAME while `num_ctx_for_model` already discovers the real window per endpoint/model — the two are unconnected. The model-name regex is a soft form of "bake model names" — removing it is directly aligned with the standing rule. The absorption cursor is O(thread length) on the turn-finalisation path (`threads.py:1044-1049` lists every row and hands all to `build_receipt` on every `end_turn`), which grows under one continuous conversation.
- Overlap with merged remediation: R-12 (session tree: deterministic compaction v0) is merged. R-12's Phase A includes the deterministic compaction v0 (receipt concatenation). But the per-tool summariser, the window-relative budgets, and the absorption cursor are not in R-12's scope — they're building blocks that R-12's rotation writer would use but are separate mechanisms. R-13 (utility slot) is merged — it fixed the model-name regex in the utility slot, but not in the context budget tier.
- Standing rules: The model-name regex removal is directly aligned with "never name or recommend an AI model on any user-facing surface." The budgets derived from the discovered window are cleaner. No violation.
- Effort justified: Yes. The flat prefix cut loses the exit code — the one piece of information that tells the model whether the command succeeded. The absorption cursor is a real O(n) cost on every `end_turn`. The reactive compress-and-retry replaces silently losing the head of the prompt (`model/client.py:735-746` detects the Ollama overflow, logs "Ollama will truncate the head of the prompt", and sends anyway).
- Minimum viable version: The per-tool summariser + the window-relative budget derivation + the absorption cursor. The reactive compress-and-retry and the image cap are lower priority.

**Opportunities:** The absorption cursor and the per-tool summariser both feed R-12's rotation writer — build them before the rotation writer's Phase B/C if those haven't merged yet. The window-relative budget derivation feeds CSC-02's own re-trigger and CSC-01's wrapper cap — build the budget first.

---

### Packet: CSC-03 — The conversation survives the process

**What it actually proposes:** Install a chained SIGTERM/SIGINT handler in the dashboard entry point that flushes non-running turn state before falling through to uvicorn (installed before uvicorn takes signals). Write a durable interrupted-turn marker when `AgentStateMachine` enters a turn, cleared on every terminal transition, surfaced as a first-person line on next start ("I was cut off while …"). Write a `.clean_shutdown` marker on graceful exit; at startup, examine the one open leaf and decide crash-vs-clean (mark and report only — do not close or delete without a founder ruling). Add a shutdown flush-to-spool for state that never reached the store. Install an asyncio loop-exception handler that collapses benign peer-hangup noise.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes. No signal handler exists (`grep -rn "signal.signal\|set_exception_handler" dashboard/ agents/` returns nothing). No interrupted-turn marker. No crash-vs-clean detection. `conversation_sqlite.py:1215-1240` documents that `append_message` returns None after a WARNING when the write fails and "nothing is left behind on failure." A crash mid-turn loses the last messages with no recovery. The section file calls the SIGTERM handler "highest value-per-line item in the unit."
- Overlap with merged remediation: R-03 (scheduler durability) is merged — it covers scheduler-side durability (receipts, liveness markers, boot catch-up). R-04 (conversation store hardening) is merged — it covers store-side hardening. But the signal handler, the interrupted-turn marker, the `.clean_shutdown` marker, and the shutdown flush-to-spool are all new — not covered by any merged R-packet. R-12 Phase A (pending-merge) includes A16-G5 (an interrupted turn leaves a persisted `interrupted` fact) — this is the transcript-side twin of the marker. If R-12 Phase A is pending-merge, the marker and the interrupted row should be built together.
- Standing rules: No violation. The marker is additive (a file, not a migration). The startup sweep is mark-and-report only — "do not close or delete without a founder ruling (no-migrations directive)." The first-person line ("I was cut off while …") is aligned with "the system speaks as the computer itself, in first person."
- Effort justified: Yes. The founder runs this .app — a crash that loses the last messages with no recovery is a real risk. The signal handler is small and high-value. The interrupted-turn marker is high priority.
- Minimum viable version: The SIGTERM handler + the interrupted-turn marker + the `.clean_shutdown` marker. The shutdown flush-to-spool and the loop-exception handler are riders at the same install site.

**Opportunities:** The `ctx.last_activity` stamp that this packet's interrupted-turn marker needs is the same stamp that CSC-05's stall notice (HM11-C12) and approval-wait-pauses-the-clock (OC15-M3) need, and the same stamp that A07-G10 (turn-liveness watchdog) asks for. Build `ctx.last_activity` once and reuse for all four. The `.clean_shutdown` marker and the startup sweep compose with CSC-04's zeroed-database detection — both run at boot before the first turn.

---

### Packet: CSC-04 — Conversation-store hardening II

**What it actually proposes:** Read the row `PRAGMA journal_mode=WAL` returns (never downgrade a WAL file). Gate new-file WAL on the SQLite WAL-reset version predicate (founder decision). Split the corruption classifier so bare structural errors (`malformed`/`NOTADB` with no FTS attribution) raise a typed corrupt error and quarantine the handle instead of fail-opening. Add a SQLite error taxonomy (busy vs damaged vs disk-full, corrupt checked before disk). Add a refcounted shared-store registry (one writer connection per database file — currently three independent connections on the same file). Add freelist-ratio-gated, interval-throttled startup maintenance. Add zeroed-database detection before the first connection. Add a progress-handler deadline for store reads. Add an end-reason taxonomy.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes, multiple confirmed bugs. The classifier at `conversation_sqlite.py:886` classifies `'malformed' in msg` as FTS-scoped — the docstring even says "a bare malformed image is structural" and then routes it to fail-open, whose contract is "the canonical write continues" — exactly the compounding Hermes documents. No `PRAGMA integrity_check` anywhere. Three independent connections on the same file (`threads.py:1235-1265`, `guest.py:647`, `conversations.py:73`), each with a bare `close()`. The WAL pragma row is discarded. Zeroed-database detection is absent — a zeroed store would present as "the assistant lost its memory" with the schema bootstrap writing over the evidence.
- Overlap with merged remediation: R-04 (conversation store + state ledger hardening) is merged. R-04 hardened the store with fsync pragmas, FTS fail-open, column reconciliation, the one-open-leaf index. But the section file says this packet "extends packet 08" — it's the second pass on the same file. The A08 gaps listed here (G1-G5, G7, G8, G11, G12, G14) are the ones R-04 didn't fix or that were found after R-04. The section file says "A08-G12 (`HALBERT_DATA_DIR` honoured by the conversation store) first, so quarantine tests cannot touch production data" — this is a prerequisite, suggesting it wasn't fixed by R-04.
- Standing rules: No violation. The WAL gate is a founder decision (decision 1) — "gate new files on the predicate, never downgrade, log at startup." The quarantine is additive (move aside, never delete). No migration.
- Effort justified: Yes. The corruption classifier routing bare structural errors to fail-open is a confirmed bug that compounds damage — "a handle that kept writing for ~50 minutes and turned a readable file unopenable on shutdown." The refcounted registry prevents lost/reordered page-write corruption from multiple connections. The zeroed-database detection prevents "the assistant lost its memory" with the schema bootstrap writing over evidence.
- Minimum viable version: The corruption classifier split + the WAL pragma row reading + the zeroed-database detection + the A08-G12 path fix. The refcounted registry and the error taxonomy are medium priority. The maintenance pass and the progress-handler deadline are lower.

**Opportunities:** The WAL-reset predicate is shared with MEM-P3 — build once in `utils/sqlite_safety.py`. The corruption quarantine and the error taxonomy feed MEM-P4's doctor. The refcounted shared-store registry is the prerequisite for any future multi-process access — but the section file notes "the precondition is unproven" (the scheduler runs inside the dashboard process), so the small version (module-level acquire/release) is sufficient.

---

### Packet: CSC-05 — Turn admission, identity and mid-turn verbs

**What it actually proposes:** Add an idempotency key on `POST /message` with in-flight replay (a retried request never costs a second generation). Declare a `system`/`scheduler` channel for machine-originated turns (currently `process()` silently treats an unknown modality as a typed admin turn). Build an opaque conversation address from transport identity (currently `session_affinity.py` routes by regexing an id out of the message text). Make approval wait pause the clock (currently a 15-minute approval wait burns the next request's whole 600s lock budget). Add a stall notice from a shared progress clock. Add a structured `clarify` verb. Add a side-question mechanism. Add replay-safety classification (unclassified means side-effecting). Add a per-turn tool-call budget. Project one canonical tool policy onto MCP identities.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Mixed. Some items are real defects: A09 bug (`process()` silently treats an unknown modality as a typed admin turn — a system turn enters the one open thread indistinguishable from the owner's typed turn). The approval-wait-pauses-the-clock gap (a turn parked on a HIGH-risk confirmation burns the next request's whole lock budget). The stall notice (no turn-level progress clock exists — `agents/turn_activity.py` is a bare generation counter without timestamps). Others are new capabilities: the `clarify` verb (founder decision 8), the side question (founder decision 4). Others are low priority: the tool-call budget, the canonical tool policy.
- Overlap with merged remediation: R-01 (talk-door ordering, interrupt algebra) is merged. R-01 covers the #1 finding (unauthenticated mid-turn steer) and the interrupt algebra (A07 gaps). The section file lists A07-G1 through G13 as gaps to fix in this packet. If R-01 merged, most A07 gaps should be fixed: A07-G1 (mid-turn steer runs before the relay receipt), A07-G2 (stop during a tool demoted to steer), A07-G3 (steer accepted after stop/commit then discarded), A07-G4 (steer marker is bare `[steered]`), A07-G5 (stop cannot abort in-flight model request), A07-G6 (second steer erases first), A07-G8/G9 (no yield primitive, queued turn cannot be stopped), A07-G10 (no turn-liveness watchdog), A07-G13 (dashboard stop button bypasses generation claim). R-01 was specifically scoped to fix these.

  R-02 (claims, admission graph, guest routes, voice provenance) is merged. R-02 covers the claims ladder and admission gates. A12-G6 (talk door produces no IngressDecision) and A09-G1 (unidentified voice can inject) should be fixed by R-02.

  R-08 (permission lattice: ask axis, approvals, leases, halt) is merged. R-08 covers the approval lattice. OC15-M3 (approval wait pauses the clock) may partially overlap with R-08's lease work.

  So a significant portion of CSC-05's audit gaps are already fixed by R-01, R-02, and R-08. The residual is the items not covered by those packets.

- Standing rules: The `clarify` verb must have no emoji, no session list. The side question should be an ephemeral hidden thread (founder decision 4). The system channel is a declared non-admin channel (founder decision 7). No violation if these are respected. The opaque conversation address degenerates cleanly to one user (peer = owner) — consistent with the one-continuous-conversation directive.
- Effort justified: The idempotency key is justified (a retried request never costs a second generation). The system channel is justified (machine-originated turns enter as admin today — a real bug, A09 confirmed). The stall notice is justified (no turn-level progress clock). The `clarify` verb and side question are new capabilities needing founder rulings. The tool-call budget and canonical tool policy are low priority.
- This is the hottest packet in the workstream — it touches `routes/agent.py`, `state_machine.py`, `steering.py`, `channels.py`, `session_affinity.py`, `executor.py`, `base.py`, `mcp/registry.py`.

**If RESHAPE: what it should become:** Strip the A07 gaps already fixed by R-01 and the A12/A09 gaps already fixed by R-02. Keep: (1) the idempotency key (not in R-01/R-02), (2) the system channel / declared origin for machine-originated turns (may be partially in R-02's channel work, but the specific A09 bug — `process()` silently treats unknown modality as admin — may not be), (3) the stall notice + `ctx.last_activity` stamp (not covered, and A07-G10 wants the same stamp), (4) the approval-wait-pauses-the-clock (may be partially in R-08's lease work — verify). Defer: the `clarify` verb (founder decision 8), the side question (founder decision 4). Drop: the tool-call budget (low priority), the canonical tool policy (low priority), the replay-safety classification (medium, can follow).

**Opportunities:** The `ctx.last_activity` stamp is shared with CSC-03's interrupted-turn marker and A07-G10's turn-liveness watchdog — build once. The idempotency key and the system channel both touch `routes/agent.py` and `state_machine.py` — sequence them together. The opaque conversation address is independent and can run in parallel.

---

### Packet: CSC-06 — Terminal reattach and desktop boot

**What it actually proposes:** Replace per-chunk `errors="replace"` decoding with a per-connection incremental UTF-8 decoder (a multi-byte code point split across a read boundary is permanently corrupted today). Close the PTY reattach loop: deliver the replay buffer as a typed `replay` frame (currently dropped), add a `reconnecting` status in the frontend, add a pure reconnect-policy module (backoff + attempt ceiling + close-code classification). Have the backend announce its actual bound port on stdout (`HALBERT_BACKEND_READY port=<N>`) after uvicorn binds; the Tauri shell waits for it under a floored deadline (currently the shell guesses a free port — a textbook TOCTOU). Install a panic hook in the Tauri shell writing to a durable sink with synchronous flush.

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes, multiple defects. The per-chunk decoding corrupts multi-byte code points split across read boundaries — "a live bug on any non-ASCII output large enough to split, independent of reconnect." The PTY reattach loop is half-built and wired nowhere — `pty.py:320-321` drops the replay item, `useTerminalSessions.ts:310-318` marks a running session done with `exitCode -1` on any close. The port decision is a textbook TOCTOU — `lib.rs:33-35` binds and drops a `TcpListener`, then passes the port to the sidecar (the comment at `:56` records that this class of bug has already bitten once). No panic hook in the Tauri shell — every diagnostic in the spawn path is an `eprintln!` that is discarded when launched from Finder.
- Overlap with merged remediation: No merged R-packet covers terminal reattach or desktop boot. These are all new.
- Standing rules: No violation. The reconnect policy is a pure module. The port announcement is a stdout line. The panic hook writes to the state dir (capability boundary, not a hardcoded path). The origin's string opens with an emoji and suggests `/new` — the section file says "both must change (no emoji in UI; no session list)."
- Effort justified: Yes. The UTF-8 decoder bug is a live defect. The port TOCTOU has already bitten once. The founder runs this .app — a false exit on wifi flap is a real UX problem. The panic hook is a prerequisite for M3's "show the tail on timeout" to be worth anything.
- Minimum viable version: The UTF-8 decoder fix (highest priority, defect) + the port announcement (high priority, defect). The PTY reattach loop and the panic hook are medium priority. The section file notes M1/M4 may hand to TERM-1 and M3/M6 to DIST-1 if those rows are dispatched separately.

**Opportunities:** The port announcement and the panic hook both touch `src-tauri/src/lib.rs` and `dashboard/__main__.py` — build them together. The reconnect policy module is a pure frontend module that can be built independently.

---

## Permissions-Consent-Security Workstream (P1 through P6)

### Packet: P1 — Command gate rebuild

**What it actually proposes:** Replace the unanchored raw-regex classifier in `tools/safety.py` with a ported two-tier hardline/dangerous classifier with command-position anchoring (hardline tier: root/system rm, mkfs, dd, fork bomb, shutdown, `sudo -S`, base64-piped-to-shell; dangerous tier: needs approval unless allowlisted). Add argv-normalisation tables (interpreter inline-eval flags like `python -Ic`, command carriers like `env`/`xargs`/`find -exec`/`sudo`, shell-wrapper unwrapping) so `env FOO=1 python3 -Ic '...'` and `bash -lc "rm -rf /"` are classified correctly. Classify network-egress binaries (curl, wget, nc, telnet, etc.) as HIGH regardless of chain position. Escape and gate staged commands before they touch a live shell (currently `terminal.py:407-423` writes raw bytes to a live PTY with no gate — an embedded `\n` executes). Remove the one `shell=True` in `approval/simulator.py`. Add a creation-time hard reject of self-restart/kill job shapes (launchctl/systemctl/pkill naming Halbert's own unit). Add heredoc-body masking for regex guards. Validate model-produced tool arguments against the declared schema before dispatch (currently `classify('run_command', {'command': ['rm','-rf','/']})` raises `AttributeError` outside the try block — a weak local model gets a crash, not a correctable refusal).

**Verdict: ACCEPT**

**Reasoning:**
- Real problem: Yes, multiple. `tools/safety.py:115-290` is unanchored raw regex — `env FOO=1 python3 -Ic '...'`, `bash -lc "rm -rf /"`, `xargs rm -rf` all read as ordinary text. `terminal.py:407-423` calls neither `_gate_command()` nor `check_command_safety()` — an embedded `\n` executes, breaking the "commands staged from the UI are staged, never executed" directive. `approval/simulator.py:176-182` runs `shell=True` with caller-supplied text, reachable from `POST /api/settings/simulate/command` with no path through SafetyChecker. `classify('run_command', {'command': ['rm','-rf','/']})` raises `AttributeError` from `executor.py:569`, outside the try at `:624` — a weak local model gets a crash rather than a correctable refusal. The section file says "this matters more for Halbert than the origin because local models mangle arguments routinely."
- Overlap with merged remediation: R-08 (permission lattice) is merged — it strengthened the lattice, not the command gate. R-09 (MCP client boundary) is merged — it covers MCP-side security, not the command gate. No merged R-packet covers the command classifier in `tools/safety.py`.
- Standing rules: No violation. Deterministic only. No model. The staged-command gating is directly aligned with "commands staged from the UI are staged, never executed" — the section file says "UI commands staged, never executed is only true once this lands." The network-egress HIGH classification settles the open "todo D1" question (founder decision F-A9).
- Effort justified: Yes. The unanchored regex is a real security gap. The `shell=True` is a real bypass. The staged-command newline injection breaks a standing directive. The schema validation matters more for Halbert than the origin because local models mangle arguments routinely.
- Minimum viable version: The argv-normalisation tables + the two-tier classifier + the staged-command gating + the `shell=True` removal + the schema validation. The heredoc masking is a false-positive fix worth doing only after the argv tables land. The self-restart/kill guard is medium priority.

**Opportunities:** The argv-normalisation tables are the prerequisite for P2's approval fingerprint (the fingerprint uses the same parse the gate saw). The schema validation at the executor seam is the prerequisite for P2's authorisation-as-a-field (both touch `executor.py` dispatch). The staged-command gating and the `shell=True` removal both touch `terminal.py` and `approval/simulator.py` — build together.

---

### Packet: P2 — Approvals bound and fail closed; the policy descriptor registry

**What it actually proposes:** Make approvals expire and fail closed (delete `mode='auto'`; every read path marks elapsed requests EXPIRED == denied; refuse up front when no approval-capable surface exists). Add hash-bound one-shot approvals with consume-before-apply. Re-bind confirmations to the tool call at resume (currently `_handle_executing` re-reads `ctx.tool_calls[-1]` without comparing to the pending record). Add base-hash guards on policy writes (currently `routes/agent.py:2172-2203` applies a stored diff by writing `new_content` wholesale with no comparison to what was reviewed). Add lifecycle-generation stamps to leases. Build one approval-presentation builder that sanitises every field (scrub, redact, cap; refuse on out-of-vocabulary `risk_level`; fences sized to content). Add approval UI features (countdown, command-span highlighting, stale-resolution classing, keyboard chords). Make approval wait time not charged to the run's clock. Add a deterministic prefix/injection check before persisting a standing allow-rule. Make authorisation a required field on tool registration (missing or duplicate is a startup error). Name the policy layers with per-layer removal audit. Add a uniform blocked-event taxonomy with finality clauses. Gate cross-tool guidance on the actual tool set. Make run-scoped tool handles die with the run. Add consent explain and permission explain surfaces. Filter presence/camera rows by session-visibility. Add a zero-tool first-contact turn for new peers.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Mixed. Some items are real defects: `engine.py:134-158` sets `expires_at` only when the caller passes `timeout_seconds` (default None); `EXPIRED` and `expires_at` have no readers; `mode='auto'` grants by argument with a log warning. `executor.py:384-394 register()` silently overwrites a duplicate name. `routes/approvals.py:72-85` emit model-authored `action`/`reasoning`/`affected_resources` as a raw dict — no redaction, cap, or invisible-character handling. `safety.py:762, 782, 798, 808` build confirmation Markdown with hard-coded triple-backtick fences that content containing backticks can break. But many items are new capabilities or UI polish: approval UI countdown, command-span highlighting, keyboard chords, consent explain CLI, zero-tool first-contact turn, presence/camera filtering.
- Overlap with merged remediation: R-08 (permission lattice: ask axis, approvals, leases, halt) is merged. R-08 covers the permission lattice, the ask axis, approvals, and leases. The section file lists A11-G1 through G12 as gaps for P2 to fix. If R-08 merged, these should be fixed: A11-G1 (ask axis recorded, never enforced), A11-G2 (unreadable persisted grant scope escapes as ValueError), A11-G3 (consent narrowing never reaches an open lease), A11-G7 (leases have no expiry), A11-G8 (no primitive binds an approval to the digest of the artefact shown), A11-G9 (widening bar's surface/principal/authn are caller-supplied strings). R-08 was specifically scoped to fix these.

  R-02 (claims, admission graph, guest routes, voice provenance) is merged. A12-G1/G2/G3/G6 (admission decisions discarded, no per-capability claim floor, _admit evaluates gates after a block, talk door produces no IngressDecision) should be fixed by R-02.

  So P2 is substantially duplicating R-08 and R-02. The residual is the items not covered by those packets.

- Standing rules: No violation if the approval UI has no emoji and uses shared colour tokens. The consent explain surface must speak in first person. The zero-tool first-contact turn must not copy the proactive greeting — "the first-contact behaviour is a log entry or a pending-review item, never an unsolicited model-authored message."
- Effort justified: The approval-presentation builder is justified (model-authored text emitted as raw dict with no redaction — a real leak). The authorisation-as-a-field on registration is justified (a tool registered without a safety branch runs with a warning — `safety.py:553-559`'s final branch returns MEDIUM/allowed/"Unknown tool"). The uniform blocked-event taxonomy is justified (a deterministic denial invites retries for the rest of the turn — no loop detection). But much of the approval/lease binding is already in R-08.
- This is a massive packet — it lists 30+ items. It needs to be split.

**If RESHAPE: what it should become:** Strip the A11/A12 gaps already fixed by R-08/R-02. Keep: (1) the approval-presentation builder (OC01-M1 — sanitising every field, not covered by R-08), (2) the authorisation-as-a-field on registration (OC17-M1/C1 — the prerequisite for everything in Theme 9, not covered by R-08), (3) the uniform blocked-event taxonomy with finality clauses (OC14-C9/M4/C5 — not covered by R-08), (4) the hash-bound one-shot approval with consume-before-apply (OC09-C7 — verify R-08 didn't fix this), (5) the base-hash guard on policy writes (OC13-M1 — verify R-08 didn't fix this). Defer: the approval UI features (ship after the presentation builder), the consent explain surface (new CLI, low priority), the zero-tool first-contact turn (new capability, no consumer yet). Drop: items 80%+ covered by R-08.

**Opportunities:** The approval-presentation builder and P1's fence helper both produce text that surfaces render — build the presentation builder as the single producer. The authorisation-as-a-field on registration is the prerequisite for the uniform blocked-event taxonomy (both need the descriptor on `register()`). The approval-wait-pauses-the-clock (OC14-C21) shares the `ctx.last_activity` stamp with CSC-03/CSC-05 — build the stamp once.

---

### Packet: P3 — Self-modification: fence, staging store, honest config writes, instruction sources

**What it actually proposes:** Build one durable pending-write store behind the "staged, never executed" directive (record id, subsystem, action, gist, origin, created_at, replay payload; three-state decision; replay through the same path). Wire `assert_not_governed` at the six named write sites (it has zero callers today — the fence exists and protects nothing). Add a config-key denylist for Halbert's own settings (secret refs, model-slot connection settings, MCP server definitions, autonomy dial). Police dry runs (currently `write_config(path='~/.config/halbert/models.yml')` returns hunks of the API-key store as a dry-run diff — a general file-read primitive with no path policy). Make config writes atomic, permission-hardened, with backup rotation and post-write verification. Strip LLM chat-template special tokens from untrusted text (Ollama applies the chat template server-side, so `<|im_start|>system` in a filename forges a role boundary). Make project-local skill trust gated behind an explicit allowlist. Build a scoped threat scanner for instruction text. Add skill install/delete/write guards for the SK-6 path. Add catalog availability gating.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Yes, multiple critical findings. `assert_not_governed` has zero callers — the Class-1 fence exists but protects nothing. `write_config.py:60-70` takes an arbitrary path with only a per-tool-name `_policy_check`. `write_config(path='~/.config/halbert/models.yml')` returns hunks of the API-key store as a dry-run diff — a general file-read primitive with no path policy, and `react_agent.py:318-322` hands that diff to the model. `being_config.py:406-434 from_dict` silently drops unknown keys — a typo in `extra_secret_keys` silently drops an operator's instruction to treat a key as secret (fails OPEN). `skills/loader.py:43-52` still returns cwd-derived skill directories unconditionally. No invisible-codepoint or chat-template-token check in the prompt path.
- Overlap with merged remediation: R-11 (skills plane) is merged — it covers 13 gaps + 10 bugs in the skills system. The skill trust gate, the skill install/delete guards, and the catalog gating may be partially covered by R-11. But the section file says "coordinate with SK-3/SK-6 in the skills workstream" — suggesting these are not fully covered. R-05 (redaction registry) is merged — the chat-template token stripping and the threat scanner are not in R-05's scope. R-08 (permission lattice) is merged — the `assert_not_governed` wiring is the D3-P5 review-gated item, not in R-08's scope.
- Standing rules: The D3-P5 review must be scheduled, not merged silently. The config-key denylist is "the no-legacy-support directive as a tested boundary." No violation. The chat-template token stripping is high priority — the section file says "the primary slots are Ollama endpoints that apply the chat template server-side, so `<|im_start|>system` in a filename forges a role boundary beneath every wrapper."
- Effort justified: Yes. The `assert_not_governed` zero-callers finding is critical — the fence exists but protects nothing. The dry-run read primitive is a real security gap. The unknown-key silent drop is a real bug. The chat-template token stripping is high priority. But the skill install/delete guards are blocked on SK-6 (no install path yet), and the catalog gating is blocked on SK-3.
- This is a massive packet — it lists 30+ items across Themes 3 and 4. It needs to be split.

**If RESHAPE: what it should become:** Split into: (1) the fence + config-write hardening — ACCEPT, high priority. Wire `assert_not_governed` at the six named sites, add the config-key denylist, police the dry-run read, make config writes atomic with backup rotation, add strict unknown-key rejection. (2) The instruction-source hardening — ACCEPT, high priority. Strip chat-template special tokens, make project-local skill trust gated, build the scoped threat scanner. (3) The skill install/delete guards — DEFER, blocked on SK-6. (4) The catalog gating — DEFER, blocked on SK-3.

**Opportunities:** The durable-write helper from MEM-P3 (`utils/atomic_write.py`) is the mechanism for the atomic config writes — build once, reuse. The chat-template token stripping and the scoped threat scanner share character classes with CSC-01's shared sanitizer — build one `security/prompt_sanitizer.py`. The pending-write store shares its shape with MEM-P5's write-approval staging — build one `approval/pending_store.py`.

---

### Packet: P4 — Egress, secrets and redaction seams

**What it actually proposes:** Build one SSRF guard with pinned DNS, per-hop redirect re-validation, and a literal-string classifier (currently `routes/llm.py:110-113` returns True unconditionally for local providers before resolution — `provider='ollama'` bypasses the whole check). Make ambient `HTTP_PROXY` an explicit opt-in (currently Python `requests` honours `HTTP_PROXY` by default with no localhost bypass — `trust_env` appears nowhere in the tree). Bound response bodies with strict Content-Length. Scan outbound URLs for secret patterns. Register Halbert's own credentials with the redaction registry at every resolution (currently `llm_config.py:465, 898-906` hands the API key out without ever registering it). Normalise pasted credentials. Build a SecretRef grammar over the existing custody ladder. Seal resolved secrets into opaque tokens. Redact tool-failure logs and audit rows (currently `executor.py:573, 592` log `{tool_name} {args}` raw into the tamper-evident audit chain). Close the audit extras bag. Route error text through the registry. Make history reads get the same projection as live events (currently `GET /agent/timeline` returns `blocks_json` straight from the store). Sanitise chat input. Make the observe-only tee fail closed. Add structural URL redaction. Add a media/file delivery deny-list. Strip forged OSC 133 markers from terminal output.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Yes, multiple critical findings. `mcp/client.py:239` merges the whole `os.environ` into every stdio MCP child — every server gets `HALBERT_MCP_TOKEN` and every other server's token (but this should be fixed by R-09). `routes/llm.py:110-113` returns True unconditionally for local providers before resolution — `provider='ollama'` bypasses the whole SSRF check. `llm_config.py:465, 898-906` hands the API key out without ever registering it — a key echoed in a tool result or model reply is not redacted. `executor.py:573, 592` log `{tool_name} {args}` raw into the tamper-evident audit chain — a shell command with an inline credential is written to a log that is by design not editable. `routes/agent.py:2325-2356` returns `blocks_json` straight from the store — the only "redaction" is user-initiated forgetting. `streaming/shell_integration.py:183-205` parses OSC 133 markers from raw PTY output — a command whose output contains a D sequence becomes a real block boundary with an attacker-chosen id and exit code.
- Overlap with merged remediation: R-05 (redaction registry) is merged — it established the registry and the choke point. The credential registration, the error-text routing, the history-read projection, and the audit extras are extensions of R-05's work, not duplications. R-06 (echo guard, display projection) is merged — it covers the display seam. The history-read projection gap and the observe-only tee fail-open are not covered by R-06. R-09 (MCP client boundary) is merged — the `mcp/client.py:239` env merge should be fixed by R-09. The SSRF guard, the credential registration, and the secret sealing are not in R-09's scope. R-10 (speech egress) is merged — the channel-echo axis may partially overlap.
- Standing rules: No violation. The SSRF guard is deterministic. The credential registration extends the existing registry. The sealing is a founder decision (F-A5 — "defer until `execute_code` needs a credential in-process").
- Effort justified: Yes. The SSRF bypass for local providers is a real hole. The unregistered API key is a real gap. The raw-args audit log is a real leak. The history-read projection gap is a real leak. The OSC 133 marker stripping is a real injection vector. But the SecretRef + sealing is a subsystem that the founder decision says to defer.
- This is a massive packet — it lists 30+ items across Themes 6, 7, and 8. It needs to be split.

**If RESHAPE: what it should become:** Split into: (1) the SSRF guard + proxy opt-in + bounded bodies — ACCEPT, high priority (the SSRF bypass is a real hole, the proxy opt-in is a hole in the "local model traffic is local" guarantee). (2) the credential registration + normalisation + error/text redaction — ACCEPT (extends R-05's registry to Halbert's own credentials and error paths; the `llm_config.py` key-not-registered finding is high). (3) the history-read projection + audit extras + tee fail-closed — ACCEPT (extends R-06's display projection to history reads and the tee). (4) the OSC 133 marker stripping — ACCEPT (real injection vector). (5) the SecretRef + sealing — DEFER (F-A5 says defer sealing). (6) the media/file delivery deny-list — ACCEPT (medium, shared deny-list naming Halbert's own secret stores). Drop: the link detection (no consumer), the ReDoS guard (unwired).

**Opportunities:** The SSRF guard is one choke point that serves every outbound HTTP call — build once in `net/ssrf_guard.py`. The credential registration extends R-05's existing registry — one `get_global_registry().register(key)` call at `resolve()` and `api_key_for()`. The history-read projection reuses R-06's `verbose_text` — one `map` at the timeline route. The OSC 133 marker stripping and the chat-input sanitiser share the "strip ANSI first, then escape C0/C1" pattern with CSC-01's shared sanitizer.

---

### Packet: P5 — Third-party process boundary and file-path primitives

**What it actually proposes:** Replace the unconditional `{**os.environ, **env}` merge with an allowlisted baseline for MCP children and a dangerous-var denylist for PTY children (but the MCP env merge should be fixed by R-09). Add a dual-gate MCP server-config scanner. Add trust-tier gating with MCP annotations. Build a declared-capability + consent-hash registry. Gate tool-surface refresh to turn boundaries (currently `mcp/health.py:359-372` re-bridges from the health tick on the agent's own loop — the tool list can change between two API calls of one turn). Add peer-capability dangerous-tier gating. Resolve helper binaries from trusted directories (currently `crypto/storage.py:204-231` drives the macOS Keychain via bare `shutil.which('security')` — a PATH-hijacked `security` sees the custody key). Harden git subprocess env. Bound ffmpeg children. Add a turn-owned process baseline with epoch-gated reap. Add a sensitive-file pattern gate on reads (currently `safety.py:451-458` returns SAFE for `read_file` with no path inspection — `~/.ssh/id_rsa` reads straight into model context). Add fd-pinned bounded reads. Add write guards that resolve before matching, name credential files, and always-ask on instruction files.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Yes, multiple. The PATH-hijacked `security` binary is a real risk — `crypto/storage.py:204-231` drives the macOS Keychain through a bare `shutil.which('security')`. `dashboard/routes/development.py:548, 551` run git via bare `subprocess.run` with inherited env. `safety.py:451-458 _classify_builtin` returns SAFE for `read_file` with no path inspection — `~/.ssh/id_rsa`, `.aws/credentials`, and `.env` read straight into model context. `_read_file` does expanduser + abspath then four separate path-based syscalls — the file measured is not provably the file read (TOCTOU). `safety.py:723-739 _classify_write` matches the raw string with `path.startswith(sensitive)` and no `resolve()` — a tilde-spelled path is mis-rated. `mcp/health.py:359-372` re-bridges from the health tick on the agent's own loop — the tool list can change mid-turn.
- Overlap with merged remediation: R-09 (MCP client boundary) is merged — the `mcp/client.py:239` env merge should be fixed by R-09. But the PTY env, the helper-binary resolution, the git env, the file-path primitives, and the capability registry are not in R-09's scope. R-08 (permission lattice) is merged — the trust-tier gating and the declared-capability registry may partially overlap.
- Standing rules: No violation. The env policy is DATA (keys + prefixes). The helper-binary resolution is a fixed list. The file-path primitives are deterministic. The section file says "root-scoped is the wrong frame for Halbert; lift the fd pinning and the taxonomy, not a filesystem root."
- Effort justified: Yes. The PATH-hijacked `security` binary is a real risk. The unpoliced read of `~/.ssh/id_rsa` is a real leak. The git env is a real risk. The fd-pinned read is a real TOCTOU fix. The tool-surface refresh gating is high priority — "churns the cache-stable prefix SK-2 protects." But the MCP server-config scanner is medium, the OSV preflight is opt-in (F-A8), and the peer-capability gating is deferred (ROADMAP LD-1's two-machine run is the consumer).
- This is a large packet. It needs to be split.

**If RESHAPE: what it should become:** Strip the MCP env merge (fixed by R-09). Split into: (1) the file-path primitives — ACCEPT, high priority (the sensitive-file read gate and the fd-pinned read are critical; the write guards that resolve before matching are critical). (2) the helper-binary resolution + git env + ffmpeg bounds — ACCEPT (real security hardening, the `security` binary PATH hijack is high). (3) the tool-surface refresh gating — ACCEPT, high priority (churns the cache-stable prefix). (4) the declared-capability + consent-hash registry — ACCEPT (medium, extends R-08's lattice). (5) the MCP server-config scanner + OSV preflight — DEFER (F-A8 is opt-in, the scanner is medium). (6) the peer-capability gating — DEFER (ROADMAP LD-1's two-machine run is the consumer). (7) the turn-owned process baseline — ACCEPT (medium, the steward should not leave strays on its own host).

**Opportunities:** The helper-binary resolver (`utils/system_bin.py`) is shared with P6's `lsof`/`scutil`/`codesign` calls — build once. The fd-pinned bounded read shares the "open once, fstat, read bounded" pattern with CSC-01's timeout-bounded read — build one `utils/bounded_read.py`. The env policy (`security/env_policy.py`) is shared between the MCP child env and the PTY child env — build one policy module.

---

### Packet: P6 — The door, the OS-grant axis, doctor/lint and the security documents

**What it actually proposes:** Replace `?token=` on WebSocket auth with single-use tickets (currently `auth.py:416-436` falls back to `websocket.query_params.get('token')` — the raw token on the query string). Add an auth-failure limiter (currently no throttle anywhere on the door). Add one inbound-HTTP guard pipeline (body cap, base64 bounds, closed request models — currently `routes/audio.py:198-215` b64decodes an unbounded `audio_base64` without `validate=True` and assigns a ROLE to the resulting voiceprint). Add strict CSP on dashboard HTML (currently no CSP, X-Frame-Options, or any header anywhere; `tauri.conf.json` sets `csp: null`). Add TCC preflights populating the OS-grant axis (currently `DEFAULT_OS_GRANTS = OsGrantTable({})` — every id reads UNDETERMINED; `signingIdentity: null` is the vulnerable regime). Harden pairing. Add pre-auth WS budget. Add view-only terminal observation. Build a policy doctor with narrowing-only auto-repair. Add a declared env var table. Write SECURITY.md and a threat model. Add a process incarnation token. Add a cancellation marker for running work. Add a shutdown budget. Add a config watcher with coalesce and re-entrancy guard. Assert a private state root at startup. Add a machine name from the OS's human-set computer name.

**Verdict: RESHAPE**

**Reasoning:**
- Real problem: Mixed. Some items are real defects: `auth.py:416-436` falls back to `?token=` on the query string — a known vulnerability pattern (CWE-598). No CSP anywhere. `routes/audio.py:198-215` b64decodes an unbounded `audio_base64` — a memory exhaustion vector. `tauri.conf.json:58 "signingIdentity": null` — every OS-grant reads UNDETERMINED by construction. `dashboard/app.py:1623-1700+ shutdown_event` is a sequence of unbounded awaits — any one wedging hangs shutdown forever. `identity.py:111-140` ends its ladder at `socket.gethostname()` — the one label the founder directive forbids. But many items are new infrastructure for consumers that don't exist: pairing hardening (ROADMAP LD-1's two-machine run is the consumer), pre-auth WS budget (no rotation exists — M14 rows are stubs), view-only terminal observation (no observer surface exists).
- Overlap with merged remediation: R-03 (scheduler durability) is merged — the process incarnation token and the cancellation marker may partially overlap with R-03's liveness markers. R-08 (permission lattice) is merged — the OS-grant axis may partially overlap. But the door hardening, the CSP, the TCC preflights, the policy doctor, and the SECURITY.md are all new.
- Standing rules: The machine name from the OS is directly aligned with "named by the onboarding name, never the raw hostname." The SECURITY.md is founder decision F-A11. No violation. The body cap and the CSP are standard hardening. The `?token=` fix uses the existing `mint_ticket`/`verify_ticket` primitive — "the primitive exists; the task is wiring."
- Effort justified: The WebSocket `?token=` fix is justified (known vulnerability pattern, the primitive exists). The CSP is justified (no CSP anywhere). The body cap is justified (unbounded b64decode). The TCC preflights are justified (every OS-grant reads UNDETERMINED). The auth limiter is lower priority (the token is `token_urlsafe(32)`, so brute force is not the threat). The pairing hardening is deferred (no consumer). The view-only terminal is deferred (no observer surface). The policy doctor is justified but is a new CLI surface.
- This is the largest packet — it lists 50+ items across Themes 10, 11, 12, and 13.

**If RESHAPE: what it should become:** Split into: (1) the door hardening — ACCEPT, high priority (WebSocket `?token=`, body cap, CSP, `?key=` on compute.py). (2) the TCC/OS-grant axis — ACCEPT (signing identity, TCC preflights — every OS-grant reads UNDETERMINED by construction). (3) the policy doctor + lint — ACCEPT (the findings/detectors infrastructure exists, the lint CLI is the missing piece; the declared env var table is a rider). (4) the SECURITY.md + threat model — ACCEPT (F-A11, documents the boundary, cheap). (5) the runtime hygiene — RESHAPE (the shutdown budget and the config watcher are real; the process incarnation token may be in R-03; the cancellation marker is a real lost-update bug). (6) the machine name fix — ACCEPT (aligned with the standing directive, small). (7) the pairing hardening — DEFER (no consumer). (8) the view-only terminal — DEFER (no observer surface). (9) the DECISIONS.md rows — ACCEPT (cheap, prevents wrong first implementations).

**Opportunities:** The helper-binary resolver from P5 is the mechanism for the `lsof`/`scutil`/`codesign` calls in the TCC preflights — build P5's resolver first. The body cap and the closed request models share the `security/http_guards.py` extraction from the MCP handler — build once. The policy doctor's check catalog composes with MEM-P4's doctor and MEM-P3's WAL gate — the doctor pattern is the same across all three workstreams.

---

## Cross-Cutting Opportunities

These mechanisms appear in multiple packets across the three workstreams and could be built once to serve several.

### 1. One shared prompt-literal sanitizer (`security/prompt_sanitizer.py`)
Appears in: CSC-01 (HM02-M2 + OC15-M1 — extract from three existing implementations), P3 (OC12-M1 — strip LLM chat-template special tokens), P4 (OC12-M3 — strip forged OSC 133 markers from terminal output).
All three need the same character-class handling: strip invisible codepoints (Cc/Cf/U+2028/U+2029), escape delimiters, normalize Unicode, and strip chat-template tokens. Halbert currently has the sanitizer THREE times with different rules — building one shared module kills the drift that `security/result_redaction.py:5-8` exists to prevent.

### 2. One SQLite safety module (`utils/sqlite_safety.py`)
Appears in: MEM-P3 (WAL-reset predicate, integrity_check helper, backup, salvage), CSC-04 (WAL pragma row reading, corruption quarantine, zeroed-database detection, error taxonomy), P6 (HM14-M1 — live SQLite files never raw-copy).
All three need SQLite health checks, corruption classification, and safe copy. The WAL-reset predicate is shared between MEM-P3 and CSC-04. The `integrity_check` helper feeds MEM-P4's doctor. The error taxonomy (busy vs damaged vs disk-full, corrupt checked before disk) is shared between CSC-04 and MEM-P3's salvage. Build once.

### 3. One durable-write helper (`utils/atomic_write.py`)
Appears in: MEM-P3 (OC02-C5 + HM06-C7 — fsync file + dir, symlink refusal), P3 (OC05-C1/C2/C10 — atomic config writes with backup rotation), P6 (HM14-M1 — live SQLite files).
All three need mkstemp + fsync file + os.replace + fsync dir + chmod 0600, with temp identity recorded so the error-path unlink cannot remove a file it did not create. Halbert already has the reference implementation in `scheduler/run_receipts.py:110-132` — the task is consolidation, not invention.

### 4. One approval-presentation builder (`approval/presentation.py`)
Appears in: P2 (OC01-M1 — the only producer of anything a surface renders), CSC-05 (HM06-C10 — the `clarify` verb's question payload), MEM-P5 (the staged-write gist).
All three produce text that a dashboard surface renders. Build one builder that scrubs, redacts, caps, and fences, and route every surface through it. The fence helper (`max(3, longest_backtick_run+1)`) serves P1's `safety.py` sites too.

### 5. One `ctx.last_activity` stamp
Appears in: CSC-03 (HM18-C2 — interrupted-turn marker), CSC-05 (HM11-C12 — stall notice; OC15-M3 — approval-wait-pauses-the-clock), A07-G10 (turn-liveness watchdog).
All four need a monotonic timestamp touched at handler entry, each tool start/complete, and each stream chunk. The section file says "this is exactly the stamp A07-G10 asks for." Build once on `StateContext`, read by the stall check, the approval-wait subtraction, the interrupted-turn marker, and the watchdog.

### 6. One bounded-read helper (`utils/bounded_read.py`)
Appears in: CSC-01 (HM02-M4 — timeout-bounded read for prompt files), P5 (OC01-C7 + OCC01-M3 — fd-pinned bounded read for tool files), P6 (OC10-M7 — image pixel cap).
All three need "open once, fstat the descriptor, read a bounded window, with a timeout." The section file says the timeout-bounded read and the fd-pinned read share the "open once, fstat, read bounded" pattern. Build one helper with optional timeout and optional fd-pinning.

### 7. One env policy module (`security/env_policy.py`)
Appears in: P5 (HM09-C4 — allowlisted env for MCP children; PTY children), P4 (OC04-C7 — ambient proxy opt-in).
Both need a policy of which env vars are safe to inherit. The MCP child needs an allowlisted baseline; the PTY child needs a dangerous-var denylist; the proxy opt-in needs `trust_env=False` on local-model sessions. Build one policy as DATA (keys + prefixes, blocked-everywhere vs inherited vs override).

### 8. One pending-write store (`approval/pending_store.py`)
Appears in: P3 (HM10-M1 — the write-approval gate module behind "staged, never executed"), MEM-P5 (HM06-C11 — write-approval staging for autonomous memory writes).
Both need a durable pending record (id, subsystem, action, gist, origin, created_at, replay payload) with a three-state decision and replay through the same path. Build one store and use it for both skill writes and memory writes.

### 9. One destructive-cleanup helper (`utils/destructive.py`)
Appears in: MEM-P3 (HM14-C6 — safe archive extraction), P3 (OC04-C10 + OC09-C11 + OC14-C14 — destructive-cleanup helper), P6 (OC06-M6 + OC01-M7 — private state root + backup manifest).
All three need "refuse root/home/cwd-containing targets, move to Trash, separate preview entry point, lock." The section file says "trash is its mechanical form; `applescript_safety.py:260-263` already treats 'empty trash' as permanent."

### 10. One read-side trust filter
Appears in: MEM-P1 (origin-class eligibility gate, read-time ownership filter, forget tombstones), P5 (sensitive-file pattern gate on reads, fd-pinned bounded read).
Both need a "what may reach the model" predicate applied at a choke point. MEM-P1's filter is on memory recall hits; P5's filter is on file reads. The pattern is the same: a deterministic predicate that drops unsafe content before it reaches the prompt. Build the predicate pattern once, apply at both boundaries.

---

## Summary of Verdicts

### Memory Workstream (6 packets)
- **ACCEPT**: MEM-P1 (read-side trust axis), MEM-P3 (store durability), MEM-P6 (compaction gate follows real number)
- **RESHAPE**: MEM-P2 (strip R-14 duplicates, keep product-boundary test + contamination backstop), MEM-P4 (split doctor from inspector; defer inspector)
- **DEFER**: MEM-P5 (gated on founder decisions 2/3/4/6; reflex lifecycle bounds are the only ACCEPT-if-ruled piece)

### Conversation-Session-Compaction Workstream (6 packets)
- **ACCEPT**: CSC-01 (turn-boundary trust and decode), CSC-02 (deterministic context reclaim), CSC-03 (conversation survives the process), CSC-04 (conversation-store hardening II), CSC-06 (terminal reattach and desktop boot)
- **RESHAPE**: CSC-05 (strip R-01/R-02/R-08 duplicates; keep idempotency key, system channel, stall notice, approval-wait-pauses-clock; defer clarify verb and side question)

### Permissions-Consent-Security Workstream (6 packets)
- **ACCEPT**: P1 (command gate rebuild)
- **RESHAPE**: P2 (strip R-08/R-02 duplicates; keep presentation builder, authorisation-as-a-field, blocked-event taxonomy), P3 (split fence+config from instruction-source from skill guards), P4 (split SSRF from credentials from history-read from sealing), P5 (strip R-09 MCP env; split file-path primitives from helper-binary from capability registry), P6 (split door hardening from TCC from doctor from pairing)
- **DEFER**: within P6 — pairing hardening (no consumer), view-only terminal (no observer surface)

### Standout Opportunities
1. **The shared prompt sanitizer** is the highest-leverage cross-cutting build — it kills the three-implementation drift in CSC-01, enables P3's chat-template token stripping, and serves P4's terminal-output marker stripping. One module, three packets.
2. **The `ctx.last_activity` stamp** is the smallest build with the most consumers — CSC-03's interrupted-turn marker, CSC-05's stall notice, CSC-05's approval-wait-pauses-the-clock, and A07-G10's turn-liveness watchdog all need it. One stamp, four mechanisms.
3. **The SQLite safety module** is the most cross-workstream build — MEM-P3's backup/salvage, CSC-04's corruption quarantine, and P6's live-file handling all need the same predicates. One module, three workstreams.
4. **The approval-presentation builder** is the highest-security-value cross-cutting build — P2's raw-dict emission, CSC-05's clarify verb, and MEM-P5's staged-write gist all produce surface-rendered text. One builder, three surfaces, zero raw-dict leaks.
5. **The durable-write helper** is the most consolidation-shaped build — the reference implementation already exists in `scheduler/run_receipts.py`, and MEM-P3, P3, and P6 all need it. One consolidation, three packets, zero new patterns.
