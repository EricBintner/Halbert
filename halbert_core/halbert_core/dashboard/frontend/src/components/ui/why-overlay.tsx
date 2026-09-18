// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * WhyOverlay Component
 *
 * Modal editor for the rationale recorded against one item.
 *
 * The rationale is the OPERATOR's note, in their words — what a thing is for
 * and why it is set the way it is — kept so the machine can hand it back
 * months later. It is not one of the Four Whys, which are the machine
 * justifying its own claims; that is WhyChip's job, and it cites evidence
 * rather than asking a person anything.
 *
 * The copy deliberately avoids asking whether something should exist. Put to
 * an operator about their own disk or service, that question is both
 * unanswerable and faintly absurd, and it is not what the field records.
 *
 * The shell is @radix-ui/react-dialog, composed the way `./sheet.tsx` composes
 * it. Radix owns role="dialog", aria-modal, the focus trap, Escape, and focus
 * restore to whatever opened the overlay — none of that is hand-rolled here.
 * `./dialog.tsx` is deliberately NOT reused: that one is hand-rolled and
 * carries the very accessibility gaps this file was rebuilt to shed.
 */
import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Brain, X, Save } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'

interface WhyOverlayProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  itemId: string
  itemName: string
  itemType: string
  initialWhy?: string
  onSave?: (why: string) => void
}

/**
 * The save shortcut accepts Ctrl *or* Cmd, so the hint has to name the key
 * this operator actually has under their thumb rather than always saying Ctrl.
 */
function modifierGlyph(): string {
  if (typeof navigator === 'undefined') return 'Ctrl'
  return /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent) ? '⌘' : 'Ctrl'
}

export function WhyOverlay({
  open,
  onOpenChange,
  itemId,
  itemName,
  itemType,
  initialWhy = '',
  onSave,
}: WhyOverlayProps) {
  const [why, setWhy] = React.useState(initialWhy)
  const [isSaving, setIsSaving] = React.useState(false)
  const [saved, setSaved] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const wasOpen = React.useRef(false)
  const inputId = React.useId()
  const modifier = React.useMemo(modifierGlyph, [])

  // Reset on the closed -> open transition only. Resetting whenever
  // `initialWhy` changes would wipe the success state one render after it was
  // set, and would clobber whatever the operator is mid-way through typing the
  // moment a fetched rationale arrived from the server.
  React.useEffect(() => {
    if (open && !wasOpen.current) {
      setWhy(initialWhy)
      setSaved(false)
      setError(null)
    }
    wasOpen.current = open
  }, [open, initialWhy])

  // The close-after-save delay is the only timer left in this component, and it
  // must not fire into an unmounted tree — the parent unmounts us on close.
  React.useEffect(
    () => () => {
      if (closeTimer.current) clearTimeout(closeTimer.current)
    },
    [],
  )

  const handleSave = async () => {
    const trimmed = why.trim()
    if (!trimmed || isSaving) return

    setIsSaving(true)
    setError(null)
    try {
      await api.saveRationale(itemId, itemName, itemType, trimmed)
      onSave?.(trimmed)
      setSaved(true)
      closeTimer.current = setTimeout(() => onOpenChange(false), 500)
    } catch (err) {
      // Stay open and keep the text exactly where it is: until the server has
      // it, this textarea is the only copy of what the operator just wrote.
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  /**
   * Clearing the box and pressing Save cannot do this: an empty note is
   * rejected, which is right — a blank rationale is not a rationale. Removal
   * is its own act, so it gets its own control.
   */
  const handleRemove = async () => {
    setIsSaving(true)
    setError(null)
    try {
      await api.deleteRationale(itemId)
      onSave?.('')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  // Save on Ctrl+Enter / Cmd+Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSave()
    }
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          // Same React-tree bubbling as the content below: without this,
          // dismissing the overlay by clicking the backdrop also opens the
          // row's detail sheet.
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          className={cn(
            'fixed inset-0 z-50 bg-background/80 backdrop-blur-sm',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
            'duration-200',
          )}
        />
        <DialogPrimitive.Content
          // Radix portals the dialog to document.body, but React synthetic
          // events bubble the REACT tree, not the DOM one — so without this a
          // click on the textarea still reaches the row this overlay was
          // opened from, and Services/Network rows open their detail sheet
          // underneath. WhyBrain's own trigger stops the opening click; these
          // stop every click after it.
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          onOpenAutoFocus={(e) => {
            // Radix would land on the first tabbable node, which is the close
            // button. The operator opened this to type.
            e.preventDefault()
            textareaRef.current?.focus()
          }}
          className={cn(
            'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
            'w-[calc(100%-2rem)] max-w-lg rounded-xl border bg-card shadow-2xl',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
            'duration-200',
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  'p-2 rounded-lg',
                  initialWhy ? 'bg-status-telemetry-bg' : 'bg-muted',
                )}
              >
                <Brain
                  className={cn(
                    'h-5 w-5',
                    initialWhy ? 'text-status-telemetry' : 'text-muted-foreground',
                  )}
                />
              </div>
              <div>
                <DialogPrimitive.Title className="text-lg font-semibold">
                  Rationale
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="text-sm text-muted-foreground">
                  {itemType}: <span className="font-medium text-foreground">{itemName}</span>
                </DialogPrimitive.Description>
              </div>
            </div>

            <DialogPrimitive.Close
              className={cn(
                'p-2 rounded-lg hover:bg-accent transition-colors',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
              )}
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </DialogPrimitive.Close>
          </div>

          {/* Body */}
          <div className="p-4 space-y-4">
            <div className="space-y-2">
              <label htmlFor={inputId} className="text-sm font-medium text-muted-foreground">
                What it is for, and why it is set this way
              </label>
              <textarea
                ref={textareaRef}
                id={inputId}
                value={why}
                onChange={(e) => setWhy(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="In your own words"
                className={cn(
                  'w-full min-h-[120px] p-3 rounded-lg border bg-background resize-none',
                  'placeholder:text-ink-ghost',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                  'transition-all duration-200',
                )}
              />
              <p className="text-xs text-muted-foreground">
                Press <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs">{modifier}</kbd>+
                <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs">Enter</kbd> to save
              </p>
            </div>

            {error ? (
              <p
                role="alert"
                className="rounded-md border border-error/40 bg-error-muted px-3 py-2 text-sm text-error"
              >
                Saving failed. Nothing was recorded, and your note is still in the
                box above. <span className="font-mono text-xs">{error}</span>
              </p>
            ) : null}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 p-4 border-t bg-muted/30">
            {initialWhy ? (
              <button
                onClick={handleRemove}
                disabled={isSaving}
                className={cn(
                  'mr-auto px-3 py-2 text-sm rounded-lg transition-colors',
                  'text-error hover:bg-error-muted',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                Remove
              </button>
            ) : null}
            <DialogPrimitive.Close
              className={cn(
                'px-3 py-2 text-sm rounded-lg hover:bg-accent transition-colors',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
              )}
            >
              Cancel
            </DialogPrimitive.Close>
            <button
              onClick={handleSave}
              disabled={!why.trim() || isSaving}
              className={cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {saved ? (
                <>Saved</>
              ) : isSaving ? (
                <>Saving</>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  Save
                </>
              )}
            </button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export default WhyOverlay
