// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-3's two notices, and the live region neither of them is.
 *
 * The fallback line — what was asked for was unreachable, something else
 * answered — carried `role="status"`, an implicit polite live region, on an
 * element that mounts and unmounts. `lib/announce.ts` states the rule: "a live
 * region only works when there is exactly one of each kind", and the shell owns
 * it.
 *
 * There is a second reason this one could not stay here, particular to this
 * component: AgentChat renders it twice over the life of one turn, once while
 * the turn is live and once after (the two slots are gated apart by
 * `liveUser`, so they are never on screen together, but they do both mount in
 * sequence). A region that speaks when it mounts would have said the same
 * sentence twice. The fact arrives once — on `model_selected` — so that is
 * where it is spoken; see useAgentStream.fallback.test.ts.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TurnModelNotice } from './TurnModelNotice'
import type { TurnModelInfo } from '@/hooks/useAgentStream'

const TURN: TurnModelInfo = {
  model: 'answered-here', endpoint: 'http://localhost:11434', provider: 'ollama',
  tier: 'guide', pinned: false, escalated: false, reason: '',
}

const politeRegions = (c: HTMLElement) =>
  c.querySelectorAll('[role="status"], [aria-live="polite"]')

describe('TurnModelNotice', () => {
  it('shows a fallback without declaring a live region for it', () => {
    const { container } = render(
      <TurnModelNotice turn={{ ...TURN, fallbackFrom: 'asked-for-this' }} />,
    )
    // Still on screen, and still says both halves: "the one you pinned" and
    // "the one that answered" must never look alike.
    expect(screen.getByText('asked-for-this')).toBeInTheDocument()
    expect(screen.getByText('answered-here')).toBeInTheDocument()
    expect(screen.getByText(/was unavailable/)).toBeInTheDocument()

    expect(politeRegions(container)).toHaveLength(0)
  })

  it('shows an escalation, and declares no region for that either', () => {
    const { container } = render(
      <TurnModelNotice turn={{ ...TURN, escalated: true }} />,
    )
    expect(screen.getByText(/Escalated to the specialist/)).toBeInTheDocument()
    expect(politeRegions(container)).toHaveLength(0)
  })

  it('says nothing at all for an ordinary turn', () => {
    const { container } = render(<TurnModelNotice turn={TURN} />)
    expect(container).toBeEmptyDOMElement()
  })
})
