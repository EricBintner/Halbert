# Storybook Chrome & IconDock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brand the design-system Storybook chrome from the token file ("Halbert's Storybook", both themes, docs pages, tab title, meta) and ship an `IconDock` surface that the marketing page uses for its bottom-right GitHub / Storybook / X / Reddit cluster.

**Architecture:** `.storybook/tokens.ts` and `.storybook/theme.ts` are pure modules (CSS text in, Storybook `ThemeVars` out); `main.ts` reads the token file and the 7-line mark at build time and injects both themes as JSON into the manager and preview documents, where `manager.ts` and a custom docs container apply them and follow the Daylight / After hours global. `IconDock` is a plain-CSS surface on tokens, with vendored public-domain brand glyphs, consumed by the marketing site through its existing vite alias.

**Tech Stack:** Storybook 8.6 (react-vite), React 18/19, Vitest + Testing Library, plain CSS on `shared-tokens/tokens.css`, Vite 6 + Tailwind v4 (marketing).

**Spec:** `documentation/design/STORYBOOK-CHROME-AND-ICON-DOCK-2026-09-16.md`

**Ground rules for this repo (read before starting):**
- Work in the main tree on `main`, no worktree (founder, 2026-09-16). Files `packages/design-system/.storybook/manager.ts` and `manager-head.html` plus seven story files already carry an uncommitted draft from another session; this plan **replaces** the two config files and **keeps** the `tags: ['autodocs']` story edits.
- **Do not commit unless the founder asks.** No `Co-Authored-By` or generation trailers, ever.
- Never type a colour literal into source. Every colour comes from `shared-tokens/tokens.css`, at build time or via `var()`.
- Sentence case in UI copy, no terminal punctuation on labels.
- All commands below run from `packages/design-system` unless stated. Node 22.

---

## File map

| File | Responsibility |
|---|---|
| `packages/design-system/.storybook/tokens.ts` (create) | Pure parser: `tokens.css` text → resolved light/dark dictionaries |
| `packages/design-system/.storybook/theme.ts` (create) | Slot→token table, `buildThemes`, brand-line HTML, mark SVG parser, injected-global reader |
| `packages/design-system/.storybook/main.ts` (modify) | Read files at build time, inject themes + `theme-color` meta into both documents |
| `packages/design-system/.storybook/manager.ts` (replace) | Apply theme, follow the theme global, rebrand the tab title |
| `packages/design-system/.storybook/manager-head.html` (replace) | Font stylesheet + page meta (no `<title>`) |
| `packages/design-system/.storybook/preview-head.html` (modify) | Relative font path |
| `packages/design-system/.storybook/preview.tsx` (modify) | Themed docs container, sort order |
| `packages/design-system/tsconfig.json` (modify) | Add `vite/client` types for `?raw` imports in tests |
| `packages/design-system/src/test/storybookTheme.test.ts` (create) | Theme contract tests |
| `packages/design-system/src/icons/brands.tsx` (create) | Vendored GitHub / Storybook / X / Reddit glyphs |
| `packages/design-system/src/surfaces/IconDock.tsx` (create) | The dock |
| `packages/design-system/src/styles.css` (modify) | `icon-dock` section + focus rule |
| `packages/design-system/src/index.ts` (modify) | Exports |
| `packages/design-system/src/test/iconDock.test.tsx` (create) | Dock contract tests |
| `packages/design-system/src/stories/IconDock.stories.tsx` (create) | `Surfaces/IconDock` |
| `packages/design-system/src/stories/{Modules,Instruments,DataComponentTemplates}.stories.tsx` (modify) | `autodocs` tag |
| `marketing/web-v10/src/components/CornerDock.jsx` (create) | The four items in a fixed corner wrapper |
| `marketing/web-v10/src/App.jsx` (modify) | Mount it |
| `marketing/web-v10/src/index.css` (modify) | Import the design-system stylesheet |
| `documentation/legal/THIRD-PARTY-LICENSES.md` (modify) | §3.7 provenance row |
| `.handoff/RESEARCH-PUBLIC-STORYBOOK-AUDIT-2026-09-15.md` (modify) | Pointer to the spec |

---

### Task 1: Token reader and theme table (pure, test-first)

**Files:**
- Create: `packages/design-system/.storybook/tokens.ts`
- Create: `packages/design-system/.storybook/theme.ts`
- Modify: `packages/design-system/tsconfig.json`
- Test: `packages/design-system/src/test/storybookTheme.test.ts`

- [ ] **Step 1: Add `vite/client` to the tsconfig types** so `?raw` imports typecheck.

`packages/design-system/tsconfig.json`, change the `types` line to:

```json
    "types": ["vitest/globals", "@testing-library/jest-dom", "vite/client"]
```

- [ ] **Step 2: Write the failing test**

`packages/design-system/src/test/storybookTheme.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'

import tokensCss from '../../../../shared-tokens/tokens.css?raw'
import markSvg from '../../../../assets/brand/halbert-mark-7lines.svg?raw'
import { parseTokens, resolveValue } from '../../.storybook/tokens'
import { BRAND_NAME, BRAND_URL, SLOTS, buildThemes, parseMarkSvg } from '../../.storybook/theme'

const tokens = parseTokens(tokensCss)
const themes = buildThemes(tokens, parseMarkSvg(markSvg))

describe('tokens.ts', () => {
  it('resolves var() chains recursively', () => {
    const map = { '--a': 'var(--b)', '--b': 'var(--c)', '--c': '#123456' }
    expect(resolveValue('var(--a)', map)).toBe('#123456')
  })

  it('throws on an undeclared token instead of passing var() through', () => {
    expect(() => resolveValue('var(--nope)', {})).toThrow(/--nope/)
  })

  it('leaves no var() in either resolved dictionary', () => {
    for (const theme of [tokens.light, tokens.dark]) {
      for (const [name, value] of Object.entries(theme)) expect(value, name).not.toMatch(/var\(/)
    }
  })

  it('reads the dark block as overrides on top of light', () => {
    expect(tokens.dark['--color-canvas']).not.toBe(tokens.light['--color-canvas'])
    // A theme-invariant token is present in both and identical.
    expect(tokens.dark['--font-sans']).toBe(tokens.light['--font-sans'])
  })
})

describe('theme.ts', () => {
  it('maps every slot to a token declared in both themes', () => {
    for (const [slot, token] of Object.entries(SLOTS)) {
      expect(tokens.light[token], `${slot} <- ${token} (light)`).toBeTruthy()
      expect(tokens.dark[token], `${slot} <- ${token} (dark)`).toBeTruthy()
    }
  })

  it('lifts the accent and flips ink-on-accent after hours', () => {
    expect(themes.light.colorPrimary).not.toBe(themes.dark.colorPrimary)
    expect(themes.light.textInverseColor).not.toBe(themes.dark.textInverseColor)
    expect(themes.light.base).toBe('light')
    expect(themes.dark.base).toBe('dark')
  })

  it('sets the type triad', () => {
    expect(themes.light.fontBase).toContain('Space Grotesk')
    expect(themes.light.fontCode).toContain('JetBrains Mono')
  })

  it('parses the radius token to a number', () => {
    expect(themes.light.appBorderRadius).toBe(6)
    expect(themes.light.inputBorderRadius).toBe(6)
  })

  it('puts the mark before the name in the brand line, stroked with that theme accent', () => {
    for (const theme of ['light', 'dark'] as const) {
      const title = themes[theme].brandTitle ?? ''
      expect(title.indexOf('<svg')).toBeGreaterThanOrEqual(0)
      expect(title.indexOf('<svg')).toBeLessThan(title.indexOf(BRAND_NAME))
      expect(title).toContain(`stroke="${tokens[theme]['--color-accent']}"`)
      expect(title).toContain('stroke-width="48.00"')
    }
    expect(themes.light.brandUrl).toBe(BRAND_URL)
  })

  it('extracts geometry from the ratified mark file', () => {
    const mark = parseMarkSvg(markSvg)
    expect(mark.viewBox).toBe('0 0 1024 1024')
    expect(mark.strokeWidth).toBe('48.00')
    expect(mark.d.startsWith('M 512.00 80.00')).toBe(true)
  })
})
```

- [ ] **Step 3: Run it and confirm it fails on the missing modules**

Run: `npx vitest run src/test/storybookTheme.test.ts`
Expected: FAIL — "Failed to resolve import "../../.storybook/tokens"".

- [ ] **Step 4: Write `tokens.ts`**

`packages/design-system/.storybook/tokens.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/**
 * Reads the canonical token dictionary for the Storybook chrome.
 *
 * Storybook's theme API takes literal values — it cannot read a CSS custom
 * property — and the standing directive forbids literal colours in source.
 * This module is the bridge. It is pure (CSS text in, dictionaries out) so
 * main.ts can feed it the file at build time and the vitest suite can feed
 * it the same file through Vite's ?raw import. The values then travel to the
 * manager and preview documents as build-time JSON; no runtime file holds a
 * colour of its own.
 */

export type TokenMap = Record<string, string>

export interface ThemeTokens {
  light: TokenMap
  dark: TokenMap
}

const DECLARATION = /(--[\w-]+)\s*:\s*([^;]+);/g

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** The declaration list of the first block whose selector matches. */
function blockFor(css: string, selector: RegExp): string {
  const match = selector.exec(css)
  if (!match) throw new Error(`tokens.css: no block matching ${selector}`)
  const open = css.indexOf('{', match.index)
  const close = css.indexOf('}', open)
  if (open === -1 || close === -1) throw new Error(`tokens.css: unbalanced block after ${selector}`)
  return css.slice(open + 1, close)
}

function declarations(block: string): TokenMap {
  const out: TokenMap = {}
  for (const [, name, value] of block.matchAll(DECLARATION)) out[name] = value.trim()
  return out
}

/** Resolve every var() reference in `value` against `tokens`, recursively. */
export function resolveValue(value: string, tokens: TokenMap, depth = 0): string {
  if (depth > 16) throw new Error(`tokens.css: var() chain too deep in "${value}"`)
  return value.replace(/var\((--[\w-]+)\)/g, (_, name: string) => {
    const next = tokens[name]
    if (next === undefined) throw new Error(`tokens.css: ${name} is not declared`)
    return resolveValue(next, tokens, depth + 1)
  })
}

function resolveAll(tokens: TokenMap): TokenMap {
  const out: TokenMap = {}
  for (const name of Object.keys(tokens)) out[name] = resolveValue(tokens[name], tokens)
  return out
}

/**
 * The light dictionary is the first `:root {` block. The dark dictionary is
 * the explicit `:root[data-theme="dark"]` block laid over it — the explicit
 * block, not the media-query copy; scripts/check_contrast.py guards the two
 * against drifting apart.
 */
export function parseTokens(css: string): ThemeTokens {
  const clean = stripComments(css)
  const light = declarations(blockFor(clean, /:root\s*\{/))
  const darkOverrides = declarations(blockFor(clean, /:root\[data-theme="dark"\]/))
  return {
    light: resolveAll(light),
    dark: resolveAll({ ...light, ...darkOverrides }),
  }
}
```

- [ ] **Step 5: Write `theme.ts`**

`packages/design-system/.storybook/theme.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { ThemeVars } from '@storybook/theming'

import type { ThemeTokens, TokenMap } from './tokens'

/**
 * The Storybook chrome theme, derived from the token dictionary.
 *
 * This is the one hand-written table in the chain: theme slot → token NAME.
 * Values never appear here. `buildThemes` runs in main.ts at build time; the
 * result is injected into both documents as JSON and read back by
 * `readInjectedThemes` in manager.ts and preview.tsx.
 */

export const BRAND_NAME = "Halbert's Storybook"
/** The brand line links home, not to the repo: the marketing dock owns the GitHub link. */
export const BRAND_URL = 'https://halbert.computer'

/**
 * Slot → token. The selected sidebar row is accent-STRONG with ink-on-accent
 * text, so the dark-mode flip in BRAND-GUIDELINES §3.4 happens for free, and
 * it is the one vermilion element in the view.
 */
export const SLOTS = {
  colorPrimary: '--color-accent',
  colorSecondary: '--color-accent-strong',
  appBg: '--color-canvas',
  appContentBg: '--color-surface',
  appPreviewBg: '--color-canvas',
  appBorderColor: '--color-line',
  textColor: '--color-ink',
  textInverseColor: '--color-ink-on-accent',
  textMutedColor: '--color-ink-tertiary',
  barTextColor: '--color-ink-secondary',
  barSelectedColor: '--color-accent-strong',
  barHoverColor: '--color-accent-strong',
  barBg: '--color-canvas',
  buttonBg: '--color-surface',
  buttonBorder: '--color-line',
  booleanBg: '--color-surface-subtle',
  booleanSelectedBg: '--color-surface',
  inputBg: '--color-surface',
  inputBorder: '--color-line-strong',
  inputTextColor: '--color-ink',
  fontBase: '--font-sans',
  fontCode: '--font-mono',
} as const satisfies Partial<Record<keyof ThemeVars, string>>

export const RADIUS_TOKEN = '--radius-md'
export const ACCENT_TOKEN = '--color-accent'

export interface MarkGeometry {
  viewBox: string
  strokeWidth: string
  d: string
}

/** Pull the geometry out of a brand SVG so the mark has one source: assets/brand. */
export function parseMarkSvg(svg: string): MarkGeometry {
  const attr = (name: string) => {
    const m = new RegExp(`${name}="([^"]+)"`).exec(svg)
    if (!m) throw new Error(`mark svg: no ${name} attribute`)
    return m[1]
  }
  return { viewBox: attr('viewBox'), strokeWidth: attr('stroke-width'), d: attr(' d') }
}

/** The sidebar brand line: mark, then the name, in the manager's own font. */
export function brandTitleHtml(accent: string, mark: MarkGeometry): string {
  return (
    '<span style="display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:14px;letter-spacing:-0.01em">' +
    `<svg width="22" height="22" viewBox="${mark.viewBox}" fill="none" stroke="${accent}" ` +
    `stroke-width="${mark.strokeWidth}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
    `<path d="${mark.d}"/></svg>` +
    `<span>${BRAND_NAME}</span></span>`
  )
}

function radiusPx(tokens: TokenMap): number {
  const n = Number.parseFloat(tokens[RADIUS_TOKEN] ?? '')
  if (Number.isNaN(n)) throw new Error(`tokens.css: ${RADIUS_TOKEN} is not a length`)
  return n
}

export function buildTheme(base: 'light' | 'dark', tokens: TokenMap, mark: MarkGeometry): ThemeVars {
  const slots = {} as Record<keyof typeof SLOTS, string>
  for (const [slot, token] of Object.entries(SLOTS) as Array<[keyof typeof SLOTS, string]>) {
    const value = tokens[token]
    if (!value) throw new Error(`tokens.css: ${token} (for ${slot}) is missing`)
    slots[slot] = value
  }
  return {
    base,
    ...slots,
    appBorderRadius: radiusPx(tokens),
    inputBorderRadius: radiusPx(tokens),
    brandTitle: brandTitleHtml(tokens[ACCENT_TOKEN], mark),
    brandUrl: BRAND_URL,
    brandTarget: '_self',
  }
}

export interface InjectedThemes {
  light: ThemeVars
  dark: ThemeVars
}

export function buildThemes(tokens: ThemeTokens, mark: MarkGeometry): InjectedThemes {
  return { light: buildTheme('light', tokens.light, mark), dark: buildTheme('dark', tokens.dark, mark) }
}

export const INJECTED_GLOBAL = '__HALBERT_STORYBOOK_THEMES__'

declare global {
  // eslint-disable-next-line no-var
  var __HALBERT_STORYBOOK_THEMES__: InjectedThemes | undefined
}

/** Browser side: the JSON main.ts injected into this document's <head>. */
export function readInjectedThemes(): InjectedThemes {
  const themes = globalThis.__HALBERT_STORYBOOK_THEMES__
  if (!themes) throw new Error(`${INJECTED_GLOBAL} missing — .storybook/main.ts injects it via managerHead/previewHead`)
  return themes
}
```

- [ ] **Step 6: Run the test and confirm it passes**

Run: `npx vitest run src/test/storybookTheme.test.ts`
Expected: PASS, 10 tests.

- [ ] **Step 7: Typecheck**

Run: `npm run typecheck`
Expected: exit 0. (If `?raw` errors, the `vite/client` type from Step 1 is missing.)

---

### Task 2: Inject the themes and apply them in the chrome

**Files:**
- Modify: `packages/design-system/.storybook/main.ts`
- Replace: `packages/design-system/.storybook/manager.ts`
- Replace: `packages/design-system/.storybook/manager-head.html`
- Modify: `packages/design-system/.storybook/preview-head.html`
- Modify: `packages/design-system/.storybook/preview.tsx`
- Modify: `packages/design-system/src/stories/Modules.stories.tsx`, `Instruments.stories.tsx`, `DataComponentTemplates.stories.tsx`

- [ ] **Step 1: Rewrite `main.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { StorybookConfig } from '@storybook/react-vite'

import { parseTokens } from './tokens'
import { INJECTED_GLOBAL, buildThemes, parseMarkSvg } from './theme'

// This file is loaded through esbuild-register as CommonJS, so __dirname is
// the config directory. tokens.css and the brand assets live at the repo root.
const REPO_ROOT = resolve(__dirname, '../../..')
const read = (rel: string) => readFileSync(resolve(REPO_ROOT, rel), 'utf8')

const tokens = parseTokens(read('shared-tokens/tokens.css'))
const themes = buildThemes(tokens, parseMarkSvg(read('assets/brand/halbert-mark-7lines.svg')))

// The themes travel to both documents as build-time JSON; no runtime file
// holds a colour. "</" is escaped so the brand-line markup cannot close the tag.
const themeScript = `<script>globalThis.${INJECTED_GLOBAL} = ${JSON.stringify(themes).replace(/<\//g, '<\\/')};</script>`
const themeColorMeta =
  `<meta name="theme-color" media="(prefers-color-scheme: light)" content="${tokens.light['--color-canvas']}">` +
  `<meta name="theme-color" media="(prefers-color-scheme: dark)" content="${tokens.dark['--color-canvas']}">`

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',
    // The brand's accessibility gate covers colour pairs in the token file;
    // this covers the other half — roles, names, and contrast as rendered.
    '@storybook/addon-a11y',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  core: { disableTelemetry: true },
  managerHead: (head) => `${head ?? ''}\n${themeColorMeta}\n${themeScript}`,
  previewHead: (head) => `${head ?? ''}\n${themeScript}`,
  viteFinal: async (config) => {
    // tokens.css lives at the repo root, two levels above this package.
    config.server ??= {}
    config.server.fs ??= {}
    config.server.fs.allow = ['../..', ...(config.server.fs.allow ?? [])]
    return config
  },
}

export default config
```

- [ ] **Step 2: Replace `manager.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { addons } from '@storybook/manager-api'
import { create } from '@storybook/theming'
import { GLOBALS_UPDATED, SET_GLOBALS } from 'storybook/internal/core-events'

import { BRAND_NAME, readInjectedThemes } from './theme'

/**
 * Manager (chrome) branding.
 *
 * The two themes arrive from main.ts as injected JSON (see theme.ts). This
 * file applies the light one, then follows the Daylight / After hours global
 * so the sidebar changes with the canvas instead of staying bone while the
 * stories go charcoal.
 */
const injected = readInjectedThemes()
const themes = { light: create(injected.light), dark: create(injected.dark) }

addons.setConfig({ theme: themes.light })

const STOCK_SUFFIX = ' ⋅ Storybook'
const BRAND_SUFFIX = ` ⋅ ${BRAND_NAME}`

addons.register('halbert/chrome', (api) => {
  const follow = ({ globals }: { globals?: { theme?: unknown } }) => {
    api.setOptions({ theme: globals?.theme === 'dark' ? themes.dark : themes.light })
  }
  api.on(SET_GLOBALS, follow)
  api.on(GLOBALS_UPDATED, follow)

  // Storybook hardcodes the tab-title suffix in getDescription() and writes
  // its own <title> before any head injection, so the only seam is the node
  // itself. The observer writes only when the suffix is not already ours,
  // so its own write cannot re-trigger it.
  const title = document.querySelector('title')
  if (!title) return
  const rebrand = () => {
    const text = title.textContent ?? ''
    if (text.endsWith(STOCK_SUFFIX)) {
      title.textContent = text.slice(0, -STOCK_SUFFIX.length) + BRAND_SUFFIX
    } else if (text === 'Storybook' || text.endsWith('- Storybook')) {
      title.textContent = BRAND_NAME
    }
  }
  rebrand()
  new MutationObserver(rebrand).observe(title, { childList: true, characterData: true, subtree: true })
})
```

- [ ] **Step 3: Replace `manager-head.html`**

```html
<!--
  Manager chrome <head>. The colours and the brand line arrive from main.ts as
  build-time JSON (see .storybook/theme.ts); this file holds only what is
  static: the brand fonts, which the manager document would otherwise never
  load, and the page meta for the public site. There is no <title> here on
  purpose — Storybook writes its own first and manager.ts rebrands it.
-->
<link rel="stylesheet" href="./fonts/fonts.css" />

<meta name="description" content="The Olivetti Vermilion & Bone component library shared by the Halbert desktop shell and marketing site. Open source under GPL-3.0-or-later." />
<link rel="canonical" href="https://storybook.halbert.computer/" />

<meta property="og:type" content="website" />
<meta property="og:site_name" content="Halbert" />
<meta property="og:url" content="https://storybook.halbert.computer/" />
<meta property="og:title" content="Halbert's Storybook" />
<meta property="og:description" content="The Olivetti Vermilion & Bone component library shared by the Halbert desktop shell and marketing site." />
<meta property="og:image" content="https://halbert.computer/og-image.png" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />

<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="Halbert's Storybook" />
<meta name="twitter:description" content="The Olivetti Vermilion & Bone component library shared by the Halbert desktop shell and marketing site." />
<meta name="twitter:image" content="https://halbert.computer/og-image.png" />
```

- [ ] **Step 4: Make the preview font path relative**

`preview-head.html`: change `href="/fonts/fonts.css"` to `href="./fonts/fonts.css"` and extend the comment with: `Relative on purpose: the built site may be served from a subpath.`

- [ ] **Step 5: Themed docs container and sort order in `preview.tsx`**

Add these imports after the existing ones:

```tsx
import { DocsContainer, type DocsContainerProps } from '@storybook/blocks'
import { create } from '@storybook/theming'
import { GLOBALS_UPDATED } from 'storybook/internal/core-events'

import { readInjectedThemes } from './theme'
```

Add after the `withTheme` decorator:

```tsx
/**
 * Docs pages (autodocs, MDX) are styled by Storybook's own docs theme, not by
 * the token file, so they need the same light/dark pair the manager uses and
 * they need to follow the toolbar toggle. The store is not on the public
 * context type, hence the narrow cast for the initial value; updates arrive
 * on the channel.
 */
const injected = readInjectedThemes()
const docsThemes = { light: create(injected.light), dark: create(injected.dark) }

type ThemeName = keyof typeof docsThemes
const themeOf = (globals?: { theme?: unknown }): ThemeName => (globals?.theme === 'dark' ? 'dark' : 'light')

function initialTheme(context: DocsContainerProps['context']): ThemeName {
  const store = (context as unknown as { store?: { userGlobals?: { globals?: { theme?: unknown } } } }).store
  return themeOf(store?.userGlobals?.globals)
}

const ThemedDocsContainer = ({ context, children }: React.PropsWithChildren<DocsContainerProps>) => {
  const [theme, setTheme] = React.useState<ThemeName>(() => initialTheme(context))
  React.useEffect(() => {
    const onGlobals = ({ globals }: { globals?: { theme?: unknown } }) => setTheme(themeOf(globals))
    context.channel.on(GLOBALS_UPDATED, onGlobals)
    return () => context.channel.off(GLOBALS_UPDATED, onGlobals)
  }, [context])
  return (
    <DocsContainer context={context} theme={docsThemes[theme]}>
      {children}
    </DocsContainer>
  )
}
```

In `parameters`, add `docs: { container: ThemedDocsContainer },` and change the sort order to:

```ts
        order: ['Brand', 'Design Tokens', 'Primitives', 'Instruments', 'Surfaces', 'Modules', 'Agent', 'Voice', 'Drafts'],
```

(Instruments is a root the audit predates; it sits with the primitives it extends. Agent lands after Modules, as the spec says.)

- [ ] **Step 6: Add `tags: ['autodocs']`** directly under the `title:` line of the default `meta` in `Modules.stories.tsx`, `Instruments.stories.tsx`, and `DataComponentTemplates.stories.tsx`. Leave `Tokens.stories.tsx` alone: it is a document, not a component.

- [ ] **Step 7: Typecheck and unit tests**

Run: `npm run typecheck && npx vitest run`
Expected: exit 0, all tests pass (the theme test from Task 1 plus the existing suite).

- [ ] **Step 8: Static build**

Run: `npm run build-storybook -- --quiet`
Expected: exit 0, `storybook-static/` rebuilt. Then:

Run: `grep -c '__HALBERT_STORYBOOK_THEMES__' storybook-static/index.html storybook-static/iframe.html && grep -o '<meta name="theme-color"[^>]*>' storybook-static/index.html && grep -o 'href="./fonts/fonts.css"' storybook-static/index.html storybook-static/iframe.html`
Expected: `1` for each file, two theme-color metas, the font link in both documents.

- [ ] **Step 9: Browser check**

Serve the build: `npx http-server storybook-static -p 6060 -s` (or `python3 -m http.server 6060 -d storybook-static`), then in the built-in browser open `http://localhost:6060/`. Confirm:
- Sidebar heading shows the vermilion 7-line mark followed by "Halbert's Storybook" in Space Grotesk; the tab title ends with "⋅ Halbert's Storybook".
- Toggle After hours: sidebar and toolbar go charcoal, the mark's stroke lifts, an autodocs page (Primitives / Button / Docs) turns charcoal too.
- Console has no errors from `manager.ts` or `preview.tsx`.
Screenshot light and dark for the final report.

---

### Task 3: Brand glyphs, `IconDock`, styles, tests, story

**Files:**
- Create: `packages/design-system/src/icons/brands.tsx`
- Create: `packages/design-system/src/surfaces/IconDock.tsx`
- Modify: `packages/design-system/src/styles.css`
- Modify: `packages/design-system/src/index.ts`
- Test: `packages/design-system/src/test/iconDock.test.tsx`
- Create: `packages/design-system/src/stories/IconDock.stories.tsx`

- [ ] **Step 1: Write the failing test**

`packages/design-system/src/test/iconDock.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { IconDock, type IconDockItem } from '../surfaces/IconDock'
import { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '../icons/brands'

const marketing: IconDockItem[] = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
]

describe('IconDock', () => {
  it('is a navigation landmark named by its label', () => {
    render(<IconDock items={marketing} label="Elsewhere" />)
    expect(screen.getByRole('navigation', { name: 'Elsewhere' })).toBeInTheDocument()
  })

  it('names every control by its label, not its glyph', () => {
    render(<IconDock items={marketing} />)
    expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Storybook' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'X' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reddit' })).toBeInTheDocument()
  })

  it('opens absolute links in a new tab without leaking the opener', () => {
    render(<IconDock items={marketing} />)
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link).toHaveAttribute('href', 'https://github.com/EricBintner/Halbert')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('keeps relative links in the same tab', () => {
    render(<IconDock items={[{ id: 'docs', label: 'Docs', icon: GitHubIcon, href: '/docs' }]} />)
    const link = screen.getByRole('link', { name: 'Docs' })
    expect(link).not.toHaveAttribute('target')
    expect(link).not.toHaveAttribute('rel')
  })

  it('renders a disabled item as a disabled button with the coming-soon tooltip, out of the tab order', async () => {
    render(<IconDock items={marketing} />)
    const x = screen.getByRole('button', { name: 'X' })
    expect(x).toBeDisabled()
    expect(x).toHaveAttribute('title', 'X · coming soon')

    await userEvent.tab()
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('link', { name: 'Storybook' })).toHaveFocus()
    await userEvent.tab()
    expect(x).not.toHaveFocus()
  })

  it('fires the click handler of an action item', async () => {
    const onClick = vi.fn()
    render(<IconDock items={[{ id: 'go', label: 'Go', icon: GitHubIcon, onClick }]} />)
    await userEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('treats an item with no target as a placeholder', () => {
    render(<IconDock items={[{ id: 'later', label: 'Later', icon: XIcon }]} />)
    expect(screen.getByRole('button', { name: 'Later' })).toBeDisabled()
  })

  it('stacks when vertical', () => {
    render(<IconDock items={marketing} orientation="vertical" />)
    expect(screen.getByRole('navigation')).toHaveClass('hb-dock', 'hb-dock--vertical')
  })

  it('hides the glyph from assistive tech', () => {
    render(<IconDock items={marketing} />)
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link.querySelector('[aria-hidden="true"]')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/test/iconDock.test.tsx`
Expected: FAIL — cannot resolve `../surfaces/IconDock`.

- [ ] **Step 3: Write the brand glyphs**

`packages/design-system/src/icons/brands.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'

/**
 * Third-party brand glyphs, vendored.
 *
 * Path data from Simple Icons 16.31.0 (https://simpleicons.org), released
 * under CC0 1.0. The marks remain trademarks of their owners and are used
 * only to identify a link to the named service. Recorded in
 * documentation/legal/THIRD-PARTY-LICENSES.md §3.7.
 *
 * Each glyph is a plain component that accepts `className` and draws in
 * `currentColor`, which is the icon contract NavRail and IconDock share, so a
 * brand glyph and a lucide icon sit side by side without adapters.
 */

export interface BrandIconProps extends React.SVGAttributes<SVGSVGElement> {
  /** Rendered size in px. @default 16 */
  size?: number | string
}

function brandIcon(displayName: string, d: string) {
  const Icon = React.forwardRef<SVGSVGElement, BrandIconProps>(function BrandIcon({ size = 16, ...props }, ref) {
    return (
      <svg ref={ref} width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false" {...props}>
        <path d={d} />
      </svg>
    )
  })
  Icon.displayName = displayName
  return Icon
}

export const GitHubIcon = brandIcon(
  'GitHubIcon',
  'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12',
)

export const StorybookIcon = brandIcon(
  'StorybookIcon',
  'M16.71.243l-.12 2.71a.18.18 0 00.29.15l1.06-.8.9.7a.18.18 0 00.28-.14l-.1-2.76 1.33-.1a1.2 1.2 0 011.279 1.2v21.596a1.2 1.2 0 01-1.26 1.2l-16.096-.72a1.2 1.2 0 01-1.15-1.16l-.75-19.797a1.2 1.2 0 011.13-1.27L16.7.222zM13.64 9.3c0 .47 3.16.24 3.59-.08 0-3.2-1.72-4.89-4.859-4.89-3.15 0-4.899 1.72-4.899 4.29 0 4.45 5.999 4.53 5.999 6.959 0 .7-.32 1.1-1.05 1.1-.96 0-1.35-.49-1.3-2.16 0-.36-3.649-.48-3.769 0-.27 4.03 2.23 5.2 5.099 5.2 2.79 0 4.969-1.49 4.969-4.18 0-4.77-6.099-4.64-6.099-6.999 0-.97.72-1.1 1.13-1.1.45 0 1.25.07 1.19 1.87z',
)

export const XIcon = brandIcon(
  'XIcon',
  'M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z',
)

export const RedditIcon = brandIcon(
  'RedditIcon',
  'M12 0C5.373 0 0 5.373 0 12c0 3.314 1.343 6.314 3.515 8.485l-2.286 2.286C.775 23.225 1.097 24 1.738 24H12c6.627 0 12-5.373 12-12S18.627 0 12 0Zm4.388 3.199c1.104 0 1.999.895 1.999 1.999 0 1.105-.895 2-1.999 2-.946 0-1.739-.657-1.947-1.539v.002c-1.147.162-2.032 1.15-2.032 2.341v.007c1.776.067 3.4.567 4.686 1.363.473-.363 1.064-.58 1.707-.58 1.547 0 2.802 1.254 2.802 2.802 0 1.117-.655 2.081-1.601 2.531-.088 3.256-3.637 5.876-7.997 5.876-4.361 0-7.905-2.617-7.998-5.87-.954-.447-1.614-1.415-1.614-2.538 0-1.548 1.255-2.802 2.803-2.802.645 0 1.239.218 1.712.585 1.275-.79 2.881-1.291 4.64-1.365v-.01c0-1.663 1.263-3.034 2.88-3.207.188-.911.993-1.595 1.959-1.595Zm-8.085 8.376c-.784 0-1.459.78-1.506 1.797-.047 1.016.64 1.429 1.426 1.429.786 0 1.371-.369 1.418-1.385.047-1.017-.553-1.841-1.338-1.841Zm7.406 0c-.786 0-1.385.824-1.338 1.841.047 1.017.634 1.385 1.418 1.385.785 0 1.473-.413 1.426-1.429-.046-1.017-.721-1.797-1.506-1.797Zm-3.703 4.013c-.974 0-1.907.048-2.77.135-.147.015-.241.168-.183.305.483 1.154 1.622 1.964 2.953 1.964 1.33 0 2.47-.81 2.953-1.964.057-.137-.037-.29-.184-.305-.863-.087-1.795-.135-2.769-.135Z',
)
```

- [ ] **Step 4: Write `IconDock.tsx`**

`packages/design-system/src/surfaces/IconDock.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export interface IconDockItem {
  id: string
  /** Accessible name and tooltip, e.g. "GitHub". Sentence case, no terminal punctuation. */
  label: string
  /** Rendered at 16px in currentColor — a lucide icon, a brand glyph, anything that takes className. */
  icon: React.ComponentType<{ className?: string }>
  /** Renders an anchor. Absolute URLs open in a new tab with rel="noopener noreferrer". */
  href?: string
  /** Renders a button. */
  onClick?: () => void
  /**
   * Renders a native disabled button: announced by name, dimmed, out of the
   * tab order, with a "coming soon" tooltip. An item with neither `href` nor
   * `onClick` is treated the same way — a placeholder for a link that does
   * not exist yet.
   */
  disabled?: boolean
}

export interface IconDockProps extends Omit<React.HTMLAttributes<HTMLElement>, 'children'> {
  items: IconDockItem[]
  /** Accessible name of the dock. @default "Links" */
  label?: string
  orientation?: 'horizontal' | 'vertical'
}

const isExternal = (href: string) => /^https?:\/\//i.test(href)

/**
 * A plate of icon-only links or actions.
 *
 * The dock is a plate, not a bare row, on purpose: it carries its own surface
 * ground and hairline, so the glyphs stay legible wherever the plate lands —
 * including over the marketing site's vermilion strokes, which the header
 * there can only survive with an inverting mask.
 *
 * Every control is named by `label`; the glyph is decorative. A disabled item
 * is a real disabled <button> rather than a styled span, so assistive tech
 * announces it as dimmed and it never lands in the tab order.
 */
export const IconDock = React.forwardRef<HTMLElement, IconDockProps>(function IconDock(
  { items, label = 'Links', orientation = 'horizontal', className, ...props },
  ref,
) {
  return (
    <nav
      ref={ref}
      className={cx('hb-dock', orientation === 'vertical' && 'hb-dock--vertical', className)}
      aria-label={label}
      {...props}
    >
      {items.map((item) => {
        const Icon = item.icon
        const glyph = (
          <span className="hb-dock__glyph" aria-hidden="true">
            <Icon />
          </span>
        )

        if (item.disabled || (!item.href && !item.onClick)) {
          return (
            <button
              key={item.id}
              type="button"
              className="hb-dock__btn"
              disabled
              aria-label={item.label}
              title={`${item.label} · coming soon`}
            >
              {glyph}
            </button>
          )
        }

        if (item.href) {
          const external = isExternal(item.href)
          return (
            <a
              key={item.id}
              className="hb-dock__btn"
              href={item.href}
              aria-label={item.label}
              title={item.label}
              target={external ? '_blank' : undefined}
              rel={external ? 'noopener noreferrer' : undefined}
            >
              {glyph}
            </a>
          )
        }

        return (
          <button
            key={item.id}
            type="button"
            className="hb-dock__btn"
            aria-label={item.label}
            title={item.label}
            onClick={item.onClick}
          >
            {glyph}
          </button>
        )
      })}
    </nav>
  )
})
```

- [ ] **Step 5: Styles**

In `packages/design-system/src/styles.css`, add `.hb-dock__btn:focus-visible,` to the shared focus rule (the selector list at lines 34–38, before `.hb-window__toggle:focus-visible {`). Then append at the end of the file:

```css
/* ------------------------------------------------------------- icon-dock -- */

/* A plate of icon-only controls. The plate carries its own ground and
 * hairline so the glyphs read wherever it lands — over a vermilion stroke on
 * the marketing site included. */
.hb-dock {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1);
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-subtle);
}
.hb-dock--vertical {
  flex-direction: column;
}

.hb-dock__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--color-ink-secondary);
  cursor: pointer;
  text-decoration: none;
  transition: background-color var(--duration-switch) var(--ease-switch),
              color var(--duration-switch) var(--ease-switch),
              border-color var(--duration-switch) var(--ease-switch);
}
.hb-dock__btn:hover:not(:disabled) {
  background-color: var(--color-surface-subtle);
  color: var(--color-ink);
}
.hb-dock__btn:active:not(:disabled) {
  border-color: var(--color-line);
}
/* Ghost ink is licensed for disabled controls and nothing readable (§3.1). */
.hb-dock__btn:disabled {
  color: var(--color-ink-ghost);
  cursor: not-allowed;
}

.hb-dock__glyph {
  display: inline-flex;
  width: 16px;
  height: 16px;
}
.hb-dock__glyph > * {
  width: 100%;
  height: 100%;
}
```

- [ ] **Step 6: Exports** — append to `src/index.ts` under `// Surfaces`:

```ts
export { IconDock } from './surfaces/IconDock'
export type { IconDockProps, IconDockItem } from './surfaces/IconDock'
```

and a new group before `// Utilities`:

```ts
// Icons (vendored brand glyphs — see src/icons/brands.tsx for provenance)
export { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from './icons/brands'
export type { BrandIconProps } from './icons/brands'
```

- [ ] **Step 7: Run the test and confirm it passes**

Run: `npx vitest run src/test/iconDock.test.tsx`
Expected: PASS, 9 tests.

- [ ] **Step 8: Story**

`packages/design-system/src/stories/IconDock.stories.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Meta, StoryObj } from '@storybook/react'

import { IconDock, type IconDockItem } from '../surfaces/IconDock'
import { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '../icons/brands'

/** Generic 16px stroke glyphs for the action examples (lucide paths). */
const Icon = (d: string) =>
  function StrokeIcon({ className }: { className?: string }) {
    return (
      <svg className={className} width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={d} />
      </svg>
    )
  }
const RefreshIcon = Icon('M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6')
const SunIcon = Icon('M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z')

/** The marketing set: two live links, two placeholders until the accounts exist. */
const corner: IconDockItem[] = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
]

const meta: Meta<typeof IconDock> = {
  title: 'Surfaces/IconDock',
  tags: ['autodocs'],
  component: IconDock,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'A plate of icon-only links or actions. The plate carries its own ground and hairline, so it stays legible over any field — the marketing site uses it bottom-right, over the vermilion strokes. Disabled items are real disabled buttons: named, dimmed, out of the tab order, with a "coming soon" tooltip.',
      },
    },
  },
  args: { items: corner, label: 'Links', orientation: 'horizontal' },
  argTypes: {
    orientation: { control: 'inline-radio', options: ['horizontal', 'vertical'] },
    items: { control: false },
  },
}
export default meta
type Story = StoryObj<typeof IconDock>

/** GitHub and Storybook live; X and Reddit placeholders. */
export const MarketingCorner: Story = {}

export const AllEnabled: Story = {
  args: {
    items: corner.map((item) =>
      item.disabled ? { ...item, disabled: false, href: `https://example.com/${item.id}` } : item,
    ),
  },
}

export const Vertical: Story = {
  args: { orientation: 'vertical' },
}

/** Buttons instead of links: the same plate as an action cluster. */
export const Actions: Story = {
  args: {
    label: 'Canvas tools',
    items: [
      { id: 'refresh', label: 'Refresh readings', icon: RefreshIcon, onClick: () => undefined },
      { id: 'daylight', label: 'Daylight', icon: SunIcon, onClick: () => undefined },
    ],
  },
}
```

- [ ] **Step 9: Full package check**

Run: `npm run typecheck && npx vitest run && npm run build-storybook -- --quiet`
Expected: all exit 0. `Surfaces/IconDock` appears in the built sidebar with a Docs entry.

---

### Task 4: Marketing corner dock

**Files:**
- Create: `marketing/web-v10/src/components/CornerDock.jsx`
- Modify: `marketing/web-v10/src/App.jsx`
- Modify: `marketing/web-v10/src/index.css`

All commands in this task run from `marketing/web-v10`.

- [ ] **Step 1: Import the design-system stylesheet**

`marketing/web-v10/src/index.css`, after line 2 (`@import "../shared-tokens/tokens.css";`), add:

```css
/* Component styles for the design-system surfaces this site mounts (IconDock).
 * Relative path, not the vite alias: Tailwind v4 resolves @import itself. */
@import "../../../packages/design-system/src/styles.css";
```

- [ ] **Step 2: Write `CornerDock.jsx`**

```jsx
import React from 'react';
import { IconDock, GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '@halbert/design-system';

// X and Reddit stay disabled with no address until the accounts exist
// (founder, 2026-09-16). Order is the founder's.
const ITEMS = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
];

/**
 * Bottom-right corner links. The dock is a plate with its own ground, so it
 * needs none of the stroke-intersection mask the header and folio bar use.
 * Visible at every width: these are the links a phone visitor needs most.
 */
export function CornerDock() {
  return (
    <div
      data-testid="corner-dock"
      className="fixed z-30"
      style={{
        right: 'calc(env(safe-area-inset-right, 0px) + 1.5rem)',
        bottom: 'calc(env(safe-area-inset-bottom, 0px) + 1.5rem)',
      }}
    >
      <IconDock items={ITEMS} label="Halbert elsewhere" />
    </div>
  );
}
```

- [ ] **Step 3: Mount it in `App.jsx`**

Add the import next to the other component imports:

```jsx
import { CornerDock } from './components/CornerDock';
```

and render it directly after `<ScrollHUD ... />`:

```jsx
      {/* Bottom-right links: GitHub, Storybook, and the two placeholders */}
      <CornerDock />
```

- [ ] **Step 4: Production build**

Run: `npm run build`
Expected: exit 0, no warnings about unresolved imports.

- [ ] **Step 5: Browser check**

Start the dev server through the desktop app's preview (`marketing-v10`, port 5188). Confirm in the built-in browser:
- Four glyphs bottom-right in a plate; GitHub and Storybook are links (hover changes ink), X and Reddit are dimmed with the tooltip.
- Phone width (375px): the dock is visible, clear of the dossier trigger at bottom-left.
- Dark scheme: plate goes charcoal with bone-tinted glyphs.
- Scroll to a stop where a vermilion stroke passes under the corner: the plate stays legible.
- Console: no errors.
Screenshot desktop light, desktop dark, and phone for the final report.

---

### Task 5: Documentation

**Files:**
- Modify: `documentation/legal/THIRD-PARTY-LICENSES.md`
- Modify: `.handoff/RESEARCH-PUBLIC-STORYBOOK-AUDIT-2026-09-15.md`
- Modify: `documentation/design/STORYBOOK-CHROME-AND-ICON-DOCK-2026-09-16.md`

- [ ] **Step 1: Provenance row** — insert before `## 4. Attribution Notice for Redistributions`:

```markdown
### 3.7 Bundled Brand Glyphs

Four third-party brand marks are vendored as SVG path data in
`packages/design-system/src/icons/brands.tsx` so the design system carries no
icon-library dependency for them. The marks identify links to the named
services and remain trademarks of their owners.

| Glyph | Source | Version | Licence |
| :--- | :--- | :--- | :--- |
| GitHub, Storybook, X, Reddit | [Simple Icons](https://simpleicons.org) | 16.31.0 | CC0 1.0 Universal |

CC0 requires no notice; this row exists so the provenance is recorded the
same way as the typefaces in §3.6.
```

- [ ] **Step 2: Audit pointer** — under the `**Status:**` line of the audit handoff, add:

```markdown
**Resolution (2026-09-16):** §3's branding rows are implemented per
`documentation/design/STORYBOOK-CHROME-AND-ICON-DOCK-2026-09-16.md`. Still open
from §3: Welcome/MDX pages and CI deploy (founder: deploy is out of scope for now).
```

- [ ] **Step 3: Spec status** — change the spec's `**Status:**` line to `Implemented 2026-09-16; see §7 for what was verified`, and append a §8 "Deviations" note: Instruments added to the sort order (a root the audit predates); Tokens overview left without autodocs because it is a document, not a component.

---

### Task 6: Final verification (no claims without output)

- [ ] `cd packages/design-system && npm run typecheck && npx vitest run && npm run build-storybook -- --quiet` — all green; paste the vitest summary line.
- [ ] `cd marketing/web-v10 && npm run build` — green.
- [ ] `git status --short` — list every changed file and confirm nothing outside the file map is touched (the other session's `.claude/launch.json` and `storybook-static/` changes are not ours).
- [ ] Screenshots from Task 2 Step 9 and Task 4 Step 5 attached to the report.
- [ ] Offer to commit in four commits (chrome; glyphs + dock; marketing; docs). Do not commit unless the founder says so.
