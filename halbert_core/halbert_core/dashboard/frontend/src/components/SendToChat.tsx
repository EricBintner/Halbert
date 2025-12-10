/**
 * SendToChat - Universal component to send context to chat.
 * 
 * Usage:
 * - Click: Continue in current conversation
 * - Shift+Click or Right-Click: Open new conversation
 * 
 * Props:
 * - context: The text/data to send to chat
 * - title: Display title for the item
 * - type: Type of item (backup, service, storage, etc.)
 * - itemId: Optional ID for @mention
 * - alwaysNewChat: If true, always creates new conversation
 * - useSpecialist: If true, uses 70b model for deep research
 * - className: Additional CSS classes
 */

import { MessageSquare, MessageSquarePlus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface SendToChatProps {
  context: string
  title: string
  type: string
  itemId?: string
  alwaysNewChat?: boolean
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
  newConversation?: boolean
  useSpecialist?: boolean
  prefillMessage?: string
  reuseExisting?: boolean  // Phase 18: Reuse existing conversation with same title
}

/**
 * Dispatch event to open chat with context
 */
export function openChat(event: OpenChatEvent) {
  window.dispatchEvent(new CustomEvent('halbert:open-chat', { detail: event }))
}

/**
 * Open chat for deep research with specialist model
 */
export function researchInChat(
  title: string,
  type: string,
  context: string,
  question?: string
) {
  openChat({
    title,
    type,
    context,
    newConversation: true,
    useSpecialist: true,
    prefillMessage: question || `Tell me more about this ${type}`,
  })
}

export function SendToChat({
  context,
  title,
  type,
  itemId,
  alwaysNewChat = false,
  useSpecialist = false,
  variant = 'icon',
  label,
  className,
}: SendToChatProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    const newConversation = alwaysNewChat || e.shiftKey
    
    openChat({
      title,
      type,
      context,
      itemId,
      newConversation,
      useSpecialist,
    })
  }
  
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    // Right-click always opens new conversation
    openChat({
      title,
      type,
      context,
      itemId,
      newConversation: true,
      useSpecialist,
    })
  }
  
  const Icon = alwaysNewChat ? MessageSquarePlus : MessageSquare
  const tooltipText = alwaysNewChat 
    ? 'Discuss in new chat'
    : 'Continue in chat (Shift+click for new)'
  
  if (variant === 'icon') {
    return (
      <button
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        title={tooltipText}
        className={cn(
          "p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground",
          className
        )}
      >
        <Icon className="h-4 w-4" />
      </button>
    )
  }
  
  if (variant === 'button') {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        title={tooltipText}
        className={className}
      >
        <Icon className="h-4 w-4 mr-2" />
        {label || 'Ask AI'}
      </Button>
    )
  }
  
  // Text variant
  return (
    <button
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      className={cn(
        "inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors",
        className
      )}
    >
      <Icon className="h-3 w-3" />
      {label || 'Ask AI'}
    </button>
  )
}

/**
 * Research button - always opens new chat with specialist model
 */
export function ResearchButton({
  context,
  title,
  type,
  question,
  className,
  size = 'sm',
  variant = 'outline',
  label = 'Research This',
}: {
  context: string
  title: string
  type: string
  question?: string
  className?: string
  size?: 'sm' | 'default' | 'lg' | 'icon'
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  label?: string
}) {
  const handleClick = () => {
    researchInChat(title, type, context, question)
  }
  
  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleClick}
      className={cn("gap-2", className)}
    >
      <Search className="h-4 w-4" />
      {label}
    </Button>
  )
}

export default SendToChat
