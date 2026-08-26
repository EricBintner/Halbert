// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * GroupedDiscoveryCard - Fused card for multiple discoveries sharing a config
 * 
 * Phase 24: Discovery Consolidation
 * 
 * Renders multiple related discoveries in a single card with:
 * - Shared header showing the tool/type and config file
 * - Individual entries for each discovery with their own status
 * - Shared actions at the bottom
 * 
 * Usage:
 *   <GroupedDiscoveryCard
 *     title="Btrbk Backups"
 *     icon={<Archive />}
 *     configPath="/etc/btrbk/btrbk.conf"
 *     items={btrbkBackups}
 *     renderItem={(item) => <BackupEntry backup={item} />}
 *   />
 */

import { ReactNode } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfigFileButton, getConfigPath } from './ConfigFileButton'
import { cn } from '@/lib/utils'

export interface GroupedItem {
  id: string
  name: string
  title?: string
  description?: string
  status?: string
  severity?: string
  config_path?: string
  data?: Record<string, unknown>
}

export interface GroupedDiscoveryCardProps<T extends GroupedItem> {
  /** Title for the card header (e.g., "Btrbk Backups", "Samba Shares") */
  title: string
  
  /** Icon for the header */
  icon?: ReactNode
  
  /** Shared config file path - displayed in header */
  configPath?: string
  
  /** Array of items to display */
  items: T[]
  
  /** Render function for each item */
  renderItem: (item: T, index: number, isLast: boolean) => ReactNode
  
  /** Optional actions section at the bottom */
  actions?: ReactNode
  
  /** Show item count badge (default: true) */
  showCount?: boolean
  
  /** Subtitle/description for the card */
  subtitle?: string
  
  /** Additional CSS classes */
  className?: string
  
  /** Header variant: 'default' or 'compact' */
  headerVariant?: 'default' | 'compact'
}

export function GroupedDiscoveryCard<T extends GroupedItem>({
  title,
  icon,
  configPath,
  items,
  renderItem,
  actions,
  showCount = true,
  subtitle,
  className,
  headerVariant = 'default',
}: GroupedDiscoveryCardProps<T>) {
  // If only one item and no explicit config path, try to get from item
  const effectiveConfigPath = configPath || (items.length > 0 ? getConfigPath(items[0]) : null)
  
  return (
    <Card className={cn("overflow-hidden", className)}>
      {/* Fused Header */}
      <div className={cn(
        "flex items-center justify-between border-b",
        headerVariant === 'compact' ? "p-3 bg-muted/30" : "p-4 bg-muted/50"
      )}>
        <div className="flex items-center gap-2">
          {icon && <span className="shrink-0">{icon}</span>}
          <span className={cn(
            "font-semibold",
            headerVariant === 'compact' && "text-sm"
          )}>
            {title}
          </span>
          {showCount && items.length > 1 && (
            <Badge variant="outline" className="text-xs">
              {items.length} items
            </Badge>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {subtitle && (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          )}
          {effectiveConfigPath && (
            <ConfigFileButton 
              path={effectiveConfigPath} 
              variant="full"
              size="sm"
            />
          )}
        </div>
      </div>
      
      <CardContent className="p-0">
        {/* Render each item with dividers */}
        {items.map((item, index) => (
          <div 
            key={item.id} 
            className={cn(
              index < items.length - 1 && "border-b border-dashed"
            )}
          >
            {renderItem(item, index, index === items.length - 1)}
          </div>
        ))}
        
        {/* Shared Actions */}
        {actions && (
          <div className="border-t p-3 bg-muted/30 flex gap-2">
            {actions}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Utility: Group items by their group_key or config_path
 */
export interface GroupedResult<T> {
  key: string
  configPath: string | null
  items: T[]
}

export function groupByConfig<T extends GroupedItem>(
  items: T[],
  getGroupKey?: (item: T) => string | null
): GroupedResult<T>[] {
  const groups = new Map<string, GroupedResult<T>>()
  
  for (const item of items) {
    // Get group key from custom function or fall back to config_path
    const key = getGroupKey?.(item) ?? getConfigPath(item) ?? item.id
    
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        configPath: getConfigPath(item),
        items: [],
      })
    }
    groups.get(key)!.items.push(item)
  }
  
  return Array.from(groups.values())
}

/**
 * Utility: Check if items should be fused (multiple items with same config)
 */
export function shouldFuse<T extends GroupedItem>(items: T[]): boolean {
  if (items.length <= 1) return false
  
  const configPaths = new Set(
    items.map(i => getConfigPath(i)).filter(Boolean)
  )
  
  // Fuse if all items share the same config path
  return configPaths.size === 1
}
