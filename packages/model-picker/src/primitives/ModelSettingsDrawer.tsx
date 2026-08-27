// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

import type { HTMLAttributes, ReactNode } from 'react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { providerDescriptor } from '../types'
import type {
  AppRole,
  EndpointTestResult,
  ProviderId,
  SavedEndpoint,
} from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { ProviderCard } from './ProviderCard'
import { RoleAssignmentRow } from './RoleAssignmentRow'

/**
 * Which half of a grouped provider list something belongs to.
 */
export type ProviderGroupId = 'local' | 'cloud'

/**
 * One key per element a host may need to reach.
 *
 * A composite whose only seam is its own root cannot be styled, so the first
 * host that needed styled rows abandoned it and re-implemented every effect
 * inside it. These keys exist so the second host does not have to.
 */
export interface ModelSettingsDrawerClassNames {
  root?: string
  /** Wraps `rolesHeader` and the role grid, for hosts that frame the table. */
  rolesSection?: string
  roleGrid?: string
  roleRow?: string
  /** The "saved but nothing is using it yet" offer. */
  assignPrompt?: string
  providersSection?: string
  providersTrigger?: string
  providersRegion?: string
  /**
   * Each set of cards: the two `groupProviders` sections, and the offers for
   * engines running here but not saved.
   */
  providerGroup?: string
  providerGroupHeading?: string
  providerCard?: string
  /** Supporting and empty-state lines inside the providers region. */
  note?: string
  announcement?: string
}

export interface ModelSettingsDrawerProps
  extends HTMLAttributes<HTMLDivElement> {
  picker: UseModelPickerResult
  /** Collapsed by default; opens itself when there are no endpoints yet. */
  providersOpen?: boolean
  onProvidersOpenChange?: (open: boolean) => void
  /** Applied after any class the drawer sets, so a host always wins. */
  classNames?: ModelSettingsDrawerClassNames
  /** Rendered above the role grid; a host's column captions go here. */
  rolesHeader?: ReactNode
  /** Forwarded to every row as its `renderStatus`. */
  renderRoleStatus?: (
    role: AppRole,
    result: EndpointTestResult | undefined,
  ) => ReactNode
  /** Rendered inside each provider card, beside its title. */
  renderProviderBadge?: (
    endpoint: SavedEndpoint | undefined,
    provider: ProviderId,
  ) => ReactNode
  /** Rendered inside each group heading, when `groupProviders` is set. */
  renderGroupBadge?: (group: ProviderGroupId) => ReactNode
  /** Replaces the trigger's own label. */
  renderProvidersLabel?: (open: boolean, count: number) => ReactNode
  /** Rendered last in the providers region; a host's "add a provider" control. */
  providersFooter?: ReactNode
  /** Split the cards into a local-engine section and a cloud section. */
  groupProviders?: boolean
}

/** Joins what is present. Host classes come last, so a host always wins. */
function cx(...values: (string | undefined)[]): string | undefined {
  const joined = values.filter(Boolean).join(' ')
  return joined === '' ? undefined : joined
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
  const {
    picker,
    providersOpen,
    onProvidersOpenChange,
    classNames,
    className,
    rolesHeader,
    renderRoleStatus,
    renderProviderBadge,
    renderGroupBadge,
    renderProvidersLabel,
    providersFooter,
    groupProviders = false,
    ...rest
  } = props

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
  const localHeadingId = useId()
  const cloudHeadingId = useId()

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

  const savedCard = (endpoint: SavedEndpoint) => (
    <ProviderCard
      key={endpoint.id}
      picker={picker}
      endpoint={endpoint}
      className={cx(classNames?.providerCard)}
      renderBadge={renderProviderBadge}
    />
  )

  const offerCard = (provider: ProviderId) => (
    <ProviderCard
      key={provider}
      picker={picker}
      provider={provider}
      className={cx(classNames?.providerCard)}
      renderBadge={renderProviderBadge}
    />
  )

  const unsavedOffers =
    unsavedLocal.length > 0 ? (
      <div
        role="group"
        aria-label="Running on this machine"
        className={cx(classNames?.providerGroup)}
      >
        <p className={cx(classNames?.note)}>Running here, not saved yet.</p>
        {unsavedLocal.map(offerCard)}
      </div>
    ) : null

  const localEndpoints = endpoints.filter(
    (e) => providerDescriptor(e.provider).isLocal,
  )
  const cloudEndpoints = endpoints.filter(
    (e) => !providerDescriptor(e.provider).isLocal,
  )

  const groupedProviders = (
    <>
      <section
        aria-labelledby={localHeadingId}
        className={cx(classNames?.providerGroup)}
      >
        <h4 id={localHeadingId} className={cx(classNames?.providerGroupHeading)}>
          Local engines
          {renderGroupBadge?.('local')}
        </h4>
        {localEndpoints.map(savedCard)}
        {unsavedOffers}
        {localEndpoints.length === 0 && unsavedLocal.length === 0 ? (
          <p className={cx(classNames?.note)}>
            {picker.discovering
              ? 'Looking for an engine on this machine…'
              : 'Nothing detected on the standard local ports.'}
          </p>
        ) : null}
      </section>

      <section
        aria-labelledby={cloudHeadingId}
        className={cx(classNames?.providerGroup)}
      >
        <h4 id={cloudHeadingId} className={cx(classNames?.providerGroupHeading)}>
          Cloud providers
          {renderGroupBadge?.('cloud')}
        </h4>
        {cloudEndpoints.length > 0 ? (
          cloudEndpoints.map(savedCard)
        ) : (
          <p className={cx(classNames?.note)}>No cloud provider configured.</p>
        )}
      </section>
    </>
  )

  const flatProviders = (
    <>
      {endpoints.map(savedCard)}
      {unsavedOffers}
      {endpoints.length === 0 && unsavedLocal.length === 0 ? (
        <p className={cx(classNames?.note)}>
          {picker.discovering
            ? 'Looking for providers on this machine…'
            : 'No providers configured yet.'}
        </p>
      ) : null}
    </>
  )

  return (
    <div {...rest} className={cx(className, classNames?.root)}>
      <div className={cx(classNames?.rolesSection)}>
        {rolesHeader}
        <div
          role="group"
          aria-label="Model assignments"
          className={cx(classNames?.roleGrid)}
        >
          {picker.roles.map((role) => (
            <RoleAssignmentRow
              key={role.id}
              picker={picker}
              role={role}
              className={cx(classNames?.roleRow)}
              renderStatus={
                renderRoleStatus
                  ? (result) => renderRoleStatus(role, result)
                  : undefined
              }
            />
          ))}
        </div>
      </div>

      {justAdded && emptyRole && (candidate || stillListing) ? (
        <div className={cx(classNames?.assignPrompt)}>
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

      <div className={cx(classNames?.providersSection)}>
        <button
          type="button"
          id={buttonId}
          aria-expanded={open}
          aria-controls={regionId}
          onClick={() => setOpen(!open)}
          className={cx(classNames?.providersTrigger)}
        >
          {renderProvidersLabel ? (
            renderProvidersLabel(open, endpoints.length)
          ) : (
            <>
              <span aria-hidden="true">{open ? '▾' : '▸'}</span>{' '}
              {endpoints.length > 0
                ? `Providers (${endpoints.length})`
                : 'Providers'}
            </>
          )}
        </button>
        <div
          id={regionId}
          role="region"
          aria-labelledby={buttonId}
          hidden={!open}
          className={cx(classNames?.providersRegion)}
        >
          {open ? (
            <>
              {groupProviders ? groupedProviders : flatProviders}
              {providersFooter}
            </>
          ) : null}
        </div>
      </div>

      <div
        role="status"
        aria-live="polite"
        className={cx(classNames?.announcement)}
      >
        {announcement}
      </div>
    </div>
  )
}
