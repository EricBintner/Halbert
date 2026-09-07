# OSS Review: Hermes Agent — patterns, code, and workflows worth learning from or lifting

**Date:** 2026-09-07
**Source reviewed:** `/Volumes/Thunderbolt/AI/OSS/hermes-agent` (Nous Research; Python)
**Version reviewed:** main @ `d9833c5615` ("fix(gateway): resolve busy origin privacy in routed profile")
**Method:** Eight parallel deep-dives (learning loop/skills, state machinery, memory/user modeling, gateway/channels, cron, subagents/script-RPC/terminals, MCP/providers/TUI, evals/batch/datagen), each briefed on Halbert's state and the prior OpenClaw review so findings could be rated as confirmed-twice / new / contradictory.
**Companion reviews:** `OSS-REVIEW-OPENCLAW-2026-09-07.md` (this series' first pass), `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-OPENCLAW-MEMORY-PROMOTION-SECOND-GUESS-2026-09-07.md` (the memory_v2 decision doc).

---

## What Hermes is (framing)

A "self-improving" personal agent: Python, one SQLite state DB per profile, a messaging gateway (Telegram/Discord/Slack/WhatsApp/Signal + CLI) and a separate TUI/desktop gateway over one JSON-RPC protocol, ~15 eval batteries, and a training-data-generation leg. Its architecture posture rhymes with Halbert's more than OpenClaw's did: **deterministic policy first, LLM judgment fenced inside it** — and Hermes's incident history (#29912, #67140, #61521) is the strongest external argument yet for that directive, because every one of those incidents is an LLM-judgment path that had to be re-fenced with a deterministic guard after it misbehaved.

Hermes is also the **most language-portable** target reviewed: Python throughout, so lifts are ports, not transcriptions. The trade: the codebase is mature to the point of archaeological (issue-number comments everywhere, plugin-compat shims, 3.2k-line files) — take the *invariants*, not the structure.

---

## Cross-reference with the OpenClaw review

**Confirmed twice (raise confidence to "adopt"):**
- SKILL.md CC/agentskills.io compatibility + a 60-char description discipline as the routing surface (Hermes hard-rejects over-budget descriptions at create time — enforcement, not lint).
- Challenge-code pairing with TTL/caps (Hermes adds NIST-style lockout + "default ignore, not pair" once any allowlist exists, so unknown contacts don't get info-leaking codes).
- Silent/suppression tokens for unattended replies (Hermes's `[SILENT]` matcher is shared across lanes so they can't drift).
- Durable run receipts where "interrupted/unknown" requires proof the owner died — never a timeout guess.
- Incident-deduped failure alerting (same error signature = one incident; ack closes it; new error = new incident).
- Post-turn/background writes never touching the live prompt (frozen snapshots, prefix-cache stability).
- Session search that never returns what's already in live context.

**Hermes adds, beyond the OpenClaw bar** (the new material):
- An **interrupt algebra** (stop/steer/redirect as three protocol verbs with a generation-claim race resolution and a yield-not-kill rule).
- A **zero-context-cost script execution** pattern (one tool call runs a multi-step tool pipeline; only the script's stdout enters context).
- State machinery hardened by years of real corruption incidents (atomic compression rotation, FTS fail-open, repair-on-a-copy, darwin fsync barriers).
- A cron system with cadence-scaled grace and occurrence-level idempotency.
- A **learning loop whose triggers are deterministic counters** and whose destructive actions are all guarded/reversible.
- An eval methodology (question-bank invariance, ceiling control arms, reviewer-authored probe batteries) that directly answers two open Halbert problems (the R5 gate, the 38 red seams).

**Contradictions with OpenClaw (record, don't resolve here):**
- Memory: OpenClaw is a signal-store/promotion design; Hermes is a **no-retrieval-strengthening** design (read-only recall everywhere, ranking fixed by deterministic rules over source metadata). Both reject what Haloysius does today (`.access()` strengthening on every search result). The second-guess doc's Option A is compatible with both; see the companion note in the Haloysius repo.
- Curated core: OpenClaw injects a budget-capped file; Hermes injects **wholesale frozen snapshots** of two small files (MEMORY.md ~2200 chars / USER.md ~1375 chars) and accepts no per-item ranking at all. Hermes's write-approval staging (`memory.write_approval` — auto-writes staged to a pending queue for out-of-band human approval) is the missing governance piece for *any* always-injected core.

---

## Ranked verdict: what to lift, by Halbert workstream

### 1. Zero-context-cost script execution (the `execute_code` pattern) — the crown jewel

`tools/code_execution_tool.py`: the model writes one Python script; a **generated stub module** (`hermes_tools.py`, plain-source, compiled per-session from the intersection of sandbox-allowed ∩ session-enabled tools — a disabled tool physically does not exist in the module) calls real agent tools over RPC (UDS locally; atomic-rename `req_N`/`res_N` file pairs over any remote execute channel); only the script's **stdout** returns to context, capped head/tail with a digest-keyed spill file and a `read_file(offset=...)` pointer. A 30-step search/extract/filter pipeline becomes one tool call and one turn. All enforcement is host-side in one function: constant-time token check, frozenset allow-list, mutable budget counter (only a dispatched call consumes budget — refusals are free).

Halbert mapping: the watched-terminal world generates exactly the "N grep/read/parse steps" pattern this collapses; stubs generated from Halbert's tool registry (including terminal-watch/read-PTY tools) let the agent run "scan every session's scrollback, classify, act" as one turn. Security posture notes: Hermes approves the script as a unit and documents that `subprocess/os.system` sail past the terminal guard — Halbert's version must inherit packet-02's lattice and the write-plane rules, and the "isolated backend is the jail" framing means the guard story depends on where it runs. **Anti-pattern to refuse:** Hermes's inline `` !`cmd` `` shell expansion during skill preprocessing (prompt-to-RCE surface) — do not lift.

### 2. The interrupt algebra — `agent/interrupt_control.py`

Three verbs, not one: **interrupt** (with `require_generation` — the abort publishes only if the turn's activity-generation still matches at the final mutation edge, so a resumed turn abandons the abort rather than double-firing), **steer** (appends user text to the *last tool result* once the current batch finishes; never kills anything), **redirect** (cancels only the model request, keeps completed messages, degrades to steer mid-tool and asks workers to *yield* — a foreground `sleep 300` hands the process to the background registry so the steer lands soon — "never kill a tool to deliver guidance"). Stop and redirect share one lock so a stop can't race into a retry. Gateway-side: busy modes are per-channel (`interrupt/queue/steer`), interrupt is demoted to queue when subagents or compression are in flight, and voice notes are transcribed **before** interrupting so the interrupt text is the transcript, not a placeholder.

Halbert mapping: the control surface for dashboard + terminal; the `require_generation` claim generalizes to any cross-thread cancel in the FastAPI core.

### 3. State machinery — the session-tree deep pass, pre-solved

The compression rotation is exactly Halbert's planned append-only tree with branch summaries, hardened by incidents:
- `publish_compression_child`: **one transaction** closes the parent, publishes the summary child + handoff messages, and stamps the parent — readers never see an ended parent with a missing child. A **watermark** taken at compression start bounds a tail-clone: messages appended *during* the slow summarization are column-cloned into the child.
- The **turn lease key walks to the lineage root** — every rotation segment serializes under one stable conversation identity.
- Anti-thrash counters are **persisted on the session row** (cooldown-until with merge-max, streaks, recovery deadline), not in-process.
- Four edge types (continuation/branch/delegate/tool children) share one `parent_session_id` column, distinguished by JSON markers.
- Cheap wins independent of the tree: `PRAGMA checkpoint_fullfsync=1` + forced `synchronous=FULL` on darwin (a real corruption class on Halbert's platform); the **FTS fail-open contract** (breadcrumb + trigger-drop atomically; a corrupt derived index never blocks canonical writes); **declarative column reconciliation** from one SCHEMA_SQL source (kills the skipped-migration class); repair on a scratch copy promoted via the online backup API, never in place, with a fingerprinted attempt ledger; title provenance as a CAS ladder (derived < llm < user) in the storage layer.

### 4. Cron — upgrades the scheduler packet (03)

Beyond the OpenClaw set: **grace scaled to cadence** (half the period, clamped [120s, 2h]; within grace catch up, beyond it fast-forward and fire once, `next_run_at` persisted *at dispatch time under the lock*); **occurrence-level idempotency** (`completed_occurrence` — a completed scheduled instant can never fire again even if `next_run_at` was left stale by a crash); one-shots past grace are **retired with a diagnostic file**, never fired hours late; the **monitor-hash gate** (a cheap script/URL hashed each tick; unchanged → the agent run is suppressed entirely; changed → a capped diff is injected — hash persisted before the run so a failed run doesn't re-alert forever); a closed `last_status` set (`ok / error / delivery_failed / blocked_config` — run success ≠ user got it); fail-before-spend preflight (blocked_config refuses before any LLM spend); fresh-session-per-fire with continuity via a **per-job KV notepad** + `context_from` chaining (cursors/watermarks as files, not memory); inactivity-based timeouts (a job streaming for hours is fine; a hung tool call dies); and consent-first self-scheduling (a suggestion queue with latched dedup, capped at 5 pending, nothing auto-creates). Anti-pattern: don't pay the hand-edited-JSON repair tax — validate-and-reject on load, receipts in SQLite from day one.

### 5. Learning loop — for the skills deep pass

The self-improvement triggers are **deterministic counters** (≥10 tool iterations → skill review; 10 user turns without a memory write → memory review; both reset on actual use, rehydrated from history on restart). The review is a **post-delivery background fork** sharing the parent's session and cache, running under a **dispatch-side tool whitelist** (advertised tools stay byte-identical; only dispatch is filtered — cache-safe), auto-denying dangerous commands, cancellable by any live turn, surfacing a one-line summary. The prompt policy is the real IP: an anti-hoarding doctrine (environment-dependent failures, transient errors, negative tool claims, and unresolved failures are never captured — "never dress up dead ends as best practice"; patch-this-session's-skill-first preference ladder; frustration is a first-class signal). Guards: **read-before-write** enforced per-fork via a ContextVar set (transcript quoting doesn't count), ownership provenance via a sidecar `created_by: agent` key (never inferred from location), autonomous pins block all writes while foreground pins block only deletes, **archive-not-delete** everywhere with tarball rollback before any mutating pass, and a delete guard requiring an `absorbed_into=` forwarding target (after the LLM archived active clusters with zero verified consolidations, #29912). A calibrated linter turns hoarding failure modes into machine checks (PR-ref density, >60 reference files, marketing words). Anti-pattern: the SKILL.md "## Verification" section exists but nothing executes it — Halbert's version should run it (dry-run the canonical command) before a self-created skill is trusted.

### 6. Memory — the input that matters for the Haloysius decision

Hermes is the **existence proof that rich recall works with no retrieval-strengthening at all**: FTS5 session search is stateless BM25 with no write-back; external-provider reads are read-only; built-in memory is wholesale-injected (no per-item ranking, so no loop is possible). Ranking pathologies are fixed with deterministic rules over source metadata (cron sessions demoted below interactive ones before dedup — "recall blindness" — and current-lineage hits suppressed while still in live context). Where Hermes records usage, it's the "used" hierarchy: the **skill ledger** records actual tool invocations and a deterministic curator consumes them for lifecycle transitions — **build event tables with a named consumer, not as an archive.** Claim-identity is structurally forced: entries addressed by content substring with ambiguous-match rejection; corrections supersede by writing a new claim. `write_approval` staging governs who may auto-write the always-injected core. And the loop-breaker the second-guess doc didn't name: **sanitize in both directions** — recalled context is stripped from outgoing sync (a `StreamingContextScrubber` even handles spans across stream deltas) so retrieval can never re-ingest its own output. (Companion note written to the Haloysius repo.)

### 7. Gateway/channels — upgrades packets 02/04 and the channel thinking

Per-platform session keys with **opt-in cross-channel continuity** (a `/resume` gated by an IDOR-proof: the persisted row must prove platform+thread+chat+user match; legacy NULL rows fail closed). The **turn lease keyed by transcript-owner, not route** (because cross-channel resume makes route→session many-to-one) — the single most valuable invariant if a Halbert session is ever reachable from two surfaces. A durable **delivery-obligation ledger** (pending → attempting → delivered/failed, with differentiated honest "♻️ may be a duplicate" markers per crash state). Two-axis permissions (who may talk vs. who may run which commands — `allow_admin_from` / `user_allowed_commands` with a `{help, whoami}` floor), wire-invisible trust flags excluded from serialization, and identity alias canonicalization shared by authz and session keys so the two never drift. Voice memo discipline upgrades packet-04: STT-eligible vs file-audio classification, transcribe-once cached on the event, echo-back for live verification, interrupt-with-transcript, duplicate suppression. Also: `TeeTransport` gives a second client the TUI's event stream for free — one transport tee, dashboard included.

### 8. Providers/TUI/MCP

- **ProviderProfile**: a dataclass + hooks (not 20 booleans) where every quirk is a documented overridable hook; the **utility slot resolves from the provider's own catalog/profile** (a hardcoded cheap-model ID "rots"), with per-task `prefer_fast` opt-in — the blueprint for Halbert's planned utility slot.
- **Cost accounting**: `estimated_cost_usd` vs `actual_cost_usd` with `cost_status/cost_source/pricing_version`, and per-(session, model, billing-route, task) usage rows — honest provenance for "cost so far," aligned with Halbert's slot model.
- **Display-side redaction**: every UI transport emission goes through one `_verbose_text()` seam — forced redaction + a hard cap (the cap is an OOM defense, not just privacy; a render-tree blowup killed the TUI parent, #34095). A second choke point under Halbert's response redaction.
- **MCP**: as a server, thin (messaging bridge; the approval-respond tool pops an in-memory dict with **no enforcement path** — do not copy); as a client, a PR-reviewed manifest catalog (presence = approval) with dual-gate validation (save time AND spawn time) and post-incident IOC hardening. The EventBridge (mtime-gated SQLite polling → cursor events → long-poll) is cheap and liftable for satellite state.
- **TUI**: the fast-echo bypass rules (never fast-path output that changes other cells; make the unsafe-path precondition a named pure function; fall through, don't swallow) and description-token fuzzy ranking on slash commands.

### 9. Evals — two open Halbert problems get blueprints

- **The R5 gate** (un-gating the Consolidator's LLM pass): the compaction eval is the blueprint — question banks generated from the region-to-be-destroyed, cached by content hash so every arm answers the identical exam; consolidation under a policy matrix; closed-book answering with forced "NOT IN CONTEXT"; a judge that sees gold and scores hedged guesses as partial; a **ceiling control arm** (without it, "45%" has no meaning — the uncompacted ceiling was 96.7% vs the shipped default's 45.8%); committed dated scorecards with methodology caveats; sentinel tripwire tests and synthetic transcripts so the harness itself smoke-tests in CI without LLMs; "harness as the permanent gate."
- **The 38 red seams**: the postmortem probe battery — reviewer-authored defect reproductions as standalone scripts where pass = exit 0 + expected stdout marker, run against base/branch checkouts via a PROBES table. No framework.
- **CRAG gating**: `judge_goal`'s structure — deterministic quality gates short-circuit the LLM judge (a failing gate's bounded output becomes the continuation prompt; no judge is spent), a closed verdict vocabulary (`done/blocked/continue/wait` with structured wait directives), anti-self-congratulation prompt language ("require specific evidence"; DONE "requires the deliverable to actually exist"), and failure-mode separation (parse-failure vs transport-failure circuit breakers; single transport errors fail open to continue).

---

## Anti-patterns to refuse (consolidated)

1. **LLM judgment on security paths without deterministic guards** — Hermes's own incident history is the argument; start with the guards.
2. **Env-var allowlists / first-writer-wins config bridges** as a security source of truth (three multiplex-profile credential leaks, each patched) — keep identity/permissions in one typed store.
3. **Approval-shaped wire tools with no enforcement path.**
4. **Inline shell expansion during prompt/skill preprocessing** (prompt-to-RCE).
5. **Hand-edited-JSON stores** whose due-scans become eternal repair passes; and **invariant docs written by hand** (Hermes's own cron AGENTS.md contradicts its code — generate invariants from tests or they lie).
6. **In-process subagent isolation** for anything security-relevant (a compromised child prompt lives in the process holding the PTYs).
7. **Schema-as-side-effect** (tool methods whose docstrings are the wire schema — a reword is a wire change invisible in diffs).
8. **Mixin/globals decomposition at Hermes's scale** (16 mixins, methods rebound onto a 3.2k-line server's globals) — organizational debt from monolith growth; the module count is at the ceiling even where justified.
9. **Cache-parity agent forks** as the implementation shape for background work — the *idea* (post-turn, off-path learning) is right; the fork-with-suppressed-flags implementation is where their incidents lived. Design background passes as first-class queued jobs with explicit isolation.

---

## Top 10 lifts, overall

1. **Zero-context-cost script execution** (generated stub module + host-side RPC enforcement + stdout-only capped return) — new capability, high value for the terminal direction.
2. **The interrupt algebra** (stop/steer/redirect + generation claims + yield-not-kill) — the control surface for every Halbert channel.
3. **Atomic compression rotation + watermark + lineage-rooted leases** — the session-tree deep pass, pre-solved by incidents.
4. **The R5 eval-harness blueprint** (question-bank invariance, ceiling arm, judge-sees-gold) + **the probe battery** for the red seams.
5. **Cron durability set** (cadence-scaled grace, dispatch-time persistence, occurrence idempotency, monitor-hash gate, closed status taxonomy) — upgrades packet-03.
6. **The learning-loop skeleton** (deterministic nudge counters, post-delivery review with dispatch whitelist, anti-hoarding policy text, read-before-write, archive-not-delete) — for the skills deep pass.
7. **Conversation-store hardening** (darwin fsync PRAGMAs, FTS fail-open, declarative column reconciliation, repair-on-copy with attempt ledger) — small, cheap, permanent.
8. **No-retrieval-strengthening memory discipline + sanitize-both-directions + write-approval staging** — inputs to the Haloysius decision, already delivered as a companion note.
9. **Two-axis channel permissions + IDOR-proof cross-channel resume + the delivery-obligation ledger** — upgrades to packets 02/04 and the channel design.
10. **ProviderProfile + catalog-derived utility slot + honest cost accounting** — for the model-picker deep pass.

---

## Follow-ups this review drives (recorded for the master plan)

- PACKET-03 gets the Hermes cron set as an addendum (cadence grace, occurrence receipts, monitor hash, status enum).
- PACKET-04 gets the voice-memo discipline (transcribe-once, echo-back, interrupt-with-transcript) and the interrupt algebra's voice rule.
- PACKET-05 gets the display-side redact+cap seam as an addendum.
- New packets justified: zero-context script execution; the interrupt algebra; conversation-store hardening; the R5 harness + probe battery.
- Deep-pass agenda updates: the session-tree entry now points at Hermes's rotation machinery as the reference implementation; the skills entry inherits the learning-loop skeleton and the CC-compatible format's enforcement details; the model-picker entry inherits ProviderProfile and the utility-slot ladder.
- Cross-repo: Hermes memory inputs delivered to the Haloysius second-guess decision doc (see the companion note in `/Volumes/4TB-BAD/Haloysius/.handoff/`).