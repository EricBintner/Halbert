# Phase 7 → Phase 8 Transition Review & Work Plan

**Date:** 2026-08-29
**Status:** Ready for review — awaiting founder sign-off before implementation
**Scope:** Phase 7 completeness audit, model routing correction, Phase 8 detailed work plan, and Sentient Home roadmap alignment

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

### 2.2 Current Model Architecture

The model system has three slots in `models.yml`:

| Slot | Purpose | Current Default | Should Default To |
|------|---------|-----------------|-------------------|
| `chat_model` | General conversation, tool calling | Local Ollama (no model configured) | **Cloud** (user's choice — OpenAI/Anthropic) |
| `specialist_model` | Code generation, complex reasoning | Not configured | Cloud or powerful local (14B+) |
| `vision_model` | Image understanding | Falls back to chat_model | Cloud (GPT-4V, etc.) or local VLM |

**Missing slot:** `secure_model` — a model that is **guaranteed local-only** for processing sensitive data. This does not exist yet.

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
    model: qwen2.5:3b              # small, fast, never leaves the machine
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
#   secure_model → qwen2.5:3b (local-only, hardcoded)
```

### 2.5 Routing Flow

```
User message → chat_model (cloud, user's choice)
                ↓
            Tool execution → tool may handle sensitive data
                ↓
            Sensitive data processing → secure_model (local 3B, never leaves machine)
                ↓
            Tool result (sanitized) → back to chat_model for response synthesis
```

The cognitive tick (`advance_turn`) runs on `secure_model` because it processes persona memory and internal state — this is the being's private monologue, not user-facing chat.

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
- `halbert_core/halbert_core/model/client.py` — Model client (3 slots, needs 4th)
- `halbert_core/halbert_core/model/llm_config.py` — Model config store
- `halbert_core/halbert_core/model/config_wizard.py` — Model config wizard defaults
