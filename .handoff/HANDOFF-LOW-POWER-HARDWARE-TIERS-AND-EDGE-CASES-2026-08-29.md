# Low-Power Operation Mode: Edge Cases, Hardware Tiers, and Low-Spec LLM Assessment

**Date:** 2026-08-29  
**Status:** Approved & Implemented — Reference Specification & Operational Guidelines  
**Scope:** Practical user edge cases, dual-track hardware requirements (Home vs. Workstation), dedicated resource headroom analysis, Home Assistant SourcePrep scoping, and low-parameter/quantized local LLM analysis.

---

## 1. Executive Summary

With the completion of Phase 7 (Multi-Instance & Config Isolation) and Phase 8 (4-Slot Model Architecture & Light Variant Packaging), Halbert runs across a broad hardware spectrum ranging from legacy dual-core Intel machines and low-power Intel N100/N150 mini PCs to Raspberry Pi 4/5 ARM64 boards, up to high-end Apple Silicon workstations.

This document establishes:
1. **Practical user edge cases & compatibility solutions** identified during Phase 8 implementation.
2. **Dual-Track Hardware Requirements** separating **Home Appliance / Hub** deployments from **Workstation / Sysadmin Server** deployments.
3. **Dedicated Resource Headroom vs. Total Host Sizing**: Clearly distinguishing the unreserved RAM/CPU budget Halbert consumes from the total host capacity required when co-located with sibling workloads (Home Assistant, Frigate, IDEs, browsers).
4. **Minimum SourcePrep requirements** for Home Automation (HA) vs. Full Sysadmin contexts.
5. **Local `secure_model` assessment**, evaluating 1B–4B parameter models, CPU duty cycles, and quantization strategies on edge hardware.

---

## 2. Practical User Edge Cases & Compatibility Solutions

### 2.1 Model Configuration & First-Boot UX

#### Edge Case 1: Empty Local Model List Locks Out `secure_model` in Model Picker
* **Problem:** In `@halbert/model-picker` (`RoleAssignmentRow.tsx`), filtering endpoints for `requiresLocal` checked whether an installed model on that endpoint had `isLocal: true`. On a fresh install where Ollama is running but no model has been pulled yet, the endpoint was filtered out of the `Secure (Local)` dropdown entirely.
* **Resolution:** Filter endpoints by `providerDescriptor(e.provider).isLocal` or endpoint URL loopback status rather than requiring an existing model. This allows the user to select "Local Ollama" and view the actionable prompt: *"No models found on endpoint — pull a model via `ollama pull <model>`"*.

#### Edge Case 2: URL Formatting Without `http://` Scheme
* **Problem:** In `llm_config.py:_is_local_url()`, `urlparse(url).hostname` is used to enforce localhost loopback. When a user enters `localhost:11434` or `127.0.0.1:11434` without `http://`, `urlparse` treats `localhost` as the URL scheme, leaving `hostname = None`, which caused `_is_local_url()` to return `False` and silently disable the slot.
* **Resolution:** Ensure `_clean_endpoint()` and `_is_local_url()` normalize URLs lacking a scheme by prepending `http://` prior to parsing.

#### Edge Case 3: Containerized Environments (Docker / Podman Host Bridge)
* **Problem:** In containerized setups where Halbert runs in Docker and reaches Ollama on the host via `http://host.docker.internal:11434` or bridge IP `http://172.17.0.1:11434`, standard loopback IP checks failed.
* **Resolution:** Whitelist `host.docker.internal` and `gateway.docker.internal` in `_is_local_url()`.

---

### 2.2 Runtime Resilience & Network Failovers

#### Edge Case 4: Cloud `chat_model` Goes Offline
* **Problem:** Users configured with Cloud `chat_model` (OpenAI/Anthropic) and local `secure_model` (Ollama) lose chat functionality during an ISP outage, even though local compute is available.
* **Resolution:** When a Cloud request fails due to network disconnect/timeout, display a non-blocking UI alert banner with a 1-click fallback: *"Cloud endpoint unreachable (Offline). Switch Chat to local model?"*

#### Edge Case 5: Context Window KV-Cache CPU Latency on Low-Power Cores
* **Problem:** On an Intel N100 or Raspberry Pi 5, allocating a 32k context window (`num_ctx: 32768`) in system RAM causes high prompt ingestion latency (20–40s before first token).
* **Resolution:** For `SBC_LOW_POWER` ($\le 4\text{GB}$) and `ENTRY_8GB` ($4\text{–}8\text{GB}$) hardware profiles, cap the automatic `num_ctx` expansion to $8192$ tokens (configurable via `HALBERT_NUM_CTX_MAX`).

#### Edge Case 6: Remote SourcePrep Server Goes Offline / Sleep
* **Problem:** A low-power client offloading SourcePrep to a networked workstation (`SOURCEPREP_URL=http://desktop.lan:8400`) experiences retrieval drops when the workstation sleeps.
* **Resolution:** `SourcePrepRetrievalBackend` catches connection errors and fails open (returns empty context without raising), allowing the agent to answer using conversational context. Settings UI displays live status: *"Remote SourcePrep unreachable (operating in un-indexed fallback mode)"*.

---

### 2.3 Variants & Multi-Instance Flow

#### Edge Case 7: Home Assistant Credential Precedence (`home-light` vs `home`)
* **Problem:** `home-light` allows `ha_url` and `ha_token` in `being.yml` (single-file deploy), while `home` uses `ha_config.yml`.
* **Resolution:** Enforce strict precedence: `ha_config.yml` (if populated) overrides `being.yml`. When `home-light` boots without `ha_config.yml`, it seeds config from `being.yml`.

#### Edge Case 8: Navigating to Gated Features in `home-light`
* **Problem:** `home-light` disables sysadmin ingestion, discovery, and terminal session manager to minimize RAM and CPU load.
* **Resolution:** Gated routes render a clean informational card (*"Terminal / Discovery is disabled in home-light mode to conserve resources"*) with a button returning to Dashboard, rather than throwing 404 or unhandled errors.

---

## 3. Dedicated Resource Headroom vs. Total Host Sizing

When stating system requirements, we distinguish between:
1. **Dedicated Process Budget (Unreserved Headroom):** The specific slice of RAM, CPU cores, and storage I/O that Halbert and its local model backend (Ollama) strictly require to be free and available without contention.
2. **Total Host System Sizing:** The overall host machine capacity needed to run Halbert alongside its typical co-located sibling processes (Home Assistant + Frigate on Home Hubs; IDEs + Browsers + Docker on Workstations).

```
+-----------------------------------------------------------------------------------+
| HOME HUB / APPLIANCE TRACK (24/7 Headless Daemon)                                 |
| Halbert Dedicated Budget: 1.2GB - 3.5GB unreserved RAM | 1-2 CPU cores on burst   |
| Co-located Sibling Workloads: Home Assistant, Frigate NVR, MQTT, Wyoming Voice    |
+-----------------------------------------------------------------------------------+
| WORKSTATION / SYSADMIN TRACK (Interactive Terminal & Codebase Brain)             |
| Halbert Dedicated Budget: 1.5GB - 12GB unreserved RAM/VRAM | 2-4 CPU/GPU cores    |
| Co-located Sibling Workloads: IDEs, Browsers (50+ tabs), Docker, Compilers        |
+-----------------------------------------------------------------------------------+
```

### CPU Duty Cycle & Thermal Considerations
Running a local 3B–4B model on CPU (e.g. Intel N100 or Raspberry Pi 5) saturates 100% of all assigned CPU cores during active inference. 
* **Home Context:** If background cognitive monologue (`advance_turn`) runs constantly on CPU, it creates persistent fan noise, thermal throttling, and scheduling latency for real-time services (like Frigate video decoding or Wyoming voice audio streaming).
* **Architectural Rule:** In Home Hub / low-power deployments, cognitive monologue defaults to **template thoughts (`HALBERT_LLM_THOUGHTS=0`)**, keeping CPU utilization near 0% at idle and bursting only when an explicit user question or high-priority automation trigger occurs.

---

## 4. Track A: Home Appliance & Hub Requirements (`home` / `home-light`)

Designed for 24/7 continuous headless operation, smart home event streaming, and voice integration.

| Tier | Dedicated Halbert Budget (Unreserved Headroom) | Total Host Sizing (Accounting for Sibling Workloads) | Recommended Sibling Workloads | Local Model & Runtime Configuration |
|---|---|---|---|---|
| **Tier 1: Home Minimal** | **$\sim 1.2\text{GB}$ Free RAM**<br>1 shared CPU core<br>10GB free storage | **4GB RAM**<br>Quad-Core CPU (Pi 4, Celeron, RK3588)<br>32GB–64GB eMMC/SSD | Home Assistant Core + Mosquitto MQTT | • `HALBERT_VARIANT=home-light`<br>• `secure_model`: 1B–1.5B Q4 ($\sim 1\text{GB}$ RAM) or Template Thoughts<br>• `chat_model`: Cloud / LAN offload<br>• SourcePrep: Remote / Un-indexed |
| **Tier 2: Home Recommended** | **$\sim 3.0\text{GB}$ Free RAM**<br>2 CPU cores on burst<br>25GB free storage | **8GB – 16GB RAM**<br>4 E-cores / Quad-Core (N100, N150, Pi 5)<br>128GB+ NVMe SSD | Home Assistant OS + Frigate NVR (1–3 cams) + Wyoming Voice | • `HALBERT_VARIANT=home`<br>• `secure_model`: 3B–4B Q4 ($\sim 2.5\text{GB}$ RAM, 10–15 tok/s)<br>• `chat_model`: Cloud or local 3B–4B<br>• SourcePrep: Local HA-scoped ($\sim 150\text{MB}$) |
| **Tier 3: Home Power Hub** | **$\sim 5.0\text{GB}$ Free RAM**<br>4 CPU cores / iGPU<br>50GB free storage | **16GB – 32GB RAM**<br>Intel Core i5 / N305 / AMD Ryzen / Mac Mini<br>256GB+ NVMe SSD | Full HA Stack + Frigate (4+ HD cams) + Local Whisper + Plex/Jellyfin | • `HALBERT_VARIANT=home`<br>• `secure_model`: 4B–8B Q4/Q8 local model<br>• `chat_model`: 7B–8B local or Cloud<br>• Full Local HA SourcePrep + Voice |

---

## 5. Track B: Workstation & Sysadmin Server Requirements (`sysadmin`)

Designed for interactive terminal sessions, system diagnosis, and full-corpus SourcePrep code/config intelligence.

| Tier | Dedicated Halbert Budget (Unreserved Headroom) | Total Host Sizing (Accounting for Sibling Workloads) | Recommended Sibling Workloads | Local Model & Runtime Configuration |
|---|---|---|---|---|
| **Tier 1: Workstation Entry** | **$\sim 1.5\text{GB}$ Free RAM**<br>1 CPU core<br>15GB free storage | **8GB RAM**<br>Older Laptop / Desktop (2nd–8th Gen Core, 8GB RAM) | Lightweight OS + Terminal + Single Browser Window | • `halbert-core[light]`<br>• `secure_model`: 1B–2B Q4 or Template Thoughts<br>• `chat_model`: Cloud API (OpenAI/Anthropic)<br>• SourcePrep: Remote LAN Offload |
| **Tier 2: Workstation Semi-Pro** | **$\sim 2.5\text{GB} – 3.0\text{GB}$ Free RAM**<br>2 CPU cores / Neural Engine<br>30GB free storage | **16GB – 24GB RAM**<br>Apple Silicon Mac (M1/M2/M3/M4 16GB–24GB), PC Laptop 16GB–24GB | IDE (VS Code/Cursor) + Web Browser (40+ tabs) + Docker | **Single Local Model Rule:**<br>• `secure_model` & default `chat_model`: Apple Intelligence 3B (on ANE ~2.5GB) or single 3B local model<br>• `specialist_model`: **Cloud Frontier (Recommended)** (Claude 3.5 Sonnet, GPT-4o, Groq, Ollama Cloud)<br>• SourcePrep: Host config + Local scope |
| **Tier 3: Workstation Pro** | **$\sim 8\text{GB} – 12\text{GB}$ Free RAM / VRAM**<br>Dedicated GPU / Neural Engine<br>100GB free storage | **32GB – 36GB RAM (or Unified)**<br>Mac Studio / MacBook Pro 32GB, PC with RTX 3060/4060 (8–12GB VRAM) | Full Dev Suite + Multiple Containers + Heavy Compilations | • Full `halbert-core` with `[vision]` and `[cloud-apis]`<br>• `secure_model`: Apple Intelligence 3B or 7B–8B local model<br>• `chat_model` / `specialist`: 14B–32B Q4 local model OR Cloud Frontier<br>• SourcePrep: Full local 70k+ chunk corpus |
| **Tier 4: Sovereign Homelab** | **$\ge 24\text{GB}$ Free RAM / VRAM**<br>Multi-GPU / High-core CPU<br>250GB+ fast NVMe | **64GB – 128GB+ RAM**<br>Mac Studio 64–128GB, Dual RTX 3090/4090 Workstations, Proxmox Cluster | Multi-tenant virtualization + Cluster orchestrations | • 100% Offline Sovereign AI<br>• `chat_model` / `specialist_model`: 32B–70B local<br>• Local Whisper large-v3 + Piper TTS + VLMs<br>• Distributed SourcePrep hub for satellites |

---

## 6. Minimum SourcePrep Requirements: Home Automation (HA) vs. Sysadmin

A major architectural insight is the difference in resource overhead between indexing a **Full Sysadmin Knowledge Corpus** vs. a **Dedicated Home Automation Corpus**:

| Metric | Full Sysadmin Corpus | HA-Scoped Corpus |
|---|---|---|
| **Corpus Contents** | Arch-Wiki, macOS man-pages, Linux admin guides, kernel docs | HA entity registry, YAML automations, area topology, Frigate zones, device manuals |
| **Total Chunks** | 71,092 chunks | 500 – 5,000 chunks |
| **Disk Size** | $\sim 220\text{MB}$ (768-dim float32) | $\sim 1.5\text{MB} – 15\text{MB}$ |
| **Daemon RAM Overhead** | $\sim 1.2\text{GB} – 2.0\text{GB}$ RSS | $\sim 120\text{MB} – 180\text{MB}$ RSS |
| **Indexing CPU Time** | 10 – 30 minutes (CPU) | 5 – 20 seconds |
| **Minimum Headroom to Run Locally** | $\ge 2.0\text{GB}$ Dedicated RAM | **$\sim 200\text{MB}$ Dedicated RAM** |

### Deployment Rules for SourcePrep:
1. **Home Track ($\le 4\text{GB}$ Hosts):** Point `SOURCEPREP_URL` to a remote workstation or run in un-indexed fallback mode.
2. **Home Track ($\ge 8\text{GB}$ Hosts):** Local HA-scoped SourcePrep consumes only $\sim 150\text{MB}$ RAM and runs comfortably alongside Home Assistant and Frigate.
3. **Workstation Track ($\ge 16\text{GB}$ Hosts):** Full local SourcePrep daemon indexes the entire 70k sysadmin knowledge base without impacting desktop responsiveness.

---

## 7. Local LLM (`secure_model`) Assessment: 1B–4B Models & Quantization

The `secure_model` slot is mandatory for processing sensitive system configurations, API credentials, camera metadata, and internal persona monologue (`advance_turn` cognitive tick).

### 7.1 Parameter Size Evaluation for Low-Power Devices

| Parameter Class | Memory Headroom (Q4_K_M) | CPU Inference Speed (N100) | CPU Inference Speed (Pi 4) | Fitness for `secure_model` Role |
|---|---|---|---|---|
| **1B – 1.5B** | $\sim 0.8\text{GB} – 1.2\text{GB}$ | 20 – 35 tok/s | 10 – 16 tok/s | **Optimal for Minimal Tiers:** Ultra-low RAM, fast cognitive monologue summarization, low thermal impact. |
| **2B – 3B** | $\sim 1.4\text{GB} – 2.2\text{GB}$ | 15 – 22 tok/s | 6 – 10 tok/s | **Sweet Spot for 4GB–8GB Hosts:** Reliable tool calling, structured JSON output, safe privacy scrubbing. |
| **3.8B – 4B** | $\sim 2.4\text{GB} – 3.2\text{GB}$ | 10 – 15 tok/s | 3 – 5 tok/s | **Standard for 8GB–16GB Hosts:** Strong reasoning, reliable schema adherence, fits alongside HA. |
| **7B – 8B** | $\sim 4.5\text{GB} – 5.8\text{GB}$ | 4 – 7 tok/s | 1 – 2 tok/s (OOM risk) | **Pro Tiers only ($\ge 16\text{GB}$ RAM):** Too heavy for low-power CPU-only hosts. |

### 7.2 Quantization Strategies for Constrained Memory

1. **`Q4_K_M` (4-bit medium - Default Baseline):**
   * Memory factor: $\sim 0.65\text{ GB}$ per billion parameters.
   * Delivers the optimal balance between perplexity retention and inference throughput on x86/ARM SIMD/NEON.
2. **Smaller Model vs. Extreme Quantization:**
   * *Assessment:* Running a 4B model at 2-bit (`Q2_K`, $\sim 1.4\text{GB}$ RAM) causes significant degradation in structured JSON generation and tool schema adherence.
   * *Recommendation:* Prefer a **2B model at Q4_K_M** over a **4B model at Q2_K**. The 2B Q4 model has superior schema precision and lower latency with identical memory usage.
3. **Importance Matrix (`IQ3_S` / `IQ2_XXS`):**
   * Retains precision on critical attention heads while compressing feed-forward layers, enabling 3B models to run under $1.6\text{GB}$ RAM if memory is strictly constrained.

---

## 8. Actionable Implementation Checklist

- [x] 4-slot model configuration implemented (`chat_model`, `specialist_model`, `vision_model`, `secure_model`).
- [x] Local-only URL enforcement implemented with robust hostname/loopback parsing.
- [x] Dependency trimming complete (`[light]` extra without `torch`/`chromadb`).
- [x] Hardware profiles extended for `SBC_LOW_POWER` ($\le 4\text{GB}$) and `ENTRY_8GB` ($4\text{–}8\text{GB}$).
- [x] Multi-instance `home-light` runtime gating implemented.
- [ ] Fix Model Picker endpoint filtering for `requiresLocal` in `@halbert/model-picker` (`RoleAssignmentRow.tsx`).
- [ ] Add `http://` auto-prefixing in `_clean_endpoint()` and `_is_local_url()`.
- [ ] Whitelist `host.docker.internal` in `_is_local_url()`.
- [ ] Add 1-click local fallback prompt in chat UI when Cloud `chat_model` encounters connection errors.
- [ ] Document HA-scoped SourcePrep vs Remote SourcePrep setup in `deploy/README.md`.
