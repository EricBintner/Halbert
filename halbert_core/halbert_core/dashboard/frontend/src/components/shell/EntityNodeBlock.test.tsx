// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * EntityNodeBlock — rail header with entity label + node buttons.
 *
 * The switch persists the endpoint override to localStorage and reloads; the
 * test asserts the persisted override (the durable part) rather than the
 * reload itself, which jsdom cannot perform.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { EntityNodeBlock, PRESENCE_WINDOW_MS } from './EntityNodeBlock'
import { getInstanceEndpoint, setInstanceEndpoint } from '@/lib/apiBase'

const INFO = {
  persona_id: 'p',
  display_name: 'Halbert',
  body_name: 'desk',
  role: 'host',
  singular: true,
  features: { home: false, gpu: false, development: false, wyoming_port: 0 },
}

const NOW = Date.now()

const peer = (over: Partial<Record<string, unknown>>) => ({
  node_id: 'n150',
  node_name: 'N150',
  role: 'home',
  endpoint: 'http://n150.lan:8001',
  capabilities: [],
  compute_direction: 'outbound',
  wol_enabled: false,
  wol_mac: null,
  wol_broadcast: null,
  paired_at: '2026-09-01T00:00:00Z',
  last_seen: new Date(NOW - 60_000).toISOString(),
  revoked: false,
  ...over,
})

function stubFetch(devices: unknown[] = [], info: unknown = INFO) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
    if (String(url).includes('/api/devices')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          status: 'ok', entity_mode: 'singular', body_name: 'desk',
          canonical_memory_url: '', canonical_thread_url: '', devices,
        }),
      })
    }
    if (String(url).includes('/api/instance/info')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(info) })
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
  }))
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="path">{location.pathname}</div>
}

function renderBlock(initialPath = '/storage') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<><EntityNodeBlock /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  setInstanceEndpoint(null)
  localStorage.clear()
})

afterEach(() => {
  setInstanceEndpoint(null)
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('EntityNodeBlock', () => {
  it('renders the entity name as a label, not a button', async () => {
    stubFetch()
    renderBlock()
    await waitFor(() => expect(screen.getByText('Halbert')).toBeInTheDocument())
    expect(screen.getByText('Halbert').closest('button')).toBeNull()
  })

  it('single node: one button, marked current, no peer dots', async () => {
    stubFetch([])
    renderBlock()
    const btn = await screen.findByRole('button', { name: /desk/ })
    expect(btn).toHaveAttribute('aria-current', 'true')
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })

  it('the node button IS the landing page: clicking the active node goes to /', async () => {
    stubFetch()
    renderBlock('/storage')
    expect(screen.getByTestId('path')).toHaveTextContent('/storage')
    await userEvent.click(await screen.findByRole('button', { name: /desk/ }))
    expect(screen.getByTestId('path')).toHaveTextContent('/')
  })

  it('lists linked nodes and excludes revoked ones', async () => {
    stubFetch([peer({}), peer({ node_id: 'old', node_name: 'Old Box', revoked: true })])
    renderBlock()
    await screen.findByRole('button', { name: /N150/ })
    expect(screen.queryByText('Old Box')).not.toBeInTheDocument()
  })

  it('peer presence comes from last_seen: recent is filled, stale is hollow', async () => {
    stubFetch([
      peer({ node_id: 'a', node_name: 'Fresh', last_seen: new Date(NOW - 30_000).toISOString() }),
      peer({ node_id: 'b', node_name: 'Stale', last_seen: new Date(NOW - PRESENCE_WINDOW_MS * 4).toISOString() }),
      peer({ node_id: 'c', node_name: 'Never', last_seen: null }),
    ])
    renderBlock()
    const fresh = await screen.findByRole('button', { name: /Fresh/ })
    const stale = screen.getByRole('button', { name: /Stale/ })
    const never = screen.getByRole('button', { name: /Never/ })
    expect(fresh).toHaveAttribute('title', expect.stringContaining('online now'))
    expect(stale).toHaveAttribute('title', expect.stringContaining('last seen'))
    expect(never).toHaveAttribute('title', expect.stringContaining('never seen online'))
  })

  it('clicking a peer persists the endpoint override (the switch artifact)', async () => {
    stubFetch([peer({})])
    renderBlock()
    await userEvent.click(await screen.findByRole('button', { name: /N150/ }))
    expect(getInstanceEndpoint()).toBe('http://n150.lan:8001')
    expect(localStorage.getItem('halbert:active-body')).toBe('http://n150.lan:8001')
  })

  it('falls back to "this machine" while instance info has not loaded', async () => {
    stubFetch([], null)
    renderBlock()
    expect(screen.getByRole('button', { name: /this machine/ })).toBeInTheDocument()
    // Let the two fetches settle so their state updates land inside act().
    await waitFor(() => expect(screen.getAllByRole('button')).toHaveLength(1))
  })

  it('the entity label carries the mode — the old pill tooltip moved here', async () => {
    stubFetch()
    renderBlock()
    await waitFor(() =>
      expect(screen.getByText('Halbert')).toHaveAttribute(
        'title', 'Halbert — Singular Entity (shared memory across machines)',
      ))
  })

  it('independent: the label names the mode the ratified way', async () => {
    stubFetch([], { ...INFO, singular: false })
    renderBlock()
    await waitFor(() =>
      expect(screen.getByText('Halbert')).toHaveAttribute(
        'title', 'Halbert — Independent Node (own memory)',
      ))
  })
})
