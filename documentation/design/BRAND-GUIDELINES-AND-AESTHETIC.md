# Halbert Brand Guidelines: Aesthetic, Colour Law & Voice

**Version:** 1.0.0
**Date:** 2026-08-26
**Status:** Active Brand Standard — Track 1 deliverable
**Scope:** Every surface that speaks as Halbert — desktop shell, dashboard, marketing, CLI, and the machine's own replies
**Supersedes:** the palette tables in `DESIGN-SYSTEM-SPEC.md` §3 (see §9, Corrections)

**Reads with:**
- [`/shared-tokens/tokens.css`](file:///Volumes/4TB-BAD/Halbert/shared-tokens/tokens.css) — the canonical dictionary. **Values live there, not here.**
- [`/scripts/check_contrast.py`](file:///Volumes/4TB-BAD/Halbert/scripts/check_contrast.py) — the executable form of §7
- [BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md) — the 5-track roadmap this is Track 1 of
- [philosophy.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/philosophy.md) — why Halbert speaks in the first person at all

---

## 1. What This Document Is For

A brand guideline that only lists colours is a paint chart. This one states the
**rules that make the paint mean something**, and every rule here is either
enforceable by a script or specific enough to fail a code review.

> *"An LLM that identifies as the computer itself is fundamentally more useful
> than an LLM that merely answers questions about computers."*

That sentence is the whole brand. Halbert is not a dashboard that reports on a
machine; it is the machine, with a face. Everything below follows from that:
the paper field exists because engineering notebooks are made of paper, the
single accent exists because instruments have one indicator lamp, and the voice
rules exist because a machine that overstates what it knows about itself is
worse than useless — it is dangerous.

**One hard rule about this file:** it contains no hex values outside the
Corrections log. The dictionary is `/shared-tokens/tokens.css`. A guideline
that duplicates values becomes a second source of truth, and a second source of
truth is how this project ended up with three divergent palettes (§9).

---

## 2. The Five Pillars

Halbert rejects two industry clichés outright:

- **Corporate SaaS monotony** — flat white cards, generic blue buttons, sterile
  sans-serif. It looks like an invoicing platform. It has no point of view.
- **The cyberpunk hacker trope** — pitch black, lime terminal text, glowing
  neon. It is juvenile fantasy, and it signals *toy* on a machine that is about
  to be trusted with `rm`.

Instead: Marcello Nizzoli and Ettore Sottsass at Olivetti, Dieter Rams at Braun,
Massimo Vignelli's Unigrid, and the 1975 NASA Graphics Standards Manual.

| # | Pillar | What it means in practice |
|---|---|---|
| 1 | **Daylight & Paper** | The field is warm unbleached linen, not white and not black. Halbert is a daytime instrument you read in a lit room. |
| 2 | **The Letterpress Stroke** | One mechanical orange-red, used for focal intent only. Never wallpaper. See the Vermilion Budget (§3.2). |
| 3 | **Editorial & Computational Type** | A strict triad — humanist serif, modernist sans, tabular mono — each with one job (§4). |
| 4 | **Instrument Tactility** | Elevated plates with crisp hairlines and recessed data trays. Things look like they could be *machined*. |
| 5 | **Honesty of State** | Zero vanity metrics. Every pixel traces to real telemetry, justified by the Four Whys. If a sensor is dark, say so (§6). |

---

## 3. Colour Law

### 3.1 The Surface Licence

The single most important idea in this system, and the one that has been got
wrong repeatedly:

> **Contrast is a property of a pair, not of a colour.**

A token is therefore never "accessible" on its own. It is licensed for specific
grounds, and using it elsewhere is a defect even if the hex is correct.

| Family | Licensed grounds | Floor | Why |
|---|---|---|---|
| **Ink** (`--color-ink`, `-secondary`, `-tertiary`) | canvas · surface · surface-subtle | AAA / AAA / AA | Ink is the universal text colour and lands everywhere, trays included. |
| **Chromatic** (`--color-accent-*`, `--color-status-*`) | canvas · surface · its own tint | AA | These are accents, not body text. A vermilion caption is never set on a recessed tray. |
| **`--color-surface-muted`** | *disabled controls only* | exempt | WCAG 1.4.3 exempts disabled controls. **Nothing readable belongs here.** |
| **`--color-ink-ghost`** | disabled + decorative rules | 3:1 non-text | Not a text colour. Placeholder text that must be read uses `--color-ink-tertiary`. |
| **`--color-accent`** | non-text marks + display ≥24px/700 | 3:1 non-text | The identity stroke. Anything smaller, or any button fill, uses `--color-accent-strong`. |
| **`--color-focus-ring`** | every text surface | 3:1 non-text | WCAG 1.4.11 / 2.4.13. The one boundary that must stand alone. |

**The stroke you see is not the stroke you press.** `--color-accent` is the
brand mark. `--color-accent-strong` is the interactive shade, dark enough that
text on top of it clears AA at real button sizes. Reaching for the brand shade
on a button is the single most likely way to fail the gate.

### 3.2 The Vermilion Budget

Restraint is the aesthetic. Rams' Braun radios have one red button, and it means
*this one*.

- **One vermilion element per view has primary status.** If two things are
  vermilion, neither is the answer to "what do I do now?"
- Vermilion is for: the primary action, the active/focused state, the live pulse
  dot, a data bar's fill when it is the subject, and the mark itself.
- Vermilion is **never**: a page background, a large fill, a decorative rule, a
  hover state on something non-interactive, or more than one adjacent CTA.
- **Destructive is not vermilion.** Vermilion means *act*; critical means
  *something is wrong*. `--color-status-critical` is a different, cooler red on
  purpose. A vermilion "Delete everything" button reads as encouragement.

### 3.3 Status Tones Carry Meaning, Not Decoration

Four diagnostic pigments, one meaning each, never used for variety:

| Token | Means | Never means |
|---|---|---|
| `--color-status-nominal` | Measured, and within range | "good job", success of a UI action |
| `--color-status-warning` | Measured, trending wrong, no action required yet | "note", "tip" |
| `--color-status-critical` | Measured, action required now | destructive-button styling |
| `--color-status-telemetry` | Provenance: retrieval, citation, RAG, evidence | generic "info" |

Every status pill carries a **text label as well as a colour**. Colour alone
fails WCAG 1.4.1 and fails colourblind users; a pill that only turns amber has
told a third of a large audience nothing.

### 3.4 Dark Mode — Olivetti After Hours

Dark mode is **not an inversion**. The paper is put away and the instrument is
lit from within: a warm charcoal ground, never `#000`, with bone ink.

Two things genuinely flip rather than darken, and both are counter-intuitive:

1. **The vermilion lifts.** The brand shade reaches only 3.73:1 on charcoal, so
   the stroke opens to a brighter tone, and the **press state brightens instead
   of dimming** — a lit control cannot dim without going illegible.
2. **Text on an accent fill flips from bone to the dark ground.** White on
   lifted vermilion is 3.24:1 and fails. `--color-ink-on-accent` handles this
   automatically; never hardcode `#fff` on a button.

Dark status chips are **opaque, not translucent**. A translucent wash over an
elevated surface lands *lighter* than canvas and silently drops its tone under
4.5:1. In dark mode a chip is a recessed one.

Halbert ships **light-first**: the daylight field is the identity, and dark mode
is the accommodation. The OS preference is honoured only when the app has made
no explicit choice.

---

## 4. Typography

Three faces, three jobs. A face used outside its job is a defect.

| Face | Token | Job | Never |
|---|---|---|---|
| **Fraunces** (humanist serif) | `--font-display` | Headings, the machine's own voice at rest, editorial statements | Body copy, UI chrome, anything under ~18px |
| **Space Grotesk** (modernist sans) | `--font-sans` | UI chrome, body copy, labels, buttons | Numbers that need to align |
| **JetBrains Mono** (tabular mono) | `--font-mono` | **All telemetry**, paths, commands, timestamps, identifiers, status-pill labels | Prose. Mono prose reads as a terminal cosplay. |

**Numbers are always mono.** A CPU temperature in a proportional face jitters as
it ticks. Tabular figures are the reason this pillar exists — a vitals plate
updating every second must not reflow.

**Micro-labels** — the small uppercase captions over a value — are mono,
`--tracking-label`, and `--color-ink-tertiary`. They are the engraved legend on
an instrument panel, not a heading.

---

## 5. Motion & Materiality

Motion mimics **physical switches and optical shutters**. Nothing bounces,
nothing overshoots, nothing is cute.

- **Ceiling: 250ms.** `--duration-instant` for state flips, `--duration-switch`
  for toggles and presses, `--duration-shutter` for panels opening.
- **Easing is `--ease-switch` or `--ease-shutter`.** No `ease-in-out` defaults,
  no spring physics, no `cubic-bezier` with a negative control point.
- **`prefers-reduced-motion` is honoured globally**, in the token file itself —
  the durations collapse to `0ms`. Do not re-implement this per component.
- **Nothing animates that is not changing.** No idle pulses, no shimmer on
  loaded content, no attention-seeking. Halbert is not Clippy (§6.4).

Plates get `--shadow-plate`; trays are recessed by *fill and hairline*, never by
an inset shadow. Radii are the four in the dictionary — an arbitrary
`rounded-[7px]` is a defect.

---

## 6. Voice & Microcopy

### 6.1 Two Different Things Are Written Here

Confusing these causes most microcopy bugs:

| | **Chrome** | **Speech** |
|---|---|---|
| What | Buttons, labels, empty states, errors | Halbert's generated replies |
| Written by | Us, at build time | The model, at runtime |
| Voice | **Voice-neutral** | The configured voice |
| Rule | Never assume "I" | Always consistent with the setting |

**Chrome must not assume a voice.** Halbert's self-reference is a user setting
(`BeingConfig.voice` in `halbert_core/config/being_config.py:35`, changeable at
runtime via the settings route), with three values whose identity blocks live in
`halbert_core/prompts/agent_prompts.py`:

- `first_person` — *"I am the machine."* (default)
- `the_computer` — *"This system…"*, a resident intelligence watching over it
- `hybrid` — first person for experience, third for objective fact

A button reading **"Ask me about my disks"** is broken for two of the three
settings. Write **"Ask about storage"**. Chrome describes the action; speech
carries the identity.

### 6.2 How Halbert Speaks

The identity emerges from **data, not creative writing**. Every claim about
state traces to live telemetry, indexed logs, a config snapshot, or memory
retrieval.

| Write this | Not this | Why |
|---|---|---|
| "I logged 3 read errors on `/dev/sda1` at 08:00." | "I'm feeling unwell today!" | Biography is grounded. Feelings are not a substitute for a sensor. |
| "I don't have visibility into that service's logs." | "That service is fine." | Absence of data is a fact worth stating. |
| "Pending sectors: 3. Reallocated: 0. I'd run an extended SMART test before this becomes a restore." | "Your disk might be dying!!" | State the measurement, then the recommendation, then the stakes. |
| "I'm mounted with `background_compression=none`." | "The system is configured suboptimally." | Configuration is physiology. Be specific and cite the file. |
| "This will rewrite `/etc/ssh/sshd_config`. I'll snapshot first." | "Applying changes…" | Say what will change, where, and what the undo is. |

**Tone:** knowledgeable, precise, safety-conscious. A senior sysadmin who
happens to be the machine. Never chirpy, never apologetic, never padded with
"Great question!". Concern is proportionate: a full disk is not a crisis and a
failing disk is not a footnote.

### 6.3 The Four Whys

Any proactive statement — anything Halbert says *unprompted* — must be able to
answer all four, and the UI must be able to show them:

1. **Why now?** What changed, and when.
2. **Why care?** The consequence if ignored.
3. **Why so?** The evidence, with a citable source.
4. **Why trust?** Provenance — which sensor, which log window, which snapshot.

An interruption that cannot answer these is not an insight; it is a
notification, and Halbert does not send notifications.

### 6.4 What Halbert Is Not

From `philosophy.md`, and binding on copy:

- **Not AGI.** Never claim consciousness, feelings-as-such, or suffering. "I
  experienced a read error" is biography. "I'm scared of dying" is a bug.
- **Not role-play.** The persona never invents state to stay in character. If
  the metaphor and the data conflict, the data wins and the metaphor is dropped.
- **Not Clippy.** No interrupting, no useless animation, no personality for its
  own sake. Halbert speaks when it has something evidenced to say.

### 6.5 Never Name a Model

**Standing founder directive.** No surface — docs, config templates, code
defaults, UI, CLI, marketing, or tests — names, lists, or recommends a specific
foundation model.

- Capability and context limits come from **runtime metadata or the user's
  `models.yml`**, never from a model-name substring.
- Hardware guidance is expressed in **parameter size and memory budget**, never
  in names.
- Licence notices are derived from the **licence text the runtime ships**, via
  `halbert_core/model/attribution.py` — not from a hand-typed table.

Halbert is model-agnostic, and named-model copy goes stale faster than any
other kind.

### 6.6 Mechanics

- **Sentence case** for everything: buttons, headings, labels. No Title Case.
- **No terminal punctuation on labels or pills.** Prose gets full stops.
- **Paths, commands, identifiers, and values are always mono**, inline included.
- **Timestamps are absolute and local** (`03:02`, `Jul 14`), never "2 hours ago"
  in telemetry. Relative time is fine in prose, never in a data field.
- **Units always accompany numbers**, and match the sensor's own units.
- **Errors state what failed, what it means, and what to do** — in that order,
  in three sentences or fewer.

---

## 7. Governance Gates

Three gates. The first one is executable; run it.

### Gate 1 — Accessibility (WCAG 2.1)

```bash
python3 scripts/check_contrast.py           # exits non-zero on failure
python3 scripts/check_contrast.py --verbose # print every licensed pair
```

The script parses `/shared-tokens/tokens.css`, resolves every `var()` chain,
composites translucent values, and checks each token against the grounds it is
**licensed** for (§3.1), in **both themes**. It also guards the
`prefers-color-scheme` block against drifting from the explicit dark block,
since plain CSS cannot share a declaration list between two selectors.

Floors: body ink **AAA (7:1)**, captions and chromatic text **AA (4.5:1)**,
non-text marks and the focus ring **3:1**.

Beyond the script, by review:
- Every status colour is paired with a **text label** (1.4.1).
- Every interactive element has a **visible focus ring** using
  `--color-focus-ring` (2.4.7).
- Type is never set below **10px**, and 10px is reserved for mono micro-labels.

### Gate 2 — Computational Honesty

- **No mock telemetry in production views.** Not zeroes, not placeholder
  sparklines, not lorem values.
- An unreadable sensor renders an **honest degraded state** — `[Sensor offline]`
  — never a plausible-looking number.
- Every displayed value is **traceable to a source** the UI can cite.
- No vanity metrics. If a number does not inform a decision, it is decoration
  and it comes out.

### Gate 3 — Motion Restraint

- Nothing over **250ms**; easing from the dictionary only.
- `prefers-reduced-motion` verified, not assumed.
- Nothing animates that is not changing state.

---

## 8. Applying This

**Do not hardcode a colour.** Every value comes from `var(--color-*)`. If you
find yourself typing `#`, you are creating the fourth palette.

| Surface | How tokens arrive |
|---|---|
| `marketing/web-v7` | `@import "../../../shared-tokens/tailwind-v4.css"` → `@theme inline` registers `bg-canvas`, `font-display`, … |
| `halbert_core/.../frontend` | `@import` in `src/index.css`; Tailwind v3 scales `canvas` / `ink` / `vermilion` / `status` / `hairline` / `focus` |
| Anything else | `@import` `/shared-tokens/tokens.css` directly. Zero dependencies. |

The Tailwind adapters point at the internal `--hb-*` tier rather than the public
`--color-*` names. That is deliberate: Tailwind re-emits every theme key it is
given, so pointing a key at itself produces a self-referential declaration that
is invalid at computed-value time and "works" only by load-order accident. The
public names stay stable for authors; the adapters use the tier underneath.

---

## 9. Corrections Log

This pass reconciled three divergent palettes and fixed defects that the
previous documents asserted as compliant. Recorded here because the wrong
values were published, and anyone holding the old docs needs to know.

**Three sources had drifted.** `DESIGN-SYSTEM-SPEC.md` (2026-08-23),
`BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md` (2026-08-26), and the live
`marketing/web-v7` disagreed. Worse, web-v7's `tokens.css` and its `ui.jsx`
disagreed *with each other*: the component file hardcoded 16 hex values from the
older spec and never read the token file sitting beside it. The newer ramp won
on merit — it lifts secondary ink from AA to AAA — and is now canonical.

| # | Defect | Was | Now |
|---|---|---|---|
| 1 | **Warning tone failed AA everywhere.** Braun ochre `#C4781C` measured **3.16:1** on canvas, used at 10px in pills. It violated the plan's own Gate 1. | `#C4781C` | A darker ochre at **5.05:1**. The original was a *dark-mode* colour all along — it measures 4.97:1 on charcoal and is now used there. |
| 2 | **`--color-ink-on-accent` was worse than white.** The warm off-white `#FFF7ED` was documented as "high-legibility" but measured **4.05:1** on the accent versus white's 4.30:1 — it *cost* contrast for warmth invisible at 11px. | `#FFF7ED` | Pure white in light mode; flips to the dark ground in dark mode, where white fails at 3.24:1. |
| 3 | **The brand shade failed as a button fill.** White on `#D34E24` is **4.30:1** — below the plan's own stated 4.5:1 CTA floor — and `Btn` used it at 11px. | one accent | Split: `--color-accent` (identity, non-text) and `--color-accent-strong` (**4.98:1** filled). |
| 4 | **Tertiary ink failed AA for small text** at 3.92:1 on trays, while being used for 10px captions. | `#78716C` | Darkened to **4.75:1** minimum. |
| 5 | **Ghost ink failed even the 3:1 non-text floor** at 2.06:1, while documented for placeholders. | `#A8A29E` | Raised to **3.21:1**, and re-scoped: placeholder text uses tertiary ink. |
| 6 | **No focus-ring token existed at all.** WCAG 2.4.7 had no token to satisfy. | — | `--color-focus-ring`, verified ≥3:1 on every surface in both themes. |
| 7 | **Contrast figures in `DESIGN-SYSTEM-SPEC.md` §3.2 were copied from the older palette** and understate the current ramp (secondary ink is 9.36:1, not 6.2:1). | stale table | This document + the script. The spec's §3 tables are superseded. |
| 8 | **Pill borders were built by string concatenation** (`` `${t.fg}55` ``), which silently produces an invalid colour for any non-hex value. | `${fg}55` | Named `--color-status-*-line` tokens. |

**Dark mode did not previously exist** in any specified form. It is defined here
and in the dictionary, and it is verified by the same gate.

---

## 10. Open Questions for the Founder

Flagged rather than decided:

1. ~~**The dashboard is still stock shadcn blue.**~~ **Resolved 2026-08-26** —
   repainted on the founder's call. The shadcn slots are now *generated* from
   the token file by `scripts/gen_shadcn_theme.py`, which contrast-checks every
   text-on-ground pair and refuses to write a failing theme. Note the remaining
   debt: 1,031 literal Tailwind palette classes still bypass the theme across 58
   files. All 50 that clashed outright are fixed; the rest are saturated status
   colours that read off-brand but stay legible, and
   `scripts/check_literal_colors.py` ratchets them so the count cannot grow.
2. **`Fraunces` and `Space Grotesk` are still not loaded in the desktop app**,
   which sets Karla. The triad is registered as `font-display` / `font-grotesk`,
   so type can be adopted deliberately rather than shifting under the repaint.
   The colour identity has landed; the typographic one has not.
3. **Web fonts are not self-hosted.** For a local-first, sovereign-host product,
   pulling faces from a CDN at runtime is a posture inconsistency worth
   resolving before launch.
