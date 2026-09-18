// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { TactileMeter } from './TactileMeter'
import { SegmentedBar, type SegmentItem } from './SegmentedBar'

export interface DrivePartitionItem {
  id: string
  device: string
  mountpoint?: string
  fstype?: string
  size: string
  used?: string
  percent?: number
  severity?: 'nominal' | 'warning' | 'critical' | 'telemetry'
}

export interface DriveCassetteProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Physical device path (e.g. "/dev/nvme0n1", "/dev/sdi"). */
  device: string
  /** Bcachefs/ZFS tier label or volume tag (e.g. "nvme.u2_01", "bg.hdd_14t_01"). */
  label?: string
  /** Commercial drive model (e.g. "Samsung PM9A3 3.84 TB", "Seagate Exos X16 14 TB"). */
  model?: string
  /** Hardware transport and bus interface (e.g. "PCIe 4.0 x4 NVMe", "SATA 6 Gb/s · 7200 RPM"). */
  transport?: string
  /** Total raw capacity (e.g. "3.84 TB", "14.0 TB"). */
  size?: string
  /** Currently used capacity (e.g. "1.20 TB"). */
  used?: string
  /** Utilization percentage (0-100). */
  percent?: number
  /** Drive SMART health status (e.g. "PASSED", "WARNING", "FAILED"). */
  smartStatus?: string
  /** Drive temperature in Celsius (e.g. 38 or "38°C"). */
  temperature?: number | string
  /** Functional roles served in array (e.g. ["Write", "Foreground"], ["Bulk Data"]). */
  roles?: string[]
  /** Optional serial number or WWN identifier. */
  serial?: string
  /** Nested partitions belonging to this physical drive. */
  partitions?: DrivePartitionItem[]
  /** Custom meter override (if caller provides pre-configured meter). */
  meter?: React.ReactNode
  /** Optional tertiary metadata or technical flags. */
  subdeck?: React.ReactNode
}

/**
 * DriveCassette — A semi-isolated physical storage drive instrument.
 *
 * Implements the Braun / Vignelli physical cassette metaphor:
 * - Clear, semi-isolated containment with generous breathing room.
 * - Hardware identity (device node, model, transport bus, serial).
 * - Live physical diagnostics (SMART status pip, temperature in Celsius).
 * - Thick calibrated gauge track; identifiers live in the header, not on the mark.
 * - Integrated partition map grouping when physical drives contain partition tables.
 */
export const DriveCassette = React.forwardRef<HTMLDivElement, DriveCassetteProps>(function DriveCassette(
  {
    device,
    label,
    model,
    transport,
    size,
    used,
    percent,
    smartStatus = 'PASSED',
    temperature,
    roles = [],
    serial,
    partitions,
    meter,
    subdeck,
    className,
    ...props
  },
  ref,
) {
  const cassetteId = useId()

  const isWarning = smartStatus === 'WARNING'
  const isCritical = smartStatus === 'FAILED' || smartStatus === 'CRITICAL'

  const smartTone = isCritical ? 'critical' : isWarning ? 'warning' : 'nominal'

  // Convert partitions to SegmentedBar slices if present
  const partitionSegments: SegmentItem[] = React.useMemo(() => {
    if (!partitions || partitions.length === 0) return []
    const tonePalette: SegmentItem['tone'][] = ['data-blue', 'data-teal', 'data-amber', 'data-purple']
    return partitions.map((p, idx) => {
      const numMatch = p.size.match(/([\d.]+)\s*([A-Za-z]+)?/)
      let val = numMatch ? parseFloat(numMatch[1]) : 10
      const unit = numMatch && numMatch[2] ? numMatch[2].toUpperCase() : 'GB'
      if (unit.startsWith('T')) val *= 1000
      else if (unit.startsWith('M')) val /= 1000

      return {
        id: p.id || p.device,
        label: p.mountpoint || p.device,
        value: val,
        tone: p.severity === 'critical' ? 'critical' : p.severity === 'warning' ? 'warning' : tonePalette[idx % tonePalette.length],
        detail: p.fstype,
      }
    })
  }, [partitions])

  return (
    <div
      ref={ref}
      id={cassetteId}
      className={cx('hb-drive-cassette', isCritical && 'is-critical', isWarning && 'is-warning', className)}
      {...props}
    >
      {/* Header Deck: Hardware Identity & Diagnostics */}
      <div className="hb-drive-cassette__header">
        {/* Left: Device & Hardware Profile */}
        <div className="hb-drive-cassette__identity">
          <div className="hb-drive-cassette__name-row">
            <span className="hb-drive-cassette__device">{device}</span>
            {label && <span className="hb-drive-cassette__label-chip">{label}</span>}
            {roles.map((role) => (
              <span key={role} className="hb-drive-cassette__role-tag">
                {role}
              </span>
            ))}
          </div>

          <div className="hb-drive-cassette__hardware-meta">
            {model && <span className="hb-drive-cassette__model">{model}</span>}
            {model && transport && <span className="hb-drive-cassette__bullet">·</span>}
            {transport && <span className="hb-drive-cassette__transport">{transport}</span>}
            {size && <span className="hb-drive-cassette__size">({size})</span>}
          </div>

          {serial && <div className="hb-drive-cassette__serial">SN: {serial}</div>}
        </div>

        {/* Right: Diagnostics & Telemetry (SMART & Temp) */}
        <div className="hb-drive-cassette__diagnostics">
          {temperature != null && (
            <span className="hb-drive-cassette__temp">
              {typeof temperature === 'number' ? `${temperature}°C` : temperature}
            </span>
          )}
          <span className={cx('hb-drive-cassette__smart-pip', `hb-drive-cassette__smart-pip--${smartTone}`)}>
            <span className="hb-drive-cassette__smart-dot" />
            <span className="hb-drive-cassette__smart-text">{smartStatus}</span>
          </span>
        </div>
      </div>

      {/* Tier 2: Physical Instrument Gauge */}
      <div className="hb-drive-cassette__meter-zone">
        {meter ? (
          meter
        ) : partitions && partitions.length > 0 ? (
          <div className="hb-drive-cassette__partition-block">
            <div className="hb-drive-cassette__partition-header">
              <span className="hb-drive-cassette__partition-title">Physical Partition Allocation</span>
              <span className="hb-drive-cassette__partition-count">
                {partitions.length} {partitions.length === 1 ? 'partition' : 'partitions'}
              </span>
            </div>
            <SegmentedBar
              segments={partitionSegments}
              size="md"
              unit="GB"
              showLegend={false}
              showFreeHeadroom
            />

            {/* Nested Partition Sub-Rows */}
            <div className="hb-drive-cassette__partition-list">
              {partitions.map((p) => (
                <div key={p.id || p.device} className="hb-drive-cassette__partition-row">
                  <div className="hb-drive-cassette__part-id">
                    <span className="hb-drive-cassette__part-dev">{p.device}</span>
                    {p.mountpoint && <span className="hb-drive-cassette__part-mount">→ {p.mountpoint}</span>}
                  </div>
                  <div className="hb-drive-cassette__part-info">
                    {p.fstype && <span className="hb-drive-cassette__part-fs">{p.fstype}</span>}
                    <span className="hb-drive-cassette__part-capacity">
                      {p.used ? `${p.used} / ${p.size}` : p.size}
                      {p.percent != null && ` (${p.percent}%)`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="hb-drive-cassette__gauge-block">
            {(used || size || percent != null) && (
              <div className="hb-drive-cassette__gauge-header">
                <span className="hb-drive-cassette__gauge-readout">
                  {used && size
                    ? `${used} / ${size} · ${percent ?? 0}%`
                    : size
                      ? `${size} · ${percent ?? 0}%`
                      : `${percent ?? 0}%`}
                </span>
              </div>
            )}
            <TactileMeter
              value={percent ?? 0}
              tone={isCritical ? 'critical' : isWarning ? 'warning' : 'telemetry'}
              size="thick"
              aria-label={label ? `${label} · ${device} capacity` : `${device} capacity`}
              ticks={[25, 50, 75, 90]}
            />
          </div>
        )}
      </div>

      {/* Optional Subdeck */}
      {subdeck && <div className="hb-drive-cassette__subdeck">{subdeck}</div>}
    </div>
  )
})
