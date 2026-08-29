# Halbert Master Incomplete Work & Task Packets Index (2026-08-29)

**Author:** Antigravity Pairing Assistant  
**Date:** 2026-08-29  
**Purpose:** Actionable Handoff Task Packets for Completing All Open Work and Resolving Gaps  
**Target AI Models:** **Fable** (5 Technical Packets) & **Opus** (1 Strategic/Legal Packet)  

---

## 1. Executive Summary

This index organizes all incomplete work, pending TODO items, architectural gaps, and unexecuted designs across Halbert into **6 self-contained Task Execution Packets**. 

Each packet provides exact implementation instructions, lists specific files to create/modify with line-level context, details expected behavioral changes, and includes the automated test suites required to verify completion.

---

## 2. Incomplete Work Task Packet Directory

| Task Packet ID | Task Domain & Scope | Target Model | Key Implementation Goals | Actionable Handoff Document |
|---|---|---|---|---|
| **TASK-01** | **Sentient Home Bugfix & Phase 8 Light Variant** | **Fable** | Wire `HALBERT_MODEL` env var, add `secure_model` slot (`qwen3:4b`), serialize `BeingConfig` YAML fields, implement `home-light` variant | [`.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md) |
| **TASK-02** | **Settings Decomposition & Nav Consolidation** | **Fable** | Decompose 3,105-line `Settings.tsx` into 6 tab components, streamline 14-item sidebar to 4 primary domains, rename `pages/Security.tsx` → `pages/Findings.tsx` | [`.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md) |
| **TASK-03** | **Security CLI Tools & Operational Index Rebuild** | **Fable** | Package `check_credential` and `check_breach` as console scripts in `pyproject.toml`, write operational unredacted index rebuild script | [`.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-03-SECURITY-CLI-AND-INDEX-REBUILD.md) |
| **TASK-04** | **GPU Deep-Scan Refactor & Specialist Tooling** | **Fable** | Port raw Ollama GPU analyze route to agent specialist tool, move NVIDIA/CUDA knowledge to SourcePrep markdown, adopt `AIAnalysisPanel.tsx` | [`.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-04-GPU-ANALYZE-AGENT-TOOLING.md) |
| **TASK-05** | **Agent Context Plumbing & Role Config Harvester** | **Fable** | Wire `SendMessageRequest.context` into agent working memory, implement role-scoped config harvesting engine (`role_harvester.py`) | [`.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-05-ROLE-SCOPED-CONFIG-AND-AGENT-CLEANUP.md) |
| **TASK-06** | **Founder Decisions & App Store Legal Strategy** | **Opus** | Draft DCO language in `CONTRIBUTING.md`, commit `LICENSE-EXCEPTION-APPSTORE`, lock Tauri bundle IDs, finalize $29 perpetual terms | [`.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md) |

---

## 3. How to Launch and Execute a Task Packet

1. **Assign to the designated Model:**
   - Use **Fable** for **TASK-01 through TASK-05** (High rigor, full-stack code changes, async event loops, React component refactors).
   - Use **Opus** for **TASK-06** (Strategic synthesis, licensing jurisprudence, founder decision framing).
2. **Provide the Packet Link:** Feed the exact file URI (e.g. `file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-01-SENTIENT-HOME-BUGFIX-AND-PHASE8.md`) into the model's initialization prompt.
3. **Run Verification:** Demand that the model execute the included test suite commands in Section 3 of that packet before marking the task complete.
