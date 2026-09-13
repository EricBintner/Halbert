# Shared Compute, Inference Dispatch & Workload Scheduling

**Location**: `.handoff/research/multi-node-systems/03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md`  
**Date**: 2026-09-12  
**Focus**: Network physics of distributed LLM serving, pipeline vs tensor parallelism, disaggregated prefill/decode, heterogeneous home hardware scheduling, and streaming redaction boundaries.

---

## 1. The Physics of LAN Compute: Bandwidth vs. Latency Math

When designing shared compute systems across a local home network, software engineers frequently run into physical hardware walls. Distributing deep learning workloads is governed by strict mathematical relationships between **compute density (TFLOPS)**, **memory bandwidth (GB/s)**, and **interconnect latency (ms)**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MEMORY & INTERCONNECT BANDWIDTH GAP                    │
│                                                                             │
│  Internal Bus (Apple M2 Ultra / M3 Max):    800 GB/s (800,000 MB/s)         │
│  Internal Bus (NVIDIA RTX 4090):           1,008 GB/s (1,008,000 MB/s)       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Thunderbolt 5 RDMA:                          10 GB/s    (10,000 MB/s)      │
│  10GbE Ethernet:                               1.25 GB/s  (1,250 MB/s)      │
│  1GbE Standard Home LAN:                       0.125 GB/s   (125 MB/s)      │
│  Home Wi-Fi 6 (Typical):                       0.05 GB/s     (50 MB/s)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **The 10,000x Discrepancy**: The internal memory bus of an AI workstation is **6,400 to 16,000 times faster** than a standard Gigabit home network. Any distributed architecture that attempts to split individual matrix multiplications across standard LAN cables will spend 99.9% of its time waiting on network packets.

---

## 2. Distributed Inference Paradigms: What Works on a LAN

We analyzed the three primary ways to split or share neural network inference across multiple machines:

```
Three Distributed Inference Paradigms:

1. Tensor Parallelism (TP)         2. Pipeline Parallelism (PP)      3. Request-Level Offloading
   [Matrix Split Across Nodes]        [Layers Split Across Nodes]       [Model Lives on 1 Node]

   Node A: [W1_left ]                 Node A: Layers 1–40 (Prefill)     Node A: Satellite / Audio
   Node B: [W1_right]                 Node B: Layers 41–80 (Decode)     Node B: High-RAM GPU Host
   ────────────────────────           ───────────────────────────       ─────────────────────────
   Requires AllReduce EVERY layer     Sends activations ONCE per pass   Sends prompt ONCE;
   FAILS on 1GbE / Wi-Fi              Viable on 10GbE / Thunderbolt     GOLD STANDARD for Home LAN
```

### 2.1 Tensor Parallelism (TP): Why It FAILS on Home LANs
Tensor parallelism splits individual weight matrices across GPUs. During each forward pass of a single transformer layer, all participating nodes must synchronize via an `AllReduce` operation.
- For an 80-layer model (e.g. Llama 3.3 70B or Qwen 2.5 72B), generating **one token** requires:
  $$\text{Sync Roundtrips per Token} = 80 \times 2 = 160 \text{ network roundtrips}$$
- On a standard 1GbE home switch, ping latency is $\approx 0.5\text{ ms} - 1.0\text{ ms}$. Over Wi-Fi, it is $\approx 5\text{ ms} - 15\text{ ms}$.
- **Latency Purely from Network Ping**:
  $$\text{LAN (1GbE)}: 160 \times 0.8\text{ ms} \approx 128\text{ ms per token} \implies \mathbf{\le 7.8\text{ tok/s}}$$
  $$\text{Wi-Fi}: 160 \times 10\text{ ms} \approx 1,600\text{ ms per token} \implies \mathbf{0.6\text{ tok/s}}$$
- **Verdict**: Tensor parallelism without specialized hardware (NVLink, InfiniBand, or Thunderbolt 5 RDMA) is completely unusable on standard home networks.

### 2.2 Pipeline Parallelism (PP): Viable for Layer Pooling
Pipeline parallelism splits the model sequentially by layers (e.g., Node A hosts layers 1–32; Node B hosts layers 33–64).
- Activations are transmitted across the network **only once per forward pass** (at the boundary between layer 32 and 33).
- **Payload Size**: For Llama 3 8B, hidden dimension $d = 4096$. In FP16, $4096 \times 2\text{ bytes} = 8\text{ KB}$ per token.
- Transmitting $8\text{ KB}$ over 1GbE takes $\approx 0.064\text{ ms}$.
- **Trade-off**: Pipeline bubbles (Node B sits idle while Node A computes, unless micro-batching is used). However, it allows pooling RAM from two modest machines to run a model that neither could fit alone.

### 2.3 Request-Level Offloading: The Gold Standard for Home Networks
Halbert's current model (`halbert_core/federation/compute_router.py`) uses **Request-Level Smart Routing**:
- The entire model resides on the workstation in high-bandwidth unified RAM (150–800 GB/s).
- The satellite captures user voice/text, constructs the prompt, and sends a single HTTP request ($5 - 20\text{ KB}$) over the LAN.
- The workstation generates tokens at peak memory bandwidth ($30 - 80\text{ tok/s}$) and streams tokens back via Server-Sent Events (SSE).
- **Network Overhead**: Less than $15\text{ ms}$ total across the entire conversation turn.

---

## 3. Survey of Cutting-Edge Distributed AI Systems

| Framework | Architecture | Interconnect Requirements | Target Workload | Key Insight for Halbert |
|---|---|---|---|---|
| **Exo** (`exo-explore/exo`) | Dynamic pipeline + tensor parallelism across consumer devices. | Thunderbolt 5 RDMA or high-speed Wi-Fi. | Pooling fragmented RAM (Mac + iPad + PC). | Automatic topology discovery via mDNS; dynamic placement graph. |
| **Petals** (BigScience / ACL '23) | BitTorrent-style decentralized pipeline serving. | Internet / WAN compatible (fault-tolerant). | Community-hosted 70B+ models. | Dynamic rerouting when a node drops or stutters mid-generation. |
| **llama.cpp RPC** (`ggml-rpc`) | Remote tensor backend execution over TCP. | Dedicated 10GbE network recommended. | Offloading layers to headless Linux GPU boxes. | Minimalist C++ backend; avoids Python runtime overhead on satellites. |
| **Splitwise** (ISCA '24) | Disaggregated Prefill and Decode serving. | High-bandwidth (KV-cache transfer required). | Data center throughput optimization. | Prefill is compute-bound; Decode is bandwidth-bound. |
| **DistServe** (OSDI '24) | Decoupled prefill and decode with SLA guarantees. | High-speed interconnect. | Strict TTFT and TBT deadline management. | Separate priority queues for initial latency vs sustained generation. |

---

## 4. Heterogeneous Home Hardware Tiering

In a real household, hardware capabilities vary widely. Halbert must route turns according to measured hardware profiles (`model/hardware_detector.py`):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HETEROGENEOUS HOME HARDWARE TIERS                        │
│                                                                             │
│  Tier A: High-Power Unified Compute (Mac Studio M-Series, 64–128GB)         │
│  Capabilities: 70B Q4 (15–25 tok/s), 32B Q4 (35–50 tok/s), SourcePrep RAG   │
│  Role: Primary LLM engine, deep reasoning, long-term memory consolidation    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tier B: Discrete GPU Workstation (NVIDIA RTX 4070/4090, 12–24GB VRAM)      │
│  Capabilities: Extremely fast 8B–14B (80–120 tok/s), Whisper, SD/Flux image  │
│  Role: Instantaneous interactive voice turns, vision and acoustic analysis  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tier C: Low-Power Edge Mini-PC (Intel N100 / AMD Ryzen, 8–16GB RAM)        │
│  Capabilities: 3B Q4 CPU (10–14 tok/s), Whisper base, Home Assistant core   │
│  Role: Always-on coordinator, offline emergency fallback, sensor intake     │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tier D: Micro Edge Satellite (Raspberry Pi 4/5, 2–4GB RAM)                 │
│  Capabilities: Sherpa-ONNX, Piper TTS, Template Thoughts (NO local LLM)     │
│  Role: Room voice pod, presence sensor, smart speaker microphone            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Deadline-Aware Scheduling & Priority Queuing

Halbert's `ComputeBroker` (`halbert_core/federation/compute_broker.py`) implements priority queuing. Research into real-time interactive systems reveals strict human perception deadlines:

### 5.1 The 1.5-Second Human Perception Threshold
- **Spoken Conversation**: A human interlocutor expects a response within **800ms – 1,500ms**. A delay beyond 1.5 seconds creates awkward silence and conversational breakdown.
- **Halbert Invariant**: Priority 2 (`interactive_user`) requests have a strict `VOICE_QUEUE_TIMEOUT_S = 1.5`. If the remote workstation cannot allocate a GPU slot within 1.5 seconds, the request **aborts and falls back to local fast template thoughts**.

### 5.2 The 4-Tier Turn Classification Matrix

| Turn Classification | Offload to Peer? | Priority Level | Deadline / Timeout | Fallback if Peer Busy / Offline |
|---|:---:|:---:|:---:|---|
| `interactive_user` (Voice/Chat) | **YES** | **Priority 2** | **1.5s queue timeout** | Fast local template thoughts (<100ms) |
| `high_value_event` (Alarm, Leak) | **YES** | **Priority 3** | 10.0s timeout | Local deterministic heuristic rules |
| `sleep_consolidation` (Memory reflection) | **YES** | **Priority 4** (Batch) | Deferred | Staged in queue until workstation is idle |
| `cognitive_monologue` (Internal tick) | **NO** | Local only | None | Template thoughts; **NEVER offloaded** |

> [!CAUTION]
> **The Cognitive Contention Trap**:
> An agent running an internal monologue tick every 5–10 seconds must **never** offload monologue turns to a peer GPU. Ten room satellites offloading monologue would flood the compute host with 60–120 requests per minute, permanently locking the GPU and starving the user's interactive prompts.

---

## 6. Streaming Responses & The Chunked Redaction Boundary

Halbert enforces a non-negotiable security invariant: **Tier 2 secrets (passwords, tokens, API keys) must be scrubbed deterministically before leaving a machine or being displayed (`DECISIONS.md` line 16).**

### 6.1 The Streaming Redaction Problem
When streaming tokens via Server-Sent Events (SSE), a secret can be split across arbitrary token boundaries:
```
Chunk 1: "Your API key is sk-proj-"
Chunk 2: "9xK209aF..."
```
If Chunk 1 is emitted immediately, the secret prefix leaks over the wire before the redaction regex can evaluate the full token pattern!

### 6.2 The Sliding-Window Buffering Redaction Filter

To stream tokens in real time without leaking split secrets, we implement a **Sliding-Window Lookahead Buffer**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SLIDING-WINDOW STREAMING REDACTION                      │
│                                                                             │
│  Incoming Tokens: [ "Your", " API", " key", " is", " sk-proj-", "9xK2...", " now" ]
│                                                                             │
│                     ┌───────────────────────────────┐                       │
│  Emitted to Client: │ Lookahead Window (e.g. 32 ch) │ ◄── Buffers newest    │
│  ◄───────────────── │ (Scans for partial secret     │     tokens before     │
│  "Your API key is " │  prefixes: "sk-", "ghp_", etc)│     releasing to wire │
│                     └───────────────────────────────┘                       │
│                                                                             │
│  If prefix detected: Hold buffer until pattern completes or fails match.    │
│  If match: Replace with "<secret>" and release.                             │
│  Added Latency: < 30ms (negligible for human reading speed).               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Mechanics**:
1. The filter maintains a buffer of unreleased characters (typically 32–48 characters, corresponding to the longest known secret prefix).
2. As new tokens arrive from Ollama/vLLM, text exiting the left of the window is passed through deterministic regex redaction and emitted as an SSE chunk.
3. If the window contains an ambiguous prefix (e.g., `sk-` or `BEGIN PRIVATE KEY`), emissions pause until enough characters arrive to confirm or refute the pattern.
4. Total latency added to interactive voice/chat: **15–30 ms** (completely imperceptible to users).

---

## 7. Recommended Compute Broker Architecture for Halbert

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HALBERT SHARED COMPUTE DISPATCHER                        │
│                                                                             │
│  Satellite (Pi 5)                                   Compute Host (Mac)      │
│  ┌─────────────────────────┐                        ┌─────────────────────┐ │
│  │ ComputeRouter           │                        │ ComputeBroker       │ │
│  │  - Probe peer health    │                        │  - Slot 1: Desktop  │ │
│  │    (rolling 3-failure)  │                        │    (Local P1)       │ │
│  │  - Classify turn        │  POST /api/compute/v1/ │  - Slot 2-4: Semaph │ │
│  │    (P1, P2, P3, P4)     │  chat/completions      │    (P2 Voice / P3)  │ │
│  │  - 1.5s Voice Timeout   ├───────────────────────►│  - PriorityQueue    │ │
│  │                         │  (Bearer Token / mTLS) │                     │ │
│  │                         │                        │ Engine: Ollama/vLLM │ │
│  │ Local Fallback:         │ ◄──────────────────────┤ (Local 32B/70B)     │ │
│  │  - Fast CPU Template    │  SSE Stream with       │                     │ │
│  │  - Micro 3B (if 8GB RAM)│  Sliding Redaction     │ Sliding Window      │ │
│  └─────────────────────────┘                        │ Redaction Filter    │ │
│                                                     └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Keep Request-Level Offloading**: Avoid tensor-parallelism over LAN. Route full turns to the node holding the appropriate model.
2. **Strict 1.5s Voice Preemption**: Enforce `ComputeBroker.VOICE_QUEUE_TIMEOUT_S = 1.5` so voice pods never hang waiting on batch jobs.
3. **Sliding-Window SSE Redactor**: Wire the lookahead redaction filter into `compute_endpoint.py` to enable streaming chat without compromising secret redaction.
4. **Selective Wake-on-LAN**: Send WoL magic packets only for asynchronous turns (`sleep_consolidation`, deep indexing). Let interactive turns take immediate local templates rather than making the user wait for a Mac to boot.
