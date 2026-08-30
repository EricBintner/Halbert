// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StatusLight — inline SVG status indicator for terminal blocks and task cards.
 *
 * No state is colour-only: each state has a shape, a glyph, and text.
 * SVG fill/stroke use currentColor; the parent sets the tone via CSS.
 * Forced-colours safe (currentColor survives).
 */

import { type ReactElement } from 'react'
import { cx } from '../lib'

export type StatusLightState =
  | 'running'
  | 'needs_attention'
  | 'done_unseen'
  | 'error'
  | 'blocked'

export interface StatusLightProps {
  state: StatusLightState
  elapsedSeconds?: number
  exitCode?: number | null
  label?: string
  size?: 'sm' | 'md'
  className?: string
}

const TONE_CLASS: Record<StatusLightState, string> = {
  running: 'hb-status-light--nominal',
  needs_attention: 'hb-status-light--warning',
  done_unseen: 'hb-status-light--nominal',
  error: 'hb-status-light--critical',
  blocked: 'hb-status-light--accent',
}

const DEFAULT_LABEL: Record<StatusLightState, string> = {
  running: '',
  needs_attention: 'needs input',
  done_unseen: 'exit 0',
  error: 'error',
  blocked: 'awaiting approval',
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}m${s.toString().padStart(2, '0')}s`
}

function labelText(props: StatusLightProps): string {
  if (props.label !== undefined) return props.label
  if (props.state === 'running')
    return props.elapsedSeconds !== undefined ? formatElapsed(props.elapsedSeconds) : ''
  if (props.state === 'done_unseen') return `exit ${props.exitCode ?? 0}`
  if (props.state === 'error') return `exit ${props.exitCode ?? 1}`
  return DEFAULT_LABEL[props.state]
}

function Glyph({ state, size }: { state: StatusLightState; size: number }): ReactElement | null {
  if (state === 'running') return null
  const half = size / 2
  if (state === 'needs_attention') {
    return (
      <>
        <rect x={half - 0.6} y={size * 0.2} width={1.2} height={size * 0.4} rx={0.3} fill="currentColor" />
        <rect x={half - 0.6} y={size * 0.68} width={1.2} height={1.2} rx={0.3} fill="currentColor" />
      </>
    )
  }
  if (state === 'done_unseen') {
    return (
      <path
        d={`M ${size * 0.25} ${half} L ${size * 0.42} ${size * 0.68} L ${size * 0.75} ${size * 0.32}`}
        stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" fill="none"
      />
    )
  }
  if (state === 'error') {
    return (
      <path
        d={`M ${size * 0.3} ${size * 0.3} L ${size * 0.7} ${size * 0.7} M ${size * 0.7} ${size * 0.3} L ${size * 0.3} ${size * 0.7}`}
        stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" fill="none"
      />
    )
  }
  if (state === 'blocked') {
    return (
      <>
        <rect x={size * 0.32} y={size * 0.28} width={1.4} height={size * 0.44} rx={0.3} fill="currentColor" />
        <rect x={size * 0.54} y={size * 0.28} width={1.4} height={size * 0.44} rx={0.3} fill="currentColor" />
      </>
    )
  }
  return null
}

export function StatusLight({ state, elapsedSeconds, exitCode, label, size = 'sm', className }: StatusLightProps): ReactElement {
  const px = size === 'md' ? 14 : 10
  const text = labelText({ state, elapsedSeconds, exitCode, label })
  const isFilled = state === 'done_unseen' || state === 'error' || state === 'blocked'
  const isOutline = state === 'running' || state === 'needs_attention'

  return (
    <span
      className={cx('hb-status-light', TONE_CLASS[state], className)}
      role="img"
      aria-label={text || state}
      data-status-light={state}
    >
      <svg
        width={px} height={px}
        viewBox={`0 0 ${px} ${px}`}
        fill={isFilled ? 'currentColor' : 'none'}
        stroke={isOutline ? 'currentColor' : 'none'}
        strokeWidth={isOutline ? 1.2 : 0}
        aria-hidden="true"
      >
        {isFilled && <circle cx={px / 2} cy={px / 2} r={px / 2 - 0.5} fill="currentColor" />}
        {isOutline && <circle cx={px / 2} cy={px / 2} r={px / 2 - 0.6} fill="none" stroke="currentColor" strokeWidth={1.2} />}
        <Glyph state={state} size={px} />
      </svg>
      {text && <span className="hb-status-light__label">{text}</span>}
    </span>
  )
}
