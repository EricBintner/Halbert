/**
 * AgentChat Component
 * 
 * Cascade-style chat that renders structured agent events.
 * Based on research2.md state machine workflow.
 * 
 * Phase 59: Enhanced with Chat feature parity:
 * - @mention autocomplete
 * - Vision/image support (drag/drop/paste)
 * - Message queue (type while busy)
 * - Code block rendering with run buttons
 * - Model loading status
 */

import { useState, useRef, useEffect } from 'react';
import { 
  Send, 
  StopCircle, 
  RotateCcw, 
  AtSign, 
  Terminal,
  Image as ImageIcon,
  X as XIcon,
  Camera,
  Plus,
  ChevronDown,
  MessageSquare,
  Trash2,
} from 'lucide-react';
import { useAgentStream } from '../../hooks/useAgentStream';
import { StateBadge } from './StateBadge';
import { PlanChecklist } from './PlanChecklist';
import { ToolExecutionCard } from './ToolExecutionCard';
import { ConfirmationDialog } from './ConfirmationDialog';
import { ThinkingPanel } from './ThinkingPanel';
import { WhyChip, type ProvenanceRef } from '../WhyChip';
import { ModuleRenderer } from '../ModuleRenderer';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ScanBlock } from './ScanBlock';
import { ContextBar } from './ContextBar';
import { DiffBlock } from './DiffBlock';
import { CodeBlock } from '../domain/CodeBlock';
import { cn } from '../../lib/utils';
import { api } from '../../lib/api';

interface UserMessage {
  id: string;
  content: string;
  timestamp: number;
  images?: string[];  // Base64 image data
}

interface AttachedImage {
  id: string;
  dataUrl: string;
  name: string;
}

interface Mentionable {
  id: string;
  mention: string;
  name: string;
  type: string;
}

interface AgentConversation {
  conversation_id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count?: number;
}

interface AgentChatProps {
  className?: string;
  onRunCommand?: (cmd: string) => Promise<{output?: string, error?: string, exit_code?: number}>;
}

// -----------------------------------------------------------------------------
// Provenance ref → module parsing (Phase 8 / T8a.3)
//
// Ref strings arrive from the backend in free-form shapes. Parse defensively:
// accept a JSON object, "source@cursor" / "source:cursor" for log refs, and
// "path:start-end" / "path:line" suffixes for path refs. Fall back to treating
// the whole ref as the source/path.
// -----------------------------------------------------------------------------

interface ExpandedProvenanceModule {
  key: string;
  label: string;
  module: string;
  props: Record<string, any>;
}

function parseLogRef(ref: string): { source?: string; cursor?: string } {
  try {
    const parsed = JSON.parse(ref);
    if (parsed && typeof parsed === 'object') {
      return {
        source: parsed.source ?? parsed.log ?? parsed.unit ?? parsed.service,
        cursor: parsed.cursor ?? parsed.pos ?? parsed.offset,
      };
    }
  } catch { /* not JSON */ }
  const atIdx = ref.indexOf('@');
  if (atIdx > 0) return { source: ref.slice(0, atIdx), cursor: ref.slice(atIdx + 1) };
  const colonIdx = ref.indexOf(':');
  if (colonIdx > 0) return { source: ref.slice(0, colonIdx), cursor: ref.slice(colonIdx + 1) };
  return { source: ref };
}

function parsePathRef(ref: string): { path?: string } {
  try {
    const parsed = JSON.parse(ref);
    if (parsed && typeof parsed === 'object') {
      const path = parsed.path ?? parsed.file ?? parsed.filename;
      if (typeof path === 'string') return { path };
    }
  } catch { /* not JSON */ }
  // Strip a trailing ":N" or ":N-M" line-range suffix, but only when what
  // precedes it looks like a path (avoids mangling "C:\..."-style strings).
  const m = ref.match(/^(.+?\/.*?):(\d+)(?:-(\d+))?$/);
  if (m) return { path: m[1] };
  return { path: ref };
}

// Helper to render message content with code blocks
function MessageContent({ 
  content, 
  onRunCommand 
}: { 
  content: string;
  onRunCommand?: (cmd: string) => Promise<{output?: string, error?: string, exit_code?: number}>;
}) {
  const parts: Array<{ type: 'text' | 'code', content: string, lang?: string }> = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  
  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    let codeContent = match[2].trim();
    codeContent = codeContent.replace(/^`+|`+$/g, '').trim();
    parts.push({ type: 'code', content: codeContent, lang: match[1] || 'bash' });
    lastIndex = match.index + match[0].length;
  }
  
  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) });
  }
  
  if (parts.length === 0) {
    parts.push({ type: 'text', content });
  }
  
  return (
    <div className="space-y-2 min-w-0 overflow-hidden">
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return (
            <CodeBlock 
              key={i} 
              code={part.content} 
              lang={part.lang || 'bash'} 
              onRun={onRunCommand}
              compact
            />
          );
        } else {
          return (
            <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
          );
        }
      })}
    </div>
  );
}

export function AgentChat({ className, onRunCommand }: AgentChatProps) {
  const [userMessages, setUserMessages] = useState<UserMessage[]>([]);
  const [input, setInput] = useState('');
  const [agentError, setAgentError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationDropdownRef = useRef<HTMLDivElement>(null);
  
  // Phase 59: Conversation management
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [showConversationList, setShowConversationList] = useState(false);
  const [conversationTitle, setConversationTitle] = useState('New Conversation');
  
  // Phase 59: @mention autocomplete
  const [mentionables, setMentionables] = useState<Mentionable[]>([]);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  
  // Phase 59: Vision/image support
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [isDraggingImage, setIsDraggingImage] = useState(false);
  
  // Phase 59: Message queue (type while busy)
  const [messageQueue, setMessageQueue] = useState<string[]>([]);

  // Phase 8 / T8a.3: modules expanded from provenance WhyChip clicks
  const [expandedProvenanceModules, setExpandedProvenanceModules] = useState<ExpandedProvenanceModule[]>([]);
  
  const {
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
    reset,
  } = useAgentStream({
    onStateChange: (state, prev) => {
      console.log('State:', prev, '->', state);
    },
    onToolStart: (tool, args) => {
      console.log('Tool start:', tool, args);
    },
    onError: (err) => {
      console.error('Agent error:', err);
      setAgentError(err);
    },
  });

  // Load mentionables and conversations on mount
  useEffect(() => {
    const loadMentionables = async () => {
      try {
        const data = await api.getMentionables();
        setMentionables(data.mentionables || []);
      } catch (error) {
        console.error('Failed to load mentionables:', error);
      }
    };
    loadMentionables();
    loadConversations();
  }, []);
  
  // Load conversations list
  const loadConversations = async () => {
    try {
      const data = await api.listAgentConversations();
      setConversations(data.conversations || []);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };
  
  // Load a specific conversation
  const loadConversation = async (convId: string) => {
    try {
      const data = await api.getAgentConversation(convId);
      if (data) {
        setCurrentConversationId(convId);
        setConversationTitle(data.title || 'Conversation');
        // Convert stored messages to UserMessage format
        const msgs: UserMessage[] = (data.messages || []).map((m: {role: string, content: string, timestamp?: number}, idx: number) => ({
          id: `loaded-${idx}`,
          content: m.content,
          timestamp: m.timestamp || Date.now(),
        })).filter((m: UserMessage) => m.content);
        setUserMessages(msgs);
        setShowConversationList(false);
        reset(); // Reset agent session for loaded conversation
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };
  
  // Start new conversation
  const startNewConversation = () => {
    setCurrentConversationId(null);
    setConversationTitle('New Conversation');
    setUserMessages([]);
    setShowConversationList(false);
    reset();
  };
  
  // Delete conversation
  const deleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteAgentConversation(convId);
      setConversations(prev => prev.filter(c => c.conversation_id !== convId));
      if (currentConversationId === convId) {
        startNewConversation();
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  // Click outside to close conversation dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (conversationDropdownRef.current && !conversationDropdownRef.current.contains(e.target as Node)) {
        setShowConversationList(false);
      }
    };
    if (showConversationList) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showConversationList]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [userMessages, response, session?.toolExecutions]);
  
  // Process queued messages when streaming completes
  useEffect(() => {
    if (!isStreaming && messageQueue.length > 0) {
      const nextMessage = messageQueue[0];
      setMessageQueue(prev => prev.slice(1));
      setInput(nextMessage);
      // Auto-send after a brief delay
      setTimeout(() => {
        const userMsg: UserMessage = {
          id: 'user-' + Date.now(),
          content: nextMessage,
          timestamp: Date.now(),
        };
        setUserMessages(prev => [...prev, userMsg]);
        sendMessage(nextMessage);
        setInput('');
      }, 100);
    }
  }, [isStreaming, messageQueue]);
  
  // Filter mentionables based on input
  const filteredMentionables = mentionables.filter(m => 
    m.mention.toLowerCase().includes(mentionFilter.toLowerCase()) ||
    m.name.toLowerCase().includes(mentionFilter.toLowerCase())
  ).slice(0, 8);

  // Image handling
  const processImageFile = (file: File): Promise<AttachedImage> => {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith('image/')) {
        reject(new Error('Not an image file'));
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        resolve({
          id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          dataUrl,
          name: file.name,
        });
      };
      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsDataURL(file);
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(false);
    
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length === 0) return;
    
    try {
      const newImages = await Promise.all(files.map(processImageFile));
      setAttachedImages(prev => [...prev, ...newImages]);
    } catch (err) {
      console.error('Failed to process dropped images:', err);
    }
  };

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const imageItems = items.filter(item => item.type.startsWith('image/'));
    
    if (imageItems.length === 0) return;
    
    e.preventDefault();
    
    for (const item of imageItems) {
      const file = item.getAsFile();
      if (file) {
        try {
          const image = await processImageFile(file);
          setAttachedImages(prev => [...prev, image]);
        } catch (err) {
          console.error('Failed to process pasted image:', err);
        }
      }
    }
  };

  const removeAttachedImage = (id: string) => {
    setAttachedImages(prev => prev.filter(img => img.id !== id));
  };
  
  // Input handling with @mention detection
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
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

  const insertMention = (mentionable: Mentionable) => {
    const lastAtIndex = input.lastIndexOf('@');
    const newInput = input.slice(0, lastAtIndex) + mentionable.mention + ' ';
    setInput(newInput);
    setShowMentions(false);
    inputRef.current?.focus();
  };

  // Phase 8 / T8a.3: clicking a provenance ref expands the source inline.
  // log_cursor / metric_window → evidence module; path_lines / snapshot_id →
  // config-diff module. memory_id / observation_id keep the chip popover.
  const handleProvenanceExpand = (provRef: ProvenanceRef) => {
    let expansion: Omit<ExpandedProvenanceModule, 'key'> | null = null;

    if (provRef.type === 'log_cursor' || provRef.type === 'metric_window') {
      const { source, cursor } = parseLogRef(provRef.ref);
      expansion = {
        label: provRef.label || provRef.ref,
        module: 'evidence',
        props: { source, cursor },
      };
    } else if (provRef.type === 'path_lines' || provRef.type === 'snapshot_id') {
      const { path } = parsePathRef(provRef.ref);
      expansion = {
        label: provRef.label || provRef.ref,
        module: 'config-diff',
        props: { path },
      };
    }

    if (!expansion) return;

    setExpandedProvenanceModules(prev => {
      const key = `${expansion.module}:${provRef.ref}`;
      if (prev.some(p => p.key === key)) return prev; // already expanded
      return [...prev, { key, ...expansion }];
    });
  };

  const dismissExpandedModule = (key: string) => {
    setExpandedProvenanceModules(prev => prev.filter(m => m.key !== key));
  };

  const handleSend = async () => {
    // Queue messages if streaming
    if (isStreaming && input.trim()) {
      setMessageQueue(prev => [...prev, input.trim()]);
      setInput('');
      return;
    }

    if ((!input.trim() && attachedImages.length === 0)) return;

    // Extract base64 data from attached images
    const imageData = attachedImages.map(img => {
      const base64Match = img.dataUrl.match(/^data:image\/\w+;base64,(.+)$/);
      return base64Match ? base64Match[1] : img.dataUrl;
    });

    const userMsg: UserMessage = {
      id: 'user-' + Date.now(),
      content: input.trim() || (imageData.length > 0 ? '[Image]' : ''),
      timestamp: Date.now(),
      images: imageData.length > 0 ? imageData : undefined,
    };

    setUserMessages(prev => [...prev, userMsg]);
    setAgentError(null);
    setAttachedImages([]);
    setExpandedProvenanceModules([]);

    // TODO: Pass images to agent backend when vision support is added
    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showMentions) {
      e.preventDefault();
      handleSend();
    } else if (e.key === 'Escape') {
      setShowMentions(false);
    }
  };
  
  // Auto-resize textarea
  const autoResizeTextarea = () => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }
  };
  
  useEffect(() => {
    if (!input && inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input]);

  const handleReset = () => {
    reset();
    setAgentError(null);
    setExpandedProvenanceModules([]);
  };

  return (
    <div className={cn('flex flex-col h-full bg-zinc-950', className)}>
      {/* Conversation Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <div className="relative" ref={conversationDropdownRef}>
          <button
            onClick={() => setShowConversationList(!showConversationList)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <MessageSquare className="h-4 w-4 text-zinc-400" />
            <span className="max-w-[180px] truncate">{conversationTitle}</span>
            <ChevronDown className={cn("h-4 w-4 text-zinc-400 transition-transform", showConversationList && "rotate-180")} />
          </button>
          
          {/* Conversation Dropdown */}
          {showConversationList && (
            <div className="absolute left-0 top-full mt-1 w-72 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 max-h-80 overflow-y-auto">
              <div className="p-2 border-b border-zinc-700">
                <button
                  onClick={startNewConversation}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700 rounded-lg transition-colors"
                >
                  <Plus className="h-4 w-4 text-blue-400" />
                  New Conversation
                </button>
              </div>
              
              {conversations.length === 0 ? (
                <div className="p-4 text-center text-xs text-zinc-500">
                  No saved conversations
                </div>
              ) : (
                <div className="p-2 space-y-1">
                  {conversations.map((conv) => (
                    <button
                      key={conv.conversation_id}
                      onClick={() => loadConversation(conv.conversation_id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors group",
                        currentConversationId === conv.conversation_id
                          ? "bg-blue-600/20 text-blue-300"
                          : "text-zinc-300 hover:bg-zinc-700"
                      )}
                    >
                      <MessageSquare className="h-4 w-4 text-zinc-500 shrink-0" />
                      <span className="flex-1 truncate text-left">{conv.title || 'Untitled'}</span>
                      <button
                        onClick={(e) => deleteConversation(conv.conversation_id, e)}
                        className="p-1 opacity-0 group-hover:opacity-100 hover:bg-red-500/20 rounded transition-all"
                        title="Delete conversation"
                      >
                        <Trash2 className="h-3 w-3 text-red-400" />
                      </button>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        
        <button
          onClick={startNewConversation}
          className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
          title="New conversation"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      
      {session?.contextItems && session.contextItems.length > 0 && (
        <ContextBar
          items={session.contextItems.map(ci => ({
            id: ci.id,
            type: ci.source === 'rag' ? 'search' : ci.source === 'file' ? 'file' : ci.source === 'memory' ? 'memory' : 'search',
            label: ci.label,
            tokens: ci.tokens,
          }))}
          onRemoveItem={() => {}}
        />
      )}
      
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Empty State */}
        {userMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-4">
              <span className="text-3xl">🤖</span>
            </div>
            <h2 className="text-xl font-semibold text-zinc-200 mb-2">
              Halbert Agent
            </h2>
            <p className="text-sm text-zinc-400 max-w-md mb-6">
              I can help you manage your system, search documentation, execute commands, 
              and more. Ask me anything about your Linux environment.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {['Check system status', 'Search docs', 'Manage services', 'Run diagnostics'].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-full border border-zinc-700 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
        
        {userMessages.map((msg, idx) => (
          <div key={msg.id} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[80%] bg-blue-600 text-white px-4 py-2 rounded-lg">
                <p className="text-sm">{msg.content}</p>
              </div>
            </div>
            
            {idx === userMessages.length - 1 && session && (
              <div className="flex justify-start">
                <div className="max-w-[85%] bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <StateBadge state={session.state} showPulse={isStreaming} />
                    {session.loopCount > 0 && (
                      <span className="text-xs text-zinc-500">Loop {session.loopCount}</span>
                    )}
                  </div>
                  
                  {session.plan.length > 0 && (
                    <PlanChecklist plan={session.plan} currentStep={session.currentStep} />
                  )}
                  
                  {/* Active Scan Visualization */}
                  {session.activeScan && (
                    <ScanBlock
                      source={session.activeScan.source}
                      query={session.activeScan.query}
                      fileCount={session.activeScan.fileCount}
                      isComplete={session.activeScan.isComplete}
                      resultsCount={session.activeScan.results}
                    />
                  )}
                  
                  {session.toolExecutions.map((exec) => (
                    <ToolExecutionCard key={exec.executionId} execution={exec} />
                  ))}
                  
                  {/* Diff Proposals */}
                  {session.diffProposals.map((diff) => (
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
                  
                  {thinking && <ThinkingPanel thinking={thinking} isStreaming={isStreaming} />}
                  
                  {session.confidence > 0 && (
                    <ConfidenceIndicator
                      confidence={session.confidence}
                      cragAction={session.cragAction}
                      size="sm"
                    />
                  )}
                  
                  {response && (
                    <div className="text-sm text-zinc-300">
                      <MessageContent content={response} onRunCommand={onRunCommand} />
                      {isStreaming && <span className="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-0.5" />}
                      {/* Phase 8: Provenance chips */}
                      {!isStreaming && provenance.length > 0 && (
                        <div className="mt-2">
                          <WhyChip provenance={provenance} onExpand={handleProvenanceExpand} />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Phase 8: Module invocations rendered inline */}
                  {!isStreaming && moduleInvocations.length > 0 && (
                    <div className="mt-3 space-y-3">
                      {moduleInvocations.map((inv, i) => (
                        <ModuleRenderer key={i} module={inv.module} props={inv.props} />
                      ))}
                    </div>
                  )}

                  {/* Phase 8: Provenance-expanded sources (WhyChip onExpand) */}
                  {expandedProvenanceModules.length > 0 && (
                    <div className="mt-3 space-y-3">
                      {expandedProvenanceModules.map((m) => (
                        <div key={m.key} className="relative">
                          <button
                            onClick={() => dismissExpandedModule(m.key)}
                            className="absolute right-2 top-2 z-10 p-1 rounded bg-zinc-800/80 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
                            title="Close"
                          >
                            <XIcon className="h-3 w-3" />
                          </button>
                          <ModuleRenderer module={m.module} props={m.props} />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        
        {agentError && !isStreaming && (
          <div className="flex justify-center">
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 flex items-center gap-2">
              <span className="text-sm text-red-400">{agentError}</span>
              <button onClick={handleReset} className="p-1 hover:bg-red-500/20 rounded">
                <RotateCcw className="h-4 w-4 text-red-400" />
              </button>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Mention Autocomplete */}
      {showMentions && filteredMentionables.length > 0 && (
        <div className="mx-4 mb-1 bg-zinc-800 border border-zinc-700 rounded-md shadow-lg max-h-48 overflow-y-auto">
          {filteredMentionables.map((m) => (
            <button
              key={m.id}
              className="w-full px-3 py-1.5 text-left hover:bg-zinc-700 flex items-center gap-2 text-xs"
              onClick={() => insertMention(m)}
            >
              {m.type === 'terminal' ? (
                <Terminal className="h-3 w-3 text-green-500" />
              ) : (
                <AtSign className="h-3 w-3 text-zinc-400" />
              )}
              <span className="font-medium text-zinc-200">{m.mention}</span>
              <span className="text-zinc-500 ml-auto">{m.type}</span>
            </button>
          ))}
        </div>
      )}
      
      <div 
        className={cn(
          "border-t border-zinc-800 p-4 transition-colors",
          isDraggingImage && "bg-blue-500/10 border-blue-500"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Attached Images Preview */}
        {attachedImages.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {attachedImages.map(img => (
              <div key={img.id} className="relative group">
                <img 
                  src={img.dataUrl} 
                  alt={img.name}
                  className="h-12 w-12 object-cover rounded border border-zinc-700"
                />
                <button
                  onClick={() => removeAttachedImage(img.id)}
                  className="absolute -top-1 -right-1 h-4 w-4 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <XIcon className="h-2.5 w-2.5" />
                </button>
              </div>
            ))}
          </div>
        )}
        
        {/* Drop indicator */}
        {isDraggingImage && (
          <div className="mb-2 p-2 border-2 border-dashed border-blue-500 rounded text-center text-xs text-blue-400">
            <ImageIcon className="h-4 w-4 mx-auto mb-1" />
            Drop image here
          </div>
        )}
        
        {/* Message Queue */}
        {messageQueue.length > 0 && (
          <div className="mb-2 space-y-1">
            {messageQueue.map((msg, idx) => (
              <div key={idx} className="flex items-center justify-between gap-2 px-2 py-1 bg-amber-500/10 border border-amber-500/20 rounded text-xs">
                <span className="text-zinc-400 truncate">Queued: {msg}</span>
                <button
                  onClick={() => setMessageQueue(prev => prev.filter((_, i) => i !== idx))}
                  className="text-zinc-400 hover:text-zinc-200 shrink-0"
                >
                  <XIcon className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                handleInputChange(e);
                autoResizeTextarea();
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={isStreaming ? "Type to queue next message..." : "Ask Halbert... (@ to mention, paste/drop images)"}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 pr-10 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500 resize-none overflow-hidden min-h-[40px]"
              rows={1}
              style={{ maxHeight: '150px' }}
            />
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent('halbert:capture-screenshot'))}
              className="absolute right-2 bottom-2 text-zinc-500 hover:text-zinc-300 transition-colors"
              title="Screenshot"
            >
              <Camera className="h-4 w-4" />
            </button>
          </div>
          
          {isStreaming ? (
            <button onClick={cancel} className="p-2 bg-red-600 hover:bg-red-500 rounded-lg transition-colors flex-shrink-0">
              <StopCircle className="h-5 w-5 text-white" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() && attachedImages.length === 0}
              className="p-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors flex-shrink-0"
            >
              <Send className="h-5 w-5 text-white" />
            </button>
          )}
        </div>
        
        <div className="flex items-center justify-between mt-2 text-xs text-zinc-500">
          <span>{isStreaming ? 'Agent working... type to queue' : 'Press Enter to send'}</span>
          {session && <span>Session: {session.sessionId.slice(0, 8)}...</span>}
        </div>
      </div>
      
      {session?.pendingConfirmation && (
        <ConfirmationDialog
          confirmation={session.pendingConfirmation}
          onConfirm={() => confirmAction(session.pendingConfirmation!.actionId, true)}
          onReject={() => confirmAction(session.pendingConfirmation!.actionId, false)}
        />
      )}
    </div>
  );
}

export default AgentChat;
