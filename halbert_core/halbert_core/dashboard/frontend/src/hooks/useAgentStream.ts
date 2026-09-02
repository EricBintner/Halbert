// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Agent Stream Hook
 * 
 * React hook for interacting with the agent state machine via SSE.
 * Based on research5.md Part 8.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { apiUrl } from '@/lib/apiBase';
import { terminalSessionStore } from './useTerminalSessions';
import type { TerminalBlock } from './useTerminalSessions';
import { announce } from '@/lib/announce';
import { useTokenBuffer } from './useTokenBuffer';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type AgentState =
  | 'idle'
  | 'planning'
  | 'searching'
  | 'reading'
  | 'executing'
  | 'observing'
  | 'reflecting'
  | 'responding'
  | 'awaiting_confirmation'
  | 'error';

export type CRAGAction = 'CORRECT' | 'INCORRECT' | 'AMBIGUOUS' | 'PENDING';

export interface PlanStep {
  step: string;
  tool?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
}

export interface ToolExecution {
  executionId: string;
  tool: string;
  args: Record<string, unknown>;
  status: 'running' | 'success' | 'error';
  result?: unknown;
  error?: string;
}

export interface ConfirmationRequest {
  actionId: string;
  tool: string;
  description: string;
  riskLevel: string;
}

export interface ScanInfo {
  source: 'rag' | 'memory' | 'web' | 'file';
  query?: string;
  fileCount?: number;
  isComplete: boolean;
  results?: number;
}

export interface ContextLoadedItem {
  id: string;
  source: string;
  label: string;
  count: number;
  tokens?: number;
}

export interface DiffProposal {
  id: string;
  filePath: string;
  oldContent?: string;
  newContent: string;
  additions: number;
  deletions: number;
  status: 'pending' | 'applied' | 'rejected';
}

export interface SomaticBlockEvent {
  block_type: string;
  block_id: string;
  status: string;
  finding_id?: string;
  proposal_id?: string;
  approval_request_id?: string;
  action_id?: string;
  reflection_id?: string;
}

export interface SubagentEvent {
  type: string; // spawned | at_capacity | completed | failed | cancelled | ...
  handle_id: string;
  agent_type?: string;
  status?: string;
  result_block_id?: string;
}

export interface AgentSession {
  sessionId: string;
  state: AgentState;
  plan: PlanStep[];
  currentStep: number;
  loopCount: number;
  confidence: number;
  cragAction: CRAGAction;
  toolExecutions: ToolExecution[];
  pendingConfirmation: ConfirmationRequest | null;
  error: string | null;
  activeScan: ScanInfo | null;
  contextItems: ContextLoadedItem[];
  diffProposals: DiffProposal[];
  // A2c/C1d/D1c: lifecycle + status event streams (E1f)
  conversationStatus?: string | null;
  somaticBlocks?: SomaticBlockEvent[];
  subagentEvents?: SubagentEvent[];
  /** Terminal sessions opened during this turn, oldest first (E1f). */
  terminalSessions?: string[];
  /** Subject the server put this turn in (thread_started). */
  thread?: { threadId: string; title: string; unread?: boolean } | null;
  /**
   * Earlier subject pulled into this turn (thread_recalled), one at most.
   * `lastTurnId` is that thread's most recent turn — where the chip jumps.
   */
  recalled?: {
    threadId: string;
    title: string;
    date: string;
    matchTerms: string[];
    lastTurnId: string | null;
  } | null;
  /** Server turn id once the user row is stored (turn_persisted). */
  turnId?: string | null;
  /**
   * Task cards completed this turn (Plan C `task_completed`). Plan B defines
   * the factory; the hook only mirrors them so the Tasks column can move a
   * card to Finished.
   */
  tasks?: { block_id: string; owner: string; completed: boolean }[];
  /** Phase 2: the engine's modality decision for this turn. */
  modality?: ModalityInfo | null;
  /** Phase 2: speech segments emitted for voice delivery this turn. */
  speechSegments?: SpeechSegmentEvent[];
}

export interface StreamEvent {
  type: string;
  session_id: string;
  timestamp: number;
  [key: string]: unknown;
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

/**
 * Which model should answer this turn.
 *
 * Sent per message rather than held on the server, because one agent instance
 * is shared by every session — a selection stored server-side would leak
 * between conversations.
 *
 * `tier: 'auto'` is the absence of a pin, not a third mode; it is dropped
 * from the request body.
 */
export interface ModelSelection {
  /** Exact model name. Bypasses the complexity router entirely. */
  model?: string;
  /** Force a tier without naming a model. */
  tier?: 'guide' | 'specialist' | 'vision' | 'auto';
  /** Saved-endpoint id the model came from; disambiguates identical names. */
  endpointId?: string;
}

export interface UseAgentStreamOptions {
  onStateChange?: (state: AgentState, previousState: AgentState | null) => void;
  onToolStart?: (tool: string, args: Record<string, unknown>) => void;
  onToolComplete?: (executionId: string, success: boolean) => void;
  onConfirmationRequired?: (confirmation: ConfirmationRequest) => void;
  onError?: (error: string) => void;
  onComplete?: () => void;
}

/**
 * What actually answered this turn, as reported by the backend.
 *
 * The engine's routing decisions used to reach a log line and nothing else, so
 * an escalation to the specialist — or a pinned model being unreachable and the
 * guide answering instead — was invisible to the person paying for it.
 */
export interface TurnModelInfo {
  model: string;
  endpoint: string;
  provider: string;
  tier: string;
  pinned: boolean;
  escalated: boolean;
  reason: string;
  /** The model that was asked for but could not be reached, when one fell back. */
  fallbackFrom?: string;
}

export interface UseAgentStreamReturn {
  session: AgentSession | null;
  isStreaming: boolean;
  response: string;
  thinking: string;
  provenance: ProvenanceRef[];
  moduleInvocations: ModuleInvocation[];
  /** Null until the backend reports the model for the current turn. */
  turnModel: TurnModelInfo | null;
  /**
   * `sessionId` names ONE TURN, not a conversation to reopen: the server
   * resolves the subject thread. Omit it and a fresh id is minted per send.
   */
  sendMessage: (message: string, sessionId?: string, selection?: ModelSelection, images?: string[]) => void;
  confirmAction: (actionId: string, confirmed: boolean) => void;
  applyDiff: (diffId: string) => void;
  rejectDiff: (diffId: string) => void;
  cancel: () => void;
  reset: () => void;
  /** Drop a context chip locally (the server is told separately, if at all). */
  dismissContextItem: (id: string) => void;
}

// Phase 8: Provenance and module invocation types
export interface ProvenanceRef {
  type: 'log_cursor' | 'snapshot_id' | 'metric_window' | 'path_lines' | 'memory_id' | 'observation_id';
  ref: string;
  label: string;
  url?: string;
}

export interface ModuleInvocation {
  module: string;
  props: Record<string, any>;
}

// Phase 2 modality wiring: the engine's modality decision + speech segments.
export type ResponseModality = 'text' | 'voice' | 'mixed' | 'deferred';

export interface ModalityInfo {
  /** The engine's recommended delivery modality for this turn. */
  modality: ResponseModality;
  /** Markdown-stripped text to speak (redacted in multi-occupant mode). */
  speechText: string;
  /** Full markdown to render on screen (always lossless). */
  displayText: string;
}

export interface SpeechSegmentEvent {
  text: string;
  role: string; // 'persona' | 'narrator' | 'cameo' | 'thought' | 'silent'
  prosody: {
    rate: number;
    volume: number;
    whisper: boolean;
  };
}

// A store failure is logged once per page load; the turn still answers and
// the timeline just will not show it after a reload (spec §12).
let storeErrorWarned = false;

/**
 * Terminal events (E1f) drive the shared terminal-session store rather than
 * React state, so the tiles in the conversation and the rows in the accordion
 * dock are the same live sessions.
 *
 * This runs *outside* the setSession updater on purpose: updaters must be pure
 * (React 18 StrictMode invokes them twice), and appending output twice would
 * duplicate every chunk on screen.
 */
export function applyTerminalEvent(event: StreamEvent): void {
  const terminalId = event.terminal_session_id as string | undefined;
  if (!terminalId) return;

  switch (event.type) {
    case 'terminal_spawn': {
      const info = {
        command: (event.command as string) ?? '',
        pid: (event.pid as number) ?? 0,
        sandboxed: !!event.sandboxed,
        cwd: (event.cwd as string | undefined) ?? undefined,
        originSessionId: event.session_id,
        blockId: (event.block_id as string | undefined) ?? undefined,
        owner: (event.owner as string | undefined) ?? undefined,
      };
      // 'ws' means a real PTY the backend session manager owns — attach a
      // socket for full duplex. Otherwise the output rides this SSE stream.
      if (event.attach === 'ws') {
        terminalSessionStore.attach(terminalId, info);
      } else {
        terminalSessionStore.adopt(terminalId, info);
      }
      break;
    }
    case 'terminal_output':
      terminalSessionStore.appendOutput(terminalId, (event.data as string) ?? '');
      break;
    case 'terminal_complete':
      terminalSessionStore.complete(
        terminalId,
        typeof event.exit_code === 'number' ? event.exit_code : -1,
      );
      break;
    case 'terminal_block': {
      const block: TerminalBlock = {
        block_id: (event.block_id as string) ?? '',
        owner: (event.owner as string) ?? '',
        status: 'running',
        isTaskCard: !!event.promote,
        label: (event.label as string | undefined) ?? undefined,
      };
      terminalSessionStore.addBlock(terminalId, block);
      break;
    }
    case 'terminal_block_promote':
      terminalSessionStore.promoteBlock(terminalId, (event.block_id as string) ?? '');
      break;
    case 'terminal_needs_input':
      terminalSessionStore.setBlockNeedsAttention(
        terminalId,
        (event.block_id as string) ?? '',
      );
      break;
  }
}

export function useAgentStream(options: UseAgentStreamOptions = {}): UseAgentStreamReturn {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  // rAF buffering: LLMs emit 30-80 tokens/sec but the screen refreshes at
  // ~60 Hz. Writing each token to React state as it arrives causes one
  // re-render per token and O(n^2) string concatenation. Instead, chunks
  // accumulate in the buffer hook and flush to state once per animation
  // frame — at most 60 commits a second regardless of generation speed.
  const {
    value: response,
    push: appendResponse,
    flush: flushResponse,
    set: setResponse,
    clear: clearResponse,
  } = useTokenBuffer();
  const {
    value: thinking,
    push: appendThinking,
    flush: flushThinking,
    clear: clearThinking,
  } = useTokenBuffer();
  const [provenance, setProvenance] = useState<ProvenanceRef[]>([]);
  const [moduleInvocations, setModuleInvocations] = useState<ModuleInvocation[]>([]);
  const [turnModel, setTurnModel] = useState<TurnModelInfo | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // The immediate flush every stream end goes through: committed text is
  // never left waiting on a frame that may not come (a backgrounded tab
  // throttles rAF to zero while the stream still completes).
  const flushNow = useCallback(() => {
    flushResponse();
    flushThinking();
  }, [flushResponse, flushThinking]);

  // Mirror of isStreaming for the unmount cleanup, which cannot read state.
  const isStreamingRef = useRef(false);
  useEffect(() => { isStreamingRef.current = isStreaming; }, [isStreaming]);

  // Abort a turn the user walked away from, on unmount and ONLY on unmount.
  //
  // This used to depend on [isStreaming], which meant React ran the cleanup
  // on the true -> false transition as well — that is, on every normal
  // completion — with the captured isStreaming still true. So each finished
  // turn aborted its own stream and POSTed /api/agent/cancel, and the
  // backend could persist a fully streamed reply as cancelled (R11-01). An
  // explicit cancel() sent two.
  //
  // With [] the effect runs once, so eventSourceRef has to be read at
  // cleanup time rather than captured — which is safe here for the reason it
  // was not before: there is no re-render after an unmount, so there is no
  // newly-started fetch to abort by mistake.
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      if (sessionIdRef.current && isStreamingRef.current) {
        fetch(apiUrl(`/api/agent/cancel/${sessionIdRef.current}`), { method: 'POST' })
          .catch(() => {}); // Ignore errors on cleanup
      }
    };
  }, []);

  const initSession = useCallback((sessionId: string) => {
    setSession({
      sessionId,
      // 'planning', not 'idle': initSession is only called when a turn is
      // being sent (sendMessage / confirmAction). The backend's first
      // state_change event takes a few seconds to arrive over SSE; showing
      // 'idle' during that gap makes it look like nothing happened.
      state: 'planning',
      plan: [],
      currentStep: 0,
      loopCount: 0,
      confidence: 0,
      cragAction: 'PENDING',
      toolExecutions: [],
      pendingConfirmation: null,
      error: null,
      activeScan: null,
      contextItems: [],
      diffProposals: [],
      terminalSessions: [],
      thread: null,
      recalled: null,
      turnId: null,
      tasks: [],
      modality: null,
      speechSegments: [],
    });
    sessionIdRef.current = sessionId;
  }, []);

  const handleEvent = useCallback((event: StreamEvent) => {
    if (
      event.type === 'terminal_spawn' ||
      event.type === 'terminal_output' ||
      event.type === 'terminal_complete' ||
      event.type === 'terminal_block' ||
      event.type === 'terminal_block_promote' ||
      event.type === 'terminal_needs_input'
    ) {
      applyTerminalEvent(event);
    }

    // Blocked on approval is the one thing said assertively (design §11).
    // Outside the updater: updaters must stay pure (StrictMode runs them
    // twice), and this must be said exactly once.
    if (event.type === 'tool_confirmation_required') {
      announce('Waiting for your approval', { assertive: true });
    }

    // Streamed text parks in the rAF buffers — one commit per frame, not
    // one per token — and the stream's end flushes whatever is left so no
    // tail is lost waiting on a frame. Both outside the updater, same
    // purity rule as the announcement above.
    if (event.type === 'response_chunk') {
      appendResponse(event.content as string);
    } else if (event.type === 'thinking') {
      appendThinking(event.content as string);
    } else if (event.type === 'response_complete') {
      flushNow();
    }

    // The state-change callback is how the surface announces progress
    // (AgentChat maps the state to a sentence for the shell's live region),
    // so it must fire exactly once per event — outside the updater, where
    // StrictMode cannot double it.
    if (event.type === 'state_change') {
      options.onStateChange?.(
        event.state as AgentState,
        event.previous_state as AgentState | null,
      );
    }

    setSession(prev => {
      if (!prev) return prev;

      switch (event.type) {
        case 'state_change':
          return { ...prev, state: event.state as AgentState };

        case 'plan':
          return { 
            ...prev, 
            plan: (event.steps as PlanStep[]) || [] 
          };

        case 'plan_step_update':
          const updatedPlan = [...prev.plan];
          const stepIndex = event.step_index as number;
          if (updatedPlan[stepIndex]) {
            updatedPlan[stepIndex] = {
              ...updatedPlan[stepIndex],
              status: event.status as PlanStep['status']
            };
          }
          return { ...prev, plan: updatedPlan };

        case 'model_selected':
          // A fallback is the one thing about model selection that is not
          // ordinary: the admin asked for one model and got another, possibly
          // at a different price and certainly with different behaviour. It is
          // said here rather than from the notice that shows it, because this
          // event arrives once per turn while that notice mounts twice.
          if (event.fallback_from) {
            announce(
              `${event.fallback_from as string} was unavailable. ` +
              `${event.model as string} answered instead.`,
            );
          }
          setTurnModel({
            model: event.model as string,
            endpoint: event.endpoint as string,
            provider: event.provider as string,
            tier: event.tier as string,
            pinned: Boolean(event.pinned),
            escalated: Boolean(event.escalated),
            reason: (event.reason as string) || '',
            fallbackFrom: (event.fallback_from as string) || undefined,
          });
          return prev;

        case 'confidence_update':
          return { 
            ...prev, 
            confidence: event.confidence as number,
            cragAction: event.crag_action as CRAGAction
          };

        case 'tool_start':
          const newExecution: ToolExecution = {
            executionId: event.execution_id as string,
            tool: event.tool as string,
            args: event.args as Record<string, unknown>,
            status: 'running'
          };
          options.onToolStart?.(newExecution.tool, newExecution.args);
          return {
            ...prev,
            toolExecutions: [...prev.toolExecutions, newExecution]
          };

        case 'tool_complete':
          const executions = prev.toolExecutions.map(exec => {
            if (exec.executionId === event.execution_id) {
              return {
                ...exec,
                status: (event.success ? 'success' : 'error') as ToolExecution['status'],
                result: event.result,
                error: event.error as string | undefined
              };
            }
            return exec;
          });
          options.onToolComplete?.(event.execution_id as string, event.success as boolean);
          return { ...prev, toolExecutions: executions };

        case 'tool_confirmation_required':
          const confirmation: ConfirmationRequest = {
            actionId: event.execution_id as string,
            tool: event.tool as string,
            description: event.description as string,
            riskLevel: event.risk_level as string
          };
          options.onConfirmationRequired?.(confirmation);
          return { ...prev, pendingConfirmation: confirmation };

        case 'response_complete':
          // The buffered stream text was flushed before this updater ran
          // (see above); the final committed content replaces it, and the
          // buffer's `set` drops any draft left for a frame that will now
          // never matter.
          // Tolerate provenance riding on the completion event as well as
          // the dedicated response_provenance event.
          if (Array.isArray(event.provenance)) {
            setProvenance(event.provenance as ProvenanceRef[]);
          }
          // The backend strips structured-action blocks (e.g. invoke_module
          // JSON) from the final committed text; adopt it so the rendered
          // bubble never shows the raw JSON tail that streamed in chunks.
          if (typeof event.content === 'string' && event.content.length > 0) {
            setResponse(event.content);
          }
          setIsStreaming(false);
          options.onComplete?.();
          return prev;

        case 'response_provenance':
          setProvenance(event.provenance as ProvenanceRef[] || []);
          return prev;

        case 'module_invoke':
          setModuleInvocations(prev => [...prev, {
            module: event.module as string,
            props: event.props as Record<string, any> || {},
          }]);
          return prev;

        case 'error':
          const errorMsg = event.message as string;
          options.onError?.(errorMsg);
          // Stop streaming — an error event is terminal. Without this, the
          // UI keeps pulsing "responding" if the backend sends error
          // without a subsequent session_ended.
          setIsStreaming(false);
          return { ...prev, error: errorMsg, state: 'error' };

        case 'loop_warning':
          return { 
            ...prev, 
            loopCount: event.loop_count as number 
          };

        case 'session_ended':
          setIsStreaming(false);
          options.onComplete?.();
          return { ...prev, state: 'idle', activeScan: null };

        case 'scan_start':
          return {
            ...prev,
            activeScan: {
              source: event.source as ScanInfo['source'],
              query: event.query as string | undefined,
              fileCount: event.file_count as number | undefined,
              isComplete: false,
            }
          };

        case 'scan_complete':
          return {
            ...prev,
            activeScan: prev.activeScan ? {
              ...prev.activeScan,
              isComplete: true,
              results: event.results as number | undefined,
            } : null
          };

        case 'context_loaded':
          const newContextItem: ContextLoadedItem = {
            id: `ctx-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            source: event.source as string,
            label: event.label as string || event.source as string,
            count: event.count as number || 1,
            tokens: event.tokens as number | undefined,
          };
          return {
            ...prev,
            contextItems: [...prev.contextItems, newContextItem],
            activeScan: null,
          };

        case 'diff_proposal':
          const newDiff: DiffProposal = {
            id: event.diff_id as string || `diff-${Date.now()}`,
            filePath: event.file_path as string,
            oldContent: event.old_content as string | undefined,
            newContent: event.new_content as string,
            additions: event.additions as number || 0,
            deletions: event.deletions as number || 0,
            status: 'pending',
          };
          return {
            ...prev,
            diffProposals: [...prev.diffProposals, newDiff],
          };

        case 'diff_applied':
          return {
            ...prev,
            diffProposals: prev.diffProposals.map(d =>
              d.id === event.diff_id ? { ...d, status: 'applied' as const } : d
            ),
          };

        case 'diff_rejected':
          return {
            ...prev,
            diffProposals: prev.diffProposals.map(d =>
              d.id === event.diff_id ? { ...d, status: 'rejected' as const } : d
            ),
          };

        // A2c: user-facing conversation status (in_progress/blocked/waiting/...)
        case 'conversation_status':
          return { ...prev, conversationStatus: (event.status as string) ?? null };

        // C1d: somatic block phase/status change
        case 'somatic_block':
          return {
            ...prev,
            somaticBlocks: [...(prev.somaticBlocks ?? []), {
              block_type: event.block_type as string,
              block_id: event.block_id as string,
              status: event.status as string,
              finding_id: event.finding_id as string | undefined,
              proposal_id: event.proposal_id as string | undefined,
              approval_request_id: event.approval_request_id as string | undefined,
              action_id: event.action_id as string | undefined,
              reflection_id: event.reflection_id as string | undefined,
            }],
          };

        // E1f: a terminal came alive inside this turn. The store already has
        // it (applyTerminalEvent above); record the id so the conversation can
        // render its tile inline.
        case 'terminal_spawn': {
          const terminalId = event.terminal_session_id as string;
          if (!terminalId || (prev.terminalSessions ?? []).includes(terminalId)) {
            return prev;
          }
          return {
            ...prev,
            terminalSessions: [...(prev.terminalSessions ?? []), terminalId],
          };
        }

        case 'terminal_output':
        case 'terminal_complete':
          // Output and exit live in the terminal store, not in session state.
          return prev;

        // Plan B: somatic blocks live in the terminal store (applyTerminalEvent
        // above). The session only needs to know about promoted task cards so
        // the conversation can render them inline.
        case 'terminal_block':
        case 'terminal_block_promote':
        case 'terminal_needs_input':
          return prev;

        // Plan C: a task card finished. Plan B defines the factory; the hook
        // mirrors it so the Tasks column can move the card to Finished, light
        // the StatusLight, and mark the thread unread.
        case 'task_completed': {
          const blockId = (event.block_id as string) ?? '';
          const owner = (event.owner as string) ?? '';
          console.log('[AGENT] task_completed:', blockId, owner);
          // Mark the block completed in the terminal store as well.
          const tid = event.terminal_session_id as string | undefined;
          if (tid) terminalSessionStore.completeBlock(tid, blockId);
          return {
            ...prev,
            thread: prev.thread
              ? { ...prev.thread, unread: true } as AgentSession['thread']
              : prev.thread,
            tasks: [...(prev.tasks ?? []), { block_id: blockId, owner, completed: true }],
          };
        }

        // D1c: subagent lifecycle event
        case 'subagent_event':
          return {
            ...prev,
            subagentEvents: [...(prev.subagentEvents ?? []), {
              type: event.subagent_event as string,
              handle_id: event.handle_id as string,
              agent_type: event.agent_type as string | undefined,
              status: event.status as string | undefined,
              result_block_id: event.result_block_id as string | undefined,
            }],
          };

        // Plan A continuity: the server owns thread identity. The hook only
        // mirrors what it was told so the label and the chip can follow.
        case 'thread_started': {
          // A new subject pauses the previous one, and whatever was pulled
          // into the previous one expires with it (spec §6): no thread chip
          // survives a thread_started.
          return {
            ...prev,
            thread: {
              threadId: event.thread_id as string,
              title: (event.title as string) ?? '',
            },
            recalled: null,
            contextItems: prev.contextItems.filter((item) => item.source !== 'thread'),
          };
        }

        case 'thread_recalled': {
          const threadId = event.thread_id as string;
          const title = (event.title as string) ?? '';
          const date = (event.date as string) ?? '';
          const matchTerms = Array.isArray(event.match_terms) ? (event.match_terms as string[]) : [];
          const lastTurnId =
            typeof event.last_turn_id === 'string' && event.last_turn_id ? event.last_turn_id : null;
          // Max one thread chip: a second recall replaces the first.
          const others = prev.contextItems.filter((item) => item.source !== 'thread');
          return {
            ...prev,
            recalled: { threadId, title, date, matchTerms, lastTurnId },
            contextItems: [
              ...others,
              { id: `thread:${threadId}`, source: 'thread', label: `pulled in: ${title} · ${date}`, count: 1 },
            ],
          };
        }

        case 'turn_persisted': {
          return { ...prev, turnId: (event.turn_id as string) ?? null };
        }

        case 'thread_store_error': {
          if (!storeErrorWarned) {
            storeErrorWarned = true;
            console.warn('[AGENT] thread store error (turn still answered):', event.message);
          }
          return prev;
        }

        // Phase 2 modality wiring: the engine's modality decision for
        // this turn. The frontend uses this to show a modality badge and
        // route speech segments to the audio playback component.
        case 'modality_resolved': {
          const modality = (event.modality as ResponseModality) ?? 'text';
          const speechText = (event.speech_text as string) ?? '';
          const displayText = (event.display_text as string) ?? '';
          return {
            ...prev,
            modality: { modality, speechText, displayText },
          };
        }

        // Phase 2: a speech segment emitted for voice delivery. The
        // frontend's audio component plays these in order; the text
        // channel renders displayText from modality_resolved instead.
        case 'speech_segment': {
          const prosodyData = event.prosody as
            | { rate?: number; volume?: number; whisper?: boolean }
            | undefined;
          const seg: SpeechSegmentEvent = {
            text: (event.text as string) ?? '',
            role: (event.role as string) ?? 'persona',
            prosody: {
              rate: prosodyData?.rate ?? 1.0,
              volume: prosodyData?.volume ?? 1.0,
              whisper: prosodyData?.whisper ?? false,
            },
          };
          return {
            ...prev,
            speechSegments: [...(prev.speechSegments ?? []), seg],
          };
        }

        default:
          return prev;
      }
    });
  }, [options]);

  const sendMessage = useCallback((message: string, sessionId?: string, selection?: ModelSelection, images?: string[]) => {
    // Close existing connection
    eventSourceRef.current?.close();
    
    // Reset state
    setIsStreaming(true);
    clearResponse();
    setTurnModel(null);
    clearThinking();
    setProvenance([]);
    setModuleInvocations([]);
    // A session id names ONE TURN, never a conversation. Continuity is the
    // server's job: it resolves the subject thread itself and tells us which
    // one it chose (thread_started / turn_persisted), so a fresh id per send
    // is correct here. A stable id would be actively wrong — the timeline
    // falls back to `local-${sessionId}` for any turn the server never
    // persisted (lib/turnFromSession), and two turns sharing one id collide
    // in the transcript. An explicit id names the single turn being sent.
    const sid = sessionId || crypto.randomUUID();
    initSession(sid);

    // Use fetch with POST for SSE (EventSource only supports GET)
    const controller = new AbortController();
    
    // Connection timeout — 5 minutes is the sensible default for local and
    // network LLMs. The old GPU Tweaks localStorage override was removed;
    // httpx on the backend handles retry/timeout policy.
    const CONNECTION_TIMEOUT = 300 * 1000;
    let lastDataTime = Date.now();
    let timeoutCheckInterval: ReturnType<typeof setInterval> | null = null;
    
    const startTimeoutCheck = () => {
      timeoutCheckInterval = setInterval(() => {
        const timeSinceLastData = Date.now() - lastDataTime;
        if (timeSinceLastData > CONNECTION_TIMEOUT) {
          const timeoutMin = Math.round(CONNECTION_TIMEOUT / 60000);
          console.error(`Connection timeout - no data received for ${timeoutMin} minutes`);
          controller.abort();
          setIsStreaming(false);
          setSession(prev => prev ? { 
            ...prev, 
            state: 'error',
            error: `Connection timed out after ${timeoutMin} min. Try increasing timeout in Settings > AI > Performance Tweaks.` 
          } : null);
          options.onError?.('Connection timed out');
          if (timeoutCheckInterval) clearInterval(timeoutCheckInterval);
        }
      }, 10000); // Check every 10 seconds
    };
    
    const stopTimeoutCheck = () => {
      if (timeoutCheckInterval) {
        clearInterval(timeoutCheckInterval);
        timeoutCheckInterval = null;
      }
    };
    
    // Engine defaults — the backend owns max_tokens and temperature policy.
    const maxTokens = 8192;
    const temperature = 0.7;
    
    fetch(apiUrl('/api/agent/message'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        session_id: sid,
        max_tokens: maxTokens,
        temperature: temperature,
        // Base64-encoded images for the vision model. Omitted when no images
        // are attached so the backend keeps its automatic text routing.
        ...(images && images.length > 0 ? { images } : {}),
        // Omitted entirely when the user has not pinned anything, so the
        // backend keeps its automatic routing.
        ...(selection?.model ? { model: selection.model } : {}),
        ...(selection?.tier && selection.tier !== 'auto'
          ? { tier: selection.tier }
          : {}),
        ...(selection?.endpointId ? { endpoint_id: selection.endpointId } : {}),
      }),
      signal: controller.signal
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('No response body');
      }
      
      // Start timeout monitoring
      startTimeoutCheck();
      
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        // Update last data time on any data received
        lastDataTime = Date.now();
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as StreamEvent;
              handleEvent(data);
            } catch (err) {
              // Ignore parse errors for partial data
            }
          }
        }
      }
      
      stopTimeoutCheck();
      flushNow();
      setIsStreaming(false);
    }).catch((err) => {
      stopTimeoutCheck();
      if (err.name !== 'AbortError') {
        console.error('Agent stream error:', err);
        flushNow();
        setIsStreaming(false);
        setSession(prev => prev ? { ...prev, state: 'error', error: err.message || 'Connection error' } : null);
        options.onError?.(err.message || 'Connection error');
      }
    });
    
    // Store abort controller for cancel functionality
    eventSourceRef.current = { close: () => { stopTimeoutCheck(); controller.abort(); } } as EventSource;
  }, [initSession, handleEvent, options, flushNow]);

  const confirmAction = useCallback((actionId: string, confirmed: boolean) => {
    if (!sessionIdRef.current) return;

    // Close existing connection
    eventSourceRef.current?.close();

    setIsStreaming(true);

    // Clear pending confirmation
    setSession(prev => prev ? { ...prev, pendingConfirmation: null } : null);

    // Create new SSE connection for confirmation
    const controller = new AbortController();
    const url = apiUrl(`/api/agent/confirm/${sessionIdRef.current}`);

    // Store the controller so cancel() can abort the confirmation stream.
    // Without this, the Stop button is dead during a confirmation response
    // and isStreaming stays true forever.
    eventSourceRef.current = {
      close: () => { controller.abort(); },
    } as EventSource;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId, confirmed }),
      signal: controller.signal,
    }).then(response => {
      if (!response.ok) {
        throw new Error(`Confirmation failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      const readStream = async () => {
        if (!reader) return;

        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as StreamEvent;
                handleEvent(data);
              } catch (err) {
                // Ignore parse errors for partial data
              }
            }
          }
        }

        flushNow();
        setIsStreaming(false);
      };

      readStream();
    }).catch(err => {
      if (err.name === 'AbortError') return; // User cancelled, not an error
      console.error('Confirmation error:', err);
      flushNow();
      setIsStreaming(false);
      setSession(prev => prev ? { ...prev, error: String(err) } : null);
    });
  }, [handleEvent, flushNow]);

  const cancel = useCallback(() => {
    eventSourceRef.current?.close();
    setIsStreaming(false);

    // Flush any buffered text so it lands in the response before the turn
    // is folded. The flush empties the buffers and cancels the pending
    // frame, so nothing leaks into the next turn either.
    flushNow();

    if (sessionIdRef.current) {
      fetch(apiUrl(`/api/agent/cancel/${sessionIdRef.current}`), { method: 'POST' })
        .catch(err => console.error('Cancel error:', err));
    }
  }, [flushNow]);

  const reset = useCallback(() => {
    cancel();
    // One conversation: terminals belong to the timeline, not to this hook's
    // local state, so a reset never clears the store (there is no "New
    // Conversation" any more — see hooks/useTerminalSessions clearOrigin,
    // which stays for the dock's own use). reset() now only drops the live
    // turn: the session, its stream state and the model that answered it.
    setSession(null);
    clearResponse();
    setTurnModel(null);
    clearThinking();
    setProvenance([]);
    setModuleInvocations([]);
    sessionIdRef.current = null;
  }, [cancel, clearResponse, clearThinking]);

  const dismissContextItem = useCallback((id: string) => {
    setSession(prev => prev ? {
      ...prev,
      contextItems: prev.contextItems.filter(item => item.id !== id),
      recalled: prev.recalled && `thread:${prev.recalled.threadId}` === id ? null : prev.recalled,
    } : null);
  }, []);

  const applyDiff = useCallback((diffId: string) => {
    if (!sessionIdRef.current) return;
    
    // Optimistically update local state
    setSession(prev => prev ? {
      ...prev,
      diffProposals: prev.diffProposals.map(d =>
        d.id === diffId ? { ...d, status: 'applied' as const } : d
      ),
    } : null);
    
    // Send to backend
    fetch(apiUrl(`/api/agent/diff/${sessionIdRef.current}/${diffId}/apply`), { method: 'POST' })
      .catch(err => console.error('Apply diff error:', err));
  }, []);

  const rejectDiff = useCallback((diffId: string) => {
    if (!sessionIdRef.current) return;
    
    // Optimistically update local state
    setSession(prev => prev ? {
      ...prev,
      diffProposals: prev.diffProposals.map(d =>
        d.id === diffId ? { ...d, status: 'rejected' as const } : d
      ),
    } : null);
    
    // Send to backend
    fetch(apiUrl(`/api/agent/diff/${sessionIdRef.current}/${diffId}/reject`), { method: 'POST' })
      .catch(err => console.error('Reject diff error:', err));
  }, []);

  return {
    session,
    isStreaming,
    response,
    thinking,
    provenance,
    moduleInvocations,
    turnModel,
    sendMessage,
    confirmAction,
    applyDiff,
    rejectDiff,
    cancel,
    reset,
    dismissContextItem,
  };
}

export default useAgentStream;
