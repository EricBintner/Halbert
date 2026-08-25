/**
 * Hooks barrel export
 * 
 * Phase 20D: Shared hooks for common patterns
 * Phase 36: Agent stream hook for state machine
 */

export { useScanPage, type ScanType } from './useScanPage'
export { useCopyToClipboard } from './useCopyToClipboard'
export {
  useAgentStream,
  type AgentState,
  type CRAGAction,
  type PlanStep,
  type ToolExecution,
  type AgentSession,
  type ConfirmationRequest,
  type ScanInfo,
  type ContextLoadedItem,
  type DiffProposal,
  type UseAgentStreamOptions,
  type UseAgentStreamReturn,
} from './useAgentStream'
export {
  useTerminalSessions,
  type TerminalSession,
  type TerminalSessionStatus,
  type SpawnOptions,
  type UseTerminalSessions,
} from './useTerminalSessions'
