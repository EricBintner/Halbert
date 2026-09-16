# Storybook Chrome Branding & the IconDock — Design

**Date:** 2026-09-16
**Status:** Implemented 2026-09-16; see §6 for what was verified and §8 for deviations
**Scope:** `packages/design-system/.storybook/`, `packages/design-system/src/`, `marketing/web-v10/src/`
**Reads with:**
- [BRAND-GUIDELINES-AND-AESTHETIC.md](BRAND-GUIDELINES-AND-AESTHETIC.md) — colour law, typography, voice
- [`/shared-tokens/tokens.css`](../../shared-tokens/tokens.css) — the only source of colour values
- [.handoff/RESEARCH-PUBLIC-STORYBOOK-AUDIT-2026-09-15.md](../../.handoff/RESEARCH-PUBLIC-STORYBOOK-AUDIT-2026-09-15.md) — the audit this answers

---

## 1. Goal

Two deliverables, decided with the founder on 2026-09-16:

1. **Brand the Storybook chrome.** The sidebar, toolbar, panels, docs pages,
   tab title, and page meta carry the Olivetti Vermilion & Bone identity in
   both themes. The brand line reads **"Halbert's Storybook"** with the
   7-line mark before it.
2. **An `IconDock` component** in the design system, shown in Storybook, and
   used on the marketing page as a bottom-right cluster: GitHub, Storybook,
   X, Reddit. X and Reddit are disabled with no link yet. The Storybook link
   points at `https://storybook.halbert.computer`.

Explicitly out of scope: hosting or deploying the subdomain, Welcome or
per-component MDX pages, and the worktree entries another session added to
`.claude/launch.json`.

## 2. What the review found

The Storybook was stock. A concurrent session left an uncommitted draft
(`manager.ts`, `manager-head.html`, `autodocs` on seven story files) that this
design supersedes in place. The draft stopped short in these places:

| Finding | Why it matters |
|---|---|
| Docs pages untouched | Autodocs and MDX render in Storybook's white theme and stock fonts, even with the canvas on After hours. |
| Chrome never loads the brand fonts | The manager document has no link to `fonts.css`; the draft named Nunito Sans, Storybook's default. |
| Theme set once | The sidebar stays bone when the canvas goes charcoal. |
| `<title>` injection cannot work | Storybook writes its own `<title>` first and hardcodes the " ⋅ Storybook" suffix in `getDescription`. |
| Hex literals in `manager.ts` | The standing directive forbids hardcoded colours; the theme API needs literals, so the values must be *derived*. |
| `/fonts/fonts.css` absolute path in `preview-head.html` | Breaks under subpath hosting. |
| `Agent` missing from `storySort.order` | Sorts after Drafts. |
| Social meta on raw GitHub | `https://halbert.computer/og-image.png` is live and is the right absolute URL. |

Verified enabler: with `brandTitle` set and no `brandImage`, the manager
renders the title through `dangerouslySetInnerHTML`, so the brand line can be
inline SVG plus text in the real Space Grotesk.

## 3. Storybook chrome

### 3.1 Token plumbing (decision A1)

- `.storybook/tokens.ts` — Node-side. Reads `shared-tokens/tokens.css`, parses
  the `:root` block and the explicit dark block, resolves every `var()` chain,
  and returns `{ light, dark }` dictionaries keyed by token name.
- `.storybook/theme.ts` — the one hand-written table, theme slot → token name,
  and `buildTheme(base, tokens)` returning Storybook `ThemeVars`.

| Theme slot | Token |
|---|---|
| `colorPrimary` | `--color-accent` |
| `colorSecondary`, `barSelectedColor`, `barHoverColor` | `--color-accent-strong` |
| `appBg`, `barBg`, `appPreviewBg` | `--color-canvas` |
| `appContentBg`, `buttonBg`, `inputBg`, `booleanSelectedBg` | `--color-surface` |
| `booleanBg` | `--color-surface-subtle` |
| `appBorderColor`, `buttonBorder` | `--color-line` |
| `inputBorder` | `--color-line-strong` |
| `textColor`, `inputTextColor` | `--color-ink` |
| `barTextColor` | `--color-ink-secondary` |
| `textMutedColor` | `--color-ink-tertiary` |
| `textInverseColor` | `--color-ink-on-accent` |
| `appBorderRadius`, `inputBorderRadius` | `--radius-md` (parsed to a number) |
| `fontBase` | `--font-sans` |
| `fontCode` | `--font-mono` |

The selected sidebar row is therefore accent-strong with ink-on-accent text:
the dark-mode flip in the brand rules (§3.4) happens for free, and it is the
one vermilion element in the view.

`main.ts` builds both themes at config time and injects them as a JSON global
through the `managerHead` and `previewHead` hooks. No runtime file contains a
colour literal. The same hook adds `theme-color` meta per colour scheme from
the canvas tokens.

### 3.2 Brand line

`brandTitle` is HTML: an inline 7-line mark (24px, stroked with that theme's
`--color-accent`, so it lifts in the dark theme) followed by
`Halbert's Storybook`. `brandUrl` is `https://halbert.computer`, opened in the
same tab. The manager head links `./fonts/fonts.css` so the line renders in
Space Grotesk.

### 3.3 Dark mode

- **Manager.** `manager.ts` registers a tiny addon that listens for
  `SET_GLOBALS` and `GLOBALS_UPDATED` and calls `api.setOptions({ theme })`
  with the light or dark theme according to the `theme` global.
- **Docs.** `preview.tsx` sets `parameters.docs.container` to a component that
  wraps Storybook's `DocsContainer`, reads `context.store.userGlobals.globals.theme`,
  and passes the matching docs theme. The existing `withTheme` decorator is
  unchanged.

### 3.4 Tab title

The same manager addon observes the `<title>` node with a `MutationObserver`
and rewrites a trailing ` ⋅ Storybook` to ` ⋅ Halbert's Storybook`. The
observer only writes when the suffix is not already the brand one, so it cannot
loop. The `<title>` in the draft `manager-head.html` is removed.

### 3.5 Page meta (`manager-head.html`)

- `description`: the package description.
- `canonical` and `og:url`: `https://storybook.halbert.computer/`.
- `og:image` / `twitter:image`: `https://halbert.computer/og-image.png`,
  1200×630, with `og:image:alt`.
- `og:title` / `twitter:title`: `Halbert's Storybook`.

### 3.6 Small fixes

- `preview-head.html` and `manager-head.html` use `./fonts/fonts.css`.
- `storySort.order` becomes Brand, Design Tokens, Primitives, Surfaces,
  Modules, Agent, Voice, Drafts.
- `tags: ['autodocs']` on every component story meta the draft missed.
- `src/test/storybookTheme.test.ts` (vitest, imports from `../../.storybook/`,
  which puts those files under `tsc` as well): every mapped slot resolves to a
  non-empty value in both themes; the brand line contains the mark and the
  name; radius parses to a number. `tokens.ts` is the only file that touches
  `fs`; `theme.ts` is pure so the manager and preview bundles can import it.

## 4. `IconDock` (decision B1)

### 4.1 API

```ts
export interface IconDockItem {
  id: string
  /** Accessible name and tooltip, e.g. "GitHub". */
  label: string
  /** Rendered at 16px in currentColor, like NavRail icons. */
  icon: React.ComponentType<{ className?: string }>
  href?: string
  onClick?: () => void
  /** Renders a native disabled button with the "coming soon" tooltip. */
  disabled?: boolean
}

export interface IconDockProps extends Omit<React.HTMLAttributes<HTMLElement>, 'children'> {
  items: IconDockItem[]
  /** aria-label of the <nav>. Default "Links". */
  label?: string
  orientation?: 'horizontal' | 'vertical'
}
```

File: `src/surfaces/IconDock.tsx`, exported from `src/index.ts` with its types.

### 4.2 Rendering rules

| Item | Element | Attributes |
|---|---|---|
| `href` | `<a>` | `aria-label`, `title`; absolute URLs get `target="_blank" rel="noopener noreferrer"` |
| `onClick` | `<button type="button">` | `aria-label`, `title` |
| `disabled` | `<button type="button" disabled>` | `aria-label`, `title="<label> · coming soon"` |

The icon carries `aria-hidden="true"`; the label is the name. Sentence case,
no terminal punctuation, per the brand mechanics.

### 4.3 Styling (`styles.css`, section `icon-dock`)

Redesigned by the founder on 2026-09-16, after the first build: **no plate**.

- `.hb-dock`: inline-flex, gap `--space-2`, `color: inherit`. No background,
  border, radius, shadow or padding. `.hb-dock--vertical` stacks.
- `.hb-dock__btn`: 32×32, `--radius-md` (for the focus ring only), no border,
  no fill, `color: inherit`. Hover: `--color-accent` (licensed for non-text
  marks; a 16px glyph is one). Focus: the shared focus-ring rule. Disabled:
  `opacity: 0.4`, `cursor: not-allowed`. Transitions use `--duration-switch`
  / `--ease-switch`.
- Why inherit and opacity, not tokens per state: the glyphs must be paintable
  in a second ink by a parent. The marketing site draws the dock twice — a
  base copy in ink and a copy in `--color-ink-on-stroke` masked to the
  vermilion stroke — exactly as its header logo is drawn. A fixed grey for
  disabled could not follow the inverted copy; opacity does.

### 4.4 Brand glyphs

`src/icons/brands.tsx` exports `GitHubIcon`, `StorybookIcon`, `XIcon`,
`RedditIcon`: 24-unit viewBox, `fill="currentColor"`, 16px default. Path data
is vendored from the Simple Icons set (CC0-1.0); the file header records the
source and version, and `documentation/legal/THIRD-PARTY-LICENSES.md` gains a
provenance row. Trademarks stay with their owners.

### 4.5 Tests and story

- `src/test/iconDock.test.tsx`: accessible names; external-link attributes;
  click items fire; disabled items are disabled buttons with the tooltip and
  out of the tab order; the nav label; the vertical class.
- `src/stories/IconDock.stories.tsx`, `Surfaces/IconDock`, autodocs, four
  cases: the marketing set (two disabled), all enabled, vertical, click actions.

## 5. Marketing page

- `marketing/web-v10/src/components/CornerDock.jsx` builds the four items and
  renders `IconDock` **twice**: a base copy, fixed bottom-right, and a masked
  copy in `--color-ink-on-stroke` inside a full-viewport `fixed inset-0`
  layer with `mask-image: url(#stroke-intersection-mask)` — the same mask the
  header and folio bar use, so the glyphs invert where the stroke passes
  under them. The masked layer is `aria-hidden` **and** `inert`, so its
  duplicate links never enter the tab order. It must be full-viewport: the
  mask is in viewport coordinates, and a small fixed box would put its own
  top-left at the mask origin.
- **One corner frame for the page.** `CORNER_INSET` exports the header's
  frame (1.5rem from the sides, 1rem from the bottom, plus safe-area insets).
  The dossier trigger in `TechnicalDossierModal.jsx` sits on the same frame
  bottom-left, uses the `hb-dock__btn` class for the same box, ink, hover and
  focus ring, and has its own masked copy. Its plate, border, shadow, blur and
  press-scale are gone.
- Items, in order: GitHub → `https://github.com/EricBintner/Halbert`;
  Storybook → `https://storybook.halbert.computer`; X (disabled);
  Reddit (disabled).
- `App.jsx` mounts `CornerDock` beside the other fixed layers.
- `src/index.css` imports the design-system stylesheet by relative path
  (Tailwind v4 resolves `@import` itself, without the vite alias).

## 6. Verification

- `packages/design-system`: `npm run typecheck`, `npm test`,
  `npm run build-storybook -- --quiet` (the CI trio).
- `marketing/web-v10`: `npm run build`.
- Browser, built Storybook served statically: brand line and sidebar in both
  modes, an autodocs page in both modes, tab title, favicon.
- Browser, marketing dev server: the corner at desktop and phone widths, both
  colour schemes, at a scroll position where a stroke passes under the dock;
  console clean.

## 7. Sequence

Work happens in the main tree, no worktree (founder, 2026-09-16). The
superseded draft files are edited in place. Four logical changes: Storybook
chrome; glyphs + `IconDock` + tests + story; marketing corner dock; this
document and the docs index. Commits only on request; no trailers.

## 8. Deviations from the approved design

- **Sort order gained `Instruments`.** Two story roots (`Instruments/Meters`,
  `Instruments/Templates`) postdate the audit; they sit after Primitives.
  Agent is after Modules, as approved.
- **`Design Tokens/Overview` has no `autodocs` tag.** It is a document, not a
  component story; stacking its four full-page stories into one docs page
  would duplicate it.
- **vitest `css` option.** `css: false` blanked the `tokens.css?raw` import the
  theme test needs (vitest matches the `.css` extension before the query), so
  the config now lets only `?raw` ids through. Every other stylesheet is still
  skipped in tests.
- **Plate dropped (founder, same day).** §4.3 and §5 describe the bare
  version; the first build shipped a plate with hairline and shadow, which
  the founder replaced with the header's stroke-inversion treatment.
