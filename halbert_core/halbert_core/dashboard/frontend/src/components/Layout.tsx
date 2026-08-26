// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Layout — the application shell.
 *
 * Halbert has two surfaces and this is where they meet:
 *
 *   engaged   the Sovereign Host canvas — conversation spine + context stage.
 *   browsing  the system administration hub — the full navigation rail, every
 *             dashboard page, and the side panel, unchanged.
 *
 * A global top bar carries the mode switch (Cmd/Ctrl+B), the background-work
 * indicators and debug, so nothing that used to live in the sidebar footer
 * disappears when the sidebar does.
 */

import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Server,
  Archive,
  CheckCircle,
  HardDrive,
  Wifi,
  Share2,
  Shield,
  Settings,
  Bug,
  Cpu,
  Container,
  Code2,
  Package,
  Loader2,
  ScanSearch,
  Bot,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidePanel } from './SidePanel'
import { ConfigEditor } from './ConfigEditor'
import { ModeSwitch } from './shell/ModeSwitch'
import { SovereignHostShell } from './shell/SovereignHostShell'
import { useDebug } from '@/contexts/DebugContext'
import { useShellMode } from '@/contexts/ShellModeContext'
import { apiUrl } from '@/lib/apiBase'

const navigation = [
  // Overview
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Agent', href: '/agent', icon: Bot },

  // Essential System Health
  { name: 'Services', href: '/services', icon: Server },
  { name: 'Storage', href: '/storage', icon: HardDrive },
  { name: 'Backups', href: '/backups', icon: Archive },
  { name: 'Apps', href: '/apps', icon: Package },
  { name: 'Security', href: '/security', icon: Shield },

  // Networking
  { name: 'Network', href: '/network', icon: Wifi },
  { name: 'Sharing', href: '/sharing', icon: Share2 },

  // Dev & Advanced
  { name: 'Containers', href: '/containers', icon: Container },
  { name: 'GPU', href: '/gpu', icon: Cpu },
  { name: 'Development', href: '/development', icon: Code2 },

  // Utility
  { name: 'Approvals', href: '/approvals', icon: CheckCircle },
  { name: 'Settings', href: '/settings', icon: Settings },
]

interface ProgressPillProps {
  icon: React.ReactNode
  label: string
  percent: number
  detail: string | null
  tone: 'emerald' | 'blue'
}

/** Background work (scan / index) shown in the top bar, in either mode. */
function ProgressPill({ icon, label, percent, detail, tone }: ProgressPillProps) {
  const toneClasses = tone === 'emerald'
    ? 'bg-success/10 border-success/30 text-success'
    : 'bg-info/10 border-info/30 text-info'
  const barClasses = tone === 'emerald' ? 'bg-success' : 'bg-info'

  return (
    <div
      className={cn('flex items-center gap-2 rounded border px-2 py-1 text-[11px]', toneClasses)}
      title={detail || label}
    >
      {icon}
      <span className="font-medium hidden md:inline">{label}</span>
      <div className="w-16 h-1 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-300', barClasses)}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono tabular-nums">{percent}%</span>
    </div>
  )
}

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const { isDebugMode, setDebugMode, chatMetrics, logs, clearLogs } = useDebug()
  const { isEngaged } = useShellMode()

  // Global config editor state (triggered from chat "Edit Config" button)
  const [editingConfigPath, setEditingConfigPath] = useState<string | null>(null)

  // Indexing status state (moved from Settings)
  const [indexing, setIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{
    percent: number
    currentSource: string | null
    completed: number
    total: number
  }>({ percent: 0, currentSource: null, completed: 0, total: 0 })

  // System scan status state
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<{
    percent: number
    currentPhase: string | null
  }>({ percent: 0, currentPhase: null })

  // Listen for open-config-editor events from chat
  useEffect(() => {
    const handleOpenConfigEditor = (e: CustomEvent<{ filePath: string }>) => {
      console.log('[Layout] Opening config editor for:', e.detail.filePath)
      setEditingConfigPath(e.detail.filePath)
    }

    window.addEventListener('halbert:open-config-editor', handleOpenConfigEditor as EventListener)
    return () => {
      window.removeEventListener('halbert:open-config-editor', handleOpenConfigEditor as EventListener)
    }
  }, [])

  // Poll for indexing and scan status
  useEffect(() => {
    const checkStatus = async () => {
      // Check indexing status
      try {
        const res = await fetch(apiUrl('/api/settings/docs/stats'))
        const data = await res.json()
        const status = data.indexing

        if (status?.is_running) {
          setIndexing(true)
          setIndexProgress({
            percent: status.progress_percent || 0,
            currentSource: status.current_source,
            completed: status.sources_completed?.length || 0,
            total: status.sources_total || 0
          })
        } else {
          setIndexing(false)
        }
      } catch (err) {
        // Silently fail - indexing status is non-critical
      }

      // Check system scan status
      try {
        const res = await fetch(apiUrl('/api/settings/system-profile/scan/status'))
        const data = await res.json()

        if (data.is_running) {
          setScanning(true)
          setScanProgress({
            percent: data.progress_percent || 0,
            currentPhase: data.current_phase
          })
        } else {
          setScanning(false)
        }
      } catch (err) {
        // Silently fail - scan status is non-critical
      }
    }

    // Check immediately on mount
    checkStatus()

    // Poll every 2 seconds
    const interval = setInterval(checkStatus, 2000)
    return () => clearInterval(interval)
  }, [])

  // Listen for screenshot capture requests from chat input
  useEffect(() => {
    const handleCaptureScreenshot = async () => {
      try {
        // Use html2canvas to capture the window
        const html2canvas = (await import('html2canvas')).default
        const canvas = await html2canvas(document.body, {
          useCORS: true,
          logging: false,
        })

        // Convert to base64 (strip the data URL prefix for the API)
        const dataUrl = canvas.toDataURL('image/png')
        const base64 = dataUrl.replace(/^data:image\/\w+;base64,/, '')

        // Dispatch event to add screenshot to chat
        window.dispatchEvent(new CustomEvent('halbert:add-screenshot', {
          detail: {
            dataUrl,  // Full data URL for preview
            base64,   // Just base64 for API
            name: `Screenshot ${new Date().toLocaleTimeString()}`
          }
        }))

        console.log('[Layout] Screenshot captured and dispatched to chat')
      } catch (err) {
        console.error('[Layout] Failed to capture screenshot:', err)
      }
    }

    window.addEventListener('halbert:capture-screenshot', handleCaptureScreenshot)
    return () => {
      window.removeEventListener('halbert:capture-screenshot', handleCaptureScreenshot)
    }
  }, [])

  const configEditor = editingConfigPath ? (
    <ConfigEditor
      filePath={editingConfigPath}
      onClose={() => setEditingConfigPath(null)}
    />
  ) : null

  return (
    <div className="h-screen bg-background flex flex-col overflow-hidden">
      {/* Global top bar — present in both modes */}
      <header className="flex items-center gap-3 px-4 h-12 border-b bg-card shrink-0">
        <div className="flex items-center gap-2 shrink-0">
          <img src="/Halbert.png" alt="Halbert" className="h-5 w-5" />
          <span className="text-sm font-semibold hidden sm:inline">Halbert</span>
        </div>

        <ModeSwitch />

        <div className="flex-1" />

        {scanning && (
          <ProgressPill
            icon={<ScanSearch className="h-3 w-3 animate-pulse" />}
            label="Scanning"
            percent={scanProgress.percent}
            detail={scanProgress.currentPhase}
            tone="emerald"
          />
        )}
        {indexing && (
          <ProgressPill
            icon={<Loader2 className="h-3 w-3 animate-spin" />}
            label="Indexing"
            percent={indexProgress.percent}
            detail={indexProgress.currentSource}
            tone="blue"
          />
        )}

        <span className="text-[11px] text-muted-foreground font-mono hidden md:inline">v0.1.1</span>
        <Button
          variant={isDebugMode ? 'default' : 'ghost'}
          size="icon"
          className={cn('h-6 w-6', isDebugMode && 'bg-success hover:bg-success/90 text-primary-foreground')}
          onClick={() => setDebugMode(!isDebugMode)}
          title={isDebugMode ? 'Debug ON' : 'Debug'}
        >
          <Bug className="h-3 w-3" />
        </Button>
      </header>

      {/* Mode content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {isEngaged ? (
          configEditor ? (
            <div className="h-full overflow-auto p-8">{configEditor}</div>
          ) : (
            <SovereignHostShell />
          )
        ) : (
          <div className="flex h-full overflow-hidden">
            {/* Navigation rail */}
            <nav className="w-64 shrink-0 border-r bg-card overflow-y-auto px-4 py-4 space-y-1">
              {navigation.map((item) => {
                const isActive = location.pathname === item.href
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                    )}
                  >
                    <item.icon className="h-5 w-5" />
                    {item.name}
                  </Link>
                )
              })}
            </nav>

            {/* Page content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <main className="flex-1 p-8 overflow-auto relative z-0">
                {configEditor ?? children}
              </main>
            </div>

            {/* Side Panel - Chat/Terminal, always visible while browsing */}
            <SidePanel />
          </div>
        )}
      </div>

      {/* Debug Panel - non-overlaying, stats on left, logs on right */}
      {isDebugMode && (
        <div className="border-t bg-muted h-48 flex text-xs font-mono shrink-0">
          {/* Left: Stats */}
          <div className="w-48 border-r border-border p-3 flex flex-col gap-2">
            <div className="text-success font-bold flex items-center gap-1">
              <Bug className="h-3 w-3" /> Debug Mode
            </div>
            <div className="space-y-1 text-foreground">
              <div><span className="text-success">Requests:</span> {chatMetrics.totalRequests}</div>
              <div><span className="text-success">Tokens:</span> ~{chatMetrics.totalTokensEstimate}</div>
              <div><span className="text-success">Avg:</span> {chatMetrics.averageResponseTime > 0 ? `${chatMetrics.averageResponseTime.toFixed(0)}ms` : '-'}</div>
              <div><span className="text-success">Last:</span> {chatMetrics.lastResponseTime && chatMetrics.lastRequestTime ? `${(chatMetrics.lastResponseTime - chatMetrics.lastRequestTime).toFixed(0)}ms` : '-'}</div>
            </div>
          </div>
          {/* Right: Logs */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-card">
              <span className="text-foreground">Logs ({logs.length})</span>
              <button onClick={clearLogs} className="text-muted-foreground hover:text-foreground text-[10px]">Clear</button>
            </div>
            <div className="flex-1 overflow-auto p-2">
              {logs.length === 0 ? (
                <div className="text-muted-foreground text-center py-4">No logs yet. Interact with the app to see logs.</div>
              ) : (
                logs.slice().reverse().map(log => (
                  <div key={log.id} className={cn(
                    "py-0.5",
                    log.type === 'error' && "text-error",
                    log.type === 'timing' && "text-warning",
                    log.type === 'request' && "text-info",
                    log.type === 'response' && "text-success",
                    log.type === 'info' && "text-foreground"
                  )}>
                    <span className="text-muted-foreground">[{log.timestamp.toLocaleTimeString()}]</span>
                    <span className="text-muted-foreground ml-1">[{log.category}]</span>
                    <span className="ml-1">{log.message}</span>
                    {log.duration && <span className="text-muted-foreground ml-1">({log.duration.toFixed(0)}ms)</span>}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
