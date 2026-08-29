# Sentient Home UX & Interaction Architecture

**Date:** 2026-08-29  
**Status:** Comprehensive UX Specification & Embodiment Framework  
**Target:** Halbert Ambient Home AI (macOS / Linux Server + Multi-Device Wall Displays & Mobile)  

---

## 1. Vision & Identity: "The Cognitive & Orchestration Layer"

Halbert as a **Sentient Home** is fundamentally different from a conventional smart home hub or voice assistant (Home Assistant, Alexa, Apple Home). It is not a utility dashboard with 500 toggle buttons, nor a voice box waiting passively for wake-words.

Halbert **is the cognitive and orchestration mind of the home**:
- **Nervous System (Sensors & Actuators):** Ingested via Home Assistant WebSocket state changes, Zigbee sensors, ESPHome nodes.
- **Ocular Perception (Eyes):** Frigate NVR spatial cameras, local webcams, desktop screen feeds.
- **Vocal & Auditory Organs (Voice & Ears):** Whisper local STT, Piper neural TTS, ambient mic arrays.
- **Cognitive Core (Mind):** `PersonaCognition` (Haloysius) running continuous subconscious loops (`advance_turn`), experiencing the daily life of the home, maintaining worries, drives, emotions, and autobiographical memories.

```
                     ┌─────────────────────────────────────────────────────────┐
                     │               THE SENTIENT HOME CANVASES                │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
            ┌─────────────────────────────────────┼─────────────────────────────────────┐
            │                                     │                                     │
            ▼                                     ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐             ┌───────────────────────┐
│   SPATIAL AREA GRID   │             │ TEMPORAL CHRONICLE    │             │   AMBIENT COMPANION   │
│ (Auto-synced HA Areas)│             │ (Autobiographical Log)│             │ (Voice / Gaze / Chat) │
├───────────────────────┤             ├───────────────────────┤             ├───────────────────────┤
│ • Auto-synced Rooms   │             │ • "What happened?"    │             │ • Wake-word & Whisper │
│ • Light & Temp Auras  │             │ • Visual Keyframe Log │             │ • Subconscious Insights│
│ • Camera Zone Overlays│             │ • Spatial Object Track│             │ • Hands-free Gestures │
│ • Embedded Lovelace UI│             │ • Time Scrubber       │             │ • Walk-up Proximity   │
└───────────────────────┘             └───────────────────────┘             └───────────────────────┘
```

---

## 2. Leveraging Existing Tools (No Reinventing the Wheel)

### The Anti-Pattern: Building a Proprietary 3D/2D CAD Floorplan Engine
Building custom vector floorplan editors, drag-and-drop room designers, and 3D rendering engines from scratch would take months of development and duplicate existing open-source ecosystems.

### The Solution: Direct Integration with Proven Home Assistant Tooling

| Tool / Integration | What it Provides | How Halbert Leverages It |
|---|---|---|
| **HA Area Registry API** (`/api/config/area_registry/list`) | Native mapping of all rooms (`living_room`, `kitchen`, `garage`), entity assignments, and device groupings. | **Zero-Configuration Spatial Model:** Halbert connects to HA, auto-imports all Areas and bound entities, and immediately constructs its internal spatial reasoning graph. |
| **Bermuda BLE Trilateration / ESPresense / Room-Assistant** | Room-level presence tracking via Bluetooth beacons, Apple Watches, phones (`sensor.eric_room = "living_room"`). | **Spatial Pronoun Resolution:** When the user says *"Turn off the lights in here"*, Halbert checks the room-presence sensor to resolve the active room automatically. |
| **HA Floorplan (ha-floorplan / Lovelace SVG)** & **3D Floorplan** | Community-standard interactive 2D SVGs / 3D GLTF models created by power users. | **Seamless Lovelace Embedding:** Users who already created custom floorplans can view them directly inside Halbert via an embedded Lovelace card/iframe view. |
| **Frigate Lovelace Card & Birdseye** | Real-time multi-camera streaming, tracked bounding boxes, and spatial camera mosaics. | **Camera Gaze Inlays:** Embedded live low-latency snapshots with Frigate detection overlays. |

---

## 3. The Three Core UX Canvases

### Canvas 1: The Spatial Living Topology ("The House at a Glance")

Rather than manual CAD layouts, Halbert presents a clean, auto-generated **Spatial Living Area Grid**:

1. **Auto-Generated Room Cards:**
   - Grouped automatically from Home Assistant's Area Registry (`Living Room`, `Office`, `Kitchen`, `Garage`).
   - **Presence Warmth:** Rooms subtly glow with warmth when occupied (combining PIR motion, mmWave radar, Frigate person detection, and BLE beacon sensors).
   - **Environmental Aura:** Temperature, humidity, and air quality gradients.
   - **Active State Summary:** "3 lights on, 71°F, music playing".
2. **Frigate Camera Inlays:**
   - Real-time snapshot previews pinned to room cards with tracked object bounding boxes (green = resident, blue = courier, yellow = pet).
3. **Optional Advanced Floorplan Tab:**
   - For users with existing `ha-floorplan` or 3D Lovelace cards, a toggle switches from the auto-generated Area Grid to the full embedded Home Assistant Lovelace floorplan.

---

### Canvas 2: The Temporal Chronicle & Episodic Time Machine

Traditional smart homes give you dry, disconnected entity state logs (`binary_sensor.front_door changed to on at 14:02:11`). Halbert provides a **narrative, autobiographical human memory**:

```
[08:15 AM] ☀️ Morning Awakening
            "Living room blinds opened as kitchen coffee maker powered on. 
             Eric entered kitchen at 08:20 AM."
            [ 📷 1-sec Keyframe Thumbnail ]

[11:30 AM] 📦 Delivery Detected (Front Porch)
            "FedEx courier left a parcel at the door. Frigate verified package on porch."
            [ 📷 Snapshot: Package on mat ] → [ Action: Acknowledge / Snooze ]

[02:14 PM] ⚠️ Anomaly Observed (Backyard)
            "Back gate unlatched and swinging in high wind (18 mph gusts). 
             Halbert raised security vigilance."
            [ 📷 Clip Preview ] → [ Action: Dismiss / Ask Halbert ]

[05:45 PM] 🚗 Arrival & Welcome
            "Garage door opened; vehicle parked. Welcome home lighting initiated."
```

#### The "Time Machine" Scrub Bar
- A fluid scrubber across the bottom of the interface lets users slide backwards through the day or week.
- Scrubbing to `02:00 PM` retroactively reflects the home's exact state at 2:00 PM (lights, temperature, camera snapshots, room occupancy).

---

### Canvas 3: The Ambient Companion & Conversational Surface

Halbert communicates through three integrated modalities depending on context:

1. **Voice & Ear (Audio Modality):**
   - **Zero-Friction Wake Word:** *"Halbert"* or *"Computer"*.
   - **Continuous Stream Duplex:** Low-latency Whisper STT streaming + Piper neural voice with **barge-in interruption handling**.
   - **Conversational Memory:** Pronouns resolve naturally (*"Turn that off"*, *"What was that noise?"*, *"Show me who just arrived"*).
2. **Visual Gaze & MediaPipe Gesture Confirmation:**
   - On wall tablets or desk monitors equipped with cameras, Halbert tracks user presence and proximity:
     - **Walk-Up Wake:** Screen seamlessly transitions from ambient clock/mood art to active home overview when someone approaches within 4 feet.
     - **Gesture Approvals:** For critical home actions (e.g. unlocking the front door or turning off all security alarms), Halbert asks: *"Confirm unlock front door?"* $\rightarrow$ User gives a **physical thumbs-up to the camera** $\rightarrow$ Action executes instantly with an audible chime.
3. **Proactive Whispers (Subconscious Notification Stream):**
   - Non-intrusive **Subconscious Insights**:
     - *"I noticed the kitchen window is open while the AC is cooling. Want me to adjust the thermostat?"*
     - *"Good morning! All homelab backups finished cleanly overnight, and there's a package waiting by the side door."*

---

## 4. Concrete Settings Architecture: What the User Actually Configures

To give users full control without overwhelming them, settings are grouped into clear, functional sections in `Settings > Home & Space`:

```
Settings > Home & Space
────────────────────────────────────────────────────────────────────────
Home Assistant Connection
  [x] Enabled
  Server URL:    [ http://homeassistant.local:8123         ]
  Access Token:  [ ••••••••••••••••••••••••••••••••••••••• ] [Test Connection]
  [x] Auto-sync Areas, Devices, and Entities

Frigate NVR Connection
  [x] Enabled
  Server URL:    [ http://frigate.local:5000               ]
  MQTT Broker:   [ 192.168.1.50:1883                       ]
  MQTT User:     [ halbert_mqtt                            ]
  MQTT Password: [ ••••••••••••                            ]
  
  Camera Zone to Area Mapping:
    • Camera: front_porch (zone: mat)   → Area: [ Front Porch    ▾ ]
    • Camera: driveway    (zone: yard)  → Area: [ Driveway       ▾ ]
    • Camera: living_room (zone: couch) → Area: [ Living Room    ▾ ]

Presence Tracking
  Room Presence Sensor: [ sensor.bermuda_eric_room       ▾ ]
  (Auto-populated from HA BLE/ESPresense tracking sensors)

Physical Action Safety Policy
  Autonomy Level:
    ( ) Autonomous — Execute safe lighting/climate actions automatically
    (•) Confirm High-Risk — Require voice/gesture PIN for locks, sirens, heaters
    ( ) Advisory Only — Suggest actions in chat/notifications, never execute

  Environmental Safeguards:
    [x] Freeze Guard Minimum Temp: [ 50 ] °F / [ 10 ] °C
    [x] Quiet Hours: From [ 22:00 ] to [ 07:00 ] (mutes TTS & audible alerts)
────────────────────────────────────────────────────────────────────────
```

---

## 5. Interaction Scenarios

### Scenario A: Spatial Multimodal Retrieval ("Where are my tools?")
1. **User asks:** *"Halbert, where did I put my multimeter?"*
2. **Spatial Search:**
   - Resolves `"multimeter"` through `FrigateStateTracker` and `VisionCache` episodic visual index.
3. **Halbert responds:** *"You set it on the garage workbench next to the 3D printer at 11:45 AM."*
4. **UI Action:** Highlights the Garage Workbench card on the Spatial Area Grid with the keyframe thumbnail.

### Scenario B: Ambient Homelab Sentry
1. **Event:** Server rack in basement triggers high drive temperature (55°C) and amber warning LED.
2. **Fusion:** HA sensor reports temperature spike + basement camera detects blinking amber LED on drive bay 3.
3. **Cognitive Tick:** `system_event_mapper` adds `hardware_warning` to Halbert's worries.
4. **Proactive Notification:** Halbert presents a unified diagnostic card with the live camera crop showing the blinking LED and offers to take the drive offline upon thumbs-up confirmation.
