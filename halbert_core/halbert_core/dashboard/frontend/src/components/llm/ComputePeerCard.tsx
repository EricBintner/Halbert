// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The compute-peer settings card — the AI tab's whole surface on a
 * home variant (home automation simplification S3 / W15).
 *
 * An HA node runs no model of its own: chat and specialist turns are served
 * by the paired workstation, and the workstation's own model configuration
 * governs which model answers. So this node has no model picker — Settings
 * renders this card instead of <ModelSettings /> — and the card deliberately
 * offers no model selection either. Its whole job is the link:
 *
 *  - the workstation's address (hostname:port or a Tailscale address)
 *  - "Test Connection" — the peer health probe, reusing PeerProvider's
 *    read-only GET /api/compute/v1/models call via POST /compute/peer-probe
 *  - "Use This Peer" — POST /api/peers/compute-peer, which saves one
 *    peer:// endpoint and points both chat_model and specialist_model at it
 *  - a read-only summary of the link, including the model list the
 *    workstation advertises (empty until its models route is implemented —
 *    its configuration still governs)
 *
 * The bearer token from the workstation's pairing is optional here: a
 * re-paired token can be pasted to refresh the stored credential, and an
 * omitted one never clears what the pairing already saved (the backend
 * route guards that).
 */
import { useCallback, useEffect, useState } from 'react'
import { Check, Network, X } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import {
  getComputePeerLink,
  linkComputePeer,
  probeComputePeer,
  type ComputePeerLinkSummary,
  type ComputePeerProbeResult,
} from '@/lib/peerApi'

export function ComputePeerCard() {
  const [link, setLink] = useState<ComputePeerLinkSummary | null>(null)
  const [address, setAddress] = useState('')
  const [token, setToken] = useState('')
  const [testing, setTesting] = useState(false)
  const [linking, setLinking] = useState(false)
  const [probe, setProbe] = useState<ComputePeerProbeResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reloadLink = useCallback(async () => {
    try {
      const current = await getComputePeerLink()
      setLink(current)
      // A saved link pre-fills the field, so "Test Connection" after a
      // restart tests the address that is actually configured.
      if (current) setAddress((prev) => prev.trim() || current.url)
    } catch {
      // The card still works as an entry form; the summary block simply
      // reports nothing rather than failing the whole tab.
      setLink(null)
    }
  }, [])

  useEffect(() => { void reloadLink() }, [reloadLink])

  const handleTest = useCallback(async () => {
    setTesting(true)
    setProbe(null)
    setError(null)
    try {
      setProbe(await probeComputePeer(address.trim(), token.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Peer probe failed')
    } finally {
      setTesting(false)
    }
  }, [address, token])

  const handleLink = useCallback(async () => {
    setLinking(true)
    setProbe(null)
    setError(null)
    try {
      await linkComputePeer(address.trim(), token.trim())
      await reloadLink()
      setError(null)
      setToken('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Linking the compute peer failed')
    } finally {
      setLinking(false)
    }
  }, [address, token, reloadLink])

  const busy = testing || linking
  const canSubmit = address.trim().length > 0 && !busy

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-5 w-5" />
          Compute Peer
        </CardTitle>
        <CardDescription>
          This node runs no model of its own. Language-model work is served by the
          compute peer, and its own model configuration governs which model
          answers — change it there, not here.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* The standing state of the link, read-only: both slots resolving to
            the one peer is the contract, not something to configure here. */}
        {link ? (
          <div className="flex items-start gap-3 rounded-lg border border-success/40 bg-success-muted px-4 py-3">
            <Check className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">
                Linked to <span className="font-mono">{link.url}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                Chat and specialist turns both resolve to this peer
                {link.slots.chat_model && link.slots.specialist_model
                  ? '. '
                  : ' — re-link to refresh the slots. '}
                The compute peer&apos;s own model picker governs which model serves them.
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No compute peer linked yet. Enter the compute peer&apos;s address and
            pair this node with it.
          </p>
        )}

        {error ? (
          <p
            role="alert"
            className="rounded-md border border-error/40 bg-error-muted px-3 py-2 text-sm text-error"
          >
            {error}
          </p>
        ) : null}

        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="compute-peer-address">Compute peer address</Label>
            <Input
              id="compute-peer-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="workstation.local:8000 or a Tailscale address"
              className="font-mono"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Hostname and port of the compute peer&apos;s dashboard — hostname:port,
              peer://host:port, or an http(s):// address all work.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="compute-peer-token">Pairing token (optional)</Label>
            <Input
              id="compute-peer-token"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Bearer token from the compute peer's pairing"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Only needed to store or refresh a re-paired credential; a saved token
              is never cleared by leaving this empty.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => void handleTest()} disabled={!canSubmit}>
              {testing ? 'Testing…' : 'Test Connection'}
            </Button>
            <Button onClick={() => void handleLink()} disabled={!canSubmit}>
              {linking ? 'Linking…' : 'Use This Peer'}
            </Button>
          </div>
        </div>

        {/* The probe's answer, including the read-only model list — never a
            picker. Colour is never the only signal: the icon and the wording
            carry the outcome too. */}
        <div role="status" aria-live="polite" className="min-h-[1rem] text-sm">
          {probe ? (
            <div
              className={cn(
                'flex items-start gap-2 rounded-md border px-3 py-2',
                probe.ok
                  ? 'border-success/40 bg-success-muted text-foreground'
                  : 'border-error/40 bg-error-muted text-error',
              )}
            >
              {probe.ok ? (
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <X className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              <div className="space-y-1">
                <p className="font-medium">
                  {probe.ok ? 'Peer reachable.' : 'Peer unreachable.'} {probe.message}
                </p>
                {probe.ok && probe.models.length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    The compute peer serves:{' '}
                    <span className="font-mono">{probe.models.join(', ')}</span>
                  </p>
                ) : probe.ok ? (
                  <p className="text-xs text-muted-foreground">
                    The compute peer advertises no specific model list — its own
                    configuration governs which model answers.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}