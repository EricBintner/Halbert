# HANDOFF — OSS Pass-2 Implementation Plan Review

**Status:** ACTIVE
**To:** Next agent (fable/k3 tier or equivalent)
**From:** Previous session (planning pass, 2026-09-11)
**Repo:** `/Volumes/4TB-BAD/Halbert`
**Branch:** `main` (planning only — no code changes were made by the prior session)

---

## 0. What this handoff asks of you

You are receiving a body of planning work for the Halbert project. The prior session produced a formal implementation plan for the "OSS pass-2 discovery backlog" — a set of ~87 work units derived from a critical review of four open-source AI agent codebases (Hermes, Open-Claude-Code, OpenClaw, Warp) filtered against Halbert's actual architecture, standing directives, and product fit.

Your job has three parts:

1. **Review** the formal implementation plan critically. Find what's wrong, what's missing, what's over-scoped, what's under-scoped, what's sequenced badly, what violates a standing directive, what duplicates an existing mechanism, and what wouldn't actually improve the user's experience.

2. **Write a verbose implementation plan** that corrects the issues you find. This plan should be detailed enough that another engineer (or agent) can dispatch each unit without re-deriving the context. For each unit: what to build, which files to touch, what the test looks like, what the acceptance criteria are, what NOT to build, and how it verifies against measured state.

3. **Return a handoff** to the next session describing what you reviewed, what you changed, what you rejected, and what the next agent should do.

This is a planning and documentation task. Do not modify product code. You may create or edit files under `.handoff/oss-pass-2/`.

---

## 1. What Halbert is

Halbert is a macOS-resident AI steward — a daemon that lives on your machine, speaks as the computer itself in first person, watches your terminals, manages scheduled work, and maintains a continuous conversation across sessions. It is not a chatbot. It is not a cloud agent. It is the machine talking to you about itself.

The product has three layers:

- **`halbert_core/`** — the Python backend (FastAPI + the agent state machine, model client, scheduler, memory, tools, MCP server, voice pipeline, terminal bridge).
- **`halbert_core/halbert_core/dashboard/`** — the React/Tauri desktop app (the primary user surface).
- **`crates/`** — Rust crates (halbert-ffi, halbert-mqtt, halbert-sandbox, halbert-snapshots, halbert-telemetry). The full Rust rebuild is **deferred**; current features get finished first.

The two independently consumable libraries are `packages/model-picker` and `packages/design-system`.

---

## 2. Standing directives (read before any user-facing change)

These live in `DECISIONS.md` → "Standing directives". They are non-negotiable. The plan you are reviewing must respect every one.

1. **The LLM identifies as the computer itself, first person, grounded in measured data; never an assistant.** Error messages, recovery notices, doctor findings — all speak as the machine. Never "I apologize, an error occurred." Always "My local inference server on port 11434 stopped responding mid-generation. I preserved your conversation state and restarted the connection."

2. **Never name or recommend an AI model on any user-facing surface.** Connection slots, not model menus. The locality check (`is_local_model()`) is the only judge of local vs cloud; the `:cloud` tag is primary evidence, a loopback URL is not sufficient.

3. **Never write "Sovereign" on a user-facing surface.** The engaged surface carries the onboarding name, never the raw hostname.

4. **One seamless conversation with hidden topic threads; no conversation list.** Commands from the UI are staged, never executed.

5. **User shells stay but are watched by the AI; the agent reuses idle terminals; subtle indicator-light notifications.**

6. **Tier 2 (secrets) is answered by a deterministic template, never a model.** Scrub before the model. Never ask a model to summarize secrets out of a payload.

7. **Colours only from `shared-tokens/tokens.css`; no hardcoded colours; no emoji in UI.**

8. **No users yet — do not build migrations or back-compat shims unasked.** Leave superseded data on disk, unread. Never delete it.

9. **Full Rust rebuild deferred; Linux OS far future; current features completed and tested first.**

10. **Never `Co-Authored-By` or generation trailers in commits.**

---

## 3. Invariants — one place each thing is decided

Each of these has exactly one choke point. The plan must route new code through these, not add a second check.

- **Model locality** — `is_local_model()` in `halbert_core/halbert_core/model/llm_config.py:181`.
- **Feature gating** — `has_capability()` in `halbert_core/halbert_core/capabilities.py:499`. Capabilities are presence probes. Do not gate on a variant flag.
- **Colour** — `shared-tokens/tokens.css`. Never hardcode. Run `scripts/check_contrast.py`.
- **Redaction** — `ingestion/redaction_registry.py`, enforced at `security/display_transport.py`. Scrub deterministically before the model.
- **Licence notices** — `model/attribution.py` derives them from runtime licence text.

---

## 4. Test discipline (critical — get this wrong and you waste hours)

Every Python test run needs the `arch -arm64` prefix:

```bash
# Main tree
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# Worktree (never bare pytest — the editable install pins imports to the main tree)
arch -arm64 ./wt_pytest.py halbert_core/tests
```

The venv's `python3` is a universal2 binary. Unprefixed, it launches the x86_64 slice and the first compiled extension dies with `ImportError: … incompatible architecture`. This reads as a broken dependency and is not one. Don't diagnose it with `platform.machine()` either — a direct `python -c` check can print `arm64` in the same shell where `python -m pytest` launches x86_64.

`main` is **not green**. A known nonzero baseline of failures exists. Get a baseline run on your merge-base before concluding any change caused anything.

Frontend: root `npm test` and `npm run typecheck` fan out across workspaces.

---

## 5. Remediation status (verified during the prior session)

The OSS pass-2 work has two remediation batches:

| Batch | Packets | Merged to `main`? | Commit |
|---|---|---|---|
| Opus | R-01, R-02, R-04, R-05, R-06, R-07, R-08, R-09, R-10, R-11, R-12 Phases B/C, R-14 | **Yes** | `55ecef87` |
| Sonnet | R-03, R-13, R-15, R-12 Phase A | **No** — branch `fix/remediation-sonnet-batch-1` (head `068d1f05`) | — |

**This matters:** several packets in the plan were told "R-03/R-13/R-15 already covers this." That's only true after the sonnet branch merges. The plan's Milestone 5a handles verification. Do not assume the sonnet batch is merged — verify with `git log --oneline main | grep -i sonnet` or `git branch --merged main | grep sonnet` before claiming overlap.

---

## 6. The planning spine

`ROADMAP.md` and `DECISIONS.md` are the only planning spine. `.handoff/` documents are session correspondence and research artifacts — useful history, zero authority. The plan you are reviewing lives in `.handoff/oss-pass-2/` and is correspondence, not a decision. If any part of the plan conflicts with `ROADMAP.md` or `DECISIONS.md`, the plan is wrong.

---

## 7. Files you need to read

Read these in order. They are the complete context for the plan you are reviewing.

### The plan itself (start here)

| File | Lines | What it is |
|---|---|---|
| `.handoff/oss-pass-2/FORMAL-IMPLEMENTATION-PLAN-2026-09-11.md` | ~460 | **The formal plan you are reviewing.** Six milestones, 87 units, dependency graph, tactical directives. |
| `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-2026-09-11.md` | ~1080 | The predecessor plan (Parts A–F). Parts E–F contain the UX scrutiny reasoning that informed the milestone groupings. Superseded by the formal plan but still useful for reasoning context. |
| `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-REVIEW-AND-REINVENTIONS-2026-09-11.md` | ~380 | An external review of the predecessor plan. Three valid corrections (MP-5 dropped, activity_clock missing, Phase 3 logjam) were adopted. Five oversteps were pushed back on. The formal plan's §1 documents what was accepted and rejected. |

### The source verdicts (read the formal plan first, then these for detail)

| File | Lines | What it is |
|---|---|---|
| `.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md` | ~660 | The authoritative per-packet verdicts (ACCEPT / RESHAPE / DEFER / REJECT) with reasoning. |
| `.handoff/oss-pass-2/deep-eval-group1-memory-conversation-permissions.md` | ~420 | Deep evaluation of MEM-P1–P6, CSC-01–CSC-06, P1–P6. |
| `.handoff/oss-pass-2/deep-eval-group2-scheduler-terminal-voice.md` | ~435 | Deep evaluation of SCHED-P1–P6, TT-01–TT-06, VMV-1–VMV-6. |
| `.handoff/oss-pass-2/deep-eval-group3-skills-mcp-models.md` | ~490 | Deep evaluation of SP-1–SP-6, MCP-A/B/C, CH-A, GW-A, CMD-A, MP-1–MP-6. |
| `.handoff/oss-pass-2/deep-eval-group4-dashboard-testing-other.md` | ~610 | Deep evaluation of DIAG-01/02, DAEMON-01, LOG-01, BIND-01, SURFACE-01, TERM-02, DIST-02, T1–T6, OTHER-P1–P6, F01–F20. |

### The discovery source (read only if you need to trace a packet to its origin)

| File | What it is |
|---|---|
| `.handoff/oss-pass-2/discovery_digest.md` | The raw discovery digest from the OSS pass-2 reverse-engineering pass. |
| `.handoff/oss-pass-2/section_*.md` (12 files) | Per-workstream discovery sections (memory, conversation, permissions, scheduler, terminal, voice, skills, mcp, models, dashboard, testing, other). |

### The project spine (read before any recommendation that touches product direction)

| File | What it is |
|---|---|
| `ROADMAP.md` | The only now/next/deferred document. |
| `DECISIONS.md` | Standing directives + decided items + implemented-per-default items. |
| `AGENTS.md` | How to work in this repo (test commands, invariants, build targets, environment standards). |

---

## 8. The formal plan's structure (what you are reviewing)

The plan has six milestones:

| Milestone | Theme | Units | Key constraint |
|---|---|---|---|
| M0 | Substrate integrity & shared primitives | 9 | T1 (hermetic tests) first; everything else file-disjoint |
| M1 | Model pipeline & conversational resilience | 6 | SP-3 + MP-5 fix data loss; DAEMON-01b merges last (hot file) |
| M2 | Watched terminal & sovereign command engine | 11 | CSC-06 + GW-A coordinate (same PTY replay ring) |
| M3 | Memory trust, turn provenance & diagnostic core | 16 | DIAG-01 is the universal diagnostic sink |
| M4 | Grounded UI, voice & ambient stewarding | 15 | SCHED-P5 core lifecycle is founder-independent |
| M5 | Upstream harmonization & founder gates | 30 | 5a: verify sonnet batch; 5b: founder-gated work |

Total: 87 units (including shared primitives and split packets).

The plan's design principles:
1. Primitives before consumers (no duplicate implementations).
2. Live defects first (cheapest, highest-value).
3. One merge per seam (packets touching the same file merge into one dispatch unit).
4. Verification-before-done (check measured OS state, not model judgment).
5. Milestones are dispatch themes, not serialization barriers.
6. Standing directives hold.

---

## 9. What to look for in your review

### Correctness

- Does any unit violate a standing directive? (Check §2 above.)
- Does any unit add a second implementation of an invariant? (Check §3 above.)
- Does any unit claim R-03/R-13/R-15 overlap without the sonnet batch being merged? (Check §5 above.)
- Does any unit duplicate a primitive that another unit is supposed to build? (The plan consolidates: LOG-01+OTHER-P2, durable_write, subprocess_env, text_hygiene, activity_clock, process_group, DIAG-01. Verify no unit builds its own.)
- Are the file paths in the plan accurate? Spot-check against the actual tree.

### Sequencing

- Are dependencies correctly stated? (A unit listed as "depends on X" — does X actually need to land first?)
- Are the "merge last" notes correct? (DAEMON-01b and TT-05 both touch `state_machine.py` — the hottest file. Are there other hot-file collisions the plan misses?)
- Is the "milestones are themes, not barriers" principle applied correctly? (SP-3 and SP-4a are one-line fixes that should land immediately, not wait for M0. Are there other units that should escape their milestone?)

### Scope

- Is any unit over-scoped? (Does it build infrastructure for a consumer that doesn't exist?)
- Is any unit under-scoped? (Does it fix half a bug and leave the other half?)
- Are the "what NOT to build" exclusions correct? (The plan defers SP-5/SP-6, CMD-A, TT-06 full architecture, DIST-02, and various tails. Verify these deferrals are correct.)
- Does any unit introduce unnecessary UI complexity or a new conceptual burden?

### UX value

- Does each unit solve a user-visible pain, or does it merely mirror an OSS mechanism?
- Does it improve trust, recoverability, clarity, latency, or successful task completion?
- Does it reduce confusing failure modes?
- Can the UX outcome be verified with deterministic tests or UI assertions?

### Missing work

- Is anything in the final critical report (FINAL-CRITICAL-DISCOVERY-BACKLOG) absent from the plan? The formal plan claims 87 units accounting for every packet. Verify the count.
- Are there cross-cutting opportunities the plan misses? (The plan identifies: LOG-01+OTHER-P2, support bundle, durable-write helper, subprocess env, one sanitizer, one circuit breaker, one doctor registry, terminal replay, shared process-group, shared deadline. Are there others?)

### Architecture fit

- Does the plan respect "one seamless conversation, no conversation list"?
- Does it respect "commands staged, never executed"?
- Does it respect "user shells stay, watched by the AI"?
- Does it respect "no model names on surfaces"?
- Does it respect "no emoji, shared tokens"?
- Does it respect "local-first, Tier 2 by template"?
- Does it respect "no migrations, no back-compat shims"?

---

## 10. What the verbose implementation plan should contain

For each unit in your corrected plan:

1. **Packet ID and name** — the discovery packet it came from.
2. **User problem** — one or two sentences on what the person experiences today that is wrong.
3. **What to build** — the concrete scope, narrowed to the minimum viable slice.
4. **What NOT to build** — explicit exclusions (tails deferred, infrastructure not needed yet).
5. **Target files** — specific paths, with line references where known.
6. **Dependencies** — what must land first (primitives, other packets, remediation verification).
7. **Effort** — S / S-M / M / L, with a one-line justification.
8. **UX rationale** — why this improves what the person experiences.
9. **Acceptance criteria** — what "done" means, in measurable terms.
10. **Verification** — the specific test or assertion that proves it works. Verification checks measured state, not model judgment.
11. **Exclusions** — what is explicitly NOT in this unit, and where it goes instead.

The plan should also include:

- A dependency graph (which units block which).
- A "merge last" list (which units touch hot files and must sequence after others).
- A "land immediately" list (one-line fixes with no dependencies).
- A cross-cutting primitives table (what is built once and consumed by multiple units).
- A packet accounting table (every packet from the final report, accounted for).

---

## 11. Known issues in the formal plan (things to verify, not necessarily fix)

These are the prior session's own notes on potential weaknesses:

1. **The packet count (87) may not be exactly right.** The formal plan claims every packet is accounted for. The count includes shared primitives and split packets (e.g., SURFACE-01a/b, DAEMON-01a/b, BIND-01a/b, OTHER-P6a/b, SCHED-P5 core/tail). Verify by counting against the final report.

2. **Some file paths are inferred, not verified.** The plan cites paths like `streaming/session_manager.py`, `tools/terminal_tools.py`, `tools/command_norm.py`, `dashboard/event_replay.py`, `utils/activity_clock.py`, `utils/sqlite_safety.py` — some of these may not exist yet (they're proposed new files) and some may be named differently than the plan assumes. Spot-check against the actual tree.

3. **The "merge last" list may be incomplete.** The plan flags DAEMON-01b and TT-05 as touching `state_machine.py`. But SP-3, TT-05, DAEMON-01b, CSC-01, CSC-02, and SCHED-P4 all touch the state machine. The plan may need a more complete hot-file collision map.

4. **The activity_clock contract is minimal.** The plan gives `record_activity()`, `idle_seconds()`, `is_stalled()`. The review's version added `source: str` parameter and a configurable `idle_timeout`. Verify the contract is sufficient for all four consumers (MP-3, SCHED-P2, SCHED-P4, DAEMON-01b).

5. **MP-5's scope may overlap TT-05.** Both fix malformed tool calls. MP-5 is the deterministic extractor (parse repair); TT-05 is the loop guardrail (3-strike budget, per-run ceiling). Verify the boundary is clean — MP-5 repairs, TT-05 bounds.

6. **The sonnet batch may have merged since the prior session verified.** Re-check with `git branch --merged main | grep sonnet` before relying on the "not merged" claim.

7. **The plan does not address the `routes/settings.py` hub file.** This file is 3,200+ lines and heavily edited by concurrent sessions. BIND-01a and OTHER-P6b both touch it. The plan should note the rebase risk.

8. **The plan's effort estimates are rough.** They are S / S-M / M / L without hour counts. This is intentional (the prior session was told not to give timelines), but the verbose plan should at least justify each estimate.

---

## 12. Constraints on your work

- **Do not modify product code.** This is a planning task. You may create or edit files under `.handoff/oss-pass-2/`.
- **Do not create Paperclip issues or dispatch work.** The prior session was explicitly told not to. You should not either unless the user asks.
- **Do not claim R-03/R-13/R-15 are merged without verifying.** Re-check the git state.
- **Do not reproduce entire source files.** Keep code excerpts short. Reference paths and symbols.
- **Do not add commit trailers** (`Co-Authored-By`, `Generated with Devin`, etc.).
- **Do not use emojis** in any output or file.
- **Respect the standing directives** in every recommendation you make.
- **Treat `.handoff/` as correspondence, not authority.** `ROADMAP.md` and `DECISIONS.md` are the spine.

---

## 13. What to deliver

1. **A review document** at `.handoff/oss-pass-2/REVIEW-FORMAL-PLAN-2026-09-11.md` containing:
   - Your assessment of the formal plan's strengths and weaknesses.
   - Specific issues found (correctness, sequencing, scope, UX, missing work, architecture fit).
   - What you accepted, what you rejected, and why.

2. **A verbose implementation plan** at `.handoff/oss-pass-2/VERBOSE-IMPLEMENTATION-PLAN-2026-09-11.md` containing:
   - The corrected milestone structure (if you changed it).
   - Every unit with the 11 fields from §10 above.
   - The dependency graph, merge-last list, land-immediately list, cross-cutting primitives table, and packet accounting table.

3. **A return handoff** at `.handoff/oss-pass-2/HANDOFF-FROM-REVIEW-2026-09-11.md` containing:
   - What you reviewed.
   - What you changed and why.
   - What you rejected and why.
   - What the next agent should do.
   - Any open questions for the founder.

---

## 14. Quick reference — the formal plan's milestone summary

| Milestone | Units (count) | Key units |
|---|---|---|
| M0 — Substrate | T1, DAEMON-01a, durable_write, process_group, activity_clock, text_hygiene, subprocess_env, OTHER-P4, DIAG-02 (9) | T1 first (hermetic tests) |
| M1 — Model pipeline | SP-3, MP-5, MP-2, MP-3, MP-4, DAEMON-01b (6) | SP-3 + MP-5 fix data loss; DAEMON-01b merges last |
| M2 — Terminal & command | CSC-06, GW-A, TT-01, TT-03, TT-04a, P2, TERM-02, BIND-01a, SP-4a, SP-2, TT-05 (11) | CSC-06 + GW-A coordinate |
| M3 — Memory & diagnostics | CH-A, MEM-P1, MEM-P2, MEM-P3, MEM-P6, DIAG-01, LOG-01+OTHER-P2, CSC-01, CSC-02, CSC-04, P1, P4, P6, OTHER-P1, OTHER-P3, OTHER-P5 (16) | DIAG-01 is the universal sink |
| M4 — UI, voice, scheduler | SURFACE-01a, SURFACE-01b, SCHED-P6, SCHED-P2, SCHED-P4, SCHED-P5, OTHER-P6a, OTHER-P6b, VMV-1, VMV-3, VMV-5, VMV-6, T2, T4, MP-6 (15) | SCHED-P5 core is founder-independent |
| M5 — Verification & gates | 5a: MP-1, SCHED-P1, SCHED-P3, T5, CSC-03, MCP-A/B/C, SP-1, VMV-2, VMV-4, TT-02 (12 verify); 5b: MEM-P5, SP-5, SP-6, CMD-A, DIST-02, TT-06 + tails (18 gated) (30) | 5a verifies sonnet batch; 5b waits on founder |

---

## 15. SourcePrep

The project uses SourcePrep for structural codebase intelligence. If you need to understand how files connect, module structure, or what depends on what:

- `prep` — orientation (module map, hub files, focus areas).
- `prep_search` — semantic code lookup with dependency expansion.
- `prep_impact` — before editing, check what depends on a file.
- `prep_audit` — structural findings (coupling, cycles, concept violations).

All SourcePrep tools are read-only and safe to auto-approve. If `prep` returns "setup in progress," the index hasn't been built yet — work normally with read/grep tools.

---

Good luck. The plan is the product of several sessions of deep evaluation, but it is not sacred. If you find something wrong, fix it. If you find something missing, add it. If you find something that shouldn't be there, cut it. The goal is a plan that another engineer can dispatch without re-deriving the context — and that respects Halbert's architecture, standing directives, and actual product surfaces.
