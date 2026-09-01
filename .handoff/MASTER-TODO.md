# Master TODO & AI Review/Handoff Index

**Living task list & AI review directory.** Items move here from session handoffs so nothing gets
lost between sessions. Strike through and date when done.

**Updated:** 2026-08-30 (model/effort reassessment + ultracode regrouping + home automation simplification — Batch U6)  
**Master Review Portfolio:** 11 Comprehensive Review Packets (`.handoff/REVIEW-PACKET-*.md`)  
**Active Incomplete Task Packets:** 10 Actionable Implementation Packets (`.handoff/TASK-PACKET-*.md`) + U6 simplification workstream

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
| **U6 — Home Automation Simplification (S1-S7)** | [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md) (its §12 work list W1-W25 is authoritative) | GLM-5.3 medium | Remove `secure_model`, SourcePrep, and the model picker from `home`/`home-light` variants; drop the 1B tier (SBC_LOW_POWER offload-only); Apple Intelligence local-only (peer compute routes to Ollama); HA memory embeddings via Ollama/ONNX (NOT `sentence-transformers` in halbert_core — see the handoff §4.7 correction). Must land **before** federated Phase 9. Details: §3 "Home Automation Simplification" subsection below. |

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

> **2026-08-30 simplification addendum:** REV-03, REV-05, REV-06, and REV-10 must also be reviewed against [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md):
> - **REV-03** — home/home-light have no `secure_model` (unconfigured + hidden), no SourcePrep retrieval backend, no model picker (Compute Peer setting instead); persona memory embeddings are NOT SourcePrep and stay local.
> - **REV-05** — Apple Intelligence is local-only (never a peer backend); no 1B tier; `SBC_LOW_POWER` recommends offload-only; `secure_model` is sysadmin-only.
> - **REV-06** — SourcePrep scoped RAG is workstation/sysadmin-only; HA variants must not instantiate the retrieval backend or configure `SOURCEPREP_URL`.
> - **REV-10** — the HA node is a pure compute client (peer -> template thoughts fallback; no local models/SourcePrep/secure_model/picker); `compute_backends` advertises `ollama`/`vllm` only; S1-S7 land before federated Phase 9.

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
- [ ] **`HALBERT_MODEL` env var wiring** — Thread env override into `llm_config.resolve("chat_model")` (not `cognition_wiring.py`). Verified 2026-08-30: no `HALBERT_MODEL` handling exists anywhere in `halbert_core` Python. **Scope: main/sysadmin variants only** — home/home-light have no local model to override (chat/specialist resolve to the compute peer; see Batch U6). (See [`TASK-PACKET-01`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md), Batch U4).
- [x] ~~**Add `secure_model` slot (`qwen3:4b`)**~~ Done — `llm_config.py:64` `SLOTS = ("chat_model", "specialist_model", "vision_model", "secure_model")` with local-only enforcement; `get_secure_model()` exported in `client.py:236`. **Revised 2026-08-30 (S1):** the slot is now **sysadmin-variant-only** — home/home-light must leave it unconfigured, gate its auto-provisioning, and hide its UI role row (Batch U6, W1-W6).
- [x] ~~**Phase 8 Light Variant (`home-light`)**~~ Done in `app.py:423-432` (heavy services skipped on `home-light`) and `cognition_wiring.py:81-93` (`BeingConfig.variant` first, env fallback). **Revised 2026-08-30 (S1-S5):** what home-light *ships* is redefined — no `secure_model`, no SourcePrep, no model picker (Compute Peer setting instead); see Batch U6. App Store *packaging* itself remains part of TASK-06/U5.

### Home Automation Simplification (Batch U6 — added 2026-08-30)

Direction accepted per [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md) — its Section 12 (work items W1-W25, decisions D1-D4) is the **code-verified, authoritative** work list and supersedes the handoff's earlier code-impact prose where they differ. Lands **before** federated Phase 9.

- [ ] **D1 — Unify variant resolution (prerequisite for S1/S3/S4)** — `GET /api/instance/info` (`dashboard/routes/instance.py:33`) reads only the `HALBERT_VARIANT` env var while backend gating uses `cognition_wiring._get_variant()` (being.yml > env > sysadmin). Make them agree, or a being.yml-set home variant gates backend services while the UI still renders the sysadmin picker.
- [ ] **S1 — Remove `secure_model` from home/home-light** — gate Apple Intelligence auto-provisioning (`auto_provision.py:66-71`, triggered from `routes/llm.py:~208-217`), the config wizard's secure_model writes (`config_wizard.py:101-107, 262-327`), and the secure turn gate (`agent.py:465-476`); hide the role row via `variants: ["sysadmin"]` in `halbertModelRoles.ts` + host-side filtering in `ModelSettings.tsx` (not inside the shared package). (W1-W6)
- [ ] **S2 — Remove SourcePrep from home/home-light** — nothing currently skips it for any variant: variant-gate the `SourcePrepAdapter`/assembler factories (`agent.py:136-142`, `context/adapters.py:337-343,429,455`, `extra_adapters.py:559`), pass `skip_retrieval=True` in `cognition_wiring.py:141-149`, drop the config-watcher reindex callback for `home` (`app.py:616-622`), retire the HA-config bridge surface (`ha_config_bridge.py` + `/home/config-search` routes; `ha_config_tools.py` is dead code), fix `deploy/halbert-home.service` + `deploy/README.md`. (W7-W13)
- [ ] **S3 — Compute Peer setting replaces the model picker on HA nodes** — **prerequisite:** register `PeerProvider` in the model stack (`peer` is missing from `CHAT_CAPABLE_PROVIDERS`, `tier_router.py`, `providers/__init__.py` — any peer slot is currently disabled as "not chat-capable"); then ComputePeerCard mounted instead of `<ModelSettings />` (`Settings.tsx:2241`) + persist a `peer://` endpoint into `chat_model`/`specialist_model`. (W14-W16)
- [ ] **S4 — Drop the 1B tier; `SBC_LOW_POWER` offload-only** — clamp `recommend_budget()`/`get_installation_commands()` (`hardware_detector.py:429-525`; the "1B tier" is emergent arithmetic, not a named recommendation), add the wizard compute-peer prompt (new functionality — the wizard has no profile gating today), implement `ComputeRouter.route()` (the SBC local-model skip itself **already exists and is tested**). Needs D2 first. (W17-W19)
- [ ] **S5 — HA memory embeddings via Ollama/ONNX** — do **NOT** add `sentence-transformers` to halbert_core extras (wrong package — the on-path persona embedder is haloysius's ONNX/Ollama `MemoryEmbedder`; halbert_core's own `sentence-transformers` consumer is eval-only). Confirm the operative memory path (D3) first; optionally add a `[home]` extra = `[light]` + `[cognition]`. (W20-W21)
- [ ] **S6 — Apple Intelligence local-only** — strip `apple_foundation` from the mDNS `compute_backends` contract (`peer_discovery.py:35-47,272-293`, `peers_config.py:88`, `federation/README.md:35,105`, `peer.py:45`, `compute_endpoint.py:231-232,257`); **update `test_peer_discovery.py:36,43,119` which asserts the old advertisement**; fix the `PeerAuthMiddleware` ImportError (`federation/__init__.py:53,77-79` imports a class that doesn't exist). (W22-W24)
- [ ] **S7 — Revise `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`** — drop the 1B-1.5B tier row from the §7.1 capability table, the Q2_K/IQ2_XXS extreme-quantization research, and the "2B Q4 vs 4B Q2" analysis; 2B-3B is the minimum for local inference (8GB+ hosts only). (W25)
- [ ] **D2 — 4GB boundary decision** — code classifies `SBC_LOW_POWER` as strictly <4GB (4GB hosts are `ENTRY_8GB` with local-model support `True`), but the handoff's table says 4GB = offload-only. Either move the boundary (`hardware_detector.py:423`, `compute_router.py:263`, `test_hardware_profile_fallback.py`) or correct the docs to "<4GB".
- [ ] **D3 — Confirm the HA persona memory path** — the dashboard agent path wires `memory_service=None` (receipts/FTS5, `agent.py:144-146`); if that is operative on home nodes, S5 needs no packaging change at all.
- [ ] **D4 — home vs home-light merge decision** — the per-variant service-skip matrix is recorded in the handoff §12.1; if `home` retires into `home-light`, S2's watcher gating collapses into the merge.

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
- [x] ~~**Apple Intelligence Platform Bridge — merge**~~ Merged at `11ded488` (2026-08-30 erratum 3); platform verification on macOS 15.1+ M-series Silicon remains open. (See [`TASK-PACKET-10`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md), Batch U4).
- [ ] **Apple Intelligence local-only scoping (S6, Batch U6)** — ensure `apple-foundation` is never exposed to peers: peer compute on a Mac routes to Ollama; mDNS `compute_backends` = `ollama`/`vllm` only; `PeerProvider` receives the Ollama model list only. (W22-W24 in the simplification handoff §12.)

---

### Product Strategy & Founder Legal Decisions (`FOUNDER-TODO.md`)
- [ ] **`FDR-DEC-01`: DCO Language in `CONTRIBUTING.md`** — Developer Certificate of Origin commercial dual-distribution clause. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-02`: GPLv3 §7 Exception Text** — Commit `LICENSE-EXCEPTION-APPSTORE` and update SPDX headers. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-03`: Bundle Identifiers** — Confirm `ai.halbert.home` vs `ai.halbert.pro` in `tauri.conf.json`. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).
- [ ] **`FDR-DEC-04`: Perpetual Pricing** — $29 one-time terms and offline Ed25519 license verification. (See [`TASK-PACKET-06`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md)).

---

### Rust Native Core & HalbertOS (Long-Term Project — added 2026-08-31, augmented 2026-08-31, edits landed 2026-09-01)

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
