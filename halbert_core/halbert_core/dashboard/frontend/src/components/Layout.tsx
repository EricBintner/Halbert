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

import { useState, useEffect, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Home as HomeIcon,
  Server,
  Archive,
  HardDrive,
  Shield,
  Settings as SettingsIcon,
  Terminal,
  Loader2,
  ScanSearch,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfigEditor } from './ConfigEditor'
import { HalbertMark, NavRail, type NavRailSection } from '@halbert/design-system'
import { ModeSwitch } from './shell/ModeSwitch'
import { InstanceSwitch, type InstanceInfo } from './shell/InstanceSwitch'
import { AcousticAuraIndicator } from '@/components/audio'
import { HostShell } from './shell/HostShell'
import { useShellMode } from '@/contexts/ShellModeContext'
import { askHost, runOnHost, configWithHost } from '@/lib/hostConversation'
import { apiUrl } from '@/lib/apiBase'

type NavItem = { id: string; label: string; icon: typeof LayoutDashboard }
type NavSection = { label: string; items: NavItem[] }

/**
 * The rail carries the primary domains (TASK-PACKET-02, Task 2.3):
 *
 *   Being & Ambient Home     the host canvas and the spatial home
 *   Intelligence & Findings  what the scans surfaced — findings, not the
 *                            Settings > Security trust gates
 *   Host Controls            the sysadmin surface
 *
 * Settings is the fourth domain but never a rail item: the Settings page
 * overtakes the shell and renders its own rail, so the top-bar gear is the
 * single entry point.
 *
 * Pages that fall outside these domains — Apps, Network, Sharing, Containers,
 * GPU, Development, Approvals — stay routed but leave the rail. They are
 * slated for future sub-views (compute/homelab) and a top-bar approvals badge.
 */
const HOST_CONTROLS = 'Host Controls'

const navSections: NavSection[] = [
  {
    label: 'Being & Ambient Home',
    items: [
      { id: '/', label: 'Dashboard', icon: LayoutDashboard },
      { id: '/home', label: 'Home', icon: HomeIcon },
    ],
  },
  {
    label: 'Intelligence & Findings',
    items: [
      { id: '/findings', label: 'Findings', icon: Shield },
    ],
  },
  {
    label: HOST_CONTROLS,
    items: [
      { id: '/services', label: 'Services', icon: Server },
      { id: '/storage', label: 'Storage', icon: HardDrive },
      { id: '/backups', label: 'Backups', icon: Archive },
      { id: '/terminal', label: 'Terminal', icon: Terminal },
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
  const navigate = useNavigate()
  const { isEngaged, setMode } = useShellMode()

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

  // Multi-instance: current instance info for sidebar filtering
  const [instanceInfo, setInstanceInfo] = useState<InstanceInfo | null>(null)

  // Fetch instance info on mount
  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const res = await fetch(apiUrl('/api/instance/info'))
        if (res.ok) {
          const data = await res.json()
          setInstanceInfo(data)
        }
      } catch {
        // Non-fatal
      }
    }
    fetchInfo()
  }, [])

  // Filter nav sections based on the connected instance. Home hides when the
  // instance lacks the home feature. The whole Host Controls domain hides on a
  // paired 'home' instance: its services, storage, backups, and terminal
  // belong to a machine the user does not administer from here.
  const filteredSections = navSections
    .filter((section) => section.label !== HOST_CONTROLS || instanceInfo?.role !== 'home')
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (!instanceInfo) return true
        // Hide Home tab if instance doesn't have home feature
        if (item.id === '/home' && !instanceInfo.features.home) return false
        return true
      }),
    }))
    .filter((section) => section.items.length > 0)

  /** Settings is not a dashboard tab — it overtakes the shell. The gear in the
   * top bar is the only entry point, so the rail never shows a Settings item. */
  const isSettingsRoute = location.pathname === '/settings'

  const openSettings = useCallback(() => {
    setMode('browsing')
    navigate('/settings')
  }, [navigate, setMode])

  const handleNavSelect = useCallback((id: string) => {
    navigate(id)
  }, [navigate])

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

        <InstanceSwitch />

        <AcousticAuraIndicator />

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

        {/* Settings entry — top-right corner, always present in both modes.
         * Not a dashboard tab: it overtakes the shell, so the gear is the
         * only way in. About, Legal Notices, and Developer Tools all live
         * inside the Settings page now. */}
        <Button
          variant={isSettingsRoute ? 'default' : 'ghost'}
          size="icon"
          className="h-7 w-7"
          onClick={openSettings}
          title="Settings"
          aria-label="Open settings"
        >
          <SettingsIcon className="h-4 w-4" />
        </Button>
      </header>

      {/* Mode content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {isEngaged ? (
          configEditor ? (
            <div className="h-full overflow-auto p-8">{configEditor}</div>
          ) : (
            <HostShell />
          )
        ) : isSettingsRoute ? (
          /* Settings overtakes the dashboard: no dashboard rail, no padded
           * main wrapper. The Settings page renders its own NavRail (in the
           * same position) plus its content, filling the whole surface. */
          <div className="h-full w-full overflow-hidden">
            {children}
          </div>
        ) : (
          <div className="flex h-full overflow-hidden">
            {/* Navigation rail — shared NavRail component, identical
             * typography to the settings rail by construction. */}
            <NavRail
              sections={filteredSections as NavRailSection[]}
              activeId={location.pathname}
              onSelect={handleNavSelect}
            />

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
    </div>
  )
}
