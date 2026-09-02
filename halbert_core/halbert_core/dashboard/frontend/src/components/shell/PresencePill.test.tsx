// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PresencePill — the top-bar identity indicator.
 *
 * The pill's own info fetch must go through the resolved API base: a bare
 * relative URL resolves against tauri://localhost in the packaged app and
 * the pill shows the fallback body name regardless of the backend. And a
 * body switch persists, so the pill that mounts after the reload reports
 * the switched-to body as active (W1-02 / W4-03).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PresencePill } from './PresencePill'
import { setInstanceEndpoint } from '@/lib/apiBase'

function stubInfoFetch() {
  const fetchMock = vi.fn().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: async () => ({
        persona_id: 'p',
        scene_context: 'desk',
        role: 'host',
        variant: 'workstation',
        display_name: 'Macky',
        port: 8000,
        features: { home: false, gpu: false, development: false, wyoming_port: 0 },
        data_dir: '',
        config_dir: '',
        body_name: 'desk',
        singular: true,
      }),
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mount() {
  return render(
    <MemoryRouter>
      <PresencePill />
    </MemoryRouter>,
  )
}

describe('PresencePill', () => {
  beforeEach(() => {
    localStorage.clear()
    setInstanceEndpoint(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete window.__HALBERT_API_BASE__
    setInstanceEndpoint(null)
    localStorage.clear()
  })

  it('fetches the local body through the resolved API base (Tauri webview)', async () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const fetchMock = stubInfoFetch()
    mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8042/api/instance/info'),
    )
    expect(await screen.findByText('Macky @ desk')).toBeInTheDocument()
  })

  it('fetches the switched-to body after a reload', async () => {
    // The switch happened on the previous page load; the override outlived it.
    setInstanceEndpoint('http://x:8001')
    const fetchMock = stubInfoFetch()
    mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('http://x:8001/api/instance/info'),
    )
  })
})
