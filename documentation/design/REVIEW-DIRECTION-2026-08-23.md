# Review: Overall Direction and Planning

**Status:** Completed Senior Architecture & Product Review  
**Reviewer:** Senior Systems Architect & Product Strategist  
**Date:** 2026-08-23  
**Target Architecture:** Halbert Unified Cognitive Host Infrastructure  
**Reads with:** `.handoff/HANDOFF-REVIEW-2026-08-23.md`, `documentation/design/the-being.md`, `documentation/design/explorations.md`, `.handoff/ROADMAP-2026-08-23.md`, `.handoff/IMPLEMENTATION-PLAN-2026-08-23.md`

---

## 1. First Impression & Strategic Evaluation

Halbert's core premise—*"an LLM that identifies as the computer itself is fundamentally more useful than an LLM that merely answers questions about computers"*—is a compelling and timely product concept. The previous drift into a 17-page IT operations dashboard with a chatbot bolted onto the side diluted the core value proposition. The pivot toward **the conversation as the primary container**, backed by **summonable domain modules** and governed by the **Law of Four Whys**, is the right strategic correction.

### What is strong:
1. **The Law of Four Whys:** Framing all system interactions around *Why Now, Why Care, Why So, and Why Trust* provides a strict antidote to LLM hallucinations and alert fatigue.
2. **Sibling Leverage:** Utilizing Haloysius as the agnostic cognitive mind spine and SourcePrep as the awareness/rationale substrate avoids reinventing complex cognitive and retrieval primitives.
3. **The Two-Slice MVP:** Slicing through the entire stack with one proactive loop (config conflict) and one reactive loop ("how are you?") ensures the architecture is verified end-to-end early.

### What needs critical attention:
1. **Long Sequential Critical Path:** The 8-phase linear dependency chain (Phase 0 -> 2 -> 3 -> 4 -> 4.5 -> 5/6 -> 7 -> 8) creates delivery risk. Proactive detectors and why-data models can be decoupled and developed earlier.
2. **Missing Privilege Elevation & OS Security Boundary:** The plan assumes `write_config.py` can modify `/etc/` files seamlessly without detailing the Polkit/sudo privilege boundary in the desktop app.
3. **Tri-Store Synchronization:** Operating SourcePrep, Haloysius `memory_v2`, and SQLite findings concurrently introduces lifecycle boundaries that must be strictly policed.

---

## 2. Scope Assessment

### 2.1 Is the Two-Slice MVP the Right Cut?
**Verdict: Yes, but keep the scope of each slice razor-thin.**

The two slices validate the two fundamental interaction vectors:
- **Slice 1 (Proactive):** Machine initiates -> User reviews & approves change. (Proves autonomous detection, gatekeeping, consequence modeling, blast-radius, and safe write execution).
- **Slice 2 (Reactive):** User initiates -> Machine answers grounded in self-telemetry and summons visual proof. (Proves identity, retrieval grounding, provenance citation, and dynamic UI module summoning).

**Recommendation:** Do not expand either slice beyond the curated 3 detectors (SSHD drop-in, fstab phantom, key permissions) and the 4 initial modules (Config-Diff, Vitals, Storage, Evidence Drawer).

### 2.2 Are We Trying to Do Too Much? (62 Tasks Across 8 Phases)
The task breakdown in `IMPLEMENTATION-PLAN-2026-08-23.md` is thorough, but some tasks can be deferred without compromising the MVP:
- **Defer multi-platform corpus scraping additions:** Freeze doc corpus to Linux + macOS baseline; defer BSD doc expansions until post-Slice 2.
- **Defer complex LOD compression & semantic graph traversals in SourcePrep:** Rely strictly on heading-based markdown chunking, FTS5 + ONNX embeddings, and file-anchored concepts.
- **Simplify Precedence Resolution Engine (Phase 5d):** Focus exclusively on `sshd_config.d` glob ordering and `systemd` drop-in precedence for v1.

### 2.3 Are We Trying to Do Too Little? (Gaps in the Current Plan)
The following missing items must be added to the roadmap:
1. **Privilege Elevation Subsystem:** A secure Polkit / privileged local helper daemon for modifying root-owned `/etc` configs without running the entire FastAPI backend as root.
2. **Notification Secret Scrubbing:** A redaction filter ensuring proactive push notifications never leak credentials or private keys.
3. **Journald Cursor State Persistence:** Persisting log read cursors across daemon restarts to avoid re-triggering historical log alerts.

---

## 3. Sequencing, Parallelism & Critical Path Optimizations

### Current Critical Path:
```
Phase 0 (RAG Corpus) ──> Phase 2 (RAG Consolidation) ──> Phase 3 (Intake Wiring) ──> Phase 4 (chat.py EOL) ──> Phase 4.5 (Gate) ──> Phase 5/6 ──> Phase 7 ──> Phase 8
```

### Proposed Optimized Parallel Path:
```
[Track A: Retrieval & Intake]
Phase 0 (Corpus Ingestion) ──> Phase 2 (SourcePrep RAG) ──┐
Phase 1 (Intake Signals/Budget/Complexity) ───────────────┼──> Phase 3 (Intake Wiring) ──> Phase 4 (chat.py EOL) ──> Phase 4.5 (Boot Gate)
                                                          │                                                                 │
[Track B: Detectors & Why Engine (Unblocked)]             │                                                                 │
Phase 5b/c/d (SQLite Store + 3 Config Detectors) ─────────┘                                                                 │
                                                                                                                            ▼
                                                                                   Phase 7 (Proactive SSE) ──> Phase 8 (Reactive Slices)
```

**Key Sequencing Changes:**
1. **Early Detector Prototyping:** Phase 5c (Config Detectors) and Phase 5b (SQLite Findings Store) can be written as standalone unit-tested Python libraries in parallel with Phase 0/1. They have zero dependency on SourcePrep or Haloysius.
2. **Decouple chat.py Retirement:** Deprecating `chat.py` can happen in parallel with agent path enhancements rather than gating all downstream work.

---

## 4. Architectural Blind Spots & Store Analysis

### 4.1 Tri-Store Separation: SourcePrep vs Memory_v2 vs SQLite Findings
The proposed division of responsibility is clean if maintained strictly:
- **`SQLite` (Transactional / State Engine):** Owns *Actionable Work Items* (Findings, Proposals, Approvals, Snooze Timers, Rollback Manifests).
- **`memory_v2` (Episodic / Haloysius Mind):** Owns *Relational Context* (What the user said, conversation history, user preferences, short-term conversational context).
- **`SourcePrep` (Awareness Substrate & Semantic Graph):** Owns *Static & Semi-Static Grounding* (System documentation, `/etc` snapshots, file-anchored rationale concepts, long-term operational memories).

```
+-----------------------------------------------------------------------------+
|                           TRI-STORE TOPOLOGY                                |
+----------------------+----------------------+-------------------------------+
| Store                | Content              | Lifecycle / Access Pattern    |
+----------------------+----------------------+-------------------------------+
| SQLite               | Findings & Proposals | CRUD, Status transitions, FSM |
| Haloysius memory_v2  | Dialogues & Identity | Turn-based, decay, summarize  |
| SourcePrep           | Docs, Tree, Concepts | Vector search, FTS5, Anchored |
+----------------------+----------------------+-------------------------------+
```

### 4.2 SourcePrep Project Boundaries
- `halbert-knowledge`: Read-only doc corpus (man pages, distro documentation). Re-indexed only on app version upgrade or manual sync.
- `halbert-host`: Live system snapshot tree (`/etc`, systemd units, active discovery scans). Dynamic inotify watcher triggers incremental indexing.
- **Assessment:** This 2-project split is correct. Merging them would cause high I/O churn whenever `/etc` files change.

### 4.3 ChromaDB Retirement Strategy
- Retiring ChromaDB from the live chat/retrieval path is urgent. SourcePrep provides significantly higher precision and trace graph capabilities.
- Retaining ChromaDB solely for legacy eval scripts is acceptable for Phase 2–4, but all ChromaDB code should be purged before Phase 8 release to reduce binary footprint and dependency conflicts.

---

## 5. Missing Categories of Work & Recommendations

### 5.1 Error Handling & Graceful Degradation Strategy
The being must never crash or emit raw stack traces when dependencies fail.
1. **SourcePrep Daemon Offline:** Fall back to direct file inspection via Python `pathlib` + exact grep. Emits message annotation: *"Documentation search unavailable; inspecting live config files directly."*
2. **Local LLM Backend (Ollama/MLX) Out of Memory / Down:** UI switches to a high-visibility status banner with an autonomous service restart button. Rule-based watchers continue functioning.
3. **macOS Sensor Absence:** The system self-model explicitly registers missing telemetry subsystems (`journald_available: false`) and suppresses impossible queries rather than throwing errors.

### 5.2 Observability & Self-Telemetry
Implement a lightweight internal telemetry bus (`HalbertSelfHealth`):
- **Retrieval Precision Score:** Percentage of RAG search results referenced in generated turns.
- **Interruption Efficiency Ratio:** `(Approved + Acknowledged Findings) / Total Dispatched Interrupts`. If ratio drops below 0.6, Halbert suggests increasing proactivity threshold.
- **Cognitive Tick Latency:** Time taken per cognitive phase (Intake -> Retrieval -> Planning -> Execution).

### 5.3 Security Model for Proactive Notifications
- **Desktop Toast Sanitization:** OS notifications must display only high-level categorizations (`"SSH Configuration Hardening Issue"`) and never raw config lines or tokens.
- **Polkit Privilege Engine:** Implement a separate setuid / polkit helper (`halbert-exec`) for executing root-level writes rather than running FastAPI as root.

### 5.4 Testing Pyramid
```
      / \
     /   \     E2E Flow Tests (Tauri + Mocked Local Backend) [5 tests]
    /-----\
   /       \   Integration & Boot Gate Tests (Ubuntu Host & macOS Dev) [15 tests]
  /---------\
 /           \ Retrieval Precision & Grounding Benchmarks (20 queries) [20 tests]
/-------------\
Unit Tests (Signals, Budget, Detectors, Precedence, Parsers) [100+ tests]
```

---

## 6. RAG Corpus Strategy

1. **Quality Over Quantity:** The ~31K raw doc corpus contains duplicates and unformatted man page boilerplate. Aggressively converting to clean, structured markdown with heading metadata (H2 per topic/doc) reduces noise and allows SourcePrep's `chunk_markdown()` to excel.
2. **Size-Bound Split:** Enforcing the 500-doc / 500KB chunk limit per markdown file prevents SourcePrep's 8000-character large-file truncation cutoff.
3. **Cross-Platform Organization:** Grouping into `linux-man-pages/`, `linux-arch-wiki/`, `macos-man-pages/`, and `macos-homebrew/` aligns cleanly with SourcePrep scope filters.

---

## 7. Concrete Adjustments to the Implementation Plan

| Task ID | Recommended Modification | Rationale |
|---|---|---|
| **T0a.1** | Add strict 500KB file splitting to `jsonl_to_markdown.py` | Prevents hitting SourcePrep large file truncation. |
| **T1b.1** | Verify removal of `self_knowledge` column from budget table | Keeps token allocation clean post-ChromaDB. |
| **T4.5** | Add Polkit / privilege elevation check to Boot-Test Gate | Ensures `/etc` write actions work securely on target Ubuntu host. |
| **T5c.1** | Start 3 core detectors immediately in parallel with Phase 0/1 | Unblocks proactive testing early. |
| **T7b.1** | Implement `/api/being/events` SSE with missed event replay | Protects against event loss during sleep/wake cycles. |
| **T8a.1** | Anchor `WhyChip` to SourcePrep concepts and SQLite IDs | Unifies provenance UI across findings and metrics. |

---

## 8. Summary Assessment

**Are we building the right thing?**  
**Yes.** An embodied computational host entity that operates through conversation, justifies every action with the Four Whys, and maintains persistent config memory is a substantial leap forward from traditional passive dashboards.

**Are we building it the right way?**  
**Yes, with the recommended parallelization.** Leveraging Haloysius for cognition and SourcePrep for awareness provides an unfair architectural advantage. By prioritizing the user flows specified in `REVIEW-DESIGN-MECHANICS-2026-08-23.md` and decoupling the detector library build, the team can reach the two proof slices faster with zero architectural debt.
