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
 * A global top bar carries the voice entry, the mode switch (Cmd/Ctrl+B), the
 * background-work indicators and debug, so nothing that used to live in the
 * sidebar footer disappears when the sidebar does.
 *
 * One route overtakes the whole shell, not just the content area: /voice
 * (O8) is a full-bleed surface with its own dark canvas and its own header,
 * so neither the rail nor the shell top bar renders over it.
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
  AudioLines,
  Package,
  Wifi,
  Share2,
  Cpu,
  Container,
  Code2,
  CheckCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfigEditor } from './ConfigEditor'
import { HalbertMark, NavRail, type NavRailSection } from '@halbert/design-system'
import { PanelToggle } from './shell/PanelToggle'
import { PresencePill, type InstanceInfo } from './shell/PresencePill'
import { AcousticAuraIndicator, VoiceHudSummonButton } from '@/components/audio'
import { HostShell } from './shell/HostShell'
import { useShellMode } from '@/contexts/ShellModeContext'
import { askHost, runOnHost, configWithHost } from '@/lib/hostConversation'
import { apiUrl } from '@/lib/apiBase'

type NavItem = { id: string; label: string; icon: typeof LayoutDashboard }
type NavSection = { label: string; items: NavItem[] }

/**
 * The rail carries four domains (shell redesign, Section 9.3):
 *
 *   Overview              the dashboard and the spatial home view
 *   Findings & Approvals  what the agent surfaced — findings and proposals
 *                         that need human attention
 *   System                the sysadmin surface — services, storage, backups,
 *                         terminal
 *   Workloads             things running on the machine that aren't core
 *                         system services — containers, GPU, apps, network,
 *                         sharing, development
 *
 * Sections with a single visible item render without a header label — the
 * item stands alone as a top-level nav entry (adaptive headers, 9.4).
 *
 * Settings is never a rail item: the Settings page renders in the center
 * panel, and the top-bar gear is the entry point.
 */
const SYSTEM = 'System'

const navSections: NavSection[] = [
  {
    label: 'Overview',
    items: [
      { id: '/', label: 'Dashboard', icon: LayoutDashboard },
      { id: '/home', label: 'Home', icon: HomeIcon },
    ],
  },
  {
    label: 'Findings & Approvals',
    items: [
      { id: '/findings', label: 'Findings', icon: Shield },
      { id: '/approvals', label: 'Approvals', icon: CheckCircle },
    ],
  },
  {
    label: SYSTEM,
    items: [
      { id: '/services', label: 'Services', icon: Server },
      { id: '/storage', label: 'Storage', icon: HardDrive },
      { id: '/backups', label: 'Backups', icon: Archive },
      { id: '/terminal', label: 'Terminal', icon: Terminal },
    ],
  },
  {
    label: 'Workloads',
    items: [
      { id: '/containers', label: 'Containers', icon: Container },
      { id: '/gpu', label: 'GPU', icon: Cpu },
      { id: '/apps', label: 'Apps', icon: Package },
      { id: '/network', label: 'Network', icon: Wifi },
      { id: '/sharing', label: 'Sharing', icon: Share2 },
      { id: '/development', label: 'Development', icon: Code2 },
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
  const { isVoice, setMode, enterVoice, exitVoice, centerVisible, rightVisible } = useShellMode()

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
  // instance lacks the home feature. The whole System domain hides on a paired
  // 'home' instance: its services, storage, backups, and terminal belong to a
  // machine the user does not administer from here. Workloads' dev-oriented
  // pages (Containers, GPU, Development) hide when the instance lacks the
  // development feature.
  const filteredSections = navSections
    .filter((section) => section.label !== SYSTEM || instanceInfo?.role !== 'home')
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (!instanceInfo) return true
        if (item.id === '/home' && !instanceInfo.features.home) return false
        if ((item.id === '/gpu' || item.id === '/development' || item.id === '/containers')
            && !instanceInfo.features.development) return false
        return true
      }),
    }))
    .filter((section) => section.items.length > 0)

  /** Settings is not a dashboard tab — it overtakes the shell. The gear in the
   * top bar is the only entry point, so the rail never shows a Settings item. */
  const isSettingsRoute = location.pathname === '/settings'

  /** Voice (O8) is a mode reached through a route: the /voice deep link and
   * the top-bar button beside the mode switch are the only ways in. The route
   * drives the mode, so the shell follows the URL in both directions. */
  const isVoiceRoute = location.pathname === '/voice'

  /** The floating voice HUD (P4) loads the SPA at /voice-hud inside its own
   * 480x72 transparent overlay window — full-bleed for the same reasons as
   * /voice, but it is NOT a shell mode: it never parks or restores the base
   * surface and the route lives only in the overlay's webview. */
  const isVoiceHudRoute = location.pathname === '/voice-hud'

  // Route <-> mode synchronization. Entering /voice parks the current
  // surface; leaving the route (the screen's Host Canvas edge sets the base
  // surface explicitly before navigating) restores it.
  useEffect(() => {
    if (isVoiceRoute && !isVoice) {
      enterVoice()
    } else if (!isVoiceRoute && isVoice) {
      exitVoice()
    }
  }, [isVoiceRoute, isVoice, enterVoice, exitVoice])

  const openSettings = useCallback(() => {
    // Settings renders in the center panel. Keep the conversation visible
    // (right panel) so the user can ask Halbert for help while configuring.
    setMode('both')
    navigate('/settings')
  }, [navigate, setMode])

  const openVoice = useCallback(() => {
    navigate('/voice')
  }, [navigate])

  const handleNavSelect = useCallback((id: string) => {
    // Clicking a nav item when center is hidden auto-shows the center
    // panel (Section 9.6). Navigation implies a target, and the target
    // is the center panel.
    if (!centerVisible) {
      setMode(rightVisible ? 'both' : 'browsing')
    }
    navigate(id)
  }, [navigate, centerVisible, rightVisible, setMode])

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
    const toEngaged = () => setMode('both')

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
    <div className="h-screen bg-background flex flex-col overflow-hidden" data-testid="app-shell">
      {/* Global top bar — present in both modes, and on every route except
       * /voice (O8): that screen owns the window, dark canvas and its own
       * header included. */}
      {!isVoiceRoute && (
        <header className="flex items-center gap-3 px-4 h-12 border-b border-border bg-background shrink-0">
          <div className="flex items-center gap-2 shrink-0">
            <HalbertMark size={20} density="medium" tone="accent" />
            <span className="text-sm font-semibold hidden sm:inline text-foreground">Halbert</span>
          </div>

          <PanelToggle />

          {/* Voice entry — a mode, not a nav tab: the deep link and this
           * button beside the mode switch are the only doors in. The route
           * effect parks whichever surface is on screen. */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={openVoice}
            title="Voice Mode"
            aria-label="Enter voice mode"
          >
            <AudioLines className="h-4 w-4" />
          </Button>

          {/* Floating voice HUD (P4) — summons the borderless desktop
           * companion pill over whatever the user is working in. Renders
           * nothing outside the Tauri shell (plain browsers have no
           * window to summon). */}
          <VoiceHudSummonButton />

          <PresencePill />

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
      )}

      {/* Mode content — the 3-panel shell.
       *
       * Voice routes (/voice, /voice-hud) are full-bleed and render bare.
       * Everything else is: left NavRail + center page panel + right
       * conversation panel, with center and right independently togglable
       * via the PanelToggle in the top bar (Cmd+D, Cmd+J).
       *
       * When center is hidden, the right panel (HostShell) takes the full
       * width — the "Host Focus" state. When right is hidden, the center
       * page takes the full width — "Dashboard Focus". When both are
       * visible — "Side-by-Side Co-pilot" (the default).
       *
       * Clicking a nav item when center is hidden auto-shows the center
       * panel (handleNavSelect below). */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {isVoiceHudRoute ? (
          /* The floating voice HUD (P4) is a 480x72 borderless transparent
           * Tauri overlay — any shell chrome (top bar, rail, padding) would
           * paint an opaque bar behind the pill and eat the whole window.
           * Like the /voice exception, the page renders bare. */
          children
        ) : isVoiceRoute ? (
          /* Voice is full-bleed — no rail, no padded main, no shell
           * chrome of any kind. The screen brings its own h-screen dark
           * canvas, so it renders bare: it IS the shell while it is up. */
          children
        ) : (
          <div className="flex h-full overflow-hidden">
            {/* Navigation rail — always present (not togglable in this phase).
             * Shared NavRail component, identical typography to the settings
             * rail by construction. */}
            <NavRail
              sections={filteredSections as NavRailSection[]}
              activeId={location.pathname}
              onSelect={handleNavSelect}
            />

            {/* Center panel — the active page / Settings. Hidden when the
             * user focuses on the conversation (Host Focus state). */}
            {centerVisible && (
              <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <main className="flex-1 p-6 md:p-8 overflow-auto relative z-0">
                  <div className="max-w-6xl mx-auto w-full">
                    {configEditor ?? children}
                  </div>
                </main>
              </div>
            )}

            {/* Right panel — the conversation (HostShell). Hidden when the
             * user focuses on the dashboard (Dashboard Focus state). When
             * center is hidden, this takes the full remaining width. */}
            {rightVisible && (
              <div className={cn(
                'flex flex-col min-w-0 overflow-hidden',
                centerVisible ? 'w-[40%] max-w-[640px] min-w-[320px] border-l border-border' : 'flex-1',
              )}>
                <HostShell />
              </div>
            )}

            {/* Edge case: both panels hidden. Show the rail with an empty
             * state so the user can click a nav item to re-open the center. */}
            {!centerVisible && !rightVisible && (
              <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
                Press Cmd+D for dashboard or Cmd+J for conversation
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
