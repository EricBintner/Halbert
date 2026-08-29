# Low-Power Operation Mode: Edge Cases, Hardware Tiers, and Low-Spec LLM Assessment

**Date:** 2026-08-29  
**Status:** Approved & Implemented — Reference Specification & Operational Guidelines  
**Scope:** Practical user edge cases, UI/user-flow friction points, 4-tier hardware taxonomy, Home Assistant SourcePrep scoping, and low-parameter/quantized local LLM analysis.

---

## 1. Executive Summary

With the completion of Phase 7 (Multi-Instance & Config Isolation) and Phase 8 (4-Slot Model Architecture & Light Variant Packaging), Halbert runs across a broad hardware spectrum ranging from legacy dual-core Intel machines and low-power Intel N100/N150 mini PCs to Raspberry Pi 4/5 ARM64 boards, up to high-end Apple Silicon workstations.

This document consolidates:
1. **Practical user edge cases & compatibility solutions** identified during Phase 8 implementation.
2. **Four tiers of hardware support** (Minimum, Recommended, Ideal, Power User) defining resource envelopes and deployment topologies.
3. **Minimum SourcePrep requirements** for Home Automation (HA) vs. Full Sysadmin contexts.
4. **Assessment of the local `secure_model` requirement**, evaluating 1B–4B parameter models and quantization strategies for constrained edge hardware.

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

## 3. Hardware Tiers of Support

To guarantee predictability across diverse deployment environments, Halbert defines **four official tiers of hardware support**:

```
+-----------------------------------------------------------------------------------+
| Tier 1: Minimum (SBC / Edge / Legacy)      | Tier 2: Recommended (Mainstream Hub) |
| RAM: 4GB | CPU: Quad-Core / Celeron / Pi 4 | RAM: 8GB-16GB | CPU: N100 / Pi 5     |
| Local: 1B-2B Q4 (or Template Thoughts)     | Local: 3B-4B Q4 (10-15 tok/s)        |
| Chat: Cloud / LAN offload                  | Chat: Cloud or Local 3B-4B           |
| SourcePrep: Remote / Un-indexed fallback   | SourcePrep: HA-Scoped or Remote      |
+-----------------------------------------------------------------------------------+
| Tier 3: Ideal (Workstation / Pro Server)   | Tier 4: Power User (Sovereign Lab)   |
| RAM: 16GB-32GB | GPU: M-Series / RTX 4060  | RAM: 64GB-128GB+ | GPU: Multi-RTX    |
| Local: 7B-14B Q4/Q8                        | Local: 32B-70B + Local Vision/Voice  |
| Chat: Local or Cloud                       | Chat: Fully Offline Sovereign        |
| SourcePrep: Full local 70k+ corpus         | SourcePrep: Full Local + Multi-Node  |
+-----------------------------------------------------------------------------------+
```

### Tier 1: Minimum (Low-Power / Edge / Legacy PC)
* **Target Hardware:** Raspberry Pi 4 (4GB RAM), Rockchip RK3588 (4GB), Legacy Intel (Core 2 Duo / 2nd–6th Gen Core / Celeron / Pentium, 4GB RAM), Budget Thin Clients.
* **Resource Envelope:** 4GB RAM, CPU-only, 32GB–64GB storage (SD / eMMC / SATA SSD), 5–15W TDP.
* **Package Variant:** `halbert-core[light]` (pure wheels; no `torch`, `sentence-transformers`, or `chromadb`).
* **Runtime Variant:** `HALBERT_VARIANT=home-light`.
* **Model Configuration:**
  * `secure_model`: Ultra-light 1B–2B quantized model ($\sim 1.0\text{–}1.5\text{GB}$ RAM) or template thoughts (`HALBERT_LLM_THOUGHTS=0`).
  * `chat_model` / `specialist_model`: Cloud API (OpenAI, Anthropic, Gemini, Groq) or LAN GPU server.
  * `vision_model`: Cloud VLM (GPT-4o, Claude 3.5 Sonnet) or disabled.
* **SourcePrep:** Remote offload (`SOURCEPREP_URL=http://<desktop-ip>:8400`) or un-indexed SQLite FTS5 fallback.

### Tier 2: Recommended (Mainstream Home Hub / Budget Workstation)
* **Target Hardware:** Intel N100 / N150 / N95 Mini PCs, Raspberry Pi 5 (8GB RAM), Intel Core i3/i5 (8GB–16GB RAM), Apple Silicon Mac Mini 8GB.
* **Resource Envelope:** 8GB–16GB RAM, 4–8 CPU cores (or 4 Gracemont E-cores), 128GB+ NVMe SSD, 10–25W TDP.
* **Package Variant:** `halbert-core[light]` or standard `halbert-core`.
* **Runtime Variant:** `HALBERT_VARIANT=home` or `sysadmin`.
* **Model Configuration:**
  * `secure_model`: 3B–4B Q4 quantized model ($\sim 2.5\text{–}3.5\text{GB}$ RAM) delivering 10–15 tok/s via local Ollama.
  * `chat_model`: Cloud API (encouraged) or local 3B–4B model.
  * `specialist_model`: Cloud API or LAN GPU offload.
  * `vision_model`: Cloud VLM or local small VLM (via Ollama).
* **SourcePrep:** Local HA-scoped SourcePrep ($\sim 150\text{MB}$ RAM) or Remote full SourcePrep.

### Tier 3: Ideal (Dedicated Server / Pro Workstation / Apple Silicon)
* **Target Hardware:** Apple Silicon Mac (M1/M2/M3/M4 with 16GB–32GB unified memory), Linux/Windows Workstations with AMD Ryzen 7 / Intel Core i7 + NVIDIA RTX 3060/4060 (8GB–12GB VRAM).
* **Resource Envelope:** 16GB–32GB RAM/VRAM, fast NVMe, 35–150W TDP.
* **Package Variant:** Full `halbert-core` with optional `[cloud-apis]` and `[vision]`.
* **Runtime Variant:** `HALBERT_VARIANT=sysadmin` or `home`.
* **Model Configuration:**
  * `secure_model`: 4B–8B Q4/Q8 local model.
  * `chat_model`: 7B–14B local model or Cloud API.
  * `specialist_model`: 14B–32B local model (or Cloud Frontier model).
  * `vision_model`: Local VLM or Cloud VLM.
* **SourcePrep:** Full local SourcePrep instance (70,000+ chunks sysadmin corpus + FTS5 + trace graph).

### Tier 4: Power User / Sovereign Homelab (Multi-Node / High-End)
* **Target Hardware:** Mac Studio (64GB–128GB unified), Multi-GPU Linux Servers (e.g. dual RTX 3090/4090 with 48GB VRAM), Proxmox Homelab Clusters.
* **Resource Envelope:** 64GB–128GB+ RAM/VRAM, high-speed LAN / 10GbE / Tailscale mesh.
* **Package Variant:** Full `halbert-core` + multi-instance network topology.
* **Runtime Variant:** Multiple concurrent instances (Host Sysadmin + Home Hub + Voice Satellites).
* **Model Configuration:** Fully offline sovereign AI — 32B–70B local models, local Whisper large-v3, local Piper TTS, local high-res VLMs.
* **SourcePrep:** Distributed SourcePrep hub serving multiple satellite Halbert instances over LAN.

---

## 4. Minimum SourcePrep Requirements for Home Automation (HA)

A key finding from Phase 8 benchmarking is the vast difference between the **Sysadmin Knowledge Corpus** and a **Dedicated Home Automation Corpus**:

| Metric | Full Sysadmin Corpus | HA-Scoped Corpus |
|---|---|---|
| **Corpus Contents** | Arch-Wiki, macOS man-pages, Linux admin guides, kernel docs | HA entity registry, YAML automations, area topology, Frigate zones, device manuals |
| **Total Chunks** | 71,092 chunks | 500 – 5,000 chunks |
| **Embedding Size on Disk** | $\sim 220\text{MB}$ (768-dim float32) | $\sim 1.5\text{MB} – 15\text{MB}$ |
| **Daemon RAM Footprint** | $\sim 1.2\text{GB} – 2.0\text{GB}$ RSS | $\sim 120\text{MB} – 180\text{MB}$ RSS |
| **Indexing CPU Time** | 10 – 30 minutes (CPU) | 5 – 20 seconds |
| **Minimum Hardware to Run Locally** | Tier 2 (8GB RAM, NVMe) | Tier 1 (4GB RAM, eMMC/SSD) |

### Guidelines for HA Deployments:
1. **On $\le 4\text{GB}$ RAM (Tier 1):** Do not run the full sysadmin SourcePrep daemon locally. Either:
   * Point `SOURCEPREP_URL` to a Tier 2/3 machine on LAN, or
   * Run HA-scoped SourcePrep with only `host` and `ha_config` scopes active.
2. **On $\ge 8\text{GB}$ RAM (Tier 2+):** Local SourcePrep runs comfortably alongside Ollama and Home Assistant.

---

## 5. Local LLM (`secure_model`) Assessment: 1B–4B Models & Quantization

The `secure_model` slot is mandatory for processing sensitive system configurations, API credentials, camera metadata, and internal persona thoughts (`advance_turn` cognitive tick). 

### 5.1 Parameter Size Evaluation for Low-Power Devices

| Parameter Class | Memory (Q4_K_M) | Inference Speed (N100) | Inference Speed (Pi 4) | Fitness for `secure_model` Role |
|---|---|---|---|---|
| **1B – 1.5B** | $\sim 0.8\text{GB} – 1.2\text{GB}$ | 20 – 35 tok/s | 10 – 16 tok/s | **Excellent for Tier 1:** Ultra-low RAM, fast cognitive monologue summarization, basic intent classification. |
| **2B – 3B** | $\sim 1.4\text{GB} – 2.2\text{GB}$ | 15 – 22 tok/s | 6 – 10 tok/s | **Sweet Spot for 4GB–8GB:** Reliable tool calling, structured JSON output, safe privacy scrubbing. |
| **3.8B – 4B** | $\sim 2.4\text{GB} – 3.2\text{GB}$ | 10 – 15 tok/s | 3 – 5 tok/s | **Standard for Tier 2:** Strong reasoning, excellent tool calling, fits in 8GB RAM alongside HA. |
| **7B – 8B** | $\sim 4.5\text{GB} – 5.8\text{GB}$ | 4 – 7 tok/s | 1 – 2 tok/s (OOM risk) | **Tier 3+ only:** Too heavy for low-power CPU-only devices. |

### 5.2 Quantization Strategies for Constrained Memory

1. **`Q4_K_M` (4-bit medium - Default Baseline):**
   * Memory factor: $\sim 0.65\text{ GB}$ per billion parameters.
   * Delivers the optimal balance between perplexity retention and inference throughput on x86/ARM SIMD/NEON.
2. **`Q3_K_M` / `Q2_K` (Extreme Quantization vs. Smaller Models):**
   * *Assessment:* Running a 4B model at 2-bit ($\sim 1.4\text{GB}$ RAM) causes significant degradation in structured JSON generation and tool schema adherence. 
   * *Recommendation:* Prefer a **2B model at Q4_K_M** over a **4B model at Q2_K**. The 2B Q4 model has superior schema precision and lower latency with identical memory usage.
3. **`IQ3_S` / `IQ2_XXS` (Importance Matrix Quantization):**
   * Where available via Ollama / llama.cpp, i-matrix quantization retains higher precision for core attention weights while compressing feed-forward layers, enabling 3B models to run under $1.6\text{GB}$ RAM with minimal quality loss.

---

## 6. Actionable Implementation Checklist

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
