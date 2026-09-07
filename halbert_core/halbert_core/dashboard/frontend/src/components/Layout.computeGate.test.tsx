// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The Shared Compute rail item is gated on linked-node count (revised design
 * §3.1 principle 5: "Shared compute only when more than one node exists").
 *
 * Layout counts nodes from /api/devices the way the rail's EntityNodeBlock
 * does — revoked devices and endpoint-less records excluded — and hides
 * /compute until a second linked node exists. A single-machine install sees
 * zero cluster chrome (constraint 9).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider } from '@/contexts/ShellModeContext'

/** The NavRail sections Layout last rendered — captured from the mock. */
let capturedSections: Array<{ items: Array<{ id: string }> }> | null = null

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    NavRail: (props: { sections?: Array<{ items: Array<{ id: string }> }> }) => {
      capturedSections = props.sections ?? null
      return <div data-testid="nav-rail" />
    },
  }
})

function device(overrides: Record<string, unknown> = {}) {
  return {
    node_id: 'n150',
    node_name: 'N150',
    endpoint: 'http://n150.lan:8001',
    capabilities: [],
    paired_at: '2026-09-01T00:00:00Z',
    last_seen: '2026-09-07T12:00:00Z',
    revoked: false,
    role: 'host',
    ...overrides,
  }
}

function renderShell(devices: ReturnType<typeof device>[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/api/devices')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: 'ok',
            entity_mode: 'independent',
            body_name: 'desk',
            canonical_memory_url: '',
            canonical_thread_url: '',
            devices,
          }),
        })
      }
      if (typeof url === 'string' && url.includes('/api/settings/approvals/pending')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ pending: [], blocked_by_rules: 0 }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ role: 'standalone', features: { home: true, gpu: true, development: true } }),
      })
    }),
  )
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ShellModeProvider>
        <Layout>
          <Routes>
            <Route path="*" element={<div data-testid="page-child" />} />
          </Routes>
        </Layout>
      </ShellModeProvider>
    </MemoryRouter>,
  )
}

/** Rail item ids from the last rendered NavRail props. */
function railIds(): string[] {
  return (capturedSections ?? []).flatMap((s) => s.items.map((i) => i.id))
}

/** Wait until instance info and devices have both landed (the gate's inputs). */
async function awaitRailSettled(): Promise<void> {
  await waitFor(() => {
    expect(capturedSections).toBeTruthy()
    // Machine tools are never capability-gated here; when they are present,
    // instance info has loaded. The devices fetch sets linkedNodeCount; the
    // per-test waitFor below then polls to the post-gate state.
    expect(railIds()).toContain('/services')
  })
}

describe('Layout Shared Compute gate', () => {
  beforeEach(() => {
    capturedSections = null
    localStorage.clear()
    // 'browsing' keeps the right panel (HostShell/AgentChat) unmounted —
    // jsdom has no scrollIntoView, and this test only cares about the rail.
    localStorage.setItem('halbert:shell-mode', 'browsing')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('shows Shared Compute when a second linked node exists', async () => {
    renderShell([device()])
    await awaitRailSettled()
    await waitFor(() => expect(railIds()).toContain('/compute'))
  })

  it('hides Shared Compute on a single-node install', async () => {
    renderShell([])
    await awaitRailSettled()
    // The item renders in the pre-devices null state, then hides — wait for
    // the settled rail, not a snapshot taken mid-flight.
    await waitFor(() => expect(railIds()).not.toContain('/compute'))
    // The machine tools stay — hiding compute must not hollow out the rail.
    expect(railIds()).toContain('/services')
  })

  it('does not count revoked devices as linked nodes', async () => {
    renderShell([device({ revoked: true }), device({ node_id: 'n3', node_name: 'no-endpoint', endpoint: null })])
    await awaitRailSettled()
    await waitFor(() => expect(railIds()).not.toContain('/compute'))
  })
})