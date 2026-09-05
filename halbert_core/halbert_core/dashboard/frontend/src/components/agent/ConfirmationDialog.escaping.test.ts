// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { renderDescription } from './ConfirmationDialog'

describe('renderDescription', () => {
  // This is the one screen where a person authorises a privileged action, and
  // the description carries a model-supplied command. Anything that can
  // influence it -- a filename, a package name, a config file the agent just
  // read -- must not become markup here.
  it('escapes injected tags instead of rendering them', () => {
    const out = renderDescription('<img src=x onerror="alert(1)">')
    expect(out).not.toContain('<img')
    expect(out).toContain('&lt;img')
  })

  it('escapes a script tag', () => {
    const out = renderDescription('<script>fetch("/x")</script>')
    expect(out).not.toContain('<script')
    expect(out).toContain('&lt;script')
  })

  it('cannot be used to overlay reassuring text over an alarming command', () => {
    const out = renderDescription('rm -rf / <div style="position:absolute">safe</div>')
    expect(out).not.toContain('<div')
    expect(out).toContain('rm -rf /')
  })

  it('still renders the formatting it is there for', () => {
    expect(renderDescription('**bold**')).toContain('<strong>bold</strong>')
    expect(renderDescription('`code`')).toContain('<code')
    expect(renderDescription('a\nb')).toContain('<br/>')
  })

  it('escapes inside a code span rather than trusting it', () => {
    const out = renderDescription('`<b>x</b>`')
    expect(out).toContain('<code')
    expect(out).not.toContain('<b>')
    expect(out).toContain('&lt;b&gt;')
  })

  it('handles an empty or missing description', () => {
    expect(renderDescription('')).toBe('')
    expect(renderDescription(undefined as unknown as string)).toBe('')
  })
})
