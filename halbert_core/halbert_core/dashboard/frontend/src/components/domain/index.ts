/**
 * Domain Components - Phase 20 Component Library
 * 
 * Universal UI patterns for system item interactions.
 */

export { SystemItemActions, type SystemItem, type SystemItemActionsProps } from './SystemItemActions'
export { StatusBadge, type StatusBadgeProps } from './StatusBadge'
export { UsageBar, type UsageBarProps } from './UsageBar'
export { EmptyState, type EmptyStateProps } from './EmptyState'

// Phase 24: Discovery Consolidation Components
export { ConfigFileButton, getConfigPath, type ConfigFileButtonProps } from './ConfigFileButton'
export { 
  GroupedDiscoveryCard, 
  groupByConfig, 
  shouldFuse,
  type GroupedItem, 
  type GroupedDiscoveryCardProps,
  type GroupedResult 
} from './GroupedDiscoveryCard'

// Phase 20D: Shared Utilities
export { CodeBlock } from './CodeBlock'
export { MarkdownRenderer } from './MarkdownRenderer'
export { PageHeader, type PageHeaderProps } from './PageHeader'
