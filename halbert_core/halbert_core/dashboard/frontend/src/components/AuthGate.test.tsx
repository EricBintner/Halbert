// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SEC-1: the browser's view of a shut door.
 *
 * The case that matters most is the last one: when the backend is unreachable
 * the gate must get out of the way, because "here is how to authenticate" is
 * the wrong answer to "the server is down" and would send the user chasing a
 * credential they already have.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthGate } from './AuthGate'

const child = <div>the dashboard</div>

describe('AuthGate', () => {
  const realFetch = window.fetch

  beforeEach(() => {
    delete window.__HALBERT_TOKEN__
    delete window.__HALBERT_API_BASE__
  })

  afterEach(() => {
    window.fetch = realFetch
  })

  it('renders immediately in the desktop app, which carries its own credential', () => {
    window.__HALBERT_TOKEN__ = 'injected'
    const spy = vi.fn()
    window.fetch = spy as unknown as typeof fetch
    render(<AuthGate>{child}</AuthGate>)
    expect(screen.getByText('the dashboard')).toBeTruthy()
    expect(spy).not.toHaveBeenCalled()
  })

  it('renders the dashboard when the session cookie is good', async () => {
    window.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ authenticated: true, credential: 'session' })),
    ) as unknown as typeof fetch
    render(<AuthGate>{child}</AuthGate>)
    await waitFor(() => expect(screen.getByText('the dashboard')).toBeTruthy())
  })

  it('explains how to get in when the caller is unauthenticated', async () => {
    window.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ authenticated: false, credential: 'none' })),
    ) as unknown as typeof fetch
    render(<AuthGate>{child}</AuthGate>)
    await waitFor(() =>
      expect(screen.getByText(/I don't know who you are yet/)).toBeTruthy(),
    )
    expect(screen.getByText(/halbert_core\.dashboard\.ticket/)).toBeTruthy()
    expect(screen.queryByText('the dashboard')).toBeNull()
  })

  it('gets out of the way when the backend is unreachable', async () => {
    window.fetch = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch
    render(<AuthGate>{child}</AuthGate>)
    // A down backend is not a locked door; telling the user to fetch a link
    // would send them after a credential they may already have.
    await waitFor(() => expect(screen.getByText('the dashboard')).toBeTruthy())
  })
})
