// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/*
 * A headless model picker: local discovery, bring-your-own-key endpoints, role
 * assignment and per-turn tier control, with no styling of its own.
 *
 * Two rules keep it portable between hosts:
 *   1. No role names — the host passes its own slots and the package renders
 *      whatever it is handed.
 *   2. No I/O — every read and write goes through the injected transport.
 *
 * Re-exports only; importing this module has no side effects.
 */

export * from './types'

export { useModelPicker } from './useModelPicker'
export type {
  UseModelPickerOptions,
  UseModelPickerResult,
} from './useModelPicker'

export { matchModels, scoreMatch } from './match'

export { ModelSelectorPill, useModelPillState } from './primitives/ModelSelectorPill'
export type {
  ModelPillState,
  ModelSelectorPillProps,
} from './primitives/ModelSelectorPill'

export { QuickSwitchPopover } from './primitives/QuickSwitchPopover'
export type { QuickSwitchPopoverProps } from './primitives/QuickSwitchPopover'

export { RoleAssignmentRow } from './primitives/RoleAssignmentRow'
export type { RoleAssignmentRowProps } from './primitives/RoleAssignmentRow'

export { ProviderCard } from './primitives/ProviderCard'
export type { ProviderCardProps } from './primitives/ProviderCard'

export { ModelSettingsDrawer } from './primitives/ModelSettingsDrawer'
export type {
  ModelSettingsDrawerClassNames,
  ModelSettingsDrawerProps,
  ProviderGroupId,
} from './primitives/ModelSettingsDrawer'
