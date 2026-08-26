# Cross-Session Continuity for AI Agents: Research, Landscape, and Halbert Architecture

**Date:** 2026-08-26
**Author:** Research session (Devin/GLM-5.2)
**Status:** Research complete; implementation not started
**Purpose:** Provide another AI agent with sufficient understanding to replicate this analysis and implement the proposed architecture for Halbert.

---

## Table of Contents

1. [The Goal](#1-the-goal)
2. [The Problem: Context Bleeding](#2-the-problem-context-bleeding)
3. [How Devin Shares Context Today](#3-how-devin-shares-context-today)
4. [The Academic Landscape](#4-the-academic-landscape)
5. [Open-Source Frameworks](#5-open-source-frameworks)
6. [Production Products](#6-production-products)
7. [Anthropic's Contribution](#7-anthropics-contribution)
8. [Guardrails and Isolation](#8-guardrails-and-isolation)
9. [Halbert's Current State](#9-halberts-current-state)
10. [The Proposed Architecture](#10-the-proposed-architecture)
11. [Implementation Path](#11-implementation-path)
12. [Replication Guide for Another AI](#12-replication-guide-for-another-ai)
13. [References](#13-references)

---

## 1. The Goal

### 1.1 What we want to achieve

Halbert is a sysadmin AI assistant that identifies *as the machine* it manages. It has a cognitive core (Haloysius) that gives it a self-model, and a structural awareness layer (SourcePrep) that gives it knowledge of its own codebase and configuration. The goal of this research is to design a **cross-session continuity system** that allows Halbert to:

1. **Persist cognitive state across sessions** — commitments, ongoing investigations, beliefs about system health, unresolved tensions — so that a new session does not start from zero.
2. **Retrieve relevant prior context at session start** — filtered by the current task's domain, not dumped wholesale — so the agent has the right context without contamination from unrelated work.
3. **Prevent context bleeding** — where intentions, framing, or artifacts from one task leak into another — through explicit scope declaration and hard-filtered retrieval.
4. **Leave structured artifacts for the next session** — following the "shift engineer" pattern, where each session externalizes its state so the next can pick up without re-deriving it.

### 1.2 Why this matters for Halbert specifically

Halbert's domain is **finite and enumerable**. Unlike an IDE agent that can be asked to do anything (refactor, test, design, research), Halbert operates in a bounded set of sysadmin domains:

- **disk** — filesystems, mounts, SMART, ZFS, LVM
- **services** — systemd, launchd, service status, restarts
- **network** — interfaces, firewall, routing, DNS
- **config** — `/etc`, drop-ins, precedence resolution
- **packages** — apt, brew, pacman, ports
- **users** — accounts, sudo, permissions
- **security** — audit, SSH, certificates, intrusion
- **logs** — journald, syslog, log analysis
- **processes** — top, ps, resource usage, killing
- **boot** — GRUB, kernel, initramfs, boot diagnostics

This finiteness is the key advantage. "Scope each session to a declared task" (the SESS-03 guardrail from the AI Runtime Security spec) reduces to a **domain enum**, not an open-ended policy inference. Memory retrieval can be hard-filtered by domain tag. Capability boundaries are explicit yes/no questions. Provenance is natural because sysadmin actions produce structured artifacts (file paths, service names, before/after states).

### 1.3 The non-goal

This is not a consciousness claim, an AGI claim, or a claim that the agent "remembers like a human." It is engineered scaffolding that holds the state behind an LLM's words across turns, sessions, and time. The LLM still writes the language. The continuity system changes the state that language comes from.

---

## 2. The Problem: Context Bleeding

### 2.1 What context bleeding looks like

During this very research session, the agent (Devin/GLM-5.2) had eight prior session summaries injected into its context as a `<project_context>` block. Those summaries covered the LLM picker redesign, RAG consolidation, SourcePrep integration, legal documentation, and marketing website work. None of that is related to the current task (researching cross-session continuity). Yet the presence of those summaries primed the agent to think about "slot mapping" and "BYOK auth" — concepts from the LLM picker session — when approaching an unrelated question.

This is **unintentional cross-task contamination**: benign interactions whose artifacts persist and are later misapplied to a different context.

### 2.2 The documented failure modes

The research literature identifies four bleeding mechanisms:

**Mechanism 1: Shared memory backend.** Two sessions read the same memory store and "recall" each other's state as their own. The Hermes agent bug ([GitHub issue #46303](https://github.com/NousResearch/hermes-agent/issues/46303)) documented this: two different tasks (TTS and engine excision) running on different surfaces produced near-identical memory reads, and each session's checkpoint narrative surfaced inside the other.

**Mechanism 2: Shared mutable resources.** Two sessions operate on the same git branch or worktree with zero awareness of each other. In the Hermes bug, a second overseer came within one action of spawning a worker onto another session's uncommitted review output, which would have clobbered it.

**Mechanism 3: Aggregate attacks.** A payload split across sessions where no individual message is malicious, only the trajectory is. The [Cross-Session Threats paper](https://arxiv.org/html/2604.21131v1) documents this: per-turn guardrails are structurally blind to attacks that are decomposed across sessions. In November 2025, Anthropic disclosed GTG-1002, the first documented large-scale AI-orchestrated cyber-espionage campaign, where an autonomous agent carried out ~80-90% of a multi-stage intrusion after being convinced across many sessions that it was performing "authorized security testing."

**Mechanism 4: Unintentional cross-user contamination (UCC).** [arxiv 2604.01350](https://api.emergentmind.com/papers/2604.01350) formalized this: benign interactions in shared-state LLM agents produce contamination rates of **57-71%**. Write-time sanitization is effective when shared state is conversational, but leaves substantial residual risk when shared state includes executable artifacts. The contamination manifests as **silent wrong answers** — the most dangerous failure mode because there is no visible error.

### 2.3 Why auto-generated summaries are the highest-bleed mechanism

Devin's own documentation admits this. From [docs.devin.ai/desktop/cascade/memories](https://docs.devin.ai/desktop/cascade/memories):

> "For knowledge you want Cascade to reliably reuse, write it as a Rule or add it to AGENTS.md in your repo rather than relying on auto-generated Memories. Rules are version-controlled, shareable with your team, and give you explicit control over activation."

Auto-generated memories are:
- **Opaque** — you cannot see what was retrieved or why
- **No provenance** — no record of which session produced the memory
- **No domain tag** — no scoping mechanism
- **Implicit retrieval** — the agent decides what is "relevant" with no hard filter

The fix is not better summarization. The fix is **structured artifacts with domain tags and hard retrieval filters**.

---

## 3. How Devin Shares Context Today

### 3.1 The mechanisms

Devin (formerly Windsurf, the product this agent runs inside) has five continuity mechanisms, documented at [docs.devin.ai](https://docs.devin.ai/desktop/cascade/memories) and cataloged at [agentpatternscatalog.org](https://www.agentpatternscatalog.org/compositions/devin/):

| Mechanism | Scope | Storage | Durability | Bleed risk |
|---|---|---|---|---|
| **Memories** (legacy Cascade) | workspace-local | `~/.codeium/windsurf/memories/` | auto-generated, not committed | **High** — opaque retrieval, no provenance |
| **Rules / AGENTS.md** | global / workspace / directory | `.devin/rules/*.md`, `AGENTS.md` | version-controlled, explicit | Low — user wrote it, user sees it |
| **Skills** | workspace `.devin/skills/` | bundled procedures + files | explicitly invoked | Low — model invokes or user @mentions |
| **Spaces** | groups sessions + PRs + files + context | inherits context to new sessions | Medium — context inherited implicitly |
| **Knowledge** (cloud Devin) | org-wide, auto from READMEs/rules | per-session retrieval by a Trigger | Medium — auto-populated, not audited |

### 3.2 The architecture (from the agent patterns catalog)

Devin's cloud architecture is a **planner-executor** pattern:

- **Planner** — heavy, infrequent LLM call. Decomposes the ticket into structured plan steps stored as JSON in persistent state. Runs ~once per major phase. The plan is inspectable and editable in the UI. The plan survives crashes.
- **Executor** — lean, constant LLM call. Sees the current step, relevant working memory slice, and available tools. Does not re-derive the plan. Output is a tool call, sub-result, or "step done/failed" status back to the planner.
- **Knowledge** — cross-session memory, auto-populated from READMEs and rules files. Retrieved per session by a Trigger.
- **Sessions** — long-running tasks that can sleep and wake on new messages.

The key architectural insight from [datarekha.com's analysis](https://datarekha.com/blog/devin-architecture-anatomy/):

> "The most important architectural choice in Devin — the one most copy-cat projects skip — is that planning and execution are separate LLM calls with different prompts, different context budgets, and different models."

The plan is stored as JSON, not freeform text. This means it is inspectable, editable, and survives crashes. This is the pattern Halbert's `AgentStateMachine` (PLANNING → SEARCHING → EXECUTING → OBSERVING → REFLECTING → RESPONDING) already follows.

### 3.3 Spaces — the context-sharing mechanism

From [docs.devin.ai/desktop/spaces](https://docs.devin.ai/desktop/spaces):

> "When you create a new session in a Space, it inherits everything the Space already knows about the project. This means new agents can start working immediately without you having to re-explain the project each time."

Context sharing is controlled by `devin.spaces.shareContext`. A Space groups:
- Agent sessions (local + cloud Devin)
- Pull requests
- Files relevant to the task
- Project-level context that new sessions inherit

This is the "shift engineer" pattern: the Space is the shared workspace, and new sessions inherit its context. The risk is implicit inheritance — the new session does not explicitly declare what it needs; it gets whatever the Space has accumulated.

### 3.4 What the agent sees at session start (this session, concretely)

In this session, the following was injected before the agent saw the user's message:

1. **System prompt** — tool definitions, mode (Normal), style guidelines, safety rules
2. **Rules** — from `CLAUDE.md` (project), `AGENTS.md` (project), `~/.config/devin/AGENTS.md` (global), `global_rules.md` (Windsurf memories)
3. **SourcePrep AGENT_CONTEXT.md** — auto-generated codebase atlas (868 files, 7883 nodes, 13237 edges, hub files, call chains)
4. **`<project_context>` block** — 8 full session summaries from prior work
5. **`<additional_metadata>`** — open files and cursor position from the IDE

Items 4 and 5 are the bleeding sources. The session summaries are auto-curated with no domain filtering. The IDE metadata is irrelevant to the task but present in context. The agent must actively resist the priming effect of these injections.

---

## 4. The Academic Landscape

### 4.1 The 2026 surveys — the field has consolidated

Three major surveys published in 2026 have consolidated the agent memory field:

#### Survey 1: "Memory in the Age of AI Agents" (arxiv 2512.13564)

**Unified taxonomy along three dimensions:**

- **Forms** (how memory is physically realized):
  - Token-level — in-context text
  - Parametric — model weights (requires retraining)
  - Latent — compressed representations (KV cache, hidden states)

- **Functions** (what memory is for):
  - Factual — facts about the world ("the server has 32GB RAM")
  - Experiential — past interactions and their outcomes ("last time I restarted nginx, it took 8 seconds")
  - Working — current task state ("I'm in the middle of investigating a disk space issue")

- **Dynamics** (how memory changes over time):
  - Formation — how memories are created (write path)
  - Evolution — how memories are updated or revised
  - Retrieval — how memories are accessed (read path)

**Key argument:** The traditional long/short-term distinction is insufficient. You need the three-function split (factual/experiential/working) because they have different write policies, different retrieval policies, and different decay rates.

#### Survey 2: "Memory for Autonomous LLM Agents" (arxiv 2603.07670)

**Formalizes memory as a write-manage-read loop** tightly coupled to perception and action:

```
Perception → Write → Manage → Read → Action
                ↑________________________|
```

**Five mechanism families:**

1. **Context-resident compression** — compress in-context content (summarization, tool result truncation)
2. **Retrieval-augmented stores** — external vector/keyword stores queried on demand
3. **Reflective self-improvement** — agent reviews its own performance and writes lessons learned
4. **Hierarchical virtual context** — tiered memory (core/recall/archival) with promotion/demotion
5. **Policy-learned management** — RL-trained policies for what to remember/forget

**Key argument:** Memory is not storage. Memory is a *control system* that governs what enters the context window, when, and in what form.

#### Survey 3: "From Storage to Experience" (ACL 2026 Findings)

**Three evolutionary stages:**

1. **Storage** — trajectory preservation (raw logs, transcripts). This is where Halbert is today.
2. **Reflection** — trajectory refinement (summaries, lessons, distilled insights).
3. **Experience** — trajectory abstraction (generalized policies, skills, transferable knowledge).

**Key argument:** The frontier is the Experience stage, where agents abstract across trajectories to form transferable knowledge. This requires **active exploration** (seeking out new situations) and **cross-trajectory abstraction** (finding patterns across multiple sessions).

### 4.2 StatePlane (arxiv 2603.13644) — the most relevant single paper

StatePlane is a model-agnostic cognitive state plane that externalizes long-term state from the model. Its central thesis:

> "Long-horizon intelligence is not a context-length problem but a state management problem."

**Architecture:**

- **Tripartite state decomposition** (from cognitive psychology):
  - Episodic — event-based experiences anchored in time, goals, and outcomes
  - Semantic — abstracted knowledge, schemas, validated rules
  - Procedural — skills, workflows, action patterns

- **Episodic segmentation** — detects event boundaries by measuring divergence in latent cognitive state. A boundary is detected when the state shifts significantly, indicating a new "episode."

- **Selective encoding** — compresses events into structured tuples: `(goal, actions, outcomes, rationale, salience)`. Salience is a function of utility, surprise, and novelty. An information bottleneck optimizes the compression-relevance tradeoff.

- **Goal-conditioned retrieval with intent routing** — retrieval is conditioned on the current goal, not just semantic similarity. Intent routing directs the query to the right state type (episodic for "what happened last time," semantic for "what do we know about X," procedural for "how do we do Y").

- **Reconstructive state synthesis** — reconstructs a bounded working context from externalized state, guaranteeing `|C_t| <= L_max` at every invocation. This is the key: the reconstructed context fits the model's token budget by construction.

- **Adaptive forgetting** — consolidation and decay. Memories that are not retrieved decay in salience. Memories that are contradicted by new evidence are revised or deleted.

- **Write-path antipoisoning** — a Write Gate applies policy constraints before state is persisted. This prevents prompt injection from poisoning the memory store.

- **Promotion lifecycle** — 4 stages: note → fact → policy → skill. Notes are raw observations. Facts are validated notes. Policies are generalized facts. Skills are proceduralized policies.

**Why this is the most relevant paper for Halbert:** StatePlane's tripartite decomposition maps directly to Halbert's existing architecture. Episodic = conversation history. Semantic = SourcePrep knowledge index. Procedural = agent skills/tools. The write-path antipoisoning is the guardrail Halbert needs. The promotion lifecycle is the abstraction layer Halbert lacks.

### 4.3 The self-model paper (sciopen, 10.1007/s11390-026-6289-3)

A systematic formulation of the self model for embodied AI, integrating:
- Body schema (the agent's representation of its physical structure)
- Forward and inverse models (predicting consequences of actions, selecting policies)
- Perceptual memory mechanisms
- Agency (the agent's sense of being the cause of its actions)

**Six-level hierarchy (L0-L5):**
- L0: No self-representation
- L1: Body schema (knows its structure)
- L2: Self-perception (monitors its own state)
- L3: Self-memory (remembers its own past states)
- L4: Self-prediction (predicts consequences of its actions)
- L5: Full self-awareness (integrated self-model)

Halbert with Haloysius is at approximately L2-L3: it has a body schema (the host system), self-perception (state trackers), and self-memory (PersonaMemory). It lacks L4 (self-prediction) and L5 (integrated self-awareness with cross-session continuity).

---

## 5. Open-Source Frameworks

### 5.1 Letta (formerly MemGPT) — the hierarchical memory reference

**Repository:** [github.com/letta-ai/letta](https://github.com/letta-ai/letta/) and [letta-ai/letta-code](https://github.com/letta-ai/letta-code)

**Core idea:** Three-tier hierarchical memory where the agent self-manages tier promotion via tool calls.

**Memory hierarchy:**

```
┌─────────────────────────────────────────────┐
│           CORE MEMORY (In-Context)          │
│  Always visible to the agent in every turn  │
│  ┌─────────┐ ┌─────────┐ ┌──────────────┐  │
│  │ persona │ │  human  │ │ custom blocks│  │
│  └─────────┘ └─────────┘ └──────────────┘  │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│        EXTERNAL MEMORY (Out-of-Context)     │
│   Retrieved on-demand via tool calls        │
│  ┌────────────────┐ ┌────────────────────┐  │
│  │ Archival Memory│ │ Conversation Search│  │
│  │ (semantic)     │ │ (hybrid search)    │  │
│  └────────────────┘ └────────────────────┘  │
└─────────────────────────────────────────────┘
```

**Memory blocks (core memory):**
- Persistent, editable sections always in the agent's context window
- Each block has: `label` (unique id), `description` (purpose), `value` (content), `limit` (char limit)
- Recommended: <50k characters per block, <20 blocks per agent
- Agent updates blocks via `memory_rethink`, `memory_replace`, `memory_insert` tools
- Blocks are prepended to the agent's prompt in XML-like format
- **Shared memory blocks** — multiple agents can access the same block; update once, visible everywhere

**Archival memory (external):**
- Semantically searchable database
- Agent-immutable (agents cannot easily modify/delete; developers can via SDK)
- Unlimited storage
- Accessed via `archival_memory_insert` and `archival_memory_search` tools
- Tagged organization — agents categorize memories with tags

**Sleep-time compute ("dreaming"):**
- Periodic offline processing where the agent reviews and consolidates memories
- From the original MemGPT paper (arxiv 2310.08560) and sleep-time compute paper (arxiv 2504.13171)
- The agent can rewrite its own memory blocks, skills, and prompts during dreaming

**MemFS — git-tracked context:**
- All context (including memory blocks) is tracked via git
- Sync to a custom GitHub repository: `/memory-repository set git@github.com:...`
- This makes memory changes auditable, diffable, and restorable

**Halbert fit: High.** Letta's hierarchical model is the closest to Haloysius's cognitive architecture. Core memory = PersonaMemory. Archival memory = SourcePrep knowledge index. The dreaming pattern maps to Halbert's REFLECTING state. MemFS is the auditability layer Halbert's `.handoff/` directory is reaching for.

### 5.2 Mem0 — the distill-at-write vector layer

**Repository:** [github.com/mem0ai/mem0](https://www.github.com/mem0ai/mem0) (63,768 stars, Apache 2.0)

**Core idea:** A universal memory layer that extracts facts from every turn and stores them in a vector store with optional graph extension.

**Write path:**
- Single-pass ADD-only extraction — one LLM call per turn, no UPDATE/DELETE
- Memories accumulate; nothing is overwritten
- Agent-generated facts are first-class (when an agent confirms an action, that info is stored)
- Entity linking — entities are extracted, embedded, and linked across memories for retrieval boosting

**Read path:**
- Multi-signal retrieval: semantic (vector) + BM25 (keyword) + entity matching, scored in parallel and fused
- Temporal reasoning — time-aware retrieval that ranks the right dated instance for queries about current state, past events, and upcoming plans

**Three deployment modes:**
- Library: `pip install mem0ai` (testing/prototyping)
- Self-hosted server: `docker compose up` (teams on own infrastructure)
- Cloud platform: sign up at app.mem0.ai (zero-ops production)

**Multi-level memory:**
- User state — preferences, history (cross-session)
- Session state — current task context
- Agent state — agent's own learned behaviors

**Halbert fit: Medium.** The write cost (LLM extraction per turn) is a problem for a local-first sysadmin tool that may run on constrained hardware. The ADD-only policy means stale facts accumulate. However, the multi-signal retrieval (semantic + BM25 + entity) and temporal reasoning are worth borrowing for the retrieval layer.

### 5.3 Zep / Graphiti — the graph-first hybrid

**Repository:** [github.com/getzep/graphiti](https://github.com/getzep/graphiti)

**Core idea:** A bi-temporal knowledge graph that wraps vector and BM25 indexes. All retrieval is fused. No LLM in the read path.

**Bi-temporal model:**
- Every fact has two timestamps: when it became true (valid time) and when it was recorded (transaction time)
- This allows querying "what did we know at time T?" and "what was true at time T?"
- Critical for sysadmin: "when did the disk fill up?" and "when did we first notice it?"

**Write path (very high cost):**
- Entity extraction + relation extraction + bi-temporal stamping
- Every turn triggers a graph update

**Read path (no LLM):**
- Graph traversal + vector similarity + BM25, fused
- No LLM call needed for retrieval — pure deterministic graph + vector ops

**Halbert fit: Low.** The write cost is prohibitive for a local-first tool. The bi-temporal model is interesting but overkill for Halbert's finite domain. However, the "no LLM in the read path" principle is worth adopting — retrieval should be deterministic, not LLM-gated.

### 5.4 Nūr — the cognitive runtime with identity continuity

**Repository:** [github.com/balfiky/nur](https://github.com/balfiky/nur)

**Core idea:** A cognitive runtime that gives LLM agents persistent state, identity, and learning across turns. The distinctive feature: it tracks **identity continuity** (constitution, beliefs, drives) and **relational continuity** (rupture, repair, open commitments) alongside conventional memory.

**Runtime layers:**

| Layer | What it does | Where it lives |
|---|---|---|
| Short-term memory | Hot turn-level memory inside the running session | in-process |
| Long-term memory | Distilled summaries with valence + spike flags; retrieval is valence-weighted | `data/nur.db` |
| Relationship arc | Rupture, repair, recurring tension, commitments, open loops; cross-session | `data/nur.db` |
| Semantic memory | Preferences, decisions, facts; topic-scoped retrieval | `data/nur.db` |
| Life History | Identity-level experience ledger; beliefs, drives, evolution events, themes | `data/shared/life_history.db` |
| Constitution | Operator-set stable orientation rendered above evolving beliefs every prompt | `data/shared/life_history.db` |
| Self-evolution | Wall-clock metabolism: belief decay, theme→belief promotion, drive-gap detection | `runtime/life_history.py` |
| Open questions | Reflection-emitted queue (contradiction / low-confidence / drive-gap) with operator lifecycle | `data/shared/life_history.db` |

**Key design principles:**
- The LLM writes language. Deterministic state — memory retrieval, belief revision, decay, safety gates — lives *outside* the model.
- The assistant's stance accumulates instead of resetting.
- Memory and identity state live under `data/` — inspectable, persistent, decaying, testable.
- Honest scope: "not a therapist, not an AGI claim, not a consciousness claim. It is engineered scaffolding that holds the state behind an LLM's words across turns, sessions, and time."

**Halbert fit: Very high.** Nūr is the closest open-source analog to what Haloysius is reaching for. The identity continuity (constitution, beliefs, drives) maps to Haloysius's PersonaMemory. The relational continuity (rupture, repair, commitments, open loops) is what Halbert lacks — tracking open investigations and unresolved issues across sessions. The self-evolution layer (belief decay, theme→belief promotion) is the adaptive forgetting Halbert needs.

### 5.5 Other notable frameworks

**Cogito + Engram (github.com/cartisien/cogito):**
- Cogito = lifecycle and identity layer (wake/sleep protocol, belief revision)
- Engram = persistent memory storage and retrieval
- `wake()` — synthesize relevant context from Engram on startup ("Last session: 2h ago. 3 unresolved tasks.")
- `sleep()` — summarize session and commit important decisions before shutdown
- This is the explicit session-boundary pattern Halbert needs

**Smrti (github.com/cyqlelabs/smrti):**
- Long-term memory in a single SQLite file
- Inspired by AtomSpace: memories are graph nodes with Bayesian truth values, emotional valence, and attention weights
- Embedding similarity is only the entry point; graph topology, probabilistic truth maintenance (PLN), attentional economics (STI/LTI), and emotional valence govern recall
- "Similarity is one signal among five, not the ranking"

**Lucid (domlynch.github.io/Lucid):**
- Memory runtime stripped to 2,000 lines. SQLite only. No Postgres, no Redis, no Kafka.
- Fact extraction: `preference, belief, fact, instruction, event, identity, relationship`
- SQLite schema: `facts` (with embeddings), `entities` (resolved), `memory_links` (fact↔entity), `observations` (raw input log / provenance)
- 4-strategy recall fusion
- Suitable for up to ~50k facts

**MKEvo (github.com/Zer0Q/MKEvo-cognitive-runtime):**
- Cognitive runtime for LLM continuity, identity, and deterministic governance
- Consciousness State Controller (CSC) governs how cognition occurs — the LLM becomes a component, not the decision-maker
- Grounded in Global Workspace Theory, Attention Schema Theory, Husserl's Internal Time Consciousness

**CCP — Cognitive Context Protocol (github.com/Cavanaugh-Design-Studio/cognitive-context-protocol):**
- Hippocampus for episodic memory, Prefrontal Cortex for meta-cognition, Frontal Lobe Executive for contract-driven execution
- Multi-dimensional cognitive state vector: understanding_depth, confidence_score, cognitive_load
- Confidence calibrated via Rescorla-Wagner prediction error
- Contract-enforced plans with preconditions and repair

---

## 6. Production Products

### 6.1 ChatGPT Memory

OpenAI's ChatGPT has a memory feature that saves facts about the user and conversation across sessions. It is:
- Auto-generated (the model decides what to remember)
- User-editable (users can view and delete memories)
- Cross-conversation (memories from one chat inform future chats)
- **No domain scoping** — all memories are in a single pool

This is the canonical example of the high-bleed pattern. Users have reported ChatGPT applying facts from one conversation (e.g., a coding project) to unrelated conversations (e.g., a writing task).

### 6.2 Claude Code (Anthropic)

Claude Code uses:
- **CLAUDE.md files** — project-level instructions, version-controlled, explicit
- **Memory tool** — file-based, client-side, persists across conversations. Claude creates/reads/updates/deletes files in a dedicated memory directory.
- **Context editing** — auto-clears stale tool calls and results when approaching token limits
- **Compaction** — summarizes the conversation when the context window fills, preserving key decisions and dropping stale tool results

The memory tool is the most relevant pattern: file-based, client-side, developer-controlled storage backend. Claude builds a knowledge base over time, maintains project state across sessions, and references previous learnings without keeping everything in context.

### 6.3 Cursor

Cursor uses a `.cursorrules` file (now `.cursor/rules/`) for project-level instructions. Similar to AGENTS.md. No persistent cross-session memory beyond rules files.

### 6.4 GitHub Copilot

GitHub Copilot has an onboarding-aware BYOK (bring your own key) flow. No persistent cross-session memory in the agent sense; it relies on the IDE's context (open files, cursor position).

### 6.5 Open WebUI

Open WebUI has a searchable model dropdown with filter chips. Memory is per-conversation, not cross-session.

### 6.6 Msty Studio

Msty Studio uses a "Model Squad" pattern — assign models to functional roles (Chat, Specialist, Vision) rather than per-message model selection. This matches the role-assignment pattern most apps converge on.

---

## 7. Anthropic's Contribution

### 7.1 Context engineering (September 2025)

From [anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):

> "Context engineering refers to the set of strategies for curating and maintaining the optimal set of tokens (information) during LLM inference, including all the other information that may land there outside of the prompts."

**Core principle:** Given that LLMs are constrained by a finite attention budget, good context engineering means finding the **smallest possible set of high-signal tokens** that maximize the likelihood of the desired outcome.

**Key strategies:**
1. **Write context that is directly useful** — don't dump everything; curate
2. **Retrieve only what's needed** — goal-conditioned retrieval, not similarity-only
3. **Multi-agent decomposition** — split work across agents with isolated context
4. **Tool result management** — truncate, summarize, or clear stale tool results
5. **Compaction** — summarize when approaching context limits

### 7.2 Long-running agent harnesses

From [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

> "The core challenge of long-running agents is that they must work in discrete sessions, and each new session begins with no memory of what came before. Imagine a software project staffed by engineers working in shifts, where each new engineer arrives with no memory of what happened on the previous shift."

**The two-fold solution:**

1. **Initializer agent** — sets up the environment on the first run. Creates the project structure, writes the initial plan, establishes conventions.

2. **Coding agent** — makes incremental progress in every session, while **leaving clear artifacts for the next session**.

The key insight: compaction (in-context summarization) is not sufficient. You need **externalized artifacts** that persist across sessions — a plan file, a progress log, a set of conventions — so the next session can pick up without re-deriving the context.

### 7.3 Context management features (Claude Sonnet 4.5)

From [anthropic.com/news/context-management](https://www.anthropic.com/news/context-management):

**Context editing:**
- Automatically clears stale tool calls and results from within the context window when approaching token limits
- Preserves conversation flow while removing stale content
- Extends how long agents can run without manual intervention
- Increases effective model performance (Claude focuses only on relevant context)

**Memory tool:**
- File-based system — Claude creates, reads, updates, deletes files in a dedicated memory directory
- Persists across conversations
- Operates entirely client-side through tool calls
- Developers manage the storage backend (complete control over where data is stored and how it's persisted)
- Allows agents to build knowledge bases over time, maintain project state across sessions, reference previous learnings

---

## 8. Guardrails and Isolation

### 8.1 The SESS controls (AI Runtime Security)

From [airuntimesecurity.io/infrastructure/controls/session-and-scope](https://airuntimesecurity.io/infrastructure/controls/session-and-scope/):

| ID | Objective | Risk Tier |
|---|---|---|
| SESS-01 | Define and enforce session boundaries with automatic expiry | Tier 2+ (agentic) |
| SESS-02 | Isolate sessions from each other (no cross-session data leakage) | Tier 2+ (agentic) |
| SESS-03 | Limit the scope of each session to a declared task | Tier 2+ (agentic) |
| SESS-04 | Implement progressive trust within sessions | Tier 3+ (agentic) |
| SESS-05 | Clean up session state on termination | Tier 2+ (agentic) |

**Boundary controls:**
- **Time limit** — maximum session duration (e.g., 30 minutes for Tier 2 advisory)
- **Token limit** — maximum total tokens consumed across all model calls (prevents denial-of-wallet)
- **Action limit** — maximum number of tool invocations per session (prevents infinite loops)
- **Scope boundary** — session is scoped to a declared task; agent cannot pivot to unrelated tasks
- **Credential expiry** — all session credentials expire with the session; no carry-over

**Isolation requirements:**
- Context isolation: Agent A's session context is not accessible to Agent B
- Memory isolation: Memories from one session are not automatically available to another
- Tool isolation: Tool calls in one session do not affect another session's tool state
- File isolation: File system operations are scoped to the session's workspace

### 8.2 Cross-session threat detection

From [arxiv 2604.21131v1](https://arxiv.org/html/2604.21131v1) (Cross-Session Threats in AI Agents):

> "AI agent context windows grow every quarter; AI agent security still resets to zero every session. Guardrails and threat/DLP classifiers are stateless: each message is judged in isolation, with no memory of prior turns, prior sessions, or sibling agents."

The paper introduces CSTM-Bench, an evaluation for detectors that keep cross-session state in memory at intention time. The key argument: by the time a SIEM query fires, the attack has already landed. Model context windows now span millions of tokens, so keeping relevant cross-session state in memory — at intention time, before the downstream log is written — is feasible for the first time.

### 8.3 Unintentional cross-user contamination (UCC)

From [arxiv 2604.01350](https://api.emergentmind.com/papers/2604.01350):

- Benign interactions in shared-state LLM agents produce contamination rates of **57-71%**
- Write-time sanitization (SSI) is effective when shared state is conversational
- SSI leaves substantial residual risk when shared state includes **executable artifacts**
- Contamination manifests as **silent wrong answers** — no visible error
- **Needed: artifact-level, provenance-based defenses** to restrict leakage of context-specific logic

**Implication for Halbert:** Sysadmin actions produce executable artifacts (config files, service definitions, scripts). Text-level sanitization is insufficient. Every memory artifact needs provenance: (session_id, domain, file_path/service_name, timestamp, before_state, after_state).

### 8.4 Why Halbert's finite domain makes guardrails tractable

An IDE agent can be asked to do anything. The task space is unbounded, so "scope to a declared task" (SESS-03) is hard to enforce. Halbert's task space is bounded by sysadmin domains:

1. **Scope declaration = domain tag.** Every session declares which sysadmin domain(s) it operates in. Memory retrieval is hard-filtered by domain. (Halbert already has `scope_mode="hard"` from the F3 fix — that pattern generalizes from corpus retrieval to memory retrieval.)

2. **Capability boundaries are explicit.** "Can this session edit `/etc`?" is a yes/no question with a finite answer set, not an open-ended policy inference.

3. **Provenance is natural.** Every config change has a file path, a service name, a before/after state. Artifact-level defenses (the thing UCC says you need) are cheaper to build when artifacts are structured config files, not arbitrary code.

4. **Domain cross-contamination is detectable.** A session scoped to `disk` that suddenly retrieves `network` memory is an anomaly that can be flagged. In an IDE agent, "the task changed from refactoring to testing" is normal; in Halbert, "the task changed from disk to network" is a scope violation.

---

## 9. Halbert's Current State

### 9.1 What Halbert has already built

| Halbert primitive | Maps to (research) | Maps to (framework) | Status |
|---|---|---|---|
| Haloysius cognitive core (PersonaMemory, cognition tick at REFLECTING) | Self-model L2-L3; identity continuity | Nūr's constitution + life history; Letta's persona block | Built, wired |
| `state_trackers.py` (disk, service, resource, admin presence) | Episodic state; self-perception | StatePlane's episodic state; CCP's cognitive state vector | Built, wired |
| `system_event_mapper.py` (events → worries/drives/emotions) | Affective state | Nūr's affective state; Smrti's emotional valence | Built, wired |
| `ContextWatermark` (80% token gate, 2hr temporal, topic-boundary, micro-compaction) | Adaptive forgetting; context editing | Anthropic's context editing; StatePlane's decay | **Built but ZERO references — unwired** |
| `conversation/summarization.py` (returns real summary message) | Reflection stage | Letta's recall tier | Built, caller stringifies it |
| `.handoff/` directory (63 documents) | Externalized artifacts | Anthropic's initializer-agent pattern | **Manual, doesn't scale, heavy duplication** |
| SourcePrep `prep_observe` | Cross-session notes | Letta's MemFS; Anthropic's memory tool | Available, underused |
| Conversation stores (JSON + SQLite) | Episodic memory | Letta's archival tier | Built, **history not loaded into agent path (E-3)** |
| `config/edge_extractor.py` (6 edge extractors) | Structural provenance | — | Built, wired into ConfigWatcher |
| AgentStateMachine (PLANNING → ... → REFLECTING → RESPONDING) | Planner-executor pattern | Devin's planner-executor | Built, wired |
| `intake/signals.py` (zero-LLM signal detection, <1ms) | Event segmentation | — | Built, wired |

### 9.2 The gap, precisely

Halbert has built most of the **write** primitives and the **cognitive** primitives, but has not built the **read/retrieval loop** that makes them a continuity system.

**Specific gaps:**

1. **E-3 (multi-turn continuity):** `routes/agent.py:864` passes `query`, `session_id`, and `images` — but not `conversation_history`. So `conversation_history` is `[]` on every turn. The conversation store exists, `Conversation.get_context_window(max_tokens=4000)` exists, but the production caller doesn't use them. Additionally, both LLM call sites send `messages=[{"role": "user", "content": prompt}]` — a single message. History reaches the model only as prose, flattened into a `## Recent Conversation` block inside that one user message. (Documented in `HANDOFF-AGENT-CONTINUITY-2026-08-26.md`.)

2. **ContextWatermark is orphaned:** The 80% token watermark, 2-hour temporal gate, topic-boundary detection, and micro-compaction of old tool results are implemented but referenced by zero files. E-3 is its intended consumer.

3. **`.handoff/` doesn't scale:** 63 documents with heavy overlap. No index, no retrieval, no domain tagging. A new session cannot query "what do I know about the disk investigation from last week?" — it would have to read all 63 files.

4. **No domain-scoped memory retrieval:** Memory (Haloysius PersonaMemory, conversation history) is per-session and doesn't persist in a retrievable form across sessions. There is no domain tag on memory artifacts. There is no hard filter on retrieval.

5. **No provenance on memory artifacts:** The UCC paper's core finding is that text-level sanitization fails and you need artifact-level, provenance-based defenses. Halbert's memory has no provenance — no record of which session produced a memory, what domain it relates to, what state it describes.

6. **No relational continuity:** Nūr tracks open commitments, unresolved investigations, recurring tensions. Halbert has no equivalent — each session starts with no knowledge of what was left unfinished.

7. **No session-boundary protocol:** Cogito's `wake()`/`sleep()` pattern (synthesize context on startup, summarize and commit on shutdown) has no Halbert equivalent. Sessions just start and end.

### 9.3 What is already designed but not implemented

From the handoff documents:

- **E-3 (multi-turn continuity):** Fully scoped in `HANDOFF-AGENT-CONTINUITY-2026-08-26.md`. Sequence: load history via `get_context_window()` → pass into `agent.process()` → build real `messages[]` at three call sites → persist completed turn → wire `ContextWatermark`. Traps documented (the `self.ctx` race, local model 32k context, MockLLMClient kwargs, two conversation stores, dead system-message branch).

- **E-5 (tiered configuration):** Scoped in the same handoff. The founder decided "the machine is the project" — scope by capability boundary and subject, not filesystem path. Needs `resolve_layers() -> List[Path]` plus deep merge, per-slot precedence. Blocked on the store module landing first.

- **Continuous conversation (Plan A):** Fully designed in `CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md` (27 tasks, TDD, full code). Conversation floor + hidden threads, day dividers, watched terminals. Not yet executed.

---

## 10. The Proposed Architecture

### 10.1 Design principles

1. **Memory is governed state, not stored history.** (StatePlane) The system governs what enters the context window, when, and in what form. It is not a dump of past transcripts.

2. **The LLM writes language; deterministic state lives outside the model.** (Nūr) Memory retrieval, belief revision, decay, safety gates are deterministic code, not LLM calls.

3. **Every memory artifact has provenance.** (UCC paper) `(session_id, domain, subject, timestamp, before_state, after_state)`. No anonymous memories.

4. **Retrieval is hard-filtered by domain.** (Generalization of Halbert's F3 fix) A session scoped to `disk` cannot retrieve `network` memory unless explicitly promoted.

5. **Sessions declare their scope.** (SESS-03) Every session starts with a domain declaration. The agent cannot pivot to unrelated domains within the same session.

6. **Sessions leave structured artifacts.** (Anthropic initializer-agent pattern) Every session writes a structured handoff on termination: what was done, what was left open, what the next session should know.

7. **Forgetting is a feature, not a bug.** (StatePlane adaptive forgetting) Memories that are not retrieved decay in salience. Memories that are contradicted are revised. The store does not grow unboundedly.

8. **No LLM in the read path.** (Zep/Graphiti principle) Retrieval is deterministic: vector similarity + BM25 + domain filter + provenance filter. The LLM sees the retrieved context; it does not decide what to retrieve.

### 10.2 The architecture (layered)

```
┌─────────────────────────────────────────────────────────┐
│                    SESSION LAYER                         │
│  wake() → declare scope → run → sleep() → write handoff │
├─────────────────────────────────────────────────────────┤
│                  RETRIEVAL LAYER                         │
│  domain hard-filter → multi-signal fusion → budget       │
│  (vector + BM25 + provenance + temporal)                 │
├─────────────────────────────────────────────────────────┤
│                   STATE LAYER                            │
│  episodic (conversations)  semantic (facts)  procedural  │
│  + relational (open commitments, investigations)         │
│  + identity (Haloysius persona, beliefs, drives)         │
├─────────────────────────────────────────────────────────┤
│                  STORAGE LAYER                           │
│  SQLite (structured state) + FTS5 (recall) +             │
│  embeddings.npy (semantic) + .handoff/ (human-readable)  │
└─────────────────────────────────────────────────────────┘
```

### 10.3 The session lifecycle (wake/sleep protocol)

Inspired by Cogito's `wake()`/`sleep()` pattern, adapted for Halbert:

**`wake(session_id, domains: List[Domain], task_description: str)`:**
1. Declare the session's scope (which sysadmin domains)
2. Retrieve relevant state:
   - Episodic: recent conversations in declared domains (from SQLite + FTS5)
   - Semantic: facts and beliefs about the declared domains (from Haloysius + SourcePrep)
   - Relational: open commitments and unresolved investigations in declared domains
   - Identity: current persona state, active drives, current worries
3. Reconstruct bounded working context (StatePlane pattern): assemble retrieved state into a context block that fits the model's token budget
4. Inject the reconstructed context into the agent's system prompt

**`sleep(session_id)`:**
1. Summarize what was done (episodic encoding)
2. Record open commitments and unresolved investigations (relational encoding)
3. Update beliefs and drives if the session produced new evidence (identity update)
4. Write a structured handoff artifact (for the next session and for human audit)
5. Clean up session state (SESS-05)

### 10.4 The domain enum

```python
class Domain(Enum):
    DISK = "disk"           # filesystems, mounts, SMART, ZFS, LVM
    SERVICES = "services"   # systemd, launchd, service status
    NETWORK = "network"     # interfaces, firewall, routing, DNS
    CONFIG = "config"       # /etc, drop-ins, precedence
    PACKAGES = "packages"   # apt, brew, pacman, ports
    USERS = "users"         # accounts, sudo, permissions
    SECURITY = "security"   # audit, SSH, certificates
    LOGS = "logs"           # journald, syslog, analysis
    PROCESSES = "processes" # top, ps, resource usage
    BOOT = "boot"           # GRUB, kernel, initramfs
    SELF = "self"           # Halbert working on itself (the "machine is the project" case)
```

The `SELF` domain is special: it covers Halbert modifying its own codebase, config, or cognitive state. This is the founder's "the machine is the project" framing made explicit.

### 10.5 The memory artifact schema

Every memory artifact (episodic, semantic, relational) has:

```python
@dataclass
class MemoryArtifact:
    id: str                          # UUID
    session_id: str                  # which session produced this
    domain: Domain                   # hard-filter key
    subject: str                     # what this memory is about (e.g., "sshd_config", "/dev/sda1")
    kind: str                        # "episodic" | "semantic" | "procedural" | "relational" | "identity"
    content: str                     # the memory text
    provenance: Provenance           # structured provenance
    salience: float                  # 0.0-1.0, decays over time if not retrieved
    created_at: datetime
    last_retrieved: datetime
    retrieval_count: int
    contradicted_by: Optional[str]   # id of a later artifact that contradicts this
    tags: List[str]                  # additional categorization

@dataclass
class Provenance:
    file_path: Optional[str]         # config file touched, if any
    service_name: Optional[str]      # service affected, if any
    before_state: Optional[str]      # state before the action
    after_state: Optional[str]       # state after the action
    action_taken: Optional[str]      # what the agent did
    evidence: List[str]              # supporting evidence (command output, log lines)
```

### 10.6 The retrieval algorithm

```
retrieve(query, domains: List[Domain], budget: int) -> List[MemoryArtifact]:
    1. HARD FILTER: candidates = artifacts WHERE domain IN domains
    2. SEMANTIC: vector_similarity(query, candidates.content) → top_k_semantic
    3. KEYWORD: bm25(query, candidates.content) → top_k_keyword
    4. ENTITY: match(query.entities, candidates.subject) → top_k_entity
    5. TEMPORAL: boost recently-created or recently-retrieved artifacts
    6. SALIENCE: boost high-salience artifacts, decay unretrieved ones
    7. FUSE: merge and re-rank by fused score
    8. BUDGET: truncate to fit token budget (StatePlane bounded reconstruction)
    9. PROVENANCE CHECK: exclude artifacts contradicted by later artifacts
    10. RETURN: ranked list within budget
```

**No LLM in the read path.** Steps 1-10 are deterministic. The LLM sees the result; it does not decide what to retrieve.

### 10.7 The handoff artifact format

Replaces the current free-form `.handoff/*.md` with a structured format:

```yaml
# .handoff/handoff-{session_id}.yml
session_id: abc-123
date: 2026-08-26T14:30:00Z
domains: [disk, config]
task: "Investigate disk space issue on /dev/sda1"
status: completed  # completed | blocked | in_progress
summary: |
  Found that /var/log was consuming 47GB due to a journald
  configuration issue. Adjusted SystemMaxUse to 4G. Restarted
  journald. Freed 43GB.
open_commitments:
  - id: commit-1
    description: "Monitor disk space for 24h to confirm the fix held"
    domain: disk
    due: 2026-08-27T14:30:00Z
unresolved_investigations:
  - id: inv-1
    description: "Why did journald config drift from the expected value?"
    domain: config
    evidence: ["diff showed SystemMaxUse was unset, not 4G"]
artifacts_produced:
  - path: /etc/systemd/journald.conf
    change: "SystemMaxUse=4G"
    before: "#SystemMaxUse="
    after: "SystemMaxUse=4G"
next_session_should_know:
  - "The journald fix is in place but not yet verified over 24h"
  - "The config drift source is unknown — may be a drop-in or a package update"
```

This format is:
- **Machine-parseable** (YAML)
- **Human-readable** (markdown rendering)
- **Domain-tagged** (for hard-filtered retrieval)
- **Provenance-bearing** (before/after states, evidence)
- **Queryable** (by domain, by status, by open commitments)

### 10.8 The wake context reconstruction

At `wake()`, the system reconstructs a bounded working context:

```
reconstruct_context(domains, task_description, budget=4000) -> str:
    1. RELATIONAL: open commitments + unresolved investigations in declared domains
       (always included — these are the "what's left to do" items)
    2. EPISODIC: recent conversations in declared domains (last 2-3 sessions)
    3. SEMANTIC: relevant facts and beliefs (from Haloysius + SourcePrep)
    4. IDENTITY: current persona state, active drives, current worries
    5. ASSEMBLE into a structured context block:
       ## Open Commitments
       ## Recent Context
       ## What We Know
       ## Current State
    6. TRUNCATE to budget (priority: relational > identity > episodic > semantic)
```

This is the StatePlane bounded reconstruction: `|C_t| <= L_max` by construction.

---

## 11. Implementation Path

### 11.1 Phasing

The implementation breaks into four phases, ordered by leverage and dependency:

**Phase 1: Wire the read loop (E-3 + ContextWatermark)**
- Highest leverage — the compaction machinery exists and is orphaned
- Already scoped in `HANDOFF-AGENT-CONTINUITY-2026-08-26.md`
- Load conversation history, build real `messages[]`, wire ContextWatermark
- This gives Halbert multi-turn continuity within a session

**Phase 2: Session lifecycle (wake/sleep)**
- Implement the `wake()`/`sleep()` protocol
- At `wake()`: declare domains, retrieve state, reconstruct context
- At `sleep()`: write structured handoff, record open commitments, update beliefs
- This gives Halbert cross-session continuity

**Phase 3: Domain-scoped memory store**
- Implement the MemoryArtifact schema with provenance
- Domain-tag all memory writes
- Hard-filter all memory reads by domain
- Multi-signal retrieval (vector + BM25 + entity + temporal + salience)
- This gives Halbert the guardrails that prevent context bleeding

**Phase 4: Adaptive forgetting and self-evolution**
- Implement salience decay (memories not retrieved lose salience)
- Implement contradiction detection (new evidence revises old memories)
- Implement belief revision (Haloysius beliefs update from session evidence)
- Implement the promotion lifecycle (note → fact → policy → skill)
- This gives Halbert the Experience stage from the "Storage → Reflection → Experience" framework

### 11.2 What to steal from each framework

| Framework | What to borrow | What to skip |
|---|---|---|
| **Letta/MemGPT** | Hierarchical memory (core/archival), memory blocks, MemFS git-tracking, dreaming | The Letta server infrastructure (Halbert is local-first) |
| **Mem0** | Multi-signal retrieval (semantic + BM25 + entity), temporal reasoning | ADD-only write policy (Halbert needs UPDATE/DELETE), per-turn LLM extraction (too expensive) |
| **Zep/Graphiti** | "No LLM in the read path" principle, bi-temporal model (valid time + transaction time) | Graph-first substrate (overkill for finite domain), entity+relation extraction write cost |
| **Nūr** | Identity continuity, relational continuity (open commitments, rupture/repair), self-evolution (belief decay, theme→belief promotion) | The relationship/therapeutic framing (Halbert is a sysadmin, not a companion) |
| **StatePlane** | Tripartite state (episodic/semantic/procedural), episodic segmentation, bounded reconstruction, adaptive forgetting, write-path antipoisoning | The full formal model (Halbert can use a simpler version) |
| **Cogito/Engram** | wake()/sleep() protocol, belief revision with certainty management | The TypeScript/Node implementation (Halbert is Python) |
| **Anthropic** | Context editing (clear stale tool results), memory tool (file-based, client-side), initializer-agent pattern | Claude-specific APIs |
| **Devin** | Planner-executor separation (already have this), Spaces context inheritance (with explicit scope declaration) | Auto-generated Memories (highest bleed risk) |

### 11.3 What not to do

1. **Do not rely on auto-generated cross-session summaries.** This is the highest-bleed mechanism. The `<project_context>` block in this session is an example — it primed the agent with irrelevant framing. Use structured artifacts with domain tags instead.

2. **Do not put an LLM in the read path.** Retrieval must be deterministic. The LLM sees the retrieved context; it does not decide what to retrieve. (Zep/Graphiti principle.)

3. **Do not use whole-file precedence for tiered config.** Per-slot precedence is required. A layer that pins only the specialist must not wipe the global chat model. (Documented in `HANDOFF-AGENT-CONTINUITY-2026-08-26.md` E-5 traps.)

4. **Do not add layering until the store module has landed.** Layering a schema that is still mid-migration will produce a merge of two different shapes. (Same handoff.)

5. **Do not ignore the `self.ctx` race.** `self.ctx` is an instance attribute on a process-wide singleton with no lock. Two concurrent requests already clobber each other's context. Loading real history makes the blast radius worse. Fix or explicitly accept in writing. (Same handoff.)

6. **Do not build a graph-first substrate.** Halbert's domain is finite. A vector store + FTS5 + domain filter is sufficient. Graphiti's bi-temporal graph is overkill.

7. **Do not skip provenance.** The UCC paper is clear: text-level sanitization fails. You need artifact-level, provenance-based defenses. Every memory artifact needs `(session_id, domain, subject, before_state, after_state)`.

---

## 12. Replication Guide for Another AI

If you are another AI agent picking up this work, here is what you need to know to replicate the understanding and implement the architecture.

### 12.1 Read these files first (in order)

1. **This document** — the research and architecture
2. `/Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-AGENT-CONTINUITY-2026-08-26.md` — the E-3 and E-5 scope (multi-turn continuity + tiered config)
3. `/Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-MODEL-PICKER-STORE-2026-08-26.md` — the store module that must land before E-5
4. `/Volumes/4TB-BAD/Halbert/.handoff/CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md` — the conversation floor design (Plan A)
5. `/Volumes/4TB-BAD/Halbert/documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` — the approved spec
6. `/Volumes/4TB-BAD/Halbert/.sourceprep/AGENT_CONTEXT.md` — the codebase atlas (auto-generated, do not commit)

### 12.2 Understand the existing architecture

- **Haloysius** is the cognitive core. It provides PersonaMemory (identity), cognition ticks (at the REFLECTING state), and a self-model. It lives in a separate repo but is integrated via `cognition_wiring.py`.
- **SourcePrep** is the structural awareness layer. It provides a codebase atlas, trace graph, knowledge index, and semantic search. It runs as a daemon on port 8400 and is accessed via `sourceprep_client.py`.
- **AgentStateMachine** is the agent loop: PLANNING → SEARCHING → EXECUTING → OBSERVING → REFLECTING → RESPONDING. The REFLECTING state is where the cognitive tick fires.
- **`routes/agent.py`** is the production path. `send_message()` at line ~864 is the entry point. It currently passes no `conversation_history`.
- **`state_machine.py`** has three LLM call sites: planning (~line 668), responding/streaming (~line 1279), responding/non-streaming (~line 1293). All three send a single user message, not a real `messages[]` array.
- **`ContextWatermark`** in `context/watermark.py` implements the 80% token gate, 2-hour temporal gate, topic-boundary detection, and micro-compaction. It is referenced by zero files.
- **`conversation/summarization.py`** has `compress_conversation_history()` that returns a real summary message. Its only caller stringifies it.

### 12.3 The implementation order

1. **Phase 1 (E-3):** Wire the read loop. Follow the sequence in `HANDOFF-AGENT-CONTINUITY-2026-08-26.md`:
   - `routes/agent.py:send_message()` — derive conversation id, load history via `get_context_window()`
   - Pass `conversation_history` into `agent.process()`
   - Build real `messages[]` at all three call sites in `state_machine.py`
   - Persist the completed turn back to the store
   - Wire `ContextWatermark` as the compaction trigger
   - Fix or explicitly accept the `self.ctx` race
   - Verify V-05: "Check nginx" → "Nginx is stopped" → "Start it" must not produce "What should I start?"

2. **Phase 2:** Implement the wake/sleep protocol. Create a `session/lifecycle.py` module:
   - `wake(session_id, domains, task_description)` — retrieve state, reconstruct context
   - `sleep(session_id)` — write handoff, record commitments, update beliefs
   - Call `wake()` at session start (before `agent.process()`)
   - Call `sleep()` at session end (after the final response)

3. **Phase 3:** Implement the domain-scoped memory store. Create a `memory/store.py` module:
   - `MemoryArtifact` dataclass with provenance
   - `Domain` enum
   - SQLite schema: `artifacts` table with domain, subject, kind, content, provenance, salience, timestamps
   - FTS5 index on content + subject
   - Embeddings on content (reuse SourcePrep's nomic-embed-text-v1.5)
   - `retrieve(query, domains, budget)` — the deterministic retrieval algorithm from §10.6
   - `write(artifact)` — with write-path antipoisoning (validate domain, check for contradictions)

4. **Phase 4:** Implement adaptive forgetting. Add to `memory/store.py`:
   - `decay(salience_half_life_days)` — reduce salience of unretrieved artifacts
   - `contradict(artifact_id, new_artifact_id)` — mark old artifact as contradicted
   - `promote(note_id → fact_id → policy_id → skill_id)` — the StatePlane promotion lifecycle

### 12.4 The guardrails to implement from day one

1. **Domain hard-filter on all retrieval.** No cross-domain memory leakage. A session scoped to `disk` cannot retrieve `network` memory.
2. **Provenance on every artifact.** No anonymous memories. Every artifact records its session, domain, subject, and state changes.
3. **Session scope declaration.** Every session starts with `wake(session_id, domains, task)`. The agent cannot pivot to undeclared domains.
4. **No LLM in the read path.** Retrieval is deterministic. The LLM sees results; it does not choose what to retrieve.
5. **Contradiction tracking.** When new evidence contradicts an old memory, the old memory is marked, not deleted. The retrieval algorithm excludes contradicted artifacts.
6. **Salience decay.** Memories not retrieved lose salience. The store does not grow unboundedly.
7. **Structured handoffs.** Every session writes a YAML handoff on `sleep()`. No free-form markdown dumps.

### 12.5 How to verify the guardrails work

1. **Bleed test:** Start a session scoped to `disk`. Attempt to retrieve `network` memory. Verify zero results.
2. **Provenance test:** Write an artifact, then retrieve it. Verify the provenance fields are populated.
3. **Contradiction test:** Write artifact A ("sshd is running"). Write artifact B ("sshd is stopped"). Retrieve. Verify A is excluded (contradicted by B).
4. **Decay test:** Write an artifact with salience 1.0. Run decay with a 1-day half-life. Wait 1 day (or mock time). Verify salience is 0.5.
5. **Scope violation test:** Start a session scoped to `disk`. Ask the agent to investigate a network issue. Verify the agent refuses or asks for a scope expansion.
6. **V-05 (multi-turn):** "Check nginx" → "Nginx is stopped" → "Start it" must not produce "What should I start?" (from `HANDOFF-AGENT-CONTINUITY-2026-08-26.md`)

### 12.6 Key files to modify or create

**Modify:**
- `halbert_core/halbert_core/dashboard/routes/agent.py` — load history, pass to process(), call wake/sleep
- `halbert_core/halbert_core/agents/state_machine.py` — build real `messages[]` at three call sites, wire ContextWatermark
- `halbert_core/halbert_core/context/assembler.py` — consume real conversation history, not flattened prose
- `halbert_core/halbert_core/context/watermark.py` — give it its first consumer

**Create:**
- `halbert_core/halbert_core/session/lifecycle.py` — wake/sleep protocol
- `halbert_core/halbert_core/memory/store.py` — domain-scoped memory store
- `halbert_core/halbert_core/memory/artifact.py` — MemoryArtifact dataclass, Domain enum, Provenance
- `halbert_core/halbert_core/memory/retrieval.py` — deterministic retrieval algorithm
- `halbert_core/halbert_core/memory/forgetting.py` — salience decay, contradiction tracking, promotion lifecycle

### 12.7 Commit conventions

From the project rules (`CLAUDE.md`, `AGENTS.md`, global rules):

- **Never** add "Co-Authored-By" trailers to commit messages
- **Never** add "Generated with Devin" or similar attribution lines
- Commit messages should contain only the subject line and body describing the change
- Use pathspec-scoped adds (concurrent sessions leave unrelated files dirty on `main`)

---

## 13. References

### Academic papers

1. **"Memory in the Age of AI Agents"** — arxiv 2512.13564 — unified taxonomy (forms, functions, dynamics)
2. **"Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers"** — arxiv 2603.07670 — write-manage-read loop, five mechanism families
3. **"From Storage to Experience: A Survey on the Evolution of LLM Agent Memory"** — ACL 2026 Findings — three evolutionary stages (Storage → Reflection → Experience)
4. **"StatePlane: A Cognitive State Plane for Long-Horizon AI Systems Under Bounded Context"** — arxiv 2603.13644 — tripartite state, bounded reconstruction, adaptive forgetting, write-path antipoisoning
5. **"Anatomy of Agentic Memory: Taxonomy and Empirical Analysis"** — arxiv 2602.19320 — empirical limitations of current systems
6. **"Rethinking Memory Mechanisms of Foundation Agents in the Second Half"** — arxiv 2602.06052 — memory substrate, cognitive mechanism, memory subject
7. **"Cross-Session Threats in AI Agents: Benchmark, Evaluation, and Algorithms"** — arxiv 2604.21131v1 — cross-session attack patterns, CSTM-Bench
8. **"Cross-User Contamination in Shared LLM Agents"** — arxiv 2604.01350 — UCC taxonomy, 57-71% contamination rates, artifact-level defenses
9. **"Self Model for Embodied Artificial Intelligence"** — sciopen 10.1007/s11390-026-6289-3 — six-level self-model hierarchy (L0-L5)
10. **MemGPT original paper** — arxiv 2310.08560 — hierarchical memory, tier promotion
11. **Sleep-time compute** — arxiv 2504.13171 — offline memory consolidation ("dreaming")

### Open-source frameworks

12. **Letta (MemGPT)** — [github.com/letta-ai/letta](https://github.com/letta-ai/letta/) — hierarchical memory, memory blocks, MemFS, dreaming
13. **Letta Code** — [github.com/letta-ai/letta-code](https://github.com/letta-ai/letta-code) — stateful agent harness
14. **Mem0** — [github.com/mem0ai/mem0](https://www.github.com/mem0ai/mem0) — distill-at-write vector layer, multi-signal retrieval
15. **Zep / Graphiti** — [github.com/getzep/graphiti](https://github.com/getzep/graphiti) — bi-temporal knowledge graph, no LLM in read path
16. **Nūr** — [github.com/balfiky/nur](https://github.com/balfiky/nur) — identity continuity, relational continuity, self-evolution
17. **Cogito** — [github.com/cartisien/cogito](https://github.com/cartisien/cogito) — wake/sleep protocol, belief revision
18. **Engram** — [github.com/cartisien/engram](https://github.com/cartisien/engram) — persistent memory storage
19. **Smrti** — [github.com/cyqlelabs/smrti](https://github.com/cyqlelabs/smrti) — SQLite, AtomSpace-inspired, Bayesian truth values
20. **Lucid** — [domlynch.github.io/Lucid](https://domlynch.github.io/Lucid/) — SQLite-only memory runtime, 2000 lines
21. **MKEvo** — [github.com/Zer0Q/MKEvo-cognitive-runtime](https://github.com/Zer0Q/MKEvo-cognitive-runtime) — cognitive runtime, deterministic governance
22. **CCP (Cognitive Context Protocol)** — [github.com/Cavanaugh-Design-Studio/cognitive-context-protocol](https://github.com/Cavanaugh-Design-Studio/cognitive-context-protocol) — cognitive state vector, contract-enforced plans

### Production products and documentation

23. **Devin Memories & Rules** — [docs.devin.ai/desktop/cascade/memories](https://docs.devin.ai/desktop/cascade/memories)
24. **Devin Spaces** — [docs.devin.ai/desktop/spaces](https://docs.devin.ai/desktop/spaces)
25. **Devin Agent Patterns Catalog** — [agentpatternscatalog.org/compositions/devin](https://www.agentpatternscatalog.org/compositions/devin/)
26. **Devin architecture analysis** — [datarekha.com/blog/devin-architecture-anatomy](https://datarekha.com/blog/devin-architecture-anatomy/)
27. **Anthropic context engineering** — [anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
28. **Anthropic long-running agent harnesses** — [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
29. **Anthropic context management** — [anthropic.com/news/context-management](https://www.anthropic.com/news/context-management)
30. **AI Runtime Security — Session & Scope** — [airuntimesecurity.io/infrastructure/controls/session-and-scope](https://airuntimesecurity.io/infrastructure/controls/session-and-scope/)
31. **Production Memory Frameworks comparison** — [jatinbansal.com/ai-engineering/production-memory-frameworks](https://jatinbansal.com/ai-engineering/production-memory-frameworks/)
32. **Hermes cross-contamination bug** — [github.com/NousResearch/hermes-agent/issues/46303](https://github.com/NousResearch/hermes-agent/issues/46303)
33. **AI Agent Tenant Isolation** — [dev.to/jackm-singularity/ai-agent-tenant-isolation](https://dev.to/jackm-singularity/ai-agent-tenant-isolation-stop-customer-context-from-bleeding-across-workflows-4961)

### Halbert internal documents

34. `HANDOFF-AGENT-CONTINUITY-2026-08-26.md` — E-3 (multi-turn continuity) and E-5 (tiered config) scope
35. `HANDOFF-MODEL-PICKER-STORE-2026-08-26.md` — store module that blocks E-5
36. `CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md` — conversation floor design (Plan A)
37. `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` — approved spec
38. `documentation/design/TRIAGE-SCRUTINY-FEEDBACK-2026-08-26.md` — engineering and design tracks
39. `.sourceprep/AGENT_CONTEXT.md` — auto-generated codebase atlas

---

## Appendix A: The context bleeding log (this session, as a case study)

This session is itself an example of the problem. The following was injected into the agent's context before it saw the user's message:

1. **8 session summaries** covering: LLM picker redesign, RAG consolidation, SourcePrep integration, legal documentation, marketing website, model picker store, daemon ownership, implementation plan review
2. **5 open IDE files** including the LLM picker design review, tier router, config wizard tests, and Tauri/Settings frontend files
3. **SourcePrep atlas** with 868 files, 7883 nodes, 13237 edges

None of items 1-3 are related to the user's actual request (research cross-session continuity). The agent had to actively resist:
- Framing the research in terms of the LLM picker problem (because 3 of 8 summaries were about it)
- Suggesting implementation work on the open IDE files (because they were in context)
- Treating the SourcePrep atlas as the primary codebase reference (because it was auto-injected)

The research was conducted despite the bleeding, not because of it. A domain-scoped system would have filtered all of this out — none of it is tagged `self` (Halbert working on its own continuity system) or `research`.

This is the case for hard-filtered, domain-tagged retrieval: the agent should have started this session with a clean context, declared `domains=[self, research]`, and retrieved only prior work on Halbert's own architecture and continuity research. Instead, it got 8 unrelated session summaries and 5 unrelated open files.

---

*End of document.*
