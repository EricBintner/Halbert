// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

import type { HTMLAttributes } from 'react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { ProviderId } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { ProviderCard } from './ProviderCard'
import { RoleAssignmentRow } from './RoleAssignmentRow'

export interface ModelSettingsDrawerProps
  extends HTMLAttributes<HTMLDivElement> {
  picker: UseModelPickerResult
  /** Collapsed by default; opens itself when there are no endpoints yet. */
  providersOpen?: boolean
  onProvidersOpenChange?: (open: boolean) => void
}

/**
 * Master-detail configuration: what each slot points at on top, where models
 * come from underneath.
 *
 * The order matters. Assignments are what the user came to change; the
 * provider list is plumbing they touch once, so it stays folded away until
 * there is nothing assigned to look at.
 */
export function ModelSettingsDrawer(props: ModelSettingsDrawerProps) {
  const { picker, providersOpen, onProvidersOpenChange, ...rest } = props

  const [selfOpen, setSelfOpen] = useState(false)
  const [justAddedId, setJustAddedId] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')

  const controlled = providersOpen !== undefined
  const open = controlled ? providersOpen : selfOpen

  const setOpen = useCallback(
    (next: boolean) => {
      if (!controlled) setSelfOpen(next)
      onProvidersOpenChange?.(next)
    },
    [controlled, onProvidersOpenChange],
  )

  const endpoints = picker.config.endpoints

  const knownEndpointIds = useRef<string[] | null>(null)
  useEffect(() => {
    if (picker.loading) return
    const before = knownEndpointIds.current
    knownEndpointIds.current = endpoints.map((e) => e.id)
    // The first settled config is the setup the user already had, not
    // something they just added in this session.
    if (before === null) return
    const added = endpoints.find((e) => !before.includes(e.id))
    if (added) {
      setJustAddedId(added.id)
      setAnnouncement(`${added.name} added.`)
    }
  }, [picker.loading, endpoints])

  useEffect(() => {
    if (justAddedId && !endpoints.some((e) => e.id === justAddedId)) {
      setJustAddedId(null)
    }
  }, [justAddedId, endpoints])

  const autoOpened = useRef(false)
  useEffect(() => {
    if (autoOpened.current || picker.loading || endpoints.length > 0) return
    // Opened once, never re-forced: a user who folds this away keeps it folded.
    autoOpened.current = true
    setOpen(true)
  }, [picker.loading, endpoints.length, setOpen])

  const buttonId = useId()
  const regionId = useId()

  const justAdded = justAddedId
    ? endpoints.find((e) => e.id === justAddedId)
    : undefined

  const emptyRole = picker.roles.find((role) => {
    const assignment = picker.assignmentFor(role.id)
    return !assignment?.model || !assignment.enabled
  })

  const candidate =
    justAdded && emptyRole
      ? picker
          .modelsForRole(emptyRole.id)
          .find((m) => m.endpointId === justAdded.id)
      : undefined

  const stillListing = justAdded
    ? picker.listing.includes(justAdded.id)
    : false

  const assignCandidate = async () => {
    if (!emptyRole || !candidate) return
    await picker.assignRole(emptyRole.id, candidate.endpointId, candidate.id)
    setJustAddedId(null)
    setAnnouncement(`${candidate.name} assigned to ${emptyRole.label}.`)
  }

  const configuredProviders = new Set<ProviderId>(endpoints.map((e) => e.provider))
  const unsavedLocal: ProviderId[] = []
  if (picker.discovery) {
    // Matched by provider rather than URL: a second card for a provider the
    // user already configured reads as a duplicate, not an offer.
    if (picker.discovery.ollama.running && !configuredProviders.has('ollama')) {
      unsavedLocal.push('ollama')
    }
    if (
      picker.discovery.lmStudio.running &&
      !configuredProviders.has('lm-studio')
    ) {
      unsavedLocal.push('lm-studio')
    }
  }

  return (
    <div {...rest}>
      <div role="group" aria-label="Model assignments">
        {picker.roles.map((role) => (
          <RoleAssignmentRow key={role.id} picker={picker} role={role} />
        ))}
      </div>

      {justAdded && emptyRole && (candidate || stillListing) ? (
        <div>
          <p>
            {justAdded.name} is saved but nothing is using it yet.
          </p>
          <button
            type="button"
            disabled={!candidate}
            onClick={() => {
              void assignCandidate()
            }}
          >
            {`Use it for ${emptyRole.label}`}
          </button>
          {/* Dismissible because the offer is a guess, and a guess the user
              declines must not sit there forever. */}
          <button type="button" onClick={() => setJustAddedId(null)}>
            Not now
          </button>
        </div>
      ) : null}

      <div>
        <button
          type="button"
          id={buttonId}
          aria-expanded={open}
          aria-controls={regionId}
          onClick={() => setOpen(!open)}
        >
          <span aria-hidden="true">{open ? '▾' : '▸'}</span>{' '}
          {endpoints.length > 0 ? `Providers (${endpoints.length})` : 'Providers'}
        </button>
        <div
          id={regionId}
          role="region"
          aria-labelledby={buttonId}
          hidden={!open}
        >
          {open ? (
            <>
              {endpoints.map((endpoint) => (
                <ProviderCard
                  key={endpoint.id}
                  picker={picker}
                  endpoint={endpoint}
                />
              ))}

              {unsavedLocal.length > 0 ? (
                <div role="group" aria-label="Running on this machine">
                  <p>Running here, not saved yet.</p>
                  {unsavedLocal.map((provider) => (
                    <ProviderCard
                      key={provider}
                      picker={picker}
                      provider={provider}
                    />
                  ))}
                </div>
              ) : null}

              {endpoints.length === 0 && unsavedLocal.length === 0 ? (
                <p>
                  {picker.discovering
                    ? 'Looking for providers on this machine…'
                    : 'No providers configured yet.'}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      <div role="status" aria-live="polite">
        {announcement}
      </div>
    </div>
  )
}
