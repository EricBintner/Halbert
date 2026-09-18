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
          isDefined ? 'text-status-telemetry' : 'text-ink-ghost hover:text-ink-tertiary',
          className,
        )}
        title={isDefined ? 'Edit rationale' : 'Add rationale'}
        aria-label={isDefined ? `Rationale for ${itemName}` : `Add rationale for ${itemName}`}
      >
        <Brain className={cn(sizeClasses[size], isDefined && 'fill-status-telemetry-bg')} />
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
