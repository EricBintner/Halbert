// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-2: the in-chat model control.
 *
 * Halbert's styled wrapper around the package's headless pill and quick-switch
 * popover. Everything here is Halbert-specific — the design tokens, the role
 * vocabulary, the settings link — and so does not belong in a package that
 * knows no role names.
 *
 * The picker is owned by the composer rather than created here, because the
 * `/model` command has to drive the same pin this control shows. Two pickers
 * would mean typing `/model <name>` and clicking the pill disagreed about what
 * is pinned.
 */
import { useLayoutEffect, useRef, useState } from 'react'
import { ModelSelectorPill, QuickSwitchPopover } from '@halbert/model-picker'
import type {
  ModelPillState,
  ModelSelection,
  TierRoles,
  UseModelPickerResult,
} from '@halbert/model-picker'
import { CHAT_ROLE_ID } from '@/lib/halbertModelRoles'
import { announce } from '@/lib/announce'
import { cn } from '@/lib/utils'

export interface ChatModelPillProps {
  picker: UseModelPickerResult
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Pre-fills the popover search, e.g. from an ambiguous `/model <query>`. */
  initialQuery?: string
  /** Fires when a selection is committed from the popover. */
  onSelected?: (selection: ModelSelection) => void
  onOpenSettings?: () => void
  className?: string
  /**
   * Overrides where the popover sits relative to the pill.
   *
   * Normally nothing passes this: the pill measures the room above and below
   * itself and picks the side that fits (see `choosePlacement`). A host only
   * needs this when it knows something the measurement cannot — a portal, a
   * transformed ancestor, a container that scrolls independently of the
   * viewport.
   *
   * Only the position half of the class list is overridden; the surface
   * (background, border, scroll, padding) is not a caller's business, and the
   * height is still clamped to the room on whichever side the caller chose.
   */
  popoverClassName?: string
}

/** Downward from a pill with room beneath it. */
const POSITION_BELOW = 'absolute right-0 top-full mt-1 w-96 z-50'
/** Upward, for a pill in the composer footer. */
const POSITION_ABOVE = 'absolute right-0 bottom-full mb-1 w-96 z-50'

/**
 * The tallest the surface ever gets (what `max-h-96` used to say). Beyond
 * this the list is scrolled rather than grown, because a popover taller than
 * this stops reading as a menu.
 */
const MAX_SURFACE_PX = 384
/** Breathing room between the popover and the window edge it opens toward. */
const EDGE_GAP_PX = 8
/**
 * Below this the popover is unusable whichever side it is on, so it stops
 * shrinking and accepts the overflow rather than becoming a two-row slot.
 */
const MIN_SURFACE_PX = 120

type PopoverSide = 'above' | 'below'

interface PopoverPlacement {
  side: PopoverSide
  maxHeight: number
}

/** The band of screen the popover is allowed to occupy, in viewport pixels. */
interface PopoverFrame {
  top: number
  bottom: number
}

/**
 * The box that actually clips the popover, which is not the window.
 *
 * The shell puts a 49px header (`h-12` + a border) above the mode container,
 * and that container is `overflow-hidden` — so the top 49px of the viewport
 * is a ceiling the popover is cut off by, not room it can open into.
 * Measuring against y=0 made `bottom-full` popovers land their top edge at
 * y=4 on any window shorter than ~480 CSS px, hiding the search box that
 * takes focus on open. That height is a browser at 210% zoom, which is a
 * low-vision user's normal setting.
 *
 * The nearest ancestor whose `overflow-y` is not `visible` is that box. A
 * scrolling ancestor counts too: nothing scrolls an absolutely positioned
 * popover into view, so from here scroll and clip are the same thing. The
 * result is intersected with the viewport, because a container taller than
 * the window is still bounded by the window, and falls back to the viewport
 * when nothing clips.
 *
 * `overflowY || overflow` rather than `overflowY` alone: engines that do not
 * expand the shorthand in computed style (jsdom, so the tests below) report
 * the longhand as empty, and an empty string must read as "does not clip",
 * not as "clips".
 */
function clippingFrame(trigger: Element | null): PopoverFrame {
  const viewport: PopoverFrame = { top: 0, bottom: window.innerHeight }
  for (let node = trigger?.parentElement ?? null; node; node = node.parentElement) {
    const style = window.getComputedStyle(node)
    const overflowY = style.overflowY || style.overflow
    if (!overflowY || overflowY === 'visible') continue
    const box = node.getBoundingClientRect()
    return {
      top: Math.max(viewport.top, box.top),
      bottom: Math.min(viewport.bottom, box.bottom),
    }
  }
  return viewport
}

/**
 * Which side the popover opens toward, and how tall it may be, given the
 * frame that clips it (see `clippingFrame`).
 *
 * With no layout at all (jsdom, or a trigger not yet mounted) the rect reads
 * as zeros, which lands on `below` — the behaviour before any of this
 * existed.
 */
function choosePlacement(
  trigger: DOMRect,
  frame: PopoverFrame,
  forcedSide?: PopoverSide,
): PopoverPlacement {
  const above = Math.max(0, trigger.top - frame.top - EDGE_GAP_PX)
  const below = Math.max(0, frame.bottom - trigger.bottom - EDGE_GAP_PX)
  const side: PopoverSide =
    forcedSide ?? (below >= MAX_SURFACE_PX || below >= above ? 'below' : 'above')
  const room = side === 'above' ? above : below
  return {
    side,
    maxHeight: Math.round(Math.max(MIN_SURFACE_PX, Math.min(MAX_SURFACE_PX, room))),
  }
}

/**
 * A caller that positions the popover itself still has to be clamped, and the
 * clamp has to protect the edge it actually opens toward. The class list is
 * the only thing the caller told us, so it is what we read.
 */
function forcedSideOf(popoverClassName: string | undefined): PopoverSide | undefined {
  if (!popoverClassName) return undefined
  return /\bbottom-full\b/.test(popoverClassName) ? 'above' : 'below'
}

const STATUS_STYLE: Record<ModelPillState['status'], string> = {
  ready: 'text-success',
  offline: 'text-warning',
  unconfigured: 'text-muted-foreground',
}

/**
 * The slot each tier pin actually runs on, matching `_resolve_turn_model` in
 * routes/agent.py. Without it the pill reads every pin off the chat slot and
 * names a local model while a pinned cloud specialist answers and bills.
 */
const TIER_ROLES: TierRoles = {
  guide: CHAT_ROLE_ID,
  specialist: 'specialist_model',
  vision: 'vision_model',
}

export function ChatModelPill({
  picker,
  open,
  onOpenChange,
  initialQuery,
  onSelected,
  onOpenSettings,
  className,
  popoverClassName,
}: ChatModelPillProps) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [placement, setPlacement] = useState<PopoverPlacement>({
    side: 'below',
    maxHeight: MAX_SURFACE_PX,
  })

  // Before paint, not after: measuring in a plain effect shows one frame of
  // the popover on the wrong side, which on a footer pill is one frame of it
  // hanging off the bottom of the window.
  useLayoutEffect(() => {
    if (!open) return
    const measure = () => {
      const trigger = triggerRef.current
      if (!trigger) return
      setPlacement(
        choosePlacement(
          trigger.getBoundingClientRect(),
          clippingFrame(trigger),
          forcedSideOf(popoverClassName),
        ),
      )
    }
    measure()
    // The room above a footer pill is the frame height minus the composer,
    // so resizing changes the answer while the popover is still open.
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [open, popoverClassName])

  return (
    <div className="relative">
      <ModelSelectorPill
        ref={triggerRef}
        picker={picker}
        activeRoleId={CHAT_ROLE_ID}
        tierRoles={TIER_ROLES}
        open={open}
        onToggle={() => onOpenChange(!open)}
        // Through the shell's one polite region (LiveRegion, design §11)
        // rather than a second one of the pill's own: a screen reader given
        // two polite regions in one document reads them in whatever order it
        // likes, and everything else this surface says already goes here.
        // `announce` is module-level, so its identity is stable.
        onAnnounce={announce}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg',
          'text-muted-foreground hover:text-foreground hover:bg-muted transition-colors',
          'border border-transparent hover:border-border',
          className,
        )}
      >
        {(state) => (
          <>
            <span className={STATUS_STYLE[state.status]} aria-hidden="true">
              {state.status === 'offline' ? '○' : '●'}
            </span>
            {state.providerLabel && (
              <span className="text-muted-foreground">{state.providerLabel}</span>
            )}
            <span className="max-w-[180px] truncate">{state.label}</span>
            {state.pinned && !state.tierBadge && (
              // A pin bypasses complexity routing entirely, so the fact that
              // one is in force has to be visible without opening anything.
              // A tier badge carries its own lock and needs no second one.
              <span className="text-info" aria-hidden="true">🔒</span>
            )}
            {state.tierBadge && (
              // The tier decides which slot answers, and a tier pin moves that
              // without touching anything else on the pill.
              <span
                data-part="tier"
                className={cn(
                  'shrink-0 rounded-md border border-border/60 px-1.5 py-0.5 text-[10px] leading-none',
                  state.tier === 'auto' ? 'text-muted-foreground' : 'text-info',
                )}
              >
                {state.tierBadge}
              </span>
            )}
          </>
        )}
      </ModelSelectorPill>

      <QuickSwitchPopover
        picker={picker}
        open={open}
        onClose={() => onOpenChange(false)}
        initialQuery={initialQuery}
        onSelected={(selection) => {
          onSelected?.(selection)
          onOpenChange(false)
        }}
        onOpenSettings={onOpenSettings}
        triggerRef={triggerRef}
        className={cn(
          popoverClassName ??
            (placement.side === 'above' ? POSITION_ABOVE : POSITION_BELOW),
          'bg-muted border border-border rounded-lg shadow-xl',
          'overflow-y-auto p-2 text-sm',
        )}
        // Not `max-h-96`: the cap is the room actually available on the side
        // this opens toward, which no static class can know.
        style={{ maxHeight: `${placement.maxHeight}px` }}
      />
    </div>
  )
}
