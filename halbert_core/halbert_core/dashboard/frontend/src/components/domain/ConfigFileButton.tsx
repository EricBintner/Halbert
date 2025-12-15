/**
 * ConfigFileButton - Consistent button to open/edit config files
 * 
 * Provides a standardized UI for config file editing across all pages.
 * Uses the global config editor via halbert:open-config-editor event.
 * 
 * Usage:
 *   <ConfigFileButton path="/etc/samba/smb.conf" />
 *   <ConfigFileButton path="/etc/btrbk/btrbk.conf" label="Edit Backup Config" />
 *   <ConfigFileButton path={configPath} variant="icon" />
 */

import { Button } from '@/components/ui/button'
import { FileCode, Pencil, ExternalLink, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ConfigFileButtonProps {
  /** Path to the config file */
  path: string
  
  /** 
   * Button label (default: "Edit Config" for full, filename for compact)
   * Set to empty string to show only icon
   */
  label?: string
  
  /** 
   * Appearance variant:
   * - 'full': Full button with icon and label (default)
   * - 'compact': Smaller button
   * - 'icon': Icon only
   * - 'inline': Inline text style for use within text
   */
  variant?: 'full' | 'compact' | 'icon' | 'inline'
  
  /** Size for button variants */
  size?: 'sm' | 'default' | 'lg'
  
  /** Icon to use (default: FileCode) */
  icon?: 'file' | 'pencil' | 'settings' | 'external'
  
  /** Show the file path as tooltip (default: true) */
  showTooltip?: boolean
  
  /** Additional CSS classes */
  className?: string
  
  /** Click handler override (default: opens config editor) */
  onClick?: () => void
  
  /**
   * Start a new chat conversation when opening config editor (default: true)
   * Set to false when opening from within an existing chat
   */
  startNewChat?: boolean
  
  /** Optional context name for the chat (e.g., "nginx config") */
  contextName?: string
}

const iconMap = {
  file: FileCode,
  pencil: Pencil,
  settings: Settings,
  external: ExternalLink,
}

export function ConfigFileButton({
  path,
  label,
  variant = 'full',
  size = 'sm',
  icon = 'file',
  showTooltip = true,
  className,
  onClick,
  startNewChat = true,
  contextName,
}: ConfigFileButtonProps) {
  const IconComponent = iconMap[icon]
  
  // Extract filename for display
  const filename = path.split('/').pop() || path
  
  // Determine display label based on variant
  const displayLabel = label !== undefined 
    ? label 
    : variant === 'compact' 
      ? filename 
      : 'Edit Config'
  
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    
    if (onClick) {
      onClick()
    } else {
      // Start a new chat conversation if requested (default behavior)
      if (startNewChat) {
        const name = contextName || filename
        window.dispatchEvent(new CustomEvent('halbert:open-chat', {
          detail: {
            title: `Editing ${name}`,
            type: 'config',
            context: `Editing config file: \`${path}\`\n\nI can help you modify this config file. Just tell me what changes you'd like to make.`,
            configPath: path,
            newConversation: true,
          }
        }))
      }
      
      // Open the global config editor
      window.dispatchEvent(new CustomEvent('halbert:open-config-editor', {
        detail: { filePath: path }
      }))
    }
  }
  
  // Icon-only variant
  if (variant === 'icon') {
    return (
      <Button
        variant="ghost"
        size={size}
        className={cn("h-8 w-8 p-0", className)}
        title={showTooltip ? `Edit ${path}` : undefined}
        onClick={handleClick}
      >
        <IconComponent className="h-4 w-4" />
      </Button>
    )
  }
  
  // Inline variant (text-style link)
  if (variant === 'inline') {
    return (
      <button
        className={cn(
          "inline-flex items-center gap-1 text-primary hover:underline cursor-pointer",
          "text-sm font-medium",
          className
        )}
        title={showTooltip ? `Edit ${path}` : undefined}
        onClick={handleClick}
      >
        <IconComponent className="h-3.5 w-3.5" />
        <span className="font-mono text-xs">{filename}</span>
      </button>
    )
  }
  
  // Full and compact variants
  return (
    <Button
      variant="ghost"
      size={size}
      className={cn(
        variant === 'compact' && "text-xs h-7 px-2",
        className
      )}
      title={showTooltip ? `Edit ${path}` : undefined}
      onClick={handleClick}
    >
      <IconComponent className={cn("mr-1.5", variant === 'compact' ? "h-3.5 w-3.5" : "h-4 w-4")} />
      {displayLabel}
    </Button>
  )
}

/**
 * Utility to extract config path from discovery data
 * Checks multiple common locations for config_path
 */
export function getConfigPath(discovery: { 
  config_path?: string
  data?: { config_path?: string }
}): string | null {
  return discovery.config_path || discovery.data?.config_path || null
}
