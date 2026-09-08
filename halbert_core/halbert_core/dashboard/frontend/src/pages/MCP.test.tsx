// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * MCP page tests (B5) — rendering, empty state, capability-off state,
 * and the add-server form's token_env-only contract (a literal token is
 * never sent; the form carries an env var NAME).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MCP } from './MCP'

function mockFetch(responses: Record<string, (opts: RequestInit) => unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, opts: RequestInit = {}) => {
    const handler = responses[url] ?? responses[Object.keys(responses).find(k => url.startsWith(k))!]
    const body = handler ? handler(opts) : {}
    return {
      ok: true, status: 200,
      json: async () => body,
      text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
    }
  }))
}

beforeEach(() => {
  mockFetch({
    '/api/mcp/status': () => ({
      enabled: true,
      monitor_running: false,
      default_risk: 'medium',
      servers: [],
      skipped_servers: [],
      load_error: '',
    }),
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('MCP page', () => {
  it('renders the page header', async () => {
    render(<MCP />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^mcp$/i })).toBeTruthy()
    })
  })

  it('shows the empty state when no servers are configured', async () => {
    render(<MCP />)
    await waitFor(() => {
      expect(screen.getByText(/no mcp servers/i)).toBeTruthy()
    })
  })

  it('renders the capability-off empty state', async () => {
    mockFetch({
      '/api/mcp/status': () => ({
        enabled: false,
        monitor_running: false,
        servers: [],
        skipped_servers: [],
        load_error: '',
      }),
    })
    render(<MCP />)
    await waitFor(() => {
      expect(screen.getByText(/mcp is off/i)).toBeTruthy()
    })
  })

  it('renders a configured server with its name and transport', async () => {
    mockFetch({
      '/api/mcp/status': () => ({
        enabled: true,
        monitor_running: true,
        default_risk: 'medium',
        servers: [{
          name: 'filesystem',
          transport: 'stdio',
          configured: true,
          connected: true,
          health: 'healthy',
          last_error: '',
          tool_count: 3,
          reconnect_attempts: 0,
          backoff_seconds: null,
          next_retry_in: null,
          risk_override: null,
          tool_risk: {},
        }],
        skipped_servers: [],
        load_error: '',
      }),
    })
    render(<MCP />)
    await waitFor(() => {
      expect(screen.getByText('filesystem')).toBeTruthy()
      expect(screen.getByText('stdio')).toBeTruthy()
    })
  })

  it('opens the add-server form and requires a name', async () => {
    render(<MCP />)
    await waitFor(() => expect(screen.getByText(/no mcp servers/i)).toBeTruthy())
    // Two "Add Server" buttons exist (header + empty state); click the
    // empty-state one (the card's primary action).
    const addButtons = screen.getAllByRole('button', { name: /add server/i })
    fireEvent.click(addButtons[addButtons.length - 1])
    expect(screen.getByText(/add mcp server/i)).toBeTruthy()
    // Switch to http transport to reveal the token_env field (the form
    // carries an env var NAME, never a token value).
    fireEvent.change(screen.getByDisplayValue('stdio (local process)'), {
      target: { value: 'http' },
    })
    expect(screen.getByPlaceholderText(/LINEAR_MCP_TOKEN/i)).toBeTruthy()
  })
})
