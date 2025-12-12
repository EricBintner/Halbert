/**
 * UsageBar - Percentage progress bar with automatic color coding
 * 
 * Provides consistent usage visualization for storage, memory, etc.
 * Auto-colors based on thresholds: normal → warning → critical
 * 
 * Usage:
 *   <UsageBar percent={75} />
 *   <UsageBar percent={92} used="92GB" total="100GB" />
 *   <UsageBar percent={45} showPercent={false} height="sm" />
 */

import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

export interface UsageBarProps {
  /** Usage percentage (0-100) */
  percent: number
  /** Used amount label (e.g., "45GB") */
  used?: string
  /** Total amount label (e.g., "100GB") */
  total?: string
  /** Show percentage label (default: true) */
  showPercent?: boolean
  /** Warning threshold percentage (default: 75) */
  warningThreshold?: number
  /** Critical threshold percentage (default: 90) */
  criticalThreshold?: number
  /** Bar height variant */
  height?: 'sm' | 'default'
  /** Additional CSS classes */
  className?: string
}

export function UsageBar({
  percent,
  used,
  total,
  showPercent = true,
  warningThreshold = 75,
  criticalThreshold = 90,
  height = 'default',
  className,
}: UsageBarProps) {
  // Clamp percent to 0-100
  const clampedPercent = Math.min(100, Math.max(0, percent))
  
  // Determine color based on thresholds
  const getIndicatorColor = () => {
    if (clampedPercent >= criticalThreshold) return 'bg-red-500'
    if (clampedPercent >= warningThreshold) return 'bg-yellow-500'
    return '' // Use default primary color
  }
  
  const indicatorColor = getIndicatorColor()
  const heightClass = height === 'sm' ? 'h-1.5' : 'h-2'
  
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 relative">
        <Progress
          value={clampedPercent}
          className={cn(heightClass, "bg-muted")}
        />
        {/* Overlay colored indicator */}
        {indicatorColor && (
          <div 
            className={cn(
              "absolute top-0 left-0 rounded-full transition-all",
              heightClass,
              indicatorColor
            )}
            style={{ width: `${clampedPercent}%` }}
          />
        )}
      </div>
      {showPercent && (
        <span className={cn(
          "text-muted-foreground tabular-nums",
          height === 'sm' ? 'text-xs w-10' : 'text-sm w-12',
          "text-right"
        )}>
          {Math.round(clampedPercent)}%
        </span>
      )}
      {used && total && (
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {used} / {total}
        </span>
      )}
    </div>
  )
}

export default UsageBar
