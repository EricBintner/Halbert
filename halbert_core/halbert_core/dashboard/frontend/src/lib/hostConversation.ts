// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The bridge from a dashboard item into the conversation.
 *
 * ~40 buttons across 12 pages — "Ask Halbert about this", "Continue in chat",
 * "Edit Config", the @-tag and the code-block Run — need to reach a
 * conversation that is not mounted while they are on screen: they render in
 * BROWSING mode, and AgentChat mounts only in ENGAGED mode. A listener living
 * on AgentChat therefore cannot receive the event whose whole job is to bring
 * AgentChat up.
 *
 * So the request is parked here, at module level, and survives the mode flip:
 *
 *   button --> requestHost() --> [pending] --> setMode('engaged')
 *                                    |
 *                         AgentChat mounts, subscribes, drains
 *
 * This also matters because the old wiring failed SILENTLY:
 * `window.dispatchEvent` with no listener returns true and logs nothing, so a
 * dead button was indistinguishable from a working one. Nothing here dispatches
 * into the void — a request with no consumer stays pending until one arrives.
 */

export type HostRequestKind = 'ask' | 'run' | 'config'

export interface HostRequest {
  kind: HostRequestKind
  /** Placed in the composer. NEVER sent automatically. */
  prefill?: string
  /** Seeded as the assistant's opening turn, so the subject is on the record. */
  context?: string
  /** Item to @-tag, when the caller wants a reference rather than a prefill. */
  itemId?: string
  /** Human label for the staged subject. */
  title?: string
  /** Absolute path, for the config-editing loop. */
  configPath?: string
}

type Listener = (request: HostRequest) => void

let pending: HostRequest | null = null
const listeners = new Set<Listener>()

/**
 * Queue a request for the conversation.
 *
 * Delivers immediately if a conversation is mounted; otherwise holds it until
 * one subscribes, which is what makes this work across the mode flip.
 */
export function requestHost(request: HostRequest): void {
  if (listeners.size > 0) {
    listeners.forEach((listener) => listener(request))
    return
  }
  pending = request
}

/** Subscribe the mounted conversation. Drains anything queued before mount. */
export function subscribeHost(listener: Listener): () => void {
  listeners.add(listener)
  if (pending) {
    const queued = pending
    pending = null
    // After paint, so the composer exists before we write into it.
    queueMicrotask(() => listener(queued))
  }
  return () => {
    listeners.delete(listener)
  }
}

/** Ask the host about a dashboard item. */
export function askHost(request: Omit<HostRequest, 'kind'>): void {
  requestHost({ kind: 'ask', ...request })
}

/**
 * Stage a command for the user to read before running it.
 *
 * Deliberately a prefill and NOT an execution. Halbert manages storage,
 * services, networking and containers; turning every Run button into
 * execute-on-click would be a change of safety posture rather than a
 * refactor, so the command lands in the composer and waits for a human.
 */
export function runOnHost(command: string, title?: string): void {
  requestHost({
    kind: 'run',
    title,
    prefill: `Please run this command:\n\n\`\`\`bash\n${command}\n\`\`\``,
  })
}

/** Open the conversation against a config file being edited. */
export function configWithHost(configPath: string, context?: string): void {
  requestHost({ kind: 'config', configPath, context, title: configPath })
}
