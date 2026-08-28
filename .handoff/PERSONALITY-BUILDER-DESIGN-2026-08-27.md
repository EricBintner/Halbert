# Halbert Personality Builder — Design Document (v3, Branch-Aware)

**Date:** 2026-08-27  
**Status:** Revised after codebase scrutiny + branch/worktree audit  
**Supersedes:** v1 and v2 (same date) — see §7 for v1 corrections, §8 for v2 corrections

---

## 1. Executive Summary

Halbert's persona system is a 3-option enum (IT_ADMIN / FRIEND / CUSTOM) with hardcoded prompts. CUSTOM has been disabled since Phase 4. The personality work was spun into Haloysius (framework), reintegrated at the cognition/memory layer, but **never wired to the prompt/personality layer**. Haloysius has a rich personality system (Big Five, archetypes, prompt generation) that is framework-agnostic and directly reusable.

This document maps what exists, identifies gaps, corrects v1/v2 errors, accounts for in-flight branch work, and proposes a minimal personality builder that extends `BeingConfig` with personality fields, reuses Haloysius modules, and themes archetypes for sysadmin context.

---

## 1A. Branch & Worktree Audit (NEW in v3)

**Critical context:** The v1/v2 design was written while on branch `feat/role-scoped-skills`, which is **behind main** and lacks the continuous-conversation merge. The following in-flight work affects the design:

### Active Branches

| Branch | Last Commit | Relevance |
|--------|-------------|-----------|
| `main` (bee17bf) | 28 min ago | Has Plan A (continuous-conversation) merge. **Source of truth for this design.** |
| `feat/role-scoped-skills` (4c7841d) | 7 hrs ago | Current worktree. Added skills system (loader/matcher/composer/registry + 6 built-in skills). **Behind main** -- lacks Plan A. |
| `feat/continuous-conversation` (f48d937) | 6 hrs ago | Merged into main. Added threads, continuity prompts, receipt rendering. |
| `feat/agent-continuity` | 16 hrs ago | Has PERSONAS-RECONSIDER doc + extensive agent changes. |
| `feat/picker-followup` | 15 hrs ago | Model picker follow-ups. Has PERSONAS-RECONSIDER doc. |
| `fix/post-merge-followups` | 28 min ago | Post-merge fixes on main. |

### Active Worktrees

| Path | Branch |
|------|--------|
| `/Volumes/4TB-BAD/Halbert` | `feat/role-scoped-skills` (current) |
| `~/.config/superpowers/worktrees/Halbert/continuity-wiring` | `feat/continuity-wiring` |
| `~/.config/superpowers/worktrees/Halbert/continuous-conversation` | `feat/continuous-conversation` |
| `~/.config/superpowers/worktrees/Halbert/merge-plan-a` | `fix/post-merge-followups` |
| `~/.config/superpowers/worktrees/Halbert/model-picker-independent` | `feat/model-picker-independent` |

### Key Doc on Main: PERSONAS-RECONSIDER-WITH-HALOYSIUS-2026-08-27.md

This doc exists on `main` (commit bee17bf) but NOT on our current branch. It says:

1. **Personas panel is unreachable** -- `Settings.tsx:1864` has `<TabsContent value="personas">` but no matching `<TabsTrigger>`. Known, not an oversight.
2. **Persona backend API is still mounted** -- `app.py:283` includes `persona.router`.
3. **Founder position:** personas shelved, but Haloysius changes the calculus. The Being tab is where the computer's character now lives.
4. **Question:** is `persona/` the customisation layer the Being surface should stand on, or a second, disagreeing answer?
5. **Do NOT delete** `persona/`, its routes, or the Settings panel. **Do NOT add** a TabsTrigger. Leave until the Being/Haloysius personality question is answered.

**Implication for our design:** The design correctly extends BeingConfig (not persona/). But we must NOT touch `persona/manager.py` or `dashboard/routes/persona.py` at all -- the founder has explicitly fenced them off.

### Plan A (Continuous Conversation) Impact on `agent_prompts.py`

Main has **909 lines** in `agent_prompts.py`; our branch has **475 lines**. The delta is the continuous-conversation feature which added:

- `CONTINUITY_PREAMBLE` / `CONTINUITY_PREAMBLE_NO_TOOLS` -- voice-dependent continuity hints
- `_defang_continuity()` / `_defang_line_markers()` / `defang_system_text()` -- security: neutralize `<continuity>` tag injection in untrusted text
- `_continuity_section()` -- renders continuity hint block
- `render_recalled_receipts()` -- renders recalled thread receipts
- `RECALLED_SECTION_HEADER` / `RECALLED_MAX` / `_RECALLED_TITLE_CHARS` -- constants for receipt rendering
- Modified `build_planning_prompt()` and `build_response_prompt()` to accept `continuity` and `tools_supported` parameters

**The `build_system_prompt()` method itself is unchanged** on main vs our branch -- it still delegates to `PromptBuilder` or falls back to 3 hardcoded layers. Personality injection point is the same.

### Existing Being API on Main

Main already has `/api/settings/being` GET and POST endpoints (`settings.py:3064-3119`):
- `BeingConfigUpdate` Pydantic model with: voice, proactivity, purpose, quiet_hours, morning_report, category_overrides
- GET loads `being.yml` and returns `cfg.to_dict()`
- POST applies partial updates (only non-None fields), validates, saves

**Implication:** Personality fields should extend `BeingConfigUpdate` and the existing `/api/settings/being` endpoints, NOT create separate `/api/settings/personality` endpoints. This is simpler and aligns with the PERSONAS-RECONSIDER doc's guidance that the Being surface is where character lives.

### Skills System on `feat/role-scoped-skills`

Our current branch added a skills system (`halbert_core/skills/`):
- `loader.py`, `matcher.py`, `composer.py`, `registry.py` -- 4 modules
- 6 built-in domain skills: config-ops, discovery-ops, network-ops, security-ops, service-ops, storage-ops
- Skills compose into scope, budget, tier, and safety constraints

**Implication:** Skills are orthogonal to personality -- skills define *what* Halbert can do (scope/budget/tier), personality defines *how* Halbert communicates. Both feed into the prompt but at different layers. No conflict, but the skills composer may eventually need to pass personality_section through to the prompt builder alongside skill scope.

---

## 2. What Exists Today (Verified)

### 2.1 Halbert — Two Prompt Paths

**CRITICAL FINDING (missed in v1):** Halbert has **two separate prompt systems** that run in different code paths:

| Path | Used When | How It Works |
|------|-----------|-------------|
| **Primary: `PromptBuilder`** | `base_builder` is wired (the normal agent path) | `AgentPromptBuilder.build_system_prompt()` delegates to `PromptBuilder.build_prompt()` which loads XML components from `config/prompts/v2/base/` (identity.xml, objectives.xml, constraints.xml, output-format.xml, safety.xml). Component order: `["identity", "objectives", "constraints", "output-format", "safety"]`. |
| **Fallback: hardcoded layers** | `base_builder` is None or raises | `AgentPromptBuilder` assembles 3 hardcoded layers: identity (voice-dependent), capabilities, constraints. |

The wiring happens in `dashboard/routes/agent.py:114-142`:
- `PromptBuilder(prompt_loader)` is created and passed as `base_builder` to `AgentPromptBuilder`
- `BeingConfig.voice` is loaded once at agent init and passed to `AgentPromptBuilder`
- The agent is a singleton (`_agent_instance`)

**Also:** `PromptManager` (`model/prompt_manager.py`) is a **third, older system** used only by `scheduler/autonomous_tasks.py` and the `/api/settings/prompts` endpoint. It is NOT in the chat path. v1 incorrectly listed it as a chat-path integration point.

### 2.2 Component Inventory (Verified)

| Component | File | State |
|-----------|------|-------|
| PersonaManager | `halbert_core/persona/manager.py` | Enum: IT_ADMIN, FRIEND, CUSTOM (CUSTOM raises `PersonaSwitchError` at line 156-159). Memory dir switching. |
| AgentPromptBuilder | `halbert_core/prompts/agent_prompts.py` | Delegates to `PromptBuilder` when wired. Fallback: 3 hardcoded layers + voice. |
| PromptBuilder | `halbert_core/prompts/builder.py` | XML-component-based. `COMPONENT_ORDER = ["identity", "objectives", "constraints", "output-format", "safety"]`. No personality injection point. |
| PromptLoader | `halbert_core/prompts/loader.py` | Loads XML from `config/prompts/v2/base/`. File-cached. |
| identity.xml | `config/prompts/v2/base/identity.xml` | Static XML with `<voice>` section (tone, perspective, style). **Duplicates what personality would control.** |
| BeingConfig | `halbert_core/config/being_config.py` | `being.yml`: voice, proactivity, purpose, quiet_hours. No personality. Loaded once at agent init. `save_being_config` strips empty strings and None. |
| PromptManager | `halbert_core/model/prompt_manager.py` | Old hardcoded system. Chat path does NOT use this. Only scheduler + settings API. |
| Dashboard API | `halbert_core/dashboard/routes/persona.py` | status/list/switch/memory. No personality. |
| Haloysius integration | `halbert_core/integrations/` | Cognition/memory layer only. All imports are lazy (try/except or function-level). |

### 2.3 Haloysius Framework (Verified APIs)

| Component | API | Reusable? |
|-----------|-----|-----------|
| `PersonalityProfile` | `persona/personality.py` — dataclass with 5 floats (0.0-1.0), `from_dict()`, `generate_prompt_section()`, `get_linguistic_guidance()`, `get_behavioral_tendencies()`, `evolve()`. Has `__post_init__` validation (0.0-1.0 range). | **Yes — directly.** No companion content. |
| `PersonalityArchetype` | `persona/personality_presets.py` — dataclass: `id, name, icon, tagline, description, profile, communication_style, conflict_response, emotional_expression, example_dialogue, best_paired_with, famous_examples`. Has `generate_system_prompt_section()` that calls `profile.generate_prompt_section()` + behavioral descriptions. | **Mechanism yes.** `icon` is required (no default). `famous_examples` and `best_paired_with` have defaults (empty list). |
| `personality_builder` | `persona/personality_builder.py` — MBTI->Big Five conversion. | **Future, not MVP.** Adds complexity. |
| `PersonaConfig` | `persona/manager.py` — extensive dataclass with companion fields. | **Pattern only.** |
| `IdentityPromptBuilder` | `persona/identity.py` — 4-layer with "hidden human identity". | **Pattern only.** Machine != human. |

### 2.4 LinuxBrain

All `halley_core/persona/` files are re-export shims to Haloysius. Reference for consumer-app adaptation pattern only.

---

## 3. Gap Analysis

### 3.1 What Halbert Can't Do

1. No custom persona creation (CUSTOM disabled)
2. No personality customization (no Big Five, no archetype, no traits)
3. No tone-of-voice customization (voice mode = pronoun choice, not personality)
4. No custom system prompt (mentioned in code, no API/UI to set it)
5. No speech patterns or directives
6. No personality-to-prompt pipeline (Haloysius modules exist but unwired)

### 3.2 What NOT to Bring From Haloysius

- Hidden human identity layer (Halbert is a machine)
- Content level (sfw/romantic/nsfw)
- Visual identity / image generation
- LoRA adapter settings
- Roleplay mode / user persona
- Birth gender, orientation, birthplace
- Clothing/location state machines
- MBTI sliders (adds complexity, not MVP)
- Companion-style example dialogue (need sysadmin examples)

---

## 4. Scrutiny — v1 Errors Corrected

### 4.1 Wrong Prompt Stack Diagram

**v1 claimed:** A 7-layer stack with "Layer 3: Personality" between identity and capabilities.

**Reality:** The primary chat path uses `PromptBuilder` which assembles XML components in order `["identity", "objectives", "constraints", "output-format", "safety"]` + tools + dynamic context. There is no "Layer 3" slot. The fallback path has 3 hardcoded layers (identity, capabilities, constraints).

**Fix:** Personality must be injected into **both** paths:
- Primary: Insert as a new XML component or programmatic injection in `PromptBuilder.build_prompt()`
- Fallback: Insert between identity and capabilities in `AgentPromptBuilder` fallback path

### 4.2 Wrong Integration Point for PromptManager

**v1 claimed:** `model/prompt_manager.py` CUSTOM mode loads personality from BeingConfig.

**Reality:** `PromptManager` is not in the chat path. It's used by `scheduler/autonomous_tasks.py` and `/api/settings/prompts`. Wiring personality into it would only affect autonomous scheduled tasks, not interactive chat.

**Fix:** Remove `PromptManager` from integration points for MVP. It can be updated later for autonomous task personality.

### 4.3 Missed: Agent Singleton / Hot-Reload

**v1 missed:** The agent is a singleton created in `get_agent()`. `BeingConfig` is loaded once at init time. Changing personality via API would not take effect until agent restart.

**Fix:** Add a `reload_personality()` method on `AgentPromptBuilder` that re-reads `being.yml`. The existing `set_voice()` method (line 107-112) already proves this pattern was anticipated.

### 4.4 Missed: identity.xml Already Has Voice/Tone

**v1 missed:** `config/prompts/v2/base/identity.xml` has a `<voice>` section with `<tone>Technical, concise, helpful</tone>`, `<perspective>`, and `<style>`. This overlaps with what personality would control.

**Fix:** The personality layer is **additive to identity.xml**, not a replacement. Identity.xml defines *who* Halbert is (role, expertise, priorities). Personality defines *how* Halbert communicates (tone, style, behavioral traits). The static `<voice>` section in identity.xml becomes the default; personality layer overrides/augments it when customized.

### 4.5 Missed: PersonalityArchetype.icon Is Required

**v1 missed:** `PersonalityArchetype.icon: str` has no default value. Sysadmin archetypes must provide icons.

**Fix:** Use text-based icons (not emoji per user rules): e.g., `"shield"` for Sentinel, `"book"` for Mentor. Or use the existing icon font system if one exists in the dashboard.

### 4.6 Missed: Haloysius Imports Must Be Lazy

**v1 missed:** All Haloysius imports in Halbert are lazy (function-level or try/except). Haloysius is optional at import time.

**Fix:** Personality imports must follow the same pattern:
```python
def _get_personality_prompt(being_cfg) -> str:
    try:
        from haloysius.persona.personality import PersonalityProfile
        from haloysius.persona.personality_presets import PersonalityArchetype
        ...
    except ImportError:
        logger.warning("Haloysius not available, personality disabled")
        return ""
```

### 4.7 Missed: save_being_config Strips Empty Strings

**v1 missed:** `save_being_config` line 162 strips `None` and `""` values. `custom_personality_prompt: ""` would be stripped (fine -- defaults to empty). But this means the field won't appear in YAML until set, which is correct behavior.

**Fix:** No change needed. Document as expected behavior.

### 4.8 Persona vs Personality -- Orthogonal Concerns

**v1 conflated:** PersonaManager (IT_ADMIN/FRIEND/CUSTOM) manages **memory isolation and role**. BeingConfig personality manages **communication style**. These are orthogonal.

**Fix:** Personality is global (being.yml), not per-persona. The CUSTOM persona slot is a separate concern -- it could use personality from being.yml, but enabling it is not required for personality to work. Personality applies to ALL personas. Remove "enable CUSTOM persona" from Phase 1.

---

## 5. Corrected Design

### 5.1 Architecture

```
PRIMARY CHAT PATH (PromptBuilder):
  config/prompts/v2/base/identity.xml   -> who Halbert is
  config/prompts/v2/base/objectives.xml -> what Halbert does
  -- NEW: personality injection point --  -> how Halbert communicates
  config/prompts/v2/base/constraints.xml -> rules
  config/prompts/v2/base/output-format.xml -> format
  config/prompts/v2/base/safety.xml     -> immutable safety
  + tools, model overrides, tier, dynamic context

FALLBACK PATH (AgentPromptBuilder hardcoded):
  Layer 1: Identity (voice-dependent)
  -- NEW: personality injection point --
  Layer 2: Capabilities
  Layer 3: Constraints

AUTONOMOUS PATH (PromptManager -- NOT in MVP scope):
  base_safety + mode_layer + persona_layer
  (future: personality could augment persona_layer)
```

### 5.2 Data Model -- Extended BeingConfig

```python
@dataclass
class BeingConfig:
    # --- Existing ---
    voice: str = "first_person"
    proactivity: str = "balanced"
    purpose: str = ""
    quiet_hours: Optional[Dict[str, str]] = None
    morning_report: Optional[Dict[str, Any]] = None
    category_overrides: Dict[str, str] = field(default_factory=dict)
    timezone: str = "local"

    # --- NEW: Personality ---
    personality_profile: Dict[str, float] = field(default_factory=lambda: {
        "openness": 0.5, "conscientiousness": 0.5,
        "extraversion": 0.5, "agreeableness": 0.5, "neuroticism": 0.5,
    })
    archetype_id: Optional[str] = None
    tone_descriptors: List[str] = field(default_factory=list)
    speech_patterns: List[str] = field(default_factory=list)
    directives: List[str] = field(default_factory=list)
    custom_personality_prompt: str = ""  # escape hatch
```

`from_dict()` already filters via `cls.__dataclass_fields__`, so new fields are automatically picked up from YAML. `save_being_config` strips None/empty -- expected behavior.

### 5.3 Sysadmin Archetypes

5 presets using `PersonalityArchetype` structure. Must include `icon` field.

| ID | Name | Icon | Tagline | Big Five |
|----|------|------|---------|----------|
| `sentinel` | The Sentinel | `shield` | Vigilant, precise, unflappable | C:0.90 E:0.30 N:0.15 |
| `mentor` | The Mentor | `book` | Patient, explanatory, encouraging | O:0.70 C:0.75 A:0.80 |
| `surgeon` | The Surgeon | `scalpel` | Clinical, fast, exact | C:0.85 A:0.35 E:0.40 |
| `architect` | The Architect | `compass` | Strategic, holistic, design-oriented | O:0.85 C:0.80 |
| `comedian` | The Witty Operator | `sparkle` | Dry humor, technically sharp | E:0.75 A:0.65 |

Each includes: `communication_style`, `conflict_response`, `emotional_expression`, `example_dialogue` (sysadmin-themed). `famous_examples` and `best_paired_with` left as empty lists.

### 5.4 Prompt Generation Pipeline

New function `generate_personality_section(being_cfg) -> str` in a new module `halbert_core/persona/personality_prompt.py`:

```
1. If custom_personality_prompt non-empty -> return it directly
2. Else if archetype_id set -> load archetype, call generate_system_prompt_section()
   -> append tone_descriptors, speech_patterns, directives
3. Else if personality_profile has any non-0.5 values -> PersonalityProfile.from_dict()
   -> generate_prompt_section() -> append tone/speech/directives
4. Else -> return "" (no personality layer, current behavior)
```

### 5.5 Injection -- Primary Path (PromptBuilder)

Add a `personality_section` parameter to `PromptBuilder.build_prompt()`:

```python
def build_prompt(self, tier, system_context=None, user_prefs=None,
                 project_context=None, rag_results=None,
                 conversation_history=None, model_name=None,
                 personality_section=None):  # NEW
    parts = []
    parts.append(self.build_base_prompt(core_tools_only=(tier=="guide")))
    # ... model overrides, tier additions ...
    if personality_section:
        parts.append(f"<personality>\n{personality_section}\n</personality>")
    # ... system_context, user_prefs, etc.
```

Then in `AgentPromptBuilder.build_system_prompt()`, generate the personality section from BeingConfig and pass it through.

### 5.6 Injection -- Fallback Path (AgentPromptBuilder)

In the fallback branch (line 182-192), insert personality between identity and capabilities:

```python
parts = [self._get_identity()]
personality = self._generate_personality()
if personality:
    parts.append(personality)
parts.append(self.LAYER_2_CAPABILITIES)
parts.append(self.LAYER_3_CONSTRAINTS)
```

### 5.7 Hot-Reload

Add to `AgentPromptBuilder`:

```python
def reload_personality(self):
    """Re-read being.yml for personality changes. Called by API after update."""
    try:
        from ..config.being_config import load_being_config
        self._being_cfg = load_being_config()
        self.set_voice(self._being_cfg.voice)
    except Exception as e:
        logger.warning(f"Personality reload failed: {e}")
```

The API endpoint calls `agent.prompt_builder.reload_personality()` after saving.

### 5.8 API Endpoints (Revised in v3)

**v2 proposed separate `/api/settings/personality` endpoints. v3 corrects this:** the Being API already exists at `/api/settings/being` on main. Personality fields should extend the existing endpoints.

**Extend `BeingConfigUpdate`** (Pydantic model in `settings.py:3067`):

```python
class BeingConfigUpdate(BaseModel):
    # --- Existing ---
    voice: Optional[str] = None
    proactivity: Optional[str] = None
    purpose: Optional[str] = None
    quiet_hours: Optional[Dict[str, str]] = None
    morning_report: Optional[Dict[str, Any]] = None
    category_overrides: Optional[Dict[str, str]] = None
    # --- NEW: Personality ---
    personality_profile: Optional[Dict[str, float]] = None
    archetype_id: Optional[str] = None
    tone_descriptors: Optional[List[str]] = None
    speech_patterns: Optional[List[str]] = None
    directives: Optional[List[str]] = None
    custom_personality_prompt: Optional[str] = None
```

**Extend existing `POST /api/settings/being`** to handle the new fields (same partial-update pattern).

**New endpoints** (only for read-only personality operations that don't fit the being update pattern):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings/being` | Already returns full config -- personality fields included automatically once BeingConfig is extended |
| POST | `/api/settings/being` | Already does partial update -- personality fields included once BeingConfigUpdate is extended |
| GET | `/api/settings/personality/archetypes` | List sysadmin archetypes (new, read-only) |
| GET | `/api/settings/personality/archetypes/{id}` | Specific archetype (new, read-only) |
| POST | `/api/settings/personality/preview` | Dry-run: returns generated prompt section (new) |

**Reset** can be done via `POST /api/settings/being` with default values (all 0.5, no archetype). No separate reset endpoint needed.

### 5.9 What Stays Unchanged

- Base safety prompt (immutable)
- Voice modes (first_person / the_computer / hybrid) -- orthogonal to personality
- Haloysius cognition integration (advance_turn, memory adapter)
- Proactivity, quiet hours, morning report
- All existing IT_ADMIN / FRIEND personas and their memory isolation
- `PromptManager` (autonomous path) -- not modified in MVP
- **`persona/manager.py`, `dashboard/routes/persona.py`, Settings.tsx personas panel** -- explicitly fenced off by founder per PERSONAS-RECONSIDER-WITH-HALOYSIUS-2026-08-27.md. Do NOT touch.
- **Continuous-conversation features** (threads, continuity prompts, receipt rendering, defang security) -- personality is additive, must not break these.

---

## 6. Implementation Strategy (Revised in v3)

### Prerequisite: Branch Alignment

**All implementation must be based on `main`, not `feat/role-scoped-skills`.** The current branch lacks Plan A (continuous conversation). Options:
1. Branch from `main` for personality work
2. Rebase `feat/role-scoped-skills` onto `main` first (brings skills + continuity together)
3. Wait for skills branch to merge to main, then branch

### Phase 1: Core Personality (Backend) -- ~4 files, ~200 LOC

**Step 1.1: Extend BeingConfig** (`config/being_config.py`)
- Add 5 new fields to dataclass
- Add validation: personality_profile values in 0.0-1.0, archetype_id in known set
- ~30 LOC

**Step 1.2: Create sysadmin archetypes** (`halbert_core/persona/archetypes.py`)
- New file: 5 `PersonalityArchetype` instances using Haloysius dataclass
- `get_archetype(id)`, `list_archetypes()` utility functions
- Lazy import of `PersonalityArchetype` from Haloysius
- ~120 LOC

**Step 1.3: Create personality prompt generator** (`halbert_core/persona/personality_prompt.py`)
- New file: `generate_personality_section(being_cfg) -> str`
- Implements the 4-step pipeline (custom -> archetype -> sliders -> empty)
- Lazy imports of `PersonalityProfile` from Haloysius
- ~60 LOC

**Step 1.4: Wire into AgentPromptBuilder** (`prompts/agent_prompts.py`)
- Add `_being_cfg` attribute (loaded in `__init__`)
- Add `_generate_personality()` method that calls `generate_personality_section()`
- Add `reload_personality()` method
- Inject into both primary (PromptBuilder) and fallback paths
- Add `personality_section` parameter to `PromptBuilder.build_prompt()` call
- **Must be done on main branch** -- the file on main has 909 lines with continuity features that must be preserved
- ~40 LOC in agent_prompts.py, ~5 LOC in builder.py

**Step 1.5: Wire PromptBuilder** (`prompts/builder.py`)
- Add `personality_section` optional parameter to `build_prompt()`
- Insert as `<personality>` XML block after tier additions, before dynamic context
- ~5 LOC

**Step 1.6: Extend existing Being API** (`dashboard/routes/settings.py`)
- Extend `BeingConfigUpdate` Pydantic model with personality fields
- Extend `POST /api/settings/being` to apply personality updates
- Add 3 new read-only endpoints: archetypes list, archetype detail, preview
- PUT triggers `reload_personality()` on the agent singleton
- ~60 LOC (less than v2's 100 LOC because we extend existing endpoints)

**Step 1.7: Wire BeingConfig into agent init** (`dashboard/routes/agent.py`)
- Store full `being_cfg` (not just `voice`) on `AgentPromptBuilder`
- ~3 LOC change

**Deliverable:** Personality config via existing Being API, affects chat prompts, testable with curl.

### Phase 2: Polish -- ~3 files

- Prompt preview endpoint (dry-run generation)
- Archetype blending (mix two archetypes via `blend_archetypes()` from Haloysius)
- Update `PromptManager` CUSTOM mode for autonomous tasks (optional)
- Tests: unit test personality generation, integration test API -> prompt
- **Skills integration:** if skills branch is merged, ensure skills composer and personality coexist in prompt

### Phase 3: UI (Design Team)

- Extend existing Being tab in Settings.tsx with personality controls
- Archetype picker with descriptions
- Big Five sliders with live preview
- Tone/directives editor
- Custom prompt textarea (escape hatch)
- **Do NOT add personas tab trigger** -- per PERSONAS-RECONSIDER doc

### Implementation Order (Dependency Chain)

```
Prerequisite: branch from main (or rebase skills onto main)

1.1 BeingConfig fields
  | (depends on)
1.2 Archetypes module <-- depends on Haloysius PersonalityArchetype
  |
1.3 Personality prompt generator <-- depends on 1.1 + 1.2
  |
1.4 AgentPromptBuilder wiring <-- depends on 1.3
  | (parallel with)
1.5 PromptBuilder parameter <-- no dependency on 1.4
  |
1.7 Agent init wiring <-- depends on 1.4
  |
1.6 Extend Being API <-- depends on 1.1 + 1.7
```

1.1, 1.2, and 1.5 can be done in parallel. 1.3 depends on 1.1+1.2. 1.4 depends on 1.3+1.5. 1.6 is last.

---

## 7. v1 -> v2 Correction Summary

| # | v1 Claim | Reality | Fix |
|---|----------|---------|-----|
| 1 | 7-layer prompt stack | Primary path: XML components via PromptBuilder. Fallback: 3 hardcoded layers. | Inject into both paths separately |
| 2 | PromptManager is chat-path integration point | PromptManager is only used by scheduler, not chat | Remove from MVP integration points |
| 3 | No mention of agent singleton / hot-reload | Agent is singleton, BeingConfig loaded once at init | Add `reload_personality()` method |
| 4 | No mention of identity.xml voice section | identity.xml has static `<voice>` with tone/style | Personality is additive, not replacement |
| 5 | Archetypes don't specify icons | `PersonalityArchetype.icon` is required (no default) | Add icon field to each archetype |
| 6 | Implies direct Haloysius imports | All Haloysius imports in Halbert are lazy | Use lazy imports throughout |
| 7 | CUSTOM persona enabling is Phase 1 | CUSTOM is orthogonal to personality | Move to Phase 2, personality is global |
| 8 | "16 archetypes" in Haloysius | Actually 12 archetypes in personality_presets.py | Corrected count (we create 5 new anyway) |

---

## 8. v2 -> v3 Correction Summary (Branch Audit)

| # | v2 Claim | Reality (from branch audit) | Fix |
|---|----------|---------|-----|
| 1 | Design based on `feat/role-scoped-skills` code | Branch is behind main; main has Plan A (continuous conversation) with 909-line `agent_prompts.py` vs 475 on our branch | All implementation must branch from `main` |
| 2 | Separate `/api/settings/personality` endpoints | `/api/settings/being` GET/POST already exists on main with `BeingConfigUpdate` model | Extend existing Being API instead of creating new endpoints |
| 3 | No mention of PERSONAS-RECONSIDER doc | Doc on main explicitly fences off `persona/` from changes | Added to "What Stays Unchanged" -- do NOT touch persona/ |
| 4 | No mention of continuous-conversation features | Main has continuity prompts, defang security, receipt rendering, thread management | Added to "What Stays Unchanged" -- must not break these |
| 5 | No mention of skills system | `feat/role-scoped-skills` added skills loader/matcher/composer/registry + 6 built-in skills | Documented as orthogonal; Phase 2 includes skills integration check |
| 6 | No branch alignment prerequisite | Current branch lacks Plan A | Added prerequisite section in implementation strategy |
| 7 | UI: "Personality settings panel in dashboard" | Being tab already exists in Settings.tsx on main | Phase 3 changed to "Extend existing Being tab" |
| 8 | Phase 3: no mention of personas tab | PERSONAS-RECONSIDER doc says do NOT add TabsTrigger | Added explicit warning in Phase 3 |

---

## 9. Open Questions for Design Team

1. **Archetype count** -- 5 enough for MVP, or add more?
2. **Per-persona personality** -- global (being.yml) is MVP. Per-persona would require storing personality in PersonaState or a per-persona config file. Future enhancement?
3. **Preset sharing** -- allow import/export of personality configs (YAML files)?
4. **Personality evolution** -- Haloysius has `PersonalityProfile.evolve()` that shifts traits based on experience. Enable for Halbert?
5. **Dashboard placement** -- resolved: extend the existing Being tab in Settings.tsx (per PERSONAS-RECONSIDER doc guidance).
6. **identity.xml voice section** -- should personality layer override the static `<tone>`/`<style>` in identity.xml when customized, or always append?
7. **Autonomous task personality** -- should scheduled tasks (PromptManager path) also pick up personality? MVP says no; confirm.
