// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

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
  size?: 'sm' | 'md'
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
    offline = false,
    className,
    id,
    ...props
  },
  ref,
) {
  const barId = useId(id)
  
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
                />
              )
            })}
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
