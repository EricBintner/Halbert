# Master TODO & AI Review/Handoff Index

> **2026-09-02:** this file is now the handoff INDEX only. Now/next/deferred live in `ROADMAP.md`; decisions in `DECISIONS.md`. §0 and §3 below are stale (U1–U6 are merged; the review remediation backlog is tracked per ROADMAP row) and will be reduced to pointers by the SONNET-05 doc pass.

> **2026-09-02 (SONNET-05 doc pass, done).** §0 and §3 resynced against reality below — struck rows reflect what actually landed, sourced from `.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` and `.handoff/RESULTS-SONNET-01/02/03/04-2026-09-02.md`, not from re-running the original audit. A new **§2a Review remediation backlog** gives the finding-id-level detail (`R04-F1`, `R06-F2`, …) the higher-level `ROADMAP.md` §3 rows don't carry — treat it as the historical evidence trail, `ROADMAP.md` as the current now/next/deferred source of truth per the 2026-09-02 planning-spine decision (`DECISIONS.md`). Founder-gated items are pointers to `.handoff/DISPATCH-2026-09-01-FOUNDER-DECISIONS.md` only, not duplicated here.

**Living task list & AI review directory.** Items move here from session handoffs so nothing gets
lost between sessions. Strike through and date when done.

**Updated:** 2026-09-14 (§4 resync: uncommitted work, unmerged branches, ROADMAP §3/SECURITY-TODO open rows, DECISIONS queue, designed-but-unstarted handoffs — see §4; earlier sections resynced 2026-09-02 by SONNET-05)
**Master Review Portfolio:** 11 Comprehensive Review Packets (`.handoff/REVIEW-PACKET-*.md`) — remediation status: §2a below
**Active Incomplete Task Packets:** 10 Actionable Implementation Packets (`.handoff/TASK-PACKET-*.md`) — superseded by the 2026-09-01 dispatch packets (OPUS-01..05, SONNET-01..05); kept as an index of the original handoff docs, not as open work

> **2026-08-30 Reassessment (GLM-5.3).** All packets were previously tiered "Fable" (one "Opus").
> After verifying actual code state, no remaining packet requires Fable. All implementation work is
> well-specified, line-targeted, and within reach of **GLM-5.3**; related packets have been regrouped
> into **Ultracode Batch U1–U5** below so each batch runs as a single workflow. Fable/Opus are reserved
> only as optional second-opinion passes on the two security reviews (REV-01/REV-02) and founder legal
> sign-off (REV-07/TASK-06). Status column reflects what verification found — several packets were
> already partially or fully executed. **Superseded 2026-09-02**: this reassessment predates the
> 2026-09-01 audit and its OPUS-01..05/SONNET-01..05 dispatch, which is what actually executed the
> remaining work — see §0 below for the batch-to-dispatch mapping.

---

## 0. Ultracode Execution Batches (Regrouped 2026-08-30) — ~~all six merged~~ (2026-09-02)

All U1–U6 batches below landed on `main` (verified against `.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` and `RESULTS-SONNET-01/02/03/04-2026-09-02.md`, not by re-running the original packets — those RESULTS docs are the evidence). Residual, still-open items each batch left behind now live in **§2a Review remediation backlog** below (finding-id granularity) or as founder-gated rows in `DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`, not in this table.

| Batch | Scope (packets folded in) | Landed | What's still open |
|---|---|---|---|
| ~~**U1 — Security & Trust Boundary**~~ | TASK-09, TASK-03 Task 3.2, REV-01 + REV-02 | `feat/security-review-01` merged (`909b56c4`, SONNET-01); `R1-F4` autonomy-level race, `R2-P3` id-less `tools/call`, `R2-P4` unbounded stdio reads, `R2-P5` case-sensitive Bearer all fixed same session | `SEC-04` real unredacted rebuild deferred (daemon reported wedged, SONNET-01 §Task 4); `R2-P1/P2` (federation/peers_config.py, OPUS-03's file, not touched); `R2-F2b` no socket timeout, not attempted; `NEW-01` `_egress_ack` provenance, documented not fixed; `SEC-14` daemon `/projects` no bearer, CoDRAG's to fix |
| ~~**U2 — Voice / Auditory Cortex**~~ | TASK-07, REV-09 + REV-03 | All four TASK-07 fixes + the P0/P1 auditory-cortex chain landed via OPUS-02 (`65ff3e83`, `409fc509`, `9ec19f8a`, `8e18a93c`) — Wyoming auth+loopback default, VAD frame size, voiceprint loading, `VM-STT` spoken input now becomes a turn, `<speech>` defanging | `R9-F06/F07/F08/F11/F13`, `U2-09` modality-context XML — below the P0/P1 line, chain works without them; **0/22 real-audio hardware runs**, unchanged (`VM-27`/`VM-15`/`HW-01`, founder queue) |
| ~~**U3 — Frontend (Settings, Nav, Chat UI)**~~ | TASK-02, TASK-08, REV-08 + REV-11 | Settings decomposed to ~880 lines / 12 lazy-mounted tabs (SONNET-04); nav re-railed (System/Workloads, pre-dated this packet) + approvals badge added; `pages/Security.tsx`→`Findings.tsx` renamed; all of OPUS-05's chat-streaming fixes (`R11-01/02/03/04/05/06/09/10/12/13`) | `R11-07` focus bug (lives in OPUS-03's `DevicesTab.tsx`); `R11-08` HostShell landmark (moved under the shell redesign, nobody's touched it); `R11-10`'s abort half needs a one-line follow-up in `api.ts` (not this packet's file) |
| ~~**U4 — Model Routing & Agent Tooling**~~ | TASK-01, TASK-04, TASK-05, TASK-10, REV-05 + REV-06 | `HALBERT_MODEL` override done (fails open on resolution error, SONNET-03 Task 8); circular secure-model gate fixed (`CAP_SECURE_MODEL_ALLOWED`, SONNET-03 Task 2); Apple Intelligence bridge-running gate (Task 4); API keys redacted from `/llm/config` (Task 6); `cascade_router.py` deleted, PICK-02/03 fixed (Task 7); all of OPUS-01's agent-core fixes (`R06-F1..F8`, `O1/O2`) | `R05-F4/F5/F6/F8` (`model/client.py` — images not translated per-provider, GPU lock, `stream=True` `.json()` bug, `is_model_loaded` prefix false positives — flagged, not this session's file); `U4-20` Swift bridge — hidden until built, per founder default |
| ~~**U5 — Founder Decisions**~~ | TASK-06, REV-07 | Drafts exist (`APP-STORE-DISTRIBUTION-STRATEGY.md`, licence gate automated and green as of this packet) | Still human-gated — see `.handoff/DISPATCH-2026-09-01-FOUNDER-DECISIONS.md` §A for the ratification list; nothing here duplicates that sheet |
| ~~**U6 — Home Automation Simplification (S1-S7)**~~ | `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` §12 (W1-W25) | Fully merged (`4e4ff2f4`, `93c863c1`, D4 `8545af94`); `U6-BUG-01` (registry ignores `HALBERT_VARIANT`) and `U6-BUG-02` (circular secure-model gate) both fixed by SONNET-03; `U6-28` retired `home-light` string check fixed | D2/D4/Q3/Q4 still await ratification (implemented-per-default, see `DECISIONS.md`); Frigate queue cap (`U6-BUG-03`) and snapshot→vision routing (`U6-BUG-04`) not started |

**Errata from the original packets** — kept for history only, all superseded by what actually shipped (above):
1. TASK-05 Task 5.1 (obsolete — field removed, done). 2. TASK-08's `ChatPanel.tsx` reference (file never existed; the real files are `useAgentStream.ts`/`AgentChat.tsx`, both since rewritten by OPUS-05). 3. TASK-09/TASK-10 merges (done, `297ceb67`/`11ded488` — both further superseded by the 2026-09-01 security-review-01 merge and this session's work). 4. TASK-03 Task 3.1 (done). 5. TASK-06's wrong `tauri.conf.json` path. 6. TASK-01 Task 1.4's false premise. 7. Missing verification test paths — all now exist.

---

## 1. Master Review Packets (Code Reviews — reassigned 2026-08-30)

**Table below is an index of the original handoff docs, not open work — see §2a for what each review's findings actually resolved to (done/open, by finding id) as of 2026-09-02.**

Each packet provides a complete audit of plans (past 2 weeks), git commits (past week), key files, security boundaries, and specific review directives.
GLM-5.3 did not author this code, so it is a reasonably independent reviewer. Security-critical packets get an adversarial verify pass; founder legal items stay human-gated.

| ID | Scope & Domain | Review Tier | Batch | Hand-off Document Link |
|---|---|---|---|---|
| **REV-01** | **Security Architecture, Trust Boundaries & Sensitivity Classification** | **GLM-5.3 high + adversarial verify** (optional Fable second opinion) | U1 | [`REVIEW-PACKET-01-SECURITY-AND-TRUST-BOUNDARY.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-01-SECURITY-AND-TRUST-BOUNDARY.md) |
| **REV-02** | **Halbert MCP Server & Client Boundary Architecture** | **GLM-5.3 high + adversarial verify** (optional Fable second opinion) | U1 | [`REVIEW-PACKET-02-MCP-SERVER-AND-BOUNDARY.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-02-MCP-SERVER-AND-BOUNDARY.md) |
| **REV-03** | **Sentient Home Architecture (Home Assistant, Wyoming, Frigate CV)** | **GLM-5.3 medium** | U2 | [`REVIEW-PACKET-03-SENTIENT-HOME-AND-VOICE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-03-SENTIENT-HOME-AND-VOICE.md) |
| **REV-04** | **Sovereign Host Vision & Continuous Terminal / Somatic Nervous System** | **GLM-5.3 high** (architectural judgment, not mechanical) | standalone | [`REVIEW-PACKET-04-SOVEREIGN-HOST-AND-TERMINALS.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-04-SOVEREIGN-HOST-AND-TERMINALS.md) |
| **REV-05** | **Unified LLM Router, GPU Locking & Apple Intelligence On-Device** | **GLM-5.3 medium** | U4 | [`REVIEW-PACKET-05-UNIFIED-LLM-ROUTER-AND-GPU.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-05-UNIFIED-LLM-ROUTER-AND-GPU.md) |
| **REV-06** | **Core Agent Evolution, Intake Pipeline, Reactive Slices & SourcePrep RAG** | **GLM-5.3 medium** | U4 | [`REVIEW-PACKET-06-AGENT-CORE-RAG-AND-REACTIVE-SLICES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-06-AGENT-CORE-RAG-AND-REACTIVE-SLICES.md) |
| **REV-07** | **Product Strategy, Legal/Licensing & Mac App Store Distribution** | **GLM-5.3 high (drafts) + founder sign-off** | U5 | [`REVIEW-PACKET-07-LEGAL-OPEN-CORE-AND-DISTRIBUTION.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-07-LEGAL-OPEN-CORE-AND-DISTRIBUTION.md) |
| **REV-08** | **UI/UX Redesign, Settings Decomposition & Design System Consolidation** | **GLM-5.3 medium** | U3 | [`REVIEW-PACKET-08-UI-REDESIGN-AND-SETTINGS-DECOMPOSITION.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-08-UI-REDESIGN-AND-SETTINGS-DECOMPOSITION.md) |
| **REV-09** | **Auditory Cortex & Multimodal Audio AI Pipeline** | **GLM-5.3 medium** | U2 | [`REVIEW-PACKET-09-AUDITORY-CORTEX-AND-AUDIO-PIPELINE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-09-AUDITORY-CORTEX-AND-AUDIO-PIPELINE.md) |
| **REV-10** | **Federated Fleet & Multi-Persona System Architecture** | **GLM-5.3 medium** | standalone | [`REVIEW-PACKET-10-FEDERATED-FLEET-AND-MULTI-PERSONA.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-10-FEDERATED-FLEET-AND-MULTI-PERSONA.md) |
| **REV-11** | **Chat UI Performance, Streaming State & Accessibility Audit** | **GLM-5.3 medium** | U3 | [`REVIEW-PACKET-11-CHAT-UI-PERFORMANCE-AND-ACCESSIBILITY.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-PACKET-11-CHAT-UI-PERFORMANCE-AND-ACCESSIBILITY.md) |

> **2026-08-30 simplification addendum:** REV-03, REV-05, REV-06, and REV-10 must also be reviewed against [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md):
> - **REV-03** — home/home-light have no `secure_model` (unconfigured + hidden), no SourcePrep retrieval backend, no model picker (Compute Peer setting instead); persona memory embeddings are NOT SourcePrep and stay local.
> - **REV-05** — Apple Intelligence is local-only (never a peer backend); no 1B tier; `SBC_LOW_POWER` recommends offload-only; `secure_model` is sysadmin-only.
> - **REV-06** — SourcePrep scoped RAG is workstation/sysadmin-only; HA variants must not instantiate the retrieval backend or configure `SOURCEPREP_URL`.
> - **REV-10** — the HA node is a pure compute client (peer -> template thoughts fallback; no local models/SourcePrep/secure_model/picker); `compute_backends` advertises `ollama`/`vllm` only; S1-S7 land before federated Phase 9.

---

## 2. Incomplete Work Task Packets (Actionable Implementation Handoffs — reassigned 2026-08-30)

**Superseded 2026-09-02**: every row below either landed via the 2026-08-30 Ultracode batches (§0, now struck) or via the 2026-09-01 dispatch packets (§2a). Kept as an index of the original handoff docs.

Each task packet contains step-by-step instructions, file lists, line-number targets, design constraints, and automated verification commands.
Status reflects code verification on 2026-08-30 — several packets were already partially executed.

| ID | Task Domain & Scope | Model / Effort | Batch | Status | Hand-off Implementation Document |
|---|---|---|---|---|---|
| **TASK-01** | **Sentient Home Bugfix & Phase 8 Light Variant** | **GLM-5.3 medium** | U4 | **Mostly done** — Tasks 1.1–1.3 already shipped; only `HALBERT_MODEL` env override remains; Task 1.4 premise false | [`TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md) |
| **TASK-02** | **Settings Megafile Decomposition & Navigation Consolidation** | **GLM-5.3 medium** | U3 | **Open** — Settings.tsx now 3,283 lines | [`TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md) |
| **TASK-03** | **Security CLI Tools Migration & Operational Index Rebuild** | **GLM-5.3 medium** | U1 | **Task 3.1 done**; Task 3.2 (rebuild script) open | [`TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md) |
| **TASK-04** | **GPU Deep-Scan Refactor & Agent Specialist Tooling** | **GLM-5.3 medium** | U4 | **Open** — raw Ollama call still in `routes/gpu.py:693` | [`TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md) |
| **TASK-05** | **Role-Scoped Config Harvesting** (context plumbing dropped) | **GLM-5.3 medium** | U4 | **Task 5.1 obsolete** (field removed by decision 2026-08-30); harvester (5.2/5.3) open | [`TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md) |
| **TASK-06** | **Executive Decisions, Legal DCO & App Store Distribution** | **GLM-5.3 high drafts + founder decisions** | U5 | **Founder-gated** — AI drafts; FDR-DEC-01…04 need founder sign-off | [`TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md) |
| **TASK-07** | **Auditory Cortex Critical Fixes & Modality Delimiter Defanging** | **GLM-5.3 medium** | U2 | **Open** — all four fixes verified still undone | [`TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md) |
| **TASK-08** | **Chat UI Sprint 1 & 2 (Stability, Perf & A11y)** | **GLM-5.3 medium** | U3 | **Partially done** — abort cleanup shipped in `useAgentStream.ts`; Task 8.1/8.2 file refs wrong; token buffer + ARIA open | [`TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md) |
| **TASK-09** | **Security Review 01 Integration & Dispatch Egress Hardening** | **GLM-5.3 high** | U1 | **Merge done** (`297ceb67`); verification + missing tests open | [`TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md) |
| **TASK-10** | **Apple Intelligence Foundation Integration & Onboarding** | **GLM-5.3 medium** | U4 | **Merge done** (`11ded488`); platform verification open (tests exist) | [`TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md) |

---

## 2a. Review remediation backlog (added 2026-09-02, SONNET-05)

One row per finding from the seven REV-* review packets that had real, confirmed-reproducing findings as of the 2026-09-01 audit (`.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6, `.handoff/audit-2026-09-01/AUDIT-FINDINGS-DETAIL.md`). REV-01/REV-02 (security) are U1, already struck above — not repeated here. Status is sourced from `.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` and `RESULTS-SONNET-01/02/03/04-2026-09-02.md`; a finding not mentioned in any RESULTS doc is marked open on the assumption nothing touched it, not on a fresh re-check.

**REV-04 — Sovereign Host / Terminals (owner: OPUS-04)**

| Finding | Status |
|---|---|
| `R04-F1` reaper kills live user terminals | ~~Done~~ `426b3be2` |
| `R04-F3` pool leaks busy slot on error | ~~Done~~ `0a35c1b2` |
| `R04-F4` unbounded block output (~800 MB reproduced) | ~~Done~~ `0a35c1b2` |
| `R04-F5` `kill()` blocks the event loop | ~~Done~~ `98662c4a` |
| `R04-F6` unbounded fan-out | ~~Done~~ `98662c4a` |
| `R04-F7` unbounded `/api/terminal/exec` timeout/output | ~~Done~~ `e8358ed5` |
| `R04-F8` `speaker_role` kwarg missing from 3 test doubles | ~~Done~~ `902c485c` (OPUS-01) |
| `R04-F10` stale-thread guard never implemented | ~~Done~~ `e8358ed5` |
| `R04-F11` dead emitter | ~~Done~~ `e8358ed5` |
| `R04-F12` post-SIGKILL zombie | ~~Done~~ `ec924bbc` |
| `R04-F13` fd leak | ~~Done~~ `98662c4a` |
| `R04-F2`/`TERM-08` watched-shell → thread pipeline, `TasksColumn`/`YourShellRegion` mount | Open — built, unwired; founder decision (`DISPATCH...FOUNDER-DECISIONS.md`); `TERM-08`'s StatusLight target needs a new home since `ModeSwitch.tsx` was deleted by the shell redesign |
| `R04-F9` somatic block pipeline | Open — built, unwired; same founder decision |
| `R04-POOL` agent PTY pool enable-by-default | Open — now *safe* to enable (F3/F4 were the blockers) but still test-only; founder decision, recommend (a) wire it |

**REV-05 — Unified LLM Router, GPU, Apple Intelligence (owner: SONNET-03, `R05-F1` OPUS-03)**

| Finding | Status |
|---|---|
| `R05-F1` no `peer://` branch in `_stream_turn` | ~~Done~~ `e7bcf029` (OPUS-03) |
| `R05-F2` Apple Intelligence slot ignores `apple_intelligence_bridge_running` | ~~Done~~ `fc55d245` |
| `R05-F3` `GET /api/llm/config` returns provider API keys in plaintext | ~~Done~~ `94dd4a0d` |
| `R05-F7` `TierRouter.refresh()` misses mid-session file edits | ~~Done~~ `c56dcb4f` |
| `R05-N1`/`U4-18`/`U6-BUG-02` circular secure-model provisioning gate | ~~Done~~ `fc55d245` (`CAP_SECURE_MODEL_ALLOWED`) |
| `R05-P2` `HALBERT_MODEL` override fails closed on variant-resolution error | ~~Done~~ `c56dcb4f` |
| `R05-F4` images not translated per-provider wire format | Open — `model/client.py`, not this session's file; flagged for a follow-up packet |
| `R05-F5` GPU lock not taken on the streaming path | Open — same file, same flag |
| `R05-F6` `stream=True` calling `.json()` on an SSE body | Open — same file, same flag |
| `R05-F8` `is_model_loaded` prefix false positives | Open — same file, same flag |
| `STUB-01` `tier_router.py` OpenAI `NotImplementedError` stub | ~~Done~~ `a4e4b5a3` (traced unreachable from the real chat path; now a generic `Unknown provider` like every other legacy-hierarchy gap) |

**REV-06 — Agent Core, Intake Pipeline, Reactive Slices, SourcePrep RAG (owner: OPUS-01, RAG half SONNET-05)**

| Finding | Status |
|---|---|
| `R06-F1` defanged query leaks into the next turn/session | ~~Done~~ `e0052bce` — moved onto `StateContext`, structurally can't reintroduce |
| `R06-F2` `response_modality` UnboundLocalError | ~~Done~~ `58863b5e` — cleared 24-33 test failures alone |
| `R06-F3` SEARCHING ignores `retrieval_scope`/skill scope | ~~Done~~ `90207b55` |
| `R06-F4` failed chmod excluded from rollback | ~~Done~~ `5e090cf5` |
| `R06-F5` `merge_thread` orphans `open_loops`/`terminal_blocks`/`compact_boundaries` rows | ~~Done~~ `2d99bc27` |
| `R06-F6` Wyoming turn abandons `agent.process()` without `aclosing` | ~~Done~~ `8e18a93c` (OPUS-02) |
| `R06-F8` bare `except TypeError` retries retrieval unscoped | ~~Done~~ `90207b55` |
| `R06-O1` mispaired ReAct observations | ~~Done~~ `2857a641` |
| `R06-O2` `recall_memory`/`search_discoveries` silently substituted | ~~Done~~ `2857a641` |
| `R06-X1` CRAG `secure=` kwarg test drift | ~~Done~~ `902c485c` |
| `RAG-06`/`U4-14` role scopes unreachable (no `assigned_to_role`) | ~~Done~~ SONNET-05, `sourceprep_template.yml` — 5 of 8 skill roles now mapped (network/service/storage/security/config-ops); 3 (discovery/frigate/home-ops) have no file-backed manifest to map to, by design; re-applying to the live daemon is `RAG-05`, founder queue |
| `RAG-07` `_reconcile_scopes` can never remove paths | Open — documented, not fixed (daemon's `GET /scopes` returns `path_count` not `paths`; no per-scope detail endpoint exists client-side to fix it against; needs a live healthy daemon to verify, deferred) |
| `RAG-12`/`LEG-GATE` licence manifest red | ~~Done~~ SONNET-05 — self-referential-extras parser bug fixed, 9 deps registered, gate green (51/51) |
| `U4-08` CUDA doc unreachable (`data/knowledge/` dead directory) | ~~Done~~ SONNET-05 — moved to `data/linux/nvidia-docs/nvidia_cuda_compatibility.jsonl`, matrix updated to 580.x/CUDA 13, manifest counts updated, quality-gate test added; re-embed is founder-queued (`RAG-05`) |
| `RAG-01` daemon-side scope fixes (LOD skip, `scope_mode=hard`) | Open — uncommitted in the CoDRAG checkout (`/Volumes/4TB-BAD/HumanAI/CoDRAG`); a clean daemon restart reverts to 1-chunk file-head responses; not this repo's to fix |
| `RAG-10` stale `CODEINDEX-BUILD-LOCK.txt` + stale RAG handoff status headers | ~~Done~~ SONNET-05 — lockfile deleted (its PID confirmed not running), `HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md` status corrected |
| `RAG-13` 13 corpus JSONL files (≈71 MB) gitignored | Open — founder decision; SONNET-05 corrected the doc claim from "all 53 committed" to the verified "45 tracked, 13 not" with the exact file list (`documentation/RAG-DATA-SOURCES-2026-08-24.md` §1.1) |
| `RAG-14` no way for a new install to get the ~20-hour index | Open — founder decision (ship as asset vs. UI-driven build) |
| `RAG-19`/`RAG-20`/`RAG-21` `GAPS.md`/`RAG_AUDIT_REPORT.md`/legacy ChromaDB doc indexing | `RAG-19`/`RAG-20` ~~Done~~ SONNET-05 (archived with banners); `RAG-21` (retire ChromaDB `routes/rag.py`/Settings docs UI/CLI `rag-add`) open, founder decision recommends retire |

**REV-08 — UI/UX Redesign, Settings Decomposition (owner: SONNET-04)**

| Finding | Status |
|---|---|
| `R08-01` Approvals + 6 routed pages have no nav entry | ~~Done~~ pre-dated packet (shell redesign) + `886e1b9d` (approvals badge) |
| `R08-02` NavRail ARIA tabs half-implemented | ~~Done~~ `af16f2f8` — dropped tab roles for nav semantics, added `aria-current` |
| `R08-04` literal-colour ratchet red | ~~Done~~ `c6989455` — 9 files swept to semantic tokens, re-baselined at 211 |
| `R08-05` indexing poll leak | ~~Done~~ `6e4ef14b` |
| `R08-07` Clear Cache placebo / Debug toggle / blocklist PUT-per-keystroke | ~~Done~~ `6e4ef14b` |
| `DS-10` 56 hardcoded hex colours | Open — not this packet's files (`ConfidenceIndicator.tsx` is real, fixable; `xtermTheme.ts`'s 40 are legitimate/documented; rest are false positives) |

**REV-09 — Auditory Cortex & Audio Pipeline (owner: OPUS-02)**

| Finding | Status |
|---|---|
| `R9-F01` Wyoming unauthenticated on `0.0.0.0:10400` by default | ~~Done~~ `65ff3e83` — now `127.0.0.1` + disabled by default, breaking change, operator-visible |
| `R9-F02` second event loop, per-loop turn lock | ~~Done~~ `8e18a93c` |
| `R9-F03`/`U2-14` VAD fed 480-sample frames, Silero needs 512 | ~~Done~~ `409fc509` |
| `R9-F04` enrolled voiceprints never loaded | ~~Done~~ `409fc509` |
| `R9-F05`/`U2-15` production can never resolve VOICE modality | ~~Done~~ `65ff3e83` — the keystone fix (`has_speaker()` was permanently False) |
| `R9-F10`/`R3-F04` audio-chunk framing | ~~Done~~ `65ff3e83` |
| `R3-F10b` `Server.aclose()` doesn't exist on Python 3.10 | ~~Done~~ `65ff3e83` |
| `U2-05` satellite replies send raw markdown to HA TTS | ~~Done~~ `65ff3e83` |
| `U2-07` `<speech>` tag defanging | ~~Done~~ `8e18a93c` |
| `VM-STT` spoken input never becomes a turn | ~~Done~~ `9ec19f8a` — no new endpoint needed, reused the existing bidirectional mic socket |
| `R9-F06`/`F07`/`F08`/`F11`/`F13`, `U2-09` modality-context XML | Open — below the P0/P1 line, chain runs end to end without them |
| `is_speech`'s per-frame `detector.flush()` | Open — packet asked to remove it; OPUS-02 deliberately did not (Silero is stateful, flushing discards context hysteresis depends on; untestable without sherpa-onnx, flagged rather than guessed) |
| Hardware validation | **0/22**, unchanged — no sherpa-onnx/openwakeword/Piper in `.venv`, founder queue (`HW-01`/`VM-15`/`VM-27`) |

**REV-10 — Federated Fleet & Multi-Persona (owner: OPUS-03)**

| Finding | Status |
|---|---|
| `R10-N1`/`ROUTE-01` devices router mounted without `/api` prefix | ~~Done~~ `1f3b68fc` |
| `R10-F1`/`SE-16` self-service pairing (no confirmation/expiry/rate limit) | ~~Done~~ `7dc93e68` |
| `R10-F2`/`SE-09` workstation compute endpoint never mounted | ~~Done~~ `92cf9868` |
| `R10-F3`/`SE-08` three components disagree on the health route | ~~Done~~ `92cf9868` |
| `R10-F5` any peer can revoke any other | ~~Done~~ `1f3b68fc` + `7dc93e68` |
| `R10-F10`/`R10-F11` 500s on unbuilt surfaces | ~~Done~~ `0175377d` |
| `SE-15` UI pairing cannot succeed (mDNS list hardcoded, manual tab throws, token never reaches the other machine's `being.yml`) | Open — NOT in OPUS-03's fixed list (that table covers `ROUTE-01`/`SE-16`/`SE-09`/`SE-08`/`R05-F1`/`FED-01` only); `SE-16` fixed the backend pairing-security flaw, this is the separate frontend gap. This is P7's actual acceptance gap — see `IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md`'s corrected Status block |
| `SE-05` `ComputeRouter.route()` never instantiated | Open — founder decision, recommend wire for HOME variant only (endpoint it routes to now exists and works) |
| `SE-10` `PeerToolProxy` never injected into the live tool-execution path | Open — not in OPUS-03's fixed list; P5a/P5d's own security tests exercise it directly, not through a real turn |
| `SE-12` deferred queue unbounded, `replay_deferred` unimplemented | Open — gated on `SE-05` |
| `SE-28` two-machine LAN test | Open — not written, needs the founder's real two-machine run behind it |
| `R2-F6` outbound token custody (Fleet Cockpit blocker) | Open — `PeersConfig` stores only hashes by design (M14); needs its own credential store decision before the Fleet Cockpit can be built; routes deliberately answer 501 rather than inventing an unreviewed store |
| `PERS-02`/`PERS-03`/`PERS-05` persona sources of truth | Open — not started; design recommendation A (pick `PersonaStore`) stands |

**REV-11 — Chat UI Performance & Accessibility (owner: OPUS-05)**

| Finding | Status |
|---|---|
| `R11-01` every completed turn cancels itself (double-cancel on explicit stop) | ~~Done~~ `c099be47` |
| `R11-02` queued send drops pending approvals | ~~Done~~ `edb36d25` |
| `R11-03` impure `setSession` updater | ~~Done~~ `9cfb10c2` |
| `R11-04`/`05`/`06`/`09`/`10`(partial)/`12` re-parsing/overlapping-loads/etc. | ~~Done~~ `689f5f78` |
| `R11-11` composer claims a popup that isn't rendered | ~~Done~~ `7dce8e58` |
| `R11-13` callback churn | ~~Done~~ `9cfb10c2` |
| `R11-10`'s abort half (shared `inFlight` flag in `api.ts`) | Open — one-line follow-up (`signal` param on `api.getTimeline`) for whoever owns `api.ts` next; `useTimeline`'s own half is fixed |
| `R11-07` focus after "Forget this" | Open — lives in `DevicesTab.tsx` (OPUS-03's file, not OPUS-05's) |
| `R11-08` HostShell landmark | Open — `components/shell/**` moved under the shell redesign; not addressed |
| `CUA-04` adopt `react-markdown`+`remark-gfm` | Open — deliberately not done; would have added an unregistered dependency while the licence gate was red. **Gate is now green (this packet's Task 2)** — reconsider next time this area is touched |

---

## 3. Specific Subsystem Status & Detailed Open Loops

**Superseded 2026-09-02 — reduced to pointers (SONNET-05 doc pass).** Every checkbox below that this granularity used to track individually now has a more accurate, evidence-sourced status in **§2a** (finding-id level) or `ROADMAP.md` §3 (product-capability level, current now/next/deferred source of truth). Kept as a compressed summary per subsystem so the subsystem groupings themselves aren't lost, not as a place to check new boxes.

### Security & Trust Boundary Subsystem — ~~all listed items done~~ (2026-09-02)
All eight Step/Follow-up items were already done as of 2026-08-30. `feat/security-review-01` merged (superseded by the fuller 2026-09-02 merge, `909b56c4`, SONNET-01 — see §0 U1). The one open item, the unredacted index rebuild, is still open: `SEC-04` in §2a's U1 row (daemon reported wedged, deferred by SONNET-01, not this session's to force).

### Sentient Home & Auditory Cortex Subsystems — ~~11 of 14 items done~~ (2026-09-02)
The four TASK-07 fixes (speaker role, TTS markdown stripping, session ID collision, barge-in wiring), the modality-aware prompt builder, `StreamingTagDemuxer`, the SSE schema, `<modality_context>` XML, ThreadManager injection, and `HALBERT_MODEL` wiring are all done — see **REV-09** and **REV-06** in §2a for the finding ids and commits. `secure_model` and Phase 8 light variant were already done as of 2026-08-30 (further revised by U6, see below). Still open: Rust AEC (`audio_capture.rs` marked dormant by decision, not built — `VM-22`); the frontend voice UI components (`AcousticAuraIndicator.tsx` exists, the rest per `ROADMAP.md` VOICE-1); macOS NSPanel/CGEventTap HUD (`FDR-08`, founder-gated channel decision).

### Home Automation Simplification (Batch U6) — ~~S1, S2, S6 done; D1 done~~ (2026-09-02)
Struck in §0 above (Batch U6 fully merged `4e4ff2f4`/`93c863c1`/D4 `8545af94`). D1 (unify variant resolution) is done — `SONNET-03` routed `CapabilityRegistry` through `cognition_wiring._get_variant()` (`U6-BUG-01`). D2/D4/Q3/Q4 are implemented-per-default, awaiting founder ratification (`DECISIONS.md`). S3 (Compute Peer setting) and S4 (drop 1B tier, wizard compute-peer prompt) are **done** — verified 2026-09-02 against the actual code (`ComputePeerCard.tsx` + `Settings.tsx:806`'s `isHomeVariant` branch for S3; no 1B recommendation path left in `hardware_detector.py`, `config_wizard.py::_prompt_compute_peer`/`_test_compute_peer` wired for S4 — see the corrected checkboxes in `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`). S5 (HA memory embeddings), S7 (revise the low-power handoff) — not independently re-verified this pass; check against `ROADMAP.md`'s HOME-1 row. `U6-BUG-03` (Frigate queue cap) and `U6-BUG-04` (snapshot→vision routing) are U6 residue, not a REV finding — confirmed still open, not started (per `.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` §3 "Deliberately not done").

### Frontend, Chat UI & Settings Megafile Subsystems — ~~all five items done~~ (2026-09-02)
Settings decomposed (SONNET-04, ~880 lines / 12 lazy tabs, not the originally-planned 8 — `VisionTab`/`DevicesTab`/`SecurityTab` added since); nav re-railed; `Security.tsx`→`Findings.tsx` renamed; Chat UI Sprint 1&2 fully done via OPUS-05 (§2a REV-11); GPU deep-scan refactor done (raw Ollama call removed, 4 registered specialist tools, `162f3965`/`fbfb5614` — though the CUDA knowledge doc it produced needed its own fix, `U4-08`, done this packet).

### Core Agent & Configuration Engine Subsystems — ~~context field removal, AI bridge merge done~~ (2026-09-02)
Role-scoped config harvesting: the harvester itself + `assigned_to_role` template wiring done this packet (§2a REV-06, `RAG-06`/`U4-14`); re-applying to the live daemon is founder-queued (`RAG-05`). Apple Intelligence local-only scoping (S6): done (§2a REV-06/U6 above).

### Product Strategy & Founder Legal Decisions — moved to `DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`
`FDR-DEC-01..04` (DCO language, §7 exception text, bundle identifiers, perpetual pricing) map onto that sheet's §A `FDR-01/02/03/04` rows — same open items, not duplicated here. See that document for the current default-assumed answer to each.

---

### Added 2026-09-02 (SONNET-05) — Voice Mode visual UI, singular entity, branch hygiene, CI status

- [x] ~~**Voice Mode visual UI (doc 16, F1-F5/O1-O9/P1-P4/G1-G4)**~~ Complete on `main` per `.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` §5 — P4 got its two-stage review (`88413a42`); the stale "P4 unreviewed" caveat in `HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md` is corrected (this packet). What was missing — the loop connecting voice input/output to a real turn — is also now done: `VM-STT` (`9ec19f8a`) and `U2-15` (`65ff3e83`), both OPUS-02. Open: no real-audio hardware run has ever happened (0/22), and `is_speech`'s per-frame `detector.flush()` needs one to evaluate (§2a REV-09).
- [x] ~~**Singular entity / compute peer (`feat/singular-entity-opus`)**~~ Branch retired — all 7 commits reached `main` via cherry-picks then were superseded (SONNET-02 §2.1). `IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md`'s "Status: COMPLETE" corrected this packet to "code units complete; not usable end to end" — OPUS-03 fixed the devices API, the compute endpoint, and the pairing *security* flaw (`SE-16`, no confirmation/expiry/rate limit) and peer streaming (`R05-F1`, clean failure not silent breakage), but `SE-15` (UI-driven pairing still cannot complete end to end — mDNS hardcoded empty, manual entry throws, token doesn't reach the other machine), `SE-05` (wire `ComputeRouter.route()`), `SE-10` (`PeerToolProxy` never injected), `PERS-02/03/05` (persona sources of truth), and `SE-28` (two-machine test) remain open — see §2a REV-10.
- [x] ~~**Branch and worktree hygiene**~~ Done by SONNET-02 (2026-09-02): 10 local branches + 2 remote-only + 2 stashes + 3 of 5 "unmerged" branches confirmed to contain nothing `main` lacks and retired; 12 worktrees removed (~11 GB reclaimed, largest single item `.claude/worktrees/central-todo-batches` at 7.0 GB); canonical `wt_pytest.py` committed at the repo root. Two residual items **blocked on the harness's auto-mode classifier, not on the work**: 5 remote branch deletions (`docs/chat-ui-audit`, `feat/halbert-mcp`, `feat/modality-voice-phase2`, `feat/federated-fleet`, `feat/plan-b-terminals` — all still on `origin`, confirmed ancestors of `main`, ready to delete) and a backup push of `feat/rust-native-core` to origin (local-only today). Full detail: `.handoff/RESULTS-SONNET-02-2026-09-02.md`.
- [x] ~~**CI status**~~ SONNET-05 (this packet): `.github/workflows/ci.yml` now installs the `vision` extra (closes 13 of the then-remaining local failures), aligns Node 20→22 to match `.nvmrc`, adds a `rust-tauri` job (macOS runner, `cargo test`, 24 tests — verified locally before adding), and a `marketing-web-v7` build-smoke job. Dashboard `package.json` gained a `typecheck` script so the root `npm run typecheck` actually reaches it. `e2e/README.md` documents the two Playwright smoke scripts that stay out of CI (need a live backend). Not done: confirming the remote GitHub Actions run status — `gh` is still not installed on this machine, so this is unverified beyond local reproduction of every new job's command.

---

### Rust Native Core & HalbertOS (Long-Term Project — added 2026-08-31, augmented 2026-08-31, edits landed 2026-09-01)

> **DEFERRED BY DIRECTION (2026-09-01, `HA-01`).** The founder's 2026-09-01 direction is explicit: "the full Rust rebuild is deferred, a Linux OS is far future; the priority is to get the current features completed and tested" (`.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` header, `ROADMAP.md` §1, `DECISIONS.md` standing directives). `feat/rust-native-core` stays parked — SONNET-02 confirmed its merge-tree is clean against `main` and it is local-only (needs a backup push to origin, not yet done). The "Recommended start: R0... can begin now" line two paragraphs below predates this direction and should not be read as current guidance — nothing in this section is scheduled. Revive triggers are the plan's own L0–L3 gates (§16).

Separate living TODO with **72 tasks across 8 phases (R0–R7)** — 56 in the R1–R6 build phases. Synced with the HA strategy scoping decisions (D1-D8), the experimental docs corrections, and the sanity review's findings F1-F13 + recommendations RA-RE (applied 2026-08-31). Full plan with model tier + effort level per task:
[`RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md)

**Phase summary:**
- **R0 — Foundation + Docker track** (crates/ workspace + scaffolding + R0.9 Dockerfile + R0.10 CI image build/publish): 10 tasks, Sonnet med/high, ~3 days
- **R1 — Native Device Bus** (halbert-mqtt + Python registry): 9 tasks + FFI wave R4a, Sonnet xhigh + GLM-5.3 high, ~2.5 weeks
- **R2 — Kernel Telemetry** (eBPF probes): 10 tasks + FFI wave R4b, Opus xhigh + Fable review, ~3 weeks
- **R3 — Atomic Safety** (Btrfs snapshots + Landlock): 9 tasks + FFI wave R4c, Opus xhigh + Fable review, ~2 weeks
- **R4 — PyO3 Bridge** (halbert-ffi — now **three waves**: R4a after R1, R4b after R2, R4c after R3): 7 tasks, Sonnet xhigh, absorbed into the three legs
- **R5 — halbertd Daemon** (systemd/launchd + internal socket IPC + one external MCP surface): 14 tasks, Opus xhigh + Fable review, ~3 weeks
- **R6 — Deployment Paths** (sidecar compose on the published registry image + HA Add-on wrapper + OS-MCP): 7 tasks, Sonnet high, ~1 week
- **R7 — Turnkey Appliance** (north-star, gated): 6 tasks, Opus xhigh, ~4 weeks

**Recommended start:** R0 (scaffolding **and** the Docker track) can begin now in parallel with U-batches — the agent container image has zero Rust dependency and dogfoods from week 1. Next: R1 + wave R4a (highest product value — makes HA optional, and is now verifiable on its own timeline). R2 + R4b and R3 + R4c run in parallel on the Linux+Btrfs reference VM. Critical path: roughly 7 weeks fully parallel vs ~12 sequential.

**Review applied 2026-08-31:** [`REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md) — sanity review's 13 findings (F1-F13) and 5 recommendations (RA-RE) accepted per founder directive; all 11 proposed edits landed in the plan, the scoping doc, and this index. The two HIGH findings: **F1** (R1 was not verifiable before R4 due to monolithic FFI gating — fixed by restructuring R4 into per-crate waves R4a/R4b/R4c) and **F2** (no task built the container image the deployment paths depend on — fixed by adding the R0.9/R0.10 Docker track). External confirmation review is now optional second opinion, not a gate.

**Architectural principle:** Rewrite stable system API interfaces (eBPF, Btrfs, Landlock, MQTT) in Rust. Keep application logic (scanners, state machine, prompts, device registry) in Python. Rust crates are thin native layers; Python is the brain that calls them.

**Explicitly deferred (D7):** Custom kernel, Wayland compositor, PID 1, initramfs sentinel, dm-verity, native Matter controller, BLE, Windows platform, APFS snapshot SPIs; Z-Wave JS native client (trivial, ~3 days — re-enters L0 planning once R1 proves the native-device pattern; plan §11/§16.4a).

---

## 4. Resync — 2026-09-14: unfinished work across every thread

Captured by auditing `git status`/`git branch --no-merged`/`git worktree list`, `ROADMAP.md`, `SECURITY-TODO.md`, `DECISIONS.md` pending rows, and the post-2026-09-02 `.handoff/` corpus. `ROADMAP.md` §3 remains the only now/next/deferred source — this section is capture, not priority. Strike and date when done.

### 4.1 Uncommitted in the main checkout (working tree)

- [ ] **Onboarding machine-role inference** — scan-first onboarding replacing dead `user_type`: `discovery/role_inference.py` (new), `GET /api/settings/onboarding/probe`, `roles: list[str]` + optional `notes` on `POST /onboarding/complete`, `GET/POST /api/settings/machine-roles`, roles in prompt identity block + `get_summary()` + `/api/instance/info` + `routeCapabilities` + `landingRoute`, Being-tab role editor, HA/MQTT/Zigbee/Z-Wave scanner signals incl. macOS `usb_devices` population. 26 new Python tests + 5 frontend; suites green. `RESULTS-ONBOARDING-ROLE-INFERENCE-2026-09-13.md`. Deferred half (§6.3 role feature-gating — needs ruling on whether declared intent may remove hardware capability — §6.4 scan emphasis, §6.5 proactivity mode) is designed, not built.
- [ ] **Marketing v10 factual-review copy fixes + legal doc sync** — `marketing/web-v10/{index.html,App.jsx,stops.jsx,ScrollHUD.jsx,LayoutStage.jsx,privacy.html,terms.html}` + `documentation/legal/{PRIVACY,TERMS}.md` modified by another session; `RESULTS-MARKETING-V10-FACTUAL-REVIEW-2026-09-14.md` says LANDED (copy applied) but nothing is committed. `HANDOFF-VOICE-INFLECTION-AND-HARDWARE-SCALING-2026-09-13.md` also modified (+48/−21) — check which session owns it before committing.
- [ ] **Untracked**: `web/` (contains `feature-reference-old`), `AGENTS.md.backup-2026-09-10`, `CLAUDE.md.backup-2026-09-10` — decide commit/delete; AGENTS says `web/feature-reference` is a reference viewer, and `feature-reference-old` may be superseded.
- [ ] One stash: `stash@{0}` WIP on `feat/lift-03a-scheduler` (monitor-hash suppress/diff gate) — confirm whether it landed via merge before dropping.

### 4.2 Unmerged branches (only three; 87 merged)

- [ ] **`fix/remediation-opus-batch-2`** — 13 commits, 173 behind. The *competing* R-12 continuity implementation: main has the sonnet batch's R-12 Phase A (`98fbbb17`); this branch carries a fuller session-tree wiring plus extras — `A07-G8` yield primitive (`e7bcd05f`), utility-slot locality gate (`9e000ab3`), eval-matrix hardening (`275d9a39`, `54e05f81`, `a3cbc598`), entitlement-spike evidence doc (`5a1248cc`). Head commit `bb16bf49` names **three required rulings** (which R-12 impl, rotation threshold, `move_leaf` BEGIN IMMEDIATE) + one smaller call (cancelled-turn marker). Reconcile-or-close decision pending; do not let it rot silently.
- [x] ~~**`feat/data-viz-slice-1`**~~ Merged 2026-09-15 (`134c44dc`). The row's count was stale by the time it was read — the branch was 11 commits, not 9, and `main` had touched **none** of its fifteen files, so the feared token drift never happened and the merge was conflict-free. Review pass landed with it: the in-segment label ladder measured its track instead of assuming an 800px column, a private `--color-border*` alias palette was folded back onto the canonical tokens (31 call sites), and five meters wearing a data hue beside a `WARN` chip were settled by a ruling now written into the spec's colour table. Storybook's axe run then caught what neither test suite could see: every gauge carried `role="meter"` with no accessible name (the caller's `aria-label` was landing on the wrapper), and the in-segment labels were hardcoded `#ffffff` — wrong in dark mode, and under 4.5:1 on four categorical pigments. The contrast gate now checks label-on-mark and those four pigments are darkened. Phase 1's last task also shipped: `storage.py` was running `btrfs fi df` and `bcachefs fs usage` but discarding their byte figures, so the multi-segment gauge had no data behind it; both parsers now keep them and a filesystem reporting a split renders it, while one that does not keeps a flat mark. Open: `ROADMAP.md` has no data-viz row yet (see `DATAVIZ-1`), and Phases 2–4 of `documentation/design/DATA-VISUALIZATION-SPEC-AND-OPPORTUNITIES.md` are unstarted. Worktree at `.claude/worktrees/data-viz-slice-1` can be removed.
- [ ] **`worktree-sec-1-one-door`** — `git cherry` shows 6/7 commits patch-equivalent on main; the only non-equivalent (`71c7b88b`, SEC-D10) is already reflected in DECISIONS.md content. Effectively absorbed → verify once and delete branch + worktree.
- [ ] **~40 stale worktrees** under `.claude/worktrees/` (all `feat/lift-*`, merge-train worktrees, `remediation-*`, `sec-merge*`, `feat-app-ui-access`, `feat-guest-persona`, `feat-kokoro-tts`, `interest`, `multi-node-phase-1`) — all merged; cleanup pass pending (prior cleanup reclaimed ~11 GB, SONNET-02).

### 4.3 ROADMAP §3 rows still open (state as audited)

Rows with unresolved portions, one line each — see ROADMAP for definitions of done:

- [ ] **CI-1** — CI green: vision-extra + SPDX + ratchet state unverified since SONNET-05; `gh` absent so remote Actions status never confirmed.
- [ ] **ID-1** — open residual: prompt name still reads `BeingConfig.name` not the resolver (`C1-02`); `identity.xml` perspective tag vs the_computer voice.
- [ ] **ATTN-1** — proof slice joints still missing (`J3-7`, `J3-10`, `C2-02`, `C2-11`, `J3-12`); sshd drop-in scanner filed 2026-09-14 as the F7 proof target.
- [ ] **ATTN-2** — `/findings` still lists discovery scans not findings (`C2-03`); dashboard triage (`C2-14`); attention state on pill in every layout (`C2-08`); report persistence (`C2-10`).
- [ ] **MIND-1** — no unprompted cognitive tick (`C4-02`); Eyes→mind partial (DetectorRunner→`add_event`, retention job, occupancy erasure open under `C4-04`); cognition persistence (`C4-05`).
- [ ] **STATE-1** — grounding still opportunistic (`J2-2`, `J2-3`, `P1-02`).
- [ ] **LEDGER-1** — `run_command` outside the ledger entirely (largest hole); diff-apply route unreachable in production.
- [ ] **TRUST-1** — `C3-01/02/04/05/19`; model-issued `web_search` routes to SEARCHING but never executes; per-body peer identity blocked on Haloysius Phase 1.
- [ ] **LD-1** — `NodeFleetCockpit` written/tested/mounted nowhere (no route or nav); two-machine hardware run outstanding.
- [ ] **SHELL-1** — stubs: `W5-CONV-02/03`, `W5-PROACT-01`, `W5-TERM-01`, `W5-KEYS-01/02`, `W5-BUG-01`.
- [ ] **TERM-1** — watched user shell: `YourShellRegion` mounted nowhere, mount div never filled (`9-4-todo` §C1); legacy `/terminal` page still routed, reports connected to nothing (§C2).
- [ ] **VOICE-1** — 0 real-audio runs ever (`VM-27`, `VM-15`); `/voice` on appliance; N150 matrix; Kokoro TTS + inflection work merged from `feat/kokoro-tts` but untested on hardware.
- [ ] **HOME-1** — `W3-S01/S02/S07/S08/S11/S12/S13`, `U6-BUG-03/04` (Frigate queue cap, snapshot→vision routing).
- [ ] **CFG-1** — `A2-01/03/04/08/19`; `A2-05` being.yml split after P0s.
- [ ] **GATE-1** — `feature_flags.py` deletion + `is_home_variant()` callers (`A1-05`) still open.
- [ ] **MCP-1** — standalone-process discoveries empty (`MCP-03/04`); macOS snapshot path (`SEC-05`).
- [ ] **CLI-1** — `CLI-01..04`.
- [ ] **KNOW-1** — `P1-05/11/12`, `RAG-01/06/13/14`, `U4-08/14`; corpus number vs fresh-clone reality.
- [ ] **SKILL-1** — matcher unwired at `routes/agent.py:223`, `composed.prompt` unconsumed, `set_skill_safety` test-only, `allowed_tools` unread (DEFECT-1 verified).
- [ ] **FENCE-1** — `A1-06/08/10/11/12/13/14/15`, `PICK-04`, `PERS-02`.
- [ ] **SURF-1** — `C2-12/13`, `W3-C04`.
- [ ] **BIRTH-1** — first-conversation onboarding; the role-inference slice landed 2026-09-13 (uncommitted); the conversation-shaped flow + real progress remains, and SEC-6's design absorbs it.
- [ ] **DOCS-1** — `A4-09/21`, `A1-16`, `C4-08`, `T1-02/03/16`, `P1-08/09`.
- [ ] **GPU-1** — research done (`RESEARCH-MAC-GPU-SUPPORT-2026-09-07`); Phases 1–6 not started.
- [ ] **DIST-1** — legal cleared; code half open: entitlements plists, per-channel injection, private-API feature split, category reconcile, LICENSE-in-bundle. `FDR-09` external enrollments outstanding.
- [ ] **APPLE-1** — `secure_model` points at a never-built HTTP sidecar (`127.0.0.1:11435`); FoundationModels is native Swift, no `fm` CLI exists; every secure turn falls back — feeds the cloud-suffix path.
- [ ] **SEC-15 naming collision** — ROADMAP `SEC-15` (:cloud suffix bypass) was **fixed 2026-09-08** under the audit's `SEC-21` numbering (`is_local_model()` at five sites); ROADMAP row is stale. SECURITY-TODO `SEC-15` is a different item (prompt-injection containment) still open. Renumber the ROADMAP row.

### 4.4 SECURITY-TODO train — open items

- [ ] **SEC-1 residual** — non-loopback bind guard partial: `guard_bind` runs only in `python -m halbert_core.dashboard`; shipped `deploy/*.service` units, `packaging/systemd` unit, `cmd_dashboard_serve` don't hit it.
- [ ] **SEC-4** — policy-engine deletion (`SEC-D11`), scheduler must not execute `approval_required` jobs, safe-mode flag off CWD-relative path, approval re-read + expiry at execution. Not started.
- [ ] **SEC-5** — capability/consent split, `Lease` object on capture/exec/egress primitives, chokepoint lint + deny-all canary. Was blocked on `SEC-D10` — that call is now recorded (platforms.yml canonical, 2026-09-08), so **unblocked**.
- [ ] **SEC-8** — one halt action + `halt.json` + six doors + live indicators from open leases. Ships with SEC-5.
- [ ] **SEC-6** — two-phase boot + first-run consent review (absorbs BIRTH-1; deletes `user_type` + marker eventually — the role work composes with it). Not started.
- [ ] **SEC-9 residual** — per-entity opt-in for L2 domains (deferred to SEC-5 consent model); HA→Halbert direction still relays any HA caller's text into a full turn (SEC-12 + SEC-10 scope).
- [ ] **P1 rows** — SEC-7 consent ledger, SEC-10 speaker authority, SEC-11 egress chokepoint, SEC-12 remote-propose-only, SEC-14 self-modification fence/skills, SEC-15 prompt-injection containment, SEC-17 settings IA.
- [ ] **P2 rows** — SEC-13 data-at-rest/erasure/export, SEC-16 packaging/signing/install chain, SEC-20 threat model + honest docs.
- [ ] **P3 rows** — SEC-18 Windows empty ceiling (~1 day, scheduled early), SEC-19 sensor trust/retention.

### 4.5 DECISIONS queue (~30 unresolved rows)

- [ ] **Pending ratifications** (implemented-per-default, awaiting founder): `FD-24`, `FD-15`, `FD-16`, `FD-5/6/7`, `FD-3`, `FD-1`, `FD-19`, `FD-20`, `FD-22`, `FD-11` (revised — packaging call `ENV-01`: ship newer SQLite), `A13-G5`, `U6 D2/D4/Q3/Q4`, `R9-F01`, `R10-F1`, `VM-STT`, `R04-F1..F13`, `RNC-06`, voice `is_speech` flush, `U6-DESIGN-01`, `STUB-01`, `CC-02`, `INTEG-03..10`, `C1-02`/`W4-06` phrasing, `C2-10`, `C3-08`, `J3-7`, `C4-01`, `SEC-TLS`, `REPL-CACHE`, `COMP-STREAM`.
- [ ] **Open founder rulings table** (DECISIONS tail): `C1-02`, `W4-01`, `C2-03`/`T1-11`, `C4-10`/`C4-01`, `C4-07`, `A2-05`, `C3-14`, `C3-08`, `C3-19` (due *now* — shipped units bind off-loopback), `SEC-05`.
- [ ] **SECURITY-TODO founder calls**: `SEC-D10` done; still open `SEC-D1` (App Store channel), `SEC-D2` (X11 capture), `SEC-D3` (voiceprint retention), `SEC-D4` (bystander), `SEC-D5` (Windows target), `SEC-D11` (delete-or-repair policy engine), plus non-blocking `SEC-D6..D9`, `SEC-D12`.
- [ ] **Memory boundary — five ordered decisions** (`DESIGN-MEMORY-BOUNDARY-2026-09-10` §8): two-store split ratification; curated core → ranked claim keys; partition by acquisition mode; merge-type declaration (`LWW`/`SET`/`ASK`); disagreement meter before provenance column.
- [ ] **`FDR-04` monetization** — ACTIVE review: `HANDOFF-MONETIZATION-PLAN-REVIEW-2026-09-14.md` (device count ≥5–10, price re-derivation, MoR check, Ardour-model constraint) — awaiting a review session producing a written recommendation back to founder.
- [ ] **F-3 Phase B** — Halbert curated-core executor: R1 elision rule, R2 `messages[0]` two-tenant split, four-signal-site set (`F3-JOINT-SESSION-AGENDA-2026-09-08`); `FD-22` keeps ranker consumer unwired until then.

### 4.6 Designed-but-unstarted handoff work (post-2026-09-02 corpus)

- [ ] **Runtime + SQLite pinning** — `HANDOFF-RUNTIME-AND-SQLITE-PINNING-2026-09-10.md`, dispatchable, *highest value open*: signed app's sidecar execs `~/.local/share/halbert/repo/.venv/bin/python` from a user-writable path — anything writing there runs with all of Halbert's TCC grants. Fix = uv-pinned frozen interpreter inside the bundle + SQLite pin (closes FD-11's `ENV-01`).
- [ ] **Secure Enclave entitlement spike** — an afternoon; kill-or-confirm for the local re-auth route before any re-auth code (per STATE-OF-WORK-2026-09-10 §2).
- [ ] **Held queue (attunement F6) — go-live blocker** — nothing calls `ledger.release(...)`; every non-SPEAK outcome is a `HOLD` that silently drops. Tripwire test pins it. Unblocks a lower daily cap.
- [ ] **Disagreement meter Phase 0** — decisions then vectors, five contract items (`DISAGREEMENT-METER-SPEC` §5.1–5.4); no memory-boundary dependency.
- [ ] **Chat UI modernization plans** — `PLAN-CHAT-UI-MODERNIZATION-AND-STACKED-TERMINAL-2026-09-11.md`, `PLAN-CHAT-UI-REFINED`, `PLAN-CHAT-UI-FABLE-LEVEL-DESIGN`, `HANDOFF-CHAT-UI-PHASES-1-3-5-2FE-2026-09-11.md` — designed 2026-09-11, no implementation commits found on main.
- [ ] **oss-pass-3 blueprint lifts** (`oss-pass-3/03`): `@pierre/diffs` DiffBlock upgrade, `/btw` ephemeral side-queries, git-worktree task isolation, Swift FFI into `crates/halbert-ffi`, out-of-process ptyHostWorker pattern.
- [ ] **Phase 4 follow-ups** (`HANDOFF-PHASE-4-FOLLOWUPS-2026-09-11.md`): zero tests for `_run_command_background`/`task_started`/`port_discovered` chain; port-sniff guard is per-chunk not per-match (narrow edge case).
- [ ] **Multi-node deferred** (dispatch §7): upstream model→endpoint streaming deltas, DAG branch grafting, PAKE, Root CA, SWIM, CRDT replication; `SlidingWindowRedactor` multi-line-secret residual.
- [ ] **Marketing open items** (`RESULTS-MARKETING-V10` §6): early-access form is fake — the only remaining untruthful element (pre-launch treatment + post-launch wiring); email ecosystem session (contacts, MX, unsubscribe); KnowledgePlate corpus number regen; `halbert.net` domain keep/lapse.
- [ ] **Proposed DECISIONS rows awaiting ratification** (RESULTS §7): sharpened model-naming rule (unversioned client names OK, versioned never), "thousands" corpus headline until RAG-13, device-count floor ≥5.
- [ ] **`iOS companion` open items** (from multi-node thread): talk-door decision, WKWebView audio spike, ingress sharing, credential-header fix — verify against `DISPATCH-MULTI-NODE-SYSTEMS-v2` before scheduling.
- [ ] **Voice**: 0 real-audio hardware runs (VOICE-1 above) — the Kokoro/inflection chain on `feat/kokoro-tts` is merged but never heard.
- [ ] **Rung-3 characterisation** — unbuilt joint build across applications; wants a decision that it *is* joint (STATE-OF-WORK-2026-09-10 §3).

### 4.7 Convention note for the next resync

`git branch --no-merged main` + `git worktree list` + `git status` is the three-command floor; ROADMAP §3 rows move only on RESULTS/commit evidence; any handoff claiming LANDED whose files are still `M`/`??` in `git status` is uncommitted, not landed.
