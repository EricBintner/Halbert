// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * routeCapabilities — the single route → machine-capability table.
 *
 * Two consumers, one table (handoff HANDOFF-NODE-LIST-RAIL-DESIGN §5R.3 N5 —
 * if the rail's item filter and the node-switch fallback keep separate lists
 * they WILL drift):
 *
 * 1. Layout's nav filtering — hide a nav item when the active node lacks the
 *    capability it needs (GPU item on a node with no GPU).
 * 2. The post-switch route fallback — after switching nodes the page reloads
 *    pointed at the new machine; if the current route is not supported there,
 *    land on `/` instead of a broken page (`/gpu` on a GPU-less node).
 *
 * Anything not listed here is a route every node serves (terminal, storage,
 * services, network, backups, apps, sharing, findings, approvals, compute,
 * settings) and is never bounced. The rail's capability filtering and this
 * fallback read exactly this map.
 *
 * Gating uses the fine-grained flags in /api/instance/info (`features.gpu`,
 * `features.home`, `features.development`) — not the coarse "development
 * implies GPU" collapse the old filter used (§5R.2).
 */

export interface InstanceFeatures {
  home: boolean
  gpu: boolean
  development: boolean
  /** Split from `development` when machine roles landed: a machine
   * declared server-or-hub-only drops the Development tab but keeps
   * Containers, which the role table calls a primary server view. */
  containers: boolean
}

/** Routes that demand a capability. Unlisted routes are always allowed. */
export const ROUTE_REQUIREMENTS: Readonly<Record<string, keyof InstanceFeatures>> = {
  '/home': 'home',
  '/gpu': 'gpu',
  '/containers': 'containers',
  '/development': 'development',
}

/**
 * Can this route be served by a node with these features?
 *
 * `features === null` means instance info has not loaded yet — allow, as the
 * pre-existing filter did: a flicker of an item that later hides beats a nav
 * that starts empty.
 */
export function routeAllowed(
  pathname: string,
  features: InstanceFeatures | null,
): boolean {
  if (!features) return true
  const required = ROUTE_REQUIREMENTS[normalize(pathname)]
  return required === undefined || features[required] === true
}

/**
 * Where a node switch should land: the current route if the target node can
 * serve it, otherwise `/` (the node's landing page — the node button IS the
 * landing page, so `/` always exists).
 */
export function safeRouteAfterSwitch(
  pathname: string,
  features: InstanceFeatures | null,
): string {
  return routeAllowed(pathname, features) ? pathname : '/'
}

/** Trailing slashes and empty strings collapse to the landing route. */
function normalize(pathname: string): string {
  const p = pathname.replace(/\/+$/, '')
  return p === '' ? '/' : p
}

/**
 * Where onboarding should land once setup finishes, given the declared
 * machine roles (HANDOFF-ONBOARDING-ROLE-INFERENCE §6.1). A machine that is
 * only a server opens on Services (service health is its centre of
 * gravity); a machine that is only a home hub opens on the Home panel;
 * anything with a workstation side — and anything undeclared — opens on
 * the overview. Used for the post-onboarding navigation only; `/` stays
 * reachable from the rail either way.
 */
export function landingRoute(roles: readonly string[] | null | undefined): string {
  const set = new Set(roles ?? [])
  if (set.has('workstation') || set.size === 0) return '/'
  if (set.has('server')) return '/services'
  if (set.has('home_automation_hub')) return '/home'
  return '/'
}
