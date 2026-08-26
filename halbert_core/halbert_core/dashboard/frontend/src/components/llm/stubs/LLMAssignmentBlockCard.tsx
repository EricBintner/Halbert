// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Stub for LLMAssignmentBlockCard — mapped mode assignment card.
 * Halbert uses structured mode only, so this renders a placeholder.
 */
import type { PrepTaskId, SavedEndpoint, EndpointTestResult } from '@/types/llm';

export interface LLMAssignmentBlockCardProps {
  id: string;
  endpointId: string;
  model: string;
  tasks: PrepTaskId[];
  enableReasoning?: boolean;
  alwaysOn?: boolean;
  concurrency?: number;
  endpoints: SavedEndpoint[];
  availableModels: string[];
  loadingModels?: boolean;
  assignedTasks: PrepTaskId[];
  onEndpointChange: (blockId: string, endpointId: string) => void;
  onModelChange: (blockId: string, model: string) => void;
  onRefreshModels: (endpointId: string) => void;
  onAddTask: (blockId: string, taskId: PrepTaskId) => void;
  onRemoveTask: (blockId: string, taskId: PrepTaskId) => void;
  onEnableReasoningChange?: (blockId: string, enabled: boolean) => void;
  onAlwaysOnChange?: (blockId: string, alwaysOn: boolean) => void;
  onConcurrencyChange?: (blockId: string, concurrency: number) => void;
  onDelete: (blockId: string) => void;
  onTest?: (blockId: string) => void;
  testResult?: EndpointTestResult;
  testingConnection?: boolean;
  className?: string;
}

export function LLMAssignmentBlockCard(_props: LLMAssignmentBlockCardProps): null {
  return null;
}
