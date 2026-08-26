// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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

// Phase 52: ChromaDB Storage Management
export { ChromaDBSettings } from './ChromaDBSettings'

// Dataset Download Manager
export { DatasetManager } from './DatasetManager'

// Phase 54: Data Version and Freshness
export { DataVersionCard } from './DataVersionCard'
