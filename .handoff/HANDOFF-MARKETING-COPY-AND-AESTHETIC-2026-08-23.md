# Handoff: Marketing Website — Copy Overhaul & 60s Ad Aesthetic

**Date:** 2026-08-23
**Status:** New creative direction — ready for implementation
**From:** Eric + Devin (codebase session)
**To:** Design AI / next session

---

## The Problem

The current marketing site (`marketing/web/`) has a draft foundation — the React/Vite/Tailwind 4 scaffold works, the design tokens are solid, and the component structure exists. But the **content is atrocious** and the **aesthetic completely missed the mid-century 60s advertising mark**. The site currently reads like a generic SaaS landing page with a warm color palette, not a bold 1960s print ad brought to life on the web.

---

## Part 1: Copy Direction — "I Am Your Computer"

### The Ethos

All headline copy is written in the **first-person voice of the computer itself**. The computer is speaking directly to the reader. Body copy then explains what that statement means in practical terms.

This is not a gimmick. It is the core product thesis made literal: Halbert IS the computer talking. The marketing copy should embody the product's central premise — first-person embodiment, no disclaimers, no "the AI assistant will..." hedging. The computer speaks.

### Copy Structure Pattern

```
HEADLINE (computer speaking, first person, short, punchy)
   ↓
BODY COPY (explains what the headline means, what it does for you)
```

### Example Copy Treatments

**Current (bad):**
> "Your computer has something to say."
> "A local-first AI assistant that knows your machine — because it is your machine."

**Direction (good):**
> HEADLINE: "I know what's wrong with me."
> BODY: Halbert reads its own sensors, logs, and configuration history. When something breaks, it tells you — in plain language, with evidence. No dashboards to decode.

**More headline examples in the computer's voice:**
- "I remember why you changed that."
- "I can feel my own temperature."
- "I checked my own logs. Here's what I found."
- "Don't guess. Ask me."
- "I'm not feeling well."
- "I changed my own port. Here's why."
- "I won't touch anything without your permission."
- "I know myself better than any cloud AI could."

### Tone Rules

1. **First person only in headlines.** The computer says "I", "me", "my."
2. **Body copy shifts to second person.** "Halbert tells you...", "You can ask..."
3. **No hedging.** No "may", "might", "could help", "attempts to." The computer states facts about itself.
4. **Short sentences.** 1960s ad copy was telegraphic. "Think Small." "Lemon." "It's ugly, but it gets you there."
5. **Self-aware but not cute.** The computer is matter-of-fact about being a computer. No jokes about being a robot. No "beep boop." Just honest self-reporting.
6. **Period at the end of headlines.** This was a deliberate VW ad convention — the period makes it a statement, not a flash. Keep this.

### Copy Strategy: Test Multiple Variants

Do NOT lock in a single copy treatment. The site should be structured to **test multiple copy/content strategies** against each other. Build the component architecture so headlines and body copy are data-driven (passed as props or pulled from a copy file), not hardcoded in JSX. This allows rapid A/B testing of:

- Different headline voices (more technical vs. more human)
- Different lengths (single-word "Lemon"-style vs. full sentences)
- Different emotional registers (calm/clinical vs. urgent/concerned)
- Different section orderings (does "I know myself" convert better than "I remember" first?)

Create a `copy/` directory with variant files (e.g., `copy/variant-a.js`, `copy/variant-b.js`) that export the full content tree. The App imports one at a time. This is not over-engineering — it's the VW way. Bernbach tested headlines.

---

## Part 2: 60s Advertising Aesthetic — Research & Direction

### What We Missed

The current site uses:
- Inter (body) + Instrument Sans (display) + JetBrains Mono (code)
- Rounded corners everywhere (`rounded-xl`, `rounded-2xl`, `rounded-3xl`)
- Lucide icons (generic SVG icon set)
- Bootstrap-style card layouts (centered text, equal-width columns, pill badges)
- Soft shadows and subtle borders
- A "warm SaaS" feel that happens to use vermilion

This is a 2024 SaaS landing page with a nice color palette. It is NOT a 1960s print ad.

### What 60s Advertising Actually Looks Like

#### Saul Bass (1920–1996)
- **Key principle:** The image IS the idea. Not decoration accompanying text — the visual itself communicates the concept.
- **Technique:** Bold, simple geometric forms. Hand-cut paper aesthetics. Limited color (often 2-3 colors max). Asymmetry. White space as a compositional element, not empty space to fill.
- **Typography:** Bass used type as shape — letters were graphic elements, not just text. He favored sans-serifs set at large sizes with tight tracking.
- **Web translation:** Think CSS shapes (clip-path, transforms), not stock illustrations. Think one bold visual concept per section, not a grid of feature cards.

#### Paul Rand (1914–1996)
- **Key principle:** "A successful advertisement is a complete unit... not a patchwork of Illustration, Headline, Typography and Signature." Everything is integrated from the start.
- **Technique:** Visual puns. Wit. A single image that embodies the message. Rand's Olivetti ads, IBM posters, and Westinghouse work all share this: one idea, perfectly executed, where the type and image are inseparable.
- **Typography:** Rand used both serif and sans-serif, but always with purpose. He treated type as architecture, not decoration.
- **Web translation:** Each section should be a complete Rand-style unit where the headline, visual, and layout are designed together. Not "header + image + 3 columns of features."

#### Volkswagen "Think Small" / "Lemon" (DDB, 1959–1960s)
- **Layout:** 2/3 image, 1/3 copy. Three blocks with a headline in between. The image was "naked-looking, not full and lush" (Helmut Krone).
- **Typography:** Sans-serif body copy (unusual for the era — most ads used serif body). Deliberate "widows" — paragraphs broken into short, punchy blocks rather than solid walls of text.
- **Headlines:** Single short statements with a period. "Think Small." "Lemon." "It's ugly, but it gets you there." Self-deprecating, honest, conversational.
- **Tone:** Anti-aspiration. Instead of "you'll be amazing with this product," it was "this product is weird and here's why that's actually good."
- **Web translation:** Asymmetric layouts (not centered). Short copy blocks with deliberate line breaks. Headlines that end with periods. Honest, self-aware tone. The product shown plainly, not glamorized.

#### Typefaces of the Era
- **Futura** (Paul Renner, 1927) — THE geometric sans of 60s advertising. VW used it. Clean, geometric, single-story `a`. Available as a web font.
- **Helvetica** (Max Miedinger, 1957) — Entered American advertising in the early 60s. The workhorse.
- **Akzidenz-Grotesk** (1898, Berthold) — The original grotesque. Used widely in 60s European ads. Less polished than Helvetica, more character.
- **Univers** (Adrian Frutiger, 1957) — Systematic grotesque. Used by many 60s designers.
- **Trade Gothic** — Used for small print and captions in 60s ads.

**Recommendation:** Replace Instrument Sans with **Futura** (or the open-source equivalent **Jost** or **Renner**). Replace Inter with **Helvetica Neue** or the open-source **Inter** (acceptable, but consider **Work Sans** or **DM Sans** for more character). Keep JetBrains Mono for code blocks — it's the right call for terminal mockups.

The critical typeface decision: **the display face should be a geometric sans (Futura/Jost), not a humanist sans (Instrument Sans).** The Al/AI pun works better with a geometric sans where `l` and `I` are identical vertical strokes.

### Aesthetic Principles to Implement

1. **Asymmetry over centering.** 60s ads rarely centered everything. The VW ads placed the car in the upper-left, copy in the lower-right. Use asymmetric grid layouts. Break the 12-column grid in unexpected ways.

2. **White space as composition.** Large empty areas are deliberate. Don't fill every column. Let sections breathe with 60s-magazine-spread proportions.

3. **Bold, simple visuals.** One strong visual concept per section. Not a grid of 3 equal cards with icons. Think: a single large illustration, a bold typographic treatment, or a dramatic product mockup.

4. **Heavy rules and borders.** 60s ads used thick black rules (lines) to separate sections. Not hairline borders — actual 2-4px black lines. Use `border-2` or `border-4` with solid black or dark ink.

5. **Limited color.** The vermilion + warm paper palette is right. But use color as an accent, not everywhere. Most of the page should be ink-on-paper. Vermilion appears in one or two places per section, not on every button and badge.

6. **No rounded corners.** 60s print design had sharp corners. Replace `rounded-xl` / `rounded-2xl` / `rounded-3xl` with square corners or at most `rounded-sm` (2px). This is a major visual shift.

7. **No Lucide icons.** 60s ads used custom illustrations, not icon sets. Either: (a) create simple custom SVG illustrations in the Bass/Rand style, or (b) use typography as the visual element instead of icons.

8. **Deliberate line breaks in copy.** VW ads broke paragraphs into short, punchy blocks. Use `<br />` or CSS to control line breaks. Don't let the browser auto-wrap body copy — craft the reading rhythm.

9. **Crop marks and editorial details.** Add subtle print-production details: crop marks at section corners, caption-style metadata in mono, "Figure 1." style annotations. These sell the print-ad aesthetic.

10. **Overprint/misregistration effects.** A subtle CSS technique: offset color layers behind text or shapes to simulate printing misregistration. This is a hallmark of letterpress aesthetics. Use `text-shadow` or layered pseudo-elements with slight offsets in vermilion.

---

## Part 3: What to Do Differently — Component by Component

### Header
**Current:** Fixed top bar, centered logo, nav links, CTA button. Generic SaaS.
**Direction:** Think magazine masthead. Large wordmark left-aligned. Issue number / date in mono on the right ("No. 1 — August 2026"). No nav links in the header — let the page scroll. The CTA is a single underlined text link, not a pill button. Or: no header at all — the hero IS the top of the page, and navigation appears as a side-margin annotation.

### Hero
**Current:** Two-column grid (text left, terminal right). Eyebrow badge, headline, subhead, tagline callout, waitlist form, platform pills. Everything centered in its column.
**Direction:** VW ad layout. 2/3 visual (the terminal/conversation demo), 1/3 copy. Or invert it. The headline is a single short statement in large Futura, left-aligned, with a period. Below it, 2-3 short copy blocks (not one paragraph). The waitlist form is a simple input + text link, not a styled card. No eyebrow badge. No platform pills. Let the copy do the work.

### HowItWorks
**Current:** 3 equal-width step cards with icons, titles, descriptions. Sticky desktop window mockup on the right. Scroll-driven step activation.
**Direction:** Kill the 3-card grid. Instead: 3 full-width sections, each a complete 60s ad unit. Section 1: "I know myself." — large visual of sensor data, asymmetric layout. Section 2: "I remember." — config diff shown as a document with annotations. Section 3: "I speak." — the conversation demo as the hero visual. Each section has its own personality, not a template repeated 3 times.

### TheBeing
**Current:** Centered philosophy section with badge, big quote, 3 pillar cards, CLI demo.
**Direction:** This is the emotional core. Make it a single full-bleed statement — the computer's voice, large, alone on the page. "I am not an assistant. I am the machine." No cards. No pillars. Just the statement and a single piece of evidence (the proactive alert demo) below it. Let the silence do the work.

### Footer
**Current:** CTA card, 4-column link grid, legal text. Standard SaaS footer.
**Direction:** Magazine colophon. Small, left-aligned. "Halbert. Published by Eric Bintner. Set in Futura and JetBrains Mono. Printed on warm paper, 2026." The waitlist is a single line: "To subscribe, enter your email: [input] [submit]". No columns of links. No "Product / Architecture / Commitment" headers.

---

## Part 4: Technical Implementation Notes

### Fonts to Add
```
@fontsource/jost          → Display (Futura alternative, geometric sans, single-story a)
@fontsource/work-sans     → Body (more character than Inter, still clean)
@fontsource/jetbrains-mono → Keep (code blocks)
```

Or self-host (aligns with "local-first" brand ethos):
- Jost (open source Futura alternative): https://fonts.google.com/specimen/Jost
- Work Sans: https://fonts.google.com/specimen/Work+Sans

### CSS Techniques for 60s Print Aesthetic

**Paper texture (enhance existing):**
```css
.paper-texture {
  background-image:
    repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(26,25,24,0.015) 2px, rgba(26,25,24,0.015) 4px),
    repeating-linear-gradient(90deg, transparent, transparent 2px, rgba(26,25,24,0.015) 2px, rgba(26,25,24,0.015) 4px);
}
```

**Overprint/misregistration effect:**
```css
.overprint {
  text-shadow: 2px 0 0 var(--color-accent), -1px 0 0 var(--color-status-info);
  /* Simulates CMYK plate misalignment */
}
```

**Crop marks:**
```css
.crop-marks::before, .crop-marks::after {
  content: "";
  position: absolute;
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-ink);
}
.crop-marks::before { top: -6px; left: -6px; border-right: none; border-bottom: none; }
.crop-marks::after { bottom: -6px; right: -6px; border-left: none; border-top: none; }
```

**Heavy rules (section dividers):**
```css
.rule-heavy {
  border-top: 3px solid var(--color-ink);
  /* Not hairline — bold print rule */
}
```

### Layout: Break the Grid

The current 12-column Tailwind grid is too regular. For 60s ad layouts:
- Use `col-span-7` and `col-span-4` (leaving 1 column of white space)
- Offset content with `col-start-2` or `col-start-3`
- Let some sections be full-bleed (edge to edge)
- Use `margin-left: 15%` or arbitrary values to create asymmetric placement

### Custom SVG Illustrations

Replace Lucide icons with simple custom SVGs. Saul Bass style:
- Bold shapes (circles, triangles, rectangles)
- 2-3 colors max
- Slightly imperfect (hand-drawn feel)
- Conceptual, not literal (don't draw a CPU icon — draw a visual metaphor)

---

## Part 5: What to Keep from the Current Site

1. **The color palette** (Olivetti Vermilion + warm archival paper). This is right. Keep the tokens.
2. **The token architecture** in `shared-tokens/tokens.css`. Production-ready.
3. **The AnimatedCLI component.** The terminal demo is a strong product visualization. Keep it, but restyle its container (sharp corners, heavy border, no rounded).
4. **The DesktopWindow component.** Good for showing product UI. Restyle with sharp corners and heavy borders.
5. **GSAP scroll animations.** The motion philosophy is good. Keep the easing tokens.
6. **The Netlify form integration.** Keep the waitlist form mechanics.
7. **The Tailwind 4 + Vite + React 19 stack.** No reason to change the build tooling.
8. **The `paper-texture` CSS class.** Good foundation, enhance it.

---

## Part 6: Deliverables

1. **Copy file(s):** `marketing/web/src/copy/` directory with at least 2 variant content trees, each following the "I am your computer" ethos. Each variant includes all section copy (hero headline + body, how-it-works section copy, the-being statement, footer colophon).

2. **Restyled components:** All existing components rebuilt with:
   - Sharp corners (no `rounded-xl` / `rounded-2xl` / `rounded-3xl`)
   - Asymmetric layouts (not centered grids)
   - Heavy rules instead of hairline borders
   - Custom SVG illustrations instead of Lucide icons
   - Futura/Jost as display face
   - Period-ending headlines in the computer's first-person voice
   - Short, punchy body copy blocks with deliberate line breaks

3. **New section concepts:** At least one section that is a pure 60s ad unit — a single bold visual + headline + minimal copy, taking up a full viewport. Think "Think Small" but for a computer that talks.

4. **A/B test infrastructure:** The App should be able to switch between copy variants by changing a single import. This enables testing different copy strategies without code changes.

5. **Updated `index.html`:** New font preloads, updated meta description in the computer's voice.

---

## Part 7: References to Study

### Books
- "Ugly Is Only Skin-Deep" by Dominik Imseng — the story of the VW ad campaign
- "Helvetica Forever" — history of the typeface that defined the era
- "Paul Rand: Modernist Master" — complete works and writings
- "Saul Bass: A Life in Film and Design" — Bass's complete oeuvre

### Online
- Fonts In Use: Volkswagen of America ads 1960-68 — https://www.fontsinuse.com/uses/1976/volkswagen-of-america-ads-1960-68
- Paul Rand archive — https://www.paulrand.design/
- Helmut Krone interview — https://www.think.cz/english/people/an-interview-with-helmut-krone/
- 1960s Advertising archive — https://www.digitaladarchive.com/decade/1960s

### Key VW ads to study (find scans online)
- "Think Small" (1959) — the most famous ad of the 20th century
- "Lemon" (1960) — single-word headline, quality argument
- "It's ugly, but it gets you there" — self-deprecating honesty
- "Repair 'em? I've got enough parts to build 'em!" — conversational voice
- "Do you think the Volkswagen is homely?" — rhetorical question

### Paul Rand ads to study
- Olivetti ads (1950s-60s) — typewriter as visual pun
- IBM posters — geometric simplicity
- Westinghouse ads — integrated type and image
- Container Corporation series — abstract symbolism

### Saul Bass work to study
- Atlas Corp annual report (1960) — bold geometric forms
- Bell System logo (1969) — humanist geometry
- Film title sequences (Anatomy of a Murder, Vertigo, Ocean's 11) — type as motion

---

## Part 8: The Voice Test

Before building anything, write 10 headlines in the computer's first-person voice. Read them out loud. Do they sound like a computer that knows itself? Or do they sound like a marketing writer pretending to be a computer?

The best headlines will feel slightly unsettling — like the machine is actually speaking. Not cute. Not robotic. Just... honest. A computer that says "I'm not feeling well" when a disk is failing. A computer that says "I remember why you changed that" when you ask about a config edit.

That voice IS the product. The marketing site should sound exactly like talking to Halbert.

---

## Part 9: Current File Structure (for reference)

```
marketing/web/
├── index.html
├── package.json
├── shared-tokens/
│   └── tokens.css          ← KEEP (color palette, motion tokens)
├── src/
│   ├── main.jsx
│   ├── App.jsx             ← RESTRUCTURE (copy variant switching)
│   ├── index.css           ← ENHANCE (paper texture, overprint, crop marks)
│   ├── lib/
│   │   ├── useSmoothScroll.js
│   │   └── demo-scripts.js ← KEEP (terminal demo scripts)
│   ├── components/
│   │   ├── Header.jsx      ← REBUILD (magazine masthead)
│   │   ├── Hero.jsx        ← REBUILD (VW ad layout)
│   │   ├── HowItWorks.jsx  ← REBUILD (3 full-width ad units, not card grid)
│   │   ├── TheBeing.jsx    ← REBUILD (single statement, no cards)
│   │   ├── Footer.jsx      ← REBUILD (colophon, not link grid)
│   │   ├── AnimatedCLI.jsx ← KEEP (restyle container only)
│   │   ├── DesktopWindow.jsx ← KEEP (restyle container only)
│   │   ├── TerminalFrame.jsx  ← KEEP
│   │   └── HalbertMark.jsx    ← KEEP (logo mark)
│   └── copy/               ← NEW (variant copy files)
│       ├── variant-a.js
│       └── variant-b.js
```

---

## Part 10: Summary

The foundation is built. The stack works. The palette is right. What's missing is **soul** — the 60s advertising aesthetic that makes this feel like a Saul Bass poster or a DDB Volkswagen ad, not another SaaS landing page. And the copy needs to embody the product's core thesis: the computer speaking in first person.

The two changes that will have the most impact:
1. **Switch the display typeface to Futura/Jost** (geometric sans, not humanist)
2. **Rewrite all copy in the computer's first-person voice** with period-ending headlines

Everything else (asymmetry, heavy rules, crop marks, custom SVGs, no rounded corners) builds on those two foundations.

Go make something that looks like it belongs in a 1962 issue of LIFE magazine — but it's selling a computer that talks back.
