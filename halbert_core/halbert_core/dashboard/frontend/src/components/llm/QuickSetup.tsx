// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Terminal, Zap } from 'lucide-react'
import { Button } from '@/components/prep-primitives/Button'
import { apiUrl } from '@/lib/apiBase'

/** Shape of GET /api/settings/model/status. */
export interface ModelStatusResponse {
  chat: {
    configured: boolean
    model: string
    endpoint_url: string
    provider: string
    reachable: boolean
    model_available: boolean
  }
  local_ollama: { reachable: boolean; url: string; model_count: number }
  hardware: { tier: number; total_vram_gb: number | null }
}

/**
 * First-run helper, shown only while no chat model is configured.
 *
 * Auto-discovery finds a running engine and the drawer can add one by hand,
 * but neither tells a first-time user which of the models they already have is
 * a sensible choice, or what to do when nothing is running at all. This is the
 * one screen that answers both, and it disappears the moment it is no longer
 * needed.
 *
 * Ported from the parallel picker implementation, which is the only place
 * either implementation grew a fresh-install flow.
 */
export function QuickSetup({ onApplied }: { onApplied: () => void | Promise<void> }) {
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetch(apiUrl('/api/settings/model/status'))
      setStatus(r.ok ? ((await r.json()) as ModelStatusResponse) : null)
    } catch {
      setStatus(null)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const apply = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const r = await fetch(apiUrl('/api/settings/model/apply-recommended'), { method: 'POST' })
      const data = (await r.json()) as { success?: boolean; message?: string }
      setMessage(data.message ?? null)
      if (data.success) await onApplied()
    } catch {
      setMessage('Could not apply hardware defaults.')
    } finally {
      setBusy(false)
    }
  }

  const runInTerminal = () =>
    window.dispatchEvent(new CustomEvent('halbert:run-command', { detail: { command: 'ollama serve' } }))

  if (!status) return null
  const ollama = status.local_ollama
  const row = 'flex items-center justify-between gap-4 flex-wrap'

  return (
    <div className="rounded-lg border border-border bg-muted p-4 space-y-3" data-testid="quick-setup">
      {ollama.reachable && ollama.model_count > 0 && (
        <div className={row}>
          <p className="text-sm text-foreground">
            Local Ollama detected with {ollama.model_count} {ollama.model_count === 1 ? 'model' : 'models'}.
          </p>
          <Button size="sm" onClick={() => void apply()} loading={busy}>
            <Zap className="w-3.5 h-3.5" />
            Use the largest model that fits my hardware
          </Button>
        </div>
      )}
      {ollama.reachable && ollama.model_count === 0 && (
        <div className={row}>
          <p className="text-sm text-foreground">Local Ollama is running but has no models yet. Pull one, then refresh.</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </Button>
        </div>
      )}
      {!ollama.reachable && (
        <div className={row}>
          <p className="text-sm text-foreground">
            No LLM endpoint is reachable. Start Ollama with{' '}
            <code className="bg-background px-1 rounded font-mono text-xs">ollama serve</code> or add an endpoint below.
          </p>
          <Button size="sm" variant="outline" onClick={runInTerminal}>
            <Terminal className="w-3.5 h-3.5" />
            Run in terminal
          </Button>
        </div>
      )}
      {message && <p className="text-xs text-muted-foreground">{message}</p>}
    </div>
  )
}
