# Home Automation — Implementation Strategy

**Date:** 2026-08-27
**Status:** Planning, post-review
**Worktree:** `~/.config/superpowers/worktrees/Halbert/home-automation` (branch `feat/home-automation`)

---

## 1. Review Feedback Assessment

The review feedback (`HOME-AUTOMATION-DESIGN-REVIEW-FEEDBACK.md`) is **highly meaningful**. Here's the point-by-point verdict:

### Accepted (incorporate into plan)

| # | Feedback | Verdict | Action |
|---|----------|---------|--------|
| 1.2 | WebSocket event flood vulnerability | **Critical** | Filter at subscription boundary, debounce telemetry |
| 1.3 | No initial state sync on boot | **Critical** | `GET /api/states` hydration on startup/reconnect |
| 2.1 | Phase 3 (HACS) before Phase 4 (Voice) is backwards | **Agree** | Wyoming doesn't need HACS. Reorder. |
| 2.2 | SourcePrep scheduled too late | **Agree** | Move to Phase 3. Config awareness amplifies Phase 2. |
| 2.3 | Phase 1 lacks tactile satisfaction | **Agree** | Add minimal `call_service` tool to Phase 1. |
| 3.2 | `cognition_wiring.py` hardcodes persona_id and scene_context | **Verified critical** | Must parameterize even for two-process approach. |
| 3.3 | ChromaDB/SQLite lock collision risk | **Valid** | Document `--data-dir` isolation requirement. |
| 4.1 | SourcePrep single-project limitation | **Verified** | Design doc claim was inaccurate. Accept single-project for now. |
| 5.1 | Missed competitors (Extended OpenAI Conversation, native Assist) | **Valid** | Update competitive analysis. |
| 5.2 | "Cognition not chat" is engineering concept, not user benefit | **Agree** | Reframe moat as user-facing value. |
| 6.1 | 3B model default for N150 voice | **Agree** | 7B is too slow for voice on N150. 3B is the target. |
| 6.4 | Offload embeddings to Ollama | **Strong agree** | Removes PyTorch ~500MB. Major win. |
| 7.1 | Missing `@app.get("/home")` in app.py SPA routes | **Verified critical** | Must add or direct nav/refresh 404s. |
| P2.1 | Multi-human household reality | **Strong agree** | Design for partner acceptance factor. |
| P2.2 | "Catch-up debrief" as primary interaction | **Strong agree** | This is the killer UX pattern. |
| P3.1 | Automation conflict auditor (Gem 1) | **Strong agree** | This is the differentiated feature. |
| P3.2 | HA History API for instant context (Gem 2) | **Strong agree** | Query logbook on first boot. |
| P3.3 | Area/floor spatial scoping (Gem 3) | **Agree** | Essential for voice. |
| P4 | Physical safety governance levels | **Critical** | `HAGovernancePolicy` with 4-level enforcement. |

### Accepted but deferred

| # | Feedback | Verdict | Action |
|---|----------|---------|--------|
| 4.2 | `CompositeRetrievalBackend` for multi-project | **Good idea, later** | Phase 6+ enhancement. Single project is fine for MVP. |
| P3.4 | Power signature tracking (Gem 4) | **Future** | Phase 5+ or plugin. |
| P3.5 | Dynamic tariff/energy optimization (Gem 5) | **Future** | Phase 5+ or plugin. |
| P3.6 | Consumables tracking (Gem 6) | **Future** | Natural fit for cognition, but not MVP. |

### Rejected

| # | Feedback | Verdict | Reason |
|---|----------|---------|--------|
| 6.2 | Cloud LLM fallback question | **Out of scope** | Halbert is self-hosted. Cloud is a config option, not architecture. |

---

## 2. Revised Roadmap

Based on the feedback, the roadmap is resequenced:

| Phase | Goal | Key Change |
|-------|------|------------|
| **1** | Home panel + HA REST client + minimal service call | Added `call_service` tool + SPA route fix |
| **2** | HA WebSocket events (filtered) → cognition | Added event filtering, state hydration, HA History backfill |
| **3** | SourcePrep for HA configs | **Moved up from Phase 6**. No refactoring, just project registration. |
| **4** | Voice via Wyoming agent | **Moved up from Phase 4** (was already 4, but now confirmed before HACS). No HACS dependency. |
| **5** | Frigate integration | Unchanged. MQTT events → cognition. |
| **6** | HA Custom Integration (HACS bridge) | **Moved down from Phase 3**. Polish layer, not prerequisite. |
| **7** | Multi-instance (if needed) | Unchanged. Two-process approach. |
| **8** | Light variant packaging | Unchanged. |

### Why this order is better

1. **Phase 1** gives tactile feedback (chat can call `light.turn_off`)
2. **Phase 2** makes the house aware (filtered events → cognition + history backfill)
3. **Phase 3** gives config understanding (SourcePrep indexes HA YAMLs — now the house knows *why* things happen, not just *that* they happened)
4. **Phase 4** gives voice (Wyoming TCP — zero HACS dependency, works with HA Voice PE)
5. **Phase 5** gives eyes (Frigate MQTT)
6. **Phase 6** is polish (HACS installability, Assist API tools — nice to have, not blocking)
7. **Phase 7-8** are operational concerns

---

## 3. Phase 1 Implementation Plan (Detailed)

### 3.1 Prerequisite: Parameterize `cognition_wiring.py`

Before any home-specific code, the hardcoded identity strings must be parameterized. This is a **prerequisite for Phase 1** because the home instance needs `persona_id="home"` and `scene_context="smart home automation"`.

**Changes to `cognition_wiring.py`:**

```python
# Before (hardcoded):
cognition = PersonaCognition(persona_id="halbert")
cognition.scene_context = "macOS system administration"
store = PersonaMemoryStore("halbert")
ThoughtGenerator("halbert", "Halbert", ...)

# After (parameterized via BeingConfig or env):
persona_id = os.environ.get("HALBERT_PERSONA_ID", "halbert")
scene_context = os.environ.get("HALBERT_SCENE_CONTEXT", "")
if not scene_context:
    # fall back to platform-derived default
    ...
cognition = PersonaCognition(persona_id=persona_id)
cognition.scene_context = scene_context
store = PersonaMemoryStore(persona_id)
ThoughtGenerator(persona_id, persona_id.capitalize(), ...)
```

This is a ~10 line change. No architectural refactor. The two-process approach works because each process sets different env vars.

**Also:** Document `HALBERT_DATA_DIR` for ChromaDB/SQLite isolation. The home process uses `HALBERT_DATA_DIR=~/.local/share/halbert-home` to avoid lock collisions.

### 3.2 File Manifest

| File | Purpose |
|------|---------|
| `integrations/home_assistant/__init__.py` | Package init |
| `integrations/home_assistant/ha_client.py` | REST API client (aiohttp) |
| `integrations/home_assistant/ha_config.py` | Connection config dataclass |
| `dashboard/routes/home.py` | FastAPI routes for Home panel |
| `dashboard/frontend/src/pages/Home.tsx` | React Home panel |
| `dashboard/frontend/src/components/HomeConnectionForm.tsx` | HA connection setup form |
| `dashboard/frontend/src/components/EntityList.tsx` | Entity browser by domain/area |
| `persona/home_archetypes.py` | 4 home archetypes (Steward, Companion, Guardian, Concierge) |

### 3.3 Backend Routes

```
GET  /api/home/status          — HA connection status
GET  /api/home/entities         — List entities (filter by domain, area)
GET  /api/home/entity/{id}      — Get single entity state
POST /api/home/service          — Call HA service (domain, service, data)
GET  /api/home/areas            — List HA areas
GET  /api/home/archetypes       — List home archetypes
POST /api/home/config           — Save HA connection config
GET  /api/home/config           — Load HA connection config
```

### 3.4 Frontend

- Add `@app.get("/home")` to `app.py` SPA routes (line ~341, before `serve_spa`)
- Add `{ name: 'Home', href: '/home', icon: Home }` to `Layout.tsx` navigation array (after Dashboard, line ~51)
- Add `<Route path="/home" element={<Home />} />` to `App.tsx` (line ~93)
- `Home.tsx`: connection form (if not configured) or entity browser + chat

### 3.5 Minimal Tool: `ha_call_service`

A thin tool wrapper that lets the chat engine call HA services:

```python
class HACallServiceTool:
    """Tool for calling HA services from chat."""
    async def execute(self, domain: str, service: str, data: dict) -> str:
        result = await self.ha_client.call_service(domain, service, data)
        return f"Called {domain}.{service} with {data}"
```

This is registered as a tool in the agent's tool registry so the LLM can call it during chat. Phase 1 governance: all HA service calls require no approval (Level 0-1 only in Phase 1; governance comes in Phase 2).

### 3.6 Home Archetypes

4 archetypes following the existing `persona/archetypes.py` pattern:

| Archetype | Personality | Voice |
|-----------|-------------|-------|
| **Steward** | Conscientious, organized, proactive | Formal, precise |
| **Companion** | Warm, agreeable, conversational | Casual, friendly |
| **Guardian** | Vigilant, security-focused, direct | Alert, concise |
| **Concierge** | Service-oriented, attentive, refined | Polished, courteous |

### 3.7 Testing

- Unit test `ha_client.py` with mocked aiohttp responses
- Test config load/save round-trip
- Test archetype listing returns 4 archetypes
- Test `call_service` route with mocked HA
- Manual test: point at a real HA instance or mock the REST API
- Frontend: Home panel renders, connection form works, entity list displays, service call from chat works

---

## 4. Phase 2 Implementation Plan (Outline)

### 4.1 WebSocket Event Client

```python
# integrations/home_assistant/ha_event_stream.py
class HAEventStream:
    """Filtered WebSocket subscription to HA state_changed events."""
    
    FILTERED_DOMAINS = {
        "climate", "lock", "alarm_control_panel", "binary_sensor",
        "person", "device_tracker", "input_boolean", "sensor",
    }
    
    DEBOUNCE_DOMAINS = {
        "sensor": 30,  # seconds — telemetry sensors debounced
    }
    
    async def connect(self):
        # 1. GET /api/states to hydrate initial state
        # 2. Subscribe to state_changed via WebSocket
        # 3. Filter by domain, debounce telemetry
        # 4. Forward meaningful events to HAEventMapper
```

### 4.2 HA History Backfill (Gem 2 from review)

On first connection, query `GET /api/history/period/<timestamp>` for the last 7-14 days. Feed significant events (door opens, alarm state changes, occupancy transitions) into PersonaCognition as pre-existing observations. This makes Halbert feel like it has known the house from minute one.

### 4.3 HAEventMapper

Maps filtered HA events → PersonaCognition observations:

```
state_changed: lock.front_door (unlocked → locked)
  → observation: "The front door was locked at 10:32 PM"

state_changed: person.sarah (away → home)  
  → observation: "Sarah arrived home at 3:15 PM"

state_changed: climate.living_room (off → heat, target 21°C)
  → observation: "Living room heating turned on, target 21°C"
```

### 4.4 HAGovernancePolicy

4-level governance (from review Part 4):

```python
class HAGovernancePolicy:
    LEVEL_0_NO_CONFIRM = {"light", "fan", "media_player", "vacuum"}
    LEVEL_1_LOW_RISK = {"climate", "humidifier", "cover"}  
    LEVEL_2_CONFIRM_REQUIRED = {"lock", "alarm_control_panel", "garage_door"}
    LEVEL_3_FORBIDDEN = {"water_valve", "switch.freezer", "switch.medical"}
```

### 4.5 Cognition Wiring for Home

The home instance sets:
- `HALBERT_PERSONA_ID=home`
- `HALBERT_SCENE_CONTEXT=smart home automation`
- `HALBERT_DATA_DIR=~/.local/share/halbert-home`

The `HAEventMapper` is registered alongside (not replacing) `SystemEventMapper`. Both feed into the same `PersonaCognition` instance.

---

## 5. Phase 3 Implementation Plan (Outline)

### SourcePrep for HA Configs

**No Halbert refactoring needed.** Steps:

1. Install SourcePrep daemon on the same machine (or point at existing instance)
2. Register HA config as a project:
   ```
   sourceprep project add --name ha-config --path /config
   ```
   (Where `/config` is the HA config directory — mounted volume in Docker, or `/usr/share/hass` in HA OS)
3. In the home instance's config, set `sourceprep_project_id=ha-config`
4. `SourcePrepRetrievalBackend` already accepts `project_id` — it's a config change

**Limitation acknowledged:** The home instance can only search one SourcePrep project at a time. A `CompositeRetrievalBackend` that queries both `halbert-host` and `ha-config` is a future enhancement (Phase 6+). For now, the home instance searches HA configs; the host instance searches host configs. If a user runs both instances, each has its own retrieval scope.

**What this enables:**
- "Why is the living room light automation triggering twice?" → SourcePrep retrieves the automation YAML
- "Show me all automations that touch the front door lock" → SourcePrep semantic search
- "What changed in the thermostat schedule?" → SourcePrep retrieves config history

---

## 6. Phase 4 Implementation Plan (Outline)

### Wyoming Protocol Agent

A TCP server implementing the Wyoming conversation protocol:

```python
# integrations/wyoming_agent.py
class HalbertWyomingAgent:
    """Wyoming protocol conversation agent for HA voice pipelines."""
    
    async def handle_transcript(self, text: str, conversation_id: str):
        # 1. Feed transcript to Halbert agent loop
        # 2. Get response text
        # 3. Return as Wyoming 'response' event
        
    async def start(self, host: str = "0.0.0.0", port: int = 10400):
        # TCP server, JSONL protocol
```

**HA configuration:** Add as a Wyoming protocol integration in HA's Settings → Voice Assistants. No HACS needed. HA's voice pipeline routes STT → Halbert Wyoming agent → TTS.

**Spatial scoping (Gem 3):** HA passes `context.area_id` from the satellite device. Halbert's tool resolution filters entities by area when the user says "turn on the light" without specifying a room.

**Proactive voice:** Halbert can call HA's `tts.speak` service to initiate speech. But:
- Only for Level 2+ security events (review Part 4)
- Only to the room where the target user is detected (area-tethered)
- Suppressed when `input_boolean.guest_mode` or `input_boolean.sleeping` is active

---

## 7. Key Design Decisions (Post-Review)

### D-1: Embeddings via Ollama (not sentence-transformers)

The review correctly identifies that `sentence-transformers` pulls in PyTorch (~500MB RSS). For the N150 target, this is significant.

**Decision:** Add an `OllamaEmbeddingBackend` option in Haloysius/Halbert that uses Ollama's `/api/embeddings` endpoint with `nomic-embed-text` or `all-minilm` model. The home instance defaults to Ollama embeddings. The desktop instance can still use sentence-transformers if preferred.

**Impact:** This is a Haloysius-level change (the `EmbeddingBackend` protocol in `seam.py`). It's a consumer-side implementation, not a core change. The `PersonaMemoryStore` already accepts an embedding function — we just pass a different one.

### D-2: 3B Model Default for Home

**Decision:** The home instance defaults to Llama 3.2 3B or Qwen 2.5 3B for local inference. 7B is optional for users with more powerful hardware. The config specifies the model; the default is 3B.

### D-3: Single SourcePrep Project (for now)

**Decision:** Accept the single-project limitation. The home instance uses `ha-config` as its SourcePrep project. A `CompositeRetrievalBackend` is a future enhancement. The design doc's claim about simultaneous host+HA indexing is corrected.

### D-4: Two-Process Multi-Instance

**Decision:** No `InstanceManager`. Two daemon processes with different env vars (`HALBERT_PERSONA_ID`, `HALBERT_DATA_DIR`, `HALBERT_SCENE_CONTEXT`). The `cognition_wiring.py` parameterization (D-1 above) makes this work.

### D-5: Interaction Paradigm — Catch-Up Debrief

**Decision:** The primary interaction pattern is the "catch-up debrief" (review Part 2.2), not proactive interruptions. The user asks "anything I should know?" and Halbert summarizes from episodic memory. Proactive voice is reserved for Level 2+ security events only, and is area-tethered + suppressed by guest/sleep modes.

### D-6: HAGovernancePolicy — Physical Safety

**Decision:** Implement a 4-level governance policy for HA actions (review Part 4). Level 3 (life-safety equipment) is forbidden from autonomous LLM control. Level 2 (perimeter) requires voice/Pin confirmation. This replaces the current stub `HalbertGovernancePolicy` for the home instance.

---

## 8. Immediate Next Steps

1. **Parameterize `cognition_wiring.py`** — env var driven persona_id, scene_context, data_dir. ~10 line change. No architectural refactor.

2. **Implement Phase 1 in the worktree** — HA client, Home panel, SPA route fix, minimal service call tool, 4 archetypes.

3. **Update design doc** — correct the SourcePrep multi-project claim, add the competitive analysis (Extended OpenAI Conversation, native Assist), reframe the moat as user-facing value, add the governance levels and interaction patterns from the review.

4. **Update handoff doc** — reflect the resequenced roadmap and the Phase 1 additions (SPA route, service call tool, cognition_wiring parameterization).

---

## 9. Open Questions for Founder

1. **Embeddings via Ollama** — Should we implement `OllamaEmbeddingBackend` now (Phase 1 prerequisite for N150 target) or defer? It's a Haloysius consumer-side change.

2. **Home panel placement** — After Dashboard (position 2) or at the bottom of the nav? Review suggests after Dashboard.

3. **Phase 1 governance** — Should `call_service` in Phase 1 have any restrictions, or is it wide open (since it's just the user chatting, not autonomous)?

4. **HA History backfill depth** — 7 days or 14 days for the initial history query? More history = better context but more processing on first boot.

5. **Wyoming port** — Default port 10400 for the Halbert Wyoming agent? Standard Wyoming ports start at 10200.
