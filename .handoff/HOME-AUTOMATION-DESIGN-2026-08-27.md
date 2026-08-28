# Halbert Home Automation — Design Exploration

**Date:** 2026-08-27
**Status:** Blue-sky research

---

## 1. The Core Idea

A Halbert instance that identifies as **the home** rather than the computer. It interfaces with Home Assistant, manages the house as its "body", and runs on the HA server (N150 + Optane 375GB). The host computer's own Halbert identity stays dormant on the same machine. Shared backend infrastructure (Ollama, SourcePrep, ChromaDB) serves whichever instance is active.

Networked devices (iPad, Raspberry Pi) connect over Tailscale.

---

## 2. What's Already Multi-Instance-Friendly

| Component | Why |
|-----------|-----|
| Ollama | HTTP daemon :11434 — any client |
| SourcePrep | HTTP daemon :8400 — `SourcePrepRetrievalBackend` takes `base_url` |
| ChromaDB | Client/server mode |
| HalbertAppSeam | It's a **class** — instantiable. Global registry is the only blocker |
| Haloysius Protocols | All Protocol-based — no state |
| BeingConfig | File-based — just need per-instance paths |
| PersonaMemoryStore | Takes `persona_id` param — already supports multiple stores |

### Single-Instance Blockers

| Component | File | Blocker |
|-----------|------|---------|
| AppSeam registry | `haloysius/seam.py` | Global `_app_seam` |
| Cognition | `integrations/cognition_wiring.py` | Module-level `_cognition`, `_event_mapper`, `_trackers` |
| PersonaCognition | `cognition_wiring.py:33` | Hardcoded `persona_id="halbert"` |
| BeingConfig | `config/being_config.py` | Single `~/.config/halbert/being.yml` path |
| Dashboard | `dashboard/app.py` | Single FastAPI app, one agent assumed |

---

## 3. Three Deployment Patterns

### Pattern A: Terminal (Simplest)

iPad/Pi is a dumb terminal. Home identity lives on N150. Dashboard served over Tailscale. Zero code changes.

### Pattern B: Remote Instance (Pi has own identity)

Pi runs its own Halbert daemon with distinct identity, own memory, own being.yml. Points to N150's Ollama + SourcePrep over Tailscale. N150's host identity dormant.

### Pattern C: Single-Process Multi-Instance (User's "spawn" idea)

One Python process manages multiple Halbert identities via an InstanceManager. Default (host) identity dormant. Only the home identity runs cognition. Most resource-efficient, biggest code change.

---

## 4. Deep Dive: Pattern C (The User's Idea)

### Instance Manager

```python
@dataclass
class HalbertInstance:
    instance_id: str          # "host", "home", "workshop"
    being_config: BeingConfig
    cognition: PersonaCognition
    event_mapper: SystemEventMapper | None
    seam: HalbertAppSeam
    state: InstanceState       # ACTIVE | DORMANT | DISABLED
    memory_store: PersonaMemoryStore

class InstanceManager:
    instances: Dict[str, HalbertInstance]
    active_id: str | None
    def activate(self, instance_id: str) -> None
    def deactivate(self, instance_id: str) -> None
    def get_active(self) -> HalbertInstance | None
```

### What Changes

- **`cognition_wiring.py`**: Replace module-level singletons with per-instance factories. `get_cognition()` → `create_cognition(instance_id, being_config)`.
- **`app_seam.py`**: Skip global `register_app_seam()`, pass seam directly to cognition wiring.
- **`being_config.py`**: Add `instance_id` field, per-instance paths: `~/.config/halbert/instances/{id}/being.yml`.
- **`dashboard/app.py`**: Routes accept instance_id (path or header). Active instance is default.
- **`agents/`**: Agent constructed with instance context. `StateContext` carries `HalbertInstance` ref.

### The Dormant Default

The "host" instance: config exists, cognition created but `advance_turn` never called, no background scanning, tools unreachable from dashboard. Can be activated later.

---

## 5. Home Assistant Integration

New module: `integrations/home_assistant/`

| Component | Purpose |
|-----------|---------|
| `ha_client.py` | HTTP/WebSocket client for HA REST API + event stream |
| `ha_tools.py` | Tools: `turn_on`, `turn_off`, `set_temperature`, `lock_door` |
| `ha_event_mapper.py` | HA state changes → PersonaCognition events |
| `ha_state_trackers.py` | Track HA entity states as cognition state |
| `ha_discovery.py` | Discover HA entities → "home inventory" |
| `ha_governance.py` | Require approval for security-critical actions |

The home identity's "body" is the house: HA sensors replace `psutil`, HA services replace config file edits, water leak sensors replace disk failure alerts.

**Home being.yml:**
```yaml
instance_id: home
voice: first_person
purpose: "I am the home. I manage comfort, security, and energy."
ha_url: "http://localhost:8123"
archetype_id: caretaker
```

### Home-Facing Archetypes

| ID | Name | Big Five |
|----|------|----------|
| `caretaker` | The Caretaker | High A, high C, mid E |
| `butler` | The Butler | High C, low E, low N |
| `concierge` | The Concierge | High E, high O, high A |
| `guardian` | The Guardian | High C, low N, low A |

---

## 6. Tailscale Layer

- **Backend sharing**: Pi → `http://n100.tailnet:11434` (Ollama), `http://n100.tailnet:8400` (SourcePrep)
- **Dashboard**: iPad → `http://n100.tailnet:8000`
- **If Tailscale down**: Pi loses LLM → template thoughts fallback (Haloysius already does this). Cognition still runs. HA tools still work locally.

---

## 7. Resource Budget (N150)

| Component | RAM |
|-----------|-----|
| Ubuntu + HA | ~1GB |
| Ollama 7B Q4 | ~5GB |
| SourcePrep | ~200MB |
| ChromaDB | ~300MB |
| Halbert (1 instance) | ~200MB |
| **Total** | **~7GB** |

Optane 375GB is plenty. N150 with 16GB RAM is workable; 8GB needs a smaller model (3B/4B).

---

## 8. Minimal Viable Path

1. **Expose dashboard over Tailscale** — zero code change
2. **Create "home" being.yml** — different persona, just a config file
3. **Add HA read-only event mapper** — HA WebSocket → PersonaCognition events
4. **Add HA tools** — `turn_on`, `turn_off`, `set_temperature`
5. **Skip multi-instance for now** — run one instance with home identity. Add InstanceManager when there's a real need for two identities on one machine.

Gets 80% of the value with ~20% of the code changes.

---

## 9. Minimum Requirements Analysis

### 9.1 What Halbert Actually Needs to Run

The full Halbert stack has a lot of moving parts. Let's break down what's **required** vs **optional** for a home automation variant:

| Component | Required for HA? | Weight | Notes |
|-----------|-----------------|--------|-------|
| **Ollama (LLM daemon)** | YES | ~5GB RAM (7B Q4) | The brain. Without it, template thoughts only. |
| **Halbert daemon (Python)** | YES | ~200MB | The agent loop, cognition, tools. |
| **Haloysius (cognition)** | YES | included above | advance_turn, PersonaCognition, memory. |
| **sentence-transformers** | YES | ~90MB model | Memory embeddings (all-MiniLM-L6-v2). Runs on CPU. |
| **FastAPI dashboard** | YES | included above | How the user talks to it. |
| **Home Assistant** | YES | ~1GB | The "body" — what Halbert controls. |
| **SourcePrep daemon** | OPTIONAL | ~200MB | Awareness of house config tree. Skip for MVP. |
| **ChromaDB** | OPTIONAL | ~300MB | RAG corpus. Not needed if no SourcePrep. |
| **RAG scrapers (46 files)** | NOT NEEDED | — | Linux/macOS doc scraping. Irrelevant for HA. |
| **Config watcher/snapshot** | NOT NEEDED | — | `/etc` file monitoring. HA has its own config. |
| **Proactive scanner (psutil)** | NOT NEEDED | — | CPU/disk monitoring. HA sensors replace this. |
| **Polkit helpers** | NOT NEEDED | — | Privileged file ops. HA API doesn't need them. |
| **Terminal/PTY tools** | NOT NEEDED | — | Shell access. HA uses REST/WebSocket. |
| **Cron scheduler** | OPTIONAL | — | HA has its own automations. Maybe redundant. |
| **Autonomous executor** | OPTIONAL | — | Background tasks. HA automations may cover this. |

### 9.2 The Minimal Stack

```
N150 Server
  ├── Home Assistant           (~1GB RAM)
  ├── Ollama 7B Q4             (~5GB RAM)
  ├── Halbert daemon           (~300MB RAM)
  │   ├── Haloysius cognition  (advance_turn, memory, thoughts)
  │   ├── HA integration       (event mapper + tools)
  │   ├── FastAPI dashboard    (chat UI + API)
  │   └── sentence-transformers (memory embeddings, CPU)
  └── Tailscale                (remote access)

Total: ~6.5GB RAM, no SourcePrep, no ChromaDB, no RAG, no config watcher
```

This is genuinely lean. The "home" Halbert doesn't need to index Linux man pages or watch `/etc/fstab`. Its world is HA entities.

### 9.3 What's Overkill for HA

- **Entire `rag/` directory (46 files)**: Linux/macOS documentation scrapers. A home Halbert doesn't need Arch Wiki articles. If you want config awareness, SourcePrep indexing HA's YAML files is the right tool, not the RAG scrapers.
- **`config/` subsystem (watcher, snapshot, drift, edge_extractor)**: Monitors `/etc` files. HA has its own config management. The home Halbert reads HA state, not filesystem configs.
- **`discovery/` (43 files)**: Hardware discovery (CPU, disks, USB). A home Halbert discovers HA entities, not PCI devices.
- **`somatic/`**: PTY/terminal. No shell access needed for HA control.
- **`tools/system_tools.py`, `tools/config_editor.py`, `tools/write_config.py`**: Filesystem tools. Replaced by HA tools.
- **`proactive/` anomaly detection**: CPU/disk anomaly detection. HA sensors + automations cover this domain.

### 9.4 What You'd Actually Build New

The home Halbert is mostly **the same cognition engine with different tools and a different event source**:

| Existing (Sysadmin) | New (Home Automation) |
|---------------------|----------------------|
| `discovery/engine.py` (hardware scan) | `ha_discovery.py` (entity scan) |
| `tools/system_tools.py` (df, ps, etc.) | `ha_tools.py` (turn_on, set_temp, etc.) |
| `system_event_mapper.py` (psutil events) | `ha_event_mapper.py` (HA state changes) |
| `state_trackers.py` (CPU/disk trackers) | `ha_state_trackers.py` (room temp, occupancy) |
| Prompt: "I am the computer" | Prompt: "I am the home" |
| `rag/` (Linux docs corpus) | (none, or SourcePrep on HA YAMLs) |

The cognition loop, memory system, thought generation, prompt stack, dashboard, agent state machine — all shared infrastructure. The **only** new code is the HA integration module (~6 files) and the home-themed archetypes/personas.

---

## 10. Deployment Scenarios Reconsidered

### Scenario 1: Desktop Daemon Only (Simplest Real Target)

```
Desktop/N150 Server (always on)
  ├── HA + Ollama + Halbert (home identity)
  └── Tailscale for remote access

iPad / Phone / Any browser
  └── Web UI (dashboard served by the daemon)
```

**Minimum hardware**: Any always-on x86/ARM box with 8GB+ RAM. N150 is ideal. A Pi 5 (8GB) could even work with a 3B model.

**What you get**: A home identity you can chat with from any device. It knows your house state, can control entities, has memory of past conversations and events.

**What you don't get**: The iPad doesn't "identify as" anything — it's a window. No per-device personality.

**Code changes**: Just the HA integration module + home being.yml. No multi-instance refactoring.

### Scenario 2: Desktop Daemon + Pi Satellite

```
Desktop/N150 (always on)
  ├── HA + Ollama + Halbert (home identity)

Raspberry Pi (always on, in workshop)
  ├── Halbert daemon (workshop identity)
  ├── Own memory, own cognition
  └── Points to N150's Ollama over Tailscale
```

**Minimum hardware**: N150 (8GB+) + Pi 5 (4GB+). Pi runs Python + Haloysius + sentence-transformers but no LLM (remote Ollama).

**What you get**: The workshop Pi is its own being — "I am the workshop." It has its own memory, its own concerns (3D printer temp, dust collection, air quality). If Tailscale drops, it still thinks (template thoughts) and can control local HA entities.

**Code changes**: HA integration + being.yml per instance + the multi-instance refactoring (break singletons in cognition_wiring). OR: just run two separate Python processes with different config dirs — no refactoring needed, just two `being.yml` files and two `halbert dashboard-serve` on different ports.

### Scenario 3: Android Tablet Standalone (Future Market)

```
Android Tablet
  ├── Termux or Python-for-Android
  ├── Halbert daemon (lightweight)
  ├── HA integration (talks to HA on same network)
  └── Remote Ollama (desktop or cloud)
```

**The appeal**: No desktop required. The tablet IS the Halbert. You talk to it, it talks to HA.

**The problem**: Halbert is a Python/FastAPI app. Running on Android means either:
- **Termux**: Python runs, but it's a hack. No background daemon guarantee. Android kills background processes.
- **Kotlin/Compose rewrite of the client**: The tablet runs a native Android app that talks to a remote Halbert daemon. The daemon doesn't run on the tablet.
- **Tauri mobile**: Tauri is working on mobile. The dashboard frontend is already React. A Tauri mobile shell could wrap the web UI with native push notifications. But the daemon still runs elsewhere.

**Realistic path**: The tablet is a **client**, not a server. A native Android app (or Tauri mobile) that connects to a remote Halbert daemon. The "standalone" tablet is a UX goal, not an architecture goal — the brain lives on the server, the tablet is the face.

**Future market angle**: Sell the Android/iOS app as the interface. The daemon is self-hosted (like HA itself). The value proposition: "Your home has a personality. Talk to it."

### Scenario 4: Cloud-Hosted Daemon (SaaS Option)

```
Cloud VPS (1 vCPU, 4GB RAM)
  ├── Halbert daemon (home identity)
  └── Connects to HA via Nabu Casa / Cloudflare Tunnel

User devices
  └── Web UI or mobile app
```

**No desktop required at all.** The daemon runs in the cloud. HA connects through Nabu Casa (HA's cloud service) or a Cloudflare Tunnel. Ollama can be cloud-hosted too (e.g., RunPod, Modal) or use a managed API (OpenAI, Anthropic).

**Trade-off**: You lose the "self-hosted, local-first" ethos. But you gain zero-hardware setup. This could be the **onboarding path**: try Halbert Home in the cloud, migrate to self-hosted later.

---

## 11. The "Light Halbert" Concept

Instead of running the full Halbert stack, what if there's a **lightweight variant** that's just:

```
halbert-home/
  ├── cognition/        (Haloysius: advance_turn, memory, thoughts)
  ├── ha_integration/   (HA client, tools, event mapper, state trackers)
  ├── dashboard/        (FastAPI + React chat UI)
  ├── being.yml         (home identity config)
  └── requirements.txt  (haloysius, fastapi, uvicorn, aiohttp, sentence-transformers)
```

No RAG, no config watcher, no discovery engine, no PTY, no cron scheduler, no polkit, no 46 scrapers. Just the cognition core + HA integration + chat UI.

**Dependencies**: `haloysius`, `fastapi`, `uvicorn`, `aiohttp`, `sentence-transformers`, `pyyaml`. That's it. ~300MB installed + ~90MB model.

**This could be a separate package** (`halbert-home`) that depends on `haloysius` but not on `halbert-core`. Or a install profile: `pip install halbert[home]` vs `pip install halbert[sysadmin]`.

**The light variant runs on:**
- N150 (obviously)
- Pi 5 8GB (comfortably, with remote Ollama)
- Pi 5 4GB (tight but possible, sentence-transformers is the squeeze)
- Any cloud VPS with 2GB+ RAM (with remote Ollama)

---

## 12. Frigate + Voice Assistant — What Can We Really Offer?

### 12.1 The Competitive Landscape (What Already Exists)

There are already several HA LLM conversation agent integrations:

| Project | What It Does |
|---------|-------------|
| `hass-agent-llm` | OpenAI-compatible LLM, ChromaDB vector search, memory, tools, streaming for voice |
| `ai-conversation` | OpenAI-format LLM, STT/TTS, MCP server for HA |
| `home_assistant_llm_claude` | Claude/Groq, tool calling, fact learning, Music Assistant, streaming |
| `wyoming-letta` | Wyoming protocol conversation agent backed by Letta (stateful memory agent) |

These are **chatbots with tools**. They take a transcript, call HA APIs, return text. None of them have:

- A persistent cognitive identity ("I am the home")
- Long-term episodic memory with emotional scoring
- Thought generation between turns (the home *thinks* when you're not talking to it)
- Proactive initiation ("I noticed something at 2am")
- Personality (Big Five, archetypes, speech patterns)
- Self-awareness of camera/sensor events as experiences

### 12.2 The Unique Value Proposition

Halbert Home is not a chatbot bolted onto HA. It's a **cognitive entity that lives in the house**:

| Existing HA LLM Integrations | Halbert Home |
|------------------------------|-------------|
| Stateless or short-term session memory | Persistent episodic memory with decay, emotional scoring, consolidation |
| Reactive only (you ask, it answers) | Proactive (it notices, worries, initiates) |
| No identity — it's "the assistant" | Identity — "I am the home" with personality, archetypes, voice |
| No inter-turn cognition | `advance_turn` generates thoughts between conversations |
| Camera events = just another sensor | Camera events become *experiences* — "I saw someone at the back door last night" |
| No self-model | 3-layer self-model: objective state (HA sensors) + subjective experience (Haloysius cognition) + identity glue |

### 12.3 Voice Assistant Integration — Yes, This Is Possible

HA's voice pipeline is modular and Halbert plugs in cleanly:

```
Wake Word (openWakeWord / microWakeWord)
    ↓ Wyoming protocol
STT (faster-whisper / Whisper)
    ↓ transcript
Conversation Agent (Halbert)    ← Halbert registers here as a Wyoming conversation agent
    ↓ response text
TTS (Piper)
    ↓ audio
Speaker
```

**How it works technically:**

HA's Wyoming protocol is a simple TCP/JSONL protocol. A conversation agent server:
1. Listens on a TCP port
2. Receives `transcript` events from HA (text + conversation_id)
3. Processes the text through its brain
4. Returns `handled` events with response text

`wyoming-letta` is an existing precedent — it's a Wyoming server that forwards transcripts to a Letta agent and returns replies. Halbert would do the same but with Haloysius cognition instead of Letta.

**New module: `integrations/wyoming_agent.py`**

```python
class HalbertWyomingAgent:
    """Wyoming protocol conversation agent backed by Halbert cognition.

    Registers as a HA voice assistant conversation agent.
    Receives transcripts, runs them through the agent loop
    (with advance_turn, memory, personality), returns spoken responses.
    """
    # ~100 lines: TCP server, JSONL event handling, delegate to Halbert agent
```

**What the user experiences:**

- "Hey home, is the front door locked?" → Halbert checks HA, responds via voice
- "Did anything happen last night?" → Halbert recalls from memory + Frigate events
- "I'm going to bed" → Halbert arms the alarm, locks doors, dims lights, says goodnight in its personality
- The home *proactively speaks*: "I noticed the back gate is open — should I alert you?"

**The proactive voice angle is the killer feature.** No existing HA LLM integration does this. They're all reactive. Halbert can initiate because it has:
- Background event scanning (HA state changes, Frigate events)
- Cognition ticks between conversations (advance_turn generates thoughts/worries)
- Proactive interrupt infrastructure (already built in the dashboard)

### 12.4 Frigate Integration — The Home Has Eyes

Frigate is an NVR with AI object detection. It communicates via MQTT and integrates tightly with HA.

**Frigate publishes to MQTT:**

| Topic | What | Use for Halbert |
|-------|------|-----------------|
| `frigate/events` | Tracked object events (person, car, dog) with before/after states, zones, snapshots | Feed into PersonaCognition as *observations* |
| `frigate/reviews` | Review segments with severity (alert/detection) | Proactive alerts — "someone at the door" |
| `frigate/triggers` | Semantic search triggers | Future: "was there a red car yesterday?" |
| `frigate/stats` | System metrics (CPU, FPS, inference) | Health monitoring (optional) |

**How Frigate events flow into Halbert's cognition:**

```
Frigate camera detects person at front door
    ↓ MQTT frigate/events
HA event mapper receives event
    ↓ maps to PersonaCognition observation
PersonaCognition registers: "saw_person_at(front_door, 2:14am)"
    ↓ advance_turn processes observation
Thought generated: "It's unusual for someone to be at the front door at 2am"
    ↓ worry registered in cognition
Proactive alert triggered: "I saw someone at the front door at 2:14am. 
    The snapshot shows a figure in dark clothing. Should I review the clip?"
```

**The home doesn't just "know" a sensor triggered. It experienced something.**

The Frigate event includes:
- Object label (person, car, dog, package)
- Camera name (front_door, backyard, driveway)
- Zone (entry, yard, street)
- Snapshot URL (accessible via HA API)
- Clip URL (accessible via HA API)
- Timestamp
- Before/after zones (entered yard → approached door)

This is rich enough to generate natural-language observations in cognition:
- "A person approached the front door at 2:14am"
- "A package was delivered at 10:32am"
- "A car entered the driveway at 6:45pm" (recognized: partner's car?)

**New module: `integrations/frigate/`**

| File | Purpose |
|------|---------|
| `frigate_mqtt_client.py` | Subscribe to `frigate/events`, `frigate/reviews` MQTT topics |
| `frigate_event_mapper.py` | Map Frigate events → PersonaCognition observations |
| `frigate_tools.py` | Tools: `get_snapshot`, `get_clip`, `review_event`, `acknowledge_alert` |
| `frigate_state_tracker.py` | Track camera states in cognition (active detections per camera) |

### 12.5 What the Complete Offering Looks Like

**Halbert Home with Frigate + Voice:**

1. **Talk to your house by voice** — Wyoming protocol integration. "Hey home, good morning." The house responds with personality, tells you about overnight events, suggests actions.

2. **The house watches and remembers** — Frigate events feed into cognition. The house knows who came to the door, when the mail arrived, if a car was in the driveway overnight. It remembers these as experiences, not log entries.

3. **The house proactively alerts** — Not push notifications from HA. The house *speaks*: "I noticed the back gate is open." Or sends a message through the dashboard: "There was someone at the front door at 2am. I saved the clip. Want to see?"

4. **The house has personality** — It's not a generic assistant. It's *your* house. You chose the archetype (butler, caretaker, guardian). It has a consistent voice, remembers your preferences, knows your routines.

5. **The house thinks between conversations** — `advance_turn` runs on HA state changes and Frigate events. The house forms worries, observations, and thoughts even when nobody is talking to it. When you next interact, it has things to tell you.

6. **The house has memory** — Long-term episodic memory. "Last Tuesday you said the bedroom was cold at night — should I adjust the schedule?" No existing HA LLM integration has this.

7. **The house can act** — HA tools (turn_on, set_temperature, lock_door, run_automation) with governance. Safety-critical actions require approval. The house won't unlock the front door at 3am without asking.

### 12.6 What This Requires (Revised Stack)

```
N150 Server
  ├── Home Assistant           (~1GB)
  ├── Frigate                  (~2GB with Coral/GPU, ~1GB CPU-only)
  ├── Ollama 7B Q4             (~5GB)  [or 3B for N150: ~2.5GB]
  ├── Halbert daemon           (~300MB)
  │   ├── Haloysius cognition
  │   ├── HA integration (event mapper + tools)
  │   ├── Frigate integration (MQTT → cognition)
  │   ├── Wyoming agent (voice conversation agent)
  │   ├── FastAPI dashboard
  │   └── sentence-transformers
  ├── Wyoming STT (Whisper)    (~500MB)
  ├── Wyoming TTS (Piper)      (~200MB)
  └── Tailscale

Total: ~9-10GB RAM with 7B, ~6.5GB with 3B
```

The voice pipeline adds ~700MB (Whisper + Piper). Frigate adds ~1-2GB. This pushes the N150 toward 16GB territory, but a 3B model brings it back to ~6.5GB total.

### 12.7 What Nobody Else Has

The combination that no existing HA integration offers:

| Feature | hass-agent-llm | ai-conversation | wyoming-letta | **Halbert Home** |
|---------|----------------|-----------------|---------------|-----------------|
| LLM tool calling | Yes | Yes | Yes | Yes |
| HA entity control | Yes | Yes | Yes | Yes |
| Voice (Wyoming) | Yes | Yes | Yes | Yes |
| Streaming responses | Yes | Yes | Yes | Yes |
| Persistent memory | Short-term | No | Letta memory | **Episodic + emotional + decay** |
| Cognitive identity | No | No | Agent persona | **"I am the home" + Big Five** |
| Inter-turn thoughts | No | No | No | **advance_turn** |
| Proactive initiation | No | No | No | **Yes (Frigate/HA events → cognition → alert)** |
| Camera awareness | No | No | No | **Frigate events as experiences** |
| Personality | No | No | No | **Archetypes, speech patterns, tone** |
| Self-model | No | No | No | **3-layer (objective + subjective + identity)** |

The moat is **cognition, not chat**. Anyone can wire an LLM to HA APIs. Nobody else has a house that *thinks about what it saw*.

---

---

## 13. Integration Architecture Research

### 13.1 Two Paths: Standalone Daemon vs HA Custom Integration

Research reveals two distinct integration patterns, each with real trade-offs:

**Path A: Standalone Daemon (Current Plan)**

Halbert runs as its own process, talks to HA via REST API + WebSocket. The Home panel is part of Halbert's own dashboard.

- Pros: Full control, no HA version coupling, can run on a different machine, keeps Haloysius cognition intact
- Cons: User must install and manage a separate service. Not HACS-installable. HA power users expect HACS.

**Path B: HA Custom Integration (HACS)**

Halbert ships as a `custom_components/halbert/` package installable via HACS. It registers as:
1. A **conversation agent** (selectable in Voice Assistant pipelines)
2. An **LLM tool provider** (via the `llm.py` platform — `async_get_tools` hook)
3. Optionally, entity platforms (sensors for cognition state, memory, etc.)

HA's LLM tool platform (ADR #1412, merged in HA 2025.x) lets any integration contribute tools to the Assist API via a `llm.py` platform file:

```python
# custom_components/halbert/llm.py
@callback
def async_get_tools(hass, llm_context, api_id) -> LLMTools | None:
    return LLMTools(
        tools=[HalbertRecallTool(), HalbertObserveTool()],
        prompt="Halbert provides home awareness and memory tools."
    )
```

This is the **officially sanctioned way** for integrations to expose capabilities to LLMs in HA. The tools live in the integration's code, are evaluated per-request, and can opt out based on `api_id`.

- Pros: HACS-installable, appears in HA's native UI, integrates with HA's voice pipeline natively, power users know this pattern
- Cons: Must run inside HA's Python process (or as an add-on), coupled to HA's version schedule, Haloysius cognition must coexist with HA's asyncio loop, `BeingConfig` must be stored as a HA config entry

**Path C: Hybrid (Best of Both)**

Halbert runs as a standalone daemon (Path A) but also ships a **thin HA custom integration** (Path B) that:
1. Registers as a conversation agent that forwards transcripts to the Halbert daemon
2. Registers as an LLM tool provider that proxies tool calls to the Halbert daemon
3. The HA integration is ~200 lines of glue — all cognition stays in the daemon

This is the pattern `wyoming-letta` and `hermes-ha-integration` use: a thin HA integration that bridges to an external agent. The daemon does the heavy lifting; the integration is just a protocol adapter.

**Recommendation: Path C.** The standalone daemon is the brain. The HA custom integration is the bridge. Power users install via HACS, the integration appears in their voice pipeline settings, but all cognition/memory/personality runs in the Halbert daemon which they can also access via its own dashboard.

### 13.2 HA WebSocket API — Event Subscription

HA's WebSocket API provides real-time event subscription. This is how Halbert's event mapper will work:

```
1. Connect to ws://{ha_url}/api/websocket
2. Send: {"type": "auth", "access_token": "{token}"}
3. Send: {"id": 1, "type": "subscribe_events", "event_type": "state_changed"}
4. Receive: {"id": 1, "type": "result", "success": true}  (subscription active)
5. Receive: {"id": 1, "type": "event", "event": {
       "event_type": "state_changed",
       "data": {
           "entity_id": "light.living_room",
           "new_state": {"state": "on", "attributes": {...}},
           "old_state": {"state": "off", "attributes": {...}}
       },
       "time_fired": "2026-08-27T20:00:00+00:00"
   }}
```

Key event types to subscribe to:
- `state_changed` — entity state changes (lights, sensors, locks, climate)
- `automation_triggered` — when an HA automation fires
- `zone_entered` / `zone_left` — person/vehicle zone transitions
- `assist_satellite` — voice assistant events (if using HA voice)

The WebSocket connection auto-reconnects (HA's JS websocket library handles this; we'll need to implement reconnection in Python with `aiohttp`).

### 13.3 HA Conversation Agent Registration

To register as a conversation agent in HA, a custom integration provides a `conversation.py` platform file:

```python
# custom_components/halbert/conversation.py
class HalbertConversationAgent(ConversationAgent):
    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        # Forward to Halbert daemon via HTTP
        response = await self._halbert_client.chat(
            text=user_input.text,
            conversation_id=user_input.conversation_id,
            language=user_input.language,
        )
        return ConversationResult(
            response=response.text,
            conversation_id=user_input.conversation_id,
        )
```

The agent then appears in **Settings → Voice Assistants** as a selectable conversation agent. Users pick "Halbert" as their agent, and HA's voice pipeline routes transcripts through it.

Existing precedents: `hermes-ha-integration`, `home_assistant_llm_claude`, `hass-agent-llm`, `ai-conversation` — all use this pattern.

### 13.4 HA LLM Tool Platform — Contributing Tools

HA's LLM tool platform (ADR #1412) lets integrations contribute tools to the Assist API. This is separate from being a conversation agent — it's about exposing capabilities that *any* LLM conversation agent can call.

For Halbert, the interesting tools to contribute:
- `RecallMemory` — "What did I tell you about the bedroom temperature last week?"
- `GetHomeState` — "What's the current state of all sensors in the house?"
- `GetRecentEvents` — "What happened in the house while I was asleep?"
- `ReviewCameraEvent` — "Show me the Frigate clip from 2am" (Phase 4)

These tools would be available to *any* HA conversation agent, not just Halbert's own. This means a user could use HA's built-in LLM agent but still access Halbert's memory and awareness.

### 13.5 Power User Hardware Landscape

Research confirms the target audience and their hardware:

| Setup | Hardware | HA Runs As | Ollama | Halbert Fits? |
|-------|----------|------------|--------|---------------|
| **N150 Mini PC** | N150, 16GB RAM, 500GB SSD | HA OS in Proxmox VM or Docker | Same machine, 3B model | Yes — primary target |
| **N150 + NAS** | N150 + TrueNAS/SnapRAID | HA in VM, NAS in another VM | Same machine | Yes — SourcePrep can index NAS configs |
| **Proxmox Cluster** | 3x N150 mini PCs | HA OS VM with HA failover | Dedicated inference VM | Yes — Halbert in its own VM/CT |
| **Pi 5 8GB** | Pi 5, 8GB RAM | HA OS on SD/SSD | Remote Ollama (Tailscale) | Yes — light variant |
| **Synology NAS** | DS223j/DS923+ | HA in Docker container | Remote or NAS-side | Yes — daemon in same Docker network |
| **Desktop PC** | Any gaming/work PC | HA in Docker | Same machine | Yes — but PC must be always-on |

**Key insight:** The N150 mini PC is the sweet spot. 6W idle, 16GB RAM, Proxmox for snapshots. Power users are already running this exact setup in 2026. HA in a VM, Ollama in another VM or LXC, Halbert as a third service. Total power budget: ~15-20W.

The Proxmox angle is important: power users run **multiple VMs/LXCs** on one N150. Halbert doesn't need to be a HA add-on — it can be its own LXC container that talks to HA over the local network. This is actually cleaner than running inside HA's process.

---

## 14. Roadmap (Revised Post-Review)

### Phase 1: Home Panel + HA REST Client + Minimal Service Call

**Goal:** Halbert dashboard has a Home panel that connects to HA, shows entity state, and lets the chat call services.

**Prerequisite:** Parameterize `cognition_wiring.py` — env var driven `persona_id`, `scene_context`, `data_dir`. ~10 line change, no architectural refactor. The home process sets `HALBERT_PERSONA_ID=home`, `HALBERT_SCENE_CONTEXT=smart home automation`, `HALBERT_DATA_DIR=~/.local/share/halbert-home`.

- `integrations/home_assistant/ha_client.py` — REST API client (aiohttp)
- `integrations/home_assistant/ha_config.py` — connection config dataclass
- `dashboard/routes/home.py` — API routes (status, entities, service call, areas, archetypes, config)
- `dashboard/frontend/src/pages/Home.tsx` — Home panel UI
- `dashboard/frontend/src/components/HomeConnectionForm.tsx` — HA connection setup
- `dashboard/frontend/src/components/EntityList.tsx` — Entity browser by domain/area
- `persona/home_archetypes.py` — 4 home archetypes (Steward, Companion, Guardian, Concierge)
- **Add `@app.get("/home")` to `app.py` SPA routes** (critical — without this, direct nav/refresh 404s)
- **Add `{ name: 'Home', href: '/home', icon: Home }` to `Layout.tsx`** navigation
- **Add `<Route path="/home" element={<Home />} />` to `App.tsx`**
- Minimal `ha_call_service` tool so chat can control devices (tactile feedback in Phase 1)
- No event stream, no cognition wiring, no voice, no Frigate

**Deliverable:** User can configure HA connection, browse entities by domain/area, chat with the home identity, and turn devices on/off through chat.

### Phase 2: HA Event Stream (Filtered) → Cognition

**Goal:** The home identity is aware of the house in real-time.

- `integrations/home_assistant/ha_event_stream.py` — WebSocket client with **domain filtering** and **telemetry debouncing** (do NOT pipe raw `state_changed` into cognition — filter to meaningful domains: `climate`, `lock`, `alarm_control_panel`, `binary_sensor`, `person`, `device_tracker`)
- `integrations/home_assistant/ha_state_hydration.py` — On startup/reconnect, `GET /api/states` to hydrate initial state before processing deltas
- `integrations/home_assistant/ha_history_backfill.py` — Query `GET /api/history/period/<timestamp>` for last 7-14 days on first boot. Feed significant events into PersonaCognition as pre-existing observations. Makes Halbert feel like it has known the house from minute one.
- `integrations/home_assistant/ha_event_mapper.py` — Map filtered HA events → PersonaCognition observations
- `integrations/home_assistant/ha_state_trackers.py` — Track entity states as cognition state (room temps, occupancy, door locks)
- `integrations/home_assistant/ha_tools.py` — Tools: `turn_on`, `turn_off`, `set_temperature`, `lock_door`, `call_service`
- `integrations/home_assistant/ha_governance.py` — 4-level governance policy (Level 0: no confirm, Level 1: low risk, Level 2: voice/pin confirm, Level 3: forbidden from autonomous control)
- Background asyncio task in the dashboard for the WebSocket event loop with exponential backoff auto-reconnect

**Deliverable:** The home Halbert knows when lights turn on, doors open, temperature changes. It forms observations and can be asked "what happened last night?" and recall from memory. On first boot, it has 7-14 days of historical context.

### Phase 3: SourcePrep for HA Configs

**Goal:** The home Halbert has deep knowledge of the house configuration. Moved up from Phase 6 — config awareness amplifies Phase 2's event awareness.

- Register the HA config directory (`/config` in HA OS, or the mounted config path) as a SourcePrep project
- Index `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, entity configs, integration configs
- The home Halbert can reason about the house config tree: "Why is the living room light automation triggering twice?" → SourcePrep retrieves the automation YAML, Halbert analyzes it
- No Halbert refactoring needed — SourcePrep is already a separate daemon, just add another project
- `SourcePrepRetrievalBackend` already takes `project_id` and `base_url` params
- **Limitation:** Single project only. Home instance uses `ha-config`; host instance uses `halbert-host`. A `CompositeRetrievalBackend` for multi-project search is a future enhancement.

**Deliverable:** The home Halbert understands the house's configuration, not just its current state. It can answer questions about automations, suggest config improvements, and reason about entity relationships. Combined with Phase 2's event stream, it can detect automation conflicts ("Motion Timeout turned off the light 12 seconds after Movie Mode set it to 20%").

### Phase 4: Voice via Wyoming Agent

**Goal:** "Hey home, good morning" — talk to the house by voice. No HACS dependency required.

- `integrations/wyoming_agent.py` — Wyoming protocol TCP server (JSONL over TCP)
- Receives `transcript` events, delegates to Halbert agent loop
- Returns `response` events with reply text
- Works with HA's voice pipeline (Whisper STT + Piper TTS) — add as Wyoming protocol integration in HA Settings → Voice Assistants
- **Spatial scoping:** HA passes `context.area_id` from the satellite device. Tool resolution filters entities by area when user says "turn on the light" without specifying a room.
- **Proactive voice:** Halbert can call HA's `tts.speak` service for critical alerts. But:
  - Only for Level 2+ security events
  - Only to the room where the target user is detected (area-tethered, via mmWave or BLE beacon)
  - Suppressed when `input_boolean.guest_mode` or `input_boolean.sleeping` is active

**Deliverable:** User talks to the house via HA voice satellite (ESP32 + ReSpeaker, or HA Voice PE). The house responds with personality. Proactive alerts for security events only, area-tethered, suppressed by guest/sleep modes.

### Phase 5: Frigate Integration

**Goal:** The home has eyes. Camera events become cognitive experiences.

- `integrations/frigate/frigate_mqtt_client.py` — MQTT subscriber for `frigate/events`, `frigate/reviews`
- `integrations/frigate/frigate_event_mapper.py` — Map Frigate events → PersonaCognition observations
- `integrations/frigate/frigate_tools.py` — `get_snapshot`, `get_clip`, `review_event`, `acknowledge_alert`
- `integrations/frigate/frigate_state_tracker.py` — Track camera states in cognition

**Deliverable:** "Did anything happen last night?" → Halbert recalls Frigate events from memory. "Show me the clip from 2am" → Halbert fetches the Frigate clip URL. Proactive: "I saw someone at the back door at 2:14am."

### Phase 6: HA Custom Integration (HACS Bridge)

**Goal:** Halbert is installable via HACS and appears in HA's native UI. This is a polish layer — voice and cognition already work without it.

- `custom_components/halbert/__init__.py` — thin integration that connects to the Halbert daemon
- `custom_components/halbert/conversation.py` — conversation agent that forwards to daemon
- `custom_components/halbert/llm.py` — LLM tool provider exposing Halbert's memory/awareness tools to HA's Assist API
- `custom_components/halbert/manifest.json` — HACS metadata
- `custom_components/halbert/config_flow.py` — UI setup (daemon URL, port)
- `custom_components/halbert/sensor.py` — cognition state sensors (thoughts, worries, memory count)

**Deliverable:** Power users install via HACS, select "Halbert" as their voice assistant conversation agent, and Halbert's tools appear in HA's Assist API. The daemon does all cognition; the integration is ~200 lines of glue.

### Phase 7: Multi-Instance (If Needed)

**Goal:** Multiple Halbert identities on one machine (home + host).

- **Two-process approach (preferred):** Run two daemon processes on different ports with different env vars (`HALBERT_PERSONA_ID`, `HALBERT_DATA_DIR`, `HALBERT_SCENE_CONTEXT`). Zero refactoring beyond the Phase 1 `cognition_wiring.py` parameterization.
- `InstanceManager` (only if needed later): manages multiple `HalbertInstance` objects in one process. Requires refactoring module-level singletons into per-instance factories.

**Deliverable:** The user can talk to both "the home" and "the computer" on the same N150, each with its own identity, memory, and personality.

### Phase 8: Light Variant Packaging

**Goal:** `pip install halbert[home]` installs only what's needed for HA.

- Separate install profile or package
- Dependencies: `haloysius`, `fastapi`, `uvicorn`, `aiohttp`, `pyyaml` (no sentence-transformers if using Ollama embeddings)
- **Offload embeddings to Ollama** (`/api/embeddings` with `nomic-embed-text` or `all-minilm`) — removes PyTorch ~500MB from the process
- No RAG scrapers, no config watcher, no discovery engine, no PTY
- Runs on Pi 5 4GB with remote Ollama
- Docker image: `halbert/halbert-home:latest`
- Default model: Llama 3.2 3B or Qwen 2.5 3B (sub-1.5s voice latency on N150)

**Deliverable:** A lean package that runs on low-power hardware. The "full" Halbert and the "home" Halbert share the same codebase, just different entry points and dependency sets.

---

## 15. SourcePrep for Home Automation — Why It's Not Overkill

The user's point about SourcePrep for power users is well-taken. Here's why:

**Power users already have complex HA configs:**
- `configuration.yaml` with includes (`!include`, `!secret`)
- `automations.yaml` with dozens/hundreds of automations
- `scripts.yaml`, `scenes.yaml`, `blueprints/`
- Integration-specific configs (Zigbee2MQTT, Frigate, MQTT, Node-RED)
- Custom components in `custom_components/`
- HACS configurations

**SourcePrep indexes this tree and gives the home Halbert:**
1. **Config awareness** — "Your living room automation has a condition that checks `input_boolean.guest_mode` — is that intentional?"
2. **Dependency tracing** — "This sensor is used by 3 automations and 2 dashboards. Changing it will affect all of them."
3. **Change history** — "You changed the thermostat schedule last Tuesday. The bedroom has been colder at night since then."
4. **Natural language config search** — "Show me all automations that touch the front door lock"

**No Halbert refactoring needed for single-project usage.** SourcePrep is already a daemon. Just:
1. Point SourcePrep at the HA config directory (mounted volume, or over network)
2. Register it as a project: `sourceprep project add --name ha-config --path /config`
3. Wire `SourcePrepRetrievalBackend` with the new project_id in the home instance's `wire_halbert_seam()` call

The `SourcePrepRetrievalBackend` already accepts `project_id` and `base_url`. It's a config change, not a code change.

**Limitation (verified post-review):** `SourcePrepRetrievalBackend` supports only **one project at a time**. The home instance can search `ha-config` OR `halbert-host`, but not both simultaneously. A future `CompositeRetrievalBackend` that queries multiple projects and merges results via reciprocal rank fusion would enable full homelab awareness. For now, the home instance uses `ha-config`; the host instance uses `halbert-host`. If a user runs both instances (two-process approach), each has its own retrieval scope.

**For the NAS user:** A `CompositeRetrievalBackend` (future enhancement) would let the home Halbert index TrueNAS/SnapRAID configs, Docker compose files, and Proxmox VM configs alongside HA configs — full infrastructure awareness. This is the "power user" value proposition: the home Halbert understands your whole homelab, not just your lights.

---

## 16. Open Questions (Revised)

1. **Identity boundary** — Does the home Halbert also manage the computer/NAS it runs on, or purely HA entities? (Answer emerging: power users want both — HA entities + infrastructure awareness via SourcePrep)
2. **HA governance** — Which HA actions need approval? (Unlock door = yes, turn on lamp = no)
3. **Multi-instance now or later?** — Phase 7. Two-process approach may suffice indefinitely.
4. **Light variant as separate package?** — Phase 8. Install profile vs separate package.
5. **Android target** — PWA is the zero-effort path. Native app is future market.
6. **Cloud option** — SaaS onboarding path. Lower priority than self-hosted.
7. **Model size** — Llama 3.2 3B for N150. 7B if 16GB RAM and nothing else heavy.
8. **SourcePrep for HA configs** — Phase 6. No refactoring, just add a project. High value for power users.
9. **Two processes vs InstanceManager** — Two processes on different ports is the pragmatic answer. InstanceManager is elegant but unnecessary until there's a real concurrency requirement.
10. **Voice priority** — Phase 4. Text-first is correct for MVP. Voice is the "talk to your house" magic that differentiates.
11. **Frigate as first-class or optional?** — Phase 5. Optional plugin, not core. Not every user has cameras.
12. **Proactive voice aggressiveness** — Security-critical via TTS, everything else via dashboard notification. User-configurable threshold.
13. **HA custom integration vs standalone** — Path C (hybrid). Standalone daemon + thin HACS bridge. Phase 3.
14. **Market positioning** — HA power users who already run Ollama, Frigate, Proxmox. They'll appreciate the cognition layer. Not for casual smart bulb users.
15. **HA WebSocket vs MQTT for events** — WebSocket for HA state changes (richer data, no broker needed). MQTT only for Frigate (Phase 5). Don't require an MQTT broker for the MVP.
16. **Proxmox/LXC packaging** — Should we ship a Proxmox LXC template for Halbert? Power users run Proxmox. A one-script install into an LXC container would be compelling.
