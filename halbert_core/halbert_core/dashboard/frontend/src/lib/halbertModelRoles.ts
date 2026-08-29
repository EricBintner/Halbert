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
  { id: 'secure_model', label: 'Secure (Local)', description: 'Local-only model for sensitive operations', requiresLocal: true, optional: true },
]

/** The role the composer speaks to, and what the pill reports when unpinned. */
export const CHAT_ROLE_ID = 'chat_model'

export const modelPickerTransport = createModelPickerTransport()
