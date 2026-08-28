# Home Automation Variant — Handoff for Worktree Implementation

**Date:** 2026-08-27 (Updated after multi-pass reverse engineering review)  
**From:** Design exploration & architectural scrutiny session  
**To:** Implementation AI (worktree session)  
**Status:** Approved design, ready for Phase 1 implementation  
**Authoritative Reference Docs:**
- Design Doc: `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md`
- Architectural Scrutiny: `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-REVIEW-FEEDBACK-v2.md`

---

## 1. Mission

Build Phase 1 of the home automation variant of Halbert. The goal is **a cognition and knowledge layer for the home**, not a control surface or hub replacement. Halbert Home is a cognitive being that lives in the house, understands its state, and can be conversed with.

**What we are NOT building:**
- A HomeKit or Lovelace tile-dashboard competitor
- A hub or hardware protocol bridge (Zigbee/Z-Wave stay in HA)
- A replacement for Home Assistant automations
- A multi-instance spawning/orchestration subsystem (unnecessary for single N150 deployment)

**What we ARE building in Phase 1:**
- A new "Home" panel in the existing Halbert dashboard
- Home Assistant REST API client (`ha_client.py`) with connection management (`ha_config.py`)
- Dashboard API routes (`/api/home/*`)
- Home-facing personality archetypes (`caretaker`, `butler`, `concierge`, `guardian`) wired into the archetype registry
- Frontend UI in React (`pages/Home.tsx`), registered in router and sidebar

---

## 2. Worktree Setup

Work in the designated worktree:
```bash
~/.config/superpowers/worktrees/Halbert/home-automation
```
Branch: `feat/home-automation` from current `main`.

> [!NOTE]
> `BeingConfig` already includes personality fields (`archetype_id`, `personality_profile`, `tone_descriptors`, `speech_patterns`, `directives`, `custom_personality_prompt`) in `halbert_core/config/being_config.py`.

---

## 3. Architecture & Key Discoveries

### 3.1 Dashboard Backend (`halbert_core/dashboard/`)
- `app.py:208` — `create_app()` creates the FastAPI application.
- API route inclusion is at `app.py:265-292`.
- **CRITICAL SPA ROUTE MECHANISM (`app.py:326-347`)**: FastAPI does **not** use a catch-all route for the React SPA. It uses explicit `@app.get(...)` decorators. You must register `/home` in this table or direct browser navigation/refresh will return an HTTP 404!
- Use a clean `_SPA_ROUTES` collection or explicitly include `@app.get("/home")` alongside the existing SPA routes.

### 3.2 Home Assistant REST API Capabilities & Workaround
- States: `GET /api/states`, `GET /api/states/{entity_id}` ✅
- Services: `GET /api/services`, `POST /api/services/{domain}/{service}` ✅
- Instance Config: `GET /api/config` ✅
- **Areas and Devices (GOTCHA)**: Home Assistant has **no REST endpoints** for `/api/areas` or `/api/devices` (those are WebSocket/registry only). To fetch areas and area entities via REST in Phase 1, use Home Assistant's template rendering endpoint:
  ```http
  POST /api/template
  Content-Type: application/json
  Authorization: Bearer {token}

  {"template": "{{ areas() | list }}"}
  ```
  And for area entities:
  ```http
  POST /api/template
  Content-Type: application/json
  Authorization: Bearer {token}

  {"template": "{{ area_entities('living_room') | list }}"}
  ```
  `ha_client.py` must use this template rendering method with graceful fallback to flat domain grouping if the template endpoint is restricted or returns empty.

### 3.3 Archetype Registry Discovery (`halbert_core/persona/`)
- `personality_prompt.py:90-102` resolves `archetype_id` via `get_archetype(archetype_id)` from `persona/archetypes.py`.
- If `home_archetypes.py` is isolated and not registered in `archetypes.py`, setting `archetype_id: caretaker` logs an unknown archetype warning and falls back to generic Big Five traits, silently discarding the caretaker's dialogue style, description, and tone.
- `persona/archetypes.py` must be updated so `get_archetype()` and `list_archetypes()` also resolve home archetypes.

### 3.4 Config Storage Separation
- **`being.yml`** (`~/.config/halbert/being.yml`): Stores identity (`voice`, `archetype_id`, `purpose`, `personality_profile`).
- **`ha_config.yml`** (`~/.config/halbert/ha_config.yml`): Stores HA infrastructure connection (`ha_url`, `ha_token`, `enabled`).
- Do **NOT** put `ha_url` in `being.yml`. `BeingConfig` does not have an `ha_url` attribute.

---

## 4. Phase 1 Implementation Specification

### 4.1 Backend Components

#### 1. `halbert_core/integrations/home_assistant/__init__.py`
Package initialization.

#### 2. `halbert_core/integrations/home_assistant/ha_config.py`
```python
from dataclasses import dataclass, asdict
from pathlib import Path
import yaml
from ...utils.platform import get_config_dir

@dataclass
class HAConfig:
    ha_url: str = ""
    ha_token: str = ""
    enabled: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "HAConfig":
        config_path = path or (get_config_dir() / "ha_config.yml")
        if not config_path.exists():
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path | None = None) -> None:
        config_path = path or (get_config_dir() / "ha_config.yml")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(asdict(self), f)
```

#### 3. `halbert_core/integrations/home_assistant/ha_client.py`
Uses `aiohttp` (already in `halbert_core` dependencies).
Methods:
- `__init__(ha_url: str, ha_token: str, session: aiohttp.ClientSession | None = None)`
- `test_connection() -> bool`: calls `GET /api/`
- `get_config() -> dict`: calls `GET /api/config`
- `get_states() -> list[dict]`: calls `GET /api/states`
- `get_entity_state(entity_id: str) -> dict`: calls `GET /api/states/{entity_id}`
- `get_services() -> list[dict]`: calls `GET /api/services`
- `call_service(domain: str, service: str, service_data: dict | None = None) -> dict`: calls `POST /api/services/{domain}/{service}`
- `render_template(template_str: str) -> Any`: calls `POST /api/template` with `{"template": template_str}`
- `get_areas() -> list[str]`: calls `render_template("{{ areas() | list }}")` with fallback to `[]`
- `get_area_entities(area_name_or_id: str) -> list[str]`: calls `render_template` with `{{ area_entities('...') | list }}`

#### 4. `halbert_core/dashboard/routes/home.py`
APIRouter with prefix `/api/home`, tags `["home"]`:
- `GET /api/home/status` — returns `{ "configured": bool, "connected": bool, "url": str, "entity_count": int }`
- `POST /api/home/connect` — payload `{ "ha_url": str, "ha_token": str }`, tests connection, saves to `ha_config.yml` on success
- `POST /api/home/disconnect` — clears token and marks `enabled=False` in `ha_config.yml`
- `GET /api/home/config` — returns current config (masks token)
- `GET /api/home/entities` — returns full list of entities with optional `domain` query filter
- `GET /api/home/entities/{entity_id}` — state of a specific entity
- `GET /api/home/domains` — unique domains list with entity counts
- `GET /api/home/areas` — list of areas and their entities
- `GET /api/home/services` — available services
- `POST /api/home/service` — call a service `{ "domain": str, "service": str, "service_data": dict }`
- `GET /api/home/archetypes` — returns the 4 home archetypes

#### 5. `halbert_core/persona/home_archetypes.py`
Defines 4 home personality archetypes using lazy imports of Haloysius `PersonalityArchetype` and `PersonalityProfile`:
- `caretaker`: Warm, attentive, proactive. High agreeableness, high conscientiousness.
- `butler`: Formal, precise, discreet, obedient. High conscientiousness, low extraversion, low neuroticism.
- `concierge`: Adaptable, resource-oriented, welcoming. High openness, high extraversion.
- `guardian`: Security-conscious, vigilant, perimeter-focused. High conscientiousness, low openness, low neuroticism.
Exports `HOME_ARCHETYPES: dict[str, PersonalityArchetype]` and `get_home_archetype(id: str)`.

#### 6. `halbert_core/persona/archetypes.py` (Registry Integration)
Update `_build_archetypes()` or `get_archetype()` to include home archetypes:
```python
def get_archetype(archetype_id: str) -> Optional[object]:
    registry = _build_archetypes()
    if archetype_id in registry:
        return registry[archetype_id]
    try:
        from .home_archetypes import get_home_archetype
        return get_home_archetype(archetype_id)
    except Exception:
        return None
```
Also update `list_archetypes()` so the API can return both sysadmin and home archetypes when queried.

---

### 4.2 Frontend Components

#### 1. `halbert_core/dashboard/frontend/src/pages/Home.tsx`
- **Connection Card (when not connected)**:
  - Input for HA URL (e.g. `http://homeassistant.local:8123`)
  - Password/token input for Long-Lived Access Token
  - "Connect" button with loading and error states
- **Connected View**:
  - Connection status badge (green dot, URL, entity count)
  - Quick domain filter chips (All, Lights, Switches, Climate, Sensors, Locks)
  - Tab toggle: **By Domain** vs. **By Area (Rooms)**
  - Search input to filter entities by name or entity_id
  - Entity cards with entity ID, friendly name, state badge, and last updated time
  - Interactive quick toggle button for lights/switches (invokes `POST /api/home/service`)
- **Conversation Spine**:
  - Chat interface is always accessible from layout/side-panel so user can converse with the home entity.

#### 2. `halbert_core/dashboard/frontend/src/App.tsx`
Add route:
```tsx
import { Home } from './pages/Home'
// ...
<Route path="/home" element={<Home />} />
```

#### 3. `halbert_core/dashboard/frontend/src/components/Layout.tsx`
Add Home to sidebar navigation array right after Dashboard:
```tsx
import { Home as HomeIcon, ... } from 'lucide-react'
// ...
const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Home', href: '/home', icon: HomeIcon },
  // ...
]
```

#### 4. `halbert_core/dashboard/app.py`
1. Register the API router:
```python
from .routes import home
app.include_router(home.router, tags=["home"])
```
2. **Register the SPA route**:
In lines 326-347:
```python
@app.get("/dashboard")
@app.get("/home")  # <-- MANDATORY for SPA routing
@app.get("/terminal")
...
async def serve_spa():
    return FileResponse(frontend_dist / "index.html", ...)
```

---

## 5. File Manifest

### New Files
| File Path | Description |
|---|---|
| `halbert_core/halbert_core/integrations/home_assistant/__init__.py` | Package marker |
| `halbert_core/halbert_core/integrations/home_assistant/ha_config.py` | Connection configuration dataclass (`ha_config.yml`) |
| `halbert_core/halbert_core/integrations/home_assistant/ha_client.py` | `aiohttp`-based Home Assistant REST client with template rendering |
| `halbert_core/halbert_core/integrations/home_assistant/tests/test_ha_client.py` | Pytest suite for `ha_client` (mocking aiohttp responses) |
| `halbert_core/halbert_core/dashboard/routes/home.py` | FastAPI routes for `/api/home/*` |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Home.tsx` | React Home dashboard page |
| `halbert_core/halbert_core/persona/home_archetypes.py` | 4 home personality archetypes |

### Modified Files
| File Path | Modification Description |
|---|---|
| `halbert_core/halbert_core/dashboard/app.py` | 1. Import and include `home.router`<br>2. Add `@app.get("/home")` to SPA routes decorator list |
| `halbert_core/halbert_core/persona/archetypes.py` | Extend `get_archetype()` and `list_archetypes()` to include home archetypes |
| `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` | Add `<Route path="/home" element={<Home />} />` |
| `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` | Add `{ name: 'Home', href: '/home', icon: HomeIcon }` to `navigation` array |

---

## 6. Constraints & Coding Rules

- **No emojis** in code or UI labels. Use `lucide-react` icons exclusively.
- **Imports at top of file**, except for lazy imports of `haloysius` (which must be lazy to prevent hard crashes if Haloysius is missing).
- **Follow existing codebase styles** (e.g. FastAPI models, error handling, shadcn/ui React components).
- **Clean commits**: Do NOT include `Co-Authored-By` or any bot attribution in commit messages.
- **Do NOT modify `cognition_wiring.py`** in Phase 1. Phase 1 is strictly connection, state browsing, service calling, and UI presentation.

---

## 7. Verification Plan

1. **Unit Tests**:
   - Run `pytest halbert_core/halbert_core/integrations/home_assistant/tests/test_ha_client.py`
   - Test config serialization / deserialization round-trip
   - Test archetype lookup: verify `get_archetype("caretaker")` returns the caretaker archetype
2. **Manual Backend Verification**:
   - Start Halbert: `halbert dashboard-serve`
   - Verify `GET /api/home/status` returns 200 with `{ "configured": false, "connected": false }`
   - Verify `GET /api/home/archetypes` returns 4 archetypes
3. **Frontend Verification**:
   - Navigate directly to `http://localhost:8000/home` and reload page (verifies SPA route doesn't 404)
   - Ensure "Home" icon appears in sidebar under Dashboard
   - Enter test HA URL/token and confirm error or success state handles cleanly
