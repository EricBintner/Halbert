// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The parser decides whether a line the user typed becomes a picker action or
 * a message to the assistant. Getting that wrong either swallows real messages
 * or sends `/model pin <model>` to the model as prose, so every shape it
 * claims — and every near-miss it must refuse — is pinned here.
 */
import { describe, expect, it } from 'vitest'
import { formatModelStatus, parseModelCommand } from './slashCommands'

describe('parseModelCommand: what it refuses to claim', () => {
  it.each<[string, string]>([
    ['plain prose', 'how much memory is free?'],
    ['prose containing the word', 'which model are you using'],
    ['another command', '/help'],
    ['a longer command sharing the prefix', '/models'],
    ['a command that merely starts with it', '/modelfoo'],
    ['a hyphenated neighbour', '/model-picker'],
    ['the bare word without a slash', 'model'],
    ['a lone slash', '/'],
    ['an empty line', ''],
    ['only whitespace', '   \n  '],
    ['the command mid-sentence', 'try /model status'],
  ])('returns null for %s', (_label, input) => {
    expect(parseModelCommand(input)).toBeNull()
  })
})

describe('parseModelCommand: bare command', () => {
  it('opens the picker', () => {
    expect(parseModelCommand('/model')).toEqual({ kind: 'open' })
  })

  it('tolerates surrounding whitespace', () => {
    expect(parseModelCommand('   /model   ')).toEqual({ kind: 'open' })
  })

  it('ignores the case of the command itself', () => {
    expect(parseModelCommand('/MODEL')).toEqual({ kind: 'open' })
    expect(parseModelCommand('/Model')).toEqual({ kind: 'open' })
  })
})

describe('parseModelCommand: search', () => {
  it('treats an unrecognised argument as a query', () => {
    expect(parseModelCommand('/model model-a')).toEqual({
      kind: 'search',
      query: 'model-a',
    })
  })

  it('keeps a multi-word query intact', () => {
    expect(parseModelCommand('/model some model 7')).toEqual({
      kind: 'search',
      query: 'some model 7',
    })
  })

  it('collapses internal runs of whitespace', () => {
    expect(parseModelCommand('/model   some \t model\n7  ')).toEqual({
      kind: 'search',
      query: 'some model 7',
    })
  })

  it('preserves the case of the query', () => {
    expect(parseModelCommand('/model Model-A')).toEqual({
      kind: 'search',
      query: 'Model-A',
    })
  })
})

describe('parseModelCommand: status', () => {
  it('is recognised', () => {
    expect(parseModelCommand('/model status')).toEqual({ kind: 'status' })
  })

  it('is case-insensitive', () => {
    expect(parseModelCommand('/MODEL Status')).toEqual({ kind: 'status' })
  })

  it('rejects trailing words rather than searching for them', () => {
    const result = parseModelCommand('/model status of the guide')
    expect(result).toEqual({ kind: 'error', message: expect.any(String) })
    expect((result as { message: string }).message).toContain('/model status')
    expect((result as { message: string }).message).toContain('no arguments')
  })
})

describe('parseModelCommand: auto', () => {
  it('is recognised', () => {
    expect(parseModelCommand('/model auto')).toEqual({ kind: 'auto' })
  })

  it('is case-insensitive', () => {
    expect(parseModelCommand('/model AUTO')).toEqual({ kind: 'auto' })
  })

  it('rejects trailing words', () => {
    const result = parseModelCommand('/model auto please')
    expect(result).toEqual({ kind: 'error', message: expect.any(String) })
    expect((result as { message: string }).message).toContain('/model auto')
  })
})

describe('parseModelCommand: pin', () => {
  it.each(['pin', 'lock', 'PIN', 'Lock'])('accepts %s with a name', (keyword) => {
    expect(parseModelCommand(`/model ${keyword} model-a`)).toEqual({
      kind: 'pin',
      query: 'model-a',
    })
  })

  it('keeps the case of the name', () => {
    expect(parseModelCommand('/model pin Model-A')).toEqual({
      kind: 'pin',
      query: 'Model-A',
    })
  })

  it('keeps a multi-word name and collapses whitespace', () => {
    expect(parseModelCommand('/model pin  some   model  7 ')).toEqual({
      kind: 'pin',
      query: 'some model 7',
    })
  })

  it.each(['/model pin', '/model lock', '/model pin   '])(
    'errors with actionable usage for %s',
    (input) => {
      const result = parseModelCommand(input)
      expect(result).toEqual({ kind: 'error', message: expect.any(String) })
      expect((result as { message: string }).message).toContain('/model pin <model>')
    },
  )
})

describe('parseModelCommand: tiers', () => {
  it.each<[string, string]>([
    ['guide', 'guide'],
    ['specialist', 'specialist'],
    ['vision', 'vision'],
    ['chat', 'guide'],
    ['GUIDE', 'guide'],
    ['Specialist', 'specialist'],
  ])('%s alone selects the %s tier with no name', (keyword, tier) => {
    expect(parseModelCommand(`/model ${keyword}`)).toEqual({ kind: 'tier', tier })
  })

  it.each<[string, string]>([
    ['guide', 'guide'],
    ['specialist', 'specialist'],
    ['vision', 'vision'],
  ])('%s with a name pins into the %s tier', (keyword, tier) => {
    expect(parseModelCommand(`/model ${keyword} model-a`)).toEqual({
      kind: 'tier',
      tier,
      query: 'model-a',
    })
  })

  it('keeps the case and spacing of the name', () => {
    expect(parseModelCommand('/model  Vision   Some   Model-B ')).toEqual({
      kind: 'tier',
      tier: 'vision',
      query: 'Some Model-B',
    })
  })

  it('omits the query when only the tier was given', () => {
    const result = parseModelCommand('/model guide')
    expect(result).not.toHaveProperty('query')
  })
})

const baseStatus = {
  activeModel: 'model-a',
  providerLabel: 'Ollama',
  isLocal: true,
  pinned: true,
  tier: 'Chat (Guide)',
}

describe('formatModelStatus', () => {
  it('returns the fixed rows in order when nothing optional is known', () => {
    expect(formatModelStatus(baseStatus)).toEqual([
      { label: 'Model', value: 'model-a' },
      { label: 'Provider', value: 'Ollama' },
      { label: 'Runs on', value: 'This machine' },
      { label: 'Tier', value: 'Chat (Guide)' },
      { label: 'Selection', value: 'Pinned' },
    ])
  })

  it('reports a remote, unpinned model', () => {
    const rows = formatModelStatus({ ...baseStatus, isLocal: false, pinned: false })
    expect(rows).toContainEqual({ label: 'Runs on', value: 'Remote service' })
    expect(rows).toContainEqual({ label: 'Selection', value: 'Automatic' })
  })

  it('appends the optional rows in a stable order', () => {
    const rows = formatModelStatus({
      ...baseStatus,
      contextWindow: 8192,
      endpointUrl: 'http://localhost:11434',
    })
    expect(rows.map((row) => row.label)).toEqual([
      'Model',
      'Provider',
      'Runs on',
      'Tier',
      'Selection',
      'Context',
      'Endpoint',
    ])
    expect(rows[rows.length - 1]).toEqual({
      label: 'Endpoint',
      value: 'http://localhost:11434',
    })
  })

  it.each<[number, string]>([
    [999, '999 tokens'],
    [1000, '1,000 tokens'],
    [8192, '8,192 tokens'],
    [131072, '131,072 tokens'],
    [1048576, '1,048,576 tokens'],
  ])('formats a context window of %i with separators', (contextWindow, value) => {
    const rows = formatModelStatus({ ...baseStatus, contextWindow })
    expect(rows).toContainEqual({ label: 'Context', value })
  })

  it.each<[string, number]>([
    ['zero', 0],
    ['a negative window', -1],
    ['a non-finite window', Number.NaN],
  ])('omits the context row for %s', (_label, contextWindow) => {
    const labels = formatModelStatus({ ...baseStatus, contextWindow }).map((r) => r.label)
    expect(labels).not.toContain('Context')
  })

  it('omits a blank endpoint rather than printing an empty row', () => {
    const labels = formatModelStatus({ ...baseStatus, endpointUrl: '   ' }).map(
      (r) => r.label,
    )
    expect(labels).not.toContain('Endpoint')
  })

  it('trims a padded endpoint', () => {
    const rows = formatModelStatus({ ...baseStatus, endpointUrl: ' http://localhost:1234 ' })
    expect(rows).toContainEqual({ label: 'Endpoint', value: 'http://localhost:1234' })
  })

  it('says so when no model is selected instead of leaving the row blank', () => {
    const rows = formatModelStatus({ ...baseStatus, activeModel: '  ' })
    expect(rows).toContainEqual({ label: 'Model', value: 'None selected' })
  })
})
