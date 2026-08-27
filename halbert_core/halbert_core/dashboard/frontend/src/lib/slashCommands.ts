// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The composer's `/model` command, parsed away from React.
 *
 * The terminal page grew its slash commands inline (see pages/Terminal.tsx),
 * which left the rules for what counts as a command tangled up with the
 * keystroke handler and untestable. This module keeps the same shape — split
 * on whitespace, lower-case the leading token, treat the rest as arguments —
 * as a pure function, so the composer only has to decide what to *do* with the
 * result.
 */

/** The runtime slots a user can address by name; see halbertModelRoles.ts. */
export type ModelTier = 'guide' | 'specialist' | 'vision'

export type ModelCommand =
  | { kind: 'open' }
  | { kind: 'search'; query: string }
  | { kind: 'status' }
  | { kind: 'auto' }
  | { kind: 'pin'; query: string }
  | { kind: 'tier'; tier: ModelTier; query?: string }
  | { kind: 'error'; message: string }

const COMMAND = '/model'

/**
 * `chat` is accepted alongside `guide` because the picker labels that slot
 * "Chat (Guide)" and its wire id is `chat_model` — a user reading either would
 * otherwise have their tier switch silently parsed as a model search.
 */
const TIER_KEYWORDS: Record<string, ModelTier> = {
  guide: 'guide',
  chat: 'guide',
  specialist: 'specialist',
  vision: 'vision',
}

const PIN_KEYWORDS = ['pin', 'lock']

/**
 * Parse composer input as a `/model` command.
 *
 * Returns null when the input is not a `/model` command at all, so the caller
 * sends it as an ordinary message. Only the exact token `/model` is claimed:
 * `/models` and `/modelfoo` belong to nobody yet and must stay sendable.
 */
export function parseModelCommand(input: string): ModelCommand | null {
  const tokens = input.trim().split(/\s+/).filter(Boolean)
  if (tokens.length === 0 || tokens[0].toLowerCase() !== COMMAND) return null

  const args = tokens.slice(1)
  if (args.length === 0) return { kind: 'open' }

  const keyword = args[0].toLowerCase()
  // Arguments keep their original case: model names are case-sensitive on the
  // wire, so a lower-cased name would be rejected by the provider.
  const rest = args.slice(1).join(' ')

  if (keyword === 'status') {
    return rest
      ? argumentsRefused('/model status', 'To search, run /model <query>.')
      : { kind: 'status' }
  }

  if (keyword === 'auto') {
    return rest
      ? argumentsRefused('/model auto', 'To pin a model, run /model pin <model>.')
      : { kind: 'auto' }
  }

  if (PIN_KEYWORDS.includes(keyword)) {
    // Silently opening the picker here would look like the pin succeeded.
    return rest
      ? { kind: 'pin', query: rest }
      : {
          kind: 'error',
          message:
            'Usage: /model pin <model>. Name the model to pin, or run /model to pick one.',
        }
  }

  const tier = TIER_KEYWORDS[keyword]
  if (tier) return rest ? { kind: 'tier', tier, query: rest } : { kind: 'tier', tier }

  return { kind: 'search', query: args.join(' ') }
}

/**
 * Trailing words after a subcommand that takes none are a typo, not a search:
 * treating them as one would swap the model out from under the user.
 */
function argumentsRefused(usage: string, hint: string): ModelCommand {
  return { kind: 'error', message: `${usage} takes no arguments. ${hint}` }
}

export interface ModelStatusRow {
  label: string
  value: string
}

export type ModelStatusLines = ModelStatusRow[]

export interface ModelStatusInput {
  activeModel: string
  providerLabel: string
  isLocal: boolean
  pinned: boolean
  tier: string
  contextWindow?: number
  endpointUrl?: string
}

/**
 * Rows for the ephemeral `/model status` card. Plain label/value pairs only —
 * the card owns its own markup and colour, this owns the words.
 */
export function formatModelStatus(input: ModelStatusInput): ModelStatusLines {
  const rows: ModelStatusLines = [
    { label: 'Model', value: input.activeModel.trim() || 'None selected' },
    { label: 'Provider', value: input.providerLabel.trim() || 'Unknown' },
    { label: 'Runs on', value: input.isLocal ? 'This machine' : 'Remote service' },
    { label: 'Tier', value: input.tier.trim() || 'Unknown' },
    { label: 'Selection', value: input.pinned ? 'Pinned' : 'Automatic' },
  ]

  const context = input.contextWindow
  if (context !== undefined && Number.isFinite(context) && context > 0) {
    rows.push({ label: 'Context', value: `${withThousands(context)} tokens` })
  }

  const endpoint = input.endpointUrl?.trim()
  if (endpoint) rows.push({ label: 'Endpoint', value: endpoint })

  return rows
}

/**
 * Grouped by hand rather than by locale: the same card is read off two
 * machines when someone reports a problem, and the numbers have to match.
 */
function withThousands(value: number): string {
  return Math.round(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}
