/**
 * EmptyState - Consistent "no items found" placeholder
 * 
 * Usage:
 *   <EmptyState
 *     icon={<Archive className="h-12 w-12" />}
 *     title="No Backups Discovered"
 *     description="Click Scan to discover backup configurations."
 *     action={<Button onClick={handleScan}>Scan Now</Button>}
 *   />
 */

import { Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface EmptyStateProps {
  /** Custom icon (default: Inbox) */
  icon?: React.ReactNode
  /** Title text (e.g., "No Backups Found") */
  title: string
  /** Description text */
  description?: string
  /** Action button or element */
  action?: React.ReactNode
  /** Additional CSS classes */
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-12 px-4 text-center",
      className
    )}>
      <div className="text-muted-foreground mb-4">
        {icon || <Inbox className="h-12 w-12" />}
      </div>
      <h3 className="text-lg font-medium mb-2">{title}</h3>
      {description && (
        <p className="text-muted-foreground mb-4 max-w-sm">{description}</p>
      )}
      {action && (
        <div className="mt-2">{action}</div>
      )}
    </div>
  )
}

export default EmptyState
