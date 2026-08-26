// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Stub for LLMAssignmentsPipeline — mapped mode pipeline visualization.
 * Halbert uses structured mode only, so this renders a placeholder.
 */
import type { LLMAssignmentBlock } from '@/types/llm';

export interface LLMAssignmentsPipelineProps {
  blocks: LLMAssignmentBlock[];
  fileCount?: number;
  className?: string;
}

export function LLMAssignmentsPipeline(_props: LLMAssignmentsPipelineProps): null {
  return null;
}
