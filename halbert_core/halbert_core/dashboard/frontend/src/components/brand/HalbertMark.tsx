// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'

export type HalbertMarkDensity = 'auto' | 'display' | 'medium' | 'small' | 'compact'
export type HalbertMarkTone = 'accent' | 'ink' | 'canvas' | 'current' | 'badge'

export interface HalbertMarkProps extends React.SVGAttributes<SVGSVGElement> {
  size?: number | string
  density?: HalbertMarkDensity
  tone?: HalbertMarkTone
  color?: string
  backgroundColor?: string
  strokeWidth?: number
}

const PATHS_DISPLAY = [
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

const PATHS_MEDIUM = [
  'M 512.00 80.00 V 512.00',
  'M 425.60 88.74 V 512.00 A 86.40 86.40 0 0 0 598.40 512.00 V 88.74',
  'M 339.20 116.14 V 512.00 A 172.80 172.80 0 0 0 684.80 512.00 V 116.14',
  'M 252.80 166.42 V 512.00 A 259.20 259.20 0 0 0 771.20 512.00 V 166.42',
  'M 166.40 252.80 V 512.00 A 345.60 345.60 0 0 0 857.60 512.00 V 252.80',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

const PATHS_SMALL = [
  'M 512.00 80.00 V 512.00',
  'M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

const PATHS_COMPACT = [
  'M 512.00 80.00 V 512.00',
  'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
  'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ')

const TIER_CONFIG: Record<
  Exclude<HalbertMarkDensity, 'auto'>,
  { paths: string; strokeWidth: number }
> = {
  display: { paths: PATHS_DISPLAY, strokeWidth: 26.67 },
  medium: { paths: PATHS_MEDIUM, strokeWidth: 48.0 },
  small: { paths: PATHS_SMALL, strokeWidth: 116.0 },
  compact: { paths: PATHS_COMPACT, strokeWidth: 80.0 },
}

export const HalbertMark = React.forwardRef<SVGSVGElement, HalbertMarkProps>(
  function HalbertMark(
    {
      size = 20,
      density = 'auto',
      tone = 'accent',
      color,
      backgroundColor,
      strokeWidth,
      className = '',
      style = {},
      ...props
    },
    ref,
  ) {
    let effectiveDensity: Exclude<HalbertMarkDensity, 'auto'> = 'medium'
    if (density === 'auto') {
      if (typeof size === 'number') {
        if (size <= 24) {
          effectiveDensity = 'small'
        } else if (size <= 64) {
          effectiveDensity = 'medium'
        } else {
          effectiveDensity = 'display'
        }
      } else {
        effectiveDensity = 'medium'
      }
    } else {
      effectiveDensity = density
    }

    const { paths, strokeWidth: defaultStrokeWidth } = TIER_CONFIG[effectiveDensity]
    const finalStrokeWidth = strokeWidth ?? defaultStrokeWidth

    let strokeColor = color ?? '#D34E24'
    let bgColor = backgroundColor
    let rx = 0

    if (!color) {
      switch (tone) {
        case 'accent':
          strokeColor = '#D34E24'
          break
        case 'ink':
          strokeColor = '#1A1918'
          break
        case 'canvas':
          strokeColor = '#F7F5F0'
          break
        case 'current':
          strokeColor = 'currentColor'
          break
        case 'badge':
          strokeColor = '#F7F5F0'
          bgColor = bgColor ?? '#D34E24'
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
        className={className}
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

export default HalbertMark
