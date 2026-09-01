// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A minimal BroadcastChannel stand-in for jsdom, which does not implement
 * the API. Mirrors exactly the parts hudChannel relies on: same-name
 * channels receive each other's posts (but never the poster's own),
 * onmessage delivery, and close() deregistration.
 */

import { vi } from 'vitest'

type FakeMessageEvent = { data: unknown }

export class FakeBroadcastChannel {
  static byName = new Map<string, Set<FakeBroadcastChannel>>()
  readonly name: string
  onmessage: ((event: FakeMessageEvent) => void) | null = null

  constructor(name: string) {
    this.name = name
    let set = FakeBroadcastChannel.byName.get(name)
    if (!set) {
      set = new Set()
      FakeBroadcastChannel.byName.set(name, set)
    }
    set.add(this)
  }

  postMessage(data: unknown): void {
    for (const other of FakeBroadcastChannel.byName.get(this.name) ?? []) {
      // BroadcastChannel never echoes to the posting channel itself.
      if (other !== this && other.onmessage) other.onmessage({ data })
    }
  }

  close(): void {
    FakeBroadcastChannel.byName.get(this.name)?.delete(this)
  }
}

/** Install the fake as window.BroadcastChannel and forget prior channels. */
export function installFakeBroadcastChannel(): void {
  FakeBroadcastChannel.byName.clear()
  vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
}
