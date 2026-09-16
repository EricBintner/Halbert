// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId, useMeasuredWidth } from '../lib'

/**
 * In-segment label fitting is measured, not assumed.
 *
 * The label is mono at a known size, so one advance width per character is an
 * exact answer rather than a guess — but it is an answer in *pixels*, and a
 * slice's share of the track is a *percentage*. Converting between them needs
 * the track's real width: the same 18% slice carries 144px of label on a
 * dashboard column and 58px in a sidebar. Deciding the fit from the percentage
 * alone silently clips every track narrower than the one it was tuned on.
 */
const MONO_ADVANCE_RATIO = 0.6
const LABEL_FONT_PX: Record<string, number> = { thick: 13.5, hero: 13.5 }
const LABEL_FONT_PX_DEFAULT = 12.5
/** `padding: 0 var(--space-2)` on both flanks. */
const LABEL_PADDING_PX = 16
/** `gap: var(--space-1)` between the name and its value. */
const LABEL_GAP_PX = 4
/**
 * Width to assume before a measurement lands (SSR, first paint, jsdom). A
 * typical dashboard column — wrong only for the frame before the observer
 * fires, and never wrong in the direction that hides a label permanently.
 */
const ASSUMED_TRACK_PX = 800
/** Below this share of the track, a slice is a mark, not a label surface. */
const MIN_LABELLED_PCT = 7
/** Fallback name for the unallocated slice when its full label will not fit. */
const FREE_SHORT_LABEL = 'Free'

export type SegmentTone =
  | 'neutral'
  | 'critical'
  | 'warning'
  | 'nominal'
  | 'telemetry'
  | 'data-neutral'
  | 'data-1'
  | 'data-2'
  | 'data-3'
  | 'data-4'
  | 'data-5'
  | 'data-6'
  | 'data-blue'
  | 'data-amber'
  | 'data-teal'
  | 'data-purple'
  | 'data-green'
  | 'data-orange'

export interface SegmentItem {
  id: string
  label: string
  /** Optional shorter label for compact slices or dense responsive viewports. */
  shortLabel?: string
  value: number
  /** Tone for this slice: status ('nominal', 'warning', etc.) or data series ('data-blue', 'data-1', etc.). */
  tone?: SegmentTone
  /** Visual pattern: 'solid' or 'hatched' (diagonal mechanical stripes for metadata/overhead). */
  pattern?: 'solid' | 'hatched'
  /** Optional secondary detail (e.g. "RAID1", "Q4_K_M"). */
  detail?: string
}

export interface SegmentedBarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** The segments that compose the allocation. */
  segments: SegmentItem[]
  /** Total capacity. If omitted, the sum of segments is used as 100%. */
  total?: number
  /** Unit suffix for numerical values (e.g., "GB", "MB", "%"). Default: "GB". */
  unit?: string
  /** Whether to render the tabular legend below the gauge (default: true). */
  showLegend?: boolean
  /** Whether to automatically compute and display unallocated free headroom (default: true). */
  showFreeHeadroom?: boolean
  /** Label for unallocated headroom (default: "Free Headroom"). */
  freeHeadroomLabel?: string
  /** Height size variant (default: 'md'). */
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'thick'
  /** Whether to render labels directly inside the colored segments (best with lg/xl/thick). */
  showInSegmentLabels?: boolean
  /** Sensor or resource offline state. */
  offline?: boolean
}

/**
 * SegmentedBar — A multi-category resource allocation meter.
 *
 * Designed for filesystems (Active Data vs. Metadata vs. Snapshots vs. Free),
 * memory distribution, and VRAM layout.
 */
export const SegmentedBar = React.forwardRef<HTMLDivElement, SegmentedBarProps>(function SegmentedBar(
  {
    segments,
    total,
    unit = 'GB',
    showLegend = true,
    showFreeHeadroom = true,
    freeHeadroomLabel = 'Free Headroom',
    size = 'md',
    showInSegmentLabels = false,
    offline = false,
    className,
    id,
    ...props
  },
  ref,
) {
  const barId = useId(id)
  const trackRef = React.useRef<HTMLDivElement>(null)
  const measuredTrackPx = useMeasuredWidth(trackRef)
  const trackPx = measuredTrackPx > 0 ? measuredTrackPx : ASSUMED_TRACK_PX
  const charPx = (LABEL_FONT_PX[size] ?? LABEL_FONT_PX_DEFAULT) * MONO_ADVANCE_RATIO

  /** Pixels a slice of this percentage actually gets on the current track. */
  const slicePx = React.useCallback((pct: number) => (pct / 100) * trackPx, [trackPx])
  /** Pixels a name-plus-value label needs, or a bare value when `name` is empty. */
  const labelPx = React.useCallback(
    (name: string, value: string) =>
      (name.length + value.length) * charPx + (name ? LABEL_GAP_PX : 0) + LABEL_PADDING_PX,
    [charPx],
  )

  // Calculate total and proportions
  const sumValues = React.useMemo(() => {
    return segments.reduce((acc, s) => acc + (isNaN(s.value) ? 0 : Math.max(0, s.value)), 0)
  }, [segments])

  const effectiveTotal = total != null && total > 0 ? total : sumValues
  const freeValue = Math.max(0, effectiveTotal - sumValues)
  const hasFree = showFreeHeadroom && freeValue > 0.001

  return (
    <div
      ref={ref}
      id={barId}
      className={cx(
        'hb-segmented-bar',
        `hb-segmented-bar--${size}`,
        offline && 'is-offline',
        className,
      )}
      {...props}
    >
      {/* The Track with Segments */}
      <div
        ref={trackRef}
        className="hb-segmented-bar__track"
        role="meter"
        aria-valuenow={offline ? undefined : sumValues}
        aria-valuemin={0}
        aria-valuemax={effectiveTotal}
        aria-valuetext={
          offline
            ? '[Sensor offline]'
            : `${sumValues.toFixed(1)} of ${effectiveTotal.toFixed(1)} ${unit} allocated`
        }
      >
        {!offline ? (
          <>
            {segments.map((seg) => {
              const segVal = Math.max(0, isNaN(seg.value) ? 0 : seg.value)
              const pct = effectiveTotal > 0 ? (segVal / effectiveTotal) * 100 : 0
              if (pct <= 0) return null
              const tone = seg.tone ?? 'neutral'

              const valStr = `${segVal.toFixed(1)} ${unit}`
              const availablePx = slicePx(pct)

              const canFitFull = availablePx >= labelPx(seg.label, valStr)
              const canFitShort =
                !canFitFull &&
                Boolean(seg.shortLabel) &&
                availablePx >= labelPx(seg.shortLabel!, valStr)
              const canFitVal =
                !canFitFull &&
                !canFitShort &&
                availablePx >= labelPx('', valStr) &&
                pct >= MIN_LABELLED_PCT

              return (
                <div
                  key={seg.id}
                  className={cx(
                    'hb-segmented-bar__segment',
                    `hb-segmented-bar__segment--${tone}`,
                    seg.pattern === 'hatched' && 'is-hatched',
                  )}
                  style={{ width: `${pct}%` }}
                  title={`${seg.label}: ${segVal.toFixed(1)} ${unit} (${pct.toFixed(1)}%)`}
                >
                  {showInSegmentLabels && (
                    canFitFull ? (
                      <span className="hb-segmented-bar__segment-label" aria-hidden="true">
                        <span className="hb-segmented-bar__segment-name">{seg.label}</span>
                        <span className="hb-segmented-bar__segment-val">{valStr}</span>
                      </span>
                    ) : canFitShort ? (
                      <span className="hb-segmented-bar__segment-label" aria-hidden="true">
                        <span className="hb-segmented-bar__segment-name">{seg.shortLabel}</span>
                        <span className="hb-segmented-bar__segment-val">{valStr}</span>
                      </span>
                    ) : canFitVal ? (
                      <span className="hb-segmented-bar__segment-label hb-segmented-bar__segment-label--val-only" aria-hidden="true">
                        <span className="hb-segmented-bar__segment-val">{valStr}</span>
                      </span>
                    ) : null
                  )}
                </div>
              )
            })}
            {showInSegmentLabels && hasFree && (() => {
              const freePct = (freeValue / effectiveTotal) * 100
              if (freePct <= 0) return null
              const freeValStr = `${freeValue.toFixed(1)} ${unit}`
              const availablePx = slicePx(freePct)

              const canFitFull = availablePx >= labelPx(freeHeadroomLabel, freeValStr)
              const canFitShort = !canFitFull && availablePx >= labelPx(FREE_SHORT_LABEL, freeValStr)
              const canFitVal =
                !canFitFull &&
                !canFitShort &&
                availablePx >= labelPx('', freeValStr) &&
                freePct >= MIN_LABELLED_PCT

              return (
                <div
                  className="hb-segmented-bar__segment hb-segmented-bar__segment--free"
                  style={{ width: `${freePct}%` }}
                  title={`${freeHeadroomLabel}: ${freeValStr} (${freePct.toFixed(1)}%)`}
                >
                  {canFitFull ? (
                    <span className="hb-segmented-bar__segment-label hb-segmented-bar__segment-label--free" aria-hidden="true">
                      <span className="hb-segmented-bar__segment-name">{freeHeadroomLabel}</span>
                      <span className="hb-segmented-bar__segment-val">{freeValStr}</span>
                    </span>
                  ) : canFitShort ? (
                    <span className="hb-segmented-bar__segment-label hb-segmented-bar__segment-label--free" aria-hidden="true">
                      <span className="hb-segmented-bar__segment-name">{FREE_SHORT_LABEL}</span>
                      <span className="hb-segmented-bar__segment-val">{freeValStr}</span>
                    </span>
                  ) : canFitVal ? (
                    <span className="hb-segmented-bar__segment-label hb-segmented-bar__segment-label--free hb-segmented-bar__segment-label--val-only" aria-hidden="true">
                      <span className="hb-segmented-bar__segment-val">{freeValStr}</span>
                    </span>
                  ) : null}
                </div>
              )
            })()}
          </>
        ) : (
          <div className="hb-segmented-bar__offline-strip">
            <span className="hb-segmented-bar__offline-text">OFFLINE</span>
          </div>
        )}
      </div>

      {/* Tabular Legend */}
      {showLegend && (
        <div className="hb-segmented-bar__legend">
          {segments.map((seg) => {
            const segVal = Math.max(0, isNaN(seg.value) ? 0 : seg.value)
            const tone = seg.tone ?? 'neutral'
            const pct = effectiveTotal > 0 ? (segVal / effectiveTotal) * 100 : 0

            return (
              <div key={seg.id} className="hb-segmented-bar__legend-item">
                <span
                  className={cx(
                    'hb-segmented-bar__legend-bullet',
                    `hb-segmented-bar__legend-bullet--${tone}`,
                    seg.pattern === 'hatched' && 'is-hatched',
                  )}
                  aria-hidden="true"
                />
                <span className="hb-segmented-bar__legend-label">
                  {seg.label}
                  {seg.detail && (
                    <span className="hb-segmented-bar__legend-detail">
                      {' '}({seg.detail})
                    </span>
                  )}
                </span>
                <span className="hb-segmented-bar__legend-value">
                  {segVal.toFixed(1)} {unit}
                  <span className="hb-segmented-bar__legend-pct">
                    {' '}({pct.toFixed(0)}%)
                  </span>
                </span>
              </div>
            )
          })}

          {hasFree && !offline && (
            <div className="hb-segmented-bar__legend-item hb-segmented-bar__legend-item--free">
              <span
                className="hb-segmented-bar__legend-bullet hb-segmented-bar__legend-bullet--free"
                aria-hidden="true"
              />
              <span className="hb-segmented-bar__legend-label">{freeHeadroomLabel}</span>
              <span className="hb-segmented-bar__legend-value">
                {freeValue.toFixed(1)} {unit}
                <span className="hb-segmented-bar__legend-pct">
                  {' '}({((freeValue / effectiveTotal) * 100).toFixed(0)}%)
                </span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
})
