/**
 * Terminal Page - AI-enhanced terminal with Coder persona.
 * 
 * Architecture:
 * - xterm.js for output display
 * - Separate textarea for input (click-anywhere editing!)
 * - AI overlay for /explain, /dryrun, /fix commands
 * - WebSocket connection to PTY backend
 */

import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { 
  Play, 
  HelpCircle, 
  Eye, 
  Wrench, 
  Loader2,
  TerminalIcon,
  Sparkles,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface CommandHistory {
  command: string
  output: string
  timestamp: Date
  exitCode?: number
}

interface AISuggestion {
  type: 'explain' | 'fix' | 'dryrun' | 'suggestion'
  content: string
  actions?: Array<{ label: string; command: string }>
}

export function Terminal() {
  const terminalRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [history, setHistory] = useState<CommandHistory[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [aiSuggestion, setAiSuggestion] = useState<AISuggestion | null>(null)
  const [isAiLoading, setIsAiLoading] = useState(false)
  const [showAiPanel, setShowAiPanel] = useState(true)
  const [lastOutput, setLastOutput] = useState('')

  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Initialize xterm
  useEffect(() => {
    if (!terminalRef.current || xtermRef.current) return

    const term = new XTerm({
      cursorBlink: false,
      cursorStyle: 'bar',
      fontSize: 14,
      fontFamily: 'JetBrains Mono, Menlo, Monaco, monospace',
      theme: {
        background: '#1a1b26',
        foreground: '#a9b1d6',
        cursor: '#c0caf5',
        cursorAccent: '#1a1b26',
        selectionBackground: '#33467c',
        black: '#32344a',
        red: '#f7768e',
        green: '#9ece6a',
        yellow: '#e0af68',
        blue: '#7aa2f7',
        magenta: '#bb9af7',
        cyan: '#7dcfff',
        white: '#a9b1d6',
        brightBlack: '#444b6a',
        brightRed: '#ff7a93',
        brightGreen: '#b9f27c',
        brightYellow: '#ff9e64',
        brightBlue: '#7da6ff',
        brightMagenta: '#c29fff',
        brightCyan: '#0db9d7',
        brightWhite: '#c0caf5',
      },
      scrollback: 5000,
      convertEol: true,
    })

    const fitAddon = new FitAddon()
    const webLinksAddon = new WebLinksAddon()
    
    term.loadAddon(fitAddon)
    term.loadAddon(webLinksAddon)
    term.open(terminalRef.current)
    
    fitAddon.fit()
    
    xtermRef.current = term
    fitAddonRef.current = fitAddon

    // Welcome message
    term.writeln('\x1b[1;36m╔══════════════════════════════════════════╗\x1b[0m')
    term.writeln('\x1b[1;36m║\x1b[0m  \x1b[1;33mCerebric Terminal\x1b[0m                       \x1b[1;36m║\x1b[0m')
    term.writeln('\x1b[1;36m║\x1b[0m  AI-enhanced shell with /explain /dryrun \x1b[1;36m║\x1b[0m')
    term.writeln('\x1b[1;36m╚══════════════════════════════════════════╝\x1b[0m')
    term.writeln('')

    // Handle resize
    const handleResize = () => {
      fitAddon.fit()
    }
    window.addEventListener('resize', handleResize)

    // Connect WebSocket
    connectWebSocket()

    return () => {
      window.removeEventListener('resize', handleResize)
      term.dispose()
      wsRef.current?.close()
    }
  }, [])

  const connectWebSocket = () => {
    // For MVP, we'll simulate - real impl needs PTY backend
    setIsConnected(true)
    xtermRef.current?.writeln('\x1b[32m● Connected to local shell\x1b[0m')
    xtermRef.current?.writeln('')
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    
    // Check for /slash commands
    if (e.target.value.startsWith('/')) {
      handleSlashCommand(e.target.value)
    } else {
      // Clear AI suggestion when typing regular command
      if (!isAiLoading) {
        setAiSuggestion(null)
      }
    }
  }

  const handleSlashCommand = (cmd: string) => {
    const lower = cmd.toLowerCase()
    
    if (lower === '/explain' || lower === '/e') {
      setAiSuggestion({
        type: 'explain',
        content: 'Type /explain and press Enter to get an explanation of the last command output.',
      })
    } else if (lower === '/fix' || lower === '/f') {
      setAiSuggestion({
        type: 'fix',
        content: 'Type /fix and press Enter to get suggestions for fixing errors.',
      })
    } else if (lower === '/dryrun' || lower === '/d') {
      setAiSuggestion({
        type: 'dryrun',
        content: 'Type a command after /dryrun to preview its effects without executing.',
      })
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      executeCommand()
    } else if (e.key === 'ArrowUp' && history.length > 0) {
      e.preventDefault()
      const newIndex = Math.min(historyIndex + 1, history.length - 1)
      setHistoryIndex(newIndex)
      setInput(history[history.length - 1 - newIndex]?.command || '')
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const newIndex = Math.max(historyIndex - 1, -1)
      setHistoryIndex(newIndex)
      setInput(newIndex === -1 ? '' : history[history.length - 1 - newIndex]?.command || '')
    }
  }

  const executeCommand = async () => {
    const cmd = input.trim()
    if (!cmd || isRunning) return

    setInput('')
    setHistoryIndex(-1)

    // Handle /slash commands
    if (cmd.startsWith('/')) {
      await handleAICommand(cmd)
      return
    }

    // Execute shell command
    setIsRunning(true)
    xtermRef.current?.writeln(`\x1b[1;34m$\x1b[0m ${cmd}`)

    try {
      const response = await fetch('/api/terminal/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      })

      if (response.ok) {
        const data = await response.json()
        const output = data.output || ''
        
        // Write output to terminal
        output.split('\n').forEach((line: string) => {
          xtermRef.current?.writeln(line)
        })
        
        setLastOutput(output)
        
        // Add to history
        setHistory(prev => [...prev, {
          command: cmd,
          output,
          timestamp: new Date(),
          exitCode: data.exit_code,
        }])

        // Check for errors and offer help
        if (data.exit_code !== 0) {
          setAiSuggestion({
            type: 'fix',
            content: `Command exited with code ${data.exit_code}. Would you like me to help fix this?`,
            actions: [
              { label: 'Explain Error', command: '/explain' },
              { label: 'Suggest Fix', command: '/fix' },
            ],
          })
        }
      } else {
        // Fallback: simulate for demo
        xtermRef.current?.writeln(`\x1b[33mCommand would execute: ${cmd}\x1b[0m`)
        setLastOutput(`(simulated) ${cmd}`)
      }
    } catch (error) {
      // Simulate for demo
      xtermRef.current?.writeln(`\x1b[33m[Demo mode] ${cmd}\x1b[0m`)
      setLastOutput(`${cmd}`)
    } finally {
      setIsRunning(false)
      xtermRef.current?.writeln('')
    }
  }

  const handleAICommand = async (cmd: string) => {
    const parts = cmd.split(' ')
    const slashCmd = parts[0].toLowerCase()
    const args = parts.slice(1).join(' ')

    setIsAiLoading(true)

    try {
      if (slashCmd === '/explain' || slashCmd === '/e') {
        await simulateAIResponse('explain', lastOutput)
      } else if (slashCmd === '/fix' || slashCmd === '/f') {
        await simulateAIResponse('fix', lastOutput)
      } else if (slashCmd === '/dryrun' || slashCmd === '/d') {
        if (args) {
          await simulateAIResponse('dryrun', args)
        } else {
          setAiSuggestion({
            type: 'dryrun',
            content: 'Usage: /dryrun <command>\n\nExample: /dryrun rm -rf node_modules',
          })
        }
      } else if (slashCmd === '/help' || slashCmd === '/h') {
        setAiSuggestion({
          type: 'suggestion',
          content: '**Available Commands:**\n\n' +
            '• `/explain` or `/e` - Explain the last command output\n' +
            '• `/fix` or `/f` - Get suggestions for fixing errors\n' +
            '• `/dryrun <cmd>` or `/d` - Preview command effects\n' +
            '• `/help` or `/h` - Show this help',
        })
      }
    } finally {
      setIsAiLoading(false)
    }
  }

  const simulateAIResponse = async (type: string, context: string) => {
    // Simulate AI thinking
    await new Promise(resolve => setTimeout(resolve, 1000))

    if (type === 'explain') {
      setAiSuggestion({
        type: 'explain',
        content: context 
          ? `**Explanation:**\n\nThe command output shows:\n${context.slice(0, 200)}...\n\nThis appears to be a standard system response.`
          : 'No recent command output to explain. Run a command first!',
      })
    } else if (type === 'fix') {
      setAiSuggestion({
        type: 'fix',
        content: '**Suggested Fixes:**\n\n1. Check if the command exists: `which <command>`\n2. Verify permissions: `ls -la`\n3. Check for typos in the command',
        actions: [
          { label: 'Run Diagnostic', command: 'echo $PATH' },
        ],
      })
    } else if (type === 'dryrun') {
      setAiSuggestion({
        type: 'dryrun',
        content: `**Dry Run Preview:**\n\n\`${context}\`\n\n**This command would:**\n• Execute in the current directory\n• May modify files (check carefully)\n\n**Risk Level:** ⚠️ Medium`,
        actions: [
          { label: 'Execute', command: context },
          { label: 'Cancel', command: '' },
        ],
      })
    }
  }

  const handleActionClick = (command: string) => {
    if (command) {
      setInput(command)
      inputRef.current?.focus()
    }
    setAiSuggestion(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TerminalIcon className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Terminal</h1>
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full",
            isConnected ? "bg-green-500/20 text-green-500" : "bg-red-500/20 text-red-500"
          )}>
            {isConnected ? '● Connected' : '○ Disconnected'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowAiPanel(!showAiPanel)}
          >
            <Sparkles className="h-4 w-4 mr-1" />
            AI {showAiPanel ? 'On' : 'Off'}
          </Button>
        </div>
      </div>

      {/* Main Terminal Area */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Terminal Output */}
        <div className="flex-1 flex flex-col min-w-0">
          <div 
            ref={terminalRef}
            className="flex-1 rounded-lg overflow-hidden bg-[#1a1b26] p-2"
          />
          
          {/* Command Input */}
          <div className="mt-3 space-y-2">
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <span className="absolute left-3 top-2.5 text-primary font-mono text-sm">$</span>
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Enter command... (type /help for AI commands)"
                  className="w-full pl-7 pr-3 py-2 rounded-md border bg-card font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                  rows={1}
                  disabled={isRunning}
                  style={{ minHeight: '40px' }}
                />
              </div>
              <Button
                onClick={executeCommand}
                disabled={!input.trim() || isRunning}
                className="px-4"
              >
                {isRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
              </Button>
            </div>
            
            {/* Quick Actions */}
            <div className="flex gap-2 text-xs">
              <button
                onClick={() => setInput('/explain')}
                className="flex items-center gap-1 px-2 py-1 rounded bg-muted hover:bg-accent"
              >
                <HelpCircle className="h-3 w-3" />
                /explain
              </button>
              <button
                onClick={() => setInput('/dryrun ')}
                className="flex items-center gap-1 px-2 py-1 rounded bg-muted hover:bg-accent"
              >
                <Eye className="h-3 w-3" />
                /dryrun
              </button>
              <button
                onClick={() => setInput('/fix')}
                className="flex items-center gap-1 px-2 py-1 rounded bg-muted hover:bg-accent"
              >
                <Wrench className="h-3 w-3" />
                /fix
              </button>
            </div>
          </div>
        </div>

        {/* AI Panel */}
        {showAiPanel && (
          <Card className="w-80 flex flex-col">
            <div className="p-3 border-b flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="font-medium text-sm">AI Assistant</span>
              </div>
              <span className="text-xs text-muted-foreground">Coder</span>
            </div>
            <CardContent className="flex-1 p-3 overflow-auto">
              {isAiLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Thinking...
                </div>
              ) : aiSuggestion ? (
                <div className="space-y-3">
                  <div className="text-xs uppercase text-muted-foreground font-medium">
                    {aiSuggestion.type}
                  </div>
                  <div className="text-sm whitespace-pre-wrap">
                    {aiSuggestion.content}
                  </div>
                  {aiSuggestion.actions && (
                    <div className="flex flex-wrap gap-2 pt-2">
                      {aiSuggestion.actions.map((action, i) => (
                        <Button
                          key={i}
                          size="sm"
                          variant="outline"
                          onClick={() => handleActionClick(action.command)}
                        >
                          {action.label}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  <p className="mb-2">Type a command or use:</p>
                  <ul className="space-y-1 text-xs">
                    <li><code>/explain</code> - Explain output</li>
                    <li><code>/dryrun</code> - Preview command</li>
                    <li><code>/fix</code> - Fix errors</li>
                    <li><code>/help</code> - Show all commands</li>
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
