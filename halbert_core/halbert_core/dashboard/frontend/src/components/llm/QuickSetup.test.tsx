// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The fresh-install flow. Auto-discovery can say an engine is running; only
 * this says which of the models already installed is a sensible first choice,
 * and what to do when nothing is running at all.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuickSetup } from './QuickSetup'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function status(local: { reachable: boolean; model_count: number }) {
  return {
    chat: { configured: false, model: '', endpoint_url: '', provider: '', reachable: false, model_available: false },
    local_ollama: { reachable: local.reachable, url: 'http://localhost:11434', model_count: local.model_count },
    hardware: { tier: 3, total_vram_gb: 32 },
  }
}

let fetchMock: ReturnType<typeof vi.fn>

function serve(local: { reachable: boolean; model_count: number }, applyBody?: unknown) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/model/apply-recommended') && init?.method === 'POST') {
      return jsonResponse(applyBody ?? { success: true, message: 'Applied.' })
    }
    if (u.includes('/model/status')) return jsonResponse(status(local))
    return jsonResponse({})
  })
  vi.stubGlobal('fetch', fetchMock)
}

beforeEach(() => { serve({ reachable: true, model_count: 3 }) })
afterEach(() => vi.unstubAllGlobals())

describe('QuickSetup', () => {
  it('offers a hardware-fitted choice when an engine has models', async () => {
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText(/detected with 3 models/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /largest model that fits/i })).toBeInTheDocument()
  })

  it('says so when the engine is running but empty, rather than offering nothing', async () => {
    serve({ reachable: true, model_count: 0 })
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText(/no models yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument()
  })

  it('tells the user how to start an engine when none is reachable', async () => {
    serve({ reachable: false, model_count: 0 })
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText(/no llm endpoint is reachable/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run in terminal/i })).toBeInTheDocument()
  })

  it('asks the host to run the command rather than pretending to run it', async () => {
    serve({ reachable: false, model_count: 0 })
    const heard: string[] = []
    const listener = (e: Event) => heard.push((e as CustomEvent).detail?.command)
    window.addEventListener('halbert:run-command', listener)
    render(<QuickSetup onApplied={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /run in terminal/i }))
    window.removeEventListener('halbert:run-command', listener)
    expect(heard).toEqual(['ollama serve'])
  })

  it('reloads the picker only when applying actually succeeded', async () => {
    const onApplied = vi.fn()
    render(<QuickSetup onApplied={onApplied} />)
    await userEvent.click(await screen.findByRole('button', { name: /largest model that fits/i }))
    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1))
  })

  it('reports a failed apply and does not reload', async () => {
    serve({ reachable: true, model_count: 3 }, { success: false, message: 'Nothing fits your hardware budget.' })
    const onApplied = vi.fn()
    render(<QuickSetup onApplied={onApplied} />)
    await userEvent.click(await screen.findByRole('button', { name: /largest model that fits/i }))
    expect(await screen.findByText(/nothing fits your hardware budget/i)).toBeInTheDocument()
    expect(onApplied).not.toHaveBeenCalled()
  })

  it('renders nothing when the status call fails, rather than an empty shell', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const { container } = render(<QuickSetup onApplied={() => {}} />)
    await waitFor(() => expect(container.querySelector('[data-testid="quick-setup"]')).toBeNull())
  })
})
