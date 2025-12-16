/**
 * CodeBlock - Executable code block with copy and run buttons
 * 
 * Phase 20D: Extracted from Services.tsx for reuse across pages
 * 
 * Features:
 * - Copy to clipboard
 * - Run in terminal (for shell commands)
 * - Syntax highlighting (basic)
 * - Distinguishes runnable commands from output display
 */

import { useState } from 'react'
import { Terminal, Copy, Check, Play, Loader2 } from 'lucide-react'

interface CodeBlockProps {
  code: string
  lang?: string
  /** Callback for running commands - receives sanitized command string */
  onRun?: (command: string) => Promise<{ output?: string; error?: string; exit_code?: number }>
  /** Auto-analyze callback after command execution */
  onAutoAnalyze?: (command: string, output: string, isError: boolean) => void
  /** Show/hide the run button even for shell commands */
  showRunButton?: boolean
  /** Compact mode - smaller padding */
  compact?: boolean
}

export function CodeBlock({ 
  code, 
  lang = 'bash',
  onRun,
  onAutoAnalyze,
  showRunButton = true,
  compact = false,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [output, setOutput] = useState<string | null>(null)
  const [isError, setIsError] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  
  // Detect if this looks like command OUTPUT (not a runnable command)
  const looksLikeOutput = (
    code.includes('Loaded:') ||           // systemd status output
    code.includes('Active:') ||           // systemd status output
    code.includes('Process:') ||          // systemd process info
    code.startsWith('$ ') ||              // Shows a command with prompt (display, not runnable)
    code.startsWith('# ') ||              // Root prompt display
    /^\d{4}-\d{2}-\d{2}/.test(code) ||    // Starts with date (log output)
    /^[A-Z][a-z]{2} \d{1,2} \d{2}:/.test(code) ||  // Log timestamp like "Dec 13 10:42:09"
    code.split('\n').length > 10 ||       // Very long = probably output, not a command
    /^total \d+/.test(code) ||            // ls output
    /^-[rwx-]{9}/.test(code)              // ls -l output
  )
  
  const isShellCommand = !looksLikeOutput && (
    ['bash', 'sh', 'shell', 'zsh', ''].includes(lang.toLowerCase()) || 
    code.startsWith('sudo ') || 
    code.startsWith('ls ') ||
    code.includes('|')
  )
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  
  const handleRun = async () => {
    if (!onRun) {
      // Fallback: dispatch event to terminal
      window.dispatchEvent(new CustomEvent('halbert:run-command', { 
        detail: { command: code } 
      }))
      return
    }
    
    setIsRunning(true)
    setOutput(null)
    try {
      // Sanitize command - remove stray backticks that LLMs sometimes add
      const sanitizedCode = code.replace(/^`+|`+$/g, '').trim()
      const result = await onRun(sanitizedCode)
      const outputText = result.exit_code === 0 
        ? (result.output || '(no output)')
        : (result.error || result.output || `Exit code: ${result.exit_code}`)
      const hasError = result.exit_code !== 0
      
      setOutput(outputText)
      setIsError(hasError)
      
      // Auto-analyze: send output back to AI for analysis
      if (onAutoAnalyze) {
        onAutoAnalyze(sanitizedCode, outputText, hasError)
      }
    } catch (err) {
      const errorMsg = `Error: ${err}`
      setOutput(errorMsg)
      setIsError(true)
      if (onAutoAnalyze) {
        onAutoAnalyze(code, errorMsg, true)
      }
    } finally {
      setIsRunning(false)
    }
  }
  
  return (
    <div className="space-y-1 min-w-0">
      <div className="rounded-md overflow-hidden border border-border/50 bg-zinc-900 my-2">
        {/* Header */}
        <div className="flex items-center justify-between px-2 py-1 bg-zinc-800 border-b border-border/30">
          <div className="flex items-center gap-1.5">
            <Terminal className="h-3 w-3 text-green-400" />
            <span className="text-[10px] text-zinc-400 font-mono">{lang || 'bash'}</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopy}
              className="p-1 rounded hover:bg-zinc-700 transition-colors"
              title="Copy"
            >
              {copied ? (
                <Check className="h-3 w-3 text-green-400" />
              ) : (
                <Copy className="h-3 w-3 text-zinc-400" />
              )}
            </button>
            {isShellCommand && showRunButton && (
              <button
                onClick={handleRun}
                disabled={isRunning}
                className="p-1 rounded hover:bg-zinc-700 transition-colors disabled:opacity-50"
                title="Run in Terminal"
              >
                {isRunning ? (
                  <Loader2 className="h-3 w-3 text-blue-400 animate-spin" />
                ) : (
                  <Play className="h-3 w-3 text-green-400" />
                )}
              </button>
            )}
          </div>
        </div>
        
        {/* Code content */}
        <pre className={`${compact ? 'p-2' : 'p-3'} text-[11px] font-mono overflow-x-auto max-w-full ${
          isShellCommand 
            ? 'text-green-300'  // Runnable command
            : 'text-zinc-200'   // Output/display
        }`}>
          <code className="break-all">{code}</code>
        </pre>
      </div>
      
      {/* Output display */}
      {output && (
        <div className={`rounded-md border ${isError ? 'border-red-500/30 bg-red-950/20' : 'border-border/50 bg-zinc-800/50'}`}>
          <div className="flex items-center justify-between px-2 py-1 border-b border-border/30">
            <span className={`text-[10px] font-mono ${isError ? 'text-red-400' : 'text-zinc-400'}`}>
              {isError ? 'Error' : 'Output'}
            </span>
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="text-[10px] text-zinc-500 hover:text-zinc-300"
            >
              {isCollapsed ? 'Show' : 'Hide'}
            </button>
          </div>
          {!isCollapsed && (
            <pre className="p-2 text-[10px] font-mono text-zinc-300 overflow-x-auto max-h-40">
              <code>{output}</code>
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

export default CodeBlock
