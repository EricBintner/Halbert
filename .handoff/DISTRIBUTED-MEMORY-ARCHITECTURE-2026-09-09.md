# Distributed Memory Architecture for Federated Agent Nodes

> **Purpose:** Product research and feature planning for Halbert's federated node architecture.
> Proposes a distributed agent memory system where each node maintains a local archival memory store,
> nodes sync memory via conflict-free protocols, edge nodes cache LLM responses semantically, and
> context transfers portably across nodes on sleep/wake transitions.
>
> **Audience:** Halbert architecture / product planning.
> **Status: CLOSED — not scoped, nothing to build. Read §13 first.**
> §1 and §4–§8 are **superseded**: they were written without reference to the running system,
> and §1's premise is wrong (the primary compute is the cloud, so a sleeping host degrades
> nothing). §2–§3 (the literature) stand and have been extracted, with citation errors fixed,
> to `documentation/design/AGENT-MEMORY-RESEARCH-REFERENCE.md`.
> **One open decision** survives: §13.5 — should singular-entity mode be the default?
> **Date:** 2026-09-09 (§11–§12 same day; §13 second pass)

---

## 1. The Problem: Memory Asymmetry in Federated Agent Architectures

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

Halbert's federated model ("Sovereign Self, Shared Commons") already separates compute
asymmetrically: low-power always-on nodes (edge) handle cognition, voice, and event streams,
while high-power nodes (compute hosts) handle LLM inference. But **memory is currently
asymmetrical in a way that creates a learning gap**:

- The edge node learns things the compute host never sees (home patterns, sensor events,
  automation outcomes, voice interactions at 3 AM).
- The compute host learns things the edge node never sees (codebase changes, sysadmin
  decisions, model performance tuning).
- When the compute host sleeps, the edge node falls back to template thoughts — it loses
  access to the host's accumulated context.
- When the compute host wakes, it has no mechanism to re-hydrate what the edge node
  experienced while it was asleep.
- If the edge node answers a question the host already answered yesterday, it re-delegates
  to the host, which re-computes — **redundant inference**.

This is not a Halbert-specific problem. It is the central problem identified across the
2024–2026 distributed agent memory literature: agents operating on separate nodes accumulate
experience that is **ephemeral, isolated, and non-transferable** (SAMEP, 2025; MELD, 2026;
Portable Agent Memory, 2026). The solution space is now mature enough to build on.

---

## 2. Research Foundation

### 2.1 Agent Memory Taxonomy (the consensus model)

Three recent surveys converge on a shared taxonomy of agent memory that supersedes the
older "short-term / long-term" dichotomy:

**From "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers"**
(arXiv:2603.07670, 2026):

> "We formalize agent memory as a write-manage-read loop tightly coupled with perception
> and action, then introduce a three-dimensional taxonomy spanning temporal scope,
> representational substrate, and control policy."

The survey identifies five mechanism families:
1. **Context-resident compression** (summarization within the context window)
2. **Retrieval-augmented stores** (external vector-indexed memory)
3. **Reflective self-improvement** (agents synthesize higher-level insights from raw memories)
4. **Hierarchical virtual context** (MemGPT-style tiered paging)
5. **Policy-learned management** (RL-trained memory access policies)

**From "Memory in the Age of AI Agents"** (arXiv:2512.13564, 2025):

> "From the perspective of functions, we propose a finer-grained taxonomy that distinguishes
> factual, experiential, and working memory."

This survey identifies three dominant **forms** of agent memory:
- **Token-level memory** (raw text / token sequences)
- **Parametric memory** (fine-tuned model weights)
- **Latent memory** (compressed vector representations)

And three **functions**:
- **Factual memory** (facts about the world: "the user's name is Eric")
- **Experiential memory** (what happened: "at 6 PM the user arrived home and said 'goodnight'")
- **Working memory** (current task state: "I'm in the middle of adjusting the thermostat schedule")

**From "From Storage to Experience: A Survey on the Evolution of LLM Agent Memory"**
(ACL Findings 2026):

> "We classify the evolution of memory mechanisms into three tiers based on the level of
> information abstraction and cognitive processing: Storage (trajectory preservation),
> Reflection (trajectory refinement), and Experience (trajectory abstraction)."

This survey adds the **evolutionary dimension**: memory systems progress from raw storage
to reflective refinement to abstracted experience. The frontier is "cross-trajectory
abstraction" — extracting transferable knowledge from individual episodes.

**From "AI Meets Brain: A Unified Survey on Memory Systems from Cognitive Neuroscience to
Autonomous Agents"** (arXiv:2512.23343, 2025):

This survey maps the cognitive neuroscience taxonomy onto agent memory, distinguishing:
- **Procedural memory** (skills, learned automation patterns)
- **Conceptual/semantic memory** (facts, relationships)
- **Episodic memory** (specific events, tied to time and context)

**From "A Survey on the Memory Mechanism of Large Language Model based Agents"**
(arXiv:2404.13501, 2024):

The earliest comprehensive survey, establishing the write-manage-read loop and cataloguing
applications where memory is the differentiating factor: personal assistants, coding
agents, open-world games, scientific reasoning, and multi-agent teamwork.

### 2.2 The Five-Component Memory Model

**Portable Agent Memory** (arXiv:2605.11032, 2026) synthesizes the above into a concrete
five-component model for transferable agent memory:

> "Portable Agent Memory introduces a five-component memory model
> M = (E, S, P, W, I) spanning episodic, semantic, procedural, working, and identity memory."

| Component | What it holds | Example for Halbert |
| :--- | :--- | :--- |
| **Episodic (E)** | Time-stamped event records | "At 2026-09-09 06:12, user arrived home, said 'goodnight', lights dimmed, doors locked" |
| **Semantic (S)** | Extracted facts and relationships | "User arrives home ~6 PM weekdays; prefers thermostat at 68 at night" |
| **Procedural (P)** | Learned skills and patterns | "When user says 'goodnight': lock.all + lights.dim(10%) + thermostat.set(68)" |
| **Working (W)** | Current task state | "Currently adjusting the thermostat schedule for winter mode" |
| **Identity (I)** | Agent persona, behavioral guidelines | "I am Halbert-home. I manage the house. I speak concisely. I defer complex questions to the workstation." |

This model is the basis for the **portable transfer protocol** proposed below (Section 4.4).
The paper demonstrates Transfer Continuity Scores of 0.83–0.92 (vs. 0.28–0.45 for no-memory
baseline) when memory is structured this way and transferred across heterogeneous LLM systems.

### 2.3 Tiered Memory: The MemGPT/Letta Pattern

**MemGPT: Towards LLMs as Operating Systems** (arXiv:2310.08560, Park et al., 2023;
published UIST 2024) introduced the foundational tiered memory pattern now adopted by
Letta and most modern agent frameworks:

> "We propose virtual context management, a technique drawing inspiration from hierarchical
> memory systems in traditional operating systems which provide the illusion of an extended
> virtual memory via paging between physical memory and disk."

The MemGPT model has three tiers:

| Tier | Analogy | Description |
| :--- | :--- | :--- |
| **Core memory** (in-context) | RAM | Always in the LLM's context window. Persona, human info, current task. Limited by context window size. |
| **Archival memory** (out-of-context) | Disk | Vector-indexed external store. Agent searches via `archival_memory_search` tool call. Unlimited capacity. |
| **Recall memory** | Log file | Full conversation history. Retrieved via `conversation_search`. |

Letta (the production evolution of MemGPT) implements this with:
- **Core memory**: structured blocks (persona, human, domain-specific) in the context window
- **Archival memory**: vector database backends (pgvector, SQLite+ChromaDB, Milvus, Qdrant,
  Turbopuffer) — the agent calls `archival_memory_search` to retrieve relevant passages
- **Recall memory**: full message history in PostgreSQL or SQLite

The key insight for Halbert: **archival memory is the tier that benefits from fast local
storage**. Vector search over archival memory is the operation that determines agent
response latency. On fast storage (sub-10 µs latency), vector search returns in
milliseconds. On slow storage (HDD, ~5-10 ms latency), the same search takes seconds —
too slow for interactive agent response.

### 2.4 The Retrieval Scoring Function (Generative Agents)

**Generative Agents: Interactive Simulacra of Human Behavior** (Park et al., UIST 2023;
arXiv:2304.03442) introduced the retrieval scoring function that most agent memory
systems still use:

> "A memory retrieval model combines relevance, recency, and importance to surface the
> records needed to inform the agent's moment-to-moment behavior."

The formula:

```
score = α_rec · recency + α_imp · importance + α_rel · relevance
```

Where:
- **Recency**: exponential decay since last access (originally by event index, modern
  systems use wall-clock half-lives)
- **Importance**: LLM-assigned significance score (1-10 scale; idle events = 1, life events = 10)
- **Relevance**: cosine similarity between the query embedding and the memory embedding

The original paper used hand-tuned weights (relevance weighted 6× recency), and the
Agent Memory Atlas notes: "The formula that launched a hundred memory systems is a tuned
heuristic, and treating it as a principled result is a mistake the atlas should name plainly."
Modern systems (Redis Agent Memory Server, OpenViking) use dual half-lives on access and
creation time rather than the original index-based decay.

The **reflection** mechanism from the same paper is equally important: when the running
sum of importance scores exceeds a threshold, the agent pauses to synthesize higher-level
insights from recent memories and writes them back into the stream as new (higher-importance)
memory entries. This is the "Reflection" tier in the Storage → Reflection → Experience
evolution (ACL Findings 2026 survey).

### 2.5 Self-Organizing Memory (A-Mem)

**A-Mem: Agentic Memory for LLM Agents** (NeurIPS 2025; arXiv:2502.12110) introduces a
memory system that dynamically organizes itself, inspired by the Zettelkasten method:

> "When a new memory is added, we generate a comprehensive note containing multiple structured
> attributes, including contextual descriptions, keywords, and tags. The system then analyzes
> historical memories to identify relevant connections, establishing links where meaningful
> similarities exist. Additionally, this process enables memory evolution — as new memories
> are integrated, they can trigger updates to the contextual representations and attributes
> of existing historical memories."

This is significant for distributed memory because **self-organizing links between memories
are what make cross-node sync tractable**. If each memory is a node in a knowledge graph with
semantic links, sync can operate on the graph delta (new nodes + new edges) rather than
re-transmitting the entire memory store. A-Mem uses ChromaDB for the vector index and
demonstrates superior performance across six foundation models vs. fixed-structure memory
systems.

---

## 3. Distributed Memory Sync: The Protocol Layer

### 3.1 SAMEP: Secure Agent Memory Exchange Protocol

**SAMEP** (arXiv:2507.10562, 2025) is the most directly applicable protocol for Halbert's
federated model:

> "We introduce SAMEP (Secure Agent Memory Exchange Protocol), a novel framework that enables
> persistent, secure, and semantically searchable memory sharing among AI agents. Our protocol
> addresses three critical challenges: (1) persistent context preservation across agent sessions,
> (2) secure multi-agent collaboration with fine-grained access control, and (3) efficient
> semantic discovery of relevant historical context."

Key properties:
- **Distributed memory repository** with vector-based semantic search
- **AES-256-GCM encryption** for memory at rest and in transit
- **MCP-compatible** — standardized APIs compatible with the Model Context Protocol
- **Fine-grained access control** — per-memory access policies
- **Audit trail generation** for compliance

Experimental results: **73% reduction in redundant computations**, 89% improvement in
context relevance scores.

The MCP compatibility is critical for Halbert: the existing peer link and fleet cockpit
already use MCP transport. SAMEP's memory exchange can ride on the same channel.

### 3.2 MELD: Conflict-Free Knowledge Graph Sync

**MELD** (arXiv:2608.16357, 2026) solves the hardest problem in distributed agent memory:
**reconciling knowledge when two nodes have learned contradictory or overlapping things
independently**:

> "No protocol lets two agents' memories reconcile a fact phrased two ways, link related
> facts held apart, or reconcile contradictory knowledge without silently discarding either
> claim. We present MELD, a self-managing coherence mechanism for a federation of agent
> memories whose run-time model is the knowledge graph itself."

MELD's design principles align exactly with Halbert's "Sovereign Self" philosophy:

- **Sovereign brains**: each node owns its memory; no coordinator required
- **Five-outcome admission**: every incoming claim is classified as insert, merge, relate,
  conflict, or reject — decided from three signals:
  1. Scoped claim-key identity (is this the same fact?)
  2. Embedding similarity (is this semantically the same?)
  3. Natural-language-inference verdict (does this entail/contradict the existing claim?)
- **CRDT for status**: a per-claim status CRDT (conflict-free replicated data type) keeps
  sovereign brains coherent in claim status without a coordinator — self-healing after
  network partitions and under lossy routing
- **Contradictions preserved, not resolved**: MELD does not adjudicate truth. A detected
  contradiction is preserved for later adjudication (by the user or a higher-reasoning pass),
  never silently resolved.

Results: distributed merge is recall-non-inferior to a centralized store; the merge
classifier separates at AUC 0.968 with a 0.013 false-merge rate; the status CRDT reconverges
in 30/30 real partition-heal trials.

### 3.3 CRDT Foundations for Knowledge Graph Sync

The CRDT (Conflict-free Replicated Data Type) approach underlying MELD is well-established:

- **Merkle-CRDTs** (used by Silk, Automerge, and IPFS-related systems): each operation is
  content-addressed in a Merkle-DAG. Sync exchanges only the operations the peer is missing.
  No causal delivery requirement — if two replicas have the same set of DAG nodes, they
  compute the same state regardless of delivery order.
- **Operation-based CRDTs** (used by crdf for RDF graphs): operations are broadcast and
  applied on remote replicas. Concurrent additions on different replicas converge
  automatically.
- **State-based CRDTs** (used by Yjs, Loro for document sync): merge function takes the
  least-upper-bound of two states. Simpler but larger sync payloads.

For Halbert's use case (knowledge graph of agent memories), **Merkle-CRDTs** are the best
fit because:
1. Sync is delta-only (only missing operations transferred) — efficient on LAN
2. No coordinator needed — matches sovereign-node philosophy
3. Self-healing after partitions — nodes can sync whenever they reconnect
4. Content-addressed integrity — tamper-evident, cryptographically signed

### 3.4 DisCEdge: Distributed Context as Tokenized Sequences

**DisCEdge** (ACM 2025; doi:10.1145/3805621.3807656) addresses the efficiency of the sync
payload itself:

> "We propose DisCEdge, a distributed context management system that stores and replicates
> user context in tokenized form across edge nodes. By maintaining context as token sequences,
> our system avoids redundant computation and enables efficient data replication."

Results: **14% faster median response times**, **90% smaller client request sizes**, 15%
lower inter-node synchronization overhead vs. raw-text-based systems.

The key insight: storing and syncing context as **token sequences** (not raw text) means:
- Smaller sync payloads (tokens are more compact than text)
- No redundant tokenization on the receiving node
- Direct injection into the LLM's context window without re-processing

For Halbert: when the edge node sends its accumulated context to the compute host on
wake, sending tokenized sequences rather than raw text reduces transfer time and
re-hydration latency.

### 3.5 CoMIC: Centralized Reflection, Decentralized Execution

**CoMIC** (arXiv:2606.00756, 2026) formalizes a pattern that maps almost exactly onto
Halbert's existing architecture:

> "CoMIC follows a Centralized Reflection, Decentralized Execution design: edge agents
> execute locally using subgoal-oriented hierarchical memory and selective re-expansion
> of relevant histories, while a cloud-side LLM critic asynchronously evaluates completed
> trajectories, filters reusable experience, and aggregates cross-agent guidance keyed by
> semantic subgoal identifiers."

In Halbert terms:
- **Decentralized Execution** = the edge node runs locally (cognition, voice, HA events)
  using its own hierarchical memory
- **Centralized Reflection** = the compute host (when awake) asynchronously evaluates the
  edge node's trajectories, filters reusable experience, and generates cross-node guidance

CoMIC shows this design improves progress rate and action grounding for weak edge agents
without updating model parameters — the edge node gets smarter from the compute host's
reflection, not from running a bigger model.

---

## 4. Proposed Feature Architecture

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

Based on the research, four features are proposed. They are independent but composable.

### 4.1 Feature: Local Archival Memory Tier (per-node)

**Based on:** MemGPT/Letta tiered memory (arXiv:2310.08560), A-Mem self-organizing memory
(NeurIPS 2025), Generative Agents memory stream + reflection (arXiv:2304.03442)

Each Halbert node gets a local archival memory store with:

- **Episodic layer**: append-only event log (every HA event, voice interaction, LLM
  response, automation outcome). Timestamped, embedded, importance-scored.
- **Semantic layer**: extracted facts and relationships, updated by reflection. This is
  the "distilled knowledge" layer — small, high-value, frequently accessed.
- **Procedural layer**: learned automation patterns and skills. "When X happens, do Y."
  Stored as structured rules, not free text.
- **Reflection engine**: when the running importance sum exceeds a threshold, the node
  synthesizes higher-level insights from recent episodic memories and writes them into the
  semantic layer as new (higher-importance) entries.

**Retrieval** uses the Generative Agents scoring function:
```
score = α_rec · recency + α_imp · importance + α_rel · relevance
```
With wall-clock half-lives for recency (not the original index-based decay), LLM-assigned
importance (or a heuristic proxy for edge nodes without LLM access), and cosine similarity
for relevance.

**Storage requirement:** ~50-200 GB per node for the archival store + vector index. Fast
local storage (low-latency SSD) is required for interactive response times — vector search
latency is the bottleneck, and it is storage-latency-bound.

**Key design decisions for Halbert:**
- The edge node's reflection engine must work **without LLM access** (compute host may be
  asleep). Options: (a) defer reflection until the compute host wakes and delegates, (b)
  use a lightweight local model for reflection (the existing sentence-transformers
  embeddings could support similarity-based clustering without an LLM), or (c) use
  deterministic template-based reflection (rule extraction from repeated patterns).
- The archival store should use a **pluggable vector backend** (like Letta's approach:
  pgvector, SQLite+ChromaDB, or a lightweight embedded store) to accommodate different
  node capabilities.

### 4.2 Feature: Cross-Node Memory Sync

**Based on:** SAMEP (arXiv:2507.10562), MELD (arXiv:2608.16357), Merkle-CRDT sync
(Silk, Automerge), DisCEdge (ACM 2025)

Nodes periodically sync their archival memory via the LAN:

1. **Delta detection**: each node tracks which memory entries it has not yet shared with
   each peer (Merkle-DAG heads comparison — "what do you have that I don't?")
2. **Delta transfer**: only new entries (nodes + edges in the knowledge graph) are
   transferred, not the full store
3. **Merge**: incoming entries are admitted via MELD's five-outcome procedure (insert,
   merge, relate, conflict, reject) using embedding similarity + NLI verdict
4. **Status CRDT**: claim status (e.g., "verified", "superseded", "contradicted") syncs
   via CRDT — conflict-free, self-healing after partitions
5. **Contradiction preservation**: contradictions are flagged, not silently resolved.
   The compute host (when awake) can adjudicate via higher-reasoning LLM pass.

**Transport:** MCP-compatible (per SAMEP), riding on the existing peer link. Tokenized
payloads (per DisCEdge) for efficiency.

**Sovereignty guarantee:** each node owns its memory. Sync is opt-in per memory entry
(access control per SAMEP's fine-grained policies). A node can mark memories as
"sovereign-only" (never synced) or "shared-commons" (synced to peers).

**Key design decisions for Halbert:**
- Sync frequency: event-driven (on significant events) + periodic (hourly/daily sweep).
  Not continuous — the edge node's bandwidth and power budget matter.
- Conflict adjudication: who resolves contradictions? The compute host's LLM is the
  natural "higher reasoner," but it's asleep half the time. Defer adjudication until
  wake, or use the edge node's template-based reasoning for low-stakes contradictions.
- Access control: the edge node's home sensor data may be privacy-sensitive. Per-memory
  access policies (SAMEP) let the node control what enters the shared commons.

### 4.3 Feature: Semantic Response Cache (edge nodes)

**Based on:** DisCEdge (ACM 2025), Redis SemanticCache, FluxCache (adaptive thresholds)

Edge nodes cache **tokenized LLM responses** from the compute host, indexed by semantic
similarity. When a new query arrives:

1. **Embed the query** using the local sentence-transformers model (already running on
   edge nodes for persona memory)
2. **Vector search** the response cache for semantically similar past queries
3. **If similarity ≥ threshold**: return the cached response instantly — no network
   round-trip, no compute host wake-up
4. **If similarity < threshold**: delegate to the compute host (or fall back to template
   thoughts if the host is asleep), cache the new response

**Adaptive thresholds** (per FluxCache): the similarity threshold is not fixed. An ML
model (XGBoost or simpler) learns from user feedback ("good" / "bad" cache hits) and
adjusts the threshold per query category. This prevents stale-cache responses for
time-sensitive queries ("what's the weather?") while allowing generous caching for
stable queries ("how do I configure Zigbee2MQTT?").

**Results from the literature:**
- DisCEdge: 14% faster responses, 90% smaller request payloads
- FluxCache: 30-80% cost reduction, 40× latency improvement (<50ms vs 2000ms)
- Redis SemanticCache: sub-millisecond cache hits via vector similarity search

**Key design decisions for Halbert:**
- **TTL by query type**: time-sensitive queries (weather, sensor state, "is the door
  locked?") get short TTLs (minutes). Stable queries (configuration, how-to, persona
  questions) get long TTLs (days/weeks).
- **Cache invalidation on sync**: when the compute host sends new knowledge via memory
  sync, any cached responses that are semantically related to the new knowledge are
  invalidated (vector similarity check against the new entries).
- **Degraded-mode enrichment**: when the compute host is asleep, the cache is the edge
  node's richest fallback. Instead of "template thoughts" (deterministic, no LLM), the
  node serves cached real LLM responses to semantically similar past queries. This is a
  qualitative upgrade to the asleep-state experience.

### 4.4 Feature: Portable Memory Transfer on Sleep/Wake

**Based on:** Portable Agent Memory (arXiv:2605.11032), MemGPT context paging
(arXiv:2310.08560)

When the compute host transitions states (sleep → wake, or wake → sleep), memory is
transferred in a structured, cryptographically-signed bundle:

**On compute host sleep:**
1. The edge node stages its recent episodic + semantic memory into a transfer bundle
2. Bundle is structured per the five-component model: M = (E, S, P, W, I)
3. Bundle is serialized with a Merkle-DAG provenance structure (tamper-evident)
4. Bundle is staged on local fast storage, ready for transfer when the host wakes

**On compute host wake:**
1. The edge node sends the staged bundle to the host
2. The host **re-hydrates** the edge node's accumulated context into its own archival store
3. The host runs a **reflection pass** on the edge node's recent trajectories (CoMIC
   pattern: centralized reflection, decentralized execution)
4. The host generates **cross-node guidance** — insights from the edge node's experience
   that the host can use in its own reasoning
5. The guidance is synced back to the edge node via the cross-node sync mechanism

**Cryptographic integrity** (per Portable Agent Memory):
- Merkle-DAG provenance: every memory entry is content-addressed; tampering breaks the chain
- Capability-scoped access tokens: the bundle is encrypted; only the target host can decrypt
- Injection-resistant re-hydration: the re-hydration pipeline validates incoming memories
  against the agent's existing knowledge graph to prevent memory-mediated prompt injection

**Key design decisions for Halbert:**
- The transfer bundle is small (~100 MB - 1 GB per day of edge node activity) — the
  episodic log is the bulk; the semantic and procedural layers are distilled and compact
- Re-hydration latency matters: the host's first interaction after wake should not stall
  on memory import. Fast local storage on the host (for the archival store) makes
  re-indexing fast. The reflection pass can run asynchronously.
- The "I just woke up, what did I miss?" query should be a first-class Halbert capability:
  the host can summarize the edge node's experience during the sleep period as a natural-
  language briefing.

---

## 5. How the Features Compose

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

```
                    ┌─────────────────────────────────────────┐
                    │          COMPUTE HOST (awake)            │
                    │                                          │
                    │  ┌─────────────┐  ┌──────────────────┐   │
                    │  │ Archival    │  │ Reflection Engine │   │
                    │  │ Memory      │◄─┤ (evaluates edge  │   │
                    │  │ (vector DB) │  │  trajectories)    │   │
                    │  └──────┬──────┘  └────────┬─────────┘   │
                    │         │                  │             │
                    │         │  ┌───────────────▼──────────┐  │
                    │         │  │ Cross-Node Guidance      │  │
                    │         │  │ (insights from edge      │  │
                    │         │  │  experience)             │  │
                    │         │  └───────────┬────────────┘  │
                    └─────────┼──────────────┼────────────────┘
                              │              │
                    ┌─────────▼──────────────▼────────────────┐
                    │        CROSS-NODE SYNC (MCP)            │
                    │  • Merkle-CRDT delta sync                │
                    │  • MELD five-outcome merge                │
                    │  • SAMEP encryption + access control      │
                    │  • DisCEdge tokenized payloads           │
                    └─────────┬──────────────┬────────────────┘
                              │              │
                    ┌─────────▼──────────────▼────────────────┐
                    │          EDGE NODE (always on)            │
                    │                                          │
                    │  ┌─────────────┐  ┌──────────────────┐   │
                    │  │ Archival    │  │ Semantic Response │   │
                    │  │ Memory      │──│ Cache             │   │
                    │  │ (vector DB) │  │ (tokenized LLM    │   │
                    │  └──────┬──────┘  │  responses)       │   │
                    │         │         └────────┬─────────┘   │
                    │  ┌──────▼──────┐           │             │
                    │  │ Episodic    │    cache hit → instant   │
                    │  │ Event Log   │    cache miss → delegate │
                    │  │ (append)    │    host asleep → cache  │
                    │  └─────────────┘           │             │
                    └──────────────────────────────────────────┘
```

**Data flow:**
1. Edge node records events → episodic log → reflection → semantic layer
2. Edge node receives query → semantic cache check → hit (instant) or miss (delegate)
3. Periodic sync: edge sends new memories → host merges via MELD → host reflects → guidance back
4. Host sleeps → edge stages transfer bundle → host wakes → re-hydrate → reflect → brief

---

## 6. Storage Latency: The Hidden Enabler

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

A recurring theme across the literature is that **agent memory is storage-latency-bound**,
not compute-bound. The MemGPT paper frames this explicitly with the OS memory hierarchy
analogy: context window = RAM, archival memory = disk. The speed of "disk" determines
agent response latency.

| Operation | Storage latency budget | Impact if exceeded |
| :--- | :--- | :--- |
| Archival memory vector search | < 10 ms | Agent response feels sluggish; interactive use degraded |
| Episodic log append | < 1 ms | Event recording backs up under burst |
| Reflection (batch read of recent memories) | < 100 ms | Reflection pass stalls the cognition loop |
| Cross-node sync delta merge | < 1 s per batch | Sync window extends; bandwidth wasted |
| Re-hydration (bulk import on wake) | < 10 s | First post-wake interaction stalls |

Fast local storage (low-latency SSD, ideally sub-100 µs) keeps all of these within budget.
Slow storage (HDD, ~5-10 ms) pushes vector search and reflection into the seconds range —
too slow for interactive agent use.

This is not a hardware recommendation — it is an architectural constraint: **the archival
memory store must be on the fastest storage available on each node.** If a node only has
HDD, the archival store should be sized to fit in RAM (with a fast SSD for persistence),
or the node should use a smaller, RAM-resident archival store with HDD only for the
episodic log.

---

## 7. Open Research Questions for Halbert

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

These are questions the research does not fully answer, and that Halbert's specific
architecture will need to resolve through implementation and experimentation:

1. **Reflection without an LLM**: the edge node needs to reflect (synthesize insights from
   episodes) but may not have LLM access (compute host asleep). Options: defer reflection
   to the host, use deterministic pattern extraction, or use a tiny local model. What is
   the quality tradeoff?

2. **Contradiction adjudication latency**: MELD preserves contradictions but does not resolve
   them. Who resolves, and when? If the compute host is asleep for 12 hours, contradictions
   accumulate. Is deferred adjudication acceptable, or does it degrade the edge node's
   decision-making in the interim?

3. **Semantic cache staleness detection**: how does the edge node know a cached response is
   stale? Time-based TTL is crude. Event-based invalidation (a sensor event invalidates
   weather-related caches) is more precise but requires an invalidation rule engine. What
   is the right granularity?

4. **Memory growth management**: the episodic log grows unboundedly. The surveys identify
   "learned forgetting" as an open challenge (arXiv:2603.07670). When should old episodic
   memories be deleted, compressed, or promoted to the semantic layer and then discarded?
   What is the retention policy?

5. **Multi-node scaling**: the current design covers two nodes (edge + compute host). What
   happens with three or more? Does the CRDT sync scale? Does the semantic cache need to
   be shared across all edge nodes? Does reflection need a consensus mechanism?

6. **Privacy boundary of the shared commons**: which memories enter the shared commons and
   which stay sovereign? Home sensor data, voice recordings, and personal patterns are
   privacy-sensitive. The access control model (SAMEP) supports per-memory policies, but
   the policy authoring UX is an open question.

---

## 8. Recommended Implementation Priority

> **SUPERSEDED — see §13.** Retained for provenance; do not scope from this section.

| Phase | Feature | Dependency | Effort | Value |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Local archival memory tier** (episodic + semantic + vector search) | None | High | Foundation — everything else depends on this |
| 2 | **Reflection engine** (deferred to compute host) | Phase 1 | Medium | Turns raw episodes into reusable knowledge |
| 3 | **Semantic response cache** (edge node) | Phase 1 | Medium | Immediate UX win — faster responses, richer asleep-state |
| 4 | **Cross-node memory sync** (Merkle-CRDT + MELD merge) | Phase 1 | High | Closes the learning gap between nodes |
| 5 | **Portable memory transfer** (sleep/wake re-hydration) | Phase 4 | Medium | Smoothes the sleep/wake transition |
| 6 | **Adaptive cache thresholds** (ML-based) | Phase 3 | Low | Optimization — improves cache hit rate over time |

Phase 1 is the critical path. Without a local archival memory store, none of the other
features have a foundation to build on. The MemGPT/Letta tiered model is the proven
starting point — Halbert should adopt the core/archival/recall distinction and implement
the archival tier with a pluggable vector backend.

---

## 9. References

### Primary Research Papers

1. **MemGPT: Towards LLMs as Operating Systems** — Park et al., UIST 2024.
   arXiv:2310.08560. https://doi.org/10.48550/arxiv.2310.08560
   *Foundational tiered memory pattern (core / archival / recall). Virtual context management
   via paging between context window and external storage.*

2. **Generative Agents: Interactive Simulacra of Human Behavior** — Park et al., UIST 2023.
   arXiv:2304.03442. https://doi.org/10.1145/3586183.3606763
   *Memory stream + retrieval scoring (recency × importance × relevance) + reflection.
   The design most subsequent agent memory systems adopted or refined.*

3. **A-Mem: Agentic Memory for LLM Agents** — Xu et al., NeurIPS 2025.
   arXiv:2502.12110. https://proceedings.neurips.cc/paper_files/paper/2025/hash/19909c36f51abc4856b4560aff3d36d6-Abstract-Conference.html
   *Self-organizing memory via Zettelkasten-inspired dynamic indexing and linking.
   Memory evolution: new memories trigger updates to existing memories' attributes.*

4. **SAMEP: A Secure Agent Memory Exchange Protocol for Persistent Context Sharing in
   Multi-Agent AI Systems** — arXiv:2507.10562, 2025.
   https://arxiv.org/html/2507.10562
   *Distributed memory repository with vector search, AES-256-GCM, MCP-compatible APIs.
   73% reduction in redundant computations.*

5. **MELD: A Protocol for Merging Knowledge Across Distributed Agentic Memories** —
   arXiv:2608.16357, 2026.
   https://arxiv.org/html/2608.16357
   *Five-outcome merge procedure (insert/merge/relate/conflict/reject) with CRDT status
   sync. Sovereign brains, no coordinator, self-healing after partitions.*

6. **DisCEdge: Distributed Context Management for Large Language Models at the Edge** —
   ACM 2025. doi:10.1145/3805621.3807656
   *Tokenized context replication across edge nodes. 14% faster responses, 90% smaller
   request sizes.*

7. **Portable Agent Memory: A Protocol for Cryptographically-Verified Memory Transfer
   Across Heterogeneous AI Agents** — arXiv:2605.11032, 2026.
   https://doi.org/10.48550/arxiv.2605.11032
   *Five-component model M = (E, S, P, W, I). Merkle-DAG provenance, capability-scoped
   access tokens, injection-resistant re-hydration.*

8. **CoMIC: Collaborative Memory and Insights Circulation for Long-Horizon LLM Agents
   in Cloud-Edge Systems** — arXiv:2606.00756, 2026.
   https://arxiv.org/html/2606.00756
   *Centralized Reflection, Decentralized Execution. Edge agents execute locally;
   cloud LLM asynchronously evaluates trajectories and filters reusable experience.*

### Surveys

9. **Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers** —
   arXiv:2603.07670, 2026.
   https://arxiv.org/pdf/2603.07670
   *Write-manage-read loop. Three-dimensional taxonomy (temporal scope, representational
   substrate, control policy). Five mechanism families. Open challenges: continual
   consolidation, learned forgetting, multimodal memory.*

10. **Memory in the Age of AI Agents** — arXiv:2512.13564, 2025.
    https://www.alphaxiv.org/abs/2512.13564
    *Forms (token/parametric/latent) × functions (factual/experiential/working) ×
    dynamics (formation/evolution/retrieval). Memory as a first-class primitive.*

11. **From Storage to Experience: A Survey on the Evolution of LLM Agent Memory** —
    ACL Findings 2026.
    https://aclanthology.org/2026.findings-acl.2069.pdf
    *Three-stage evolution: Storage → Reflection → Experience. Frontier: active
    exploration and cross-trajectory abstraction.*

12. **AI Meets Brain: A Unified Survey on Memory Systems from Cognitive Neuroscience to
    Autonomous Agents** — arXiv:2512.23343, 2025.
    https://arxiv.org/html/2512.23343
    *Cognitive neuroscience taxonomy mapped to agents: procedural vs. conceptual,
    nature-based vs. scope-based classification. Memory security (attack and defense).*

13. **A Survey on the Memory Mechanism of Large Language Model based Agents** —
    arXiv:2404.13501, 2024.
    https://ar5iv.labs.arxiv.org/html/2404.13501
    *Earliest comprehensive survey. Write-manage-read loop. Applications: personal
    assistants, coding agents, games, scientific reasoning, multi-agent teamwork.*

### Frameworks and Implementations

14. **Letta (formerly MemGPT)** — letta-ai/letta.
    https://github.com/letta-ai/letta
    *Production agent framework with tiered memory. Archival backends: pgvector, SQLite+
    ChromaDB, Milvus, Qdrant, Turbopuffer. Letta Cloud for cross-device memory sync.*

15. **Silk Graph** — Merkle-CRDT graph engine for distributed, conflict-free knowledge graphs.
    https://github.com/Kieleth/silk-graph
    *No leader, no consensus, no coordinator. Schema-enforced. Content-addressed entries.
    Python bindings via PyO3.*

16. **Redis SemanticCache** — RedisVL.
    https://redis.io/docs/latest/develop/ai/redisvl/0.15.0/user_guide/how_to_guides/llmcache/
    *Semantic caching for LLM responses. Vector similarity search with configurable
    distance thresholds and TTL policies.*

17. **FluxCache** — Adaptive semantic cache for LLMs.
    https://github.com/bv-saketha-rama/flux-cache
    *Streaming-aware caching, ML-powered adaptive thresholds (XGBoost), real-time cost
    tracking. 30-80% cost reduction, 40× latency improvement.*

### Protocol Standards

18. **Model Context Protocol (MCP) Specification** — Anthropic, 2025-2026.
    https://modelcontextprotocol.io/specification/2025-11-25/index
    *Open protocol for LLM-application integration. JSON-RPC 2.0. Resources, prompts,
    tools. SAMEP's memory exchange is designed to be MCP-compatible.*

### Additional References

19. **Agent Memory Atlas** — neoneye.
    https://neoneye.github.io/agent-memory-atlas/systems/generative-agents/
    *Critical analysis of the Generative Agents retrieval scoring function. Documents
    that the famous weight vector [0.5, 3, 2] is a hand-tuned heuristic, not a principled
    result. Tracks divergence to wall-clock half-lives in modern systems.*

20. **FedCache: A Knowledge Cache-driven Federated Learning Architecture for Personalized
    Edge Intelligence** — arXiv:2308.07816, 2023.
    https://arxiv.org/html/2308.07816v3
    *Knowledge cache on the server for fetching personalized knowledge. Relevant to the
    semantic response cache pattern in federated settings.*

---

## 10. Summary

The research literature (2023-2026) has converged on a clear architectural pattern for
distributed agent memory:

1. **Tiered memory per node** (MemGPT/Letta): core (in-context) + archival (vector-indexed)
   + recall (conversation log). The archival tier is the one that benefits from fast local
   storage and enables all cross-node features.

2. **Self-organizing knowledge graph** (A-Mem): memories are not flat records — they are
   nodes in a linked knowledge graph that evolves as new memories are added. This makes
   delta sync tractable (sync the graph delta, not the full store).

3. **Conflict-free sync** (MELD + CRDTs): sovereign nodes sync without a coordinator.
   Contradictions are preserved, not silently resolved. Self-healing after partitions.

4. **Semantic response cache** (DisCEdge + Redis SemanticCache + FluxCache): edge nodes
   cache tokenized LLM responses, served by vector similarity. Adaptive thresholds learn
   from feedback. This is the single biggest UX win for the asleep-state experience.

5. **Portable memory transfer** (Portable Agent Memory): structured five-component bundles
   transfer across nodes on state transitions (sleep/wake). Cryptographically signed,
   injection-resistant re-hydration.

6. **Centralized reflection, decentralized execution** (CoMIC): the compute host reflects
   on the edge node's trajectories asynchronously, generating cross-node guidance. The
   edge node gets smarter from the host's reflection, not from running a bigger model.

Halbert's existing "Sovereign Self, Shared Commons" federated model is already aligned with
this architecture. The missing pieces are: (1) a local archival memory tier on each node,
(2) a sync protocol between nodes, (3) a semantic response cache on edge nodes, and (4) a
portable transfer mechanism for sleep/wake transitions. The research provides concrete
protocols and patterns for each — this is a buildable roadmap, not a research moonshot.
## 11. Scrutiny and Corrections

> **Added 2026-09-09.** Self-critique of this document. The above proposal was reviewed
> against the source papers and implementation details. The following issues were found
> and must be corrected before this plan is scoped into issues.

### 11.1 SAMEP does NOT ride on MCP transport

**The claim (Section 3.1):** "SAMEP's memory exchange can ride on the same channel...
the existing peer link and fleet cockpit already use MCP transport."

**The reality:** SAMEP has its own "RESTful API Layer" — it is a separate HTTP/REST
protocol, not an extension of MCP's JSON-RPC transport. The paper says:

> "Several protocols have emerged for agent communication. The Model Context Protocol
> (MCP) enables structured context passing between language models and tools... However,
> these protocols lack persistent memory capabilities and secure sharing mechanisms."

SAMEP is "compatible with" MCP in the sense that it can coexist and share API design
patterns, but it does NOT use MCP's transport. Implementing SAMEP requires a separate
REST API service on each node, not an MCP server extension.

**Impact:** The implementation cost is higher than implied. Halbert would need to run a
SAMEP REST service alongside its MCP transport, not extend the existing MCP channel.

### 11.2 MELD's merge procedure requires an NLI model, not just embeddings

**The claim (Section 3.2):** MELD's five-outcome procedure uses "embedding similarity +
NLI verdict" as if these are lightweight checks.

**The reality:** The MELD reference implementation (github.com/Future-Computing-Group/
meld-experiments) uses "a MiniLM sentence encoder + a cross-encoder NLI" for the
M-2 merge-classification rung. The NLI (Natural Language Inference) verdict is a
cross-encoder model that determines whether one claim entails, contradicts, or is
neutral toward another. This is a neural model inference, not a simple embedding
comparison.

The reference implementation notes this NLI rung is "optional and not needed for the
deterministic experiments" — but without it, the merge classifier degrades to
embedding similarity only, which has a higher false-merge rate. The full AUC 0.968
result depends on the NLI verdict being present.

**Impact for Halbert:** The edge node (which may lack LLM access when the compute host
is asleep) cannot run the full MELD merge procedure without an NLI model. Options:
- Run a small NLI cross-encoder locally on the edge node (feasible — these are
  ~100-400 MB models, not full LLMs)
- Defer merge to the compute host (sync accumulates unmerged until the host wakes)
- Use embedding-only merge with a higher false-merge rate (accept the quality loss)

This is a real architectural dependency that the document glossed over. It should be
added to the open questions (Section 7).

### 11.3 DisCEdge's 90% figure is about client-to-edge, not edge-to-host sync

**The claim (Section 3.4):** "90% smaller client request sizes" is cited in the context
of inter-node sync payload efficiency.

**The reality:** DisCEdge's 90% reduction is specifically for **client-to-server**
requests (the client sends a session reference instead of the full context). The
**inter-node synchronization overhead** reduction is 15%, not 90%. These are different
metrics for different interactions:

| Metric | Reduction | Applies to |
| :--- | :--- | :--- |
| Client request size | 90% | Client → edge node (session reference vs. full context) |
| Inter-node sync overhead | 15% | Edge node → edge node (tokenized vs. raw text replication) |
| Response time | 14% | End-to-end (avoiding re-tokenization) |

For Halbert's edge-to-host sync, the relevant figure is the **15% inter-node sync
reduction**, not 90%. The 90% figure would apply only if Halbert's edge node were
forwarding client context to the compute host on every request — which is not the
proposed architecture.

**Impact:** The benefit of tokenized payloads for inter-node sync is real but modest
(15%), not dramatic (90%). The document should correct this and downgrade the emphasis
on DisCEdge's tokenization for the sync use case.

### 11.4 The four features are NOT independent

**The claim (Section 4):** "four features are proposed. They are independent but
composable."

**The reality:** The implementation priority table (Section 8) contradicts this:
- Feature 4.2 (cross-node sync) depends on 4.1 (local archival memory) — you can't
  sync what you don't have
- Feature 4.3 (semantic cache) depends on 4.1 (needs the vector index infrastructure)
- Feature 4.4 (portable transfer) depends on 4.2 (needs sync infrastructure for the
  guidance-back step)

Only 4.1 is truly independent. The rest form a dependency chain. The "independent but
composable" framing is misleading and should be corrected to "layered, with clear
dependencies."

### 11.5 The reflection engine cannot run on sentence-transformers alone

**The claim (Section 4.1):** Option (b) for reflection without an LLM: "use a
lightweight local model for reflection (the existing sentence-transformers embeddings
could support similarity-based clustering without an LLM)."

**The reality:** Clustering similar memories is **retrieval**, not **reflection**.
Reflection (per Generative Agents, Park et al. 2023) requires synthesizing new
higher-level insights from a cluster of episodic entries — e.g., "the user's bedtime
routine has shifted 30 minutes earlier since the season changed." This requires
language generation, not just similarity matching.

Sentence-transformers can find that 30 episodic entries about "user went to bed" are
similar. They cannot synthesize the insight that bedtime shifted. That requires an LLM
(or at minimum a sequence model capable of trend extraction).

**Impact:** Option (b) should be removed or recharacterized. The realistic options for
edge-node reflection without an LLM are:
- (a) Defer reflection to the compute host (the only correct option for true reflection)
- (c) Deterministic pattern extraction (rule-based: "if event X occurs N times in a
  window, extract a pattern" — this is not reflection but it is useful)
- (d) A tiny local LLM (e.g., Qwen2.5-0.5B, ~1 GB) running on the edge node — feasible
  on modern edge hardware but adds CPU/memory/power cost

### 11.6 Embedding model mismatch across nodes is unaddressed

**The issue (not in the document):** The proposal assumes the edge node and compute
host can share and compare vector embeddings. But if the two nodes use different
embedding models (e.g., the edge node uses all-MiniLM-L6-v2 for persona memory, the
host uses a larger model or OpenAI embeddings), their vector spaces are incompatible.
You cannot compute cosine similarity between embeddings from different models.

**Impact:** This is a hard architectural constraint:
- Both nodes MUST use the same embedding model for the shared commons, OR
- The sync protocol must re-embed incoming memories using the local model (CPU cost
  on the receiving node), OR
- The shared commons uses a canonical embedding model that both nodes agree on at
  configuration time

This should be added as a key design decision in Section 4.2 and as an open question.

### 11.7 The CRDT oplog grows unboundedly and cannot be garbage-collected

**The issue (not in the document):** Merkle-CRDTs maintain an append-only oplog of all
operations. On a 24/7 always-on edge node recording every HA event, this oplog grows
continuously. Unlike the episodic log (which can be pruned — see open question #4), the
CRDT oplog cannot be safely garbage-collected without breaking sync: a peer that
reconnects after a long absence may need old operations to reconverge.

**Impact:** This is a separate growth concern from the episodic log. Options:
- Periodic oplog snapshots + compaction (trade off reconvergence speed for storage)
- Oplog TTL with fallback to full-state sync for long-absent peers
- Accept unbounded growth and size the storage accordingly (the D4800X 1.5 TB has
  room, but this is not a general solution)

This should be added to open question #4 (memory growth management).

### 11.8 FluxCache is not peer-reviewed

**The claim (Section 4.3, References 17):** FluxCache is cited alongside peer-reviewed
papers with "30-80% cost reduction, 40x latency improvement."

**The reality:** FluxCache is a GitHub repository (bv-saketha-rama/flux-cache), not a
peer-reviewed paper. The performance figures are self-reported in the README, not
validated by independent evaluation. Redis SemanticCache (ref 16) is a product
feature, not a paper — but it's from Redis (a reputable vendor), so its claims are
more trustworthy.

**Impact:** The document should distinguish between peer-reviewed results, vendor
claims, and self-reported GitHub project claims. The adaptive threshold concept
(ML-based threshold tuning) is sound and well-established in the caching literature
generally, but the specific FluxCache numbers should be flagged as unvalidated.

### 11.9 SAMEP's 73% figure is from different workloads

**The claim (Section 3.1):** "73% reduction in redundant computations" is presented
as a general result.

**The reality:** SAMEP's experiments are in "multi-agent software development,
healthcare AI with HIPAA compliance, and multi-modal processing pipelines." These
are multi-agent collaboration workloads where multiple agents work on the same task
and redundantly compute the same things. Halbert's workload is a single-user home
automation system with two nodes — the redundancy pattern is different.

**Impact:** The 73% figure should be treated as an upper bound from a different domain,
not a projected result for Halbert. The actual redundant-computation reduction for
Halbert depends on how often the edge node asks questions the host already answered —
which is an empirical question Halbert would need to measure.

### 11.10 CoMIC's workload is multi-step planning, not home automation

**The claim (Section 3.5):** CoMIC "maps almost exactly onto Halbert's existing
architecture."

**The reality:** CoMIC is designed for "long-horizon LLM agents" doing "symbolic
planning and text interaction" — multi-step tasks with subgoals, trajectories, and
progress tracking. Halbert's edge node workload is event-driven home automation
cognition: short interactions, sensor events, voice commands. These are different
workload profiles.

The "Centralized Reflection, Decentralized Execution" **pattern** maps conceptually.
But CoMIC's specific mechanisms (subgoal-oriented hierarchical memory, subgoal
identifiers, trajectory evaluation) may not directly apply to "the user said
goodnight and the lights dimmed" type events.

**Impact:** The document should downgrade "maps almost exactly" to "the architectural
pattern is analogous, but the specific mechanisms (subgoal tracking, trajectory
evaluation) would need adaptation for event-driven home automation workloads."

### 11.11 Storage latency budgets in Section 6 are engineering estimates, not research findings

**The issue:** Section 6 presents latency budgets (e.g., "Archival memory vector search
< 10 ms", "Episodic log append < 1 ms") as if they are from the literature. They are
not — no cited paper specifies these budgets. They are reasonable engineering
estimates, but the document does not distinguish them from research findings.

**Impact:** These should be labeled as engineering estimates / proposed budgets, not
as research-derived constraints. The MemGPT paper's OS memory hierarchy analogy is
conceptual, not a performance specification.

### 11.12 Portable Agent Memory's results are from a small pilot study

**The claim (Section 2.2):** "Transfer Continuity Scores of 0.83-0.92 (vs. 0.28-0.45
for no-memory baseline)" is presented as an established result.

**The reality:** This is from a "pilot study across Claude, GPT-4, and Gemini" — three
models, not a large-scale evaluation. It demonstrates the concept works but does not
validate at scale or across diverse agent architectures.

**Impact:** The result should be characterized as "promising pilot results" rather
than established performance. The five-component model itself is well-grounded in the
survey literature (Sections 2.1, 2.2); it's the specific transfer-continuity numbers
that are preliminary.

### 11.13 The architecture diagram's "host asleep → cache" path is misleading

**The issue:** The diagram shows "host asleep → cache" as a path, implying the cache
serves as the fallback when the host is asleep. But when the host is asleep and there
is a cache miss, there is no new LLM response to cache. The cache only contains
previously-cached responses. The correct flow is:

- Cache hit → return cached response (regardless of host state)
- Cache miss + host awake → delegate to host, cache the response
- Cache miss + host asleep → template thoughts (no new caching possible)

**Impact:** The diagram should show "host asleep → template thoughts or cached
response" as the fallback, not just "cache."

---

## 12. Summary of Corrections

| # | Issue | Severity | Action |
| :--- | :--- | :--- | :--- |
| 11.1 | SAMEP does not ride on MCP transport | High | Correct Section 3.1; add SAMEP REST service to implementation cost |
| 11.2 | MELD merge requires NLI model | High | Add to Section 4.2 design decisions; add to open questions |
| 11.3 | DisCEdge 90% figure misapplied | Medium | Correct Section 3.4; use 15% for inter-node sync |
| 11.4 | Features are not independent | Low | Correct Section 4 framing to "layered with dependencies" |
| 11.5 | Reflection ≠ clustering | High | Remove option (b) or recharacterize; add option (d) tiny local LLM |
| 11.6 | Embedding model mismatch | High | Add as key design decision in Section 4.2 and open question |
| 11.7 | CRDT oplog growth | Medium | Add to open question #4 |
| 11.8 | FluxCache not peer-reviewed | Low | Flag as unvalidated in references |
| 11.9 | SAMEP 73% from different domain | Medium | Characterize as upper bound, not projected result |
| 11.10 | CoMIC workload mismatch | Medium | Downgrade "maps almost exactly" to "pattern is analogous" |
| 11.11 | Storage latency budgets are estimates | Low | Label as engineering estimates in Section 6 |
| 11.12 | Portable Agent Memory pilot study | Low | Characterize as "promising pilot results" |
| 11.13 | Diagram "host asleep → cache" misleading | Low | Correct diagram flow label |

**Overall assessment:** The core architecture (tiered memory + CRDT sync + semantic
cache + portable transfer) is sound and well-grounded in the literature. The issues
above are about precision of claims, not about the fundamental approach. The most
significant corrections are:

1. **SAMEP is not MCP-native** — it needs its own REST service (11.1)
2. **MELD merge needs an NLI model** — the edge node can't fully merge without one (11.2)
3. **Reflection needs language generation** — sentence-transformers clustering is not
   reflection (11.5)
4. **Embedding models must match across nodes** — or incoming memories must be
   re-embedded (11.6)

These four issues affect implementation feasibility and should be resolved before
scoping issues. The rest are precision corrections that don't change the architecture
but improve the document's accuracy.

---

---

---

## 13. Verdict: Closed, Not Scoped

> **Added 2026-09-09, second pass.** §11 audited this document against its *sources*. It did
> not audit it against *Halbert*. §2–§3 (the literature) are sound and have been extracted to
> `documentation/design/AGENT-MEMORY-RESEARCH-REFERENCE.md`, with citation errors corrected.
>
> **§1 and §4–§8 are superseded.** They were written without reference to the running system,
> and §1's problem statement is wrong in two independent ways. Nothing here should be scoped
> into issues.

### 13.1 The premise: a sleeping host does not degrade anything

§1 builds the entire document on this sentence:

> "When the compute host sleeps, the edge node falls back to template thoughts."

It does not. `federation/compute_router.py` §P4b states the corrected order plainly:

> "The peer link's compute-offload is the *offline edge case*, not the normal path: the
> primary compute for both bodies is the **cloud LLM** directly."

The chain is **cloud → local model → peer → template → no-AI**. A sleeping Mac Studio costs
nothing; the cloud serves the turn. Template thoughts are reached only when the internet is
*also* down. And `federation/wake_on_lan.py` already wakes the workstation for the turn types
that can afford to wait (`high_value_event`, `sleep_consolidation`); interactive turns
deliberately take the template rather than make a user sit through a boot, and every deferred
turn replays when a tier returns.

So the degraded state this document is written to improve is an **internet outage**, not a
sleep transition — a far narrower and rarer window than §1 assumes.

### 13.2 The gap that is real is closed by a config flag, not a protocol

§1's second claim — that the two nodes accumulate divergent memory — *is* real, but only by
default. Singular-entity mode already solves it and already shipped:

- `memory_v2/peer_backend.py` — the workstation-side `PersonaMemoryStore` stand-in, an HTTP
  client against the canonical host. "The canonical memory lives on the always-on HA server,
  and both cognitions share one autobiography."
- `dashboard/routes/memory.py` — the peer memory API it calls.
- `.handoff/IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md` — P2a/P2b/P2c landed with SHAs.

The catch is the default: `canonical_memory_url: str = ""` (`config/being_config.py:267`).
**Opt-in, off out of the box.** So §4.2 proposes a Merkle-CRDT sync protocol to solve a
problem that setting one config value already solves.

**This is the only open decision in the document** — see §13.5.

### 13.3 Everything proposed either exists or does not fit

- **`memory_v2` already implements Phases 1–2.** The word "Haloysius" appears nowhere in
  §1–§12, yet `src/haloysius/memory_v2/` ships `store.py`, `graph.py`, `hierarchy.py`
  (RAPTOR), `reflection.py` (Self-RAG + CRAG), `consolidation.py`, `importance_scoring.py`,
  `knowledge_index.py`, `connection_discovery.py`, `temporal_graph.py`. Phase 1 is not a
  build; it is integration debt.
- **`federation/README.md` forbids the framing.** It opens: "It is **not** a greenfield
  system — it extends three existing foundations," and carries a *"Foundations (do not
  duplicate)"* table. This document duplicates it.
- **The sizing exceeds the hardware by 2–8×.** §4.1 asks for 50–200 GB per node. The
  satellite tiers allocate Halbert **10 GB / 25 GB / 50 GB** of storage and
  **0.5 / 1.0 / 1.5 GB** of RAM (`HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`).
  §11's own remedies inherit this: a 400 MB NLI cross-encoder does not fit a 1.0 GB budget
  already holding persona embeddings, and no `home` tier configures a local model at all —
  a settled policy, not a resource question. No drive fixes a 200 GB index on a 25 GB budget.
- **The semantic cache does not pay for itself.** Published production hit rates for
  open-ended conversational workloads are **10–20%**, and the guidance is that such caching
  "may not justify the operational complexity until volume crosses a few million requests per
  month." One household is ~10³/month. Static thresholds are separately unsound (vCache). See
  the reference doc §6.
- **Silk Graph cannot ship.** FSL-1.0 with a non-compete, converting to Apache 2.0 after two
  years. Halbert is GPL-3.0-or-later. A dependency that fails the licence gate should not
  reach a phase table.
- **The embedding question was already answered.** §11.6 reopens it; per-node embeddings stay
  on the satellite via Haloysius's `MemoryEmbedder`, and `embedder_factory.py` is where any
  negotiation belongs.

### 13.4 Disposition

| From §8 | Verdict | Why |
| :--- | :--- | :--- |
| 1 — Local archival tier | **Dropped** | `memory_v2` exists |
| 2 — Reflection engine | **Dropped** | `reflection.py` exists |
| 3 — Semantic response cache | **Dropped** | Premise wrong (§13.1); 10–20% hit rate at ~1000× too little volume |
| 4 — Cross-node CRDT sync | **Dropped** | Licence-blocked; solved by a config default (§13.2) |
| 5 — Portable sleep/wake transfer | **Dropped** | Gated on 4 |
| 6 — Adaptive cache thresholds | **Dropped** | Gated on 3 |
| §2–§3 literature | **Kept** | Extracted to `documentation/design/AGENT-MEMORY-RESEARCH-REFERENCE.md` |

Also worth keeping regardless of any of the above: **MELD's contradiction-preservation
principle** — a detected conflict is preserved for later adjudication, never silently
resolved. That needs no protocol.

### 13.5 The one open decision

**Should singular-entity mode be the default?**

| | Default ON | Default OFF (today) |
| :--- | :--- | :--- |
| Memory | One canonical autobiography | Two stores, divergent over time |
| Cost | Config change | — |
| Risk | Canonical host down = no memory | Nodes learn in isolation (§1's real gap) |

Not urgent, and not a research question. Decide it directly and set the default; there are no
users and no migration to carry.
