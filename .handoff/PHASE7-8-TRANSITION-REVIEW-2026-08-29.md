# Phase 7 → Phase 8 Transition Review & Work Plan

**Date:** 2026-08-29
**Status:** Ready for review — awaiting feedback from another AI session before implementation
**DO NOT IMPLEMENT until feedback is received in this document.**
**Scope:** Phase 7 completeness audit, model routing correction, model architecture code audit, Phase 8 detailed work plan, and Sentient Home roadmap alignment

---

## 1. Phase 7 Completeness Audit

### 1.1 What's Done (commits `137f8468`, `ad65ed58`)

| Component | Files | Verified |
|-----------|-------|----------|
| Env var unification (`HALBERT_*` primary, `Halbert_*` fallback) | `paths.py`, `platform.py` | Yes |
| `HALBERT_CONFIG_DIR` / `HALBERT_DATA_DIR` overrides | `platform.py` | Yes |
| `HALOYSIUS_DATA_HOME` sync from `HALBERT_DATA_DIR` | `cognition_wiring.py` | Yes |
| `HALBERT_VARIANT` gating (skip ingestion + discovery on home) | `app.py` | Yes |
| `HALBERT_PORT` env var + `__main__` block | `app.py` | Yes |
| Instance identity startup logging | `app.py` | Yes |
| `GET /api/instance/info` endpoint | `routes/instance.py` | Yes |
| Frontend Instance Switcher dropdown | `InstanceSwitch.tsx` | Yes |
| Sidebar nav filtering by instance features | `Layout.tsx` | Yes |
| Dynamic `apiBase` override | `apiBase.ts` | Yes |
| Systemd unit files (host + home) | `deploy/*.service` | Yes |
| Deployment README | `deploy/README.md` | Yes |
| Unit tests (18 tests) | `test_multi_instance.py` | Yes |

### 1.2 What's Missing (Gaps from Feedback Docs)

| Gap | Source | Priority | Blocked By |
|-----|--------|----------|------------|
| **Onboarding role selection UI** | Review Feedback §4, §6 | Medium | Founder decision on flow |
| **`BeingConfig` fields** (`scene_context`, `variant`, `ha_url`) | v2 feedback §7 | Low | Currently env-var-only; works but not configurable in `being.yml` |
| **`memory_{persona_id}.db` defensive naming** | Review Feedback §5 Q3 | Low | Haloysius already isolates by directory (`state_dir/personas/{persona_id}/`); DB filename redundancy is defense-in-depth |
| **Cross-instance peer delegation** | Design doc §4.5 | Future (Phase 8+) | Not needed for MVP |

### 1.3 Bug Found During Audit: `HALBERT_MODEL` Not Wired

**Problem:** `deploy/halbert-home.service` sets `Environment=HALBERT_MODEL=qwen2.5:3b`, but **no code reads this env var**. The actual model selection goes through `models.yml` (via `model/llm_config.py` → `model/client.py` → `_store.resolve("chat_model")`).

**Impact:** The 3B model default in the systemd unit is documentation-only. A fresh install with no `models.yml` will fall back to the default Ollama endpoint with no model configured, producing a "choose a model in Settings" error.

**Fix needed:** Either wire `HALBERT_MODEL` into the model store as a fallback, or document that `models.yml` must be provisioned per-instance (the current architecture's intent). See §2 below for the correct resolution.

---

## 2. Model Routing Correction — Critical Design Clarification

### 2.1 Founder Intent (Clarified 2026-08-29)

> "Is 3B model defaults for the secure data LLM? That's the only one that should default to local. The rest we encourage cloud but that's up to the user."

**The 3B model is NOT the general chat model.** It is the **secure-data local model** — the model that processes sensitive data (system configs, secrets, HA tokens, Frigate camera frames) that must never leave the machine. The general chat model should default to cloud (OpenAI, Anthropic, etc.) with local as fallback.

**Note on qwen2.5:** The `qwen2.5:3b` reference in the systemd unit is outdated. Qwen 2.5 is a 2024-era model. Current (2026) recommended small local models for the `secure_model` slot:

| Model | Params | RAM (Q4) | License | Ollama Pull | Notes |
|-------|--------|----------|--------|-------------|-------|
| **Qwen3 4B** | 4B | ~3-4 GB | Apache 2.0 | `qwen3:4b` | Best all-round small model; strong reasoning + tool calling |
| Llama 3.2 3B | 3B | ~3 GB | Llama Community | `llama3.2:3b` | Fastest inference; best for CPU-only/N150 |
| Gemma 3 4B | 4B | ~3-4 GB | Gemma | `gemma3:4b` | Multimodal (vision); 140+ languages |
| Phi-4-mini | 3.8B | ~3 GB | MIT | `phi4-mini` | Best math/structured output at this size |

**Recommendation:** Default `secure_model` to `qwen3:4b` (Apache 2.0, best general capability). For N150/Pi 5 class hardware where every MB counts, `llama3.2:3b` is the lighter fallback. The model choice is a deployment config, not a code decision.

### 2.2 Current Model Architecture (Code Audit)

The model system lives in three files:

1. **`halbert_core/halbert_core/model/llm_config.py`** — Single owner of the `llm_config` section of `models.yml`. Defines `SLOTS` tuple, `default_llm_config()`, `normalise()`, `resolve()`, `save()`, `update()`.
2. **`halbert_core/halbert_core/model/client.py`** — Model client. Imports `llm_config as _store`. Exposes `get_configured_model()` (chat), `get_specialist_model()`, `get_vision_model()`. Each calls `_store.resolve(slot_name)`.
3. **`halbert_core/halbert_core/model/config_wizard.py`** — Generates initial `models.yml` with 3 slots + routing + hardware profile.
4. **`halbert_core/halbert_core/model/tier_router.py`** — `TierRouterConfig.from_legacy_config()` reads the 3 slots for routing decisions.
5. **`halbert_core/halbert_core/model/__init__.py`** — Re-exports `get_configured_model`, `get_specialist_model`, `get_vision_model`.

The `SLOTS` tuple at `llm_config.py:61`:
```python
SLOTS = ("chat_model", "specialist_model", "vision_model")
```

`default_llm_config()` at `llm_config.py:122`:
```python
def default_llm_config() -> Dict[str, Any]:
    return {
        "saved_endpoints": [],
        "chat_model": _empty_slot(),
        "specialist_model": _empty_slot(),
        "vision_model": _empty_slot(),
    }
```

`normalise()` at `llm_config.py:351` iterates over `SLOTS` to validate each slot against saved endpoints and `CHAT_CAPABLE_PROVIDERS`.

`resolve()` at `llm_config.py:742` takes a slot name and returns `Optional[ResolvedModel]`.

**The `secure_model` slot does not exist.** Adding it requires changes to all 5 files above. The `SLOTS` tuple is the single point of truth — adding `"secure_model"` to it makes `normalise()`, `resolve()`, and the layer merge all work automatically. The local-only enforcement is the only custom logic needed.

| Slot | Purpose | Current Default | Should Default To |
|------|---------|-----------------|-------------------|
| `chat_model` | General conversation, tool calling | Local Ollama (no model configured) | **Cloud** (user's choice — OpenAI/Anthropic) |
| `specialist_model` | Code generation, complex reasoning | Not configured | Cloud or powerful local (14B+) |
| `vision_model` | Image understanding | Falls back to chat_model | Cloud (GPT-4V, etc.) or local VLM |
| `secure_model` (NEW) | Sensitive data processing, cognitive tick | Does not exist | **Local-only** (qwen3:4b or llama3.2:3b) |

### 2.3 Proposed `secure_model` Slot

```yaml
# models.yml (per-instance)
llm_config:
  chat_model:
    enabled: true
    endpoint_id: ep_openai_1
    model: gpt-4o  # or whatever the user picks
  specialist_model:
    enabled: false
    endpoint_id: ""
    model: ""
  vision_model:
    enabled: false
    endpoint_id: ""
    model: ""
  secure_model:                    # NEW
    enabled: true
    endpoint_id: ep_ollama_local   # MUST be a local endpoint
    model: qwen3:4b                # local-only, never leaves the machine
    # The model client enforces that this endpoint's URL is localhost/127.0.0.1
```

**Enforcement:** `model/client.py` should reject a `secure_model` configuration whose endpoint URL is not local. This is an architectural guard, not a policy — secure data must never transit a network.

**Use cases for `secure_model`:**
- Processing system config files (`/etc/hosts`, `~/.zshrc`, HA YAMLs)
- Summarizing journald logs
- Analyzing Frigate camera frames (if no cloud vision model is configured)
- Any tool execution that handles secrets, tokens, or credentials
- Cognitive tick (`advance_turn`) internal monologue — this is persona memory, not user-facing chat

**Use cases for `chat_model` (cloud-encouraged):**
- User-facing conversation
- Tool calling (the tool *results* may be sanitized before reaching the cloud model)
- Code generation
- General reasoning

### 2.4 Systemd Unit Fix

The home service unit should NOT set `HALBERT_MODEL=qwen2.5:3b` as a blanket default. Instead:

```ini
# Remove: Environment=HALBERT_MODEL=qwen2.5:3b
# The model selection is per-instance in models.yml, not env vars.
# Provisioning scripts should create a models.yml with:
#   chat_model → user's cloud choice (or local 14B if offline)
#   secure_model → qwen3:4b (local-only, enforced by code)
```

### 2.5 Routing Flow

```
User message → chat_model (cloud, user's choice)
                ↓
            Tool execution → tool may handle sensitive data
                ↓
            Sensitive data processing → secure_model (local, never leaves machine)
                ↓
            Tool result (sanitized) → back to chat_model for response synthesis
```

The cognitive tick (`advance_turn`) runs on `secure_model` because it processes persona memory and internal state — this is the being's private monologue, not user-facing chat.

### 2.6 Local-Only Enforcement Design

The `secure_model` slot must reject non-local endpoints. The enforcement belongs in `normalise()` in `llm_config.py`, which already validates each slot against `CHAT_CAPABLE_PROVIDERS`. The additional check:

```python
# In normalise(), after the existing provider check:
if slot == "secure_model" and enabled:
    ep_url = by_id[endpoint_id]["url"].lower()
    if not any(host in ep_url for host in ("localhost", "127.0.0.1", "0.0.0.0")):
        logger.warning("secure_model endpoint %r is not local; slot disabled", ep_url)
        enabled = False
```

This is an architectural guard, not a policy — secure data must never transit a network. The check is in `normalise()` so it applies on every read (file load, layer merge, save). A hand-edited `models.yml` that points `secure_model` at a cloud URL will be silently disabled with a warning, same as the existing provider-capability check.

### 2.7 Files Requiring Changes for `secure_model`

| File | Change | Lines |
|------|--------|-------|
| `model/llm_config.py:61` | Add `"secure_model"` to `SLOTS` tuple | 1 |
| `model/llm_config.py:122-128` | Add `secure_model` to `default_llm_config()` | 1 |
| `model/llm_config.py:351-387` | Add local-only check in `normalise()` loop | ~5 |
| `model/client.py` | Add `get_secure_model()` function | ~10 |
| `model/__init__.py` | Export `get_secure_model` | 2 |
| `model/config_wizard.py:230-255` | Add `secure_model` to wizard defaults | ~5 |
| `model/tier_router.py:111-135` | Add `secure_model` to `from_legacy_config()` | ~5 |
| `deploy/halbert-home.service` | Remove `HALBERT_MODEL=qwen2.5:3b` line | 1 |
| `deploy/halbert-host.service` | Remove `HALBERT_MODEL` line if present | 1 |
| `deploy/README.md` | Update model references | ~5 |
| `tests/test_secure_model.py` | New test file | ~60 |

**Total:** ~95 lines across 10 files.

---

## 3. Phase 8 — Light Variant Packaging (Detailed Work Plan)

### 3.1 Objective

Package Halbert for Intel N150 / Raspberry Pi 5 class hardware. The same GPL-3.0 codebase, with:
- Ollama embeddings replacing sentence-transformers (saves ~500MB PyTorch)
- `secure_model` defaulting to 3B (already the plan per §2)
- Reduced dependency footprint (no GPU/CV libraries on light hardware)
- Background service gating via `HALBERT_VARIANT=home` (already implemented)

### 3.2 Work Items

| # | Task | Files | Effort | Dependency |
|---|------|-------|--------|------------|
| 1 | **Ollama embedding backend** | New `halbert_core/model/ollama_embeddings.py`; update `cognition_wiring.py` to pass it to `PersonaMemoryStore` | ~50 lines | None |
| 2 | **`secure_model` slot in models.yml** | `model/llm_config.py`, `model/client.py`, `model/config_wizard.py` | ~80 lines | None |
| 3 | **Local-only enforcement for secure_model** | `model/client.py` — validate endpoint URL is localhost | ~15 lines | #2 |
| 4 | **Route cognitive tick to secure_model** | `cognition_wiring.py` — `advance_turn` uses `secure_model` not `chat_model` | ~10 lines | #2 |
| 5 | **Remove `HALBERT_MODEL` from systemd units** | `deploy/halbert-home.service`, `deploy/halbert-host.service` | ~2 lines | None |
| 6 | **Provisioning script for models.yml** | New `deploy/provision-models.sh` — creates per-instance `models.yml` with correct slots | ~40 lines | #2 |
| 7 | **Dependency trimming for light hardware** | `pyproject.toml` — optional extras group `[light]` excluding torch, sentence-transformers, CV libs | ~15 lines | #1 |
| 8 | **Ollama embedding model pull** | `deploy/README.md` — document `ollama pull nomic-embed-text` | Documentation | #1 |
| 9 | **Tests for secure_model routing** | `tests/test_secure_model.py` | ~60 lines | #2, #3 |

### 3.3 Ollama Embedding Backend Design

```python
# halbert_core/model/ollama_embeddings.py

class OllamaEmbeddingBackend:
    """Embedding callable backed by Ollama /api/embeddings.
    
    Drop-in replacement for sentence-transformers' encode() method.
    PersonaMemoryStore accepts a callable — this is all we need.
    """
    
    def __init__(self, model: str = "nomic-embed-text", url: str = None):
        self.model = model
        self.url = url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    
    def __call__(self, texts: list[str]) -> list[list[float]]:
        import requests
        # Batch embed via Ollama API
        results = []
        for text in texts:
            resp = requests.post(
                f"{self.url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            results.append(resp.json()["embedding"])
        return results
```

Wired in `cognition_wiring.py`:
```python
# When HALBERT_VARIANT=home or torch is unavailable:
from ..model.ollama_embeddings import OllamaEmbeddingBackend
embedding_fn = OllamaEmbeddingBackend(model="nomic-embed-text")
store = PersonaMemoryStore(persona_id, embedding_fn=embedding_fn)
```

### 3.4 Dependency Trimming

```toml
# pyproject.toml
[project.optional-dependencies]
light = [
    # No torch, no sentence-transformers, no CV libraries
    # Ollama handles embeddings and vision models
    "fastapi>=0.100",
    "uvicorn[standard]",
    "httpx",
    "pyyaml",
    # ... core deps only
]
full = [
    # Everything including torch, sentence-transformers, opencv, etc.
    "halbert-core[light]",
    "sentence-transformers>=2.2",
    "torch>=2.0",
    "opencv-python>=4.8",
]
```

Install on N150/Pi: `pip install halbert-core[light]`

---

## 4. Future: GPU Offload via Tailscale (Noted, Not Planned)

The founder noted that GPU-intensive tasks (VLM captioning, large model inference) could be offloaded to local-networked GPUs via Tailscale. This is a future architecture consideration:

- A light-hardware Halbert instance could proxy model requests to a more powerful machine on the Tailscale network
- The `secure_model` would still be local (3B on the N150), but the `chat_model` or `vision_model` could point at a remote Ollama instance on a GPU machine
- This is already possible today — the model endpoints in `models.yml` accept any URL, including Tailscale IPs
- No code change needed; this is a deployment configuration pattern

**Action:** Document this as a supported deployment topology in `deploy/README.md` when Phase 8 lands.

---

## 5. Sentient Home Roadmap Alignment

The Sentient Home Gap Analysis defines 6 gaps and a 5-phase roadmap. Here's how they align with Phase 8 and beyond:

| Gap | Description | Phase | Dependency |
|-----|-------------|-------|------------|
| 1 | Identity & Multi-Instance | **Phase 7 (DONE)** | — |
| 2 | Spatial Entity-Camera Fusion | Post-Phase 8 | HA Area Registry API + Frigate zone mapping |
| 3 | Semantic Visual Memory | Post-Phase 8 | Local VLM (Ollama moondream/qwen2.5-vl) + FTS5 index |
| 4 | Voice Duplex Pipeline | Post-Phase 8 | WebSocket PCM + Silero VAD + faster-whisper + Piper |
| 5 | Ambient Sentient UI | Post-Phase 8 | AreaGrid.tsx + TemporalChronicle.tsx + Lovelace embed |
| 6 | Physical Action Safety Policy | Post-Phase 8 | HomeSafetyPolicy class + governance levels |

**Phase 8 unblocks Gaps 3 and 4** by ensuring Ollama-based embeddings and models work on light hardware. Gap 2 (spatial fusion) and Gap 5 (ambient UI) are pure frontend work that can proceed in parallel. Gap 6 (safety policy) is backend logic that can proceed in parallel.

---

## 6. Open Questions for Founder

1. **`secure_model` slot approval** — Confirm the 4-slot model architecture (chat, specialist, vision, secure). Should the cognitive tick always use `secure_model`, or should that be configurable?

2. **Cloud model defaults** — Should we ship a default `models.yml` that points `chat_model` at a specific cloud provider (e.g., OpenAI), or leave it unconfigured and let the onboarding flow guide the user?

3. **Onboarding flow priority** — Should the onboarding role selection (Workstation / Home Hub / All-in-One) be built as part of Phase 8, or deferred to a separate frontend phase?

4. **Light hardware target** — Is the N150 the primary target, or is Pi 5 equally important? This affects whether we need ARM64 wheels for any dependencies.

5. **Tailscale GPU offload** — Should we document this deployment topology in Phase 8, or defer to a future "multi-node" phase?

6. **Sentient Home UI priority** — Should any of the Gap Analysis UI work (AreaGrid, TemporalChronicle, Settings > Home & Space) be pulled into Phase 8, or kept as a separate post-Phase-8 workstream?

---

## 7. Proposed Implementation Order

```
Phase 8A: Model Architecture (1-2 sessions)
  ├── secure_model slot in models.yml + client.py
  ├── Local-only enforcement for secure_model
  ├── Route cognitive tick to secure_model
  ├── Remove HALBERT_MODEL from systemd units
  └── Tests for secure_model routing

Phase 8B: Light Variant Packaging (1-2 sessions)
  ├── Ollama embedding backend
  ├── Wire embedding backend into cognition_wiring.py
  ├── Dependency trimming (pyproject.toml [light] extras)
  ├── Provisioning script for models.yml
  └── Deploy README updates (Ollama pull, Tailscale topology)

Phase 8C: Onboarding + BeingConfig (1 session, optional)
  ├── BeingConfig fields (scene_context, variant, ha_url)
  ├── Onboarding role selection UI
  └── Settings > Home & Space section

Phase 8D: Commit, merge, push
```

---

## 8. Related Documents

- `.handoff/HALBERT-MULTI-INSTANCE-DESIGN.md` — Phase 7 design (implemented)
- `.handoff/HALBERT-MULTI-INSTANCE-REVIEW-FEEDBACK.md` — Phase 7 review feedback (implemented)
- `.handoff/HOME-AUTOMATION-IMPLEMENTATION-STRATEGY.md` — Master roadmap (Phases 1-8)
- `.handoff/SENTIENT-HOME-GAP-ANALYSIS.md` — Post-Phase 8 gap analysis
- `.handoff/HANDOFF-SENTIENT-HOME-UX.md` — Sentient Home UX specification
- `documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` — Pricing & distribution
- `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` — Mac App Store strategy
- `halbert_core/halbert_core/model/client.py` — Model client (3 slots, needs 4th: `secure_model`)
- `halbert_core/halbert_core/model/llm_config.py` — Model config store (`SLOTS` tuple at line 61 is the single point of truth)
- `halbert_core/halbert_core/model/config_wizard.py` — Model config wizard defaults (line 230-255)
- `halbert_core/halbert_core/model/tier_router.py` — Tier router config (line 111-135, reads 3 slots)
- `halbert_core/halbert_core/model/__init__.py` — Model package exports (line 27-36, 68-77)
- `halbert_core/halbert_core/integrations/cognition_wiring.py` — Cognitive tick wiring (will route to `secure_model`)
- `deploy/halbert-home.service` — Home systemd unit (has dead `HALBERT_MODEL=qwen2.5:3b` at line 32)
- `deploy/halbert-host.service` — Host systemd unit

---

## 9. Feedback Area (For Reviewing AI Session)

<!-- Reviewing AI session: please add your feedback, concerns, and answers to the open questions below. Do not edit above this line. -->

### Reviewer Notes

#### 1. Executive Summary & Architectural Alignment
The transition from Phase 7 to Phase 8 is well-grounded in the multi-instance and config isolation infrastructure built in Phase 7. The introduction of the `secure_model` slot and a lightweight packaging variant (`halbert-core[light]`) provides the missing foundation for running Halbert reliably across the entire hardware spectrum — from legacy dual-core Intel machines and low-power Intel N100/N150 mini PCs to Raspberry Pi 4/5 ARM64 boards, up to high-end Apple Silicon and multi-GPU workstations.

However, several critical course corrections are required to ensure the design remains robust, strictly adheres to project rules (specifically avoiding hardcoded models and model recommendations), limits local workloads appropriately while enabling seamless cloud/LAN offloading, and maintains a transparent, intuitive UX without patronizing feature hiding or over-engineering.

---

### Critical Findings & Design Corrections

#### Finding 1: Zero Tolerance for Hardcoded Models & Hardcoded Recommendations
* **The Problem:** Sections §2.1, §2.3, §3.1, and §3.3 in the proposal introduce specific model strings (`qwen3:4b`, `llama3.2:3b`, `gemma3:4b`, `phi4-mini`, `nomic-embed-text`, `gpt-4o`) and make explicit model recommendations.
* **The Architecture Rule:** Halbert's core design (established in `hardware_detector.py` and `config_wizard.py`) operates strictly on **Model Budgets (parameter sizes in billions and memory ceilings)** and **dynamic capability discovery**, never hardcoded model names or static recommendations.
* **Mandated Corrections:**
  1. **Slot Contract:** The 4 slots (`chat_model`, `specialist_model`, `vision_model`, `secure_model`) must represent functional roles and constraints, not specific model identifiers.
  2. **Dynamic Endpoint Discovery:** When listing or defaulting models, query the endpoint's live catalog (`GET /api/tags` for Ollama, `GET /v1/models` for OpenAI-compatible/cloud) and filter by the detected `ModelBudget` (e.g. `pick_installed_model()`).
  3. **No Hardcoded Embedding Models:** `OllamaEmbeddingBackend` must NOT hardcode `model="nomic-embed-text"`. It should accept an embedding model name from config/env (`HALBERT_EMBEDDING_MODEL`), discover installed embedding models on the endpoint (e.g., tags containing `embed`), or allow the user to select their preferred embedding model in settings.

#### Finding 2: Universal Hardware Spectrum & Hardware Profiling
Halbert must run reliably across three primary low-power tiers without crashing, thrashing swap, or hanging the event loop:
1. **Legacy Intel PCs (Core 2 Duo / 2nd–6th Gen Core / Celeron / Pentium, 4GB–8GB RAM, slow CPU, SATA/HDD, limited/no AVX2):**
   - *Constraint:* CPU inference is slow (1–3 tok/s). Heavy background indexing or importing large Python packages (`torch`) exhausts RAM.
   - *Strategy:* Run `[light]` core (no PyTorch in memory). Use template thoughts (`HALBERT_LLM_THOUGHTS=0`). Offload general chat to Cloud or LAN GPU, and offload SourcePrep indexing to a networked desktop (`SOURCEPREP_URL`).
2. **Intel N100 / N150 / N95 Mini PCs (Alder Lake-N / Twin Lake, 4–8 E-cores, 8GB–16GB RAM, AVX2, NVMe):**
   - *Constraint:* CPU-only inference, 6–15W TDP ceiling.
   - *Capability:* Capable of ~10–15 tok/s on quantized 3B–4B models. Comfortable running a local `secure_model` (3B–4B) + Halbert daemon + Home Assistant.
   - *Strategy:* Run local `secure_model` via Ollama; offload heavy specialist or general chat to Cloud or LAN if desired.
3. **Raspberry Pi 4 / 5 (ARM64 / aarch64, 2GB–8GB RAM, Broadcom SoC, SD/USB/NVMe storage):**
   - *Constraint:* Pi 4 achieves ~3–5 tok/s; Pi 5 achieves ~8–12 tok/s on small models. Compiling heavy wheels (like PyTorch or older ChromaDB) on ARM64 is error-prone and memory-intensive.
   - *Strategy:* `halbert-core[light]` pure-wheel installation. Use Ollama ARM64 binary for local inference/embeddings. Offload SourcePrep indexing over LAN.
4. **`hardware_detector.py` Gap:**
   - Currently, `_classify_hardware()` classifies all systems with `< 12GB RAM` as `HardwareProfile.UNKNOWN`.
   - *Fix:* Introduce explicit profiles in `HardwareProfile` (e.g., `SBC_LOW_POWER` for <=4GB, `ENTRY_8GB` for 4–8GB) and calibrate realistic memory budgets (`max_params_b_4bit`: ~1B–2B on 4GB, ~3B–4B on 8GB, ~7B on 16GB).

#### Finding 3: Tooling Limits vs. Tool Offload Architecture (Networked & Cloud)
* **Limiting Machine Tooling to Hardware Capabilities:**
   - **Dependency Trimming (`pyproject.toml`):** Move `sentence-transformers` and legacy `chromadb` out of base `dependencies` into optional extras (`[rag-legacy]`, `[full]`). The `[light]` baseline saves ~1.5GB of disk and ~500MB of idle RAM.
   - **Background Workload Gating:** On `HALBERT_VARIANT=home` or low-power hardware, relax telemetry polling intervals and suppress heavy journald/hardware discovery sweeps.
   - **Cognitive Monologue Gating:** Keep `HALBERT_LLM_THOUGHTS=0` (template thoughts) by default. Only invoke LLM-generated internal thoughts when explicitly enabled and when local compute or a dedicated `secure_model` is configured.
* **Networked & Cloud Alternate Tools:**
   - **SourcePrep Offload:** The `SourcePrepClient` and `SourcePrepRetrievalBackend` naturally accept `base_url` (configured via `SOURCEPREP_URL` or settings). A tiny Raspberry Pi or N100 can run without local SourcePrep daemon by querying a workstation or home server running SourcePrep at `http://desktop.lan:8400`.
   - **Cloud LLM Offload:** `chat_model`, `specialist_model`, and `vision_model` can point to OpenAI, Anthropic, Gemini, Groq, or OpenRouter via saved endpoints.
   - **LAN / Tailscale Model Offload:** Any endpoint URL in `models.yml` can point to an Ollama or vLLM instance on a local IP or Tailscale node (e.g., `http://gpu-rig.tailscale:11434`), allowing low-power nodes to borrow workstation GPU compute.
   - **Local Privacy Boundary:** The `secure_model` remains strictly local (loopback) to process sensitive configuration and persona state safely.

#### Finding 4: UX Philosophy — Simple, Intuitive, Invisible, BUT Never Hide Features
* **Anti-Pattern Warning (Do NOT Hide Features on Low Hardware):**
   - Detecting low hardware (e.g. 4GB RAM or Raspberry Pi) must **NEVER** hide settings tabs, model slots, specialist/vision configuration, or cloud providers.
   - A user running Halbert on a Raspberry Pi 4 might intentionally use Cloud APIs (Claude 3.5 Sonnet, GPT-4o) or point to a remote LAN server with dual RTX 4090s. Hiding options based on local CPU/RAM is patronizing and breaks valid topologies.
* **Transparent & Helpful UX:**
   - Display detected hardware budget and profile clearly in Settings ("Hardware Budget: ~3B local parameters | Cloud / LAN offloading active").
   - Pre-populate conservative, non-breaking defaults (e.g., leaving heavy slots disabled until an endpoint is selected).
   - Provide clean, zero-friction setup without modal pop-up traps or rigid wizards.
* **Avoid Over-Engineering:**
   - Avoid building complex runtime load-balancers, dynamic heuristic CPU-throttling schedulers, or distributed consensus protocols.
   - Rely on standard declarative YAML (`models.yml`), standard environment overrides (`SOURCEPREP_URL`, `HALBERT_VARIANT`, `HALBERT_CONFIG_DIR`), and straightforward HTTP/REST connections.

#### Finding 5: Code Audit & Security Guardrails
1. **Local-Only Enforcement for `secure_model`:**
   - The proposed check `if not any(host in ep_url for host in ("localhost", "127.0.0.1", "0.0.0.0"))` in §2.6 is fragile (e.g., matches `http://attacker.com/localhost`, fails on `http://[::1]:11434` or unix sockets).
   - *Fix:* Use standard URL parsing:
     ```python
     from urllib.parse import urlparse
     import ipaddress

     def is_local_endpoint(url: str) -> bool:
         try:
             hostname = urlparse(url).hostname or ""
             if hostname in ("localhost", "0.0.0.0"):
                 return True
             ip = ipaddress.ip_address(hostname)
             return ip.is_loopback or ip.is_unspecified
         except ValueError:
             return False
     ```
2. **Ollama Embeddings API Batching:**
   - Ollama supports `/api/embed` with batching (`input: ["chunk1", "chunk2", ...]`).
   - `OllamaEmbeddingBackend` should attempt `/api/embed` first for efficient single-request batching, and fall back to sequential `/api/embeddings` only on legacy Ollama versions (< 0.1.44).

---

### Answers to Open Questions (§6)

1. **`secure_model` slot approval & Cognitive Tick Routing:**
   - **Approved.** The 4-slot model architecture (`chat_model`, `specialist_model`, `vision_model`, `secure_model`) is clean, orthogonal, and backwards-compatible.
   - **Cognitive Tick:** When `HALBERT_LLM_THOUGHTS` is enabled, internal monologue must route to `secure_model` (with fallback to `chat_model` ONLY if `chat_model` is also a verified local endpoint; otherwise fall back to template thoughts). Persona memories and internal cognitive monologue must never be sent to cloud providers without explicit user instruction.

2. **Cloud model defaults vs. Onboarding:**
   - **Leave unconfigured.** Do not ship hardcoded cloud provider keys or pre-pinned model names. A fresh install should gracefully prompt the user in Settings / Onboarding to pick their preferred provider (Cloud API key, local Ollama, or LAN endpoint).

3. **Onboarding flow priority:**
   - Keep onboarding minimal and non-blocking. A lightweight selection (Role: Workstation Sysadmin vs. Home Hub vs. Light Client) that sets `variant` and opens the unified Model Picker is sufficient. Defer elaborate multi-step onboarding wizards.

4. **Light hardware target:**
   - **Both N100/N150 and Raspberry Pi 4/5 (ARM64) are first-class targets**, alongside legacy Intel computers. All dependencies in the `[light]` group must be pure Python or have standard pre-compiled ARM64 / x86_64 wheels on PyPI.

5. **Tailscale & LAN Offload:**
   - Supported out-of-the-box via URL configuration. Document the deployment topology in `deploy/README.md` (e.g., setting `SOURCEPREP_URL=http://<lan-host>:8400` and adding remote Ollama / vLLM URLs into `models.yml`).

6. **Sentient Home UI priority:**
   - Keep UI modular. Implement the essential multi-instance and status indicators without hiding existing sysadmin or configuration controls. Full spatial ambient UI (AreaGrid, TemporalChronicle) remains in its dedicated post-Phase 8 workstream.

---

### Additional Concerns or Recommendations

1. **Pyproject.toml Base Dependency Cleanup:**
   - Ensure `chromadb` and `sentence-transformers` are completely removed from mandatory `project.dependencies` in `halbert_core/pyproject.toml` and moved to optional extras. This unblocks instant, lightweight installation on Raspberry Pi and low-spec machines.
2. **Advisory Lock Scope:**
   - In `model/client.py`, ensure `llm_advisory_lock()` continues to protect local GPU/CPU endpoints (`ollama`, `llamacpp`, `mlx`, `lm-studio`) from concurrent contention between Halbert and SourcePrep while allowing cloud endpoints to execute concurrently without locking.
3. **Graceful Fallbacks for Offline / Degraded State:**
   - If `chat_model` is configured to Cloud but the network is offline, surface a clean, actionable status banner in the UI rather than unhandled network timeout exceptions. If a local `secure_model` is available, the agent can still respond to local sysadmin queries or queue tasks.

