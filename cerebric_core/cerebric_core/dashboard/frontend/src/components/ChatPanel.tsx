/**
 * ChatPanel - Side panel chat for Cerebric Dashboard.
 * 
 * This is the "Guide/Assistant" chat - conversational, discovery-focused.
 * For command execution, see Terminal (separate component/page).
 */

import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { 
  MessageCircle, 
  ChevronRight, 
  Send, 
  Loader2,
  AtSign,
  Play,
  Copy,
  Check,
  Terminal,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'

/**
 * Renders message content with executable code blocks
 */
function MessageContent({ content, onExecuteCommand }: { 
  content: string
  onExecuteCommand?: (cmd: string) => void 
}) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  
  // Parse content into segments (text and code blocks)
  const segments: Array<{ type: 'text' | 'code'; content: string; lang?: string }> = []
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g
  let lastIndex = 0
  let match
  
  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before this code block
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: content.slice(lastIndex, match.index) })
    }
    // Add the code block
    segments.push({ 
      type: 'code', 
      content: match[2].trim(), 
      lang: match[1] || 'bash' 
    })
    lastIndex = match.index + match[0].length
  }
  
  // Add remaining text
  if (lastIndex < content.length) {
    segments.push({ type: 'text', content: content.slice(lastIndex) })
  }
  
  const handleCopy = (code: string, index: number) => {
    navigator.clipboard.writeText(code)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }
  
  const isExecutable = (lang: string) => ['bash', 'sh', 'shell', 'zsh'].includes(lang.toLowerCase())
  
  return (
    <div className="space-y-2">
      {segments.map((segment, i) => {
        if (segment.type === 'text') {
          // Render text with basic markdown (bold, inline code)
          const formatted = segment.content
            .split(/(\*\*[^*]+\*\*|`[^`]+`)/)
            .map((part, j) => {
              if (part.startsWith('**') && part.endsWith('**')) {
                return <strong key={j} className="font-semibold">{part.slice(2, -2)}</strong>
              }
              if (part.startsWith('`') && part.endsWith('`')) {
                return <code key={j} className="px-1 py-0.5 bg-muted rounded text-[10px] font-mono">{part.slice(1, -1)}</code>
              }
              return part
            })
          return <div key={i} className="whitespace-pre-wrap">{formatted}</div>
        }
        
        // Render code block
        const executable = isExecutable(segment.lang || '')
        return (
          <div key={i} className="rounded-md overflow-hidden border border-border/50 bg-zinc-900">
            <div className="flex items-center justify-between px-2 py-1 bg-zinc-800 border-b border-border/30">
              <div className="flex items-center gap-1.5">
                <Terminal className="h-3 w-3 text-green-400" />
                <span className="text-[10px] text-zinc-400 font-mono">{segment.lang || 'bash'}</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleCopy(segment.content, i)}
                  className="p-1 rounded hover:bg-zinc-700 transition-colors"
                  title="Copy"
                >
                  {copiedIndex === i ? (
                    <Check className="h-3 w-3 text-green-400" />
                  ) : (
                    <Copy className="h-3 w-3 text-zinc-400" />
                  )}
                </button>
                {executable && onExecuteCommand && (
                  <button
                    onClick={() => onExecuteCommand(segment.content)}
                    className="p-1 rounded hover:bg-zinc-700 transition-colors flex items-center gap-1"
                    title="Run in Terminal"
                  >
                    <Play className="h-3 w-3 text-green-400" />
                  </button>
                )}
              </div>
            </div>
            <pre className="p-2 text-[11px] font-mono text-green-300 overflow-x-auto">
              <code>{segment.content}</code>
            </pre>
          </div>
        )
      })}
    </div>
  )
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  mentions?: string[]
}

interface Mentionable {
  id: string
  mention: string
  name: string
  type: string
}

export function ChatPanel() {
  const [isOpen, setIsOpen] = useState(true)
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hi! I'm here to help you understand your system. Ask me about backups, services, or use @mentions for specific items.",
      timestamp: new Date(),
    }
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [mentionables, setMentionables] = useState<Mentionable[]>([])
  const [showMentions, setShowMentions] = useState(false)
  const [mentionFilter, setMentionFilter] = useState('')
  
  const inputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadMentionables()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Listen for "continue in chat" events from other components
  useEffect(() => {
    interface OpenChatEventDetail {
      // Legacy format
      service?: string
      context?: string
      // New format
      title?: string
      type?: string
      itemId?: string
      newConversation?: boolean
      useSpecialist?: boolean
      prefillMessage?: string
    }
    
    const handleOpenChat = (event: CustomEvent<OpenChatEventDetail>) => {
      // Open the chat panel
      setIsOpen(true)
      
      const detail = event.detail
      
      // Handle new conversation request
      if (detail.newConversation) {
        // Clear messages for new conversation
        setMessages([{
          id: Date.now().toString(),
          role: 'assistant',
          content: detail.useSpecialist 
            ? "🔬 Deep research mode activated. I'll use the specialist model for detailed analysis."
            : "Starting a new conversation. How can I help?",
          timestamp: new Date(),
        }])
      }
      
      // Determine title and type (support both legacy and new format)
      const title = detail.title || detail.service || 'Item'
      const type = detail.type || 'service'
      const context = detail.context || ''
      
      // Add the context as a system message
      if (context) {
        const contextMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'system',
          content: `**${title}** (${type})\n\n${context}`,
          timestamp: new Date(),
        }
        setMessages(prev => [...prev, contextMessage])
      }
      
      // Set up mention and prefill
      const itemId = detail.itemId || (detail.service ? `service/${detail.service}` : '')
      const mention = itemId ? `@${type}/${itemId} ` : ''
      const prefill = detail.prefillMessage || ''
      
      setInput(mention + prefill)
      
      // Focus the input after a short delay
      setTimeout(() => {
        inputRef.current?.focus()
      }, 100)
    }
    
    window.addEventListener('cerebric:open-chat', handleOpenChat as EventListener)
    return () => {
      window.removeEventListener('cerebric:open-chat', handleOpenChat as EventListener)
    }
  }, [])

  const loadMentionables = async () => {
    try {
      const data = await api.getMentionables()
      setMentionables(data.mentionables || [])
    } catch (error) {
      console.error('Failed to load mentionables:', error)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setInput(value)

    const lastAtIndex = value.lastIndexOf('@')
    if (lastAtIndex !== -1 && lastAtIndex === value.length - 1) {
      setShowMentions(true)
      setMentionFilter('')
    } else if (lastAtIndex !== -1) {
      const afterAt = value.slice(lastAtIndex + 1)
      if (!afterAt.includes(' ')) {
        setShowMentions(true)
        setMentionFilter(afterAt.toLowerCase())
      } else {
        setShowMentions(false)
      }
    } else {
      setShowMentions(false)
    }
  }

  const insertMention = (mentionable: Mentionable) => {
    const lastAtIndex = input.lastIndexOf('@')
    const newInput = input.slice(0, lastAtIndex) + mentionable.mention + ' '
    setInput(newInput)
    setShowMentions(false)
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !showMentions) {
      e.preventDefault()
      handleSend()
    } else if (e.key === 'Escape') {
      setShowMentions(false)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      mentions: extractMentions(input),
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await getAIResponse(userMessage.content, userMessage.mentions || [])
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response,
        timestamp: new Date(),
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('Failed to get response:', error)
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'system',
        content: 'Sorry, I encountered an error.',
        timestamp: new Date(),
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const extractMentions = (text: string): string[] => {
    const mentionRegex = /@[\w\-\/]+/g
    return text.match(mentionRegex) || []
  }

  const filteredMentionables = mentionables.filter(m => 
    m.name.toLowerCase().includes(mentionFilter) ||
    m.type.toLowerCase().includes(mentionFilter) ||
    m.id.toLowerCase().includes(mentionFilter)
  ).slice(0, 5)

  const getAIResponse = async (userInput: string, mentions: string[]): Promise<string> => {
    try {
      const response = await api.sendChat(userInput, mentions, 'guide')
      return response.response || "I'm not sure how to help with that."
    } catch (error) {
      console.error('Chat API error:', error)
      // Fallback to basic response
      return "I'm here to help! Try asking about backups, services, storage, or network."
    }
  }

  return (
    <div
      className={cn(
        "h-full bg-card border-l flex flex-col transition-all duration-200",
        isOpen ? "w-[320px]" : "w-12"
      )}
    >
      {/* Collapsed State */}
      {!isOpen ? (
        <button 
          className="flex flex-col items-center py-4 h-full hover:bg-accent/50 transition-colors"
          onClick={() => setIsOpen(true)}
        >
          <MessageCircle className="h-5 w-5 text-primary mb-2" />
          <span 
            className="text-xs font-medium text-muted-foreground"
            style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
          >
            Chat
          </span>
        </button>
      ) : (
        <>
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
            <div className="flex items-center gap-2">
              <MessageCircle className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Assistant</span>
            </div>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-7 w-7"
              onClick={() => setIsOpen(false)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex",
                  message.role === 'user' ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[90%] rounded-lg px-3 py-2 text-sm",
                    message.role === 'user'
                      ? "bg-primary text-primary-foreground"
                      : message.role === 'system'
                      ? "bg-muted/80 border border-border"
                      : "bg-muted"
                  )}
                >
                  {message.role === 'system' && (
                    <div className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wide">Context</div>
                  )}
                  {message.role === 'user' ? (
                    <div className="whitespace-pre-wrap text-xs">{message.content}</div>
                  ) : (
                    <div className="text-xs">
                      <MessageContent 
                        content={message.content} 
                        onExecuteCommand={(cmd) => {
                          // Navigate to terminal with command
                          window.dispatchEvent(new CustomEvent('cerebric:run-command', { 
                            detail: { command: cmd } 
                          }))
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-muted rounded-lg px-3 py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Mention Autocomplete */}
          {showMentions && filteredMentionables.length > 0 && (
            <div className="mx-3 mb-1 bg-popover border rounded-md shadow-lg max-h-32 overflow-y-auto">
              {filteredMentionables.map((m) => (
                <button
                  key={m.id}
                  className="w-full px-3 py-1.5 text-left hover:bg-accent flex items-center gap-2 text-xs"
                  onClick={() => insertMention(m)}
                >
                  <AtSign className="h-3 w-3 text-muted-foreground" />
                  <span className="font-medium">{m.mention}</span>
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="p-3 border-t">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask... (@ to mention)"
                className="flex-1 px-2 py-1.5 rounded-md border bg-background text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                disabled={isLoading}
              />
              <Button 
                onClick={handleSend} 
                disabled={isLoading || !input.trim()}
                size="icon"
                className="h-7 w-7"
              >
                {isLoading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Send className="h-3 w-3" />
                )}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
