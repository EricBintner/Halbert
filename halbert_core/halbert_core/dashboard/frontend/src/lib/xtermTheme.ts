// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The terminal's colours, derived from the design tokens.
 *
 * xterm paints to a canvas and cannot read CSS variables, so the surface
 * colours are resolved from the document at construction time — which means
 * the terminal follows the light/dark swap like everything else instead of
 * being the one pane that stayed on someone's editor theme.
 *
 * The ANSI palette cannot come from the tokens: a terminal needs sixteen
 * mutually distinguishable colours and the brand only defines four diagnostic
 * pigments. So the pigments anchor red/green/yellow/blue and the rest are
 * drawn to match them — desaturated, mid-century, and legible on the ground
 * they sit on. Every entry except the two documented below clears 4.5:1
 * against the terminal's own background in its own theme.
 */

export interface XtermPalette {
  background: string
  foreground: string
  cursor: string
  cursorAccent: string
  selectionBackground: string
  black: string; red: string; green: string; yellow: string
  blue: string; magenta: string; cyan: string; white: string
  brightBlack: string; brightRed: string; brightGreen: string; brightYellow: string
  brightBlue: string; brightMagenta: string; brightCyan: string; brightWhite: string
}

/* Two entries are deliberately below the text floor, as in every terminal
 * theme ever shipped:
 *   - `black` on a dark ground. ANSI black IS the dark ground; a program that
 *     prints black on default is unreadable there by construction.
 *   - `brightBlack`, which is the conventional "dim / comment" colour and is
 *     supposed to recede. */
const ANSI_LIGHT = {
  black: '#1C1917', red: '#BC3A2A', green: '#2B7552', yellow: '#955B15',
  blue: '#386C8A', magenta: '#7A4B7A', cyan: '#2A6F6B', white: '#6B645F',
  brightBlack: '#877F7A', brightRed: '#A8301F', brightGreen: '#1F6244',
  brightYellow: '#7A4810', brightBlue: '#2A5470', brightMagenta: '#623A62',
  brightCyan: '#1E5854', brightWhite: '#1C1917',
} as const

const ANSI_DARK = {
  black: '#2E2B29', red: '#D96455', green: '#38996C', yellow: '#C2761B',
  blue: '#4B8FB6', magenta: '#B08BB0', cyan: '#5AA9A3', white: '#C4BDB1',
  brightBlack: '#787169', brightRed: '#E88070', brightGreen: '#4FB585',
  brightYellow: '#D98F31', brightBlue: '#6BA9CC', brightMagenta: '#C7A5C7',
  brightCyan: '#74C2BC', brightWhite: '#F2EEE6',
} as const

function readToken(token: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return value || fallback
}

function isDark(): boolean {
  if (typeof document === 'undefined') return false
  const root = document.documentElement
  if (root.getAttribute('data-theme') === 'dark' || root.classList.contains('dark')) return true
  if (root.getAttribute('data-theme') === 'light' || root.classList.contains('light')) return false
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
}

export function xtermTheme(): XtermPalette {
  const dark = isDark()
  const ansi = dark ? ANSI_DARK : ANSI_LIGHT
  const background = readToken('--color-surface-subtle', dark ? '#131211' : '#EDE8DC')
  return {
    // The terminal interior is a recessed tray, not the page field.
    background,
    foreground: readToken('--color-ink', dark ? '#F2EEE6' : '#1C1917'),
    // The letterpress cursor.
    cursor: readToken('--color-accent-strong', dark ? '#E8683C' : '#C4451D'),
    cursorAccent: background,
    selectionBackground: readToken('--color-accent-tint', dark ? '#2D1C16' : '#FDF2EE'),
    ...ansi,
  }
}

/**
 * Resolve before xterm measures its cell grid.
 *
 * xterm sizes the grid from the mounted font at construction. Now that
 * JetBrains Mono is self-hosted rather than always-warm from a CDN, a cold
 * load can measure the fallback and lock in a grid that is wrong for every
 * row after it. Optional-called because jsdom has no `document.fonts`.
 */
export function terminalFontReady(size = 13): Promise<unknown> {
  return Promise.resolve(document.fonts?.load?.(`${size}px "JetBrains Mono"`))
}
