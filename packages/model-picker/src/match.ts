// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/**
 * Ranking shared by the popover and the `/model` slash command.
 *
 * One implementation, so the same keystrokes surface the same first candidate
 * wherever the user types them. Pure functions: no React, no I/O, and no model
 * names — every string here comes from the user's own configuration.
 */

import type { DiscoveredModel } from './types'

const EXACT = 1000
const PREFIX = 800
const SEGMENT_PREFIX = 600
const SUBSTRING = 400
const SUBSEQUENCE = 200

/** An empty query excludes nothing and ranks nothing; callers keep their order. */
const EMPTY_QUERY = 1

/** Model names segment on punctuation far more often than on spaces. */
const SEGMENT_SPLIT = /[-_:./\s]+/

function isSubsequence(text: string, query: string): boolean {
  let qi = 0
  for (let ti = 0; ti < text.length && qi < query.length; ti++) {
    if (text[ti] === query[qi]) qi++
  }
  return qi === query.length
}

/**
 * How well `text` answers `query`, higher being better; `0` means no match.
 *
 * Tiers rather than a continuous score: a prefix hit must never lose to a
 * scattered subsequence hit just because the latter is in a shorter name.
 */
export function scoreMatch(text: string, query: string): number {
  const q = query.trim().toLowerCase()
  if (!q) return EMPTY_QUERY

  const t = text.toLowerCase()
  if (t === q) return EXACT
  if (t.startsWith(q)) return PREFIX
  if (t.split(SEGMENT_SPLIT).some((segment) => segment.startsWith(q))) {
    return SEGMENT_PREFIX
  }
  if (t.includes(q)) return SUBSTRING
  if (isSubsequence(t, q)) return SUBSEQUENCE
  return 0
}

function compareText(a: string, b: string): number {
  // Deliberately not localeCompare: the same query must rank identically for
  // every user, whatever locale their browser reports.
  const la = a.toLowerCase()
  const lb = b.toLowerCase()
  if (la !== lb) return la < lb ? -1 : 1
  if (a !== b) return a < b ? -1 : 1
  return 0
}

/**
 * The models matching `query`, best first. Non-matches are dropped; an empty
 * query returns everything in the order it arrived.
 *
 * Both the display name and the wire name are scored, because endpoints differ
 * on which of the two the user actually reads.
 */
export function matchModels(
  models: DiscoveredModel[],
  query: string,
): DiscoveredModel[] {
  if (!query.trim()) return [...models]

  return models
    .map((model) => ({
      model,
      score: Math.max(scoreMatch(model.name, query), scoreMatch(model.id, query)),
    }))
    .filter((entry) => entry.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        a.model.name.length - b.model.name.length ||
        compareText(a.model.name, b.model.name) ||
        compareText(a.model.id, b.model.id) ||
        // Total order, so two endpoints offering the same name never shuffle
        // between renders.
        compareText(a.model.endpointId, b.model.endpointId),
    )
    .map((entry) => entry.model)
}
