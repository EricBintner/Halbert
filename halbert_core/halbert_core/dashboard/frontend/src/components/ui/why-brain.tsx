// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * WhyBrain Component
 *
 * Marks whether an item carries a recorded rationale — the operator's note on
 * what it is for and why it is set that way.
 * - Ghost ink: nothing recorded
 * - Telemetry tone: a rationale is on file
 *
 * Clicking opens the WhyOverlay to read or edit it.
 */
import * as React from 'react'
import { Brain } from 'lucide-react'
import { cn } from '@/lib/utils'
import { WhyOverlay } from './why-overlay'

interface WhyBrainProps {
  /** Unique identifier for this item (e.g., "service:nginx", "disk:nvme0n1") */
  itemId: string
  /** Human-readable name of the item */
  itemName: string
  /** Type/category of the item */
  itemType: string
  /** Current "why" explanation (undefined if not set) */
  why?: string
  /**
   * The rationale store could not be read, so this icon must not claim that
   * nothing is recorded. Absence of data is a fact worth stating; an empty
   * state here would tell an operator their note is gone when in truth
   * nobody could look for it.
   */
  unavailable?: boolean
  /** Callback when why is saved */
  onWhySaved?: (why: string) => void
  /** Size variant */
  size?: 'sm' | 'md' | 'lg'
  /** Additional class names */
  className?: string
}

export function WhyBrain({
  itemId,
  itemName,
  itemType,
  why,
  unavailable = false,
  onWhySaved,
  size = 'md',
  className,
}: WhyBrainProps) {
  const [isOpen, setIsOpen] = React.useState(false)
  const [currentWhy, setCurrentWhy] = React.useState(why)

  // Follow the prop. Seeding the state once would leave the icon grey forever
  // when the caller fetches the rationale after mount, which is exactly how
  // every page that reads /api/why loads one.
  React.useEffect(() => {
    setCurrentWhy(why)
  }, [why])

  const isDefined = Boolean(currentWhy && currentWhy.trim().length > 0)

  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-4 w-4',
    lg: 'h-5 w-5',
  }

  const buttonSizeClasses = {
    sm: 'h-7 w-7',
    md: 'h-8 w-8',
    lg: 'h-9 w-9',
  }

  const handleSave = (newWhy: string) => {
    setCurrentWhy(newWhy)
    onWhySaved?.(newWhy)
  }

  return (
    <>
      <button
        onClick={(e) => {
          e.stopPropagation()
          setIsOpen(true)
        }}
        className={cn(
          'inline-flex items-center justify-center rounded-md transition-colors',
          buttonSizeClasses[size],
          'hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-focus',
          unavailable
            ? 'text-ink-ghost cursor-not-allowed'
            : isDefined
              ? 'text-status-telemetry'
              : 'text-ink-ghost hover:text-ink-tertiary',
          className,
        )}
        disabled={unavailable}
        title={
          unavailable
            ? 'Rationale unavailable. The store could not be read, so nothing can be shown or recorded.'
            : isDefined
              ? 'Edit rationale'
              : 'Add rationale'
        }
        aria-label={
          unavailable
            ? `Rationale for ${itemName} unavailable`
            : isDefined
              ? `Rationale for ${itemName}`
              : `Add rationale for ${itemName}`
        }
      >
        <Brain className={cn(sizeClasses[size], isDefined && 'fill-status-telemetry-line')} />
      </button>

      {/* Mounted only while open. These icons are rendered inside per-row maps,
          and an always-mounted overlay meant one live dialog — and, before the
          Radix rebuild, one permanent document keydown listener — per row. */}
      {isOpen && (
        <WhyOverlay
          open={isOpen}
          onOpenChange={setIsOpen}
          itemId={itemId}
          itemName={itemName}
          itemType={itemType}
          initialWhy={currentWhy}
          onSave={handleSave}
        />
      )}
    </>
  )
}

export default WhyBrain
