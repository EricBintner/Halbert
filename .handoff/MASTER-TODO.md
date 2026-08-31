# Master TODO & AI Review/Handoff Index

**Living task list & AI review directory.** Items move here from session handoffs so nothing gets
lost between sessions. Strike through and date when done.

**Updated:** 2026-08-30 (model/effort reassessment + ultracode regrouping)  
**Master Review Portfolio:** 11 Comprehensive Review Packets (`.handoff/REVIEW-PACKET-*.md`)  
**Active Incomplete Task Packets:** 10 Actionable Implementation Packets (`.handoff/TASK-PACKET-*.md`)

> **2026-08-30 Reassessment (GLM-5.3).** All packets were previously tiered "Fable" (one "Opus").
> After verifying actual code state, no remaining packet requires Fable. All implementation work is
> well-specified, line-targeted, and within reach of **GLM-5.3**; related packets have been regrouped
> into **Ultracode Batch U1–U5** below so each batch runs as a single workflow. Fable/Opus are reserved
> only as optional second-opinion passes on the two security reviews (REV-01/REV-02) and founder legal
> sign-off (REV-07/TASK-06). Status column reflects what verification found — several packets were
> already partially or fully executed.

---

## 0. Ultracode Execution Batches (Regrouped 2026-08-30)

Related work is grouped so each batch can be executed as one ultracode workflow run (fan-out agents per
sub-task, verify pass per finding). Batches are independent and may run in any order; U5 is founder-gated.

| Batch | Scope (packets folded in) | Model / Effort | Remaining work after verification |
|---|---|---|---|
| **U1 — Security & Trust Boundary** | TASK-09 (verify merged dispatch gate), TASK-03 Task 3.2 (unredacted rebuild script), REV-01 + REV-02 (security reviews with adversarial verify) | GLM-5.3 high (+ optional Fable second opinion on REV-01/02) | Both branch merges landed. Remaining: dispatch/egress/CORS/phrase verification, missing security tests (`test_tier2_guarantee.py`, `test_redactor.py`, `test_security_roles.py` do not exist), `scripts/rebuild_sourceprep_unredacted.py`. |
| **U2 — Voice / Auditory Cortex** | TASK-07 (all four fixes), REV-09 + REV-03 reviews | GLM-5.3 medium | Unchanged: wyoming `speaker_role`+`session_id` fixes, `text_preprocessor.py`, BargeInHandler wiring, `<speech>` defanging all confirmed undone. |
| **U3 — Frontend (Settings, Nav, Chat UI)** | TASK-02 (decomposition + nav + rename), TASK-08 (re-pointed at `useAgentStream.ts`/`AgentChat.tsx`; abort cleanup already present — a11y + token buffer remain), REV-08 + REV-11 reviews | GLM-5.3 medium (large fan-out; tab extraction parallelizes cleanly) | Settings.tsx is 3,283 lines (packet said 3,105/3,273 — stale). `ChatPanel.tsx` does not exist; packet references corrected. |
| **U4 — Model Routing & Agent Tooling** | TASK-01 remainder (`HALBERT_MODEL` env override only), TASK-04 (GPU tool refactor), TASK-05 Task 5.2/5.3 (role harvester; Task 5.1 obsolete — see erratum), TASK-10 (merged — verification only), REV-05 + REV-06 reviews | GLM-5.3 medium | TASK-01 1.1 (secure_model)/1.2 (BeingConfig fields)/1.3 (home-light variant) already shipped; only the env-var override is left. Apple Intelligence merge landed (`11ded488`). |
| **U5 — Founder Decisions (human-gated)** | TASK-06, REV-07 | GLM-5.3 high drafts all text; **decisions remain the founder's** — AI drafting cannot close FDR-DEC-01…04 | Not ultracode. Draft DCO/§7-exception/terms docs, correct `tauri.conf.json` path (see erratum), then present for founder approval. |

**Errata found during verification (fixed in packets/indexes):**
1. **TASK-05 Task 5.1 is obsolete.** It instructs wiring `SendMessageRequest.context` into the agent — but the founder decision on 2026-08-30 was to *remove* the field (done, see §3). Packet updated; only the role harvester remains.
2. **TASK-08 references a non-existent file.** `ChatPanel.tsx` does not exist. The chat streaming code lives in `src/hooks/useAgentStream.ts` + `src/components/agent/AgentChat.tsx`, and AbortController cleanup (Task 8.1) is already implemented there. Remaining: `useTokenBuffer` and ARIA live regions.
3. **TASK-09 Task 9.1 (merge) and TASK-10 Task 10.1 (merge) are already done** — `feat/security-review-01` merged at `297ceb67`, `feat/apple-intelligence` merged at `11ded488`, both on `main`. Only verification steps remain.
4. **TASK-03 Task 3.1 is already done** — `halbert_core/cli/` exists with `check_credential.py`/`check_breach.py` and `pyproject.toml` console scripts registered. Only Task 3.2 (rebuild script) remains.
5. **TASK-06 references `src-tauri/tauri.conf.json` at repo root — wrong path.** Actual file: `halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json`.
6. **TASK-01 Task 1.4 premise is false** — `deploy/halbert-home.service` contains no `HALBERT_MODEL`/`qwen2.5:3b` line to update. Tasks 1.1–1.3 already shipped in code.
7. **Several verification-command test paths in packets do not exist yet** (e.g. `test_tier2_guarantee.py`, `test_redactor.py`, `test_security_roles.py`, `test_client.py`) — creating them is part of each batch.  

---

## 1. Master Review Packets (Code Reviews — reassigned 2026-08-30)

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

---

## 2. Incomplete Work Task Packets (Actionable Implementation Handoffs — reassigned 2026-08-30)

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

## 3. Specific Subsystem Status & Detailed Open Loops

### Security & Trust Boundary Subsystem
- [x] ~~**Step 1: Remove breach checks from describe_secret.**~~ Done (commit `50d17e45`).
- [x] ~~**Step 2: Document standalone human-run tools.**~~ Done (commit `50d17e45`).
- [x] ~~**Step 3: Enrich metadata-only describe_secret.**~~ Done (commit `9fa8068e`).
- [x] ~~**Step 4: Architectural guarantee test.**~~ Done (333 tests pass).
- [x] ~~**Follow-up: Move validation/compromise modules to CLI.**~~ Done 2026-08-30 (`halbert-check-credential`, `halbert-check-breach`).
- [x] ~~**Settings UI security tab.**~~ Done (`SecurityComponents.tsx`).
- [x] ~~**Context assembler integration.**~~ Done (`get_config_value` tier routed).
- [x] ~~**Context-assembly backstop.**~~ Done (`assembler.py:334-351`).
- [x] ~~**Merge `feat/security-review-01` (Egress Dispatch Interceptor & Transport Hardening)**~~ Branch merged into `main` at `297ceb67` on 2026-08-30. Verification of the dispatch egress gate, CORS default-deny, and server-side phrase enforcement still pending — see [`TASK-PACKET-09`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md) (Batch U1).
- [ ] **Rebuild index unredacted (operational gate)** — Staging raw files via `register_host_project(redact=False)` while verifying egress boundaries. (See [`TASK-PACKET-03`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md)).

---

### Sentient Home & Auditory Cortex Subsystems
- [ ] **Wyoming agent speaker role vulnerability** — Pass `speaker_role="unknown"` from `wyoming_agent.py` to `process()`. (See [`TASK-PACKET-07`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md)).
- [ ] **Markdown-to-plaintext converter for TTS** — Implement `strip_markdown_for_speech()` so Piper doesn't read `## headers`. (See [`TASK-PACKET-07`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md)).
- [ ] **Wyoming session ID collision** — Mint UUID per turn and thread `conversation_id`. (See [`TASK-PACKET-07`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md)).
- [ ] **Barge-in handler wiring** — Connect `BargeInHandler` to `AudioPipelineCoordinator`. (See [`TASK-PACKET-07`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md)).
- [ ] **Rust AEC implementation** — Build `audio_capture.rs` in `src-tauri` with webrtc-audio-processing.
- [ ] **Modality-aware prompt builder** — Replace `build_response_prompt()` in `agent_prompts.py` with `build_modality_aware_response_prompt()` that accepts `modality_context` (is_voice, screen_present, speaker_name, speaker_role, area_id) and conditionally emits `<speech>` dual-stream contract + Sotto Voce directives. (See doc 14 section 3).
- [ ] **`StreamingTagDemuxer` in state_machine.py** — Buffer tokens between `<speech>` and `</speech>`, emit new `StreamEvent.speech_chunk` events, strip `<speech>` tags from the visual stream so the GUI timeline receives pure Markdown, pipe speech chunks to active Piper TTS generator. (See doc 14 Gap 2).
- [ ] **`StreamEvent.speech_chunk` + `DualStreamMessageEvent` SSE schema** — Add new StreamEvent factory method and frontend handler in `useAgentStream.ts` for the dual-stream payload (acoustic_stream + visual_stream). (See doc 14 roadmap Step 1).
- [ ] **`<modality_context>` XML injection block** — Inject structured ingress metadata (channel, origin_area, speaker_verified, speaker_name, speaker_role, screen_present, quiet_hours_active, active_background_tasks) at the head of the task prompt for every turn. (See doc 14 section 2.2).
- [ ] **ThreadManager injection into Wyoming agent** — Inject `ThreadManager` into `HalbertWyomingAgent`, query `get_or_open_thread_id()` on incoming voice turns. TASK-07 covers threading `conversation_id` as `thread_id` but not the ThreadManager injection itself. (See doc 14 Gap 3).
- [ ] **Frontend voice UI components** — Build `AcousticAura.tsx` (header audio state visualizer), `VoiceCompanionPill.tsx` (floating HUD), `ModalityHandoffBadge.tsx` (where artifacts landed), `AcousticEventCard.tsx` (environmental anomaly chronicle card). Note: actual file is `AcousticAuraIndicator.tsx`, not `AcousticAura.tsx`. (See doc 14 Gap 5).
- [ ] **macOS NSPanel + CGEventTap for floating HUD** — When `VoiceCompanionPill` is built, implement non-activating `NSPanel` with `CGEventTap` hotkey monitor for `Esc`/`Space` to avoid keyboard focus trap in background IDE. (See doc 12 Finding 4, doc 14 Gap 4).
- [ ] **`HALBERT_MODEL` env var wiring** — Thread env override into `llm_config.resolve("chat_model")` (not `cognition_wiring.py`). Verified 2026-08-30: no `HALBERT_MODEL` handling exists anywhere in `halbert_core` Python. (See [`TASK-PACKET-01`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md), Batch U4).
- [x] ~~**Add `secure_model` slot (`qwen3:4b`)**~~ Done — `llm_config.py:64` `SLOTS = ("chat_model", "specialist_model", "vision_model", "secure_model")` with local-only enforcement; `get_secure_model()` exported in `client.py:236`.
- [x] ~~**Phase 8 Light Variant (`home-light`)**~~ Done in `app.py:423-432` (heavy services skipped on `home-light`) and `cognition_wiring.py:81-93` (`BeingConfig.variant` first, env fallback). App Store *packaging* itself remains part of TASK-06/U5.

---

### Frontend, Chat UI & Settings Megafile Subsystems
- [ ] **Settings.tsx Decomposition** — Decompose 3,283-line monolith into `src/components/settings/tabs/` (`SystemTab`, `KnowledgeTab`, `SafetyTab`, `VisionTab`, `AlertsTab`, `BeingTab`, `AboutTab`, `DebugTab`). (See [`TASK-PACKET-02`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md), Batch U3).
- [ ] **Sidebar Navigation Consolidation** — Streamline 14 sidebar items into 4 primary domains in `Layout.tsx`. (See [`TASK-PACKET-02`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md)).
- [ ] **Rename `pages/Security.tsx` → `pages/Findings.tsx`** — Resolve route overlap with `Settings > Security`. (See [`TASK-PACKET-02`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md)).
- [ ] **Chat UI Sprint 1 & 2 Execution** — Fix SSE reader leak, abort controller cleanup, rAF token buffer ($O(n^2) \to O(1)$), ARIA live regions. (See [`TASK-PACKET-08`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md)).
- [ ] **GPU Page Deep Scan Rebuild** — Execute 9-step plan in `.handoff/GPU-DEEP-SCAN-REBUILD-PLAN-2026-08-29.md` to roll raw Ollama scan into agent specialist tool. (See [`TASK-PACKET-04`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md)).

---

### Core Agent & Configuration Engine Subsystems
- [x] ~~**Remove `context` field on `SendMessageRequest`**~~ — Done 2026-08-30.
- [ ] **Role-Scoped Configuration Harvesting** — Implement `config/role_harvester.py` from `ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`. (See [`TASK-PACKET-05`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md)).
- [ ] **Apple Intelligence Platform Bridge** — Merge `feat/apple-intelligence` and verify on macOS 15.1+ M-series Silicon. (See [`TASK-PACKET-10`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md)).

---

### Product Strategy & Founder Legal Decisions (`FOUNDER-TODO.md`)
- [ ] **`FDR-DEC-01`: DCO Language in `CONTRIBUTING.md`** — Developer Certificate of Origin commercial dual-distribution clause. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-02`: GPLv3 §7 Exception Text** — Commit `LICENSE-EXCEPTION-APPSTORE` and update SPDX headers. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-03`: Bundle Identifiers** — Confirm `ai.halbert.home` vs `ai.halbert.pro` in `tauri.conf.json`. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-04`: Perpetual Pricing** — $29 one-time terms and offline Ed25519 license verification. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
