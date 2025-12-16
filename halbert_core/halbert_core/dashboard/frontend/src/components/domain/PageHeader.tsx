/**
 * PageHeader - Consistent page header with title, description, and actions
 * 
 * Phase 20D: Extracted common pattern from page components
 * 
 * Features:
 * - Icon + title
 * - Description text
 * - Action buttons (typically scan/refresh)
 * - Consistent spacing
 */

import React from 'react'
import { Button } from '@/components/ui/button'
import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  /** Icon to display next to title */
  icon: React.ReactNode
  /** Page title */
  title: string
  /** Description text below title */
  description?: string
  /** Whether a scan/refresh is in progress */
  scanning?: boolean
  /** Callback for scan/refresh button */
  onScan?: () => void
  /** Custom scan button text */
  scanText?: string
  /** Additional action buttons */
  actions?: React.ReactNode
  /** Hide the default scan button */
  hideScanButton?: boolean
}

export function PageHeader({
  icon,
  title,
  description,
  scanning = false,
  onScan,
  scanText = 'Scan',
  actions,
  hideScanButton = false,
}: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          {icon}
          {title}
        </h1>
        {description && (
          <p className="text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        {!hideScanButton && onScan && (
          <Button variant="outline" onClick={onScan} disabled={scanning}>
            <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
            {scanning ? 'Scanning...' : scanText}
          </Button>
        )}
      </div>
    </div>
  )
}

export default PageHeader
