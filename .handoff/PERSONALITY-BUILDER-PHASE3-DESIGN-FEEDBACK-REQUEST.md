# Personality Builder Phase 3 -- Design Feedback Request

**Date:** 2026-08-27
**From:** Implementation session (feat/personality-builder worktree)
**To:** Design feedback session
**Status:** Phase 1 COMPLETE, Phase 2 IN PROGRESS, Phase 3 needs UI design review

---

## Context

The Personality Builder implements Big Five personality traits and sysadmin-themed
archetypes for Halbert, extending the existing `BeingConfig` / Being API rather than
creating separate endpoints. Phase 1 is committed at `7d69659` on branch
`feat/personality-builder` in worktree
`~/.config/superpowers/worktrees/Halbert/personality-builder`.

**Design doc:** `/Volumes/4TB-BAD/Halbert/.handoff/PERSONALITY-BUILDER-DESIGN-2026-08-27.md` (v3)

**Critical constraint:** The `persona/` system (`persona/manager.py`,
`dashboard/routes/persona.py`, Settings.tsx personas `TabsContent`) is explicitly
fenced off per `PERSONAS-RECONSIDER-WITH-HALOYSIUS-2026-08-27.md`. Do NOT touch it.
Personality extends the existing **Being tab** only.

---

## What Phase 1 Delivered (Backend -- DONE)

### Data Model (`being_config.py`)
`BeingConfig` now has 6 personality fields:
- `personality_profile: Dict[str, float]` -- Big Five traits (0.0-1.0 each)
- `archetype_id: Optional[str]` -- references a sysadmin archetype
- `tone_descriptors: List[str]` -- e.g. ["calm", "precise"]
- `speech_patterns: List[str]` -- e.g. ["Uses bullet points for status"]
- `directives: List[str]` -- e.g. ["Always show the command before running it."]
- `custom_personality_prompt: str` -- escape hatch, replaces generated layer

### 5 Sysadmin Archetypes (`persona/archetypes.py`)
| ID | Name | Icon | Tagline |
|----|------|------|---------|
| `sentinel` | The Sentinel | shield | Vigilant, precise, unflappable |
| `mentor` | The Mentor | book | Patient, explanatory, encouraging |
| `surgeon` | The Surgeon | scalpel | Clinical, fast, exact |
| `architect` | The Architect | compass | Strategic, holistic, design-oriented |
| `comedian` | The Witty Operator | sparkle | Dry humor, technically sharp |

Each archetype has: Big Five profile, communication_style, conflict_response,
emotional_expression, example_dialogue. Uses Haloysius `PersonalityArchetype` with
lazy imports.

### Prompt Injection (`agent_prompts.py`, `builder.py`)
- **Primary path:** `PromptBuilder.build_prompt()` accepts `personality_section` param,
  injects as `<personality>` XML block after tier additions, before dynamic context.
- **Fallback path:** `AgentPromptBuilder` inserts personality between identity and
  capabilities in hardcoded layers.
- `reload_personality()` method on `AgentPromptBuilder` for hot-reload via API.

### API Endpoints (`settings.py`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/settings/being` | Returns config including personality fields |
| POST | `/api/settings/being` | Updates personality fields, hot-reloads agent |
| GET | `/api/settings/personality/archetypes` | Lists all 5 archetypes |
| GET | `/api/settings/personality/archetypes/{id}` | Single archetype detail |
| POST | `/api/settings/personality/preview` | Dry-run: generates section without saving |

### Tests
15 new tests in `test_personality_builder.py`, all passing.
24 existing continuity tests still pass (no regressions).

---

## What Phase 2 Is Delivering (Backend Polish -- IN PROGRESS)

1. **Archetype blending** -- mix two archetypes with a ratio (0.0-1.0)
2. **PromptManager CUSTOM mode** -- wire personality into autonomous path
3. **Blend API endpoint** -- `POST /api/settings/personality/blend`
4. **Additional tests** for blending and PromptManager integration

---

## What Phase 3 Needs (UI -- DESIGN FEEDBACK REQUESTED)

### Target File
`halbert_core/dashboard/frontend/src/pages/Settings.tsx`
- The `BeingSettings` component (line 72) renders inside the existing "Being" tab
- The Being tab is at `TabsContent value="being"` (line 2419)
- Current Being tab UI: voice selector (3 buttons), proactivity dial (4 buttons),
  purpose textarea, quiet hours, morning report, category overrides

### What Needs Designing

**1. Archetype Picker**
- 5 archetypes, each with: name, icon, tagline, description, communication style
- Should show as cards or a grid; selecting one sets `archetype_id`
- Need to fetch from `GET /api/settings/personality/archetypes`
- When selected, should show a preview of the personality section via
  `POST /api/settings/personality/preview`
- "None" option to clear archetype

**2. Big Five Sliders**
- 5 sliders: Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism
- Range 0.0-1.0, step 0.05
- Labels: low / high descriptors at each end (e.g. "Curious" vs "Conventional" for Openness)
- When archetype is selected, sliders should reflect the archetype's profile
- Sliders should be editable independently (overrides archetype defaults)
- Live preview of generated personality section

**3. Tone & Directives Editor**
- `tone_descriptors`: tag input (add/remove chips, e.g. "calm", "precise", "dry")
- `speech_patterns`: list of strings (add/remove, textarea per item)
- `directives`: list of strings (add/remove, textarea per item)

**4. Custom Prompt Escape Hatch**
- `custom_personality_prompt`: monospace textarea
- When non-empty, it replaces the entire generated personality layer
- UI should make this clear: "This overrides archetype and trait settings"
- Toggle/expand to reveal

**5. Archetype Blending UI (if Phase 2 lands)**
- Select two archetypes + a ratio slider
- Shows blended Big Five values
- Saves blended profile to `personality_profile` (not archetype_id)

**6. Live Preview Panel**
- Shows the generated personality prompt section in real-time
- Updates as user changes sliders, selects archetypes, edits tone/directives
- Uses `POST /api/settings/personality/preview` endpoint
- Monospace, read-only, collapsible

### Design Constraints

- **Do NOT add a "personas" tab trigger.** The personas `TabsContent` exists at line
  1864 but has no `TabsTrigger` -- this is intentional per founder guidance.
- **Extend the existing Being tab**, do not create a new tab.
- Use existing UI components: Card, Button, Input, Label, Select, Badge.
- Icons from `lucide-react` (already imported).
- The `BeingSettings` component already has `saveConfig()` and `loadConfig()` patterns.
- No emojis in UI (per project rules). Use icon fonts.

### Questions for Design Session

1. Should the archetype picker and Big Five sliders be in the same card, or separate cards?
2. Should the live preview be a collapsible section at the bottom, or a side panel?
3. Should archetype selection auto-populate sliders, or should sliders be independent with archetype as a "preset" button?
4. How should blending be exposed -- advanced section, or first-class?
5. Should the custom prompt textarea be collapsed by default with a "Use custom prompt instead" toggle?
6. Mobile considerations -- the Being tab currently uses grid layouts that may need stacking.

### API Contract for UI

```typescript
// GET /api/settings/being -> { status: "ok", config: { ...personality fields... } }
// POST /api/settings/being -> { status: "ok", config: { ...updated... } }
// GET /api/settings/personality/archetypes -> { status: "ok", archetypes: [...], available: bool }
// GET /api/settings/personality/archetypes/{id} -> { status: "ok", archetype: {...} }
// POST /api/settings/personality/preview -> { status: "ok", section: string }
// POST /api/settings/personality/blend -> { status: "ok", profile: {...} }  (Phase 2)
```

### Archetype Shape (from API)

```typescript
interface Archetype {
  id: string;
  name: string;
  icon: string;  // lucide icon name
  tagline: string;
  description: string;
  profile: {
    openness: number;
    conscientiousness: number;
    extraversion: number;
    agreeableness: number;
    neuroticism: number;
  };
  communication_style: string;
  conflict_response: string;
  emotional_expression: string;
  example_dialogue: string[];
}
```

---

## How to Review

1. Read the design doc: `/Volumes/4TB-BAD/Halbert/.handoff/PERSONALITY-BUILDER-DESIGN-2026-08-27.md`
2. Read the PERSONAS-RECONSIDER doc: `/Volumes/4TB-BAD/Halbert/.handoff/PERSONAS-RECONSIDER-WITH-HALOYSIUS-2026-08-27.md`
3. Browse the worktree: `~/.config/superpowers/worktrees/Halbert/personality-builder`
4. Read `BeingSettings` component: `halbert_core/dashboard/frontend/src/pages/Settings.tsx` (line 72)
5. Draft a UI design spec for Phase 3, answering the questions above
6. Write the spec to: `/Volumes/4TB-BAD/Halbert/.handoff/PERSONALITY-BUILDER-PHASE3-UI-SPEC.md`
