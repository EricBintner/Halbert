# Phase 7 → Phase 8 Transition Review & Work Plan

**Date:** 2026-08-29
**Status:** Ready for review — awaiting feedback from another AI session before implementation
**DO NOT IMPLEMENT until feedback is received in this document.**
**Scope:** Phase 7 completeness audit, model routing correction, model architecture code audit, Phase 8 detailed work plan, and Sentient Home roadmap alignment

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** sections 2–4, 7, and the §9 reviewer notes predate that handoff and have been revised in place. Governing direction: `secure_model` is a **sysadmin-variant-only** slot; `home`/`home-light` variants run **no local LLM**, **no SourcePrep** (local or remote — no `SOURCEPREP_URL`), and **no model picker** (a single "Compute Peer" setting instead; the workstation's picker governs); the 1B model tier is dropped and `SBC_LOW_POWER` (<4GB per code) is offload-only. Superseded passages below carry dated revision markers.

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

**Fix needed (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`):** delete the dead `HALBERT_MODEL` line — do not wire it. `home`/`home-light` variants are configured with a **Compute Peer** address (hostname:port or Tailscale), not a local model; `models.yml` model-slot provisioning applies to the sysadmin variant only (Findings 1/3/4).

---

## 2. Model Routing Correction — Critical Design Clarification

### 2.1 Founder Intent (Clarified 2026-08-29)

> "Is 3B model defaults for the secure data LLM? That's the only one that should default to local. The rest we encourage cloud but that's up to the user."

**The 3B model is NOT the general chat model.** It is the **secure-data local model** — the model that processes sensitive data (system configs, secrets, credentials) that must never leave the machine. The general chat model should default to cloud (OpenAI, Anthropic, etc.) with local as fallback.

**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** "HA tokens" and "Frigate camera frames" are removed from the `secure_model` scope — the HA LLM never sees them (they live behind HA's and Frigate's API abstractions; Halbert consumes MQTT events). `secure_model` is a **sysadmin-variant-only** slot; `home`/`home-light` variants do not configure it at all (Finding 1).

**Note on qwen2.5:** The `qwen2.5:3b` reference in the systemd unit is outdated. Qwen 2.5 is a 2024-era model. Current (2026) recommended small local models for the `secure_model` slot:

| Model | Params | RAM (Q4) | License | Ollama Pull | Notes |
|-------|--------|----------|--------|-------------|-------|
| **Qwen3 4B** | 4B | ~3-4 GB | Apache 2.0 | `qwen3:4b` | Best all-round small model; strong reasoning + tool calling |
| Llama 3.2 3B | 3B | ~3 GB | Llama Community | `llama3.2:3b` | Fastest inference; best for CPU-only/N150 |
| Gemma 3 4B | 4B | ~3-4 GB | Gemma | `gemma3:4b` | Multimodal (vision); 140+ languages |
| Phi-4-mini | 3.8B | ~3 GB | MIT | `phi4-mini` | Best math/structured output at this size |

**Recommendation:** Default `secure_model` to `qwen3:4b` (Apache 2.0, best general capability). For N150/Pi 5 class hardware where every MB counts, `llama3.2:3b` is the lighter fallback. The model choice is a deployment config, not a code decision. **Revised 2026-08-30:** this default applies to the **sysadmin variant only** — `home`/`home-light` variants do not configure `secure_model` at all (Finding 1), and there is no mandatory local model on HA nodes.

### 2.2 Current Model Architecture (Code Audit)

> **Revised 2026-08-30 (code-verified):** the code snapshot below predates the `secure_model` implementation — the slot now exists in the code: `SLOTS` is a 4-tuple (`llm_config.py:64`), `default_llm_config()` ships it empty for every variant, local-only enforcement lives in `normalise()` via `_is_local_url()` (`llm_config.py:135-149, 417-423`), and `get_secure_model()` exists in `client.py`. Read §2.7's change list accordingly: the slot infrastructure is built and **stays for the sysadmin variant only**; the open work is the simplification handoff's S1 scoping (`home`/`home-light` leave the slot empty, hide the picker row, and gate Apple Intelligence auto-provisioning and the wizard's `secure_model` writes by variant).

The model system lives in five files:

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
| `secure_model` (NEW) | Sensitive data processing, cognitive tick | Does not exist | **Local-only, sysadmin variant only** (qwen3:4b or llama3.2:3b); home/home-light: **not configured** (Finding 1, S1) |

> **Revised 2026-08-30:** on `home`/`home-light` variants none of these slots is locally provisioned — `chat_model`/`specialist_model` resolve to `peer://<workstation>:8000` set via the single Compute Peer setting (the workstation's picker governs — Finding 3 / S3), `secure_model` stays empty, and `vision_model` is pending handoff open question 3 (Frigate may handle all vision, in which case HA nodes need no `vision_model`).

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

**Use cases for `secure_model` (sysadmin variant only — revised 2026-08-30):**
- Processing system config files (`/etc/hosts`, `~/.zshrc`) — sysadmin work; HA config inspection happens from the workstation's Halbert via the fleet cockpit / MCP path, not from the HA node's own Halbert
- Summarizing journald logs
- Any tool execution that handles secrets, tokens, or credentials
- Cognitive tick (`advance_turn`) internal monologue — this is persona memory, not user-facing chat; on `home`/`home-light` variants the monologue uses deterministic template thoughts (`HALBERT_LLM_THOUGHTS=0`) — no local LLM

**Revised 2026-08-30:** "Analyzing Frigate camera frames" is removed — Frigate frames never reach the LLM (Halbert subscribes to MQTT events, e.g. "person detected"). Camera-credential edge cases on HA nodes are deterministic redaction (`redact_text()` / the `describe_secret` Tier 2 path), not LLM reasoning.

**Use cases for `chat_model` (cloud-encouraged):**
- User-facing conversation
- Tool calling (the tool *results* may be sanitized before reaching the cloud model)
- Code generation
- General reasoning

### 2.4 Systemd Unit Fix

The home service unit should NOT set `HALBERT_MODEL=qwen2.5:3b` as a blanket default. Instead:

```ini
# Remove: Environment=HALBERT_MODEL=qwen2.5:3b
# Revised 2026-08-30: home/home-light variants are pure compute clients —
# provisioning sets the compute peer address (hostname:port or Tailscale),
# and chat_model/specialist_model resolve to peer://<workstation>:8000 (S3).
# No local model slots are provisioned on home variants; per-slot models.yml
# provisioning (including secure_model) applies to the sysadmin variant only.
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

The cognitive tick (`advance_turn`) runs on `secure_model` because it processes persona memory and internal state — this is the being's private monologue, not user-facing chat. **Revised 2026-08-30:** this routing is **sysadmin-variant only**; on `home`/`home-light` variants the cognitive monologue uses deterministic template thoughts (`HALBERT_LLM_THOUGHTS=0`) — no local model, no `secure_model` (Finding 4; handoff open question 4 asks whether `advance_turn` should be disabled entirely on HA variants).

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

> **Status note (2026-08-30, code-verified):** this change list is largely complete in the code — the 4-slot `SLOTS` tuple, the `default_llm_config()` entry, the `normalise()` local-only check, `get_secure_model()` in `client.py`, and the `tier_router` read all exist (see the §2.2 revision). The remaining work is the simplification handoff's **S1** scoping: gate Apple Intelligence auto-provisioning (`auto_provision.py`) and the wizard's `secure_model` writes (`config_wizard.py`) by variant, skip the secure turn gate for `home`/`home-light` (`agent.py`), and hide the role in the UI for HA variants.

| File | Change | Lines |
|------|--------|-------|
| `model/llm_config.py:61` | Add `"secure_model"` to `SLOTS` tuple | 1 |
| `model/llm_config.py:122-128` | Add `secure_model` to `default_llm_config()` | 1 |
| `model/llm_config.py:351-387` | Add local-only check in `normalise()` loop | ~5 |
| `model/client.py` | Add `get_secure_model()` function | ~10 |
| `model/__init__.py` | Export `get_secure_model` | 2 |
| `model/config_wizard.py:230-255` | Add `secure_model` to wizard defaults — **sysadmin variant only**; on `home`/`home-light` and `SBC_LOW_POWER` the wizard prompts for a compute peer address, not model slots (S4) | ~5 |
| `model/tier_router.py:111-135` | Add `secure_model` to `from_legacy_config()` | ~5 |
| `deploy/halbert-home.service` | Remove `HALBERT_MODEL=qwen2.5:3b` line | 1 |
| `deploy/halbert-host.service` | Remove `HALBERT_MODEL` line if present | 1 |
| `deploy/README.md` | Update model references; document that home variants have no local model, no SourcePrep / no `SOURCEPREP_URL` (S2), and use the Compute Peer setting (S3) | ~5 |
| `tests/test_secure_model.py` | New test file | ~60 |

**Total:** ~95 lines across 10 files.

---

## 3. Phase 8 — Light Variant Packaging (Detailed Work Plan)

### 3.1 Objective

Package Halbert for Intel N150 / Raspberry Pi 5 class hardware. The same GPL-3.0 codebase, with:
- Persona memory embeddings staying **local** on the HA node — they are NOT SourcePrep and cannot be offloaded — served via **haloysius's ONNX/Ollama `MemoryEmbedder`** (revised 2026-08-30: NOT a new halbert_core embedding module and NOT sentence-transformers in halbert_core; keep `[light]` unchanged — S5, pending open decision D3)
- No `secure_model` on the light variant at all — `secure_model` exists only in the sysadmin variant; `home`/`home-light` offload all LLM work to the compute peer (Finding 1)
- Reduced dependency footprint (no GPU/CV libraries on light hardware)
- Background service gating via `HALBERT_VARIANT=home` (already implemented)

### 3.2 Work Items

| # | Task | Files | Effort | Dependency |
|---|------|-------|--------|------------|
| 1 | **Resolve persona-memory embedding serving** *(revised 2026-08-30, S5)* | Verify which memory path the HA persona consumes (open decision D3); if the haloysius embedder is operative, serve embeddings via its ONNX/Ollama `MemoryEmbedder` (`haloysius memory/embeddings.py`) — no new halbert_core module, no sentence-transformers in halbert_core extras | Verification | None |
| 2 | **`secure_model` slot in models.yml — sysadmin variant only** | `model/llm_config.py`, `model/client.py`, `model/config_wizard.py` — home/home-light leave the slot empty and the picker row is hidden (`variants: ["sysadmin"]` on the role, S1) | ~80 lines | None |
| 3 | **Local-only enforcement for secure_model** | `model/client.py` — validate endpoint URL is localhost | ~15 lines | #2 |
| 4 | **Route cognitive tick to secure_model on the sysadmin variant** | `cognition_wiring.py` — `advance_turn` uses `secure_model` not `chat_model`; on home/home-light the monologue is template thoughts, no local LLM (Finding 4; handoff open Q4 asks whether `advance_turn` should be disabled entirely on HA variants) | ~10 lines | #2 |
| 5 | **Remove `HALBERT_MODEL` from systemd units** | `deploy/halbert-home.service`, `deploy/halbert-host.service` | ~2 lines | None |
| 6 | **Provisioning script** | New `deploy/provision-models.sh` — home instances get the compute peer address; per-slot `models.yml` provisioning applies to sysadmin instances only (S3) | ~40 lines | #2 |
| 7 | **Dependency trimming for light hardware** | `pyproject.toml` — keep `[light]` unchanged (excludes torch, sentence-transformers, chromadb, CV libs); optionally add `[home]` = `[light]` + `[cognition]` (S5) | ~15 lines | #1 |
| 8 | **Embedding model documentation** *(contingent on D3)* | `deploy/README.md` — only if the haloysius Ollama embedder is the operative path: document the embedding model pull (e.g. `nomic-embed-text`); no sentence-transformers install on HA nodes | Documentation | #1 |
| 9 | **Tests for secure_model routing** | `tests/test_secure_model.py` | ~60 lines | #2, #3 |

### 3.3 Ollama Embedding Backend Design — SUPERSEDED

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (section 4.7, code-verified correction): do not build a halbert_core Ollama embedding backend.** The original design in this section proposed an `OllamaEmbeddingBackend` in `halbert_core/model/ollama_embeddings.py` as a drop-in replacement for sentence-transformers on home variants. Code verification overturned its premise:

- The on-path persona memory embedder is **`haloysius.memory.embeddings.MemoryEmbedder`** (wired via `cognition_wiring.py`), which already tries the ONNX/Ollama embedder first, sentence-transformers only as a legacy fallback, and TF-IDF last. `sentence-transformers` lives in **haloysius's own optional `[embeddings]` extra** (which pins torch), not in halbert_core.
- halbert_core's own sentence-transformers consumer (`rag/embeddings.py` `EmbeddingManager`) feeds only the eval/browser-only `HybridMemorySystem`, which is fenced off the agent path.
- Adding sentence-transformers to halbert_core's `[light]` would wire a dependency into the wrong package without touching the memory that actually runs on a home node — and it drags in torch, exactly the weight `[light]` exists to avoid.

**Revised direction (S5):** keep `[light]` unchanged; serve memory embeddings on HA nodes via **Ollama (e.g. `nomic-embed-text`) or the haloysius ONNX embedder**, with `haloysius[embeddings]` as the optional local-transformer upgrade (optionally surfaced as a `[home]` extra = `[light]` + `[cognition]`). Before any packaging change, confirm which memory path the HA persona actually consumes — open decision **D3**: the dashboard agent path currently wires `memory_service=None` with receipts/FTS5 recall; if that is the operative path on a home node, no packaging change is needed at all.

### 3.4 Dependency Trimming

> **Revised 2026-08-30:** this section survives with corrected rationale — `[light]` stays without torch/sentence-transformers/chromadb not because a new Ollama backend replaces them, but because home-node memory embeddings are served by haloysius's ONNX/Ollama `MemoryEmbedder` (see §3.3 revision); `haloysius[embeddings]` is the optional local-transformer upgrade. Chromadb exclusion is confirmed (no ChromaDB on home variants, S2). Never install `[rag-legacy]` (bundles chromadb) on HA nodes.

```toml
# pyproject.toml
[project.optional-dependencies]
light = [
    # No torch, no sentence-transformers, no CV libraries
    # Memory embeddings via haloysius ONNX/Ollama MemoryEmbedder
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

## 4. GPU Offload via Tailscale (Now the Federated Compute Architecture)

The founder noted that GPU-intensive tasks (VLM captioning, large model inference) could be offloaded to local-networked GPUs via Tailscale.

**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** this is no longer a "noted, not planned" deployment pattern — it is the federated compute architecture, and for `home`/`home-light` variants it is the **only** model path:

- The home node runs **no `secure_model`** and no local LLM at all (Findings 1 and 4)
- All LLM work (`chat_model`, `specialist_model`) offloads to the compute peer via the single **Compute Peer** setting; the workstation's model picker governs (Finding 3 / S3)
- This is a code-supported architecture (federated scaffold: `PeerProvider`, `ComputeRouter`, `compute_endpoint`, `peer://` endpoints), not merely a URL-configuration pattern — and it is **not** "already possible today": `peer` is not yet registered in the model stack (`CHAT_CAPABLE_PROVIDERS`, `tier_router.py`, `providers/__init__.py`), so no peer endpoint can be created or resolved yet (handoff W14)

**Action:** Implement the simplification steps S1–S7 from the 2026-08-30 handoff (its section 10) before the federated Phase 9 work, then document the Compute Peer topology in `deploy/README.md`.

---

## 5. Sentient Home Roadmap Alignment

The Sentient Home Gap Analysis defines 6 gaps and a 5-phase roadmap. Here's how they align with Phase 8 and beyond:

| Gap | Description | Phase | Dependency |
|-----|-------------|-------|------------|
| 1 | Identity & Multi-Instance | **Phase 7 (DONE)** | — |
| 2 | Spatial Entity-Camera Fusion | Post-Phase 8 | HA Area Registry API + Frigate zone mapping |
| 3 | Semantic Visual Memory | Post-Phase 8 | VLM via the compute peer + FTS5 index (pending handoff open question 3: Frigate may handle all vision — Halbert consumes MQTT events — in which case HA nodes need no `vision_model`) |
| 4 | Voice Duplex Pipeline | Post-Phase 8 | WebSocket PCM + Silero VAD + faster-whisper + Piper |
| 5 | Ambient Sentient UI | Post-Phase 8 | AreaGrid.tsx + TemporalChronicle.tsx + Lovelace embed |
| 6 | Physical Action Safety Policy | Post-Phase 8 | HomeSafetyPolicy class + governance levels |

**Phase 8 unblocks Gaps 3 and 4** by ensuring the light variant runs with local persona-memory embeddings (haloysius ONNX/Ollama `MemoryEmbedder` — revised 2026-08-30; not sentence-transformers in halbert_core) and offloaded LLM/VLM inference via the compute peer; no local VLM runs on the HA node. Gap 2 (spatial fusion) and Gap 5 (ambient UI) are pure frontend work that can proceed in parallel. Gap 6 (safety policy) is backend logic that can proceed in parallel.

---

## 6. Open Questions for Founder

1. **`secure_model` slot approval** — Confirm the 4-slot model architecture (chat, specialist, vision, secure). Should the cognitive tick always use `secure_model`, or should that be configurable? **Partially superseded 2026-08-30:** the 4-slot architecture stands, but scoped — `secure_model` is a **sysadmin-variant** slot; `home`/`home-light` never configure it, and their cognitive tick is template thoughts (Finding 1 / Finding 4).

2. **Cloud model defaults** — Should we ship a default `models.yml` that points `chat_model` at a specific cloud provider (e.g., OpenAI), or leave it unconfigured and let the onboarding flow guide the user? **Revised 2026-08-30 for home variants:** no default model at all — the workstation's model picker governs via the peer link (Finding 3); the sysadmin-variant question stands as written.

3. **Onboarding flow priority** — Should the onboarding role selection (Workstation / Home Hub / All-in-One) be built as part of Phase 8, or deferred to a separate frontend phase?

4. **Light hardware target** — Is the N150 the primary target, or is Pi 5 equally important? This affects whether we need ARM64 wheels for any dependencies.

5. **Tailscale GPU offload** — Should we document this deployment topology in Phase 8, or defer to a future "multi-node" phase?

6. **Sentient Home UI priority** — Should any of the Gap Analysis UI work (AreaGrid, TemporalChronicle, Settings > Home & Space) be pulled into Phase 8, or kept as a separate post-Phase-8 workstream?

---

## 7. Proposed Implementation Order

> **Revised 2026-08-30:** the simplification handoff supersedes parts of this order — its section 10 (steps S1–S7) and section 12 (W1–W25, D1–D4) are the authoritative work list. The tree below is revised to match.

```
Phase 8A: Model Architecture (1-2 sessions)
  ├── secure_model slot in models.yml + client.py — sysadmin variant only;
  │   home/home-light leave the slot empty and hide the picker row (S1)
  ├── Local-only enforcement for secure_model (sysadmin variant)
  ├── Route cognitive tick to secure_model — sysadmin variant only;
  │   home/home-light use template thoughts, no local LLM (Finding 4)
  ├── Remove HALBERT_MODEL from systemd units
  └── Tests for secure_model routing

Phase 8B: Light Variant Packaging (1-2 sessions)
  ├── Verify the HA persona memory path (open decision D3), then serve
  │   embeddings via haloysius ONNX/Ollama MemoryEmbedder — no new
  │   halbert_core embedding backend (S5)
  ├── Keep [light] unchanged; optionally add [home] = [light] + [cognition]
  ├── Provisioning script: compute peer for home instances;
  │   per-slot models.yml for sysadmin instances (S3)
  └── Deploy README updates: no SourcePrep / no SOURCEPREP_URL for HA
      variants (S2), Compute Peer topology (S3)

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
- `halbert_core/halbert_core/model/client.py` — Model client (4 slots incl. `secure_model`; sysadmin-only scoping pending S1)
- `halbert_core/halbert_core/model/llm_config.py` — Model config store (`SLOTS` 4-tuple at line 64 is the single point of truth; `secure_model` local-only enforced in `normalise()`)
- `halbert_core/halbert_core/model/config_wizard.py` — Model config wizard defaults (line 230-255)
- `halbert_core/halbert_core/model/tier_router.py` — Tier router config (reads the 4 slots, incl. `secure_model`)
- `halbert_core/halbert_core/model/__init__.py` — Model package exports (line 27-36, 68-77)
- `halbert_core/halbert_core/integrations/cognition_wiring.py` — Cognitive tick wiring (routes to `secure_model` on the sysadmin variant; home/home-light use template thoughts — revised 2026-08-30)
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
  3. **No Hardcoded Embedding Models:** `OllamaEmbeddingBackend` must NOT hardcode `model="nomic-embed-text"`. It should accept an embedding model name from config/env (`HALBERT_EMBEDDING_MODEL`), discover installed embedding models on the endpoint (e.g., tags containing `embed`), or allow the user to select their preferred embedding model in settings. *(Revised 2026-08-30: the halbert_core `OllamaEmbeddingBackend` is superseded — see §3.3 — the rule transfers to the haloysius ONNX/Ollama `MemoryEmbedder` if its Ollama path is configured.)*

#### Finding 2: Universal Hardware Spectrum & Hardware Profiling
Halbert must run reliably across three primary low-power tiers without crashing, thrashing swap, or hanging the event loop:
1. **Legacy Intel PCs (Core 2 Duo / 2nd–6th Gen Core / Celeron / Pentium, 4GB–8GB RAM, slow CPU, SATA/HDD, limited/no AVX2):**
   - *Constraint:* CPU inference is slow (1–3 tok/s). Heavy background indexing or importing large Python packages (`torch`) exhausts RAM.
   - *Strategy:* Run `[light]` core (no PyTorch in memory). Use template thoughts (`HALBERT_LLM_THOUGHTS=0`). Offload all LLM work to Cloud or the compute peer. **Revised 2026-08-30:** home variants have **no SourcePrep at all** — no local daemon and no remote `SOURCEPREP_URL`; the retrieval backend is not instantiated (S2). Remote SourcePrep querying remains a sysadmin-variant option.
2. **Intel N100 / N150 / N95 Mini PCs (Alder Lake-N / Twin Lake, 4–8 E-cores, 8GB–16GB RAM, AVX2, NVMe):**
   - *Constraint:* CPU-only inference, 6–15W TDP ceiling.
   - *Capability:* Capable of ~10–15 tok/s on quantized 3B–4B models — an optional local fallback on 8GB+ hosts only.
   - *Strategy:* Offload all LLM work to the compute peer (preferred); on 8GB+ hosts an optional 3B–4B local fallback may serve when the peer is asleep. **Revised 2026-08-30:** no local `secure_model` and no SourcePrep on home variants (S1, S2).
3. **Raspberry Pi 4 / 5 (ARM64 / aarch64, 2GB–8GB RAM, Broadcom SoC, SD/USB/NVMe storage):**
   - *Constraint:* Pi 4 achieves ~3–5 tok/s; Pi 5 achieves ~8–12 tok/s on small models. Compiling heavy wheels (like PyTorch or older ChromaDB) on ARM64 is error-prone and memory-intensive.
   - *Strategy:* `halbert-core[light]` pure-wheel installation. **Revised 2026-08-30:** `<4GB` (`SBC_LOW_POWER` per code) is **offload-only** — no local inference, no local embeddings model, no SourcePrep (local or remote); template thoughts when the peer is asleep (S4). An 8GB Pi 5 may use an optional 3B local fallback (offload preferred).
4. **`hardware_detector.py` Gap:**
   - Currently, `_classify_hardware()` classifies all systems with `< 12GB RAM` as `HardwareProfile.UNKNOWN`.
   - *Fix (revised 2026-08-30 per S4):* explicit profiles exist (`SBC_LOW_POWER` is strictly `<4GB` in code; a 4GB host classifies `ENTRY_8GB` — the boundary is open decision D2 in the 2026-08-30 handoff). Budget calibration: **offload-only, no local model** on `SBC_LOW_POWER`; ~3B on 8GB (`ENTRY_8GB`, fallback only, offload preferred); ~4B on 16GB. The 1B tier is dropped as a supported configuration — 2B–3B is the minimum for local inference, on 8GB+ hosts only.

#### Finding 3: Tooling Limits vs. Tool Offload Architecture (Networked & Cloud)
* **Limiting Machine Tooling to Hardware Capabilities:**
   - **Dependency Trimming (`pyproject.toml`):** Move `sentence-transformers` and legacy `chromadb` out of base `dependencies` into optional extras (`[rag-legacy]`, `[full]`). The `[light]` baseline saves ~1.5GB of disk and ~500MB of idle RAM.
   - **Background Workload Gating:** On `HALBERT_VARIANT=home` or low-power hardware, relax telemetry polling intervals and suppress heavy journald/hardware discovery sweeps.
   - **Cognitive Monologue Gating:** Keep `HALBERT_LLM_THOUGHTS=0` (template thoughts) by default. Only invoke LLM-generated internal thoughts when explicitly enabled and when local compute or a dedicated `secure_model` is configured. *(Revised 2026-08-30: on `home`/`home-light` the monologue is always template thoughts — HA nodes run no local LLM and never configure `secure_model`; handoff open question 4 asks whether `advance_turn` should be disabled entirely on HA variants.)*
* **Networked & Cloud Alternate Tools:**
   - **SourcePrep Offload (revised 2026-08-30):** for `home`/`home-light` variants there is **no SourcePrep of any kind** — no local daemon and no remote `SOURCEPREP_URL`; the `SourcePrepRetrievalBackend` is not instantiated, and explicit variant gating is required in the wiring code (leaving `SOURCEPREP_URL` unconfigured is not a mechanism — S2). The agent answers from live HA state + persona memory. Remote SourcePrep querying remains a sysadmin-variant option.
   - **Cloud LLM Offload:** `chat_model`, `specialist_model`, and `vision_model` can point to OpenAI, Anthropic, Gemini, Groq, or OpenRouter via saved endpoints.
   - **LAN / Tailscale Model Offload:** Any endpoint URL in `models.yml` can point to an Ollama or vLLM instance on a local IP or Tailscale node (e.g., `http://gpu-rig.tailscale:11434`), allowing low-power nodes to borrow workstation GPU compute — a sysadmin-variant topology; home/home-light use the Compute Peer setting instead (S3).
   - **Local Privacy Boundary (revised 2026-08-30):** the `secure_model` remains strictly local (loopback) **in the sysadmin variant**; `home`/`home-light` do not configure the slot at all (Finding 1).

#### Finding 4: UX Philosophy — Simple, Intuitive, Invisible, BUT Never Hide Features
* **Anti-Pattern Warning (Do NOT Hide Features on Low Hardware):**
   - Detecting low hardware (e.g. 4GB RAM or Raspberry Pi) must **NEVER** hide settings tabs, model slots, specialist/vision configuration, or cloud providers.
   - A user running Halbert on a Raspberry Pi 4 might intentionally use Cloud APIs (Claude 3.5 Sonnet, GPT-4o) or point to a remote LAN server with dual RTX 4090s. Hiding options based on local CPU/RAM is patronizing and breaks valid topologies.
  - **Revised 2026-08-30:** this rule governs *hardware-based* hiding and remains valid for the sysadmin variant. *Variant-based* scoping is different and required: `home`/`home-light` variants hide the model picker entirely (a Compute Peer field replaces it — S3) and hide the `secure_model` row (`variants: ["sysadmin"]` on the role — S1). A home variant is a pure compute client by architecture, not a degraded sysadmin box.
* **Transparent & Helpful UX:**
   - Display detected hardware budget and profile clearly in Settings ("Hardware Budget: ~3B local parameters | Cloud / LAN offloading active").
   - Pre-populate conservative, non-breaking defaults (e.g., leaving heavy slots disabled until an endpoint is selected).
   - Provide clean, zero-friction setup without modal pop-up traps or rigid wizards.
* **Avoid Over-Engineering:**
   - Avoid building complex runtime load-balancers, dynamic heuristic CPU-throttling schedulers, or distributed consensus protocols.
   - Rely on standard declarative YAML (`models.yml`), standard environment overrides (`SOURCEPREP_URL`, `HALBERT_VARIANT`, `HALBERT_CONFIG_DIR`), and straightforward HTTP/REST connections. *(Revised 2026-08-30: `SOURCEPREP_URL` is a sysadmin-variant override only — `home`/`home-light` configure no `SOURCEPREP_URL`, and keeping SourcePrep off HA variants requires explicit variant gating in code, not an unset env var — S2.)*

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
   - **Revised 2026-08-30:** moot as written — the halbert_core `OllamaEmbeddingBackend` (§3.3) is superseded and will not be built; the batching guidance transfers to the haloysius ONNX/Ollama `MemoryEmbedder` if its Ollama path is configured (S5).

---

### Answers to Open Questions (§6)

1. **`secure_model` slot approval & Cognitive Tick Routing:**
   - **Approved.** The 4-slot model architecture (`chat_model`, `specialist_model`, `vision_model`, `secure_model`) is clean, orthogonal, and backwards-compatible.
   - **Cognitive Tick:** When `HALBERT_LLM_THOUGHTS` is enabled, internal monologue must route to `secure_model` (with fallback to `chat_model` ONLY if `chat_model` is also a verified local endpoint; otherwise fall back to template thoughts). Persona memories and internal cognitive monologue must never be sent to cloud providers without explicit user instruction.
   - **Revised 2026-08-30:** this routing is **sysadmin-variant only**. On `home`/`home-light` there is no `secure_model` and no local `chat_model`; the monologue is always template thoughts (or `advance_turn` is disabled entirely — open question 4 of the 2026-08-30 simplification handoff).

2. **Cloud model defaults vs. Onboarding:**
   - **Leave unconfigured.** Do not ship hardcoded cloud provider keys or pre-pinned model names. A fresh install should gracefully prompt the user in Settings / Onboarding to pick their preferred provider (Cloud API key, local Ollama, or LAN endpoint). *(Revised 2026-08-30: sysadmin variant — on `home`/`home-light` onboarding collects the Compute Peer address instead; see answer 3.)*

3. **Onboarding flow priority:**
   - Keep onboarding minimal and non-blocking. **Revised 2026-08-30 (S3):** role selection sets `variant`; the **Workstation Sysadmin** role opens the unified Model Picker, but **Home Hub / Light Client open the Compute Peer setting** (hostname:port or Tailscale address) with a Test Connection button — no model picker on HA variants; the workstation's picker governs. Defer elaborate multi-step onboarding wizards.

4. **Light hardware target:**
   - **Both N100/N150 and Raspberry Pi 4/5 (ARM64) are first-class targets**, alongside legacy Intel computers. All dependencies in the `[light]` group must be pure Python or have standard pre-compiled ARM64 / x86_64 wheels on PyPI.

5. **Tailscale & LAN Offload:**
   - Supported via configuration, but **revised 2026-08-30**: `deploy/README.md` must document that `home`/`home-light` variants configure **no `SOURCEPREP_URL`** (no SourcePrep at all — S2) and use the **Compute Peer** setting for model offload (S3) — `chat_model`/`specialist_model` resolve to `peer://<workstation>:8000`. Remote-endpoint URLs in `models.yml` (and remote SourcePrep) remain a sysadmin-variant topology. Note: this is not supported out-of-the-box yet — `peer` must first be registered in the model stack (handoff W14).

6. **Sentient Home UI priority:**
   - Keep UI modular. Implement the essential multi-instance and status indicators without hiding existing sysadmin or configuration controls. Full spatial ambient UI (AreaGrid, TemporalChronicle) remains in its dedicated post-Phase 8 workstream.

---

### Additional Concerns or Recommendations

1. **Pyproject.toml Base Dependency Cleanup:**
   - Ensure `chromadb` and `sentence-transformers` are completely removed from mandatory `project.dependencies` in `halbert_core/pyproject.toml` and moved to optional extras. This unblocks instant, lightweight installation on Raspberry Pi and low-spec machines.
   - **Revised 2026-08-30 (S5):** keep `sentence-transformers` out of halbert_core's `[light]` — HA-node memory embeddings are served by **haloysius's ONNX/Ollama `MemoryEmbedder`** (`haloysius[embeddings]` is the optional local-transformer upgrade; optionally a `[home]` extra = `[light]` + `[cognition]`). Never install `[rag-legacy]` (bundles chromadb) on HA nodes. Pending open decision D3 (which memory path the HA persona consumes).
2. **Advisory Lock Scope:**
   - In `model/client.py`, ensure `llm_advisory_lock()` continues to protect local GPU/CPU endpoints (`ollama`, `llamacpp`, `mlx`, `lm-studio`) from concurrent contention between Halbert and SourcePrep while allowing cloud endpoints to execute concurrently without locking.
3. **Graceful Fallbacks for Offline / Degraded State:**
   - If `chat_model` is configured to Cloud but the network is offline, surface a clean, actionable status banner in the UI rather than unhandled network timeout exceptions. If a local `secure_model` is available (sysadmin variant), the agent can still respond to local sysadmin queries or queue tasks; `home`/`home-light` variants fall back to template thoughts (revised 2026-08-30).

