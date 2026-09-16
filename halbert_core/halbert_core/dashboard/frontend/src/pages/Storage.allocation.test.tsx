// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'

import { allocationSegments, type FilesystemAllocation } from './Storage'

const GIB = 1024 ** 3

describe('allocationSegments', () => {
  it('splits a btrfs volume into data, metadata and system marks', () => {
    const allocation: FilesystemAllocation = {
      data_bytes: 400 * GIB,
      metadata_bytes: 8 * GIB,
      system_bytes: 1 * GIB,
      source: 'btrfs fi df',
    }

    const result = allocationSegments(allocation, 1000 * GIB)!
    expect(result.segments.map((s) => s.label)).toEqual(['Data', 'Metadata', 'System'])
    expect(result.segments.map((s) => Math.round(s.value))).toEqual([400, 8, 1])
    expect(result.total).toBe(1000)
  })

  it('keeps bcachefs cached bytes as their own mark', () => {
    // Promoted copies are reclaimable. Folding them into data would tell the
    // reader the volume is fuller than it is.
    const result = allocationSegments(
      {
        data_bytes: 500 * GIB,
        metadata_bytes: 20 * GIB,
        cached_bytes: 100 * GIB,
        total_bytes: 1000 * GIB,
        source: 'bcachefs fs usage',
      },
      0,
    )!

    expect(result.segments.map((s) => s.label)).toEqual(['Data', 'Metadata', 'Cached'])
    expect(result.total).toBe(1000)
  })

  it('reports nothing when the filesystem never reported a breakdown', () => {
    // The caller falls back to the single calibrated mark. It must not get an
    // empty bar that reads as a measured zero.
    expect(allocationSegments(undefined, 1000 * GIB)).toBeNull()
    expect(allocationSegments({ source: 'btrfs fi df' }, 1000 * GIB)).toBeNull()
  })

  it('drops zero-byte slices rather than drawing invisible segments', () => {
    const result = allocationSegments(
      { data_bytes: 400 * GIB, metadata_bytes: 0, cached_bytes: 0 },
      1000 * GIB,
    )!
    expect(result.segments.map((s) => s.label)).toEqual(['Data'])
  })

  it('refuses a total it cannot trust to exceed what is allocated', () => {
    // An unparseable size string arrives as 0. Drawing that would give the
    // gauge a negative headroom slice.
    expect(allocationSegments({ data_bytes: 400 * GIB }, 0)).toBeNull()
    expect(allocationSegments({ data_bytes: 400 * GIB }, 100 * GIB)).toBeNull()
  })
})
