// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  TrustBoundaryTelemetryBar,
  Tier1RockerControl,
  Tier2StateCard,
  EscapeHatchConfirmationModal,
  MachinedTagInput,
  type TelemetryCounts,
} from '@/components/domain'
import { apiUrl } from '@/lib/apiBase'
import { SlidersHorizontal, Shield, AlertTriangle, FileCode } from 'lucide-react'

const API_BASE = apiUrl('/api')

// ─────────────────────────────────────────────────────────────────────────────
// Security Settings (MCP Trust Boundary)
// ─────────────────────────────────────────────────────────────────────────────

export function SecurityTab() {
  const [config, setConfig] = useState<any>(null)
  const [telemetry, setTelemetry] = useState<TelemetryCounts | null>(null)
  const [loading, setLoading] = useState(true)
  const [telemetryLoading, setTelemetryLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [showEscapeModal, setShowEscapeModal] = useState(false)

  useEffect(() => {
    loadConfig()
    loadTelemetry()
    // Poll every 30s to check TTL expiry and refresh telemetry
    const poll = setInterval(() => {
      loadConfig()
      loadTelemetry()
    }, 30000)
    return () => clearInterval(poll)
  }, [])

  const loadConfig = async () => {
    try {
      const resp = await fetch(`${API_BASE}/settings/being`)
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
      } else {
        // Fail closed: a stale poll must not keep showing an unlocked
        // state after the server has relocked (TTL expiry, relock from
        // another client). Drop the config so the controls disappear.
        setConfig(null)
      }
    } catch (e) {
      console.error('Failed to load security config:', e)
      setConfig(null)
    } finally {
      setLoading(false)
    }
  }

  const loadTelemetry = async () => {
    setTelemetryLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/settings/security/telemetry`)
      if (resp.ok) {
        const data = await resp.json()
        setTelemetry(data)
      } else {
        console.error('Telemetry endpoint returned', resp.status)
      }
    } catch (e) {
      console.error('Failed to load security telemetry:', e)
    } finally {
      setTelemetryLoading(false)
    }
  }

  const saveSecurity = async (updates: Record<string, any>) => {
    setSaving(true)
    try {
      const resp = await fetch(`${API_BASE}/settings/being`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ security: { ...config?.security, ...updates } }),
      })
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
        setToast('Saved')
        setTimeout(() => setToast(null), 2000)
        await loadTelemetry()
      } else {
        const err = await resp.json()
        setToast(`Error: ${err.detail || 'Failed to save'}`)
        setTimeout(() => setToast(null), 3000)
      }
    } catch (e) {
      setToast('Error: Network failure')
      setTimeout(() => setToast(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Loading security config...</CardContent></Card>
  }

  if (!config) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Failed to load config</CardContent></Card>
  }

  const sec = config.security || {
    operational_tier: 'cloud_ok',
    secret_tier: 'local_only',
    public_files: ['/etc/hosts', '/etc/hostname', '/etc/fstab'],
    extra_secret_keys: [],
    cloud_ok_keys: [],
  }

  const locked = sec.secret_tier === 'local_only'

  return (
    <div className="space-y-4">
      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg border bg-background px-4 py-2 text-sm shadow-lg">
          {toast}
        </div>
      )}

      {/* Telemetry Scope Instrument */}
      <TrustBoundaryTelemetryBar counts={telemetry} loading={telemetryLoading} />

      {/* Tier 1 — Operational Values */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            Tier 1 — Operational Values
          </CardTitle>
          <CardDescription>
            Machine context, open ports, firewall rules, and internal IP addresses.
            Choose how cloud models may access them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tier1RockerControl
            value={sec.operational_tier}
            onChange={(v) => saveSecurity({ operational_tier: v })}
            disabled={saving}
            count={telemetry?.tier_1}
          />
        </CardContent>
      </Card>

      {/* Tier 2 — Secrets (dual-state vault) */}
      <Tier2StateCard
        locked={locked}
        onUnlock={() => setShowEscapeModal(true)}
        onRelock={() => saveSecurity({ secret_tier: 'local_only', secret_tier_expiry: null, volatile_unlock: false })}
        disabled={saving}
        protectedCount={telemetry?.tier_2}
        expiry={sec.secret_tier_expiry}
      />

      {/* Per-Key Cloud Escape Hatch */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Per-Key Cloud Escape Hatch
            {telemetry && telemetry.cloud_ok_keys_count > 0 && (
              <span className="font-mono text-xs text-status-warning">
                ({telemetry.cloud_ok_keys_count} Active)
              </span>
            )}
          </CardTitle>
          <CardDescription>
            Allow specific non-critical keys to bypass Tier 2 without unlocking all secrets.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border border-status-warning-line bg-status-warning-bg p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-status-warning mt-0.5 shrink-0" />
              <p className="text-sm">
                Keys listed here bypass the Tier 2 boundary. Their raw values
                will appear in your cloud LLM vendor's inference logs. Only
                list keys whose values you are willing to expose.
              </p>
            </div>
          </div>
          <MachinedTagInput
            values={sec.cloud_ok_keys || []}
            onChange={(vals) => saveSecurity({ cloud_ok_keys: vals })}
            placeholder="Add key name (e.g. WEATHER_API_KEY)"
            disabled={saving}
            addLabel="Add Exception"
          />
        </CardContent>
      </Card>

      {/* File & Key Classification */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode className="h-5 w-5" />
            File &amp; Key Classification
          </CardTitle>
          <CardDescription>
            Override the default tier assignments for specific files and keys.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Public Files */}
          <div className="space-y-2">
            <Label className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Public Files (Tier 0 Floor)
            </Label>
            <p className="text-xs text-muted-foreground">
              Host paths whose structure is Tier 0. A value from one of these
              files is Tier 0 only if its content does not contain a secret.
            </p>
            <MachinedTagInput
              values={sec.public_files || []}
              onChange={(vals) => saveSecurity({ public_files: vals })}
              placeholder="Add file path (e.g. /etc/hosts)"
              disabled={saving}
              addLabel="Add Path"
            />
          </div>

          {/* Extra Secret Keys */}
          <div className="space-y-2">
            <Label className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Extra Secret Keys (Tier 2 Enforcement)
            </Label>
            <p className="text-xs text-muted-foreground">
              Additional config key names to treat as Tier 2, beyond the built-in
              list (password, token, api_key, secret, etc).
            </p>
            <MachinedTagInput
              values={sec.extra_secret_keys || []}
              onChange={(vals) => saveSecurity({ extra_secret_keys: vals })}
              placeholder="Add key name (e.g. serial)"
              disabled={saving}
              addLabel="Add Key"
            />
          </div>
        </CardContent>
      </Card>

      {/* Escape Hatch Confirmation Modal */}
      <EscapeHatchConfirmationModal
        open={showEscapeModal}
        onClose={() => setShowEscapeModal(false)}
        onConfirm={(ttl, phrase) => {
          const updates: Record<string, any> = {
            secret_tier: 'cloud_ok_acknowledged',
            // The backend re-verifies this phrase — the modal's check is UX
            // friction, not the enforcement boundary.
            phrase,
          }
          if (ttl === '1h') {
            const expiry = new Date(Date.now() + 3600_000)
            updates.secret_tier_expiry = expiry.toISOString()
            updates.volatile_unlock = false
          } else if (ttl === 'restart') {
            updates.volatile_unlock = true
            updates.secret_tier_expiry = null
          } else {
            updates.secret_tier_expiry = null
            updates.volatile_unlock = false
          }
          saveSecurity(updates)
          setShowEscapeModal(false)
        }}
        disabled={saving}
      />
    </div>
  )
}