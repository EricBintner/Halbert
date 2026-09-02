// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ShellModeContext — the third shell mode (O8).
 *
 * Voice is a mode, not a page: entering it (the /voice route) parks whatever
 * surface the user was on and leaving it restores exactly that surface. The
 * tests pin the store-previous / restore contract, and the fact that voice is
 * a transient posture — a route state, never persisted as the shell the app
 * reopens into.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { ShellModeProvider, useShellMode } from './ShellModeContext'

const STORAGE_KEY = 'halbert:shell-mode'

/** Drive the context from inside so every test goes through the public API. */
function Probe() {
  const { mode, setMode, toggleMode, enterVoice, exitVoice, isEngaged, isVoice } =
    useShellMode()
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="is-engaged">{String(isEngaged)}</span>
      <span data-testid="is-voice">{String(isVoice)}</span>
      <button type="button" onClick={() => setMode('browsing')}>
        to-browsing
      </button>
      <button type="button" onClick={() => setMode('engaged')}>
        to-engaged
      </button>
      <button type="button" onClick={enterVoice}>enter-voice</button>
      <button type="button" onClick={exitVoice}>exit-voice</button>
      <button type="button" onClick={toggleMode}>toggle</button>
    </div>
  )
}

function renderProbe({ stored }: { stored?: ShellModeStored } = {}) {
  if (stored) localStorage.setItem(STORAGE_KEY, stored)
  return render(
    <ShellModeProvider>
      <Probe />
    </ShellModeProvider>,
  )
}

type ShellModeStored = 'engaged' | 'browsing' | 'both'

describe('ShellModeContext voice mode', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('defaults to both (side-by-side) and does not report voice', () => {
    renderProbe()

    expect(screen.getByTestId('mode')).toHaveTextContent('both')
    expect(screen.getByTestId('is-engaged')).toHaveTextContent('false')
    expect(screen.getByTestId('is-voice')).toHaveTextContent('false')
  })

  it('entering voice from browsing stores browsing; leaving restores it', () => {
    renderProbe()

    act(() => {
      screen.getByText('to-browsing').click()
    })
    act(() => {
      screen.getByText('enter-voice').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('voice')
    expect(screen.getByTestId('is-voice')).toHaveTextContent('true')

    act(() => {
      screen.getByText('exit-voice').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('browsing')
  })

  it('entering voice from both restores both on leave', () => {
    renderProbe()

    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('exit-voice').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('both')
  })

  it('entering voice on a fresh load restores the stored base mode', () => {
    renderProbe({ stored: 'browsing' })

    // A deep link to /voice lands here before any base mode was set this
    // session: the stored preference is the surface to return to.
    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('exit-voice').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('browsing')
  })

  it('re-entering voice from voice keeps the original restore point', () => {
    renderProbe()

    act(() => {
      screen.getByText('to-browsing').click()
    })
    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('exit-voice').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('browsing')
  })

  it('honours an explicit base mode chosen while in voice', () => {
    renderProbe()

    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('to-engaged').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('engaged')
    expect(screen.getByTestId('is-voice')).toHaveTextContent('false')
  })

  it('never persists voice as the shell mode', () => {
    renderProbe({ stored: 'browsing' })

    act(() => {
      screen.getByText('enter-voice').click()
    })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('browsing')

    act(() => {
      screen.getByText('exit-voice').click()
    })
    expect(localStorage.getItem(STORAGE_KEY)).toBe('browsing')
  })

  it('leaves the mode shortcut inert while voice owns the shell', () => {
    renderProbe()

    act(() => {
      screen.getByText('enter-voice').click()
    })
    act(() => {
      screen.getByText('toggle').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('voice')
  })

  it('still flips between the two focus states when not in voice', () => {
    renderProbe()

    // Default is 'both'. toggleMode flips to 'engaged' (right-only focus).
    act(() => {
      screen.getByText('toggle').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('engaged')

    // Toggle again flips to 'browsing' (center-only focus).
    act(() => {
      screen.getByText('toggle').click()
    })
    expect(screen.getByTestId('mode')).toHaveTextContent('browsing')
  })
})

/**
 * Panel shortcuts (Cmd/Ctrl+B, +D, +J) must bail when the key lands inside a
 * PTY tile: xterm owns every keystroke in a focused terminal, and flipping
 * or hiding the panel the tile lives in mid-command is exactly the failure
 * the continuous-conversation design (§11 Keyboard) rules out.
 */
function fireShortcut(target: EventTarget, key: string) {
  act(() => {
    target.dispatchEvent(
      new KeyboardEvent('keydown', { key, metaKey: true, bubbles: true, cancelable: true }),
    )
  })
}

describe('ShellModeContext panel shortcuts', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  function renderWithTerminal() {
    return render(
      <ShellModeProvider>
        <Probe />
        <div className="xterm">
          <textarea data-testid="pty" aria-label="terminal input" />
        </div>
        <input data-testid="plain" aria-label="plain input" />
      </ShellModeProvider>,
    )
  }

  it('flips the focus state on Cmd+B from an ordinary target', () => {
    renderWithTerminal()
    fireShortcut(screen.getByTestId('plain'), 'b')
    expect(screen.getByTestId('mode')).toHaveTextContent('engaged')
  })

  it('bails on Cmd+B when the key lands inside an .xterm element', () => {
    renderWithTerminal()
    fireShortcut(screen.getByTestId('pty'), 'b')
    expect(screen.getByTestId('mode')).toHaveTextContent('both')
  })

  it('bails on Cmd+D and Cmd+J inside an .xterm element too', () => {
    renderWithTerminal()
    fireShortcut(screen.getByTestId('pty'), 'd')
    expect(screen.getByTestId('mode')).toHaveTextContent('both')
    fireShortcut(screen.getByTestId('pty'), 'j')
    expect(screen.getByTestId('mode')).toHaveTextContent('both')
  })

  it('leaves the keystroke to xterm (no preventDefault) inside a tile', () => {
    renderWithTerminal()
    const event = new KeyboardEvent('keydown', {
      key: 'b',
      metaKey: true,
      bubbles: true,
      cancelable: true,
    })
    act(() => {
      screen.getByTestId('pty').dispatchEvent(event)
    })
    expect(event.defaultPrevented).toBe(false)
  })
})
