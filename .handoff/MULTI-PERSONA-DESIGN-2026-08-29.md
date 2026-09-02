# Multi-Persona System — Technical Design & Handoff

**Date:** 2026-08-29
**From:** Technical planning session
**To:** Design review
**Status:** ~~Awaiting design input before implementation~~ **Corrected
2026-09-02 (SONNET-05/DOC-01):** Phases 1–2 are merged (`9f4d4b16`) — store,
routes, persona cards with add/delete, hot reload. Not fully resolved:
`PersonaManager`'s enum was never unified with the new store, so `/switch`
and `/activate` disagree about the active persona (`PERS-02`/REV-10 F7,
open), and the fixed-name temp-symlink race (REV-10 F8) is unfixed. Also:
`home-light` (referenced below) was merged into `home` and no longer exists
as a separate variant.
**Branch:** `feat/multi-persona` (worktree: `Halbert/multi-persona`)

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** model-picker-related persona surfaces are **sysadmin-variant-only**. On `home`/`home-light` variants there is no model picker — the persona `model` override is inert and must not render; HA variants get the single Compute Peer setting instead, and the workstation's picker governs (Finding 3 / S3). Dated notes at §2 Q2, §2 Q5, and §4 Phase 3.

---

## 1. Current State

### What Exists Today

**Single persona architecture.** The system has one `BeingConfig` stored in a single `being.yml` file at `~/.config/halbert/being.yml`. This config holds:

- **Character fields:** `name`, `voice_presentation`, `archetype_id`, `custom_personality_prompt`, `model`, `model_endpoint_id`
- **Behavior fields:** `voice`, `proactivity`, `quiet_hours`, `morning_report`, `purpose`, `category_overrides`
- **Personality fields:** `personality_profile` (Big Five), `tone_descriptors`, `speech_patterns`, `directives`
- **Senses:** `senses.vision.*` (proactive capture settings)
- **Home/variant fields:** `variant`, `scene_context`, `persona_id_override`, `ha_url`, `ha_token`, `autonomy_level`, `autonomy_overrides`
- **Security:** `security.*` (operational tier, secret tier, TTL)

**Two disconnected persona systems:**

1. **`BeingConfig` (being.yml)** — the personality builder we shipped. Single instance. Drives prompt generation, model override, identity. This is what the Settings UI edits.

2. **`PersonaManager` (persona_state.json)** — an older Phase 4 system with hardcoded `Persona.IT_ADMIN` / `Persona.FRIEND` / `Persona.CUSTOM` enum values. Manages memory directory switching (`core/` vs `personas/friend/`). Has API routes at `/api/persona/*`. **Not wired into prompt generation or model selection.** The `Persona.CUSTOM` slot is stubbed out ("coming in Phase 5").

These two systems have never been unified. The personality builder (BeingConfig) handles *who* the agent is; PersonaManager handles *which memory directory* it uses. They need to converge.

### What the User Wants

> "We currently have a single persona. We need a main persona and a way to create additional personas (maybe a + button?)"

The user wants:
- A **default/main persona** (the current being.yml)
- **Additional personas** that can be created, edited, and switched to
- A **+ button** in the UI to create new personas
- Only **one persona active at a time**

---

## 2. Design Questions for Review

### Q1: Storage Shape — Single File vs. Directory

**Option A: `personas/` directory with one YAML per persona**

```
~/.config/halbert/
  being.yml          → symlink or pointer to active persona
  personas/
    default.yml      → main persona (current being.yml content)
    work.yml         → "Work Halbert" — different name, model, style
    home.yml         → "Home Halbert" — casual, different model
                      (the per-persona model is meaningful only on sysadmin
                      variants — on home/home-light it is inert; see §2 Q2)
```

- Pros: Clean separation, easy to backup/export individual personas, no schema migration
- Cons: Need a pointer file or convention for "active" persona

**Option B: Single `being.yml` with a `personas` list**

```yaml
active_persona: "default"
personas:
  - id: default
    name: Halbert
    voice: first_person
    ...
  - id: work
    name: Work Halbert
    voice: the_computer
    ...
```

- Pros: One file, atomic reads, no pointer management
- Cons: File grows large, harder to edit manually, all personas loaded on every read

**Option C: Directory with an `active` pointer file**

```
~/.config/halbert/
  personas/
    active.txt       → contains "default"
    default.yml
    work.yml
```

- Pros: Simple, each persona is a file, active state is trivial
- Cons: Two reads (pointer + persona), but both are tiny

**Recommendation:** Option A. `being.yml` becomes a symlink to the active persona file. This is zero-change for all existing `load_being_config()` callers — they read `being.yml` as before. Switching personas is a symlink swap. Creating a persona is writing a new file + updating the symlink.

### Q2: What Fields Are Per-Persona vs. Global?

Some fields in `BeingConfig` are clearly persona-scoped (name, voice, model, personality). Others are system-scoped (security, variant, HA connection, autonomy). The question is where to draw the line.

**Per-persona (the "Character"):**
- `name`, `voice`, `voice_presentation`, `proactivity`
- `archetype_id`, `personality_profile`, `tone_descriptors`, `speech_patterns`, `directives`
- `custom_personality_prompt`
- `model`, `model_endpoint_id` *(sysadmin variants only — inert on `home`/`home-light`, which have no model picker; see the 2026-08-30 note below)*
- `purpose`, `quiet_hours`, `morning_report`, `category_overrides`
- `senses.vision.*` (persona-level vision autonomy)
- `scene_context`, `persona_id_override`

**Global (system-level, not per-persona):**
- `variant` (sysadmin vs home — this is the binary the whole daemon launched with)
- `ha_url`, `ha_token` (HA connection — one house, one connection)
- `autonomy_level`, `autonomy_overrides` (home safety governance)
- `security.*` (MCP trust boundary — system-level)

**Question for design:** Should `variant` and home fields be global, or should each persona declare its own variant? E.g., a "Home" persona and a "Sysadmin" persona on the same machine? This would mean the variant is per-persona, not per-daemon. That's a bigger architectural change — the daemon would need to reconfigure services on persona switch.

**Recommendation:** Keep variant + home fields global for now. A persona defines *personality*, not *deployment mode*. If the user wants a home persona and a sysadmin persona, they'd run two instances (which the federation work already supports).

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** the per-persona `model` / `model_endpoint_id` override is only meaningful on variants that have a model picker (**sysadmin**). On `home`/`home-light` variants there is no model picker — `chat_model`/`specialist_model` resolve to the peer endpoint set via the single Compute Peer setting, and the workstation's picker governs — so the field is inert there and must not render in the persona UI (Finding 3 / S3). The variant-stays-global recommendation above is unchanged and aligns with the handoff.

### Q3: Persona Switching — Hot Reload vs. Restart

When switching personas, should the running agent hot-reload, or require a restart?

**Hot reload (recommended):**
- `AgentPromptBuilder.reload_personality()` already exists and re-reads `being.yml`
- The model override in `_resolve_turn_model()` reads `being.yml` per-turn already
- Swapping the symlink + calling `reload_personality()` is sufficient
- Memory directory switch (from PersonaManager) could be wired in later

**Restart:**
- Simpler, but worse UX. The user expects instant persona switch.

### Q4: Relationship with PersonaManager

The existing `PersonaManager` has:
- `PersonaState` with `active_persona`, `memory_dir`, `switched_at`, `switched_by`
- `switch_to()` that changes memory directory
- API routes at `/api/persona/*`
- Audit logging

**Options:**

**A. Unify:** Replace `PersonaManager`'s hardcoded enum with dynamic personas from the `personas/` directory. `switch_to()` swaps the symlink + reloads the agent. Memory directory becomes a field in the persona YAML.

**B. Layer:** Keep `PersonaManager` for memory directory management. Add a separate `PersonaStore` for personality configs. Persona switch calls both.

**C. Replace:** Delete `PersonaManager` entirely. The new system handles everything. Memory directory is just a field in the persona YAML.

**Recommendation:** Option A (unify). The `PersonaManager` already has the right shape (state persistence, audit logging, API routes). We extend it to read personas from the filesystem instead of a hardcoded enum. The `Persona.CUSTOM` stub becomes the general case.

### Q5: UI Surface

**Current:** Single "Personality" section in Settings with one `BeingSettings` component editing one config.

**Proposed:**

```
┌─────────────────────────────────────────┐
│  Personality                            │
│                                         │
│  ┌──────────────┐ ┌──────────────┐     │
│  │ ● Default    │ │   Work       │  +  │
│  │   Halbert    │ │   Halbert    │     │
│  └──────────────┘ └──────────────┘     │
│                                         │
│  ── Active Persona: Default ──          │
│                                         │
│  ┌─ Character ─────────────────────┐    │
│  │  Name: [Halbert           ]     │    │
│  │  Style: [concise][balanced]...  │    │
│  │  Model: [Default         ▼]     │    │
│  │  ...                             │    │
│  └──────────────────────────────────┘   │
│                                         │
│  ┌─ Voice ────────────────────────┐     │
│  │  ...                             │     │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

- Persona cards at the top (horizontal scroll or wrap)
- Active persona highlighted
- **+ button** creates a new persona (prompts for name)
- Clicking a persona card switches to it (hot reload)
- Settings below edit the *active* persona
- A "Delete" button on non-default personas (with confirmation)

**Question for design:** Should persona switching be in Settings only, or also in the chat composer (like a quick-switch dropdown)? The model picker pill already has a tier quick-switch — a persona quick-switch could sit beside it. **settings only**

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** variant-gate the persona card's `Model: [Default ▼]` row and any picker-pill integration: sysadmin variants render the Model dropdown (and the picker pill exists); `home`/`home-light` variants render the Compute Peer field instead — no model picker surface exists on HA variants, so the Model row does not render there (Finding 3 / S3).

### Q6: Migration Path

Existing users have a single `being.yml`. On first load after upgrade:

1. Create `personas/` directory
2. Copy `being.yml` → `personas/default.yml`
3. Replace `being.yml` with a symlink to `personas/default.yml`
4. All existing `load_being_config()` calls continue to work unchanged

The migration is transparent. No config schema change. No API breakage.
**mo existing users**
---

## 3. Technical Architecture

### Data Model

```python
@dataclass
class PersonaConfig:
    """One persona's configuration."""
    id: str                    # slugified unique id (e.g. "default", "work")
    name: str                  # display name (e.g. "Work Halbert")
    created_at: str            # ISO timestamp
    # All BeingConfig fields (voice, personality, model, etc.)
    # ...inherited or composed from BeingConfig
    
@dataclass
class PersonaManifest:
    """Index of all personas."""
    active_id: str
    personas: List[PersonaSummary]  # id, name, created_at
```

### File Layout

```
~/.config/halbert/
  being.yml              → symlink → personas/default.yml
  personas/
    default.yml          → full BeingConfig + id + name + created_at
    work.yml
    home.yml
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/personas` | List all personas + active id |
| `POST` | `/api/personas` | Create a new persona (body: name, optional template from active) |
| `GET`  | `/api/personas/{id}` | Get a persona's full config |
| `PUT`  | `/api/personas/{id}` | Update a persona's config (replaces `POST /settings/being`) |
| `DELETE` | `/api/personas/{id}` | Delete a persona (cannot delete active or last remaining) |
| `POST` | `/api/personas/{id}/activate` | Switch active persona (swaps symlink, hot-reloads agent) |

**Backward compatibility:** `GET /settings/being` and `POST /settings/being` continue to work — they read/write through the symlink to the active persona. No existing caller breaks.

### Backend Changes

1. **`persona/store.py` (new):** `PersonaStore` class that manages the `personas/` directory. CRUD operations, symlink management, migration.

2. **`persona/manager.py` (modified):** Replace hardcoded `Persona` enum with dynamic personas from `PersonaStore`. `switch_to()` calls `PersonaStore.activate(id)` + `AgentPromptBuilder.reload_personality()`.

3. **`dashboard/routes/persona.py` (modified):** New endpoints above. Keep existing `/api/persona/status` and `/api/persona/list` as aliases for backward compat.

4. **`config/being_config.py` (minimal change):** `load_being_config()` continues to read `being.yml`. The symlink makes it transparent. Add `id`, `name` (display), `created_at` fields to `BeingConfig` for persona metadata.

5. **`dashboard/routes/agent.py` (no change):** `_resolve_turn_model()` already reads `being.yml` per-turn via `load_being_config()`. The symlink swap is transparent.

6. **`prompts/agent_prompts.py` (no change):** `reload_personality()` already re-reads `being.yml`.

### Frontend Changes

1. **`BeingSettings` component (modified):**
   - Add persona card row at top
   - Fetch `GET /api/personas` on mount
   - `+` button → `POST /api/personas` with name prompt
   - Card click → `POST /api/personas/{id}/activate`
   - Edit forms below write to `PUT /api/personas/{id}` (or continue using `POST /settings/being` which writes to the active persona)

2. **Persona card component (new):** Compact card showing name, archetype badge, model badge. Active state highlighted. Delete button (hover reveal). The model badge renders on sysadmin variants only — `home`/`home-light` show no model badge (Finding 3 / S3; see the §2 Q5 note).

### Migration Logic

```python
def migrate_to_multi_persona():
    """One-time migration from single being.yml to personas/ directory."""
    config_dir = get_config_dir()
    being_yml = config_dir / "being.yml"
    personas_dir = config_dir / "personas"
    
    if personas_dir.exists():
        return  # already migrated
    
    personas_dir.mkdir(parents=True, exist_ok=True)
    
    if being_yml.exists() and not being_yml.is_symlink():
        # Copy existing config as default persona
        default_yml = personas_dir / "default.yml"
        shutil.copy2(being_yml, default_yml)
        # Add persona metadata
        _add_persona_metadata(default_yml, id="default", name="Default")
        # Replace being.yml with symlink
        being_yml.unlink()
        being_yml.symlink_to(default_yml)
    else:
        # Fresh install — create default persona
        _create_default_persona(personas_dir)
```

---

## 4. Implementation Phases

### Phase 1: Backend (persona store + API)
- Create `persona/store.py` with `PersonaStore`
- Migration logic (single file → directory + symlink)
- New API endpoints (`GET/POST/DELETE /api/personas`, `POST /activate`)
- Unify `PersonaManager` with `PersonaStore`
- Tests for CRUD, migration, symlink swap

### Phase 2: Frontend (persona switcher UI)
- Persona card row in `BeingSettings`
- `+` button to create new persona
- Card click to switch
- Delete button on non-active personas
- Form editing continues to work through existing `/settings/being` endpoint

### Phase 3: Polish
- Persona name in chat composer (quick-switch dropdown beside model pill — variant-gated per the 2026-08-30 note in §2 Q5: the model pill exists only on sysadmin variants)
- Persona-specific memory directories (wire `PersonaManager.get_memory_dir()`)
- Audit logging for persona switches
- Export/import persona files

---

## 5. What's NOT in Scope

- Multiple personas active simultaneously (one at a time, per user's spec)
- Per-persona variant switching (sysadmin vs home — stays global)
- Per-persona HA connection (one house, one connection)
- Per-persona security tiers (system-level trust boundary)
- Persona inheritance/templates (a new persona starts from defaults, not a copy of active)
- Federation of personas across instances

---

## 6. Key Files

| File | Role |
|------|------|
| `config/being_config.py` | `BeingConfig` dataclass, `load_being_config()`, `save_being_config()` |
| `persona/manager.py` | `PersonaManager` — state, switching, audit (to be unified with store) |
| `persona/store.py` (new) | `PersonaStore` — directory CRUD, symlink management, migration |
| `dashboard/routes/persona.py` | API endpoints for persona CRUD + switching |
| `dashboard/routes/settings.py` | `GET/POST /settings/being` — continues to work through symlink |
| `dashboard/routes/agent.py` | `_resolve_turn_model()` — reads being.yml per-turn (no change) |
| `prompts/agent_prompts.py` | `reload_personality()` — re-reads being.yml (no change) |
| `dashboard/frontend/src/pages/Settings.tsx` | `BeingSettings` component — add persona card row |

---

## 7. Open Questions for Design Review

1. **Persona card layout:** Horizontal scroll, grid, or dropdown? How many personas before it gets unwieldy?
2. **New persona creation flow:** Modal prompt for name? Or inline input? Should it offer to copy from an existing persona?
3. **Persona switch confirmation:** Should switching require confirmation (like "Switch to Work Halbert?"), or instant?
4. **Chat composer integration:** Should the persona name appear in the composer header? Should there be a quick-switch?
5. **Persona icons/avatars:** Should each persona have an icon or color? The old PersonaManager used emoji — we're emoji-free per project rules.
6. **Memory isolation:** Should each persona get its own memory directory from the start, or is that Phase 3?
7. **Naming collision:** `name` in BeingConfig is the computer's name ("Halbert"). The persona also needs a display name ("Work Halbert"). Are these the same field, or separate? If separate, what's the persona-level field called?
