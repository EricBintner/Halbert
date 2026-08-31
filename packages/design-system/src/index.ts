// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

// Primitives
export { Button } from './primitives/Button'
export type { ButtonProps, ButtonVariant, ButtonSize } from './primitives/Button'
export { StatusBadge } from './primitives/StatusBadge'
export type { StatusBadgeProps, StatusTone } from './primitives/StatusBadge'
export { Input } from './primitives/Input'
export type { InputProps } from './primitives/Input'
export { Select } from './primitives/Select'
export type { SelectProps, SelectOption } from './primitives/Select'
export { ParametricSlider } from './primitives/ParametricSlider'
export type { ParametricSliderProps } from './primitives/ParametricSlider'
export { HalbertMark } from './primitives/HalbertMark'
export type {
  HalbertMarkProps,
  HalbertMarkDensity,
  HalbertMarkTone,
} from './primitives/HalbertMark'

// Voice Mode (audio-reactive mark engine)
export * from './voice'

export { WhyChip } from './primitives/WhyChip'
export type { WhyChipProps, ProvenanceRef } from './primitives/WhyChip'
export { StatusLight } from './primitives/StatusLight'
export type { StatusLightProps, StatusLightState } from './primitives/StatusLight'
export { EmptyState } from './primitives/EmptyState'
export type { EmptyStateProps } from './primitives/EmptyState'
export { ModuleLoadError } from './primitives/ModuleLoadError'
export type { ModuleLoadErrorProps } from './primitives/ModuleLoadError'
export { Collapsible, CollapsibleGroup } from './primitives/Collapsible'
export type { CollapsibleProps, CollapsibleGroupProps } from './primitives/Collapsible'

// Surfaces
export { AppWindow } from './surfaces/AppWindow'
export type { AppWindowProps } from './surfaces/AppWindow'
export { MetricCard } from './surfaces/MetricCard'
export type { MetricCardProps } from './surfaces/MetricCard'
export { ThinkingPanel } from './surfaces/ThinkingPanel'
export type { ThinkingPanelProps } from './surfaces/ThinkingPanel'
export { DiffBlock, DiffSummary } from './surfaces/DiffBlock'
export type { DiffBlockProps, DiffSummaryProps } from './surfaces/DiffBlock'
export { NavRail } from './surfaces/NavRail'
export type { NavRailProps, NavRailSection, NavRailItem } from './surfaces/NavRail'

// Utilities
export { cx } from './lib'
