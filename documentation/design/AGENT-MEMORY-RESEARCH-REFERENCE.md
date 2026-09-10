# Agent Memory: Research Reference (2023–2026)

> **Purpose:** A verified map of the LLM-agent memory literature, kept as a standing
> reference. This is **not** a proposal and carries no roadmap commitment.
>
> **Provenance:** Extracted from `.handoff/DISTRIBUTED-MEMORY-ARCHITECTURE-2026-09-09.md`,
> whose proposal sections were superseded. The literature survived that review; the
> proposal did not. Citation errors found in review are corrected here.
>
> **Verification:** Ten of the twenty citations were resolved directly against arXiv, ACL
> Anthology and GitHub on 2026-09-09. Each matched its description. Items not
> independently resolved are marked *(unverified)*.
>
> **Date:** 2026-09-09

---

## 1. Taxonomy

Three surveys converge on a taxonomy that supersedes the older short-term/long-term split.

**Memory for Autonomous LLM Agents** (arXiv:2603.07670, 2026) formalises memory as a
**write–manage–read loop** coupled with perception and action, with five mechanism families:

1. Context-resident compression (summarisation inside the window)
2. Retrieval-augmented stores (external vector index)
3. Reflective self-improvement (synthesising insight from raw memories)
4. Hierarchical virtual context (MemGPT-style paging)
5. Policy-learned management (RL-trained access policies)

Open challenges it names: continual consolidation, causally grounded retrieval, trustworthy
reflection, **learned forgetting**, multimodal embodied memory.

**Memory in the Age of AI Agents** (arXiv:2512.13564, 2025) splits memory by *form* —
token-level, parametric, latent — and by *function*:

| Function | Holds | Halbert example |
| :--- | :--- | :--- |
| Factual | Facts about the world | "the user's name is Eric" |
| Experiential | What happened | "at 18:04 the user arrived home" |
| Working | Current task state | "mid-way through the winter thermostat schedule" |

**From Storage to Experience** (ACL Findings 2026) adds the evolutionary axis:
**Storage → Reflection → Experience**, i.e. trajectory preservation, then refinement, then
abstraction. The frontier is cross-trajectory abstraction.

**AI Meets Brain** (arXiv:2512.23343, 2025) maps cognitive-neuroscience categories onto
agents: procedural (skills), semantic (facts), episodic (events in time and context).

### The five-component model

**Portable Agent Memory** (arXiv:2605.11032, 2026) synthesises these into
**M = (E, S, P, W, I)** — episodic, semantic, procedural, working, identity. Useful mainly
as *vocabulary* for describing what a memory store already holds.

> Its transfer-continuity results (0.83–0.92 vs 0.28–0.45 baseline) come from a **pilot study
> across three models**. Promising, not established.

---

## 2. Tiered memory (MemGPT / Letta)

**MemGPT: Towards LLMs as Operating Systems** — **Packer et al.**, arXiv:2310.08560 (Oct
2023, rev. Feb 2024). *Frequently misattributed to Park et al. and to UIST 2024; it is
neither.* Virtual context management by paging between the window and external storage:

| Tier | Analogy | Description |
| :--- | :--- | :--- |
| Core | RAM | Always in context — persona, human, current task |
| Archival | Disk | Vector-indexed external store, searched by tool call |
| Recall | Log | Full message history |

Letta is the production continuation, with pluggable archival backends (pgvector,
SQLite+Chroma, Milvus, Qdrant, Turbopuffer).

**Caveat:** the OS analogy is *conceptual*. It specifies no latency budget, and it is
routinely over-read as a storage-performance argument. Where an archival tier fits in RAM,
the disk half of the analogy does not apply at all.

---

## 3. Retrieval scoring and reflection (Generative Agents)

**Generative Agents** — Park et al., UIST 2023, arXiv:2304.03442.

```
score = α_rec · recency + α_imp · importance + α_rel · relevance
```

- **Recency** — exponential decay; the original decayed by event index, modern systems use
  wall-clock half-lives on both creation and access
- **Importance** — LLM-assigned 1–10
- **Relevance** — cosine similarity to the query embedding

The original weights `[0.5, 3, 2]` are a **hand-tuned heuristic, not a principled result**
(per the [Agent Memory Atlas](https://neoneye.github.io/agent-memory-atlas/systems/generative-agents/)).
Treating them as derived is a common error.

**Reflection:** when accumulated importance crosses a threshold, the agent synthesises
higher-level insights and writes them back at higher importance. Note that reflection
requires **language generation** — clustering similar memories by embedding is retrieval,
not reflection. Embeddings can tell you thirty entries concern bedtime; they cannot conclude
that bedtime shifted.

---

## 4. Self-organising memory (A-Mem)

**A-Mem: Agentic Memory for LLM Agents** — Xu et al., NeurIPS 2025, arXiv:2502.12110.
Zettelkasten-inspired: each new memory gets structured attributes (context, keywords, tags),
the system links it to related historical memories, and integration can **update the
attributes of existing memories**.

Relevance: a linked graph makes delta sync tractable — you can ship new nodes and edges
rather than the whole store.

---

## 5. Distributed memory protocols

**SAMEP: A Secure Protocol for Persistent Context Sharing Across AI Agents** — Hari Masoor,
arXiv:2507.10562, 2025. Distributed repository with vector search, AES-256-GCM, fine-grained
per-memory access control, audit trails.

> Two cautions. It is a **separate REST protocol** — described as *compatible with* MCP and
> A2A, not carried over MCP's JSON-RPC transport. And its headline "73% reduction in
> redundant computations" comes from multi-agent software development, HIPAA healthcare and
> multimodal pipelines — collaboration workloads where several agents recompute the same
> thing. Treat it as an upper bound from another domain.

**MELD: A Protocol for Merging Knowledge Across Distributed Agentic Memories** —
arXiv:2608.16357, 2026. The most interesting entry here. Five-outcome admission for every
incoming claim — **insert, merge, relate, conflict, reject** — decided from scoped claim-key
identity, embedding similarity, and a natural-language-inference verdict. A per-claim status
CRDT keeps peers coherent with no coordinator; reconverged in 30/30 partition-heal trials;
merge classifier AUC 0.968 at a 0.013 false-merge rate.

Its most portable idea needs none of the protocol: **contradictions are preserved, not
adjudicated.** A detected conflict is kept for later resolution rather than silently
resolved. That principle is worth adopting in any memory store.

> Cost: the NLI rung is a **cross-encoder model**, not an embedding comparison. Without it
> the classifier degrades to similarity-only with a higher false-merge rate. Roughly
> 100–400 MB of model — material on constrained hardware.

**CRDT substrate.** Merkle-CRDTs (content-addressed ops in a DAG; sync exchanges only
missing ops; order-independent convergence) fit knowledge-graph sync best — delta-only, no
coordinator, self-healing, tamper-evident.

> **Licensing trap:** [Silk Graph](https://github.com/Kieleth/silk-graph), the obvious
> Merkle-CRDT graph engine (Rust, PyO3 bindings), is **Functional Source License 1.0**,
> converting to Apache 2.0 after two years. It is source-available with a non-compete — not
> an OSI licence and **not GPL-compatible**. It cannot ship in Halbert today.

**CoMIC** — arXiv:2606.00756, 2026. *Centralized Reflection, Decentralized Execution*: edge
agents execute locally; a cloud critic asynchronously evaluates trajectories and circulates
reusable experience keyed by subgoal. Weak edge agents improve without parameter updates.

> The **pattern** generalises. The mechanisms are built for long-horizon symbolic planning
> with subgoals and trajectories, and do not transfer directly to short event-driven turns.

**DisCEdge** — arXiv:2511.22599, EuroMLSys 2026. Context stored and replicated between edge
nodes as **token sequences** rather than raw text: smaller payloads, no re-tokenisation on
receipt.

| Metric | Reduction | Applies to |
| :--- | :--- | :--- |
| Client request size | 90% | Client → edge (session reference vs full context) |
| **Inter-node sync overhead** | **15%** | Edge → edge replication |
| Response time | 14.5% | End-to-end |

> The 90% figure is widely misquoted as a sync-efficiency result. For node-to-node sync the
> relevant number is **15%**.

---

## 6. Semantic response caching

Cache LLM responses by embedding similarity; serve a hit without a round trip.

**The hit rate is the whole question, and published production data is sobering:**

| Workload | Observed hit rate |
| :--- | :--- |
| Open-ended conversational chat | **10–20%** — "reliably fails" |
| Long-tail conversational agents | 10–25% |
| Production overall | 20–45% (not the 90–95% marketed) |
| High-volume narrow categories (code, common docs) | 40–60% |

Reported guidance is that conversational caching "may not justify the operational complexity
until volume crosses a few million requests per month." Vendor "95%" claims generally refer
to **match correctness on hits**, not hit frequency — a routinely conflated distinction.

**Thresholds are harder than they look.** [vCache](https://arxiv.org/pdf/2502.03771) shows
static thresholds are fundamentally limited: similarity distributions for correct and
incorrect candidates overlap heavily and the optimum shifts with the embedding model, so one
cutoff either breaks the error budget or collapses toward exact match. GPTCache's default
0.7 is documented as suboptimal; [MeanCache](https://arxiv.org/pdf/2403.02694) reports
markedly fewer false hits. Adaptive, per-category or verified thresholds are the live
direction — and they are *more* machinery, not less.

> **Bottom line for a single-household deployment: the arithmetic does not work.** A 10–20%
> hit rate on ~10³ queries/month saves a couple hundred calls, against a vector index,
> threshold tuning, TTL policy and invalidation logic. Revisit only if volume grows by
> orders of magnitude or a narrow high-repetition category appears.

---

## 7. References

Verified 2026-09-09 unless marked.

### Papers

1. **MemGPT: Towards LLMs as Operating Systems** — Packer et al., arXiv:2310.08560 (2023, rev. 2024). No conference venue.
2. **Generative Agents: Interactive Simulacra of Human Behavior** — Park et al., UIST 2023, arXiv:2304.03442, doi:10.1145/3586183.3606763.
3. **A-Mem: Agentic Memory for LLM Agents** — Xu et al., NeurIPS 2025, arXiv:2502.12110.
4. **SAMEP: A Secure Protocol for Persistent Context Sharing Across AI Agents** — Masoor, arXiv:2507.10562 (2025).
5. **MELD: A Protocol for Merging Knowledge Across Distributed Agentic Memories** — arXiv:2608.16357 (2026).
6. **DisCEdge: Distributed Context Management for LLMs at the Edge** — arXiv:2511.22599, EuroMLSys 2026.
7. **Portable Agent Memory** — Ravindran, arXiv:2605.11032 (2026).
8. **CoMIC: Collaborative Memory and Insights Circulation for Long-Horizon LLM Agents in Cloud-Edge Systems** — arXiv:2606.00756 (2026).
9. **vCache: Verified Semantic Prompt Caching** — arXiv:2502.03771.
10. **MeanCache: User-Centric Semantic Caching for LLM Web Services** — arXiv:2403.02694.
11. **FedCache** — arXiv:2308.07816 (2023). *(unverified)*

### Surveys

12. **Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers** — arXiv:2603.07670 (2026).
13. **Memory in the Age of AI Agents** — arXiv:2512.13564 (2025). *(unverified)*
14. **From Storage to Experience: A Survey on the Evolution of LLM Agent Memory Mechanisms** — ACL Findings 2026.
15. **AI Meets Brain: A Unified Survey on Memory Systems** — arXiv:2512.23343 (2025). *(unverified)*
16. **A Survey on the Memory Mechanism of LLM based Agents** — arXiv:2404.13501 (2024). The earliest comprehensive survey.

### Implementations

17. **Letta (formerly MemGPT)** — https://github.com/letta-ai/letta. Apache 2.0.
18. **Silk Graph** — https://github.com/Kieleth/silk-graph. **FSL-1.0 → Apache 2.0 after two years. Not GPL-compatible.**
19. **Redis SemanticCache (RedisVL)** — vendor feature, not a paper.
20. **FluxCache** — https://github.com/bv-saketha-rama/flux-cache. Its "30–80% cost reduction, 40× latency" figures are **"Expected Impact (v1.0)" targets** on a two-commit, pre-v0.1.0 repo — not measurements. Do not cite as results.
21. **Agent Memory Atlas** — https://neoneye.github.io/agent-memory-atlas/. Critical commentary on the Generative Agents scoring function.
