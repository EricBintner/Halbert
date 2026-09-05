// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One guard for the ratified vocabulary, over every source file.
 *
 * The reason this is one repo-wide test and not another per-component
 * assertion: EntityIdentityCard said "Independent Body" while PresencePill
 * said "Independent Node", on two screens a user can have open at once, and
 * SIXTEEN vocabulary tests were green the whole time. Each of them checked
 * its own component against its own idea of the vocabulary. Two of them --
 * EntityIdentityCard.vocabulary and DevicesTab -- had been edited to match
 * the drift, so the drift looked verified.
 *
 * DECISIONS.md 2026-09-01 sets the UI strings: "UI says Halbert / Identity &
 * Voice / Singular Entity / Independent Node / Linked Devices".
 *
 * WHAT THIS CANNOT DO. It matches strings, so it catches a term that was
 * REPLACED, not one that was never used. It also deliberately does not ban
 * the bare word "node": CORE-CONCEPTS bans it as the noun for a physical
 * device, and no string match distinguishes that from `node_modules`, a DOM
 * node, or the ratified mode name. Getting that wrong in the other direction
 * is what caused this defect.
 */

import { describe, it, expect } from 'vitest'

/**
 * Every source file, as text, via Vite's own raw glob.
 *
 * Deliberately not `node:fs`: this project's tsconfig carries no @types/node,
 * so importing it typechecks clean under vitest and red under `tsc --noEmit`.
 * (Which is how the first version of this file shipped: the frontend gate ran
 * before the file existed.)
 */
const SOURCES = import.meta.glob('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>


/**
 * Blank out comments, keeping line numbers.
 *
 * Prose explaining why a term was retired names the term, and a multi-line
 * JSX comment has no marker on its continuation lines -- so a per-line
 * `//`-strip flags the explanation as the offence.
 */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, (m) => ' '.repeat(m.length))
}

/** Terms that were tried, rejected, and must not come back. */
const RETIRED: Array<{ bad: RegExp; use: string; why: string }> = [
  {
    bad: /Independent Body/i,
    use: 'Independent Node',
    why: 'DECISIONS.md 2026-09-01 names the mode. The avoid-list entry for '
      + '"node" is in the Physical device row and bans it as the noun for a '
      + 'machine; it does not rename a mode.',
  },
]

describe('ratified vocabulary', () => {
  const files = Object.keys(SOURCES)

  it('finds source files to check', () => {
    expect(files.length).toBeGreaterThan(100)
  })

  for (const { bad, use, why } of RETIRED) {
    it(`does not say "${bad.source}" anywhere`, () => {
      const offenders: string[] = []
      for (const file of files) {
        // This file names the retired terms in order to ban them.
        if (file.endsWith('/vocabulary.guard.test.ts')) continue
        stripComments(SOURCES[file]).split('\n').forEach((line, i) => {
          if (bad.test(line)) offenders.push(`${file}:${i + 1}`)
        })
      }
      expect(offenders, `use "${use}" instead. ${why}`).toEqual([])
    })
  }

  it('both surfaces that name the mode agree on the name', () => {
    const surfaces = [
      './components/settings/devices/EntityIdentityCard.tsx',
      './components/shell/PresencePill.tsx',
    ]
    for (const rel of surfaces) {
      const text = SOURCES[rel]
      expect(text, `${rel} was not found by the glob`).toBeTruthy()
      expect(text, `${rel} should name the ratified mode`).toContain('Independent Node')
    }
  })
})
