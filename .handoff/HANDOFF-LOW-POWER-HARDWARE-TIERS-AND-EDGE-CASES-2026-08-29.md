# Low-Power Operation Mode: Edge Cases, Hardware Tiers, and Low-Spec LLM Assessment

**Date:** 2026-08-29  
**Status:** Approved & Implemented — Reference Specification & Operational Guidelines  
**Scope:** Practical user edge cases, dual-track hardware requirements (Home vs. Workstation), dedicated resource headroom analysis, and low-parameter/quantized local LLM analysis (sysadmin track; see revision note).

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** `home` / `home-light` variants run no SourcePrep, no `secure_model`, no local LLM, and no model picker (replaced by a single "Compute Peer" setting; the workstation's picker governs). The 1B model tier is dropped; 2B–3B is the minimum class for local inference, on 8GB+ hosts only; `SBC_LOW_POWER` (<4GB per code) is offload-only (peer → template thoughts, no local model fallback) — subject to open decision D2 on the 4GB boundary. Sections 6 and 7 are rescoped to the sysadmin/workstation track.

---

## 1. Executive Summary

With the completion of Phase 7 (Multi-Instance & Config Isolation) and Phase 8 (4-Slot Model Architecture & Light Variant Packaging), Halbert runs across a broad hardware spectrum ranging from legacy dual-core Intel machines and low-power Intel N100/N150 mini PCs to Raspberry Pi 4/5 ARM64 boards, up to high-end Apple Silicon workstations.

This document establishes:
1. **Practical user edge cases & compatibility solutions** identified during Phase 8 implementation.
2. **Dual-Track Hardware Requirements** separating **Home Appliance / Hub** deployments from **Workstation / Sysadmin Server** deployments.
3. **Dedicated Resource Headroom vs. Total Host Sizing**: Clearly distinguishing the unreserved RAM/CPU budget Halbert consumes from the total host capacity required when co-located with sibling workloads (Home Assistant, Frigate, IDEs, browsers).
4. **SourcePrep scoping** — sysadmin/workstation-only. `home` and `home-light` variants run with no `SOURCEPREP_URL`, no ChromaDB, and no RAG scrapers (revised per the simplification handoff; the former HA-scoped corpus concept is superseded — see Section 6).
5. **Local model assessment for the sysadmin track:** 2B–3B is the minimum class for local inference, 8GB+ hosts only; the 1B tier is dropped; devices under 4GB (`SBC_LOW_POWER` per code) are offload-only — peer → template thoughts, no local model fallback (subject to open decision D2 on the 4GB boundary).

---

## 2. Practical User Edge Cases & Compatibility Solutions

### 2.1 Model Configuration & First-Boot UX

#### Edge Case 1: Empty Local Model List Locks Out `secure_model` in Model Picker
* **Problem:** In `@halbert/model-picker` (`RoleAssignmentRow.tsx`), filtering endpoints for `requiresLocal` checked whether an installed model on that endpoint had `isLocal: true`. On a fresh install where Ollama is running but no model has been pulled yet, the endpoint was filtered out of the `Secure (Local)` dropdown entirely.
* **Resolution:** Filter endpoints by `providerDescriptor(e.provider).isLocal` or endpoint URL loopback status rather than requiring an existing model. This allows the user to select "Local Ollama" and view the actionable prompt: *"No models found on endpoint — pull a model via `ollama pull <model>`"*.
* **Note (2026-08-30):** `home`/`home-light` variants no longer configure `secure_model` or render the model picker at all (simplification handoff Findings 1 and 3 — replaced by a "Compute Peer" setting). This fix applies to the **sysadmin variant only**.

#### Edge Case 2: URL Formatting Without `http://` Scheme
* **Problem:** In `llm_config.py:_is_local_url()`, `urlparse(url).hostname` is used to enforce localhost loopback. When a user enters `localhost:11434` or `127.0.0.1:11434` without `http://`, `urlparse` treats `localhost` as the URL scheme, leaving `hostname = None`, which caused `_is_local_url()` to return `False` and silently disable the slot.
* **Resolution:** Ensure `_clean_endpoint()` and `_is_local_url()` normalize URLs lacking a scheme by prepending `http://` prior to parsing.
* **Note (2026-08-30):** `_is_local_url()` enforcement now matters only for the sysadmin variant's `secure_model`; `home`/`home-light` configure no `secure_model` and no local endpoints.

#### Edge Case 3: Containerized Environments (Docker / Podman Host Bridge)
* **Problem:** In containerized setups where Halbert runs in Docker and reaches Ollama on the host via `http://host.docker.internal:11434` or bridge IP `http://172.17.0.1:11434`, standard loopback IP checks failed.
* **Resolution:** Whitelist `host.docker.internal` and `gateway.docker.internal` in `_is_local_url()`.

---

### 2.2 Runtime Resilience & Network Failovers

#### Edge Case 4: Cloud `chat_model` Goes Offline
* **Problem:** Users configured with Cloud `chat_model` (OpenAI/Anthropic) and local `secure_model` (Ollama) lose chat functionality during an ISP outage, even though local compute is available.
* **Resolution:** When a Cloud request fails due to network disconnect/timeout, display a non-blocking UI alert banner with a 1-click fallback: *"Cloud endpoint unreachable (Offline). Switch Chat to local model?"*
* **Scope note (2026-08-30):** This fallback applies to the **sysadmin variant only**. On `home`/`home-light`, `chat_model` resolves to `peer://workstation` and the offline fallback is template thoughts (peer → template-thoughts chain) — there is no local model to switch to. If implemented, gate the banner by variant.

#### Edge Case 5: Context Window KV-Cache CPU Latency on Low-Power Cores
* **Problem:** On an Intel N100 or Raspberry Pi 5, allocating a 32k context window (`num_ctx: 32768`) in system RAM causes high prompt ingestion latency (20–40s before first token).
* **Resolution (revised 2026-08-30):** For `ENTRY_8GB` ($4\text{–}8\text{GB}$) hosts — which may run a local 3B fallback model (offload preferred) — cap the automatic `num_ctx` expansion to $8192$ tokens (configurable via `HALBERT_NUM_CTX_MAX`). For `SBC_LOW_POWER` (<4GB per code) this cap is moot: these devices are offload-only and never load a local model (see Section 7; the 4GB boundary itself is open decision D2 in the simplification handoff).

#### Edge Case 6: Remote SourcePrep Server Goes Offline / Sleep
* **Problem:** A low-power client offloading SourcePrep to a networked workstation (`SOURCEPREP_URL=http://desktop.lan:8400`) experiences retrieval drops when the workstation sleeps.
* **Resolution:** `SourcePrepRetrievalBackend` catches connection errors and fails open (returns empty context without raising), allowing the agent to answer using conversational context. Settings UI displays live status: *"Remote SourcePrep unreachable (operating in un-indexed fallback mode)"*.
* **Scope note (2026-08-30):** `home`/`home-light` no longer configure `SOURCEPREP_URL` in any form — not remote, not local, not un-indexed fallback (simplification handoff Finding 2); the retrieval backend is not instantiated on HA nodes. This fail-open path now serves only sysadmin-track thin clients doing remote LAN offload, and remains a safety net there (see Section 6).

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
1. **Dedicated Process Budget (Unreserved Headroom):** The specific slice of RAM, CPU cores, and storage I/O that Halbert — and, where a local model applies (sysadmin track), its Ollama backend — strictly require to be free and available without contention.
2. **Total Host System Sizing:** The overall host machine capacity needed to run Halbert alongside its typical co-located sibling processes (Home Assistant + Frigate on Home Hubs; IDEs + Browsers + Docker on Workstations).

```
+-----------------------------------------------------------------------------------+
| HOME HUB / APPLIANCE TRACK (24/7 Headless Daemon)                                 |
| Halbert Dedicated Budget: ~0.5GB - 1.5GB (no-LLM home/home-light) | 1-2 CPU cores |
| Co-located Sibling Workloads: Home Assistant, Frigate NVR, MQTT, Wyoming Voice    |
+-----------------------------------------------------------------------------------+
| WORKSTATION / SYSADMIN TRACK (Interactive Terminal & Codebase Brain)             |
| Halbert Dedicated Budget: 1.5GB - 12GB unreserved RAM/VRAM | 2-4 CPU/GPU cores    |
| Co-located Sibling Workloads: IDEs, Browsers (50+ tabs), Docker, Compilers        |
+-----------------------------------------------------------------------------------+
```

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** the former Home Hub budget range (1.2GB–3.5GB) assumed a local `secure_model` plus a local HA-scoped SourcePrep corpus, both now removed from `home`/`home-light`. The no-LLM home footprint is roughly ~300MB for the `home-light` daemon plus ~200MB for persona memory embeddings (served via haloysius's ONNX/Ollama `MemoryEmbedder` — not `sentence-transformers` in halbert_core; per handoff 4.7, do NOT add `sentence-transformers` to the `[light]` extra). All LLM work is offloaded to the compute peer. The diagram range above and the Section 4 Track A budget column are re-derived 2026-08-30 from these components (~300MB daemon + ~200MB embeddings + ~300MB local voice stack where present → ~0.5GB–1.5GB); a host that keeps an optional 3B–4B local *fallback* (see Section 4's note) adds ~2.5–3GB to its own host budget, not to the home-variant footprint. Which memory path the HA persona actually consumes (receipts/FTS5 vs. the haloysius embedder) is open decision D3 in the simplification handoff.

### CPU Duty Cycle & Thermal Considerations
Running a local 3B–4B model on CPU (e.g. Intel N100 or Raspberry Pi 5) saturates 100% of all assigned CPU cores during active inference — the duty-cycle concern that drives the offload rule below. 
* **Home Context (revised 2026-08-30):** Home Hub variants run **no local LLM at all** — all LLM work is offloaded to the compute peer, and cognitive monologue uses template thoughts exclusively. Local CPU inference duty-cycle concerns now apply only to sysadmin-track hosts (or a local 3B–4B fallback model on an 8GB+ host, offload preferred).
* **Architectural Rule:** In Home Hub / low-power deployments, cognitive monologue **always uses template thoughts (`HALBERT_LLM_THOUGHTS=0`)** on `home`/`home-light`, keeping CPU utilization near 0% at idle and bursting only when an explicit user question or high-priority automation trigger occurs. *(Previously "defaults to"; open question 11.4 of the simplification handoff asks whether `advance_turn` should be disabled entirely on HA variants.)*

---

## 4. Track A: Home Appliance & Hub Requirements (`home` / `home-light`)

Designed for 24/7 continuous headless operation, smart home event streaming, and voice integration.

| Tier | Dedicated Halbert Budget (Unreserved Headroom) | Total Host Sizing (Accounting for Sibling Workloads) | Recommended Sibling Workloads | Model & Runtime Configuration (peer offload — no local models) |
|---|---|---|---|---|
| **Tier 1: Home Minimal** | **$\sim 0.5\text{GB}$ Free RAM**<br>1 shared CPU core<br>10GB free storage | **4GB RAM**<br>Quad-Core CPU (Pi 4, Celeron, RK3588)<br>32GB–64GB eMMC/SSD | Home Assistant Core + Mosquitto MQTT | • `HALBERT_VARIANT=home-light`<br>• No `secure_model` (slot unconfigured)<br>• `chat_model`: `peer://workstation` (compute peer)<br>• No SourcePrep (no `SOURCEPREP_URL`)<br>• Template thoughts when peer asleep |
| **Tier 2: Home Recommended** | **$\sim 1.0\text{GB}$ Free RAM**<br>2 CPU cores on burst<br>25GB free storage | **8GB – 16GB RAM**<br>4 E-cores / Quad-Core (N100, N150, Pi 5)<br>128GB+ NVMe SSD | Home Assistant OS + Frigate NVR (1–3 cams) + Wyoming Voice | • `HALBERT_VARIANT=home`<br>• No `secure_model` (slot unconfigured)<br>• `chat_model` + `specialist_model`: `peer://workstation` (workstation's model picker governs)<br>• No SourcePrep<br>• Persona memory embeddings stay local (haloysius ONNX/Ollama `MemoryEmbedder`) |
| **Tier 3: Home Power Hub** | **$\sim 1.5\text{GB}$ Free RAM**<br>4 CPU cores / iGPU<br>50GB free storage | **16GB – 32GB RAM**<br>Intel Core i5 / N305 / AMD Ryzen / Mac Mini<br>256GB+ NVMe SSD | Full HA Stack + Frigate (4+ HD cams) + Local Whisper + Plex/Jellyfin | • `HALBERT_VARIANT=home`<br>• No `secure_model` (slot unconfigured)<br>• `chat_model` + `specialist_model`: `peer://workstation` (workstation's model picker governs)<br>• No SourcePrep<br>• Persona memory embeddings stay local (haloysius ONNX/Ollama `MemoryEmbedder`)<br>• Full local voice stack |

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** no `home`/`home-light` tier configures a local model or `secure_model` — the HA variant offloads all LLM work to the compute peer. Per the handoff's device table, an 8GB+ host MAY keep a local 3B–4B model as a *fallback* (offload preferred), but the HA variant configuration itself never resolves to it for normal operation. **Open decision D2 (4GB boundary):** in code, `SBC_LOW_POWER` is strictly <4GB and a 4GB host classifies as `ENTRY_8GB` (optional local 3B fallback, offload preferred); the handoff's device table lists 4GB hosts as offload-only. This conflict is unresolved — do not treat Tier 1 (4GB) hosts as locally-capable until D2 lands. The Dedicated Halbert Budget column in this table was re-derived 2026-08-30 from the no-LLM component footprint (see Section 3's revision note: daemon ~300MB, persona memory embeddings ~200MB, local voice stack ~300MB where present); the former ~1.2GB / ~3.0GB / ~5.0GB figures assumed a local `secure_model` and an HA-scoped SourcePrep corpus, both of which are removed from `home`/`home-light`.

---

## 5. Track B: Workstation & Sysadmin Server Requirements (`sysadmin`)

Designed for interactive terminal sessions, system diagnosis, and full-corpus SourcePrep code/config intelligence.

| Tier | Dedicated Halbert Budget (Unreserved Headroom) | Total Host Sizing (Accounting for Sibling Workloads) | Recommended Sibling Workloads | Local Model & Runtime Configuration |
|---|---|---|---|---|
| **Tier 1: Workstation Entry** | **$\sim 1.5\text{GB}$ Free RAM**<br>1 CPU core<br>15GB free storage | **8GB RAM**<br>Older Laptop / Desktop (2nd–8th Gen Core, 8GB RAM) | Lightweight OS + Terminal + Single Browser Window | • `halbert-core[light]`<br>• `secure_model`: 2B Q4 ($\sim 1.4\text{GB}$ RAM) or Template Thoughts *(1B tier dropped 2026-08-30 — see Section 7)*<br>• `chat_model`: Cloud API (OpenAI/Anthropic)<br>• SourcePrep: Remote LAN Offload |
| **Tier 2: Workstation Semi-Pro** | **$\sim 2.5\text{GB} – 3.0\text{GB}$ Free RAM**<br>2 CPU cores / Neural Engine<br>30GB free storage | **16GB – 24GB RAM**<br>Apple Silicon Mac (M1/M2/M3/M4 16GB–24GB), PC Laptop 16GB–24GB | IDE (VS Code/Cursor) + Web Browser (40+ tabs) + Docker | **Single Local Model Rule:**<br>• `secure_model` & default `chat_model`: Apple Intelligence 3B (on ANE ~2.5GB) or single 3B local model<br>• `specialist_model`: **Cloud Frontier (Recommended)** (Claude 3.5 Sonnet, GPT-4o, Groq, Ollama Cloud)<br>• SourcePrep: Host config + Local scope<br>• *(2026-08-30, handoff Finding 5)* Apple Intelligence is local-only (this Mac's own slots); when this Mac acts as a compute peer, peer requests route to Ollama (7B–14B) — never `apple-foundation` — and mDNS `compute_backends` advertises `ollama`/`vllm` only |
| **Tier 3: Workstation Pro** | **$\sim 8\text{GB} – 12\text{GB}$ Free RAM / VRAM**<br>Dedicated GPU / Neural Engine<br>100GB free storage | **32GB – 36GB RAM (or Unified)**<br>Mac Studio / MacBook Pro 32GB, PC with RTX 3060/4060 (8–12GB VRAM) | Full Dev Suite + Multiple Containers + Heavy Compilations | • Full `halbert-core` with `[vision]` and `[cloud-apis]`<br>• `secure_model`: Apple Intelligence 3B or 7B–8B local model<br>• `chat_model` / `specialist`: 14B–32B Q4 local model OR Cloud Frontier<br>• SourcePrep: Full local 70k+ chunk corpus |
| **Tier 4: Sovereign Homelab** | **$\ge 24\text{GB}$ Free RAM / VRAM**<br>Multi-GPU / High-core CPU<br>250GB+ fast NVMe | **64GB – 128GB+ RAM**<br>Mac Studio 64–128GB, Dual RTX 3090/4090 Workstations, Proxmox Cluster | Multi-tenant virtualization + Cluster orchestrations | • 100% Offline Sovereign AI<br>• `chat_model` / `specialist_model`: 32B–70B local<br>• Local Whisper large-v3 + Piper TTS + VLMs<br>• Distributed SourcePrep hub for sysadmin-track thin clients only (never `home`/`home-light` satellites — see Section 6) |

---

## 6. SourcePrep Requirements (sysadmin/workstation track only)

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (Finding 2):** the **HA-scoped SourcePrep corpus is superseded — it will not be built.** `home` and `home-light` variants run no SourcePrep in any form: no `SOURCEPREP_URL` (remote, local, or un-indexed fallback), no ChromaDB, no RAG scrapers, and no SourcePrep daemon — the `SourcePrepRetrievalBackend` is not instantiated on HA nodes. The HA Halbert answers from live HA state (sensors, entities, events via the HA WebSocket stream) and persona memory; anything complex enough to need documentation retrieval is sysadmin work, done at the workstation. The workstation MAY index the N150's HA config via the MCP fleet path — but that is the workstation querying, not the HA node.

The resource overhead of the **Full Sysadmin Knowledge Corpus** — the only supported configuration:

| Metric | Full Sysadmin Corpus | HA-Scoped Corpus (superseded — retained for history) |
|---|---|---|
| **Corpus Contents** | Arch-Wiki, macOS man-pages, Linux admin guides, kernel docs | HA entity registry, YAML automations, area topology, Frigate zones, device manuals |
| **Total Chunks** | 71,092 chunks | 500 – 5,000 chunks |
| **Disk Size** | $\sim 220\text{MB}$ (768-dim float32) | $\sim 1.5\text{MB} – 15\text{MB}$ |
| **Daemon RAM Overhead** | $\sim 1.2\text{GB} – 2.0\text{GB}$ RSS | $\sim 120\text{MB} – 180\text{MB}$ RSS |
| **Indexing CPU Time** | 10 – 30 minutes (CPU) | 5 – 20 seconds |
| **Minimum Headroom to Run Locally** | $\ge 2.0\text{GB}$ Dedicated RAM | **$\sim 200\text{MB}$ Dedicated RAM** |

*The superseded column is kept above only to document the resource analysis that originally motivated the HA-scoped design — the ~10x RAM/disk difference between a full sysadmin corpus and an HA-scoped one was the insight that made the lightweight home corpus seem viable, and its removal is documented in the simplification handoff (sections 4.1–4.3): voice queries are short and action-oriented, live HA state answers most questions without retrieval, and remaining documentation-heavy questions are sysadmin work.*

### Deployment Rules for SourcePrep:
1. **Home Track (all `home`/`home-light` hosts):** No SourcePrep. Do not configure `SOURCEPREP_URL`; the retrieval backend is skipped entirely on these variants.
2. **Workstation Track ($\ge 16\text{GB}$ Hosts):** Full local SourcePrep daemon indexes the entire 70k sysadmin knowledge base without impacting desktop responsiveness.

---

## 7. Local LLM (`secure_model`) Assessment: 2B–8B Models & Quantization (sysadmin track)

The `secure_model` slot is mandatory in the **sysadmin variant** for reasoning about sensitive system configurations and credentials.

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (Findings 1 and 4):** `secure_model` is **not configured** on `home`/`home-light` variants at all. On home automation, the LLM never sees HA API credentials, camera metadata, or lock PINs — HA/Frigate tool-call abstraction keeps them out of the prompt, and the residual exposure is a deterministic redaction task, not LLM reasoning. HA cognitive monologue uses template thoughts, and sysadmin work on an HA device itself is done from the workstation's Halbert via the fleet cockpit. This assessment therefore scopes local models to the sysadmin track only: **2B–3B is the minimum class for local inference, on 8GB+ hosts only**; `SBC_LOW_POWER` (<4GB per code) is **offload-only** (peer → template thoughts, no local model fallback). **Open decision D2 (4GB boundary):** code classifies a 4GB host as `ENTRY_8GB` (optional local 3B fallback, offload preferred), while the simplification handoff's device table lists 4GB hosts as offload-only — resolve before S4 lands.

### 7.1 Parameter Size Evaluation for Low-Power Devices

> **Revised 2026-08-30:** the 1B–1.5B row is dropped — the 1B tier is eliminated as a supported configuration (handoff 6.5). Its own capabilities (fast summarization, low thermal impact) contradicted what the `secure_model` role requires (tool calling, structured JSON, privacy scrubbing), as the simplification handoff section 3.5 argued from this very table. The Pi 4 column is retained for history but is moot: no <4GB host loads a local model under the offload-only rule.

| Parameter Class | Memory Headroom (Q4_K_M) | CPU Inference Speed (N100) | CPU Inference Speed (Pi 4) | Fitness for `secure_model` Role |
|---|---|---|---|---|
| **2B – 3B** | $\sim 1.4\text{GB} – 2.2\text{GB}$ | 15 – 22 tok/s | N/A (offload-only) | **Minimum supported class (8GB+ hosts only):** Reliable tool calling, structured JSON output, safe privacy scrubbing. Not supported on `SBC_LOW_POWER` (<4GB) hosts — offload-only. |
| **3.8B – 4B** | $\sim 2.4\text{GB} – 3.2\text{GB}$ | 10 – 15 tok/s | N/A (offload-only) | **Standard for 8GB–16GB sysadmin hosts / local fallback (offload preferred):** Strong reasoning, reliable schema adherence. |
| **7B – 8B** | $\sim 4.5\text{GB} – 5.8\text{GB}$ | 4 – 7 tok/s | N/A (offload-only) | **Pro Tiers only ($\ge 16\text{GB}$ RAM):** Too heavy for low-power CPU-only hosts. 7B–14B Ollama is also the required backend when a Mac serves peer compute requests (handoff Finding 5). |

### 7.2 Quantization Baseline (sysadmin track)

1. **`Q4_K_M` (4-bit medium - Default and Only Supported Baseline):**
   * Memory factor: $\sim 0.65\text{ GB}$ per billion parameters.
   * Delivers the optimal balance between perplexity retention and inference throughput on x86/ARM SIMD/NEON.
   * With the extreme-quantization research dropped (below), `Q4_K_M` is the sole supported quantization for all surviving classes (2B–3B through 7B–8B).

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (Finding 4 / 6.5):** the former items below are dropped as standing recommendations — they optimized for squeezing local inference into memory-constrained (<4GB) devices, a scenario that no longer exists (offload-only). They are recorded here only to document why the decision was made:
> 2. ~~**Smaller Model vs. Extreme Quantization:**~~ the assessment found that running a 4B model at 2-bit (`Q2_K`, $\sim 1.4\text{GB}$ RAM) significantly degrades structured JSON generation and tool schema adherence — the basis for preferring a 2B model at Q4_K_M over a 4B model at Q2_K. Under the offload-only rule this tradeoff is moot: **`Q2_K` is not a supported quantization for any Halbert role.**
> 3. ~~**Importance Matrix (`IQ3_S` / `IQ2_XXS`):**~~ the IQ2_XXS/IQ3_S research existed only to fit 3B models under $\sim 1.6\text{GB}$ RAM — a budget now handled by offloading. Extreme-quantization research is eliminated (handoff 6.5).

---

## 8. Actionable Implementation Checklist

- [x] 4-slot model configuration implemented (`chat_model`, `specialist_model`, `vision_model`, `secure_model`).
- [x] Local-only URL enforcement implemented with robust hostname/loopback parsing.
- [x] Dependency trimming complete (`[light]` extra without `torch`/`chromadb`). *(2026-08-30: `[light]` correctly also excludes `sentence-transformers` — keep it that way. Persona memory embeddings on HA nodes are served via haloysius's ONNX/Ollama `MemoryEmbedder`, not halbert_core's `sentence-transformers`; do NOT add it to halbert_core extras (handoff 4.7/W20). Open decision D3 confirms which memory path the HA persona actually consumes — if the receipts/FTS5 path is operative, no packaging change is needed at all.)*
- [x] Hardware profiles extended for `SBC_LOW_POWER` ($\le 4\text{GB}$) and `ENTRY_8GB` ($4\text{–}8\text{GB}$). *(2026-08-30 update: `SBC_LOW_POWER` no longer recommends any local model — offload only, fallback peer → template thoughts, no local-model tier; `ENTRY_8GB` may use a local 3B fallback, offload preferred — handoff S4. Note: in code `SBC_LOW_POWER` is strictly <4GB; a 4GB host classifies as `ENTRY_8GB` (decision D2 pending).)*
- [x] Multi-instance `home-light` runtime gating implemented.
- [ ] Fix Model Picker endpoint filtering for `requiresLocal` in `@halbert/model-picker` (`RoleAssignmentRow.tsx`) — **sysadmin variant only** (home/home-light no longer render the picker; they get a "Compute Peer" setting instead — see handoff S3).
- [ ] Add `http://` auto-prefixing in `_clean_endpoint()` and `_is_local_url()` (sysadmin-scoped: local-only enforcement serves the sysadmin variant's `secure_model`).
- [ ] Whitelist `host.docker.internal` in `_is_local_url()` (sysadmin-scoped, as above).
- [ ] Add 1-click local fallback prompt in chat UI when Cloud `chat_model` encounters connection errors — **sysadmin variant only**. For `home`/`home-light`, implement the peer → template-thoughts fallback chain instead (no local model exists to switch to).
- [ ] Update `deploy/README.md` to state SourcePrep is not needed for `home`/`home-light` variants (no `SOURCEPREP_URL`, no ChromaDB); SourcePrep is workstation/sysadmin-only (handoff W13).
- [x] Variant-gate SourcePrep wiring out of `home`/`home-light` (handoff S2, W7–W12). *(Verified 2026-09-02, SONNET-05: `capabilities.py`'s `CAP_SOURCEPREP` preset is `False` for home, per SONNET-03's `U6-DESIGN-01` default — home ignores the daemon-presence probe unless `being.yml` opts in explicitly. `home-light` no longer exists as a separate variant — merged into `home`.)*
- [x] Replace the model picker with a "Compute Peer" setting (hostname:port + "Test Connection") for `home`/`home-light`; register `PeerProvider` in the model stack (handoff S3, W14–W16). *(Verified 2026-09-02: `ComputePeerCard.tsx` exists and `Settings.tsx:806` renders it in place of `ModelSettings` when `isHomeVariant`.)*
- [x] Drop the 1B model tier from `recommend_budget()`/`get_installation_commands()`; `SBC_LOW_POWER` = offload only (subject to decision D2); add the wizard compute-peer prompt (handoff S4, W17–W19). *(Verified 2026-09-02: no 1B recommendation path left in `model/hardware_detector.py` — only historical comments naming it; `config_wizard.py::_prompt_compute_peer`/`_test_compute_peer` exist and are wired into the wizard flow.)*
