// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/**
 * The same WCAG maths as scripts/check_contrast.py, in the browser.
 *
 * The Python gate proves the token FILE is sound. This proves what the browser
 * actually computed after every var() chain, cascade rule, and theme swap
 * resolved — which is the number a user is subject to.
 */

export function resolveToken(name: string, el: Element = document.documentElement): string {
  return getComputedStyle(el).getPropertyValue(name).trim()
}

/** Parse any computed colour the browser hands back into RGB. */
export function toRgb(color: string): [number, number, number] | null {
  const probe = document.createElement('div')
  probe.style.color = color
  probe.style.display = 'none'
  document.body.appendChild(probe)
  const computed = getComputedStyle(probe).color
  probe.remove()

  const match = computed.match(/rgba?\(([^)]+)\)/)
  if (!match) return null
  const parts = match[1].split(/[,\s/]+/).map(Number)
  if (parts.length < 3 || parts.slice(0, 3).some(Number.isNaN)) return null
  return [parts[0], parts[1], parts[2]]
}

function toLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

export function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}

export function contrast(fg: string, bg: string): number | null {
  const a = toRgb(fg)
  const b = toRgb(bg)
  if (!a || !b) return null
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

export type Grade = 'AAA' | 'AA' | 'UI' | 'FAIL'

export function grade(ratio: number, floor: number): Grade {
  if (ratio >= 7) return 'AAA'
  if (ratio >= 4.5) return 'AA'
  if (ratio >= 3) return floor <= 3 ? 'UI' : 'FAIL'
  return 'FAIL'
}

export const GRADE_TONE: Record<Grade, string> = {
  AAA: 'var(--color-status-nominal)',
  AA: 'var(--color-status-nominal)',
  UI: 'var(--color-status-telemetry)',
  FAIL: 'var(--color-status-critical)',
}
