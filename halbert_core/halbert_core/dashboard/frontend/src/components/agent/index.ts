// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Agent Components
 * 
 * React components for the agent state machine UI.
 * Phase 36: State machine visualization.
 */

export { StateBadge } from './StateBadge';
export { PlanChecklist } from './PlanChecklist';
export { ToolExecutionCard } from './ToolExecutionCard';
export { ConfirmationDialog } from './ConfirmationDialog';
export { AgentPanel, type AgentMessage } from './AgentPanel';
export { ThinkingPanel } from './ThinkingPanel';
export { ConfidenceIndicator, CircularConfidence } from './ConfidenceIndicator';
// Cascade-style components
export { ScanBlock, type ScanSource } from './ScanBlock';
export { ContextBar, ContextPill, ContextPreview, type ContextItem, type ContextType } from './ContextBar';
export { DiffBlock, DiffSummary } from './DiffBlock';
export { AgentChat } from './AgentChat';

export { TerminalTile } from './TerminalTile'
export { TerminalAccordionDock } from './TerminalAccordionDock'
