// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One poll, many consumers.
 *
 * The mode switch, the greeting and the vitals panel all read host identity at
 * different rates. Before the shared store they each ran their own fetch loop;
 * these tests pin the contract that replaced that.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useHostIdentity } from './useHostIdentity'

const IDENTITY = {
  display_name: 'Macky-Mac',
  hostname: 'Erics-Mac-Studio.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 20, physical_cores: 20, percent: 12, temperature: null },
  memory: { total_gb: 128, used_gb: 61, percent: 48 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Macky-Mac (macOS 26.5.1, Darwin 25.5.0).',
  timestamp: '',
}

function okFetch() {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => IDENTITY })
}

describe('useHostIdentity shared store', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('exposes the chosen name and the hostname as separate facts', async () => {
    vi.stubGlobal('fetch', okFetch())

    const { result } = renderHook(() => useHostIdentity(60_000))

    await waitFor(() => expect(result.current.identity).not.toBeNull())
    expect(result.current.identity!.display_name).toBe('Macky-Mac')
    expect(result.current.identity!.hostname).toBe('Erics-Mac-Studio.local')
    expect(result.current.error).toBeNull()
  })

  it('serves concurrent consumers from a single request', async () => {
    const fetchMock = okFetch()
    vi.stubGlobal('fetch', fetchMock)

    const a = renderHook(() => useHostIdentity(60_000))
    const b = renderHook(() => useHostIdentity(5_000))
    const c = renderHook(() => useHostIdentity(30_000))

    await waitFor(() => expect(a.result.current.identity).not.toBeNull())
    expect(b.result.current.identity).not.toBeNull()
    expect(c.result.current.identity).not.toBeNull()

    // Three components, one network round trip.
    expect(fetchMock).toHaveBeenCalledTimes(1)

    a.unmount(); b.unmount(); c.unmount()
  })

  it('polls at the shortest period any live consumer asked for', async () => {
    const fetchMock = okFetch()
    vi.stubGlobal('fetch', fetchMock)

    const slow = renderHook(() => useHostIdentity(60_000))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    vi.useFakeTimers()
    const fast = renderHook(() => useHostIdentity(1_000))
    await act(async () => {}) // let the mount-time load settle
    fetchMock.mockClear()

    // Each tick is awaited separately so the previous request settles first;
    // ticking three times inside one flush would be de-duplicated (see below).
    for (let i = 0; i < 3; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(1_000)
      })
    }

    // The 60s consumer must not hold the 1s one back.
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2)

    fast.unmount()
    slow.unmount()
    vi.useRealTimers()
  })

  it('does not stack requests when a tick lands mid-flight', async () => {
    // A backend slower than the poll interval must not accumulate a queue of
    // overlapping identity requests.
    let release: (() => void) | null = null
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ ok: true, json: async () => IDENTITY })
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    vi.useFakeTimers()
    const { unmount } = renderHook(() => useHostIdentity(1_000))
    await act(async () => {}) // mount-time load starts and stays pending

    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(5_000) // five ticks, all while in flight
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      release?.()
    })
    unmount()
    vi.useRealTimers()
  })

  it('stops polling once every consumer unmounts', async () => {
    const fetchMock = okFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = renderHook(() => useHostIdentity(1_000))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    vi.useFakeTimers()
    unmount()
    fetchMock.mockClear()

    await act(async () => {
      vi.advanceTimersByTime(10_000)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('keeps the last good identity when a later poll fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => IDENTITY })
      .mockRejectedValue(new Error('backend restarting'))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useHostIdentity(60_000))
    await waitFor(() => expect(result.current.identity).not.toBeNull())

    const { refreshHostIdentity } = await import('./useHostIdentity')
    await act(async () => {
      await refreshHostIdentity()
    })

    // The machine does not stop being itself because one poll missed.
    expect(result.current.identity!.display_name).toBe('Macky-Mac')
    expect(result.current.error).toBeNull()
  })
})
