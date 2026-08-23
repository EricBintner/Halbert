# Handoff: Marketing & Design System Review

**Date:** 2026-08-23
**Status:** Feedback complete — awaiting user decision on revisions
**Reviewer:** Devin session (codebase-verified)

---

## Documents reviewed

| Document | Location |
|----------|----------|
| Marketing Webpage Plan | `marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md` |
| Visual Design Direction | `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md` |
| Web Build Implementation Plan | `marketing/IMPLEMENTATION-PLAN-WEB-BUILD-2026-08-23.md` |
| Tagline Creative Concept | `marketing/creative-concepts/you-can-call-me-ai.md` |
| Design System Spec | `documentation/design/DESIGN-SYSTEM-SPEC.md` |
| Component Architecture | `documentation/design/COMPONENT-ARCHITECTURE.md` |
| User Journey Methodology | `documentation/design/USER-JOURNEY-METHODOLOGY.md` |
| Domain Modules & Why Mechanics | `documentation/design/DOMAIN-MODULES-AND-WHY-MECHANICS.md` |
| Design README | `documentation/design/README.md` |

---

## Part 1: What's strong (keep as-is)

### 1.1 The palette is the right call

Olivetti Vermilion (`#D34E24`) on warm archival paper (`#F7F5F0`) is a distinctive, confident brand identity that immediately separates Halbert from every dark-mode AI tool and every tech-startup-blue SaaS landing page. The surface ramp (canvas → surface-subtle → surface → muted) provides four tiers of depth without heavy shadows — exactly the mid-century modern restraint principle. The telemetry status colors (Eames forest green, Braun amber, terracotta red, blueprint teal) are well-chosen desaturated pigments that fit the era.

### 1.2 The token architecture is production-ready

The three-tier hierarchy (primitive → semantic → component) in DESIGN-SYSTEM-SPEC.md is the right approach. The Tailwind 4 `@theme` block is copy-paste ready for the marketing site. The motion easing tokens are well-chosen.

### 1.3 The user journey methodology is the strongest document

The Four Whys framework, the three personas, and the five journey workflows connect the design system to the product's actual value. Journey 5 (marketing conversion funnel) ties the page structure to user psychology. This is product thinking, not decoration.

### 1.4 The negative constraints are correct

No HAL eye, no sci-fi neon, no phone mockups. The wordmark direction (Hal + Albert, terminal period in Vermilion) is clean and legally safe per the creative concepts analysis.

### 1.5 The open questions from the original plan were resolved reasonably

Domain (halbert.ai), waitlist (Netlify Forms), HTML/CSS mockups over screenshots, copy ownership, and scope (single page first) — all sensible.

---

## Part 2: Verified findings (codebase reverse-engineering)

I verified every factual claim the design docs make against the actual codebase. Here's what checks out and what doesn't.

### 2.1 Component audit claims — VERIFIED

| Claim in COMPONENT-ARCHITECTURE.md | Verified? | Actual finding |
|-------------------------------------|-----------|----------------|
| `SidePanel.tsx` is a "92KB mega-component" | **ACCURATE** | 92,494 bytes. Confirmed. |
| `AgentChat.tsx` has "heavy dark backgrounds" | **ACCURATE** | Uses `bg-zinc-950`, `bg-zinc-900/50`, `bg-zinc-800`, `border-zinc-800`, `text-zinc-200`. All hardcoded dark zinc palette. |
| `DiffBlock.tsx` is "monolithic, lacking AST context & blast-radius" | **PARTIALLY ACCURATE** | Has unified/split view toggle, but source comment says "Simple diff visualization (in production, use a proper diff library)." No AST, no blast-radius. Accurate that it lacks those features. |
| `ThinkingPanel.tsx` is a "generic pulsing loader with vague text" | **INACCURATE** | It's a collapsible streaming text panel that renders the agent's reasoning in real-time. Not a "pulsing loader." The description is misleading. |
| `ConfirmationDialog.tsx` is a "generic modal alert without dry-run consequence preview" | **ACCURATE** | 3,839 bytes. Simple dialog with confirm/cancel. No dry-run preview. |
| `WhyOverlay.tsx` is a "modal overlay that obscures conversation context" | **ACCURATE** | Full-screen overlay for editing "Why" explanations. |
| File naming: `WhyOverlay.tsx` | **INACCURATE** | Actual file is `why-overlay.tsx` (kebab-case). The design doc uses PascalCase throughout, showing it may not have read the actual files. |

### 2.2 ToolExecutionCard.tsx already exists — MISSED BY DESIGN DOC

COMPONENT-ARCHITECTURE.md recommends converting `ThinkingPanel.tsx` into `ToolExecutionCard.tsx`. But `ToolExecutionCard.tsx` **already exists** at `src/components/agent/ToolExecutionCard.tsx` (3,717 bytes). It's a separate component that displays tool execution status with expandable details. The design doc's migration map didn't notice this — it proposes creating a component that already exists.

### 2.3 Contrast ratios — VERIFIED WITH CORRECTIONS

DESIGN-SYSTEM-SPEC.md §3.2 claims specific WCAG contrast ratios. I computed the actual values:

| Claim in spec | Spec says | Actual | Discrepancy |
|---------------|-----------|--------|-------------|
| Ink `#1A1918` on Canvas `#F7F5F0` | 15.8:1 | **16.11:1** | Spec slightly low. Still AAA. |
| Ink secondary `#5E5B56` on Canvas | 5.6:1 | **6.20:1** | Spec significantly low. Still AA. |
| Ink tertiary `#8C877D` on Canvas | 3.2:1 | **3.28:1** | Close enough. Below AA for normal text. |
| Accent `#D34E24` on White | **Not mentioned** | **4.30:1** | **GAP: Below AA 4.5:1 for normal text.** |
| White on Accent (CTA button) | **Not mentioned** | **4.30:1** | **GAP: Same ratio. Borderline for AA.** |
| Accent hover `#B83E18` on White | **Not mentioned** | **5.61:1** | Passes AA. |

**The accent-on-white contrast gap is the most significant finding.** The primary CTA (Vermilion background, white text) is 4.30:1 — below the 4.5:1 WCAG AA threshold for normal-size text. Since CTAs use semibold at ~16px, this is borderline. The spec documents ink contrast carefully but omits the accent contrast entirely.

**Recommendation:** Either bump CTA text to ≥18px (clears the 3:1 large-text threshold), or darken the accent slightly for button backgrounds. Or accept as a known borderline case for a marketing site.

### 2.4 Screenshots don't exist — CONFIRMED

The README references `assets/screenshots/hero/dashboard-overview-light.png` but the `assets/screenshots/` directory does not exist. The visual design direction's recommendation to build pure HTML/CSS mockups (rather than wait for screenshots) is the correct call.

### 2.5 Tailwind version mismatch — NOT ADDRESSED

The existing dashboard frontend uses **Tailwind 3** with shadcn/ui HSL CSS variables (`--background: 0 0% 100%`, `--primary: 221.2 83.2% 53.3%`, etc.). The marketing site spec proposes **Tailwind 4** with `@theme` hex tokens. The "shared design language" concept is architecturally sound but the implementation differs:

- **Marketing site (Tailwind 4):** `@theme { --color-canvas: #F7F5F0; }` → generates `bg-canvas`, `text-canvas`, etc.
- **Desktop app (Tailwind 3):** `:root { --background: 43 24% 95%; }` → used via `hsl(var(--background))` in shadcn classes

The tokens can be shared conceptually (same hex values, same semantic names) but the CSS implementation is different. Neither doc acknowledges this. If the goal is true token sharing, someone needs to either:
- Migrate the desktop app to Tailwind 4 (large effort), or
- Maintain two token files that stay in sync manually, or
- Extract tokens to a framework-agnostic JSON/JS file that both consume

### 2.6 Font mismatch — NOT ADDRESSED

The existing dashboard frontend uses **Karla** as its sans font (`fontFamily: { sans: ['Karla', 'system-ui', 'sans-serif'] }`). The design spec proposes **Inter** (body) + **Instrument Sans** (display) + **JetBrains Mono** (code). The desktop app would need a font change to align with the marketing site. This is a desktop app change, not a marketing site change, but the "shared design language" framing implies alignment that doesn't currently exist.

### 2.7 The existing dashboard has dark mode support — NOT ADDRESSED

The dashboard's `tailwind.config.js` has `darkMode: ["class"]` with both `:root` (light) and `.dark` (dark) CSS variable sets. The design spec is light-only. The desktop app currently supports both modes. The "shared design language" needs to decide: does the desktop app drop dark mode, or does the design system need dark mode tokens too?

---

## Part 3: What needs pushback

### 3.1 "Approved" status labels are premature

Four documents are marked "Status: Approved" or "Approved Foundation & Design System Standard." The user has not approved these — they are requesting feedback. The design AI marked its own work as approved before user review.

**Action:** Strip all "Approved" labels to "Draft — Pending Review" until the user signs off.

### 3.2 Scope creep — design docs cover desktop app, not just marketing

DESIGN-SYSTEM-SPEC.md, COMPONENT-ARCHITECTURE.md, USER-JOURNEY-METHODOLOGY.md, and DOMAIN-MODULES-AND-WHY-MECHANICS.md are all scoped to "Shared Design Language across Halbert Desktop & Halbert Marketing." The original brief was "design a marketing webpage."

The component architecture includes `ApprovalGate`, `ConfigDiffInspector`, `VitalsMatrix`, `EvidenceDrawer`, `ApprovalRollbackModule` — none needed for the marketing site. The migration map recommends refactoring `AgentChat.tsx` → `AgentSpine.tsx`, deconstructing `SidePanel.tsx`, replacing `ConfirmationDialog.tsx` with `ApprovalGate.tsx`, etc. This is desktop app refactoring work, not marketing site work.

**Assessment:** The design system foundation is good to have. The desktop app refactoring recommendations should not block or gate the marketing site build. The marketing site needs exactly four components: `TerminalFrame`, `AnimatedCLI`, `DesktopWindow`, and `WaitlistCapture`.

**Action:** Accept the design tokens and four marketing-relevant components as the web build scope. Treat desktop app refactoring as a separate workstream.

### 3.3 The implementation plan is thin

`IMPLEMENTATION-PLAN-WEB-BUILD-2026-08-23.md` is 69 lines — mostly a file manifest. It's missing:

- **Build phases / sequencing** — the original marketing plan had 5 phases (scaffold → hero → scrollytelling → soul → polish). The implementation plan has none.
- **The CoDRAG porting strategy** — the original plan §7 detailed which components to copy, how to re-theme them, and why not to import `@prep/ui`. The implementation plan just lists files.
- **The demo scripts** — the original plan §5 had four fully drafted `CliScript` objects. The implementation plan mentions `demo-scripts.js` but doesn't include them.
- **Mobile responsive strategy** — not mentioned.
- **Performance budget** — not mentioned.
- **Acceptance criteria** — "build runs clean" is not enough.

**Action:** The implementation plan should absorb §5, §7, §8, and §10 from `MARKETING-WEBPAGE-PLAN-2026-08-23.md` or explicitly reference them.

### 3.4 The Al/AI visual pun needs typeface verification

The design doc recommends `Instrument Sans` or `Plus Jakarta Sans` and claims the uppercase `I` is "a clean vertical bar without top or bottom serifs." The creative concepts doc noted the pun works best with single-story `a` fonts. `Instrument Sans` has a **double-story `a`** (with the top hook), which means `al` and `ai` won't look as similar as they would in a font with a single-story `a`.

The pun is really about `l` vs `I` being identical vertical strokes. In a geometric sans where both are bare verticals, the pun can still work even with a double-story `a`. But this is a hard constraint that needs testing.

**Action:** Before build starts, render "Halbert. You can call me AI." in Instrument Sans, Plus Jakarta Sans, Avenir, Gotham, and Futura. Pick the one where the pun lands hardest.

---

## Part 4: What's missing

### 4.1 No favicon, OG image, or social sharing cards

For a marketing site, the Open Graph image is critical — it's what shows up when someone shares `halbert.ai` in Slack, Discord, Twitter, or iMessage. Not mentioned in any doc. The OG card should feature the wordmark + tagline on warm paper canvas with the Vermilion period — a static brand identity image at 1200x630.

### 4.2 No font loading strategy

The implementation plan mentions Google Fonts in the HTML shell but doesn't discuss:
- `font-display: swap` vs `optional` for the display face (swap causes FOUT flashes on the hero headline)
- Self-hosting vs Google Fonts CDN (self-hosting is better for performance and privacy, and aligns with the "local-first" brand ethos)
- Preloading the display font for the hero

**Recommendation:** Self-host the fonts. Preload the display face. Use `font-display: block` for the hero font and `font-display: swap` for body/mono.

### 4.3 No discussion of marketing-to-product connection

The docs describe the marketing site and desktop app as separate deliverables sharing tokens, but don't mention:
- Whether the waitlist feeds into anything (spreadsheet? mailing list? database?)
- Whether there's a download page or just a GitHub link
- Whether the docs site is the README or something else
- How the marketing site stays in sync with product changes (who maintains token sync?)

### 4.4 No error states, loading states, or form validation spec

The waitlist form is mentioned but has no spec for: empty submission, invalid email, duplicate email, success state, error state, loading state during submission.

---

## Part 5: Summary verdict

The design direction is strong — the palette, tokens, motion philosophy, and user journey methodology are good work. The Vermilion + warm paper combination is the right brand identity. The Four Whys framework is genuinely good product thinking.

The main issues are:
1. **Premature "Approved" labels** — process issue, easy fix
2. **Scope creep into desktop app refactoring** — needs separation
3. **Thin implementation plan** — lost detail from the original marketing plan
4. **Contrast ratio gap on accent** — 4.30:1, below AA for normal text
5. **Tailwind version + font mismatch** — "shared tokens" concept doesn't address that desktop uses Tailwind 3 + Karla, marketing proposes Tailwind 4 + Inter/Instrument Sans
6. **ToolExecutionCard.tsx already exists** — migration map proposes creating it
7. **ThinkingPanel description is inaccurate** — it's a streaming text panel, not a "pulsing loader"
8. **No OG image, font loading strategy, or form validation spec**

None of these are blockers. The design system foundation is usable as-is for the marketing site build.

---

## Part 6: Recommended actions

| # | Action | Priority | Owner |
|---|--------|----------|-------|
| 1 | Strip "Approved" → "Draft — Pending Review" on all 4 design docs | High | User or Devin |
| 2 | Fix ThinkingPanel description in COMPONENT-ARCHITECTURE.md | Medium | Design AI |
| 3 | Fix ToolExecutionCard migration map (it already exists) | Medium | Design AI |
| 4 | Fix file naming throughout (kebab-case, not PascalCase) | Low | Design AI |
| 5 | Correct contrast ratios in DESIGN-SYSTEM-SPEC.md §3.2 | Medium | Design AI |
| 6 | Add accent contrast disclosure + mitigation (≥18px CTA text or darker accent for buttons) | Medium | Design AI |
| 7 | Add Tailwind version mismatch + font mismatch section to DESIGN-SYSTEM-SPEC.md | Medium | Design AI |
| 8 | Merge implementation plan with detailed sections from marketing plan | High | Devin or Design AI |
| 9 | Add OG image, favicon, font loading to build scope | Medium | Build AI |
| 10 | Test Al/AI pun in candidate typefaces before committing | High | Build AI |
| 11 | Separate desktop app refactoring into its own workstream | High | User decision |
| 12 | Add form validation / error / success state spec for waitlist | Low | Build AI |

---

## Part 7: Decision points for the user

1. **Do you want me to make the fixes directly** (strip "Approved" labels, correct contrast ratios, fix the ThinkingPanel/ToolExecutionCard claims), or **send this feedback to the design AI for revision?**

2. **On the Tailwind version mismatch:** should the marketing site proceed with Tailwind 4 as planned (and treat token sharing as conceptual for now), or should we align both to the same version first?

3. **On the desktop app refactoring recommendations:** do you want to pursue them as a separate workstream, or shelve them until after the marketing site ships?

4. **On the accent contrast:** accept 4.30:1 as borderline-fine for a marketing CTA, or darken the accent slightly?

5. **Should I merge the implementation plan and marketing plan into a single build-ready document**, or keep them separate with cross-references?
