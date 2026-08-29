// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * peerApi — typed API client for peer pairing and fleet endpoints.
 *
 * Implements the frontend side of findings C1, C2, C5, and M14.
 *
 * C1 — Single token system: The pairing flow returns a bearer token
 *      that is stored in localStorage and used for all peer/fleet
 *      API calls. This is the same token the MCP HTTP/SSE transport
 *      would use (Phase 4b).
 *
 * C2 — Extends Instance Switcher: The discovered peers and paired
 *      peers APIs feed the InstanceSwitch dropdown (already exists in
 *      shell/InstanceSwitch.tsx). This module provides the typed
 *      fetchers; InstanceSwitch consumes them.
 *
 * C5 — Fleet inspection via MCP proxy: The inspectNode() function
 *      calls POST /api/fleet/{nodeId}/inspect which proxies an MCP
 *      tool call to the satellite. No bespoke inspect API.
 *
 * M14 — Per-peer tokens + revocation: The revokePeer() function
 *      calls DELETE /api/peers/{nodeId} for surgical revocation.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A peer discovered via mDNS (unauthenticated — no token yet). */
export interface DiscoveredPeer {
  node_id: string
  node_name: string
  role: 'compute_provider' | 'satellite'
  host: string
  port: number
  endpoint: string
  capabilities: string[]
  compute_backends: string[]  // M13: ollama, apple_foundation, vllm, mlx
}

/** A paired peer with credential stored in peers.json. */
export interface PairedPeer {
  node_id: string
  node_name: string
  role: string
  paired_at: string
  last_seen: string | null
  revoked: boolean
  endpoint: string | null
  capabilities: string[]
}

/** Fleet node status — a paired peer with live status. */
export interface FleetNodeStatus {
  node_id: string
  node_name: string
  role: string
  endpoint: string | null
  online: boolean
  last_seen: string | null
  capabilities: string[]
  vitals: {
    cpu_percent: number
    memory_percent: number
    memory_available_mb: number
    temperature_c: number | null
    uptime_seconds: number
    load_average_1m: number | null
    disk_percent: number
  } | null
  discovery_count: number | null
}

/** Pairing request — satellite → desktop. */
export interface PairRequest {
  node_id: string
  node_name: string
  role: string
  capabilities: string[]
  endpoint?: string
}

/** Pairing response — desktop → satellite (PIN pending). */
export interface PairResponse {
  pin: string
  status: 'pending'
  message: string
}

/** Verify request — satellite → desktop (confirm with PIN). */
export interface VerifyRequest {
  pin: string
  node_id: string
}

/** Verify response — desktop → satellite (token issued). */
export interface VerifyResponse {
  token: string
  status: 'paired'
  desktop_node_id: string
}

/** MCP tool inspection request. */
export interface InspectRequest {
  tool_name: string
  params: Record<string, unknown>
}

/** MCP tool inspection response. */
export interface InspectResponse {
  node_id: string
  tool_name: string
  result: unknown
  redacted: boolean
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

const API_BASE = ''  // Relative paths — same-origin (Phase 7 runtime config)

/** Get the bearer token from localStorage (set during pairing). */
function getPeerToken(): string | null {
  return localStorage.getItem('halbert:peer-token')
}

/** Set the bearer token (called after successful pairing). */
export function setPeerToken(token: string): void {
  localStorage.setItem('halbert:peer-token', token)
}

/** Clear the bearer token (called on revocation or logout). */
export function clearPeerToken(): void {
  localStorage.removeItem('halbert:peer-token')
}

/** Build auth headers for peer/fleet API calls. */
function authHeaders(): Record<string, string> {
  const token = getPeerToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ---------------------------------------------------------------------------
// Peer pairing endpoints (C1, M14)
// ---------------------------------------------------------------------------

/** Request pairing with a Desktop (satellite-side call). */
export async function requestPairing(req: PairRequest): Promise<PairResponse> {
  const res = await fetch(`${API_BASE}/api/peers/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Pairing failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/** Verify pairing with PIN (satellite-side call). */
export async function verifyPairing(req: VerifyRequest): Promise<VerifyResponse> {
  const res = await fetch(`${API_BASE}/api/peers/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Verify failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/** List all paired peers (requires auth). */
export async function listPairedPeers(): Promise<PairedPeer[]> {
  const res = await fetch(`${API_BASE}/api/peers/list`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`List peers failed: ${res.status}`)
  return res.json()
}

/** Revoke a peer's token (M14 — surgical revocation). */
export async function revokePeer(nodeId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/peers/${nodeId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Revoke failed: ${res.status}`)
}

/** List peers discovered via mDNS (unauthenticated). */
export async function listDiscoveredPeers(): Promise<DiscoveredPeer[]> {
  const res = await fetch(`${API_BASE}/api/peers/discovered`)
  if (!res.ok) throw new Error(`Discovered peers failed: ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Fleet Cockpit endpoints (C5)
// ---------------------------------------------------------------------------

/** List all fleet nodes with live status. */
export async function listFleetNodes(): Promise<FleetNodeStatus[]> {
  const res = await fetch(`${API_BASE}/api/fleet/nodes`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Fleet nodes failed: ${res.status}`)
  return res.json()
}

/** Get a satellite's instance info. */
export async function getNodeInfo(nodeId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/fleet/${nodeId}/info`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Node info failed: ${res.status}`)
  return res.json()
}

/** Get a satellite's latest telemetry. */
export async function getNodeTelemetry(nodeId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/fleet/${nodeId}/telemetry`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Node telemetry failed: ${res.status}`)
  return res.json()
}

/** Proxy an MCP tool call to a satellite (C5 — no bespoke inspect API). */
export async function inspectNode(nodeId: string, req: InspectRequest): Promise<InspectResponse> {
  const res = await fetch(`${API_BASE}/api/fleet/${nodeId}/inspect`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Inspect failed: ${res.status}`)
  return res.json()
}

/** Get a satellite's discovery snapshot. */
export async function getNodeDiscoveries(nodeId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/fleet/${nodeId}/discoveries`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Node discoveries failed: ${res.status}`)
  return res.json()
}
