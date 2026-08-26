// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * System / governance helpers for the dashboard.
 *
 * Named `tauri` historically (the desktop shell is a Tauri wrapper), but
 * these are plain HTTP calls to the FastAPI backend — there is no Tauri
 * IPC dependency.
 *
 * Reconstructed 2026-08-22 (original src/lib/ was never committed).
 */

import { apiBase } from './apiBase'

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`API ${options.method ?? 'GET'} ${path} failed (${res.status}): ${detail}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------
// System info / metrics
// ---------------------------------------------------------------------

export interface SystemInfo {
  hostname: string
  os_name: string
  os_version: string
  kernel_version: string
  cpu_count: number
  total_memory_mb: number
}

export async function getSystemInfo(): Promise<SystemInfo> {
  const data = await request('/api/settings/system-profile')
  // Handle both {status: "loaded", profile: {...}} and bare profile shapes
  const p = data.profile ?? (data.os ? data : {})
  const os = p.os ?? {}
  const distro = os.distro ?? {}
  const hw = p.hardware ?? {}
  const cpu = hw.cpu ?? {}
  const mem = hw.memory ?? {}
  return {
    hostname: p.hostname ?? '',
    os_name: p.os_name ?? distro.name ?? distro.productname ?? '',
    os_version: p.os_version ?? distro.version_id ?? distro.productversion ?? '',
    kernel_version: p.kernel_version ?? os.kernel ?? p.kernel ?? '',
    cpu_count: p.cpu_count ?? parseInt(cpu['cpu(s)'] ?? '0', 10) ?? 0,
    total_memory_mb: p.total_memory_mb ?? Math.round((mem.total_gb ?? 0) * 1024),
  }
}

export interface DiskMetrics {
  mount_point: string
  fs_type: string
  total_gb: number
  used_gb: number
  available_gb: number
  usage_percent: number
}

export interface SystemMetrics {
  cpu_percent: number
  memory_percent: number
  memory_total_gb: number
  memory_available_gb: number
  memory_used_gb: number
  uptime_seconds: number
  disks: DiskMetrics[]
}

export function getSystemMetrics(): Promise<SystemMetrics> {
  return request('/api/settings/metrics')
}

// ---------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------

export interface ApprovalRequest {
  id: string
  task: string
  action: string
  reasoning?: string
  risk_level?: string
  system_state?: string
  affected_resources?: string[]
  simulation_result?: any
  rule_conflict?: {
    conflicting_rule: string
    rule_category: string
    rule_priority: string | number
  }
  status?: string
  confidence: number
  requested_at: string
  approved_at?: string
  rejected_at?: string
  rejection_reason?: string
}

export interface ApprovalHistoryItem {
  id?: string
  request_id?: string
  task?: string
  action?: string
  approved?: boolean
  reason?: string
  status?: string
  reasoning?: string
  risk_level?: string
  decided_by?: string
  decided_at: string
  requested_at?: string
  approved_at?: string
  rejected_at?: string
  rejection_reason?: string
}

export interface PendingApprovalsResponse {
  pending: ApprovalRequest[]
  count?: number
  blocked_by_rules: number
}

export function getPendingApprovals(): Promise<PendingApprovalsResponse> {
  return request('/api/settings/approvals/pending')
}

export function approveRequest(requestId: string, saveToMemory = false) {
  return request(`/api/approvals/${encodeURIComponent(requestId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved: true, reason: null, save_to_memory: saveToMemory }),
  })
}

export function rejectRequest(requestId: string, reason?: string, saveToMemory = false) {
  return request(`/api/approvals/${encodeURIComponent(requestId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ approved: false, reason: reason ?? null, save_to_memory: saveToMemory }),
  })
}

export async function getApprovalHistory(limit = 100, approvedOnly = false): Promise<ApprovalHistoryItem[]> {
  const data = await request(`/api/settings/approvals/history?limit=${limit}&approved_only=${approvedOnly}`)
  return data.history ?? []
}

// ---------------------------------------------------------------------
// Jobs / scheduler / guardrails
// ---------------------------------------------------------------------

export interface ScheduledJob {
  id: string
  name?: string
  task?: string
  trigger?: string
  schedule?: string
  state?: string
  priority?: number
  created_at?: string
  started_at?: string
  completed_at?: string
  error?: string
  retries?: number
  max_retries?: number
  next_run?: string
}

export interface SchedulerStatus {
  running: boolean
  scheduled_jobs?: number
  pending_jobs?: number
  completed_jobs?: number
  failed_jobs?: number
  max_workers?: number
  guardrails_enabled?: boolean
  safe_mode_active?: boolean
  reason?: string
}

export interface GuardrailsStatus {
  status: string
  safe_mode_active?: boolean
  config?: Record<string, any>
  error?: string
}

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  const data = await request('/api/settings/scheduler/status')
  return data.scheduler ?? { running: false, reason: data.error }
}

export async function getScheduledJobs(): Promise<ScheduledJob[]> {
  const data = await request('/api/settings/scheduler/jobs')
  return data.jobs ?? []
}

export function cancelScheduledJob(jobId: string) {
  return request(`/api/settings/scheduler/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export function getGuardrailsStatus(): Promise<GuardrailsStatus> {
  return request('/api/settings/guardrails/status')
}

export function exitSafeMode() {
  return request('/api/settings/guardrails/safe-mode/exit', { method: 'POST' })
}
