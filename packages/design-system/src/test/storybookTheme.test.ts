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
