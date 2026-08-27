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
 * The selection is reported upward rather than held here: it has to ride on
 * the next `sendMessage` call, and it must never be persisted. A pin lives for
 * the session only; the settings drawer is what changes the stored default.
 */
import { useCallback, useRef, useState } from 'react'
import { ModelSelectorPill, QuickSwitchPopover, useModelPicker } from '@halbert/model-picker'
import type { ModelPillState, ModelSelection } from '@halbert/model-picker'
import { CHAT_ROLE_ID, HALBERT_MODEL_ROLES, modelPickerTransport } from '@/lib/halbertModelRoles'
import { cn } from '@/lib/utils'

export interface ChatModelPillProps {
  /** Fires whenever the pin changes, including when it is cleared. */
  onSelectionChange: (selection: ModelSelection) => void
  onOpenSettings?: () => void
  className?: string
}

const STATUS_STYLE: Record<ModelPillState['status'], string> = {
  ready: 'text-success',
  offline: 'text-warning',
  unconfigured: 'text-muted-foreground',
}

export function ChatModelPill({
  onSelectionChange,
  onOpenSettings,
  className,
}: ChatModelPillProps) {
  const picker = useModelPicker({
    transport: modelPickerTransport,
    roles: HALBERT_MODEL_ROLES,
  })
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const handleSelected = useCallback(
    (selection: ModelSelection) => {
      onSelectionChange(selection)
      setOpen(false)
    },
    [onSelectionChange],
  )

  return (
    <div className="relative">
      <ModelSelectorPill
        ref={triggerRef}
        picker={picker}
        activeRoleId={CHAT_ROLE_ID}
        open={open}
        onToggle={() => setOpen((v) => !v)}
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
            {state.pinned && (
              // A pin bypasses complexity routing entirely, so the fact that
              // one is in force has to be visible without opening anything.
              <span className="text-info" aria-hidden="true">🔒</span>
            )}
          </>
        )}
      </ModelSelectorPill>

      <QuickSwitchPopover
        picker={picker}
        open={open}
        onClose={() => setOpen(false)}
        onSelected={handleSelected}
        onOpenSettings={onOpenSettings}
        triggerRef={triggerRef}
        className={cn(
          'absolute right-0 top-full mt-1 w-96 z-50',
          'bg-muted border border-border rounded-lg shadow-xl',
          'max-h-96 overflow-y-auto p-2 text-sm',
        )}
      />
    </div>
  )
}
