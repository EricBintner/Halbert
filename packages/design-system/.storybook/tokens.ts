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
