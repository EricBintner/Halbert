// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Cold start: what the switch says before it knows the machine's name.
 *
 * Lives in its own file on purpose. The identity store is a module-level
 * singleton that deliberately holds the last known name across mounts — so the
 * label never flashes when you toggle modes — which means "has never resolved"
 * is only reachable in a fresh module. Vitest isolates per file, so this is
 * the honest way to reach it without a test-only reset hatch.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ModeSwitch } from './ModeSwitch'
import { ShellModeProvider } from '@/contexts/ShellModeContext'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('ModeSwitch cold start', () => {
  it('falls back to the app name before identity resolves', () => {
    // A fetch that never settles: the tab still has to say something.
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))

    render(
      <ShellModeProvider>
        <ModeSwitch />
      </ShellModeProvider>,
    )

    expect(screen.getByText('Halbert')).toBeInTheDocument()
  })
})
