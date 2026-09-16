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
