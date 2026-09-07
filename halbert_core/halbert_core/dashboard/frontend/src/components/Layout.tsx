// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Layout — the application shell.
 *
 * The shell is three panels, and this is where they are composed:
 *
 *   left    the navigation rail — always present
 *   center  the active page: the dashboard, a system page, or Settings
 *   right   the conversation — Halbert, the one continuous conversation
 *
 * The center and right panels are independently togglable (Cmd/Ctrl+D and
 * Cmd/Ctrl+J via the PanelToggle; Cmd/Ctrl+B flips between the two focus
 * states). The visibility model lives in ShellModeContext: 'both' is the
 * side-by-side default, 'engaged' is the conversation alone, 'browsing' is
 * the page alone. Nothing here ever hides both.
 *
 * A global top bar carries the voice entry, the Presence Pill, the panel
 * toggles, the background-work indicators and debug, so nothing that used to
 * live in the sidebar footer disappears when a panel does.
 *
 * One route overtakes the whole shell, not just the content area: /voice
 * (O8) is a full-bleed surface with its own dark canvas and its own header,
 * so neither the rail nor the shell top bar renders over it.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
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
  ShieldAlert,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfigEditor } from './ConfigEditor'
import { HalbertMark, NavRail, type NavRailSection } from '@halbert/design-system'
import { PanelToggle } from './shell/PanelToggle'
import { GuestPresenceIndicator } from './shell/GuestPresenceIndicator'
import type { InstanceInfo } from '@/lib/instanceInfo'
import { EntityNodeBlock } from './shell/EntityNodeBlock'
import { AggregateStatusLight } from './agent/AggregateStatusLight'
import { useTasks } from '@/hooks/useTasks'
import { AcousticAuraIndicator, VoiceHudSummonButton } from '@/components/audio'
import { HostShell } from './shell/HostShell'
import { useShellMode } from '@/contexts/ShellModeContext'
import { askHost, runOnHost, configWithHost } from '@/lib/hostConversation'
import { apiUrl } from '@/lib/apiBase'
import { getPendingApprovals } from '@/lib/tauri'
import { routeAllowed, safeRouteAfterSwitch, type InstanceFeatures } from '@/lib/routeCapabilities'
import { listDevices } from '@/lib/peerApi'

type NavItem = { id: string; label: string; icon: typeof LayoutDashboard }
type NavSection = { label: string; items: NavItem[] }

/**
 * The rail carries two groups (HANDOFF-NODE-LIST-RAIL-DESIGN §5R, revised
 * design §3):
 *
 *   Shared        things shared across all nodes in the entity — home
 *                 automation (same HA data on every machine) and shared
 *                 compute (the linked-machines health grid, only when 2+
 *                 nodes are linked).
 *
 *   Machine Tools everything per-machine — terminal, storage, services,
 *                 containers, GPU, network, backups, apps, sharing,
 *                 development, findings, approvals. No section header:
 *                 these are all "tools for this machine."
 *
 * The entity name and node buttons live in the NavRail header
 * (EntityNodeBlock), not in a section. The node button IS the landing page
 * — clicking it navigates to `/`. There is no separate "Dashboard" or
 * "Overview" nav item.
 *
 * Sections with a single visible item render without a header label — the
 * item stands alone as a top-level nav entry (adaptive headers).
 *
 * Settings is never a rail item: the Settings page renders in the center
 * panel, and the top-bar gear is the entry point.
 */

/** Exported for the nav-coverage test (R08-01/NAV-01): every routed page in
 * App.tsx must have an entry point somewhere in this rail. */
export const navSections: NavSection[] = [
  {
    label: '',
    items: [
      { id: '/home', label: 'Home', icon: HomeIcon },
      { id: '/compute', label: 'Shared Compute', icon: Server },
    ],
  },
  {
    label: '',
    items: [
      { id: '/services', label: 'Services', icon: Server },
      { id: '/storage', label: 'Storage', icon: HardDrive },
      { id: '/backups', label: 'Backups', icon: Archive },
      { id: '/terminal', label: 'Terminal', icon: Terminal },
      { id: '/containers', label: 'Containers', icon: Container },
      { id: '/gpu', label: 'GPU', icon: Cpu },
      { id: '/apps', label: 'Apps', icon: Package },
      { id: '/network', label: 'Network', icon: Wifi },
      { id: '/sharing', label: 'Sharing', icon: Share2 },
      { id: '/development', label: 'Development', icon: Code2 },
      { id: '/findings', label: 'Findings', icon: Shield },
      { id: '/approvals', label: 'Approvals', icon: CheckCircle },
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
  // Derived from the terminal store, not a second list kept in step with it.
  const { running: runningTasks, finished: finishedTasks } = useTasks()

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

  // Linked-node count for the Shared Compute gate (§6.1 item 4): /api/devices
  // with revoked and endpoint-less records excluded — the same list the rail's
  // EntityNodeBlock renders.
  const [linkedNodeCount, setLinkedNodeCount] = useState<number | null>(null)

  // Pending-approvals count for the top-bar badge (R08-01/NAV-01).
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0)

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

  // The Shared Compute item appears only once a second linked node exists
  // (revised design §3.1 principle 5). Null until /api/devices answers —
  // show it, then hide it, matching the capability filter's "a flicker of
  // an item that later hides beats a nav that starts empty" rule.
  useEffect(() => {
    let cancelled = false
    listDevices()
      .then((state) => {
        if (cancelled) return
        setLinkedNodeCount(state.devices.filter((d) => !d.revoked && d.endpoint).length)
      })
      .catch(() => { /* Non-fatal — the item stays until devices respond */ })
    return () => { cancelled = true }
  }, [])

  // Poll pending approvals for the top-bar badge — same 5s cadence as the
  // Approvals page itself so the badge and the page never visibly disagree.
  useEffect(() => {
    let cancelled = false
    const checkPendingApprovals = async () => {
      try {
        const data = await getPendingApprovals()
        if (!cancelled) setPendingApprovalsCount(data.pending?.length ?? data.count ?? 0)
      } catch {
        // Non-fatal — the badge just stays at its last known count.
      }
    }
    checkPendingApprovals()
    const interval = setInterval(checkPendingApprovals, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  // Filter nav items by the active node's capabilities using the shared
  // route→capability table (§5R.3 N5). The old filter collapsed GPU, Containers,
  // and Development all onto features.development and blanket-hid System on
  // home-role nodes. The revised design (§3.1) says a home server shows
  // "whatever limited IT tools exist," so gating is capability-only via the
  // fine-grained features.gpu / features.home / features.development flags.
  const features: InstanceFeatures | null = instanceInfo
    ? { home: instanceInfo.features.home, gpu: instanceInfo.features.gpu, development: instanceInfo.features.development }
    : null

  const showSharedCompute = linkedNodeCount === null || linkedNodeCount > 0

  const filteredSections = navSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) =>
        routeAllowed(item.id, features)
        && (item.id !== '/compute' || showSharedCompute)),
    }))
    .filter((section) => section.items.length > 0)

  // Post-reload route fallback (§5R.3 N5, §6.5): after switching nodes the page
  // reloads pointed at the new machine. If the current route is not supported
  // there (e.g. /gpu on a GPU-less node), land on / instead of a broken page.
  // Runs once after instance info loads — the reload puts us back in mount, so
  // this is the first chance to check.
  useEffect(() => {
    if (!instanceInfo) return
    if (!routeAllowed(location.pathname, features)) {
      navigate(safeRouteAfterSwitch(location.pathname, features))
    }
  }, [instanceInfo]) // eslint-disable-line react-hooks/exhaustive-deps -- features derived from instanceInfo; location/navigate stable

  /** Settings is not a dashboard tab — it overtakes the shell. The gear in the
   * top bar is the only entry point, so the rail never shows a Settings item. */
  const isSettingsRoute = location.pathname === '/settings'

  const isApprovalsRoute = location.pathname === '/approvals'

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
  // panel state; leaving the route (the screen's return edge sets the base
  // state explicitly before navigating) restores it.
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

  const openApprovals = useCallback(() => {
    if (!centerVisible) {
      setMode(rightVisible ? 'both' : 'browsing')
    }
    navigate('/approvals')
  }, [navigate, centerVisible, rightVisible, setMode])

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
  // The bridge below reads panel visibility at event time; a ref keeps the
  // listeners stable instead of re-subscribing on every toggle.
  const visibilityRef = useRef({ centerVisible, rightVisible })
  useEffect(() => {
    visibilityRef.current = { centerVisible, rightVisible }
  }, [centerVisible, rightVisible])

  /**
   * The dashboard-to-conversation bridge.
   *
   * Mounted HERE, above the panel composition, and deliberately not on
   * AgentChat: every one of these buttons renders with the conversation
   * hidden ('browsing'), where AgentChat does not exist. A listener on
   * AgentChat could never hear the event whose job is to bring AgentChat up.
   *
   * Each handler parks the request and makes sure the conversation is on
   * screen; the conversation drains it once it mounts. Only the right panel
   * is revealed — the center keeps whatever state the user chose, so a
   * 'Run in Terminal' issued while the conversation has the whole shell does
   * not pop the dashboard open (shell §9.6: the user hides panels to focus).
   */
  useEffect(() => {
    const revealConversation = () => {
      const { centerVisible: cv, rightVisible: rv } = visibilityRef.current
      if (rv) return
      setMode(cv ? 'both' : 'engaged')
    }

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
      revealConversation()
    }

    // Staged, never executed — see runOnHost.
    const onRunCommand = (event: Event) => {
      const detail = (event as CustomEvent).detail ?? {}
      const command = typeof detail === 'string' ? detail : detail.command
      if (!command) return
      runOnHost(command, detail.title)
      revealConversation()
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
      revealConversation()
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

          {/* Who is speaking when it is not the machine (§5R.3 N1): the
           * guest-persona half of the old pill, kept in the top bar. Node
           * switching is the rail's job now (EntityNodeBlock), so this
           * renders nothing at all until a guest fronts. */}
          <GuestPresenceIndicator />

          {/* TERM-1's last row: with the tasks column in the right panel, a
              long-running command is visible only while that panel is open.
              This is how the machine says something is running when you are
              not looking at it. Renders nothing when nothing is. */}
          <AggregateStatusLight tasks={[...runningTasks, ...finishedTasks]} />

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

          {/* Pending approvals — the top-bar entry point for what needs human
           * sign-off (R08-01/NAV-01). The rail's Approvals item is the full
           * page; this is the always-visible count so a pending decision is
           * never silent. Hidden at zero — an empty badge is noise. */}
          <Button
            variant={isApprovalsRoute ? 'default' : 'ghost'}
            size="icon"
            className="h-7 w-7 relative"
            onClick={openApprovals}
            title={pendingApprovalsCount > 0 ? `${pendingApprovalsCount} pending approval${pendingApprovalsCount === 1 ? '' : 's'}` : 'Approvals'}
            aria-label="Open approvals"
          >
            <ShieldAlert className="h-4 w-4" />
            {pendingApprovalsCount > 0 && (
              <Badge
                variant="destructive"
                className="absolute -top-1 -right-1 h-4 min-w-4 px-1 py-0 text-[10px] leading-4 justify-center"
              >
                {pendingApprovalsCount > 9 ? '9+' : pendingApprovalsCount}
              </Badge>
            )}
          </Button>

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
              header={<EntityNodeBlock />}
            />

            {/* Center panel — the active page / Settings. Hidden when the
             * user focuses on the conversation (Host Focus state). Settings
             * needs the full center panel width (it has its own sub-rail),
             * so it skips the padded max-width wrapper. */}
            {centerVisible && (
              <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {isSettingsRoute ? (
                  <div className="flex-1 overflow-hidden">
                    {configEditor ?? children}
                  </div>
                ) : (
                  <main className="flex-1 p-6 md:p-8 overflow-auto relative z-0">
                    <div className="max-w-6xl mx-auto w-full">
                      {configEditor ?? children}
                    </div>
                  </main>
                )}
              </div>
            )}

            {/* Right panel — the conversation (HostShell). Hidden when the
             * user focuses on the dashboard (Dashboard Focus state). When
             * center is hidden, this takes the full remaining width and
             * HostShell shows its context stage. When center is visible
             * (side-by-side), HostShell is compact (conversation only). */}
            {rightVisible && (
              <div className={cn(
                'flex flex-col min-w-0 overflow-hidden',
                centerVisible ? 'w-[40%] max-w-[640px] min-w-[320px] border-l border-border' : 'flex-1',
              )}>
                <HostShell compact={centerVisible} />
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
