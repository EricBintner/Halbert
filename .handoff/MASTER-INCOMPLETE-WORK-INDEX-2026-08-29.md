# Halbert Master Incomplete Work & Task Packets Index (Updated 2026-08-30)

**Author:** Antigravity Pairing Assistant  
**Date:** 2026-08-30  
**Purpose:** Actionable Handoff Task Packets for Completing All Open Work, Resolving Subsystem Gaps, and Executing Audits  
**Target AI Models (reassigned 2026-08-30):** **GLM-5.3** for all implementation packets — effort tiers and ultracode batch groupings U1–U5 in [`MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md) § 0. No packet requires Fable/Opus; Fable remains only an optional second opinion on security reviews, and TASK-06 decisions stay founder-gated.  

---

## 1. Executive Summary

This index organizes all incomplete work, pending TODO items, architectural gaps, and unexecuted designs across Halbert into **10 self-contained Task Execution Packets**, plus the **U6 home automation simplification workstream** (S1-S7, added 2026-08-30 — see TASK-11).

Each packet provides exact implementation instructions, lists specific files to create/modify with line-level context, details expected behavioral changes, and includes the automated test suites required to verify completion.

**2026-08-30 verification pass (GLM-5.3):** code state was checked against every packet. Findings, now folded into the table below and into the packets themselves:
- **TASK-01** Tasks 1.1–1.3 already shipped (`secure_model` slot, `BeingConfig.variant`, `home-light` in `app.py`); only the `HALBERT_MODEL` env override remains; Task 1.4's premise is false.
- **TASK-03** Task 3.1 already done (`halbert_core/cli/` + console scripts registered); only Task 3.2 remains.
- **TASK-05** Task 5.1 is **obsolete** — the founder decision on 2026-08-30 was to *remove* `SendMessageRequest.context` (done); only the role harvester remains.
- **TASK-08** references `ChatPanel.tsx`, which does not exist — real code is `useAgentStream.ts` + `AgentChat.tsx`, and abort/SSE cleanup (Task 8.1) is already implemented there.
- **TASK-09 / TASK-10** branch merges already landed on `main` (`297ceb67`, `11ded488`); only verification remains.
- **TASK-01's home-variant scope is superseded (2026-08-30):** the accepted home automation simplification removes `secure_model`, SourcePrep, and the model picker from `home`/`home-light` — the shipped 1.1/1.3 work must now be partially unwired/gated. Tracked as Batch U6 / TASK-11.

---

## 2. Incomplete Work Task Packet Directory

| Task Packet ID | Task Domain & Scope | Model / Effort | Batch | Status (verified 2026-08-30) | Actionable Handoff Document |
|---|---|---|---|---|---|
| **TASK-01** | **Sentient Home Bugfix & Phase 8 Light Variant** | **GLM-5.3 medium** | U4 | Mostly done — only `HALBERT_MODEL` env override remains (**scope: main/sysadmin variants only**); home-variant portion superseded by TASK-11/U6 | [`TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md) |
| **TASK-02** | **Settings Decomposition & Nav Consolidation** | **GLM-5.3 medium** | U3 | Open — `Settings.tsx` now 3,283 lines | [`TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md) |
| **TASK-03** | **Security CLI Tools & Operational Index Rebuild** | **GLM-5.3 medium** | U1 | Task 3.1 done; Task 3.2 (rebuild script) open | [`TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md) |
| **TASK-04** | **GPU Deep-Scan Refactor & Specialist Tooling** | **GLM-5.3 medium** | U4 | Open | [`TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md) |
| **TASK-05** | **Role-Scoped Config Harvester** | **GLM-5.3 medium** | U4 | Task 5.1 obsolete (context field removed by decision); harvester open | [`TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md) |
| **TASK-06** | **Founder Decisions & App Store Legal Strategy** | **GLM-5.3 high drafts + founder sign-off** | U5 | Founder-gated | [`TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md) |
| **TASK-07** | **Auditory Cortex Critical Fixes & Modality Defanging** | **GLM-5.3 medium** | U2 | Open — all four fixes confirmed undone | [`TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md) |
| **TASK-08** | **Chat UI Sprint 2 (Perf & A11y)** | **GLM-5.3 medium** | U3 | Partially done — SSE/abort cleanup shipped in `useAgentStream.ts`; token buffer + ARIA open; packet file refs corrected | [`TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md) |
| **TASK-09** | **Security Review 01 Verification & Dispatch Egress Gate** | **GLM-5.3 high** | U1 | Merge done (`297ceb67`); verification + missing tests open | [`TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md) |
| **TASK-10** | **Apple Intelligence Bridge & Hardware Onboarding** | **GLM-5.3 medium** | U4 | Merge done (`11ded488`); platform verification open; **S6 constraint (U6): apple-foundation is Mac-local only — never a peer compute backend** | [`TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md) |
| **TASK-11** | **Home Automation Simplification (S1-S7)** | **GLM-5.3 medium** | U6 | Open — direction accepted 2026-08-30; §12 work list (W1-W25, D1-D4) code-verified. Removes `secure_model`/SourcePrep/model picker from `home`/`home-light`; drops the 1B tier (SBC offload-only); Apple Intelligence local-only; HA memory embeddings via Ollama/ONNX (NOT `sentence-transformers` in halbert_core). Lands before federated Phase 9 | [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md) |

---

## 3. Central Master Task List
All review findings and task executions are tracked live in [`MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md).
