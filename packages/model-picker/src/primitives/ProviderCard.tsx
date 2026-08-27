// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import { providerDescriptor } from '../types'
import type {
  LocalDiscovery,
  LocalEngine,
  ProviderId,
  SavedEndpoint,
} from '../types'
import type { UseModelPickerResult } from '../useModelPicker'

export interface ProviderCardProps extends HTMLAttributes<HTMLDivElement> {
  picker: UseModelPickerResult
  /** Existing endpoint, or undefined when offering a provider to add. */
  endpoint?: SavedEndpoint
  /** Used when `endpoint` is undefined. */
  provider?: ProviderId
  /**
   * Slot beside the card title, for a host's own badge. The package renders
   * no privacy badge of its own because only the host knows what its runtime
   * actually does with a configured endpoint.
   */
  renderBadge?: (
    endpoint: SavedEndpoint | undefined,
    provider: ProviderId,
  ) => ReactNode
  /**
   * Fires only once the hook reports no error for the write, so a save that
   * never reached storage cannot be announced as one that did. An endpoint
   * that stores but then cannot be listed also reports as a failure.
   */
  onSaved?: (endpoint: SavedEndpoint) => void
  /** Fires only once the hook reports no error for the removal. */
  onDeleted?: (endpointId: string) => void
}

/** A write that has settled but whose outcome the hook has not yet reported. */
type CompletedWrite =
  | { kind: 'save'; endpoint: SavedEndpoint }
  | { kind: 'delete'; endpointId: string }

/**
 * FNV-1a over provider and url. A derived id makes adding the same endpoint
 * twice an overwrite instead of a duplicate, which a clock- or random-based id
 * cannot promise.
 */
function shortHash(input: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(36).padStart(7, '0')
}

function localEngine(
  discovery: LocalDiscovery | null,
  provider: ProviderId,
): LocalEngine | null {
  if (!discovery) return null
  if (provider === 'ollama') return discovery.ollama
  if (provider === 'lm-studio') return discovery.lmStudio
  return null
}

/**
 * One connected provider: a local engine's live status, or a cloud credential.
 *
 * The fields are a draft rather than a mirror of `endpoint`, so hosts should
 * key this by endpoint id when the list can be reordered or replaced.
 */
export function ProviderCard({
  picker,
  endpoint,
  provider,
  renderBadge,
  onSaved,
  onDeleted,
  ...rest
}: ProviderCardProps) {
  const providerId = endpoint?.provider ?? provider
  const descriptor = providerId ? providerDescriptor(providerId) : undefined

  const [name, setName] = useState(endpoint?.name ?? descriptor?.label ?? '')
  const [url, setUrl] = useState(
    endpoint?.url ?? descriptor?.defaultUrl ?? '',
  )
  const [apiKey, setApiKey] = useState(endpoint?.apiKey ?? '')
  const [revealed, setRevealed] = useState(false)
  const [armed, setArmed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [written, setWritten] = useState<CompletedWrite | null>(null)

  // The hook swallows a failed write and resolves anyway, reporting through
  // `error` on the render that follows — so the host's success callback waits
  // for that render rather than firing on a write that never landed.
  useEffect(() => {
    if (!written) return
    setWritten(null)
    if (picker.error) return
    if (written.kind === 'save') onSaved?.(written.endpoint)
    else onDeleted?.(written.endpointId)
  }, [written, picker.error, onSaved, onDeleted])

  // Hooks run first so this guard stays legal; with neither prop there is no
  // provider to describe.
  if (!providerId || !descriptor) return null

  const engine = localEngine(picker.discovery, providerId)
  const chatCapable = picker.isChatCapable(providerId)
  const testResult = endpoint ? picker.testResults[endpoint.id] : undefined
  const testing = endpoint ? picker.testing === endpoint.id : false

  const base = `provider-${(endpoint?.id ?? providerId).replace(/[^a-zA-Z0-9_-]/g, '-')}`
  const titleId = `${base}-title`
  const nameFieldId = `${base}-name`
  const urlFieldId = `${base}-url`
  const keyFieldId = `${base}-key`

  const save = async () => {
    const trimmed = url.trim()
    const next: SavedEndpoint = {
      id: endpoint?.id ?? `ep_${shortHash(`${providerId}:${trimmed}`)}`,
      name: name.trim() || descriptor.label,
      provider: providerId,
      url: trimmed,
      ...(descriptor.needsApiKey && apiKey ? { apiKey } : {}),
    }
    setSaving(true)
    try {
      await picker.saveEndpoint(next)
      setWritten({ kind: 'save', endpoint: next })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!endpoint) return
    if (!armed) {
      setArmed(true)
      return
    }
    setArmed(false)
    await picker.deleteEndpoint(endpoint.id)
    setWritten({ kind: 'delete', endpointId: endpoint.id })
  }

  const notice = armed
    ? 'Removing this endpoint also clears every role pointing at it. Choose confirm to remove.'
    : testResult?.message ?? ''

  return (
    <div
      role="group"
      aria-labelledby={titleId}
      data-provider={providerId}
      data-local={descriptor.isLocal ? 'yes' : 'no'}
      {...rest}
    >
      <span id={titleId}>{endpoint?.name ?? descriptor.label}</span>
      {renderBadge?.(endpoint, providerId)}

      {chatCapable ? null : (
        <span data-badge="not-chat-capable">
          Models here can be listed and tested, but this provider is not
          available for chat in this app.
        </span>
      )}

      <label htmlFor={nameFieldId}>Name</label>
      <input
        id={nameFieldId}
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />

      <label htmlFor={urlFieldId}>Address</label>
      <input
        id={urlFieldId}
        type="url"
        value={url}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => setUrl(event.target.value)}
      />

      {descriptor.isLocal ? (
        <div data-engine={engine?.running ? 'running' : 'stopped'}>
          <span>{engine?.running ? 'Running' : 'Not detected'}</span>
          {engine?.version ? <span>Version {engine.version}</span> : null}
          <span>
            {engine
              ? `${engine.models.length} model${engine.models.length === 1 ? '' : 's'} installed`
              : 'Not scanned yet'}
          </span>
          <button
            type="button"
            onClick={() => void picker.discoverLocal()}
            disabled={picker.discovering}
          >
            {picker.discovering ? 'Scanning…' : 'Rescan'}
          </button>
        </div>
      ) : null}

      {descriptor.needsApiKey ? (
        <>
          <label htmlFor={keyFieldId}>Key</label>
          {/* The value is masked by default and never copied into a title,
              label or status string. */}
          <input
            id={keyFieldId}
            type={revealed ? 'text' : 'password'}
            value={apiKey}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setApiKey(event.target.value)}
          />
          <button
            type="button"
            aria-pressed={revealed}
            aria-controls={keyFieldId}
            aria-label={revealed ? 'Hide the key' : 'Show the key'}
            onClick={() => setRevealed((current) => !current)}
          >
            {revealed ? 'Hide' : 'Show'}
          </button>
        </>
      ) : null}

      <button
        type="button"
        onClick={() => void save()}
        disabled={
          saving ||
          url.trim() === '' ||
          (descriptor.needsApiKey && apiKey.trim() === '')
        }
      >
        {endpoint ? 'Save' : 'Add'}
      </button>

      {descriptor.isLocal ? null : (
        <>
          <button
            type="button"
            onClick={() => void (endpoint && picker.testEndpoint(endpoint.id))}
            disabled={!endpoint || testing}
          >
            {testing ? 'Testing…' : 'Test'}
          </button>
          {endpoint ? null : <span>Add this endpoint before testing it.</span>}
        </>
      )}

      {endpoint ? (
        <>
          <button type="button" onClick={() => void remove()}>
            {armed ? 'Confirm remove' : 'Remove'}
          </button>
          {armed ? (
            <button type="button" onClick={() => setArmed(false)}>
              Cancel
            </button>
          ) : null}
        </>
      ) : null}

      {/* Rendered on every pass: a live region inserted at the same moment as
          its text is not reliably announced. */}
      <p role="status" aria-live="polite">
        {notice}
      </p>
    </div>
  )
}
