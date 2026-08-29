# Sentient Home — Technical Gap Analysis & Remediation Roadmap

**Date:** 2026-08-29  
**Status:** Architectural Gap Audit & Implementation Plan  
**Target:** Halbert Ambient Intelligence Engine  

---

## Executive Summary

The foundational subsystems of Halbert — cognitive processing (`PersonaCognition`), agent state machine, intake complexity routing, local CV inference, and the Frigate NVR subsystem — are now built and passing all test suites.

However, bridging the gap between a **collection of functional backend modules** and a **seamless, ambient Sentient Home** requires closing six specific architectural and workflow gaps. Crucially, **Halbert is the cognitive and orchestration layer**, not a dashboard replacement; we deliberately avoid reinventing the wheel by leveraging Home Assistant's Area Registry, Bermuda BLE presence tracking, and Frigate Lovelace cards.

---

## 1. The Six Core Technical Gaps

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               SENTIENT HOME GAP MATRIX                                 │
├───────────────────────────────┬─────────────────────────────────┬──────────────────────┤
│ DOMAIN                        │ CURRENT STATE                   │ REQUIRED TARGET      │
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 1. Identity & Multi-Instance  │ Module singletons; 1 persona    │ Clean "Host" vs "Home"│
│                               │ hardcoded ("halbert")           │ instance isolation   │
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 2. Spatial Entity-Camera Fusion  │ HA areas and Frigate camera  │ Auto-import HA Areas │
│                               │ zones exist in separate silos   │ & map Frigate zones  │
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 3. Semantic Visual Memory     │ 7-day disk cache of JPEGs       │ Dense VLM summaries  │
│                               │ with MD5 dedup (no search)      │ indexed in FTS5/Vec  │
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 4. Voice Duplex Pipeline      │ REST/SSE streaming endpoints;   │ Full-duplex WebSocket│
│                               │ no direct audio streaming       │ VAD + Whisper + Piper│
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 5. Ambient Sentient UI        │ Chat composer, Settings, Alerts │ Auto Area Grid +     │
│                               │ (desktop dashboard style)       │ Chronicle & Embeds   │
├───────────────────────────────┼─────────────────────────────────┼──────────────────────┤
│ 6. Physical Action Safety     │ Shell command safety levels     │ Physical Home Safety │
│                               │ (SAFE/LOW/MED/HIGH/CRIT)        │ Policy & Backstops   │
└───────────────────────────────┴─────────────────────────────────┴──────────────────────┘
```

---

## 2. Detailed Gap Analysis & Remediation

---

### Gap 1: Identity & Multi-Instance Architecture

#### The Problem:
`halbert_core/integrations/cognition_wiring.py` maintains global module singletons (`_cognition`, `_event_mapper`, `_trackers`) initialized with hardcoded `persona_id="halbert"`. `BeingConfig` reads exclusively from `~/.config/halbert/being.yml`. When running on a server that acts both as the physical home controller and a Linux sysadmin host, the "Home" persona needs to operate independently from the "Host Sysadmin" persona.

#### Remediation Plan:
1. **Per-Instance Configuration Directory:**
   - Establish `~/.config/halbert/instances/<instance_id>/being.yml`.
   - Update `load_being_config(instance_id: Optional[str] = None)` to load instance-scoped configs.
2. **Instance Registry in `cognition_wiring.py`:**
   - Replace module-level singletons with an `InstanceRegistry` mapping `instance_id -> (PersonaCognition, CompositeEventMapper)`.
3. **HTTP / WebSocket Routing Context:**
   - FastAPI request middleware extracts `X-Halbert-Instance` header (defaulting to `"home"` for IoT endpoints, `"host"` for sysadmin tools).

---

### Gap 2: Spatial Entity-Camera Fusion (Leveraging Existing HA Tools)

#### The Problem:
Home Assistant already has an **Area Registry** (`/api/config/area_registry/list`) and device mappings. Frigate organizes video streams by `camera_name` and `zones`. Currently, there is no cross-domain link connecting Frigate camera zones to HA Areas.

#### Remediation Plan (No Reinventing the Wheel):
1. **Auto-Import HA Area Registry:**
   - On startup / connection, Halbert calls `/api/config/area_registry/list` and `/api/config/entity_registry/list`.
   - Constructs an in-memory `SpatialTopology` mapping `Area -> [Entity IDs, Device IDs]`.
2. **Zone Mapping via Settings Dropdown:**
   - In `Settings > Home & Space`, users simply select which HA Area corresponds to each Frigate camera zone (e.g. `front_porch` camera zone $\rightarrow$ `Front Porch` Area).
3. **Room Presence Ingestion:**
   - Subscribes to Bermuda BLE / ESPresense sensors (`sensor.bermuda_user_room`) to track user room location for spatial pronoun resolution (*"Turn off the lights in here"*).

---

### Gap 3: Semantic Visual Memory & Queryable Omniscience

#### The Problem:
`VisionCache` stores snapshot JPEGs on disk with rolling 7-day TTL and MD5 deduplication. However, when a user asks *"Where did I leave my soldering iron?"* or *"When did the dog go into the backyard?"*, Halbert cannot search inside historical image frames.

#### Remediation Plan:
1. **Event Keyframe Captioning Pipeline:**
   - When Frigate emits a high-confidence review event or object detection, extract the keyframe snapshot.
   - Run a lightweight on-prem scene captioner (via local Ollama with `moondream:latest` or `qwen2.5-vl:3b` / MobileCLIP).
   - Generate a structured semantic scene descriptor (timestamp, zone_id, objects, dense description).
2. **Episodic SQLite FTS5 Indexing:**
   - Store the scene description and object tags in `PersonaMemoryStore` under `MemoryType.EPISODIC`.
   - Add tool `query_visual_episodes(query: str, time_window: Optional[str])` allowing the agent to perform natural-language lookups over visual home history.

---

### Gap 4: Voice Duplex Audio Pipeline (Whisper + Piper)

#### The Problem:
The current dashboard communicates over HTTP REST and Server-Sent Events (SSE) text streams. Real-time voice interaction requires continuous streaming audio with voice activity detection (VAD), wake-word listening, and barge-in (interruption handling).

#### Remediation Plan:
Create `halbert_core/voice/`:
```
halbert_core/voice/
├── __init__.py
├── audio_server.py      # WebSocket server accepting 16kHz 16-bit PCM
├── vad_stream.py        # Silero VAD frame classifier (speech start/end detection)
├── whisper_engine.py    # faster-whisper local streaming STT
├── piper_engine.py      # Piper TTS streaming audio chunk generator
└── wake_word.py         # OpenWakeWord ("Hey Halbert" / "Computer")
```
- **Barge-in Logic:** When VAD detects user speech while Piper TTS is actively streaming audio back, the server immediately cancels the current playback task and flushes audio buffers.

---

### Gap 5: Ambient Sentient UI & Spatial Topology Canvas

#### The Problem:
`dashboard/frontend/` provides classic desktop management cards: chat message stream, settings tabs, and telemetry gauges. It lacks an ambient, glanceable representation of the physical home.

#### Remediation Plan (Connecting with UI Redesign Plan):
1. **Auto-Generated Area Grid (`AreaGrid.tsx`):**
   - Renders clean room cards directly from the imported HA Area Registry with occupancy glow, temperature, and live Frigate thumbnails.
2. **Embedded Lovelace Bridge (`LovelaceEmbed.tsx`):**
   - For users who already built custom 2D/3D floorplans in Home Assistant, provide a 1-click embed toggle to display their existing Lovelace cards.
3. **Temporal Chronicle (`TemporalChronicle.tsx`):**
   - Narrative daily timeline displaying human-readable event cards with thumbnail previews and a time-travel scrubber.

---

### Gap 6: Physical Action Safety Policy & Backstops

#### The Problem:
`ToolSafetyFramework` was designed for operating system CLI safety (preventing `rm -rf /`). In a physical home, smart home actions have real-world biological and physical consequences.

#### Remediation Plan:
Create `halbert_core/integrations/home_assistant/safety_policy.py`:
```python
class HomeSafetyLevel(Enum):
    AUTONOMOUS = "autonomous"          # Safe lighting, harmless sensor queries
    CONFIRM_HIGH = "confirm_high"      # Unlocking deadbolts, heaters, alarm sirens
    ADVISORY_ONLY = "advisory_only"    # Suggest in chat only, never auto-execute

class HomeSafetyPolicy:
    def evaluate_action(self, entity_id: str, service: str, data: Dict) -> HomeSafetyCheckResult:
        # Enforces hard environmental backstops:
        # 1. Minimum temperature freeze guard (never allow HVAC heating off if temp < 50°F / 10°C)
        # 2. Perimeter security confirmation (unlocking requires voice PIN or physical gesture)
        # 3. Nighttime quiet hours safety (curfew on loud siren tests or bright strobe automations)
```

---

## 3. Prioritized Implementation Roadmap

### Phase 1: Spatial Digital Twin & Entity Fusion (Gaps 1 & 2)
- [ ] Connect to HA Area Registry API (`/api/config/area_registry/list`) to auto-import rooms and entities.
- [ ] Implement camera zone to Area mapping in `home_config.json`.
- [ ] Ingest Bermuda BLE / ESPresense room presence sensors for spatial pronouns.

### Phase 2: Settings Modularization & UI Streamlining (Gap 5 & UI Plan)
- [ ] Decompose `Settings.tsx` into modular sub-tabs in `src/pages/settings/`.
- [ ] Add `HomeSettings.tsx` with HA connection, Frigate, presence sensor, and safety policy controls.
- [ ] Consolidate sidebar navigation into 4 primary domains.

### Phase 3: Semantic Visual Memory & Episode Search (Gap 3)
- [ ] Implement keyframe scene captioning on Frigate review events using local VLM.
- [ ] Index spatial visual descriptors into SQLite FTS5 episodic memory.
- [ ] Implement `query_visual_episodes` agent tool.

### Phase 4: Physical Home Safety Policy (Gap 6)
- [ ] Implement `HomeSafetyPolicy` with temperature freeze-guards and perimeter safety gates.
- [ ] Wire gesture/voice PIN confirmation into `StateContext.pending_confirmation`.

### Phase 5: Voice Duplex Streaming Engine (Gap 4)
- [ ] Implement WebSocket PCM audio streaming in FastAPI.
- [ ] Integrate Silero VAD + faster-whisper + Piper audio stream with barge-in support.
