// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * U6/S1: the variant a variant-aware surface filters by.
 *
 * `null` is the hook's only failure mode and means "unknown", never
 * "sysadmin" — callers must treat it as "keep the unfiltered surface", or a
 * dead info route would silently shrink the picker on every instance.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useInstanceVariant } from './useInstanceVariant'

function okFetch(body: unknown) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => body })
}

afterEach(() => vi.unstubAllGlobals())

describe('useInstanceVariant', () => {
  it('resolves the variant the instance reports', async () => {
    vi.stubGlobal('fetch', okFetch({ variant: 'home' }))
    const { result } = renderHook(() => useInstanceVariant())
    await waitFor(() => expect(result.current).toBe('home'))
  })

  it('asks the instance info route', async () => {
    const fetchMock = okFetch({ variant: 'sysadmin' })
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useInstanceVariant())
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe('/api/instance/info')
  })

  it('stays null while the route is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const { result } = renderHook(() => useInstanceVariant())
    await waitFor(() => expect(result.current).toBeNull())
  })

  it('stays null on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }))
    const { result } = renderHook(() => useInstanceVariant())
    await waitFor(() => expect(result.current).toBeNull())
  })

  it('stays null when the payload carries no variant', async () => {
    vi.stubGlobal('fetch', okFetch({ data: {} }))
    const { result } = renderHook(() => useInstanceVariant())
    await waitFor(() => expect(result.current).toBeNull())
  })

  it('ignores a non-string variant rather than trusting it', async () => {
    vi.stubGlobal('fetch', okFetch({ variant: 3 }))
    const { result } = renderHook(() => useInstanceVariant())
    await waitFor(() => expect(result.current).toBeNull())
  })
})