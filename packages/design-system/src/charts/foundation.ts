// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Shared vocabulary for the chart primitives.
 *
 * Every chart in this directory declares the **job** it serves. The job is not
 * decoration: a reviewer should be able to ask "is this a trend drawn as a
 * ratio?" and answer it from the component name alone. The catalogue of jobs is
 * fixed and small — when data does not fit one of them, the honest answer is
 * usually a table or a stat tile rather than a new chart type.
 *
 * Rules these components hold to, from the design system's standing directives:
 * - Colour comes from `shared-tokens/tokens.css`; no literal ever appears here.
 * - Categorical `data-*` tones tell *series* apart. A status tone
 *   (nominal / warning / critical) means a threshold was crossed and is never
 *   reused as "series 6" (`DATAVIZ-TONE`).
 * - No text is drawn on a mark. Labels live beside the mark or in a legend
 *   (reverted 2026-09-18 after it failed on every short fill).
 * - An unmeasured value renders as an explicit dark state, never as zero.
 */

/** The reader's task. One of these, or it is not a chart. */
export type ChartJob =
  | 'ratio-against-limit'
  | 'parts-of-whole'
  | 'measure-across-peers'
  | 'state-across-items'
  | 'measure-over-time'
  | 'scope-within-scope'
  | 'instance-through-stages'
  | 'estimate-with-uncertainty'
  | 'facts-with-lifespans'
  | 'events-across-time'

/** Categorical series pigments, assigned in fixed order and never cycled. */
export type SeriesTone =
  | 'data-1'
  | 'data-2'
  | 'data-3'
  | 'data-4'
  | 'data-5'
  | 'data-blue'
  | 'data-orchid'
  | 'data-teal'
  | 'data-purple'
  | 'data-green'
  | 'data-neutral'

/** Threshold states. Reserved — never used to tell series apart. */
export type StatusTone = 'nominal' | 'warning' | 'critical' | 'telemetry' | 'neutral'

export type ChartTone = SeriesTone | StatusTone

/**
 * The fixed assignment order.
 *
 * A fifth series is the fifth entry, not a generated hue — past five the honest
 * moves are folding the tail into "Other" or faceting into small multiples.
 */
export const SERIES_ORDER: SeriesTone[] = ['data-1', 'data-2', 'data-3', 'data-4', 'data-5']

/** The nth series' pigment, or the neutral once the order is exhausted. */
export function seriesTone(index: number): SeriesTone {
  return SERIES_ORDER[index] ?? 'data-neutral'
}

/** Map a reading to a threshold state. The one place the thresholds live. */
export function thresholdTone(percent: number, warn = 75, crit = 90): StatusTone {
  if (!isFinite(percent)) return 'neutral'
  if (percent >= crit) return 'critical'
  if (percent >= warn) return 'warning'
  return 'telemetry'
}

/** Linear map from a data domain onto a pixel range, clamped to the range. */
export function scale(value: number, min: number, max: number, from: number, to: number): number {
  if (!isFinite(value) || max === min) return from
  const t = (value - min) / (max - min)
  return from + Math.max(0, Math.min(1, t)) * (to - from)
}

/** Tabular-safe fixed formatting that never renders "NaN" into a label. */
export function fmt(value: number, digits = 1): string {
  return isFinite(value) ? value.toFixed(digits) : '—'
}

/** BEM-ish modifier for a tone, so CSS owns the pigment and TS never names one. */
export function toneClass(block: string, tone: ChartTone | undefined): string | false {
  return tone ? `${block}--${tone}` : false
}
