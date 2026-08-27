// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import {
  forwardRef,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type {
  ButtonHTMLAttributes,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactNode,
} from 'react'
import type {
  LocalDiscovery,
  LocalEngine,
  ModelSelection,
  ProviderId,
  Tier,
  TierRoles,
} from '../types'
import { providerDescriptor } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'

/** What the pill has resolved about the next turn. */
export interface ModelPillState {
  /**
   * The model name to show. Never a hard-coded name — it is whatever the user
   * configured, or a prompt to configure something when `status` is
   * `unconfigured`.
   */
  label: string
  /** Vendor label, empty when there is nothing to attribute. */
  providerLabel: string
  isLocal: boolean
  pinned: boolean
  status: 'ready' | 'offline' | 'unconfigured'
  tier: Tier
  /**
   * The active tier, ready to render, in the three forms the surface spec
   * names: `⚡ Auto: Guide`, `🔒 Pin: Specialist`, `👁️ Vision`. Empty while an
   * exact model pin is in force, because such a pin bypasses tier routing and
   * naming a tier would promise an escalation that cannot happen.
   */
  tierBadge: string
}

export interface ModelSelectorPillProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  picker: UseModelPickerResult
  /** Role whose assignment is shown when no tier is pinned. */
  activeRoleId: string
  /**
   * Which of the host's roles each tier pin resolves to. Omitting it leaves a
   * tier pin reading `activeRoleId`, which is what every host got before this
   * existed — and wrong for any host that routes a tier to another slot.
   */
  tierRoles?: TierRoles
  open?: boolean
  onToggle?: () => void
  /**
   * Class for the switch announcement. This package ships no CSS, so a host
   * that wants the live region off-screen rather than visible says so here.
   */
  announcementClassName?: string
  /** Render-prop escape hatch; receives everything needed to draw a custom pill. */
  children?: (state: ModelPillState) => ReactNode
}

const UNCONFIGURED_LABEL = 'Choose a model'

const STATUS_MARK: Record<ModelPillState['status'], string> = {
  ready: '●',
  offline: '○',
  unconfigured: '◌',
}

const LOCK = '🔒'
const BOLT = '⚡'
const EYE = '👁️'

/** Tier names are this package's own vocabulary, unlike host role ids. */
const TIER_LABEL: Record<Exclude<Tier, 'auto'>, string> = {
  guide: 'Guide',
  specialist: 'Specialist',
  vision: 'Vision',
}

function tierBadgeFor(tier: Tier, modelPinned: boolean): string {
  // A model pin bypasses the router outright; the lock beside the name already
  // says so, and a tier here would claim a routing rule that is not running.
  if (modelPinned) return ''
  if (tier === 'auto') return `${BOLT} Auto: ${TIER_LABEL.guide}`
  if (tier === 'vision') return `${EYE} ${TIER_LABEL.vision}`
  return `${LOCK} Pin: ${TIER_LABEL[tier]}`
}

function localEngine(
  discovery: LocalDiscovery | null,
  provider: ProviderId | undefined,
): LocalEngine | undefined {
  if (!discovery || !provider) return undefined
  if (provider === 'ollama') return discovery.ollama
  if (provider === 'lm-studio') return discovery.lmStudio
  return undefined
}

/**
 * The pill's resolution rules, without the markup, so a host can build its own
 * trigger and still agree with the stock one about what answers next.
 */
export function useModelPillState(
  picker: UseModelPickerResult,
  activeRoleId: string,
  tierRoles?: TierRoles,
): ModelPillState {
  const { selection, models, effectiveAssignmentFor, endpointFor, discovery, isPinned } =
    picker

  // Read out one field at a time: a host writing the ordinary inline literal
  // would otherwise hand the memo a new object on every render.
  const guideRole = tierRoles?.guide
  const specialistRole = tierRoles?.specialist
  const visionRole = tierRoles?.vision

  return useMemo(() => {
    const tier = selection.tier ?? 'auto'
    // An exact model pin outranks a tier, the same order a router applies them
    // in: model override first, tier only if there is none.
    const pinnedTier = selection.model || tier === 'auto' ? undefined : tier
    const tierRole =
      pinnedTier === 'guide'
        ? guideRole
        : pinnedTier === 'specialist'
          ? specialistRole
          : pinnedTier === 'vision'
            ? visionRole
            : undefined

    // The effective assignment, not the editable one: on a layered host the
    // pill would otherwise name a model a workspace file or a session pin has
    // already overridden, which is exactly the question the pill exists to
    // answer.
    const usable = (roleId: string | undefined) => {
      const assignment = roleId ? effectiveAssignmentFor(roleId) : undefined
      return assignment?.enabled && assignment.model ? assignment : undefined
    }

    // A tier pin sends the turn to that tier's slot, so the pill has to read
    // that slot: resolving every pin against the chat role has the pill state a
    // local model while a pinned cloud model answers and bills.
    // An unconfigured tier is not a dead end — routers fall back to the default
    // slot rather than refuse the turn — so the pill falls back with them
    // instead of claiming nothing will answer.
    const fallback = usable(tierRole) ?? usable(activeRoleId)

    const name = selection.model ?? fallback?.model ?? ''
    const endpointId = selection.model
      ? selection.endpointId
      : fallback?.endpointId

    const found = models.find(
      (m) => m.id === name && (!endpointId || m.endpointId === endpointId),
    )
    // A model can be assigned before its endpoint has been listed, so provider
    // and locality fall back to the endpoint record rather than blanking.
    const provider =
      found?.provider ??
      (endpointId ? endpointFor(endpointId)?.provider : undefined)
    const isLocal =
      found?.isLocal ?? (provider ? providerDescriptor(provider).isLocal : false)

    const engine = localEngine(discovery, provider)
    const status: ModelPillState['status'] = !name
      ? 'unconfigured'
      : isLocal && engine && !engine.running
        ? 'offline'
        : 'ready'

    return {
      label: name || UNCONFIGURED_LABEL,
      providerLabel: provider ? providerDescriptor(provider).label : '',
      isLocal,
      // A tier pin bypasses the host's router exactly as a model pin does, so
      // both read as locked.
      pinned: isPinned,
      status,
      tier,
      tierBadge: tierBadgeFor(tier, Boolean(selection.model)),
    }
  }, [
    activeRoleId,
    effectiveAssignmentFor,
    discovery,
    endpointFor,
    guideRole,
    isPinned,
    models,
    selection.endpointId,
    selection.model,
    selection.tier,
    specialistRole,
    visionRole,
  ])
}

function switchAnnouncement(state: ModelPillState): string {
  const tierName = state.tier === 'auto' ? '' : TIER_LABEL[state.tier]
  if (state.status === 'unconfigured') {
    return tierName
      ? `Switched to the ${tierName} tier. No model is configured for it.`
      : 'No model is configured.'
  }
  const target = state.providerLabel
    ? `${state.label} on ${state.providerLabel}`
    : state.label
  if (tierName) {
    return `Switched to the ${tierName} tier: ${target} will answer the next turn.`
  }
  if (state.pinned) return `Switched to ${target} for the next turn.`
  return `Routing automatically: ${target} will answer the next turn.`
}

/**
 * Announces a switch whenever the selection changes, wherever it came from.
 *
 * Announcing from a click handler leaves every other route to a new selection
 * silent — a slash command, a host's own tier control — and the popover's own
 * region is torn down before a screen reader reaches it by any host that closes
 * on commit. Following the selection is what makes all of them audible.
 */
function useSwitchAnnouncement(
  state: ModelPillState,
  selection: ModelSelection,
): string {
  const [announcement, setAnnouncement] = useState('')
  const key = `${selection.model ?? ''} ${selection.endpointId ?? ''} ${selection.tier ?? ''}`

  // Held in a ref so the message describes the selection at the moment it
  // changed: re-deriving it when an endpoint finishes listing would re-announce
  // a switch the user has already heard.
  const latest = useRef(state)
  useEffect(() => {
    latest.current = state
  })

  const spoken = useRef<string | null>(null)
  useEffect(() => {
    if (spoken.current === null) {
      // Arriving on screen is not a switch.
      spoken.current = key
      return
    }
    if (spoken.current === key) return
    spoken.current = key
    setAnnouncement(switchAnnouncement(latest.current))
  }, [key])

  return announcement
}

/**
 * The always-visible trigger: what will answer the next turn, and one click to
 * change it.
 */
/**
 * Forwards its ref to the underlying button so a host can hand the same
 * element to QuickSwitchPopover's `triggerRef` — the popover returns focus
 * there on close and points `aria-controls` at its listbox, and the package
 * has no other way to name the trigger without reaching into a DOM it does
 * not own.
 */
export const ModelSelectorPill = forwardRef<HTMLButtonElement, ModelSelectorPillProps>(function ModelSelectorPill({
  picker,
  activeRoleId,
  tierRoles,
  open = false,
  onToggle,
  announcementClassName,
  children,
  onClick,
  onKeyDown,
  ...rest
}: ModelSelectorPillProps, ref) {
  const state = useModelPillState(picker, activeRoleId, tierRoles)
  const announcement = useSwitchAnnouncement(state, picker.selection)

  const handleClick = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      onClick?.(event)
      if (!event.defaultPrevented) onToggle?.()
    },
    [onClick, onToggle],
  )

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLButtonElement>) => {
      onKeyDown?.(event)
      if (event.defaultPrevented) return
      if (!open && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
        event.preventDefault()
        onToggle?.()
      } else if (open && event.key === 'Escape') {
        event.preventDefault()
        onToggle?.()
      }
    },
    [onKeyDown, onToggle, open],
  )

  const spoken = [
    state.label,
    state.providerLabel ? `on ${state.providerLabel}` : null,
    state.tier === 'auto' ? null : `${TIER_LABEL[state.tier]} tier`,
    state.status === 'offline' ? 'endpoint not running' : null,
    state.pinned ? 'pinned for this turn' : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <>
      <button
        ref={ref}
        type="button"
        {...rest}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Model: ${spoken}`}
        // The popover ignores outside clicks that start here, so the trigger's own
        // toggle is not fought by a dismissal firing first.
        data-model-picker-trigger=""
        data-status={state.status}
        data-tier={state.tier}
        data-local={state.isLocal || undefined}
        data-pinned={state.pinned || undefined}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        {children ? (
          children(state)
        ) : (
          <>
            <span aria-hidden="true" data-part="status">
              {STATUS_MARK[state.status]}
            </span>{' '}
            {state.providerLabel ? (
              <>
                <span data-part="provider">{state.providerLabel}</span>{' '}
              </>
            ) : null}
            <span data-part="model">{state.label}</span>
            {/* A tier badge carries its own lock, so a second glyph would only
                say the same thing twice. */}
            {state.pinned && !state.tierBadge ? (
              <>
                {' '}
                <span aria-hidden="true" data-part="pin">
                  {LOCK}
                </span>
              </>
            ) : null}
            {state.tierBadge ? (
              <>
                {' '}
                <span data-part="tier">{state.tierBadge}</span>
              </>
            ) : null}
          </>
        )}
      </button>

      {/* Outside the button: the trigger's aria-label replaces its contents for
          assistive tech, so a region nested inside it would never be spoken. */}
      <span
        aria-live="polite"
        data-model-picker-live=""
        className={announcementClassName}
      >
        {announcement}
      </span>
    </>
  )
})
