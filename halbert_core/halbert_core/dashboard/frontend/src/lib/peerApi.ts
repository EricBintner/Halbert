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
  compute_backends: string[]  // M13: ollama, vllm (mlx host-local); apple_foundation is never advertised
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

// ---------------------------------------------------------------------------
// Compute-peer endpoints (home automation simplification, S3 / W15)
//
// An HA node (home) has no model picker: it is a pure client of
// the workstation's compute endpoint. The ComputePeerCard in Settings is the
// one surface for that link — these are its three calls: read the saved
// link, test it, persist it.
// ---------------------------------------------------------------------------

/** The saved compute-peer link, summarised for the card's read-only block. */
export interface ComputePeerLinkSummary {
  url: string
  endpointId: string
  /** A bearer token was stored by the pairing (never the token itself). */
  hasToken: boolean
  /** Whether each slot resolves to the peer endpoint (read-only report). */
  slots: { chat_model: boolean; specialist_model: boolean }
}

/** Read the persisted compute-peer link from the model configuration. */
export async function getComputePeerLink(): Promise<ComputePeerLinkSummary | null> {
  const res = await fetch(`${API_BASE}/llm/config`)
  if (!res.ok) throw new Error(`Model config failed: ${res.status}`)
  const payload = await res.json()
  const llm = payload?.data?.llm_config ?? payload?.llm_config
  const endpoints: Array<{ id: string; url: string; provider: string; api_key?: string }> =
    llm?.saved_endpoints ?? []
  const peer = endpoints.find((e) => e?.provider === 'peer')
  if (!peer) return null
  const pointsHere = (slot: { enabled: boolean; endpoint_id: string } | undefined) =>
    !!slot && slot.enabled && slot.endpoint_id === peer.id
  return {
    url: peer.url,
    endpointId: peer.id,
    hasToken: !!peer.api_key,
    slots: {
      chat_model: pointsHere(llm?.chat_model),
      specialist_model: pointsHere(llm?.specialist_model),
    },
  }
}

/** Result of POST /compute/peer-probe — the card's "Test Connection" button. */
export interface ComputePeerProbeResult {
  ok: boolean
  message: string
  /** Model tags the workstation advertises; empty until its models route exists. */
  models: string[]
  url: string
}

/** Probe a workstation's compute endpoint (read-only, no GPU time). */
export async function probeComputePeer(
  endpoint: string,
  token = '',
): Promise<ComputePeerProbeResult> {
  const res = await fetch(`${API_BASE}/compute/peer-probe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint, token }),
  })
  const payload = await res.json()
  if (payload?.error) {
    throw new Error(payload.error.message || 'Peer probe failed')
  }
  return payload.data as ComputePeerProbeResult
}

/** The persisted link, as returned by POST /api/peers/compute-peer. */
export interface ComputePeerLink {
  status: string
  endpoint_id: string
  url: string
  model: string
  slots: string[]
}

/** Persist the workstation as this node's compute endpoint.
 *
 * One peer:// endpoint is saved and both chat_model and specialist_model
 * point at it — the same endpoint, the same model list — with the
 * workstation's own model configuration governing which model serves.
 * Home variants only (the route refuses the sysadmin variant).
 */
export async function linkComputePeer(
  endpoint: string,
  token = '',
  name = '',
): Promise<ComputePeerLink> {
  const res = await fetch(`${API_BASE}/api/peers/compute-peer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint, token, name }),
  })
  if (!res.ok) throw new Error(`Link failed: ${res.status} ${await res.text()}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Devices & entity-mode endpoints (P7a — routes/devices.py)
// ---------------------------------------------------------------------------
// The singular-entity product language: devices and bodies, not nodes and
// peers. These wrap the devices router the Settings → Devices page drives.

/** A paired device as the Devices page shows it (no token material). */
export interface DeviceInfo {
  node_id: string
  node_name: string
  role: string
  endpoint: string | null
  capabilities: string[]
  compute_direction: string
  wol_enabled: boolean
  wol_mac: string | null
  wol_broadcast: string | null
  paired_at: string
  last_seen: string | null
  revoked: boolean
}

/** GET /api/devices — devices plus this node's entity identity. */
export interface DevicesState {
  status: string
  entity_mode: 'singular' | 'independent'
  body_name: string
  canonical_memory_url: string
  canonical_thread_url: string
  devices: DeviceInfo[]
}

export interface EntityModeRequest {
  mode: 'singular' | 'independent'
  /** The canonical host; memory/thread URLs derive as {base}/api/memory
   *  and {base}/api/conversations. */
  base_url?: string
  memory_url?: string
  thread_url?: string
}

/** List paired devices + this node's entity identity. */
export async function listDevices(): Promise<DevicesState> {
  const res = await fetch(`${API_BASE}/api/devices`)
  if (!res.ok) throw new Error(`Devices failed: ${res.status}`)
  return res.json()
}

/** Toggle this node between singular and independent entity mode. */
export async function setEntityMode(req: EntityModeRequest): Promise<DevicesState> {
  const res = await fetch(`${API_BASE}/api/devices/entity-mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Entity mode failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/** Label which physical body this node is ("desk", "home", "kitchen"). */
export async function setBodyName(bodyName: string): Promise<DevicesState> {
  const res = await fetch(`${API_BASE}/api/devices/body-name`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body_name: bodyName }),
  })
  if (!res.ok) throw new Error(`Body name failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/** Store (or clear — empty string) the peer token for the canonical host. */
export async function setDevicePeerToken(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/devices/peer-token`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) throw new Error(`Peer token failed: ${res.status} ${await res.text()}`)
}

export interface WolToggleRequest {
  enabled: boolean
  mac?: string | null
  broadcast?: string | null
}

/** Toggle Wake-on-LAN for a device (LAN-only, off by default). */
export async function toggleDeviceWol(
  nodeId: string, req: WolToggleRequest,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/devices/${encodeURIComponent(nodeId)}/wol`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`WoL toggle failed: ${res.status}`)
}

export interface DiscoverResult {
  status: 'discovered' | 'unreachable' | 'no-endpoint' | 'no-token'
  node_id: string
  tools?: number
  capabilities: string[]
}

/** Live capability discovery against the device's MCP server. */
export async function discoverCapabilities(
  nodeId: string, token?: string,
): Promise<DiscoverResult> {
  const res = await fetch(
    `${API_BASE}/api/devices/${encodeURIComponent(nodeId)}/discover`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(token ? { token } : {}),
    },
  )
  if (!res.ok) throw new Error(`Discovery failed: ${res.status}`)
  return res.json()
}

/** Remove a device: revoke (audit-retained) by default, or erase the
 *  record entirely with forget ("Permanently Forget"). */
export async function removeDevice(nodeId: string, forget = false): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/devices/${encodeURIComponent(nodeId)}${forget ? '?forget=true' : ''}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(`Remove failed: ${res.status}`)
}
