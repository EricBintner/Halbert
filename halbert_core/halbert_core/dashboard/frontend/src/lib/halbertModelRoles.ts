// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { AppRole } from '@halbert/model-picker'
import { createModelPickerTransport } from './modelPickerTransport'

/**
 * Halbert's four runtime roles, and the one transport that serves them.
 *
 * Both picker surfaces read from here — the settings drawer and the in-chat
 * pill — so a role's copy or capability filter can never say one thing in
 * Settings and another in the composer.
 *
 * The transport is a module singleton on purpose: `useModelPicker` keys its
 * load effect on the reference it is handed, so a fresh instance per render
 * would reload the configuration on every render.
 */
export const HALBERT_MODEL_ROLES: AppRole[] = [
  { id: 'chat_model', label: 'Chat (Guide)', description: 'Quick system commands & diagnostics', requiresTools: true },
  { id: 'specialist_model', label: 'Specialist', description: 'Deep reasoning & multi-step plans', optional: true },
  { id: 'vision_model', label: 'Vision', description: 'Screenshot & hardware sensor analysis', requiresVision: true, optional: true },
  { id: 'secure_model', label: 'Secure (Local)', description: 'Local-only model for sensitive operations', requiresLocal: true, optional: true, variants: ['sysadmin'] },
]

/**
 * The roles this instance's variant should offer, filtered host-side before
 * they reach the picker.
 *
 * A role tagged with `variants` exists only on the variants it names — the
 * secure slot has no meaning on a home instance, where no local model runs
 * and a sensitive turn falls through to the local-guide/fail-closed chain
 * rather than a dedicated model. An untagged role exists everywhere.
 *
 * A variant that never arrived (the info route failed, the payload was
 * malformed) keeps every role rather than dropping some: the host picker
 * must not go dark because one route answered nothing. The cost is one
 * render pass on a home instance before the filter lands — the settings
 * drawer renders asynchronously anyway, so the row disappears before the
 * user can act on it.
 */
export function halbertRolesForVariant(variant: string | null | undefined): AppRole[] {
  if (!variant) return HALBERT_MODEL_ROLES
  return HALBERT_MODEL_ROLES.filter(
    (role) => !role.variants || role.variants.includes(variant),
  )
}

/** The role the composer speaks to, and what the pill reports when unpinned. */
export const CHAT_ROLE_ID = 'chat_model'

export const modelPickerTransport = createModelPickerTransport()
