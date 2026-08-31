// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { SpeakerProfilesCard } from './SpeakerProfilesCard'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

// Mock getUserMedia on the existing navigator
const mockGetUserMedia = vi.fn()
const mockStream = { getTracks: () => [{ stop: vi.fn() }] }
mockGetUserMedia.mockResolvedValue(mockStream)
Object.defineProperty(navigator, 'mediaDevices', {
  value: { getUserMedia: mockGetUserMedia },
  configurable: true,
  writable: true,
})

// Mock MediaRecorder
class MockMediaRecorder {
  state = 'inactive'
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['audio'], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}
vi.stubGlobal('MediaRecorder', MockMediaRecorder)

// Mock FileReader
class MockFileReader {
  result = 'data:audio/webm;base64,AAAA'
  onloadend: (() => void) | null = null
  readAsDataURL() { this.onloadend?.() }
}
vi.stubGlobal('FileReader', MockFileReader)

function mockSpeakersResponse(speakers: any[] = []) {
  return {
    ok: true,
    json: async () => ({ speakers, count: speakers.length }),
  }
}

function mockStatusResponse(installed = true) {
  return {
    ok: true,
    json: async () => ({
      enabled: true,
      available: installed,
      sherpa_onnx_installed: installed,
      state: 'idle',
      engines: {},
    }),
  }
}

const SPEAKER = {
  speaker_id: 's1',
  name: 'Eric',
  role: 'admin',
  sample_count: 3,
  threshold: 0.75,
  embedding_dim: 256,
  created_at: 0,
}

describe('SpeakerProfilesCard', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    mockGetUserMedia.mockClear()
    mockGetUserMedia.mockResolvedValue(mockStream)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads speakers and status on mount', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/speakers') && !url.includes('/test'))
        return Promise.resolve(mockSpeakersResponse([SPEAKER]))
      if (url.includes('/status')) return Promise.resolve(mockStatusResponse(true))
      return Promise.resolve({ ok: false })
    })

    render(<SpeakerProfilesCard />)

    await waitFor(() => {
      expect(screen.getByText('Eric')).toBeTruthy()
    })
  })

  it('calls the real test endpoint on Test button click', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/speakers') && !url.includes('/test'))
        return Promise.resolve(mockSpeakersResponse([SPEAKER]))
      if (url.includes('/status')) return Promise.resolve(mockStatusResponse(true))
      if (url.includes('/test'))
        return Promise.resolve({
          ok: true,
          json: async () => ({ speaker_id: 's1', matched: true, score: 0.88, threshold: 0.75 }),
        })
      return Promise.resolve({ ok: false })
    })

    render(<SpeakerProfilesCard />)

    await waitFor(() => {
      expect(screen.getByText('Eric')).toBeTruthy()
    })

    const testButton = screen.getByText('Test')
    await act(async () => {
      testButton.click()
      // Wait for the 2s recording timeout to fire and the async chain to complete
      await new Promise((r) => setTimeout(r, 2500))
    })

    await waitFor(() => {
      expect(screen.getByText(/Match: Yes/)).toBeTruthy()
    })

    // Verify the test endpoint was called with audio_base64
    const testCall = fetchMock.mock.calls.find(([url]) => url.includes('/test'))
    expect(testCall).toBeTruthy()
    const body = JSON.parse(testCall![1].body)
    expect(body.audio_base64).toBeTruthy()
  })

  it('handles 503 when sherpa-onnx is missing', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/speakers') && !url.includes('/test'))
        return Promise.resolve(mockSpeakersResponse([SPEAKER]))
      if (url.includes('/status')) return Promise.resolve(mockStatusResponse(false))
      if (url.includes('/test'))
        return Promise.resolve({
          ok: false,
          status: 503,
          json: async () => ({ detail: 'sherpa-onnx not installed' }),
        })
      return Promise.resolve({ ok: false })
    })

    render(<SpeakerProfilesCard />)

    await waitFor(() => {
      expect(screen.getByText('Eric')).toBeTruthy()
    })

    const testButton = screen.getByText('Test')
    await act(async () => {
      testButton.click()
      await new Promise((r) => setTimeout(r, 2500))
    })

    await waitFor(() => {
      expect(screen.getByText(/sherpa-onnx not installed/)).toBeTruthy()
    })
  })

  it('shows disabled tooltip when sherpa-onnx not installed', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/speakers') && !url.includes('/test'))
        return Promise.resolve(mockSpeakersResponse([SPEAKER]))
      if (url.includes('/status')) return Promise.resolve(mockStatusResponse(false))
      return Promise.resolve({ ok: false })
    })

    render(<SpeakerProfilesCard />)

    await waitFor(() => {
      expect(screen.getByText('Eric')).toBeTruthy()
    })

    const testButton = screen.getByText('Test')
    expect(testButton.getAttribute('title')).toContain('sherpa-onnx not installed')
  })
})
