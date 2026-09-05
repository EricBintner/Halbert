// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * This-device identity: body name, entity mode, canonical host — the
 * Settings → Devices page's first card (G12 / P7b, design review §15).
 *
 * Binding decisions implemented here:
 * - Q2: a ConfirmDialog when switching Independent → Singular (not for
 *   the reverse) — the dialog names what changes: shared consciousness,
 *   offline resiliency, reversibility.
 * - Q3: hybrid body-name input — free text with quick-select suggestion
 *   chips, validated as a lowercase slug.
 * - Q5: canonical host as a simple base-URL input, with an Advanced
 *   disclosure for explicit per-service URLs and the masked peer token
 *   (Q4).
 */
import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Collapsible } from '@/components/ui/collapsible'
import { ConfirmDialog, Toast } from '@/components/ui/confirm-dialog'
import { Eye, EyeOff } from 'lucide-react'
import {
  setBodyName as putBodyName,
  setEntityMode,
  setDevicePeerToken,
} from '@/lib/peerApi'
import type { DevicesState } from '@/lib/peerApi'

/** Quick-select body names (design review Q3) — chips fill the input. */
const BODY_NAME_SUGGESTIONS = [
  'workstation', 'desk', 'living room', 'kitchen', 'laptop', 'server rack',
]

const BODY_NAME_SLUG = /^[a-z0-9][a-z0-9-_ ]*$/
const toSlug = (raw: string) =>
  raw.trim().toLowerCase().replace(/[\s]+/g, '-').replace(/[^a-z0-9-_]/g, '')

interface EntityIdentityCardProps {
  state: DevicesState
  onRefresh: () => Promise<void> | void
}

export function EntityIdentityCard({ state, onRefresh }: EntityIdentityCardProps) {
  const [bodyName, setBodyName] = useState(state.body_name)
  const [savingBodyName, setSavingBodyName] = useState(false)
  const [baseUrl, setBaseUrl] = useState(deriveBaseUrl(state))
  const [memoryUrl, setMemoryUrl] = useState(state.canonical_memory_url)
  const [threadUrl, setThreadUrl] = useState(state.canonical_thread_url)
  const [peerToken, setPeerToken] = useState('')
  const [tokenVisible, setTokenVisible] = useState(false)
  const [confirmSingular, setConfirmSingular] = useState(false)
  const [savingMode, setSavingMode] = useState(false)
  const [toast, setToast] = useState<{ open: boolean; message: string; variant: 'success' | 'error' | 'info' }>(
    { open: false, message: '', variant: 'info' },
  )

  const singular = state.entity_mode === 'singular'
  const bodyNameInvalid = bodyName !== '' && !BODY_NAME_SLUG.test(bodyName)

  const showToast = (message: string, variant: 'success' | 'error' | 'info' = 'info') =>
    setToast({ open: true, message, variant })

  const saveBodyName = async () => {
    const slug = toSlug(bodyName)
    if (!slug) return
    setSavingBodyName(true)
    try {
      await putBodyName(slug)
      setBodyName(slug)
      await onRefresh()
      showToast('Body name saved', 'success')
    } catch (e) {
      showToast(`Could not save body name: ${String(e)}`, 'error')
    } finally {
      setSavingBodyName(false)
    }
  }

  const applyMode = async (mode: 'singular' | 'independent') => {
    setSavingMode(true)
    try {
      const explicit = memoryUrl && threadUrl
      await setEntityMode({
        mode,
        ...(mode === 'singular'
          ? explicit
            ? { memory_url: memoryUrl, thread_url: threadUrl }
            : { base_url: baseUrl }
          : {}),
      })
      await onRefresh()
      showToast(
        mode === 'singular'
          ? 'This body now shares the canonical host\'s memory and conversations'
          : 'This body now keeps its own memory and conversations',
        'success',
      )
    } catch (e) {
      // Optimistic rollback: onRefresh() restores the server's truth.
      await onRefresh()
      showToast(`Could not switch entity mode: ${String(e)}`, 'error')
    } finally {
      setSavingMode(false)
    }
  }

  const savePeerToken = async () => {
    try {
      await setDevicePeerToken(peerToken.trim())
      setPeerToken('')
      showToast(peerToken.trim() ? 'Peer token stored' : 'Peer token cleared', 'success')
    } catch (e) {
      showToast(`Could not store peer token: ${String(e)}`, 'error')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">This Body</CardTitle>
        <CardDescription>
          Which body Halbert is speaking from here, and whether this body
          shares the one autobiography or keeps its own.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Body name (Q3: hybrid input with suggestion chips) */}
        <div className="space-y-2">
          <Label htmlFor="body-name">Body Name</Label>
          <div className="flex gap-2">
            <Input
              id="body-name"
              value={bodyName}
              onChange={(e) => setBodyName(e.target.value)}
              placeholder="desk"
              aria-invalid={bodyNameInvalid}
            />
            <Button
              variant="outline" size="sm"
              onClick={saveBodyName}
              disabled={savingBodyName || !toSlug(bodyName) || bodyNameInvalid}
            >
              {savingBodyName ? 'Saving…' : 'Save'}
            </Button>
          </div>
          {bodyNameInvalid && (
            <p className="text-xs text-destructive" role="alert">
              Lowercase letters, digits, dashes and spaces only.
            </p>
          )}
          <div className="flex flex-wrap gap-1.5 pt-1" aria-label="Suggested body names">
            {BODY_NAME_SUGGESTIONS.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setBodyName(name)}
                className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground
                           hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        {/* Entity mode (Q2: radio pair; confirmation on the singular switch) */}
        <fieldset className="space-y-2" aria-label="Entity mode">
          <legend className="text-sm font-medium">Entity Mode</legend>
          <div className="grid gap-2">
            <button
              type="button"
              role="radio"
              aria-checked={singular}
              disabled={savingMode}
              onClick={() => !singular && setConfirmSingular(true)}
              className={`rounded-lg border p-3 text-left transition-colors
                          ${singular ? 'border-primary bg-primary/5' : 'hover:bg-accent'}`}
            >
              <span className="text-sm font-medium">Singular Entity</span>
              <span className="block text-xs text-muted-foreground pt-0.5">
                Shares consciousness, memory and conversations with the
                canonical host — one Halbert, many bodies.
              </span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={!singular}
              disabled={savingMode}
              onClick={() => singular && applyMode('independent')}
              className={`rounded-lg border p-3 text-left transition-colors
                          ${!singular ? 'border-primary bg-primary/5' : 'hover:bg-accent'}`}
            >
              {/* "Independent Node" is the ratified name for this MODE, and
                  DECISIONS.md 2026-09-01 sets the UI strings literally:
                  "Singular Entity / Independent Node / Linked Devices". It
                  was briefly changed to "Independent Body" on the reasoning
                  that §terminology lists `node` under avoid -- but that cell
                  is in the "Physical device" row, and bans node as the noun
                  for a machine. It does not rename a mode. The sibling
                  surface, PresencePill, never stopped saying "Independent
                  Node", so the change left the product contradicting itself
                  on two mounted screens. */}
              <span className="text-sm font-medium">Independent Node</span>
              <span className="block text-xs text-muted-foreground pt-0.5">
                This body keeps its own memory and conversations.
              </span>
            </button>
          </div>
        </fieldset>

        {/* Canonical host — always visible: the base URL is needed BEFORE
            the independent → singular switch (its PUT carries base_url),
            so hiding it until singular is active would be circular. */}
        <div className="space-y-2">
          <Label htmlFor="canonical-base">Canonical Host Base URL</Label>
          <Input
            id="canonical-base"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://n150.lan:8001"
          />
          {singular && (
            <Button
              variant="outline" size="sm"
              disabled={savingMode || !baseUrl}
              onClick={() => applyMode('singular')}
            >
              {savingMode ? 'Saving…' : 'Update Canonical Host'}
            </Button>
          )}
        </div>

        {/* Advanced disclosure (Q5 + Q4): explicit URLs + masked peer token */}
        <Collapsible
          title="Advanced (Explicit Endpoints & Peer Token)"
          defaultOpen={false}
        >
          <div className="space-y-3 pt-1">
            <div className="grid gap-2">
              <Label htmlFor="memory-url">Canonical memory URL</Label>
              <Input
                id="memory-url"
                value={memoryUrl}
                onChange={(e) => setMemoryUrl(e.target.value)}
                placeholder="http://n150.lan:8001/api/memory"
              />
              <Label htmlFor="thread-url">Canonical thread URL</Label>
              <Input
                id="thread-url"
                value={threadUrl}
                onChange={(e) => setThreadUrl(e.target.value)}
                placeholder="http://n150.lan:8001/api/conversations"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="peer-token">Bearer Token / Peer Secret</Label>
              <div className="flex gap-2">
                <Input
                  id="peer-token"
                  type={tokenVisible ? 'text' : 'password'}
                  value={peerToken}
                  onChange={(e) => setPeerToken(e.target.value)}
                  placeholder="Stored during pairing — enter to rotate"
                />
                <Button
                  variant="ghost" size="sm"
                  aria-label={tokenVisible ? 'Hide token' : 'Show token'}
                  onClick={() => setTokenVisible(!tokenVisible)}
                >
                  {tokenVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button variant="outline" size="sm" onClick={savePeerToken}>
                  Save
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                The credential this body presents to the canonical host.
                Normally captured during pairing; this is the manual path
                for rotation or headless setup.
              </p>
            </div>
          </div>
        </Collapsible>
      </CardContent>

      <ConfirmDialog
        open={confirmSingular}
        onClose={() => setConfirmSingular(false)}
        onConfirm={() => {
          setConfirmSingular(false)
          applyMode('singular')
        }}
        title="Join the canonical host?"
        description="This body will share its memory and conversations with the canonical host: one Halbert, many bodies."
        warning="If the canonical host is unreachable, this body falls back to its own local memory until it returns. You can revert to Independent at any time."
        confirmText="Share Consciousness"
      />
      <Toast
        open={toast.open}
        onClose={() => setToast({ ...toast, open: false })}
        message={toast.message}
        variant={toast.variant}
      />
    </Card>
  )
}

/** Best-effort base URL from the canonical memory URL (strip /api/memory). */
function deriveBaseUrl(state: DevicesState): string {
  return state.canonical_memory_url.replace(/\/api\/memory\/?$/, '')
}