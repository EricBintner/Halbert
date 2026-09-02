// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceEnrollmentModal tests: the 3-step (capture -> extract -> confirm)
 * enrollment wizard. Mocks getUserMedia/MediaRecorder/FileReader the same
 * way SpeakerProfilesCard.test.tsx does, since this modal drives the same
 * browser recording APIs to capture a sample and hand it to the backend as
 * base64.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VoiceEnrollmentModal } from './VoiceEnrollmentModal'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const mockGetUserMedia = vi.fn()
const mockStream = { getTracks: () => [{ stop: vi.fn() }] }

Object.defineProperty(navigator, 'mediaDevices', {
  value: { getUserMedia: mockGetUserMedia },
  configurable: true,
  writable: true,
})

class MockMediaRecorder {
  state = 'inactive'
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['audio'], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}
vi.stubGlobal('MediaRecorder', MockMediaRecorder)

class MockFileReader {
  result = 'data:audio/webm;base64,AAAA'
  onloadend: (() => void) | null = null
  readAsDataURL() {
    this.onloadend?.()
  }
}
vi.stubGlobal('FileReader', MockFileReader)

async function captureAudio(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /start recording/i }))
  await user.click(screen.getByRole('button', { name: /stop recording/i }))
  await waitFor(() => expect(screen.getByText(/Recording captured/i)).toBeTruthy())
}

beforeEach(() => {
  mockGetUserMedia.mockReset()
  mockGetUserMedia.mockResolvedValue(mockStream)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.stubGlobal('MediaRecorder', MockMediaRecorder)
  vi.stubGlobal('FileReader', MockFileReader)
})

describe('VoiceEnrollmentModal', () => {
  it('keeps Continue disabled until both a name is entered and audio is captured', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn())
    render(<VoiceEnrollmentModal onClose={vi.fn()} />)

    const continueButton = screen.getByRole('button', { name: /^continue$/i })
    expect(continueButton).toBeDisabled()

    await user.type(screen.getByLabelText(/speaker name/i), 'Eric')
    expect(continueButton).toBeDisabled()

    await captureAudio(user)
    expect(continueButton).toBeEnabled()
  })

  it('shows an inline error and does not capture audio when getUserMedia is denied', async () => {
    const user = userEvent.setup()
    mockGetUserMedia.mockRejectedValueOnce(new Error('denied'))
    vi.stubGlobal('fetch', vi.fn())
    render(<VoiceEnrollmentModal onClose={vi.fn()} />)

    await user.type(screen.getByLabelText(/speaker name/i), 'Eric')
    await user.click(screen.getByRole('button', { name: /start recording/i }))

    expect(await screen.findByText(/Microphone access denied/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()
  })

  it('captures audio, extracts an embedding, and completes enrollment end-to-end', async () => {
    const user = userEvent.setup()
    const calls: Array<{ url: string; init?: RequestInit }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init })
        return jsonResponse({ embedding_dim: 256 })
      }),
    )
    const onClose = vi.fn()
    const onEnrolled = vi.fn()
    render(<VoiceEnrollmentModal onClose={onClose} onEnrolled={onEnrolled} />)

    await user.type(screen.getByLabelText(/speaker name/i), 'Eric')
    await user.click(screen.getByRole('button', { name: /^admin/i }))
    await captureAudio(user)

    await user.click(screen.getByRole('button', { name: /^continue$/i }))
    expect(screen.getByText(/Extracting 256-dim CAM\+\+ speaker embedding/i)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /extract embedding/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/audio/speakers/enroll')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body).toEqual({ name: 'Eric', role: 'admin', audio_base64: 'AAAA' })
    })

    expect(await screen.findByText('Speaker enrolled successfully')).toBeTruthy()
    expect(screen.getByText(/Eric \(admin\)/)).toBeTruthy()
    expect(screen.getByText('Quality: 96%')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /^done$/i }))
    expect(onEnrolled).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('shows the server-provided error and stays on the extract step when enrollment fails', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'Speaker already enrolled' }, 400)),
    )
    render(<VoiceEnrollmentModal onClose={vi.fn()} />)

    await user.type(screen.getByLabelText(/speaker name/i), 'Eric')
    await captureAudio(user)
    await user.click(screen.getByRole('button', { name: /^continue$/i }))
    await user.click(screen.getByRole('button', { name: /extract embedding/i }))

    expect(await screen.findByText('Speaker already enrolled')).toBeTruthy()
    expect(screen.queryByText('Speaker enrolled successfully')).toBeNull()
  })

  it('the close button calls onClose', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn())
    const onClose = vi.fn()
    render(<VoiceEnrollmentModal onClose={onClose} />)

    // The header close (X) button -- the only button with no accessible text.
    const buttons = screen.getAllByRole('button')
    const closeButton = buttons.find((b) => b.textContent === '')
    expect(closeButton).toBeTruthy()
    await user.click(closeButton!)
    expect(onClose).toHaveBeenCalled()
  })
})
