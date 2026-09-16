// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Ruling B (2026-09-16): the click is the confirmation.
 *
 * `exec "${SHELL:-/bin/bash}" -i` is a wrapper head and classifies HIGH, so
 * after ruling B a bare spawn of it is a 428 and this button showed
 * "spawn failed: 428". But a person who just pressed "Open a shell" has
 * confirmed exactly that; the shell runs nothing until they type into it,
 * and the sandbox still applies. So the launcher passes force. Asking
 * "open a shell?" after the click would be friction with no safety in it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const spawnMock = vi.hoisted(() => vi.fn().mockResolvedValue('s1'))
vi.mock('../../hooks/useTerminalSessions', () => ({
  useTerminalSessions: () => ({ spawn: spawnMock }),
}))

import { ShellLauncher } from './ShellLauncher'

describe('ShellLauncher — the click is the confirmation', () => {
  beforeEach(() => spawnMock.mockClear())

  it('opens the shell with force, because the person just asked for a shell', async () => {
    render(<ShellLauncher />)
    await userEvent.click(screen.getByRole('button', { name: 'Open a shell' }))
    expect(spawnMock).toHaveBeenCalledTimes(1)
    const [command, opts] = spawnMock.mock.calls[0]
    expect(command).toContain('exec')
    expect(opts).toEqual({ force: true })
  })
})
