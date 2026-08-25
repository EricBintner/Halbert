/**
 * AgentPanel Component
 * 
 * Main panel for interacting with the agent state machine.
 * Combines state display, plan checklist, tool executions, and response.
 */

import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, X, RotateCcw, AtSign } from 'lucide-react';
import { api } from '../../lib/api';
import { useDebug } from '../../contexts/DebugContext';
import { useAgentStream } from '../../hooks/useAgentStream';
import { StateBadge } from './StateBadge';
import { PlanChecklist } from './PlanChecklist';
import { ToolExecutionCard } from './ToolExecutionCard';
import { ConfirmationDialog } from './ConfirmationDialog';
import { ScanBlock } from './ScanBlock';
import { ContextBar } from './ContextBar';
import { TerminalAccordionDock } from './TerminalAccordionDock';
import { DiffBlock } from './DiffBlock';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { MarkdownRenderer } from '../domain/MarkdownRenderer';
import { ProactiveEventsBadge } from './ProactiveEventsBadge';

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  // Agent-specific fields
  state?: string;
  plan?: unknown[];
  toolExecutions?: unknown[];
  error?: string;
}

interface AgentPanelProps {
  className?: string;
  // Props for conversation persistence
  messages?: AgentMessage[];
  onMessagesChange?: (messages: AgentMessage[]) => void;
  sessionId?: string;
}

// Mentionable type
interface Mentionable {
  id: string;
  mention: string;
  name: string;
  type: string;
}

export function AgentPanel({ 
  className = '', 
  messages: externalMessages,
  onMessagesChange,
  sessionId: externalSessionId,
}: AgentPanelProps) {
  const [input, setInput] = useState('');
  // Use external messages if provided, otherwise local state
  const [localMessages, setLocalMessages] = useState<AgentMessage[]>([]);
  const messages = externalMessages ?? localMessages;
  const setMessages = onMessagesChange ?? setLocalMessages;
  const responseRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  
  // Debug logging
  const { addLog } = useDebug();
  
  // @mentions state
  const [mentionables, setMentionables] = useState<Mentionable[]>([]);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  
  const {
    session,
    isStreaming,
    response,
    thinking,
    sendMessage: sendAgentMessage,
    confirmAction,
    cancel,
    reset,
    applyDiff,
    rejectDiff,
  } = useAgentStream({
    onStateChange: (state, prev) => {
      addLog({ type: 'info', category: 'system', message: `Agent state: ${prev} → ${state}` });
    },
    onError: (error) => {
      addLog({ type: 'error', category: 'system', message: `Agent error: ${error}` });
    },
  });
  
  // Wrapper to add logging to sendMessage
  const sendMessage = (message: string, sessionId?: string) => {
    addLog({ type: 'request', category: 'chat', message: `Agent query: ${message.slice(0, 50)}...` });
    sendAgentMessage(message, sessionId);
  };

  // Auto-scroll response
  useEffect(() => {
    if (responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight;
    }
  }, [response]);
  
  // Load mentionables on mount
  useEffect(() => {
    api.getMentionables()
      .then(data => setMentionables(data.mentionables || []))
      .catch(err => console.error('Failed to load mentionables:', err));
  }, []);
  
  // Filter mentionables based on input
  const filteredMentionables = mentionables.filter(m =>
    m.mention.toLowerCase().includes(mentionFilter.toLowerCase()) ||
    m.name.toLowerCase().includes(mentionFilter.toLowerCase())
  ).slice(0, 6);
  
  // Handle input change with mention detection
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInput(value);
    
    const lastAtIndex = value.lastIndexOf('@');
    if (lastAtIndex !== -1 && lastAtIndex === value.length - 1) {
      setShowMentions(true);
      setMentionFilter('');
    } else if (lastAtIndex !== -1) {
      const afterAt = value.slice(lastAtIndex + 1);
      if (!afterAt.includes(' ')) {
        setShowMentions(true);
        setMentionFilter(afterAt.toLowerCase());
      } else {
        setShowMentions(false);
      }
    } else {
      setShowMentions(false);
    }
  };
  
  // Insert mention into input
  const insertMention = (mentionable: Mentionable) => {
    const lastAtIndex = input.lastIndexOf('@');
    const newInput = input.slice(0, lastAtIndex) + mentionable.mention + ' ';
    setInput(newInput);
    setShowMentions(false);
    inputRef.current?.focus();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    
    // Store user message before sending
    const userMsg: AgentMessage = {
      id: 'user-' + Date.now(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };
    setMessages([...messages, userMsg]);
    
    sendMessage(input.trim(), externalSessionId);
    setInput('');
  };
  
  // Clear messages on reset
  const handleReset = () => {
    reset();
    setMessages([]);
  };
  
  // Store assistant response when streaming completes
  useEffect(() => {
    if (!isStreaming && response && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      // Only add if last message was from user (avoid duplicates)
      if (lastMsg.role === 'user') {
        const assistantMsg: AgentMessage = {
          id: 'assistant-' + Date.now(),
          role: 'assistant',
          content: response,
          timestamp: Date.now(),
          state: session?.state,
          plan: session?.plan,
          toolExecutions: session?.toolExecutions,
          error: session?.error || undefined,
        };
        setMessages([...messages, assistantMsg]);
      }
    }
  }, [isStreaming, response]);

  const handleConfirm = () => {
    if (session?.pendingConfirmation) {
      confirmAction(session.pendingConfirmation.actionId, true);
    }
  };

  const handleReject = () => {
    if (session?.pendingConfirmation) {
      confirmAction(session.pendingConfirmation.actionId, false);
    }
  };

  return (
    <div className={`flex flex-col h-full bg-background ${className}`}>
      {/* Compact Header - matches chat conversation selector */}
      <div className="px-3 py-2 border-b bg-muted/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {session && <StateBadge state={session.state} size="sm" />}
            {session && session.confidence > 0 && (
              <ConfidenceIndicator 
                confidence={session.confidence} 
                cragAction={session.cragAction || 'PENDING'}
                size="sm"
                showLabel={false}
              />
            )}
          </div>
          <div className="flex items-center gap-1">
            <ProactiveEventsBadge />
            {isStreaming && (
              <button
                onClick={cancel}
                className="flex items-center gap-1 px-2 py-1 text-xs text-destructive hover:bg-accent rounded transition-colors"
              >
                <X className="h-3 w-3" />
                Cancel
              </button>
            )}
            <button
              onClick={handleReset}
              className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors"
            >
              <RotateCcw className="h-3 w-3" />
              Reset
            </button>
          </div>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 overflow-hidden flex">
        {/* Left: Response and thinking */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Thinking (collapsible) */}
          {thinking && (
            <details className="border-b">
              <summary className="px-3 py-1.5 text-xs text-muted-foreground cursor-pointer hover:bg-accent/50">
                <Loader2 className="inline h-3 w-3 mr-1.5 animate-spin" />
                Thinking...
              </summary>
              <pre className="px-3 py-2 text-xs text-muted-foreground bg-muted/50 max-h-24 overflow-auto">
                {thinking}
              </pre>
            </details>
          )}

          {/* Response Area */}
          <div 
            ref={responseRef}
            className="flex-1 p-3 overflow-auto space-y-3"
          >
            {/* Empty state */}
            {messages.length === 0 && !isStreaming && (
              <div className="text-muted-foreground text-center text-xs mt-4">
                Ask me anything about your system...
              </div>
            )}
            
            {/* Messages (user and assistant) */}
            {messages.map((msg, idx) => (
              <div key={msg.id} className="space-y-2">
                {/* User message */}
                {msg.role === 'user' && (
                  <div className="flex justify-end">
                    <div className="max-w-[85%] bg-primary text-primary-foreground px-3 py-2 rounded-lg text-xs">
                      {msg.content}
                    </div>
                  </div>
                )}
                
                {/* Stored assistant message */}
                {msg.role === 'assistant' && (
                  <div className="max-w-[95%] rounded-lg px-3 py-2 text-xs bg-muted whitespace-pre-wrap">
                    {msg.content}
                  </div>
                )}
                
                {/* Live agent response (only for last user message while streaming) */}
                {msg.role === 'user' && idx === messages.length - 1 && session && (
                  <div className="space-y-2">
                    {/* Active Scan */}
                    {session.activeScan && (
                      <ScanBlock
                        source={session.activeScan.source}
                        query={session.activeScan.query}
                        isComplete={session.activeScan.isComplete}
                        resultsCount={session.activeScan.results}
                      />
                    )}
                    
                    {/* Context Bar */}
                    {session.contextItems && session.contextItems.length > 0 && (
                      <ContextBar items={session.contextItems.map(item => ({
                        id: item.id,
                        type: (item.source === 'rag' ? 'file' : item.source === 'memory' ? 'memory' : item.source === 'web' ? 'web' : 'search') as 'file' | 'search' | 'memory' | 'web' | 'directory',
                        label: item.label,
                        tokens: item.tokens,
                      }))} />
                    )}
                    
                    {/* Diff Proposals */}
                    {session.diffProposals && session.diffProposals.map((diff) => (
                      <DiffBlock
                        key={diff.id}
                        filePath={diff.filePath}
                        oldContent={diff.oldContent}
                        newContent={diff.newContent}
                        additions={diff.additions}
                        deletions={diff.deletions}
                        status={diff.status}
                        onApply={() => applyDiff(diff.id)}
                        onReject={() => rejectDiff(diff.id)}
                      />
                    ))}
                    
                    {/* Response */}
                    {response ? (
                      <div className="max-w-[95%] rounded-lg px-3 py-2 text-xs bg-muted">
                        <MarkdownRenderer text={response} compact />
                        {isStreaming && <span className="inline-block w-1.5 h-3 bg-primary animate-pulse ml-0.5" />}
                      </div>
                    ) : isStreaming ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Processing...
                      </div>
                    ) : null}
                    
                    {/* Error */}
                    {session.error && (
                      <div className="p-2 bg-destructive/10 border border-destructive/30 rounded text-destructive text-xs">
                        {session.error}
                      </div>
                    )}

                    {/* Terminal sessions dock (E1f) */}
                    <TerminalAccordionDock />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Mention Autocomplete */}
          {showMentions && filteredMentionables.length > 0 && (
            <div className="mx-2 mb-1 bg-popover border rounded-md shadow-lg max-h-32 overflow-y-auto">
              {filteredMentionables.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className="w-full px-3 py-1.5 text-left hover:bg-accent flex items-center gap-2 text-xs"
                  onClick={() => insertMention(m)}
                >
                  <AtSign className="h-3 w-3 text-muted-foreground" />
                  <span className="font-medium">{m.mention}</span>
                  <span className="text-muted-foreground text-[10px]">{m.type}</span>
                </button>
              ))}
            </div>
          )}

          {/* Input - matches chat input style */}
          <form onSubmit={handleSubmit} className="p-2 border-t">
            <div className="flex gap-1.5 items-stretch">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={handleInputChange}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setShowMentions(false);
                }}
                placeholder="Ask... (@ to mention)"
                disabled={isStreaming}
                className="flex-1 px-2 py-1.5 rounded-md border bg-background text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="submit"
                disabled={isStreaming || !input.trim()}
                className="h-[30px] w-[30px] flex items-center justify-center bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isStreaming ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Send className="h-3 w-3" />
                )}
              </button>
            </div>
          </form>
        </div>

        </div>
      
      {/* Plan/Tools shown inline when present */}
      {session && (session.plan.length > 0 || session.toolExecutions.length > 0) && (
        <div className="border-t p-2 space-y-2 bg-muted/20 max-h-32 overflow-auto">
          {session.plan.length > 0 && (
            <PlanChecklist 
              plan={session.plan} 
              currentStep={session.currentStep} 
            />
          )}
          {session.toolExecutions.length > 0 && (
            <div className="space-y-1">
              <h4 className="text-xs font-medium text-muted-foreground">Tools</h4>
              {session.toolExecutions.slice(-3).map((exec) => (
                <ToolExecutionCard 
                  key={exec.executionId} 
                  execution={exec} 
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Confirmation Dialog */}
      {session?.pendingConfirmation && (
        <ConfirmationDialog
          confirmation={session.pendingConfirmation}
          onConfirm={handleConfirm}
          onReject={handleReject}
        />
      )}
    </div>
  );
}

export default AgentPanel;
