/**
 * Agent Stream Hook
 * 
 * React hook for interacting with the agent state machine via SSE.
 * Based on research5.md Part 8.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

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

export interface UseAgentStreamOptions {
  onStateChange?: (state: AgentState, previousState: AgentState | null) => void;
  onToolStart?: (tool: string, args: Record<string, unknown>) => void;
  onToolComplete?: (executionId: string, success: boolean) => void;
  onConfirmationRequired?: (confirmation: ConfirmationRequest) => void;
  onError?: (error: string) => void;
  onComplete?: () => void;
}

export interface UseAgentStreamReturn {
  session: AgentSession | null;
  isStreaming: boolean;
  response: string;
  thinking: string;
  provenance: ProvenanceRef[];
  moduleInvocations: ModuleInvocation[];
  sendMessage: (message: string, sessionId?: string) => void;
  confirmAction: (actionId: string, confirmed: boolean) => void;
  applyDiff: (diffId: string) => void;
  rejectDiff: (diffId: string) => void;
  cancel: () => void;
  reset: () => void;
}

// Phase 8: Provenance and module invocation types
export interface ProvenanceRef {
  type: 'log_cursor' | 'snapshot_id' | 'metric_window' | 'path_lines' | 'memory_id' | 'observation_id';
  ref: string;
  label: string;
  url: string;
}

export interface ModuleInvocation {
  module: string;
  props: Record<string, any>;
}

export function useAgentStream(options: UseAgentStreamOptions = {}): UseAgentStreamReturn {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [response, setResponse] = useState('');
  const [thinking, setThinking] = useState('');
  const [provenance, setProvenance] = useState<ProvenanceRef[]>([]);
  const [moduleInvocations, setModuleInvocations] = useState<ModuleInvocation[]>([]);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Cleanup on unmount - cancel backend request to prevent zombie processing
  useEffect(() => {
    return () => {
      // Close the SSE connection
      eventSourceRef.current?.close();
      
      // Cancel backend request if streaming
      if (sessionIdRef.current && isStreaming) {
        fetch(`/api/agent/cancel/${sessionIdRef.current}`, { method: 'POST' })
          .catch(() => {}); // Ignore errors on cleanup
      }
    };
  }, [isStreaming]);

  const initSession = useCallback((sessionId: string) => {
    setSession({
      sessionId,
      state: 'idle',
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
    });
    sessionIdRef.current = sessionId;
  }, []);

  const handleEvent = useCallback((event: StreamEvent) => {
    setSession(prev => {
      if (!prev) return prev;

      switch (event.type) {
        case 'state_change':
          const newState = event.state as AgentState;
          const prevState = event.previous_state as AgentState | null;
          options.onStateChange?.(newState, prevState);
          return { ...prev, state: newState };

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

        case 'response_chunk':
          console.log('[AGENT] response_chunk:', JSON.stringify(event.content));
          setResponse(r => r + (event.content as string));
          return prev;

        case 'thinking':
          setThinking(t => t + (event.content as string));
          return prev;

        case 'response_complete':
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
          return { ...prev, error: errorMsg };

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

        default:
          return prev;
      }
    });
  }, [options]);

  const sendMessage = useCallback((message: string, sessionId?: string) => {
    // Close existing connection
    eventSourceRef.current?.close();
    
    // Reset state
    setIsStreaming(true);
    setResponse('');
    setThinking('');
    setProvenance([]);
    setModuleInvocations([]);
    
    // Generate or use provided session ID
    const sid = sessionId || crypto.randomUUID();
    initSession(sid);

    // Use fetch with POST for SSE (EventSource only supports GET)
    const controller = new AbortController();
    
    // Timeout detection - configurable in Settings > AI > Performance Tweaks
    // Read from localStorage, default to 5 minutes (300 seconds)
    let timeoutSeconds = 300;
    try {
      const tweaks = localStorage.getItem('halbert_gpu_tweaks');
      if (tweaks) {
        const parsed = JSON.parse(tweaks);
        if (parsed.connectionTimeout) timeoutSeconds = parsed.connectionTimeout;
      }
    } catch {}
    const CONNECTION_TIMEOUT = timeoutSeconds * 1000;
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
    
    // Get performance tweaks from localStorage (set in Settings > AI > Performance Tweaks)
    let maxTokens = 8192;
    let temperature = 0.7;
    try {
      const tweaks = localStorage.getItem('halbert_gpu_tweaks');
      if (tweaks) {
        const parsed = JSON.parse(tweaks);
        if (parsed.maxTokens) maxTokens = parsed.maxTokens;
        if (parsed.temperature) temperature = parsed.temperature;
      }
    } catch {}
    
    fetch('/api/agent/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        session_id: sid,
        max_tokens: maxTokens,
        temperature: temperature,
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
      setIsStreaming(false);
    }).catch((err) => {
      stopTimeoutCheck();
      if (err.name !== 'AbortError') {
        console.error('Agent stream error:', err);
        setIsStreaming(false);
        setSession(prev => prev ? { ...prev, state: 'error', error: err.message || 'Connection error' } : null);
        options.onError?.(err.message || 'Connection error');
      }
    });
    
    // Store abort controller for cancel functionality
    eventSourceRef.current = { close: () => { stopTimeoutCheck(); controller.abort(); } } as EventSource;
  }, [initSession, handleEvent, options]);

  const confirmAction = useCallback((actionId: string, confirmed: boolean) => {
    if (!sessionIdRef.current) return;

    // Close existing connection
    eventSourceRef.current?.close();
    
    setIsStreaming(true);
    
    // Clear pending confirmation
    setSession(prev => prev ? { ...prev, pendingConfirmation: null } : null);

    // Create new SSE connection for confirmation
    const url = `/api/agent/confirm/${sessionIdRef.current}`;
    
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId, confirmed })
    }).then(response => {
      if (!response.ok) {
        throw new Error(`Confirmation failed: ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      const readStream = async () => {
        if (!reader) return;
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const text = decoder.decode(value);
          const lines = text.split('\n');
          
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
        
        setIsStreaming(false);
      };
      
      readStream();
    }).catch(err => {
      console.error('Confirmation error:', err);
      setIsStreaming(false);
      setSession(prev => prev ? { ...prev, error: String(err) } : null);
    });
  }, [handleEvent]);

  const cancel = useCallback(() => {
    eventSourceRef.current?.close();
    setIsStreaming(false);
    
    if (sessionIdRef.current) {
      fetch(`/api/agent/cancel/${sessionIdRef.current}`, { method: 'POST' })
        .catch(err => console.error('Cancel error:', err));
    }
  }, []);

  const reset = useCallback(() => {
    cancel();
    setSession(null);
    setResponse('');
    setThinking('');
    setProvenance([]);
    setModuleInvocations([]);
    sessionIdRef.current = null;
  }, [cancel]);

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
    fetch(`/api/agent/diff/${sessionIdRef.current}/${diffId}/apply`, { method: 'POST' })
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
    fetch(`/api/agent/diff/${sessionIdRef.current}/${diffId}/reject`, { method: 'POST' })
      .catch(err => console.error('Reject diff error:', err));
  }, []);

  return {
    session,
    isStreaming,
    response,
    thinking,
    provenance,
    moduleInvocations,
    sendMessage,
    confirmAction,
    applyDiff,
    rejectDiff,
    cancel,
    reset
  };
}

export default useAgentStream;
