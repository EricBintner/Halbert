/**
 * SystemItemActions - Universal action buttons for system items
 * 
 * Provides consistent @ mention, chat, and research buttons across all pages.
 * 
 * Usage:
 *   <SystemItemActions item={{ name: "Main Storage", type: "storage", id: "main-storage" }} />
 *   <SystemItemActions item={item} showResearch />
 *   <SystemItemActions item={item} variant="full" />
 */

import { Button } from '@/components/ui/button'
import { openChat } from '@/components/SendToChat'
import { MessageCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface SystemItem {
  /** Display name (e.g., "Main Storage", "eth0") */
  name: string
  /** Discovery type (storage, network, service, backup, sharing, etc.) */
  type: string
  /** Unique identifier for @mention */
  id: string
  /** Context string for chat - describes the item */
  context?: string
}

export interface SystemItemActionsProps {
  /** The system item to create actions for */
  item: SystemItem
  
  /** Show @ mention button (default: true) */
  showMention?: boolean
  /** Show chat button (default: true) */
  showChat?: boolean
  /** Show research/deep-dive button (default: false) */
  showResearch?: boolean
  
  /** 
   * Appearance variant:
   * - 'icon': Just icons, minimal space (default)
   * - 'compact': Small buttons with icons
   * - 'full': Buttons with labels
   */
  variant?: 'icon' | 'compact' | 'full'
  
  /** Size: 'sm' or 'default' */
  size?: 'sm' | 'default'
  
  /** Custom @ click handler (overrides default) */
  onMention?: () => void
  /** Custom chat click handler (overrides default) */
  onChat?: () => void
  /** Custom research click handler (overrides default) */
  onResearch?: () => void
  
  /** Additional CSS classes */
  className?: string
}

export function SystemItemActions({
  item,
  showMention = true,
  showChat = true,
  showResearch = false,
  variant = 'icon',
  size = 'default',
  onMention,
  onChat,
  onResearch,
  className,
}: SystemItemActionsProps) {
  
  const handleMention = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onMention) {
      onMention()
      return
    }
    // Default: add to current chat (@ = mention in existing conversation)
    openChat({
      title: item.name,
      type: item.type,
      context: item.context,
      itemId: item.id,
      newConversation: false,
      useSpecialist: false,
    })
  }
  
  const handleChat = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onChat) {
      onChat()
      return
    }
    // Default: new conversation
    openChat({
      title: item.name,
      type: item.type,
      context: item.context,
      itemId: item.id,
      newConversation: true,
      useSpecialist: false,
    })
  }
  
  const handleResearch = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onResearch) {
      onResearch()
      return
    }
    // Default: new conversation with specialist model
    openChat({
      title: item.name,
      type: item.type,
      context: item.context,
      itemId: item.id,
      newConversation: true,
      useSpecialist: true,
      prefillMessage: `Deep dive into ${item.name}: analyze configuration, potential issues, and optimization opportunities.`,
    })
  }
  
  // Size-based classes
  const buttonSize = size === 'sm' ? 'h-6 w-6' : 'h-8 w-8'
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4'
  const atFontSize = size === 'sm' ? 'text-xs' : 'text-sm'
  
  // Icon-only variant (most compact)
  if (variant === 'icon') {
    return (
      <div className={cn("flex items-center gap-0.5", className)}>
        {showMention && (
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              buttonSize,
              "text-muted-foreground hover:text-blue-500 hover:bg-blue-500/10"
            )}
            onClick={handleMention}
            title={`Mention ${item.name} in chat`}
          >
            <span className={cn("font-semibold", atFontSize)}>@</span>
          </Button>
        )}
        {showChat && (
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              buttonSize,
              "text-muted-foreground hover:text-primary hover:bg-primary/10"
            )}
            onClick={handleChat}
            title={`Chat about ${item.name}`}
          >
            <MessageCircle className={iconSize} />
          </Button>
        )}
        {showResearch && (
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              buttonSize,
              "text-muted-foreground hover:text-purple-500 hover:bg-purple-500/10"
            )}
            onClick={handleResearch}
            title={`Deep research on ${item.name}`}
          >
            <Sparkles className={iconSize} />
          </Button>
        )}
      </div>
    )
  }
  
  // Compact or Full variant (with optional labels)
  const showLabels = variant === 'full'
  const buttonVariant = 'outline'
  const buttonSizeClass = size === 'sm' ? 'h-7 text-xs' : 'h-8 text-sm'
  
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {showMention && (
        <Button
          variant={buttonVariant}
          size="sm"
          className={cn(buttonSizeClass, "hover:border-blue-500 hover:text-blue-500")}
          onClick={handleMention}
          title={`Mention ${item.name} in chat`}
        >
          <span className="font-semibold">@</span>
          {showLabels && <span className="ml-1">Mention</span>}
        </Button>
      )}
      {showChat && (
        <Button
          variant={buttonVariant}
          size="sm"
          className={buttonSizeClass}
          onClick={handleChat}
          title={`Chat about ${item.name}`}
        >
          <MessageCircle className="h-4 w-4" />
          {showLabels && <span className="ml-1">Chat</span>}
        </Button>
      )}
      {showResearch && (
        <Button
          variant={buttonVariant}
          size="sm"
          className={cn(buttonSizeClass, "hover:border-purple-500 hover:text-purple-500")}
          onClick={handleResearch}
          title={`Deep research on ${item.name}`}
        >
          <Sparkles className="h-4 w-4" />
          {showLabels && <span className="ml-1">Research</span>}
        </Button>
      )}
    </div>
  )
}

export default SystemItemActions
