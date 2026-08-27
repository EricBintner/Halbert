// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type {
  HTMLAttributes,
  KeyboardEvent as ReactKeyboardEvent,
  RefObject,
} from 'react'
import type { DiscoveredModel, ModelSelection, Tier } from '../types'
import { providerDescriptor } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { matchModels } from '../match'

export interface QuickSwitchPopoverProps
  extends HTMLAttributes<HTMLDivElement> {
  picker: UseModelPickerResult
  open: boolean
  onClose: () => void
  /** Pre-fills the search box, e.g. the argument of a `/model <query>` command. */
  initialQuery?: string
  /** Called after a model or tier is chosen. */
  onSelected?: (selection: ModelSelection) => void
  /** Footer link into the full settings surface. */
  onOpenSettings?: () => void
  /**
   * The host's trigger. The package is headless and never looks up the host's
   * DOM, so the one outside element it may touch is the one handed to it here:
   * closing hands focus back to it, and while the popover is open it carries
   * `aria-controls` pointing at the listbox.
   */
  triggerRef?: RefObject<HTMLElement | null>
  /**
   * Where focus goes on close, for a host whose trigger is not one element a
   * ref can name. Wins over `triggerRef`; with neither, focus is left alone.
   */
  onRequestFocusReturn?: () => void
}

const TIERS: readonly { id: Tier; label: string }[] = [
  { id: 'guide', label: 'Guide' },
  { id: 'specialist', label: 'Specialist' },
  { id: 'vision', label: 'Vision' },
  { id: 'auto', label: 'Auto' },
]

function formatContext(tokens: number): string {
  return tokens >= 1000
    ? `${Math.round(tokens / 1000)}K context`
    : `${tokens} context`
}

function capabilityTags(model: DiscoveredModel): string[] {
  const tags: string[] = []
  if (model.capabilities.tools) tags.push('tools')
  if (model.capabilities.vision) tags.push('vision')
  if (model.capabilities.reasoning) tags.push('reasoning')
  if (model.capabilities.contextWindow) {
    tags.push(formatContext(model.capabilities.contextWindow))
  }
  return tags
}

/**
 * The searchable switcher the pill opens.
 *
 * Committing does not dismiss; whether a quick switch closes the surface is the
 * host's call, made from `onSelected`. The switch itself is announced by the
 * pill's live region rather than one here, because that region follows the
 * selection and so survives both a host that closes on commit and a pin made
 * without opening this at all.
 *
 * Focus return and the trigger's `aria-controls` both travel through
 * `triggerRef`/`onRequestFocusReturn` rather than a DOM lookup: a package that
 * knows nothing about its host cannot find the trigger for itself, and a host
 * that passes neither keeps working, minus the two behaviours.
 */
export function QuickSwitchPopover({
  picker,
  open,
  onClose,
  initialQuery,
  onSelected,
  onOpenSettings,
  triggerRef,
  onRequestFocusReturn,
  onKeyDown,
  ...rest
}: QuickSwitchPopoverProps) {
  const baseId = useId()
  const listboxId = `${baseId}-listbox`
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const optionRefs = useRef<(HTMLDivElement | null)[]>([])

  const [query, setQuery] = useState(initialQuery ?? '')
  const [highlight, setHighlight] = useState(0)

  const { models, selection, pinModel, pinTier } = picker

  const filtered = useMemo(() => matchModels(models, query), [models, query])
  const local = useMemo(() => filtered.filter((m) => m.isLocal), [filtered])
  const cloud = useMemo(() => filtered.filter((m) => !m.isLocal), [filtered])
  // Keyboard order must equal render order, so the flattening mirrors the
  // groups below rather than re-sorting.
  const flat = useMemo(() => [...local, ...cloud], [local, cloud])

  useEffect(() => {
    if (!open) return
    setQuery(initialQuery ?? '')
    setHighlight(0)
    inputRef.current?.focus()
  }, [open, initialQuery])

  useEffect(() => {
    setHighlight(0)
  }, [query])

  useEffect(() => {
    if (!open) return
    const el = optionRefs.current[highlight]
    // jsdom implements no scrollIntoView, and the popover must still work there.
    el?.scrollIntoView?.({ block: 'nearest' })
  }, [highlight, open])

  useEffect(() => {
    if (!open) return
    const dismiss = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (rootRef.current?.contains(target)) return
      // The trigger toggles itself; closing first would make its click reopen us.
      if (
        target instanceof Element &&
        target.closest('[data-model-picker-trigger]')
      ) {
        return
      }
      onClose()
    }
    document.addEventListener('mousedown', dismiss)
    return () => document.removeEventListener('mousedown', dismiss)
  }, [open, onClose])

  const returnFocus = () => {
    // Only reclaim what our own removal orphaned: a user who has already
    // clicked into another control must not have focus yanked off it.
    const active = document.activeElement
    const orphaned =
      !active || active === document.body || active === document.documentElement
    if (!orphaned) return
    if (onRequestFocusReturn) onRequestFocusReturn()
    else triggerRef?.current?.focus()
  }

  // Held in a ref so a host passing an inline callback cannot change this
  // effect's identity mid-open and fire the focus return while still open.
  const returnFocusRef = useRef(returnFocus)
  useEffect(() => {
    returnFocusRef.current = returnFocus
  })

  useEffect(() => {
    if (!open) return
    // Closing otherwise drops keyboard and screen-reader users on document.body.
    return () => returnFocusRef.current()
  }, [open])

  useEffect(() => {
    const trigger = triggerRef?.current
    if (!open || !trigger) return
    // The reference is only true while the listbox exists, so it is removed
    // with the popover rather than left dangling on the trigger.
    trigger.setAttribute('aria-controls', listboxId)
    return () => trigger.removeAttribute('aria-controls')
  }, [open, triggerRef, listboxId])

  const commitModel = useCallback(
    (model: DiscoveredModel) => {
      pinModel(model.id, model.endpointId)
      onSelected?.({ model: model.id, endpointId: model.endpointId })
    },
    [pinModel, onSelected],
  )

  const commitTier = useCallback(
    (tier: Tier) => {
      pinTier(tier)
      onSelected?.({ tier })
    },
    [pinTier, onSelected],
  )

  const handleInputKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((h) => (flat.length ? (h + 1) % flat.length : 0))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((h) => (flat.length ? (h - 1 + flat.length) % flat.length : 0))
    } else if (event.key === 'Enter') {
      const model = flat[highlight]
      if (model) {
        event.preventDefault()
        commitModel(model)
      }
    }
  }

  const handleRootKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(event)
    if (event.defaultPrevented) return
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    }
  }

  if (!open) return null

  const activeOptionId = flat[highlight]
    ? `${baseId}-option-${highlight}`
    : undefined

  const isPinnedModel = (model: DiscoveredModel) =>
    selection.model === model.id &&
    (!selection.endpointId || selection.endpointId === model.endpointId)

  const renderOption = (model: DiscoveredModel, index: number) => {
    const highlighted = index === highlight
    const pinned = isPinnedModel(model)
    const tags = capabilityTags(model)
    return (
      <div
        key={`${model.endpointId}:${model.id}`}
        id={`${baseId}-option-${index}`}
        ref={(el) => {
          optionRefs.current[index] = el
        }}
        role="option"
        // Follows the combobox pattern: aria-selected marks the option the
        // keyboard would commit; the standing pin is carried by the check mark.
        aria-selected={highlighted}
        data-highlighted={highlighted || undefined}
        data-pinned={pinned || undefined}
        tabIndex={-1}
        onMouseEnter={() => setHighlight(index)}
        onClick={() => commitModel(model)}
      >
        <span data-part="model">
          {pinned ? '✓ ' : ''}
          {model.name}
        </span>{' '}
        <span data-part="provider">
          {providerDescriptor(model.provider).label}
        </span>
        {tags.length ? (
          <>
            {' · '}
            <span data-part="capabilities">{tags.join(' · ')}</span>
          </>
        ) : null}
      </div>
    )
  }

  const renderGroup = (
    key: string,
    label: string,
    items: DiscoveredModel[],
    offset: number,
  ) =>
    items.length ? (
      <div key={key} role="group" aria-labelledby={`${baseId}-group-${key}`}>
        <div id={`${baseId}-group-${key}`} role="presentation">
          {label}
        </div>
        {items.map((model, i) => renderOption(model, offset + i))}
      </div>
    ) : null

  return (
    <div
      {...rest}
      ref={rootRef}
      data-model-picker-popover=""
      onKeyDown={handleRootKeyDown}
    >
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeOptionId}
        aria-label="Search models"
        placeholder="Search models"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={handleInputKeyDown}
      />

      <div role="group" aria-label="Response tier">
        {TIERS.map((tier) => (
          <button
            key={tier.id}
            type="button"
            aria-pressed={selection.tier === tier.id}
            data-tier={tier.id}
            data-active={selection.tier === tier.id || undefined}
            onClick={() => commitTier(tier.id)}
          >
            {tier.label}
          </button>
        ))}
      </div>

      <div id={listboxId} role="listbox" aria-label="Available models">
        {flat.length === 0 ? (
          <div role="presentation">
            {models.length === 0
              ? 'No models configured yet.'
              : 'No models match that search.'}
          </div>
        ) : (
          <>
            {renderGroup('local', 'On this machine', local, 0)}
            {renderGroup('cloud', 'Cloud providers', cloud, local.length)}
          </>
        )}
      </div>

      {onOpenSettings ? (
        <button type="button" onClick={onOpenSettings}>
          All models and endpoints…
        </button>
      ) : null}
    </div>
  )
}
