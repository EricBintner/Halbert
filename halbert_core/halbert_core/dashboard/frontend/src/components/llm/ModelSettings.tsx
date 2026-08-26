// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-6: Settings -> AI Models, rebuilt on @halbert/model-picker.
 *
 * One cohesive surface per the triage's D-6 resolution: role rows on top
 * (always visible), a collapsible providers accordion below. This file is
 * the host wrapper — everything it adds on top of the package is Halbert-
 * specific and does not belong in a package with no role names and no I/O:
 *
 *  - the three role definitions (chat_model/specialist_model/vision_model)
 *  - the vision slot's "Auto: inherit from the chat model" copy when it is
 *    unassigned, so the UI never claims a dedicated vision model exists
 *    when there isn't one (never a model name — see UI-SPEC Q3)
 *  - the LEG-MOD-02 cloud-provider disclosure gate carried over from the
 *    deleted EndpointManager, implemented by wrapping saveEndpoint rather
 *    than forking ProviderCard
 *  - an "add a provider" control: neither ModelSettingsDrawer nor
 *    RoleAssignmentRow offers a way to add a cloud endpoint that was not
 *    auto-discovered on the local machine
 */

import { useCallback, useMemo, useState } from 'react'
import {
  ModelSettingsDrawer,
  ProviderCard,
  PROVIDERS,
  useModelPicker,
} from '@halbert/model-picker'
import type { AppRole, ProviderId, SavedEndpoint, UseModelPickerResult } from '@halbert/model-picker'
import { createModelPickerTransport } from '@/lib/modelPickerTransport'
import { CloudDisclosureModal } from '@/components/legal'

// One instance for the app's lifetime: useModelPicker keys its load effect on
// this reference, so recreating it every render would reload on every render.
const transport = createModelPickerTransport()

const HALBERT_ROLES: AppRole[] = [
  { id: 'chat_model', label: 'Chat (Guide)', description: 'Quick system commands & diagnostics', requiresTools: true },
  { id: 'specialist_model', label: 'Specialist', description: 'Deep reasoning & multi-step plans', optional: true },
  { id: 'vision_model', label: 'Vision', description: 'Screenshot & hardware sensor analysis', requiresVision: true, optional: true },
]

const VISION_INHERIT_COPY =
  'Auto: inherit from the chat model. Assign a dedicated model only if your chat model is text-only.'

// LEG-MOD-02: a provider triggers the cloud data-flow disclosure when it is a
// known cloud vendor, or an Ollama endpoint pointed at Ollama Cloud rather
// than a local daemon. Carried over from the deleted EndpointManager.
const DISCLOSURE_PROVIDERS = new Set<ProviderId>([
  'openai', 'anthropic', 'google', 'azure-openai', 'openai-compatible',
])

export function needsDisclosure(endpoint: Pick<SavedEndpoint, 'provider' | 'url'>): boolean {
  if (DISCLOSURE_PROVIDERS.has(endpoint.provider)) return true
  if (endpoint.provider === 'ollama') {
    try {
      const host = new URL(endpoint.url).hostname.toLowerCase()
      return host === 'ollama.com' || host.endsWith('.ollama.com')
    } catch {
      return false
    }
  }
  return false
}

function providerLabel(id: ProviderId): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id
}

interface PendingSave {
  endpoint: SavedEndpoint
  resolve: () => void
}

/** The provider picker for a brand-new cloud endpoint: nothing in the
 * package offers this, since ModelSettingsDrawer only auto-offers locally
 * discovered engines and RoleAssignmentRow only lists already-saved ones. */
function AddProviderControl({ picker }: { picker: UseModelPickerResult }) {
  const [selected, setSelected] = useState<ProviderId | ''>('')
  const configured = new Set(picker.config.endpoints.map((e) => e.provider))
  const offerable = PROVIDERS.filter((p) => !configured.has(p.id))

  if (offerable.length === 0 && !selected) return null

  return (
    <div>
      <label htmlFor="model-settings-add-provider">Add a provider</label>
      <select
        id="model-settings-add-provider"
        value={selected}
        onChange={(event) => setSelected(event.target.value as ProviderId | '')}
      >
        <option value="">Choose a provider…</option>
        {offerable.map((p) => (
          <option key={p.id} value={p.id}>{p.label}</option>
        ))}
      </select>

      {selected ? (
        <ProviderCard
          picker={picker}
          provider={selected}
          onSaved={() => setSelected('')}
        />
      ) : null}
    </div>
  )
}

export function ModelSettings() {
  const picker = useModelPicker({ transport, roles: HALBERT_ROLES })
  const [pending, setPending] = useState<PendingSave | null>(null)

  const gatedSaveEndpoint = useCallback(
    (endpoint: SavedEndpoint) => {
      if (!needsDisclosure(endpoint)) return picker.saveEndpoint(endpoint)
      return new Promise<void>((resolve) => {
        setPending({ endpoint, resolve })
      })
    },
    [picker],
  )

  const handleAccept = useCallback(async () => {
    if (pending) {
      await picker.saveEndpoint(pending.endpoint)
      pending.resolve()
    }
    setPending(null)
  }, [pending, picker])

  const handleDecline = useCallback(() => {
    pending?.resolve()
    setPending(null)
  }, [pending])

  const visionAssignment = picker.assignmentFor('vision_model')
  const visionUnassigned = !visionAssignment?.enabled

  const displayRoles = useMemo(
    () =>
      HALBERT_ROLES.map((role) =>
        role.id === 'vision_model' && visionUnassigned
          ? { ...role, description: VISION_INHERIT_COPY }
          : role,
      ),
    [visionUnassigned],
  )

  const gatedPicker: UseModelPickerResult = useMemo(
    () => ({ ...picker, roles: displayRoles, saveEndpoint: gatedSaveEndpoint }),
    [picker, displayRoles, gatedSaveEndpoint],
  )

  return (
    <div className="space-y-4">
      <ModelSettingsDrawer picker={gatedPicker} />
      <AddProviderControl picker={gatedPicker} />

      <CloudDisclosureModal
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) handleDecline()
        }}
        onAccept={() => void handleAccept()}
        onDecline={handleDecline}
        providerName={pending ? providerLabel(pending.endpoint.provider) : undefined}
      />
    </div>
  )
}
