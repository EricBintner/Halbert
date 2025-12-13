/**
 * SidePanel - Unified slide-out panel for Chat (Guide) and Terminal (Coder).
 * 
 * Features:
 * - Toggle between Chat and Terminal modes
 * - Horizontal resize handle
 * - Listens for 'halbert:run-command' events to auto-run commands
 * - Context sharing between modes (future)
 */

import { useState, useRef, useEffect, KeyboardEvent, useCallback } from 'react'
import { 
  MessageCircle, 
  Terminal,
  ChevronRight, 
  Send, 
  Loader2,
  AtSign,
  GripVertical,
  Play,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  ChevronDown,
  Image as ImageIcon,
  X as XIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useDebug } from '@/contexts/DebugContext'
import { usePageContext } from '@/contexts/PageContext'

// Types
interface EditBlock {
  search: string
  replace: string
}

interface AttachedImage {
  id: string
  dataUrl: string  // base64 data URL
  name: string
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  mentions?: string[]
  editBlocks?: EditBlock[]  // Phase 18: Config editor edit proposals
  configPath?: string  // Path to config file for "Edit Config" button
  images?: string[]  // Vision model: base64 image data
}

interface Mentionable {
  id: string
  mention: string
  name: string
  type: string
}

interface TerminalLine {
  id: string
  type: 'input' | 'output' | 'error'
  content: string
  timestamp: Date
}

type PanelMode = 'chat' | 'terminal'

// Conversation types
interface ConversationSummary {
  id: string
  name: string
  created_at: string
  updated_at: string
  persona: string
  message_count: number
  preview: string
}

interface Conversation {
  id: string
  name: string
  created_at: string
  updated_at: string
  persona: string
  messages: Message[]
}

// Inline code block with run button and output display
function InlineCodeBlock({ code, lang, onRunCommand }: { 
  code: string, 
  lang: string, 
  onRunCommand: (cmd: string) => Promise<{output?: string, error?: string, exit_code?: number}> 
}) {
  const [isRunning, setIsRunning] = useState(false)
  const [output, setOutput] = useState<string | null>(null)
  const [isError, setIsError] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  
  const isShellCommand = ['bash', 'sh', 'shell', 'zsh'].includes(lang) || 
    code.startsWith('sudo ') || 
    code.startsWith('ls ') ||
    code.includes('|')
  
  const handleRun = async () => {
    setIsRunning(true)
    setOutput(null)
    try {
      const result = await onRunCommand(code)
      if (result.exit_code === 0) {
        setOutput(result.output || '(no output)')
        setIsError(false)
      } else {
        setOutput(result.error || result.output || `Exit code: ${result.exit_code}`)
        setIsError(true)
      }
    } catch (err) {
      setOutput(`Error: ${err}`)
      setIsError(true)
    } finally {
      setIsRunning(false)
    }
  }
  
  return (
    <div className="space-y-1 min-w-0">
      <div className="relative group">
        <pre className="bg-zinc-900 text-zinc-100 rounded p-2 text-xs font-mono overflow-x-auto max-w-full">
          <code className="break-all">{code}</code>
        </pre>
        {isShellCommand && (
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="absolute top-1 right-1 p-1 rounded bg-zinc-700 hover:bg-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50"
            title="Run inline"
          >
            {isRunning ? (
              <Loader2 className="h-3 w-3 text-blue-400 animate-spin" />
            ) : (
              <Play className="h-3 w-3 text-green-400" />
            )}
          </button>
        )}
      </div>
      
      {/* Inline output display */}
      {output && (
        <div className={cn(
          "rounded text-xs font-mono overflow-hidden",
          isError ? "bg-red-950/50 border border-red-900" : "bg-zinc-800/50 border border-zinc-700"
        )}>
          <div 
            className="flex items-center justify-between px-2 py-1 bg-zinc-800/50 cursor-pointer"
            onClick={() => setIsCollapsed(!isCollapsed)}
          >
            <span className={cn("text-[10px]", isError ? "text-red-400" : "text-zinc-400")}>
              {isError ? "Error" : "Output"}
            </span>
            <ChevronDown className={cn("h-3 w-3 text-zinc-500 transition-transform", isCollapsed && "-rotate-90")} />
          </div>
          {!isCollapsed && (
            <pre className={cn(
              "p-2 overflow-x-auto max-h-32 overflow-y-auto",
              isError ? "text-red-300" : "text-zinc-300"
            )}>
              {output}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// Helper to render message content with code blocks and terminal buttons
function MessageContent({ content, onRunCommand }: { 
  content: string, 
  onRunCommand: (cmd: string) => Promise<{output?: string, error?: string, exit_code?: number}> 
}) {
  // Parse content for code blocks
  const parts: Array<{ type: 'text' | 'code', content: string, lang?: string }> = []
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g
  let lastIndex = 0
  let match
  
  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before code block
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) })
    }
    // Add code block
    parts.push({ type: 'code', content: match[2].trim(), lang: match[1] || 'bash' })
    lastIndex = match.index + match[0].length
  }
  
  // Add remaining text
  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) })
  }
  
  // If no code blocks found, just return the content as text
  if (parts.length === 0) {
    parts.push({ type: 'text', content })
  }
  
  return (
    <div className="space-y-2 min-w-0 overflow-hidden">
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return (
            <InlineCodeBlock 
              key={i} 
              code={part.content} 
              lang={part.lang || 'bash'} 
              onRunCommand={onRunCommand} 
            />
          )
        } else {
          return (
            <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
          )
        }
      })}
    </div>
  )
}

export function SidePanel() {
  // Debug context - chatMetrics used for updating, displayed in Layout.tsx
  const { isDebugMode, addLog, updateChatMetrics, chatMetrics } = useDebug()
  
  // Page context - tracks current page, focused item, and visible items
  const { currentPage, focusedItem, setFocusedItem, buildPageContext } = usePageContext()
  
  // Panel state
  const [isOpen, setIsOpen] = useState(true)
  const [mode, setMode] = useState<PanelMode>('chat')
  const [width, setWidth] = useState(360)
  const [isResizing, setIsResizing] = useState(false)
  
  // AI name from onboarding
  const [aiName, setAiName] = useState('Halbert')
  
  // Chat state - intro message will be set after loading AI name
  const [messages, setMessages] = useState<Message[]>([])
  const [chatInput, setChatInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isModelLoading, setIsModelLoading] = useState(false)  // Model loading into VRAM
  const [loadingStatus, setLoadingStatus] = useState<string>('')  // Status message for loading
  const [mentionables, setMentionables] = useState<Mentionable[]>([])
  const [showMentions, setShowMentions] = useState(false)
  const [mentionFilter, setMentionFilter] = useState('')
  
  // Terminal state - intro message will be updated after AI name loads
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([])
  const [terminalInput, setTerminalInput] = useState('')
  const [commandHistory, setCommandHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  
  // Conversation state
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)
  const [showConversationList, setShowConversationList] = useState(false)
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  
  // Config editing context (Phase 18) - tracks if we're editing a config file
  const [configContext, setConfigContext] = useState<{
    filePath: string
    getContent: () => string
  } | null>(null)
  
  // Vision model support - attached images
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])
  const [isDraggingImage, setIsDraggingImage] = useState(false)
  
  // Model state (Phase 12e) - COMMENTED OUT: Will revisit when adding API key support for OpenAI/Anthropic/Gemini
  // For now, model selection should only happen in Settings via saved endpoints
  // const [currentModel, setCurrentModel] = useState<string>('')
  // const [availableModels, setAvailableModels] = useState<{id: string, name: string}[]>([])
  // const [showModelSelector, setShowModelSelector] = useState(false)
  
  // Refs
  const chatInputRef = useRef<HTMLTextAreaElement>(null)
  const terminalInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const terminalEndRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Expose panel width as CSS variable for ConfigEditor
  useEffect(() => {
    const actualWidth = isOpen ? width : 48
    document.documentElement.style.setProperty('--sidepanel-width', `${actualWidth}px`)
  }, [width, isOpen])

  // Load AI name, mentionables and conversations on mount
  useEffect(() => {
    // Load AI name from onboarding preferences
    const initMessages = (name: string) => {
      if (messages.length === 0) {
        setMessages([{
          id: '1',
          role: 'assistant',
          content: `Hi! I'm ${name}, your system assistant. Ask me about backups, services, or use @mentions for specific items.`,
          timestamp: new Date(),
        }])
      }
      if (terminalLines.length === 0) {
        setTerminalLines([{
          id: '0',
          type: 'output',
          content: `${name} Terminal - Type commands or use /help`,
          timestamp: new Date(),
        }])
      }
    }
    
    api.getPersonaNames()
      .then(data => {
        const name = data.ai_name || 'Halbert'
        setAiName(name)
        initMessages(name)
      })
      .catch(() => {
        // Fallback to default
        initMessages('Halbert')
      })
    loadMentionables()
    loadConversations()
    // loadModels() - disabled: model selection is now in Settings
  }, [])
  
  // COMMENTED OUT (Phase 12e) - Will revisit when adding API key support for OpenAI/Anthropic/Gemini
  // Model selection now happens in Settings > AI Models > Saved Endpoints
  /*
  const loadModels = async () => {
    try {
      const data = await api.getModels()
      if (data.current) {
        setCurrentModel(data.current.specialist || data.current.orchestrator || '')
      }
      if (data.available) {
        setAvailableModels(data.available)
      }
    } catch (error) {
      console.error('Failed to load models:', error)
    }
  }
  
  const selectModel = async (modelId: string) => {
    try {
      await api.selectModel(modelId)
      setCurrentModel(modelId)
      setShowModelSelector(false)
    } catch (error) {
      console.error('Failed to select model:', error)
    }
  }
  */

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-scroll terminal
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [terminalLines])

  // Listen for run-command events from other components (runs in terminal)
  useEffect(() => {
    const handleRunCommand = (e: CustomEvent<{ command: string }>) => {
      const { command } = e.detail
      setMode('terminal')
      setIsOpen(true)
      // Add slight delay to ensure terminal is visible
      setTimeout(() => {
        setTerminalInput(command)
        terminalInputRef.current?.focus()
      }, 100)
    }

    window.addEventListener('halbert:run-command', handleRunCommand as EventListener)
    return () => {
      window.removeEventListener('halbert:run-command', handleRunCommand as EventListener)
    }
  }, [])

  // Listen for send-to-chat events (prefills chat input with command for inline execution)
  useEffect(() => {
    const handleSendToChat = (e: CustomEvent<{ command: string; context?: string }>) => {
      const { command, context } = e.detail
      setMode('chat')
      setIsOpen(true)
      // Format command for inline execution request
      const message = context 
        ? `${context}\n\nPlease run this command:\n\`\`\`bash\n${command}\n\`\`\``
        : `Please run this command:\n\`\`\`bash\n${command}\n\`\`\``
      setTimeout(() => {
        setChatInput(message)
        chatInputRef.current?.focus()
      }, 100)
    }

    window.addEventListener('halbert:send-to-chat', handleSendToChat as EventListener)
    return () => {
      window.removeEventListener('halbert:send-to-chat', handleSendToChat as EventListener)
    }
  }, [])

  // Listen for open-chat events (from chat buttons on pages)
  useEffect(() => {
    interface OpenChatEventDetail {
      title?: string
      type?: string
      context?: string
      itemId?: string
      newConversation?: boolean
      useSpecialist?: boolean
      prefillMessage?: string
      reuseExisting?: boolean  // Phase 18: Reuse existing conversation with same title
      configPath?: string  // Path to config file for "Edit Config" button
      data?: Record<string, unknown>  // Full item data
      // Legacy format
      service?: string
    }
    
    const handleOpenChat = async (e: CustomEvent<OpenChatEventDetail>) => {
      const detail = e.detail
      setMode('chat')
      setIsOpen(true)
      
      // Build a clean mention - just @Title with underscores
      const title = detail.title || detail.service || 'Item'
      const itemId = detail.itemId || title.replace(/\s+/g, '_')
      
      if (detail.newConversation && detail.context) {
        // Check if we should reuse existing conversation (Phase 18: Config editing)
        if (detail.reuseExisting || detail.type === 'config') {
          try {
            // Look for existing conversation with same title
            console.log('[ConfigChat] Looking for existing conversation with title:', title)
            const convList = await api.listConversations()
            console.log('[ConfigChat] Conversations list:', convList)
            
            // Handle both array and object with conversations property
            const convArray = Array.isArray(convList) ? convList : convList.conversations
            const existing = convArray?.find((c: ConversationSummary) => c.name === title)
            console.log('[ConfigChat] Found existing?', existing)
            
            if (existing) {
              // Load the existing conversation
              console.log('[ConfigChat] Reusing conversation:', existing.id)
              const conv = await api.getConversation(existing.id) as Conversation
              setCurrentConversationId(conv.id)
              setMessages(conv.messages.map(m => ({
                id: m.id,
                role: m.role as 'user' | 'assistant' | 'system',
                content: m.content,
                timestamp: new Date(m.timestamp),
              })))
              loadConversations()
              setTimeout(() => chatInputRef.current?.focus(), 150)
              return
            }
            console.log('[ConfigChat] No existing conversation found, creating new')
          } catch (err) {
            console.error('Failed to check for existing conversation:', err)
          }
        }
        
        // Chat bubble: Start new conversation with context as assistant's first message
        // Create a named conversation so messages get saved
        const contextContent = `**${title}**\n\n${detail.context}`
        
        // Check for config file path - either directly provided or from data
        // Scanner uses config_path, but we also check other variations
        const configPath = detail.configPath || 
          (detail.data?.config_path as string) ||   // Scanner convention
          (detail.data?.config_file as string) ||   // Alternative name
          (detail.data?.configPath as string) ||    // camelCase
          null
        
        api.createConversation(title).then((conv: Conversation) => {
          setCurrentConversationId(conv.id)
          // Add the assistant message with context (and optional config path)
          const assistantMsg: Message = {
            id: Date.now().toString(),
            role: 'assistant' as const,
            content: contextContent,
            timestamp: new Date(),
            configPath: configPath || undefined,
          }
          setMessages([assistantMsg])
          // Save the initial assistant message
          api.addMessageToConversation(conv.id, 'assistant', contextContent)
            .catch(err => console.error('Failed to save context message:', err))
          // Update conversation list without reloading current conversation
          // (loadConversations has stale closure and would overwrite our message)
          api.listConversations().then(data => setConversations(data || [])).catch(() => {})
        }).catch(err => {
          console.error('Failed to create conversation:', err)
          // Fallback: show messages anyway but they won't be saved
          setCurrentConversationId(null)
          setMessages([{
            id: Date.now().toString(),
            role: 'assistant',
            content: contextContent,
            timestamp: new Date(),
            configPath: configPath || undefined,
          }])
        })
        
        setTimeout(() => {
          chatInputRef.current?.focus()
        }, 150)
      } else if (detail.type === 'config') {
        // Config editing mode: Just open the panel and focus
        // The conversation will be created/reused on first message send
        // ConfigEditor will set the config context via events
        console.log('[ConfigChat] Opening panel for config editing, title:', title)
        
        // Try to load existing conversation with this title
        try {
          const convList = await api.listConversations()
          const convArray = Array.isArray(convList) ? convList : convList.conversations
          const existing = convArray?.find((c: ConversationSummary) => c.name === title)
          
          if (existing) {
            console.log('[ConfigChat] Found existing conversation:', existing.id)
            const conv = await api.getConversation(existing.id) as Conversation
            setCurrentConversationId(conv.id)
            setMessages(conv.messages.map(m => ({
              id: m.id,
              role: m.role as 'user' | 'assistant' | 'system',
              content: m.content,
              timestamp: new Date(m.timestamp),
            })))
            loadConversations()
          } else {
            // No existing conversation - just show default welcome
            // Conversation will be created on first message
            console.log('[ConfigChat] No existing conversation, will create on first message')
          }
        } catch (err) {
          console.error('Failed to load conversation:', err)
        }
        
        setTimeout(() => {
          chatInputRef.current?.focus()
        }, 150)
      } else {
        // @ tag: Just add mention to current chat input (don't create new conversation)
        const mention = `@${itemId} `
        
        setTimeout(() => {
          setChatInput(prev => prev + mention)
          chatInputRef.current?.focus()
        }, 150)
      }
    }

    window.addEventListener('halbert:open-chat', handleOpenChat as unknown as EventListener)
    return () => {
      window.removeEventListener('halbert:open-chat', handleOpenChat as unknown as EventListener)
    }
  }, [])

  // Listen for config editing context (Phase 18)
  useEffect(() => {
    const handleSetConfigContext = (e: CustomEvent<{ filePath: string; getContent: () => string }>) => {
      console.log('[ConfigChat] Setting config context:', e.detail.filePath)
      setConfigContext({
        filePath: e.detail.filePath,
        getContent: e.detail.getContent,
      })
    }
    
    const handleClearConfigContext = () => {
      console.log('[ConfigChat] Clearing config context')
      setConfigContext(null)
    }

    window.addEventListener('halbert:set-config-context', handleSetConfigContext as EventListener)
    window.addEventListener('halbert:clear-config-context', handleClearConfigContext as EventListener)
    return () => {
      window.removeEventListener('halbert:set-config-context', handleSetConfigContext as EventListener)
      window.removeEventListener('halbert:clear-config-context', handleClearConfigContext as EventListener)
    }
  }, [])

  // Listen for screenshot events from Layout
  useEffect(() => {
    const handleScreenshot = (e: CustomEvent<{ dataUrl: string; base64: string; name: string }>) => {
      console.log('[SidePanel] Received screenshot:', e.detail.name)
      // Add screenshot as attached image
      setAttachedImages(prev => [...prev, {
        id: `screenshot-${Date.now()}`,
        dataUrl: e.detail.dataUrl,
        name: e.detail.name,
      }])
    }
    
    window.addEventListener('halbert:add-screenshot', handleScreenshot as EventListener)
    return () => {
      window.removeEventListener('halbert:add-screenshot', handleScreenshot as EventListener)
    }
  }, [])

  // Handle resize
  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = Math.max(280, Math.min(900, window.innerWidth - e.clientX))
      setWidth(newWidth)
      // Update CSS variable immediately during resize
      document.documentElement.style.setProperty('--sidepanel-width', `${newWidth}px`)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

  // Chat functions
  const loadMentionables = async () => {
    try {
      const data = await api.getMentionables()
      setMentionables(data.mentionables || [])
    } catch (error) {
      console.error('Failed to load mentionables:', error)
    }
  }

  // Conversation functions
  const loadConversations = async () => {
    try {
      const data = await api.listConversations()
      setConversations(data || [])
      // If no conversations exist, create one
      if (!data || data.length === 0) {
        await createNewConversation()
      } else if (!currentConversationId) {
        // Load the most recent conversation
        await loadConversation(data[0].id)
      }
    } catch (error) {
      console.error('Failed to load conversations:', error)
    }
  }

  const loadConversation = async (id: string) => {
    try {
      const conv = await api.getConversation(id) as Conversation
      setCurrentConversationId(conv.id)
      setMessages(conv.messages.map(m => ({
        ...m,
        timestamp: new Date(m.timestamp),
      })))
      setShowConversationList(false)
    } catch (error) {
      console.error('Failed to load conversation:', error)
    }
  }

  const createNewConversation = async (name?: string) => {
    try {
      const conv = await api.createConversation(name) as Conversation
      setCurrentConversationId(conv.id)
      setMessages(conv.messages.map(m => ({
        ...m,
        timestamp: new Date(m.timestamp),
      })))
      setShowConversationList(false)
      loadConversations() // Refresh list
    } catch (error) {
      console.error('Failed to create conversation:', error)
    }
  }

  const renameCurrentConversation = async () => {
    if (!currentConversationId || !renameValue.trim()) return
    try {
      await api.renameConversation(currentConversationId, renameValue.trim())
      setIsRenaming(false)
      loadConversations()
    } catch (error) {
      console.error('Failed to rename conversation:', error)
    }
  }

  const deleteCurrentConversation = async () => {
    if (!currentConversationId) return
    try {
      await api.deleteConversation(currentConversationId)
      // Clear the messages and reset to default state
      setMessages([{
        id: '1',
        role: 'assistant',
        content: `Hi! I'm ${aiName}, your system assistant. Ask me about backups, services, or use @mentions for specific items.`,
        timestamp: new Date(),
      }])
      setCurrentConversationId(null)
      setShowDeleteConfirm(false)
      loadConversations()
    } catch (error) {
      console.error('Failed to delete conversation:', error)
    }
  }

  const getCurrentConversationName = () => {
    const conv = conversations.find(c => c.id === currentConversationId)
    return conv?.name || 'New Chat'
  }

  const handleChatInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const value = e.target.value
    setChatInput(value)

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
    const lastAtIndex = chatInput.lastIndexOf('@')
    const newInput = chatInput.slice(0, lastAtIndex) + mentionable.mention + ' '
    setChatInput(newInput)
    setShowMentions(false)
    chatInputRef.current?.focus()
  }

  const handleChatKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !showMentions) {
      e.preventDefault()
      handleSendChat()
    } else if (e.key === 'Escape') {
      setShowMentions(false)
    }
  }
  
  // Auto-resize textarea based on content
  const autoResizeTextarea = () => {
    const textarea = chatInputRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px' // Max 150px (~6 lines)
    }
  }
  
  // Reset textarea height when input is cleared (e.g., after sending)
  useEffect(() => {
    if (!chatInput && chatInputRef.current) {
      chatInputRef.current.style.height = 'auto'
    }
  }, [chatInput])

  // Vision model: Handle image file to base64 conversion
  const processImageFile = (file: File): Promise<AttachedImage> => {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith('image/')) {
        reject(new Error('Not an image file'))
        return
      }
      
      const reader = new FileReader()
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string
        resolve({
          id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          dataUrl,
          name: file.name,
        })
      }
      reader.onerror = () => reject(new Error('Failed to read file'))
      reader.readAsDataURL(file)
    })
  }

  // Vision model: Handle drag and drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingImage(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingImage(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingImage(false)
    
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))
    if (files.length === 0) return
    
    try {
      const newImages = await Promise.all(files.map(processImageFile))
      setAttachedImages(prev => [...prev, ...newImages])
    } catch (err) {
      console.error('Failed to process dropped images:', err)
    }
  }

  // Vision model: Handle paste (for screenshots)
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items)
    const imageItems = items.filter(item => item.type.startsWith('image/'))
    
    if (imageItems.length === 0) return
    
    e.preventDefault() // Prevent default paste of image as text
    
    for (const item of imageItems) {
      const file = item.getAsFile()
      if (file) {
        try {
          const image = await processImageFile(file)
          setAttachedImages(prev => [...prev, image])
        } catch (err) {
          console.error('Failed to process pasted image:', err)
        }
      }
    }
  }

  // Vision model: Remove attached image
  const removeAttachedImage = (id: string) => {
    setAttachedImages(prev => prev.filter(img => img.id !== id))
  }

  // Get recent terminal history for @terminal context (Phase 13)
  const getTerminalContext = (): string => {
    const recentLines = terminalLines.slice(-10) // Last 10 lines
    if (recentLines.length === 0) return ''
    
    return '\n\n--- Terminal History ---\n' + 
      recentLines.map(line => {
        if (line.type === 'input') return line.content
        if (line.type === 'error') return `[ERROR] ${line.content}`
        return line.content
      }).join('\n') +
      '\n--- End Terminal History ---'
  }

  const handleSendChat = async () => {
    if ((!chatInput.trim() && attachedImages.length === 0) || isLoading || isModelLoading) return

    const requestStartTime = performance.now()
    const mentions = extractMentions(chatInput)
    
    // Extract base64 data from attached images (strip data URL prefix)
    const imageData = attachedImages.map(img => {
      // Convert data:image/png;base64,xxxx to just xxxx
      const base64Match = img.dataUrl.match(/^data:image\/\w+;base64,(.+)$/)
      return base64Match ? base64Match[1] : img.dataUrl
    })
    
    // Check if model is loaded - show appropriate status message
    // Use specialist model for config editing, guide model for regular chat
    try {
      const modelStatus = await api.getLoadedModels()
      
      // Determine which model to check based on context
      const isConfigEditing = !!configContext
      const modelToCheck = isConfigEditing ? modelStatus.specialist_model : modelStatus.configured_model
      const isLoaded = isConfigEditing ? modelStatus.specialist_loaded : modelStatus.configured_loaded
      
      if (!isLoaded) {
        // Model not in VRAM - will need to load first
        setIsModelLoading(true)
        setLoadingStatus(`Loading ${modelToCheck}...`)
        
        if (isDebugMode) {
          addLog({
            type: 'info',
            category: 'api',
            message: `Model not loaded, will load on first request: ${modelToCheck}`,
            data: { 
              isConfigEditing,
              modelToCheck,
              loaded_models: modelStatus.loaded_models 
            }
          })
        }
      } else {
        // Model already loaded - just show "Thinking..."
        setLoadingStatus('Thinking...')
      }
    } catch (err) {
      // If we can't check, just show "Thinking..."
      setLoadingStatus('Thinking...')
      console.debug('Could not check model status:', err)
    }
    
    // Debug logging
    if (isDebugMode) {
      addLog({
        type: 'request',
        category: 'chat',
        message: `Sending chat message (${chatInput.length} chars, ${mentions.length} mentions, ${imageData.length} images)`,
        data: { message: chatInput.slice(0, 100), mentions, hasConfigContext: !!configContext, imageCount: imageData.length }
      })
    }
    
    // Check if @terminal is mentioned and inject context
    let messageContent = chatInput.trim()
    if (mentions.some(m => m === '@terminal')) {
      const terminalContext = getTerminalContext()
      if (terminalContext) {
        messageContent += terminalContext
        if (isDebugMode) {
          addLog({
            type: 'info',
            category: 'chat',
            message: `Injected terminal context (${terminalContext.length} chars)`,
          })
        }
      }
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: chatInput.trim() || (imageData.length > 0 ? '[Image]' : ''), // Show original in UI
      timestamp: new Date(),
      mentions,
      images: imageData.length > 0 ? imageData : undefined,
    }

    setMessages(prev => [...prev, userMessage])
    setChatInput('')
    setAttachedImages([])  // Clear attached images after sending
    setIsLoading(true)

    // Ensure we have a conversation to save to
    let convId = currentConversationId
    if (!convId) {
      // Create a new conversation with a contextual name based on first message
      const contextualName = chatInput.trim().slice(0, 50) + (chatInput.trim().length > 50 ? '...' : '')
      try {
        const conv = await api.createConversation(contextualName) as Conversation
        convId = conv.id
        setCurrentConversationId(conv.id)
        loadConversations()
      } catch (err) {
        console.error('Failed to create conversation:', err)
      }
    }

    // Save user message to conversation
    if (convId) {
      api.addMessageToConversation(convId, 'user', userMessage.content, userMessage.mentions || [])
        .catch(err => console.error('Failed to save user message:', err))
    }

    try {
      let response: { 
        response: string; 
        edit_blocks?: Array<{search: string, replace: string}>; 
        proposed_content?: string;  // IDE-style diff: applied edits
        summary?: string;  // Brief description of changes
        debug?: unknown 
      }
      const apiStartTime = performance.now()
      
      // Use config chat endpoint if we're editing a config file (Phase 18)
      if (configContext) {
        if (isDebugMode) {
          addLog({
            type: 'info',
            category: 'chat',
            message: `Using config chat endpoint for: ${configContext.filePath}`,
          })
        }
        const fileContent = configContext.getContent()
        // IMPORTANT: Add current userMessage since setMessages is async and messages doesn't include it yet
        const historyMessages = [...messages.slice(-9), userMessage]
        const history = historyMessages.map(m => ({ role: m.role, content: m.content }))
        response = await api.sendConfigChat(messageContent, configContext.filePath, fileContent, history, imageData)
      } else {
        // Regular chat endpoint - pass debug flag, current page, page context, and history
        const pageContext = buildPageContext()
        // Include last 10 messages for conversation context
        // IMPORTANT: Add current userMessage since setMessages is async and messages doesn't include it yet
        const historyMessages = [...messages.slice(-9), userMessage]
        const history = historyMessages.map(m => ({ role: m.role, content: m.content }))
        response = await api.sendChat(
          messageContent, 
          userMessage.mentions || [], 
          'guide', 
          isDebugMode,
          currentPage,
          pageContext,
          imageData,  // Vision model support
          history  // Conversation history for context
        )
        
        // Clear focused item after sending (it's been included in context)
        if (focusedItem) {
          setFocusedItem(null)
        }
      }
      
      const apiEndTime = performance.now()
      const apiDuration = apiEndTime - apiStartTime
      const totalDuration = apiEndTime - requestStartTime
      
      // Debug logging for response
      if (isDebugMode) {
        const responseLength = response.response?.length || 0
        const estimatedTokens = Math.ceil((messageContent.length + responseLength) / 4)
        
        addLog({
          type: 'response',
          category: 'chat',
          message: `Received response (${responseLength} chars, ~${estimatedTokens} tokens)`,
          data: { 
            responsePreview: response.response?.slice(0, 200),
            hasEditBlocks: !!response.edit_blocks?.length,
            debug: response.debug 
          },
          duration: apiDuration
        })
        
        addLog({
          type: 'timing',
          category: 'chat',
          message: `Chat round-trip complete`,
          duration: totalDuration
        })
        
        // Update metrics
        updateChatMetrics({
          lastRequestTime: requestStartTime,
          lastResponseTime: apiEndTime,
          totalRequests: chatMetrics.totalRequests + 1,
          totalTokensEstimate: chatMetrics.totalTokensEstimate + estimatedTokens,
          averageResponseTime: (chatMetrics.averageResponseTime * chatMetrics.totalRequests + apiDuration) / (chatMetrics.totalRequests + 1)
        })
      }
      
      // Build assistant message content
      let assistantContent = response.response || "I'm not sure how to help with that."
      
      // Debug: Log what we received from the API
      console.log('[SidePanel] Response received:', {
        hasProposedContent: !!response.proposed_content,
        proposedContentLength: response.proposed_content?.length,
        summary: response.summary,
        hasConfigContext: !!configContext,
        configPath: configContext?.filePath
      })
      
      // If we have proposed content, dispatch event to trigger diff view in ConfigEditor
      // Don't show raw edit blocks in chat - just show the summary
      if (response.proposed_content && configContext) {
        console.log('[SidePanel] Dispatching proposed edit to ConfigEditor')
        window.dispatchEvent(new CustomEvent('halbert:propose-edit', {
          detail: {
            proposedContent: response.proposed_content,
            summary: response.summary || 'Made changes to the file'
          }
        }))
        
        // Show a cleaner message in chat (without the raw edit blocks)
        // Extract just the explanation from the response
        const cleanContent = assistantContent
          .replace(/<<<<<<< SEARCH[\s\S]*?>>>>>>> REPLACE/g, '')
          .trim()
        assistantContent = cleanContent || `I've made the changes. ${response.summary || 'Please review the diff in the editor.'}`
      } else {
        // Debug: Log why we didn't dispatch the event
        console.log('[SidePanel] NOT dispatching propose-edit:', {
          reason: !response.proposed_content ? 'no proposed_content in response' : 'no configContext',
          hasProposedContent: !!response.proposed_content,
          hasConfigContext: !!configContext
        })
      }
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: assistantContent,
        timestamp: new Date(),
        // Don't store edit blocks - they're now shown as diff in editor
      }

      setMessages(prev => [...prev, assistantMessage])

      // Save assistant message to conversation
      if (convId) {
        api.addMessageToConversation(convId, 'assistant', assistantMessage.content)
          .catch(err => console.error('Failed to save assistant message:', err))
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      
      if (isDebugMode) {
        addLog({
          type: 'error',
          category: 'chat',
          message: `Chat request failed: ${errorMessage}`,
          data: error,
          duration: performance.now() - requestStartTime
        })
      }
      
      console.error('Failed to get response:', error)
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'system',
        content: `Sorry, I encountered an error${isDebugMode ? `: ${errorMessage}` : '.'}`,
        timestamp: new Date(),
      }])
    } finally {
      setIsLoading(false)
      setIsModelLoading(false)
      setLoadingStatus('')
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

  // Terminal functions
  const handleTerminalKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      executeCommand(terminalInput)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (commandHistory.length > 0 && historyIndex < commandHistory.length - 1) {
        const newIndex = historyIndex + 1
        setHistoryIndex(newIndex)
        setTerminalInput(commandHistory[commandHistory.length - 1 - newIndex])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1
        setHistoryIndex(newIndex)
        setTerminalInput(commandHistory[commandHistory.length - 1 - newIndex])
      } else if (historyIndex === 0) {
        setHistoryIndex(-1)
        setTerminalInput('')
      }
    }
  }

  const executeCommand = async (cmd: string) => {
    if (!cmd.trim()) return

    const inputLine: TerminalLine = {
      id: Date.now().toString(),
      type: 'input',
      content: `$ ${cmd}`,
      timestamp: new Date(),
    }

    setTerminalLines(prev => [...prev, inputLine])
    setTerminalInput('')
    setCommandHistory(prev => [...prev, cmd])
    setHistoryIndex(-1)

    // Handle built-in commands
    if (cmd.startsWith('/')) {
      handleSlashCommand(cmd)
      return
    }

    // Execute via API
    try {
      const result = await api.executeCommand(cmd)
      
      if (result.exit_code === 0) {
        const outputLine: TerminalLine = {
          id: (Date.now() + 1).toString(),
          type: 'output',
          content: result.output || '(no output)',
          timestamp: new Date(),
        }
        setTerminalLines(prev => [...prev, outputLine])
      } else {
        // Command failed
        const errorLine: TerminalLine = {
          id: (Date.now() + 1).toString(),
          type: 'error',
          content: result.error || result.output || `Exit code: ${result.exit_code}`,
          timestamp: new Date(),
        }
        setTerminalLines(prev => [...prev, errorLine])
      }
    } catch (error) {
      const errorLine: TerminalLine = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: `Error: ${error}`,
        timestamp: new Date(),
      }
      setTerminalLines(prev => [...prev, errorLine])
    }
  }

  const handleSlashCommand = (cmd: string) => {
    const parts = cmd.slice(1).split(' ')
    const command = parts[0].toLowerCase()

    let output: string

    switch (command) {
      case 'help':
        output = `Available commands:
/help     - Show this help
/clear    - Clear terminal
/explain  - Explain last output (AI)
/fix      - Suggest fixes (AI)
/chat     - Switch to chat mode`
        break
      case 'clear':
        setTerminalLines([{
          id: Date.now().toString(),
          type: 'output',
          content: 'Terminal cleared',
          timestamp: new Date(),
        }])
        return
      case 'chat':
        setMode('chat')
        return
      default:
        output = `Unknown command: /${command}\nType /help for available commands`
    }

    setTerminalLines(prev => [...prev, {
      id: Date.now().toString(),
      type: 'output',
      content: output,
      timestamp: new Date(),
    }])
  }

  return (
    <div
      ref={panelRef}
      className={cn(
        "h-full bg-card border-l flex relative flex-shrink-0 overflow-hidden",
        !isResizing && "transition-all duration-200",  // Only animate when not dragging
        isOpen ? "" : "w-12"
      )}
      style={{ width: isOpen ? width : 48, minWidth: isOpen ? 280 : 48 }}
    >
      {/* Resize Handle */}
      {isOpen && (
        <div
          className={cn(
            "absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/30 transition-colors z-10",
            isResizing && "bg-primary/50"
          )}
          onMouseDown={startResize}
        >
          <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 p-1 rounded bg-muted opacity-0 hover:opacity-100 transition-opacity">
            <GripVertical className="h-4 w-4 text-muted-foreground" />
          </div>
        </div>
      )}

      {/* Collapsed State */}
      {!isOpen ? (
        <button 
          className="flex flex-col items-center py-4 h-full w-full hover:bg-accent/50 transition-colors"
          onClick={() => setIsOpen(true)}
        >
          {mode === 'chat' ? (
            <MessageCircle className="h-5 w-5 text-primary mb-2" />
          ) : (
            <Terminal className="h-5 w-5 text-primary mb-2" />
          )}
          <span 
            className="text-xs font-medium text-muted-foreground"
            style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
          >
            {mode === 'chat' ? 'Chat' : 'Terminal'}
          </span>
        </button>
      ) : (
        <div className="flex flex-col flex-1 ml-1 min-w-0 overflow-hidden">
          {/* Header with Toggle */}
          <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
            {/* Mode Toggle */}
            <div className="flex items-center bg-muted rounded-md p-0.5">
              <button
                onClick={() => setMode('chat')}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors",
                  mode === 'chat' 
                    ? "bg-background shadow-sm text-foreground" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <MessageCircle className="h-3 w-3" />
                Chat
              </button>
              <button
                onClick={() => setMode('terminal')}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors",
                  mode === 'terminal' 
                    ? "bg-background shadow-sm text-foreground" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Terminal className="h-3 w-3" />
                Terminal
              </button>
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

          {/* Conversation Selector (Chat mode only) */}
          {mode === 'chat' && (
            <div className="px-3 py-2 border-b bg-muted/20 relative">
              {isRenaming ? (
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') renameCurrentConversation()
                      if (e.key === 'Escape') setIsRenaming(false)
                    }}
                    className="flex-1 px-2 py-1 text-xs bg-background border rounded"
                    autoFocus
                  />
                  <button onClick={renameCurrentConversation} className="p-1 hover:bg-accent rounded">
                    <Check className="h-3 w-3 text-green-500" />
                  </button>
                  <button onClick={() => setIsRenaming(false)} className="p-1 hover:bg-accent rounded">
                    <X className="h-3 w-3 text-muted-foreground" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setShowConversationList(!showConversationList)}
                    className="flex-1 flex items-center gap-1 px-2 py-1 text-xs font-medium hover:bg-accent rounded truncate text-left"
                  >
                    <ChevronDown className={cn("h-3 w-3 transition-transform", showConversationList && "rotate-180")} />
                    <span className="truncate">{getCurrentConversationName()}</span>
                  </button>
                  <button 
                    onClick={() => createNewConversation()} 
                    className="p-1 hover:bg-accent rounded"
                    title="New conversation"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button 
                    onClick={() => {
                      setRenameValue(getCurrentConversationName())
                      setIsRenaming(true)
                    }} 
                    className="p-1 hover:bg-accent rounded"
                    title="Rename"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                  <button 
                    onClick={() => setShowDeleteConfirm(true)} 
                    className="p-1 hover:bg-accent rounded text-destructive"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              )}
              
              {/* Conversation dropdown list */}
              {showConversationList && !isRenaming && (
                <div className="absolute left-0 right-0 top-full z-20 bg-card border-b shadow-lg max-h-48 overflow-y-auto">
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => loadConversation(conv.id)}
                      className={cn(
                        "w-full px-3 py-2 text-left text-xs hover:bg-accent flex flex-col gap-0.5",
                        conv.id === currentConversationId && "bg-accent"
                      )}
                    >
                      <span className="font-medium truncate">{conv.name}</span>
                      <span className="text-muted-foreground truncate">{conv.preview || 'No messages'}</span>
                    </button>
                  ))}
                  {conversations.length === 0 && (
                    <div className="px-3 py-2 text-xs text-muted-foreground">No conversations</div>
                  )}
                </div>
              )}
              
              {/* Model Selector (Phase 12e) - COMMENTED OUT
                 Will revisit when adding API key support for OpenAI/Anthropic/Gemini.
                 For now, model selection is managed in Settings > AI Models > Saved Endpoints */}
              {/*
              <div className="mt-1 flex items-center gap-1 relative">
                <button
                  onClick={() => setShowModelSelector(!showModelSelector)}
                  className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground hover:bg-accent rounded"
                  title="Select AI model"
                >
                  <span className="opacity-60">Model:</span>
                  <span className="font-medium truncate max-w-[120px]">
                    {currentModel ? currentModel.split(':')[0] : 'default'}
                  </span>
                  <ChevronDown className={cn("h-2.5 w-2.5 transition-transform", showModelSelector && "rotate-180")} />
                </button>
                
                {showModelSelector && (
                  <div className="absolute left-0 top-full z-20 mt-1 bg-card border rounded-md shadow-lg min-w-[200px] max-h-48 overflow-y-auto">
                    <div className="px-2 py-1 text-[10px] text-muted-foreground border-b">Available Models</div>
                    {availableModels.length > 0 ? (
                      availableModels.map((model) => (
                        <button
                          key={model.id}
                          onClick={() => selectModel(model.id)}
                          className={cn(
                            "w-full px-2 py-1.5 text-left text-xs hover:bg-accent flex items-center gap-2",
                            model.id === currentModel && "bg-accent"
                          )}
                        >
                          <span className="truncate">{model.name}</span>
                          {model.id === currentModel && <Check className="h-3 w-3 text-primary ml-auto" />}
                        </button>
                      ))
                    ) : (
                      <div className="px-2 py-1.5 text-xs text-muted-foreground">Loading models...</div>
                    )}
                  </div>
                )}
              </div>
              */}
            </div>
          )}

          {/* Chat Mode */}
          {mode === 'chat' && (
            <>
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
                        "max-w-[90%] rounded-lg px-3 py-2 text-sm min-w-0 overflow-hidden",
                        message.role === 'user'
                          ? "bg-primary text-primary-foreground"
                          : message.role === 'system'
                          ? "bg-destructive/10 text-destructive"
                          : "bg-muted"
                      )}
                    >
                      <div className="text-xs overflow-hidden min-w-0">
                        <MessageContent 
                          content={message.content} 
                          onRunCommand={async (cmd) => {
                            // Execute command and return result for inline display
                            try {
                              const result = await api.executeCommand(cmd)
                              return result
                            } catch (err) {
                              return { error: String(err), exit_code: 1 }
                            }
                          }}
                        />
                      </div>
                      {/* Legacy: Edit blocks are now shown as inline diff in editor */}
                      {/* This section kept for backwards compatibility with old messages */}
                      {/* Render Edit Config button if configPath is available */}
                      {message.configPath && (
                        <div className="mt-3 pt-2 border-t border-border/50">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs gap-1.5 w-full"
                            onClick={() => {
                              // Open config editor with this file
                              window.dispatchEvent(new CustomEvent('halbert:open-config-editor', {
                                detail: { filePath: message.configPath }
                              }))
                            }}
                          >
                            <Pencil className="h-3 w-3" />
                            Edit Config ({message.configPath.split('/').pop()})
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {(isLoading || isModelLoading) && (
                  <div className="flex justify-start">
                    <div className="bg-muted rounded-lg px-3 py-2 flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {loadingStatus && (
                        <span className="text-xs text-muted-foreground">{loadingStatus}</span>
                      )}
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

              {/* Config editing indicator */}
              {configContext && (
                <div className="mx-3 mb-1 px-2 py-1 bg-sky-900/60 border border-sky-600 rounded text-[10px] text-sky-100 flex items-center gap-1">
                  <Pencil className="h-3 w-3" />
                  <span>Editing: {configContext.filePath.split('/').pop()}</span>
                  <span className="text-sky-200 ml-1">• AI can apply edits directly</span>
                </div>
              )}

              {/* Chat Input */}
              <div 
                className={cn(
                  "p-3 border-t transition-colors",
                  isDraggingImage && "bg-primary/10 border-primary"
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
                          className="h-12 w-12 object-cover rounded border"
                        />
                        <button
                          onClick={() => removeAttachedImage(img.id)}
                          className="absolute -top-1 -right-1 h-4 w-4 bg-destructive text-destructive-foreground rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <XIcon className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Drop indicator */}
                {isDraggingImage && (
                  <div className="mb-2 p-2 border-2 border-dashed border-primary rounded text-center text-xs text-primary">
                    <ImageIcon className="h-4 w-4 mx-auto mb-1" />
                    Drop image here
                  </div>
                )}
                
                <div className="flex gap-2 items-end">
                  <textarea
                    ref={chatInputRef}
                    value={chatInput}
                    onChange={(e) => {
                      handleChatInputChange(e)
                      autoResizeTextarea()
                    }}
                    onKeyDown={handleChatKeyDown}
                    onPaste={handlePaste}
                    placeholder={configContext ? "Ask to modify this file..." : "Ask... (@ to mention, paste/drop images)"}
                    className="flex-1 px-2 py-1.5 rounded-md border bg-background text-xs focus:outline-none focus:ring-1 focus:ring-primary resize-none overflow-hidden min-h-[30px]"
                    disabled={isLoading}
                    rows={1}
                    style={{ maxHeight: '150px' }}
                  />
                  <Button 
                    onClick={handleSendChat} 
                    disabled={isLoading || (!chatInput.trim() && attachedImages.length === 0)}
                    size="icon"
                    className="h-7 w-7 flex-shrink-0"
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

          {/* Terminal Mode */}
          {mode === 'terminal' && (
            <>
              {/* Terminal Output */}
              <div className="flex-1 overflow-y-auto p-3 bg-zinc-950 font-mono text-xs">
                {terminalLines.map((line) => (
                  <div
                    key={line.id}
                    className={cn(
                      "whitespace-pre-wrap mb-1",
                      line.type === 'input' && "text-green-400",
                      line.type === 'output' && "text-zinc-300",
                      line.type === 'error' && "text-red-400"
                    )}
                  >
                    {line.content}
                  </div>
                ))}
                <div ref={terminalEndRef} />
              </div>

              {/* Terminal Input */}
              <div className="p-2 border-t border-zinc-800 bg-zinc-950">
                <div className="flex items-center gap-2">
                  <span className="text-green-400 font-mono text-xs">$</span>
                  <input
                    ref={terminalInputRef}
                    type="text"
                    value={terminalInput}
                    onChange={(e) => setTerminalInput(e.target.value)}
                    onKeyDown={handleTerminalKeyDown}
                    placeholder="Enter command..."
                    className="flex-1 bg-transparent text-zinc-100 font-mono text-xs focus:outline-none"
                    autoFocus={mode === 'terminal'}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      )}
      
      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={deleteCurrentConversation}
        title="Delete Conversation"
        description="Are you sure you want to delete this conversation? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
      />
    </div>
  )
}
