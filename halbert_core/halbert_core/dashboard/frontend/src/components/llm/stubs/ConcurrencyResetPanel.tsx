// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Stub for ConcurrencyResetPanel — not used in Halbert (no scheduler).
 * Rendered as null so the Pipeline Activity section's reset button is hidden.
 */
export interface ConcurrencyResetPanelProps {
  cloudNodeIds: string[];
  baseUrl: string;
  className?: string;
}

export function ConcurrencyResetPanel(_props: ConcurrencyResetPanelProps): null {
  return null;
}
