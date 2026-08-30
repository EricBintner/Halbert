# Halbert Master Incomplete Work & Task Packets Index (Updated 2026-08-30)

**Author:** Antigravity Pairing Assistant  
**Date:** 2026-08-30  
**Purpose:** Actionable Handoff Task Packets for Completing All Open Work, Resolving Subsystem Gaps, and Executing Audits  
**Target AI Models:** **Fable** (9 Technical Task Packets) & **Opus** (1 Strategic Legal Packet)  

---

## 1. Executive Summary

This index organizes all incomplete work, pending TODO items, architectural gaps, and unexecuted designs across Halbert into **10 self-contained Task Execution Packets**. 

Each packet provides exact implementation instructions, lists specific files to create/modify with line-level context, details expected behavioral changes, and includes the automated test suites required to verify completion.

---

## 2. Incomplete Work Task Packet Directory

| Task Packet ID | Task Domain & Scope | Target Model | Key Implementation Goals | Actionable Handoff Document |
|---|---|---|---|---|
| **TASK-01** | **Sentient Home Bugfix & Phase 8 Light Variant** | **Fable** | Wire `HALBERT_MODEL` env var, add `secure_model` slot (`qwen3:4b`), serialize `BeingConfig` YAML fields, implement `home-light` variant | [`TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md) |
| **TASK-02** | **Settings Decomposition & Nav Consolidation** | **Fable** | Decompose 3,273-line `Settings.tsx` into `src/components/settings/tabs/`, streamline sidebar to 4 primary domains, rename `pages/Security.tsx` → `pages/Findings.tsx` | [`TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md) |
| **TASK-03** | **Security CLI Tools & Operational Index Rebuild** | **Fable** | Package `check_credential` and `check_breach` as console scripts in `pyproject.toml`, write operational unredacted index rebuild script | [`TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md) |
| **TASK-04** | **GPU Deep-Scan Refactor & Specialist Tooling** | **Fable** | Port raw Ollama GPU analyze route to agent specialist tool, move NVIDIA/CUDA knowledge to SourcePrep markdown, adopt `AIAnalysisPanel.tsx` | [`TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md) |
| **TASK-05** | **Agent Context Plumbing & Role Config Harvester** | **Fable** | Wire `SendMessageRequest.context` into agent working memory, implement role-scoped config harvesting engine (`role_harvester.py`) | [`TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md) |
| **TASK-06** | **Founder Decisions & App Store Legal Strategy** | **Opus** | Draft DCO language in `CONTRIBUTING.md`, commit `LICENSE-EXCEPTION-APPSTORE`, lock Tauri bundle IDs, finalize $29 perpetual terms | [`TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md) |
| **TASK-07** | **Auditory Cortex Critical Fixes & Modality Defanging** | **Fable** | Fix Wyoming admin role vulnerability, build markdown stripper for Piper TTS, fix session ID UUID collision, wire BargeInHandler | [`TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md) |
| **TASK-08** | **Chat UI Sprint 1 & 2 (Stability, Perf & A11y)** | **Fable** | Fix SSE reader leak, abort controller cleanup, rAF token buffer ($O(n^2) \to O(1)$), ARIA live regions | [`TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-08-CHAT-UI-SPRINT1-AND-2-STABILITY-PERF.md) |
| **TASK-09** | **Security Review 01 Merge & Dispatch Egress Gate** | **Fable** | Merge `feat/security-review-01`, verify dispatch-level Tier 2 egress interception, server-side phrase enforcement, CORS default-deny | [`TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-09-SECURITY-REVIEW-01-MERGE-AND-DISPATCH-GATE.md) |
| **TASK-10** | **Apple Intelligence Bridge & Hardware Onboarding** | **Fable** | Merge `feat/apple-intelligence`, verify Metal detection and auto-provisioning on Apple Silicon Macs, UI model picker banner | [`TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-10-APPLE-INTELLIGENCE-ONBOARDING-AND-TUNING.md) |

---

## 3. Central Master Task List
All review findings and task executions are tracked live in [`MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md).
