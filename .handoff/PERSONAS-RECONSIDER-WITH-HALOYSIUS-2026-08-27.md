# Personas — deferred, and worth reconsidering now that Haloysius exists

**Date:** 2026-08-27 · **Status:** NOT being worked on. Founder decision to revisit later.

Raised because the post-Plan-A review found `Settings.tsx:1864`'s
`<TabsContent value="personas">` — roughly 150 lines — has **no matching
`TabsTrigger`**, so nothing can select it. That was already true before the
Plan A merge; the merge neither caused it nor newly hid it.

## What is actually still there

Personas was made legacy, but it was never removed, and more of it is live than
the dead panel suggests:

| Piece | State |
|---|---|
| `halbert_core/persona/` — `manager.py`, `context_detector.py`, `memory_purge.py` | present |
| `PersonaManager`, `Persona`, `PersonaSwitchError`, `MemoryPurge` | exported |
| `dashboard/routes/persona.py` — REST API for persona switching and memory management | **mounted**: `app.py:283` `app.include_router(persona.router, tags=["persona"])` |
| `Settings.tsx` personas panel | present, **unreachable** (no tab trigger) |

So the backend API is serving; only the way in is missing.

## Why it is worth reconsidering rather than deleting

The founder's position: personas were shelved, but Haloysius changes the
calculus — the computer's personality can be customised, and the machinery for
that is largely built already. Settings has a **Being** tab
(`Settings.tsx:1093`) which is where the computer's character now lives, so
the question is not "bring back a shelved feature" but "is `persona/` the
customisation layer the Being surface should be standing on, or a second,
disagreeing answer to the same question?"

That is the thing to decide, and it wants deciding on the merits rather than as
a side effect of a dead-code sweep. Note the same shape as
`detect_topic_change` vs Plan A's thread segmenter: two mechanisms answering one
question is worse than either alone.

## What NOT to do meanwhile

- Do not delete `persona/`, its routes, or the Settings panel as dead code —
  the route is mounted and the panel is a surface someone may be mid-way
  through, not scaffolding.
- Do not add a `TabsTrigger` to "fix" the panel either: that ships a surface
  nobody has decided to ship, on a feature that is formally legacy.
- Leave it exactly as it is until the Being/Haloysius personality question is
  answered. This file is the record that the unreachable panel is *known*, not
  an oversight.

## Related

- `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` (the Being surface, voice)
- `.handoff/CONTINUOUS-CONVERSATION-PLAN-A-RESULTS-2026-08-27.md` (where this was surfaced)
