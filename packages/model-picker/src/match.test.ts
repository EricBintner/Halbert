// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, expect, it } from 'vitest'
import { matchModels, scoreMatch } from './match'
import type { DiscoveredModel } from './types'

function model(id: string, endpointId = 'ep-1', name = id): DiscoveredModel {
  return {
    id,
    name,
    endpointId,
    provider: 'ollama',
    isLocal: true,
    capabilities: {},
  }
}

describe('scoreMatch', () => {
  it('ranks an exact match above a prefix match', () => {
    expect(scoreMatch('alpha', 'alpha')).toBeGreaterThan(
      scoreMatch('alphabet', 'alpha'),
    )
  })

  it('ranks a prefix above a segment prefix', () => {
    expect(scoreMatch('coder-small', 'coder')).toBeGreaterThan(
      scoreMatch('small-coder', 'coder'),
    )
  })

  it('ranks a segment prefix above a bare substring', () => {
    expect(scoreMatch('small-coder', 'coder')).toBeGreaterThan(
      scoreMatch('encoder', 'coder'),
    )
  })

  it('ranks a substring above a scattered subsequence', () => {
    expect(scoreMatch('encoder', 'code')).toBeGreaterThan(
      scoreMatch('cxoxdxe', 'code'),
    )
  })

  it('is case-insensitive in both directions', () => {
    expect(scoreMatch('AlphaBeta', 'alphabeta')).toBe(scoreMatch('alphabeta', 'ALPHABETA'))
  })

  it.each(['-', '_', ':', '.', '/', ' '])(
    'treats %s as a segment boundary',
    (sep) => {
      expect(scoreMatch(`small${sep}coder`, 'coder')).toBe(
        scoreMatch('small-coder', 'coder'),
      )
    },
  )

  it('scores a non-match zero', () => {
    expect(scoreMatch('alpha', 'zzz')).toBe(0)
  })

  it('does not match when the characters are out of order', () => {
    expect(scoreMatch('abc', 'cba')).toBe(0)
  })

  it('treats a whitespace-only query as empty', () => {
    expect(scoreMatch('anything', '   ')).toBe(scoreMatch('anything', ''))
  })
})

describe('matchModels', () => {
  it('returns everything in arrival order for an empty query', () => {
    const models = [model('c'), model('a'), model('b')]
    expect(matchModels(models, '').map((m) => m.id)).toEqual(['c', 'a', 'b'])
  })

  it('does not mutate the input array', () => {
    const models = [model('c'), model('a')]
    matchModels(models, '')
    expect(models.map((m) => m.id)).toEqual(['c', 'a'])
  })

  it('drops non-matches', () => {
    const found = matchModels([model('alpha'), model('zulu')], 'alph')
    expect(found.map((m) => m.id)).toEqual(['alpha'])
  })

  it('puts the better tier first regardless of input order', () => {
    const scattered = [model('encoder'), model('coder-x'), model('coder')]
    expect(matchModels(scattered, 'coder').map((m) => m.id)).toEqual([
      'coder',
      'coder-x',
      'encoder',
    ])
  })

  it('breaks a tie toward the shorter name', () => {
    const found = matchModels([model('alpha-longer'), model('alpha-x')], 'alpha')
    expect(found[0].id).toBe('alpha-x')
  })

  it('is a total order, so equal-length ties never shuffle', () => {
    const a = [model('ab-1', 'ep-a'), model('ab-1', 'ep-b')]
    const b = [model('ab-1', 'ep-b'), model('ab-1', 'ep-a')]
    expect(matchModels(a, 'ab').map((m) => m.endpointId)).toEqual(
      matchModels(b, 'ab').map((m) => m.endpointId),
    )
  })

  it('matches on the wire id when the display name differs', () => {
    const found = matchModels([model('wire-id', 'ep-1', 'Friendly Name')], 'wire')
    expect(found).toHaveLength(1)
  })

  it('matches on the display name when the id differs', () => {
    const found = matchModels([model('opaque-1', 'ep-1', 'Friendly Name')], 'friendly')
    expect(found).toHaveLength(1)
  })

  it('ranks by whichever of the two fields matches better', () => {
    const found = matchModels(
      [model('zzz', 'ep-1', 'alpha-suffix'), model('alpha', 'ep-2', 'zzz')],
      'alpha',
    )
    expect(found[0].endpointId).toBe('ep-2')
  })

  it('returns an empty array rather than throwing on no models', () => {
    expect(matchModels([], 'anything')).toEqual([])
  })
})
