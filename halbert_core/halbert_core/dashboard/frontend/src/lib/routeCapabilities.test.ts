// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, expect, it } from 'vitest'
import { routeAllowed, safeRouteAfterSwitch, landingRoute } from './routeCapabilities'

const FULL = { home: true, gpu: true, development: true, containers: true }
const BARE = { home: false, gpu: false, development: false, containers: false }

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
    expect(routeAllowed('/containers', { ...BARE, containers: true })).toBe(true)
  })

  it('uses the fine-grained flags — GPU alone does not unlock development', () => {
    expect(routeAllowed('/development', { ...BARE, gpu: true })).toBe(false)
  })

  it('keeps Containers without Development — a declared server drops one, not both', () => {
    const serverOnly = { home: false, gpu: false, development: false, containers: true }
    expect(routeAllowed('/containers', serverOnly)).toBe(true)
    expect(routeAllowed('/development', serverOnly)).toBe(false)
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

describe('landingRoute', () => {
  it('lands a workstation — or an undeclared machine — on the overview', () => {
    expect(landingRoute(['workstation'])).toBe('/')
    expect(landingRoute([])).toBe('/')
    expect(landingRoute(null)).toBe('/')
  })

  it('lands a machine that is only a server on Services', () => {
    expect(landingRoute(['server'])).toBe('/services')
  })

  it('lands a machine that is only a home hub on Home', () => {
    expect(landingRoute(['home_automation_hub'])).toBe('/home')
  })

  it('a workstation side always wins the landing', () => {
    expect(landingRoute(['workstation', 'server'])).toBe('/')
    expect(landingRoute(['workstation', 'home_automation_hub'])).toBe('/')
  })

  it('a server+hub closet box lands on Services', () => {
    expect(landingRoute(['server', 'home_automation_hub'])).toBe('/services')
  })
})
