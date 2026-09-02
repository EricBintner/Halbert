// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Regression test for ROUTE-03: AudioSettings' quiet-hours controls used to
 * fetch `/api/being`, a route that does not exist — the real config
 * endpoints are `GET/POST /api/settings/being` (settings.py:3052, :3070).
 * This asserts the tab hits the real route and posts a body shaped the way
 * the backend's `BeingConfigUpdate.quiet_hours` model expects.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AudioSettings } from './AudioSettings'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const audioConfig = {
  enabled: true,
  local_mic: { enabled: false, device_index: 0, sample_rate: 16000, aec_enabled: false },
  wyoming_ingress: { enabled: false, host: '0.0.0.0', port: 10400 },
  acoustic_events: { enabled: false, energy_floor_db: -40, check_interval_s: 5 },
  speaker_id: { enabled: false, threshold: 0.75 },
  tts: { enabled: false, voice_model: '' },
  privacy: {
    delete_raw_after_transcription: true,
    ignore_tv_media: true,
    quiet_hours: null,
  },
}

const audioStatus = {
  enabled: true,
  available: true,
  sherpa_onnx_installed: true,
  state: 'idle',
  engines: { vad: true, asr: true, tts: true, speaker_id: true, audio_tagger: true },
}

function renderTab(beingConfig: Record<string, unknown> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/audio/config') return jsonResponse(audioConfig)
    if (url === '/api/audio/status') return jsonResponse(audioStatus)
    if (url === '/api/settings/being') {
      return jsonResponse({ status: 'ok', config: { quiet_hours: null, ...beingConfig } })
    }
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AudioSettings />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

describe('AudioSettings quiet hours (ROUTE-03)', () => {
  it('loads quiet hours from /api/settings/being, never the nonexistent /api/being', async () => {
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading audio settings/i)).toBeNull())
    expect(calls.some((c) => c.url === '/api/settings/being')).toBe(true)
    expect(calls.some((c) => c.url === '/api/being')).toBe(false)
  })

  it('enabling quiet hours POSTs to /api/settings/being with a {quiet_hours} body', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading audio settings/i)).toBeNull())

    await user.click(screen.getByLabelText(/enable quiet hours/i))

    await waitFor(() => {
      const post = calls.find(
        (c) => c.url === '/api/settings/being' && c.init?.method === 'POST',
      )
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body).toEqual({ quiet_hours: { start: '22:00', end: '07:00' } })
    })
  })
})
