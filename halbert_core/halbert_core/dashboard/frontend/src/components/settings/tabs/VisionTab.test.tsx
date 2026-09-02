// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Regression test for R08-07: the "Custom blocklist keywords" textarea used
 * to PUT the entire vision config to the backend on every keystroke. It now
 * tracks the in-progress edit in local `blocklistDraft` state (VisionTab.tsx)
 * and only commits on blur, matching the defaultValue+onBlur pattern used
 * elsewhere for free-text fields. This asserts typing produces no fetch
 * calls at all, and that blurring PUTs /api/vision/config with a single
 * `redaction_blocklist` field holding trimmed, non-empty lines.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VisionTab } from './VisionTab'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const visionStatus = {
  dependencies: { mss: true, cv2: true, numpy: true },
}

function defaultVisionConfig() {
  return {
    screen_capture: { enabled: true, quality: 85, max_dimension: 1568, monitor_index: 1, grayscale: false },
    webcam: { enabled: false, camera_index: 0, quality: 85, max_dimension: 768, grayscale: false },
    redaction: { enabled: true, blocklist: ['password', 'secret'] },
  }
}

/**
 * Render the tab with /api/vision/* routed against a mutable config, so a
 * PUT's field update is reflected the next time the tab reloads it (like
 * the real backend).
 */
function renderTab(initialConfig = defaultVisionConfig()) {
  let config = initialConfig
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/vision/status') return jsonResponse(visionStatus)
    if (url === '/api/vision/config' && init?.method === 'PUT') {
      const body = JSON.parse(init.body as string)
      const [field, value] = Object.entries(body)[0]
      if (field === 'redaction_blocklist') {
        config = { ...config, redaction: { ...config.redaction, blocklist: value as string[] } }
      } else if (field === 'screen_capture_enabled') {
        config = { ...config, screen_capture: { ...config.screen_capture, enabled: value as boolean } }
      }
      return jsonResponse({ status: 'ok' })
    }
    if (url === '/api/vision/config') return jsonResponse(config)
    if (url === '/api/vision/screenshot') return jsonResponse({})
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<VisionTab />)
  return { calls, getConfig: () => config }
}

afterEach(() => vi.unstubAllGlobals())

describe('VisionTab', () => {
  it('loads vision config and dependency status on mount', async () => {
    renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading vision settings/i)).toBeNull())
    expect(screen.getByText(/✓ mss/)).toBeTruthy()
    expect(screen.getByText(/✓ opencv-python/)).toBeTruthy()
    expect(screen.getByText(/✓ numpy/)).toBeTruthy()
  })

  describe('blocklist textarea (R08-07 regression)', () => {
    it('does not PUT while typing, and commits a trimmed line array only on blur', async () => {
      const user = userEvent.setup()
      const { calls } = renderTab()
      await waitFor(() => expect(screen.queryByText(/Loading vision settings/i)).toBeNull())

      const textarea = screen.getByLabelText(/custom blocklist keywords/i)
      expect((textarea as HTMLTextAreaElement).value).toBe('password\nsecret')

      await user.clear(textarea)
      // Includes a blank line and a whitespace-only line to exercise the
      // trim + filter(Boolean) logic in the onBlur handler.
      await user.type(textarea, 'password{enter}{enter}  {enter}token')

      // Still purely local edit state -- no network call yet.
      expect(
        calls.some((c) => c.url === '/api/vision/config' && c.init?.method === 'PUT'),
      ).toBe(false)

      await user.tab() // blur the textarea

      await waitFor(() => {
        const put = calls.find(
          (c) => c.url === '/api/vision/config' && c.init?.method === 'PUT',
        )
        expect(put).toBeTruthy()
        const body = JSON.parse(put!.init!.body as string)
        expect(body).toEqual({ redaction_blocklist: ['password', 'token'] })
      })
    })

    it('blurring with no edit made does not PUT', async () => {
      const user = userEvent.setup()
      const { calls } = renderTab()
      await waitFor(() => expect(screen.queryByText(/Loading vision settings/i)).toBeNull())

      const textarea = screen.getByLabelText(/custom blocklist keywords/i)
      await user.click(textarea)
      await user.tab()

      expect(
        calls.some((c) => c.url === '/api/vision/config' && c.init?.method === 'PUT'),
      ).toBe(false)
    })
  })

  it('toggling screen capture PUTs immediately, unlike the blocklist blur-commit', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading vision settings/i)).toBeNull())

    await user.click(screen.getByLabelText(/enable screen capture/i))

    await waitFor(() => {
      const put = calls.find((c) => c.url === '/api/vision/config' && c.init?.method === 'PUT')
      expect(put).toBeTruthy()
      expect(JSON.parse(put!.init!.body as string)).toEqual({ screen_capture_enabled: false })
    })
  })

  it('Test screen capture calls the screenshot endpoint and shows a success toast', async () => {
    const user = userEvent.setup()
    renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading vision settings/i)).toBeNull())

    await user.click(screen.getByRole('button', { name: /test screen capture/i }))

    await waitFor(() => {
      expect(screen.getByText(/Screenshot captured successfully/i)).toBeTruthy()
    })
  })
})
