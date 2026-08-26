// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { LLMConfig } from '@/types/llm';

/**
 * Strip fields that should NOT drive the debounced auto-save change-detection:
 *
 * - `assignment_mode`: toggled locally in the Settings UI; committed via the
 *   explicit "Apply {mode}" button path (switchAssignmentMode API), not auto-save.
 * - `saved_endpoints`: endpoint CRUD handlers persist these directly via their
 *   own updateGlobalConfig calls. Re-persisting through the debounced path would
 *   double-save and trigger an unneeded pipeline swap_model cycle.
 * - `model_context_cache`: cache metadata refreshed on dropdown open / endpoint
 *   test. Not user-authored config; shouldn't cause persist or swap_model.
 *
 * Fields intentionally NOT stripped:
 * - `assignment_blocks`: block edits (endpoint/model/task reassignment inside a
 *   block) are user-authored and must auto-save. The mode toggle is protected by
 *   stripping `assignment_mode` alone; block content changes ride the auto-save path.
 */
export function stripModeFields(
  cfg: LLMConfig
): Omit<LLMConfig, 'assignment_mode' | 'saved_endpoints' | 'model_context_cache'> {
  const {
    assignment_mode: _m,
    saved_endpoints: _e,
    model_context_cache: _c,
    ...rest
  } = cfg;
  void _m; void _e; void _c;
  return rest;
}
