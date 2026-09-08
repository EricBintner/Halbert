// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * MCP Page - Model Context Protocol server management (B5).
 *
 * Lists configured MCP servers with their health, tool counts, and B3
 * risk classification. The owner can add a server (stdio or http), remove
 * one, and set per-server / per-tool risk overrides. Every edit lands
 * through the backend write path (loader-validated, round-trip-gated,
 * atomic replace), which refuses to introduce a literal token — the UI
 * carries an env var NAME (token_env), never a token value.
 *
 * Capability-gated: when CAP_MCP_CLIENT is off the page renders an honest
 * "MCP is off" empty state (the same shape the status endpoint serves),
 * not an error.
 */

import { useEffect, useState, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/domain'
import {
  Plug,
  Loader2,
  Plus,
  Trash2,
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
} from 'lucide-react'

interface McpServer {
  name: string
  transport: string | null
  configured: boolean
  connected: boolean
  health: string
  last_error: string
  tool_count: number | null
  reconnect_attempts: number
  backoff_seconds: number | null
  next_retry_in: number | null
  risk_override: string | null
  tool_risk: Record<string, string>
}

interface McpStatus {
  enabled: boolean
  monitor_running: boolean
  default_risk: string
  servers: McpServer[]
  skipped_servers: string[]
  load_error: string
}

const RISK_LEVELS = ['safe', 'low', 'medium', 'high', 'critical'] as const

function HealthIcon({ health }: { health: string }) {
  if (health === 'healthy' || health === 'connected') {
    return <CheckCircle className="h-4 w-4 text-success" />
  }
  if (health === 'down' || health === 'disconnected' || health === 'error') {
    return <XCircle className="h-4 w-4 text-error" />
  }
  if (health === 'reconnecting' || health === 'degraded') {
    return <AlertTriangle className="h-4 w-4 text-warning" />
  }
  return <AlertTriangle className="h-4 w-4 text-muted-foreground" />
}

function riskTone(level: string | null): string {
  switch (level) {
    case 'critical': return 'text-error'
    case 'high': return 'text-warning'
    case 'safe': return 'text-success'
    default: return 'text-muted-foreground'
  }
}

export function MCP() {
  const [status, setStatus] = useState<McpStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await api.getMcpStatus()
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const refresh = useCallback(async () => {
    setBusy(true)
    try { await load() } finally { setBusy(false) }
  }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (status && !status.enabled) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={<Plug className="h-8 w-8" />}
          title="MCP"
          description="Model Context Protocol servers"
          hideScanButton
        />
        <Card>
          <CardContent className="p-8 text-center">
            <Plug className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">MCP is off</h3>
            <p className="text-muted-foreground">
              The MCP client capability is disabled. Enable it in being.yml
              (capabilities: mcp_client: true) to manage MCP servers.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Plug className="h-8 w-8" />}
        title="MCP"
        description="Model Context Protocol servers — extend Halbert with external tools"
        scanning={busy}
        onScan={refresh}
        scanText="Refresh"
        actions={
          <Button variant="outline" onClick={() => setShowAdd(s => !s)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Server
          </Button>
        }
      />

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-error flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" />
            {error}
          </CardContent>
        </Card>
      )}

      {status?.load_error && (
        <Card>
          <CardContent className="p-4 text-sm text-warning flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {status.load_error}
          </CardContent>
        </Card>
      )}

      {showAdd && (
        <AddServerForm
          onDone={(ok) => { setShowAdd(false); if (ok) refresh() }}
        />
      )}

      {status && status.servers.length === 0 && !showAdd && (
        <Card>
          <CardContent className="p-8 text-center">
            <Plug className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No MCP Servers</h3>
            <p className="text-muted-foreground mb-4">
              Add an MCP server to extend Halbert with external tools.
              Servers can be stdio (a local process) or http (a remote endpoint).
            </p>
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Add Server
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {status?.servers.map((srv) => (
          <ServerCard key={srv.name} server={srv} onChanged={refresh} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Server card — health, tools, risk overrides, remove
// ---------------------------------------------------------------------------

function ServerCard({
  server,
  onChanged,
}: {
  server: McpServer
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [override, setOverride] = useState<string>(
    server.risk_override ?? '',
  )

  const saveRisk = useCallback(async () => {
    setBusy(true); setErr(null)
    try {
      await api.setMcpRisk(server.name, {
        risk_override: override || null,
        tool_risk: null,
      })
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }, [server.name, override, onChanged])

  const remove = useCallback(async () => {
    if (!confirm(`Remove MCP server "${server.name}"?`)) return
    setBusy(true); setErr(null)
    try {
      await api.removeMcpServer(server.name)
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }, [server.name, onChanged])

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <HealthIcon health={server.health} />
            <div className="min-w-0">
              <h3 className="font-medium flex items-center gap-2">
                {server.name}
                {server.transport && (
                  <Badge variant="outline">{server.transport}</Badge>
                )}
                {!server.configured && (
                  <Badge variant="outline" className="text-muted-foreground">
                    unconfigured
                  </Badge>
                )}
              </h3>
              <div className="text-sm text-muted-foreground mt-1 space-y-0.5">
                <div className="flex items-center gap-3">
                  <span>
                    Health: <span className="capitalize">{server.health}</span>
                  </span>
                  {server.tool_count != null && (
                    <span>Tools: {server.tool_count}</span>
                  )}
                  {server.connected && (
                    <span className="text-success">connected</span>
                  )}
                  {server.reconnect_attempts > 0 && (
                    <span className="text-warning">
                      reconnects: {server.reconnect_attempts}
                      {server.next_retry_in != null && ` (retry in ${Math.round(server.next_retry_in)}s)`}
                    </span>
                  )}
                </div>
                {server.last_error && (
                  <div className="text-error truncate">{server.last_error}</div>
                )}
              </div>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={remove} disabled={busy}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>

        {/* Risk override */}
        <div className="mt-3 pt-3 border-t flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Risk override</Label>
            <select
              className="border rounded px-2 py-1 text-sm bg-background"
              value={override}
              onChange={(e) => setOverride(e.target.value)}
              disabled={busy}
            >
              <option value="">default ({server.risk_override ? 'override off' : 'medium'})</option>
              {RISK_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <Button variant="outline" size="sm" onClick={saveRisk} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
          </Button>
          {server.risk_override && (
            <Badge variant="outline" className={riskTone(server.risk_override)}>
              {server.risk_override}
            </Badge>
          )}
        </div>

        {/* Per-tool risk overrides */}
        {Object.keys(server.tool_risk).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(server.tool_risk).map(([tool, level]) => (
              <Badge key={tool} variant="outline" className={riskTone(level)}>
                {tool}: {level}
              </Badge>
            ))}
          </div>
        )}

        {err && (
          <div className="mt-2 text-sm text-error">{err}</div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Add server form
// ---------------------------------------------------------------------------

function AddServerForm({ onDone }: { onDone: (ok: boolean) => void }) {
  const [transport, setTransport] = useState<'stdio' | 'http'>('stdio')
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [url, setUrl] = useState('')
  const [tokenEnv, setTokenEnv] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = useCallback(async () => {
    if (!name.trim()) { setErr('Name is required'); return }
    setBusy(true); setErr(null)
    const entry: Record<string, unknown> = {
      name: name.trim(),
      transport,
    }
    if (transport === 'stdio') {
      if (!command.trim()) { setErr('Command is required for stdio'); setBusy(false); return }
      entry.command = command.trim()
      if (args.trim()) {
        entry.args = args.trim().split(/\s+/)
      }
    } else {
      if (!url.trim()) { setErr('URL is required for http'); setBusy(false); return }
      entry.url = url.trim()
      if (tokenEnv.trim()) {
        entry.auth = { type: 'bearer', token_env: tokenEnv.trim() }
      }
    }
    try {
      await api.addMcpServer(entry)
      onDone(true)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }, [name, transport, command, args, url, tokenEnv, onDone])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add MCP Server</CardTitle>
        <CardDescription>
          Configure a new MCP server. For http auth, provide an environment
          variable NAME (token_env) — never a token value.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="mcp-name">Name</Label>
            <Input id="mcp-name" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="filesystem" disabled={busy} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mcp-transport">Transport</Label>
            <select id="mcp-transport"
              className="w-full border rounded px-2 py-2 text-sm bg-background"
              value={transport}
              onChange={(e) => setTransport(e.target.value as 'stdio' | 'http')}
              disabled={busy}
            >
              <option value="stdio">stdio (local process)</option>
              <option value="http">http (remote endpoint)</option>
            </select>
          </div>
        </div>

        {transport === 'stdio' ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="mcp-command">Command</Label>
              <Input id="mcp-command" value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="npx" disabled={busy} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mcp-args">Args (space-separated)</Label>
              <Input id="mcp-args" value={args}
                onChange={(e) => setArgs(e.target.value)}
                placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
                disabled={busy} />
            </div>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="mcp-url">URL</Label>
              <Input id="mcp-url" value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://mcp.linear.app/mcp" disabled={busy} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mcp-token-env">Token env var name</Label>
              <Input id="mcp-token-env" value={tokenEnv}
                onChange={(e) => setTokenEnv(e.target.value)}
                placeholder="LINEAR_MCP_TOKEN" disabled={busy} />
            </div>
          </div>
        )}

        {err && <div className="text-sm text-error">{err}</div>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onDone(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Add Server
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
