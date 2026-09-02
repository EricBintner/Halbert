// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export type HalbertMarkDensity =
  | 'auto'
  | '10'
  | '8'
  | '7'
  | '6'
  | '5'
  | '4'
  | '3'
  | 'display' // alias for 10
  | 'medium'  // alias for 6
  | 'compact' // alias for 4
  | 'small'   // alias for 3

export type HalbertMarkTone = 'accent' | 'ink' | 'canvas' | 'current' | 'badge'

export interface HalbertMarkProps extends React.SVGAttributes<SVGSVGElement> {
  /**
   * Rendered size in pixels (or CSS unit string).
   * @default 48
   */
  size?: number | string

  /**
   * Optical sizing density tier or line count:
   * - '10' / 'display': 10 concentric paths (100%), for >=96px
   * - '8': 8 concentric paths (80%), high-detail alternative for >=64px
   * - '7': 7 concentric paths (70%), balanced display/UI mark for >=48px
   * - '6' / 'medium': 6 concentric paths (60%), for 32px-96px
   * - '5': 5 concentric paths (50%), intermediate
   * - '4' / 'compact': 4 concentric paths (40%), crisp for 24px-32px
   * - '3' / 'small': 3 concentric paths (30%), micro/favicon for 16px-24px
   * - 'auto': automatically selects based on size (<=24 -> 3, <=64 -> 6, >64 -> 10)
   * @default 'auto'
   */
  density?: HalbertMarkDensity

  /**
   * Explicit numeric line count shortcut (3 | 4 | 5 | 6 | 7 | 8 | 10).
   * Overrides `density` if provided.
   */
  lines?: 3 | 4 | 5 | 6 | 7 | 8 | 10

  /**
   * Color semantic tone preset:
   * - 'accent': Olivetti Vermilion (#D34E24)
   * - 'ink': Charcoal (#1A1918)
   * - 'canvas': Warm Archival Paper (#F7F5F0)
   * - 'current': Inherits currentColor
   * - 'badge': Inverted canvas mark on rounded Vermilion tile
   * @default 'accent'
   */
  tone?: HalbertMarkTone

  /** Custom stroke color override */
  color?: string

  /** Custom background fill color */
  backgroundColor?: string

  /** Custom stroke-width override */
  strokeWidth?: number
}

// 10 lines (N=9, sw=26.67)
const PATHS_10 = [
  'M 512.00 80.00 V 512.00',
  'M 464.00 82.67 V 512.00 A 48.00 48.00 0 0 0 560.00 512.00 V 82.67',
  'M 416.00 90.80 V 512.00 A 96.00 96.00 0 0 0 608.00 512.00 V 90.80',
  'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
  'M 320.00 125.01 V 512.00 A 192.00 192.00 0 0 0 704.00 512.00 V 125.01',
  'M 272.00 152.80 V 512.00 A 240.00 240.00 0 0 0 752.00 512.00 V 152.80',
  'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
  'M 176.00 240.47 V 512.00 A 336.00 336.00 0 0 0 848.00 512.00 V 240.47',
  'M 128.00 314.09 V 512.00 A 384.00 384.00 0 0 0 896.00 512.00 V 314.09',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 8 lines (N=7, sw=34.29)
const PATHS_8 = [
  'M 512.00 80.00 V 512.00',
  'M 450.29 84.43 V 512.00 A 61.71 61.71 0 0 0 573.71 512.00 V 84.43',
  'M 388.57 98.01 V 512.00 A 123.43 123.43 0 0 0 635.43 512.00 V 98.01',
  'M 326.86 121.68 V 512.00 A 185.14 185.14 0 0 0 697.14 512.00 V 121.68',
  'M 265.14 157.48 V 512.00 A 246.86 246.86 0 0 0 758.86 512.00 V 157.48',
  'M 203.43 209.66 V 512.00 A 308.57 308.57 0 0 0 820.57 512.00 V 209.66',
  'M 141.71 289.49 V 512.00 A 370.29 370.29 0 0 0 882.29 512.00 V 289.49',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 7 lines (N=6, sw=40.00)
const PATHS_7 = [
  'M 512.00 80.00 V 512.00',
  'M 440.00 86.04 V 512.00 A 72.00 72.00 0 0 0 584.00 512.00 V 86.04',
  'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
  'M 296.00 137.88 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.88',
  'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
  'M 152.00 273.20 V 512.00 A 360.00 360.00 0 0 0 872.00 512.00 V 273.20',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 6 lines (N=5, sw=48.00)
const PATHS_6 = [
  'M 512.00 80.00 V 512.00',
  'M 425.60 88.74 V 512.00 A 86.40 86.40 0 0 0 598.40 512.00 V 88.74',
  'M 339.20 116.14 V 512.00 A 172.80 172.80 0 0 0 684.80 512.00 V 116.14',
  'M 252.80 166.42 V 512.00 A 259.20 259.20 0 0 0 771.20 512.00 V 166.42',
  'M 166.40 252.80 V 512.00 A 345.60 345.60 0 0 0 857.60 512.00 V 252.80',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 5 lines (N=4, sw=60.00)
const PATHS_5 = [
  'M 512.00 80.00 V 512.00',
  'M 404.00 93.72 V 512.00 A 108.00 108.00 0 0 0 620.00 512.00 V 93.72',
  'M 296.00 137.88 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.88',
  'M 188.00 226.26 V 512.00 A 324.00 324.00 0 0 0 836.00 512.00 V 226.26',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 4 lines (N=3, sw=80.00)
const PATHS_4 = [
  'M 512.00 80.00 V 512.00',
  'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
  'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

// 3 lines (N=2, sw=116.00)
const PATHS_3 = [
  'M 512.00 80.00 V 512.00',
  'M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

const CONFIG_BY_LINE_COUNT: Record<number, { paths: string; strokeWidth: number }> = {
  10: { paths: PATHS_10, strokeWidth: 26.67 },
  8: { paths: PATHS_8, strokeWidth: 34.29 },
  7: { paths: PATHS_7, strokeWidth: 40.00 },
  6: { paths: PATHS_6, strokeWidth: 48.00 },
  5: { paths: PATHS_5, strokeWidth: 60.00 },
  4: { paths: PATHS_4, strokeWidth: 80.00 },
  3: { paths: PATHS_3, strokeWidth: 116.00 },
}

function resolveLineCount(density: HalbertMarkDensity, lines?: number, size?: number | string): number {
  if (lines && CONFIG_BY_LINE_COUNT[lines]) {
    return lines
  }
  switch (density) {
    case '10':
    case 'display':
      return 10
    case '8':
      return 8
    case '7':
      return 7
    case '6':
    case 'medium':
      return 6
    case '5':
      return 5
    case '4':
    case 'compact':
      return 4
    case '3':
    case 'small':
      return 3
    case 'auto':
    default:
      if (typeof size === 'number') {
        if (size <= 24) return 3
        if (size <= 64) return 6
        return 10
      }
      return 6
  }
}

export const HalbertMark = React.forwardRef<SVGSVGElement, HalbertMarkProps>(
  function HalbertMark(
    {
      size = 48,
      density = 'auto',
      lines,
      tone = 'accent',
      color,
      backgroundColor,
      strokeWidth,
      className,
      style,
      ...props
    },
    ref,
  ) {
    const lineCount = resolveLineCount(density, lines, size)
    const { paths, strokeWidth: defaultStrokeWidth } = CONFIG_BY_LINE_COUNT[lineCount] || CONFIG_BY_LINE_COUNT[6]
    const finalStrokeWidth = strokeWidth ?? defaultStrokeWidth

    // Resolve color semantics
    let strokeColor = color ?? 'currentColor'
    let bgColor = backgroundColor
    let rx = 0

    if (!color) {
      switch (tone) {
        case 'accent':
          strokeColor = 'var(--color-accent, #D34E24)'
          break
        case 'ink':
          strokeColor = 'var(--color-ink, #1A1918)'
          break
        case 'canvas':
          strokeColor = 'var(--color-canvas, #F7F5F0)'
          break
        case 'current':
          strokeColor = 'currentColor'
          break
        case 'badge':
          strokeColor = 'var(--color-canvas, #F7F5F0)'
          bgColor = bgColor ?? 'var(--color-accent, #D34E24)'
          rx = 224
          break
      }
    }

    return (
      <svg
        ref={ref}
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 1024 1024"
        width={size}
        height={size}
        className={cx(
          'hb-mark',
          `hb-mark--${lineCount}lines`,
          lineCount === 10 && 'hb-mark--display',
          lineCount === 6 && 'hb-mark--medium',
          lineCount === 4 && 'hb-mark--compact',
          lineCount === 3 && 'hb-mark--small',
          className,
        )}
        style={{
          display: 'inline-block',
          verticalAlign: 'middle',
          flexShrink: 0,
          ...style,
        }}
        aria-hidden="true"
        {...props}
      >
        {bgColor && <rect width="1024" height="1024" rx={rx} fill={bgColor} />}
        <g
          fill="none"
          stroke={strokeColor}
          strokeWidth={finalStrokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={paths} />
        </g>
      </svg>
    )
  },
)
