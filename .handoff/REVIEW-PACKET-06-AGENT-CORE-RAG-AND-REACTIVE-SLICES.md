# Review Packet 06: Core Agent Evolution, Intake Pipeline, Reactive Slices & SourcePrep RAG Integration

**Review Level:** **Fable Level Review**  
**Domain:** Agent Execution Loop, Intake Complexity Classifier, Compression Cascade, Scoped Knowledge Retrieval, Proactive Event Bus, and Findings Engine  
**Target Date:** 2026-08-29  
**Status:** Ready for Deep Core Engine & RAG Retrieval Review  

---

## 1. Executive Summary & Review Scope

Between 2026-08-22 and 2026-08-25, Halbert underwent a complete re-architecting of its core execution and retrieval pathways:
1. **Chat Path Retirement & Unified Agent Loop:** Completely retired legacy `chat.py` in favor of a single, unified `AgentRunner` orchestrating state transitions, tool execution, and memory assembly.
2. **Compression Cascade (Replacing CLaRa):** Successfully ported LinuxBrain Phase 72's multi-stage compression cascade (`SemanticCompressor`, `LinguaCompressor`, `MemoryLOD`) directly into the context assembler, dramatically improving context efficiency.
3. **Intake Pipeline & Complexity Routing:** Implemented intent parsing, task classification, and system profiling before prompt assembly.
4. **SourcePrep Scoped Knowledge Engine:** Replaced ad-hoc vector retrieval with SourcePrep's structural index across isolated scopes (`host`, `knowledge_linux`, `knowledge_macos`, `knowledge_bsd`).
5. **Reactive Slice & Proactive Event Bus:** Built end-to-end proactive daemon infrastructure: event bus, SSE push transport, scheduled morning reports, module registry, and `WhyChip` provenance citations.
6. **Findings Store & Blast-Radius Engine:** Created an automated system diagnostic pipeline: drop-in conflict detection, fstab phantom checks, precedence resolution, edge extraction, and safe `approve-apply-rollback` proposal lifecycle.

The reviewing model (**Fable**) must review the safety and robustness of the agent execution lifecycle, verify prompt assembly and token budgets under the compression cascade, audit scoped retrieval filters, and scrutinize the findings proposal rollback mechanisms.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/ROADMAP-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/ROADMAP-2026-08-23.md) | Master 8-Phase Core Architecture Roadmap | Layer definitions, slice mapping, boot smoke gates |
| [`.handoff/IMPLEMENTATION-PLAN-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/IMPLEMENTATION-PLAN-2026-08-23.md) | Detailed task-level implementation plan | Task breakdown T1.1 through T8d.1 |
| [`.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md) | Intake classifier and router specification | Query routing, intent trees, fast-path bypassing |
| [`.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md) | Retrieval architecture & corpus hygiene | Scoped search, JSONL normalization, deduplication |
| [`.handoff/PLAN-ROLE-SCOPED-CONFIG-HARVESTING-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/PLAN-ROLE-SCOPED-CONFIG-HARVESTING-2026-08-26.md) | Role-based configuration extraction plan | Config discovery, schema tagging, role scopes |
| [`.handoff/PERSONALITY-BUILDER-PHASE3-UI-SPEC.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/PERSONALITY-BUILDER-PHASE3-UI-SPEC.md) | Being personality & voice layer spec | Voice archetypes, prompt modifiers, prompt preview |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `c5d7dfb5` | 2026-08-23 | Add compression package (ported from LinuxBrain Phase 72) | `compression/*`, `tests/test_compression.py` |
| `07e82449` | 2026-08-23 | Wire compression cascade into assembler + compression API | `context/assembler.py`, `routes/compression.py` |
| `dd379f28` | 2026-08-23 | Remove CLARA, wire conversation summarization | `dashboard/app.py`, `context/assembler.py` |
| `a7c58ae0` | 2026-08-23 | Feat(intake): implement Phase 1 intake pipeline module | `intake/pipeline.py`, `intake/classifier.py` |
| `394db175` | 2026-08-23 | Feat(intake): Phase 3 — wire intake pipeline into agent path | `dashboard/routes/agent.py` |
| `7fa61efe` | 2026-08-23 | Feat(findings): findings + proposals stores with tests | `findings/store.py`, `findings/proposals.py` |
| `e3d216b9` | 2026-08-23 | Feat(findings): precedence resolution engine | `findings/precedence.py` |
| `09b4a219` | 2026-08-23 | Feat(findings): drop-in conflict, fstab phantom detectors | `findings/detectors/*` |
| `a2df980f` | 2026-08-23 | Feat(findings): blast-radius calculator from edge extractor | `findings/blast_radius.py` |
| `4c71719f` | 2026-08-23 | Feat(findings): proposal generator with approve-apply-rollback | `findings/proposals.py` |
| `da5d8019` | 2026-08-23 | Feat(config): being config schema + API endpoints | `config/being_config.py`, `routes/settings.py` |
| `51590145` | 2026-08-23 | Feat(prompts): wire voice setting into prompt layer | `prompts/agent_prompts.py` |
| `628a9896` | 2026-08-23 | Feat(proactive): event bus + SSE push transport | `proactive/event_bus.py`, `routes/proactive.py` |
| `87156bfd` | 2026-08-23 | Feat(proactive): morning report generator + scheduler task | `proactive/morning_report.py` |
| `43c233fe` | 2026-08-23 | Feat(modules): module registry + API endpoints | `modules/registry.py`, `routes/modules.py` |
| `5e5de572` | 2026-08-23 | Feat(proactive): provenance ref data model + agent wiring | `proactive/provenance.py` |
| `c5f34c6a` | 2026-08-23 | Feat(agents): wire reactive slice end-to-end | `agents/state_machine.py`, `agents/runner.py` |
| `f9aa8221` | 2026-08-24 | Feat(sourceprep): unified staging root + scoped retrieval | `integrations/sourceprep_retrieval_backend.py` |
| `5141cfe1` | 2026-08-24 | Feat: retire chat.py, migrate to agent path, fix scope API | `dashboard/routes/chat.py`, `routes/agent.py` |

---

## 4. Key Files & Architectural Components

- **Agent Engine & Context Assembler:**
  - [`halbert_core/halbert_core/agents/state_machine.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/state_machine.py)
  - [`halbert_core/halbert_core/context/assembler.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/context/assembler.py)
  - [`halbert_core/halbert_core/compression/compressor.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/compression/compressor.py)
- **SourcePrep Retrieval & Intake Pipeline:**
  - [`halbert_core/halbert_core/integrations/sourceprep_client.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_client.py)
  - [`halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py)
  - [`halbert_core/halbert_core/intake/pipeline.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/intake/pipeline.py)
- **Proactive Mechanics & Findings Engine:**
  - [`halbert_core/halbert_core/proactive/event_bus.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/proactive/event_bus.py)
  - [`halbert_core/halbert_core/findings/store.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/findings/store.py)
  - [`halbert_core/halbert_core/findings/proposals.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/findings/proposals.py)

---

## 5. Incomplete Work & Open Items

1. **Role-Scoped Config Harvesting Execution:** Design doc completed (`ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`) and tracking file created (`TODO-ROLE-SCOPED-CONFIG-2026-08-27.md`), but runtime harvesting daemon is pending implementation.
2. **Unused `SendMessageRequest.context` Field:** `dashboard/routes/agent.py` accepts a `context` parameter on incoming messages but does not pass it through to the agent context builder. Either thread it through or remove it.
3. **Personality Builder Phase 3 UI:** Frontend UI for configuring custom personality prompts and adjusting voice parameters per `PERSONALITY-BUILDER-PHASE3-UI-SPEC.md`.

---

## 6. Review Directives for Fable

- **Rollback Safety:** Scrutinize `findings/proposals.py` rollback execution. Prove that if an applied proposal fails validation or triggers an error, the previous file state and filesystem permissions are atomically restored.
- **Compression Information Retention:** Audit `compression/lingua_compressor.py` and `compression/memory_lod.py` to ensure critical syntax and entity paths in system logs are preserved during aggressive token reduction.
- **Verification Command:** Run `pytest halbert_core/tests/test_intake.py halbert_core/tests/test_compression.py halbert_core/tests/test_findings_*.py halbert_core/tests/test_proactive_*.py -v`.
