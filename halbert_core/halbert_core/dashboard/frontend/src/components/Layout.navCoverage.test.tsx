// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * R08-01/NAV-01: every route App.tsx mounts must be reachable from
 * somewhere in the shell, or explicitly acknowledged as not needing a rail
 * entry (a mode entered another way, a redirect, or a page that overtakes
 * the shell rather than living in it).
 *
 * This reads App.tsx's own <Route path="..."> list via Vite's `?raw` import
 * (no Node fs/path — this project has no @types/node dependency), so a new
 * route added there without a nav entry (or without extending
 * ROUTES_WITHOUT_RAIL_ENTRY with a reason) fails this test instead of
 * shipping silently dead.
 */
import { describe, it, expect } from 'vitest'
import appSource from '../App.tsx?raw'
import { navSections } from './Layout'

/** Routes that are deliberately not in the rail, with the reason why. */
const ROUTES_WITHOUT_RAIL_ENTRY: Record<string, string> = {
  '/security': 'legacy path, redirects to /findings',
  '/settings': 'overtakes the shell; the top-bar gear is the only entry point',
  '/voice': 'a mode entered via the top-bar voice button / deep link, not a nav tab',
  '/voice-hud': 'the floating overlay window, not a shell surface',
}

function routesFromAppTsx(): string[] {
  const matches = [...appSource.matchAll(/<Route\s+path="([^"]+)"/g)]
  return matches.map((m) => m[1])
}

function railItemIds(): Set<string> {
  const ids = new Set<string>()
  for (const section of navSections) {
    for (const item of section.items) ids.add(item.id)
  }
  return ids
}

describe('Layout nav coverage (R08-01/NAV-01)', () => {
  it('finds routes in App.tsx to check (guards against the extraction regex going stale)', () => {
    expect(routesFromAppTsx().length).toBeGreaterThan(5)
  })

  it('every App.tsx route has a rail entry point or a documented exemption', () => {
    const routes = routesFromAppTsx()
    const railIds = railItemIds()
    const uncovered = routes.filter(
      (route) => !railIds.has(route) && !(route in ROUTES_WITHOUT_RAIL_ENTRY),
    )
    expect(uncovered).toEqual([])
  })

  it("doesn't carry stale exemptions for routes App.tsx no longer has", () => {
    const routes = new Set(routesFromAppTsx())
    const staleExemptions = Object.keys(ROUTES_WITHOUT_RAIL_ENTRY).filter((r) => !routes.has(r))
    expect(staleExemptions).toEqual([])
  })
})
