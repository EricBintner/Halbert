// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { forwardRef, useCallback, useMemo } from 'react'
import type {
  ButtonHTMLAttributes,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactNode,
} from 'react'
import type { LocalDiscovery, LocalEngine, ProviderId, Tier } from '../types'
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
}

export interface ModelSelectorPillProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  picker: UseModelPickerResult
  /** Role whose assignment is shown when nothing is pinned. */
  activeRoleId: string
  open?: boolean
  onToggle?: () => void
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
): ModelPillState {
  const { selection, models, assignmentFor, endpointFor, discovery, isPinned } =
    picker

  return useMemo(() => {
    const assignment = assignmentFor(activeRoleId)
    const fallback =
      assignment?.enabled && assignment.model ? assignment : undefined

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
      tier: selection.tier ?? 'auto',
    }
  }, [
    activeRoleId,
    assignmentFor,
    discovery,
    endpointFor,
    isPinned,
    models,
    selection.endpointId,
    selection.model,
    selection.tier,
  ])
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
  open = false,
  onToggle,
  children,
  onClick,
  onKeyDown,
  ...rest
}: ModelSelectorPillProps, ref) {
  const state = useModelPillState(picker, activeRoleId)

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
    state.status === 'offline' ? 'endpoint not running' : null,
    state.pinned ? 'pinned for this turn' : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
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
          {state.pinned ? (
            <>
              {' '}
              <span aria-hidden="true" data-part="pin">
                {LOCK}
              </span>
            </>
          ) : null}
        </>
      )}
    </button>
  )
})
