// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, expect, it } from 'vitest'
import { routeAllowed, safeRouteAfterSwitch } from './routeCapabilities'

const FULL = { home: true, gpu: true, development: true }
const BARE = { home: false, gpu: false, development: false }

describe('routeAllowed', () => {
  it('allows unlisted routes on any node', () => {
    for (const p of ['/', '/terminal', '/storage', '/compute', '/findings', '/approvals', '/settings']) {
      expect(routeAllowed(p, BARE)).toBe(true)
    }
  })

  it('gates capability routes on the matching feature flag', () => {
    expect(routeAllowed('/gpu', BARE)).toBe(false)
    expect(routeAllowed('/gpu', { ...BARE, gpu: true })).toBe(true)
    expect(routeAllowed('/home', { ...BARE, home: true })).toBe(true)
    expect(routeAllowed('/containers', { ...BARE, development: true })).toBe(true)
  })

  it('uses the fine-grained flags — GPU alone does not unlock development', () => {
    expect(routeAllowed('/development', { home: false, gpu: true, development: false })).toBe(false)
  })

  it('allows everything while instance info has not loaded', () => {
    expect(routeAllowed('/gpu', null)).toBe(true)
  })

  it('treats trailing slashes as the same route', () => {
    expect(routeAllowed('/gpu/', BARE)).toBe(false)
    expect(routeAllowed('/', BARE)).toBe(true)
  })
})

describe('safeRouteAfterSwitch', () => {
  it('keeps the route when the target node serves it', () => {
    expect(safeRouteAfterSwitch('/storage', BARE)).toBe('/storage')
    expect(safeRouteAfterSwitch('/gpu', FULL)).toBe('/gpu')
  })

  it('falls back to / when the target node cannot serve the route', () => {
    expect(safeRouteAfterSwitch('/gpu', BARE)).toBe('/')
    expect(safeRouteAfterSwitch('/home', BARE)).toBe('/')
  })
})
