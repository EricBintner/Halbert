// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export interface DataGridRowProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  /** Leading icon (e.g. Folder, HardDrive, Cpu, Terminal). */
  icon?: React.ReactNode
  /** Primary title / label (e.g. volume name, metric name). */
  title: React.ReactNode
  /**
   * Data path, mountpoint, or device identifier (e.g. "/", "/var/lib/docker", "nvme0n1p2").
   * Guaranteed to start at the exact same horizontal coordinate across every row.
   */
  path?: React.ReactNode
  /** Secondary metadata or profile detail (e.g. "BTRFS · RAID1", "DDR5-5600", "PCIe 4.0"). */
  detail?: React.ReactNode
  /** Monospace tabular numbers / capacity readout (e.g. "142 GB / 500 GB"). */
  metrics?: React.ReactNode
  /**
   * Status indicator, percentage badge, or critical alert pill.
   * Locked inside a dedicated fixed-width slot so alerts can never push or distort text.
   */
  status?: React.ReactNode
  /** Physical instrument gauge (TactileMeter or SegmentedBar) rendered in Tier 2. */
  meter?: React.ReactNode
  /** Allotted width for the Title column on desktop (default: 200px). */
  titleWidth?: number | string
  /** Allotted width for the Path column on desktop (default: 180px). */
  pathWidth?: number | string
  /** Allotted width for the Metrics column on desktop (default: 180px). */
  metricsWidth?: number | string
  /** Allotted width for the Status column on desktop (default: 72px). */
  statusWidth?: number | string
  /**
   * Layout presentation variant:
   * - 'standard': 5-column rigid unigrid line above full-width meter (default).
   * - 'in-bar': Spacious avionics layout. Top deck has Title/Details (left) and Metrics/Status (right),
   *   meter track carries Path (inBarLeft) directly on the mark without grey/black boxes.
   * - 'dual-deck': Top deck has Title (left) and Metrics/Status (right),
   *   lower sub-deck has Path and Details.
   */
  variant?: 'standard' | 'in-bar' | 'dual-deck'
  /** Optional tertiary metadata or technical flags rendered below the meter. */
  subdeck?: React.ReactNode
}

/**
 * DataGridRow — Two-Tier Vignelli Unigrid Tabular Data Row.
 *
 * Enforces rigid columnar alignment across stacked instrument rows:
 * - Tier 1: 5-track CSS grid aligning Title, Data Path, Details, Metrics, and Status Badge.
 * - Tier 2: 100% full-width calibrated gauge track (TactileMeter or SegmentedBar).
 *
 * Ensures data paths start at the exact same horizontal coordinate regardless of title length,
 * and critical alert badges cannot push over other type or break layout.
 */
export const DataGridRow = React.forwardRef<HTMLDivElement, DataGridRowProps>(function DataGridRow(
  {
    icon,
    title,
    path,
    detail,
    metrics,
    status,
    meter,
    titleWidth = 200,
    pathWidth = 180,
    metricsWidth = 180,
    statusWidth = 72,
    variant = 'standard',
    subdeck,
    className,
    style,
    ...props
  },
  ref,
) {
  if (variant === 'in-bar') {
    return (
      <div
        ref={ref}
        className={cx('hb-data-row', 'hb-data-row--in-bar', className)}
        style={style}
        {...props}
      >
        {/* Upper Deck: Title + Detail on left, Metrics + Status on right */}
        <div className="hb-data-row__in-bar-header">
          <div className="hb-data-row__title-cell">
            {icon && <span className="hb-data-row__icon">{icon}</span>}
            <span className="hb-data-row__title">{title}</span>
            {detail && <span className="hb-data-row__detail-inline">· {detail}</span>}
          </div>
          <div className="hb-data-row__readout-group">
            {metrics && <span className="hb-data-row__metrics">{metrics}</span>}
            {status && <div className="hb-data-row__status-cell">{status}</div>}
          </div>
        </div>

        {/* Tier 2: 100% Full-Width Calibrated Instrument Track */}
        {meter && <div className="hb-data-row__meter-cell">{meter}</div>}

        {/* Optional Subdeck */}
        {subdeck && <div className="hb-data-row__subdeck">{subdeck}</div>}
      </div>
    )
  }

  if (variant === 'dual-deck') {
    return (
      <div
        ref={ref}
        className={cx('hb-data-row', 'hb-data-row--dual-deck', className)}
        style={style}
        {...props}
      >
        {/* Upper Deck: Title on left, Metrics + Status on right */}
        <div className="hb-data-row__dual-deck-header">
          <div className="hb-data-row__title-cell">
            {icon && <span className="hb-data-row__icon">{icon}</span>}
            <span className="hb-data-row__title">{title}</span>
          </div>
          <div className="hb-data-row__readout-group">
            {metrics && <span className="hb-data-row__metrics">{metrics}</span>}
            {status && <span className="hb-data-row__status-cell">{status}</span>}
          </div>
        </div>

        {/* Tier 2: 100% Full-Width Calibrated Instrument Track */}
        {meter && <div className="hb-data-row__meter-cell">{meter}</div>}

        {/* Lower Sub-deck: Path on left, Detail on right */}
        {(path || detail || subdeck) && (
          <div className="hb-data-row__dual-deck-footer">
            <div className="hb-data-row__path-cell">
              {path && <span className="hb-data-row__path">{path}</span>}
            </div>
            <div className="hb-data-row__detail-cell">
              {detail && <span className="hb-data-row__detail">{detail}</span>}
              {subdeck}
            </div>
          </div>
        )}
      </div>
    )
  }

  const customGridStyles: React.CSSProperties = {
    ...style,
    ['--data-row-title-width' as string]: typeof titleWidth === 'number' ? `${titleWidth}px` : titleWidth,
    ['--data-row-path-width' as string]: typeof pathWidth === 'number' ? `${pathWidth}px` : pathWidth,
    ['--data-row-metrics-width' as string]: typeof metricsWidth === 'number' ? `${metricsWidth}px` : metricsWidth,
    ['--data-row-status-width' as string]: typeof statusWidth === 'number' ? `${statusWidth}px` : statusWidth,
  }

  return (
    <div
      ref={ref}
      className={cx('hb-data-row', className)}
      style={customGridStyles}
      {...props}
    >
      {/* Tier 1: Strict 5-Column Grid */}
      <div className="hb-data-row__grid">
        {/* Col 1: Icon + Title */}
        <div className="hb-data-row__title-cell">
          {icon && <span className="hb-data-row__icon">{icon}</span>}
          <span className="hb-data-row__title">{title}</span>
        </div>

        {/* Col 2: Data Path (Starts at exact same X-coordinate across all rows) */}
        <div className="hb-data-row__path-cell">
          {path && <span className="hb-data-row__path">{path}</span>}
        </div>

        {/* Col 3: Secondary Detail / Tags */}
        <div className="hb-data-row__detail-cell">
          {detail && <span className="hb-data-row__detail">{detail}</span>}
        </div>

        {/* Col 4: Capacity / Numeric Metrics (Tabular nums) */}
        <div className="hb-data-row__metrics-cell">
          {metrics && <span className="hb-data-row__metrics">{metrics}</span>}
        </div>

        {/* Col 5: Status / Alert Badge (Fixed-width slot: cannot push layout) */}
        <div className="hb-data-row__status-cell">
          {status}
        </div>
      </div>

      {/* Tier 2: 100% Full-Width Calibrated Instrument Track */}
      {meter && <div className="hb-data-row__meter-cell">{meter}</div>}
    </div>
  )
})
