// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface StorageTierGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Tier title (e.g. "Tier 01: Foreground Write Cache", "Tier 02: Background Bulk Storage"). */
  title: string
  /** Technical profile / target rules (e.g. "Target: foreground · 2 Replicas (Mirror)"). */
  subtitle?: string
  /** Role label or classification (e.g. "WRITE CACHE", "METADATA", "BULK DATA"). */
  roleLabel?: string
  /** Overall raw or usable capacity (e.g. "7.68 TB Raw", "84.0 TB Raw"). */
  capacity?: string
  /** Operational status indicator or alert. */
  status?: React.ReactNode
  /** Optional tier-level allocation or distribution bar. */
  meter?: React.ReactNode
  /** Semi-isolated physical drive cassettes contained in this tier. */
  children: React.ReactNode
}

/**
 * StorageTierGroup — A functional storage tier or RAID VDEV cassette group.
 *
 * Implements architectural tiering for complex filesystems (Bcachefs, ZFS, multi-device Btrfs):
 * - Groups drives by operational tier (Foreground Write Cache, Promote Cache, Metadata, Bulk Data).
 * - Semi-isolates member drive cassettes inside a tactile, bordered enclosure.
 * - Displays tier target rules, aggregate capacity, and operational health.
 */
export const StorageTierGroup = React.forwardRef<HTMLDivElement, StorageTierGroupProps>(function StorageTierGroup(
  {
    title,
    subtitle,
    roleLabel,
    capacity,
    status,
    meter,
    children,
    className,
    ...props
  },
  ref,
) {
  const groupId = useId()

  return (
    <div
      ref={ref}
      id={groupId}
      className={cx('hb-tier-group', className)}
      {...props}
    >
      {/* Tier Header Deck */}
      <div className="hb-tier-group__header">
        <div className="hb-tier-group__title-cluster">
          <div className="hb-tier-group__title-row">
            <h4 className="hb-tier-group__title">{title}</h4>
            {roleLabel && <span className="hb-tier-group__role-tag">{roleLabel}</span>}
          </div>
          {subtitle && <p className="hb-tier-group__subtitle">{subtitle}</p>}
        </div>

        <div className="hb-tier-group__meta-cluster">
          {capacity && <span className="hb-tier-group__capacity">{capacity}</span>}
          {status && <div className="hb-tier-group__status">{status}</div>}
        </div>
      </div>

      {/* Optional Tier-Level Allocation Meter */}
      {meter && <div className="hb-tier-group__meter-zone">{meter}</div>}

      {/* Semi-Isolated Member Drive Cassettes */}
      <div className="hb-tier-group__drives">
        {children}
      </div>
    </div>
  )
})
