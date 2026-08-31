# Handoff: README — Home Automation Pipeline (Standalone)

**To:** README / docs AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Ready to fold into `README.md`  
**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** peer compute is the recommended HA build; the home variant has no `secure_model`, no SourcePrep, and no model picker (a single "Compute Peer" setting instead). No LLM runs on the home node by default.

---

## 1. Goal

Add a **Home Automation** section to `README.md` that explains how to run Halbert as the conversation brain of a Home Assistant setup. This is the **standalone** path: one N150-class machine running both HA and Halbert.

---

## 2. Where it fits in README.md

Insert after `### Built for macOS and Linux` (or as a new top-level `## Home Automation` section after `## Capabilities`). Do not bury it under `Ecosystem Integrations`. It is a primary use case.

---

## 3. Suggested section: `## Home Automation`

### Lead paragraph

> Halbert can live *in* your home rather than just on your computer. Point it at a Home Assistant instance and it becomes a persistent home identity: it remembers what happened, notices unusual events, and can control lights, locks, climate, and media through natural voice or chat.

### 3.1 What it can do

- **Entity-aware chat:** "Turn off the living room lights." "Is the front door locked?" "Set the thermostat to 21."
- **Catch-up debriefs:** "Anything I should know?" Halbert summarizes recent events from memory.
- **Proactive alerts:** "The back gate has been open for 10 minutes." (governed by physical-safety rules)
- **Voice via Home Assistant:** Registers as a Wyoming conversation agent. Works with HA Voice PE, ESPHome satellites, and any Wyoming microphone.
- **Entity/area awareness:** Halbert reads live HA state and the area/entity registries directly — no documentation index required.
- **Frigate eyes (optional):** MQTT events from Frigate become episodic observations — "I saw someone at the front door at 2:15 PM."

### 3.2 Two shapes

1. **Peer-compute home server** (recommended — see `HANDOFF-README-PEER-COMPUTE.md`)
   - One low-power box (Intel N150, 16 GB RAM) runs Home Assistant + Halbert's home identity, voice, and persona memory
   - All LLM work is handled by a compute host (Mac Studio or Linux GPU box)
   - Best for: richer reasoning, larger models, lower power draw on the home box

2. **Standalone home server** (this handoff — no compute peer)
   - The same N150, running Home Assistant + Halbert with no paired compute host
   - With no peer, LLM responses fall back to template thoughts — no LLM runs on the home node
   - Best for: simple, self-contained, privacy-first smart home

> A standalone build that runs a local LLM on the home node is no longer the default. Local inference (2B–3B minimum, no 1B tier) is an optional fallback on hosts with 8 GB+ RAM, and home variants have no model picker to configure one — see 3.5 (`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Findings 3 and 4).

### 3.3 Quick start (standalone)

```bash
# 1. Install Home Assistant
#    Docker or HA Core on the same machine

# 2. Install Halbert home variant
pip install -e halbert_core/

# 3. Configure the home identity
export HALBERT_VARIANT=home
export HALBERT_PERSONA_ID=home
export HALBERT_SCENE_CONTEXT="smart home automation"
export HALBERT_DATA_DIR=/var/lib/halbert-home
export HA_URL=http://localhost:8123
export HA_TOKEN=your_long_lived_token

# 4. Start the daemon
halbert dashboard-serve --port 8001
```

> A `pip install halbert[home]` extra is planned as `[light]` + `[cognition]`. Its final contents are pending the packaging decision in `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (S5 / decision D3) — it must not pull in chromadb or torch.

### 3.4 Wyoming voice setup

```bash
# Start the voice server
export WYOMING_ENABLED=1
export WYOMING_PORT=10400
python -m halbert_core.integrations.wyoming_agent
```

In Home Assistant: **Settings → Voice Assistants → Add Agent → Wyoming**. Point it at `n150.tailnet.ts.net:10400` (or `localhost:10400`).

### 3.5 Optional local fallback model (8 GB+ hosts only)

Offload to a compute peer is preferred on every home node. A local model is a fallback for when the peer is asleep, and only on hosts with 8 GB+ RAM. Devices with 4 GB RAM or less require a compute peer — local inference is not supported on them. There is no 1B tier; 2B–3B is the minimum for local inference. Home variants have no model picker, so a local fallback is configured via the config wizard or `models.yml` directly, not a UI.

| Parameter class (Q4) | Size | Why |
|---|---|---|
| 4B | ~2.5 GB | Best tool-calling of the local fallback classes, critical for HA service calls |
| 3B | ~1.9 GB | Lighter fallback for 8 GB hosts |

Run via Ollama. Memory embeddings stay local on the home node — served by the bundled ONNX embedder or Ollama (`nomic-embed-text`) — they power persona memory, not RAG.

### 3.6 Physical safety

Halbert has a four-level governance policy for HA actions:

| Level | Examples | Rule |
|---|---|---|
| 0 | Lights, fans, media players | No confirmation |
| 1 | Climate, humidifier, covers | Low risk, logged |
| 2 | Locks, alarms, garage doors | Voice or PIN confirmation |
| 3 | Water valve, freezer, medical | Forbidden from autonomous control |

### 3.7 What you need

- A Home Assistant instance
- A long-lived access token
- A machine with 8–16 GB RAM (N150 recommended — the RAM is for Home Assistant, voice, and persona memory, not a local LLM)
- A compute peer for LLM work (or the optional local fallback model from 3.5 on 8 GB+ hosts) — devices with 4 GB RAM or less require a peer; local inference is not supported on them
- Optional: Frigate for camera events

---

## 4. Diagram to include

```
┌─────────────────────────────┐
│  N150 / Home Server         │
│  ├─ Home Assistant :8123    │
│  ├─ Halbert (home) :8001    │
│  └─ Wyoming :10400          │
└─────────────────────────────┘
           ↑
    iPad / voice satellite
```

---

## 5. Things not to claim

- Do not call it "federated" or "federalist" in the README body.
- This section is about the **one-box, no-peer build**. Peer compute is the recommended HA build and gets its own section (see `HANDOFF-README-PEER-COMPUTE.md`); this standalone section remains for the simpler setup without a compute host.
- Do not claim HACS integration is required — it is Phase 6 polish.
- Do not claim any local LLM runs on the home node by default — in the peer build all LLM work goes to the compute host, which runs 7B+ via Ollama/vLLM; with no peer, responses fall back to template thoughts. A local 3B/4B fallback is optional on 8 GB+ hosts only; there is no 1B tier.
