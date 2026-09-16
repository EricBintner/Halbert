// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The pre-flight reads the honest field.
 *
 * A code block's Run stages the command at the shell prompt (HostShell's
 * handleRunCommand dispatches; runOnHost stages; nothing executes). The
 * PTY the person then presses Enter in has no classifier, so this
 * pre-flight warning is the only place the classifier's judgment can reach
 * a staged command. Ruling B (2026-09-16) made /check-safety answer
 * `requires_confirmation: true` on a HIGH verdict; the pre-flight keyed on
 * the SafetyTier field alone and never read it, so `hostname evil` -- tier
 * SAFE, verdict HIGH -- staged with no warning at all.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const checkCommandSafety = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ api: { checkCommandSafety } }))

import { CodeBlock } from './CodeBlock'

const highVerdictSafeTier = {
  command: 'hostname evil',
  tier: 'safe',
  allowed: true,
  warning: 'Unrecognised command: not on the read-only list',
  requires_confirmation: true,
  suggestion: '',
}

describe('CodeBlock pre-flight — requires_confirmation', () => {
  beforeEach(() => checkCommandSafety.mockReset())

  it('warns before staging when the classifier asks, even at tier safe', async () => {
    checkCommandSafety.mockResolvedValue(highVerdictSafeTier)
    const onRun = vi.fn().mockResolvedValue({})
    render(<CodeBlock code="hostname evil" lang="bash" onRun={onRun} showRunButton />)
    await userEvent.click(screen.getByTitle('Run in Terminal'))
    await screen.findByText(/Caution/)
    expect(screen.getByText(/not on the read-only list/)).toBeTruthy()
    expect(onRun).not.toHaveBeenCalled()
  })

  it('still stages straight through when nothing asks', async () => {
    checkCommandSafety.mockResolvedValue({ ...highVerdictSafeTier, requires_confirmation: false, warning: '' })
    const onRun = vi.fn().mockResolvedValue({})
    render(<CodeBlock code="ls -la" lang="bash" onRun={onRun} showRunButton />)
    await userEvent.click(screen.getByTitle('Run in Terminal'))
    await waitFor(() => expect(onRun).toHaveBeenCalledWith('ls -la'))
  })
})
