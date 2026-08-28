// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Layout — the application shell.
 *
 * Halbert has two surfaces and this is where they meet:
 *
 *   engaged   the host canvas — conversation spine + context stage. The mode
 *             switch names it after the machine itself.
 *   browsing  the system administration hub — the full navigation rail, every
 *             dashboard page, and the side panel, unchanged.
 *
 * A global top bar carries the mode switch (Cmd/Ctrl+B), the background-work
 * indicators and debug, so nothing that used to live in the sidebar footer
 * disappears when the sidebar does.
 */

import { useState, useEffect } from 'react'
import { Info, Palette, ExternalLink, FileText } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Home as HomeIcon,
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
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { LegalNoticesModal } from '@/components/legal'
import { ComponentLibraryViewer } from '@/components/ComponentLibraryViewer'
import { ConfigEditor } from './ConfigEditor'
import { HalbertMark } from '@/components/brand/HalbertMark'
import { ModeSwitch } from './shell/ModeSwitch'
import { HostShell } from './shell/HostShell'
import { useDebug } from '@/contexts/DebugContext'
import { useShellMode } from '@/contexts/ShellModeContext'
import { askHost, runOnHost, configWithHost } from '@/lib/hostConversation'
import { apiUrl } from '@/lib/apiBase'

type NavItem = { name: string; href: string; icon: typeof LayoutDashboard }
type NavSection = { label: string; items: NavItem[] }

const navSections: NavSection[] = [
  {
    label: 'Overview',
    items: [
      { name: 'Dashboard', href: '/', icon: LayoutDashboard },
      { name: 'Home', href: '/home', icon: HomeIcon },
    ],
  },
  {
    label: 'System',
    items: [
      { name: 'Services', href: '/services', icon: Server },
      { name: 'Storage', href: '/storage', icon: HardDrive },
      { name: 'Backups', href: '/backups', icon: Archive },
      { name: 'Apps', href: '/apps', icon: Package },
      { name: 'Security', href: '/security', icon: Shield },
    ],
  },
  {
    label: 'Network',
    items: [
      { name: 'Network', href: '/network', icon: Wifi },
      { name: 'Sharing', href: '/sharing', icon: Share2 },
    ],
  },
  {
    label: 'Development',
    items: [
      { name: 'Containers', href: '/containers', icon: Container },
      { name: 'GPU', href: '/gpu', icon: Cpu },
      { name: 'Development', href: '/development', icon: Code2 },
    ],
  },
  {
    label: 'Utility',
    items: [
      { name: 'Approvals', href: '/approvals', icon: CheckCircle },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
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
  const { isDebugMode, setDebugMode, logs, clearLogs } = useDebug()
  const { isEngaged, setMode } = useShellMode()

  // Global config editor state (triggered from chat "Edit Config" button)
  const [editingConfigPath, setEditingConfigPath] = useState<string | null>(null)
  const [showAbout, setShowAbout] = useState(false)
  const [showLegalNotices, setShowLegalNotices] = useState(false)
  const [showComponentLibrary, setShowComponentLibrary] = useState(false)

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
  /**
   * The dashboard-to-conversation bridge.
   *
   * Mounted HERE, above the mode ternary, and deliberately not on AgentChat:
   * every one of these buttons renders in browsing mode, where AgentChat does
   * not exist. A listener on AgentChat could never hear the event whose job is
   * to bring AgentChat up.
   *
   * Each handler parks the request and flips to engaged; the conversation
   * drains it once it mounts.
   */
  useEffect(() => {
    const toEngaged = () => setMode('engaged')

    const onOpenChat = (event: Event) => {
      const detail = (event as CustomEvent).detail ?? {}
      askHost({
        // OpenChatEvent calls it prefillMessage.
        prefill: detail.prefillMessage,
        context: detail.context ?? detail.description,
        itemId: detail.itemId,
        title: detail.title,
        configPath: detail.configPath,
      })
      toEngaged()
    }

    // Staged, never executed — see runOnHost.
    const onRunCommand = (event: Event) => {
      const detail = (event as CustomEvent).detail ?? {}
      const command = typeof detail === 'string' ? detail : detail.command
      if (!command) return
      runOnHost(command, detail.title)
      toEngaged()
    }

    const onSendToChat = (event: Event) => {
      const detail = (event as CustomEvent).detail ?? {}
      // GPU's 'Send to chat for execution' sends a command plus its rationale.
      // Staged for reading, like every other command path.
      askHost({
        prefill: detail.command
          ? `Please run this command:\n\n\`\`\`bash\n${detail.command}\n\`\`\``
          : detail.text,
        context: detail.context,
        title: detail.title,
      })
      toEngaged()
    }

    const onSetConfigContext = (event: Event) => {
      const detail = (event as CustomEvent).detail ?? {}
      const path = detail.configPath ?? detail.config_path ?? detail.path
      if (path) configWithHost(path, detail.context)
    }

    window.addEventListener('halbert:open-chat', onOpenChat as EventListener)
    window.addEventListener('halbert:run-command', onRunCommand as EventListener)
    window.addEventListener('halbert:send-to-chat', onSendToChat as EventListener)
    window.addEventListener('halbert:set-config-context', onSetConfigContext as EventListener)
    return () => {
      window.removeEventListener('halbert:open-chat', onOpenChat as EventListener)
      window.removeEventListener('halbert:run-command', onRunCommand as EventListener)
      window.removeEventListener('halbert:send-to-chat', onSendToChat as EventListener)
      window.removeEventListener('halbert:set-config-context', onSetConfigContext as EventListener)
    }
  }, [setMode])

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

  // Listen for screenshot capture requests from chat input.
  // Calls the backend MSS screen capture endpoint (captures the real
  // desktop, not the dashboard DOM like html2canvas did) and dispatches
  // the result back to AgentChat via halbert:add-screenshot.
  useEffect(() => {
    const handleCaptureScreenshot = async () => {
      try {
        const { apiUrl } = await import('../lib/apiBase')
        const resp = await fetch(apiUrl('/api/vision/screenshot'))
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          const msg = err.error || `HTTP ${resp.status}`
          console.error('[Layout] Screenshot failed:', msg)
          // Dispatch an error event so AgentChat can surface it
          window.dispatchEvent(new CustomEvent('halbert:screenshot-error', {
            detail: { error: msg, errorType: err.error_type || 'capture_failed' }
          }))
          return
        }
        const data = await resp.json()
        const dataUrl = `data:image/jpeg;base64,${data.image}`

        window.dispatchEvent(new CustomEvent('halbert:add-screenshot', {
          detail: {
            dataUrl,
            base64: data.image,
            name: `Screenshot ${new Date().toLocaleTimeString()}`
          }
        }))

        console.log('[Layout] Screenshot captured via backend and dispatched to chat')
      } catch (err) {
        console.error('[Layout] Screenshot fetch failed:', err)
        window.dispatchEvent(new CustomEvent('halbert:screenshot-error', {
          detail: { error: String(err), errorType: 'fetch_failed' }
        }))
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
      <header className="flex items-center gap-3 px-4 h-12 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2 shrink-0">
          <HalbertMark size={20} density="medium" tone="accent" />
          <span className="text-sm font-semibold hidden sm:inline text-foreground">Halbert</span>
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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="About">
              <Info className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setShowAbout(true)}>
              <Info className="h-4 w-4 mr-2" />
              About Halbert
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setShowLegalNotices(true)}>
              <FileText className="h-4 w-4 mr-2" />
              Legal Notices
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setShowComponentLibrary(true)}>
              <Palette className="h-4 w-4 mr-2" />
              Developer Tools
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <a href="/docs" target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                Documentation
              </a>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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

      {/* About dialog */}
      {showAbout && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowAbout(false)}>
          <div className="bg-card border rounded-lg shadow-lg max-w-md w-full mx-4 p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <HalbertMark size={24} density="medium" tone="accent" />
              <h2 className="text-lg font-semibold">Halbert</h2>
            </div>
            <p className="text-sm text-muted-foreground">AI-powered system assistant</p>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Version</p>
              <p className="text-sm font-mono">Development Build (v0.1.1)</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => { setShowAbout(false); setShowLegalNotices(true) }}>
                <FileText className="h-4 w-4 mr-1" />
                Legal Notices
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowAbout(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Legal Notices Modal */}
      <LegalNoticesModal open={showLegalNotices} onOpenChange={setShowLegalNotices} />

      {/* Component Library Viewer */}
      {showComponentLibrary && (
        <ComponentLibraryViewer onClose={() => setShowComponentLibrary(false)} />
      )}

      {/* Mode content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {isEngaged ? (
          configEditor ? (
            <div className="h-full overflow-auto p-8">{configEditor}</div>
          ) : (
            <HostShell />
          )
        ) : (
          <div className="flex h-full overflow-hidden">
            {/* Navigation rail */}
            <nav className="w-60 shrink-0 border-r border-border bg-background overflow-y-auto px-3 py-4 space-y-5">
              {navSections.map((section) => (
                <div key={section.label} className="space-y-1">
                  <p className="px-3 text-[10px] font-mono font-semibold uppercase tracking-wider text-muted-foreground/70 mb-1">
                    {section.label}
                  </p>
                  {section.items.map((item) => {
                    const isActive = location.pathname === item.href
                    return (
                      <Link
                        key={item.name}
                        to={item.href}
                        className={cn(
                          'flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-all',
                          isActive
                            ? 'bg-secondary text-foreground font-semibold border border-border/80 shadow-xs'
                            : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
                        )}
                      >
                        <item.icon className={cn("h-4 w-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                        {item.name}
                      </Link>
                    )
                  })}
                </div>
              ))}
            </nav>

            {/* Page content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <main className="flex-1 p-6 md:p-8 overflow-auto relative z-0">
                <div className="max-w-6xl mx-auto w-full">
                  {configEditor ?? children}
                </div>
              </main>
            </div>

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
            <div className="space-y-1 text-muted-foreground">
              {/* Chat metrics were written only by the removed drawer. Rather
                * than render four readouts that can only ever say 0 and '-',
                * say so — a dead sensor reports that it is dead. */}
              <div>[chat metrics unwired]</div>
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
