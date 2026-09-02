// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SendToChat - Universal component to send context to chat.
 *
 * Usage:
 * - Click: Continue in chat
 *
 * Props:
 * - context: The text/data to send to chat
 * - title: Display title for the item
 * - type: Type of item (backup, service, storage, etc.)
 * - itemId: Optional ID for @mention
 * - useSpecialist: If true, uses the configured specialist model for deep research
 * - className: Additional CSS classes
 *
 * CC-02: this used to distinguish "continue in the current conversation"
 * (click) from "open a new conversation" (shift+click / right-click), via
 * an OpenChatEvent.newConversation flag every producer set but Layout.tsx's
 * halbert:open-chat handler never read — a dead affordance advertised by a
 * tooltip and an icon swap that did nothing. Removed rather than wired up:
 * the continuity direction is one seamless chat with hidden topic threads,
 * not a chooser between conversations.
 */

import { MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface SendToChatProps {
  context: string
  title: string
  type: string
  itemId?: string
  useSpecialist?: boolean
  variant?: 'icon' | 'button' | 'text'
  label?: string
  className?: string
}

// Event types for chat integration
export interface OpenChatEvent {
  title: string
  type: string
  context?: string
  itemId?: string
  useSpecialist?: boolean
  prefillMessage?: string
  reuseExisting?: boolean  // Phase 18: Reuse existing conversation with same title
  /** Full item data for rich context */
  data?: Record<string, unknown>
  /** Description of the item */
  description?: string
  /** Current status */
  status?: string
  /** Path to config file for this item (enables Edit Config button) */
  configPath?: string
}

/**
 * Dispatch event to open chat with context
 * Also sets focused item for PageContext
 */
export function openChat(event: OpenChatEvent) {
  // Set focused item for PageContext (rich context in chat)
  if (event.itemId) {
    window.dispatchEvent(new CustomEvent('halbert:set-focused-item', { 
      detail: {
        id: event.itemId,
        name: event.title,
        title: event.title,
        type: event.type,
        status: event.status,
        description: event.description || event.context,
        data: event.data,
      }
    }))
  }
  
  window.dispatchEvent(new CustomEvent('halbert:open-chat', { detail: event }))
}

// Event types for agent integration
export function SendToChat({
  context,
  title,
  type,
  itemId,
  useSpecialist = false,
  variant = 'icon',
  label,
  className,
}: SendToChatProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    openChat({
      title,
      type,
      context,
      itemId,
      useSpecialist,
    })
  }

  const tooltipText = 'Continue in chat'

  if (variant === 'icon') {
    return (
      <button
        onClick={handleClick}
        title={tooltipText}
        className={cn(
          "p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground",
          className
        )}
      >
        <MessageSquare className="h-4 w-4" />
      </button>
    )
  }

  if (variant === 'button') {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={handleClick}
        title={tooltipText}
        className={className}
      >
        <MessageSquare className="h-4 w-4 mr-2" />
        {label || 'Ask AI'}
      </Button>
    )
  }

  // Text variant
  return (
    <button
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors",
        className
      )}
    >
      <MessageSquare className="h-3 w-3" />
      {label || 'Ask AI'}
    </button>
  )
}

export default SendToChat
