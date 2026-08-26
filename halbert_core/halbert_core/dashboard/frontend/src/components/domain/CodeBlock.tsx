// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * CodeBlock - Executable code block with copy and run buttons
 * 
 * Phase 20D: Extracted from Services.tsx for reuse across pages
 * Phase 13d: Added command safety checks with warning dialogs
 * 
 * Features:
 * - Copy to clipboard
 * - Run in terminal (for shell commands)
 * - Syntax highlighting (basic)
 * - Distinguishes runnable commands from output display
 * - Safety tier warnings before dangerous commands
 */

import { useState } from 'react'
import { Terminal, Copy, Check, Play, Loader2, SkipForward, AlertTriangle, ShieldAlert } from 'lucide-react'
import { api } from '@/lib/api'

interface CodeBlockProps {
  code: string
  lang?: string
  /** Callback for running commands - receives sanitized command string */
  onRun?: (command: string) => Promise<{ output?: string; error?: string; exit_code?: number }>
  /** Auto-analyze callback after command execution */
  onAutoAnalyze?: (command: string, output: string, isError: boolean) => void
  /** Callback when command is skipped */
  onSkip?: (command: string) => void
  /** Show/hide the run button even for shell commands */
  showRunButton?: boolean
  /** Compact mode - smaller padding */
  compact?: boolean
  /** Unique ID for this code block (for tracking) */
  blockId?: string
}

interface SafetyWarning {
  tier: 'caution' | 'dangerous' | 'blocked'
  warning: string
  suggestion: string
}

export function CodeBlock({ 
  code, 
  lang = 'bash',
  onRun,
  onAutoAnalyze,
  onSkip,
  showRunButton = true,
  compact = false,
  blockId: _blockId,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [output, setOutput] = useState<string | null>(null)
  const [isError, setIsError] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [isSkipped, setIsSkipped] = useState(false)
  const [isHandled, setIsHandled] = useState(false)  // Track if run or skipped
  // Phase 13d: Safety warning state
  const [safetyWarning, setSafetyWarning] = useState<SafetyWarning | null>(null)
  const [pendingCommand, setPendingCommand] = useState<string | null>(null)
  
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
  
  // Phase 13d: Execute command (after safety check passed or confirmed)
  const executeCommand = async (sanitizedCode: string) => {
    setIsRunning(true)
    setOutput(null)
    setSafetyWarning(null)
    setPendingCommand(null)
    try {
      const result = await onRun!(sanitizedCode)
      const outputText = result.exit_code === 0 
        ? (result.output || '(no output)')
        : (result.error || result.output || `Exit code: ${result.exit_code}`)
      const hasError = result.exit_code !== 0
      
      setOutput(outputText)
      setIsError(hasError)
      setIsHandled(true)
      
      // Auto-analyze: send output back to AI for analysis
      if (onAutoAnalyze) {
        onAutoAnalyze(sanitizedCode, outputText, hasError)
      }
    } catch (err) {
      const errorMsg = `Error: ${err}`
      setOutput(errorMsg)
      setIsError(true)
      setIsHandled(true)
      if (onAutoAnalyze) {
        onAutoAnalyze(sanitizedCode, errorMsg, true)
      }
    } finally {
      setIsRunning(false)
    }
  }
  
  const handleRun = async () => {
    if (isHandled) return  // Already handled
    
    if (!onRun) {
      // Fallback: dispatch event to terminal
      window.dispatchEvent(new CustomEvent('halbert:run-command', { 
        detail: { command: code } 
      }))
      return
    }
    
    // Sanitize command - remove stray backticks that LLMs sometimes add
    const sanitizedCode = code.replace(/^`+|`+$/g, '').trim()
    
    // Phase 13d: Check command safety before execution
    try {
      const safety = await api.checkCommandSafety(sanitizedCode)
      
      if (safety.tier === 'blocked') {
        setOutput(`⛔ Command blocked: ${safety.warning}`)
        setIsError(true)
        setIsHandled(true)
        return
      }
      
      if (safety.tier === 'dangerous' || safety.tier === 'caution') {
        // Show warning and wait for confirmation
        setSafetyWarning({
          tier: safety.tier,
          warning: safety.warning,
          suggestion: safety.suggestion,
        })
        setPendingCommand(sanitizedCode)
        return
      }
      
      // Safe command - execute directly
      await executeCommand(sanitizedCode)
    } catch (err) {
      // Safety check failed - execute anyway with warning
      console.warn('Safety check failed, executing anyway:', err)
      await executeCommand(sanitizedCode)
    }
  }
  
  // Phase 13d: Confirm execution of dangerous command
  const handleConfirmRun = async () => {
    if (pendingCommand) {
      await executeCommand(pendingCommand)
    }
  }
  
  // Phase 13d: Cancel dangerous command
  const handleCancelRun = () => {
    setSafetyWarning(null)
    setPendingCommand(null)
  }
  
  const handleSkip = () => {
    if (isHandled) return  // Already handled
    setIsSkipped(true)
    setIsHandled(true)
    if (onSkip) {
      onSkip(code)
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
            {isShellCommand && showRunButton && !isHandled && (
              <>
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
                <button
                  onClick={handleSkip}
                  disabled={isRunning}
                  className="p-1 rounded hover:bg-zinc-700 transition-colors disabled:opacity-50"
                  title="Skip this command"
                >
                  <SkipForward className="h-3 w-3 text-zinc-400" />
                </button>
              </>
            )}
            {isSkipped && (
              <span className="text-[10px] text-zinc-500 italic">skipped</span>
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
      
      {/* Phase 13d: Safety warning dialog */}
      {safetyWarning && (
        <div className={`rounded-md border p-2 my-1 ${
          safetyWarning.tier === 'dangerous' 
            ? 'border-red-500/50 bg-red-950/30' 
            : 'border-yellow-500/50 bg-yellow-950/30'
        }`}>
          <div className="flex items-start gap-2">
            {safetyWarning.tier === 'dangerous' ? (
              <ShieldAlert className="h-4 w-4 text-red-400 flex-shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className={`text-[11px] font-medium ${
                safetyWarning.tier === 'dangerous' ? 'text-red-300' : 'text-yellow-300'
              }`}>
                {safetyWarning.tier === 'dangerous' ? '⚠️ Dangerous Command' : '⚡ Caution'}
              </p>
              <p className="text-[10px] text-zinc-300 mt-0.5">{safetyWarning.warning}</p>
              {safetyWarning.suggestion && (
                <p className="text-[10px] text-zinc-400 mt-1">💡 {safetyWarning.suggestion}</p>
              )}
              <div className="flex gap-2 mt-2">
                <button
                  onClick={handleConfirmRun}
                  disabled={isRunning}
                  className={`px-2 py-1 text-[10px] rounded ${
                    safetyWarning.tier === 'dangerous'
                      ? 'bg-red-600 hover:bg-red-700 text-white'
                      : 'bg-yellow-600 hover:bg-yellow-700 text-white'
                  }`}
                >
                  {isRunning ? 'Running...' : 'Run Anyway'}
                </button>
                <button
                  onClick={handleCancelRun}
                  className="px-2 py-1 text-[10px] rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-200"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
