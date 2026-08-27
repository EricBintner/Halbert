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
import { useRef } from 'react'
import { ModelSelectorPill, QuickSwitchPopover } from '@halbert/model-picker'
import type {
  ModelPillState,
  ModelSelection,
  TierRoles,
  UseModelPickerResult,
} from '@halbert/model-picker'
import { CHAT_ROLE_ID } from '@/lib/halbertModelRoles'
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
   * Where the popover sits relative to the pill. Defaults to opening downward,
   * which is right for a pill at the top of a panel. The composer footer needs
   * the upward variant (`bottom-full mb-1`): this popover is 384px wide and up
   * to `max-h-96` tall, so downward from the footer is off the bottom of the
   * window. Only the position half of the class list is overridden — the
   * surface (background, border, scroll, padding) is not a caller's business.
   */
  popoverClassName?: string
}

/** Downward from a pill near the top of the panel. */
const DEFAULT_POPOVER_POSITION = 'absolute right-0 top-full mt-1 w-96 z-50'

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

  return (
    <div className="relative">
      <ModelSelectorPill
        ref={triggerRef}
        picker={picker}
        activeRoleId={CHAT_ROLE_ID}
        tierRoles={TIER_ROLES}
        open={open}
        onToggle={() => onOpenChange(!open)}
        announcementClassName="sr-only"
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
          popoverClassName ?? DEFAULT_POPOVER_POSITION,
          'bg-muted border border-border rounded-lg shadow-xl',
          'max-h-96 overflow-y-auto p-2 text-sm',
        )}
      />
    </div>
  )
}
