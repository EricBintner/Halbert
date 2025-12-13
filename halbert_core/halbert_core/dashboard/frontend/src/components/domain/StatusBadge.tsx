/**
 * StatusBadge - Severity-colored status badge
 * 
 * Provides consistent color coding for status indicators across all pages.
 * 
 * Usage:
 *   <StatusBadge status="Running" severity="success" />
 *   <StatusBadge status="Warning" severity="warning" showIcon />
 *   <StatusBadge status="Failed" severity="critical" />
 */

import { Badge } from '@/components/ui/badge'
import { 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  Info, 
  HelpCircle 
} from 'lucide-react'
import { cn } from '@/lib/utils'

export type Severity = 'success' | 'warning' | 'critical' | 'info' | 'unknown'

export interface StatusBadgeProps {
  /** Display text (e.g., "Running", "Failed", "Active") */
  status: string
  /** Severity level for color coding */
  severity: Severity | string
  /** Show status icon (default: false) */
  showIcon?: boolean
  /** Size variant */
  size?: 'sm' | 'default'
  /** Additional CSS classes */
  className?: string
}

const severityStyles: Record<string, string> = {
  success: 'bg-green-500/15 text-green-700 border-green-500/40 dark:bg-green-900/40 dark:text-green-300 dark:border-green-600',
  warning: 'bg-yellow-500/15 text-yellow-700 border-yellow-500/40 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-600',
  critical: 'bg-red-500/15 text-red-700 border-red-500/40 dark:bg-red-900/40 dark:text-red-300 dark:border-red-600',
  info: 'bg-sky-500/15 text-sky-700 border-sky-500/40 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-600',
  unknown: 'bg-muted text-muted-foreground border-border',
}

const severityIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  success: CheckCircle,
  warning: AlertTriangle,
  critical: XCircle,
  info: Info,
  unknown: HelpCircle,
}

export function StatusBadge({
  status,
  severity,
  showIcon = false,
  size = 'default',
  className,
}: StatusBadgeProps) {
  // Normalize severity to known values
  const normalizedSeverity = severity in severityStyles ? severity : 'unknown'
  const Icon = severityIcons[normalizedSeverity]
  
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'
  
  return (
    <Badge
      variant="outline"
      className={cn(
        severityStyles[normalizedSeverity],
        size === 'sm' && 'text-xs px-1.5 py-0 h-5',
        size === 'default' && 'text-xs px-2 py-0.5',
        className
      )}
    >
      {showIcon && <Icon className={cn(iconSize, "mr-1")} />}
      {status}
    </Badge>
  )
}

export default StatusBadge
