# Handoff: README — Home Automation Pipeline (Standalone)

**To:** README / docs AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Ready to fold into `README.md`  

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
- **Config awareness (optional):** SourcePrep indexes Home Assistant YAML so Halbert can answer *why* an automation fired.
- **Frigate eyes (optional):** MQTT events from Frigate become episodic observations — "I saw someone at the front door at 2:15 PM."

### 3.2 Two shapes

1. **Standalone home server** (this handoff)
   - One low-power box (Intel N150, 16 GB RAM)
   - Runs Home Assistant + Halbert + a 3B/4B local model
   - Best for: simple, self-contained, privacy-first smart home

2. **Peer-compute home server** (next handoff)
   - The same N150, but heavy LLM inference is handled by a Mac Studio or Linux GPU box
   - Best for: richer reasoning, larger models, lower power draw on the home box

### 3.3 Quick start (standalone)

```bash
# 1. Install Home Assistant
#    Docker or HA Core on the same machine

# 2. Install Halbert home variant
pip install -e halbert_core/   # or `pip install halbert[home]` when packaged

# 3. Configure the home identity
export HALBERT_PERSONA_ID=home
export HALBERT_SCENE_CONTEXT="smart home automation"
export HALBERT_DATA_DIR=/var/lib/halbert-home
export HA_URL=http://localhost:8123
export HA_TOKEN=your_long_lived_token

# 4. Start the daemon
halbert dashboard-serve --port 8001
```

### 3.4 Wyoming voice setup

```bash
# Start the voice server
export WYOMING_ENABLED=1
export WYOMING_PORT=10400
python -m halbert_core.integrations.wyoming_agent
```

In Home Assistant: **Settings → Voice Assistants → Add Agent → Wyoming**. Point it at `n150.tailnet.ts.net:10400` (or `localhost:10400`).

### 3.5 Recommended model for standalone

| Model | Size | Why |
|---|---|---|
| Qwen 3.5 4B (Q4) | ~2.5 GB | Best tool-calling in the 4B class, critical for HA service calls |
| SmolLM3 3B (Q4) | ~1.9 GB | Lighter, good for Pi 5 / very constrained N150 |

Run via Ollama. Sentence-transformers can be replaced with Ollama embeddings to save ~500 MB.

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
- A machine with 8–16 GB RAM (N150 recommended)
- Optional: Frigate for camera events
- Optional: SourcePrep for HA YAML awareness

---

## 4. Diagram to include

```
┌─────────────────────────────┐
│  N150 / Home Server         │
│  ├─ Home Assistant :8123    │
│  ├─ Halbert (home) :8001    │
│  ├─ Ollama 4B :11434        │
│  └─ Wyoming :10400          │
└─────────────────────────────┘
           ↑
    iPad / voice satellite
```

---

## 5. Things not to claim

- Do not call it "federated" or "federalist" in the README body.
- This section is about **one machine running everything**. The peer-compute build is a separate, optional section.
- Do not claim HACS integration is required — it is Phase 6 polish.
- Do not claim local 7B is the default — 4B/3B for standalone, 7B+ for peer-compute.
