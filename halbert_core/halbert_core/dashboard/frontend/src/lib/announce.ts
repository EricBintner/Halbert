// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * announce — speak one short sentence through the shell's live regions.
 *
 * Module-level on purpose, like hostConversation.ts: the thing that knows a
 * subject changed is a hook several components below the shell, and a live
 * region only works when there is exactly one of each kind. Two kinds
 * (design §11): polite (the default — "Pulled in earlier work: …", "New
 * subject", "<command> finished, exit 0") and assertive, reserved for the
 * one thing that blocks the admin: waiting for their approval. Subscribers
 * are the regions (LiveRegion.tsx) and tests.
 */

export interface AnnounceOptions {
  /** Interrupt what is being read. Only for blocked-on-approval. */
  assertive?: boolean
}

type Listener = (text: string, options: AnnounceOptions) => void

const listeners = new Set<Listener>()
let lastPolite = ''
let lastAssertive = ''

export function announce(text: string, options: AnnounceOptions = {}): void {
  if (options.assertive) {
    lastAssertive = text
  } else {
    lastPolite = text
  }
  listeners.forEach((listener) => listener(text, options))
}

export function subscribeAnnouncements(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The most recent polite sentence, for tests and debugging. */
export function lastAnnouncement(): string {
  return lastPolite
}

/** The most recent assertive sentence, for tests and debugging. */
export function lastAlert(): string {
  return lastAssertive
}
