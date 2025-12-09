# Cerebric Public Documentation Plan

**Purpose**: Transform internal `docs/` (AI planning) into polished public-facing `documentation/` for GitHub release.

**Principle**: The documentation describes **what exists**, not future plans. Written for developers, AI assistants, and potential contributors/acquirers.

**Exclusions**: No macOS content, no monetization, no personas/LoRAs, no user scenarios, minimal research.

---

## Documentation Structure

```
documentation/
├── README.md                    # Documentation index
├── ARCHITECTURE.md              # System design overview
├── INSTALLATION.md              # Getting started guide
├── CONFIGURATION.md             # Configuration reference
├── CLI-REFERENCE.md             # All CLI commands
├── API-REFERENCE.md             # Dashboard REST API docs
│
├── architecture/                # Deep-dive technical docs
│   ├── overview.md              # High-level architecture
│   ├── self-identity.md         # The "computer as self" concept
│   ├── runtime-engine.md        # LangGraph orchestration
│   ├── ingestion-pipeline.md    # Telemetry collection (journald, hwmon)
│   ├── memory-system.md         # RAG and retrieval (ChromaDB)
│   ├── policy-engine.md         # Policy rules and evaluation
│   ├── scheduler.md             # Autonomous task execution
│   ├── approval-system.md       # Human-in-the-loop approvals
│   ├── model-system.md          # LLM integration and routing
│   └── guardrails.md            # Safety and autonomy controls
│
├── guides/                      # How-to guides
│   ├── quickstart.md            # 5-minute setup
│   ├── custom-policies.md       # Writing policy rules
│   ├── dashboard-usage.md       # Using the web dashboard
│   ├── model-selection.md       # Choosing and configuring LLMs
│   └── troubleshooting.md       # Common issues and fixes
│
├── reference/                   # Technical reference
│   ├── code-map.md              # Module → file mapping
│   ├── config-files.md          # All configuration file schemas
│   ├── environment-vars.md      # Environment variable reference
│   ├── data-formats.md          # JSONL schemas, config formats
│   └── xdg-paths.md             # Standard paths (XDG/FHS)
│
├── design/                      # Design philosophy
│   ├── README.md                # Why this section exists
│   ├── philosophy.md            # Core principles (self-identity, grounded AI)
│   ├── research-summary.md      # Condensed research findings (one doc)
│   └── future.md                # Potential future directions
│
├── contributing/                # Contributor guides
│   ├── CONTRIBUTING.md          # How to contribute
│   ├── CODE-STYLE.md            # Python style guide
│   ├── TESTING.md               # Test conventions
│   └── SECURITY.md              # Security policy
│
└── legal/
    ├── LICENSE.md               # GPL-3.0 full text
    └── THIRD-PARTY.md           # Third-party licenses
```

---

## Source Mapping: docs/ → documentation/

| Internal Source (docs/) | Public Target (documentation/) | Transformation |
|-------------------------|--------------------------------|----------------|
| `TRACEABILITY.md` | `reference/code-map.md` | Clean up, remove status markers, add descriptions |
| `FOLDER-STRUCTURE.md` | `reference/xdg-paths.md` | Keep technical content, remove AI instructions |
| `Genesis/0-initial-thoughts.md` | `planning/design-philosophy.md` | Extract principles, remove personal notes |
| `Genesis/PRODUCT-VISION.md` | `planning/design-philosophy.md` | Merge with above |
| `Genesis/TOOL-ROADMAP.md` | `architecture/overview.md` | Tool inventory → module documentation |
| `Phase1/architecture.md` | `architecture/overview.md` | Core architecture section |
| `Phase1/engineering-spec.md` | `architecture/*.md` | Split into topic-specific files |
| `Phase2/policy-engine-spec.md` | `architecture/policy-engine.md` | Technical spec |
| `Phase2/scheduler-spec.md` | `architecture/scheduler.md` | Technical spec |
| `Phase3/ROADMAP.md` | `planning/phase-summary.md` | Completed milestone summary |
| `Phase3/autonomy-guardrails.md` | `architecture/guardrails.md` | Safety documentation |
| `Phase4/persona-system-roadmap.md` | `architecture/persona-system.md` | Persona technical docs |
| `Phase5/README.md` | `architecture/multi-model.md` | Multi-model architecture |
| `QUICK-START.md` | `INSTALLATION.md` | User-facing quickstart |
| `MANAGEMENT-SCRIPTS.md` | `guides/troubleshooting.md` | Script usage |

---

## Audit Checklist

Before any doc is published, verify:

### Code Cross-Reference
- [ ] Every code path mentioned exists in current codebase
- [ ] Function names match actual implementation
- [ ] File paths are accurate
- [ ] CLI commands work as documented

### Content Quality
- [ ] No internal planning language ("TODO", "PLANNED", "GAP")
- [ ] No personal notes or AI conversation artifacts
- [ ] No monetization/business strategy content
- [ ] No macOS-specific content (Linux-only release)
- [ ] Professional, third-person tone
- [ ] Examples are tested and work

### Structure
- [ ] Clear hierarchy with table of contents
- [ ] Consistent formatting (headers, code blocks, lists)
- [ ] Internal links work
- [ ] External links are valid

---

## Priority Order (Implementation Sequence)

### Phase 1: Core Structure ✅ COMPLETE
1. ✅ Create folder structure
2. ✅ `README.md` (documentation index)
3. ✅ `ARCHITECTURE.md` (high-level overview)
4. ✅ `INSTALLATION.md` (getting started)
5. ✅ `CLI-REFERENCE.md` (command reference)
6. ✅ `CONFIGURATION.md` (configuration reference)

### Phase 2: Architecture Deep-Dives ✅ COMPLETE
7. ✅ `architecture/overview.md`
8. ✅ `architecture/self-identity.md`
9. ✅ `architecture/runtime-engine.md`
10. ✅ `architecture/memory-system.md`
11. ✅ `architecture/rag-pipeline.md`
12. ✅ `architecture/tools.md`
13. ✅ `architecture/ingestion-pipeline.md`
14. ✅ `architecture/policy-engine.md`
15. ✅ `architecture/scheduler.md`
16. ✅ `architecture/approval-system.md`
17. ✅ `architecture/guardrails.md`

### Phase 3: Reference Documentation ✅ COMPLETE
18. ✅ `reference/code-map.md`
19. ✅ `reference/data-formats.md`
20. ✅ `reference/xdg-paths.md`

### Phase 4: Guides ✅ COMPLETE
21. ✅ `guides/quickstart.md`
22. ✅ `guides/model-selection.md`
23. ✅ `guides/troubleshooting.md`

### Phase 5: Design & Contributing ✅ COMPLETE
24. ✅ `design/README.md`
25. ✅ `design/philosophy.md`
26. ✅ `design/research-summary.md`
27. ✅ `design/future.md`
28. ✅ `contributing/CONTRIBUTING.md`
29. ✅ `contributing/CODE-STYLE.md`
30. ✅ `contributing/TESTING.md`

### Phase 6: Legal & Final Polish
31. ✅ `legal/LICENSE.md`
32. ✅ `legal/SECURITY.md`
33. ⬜ `legal/THIRD-PARTY.md` (optional)
34. ⬜ Final cross-reference audit
35. ⬜ Link validation

---

## Estimated Effort

| Phase | Documents | Est. Time |
|-------|-----------|-----------|
| Phase 1 | 5 docs | 2-3 hours |
| Phase 2 | 10 docs | 4-6 hours |
| Phase 3 | 5 docs | 2-3 hours |
| Phase 4 | 6 docs | 3-4 hours |
| Phase 5 | 8 docs | 2-3 hours |
| Phase 6 | 4 docs + audit | 2-3 hours |
| **Total** | **38 docs** | **15-22 hours** |

This is substantial documentation work done properly. We can work through it incrementally.

---

## Next Steps

1. Create the folder structure
2. Start with `README.md` as the index
3. Build `ARCHITECTURE.md` from TRACEABILITY + architecture docs
4. Work through priority order above

---

**Status**: Complete (33 documents)  
**Created**: 2025-12-07  
**Updated**: 2025-12-07

## Also Created

- `/README.md` — Main repo README
- `/LICENSE` — GPL-3.0 full text
- `/CHANGELOG.md` — Version history
- `/documentation/API-REFERENCE.md` — Dashboard API
