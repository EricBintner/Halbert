# Personality Builder Phase 3 — UI Design Specification (Radical Simplicity)

**Date:** 2026-08-27  
**Status:** Approved Realignment (Anti-Overengineering Spec)  
**Supersedes:** All previous drafts  
**Design Ethos:** *Apple-like restraint, zero theatre.* No goofy names, no clinical psychology sliders, no multi-card sprawl. Just a clean, dignified character configuration that takes 5 seconds to set and leaves room for future custom conversation models.  
**Target Surface:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` (`BeingSettings`, inside `<TabsContent value="being">`)  

---

## 1. What We Dropped (The Anti-Overengineering Ledger)

Per founder direction, we have stripped out the bloat:
- ❌ **No "Demeanor Tiles" or theatrical cards**: No "The Sentinel", "The Surgeon", "The Witty Operator", etc.
- ❌ **No Big Five sliders**: No clinical psychology dials (*Neuroticism*, *Conscientiousness*, *Openness*).
- ❌ **No Archetype Blending**: No dual dropdowns, ratio sliders, or mathematical interpolations.
- ❌ **No Tag / List Builders**: No tone-descriptor chip inputs, speech-pattern list managers, or directive builders.
- ❌ **No Raw Prompt Inspectors**: No XML `<personality>` inspection panels cluttering the settings tab.

---

## 2. The Core Surface: Single Clean "Character" Card

Everything lives in **one simple, beautifully proportioned Card** inside the Being tab:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Character                                                               │
│ Name, communication style, and custom instructions for your computer.   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Name                                                                    │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Halbert                                                             │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ What you call your computer.                                            │
│                                                                         │
│ Communication Style                                                     │
│ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│ │  Concise  │ │ Balanced  │ │ Detailed  │ │Analytical │ │  Casual   │   │
│ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
│ Simple 5-way selector. Default: Balanced.                               │
│                                                                         │
│ Voice Presentation                                                      │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                   │
│ │  Not Defined  │ │     Male      │ │    Female     │                   │
│ └───────────────┘ └───────────────┘ └───────────────┘                   │
│ How the voice is characterized in conversation.                         │
│                                                                         │
│ Conversation Model (Optional / Future)                                  │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Default Agent Model                                               ▾ │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ Use the system default, or assign a fine-tuned model to this persona.   │
│                                                                         │
│ Custom Instructions (Optional)                                          │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Keep answers under 3 sentences unless I ask for a deep dive.        │ │
│ │ Always show the full shell command before asking for confirmation.  │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ Plain text instructions injected directly into system guidance.         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Field Specifications & Semantics

### 3.1 Computer / Persona Name
- **Label:** `Name`
- **Component:** `<Input defaultValue={config.name || aiName || 'Halbert'} />`
- **Behavior:**
  - Persists to `being.yml` (and syncs with system `ai_name` in `preferences.yml`).
  - When the agent responds, it knows its given name.

### 3.2 Communication Style (5 Clean Types)
Five clear, unadorned styles. No paragraphs, no taglines, no theatrical lore.

| Style Key | Label | Under-the-Hood Trait Mapping | Behavioral Essence |
|---|---|---|---|
| `concise` | **Concise** | High Conscientiousness, Low Extraversion | Fast, minimal words, imperative commands. Diagnoses, fixes, verifies. |
| `balanced` | **Balanced** | Balanced traits (Default) | Standard sysadmin presence. Clear, calm, factual, helpful. |
| `detailed` | **Detailed** | High Openness, High Agreeableness | Explanatory, instructional. Explains why before acting. |
| `analytical` | **Analytical** | High Openness, High Conscientiousness | Systems-focused, design-oriented, addresses root causes. |
| `casual` | **Casual** | High Extraversion, Moderate Agreeableness | Approachable, light touch, understated, conversational. |

- **UI Component:** Clean horizontal button group (`grid grid-cols-2 sm:grid-cols-5 gap-2`):
  - Active: `variant="default"`
  - Inactive: `variant="outline"`
  - Saves to `being.yml: archetype_id` (or `communication_style`).

### 3.3 Voice Presentation (Gender / Presence)
Modeled directly after Apple Siri Voice settings:
- **Options:**
  - `Not Defined` (Default neutral computer identity)
  - `Male`
  - `Female`
- **UI Component:** 3-button toggle group (`grid grid-cols-3 gap-2`).
- **Under-the-hood:** Injects subtle gender presentation guidance into prompt identity only when explicitly selected (`male` or `female`). When `not_defined`, zero gender assumptions are made.

### 3.4 Conversation Model (Incoming UI Slot)
Prepares the interface for fine-tuned or domain-specific conversational models (e.g. models trained on comedians, domain experts, or specific open weights):
- **Label:** `Conversation Model`
- **UI Component:** `<Select>` dropdown:
  - Option 1: `Default (System Agent Model)` — active default.
  - Option 2: `[Custom Model Path / Identifier...]` (disabled or text input fallback).
- **Subtext:** *"Assign a specific fine-tuned model for this persona, or follow the system default."*
- **Status:** UI slot designed now; backend execution hook wired when multi-model routing lands.

### 3.5 Custom Instructions (Escape Hatch & User Directives)
- **Label:** `Custom Instructions`
- **Component:** Textarea (`min-h-[100px] font-sans text-sm rounded-md border border-input bg-background px-3 py-2`).
- **Placeholder:** *"e.g. Always show the full shell command before asking for confirmation. Keep status updates brief."*
- **Saves to:** `being.yml: custom_personality_prompt` (or directives string).

---

## 4. Why This Fits Halbert's Architecture

1. **Zero Merge Risk with Plan B:** Plan B (`feat/plan-b-terminals`) is building terminal blocks, watched shell, tasks columns, and status lights. This character card touches only `Settings.tsx` within `BeingSettings`.
2. **Tokens & Olivetti Compliance:** Uses only standard tokens (`bg-card`, `text-card-foreground`, `border-input`, `text-muted-foreground`, `bg-background`). Passes `python3 scripts/check_literal_colors.py --check` with zero new literal color classes.
3. **No External Dependencies:** Uses standard React state, native inputs, and existing Shadcn/Radix components already present in `package.json`.
4. **Clean Backend Mapping:**
   - Name → `BeingConfig.name` / `preferences.yml: ai_name`
   - Style → `BeingConfig.archetype_id` (`concise`, `balanced`, `detailed`, `analytical`, `casual`)
   - Voice Presentation → `BeingConfig.voice_presentation` (`not_defined`, `male`, `female`)
   - Custom Instructions → `BeingConfig.custom_personality_prompt`
   - Model → `BeingConfig.model` (deferred backend execution)

---

## 5. Summary of the User Experience

- **Before:** A 6-card sprawling laboratory of Big Five psychology dials, archetype blending sliders, tag editors, and XML inspectors.
- **After:** A single, dignified 6-inch card. You set your computer's name, choose how it talks in one click (Concise, Balanced, Detailed, Analytical, Casual), pick a voice presentation, optionally type any house rules, and you are done.
