// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useScan } from '@/contexts/ScanContext'
import { Tabs, TabsContent } from '@/components/ui/tabs'
import { Toast } from '@/components/ui/confirm-dialog'
import { api } from '@/lib/api'
import type { SystemInfo } from '@/lib/tauri'
import { getSystemInfo } from '@/lib/tauri'
import { NavRail, type NavRailSection } from '@halbert/design-system'
import {
  Bell,
  Cpu,
  Brain,
  BookOpen,
  Shield,
  Lock,
  Sparkles,
  MonitorSmartphone,
  Eye,
  Info,
  AudioLines,
  ArrowLeft,
  Bug,
} from 'lucide-react'
import type { DiscoveryStats, SystemProfile } from '@/components/settings/tabs/SystemTab'
import type {
  AddSourceResult,
  CoreSource,
  CustomDoc,
  DocFreshness,
  DocSuggestion,
  IndexProgress,
  NewKnowledge,
  RagIndex,
  RagStats,
  SelfKnowledgeEntry,
  TrendingSuggestion,
  UserStack,
} from '@/components/settings/tabs/KnowledgeTab'
import type { AIRule, NewRule, ToolPolicy } from '@/components/settings/tabs/SafetyTab'
import type { AlertRule } from '@/components/settings/tabs/AlertsTab'
import { useInstanceVariant } from '@/hooks/useInstanceVariant'
import { ComponentLibraryViewer } from '@/components/ComponentLibraryViewer'
import { VoiceEnrollmentModal } from '@/components/audio'
import { LegalNoticesModal } from '@/components/legal/LegalNoticesModal'
import { apiUrl } from '@/lib/apiBase'

/**
 * U3-02/U3-04: the 12 settings tab bodies were all statically imported, so
 * every one of them landed in Settings.tsx's own bundle chunk regardless of
 * which single tab a visit ever renders (TabsContent only ever mounts the
 * active one — Radix's Presence never rendered the other 11's React tree,
 * but the JS to *define* all 12 still shipped and parsed up front). Each
 * import() below is its own chunk, fetched the first time its tab is
 * actually opened; the Suspense boundary around <Tabs> below covers all of
 * them with one shared "Loading…" fallback (only one TabsContent is ever
 * mounted at a time, so at most one of these is ever in flight).
 */
const ModelSettings = lazy(() => import('@/components/llm').then((m) => ({ default: m.ModelSettings })))
const ComputePeerCard = lazy(() => import('@/components/llm').then((m) => ({ default: m.ComputePeerCard })))
const SystemTab = lazy(() => import('@/components/settings/tabs/SystemTab').then((m) => ({ default: m.SystemTab })))
const KnowledgeTab = lazy(() => import('@/components/settings/tabs/KnowledgeTab').then((m) => ({ default: m.KnowledgeTab })))
const SafetyTab = lazy(() => import('@/components/settings/tabs/SafetyTab').then((m) => ({ default: m.SafetyTab })))
const AlertsTab = lazy(() => import('@/components/settings/tabs/AlertsTab').then((m) => ({ default: m.AlertsTab })))
const BeingTab = lazy(() => import('@/components/settings/tabs/BeingTab').then((m) => ({ default: m.BeingTab })))
const DevicesTab = lazy(() => import('@/components/settings/tabs/DevicesTab').then((m) => ({ default: m.DevicesTab })))
const SecurityTab = lazy(() => import('@/components/settings/tabs/SecurityTab').then((m) => ({ default: m.SecurityTab })))
const VisionTab = lazy(() => import('@/components/settings/tabs/VisionTab').then((m) => ({ default: m.VisionTab })))
const AudioSettings = lazy(() => import('@/components/audio').then((m) => ({ default: m.AudioSettings })))
const SpeakerProfilesCard = lazy(() => import('@/components/audio').then((m) => ({ default: m.SpeakerProfilesCard })))
const AboutTab = lazy(() => import('@/components/settings/tabs/AboutTab').then((m) => ({ default: m.AboutTab })))
const DebugTab = lazy(() => import('@/components/settings/tabs/DebugTab').then((m) => ({ default: m.DebugTab })))

const API_BASE = apiUrl('/api')

/**
 * The tabs this page has, in the order they are shown. Also the whitelist for
 * `?tab=`: Radix renders no panel for a value with no trigger, so an
 * unrecognised one would leave the page showing its tab strip and nothing
 * else. An unknown tab is not an error worth a message — it is a stale or
 * mistyped link — so it opens the first tab, which is what a bare /settings
 * does too.
 */
const SETTINGS_TABS = ['system', 'ai', 'knowledge', 'safety', 'alerts', 'being', 'devices', 'security', 'vision', 'audio', 'about', 'debug'] as const
const DEFAULT_SETTINGS_TAB = SETTINGS_TABS[0]

type SettingsNavItem = { id: string; label: string; icon: typeof Cpu }
type SettingsSection = { id: string; label: string; items: SettingsNavItem[] }

const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: 'being',
    label: 'Personality & Identity',
    items: [
      { id: 'being', label: 'Identity & Voice', icon: Sparkles },
      { id: 'devices', label: 'Devices', icon: MonitorSmartphone },
    ],
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    items: [
      { id: 'ai', label: 'Models & Providers', icon: Brain },
      { id: 'knowledge', label: 'Knowledge', icon: BookOpen },
    ],
  },
  {
    id: 'system-security',
    label: 'System & Security',
    items: [
      { id: 'safety', label: 'Tool Permissions', icon: Shield },
      { id: 'alerts', label: 'Alert Rules', icon: Bell },
      { id: 'security', label: 'Trust Boundary', icon: Lock },
      { id: 'vision', label: 'Vision', icon: Eye },
      { id: 'audio', label: 'Audio & Voice', icon: AudioLines },
    ],
  },
  {
    id: 'general',
    label: 'General',
    items: [
      { id: 'system', label: 'System Info', icon: Cpu },
      { id: 'about', label: 'About', icon: Info },
    ],
  },
  {
    id: 'developer',
    label: 'Developer',
    items: [{ id: 'debug', label: 'Debug', icon: Bug }],
  },
]

/** The tab a URL asks for, or the default when it asks for nothing usable. */
export function settingsTabFromParam(raw: string | null): string {
  return (SETTINGS_TABS as readonly string[]).includes(raw ?? '')
    ? (raw as string)
    : DEFAULT_SETTINGS_TAB
}

export function Settings() {
  /**
   * The URL owns which tab is open, in both directions. Reading it is what
   * makes the model picker's "All models and endpoints…" link (which points at
   * `/settings?tab=ai`) land on the tab it names instead of on System; writing
   * it back is what makes the tab someone is looking at something they can
   * link, bookmark or reload onto.
   *
   * `replace` rather than a push: a back button that walks the user through
   * every tab they glanced at, instead of back to where they came from, is a
   * worse back button.
   */
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const activeTab = settingsTabFromParam(searchParams.get('tab'))
  const selectTab = useCallback((next: string) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      params.set('tab', next)
      return params
    }, { replace: true })
  }, [setSearchParams])

  // The AI tab is the one surface that changes shape by variant: a
  // home node has no model picker — it is a pure client of the
  // workstation's compute endpoint — so it gets the ComputePeerCard instead.
  // An unknown variant keeps the full picker: a failed info route must not
  // shrink the surface on the machine that needs it.
  const variant = useInstanceVariant()
  const isHomeVariant = variant === 'home'

  const [showComponentLibrary, setShowComponentLibrary] = useState(false)
  const [showLegalNotices, setShowLegalNotices] = useState(false)
  const [showEnrollmentModal, setShowEnrollmentModal] = useState(false)

  // Scan context for coordinated system-wide scanning
  const { triggerDeepScan, isDeepScanning } = useScan()
  
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [alertRules, setAlertRules] = useState<AlertRule[]>([])
  const [discoveryStats, setDiscoveryStats] = useState<DiscoveryStats | null>(null)
  
  // Policy state
  const [policy, setPolicy] = useState<ToolPolicy>({
    default_allow: true,
    tools: {}
  })
  const [policyPath, setPolicyPath] = useState<string>('')
  const [savingPolicy, setSavingPolicy] = useState(false)

  // Editing endpoint state
  const [showAddKnowledgeSource, setShowAddKnowledgeSource] = useState(false)
  
  // RAG knowledge source state
  const [newSourceUrl, setNewSourceUrl] = useState('')
  const [newSourceName, setNewSourceName] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [addSourceResult, setAddSourceResult] = useState<AddSourceResult | null>(null)
  const [ragStats, setRagStats] = useState<RagStats | null>(null)
  const [ragIndexes, setRagIndexes] = useState<RagIndex[]>([])
  const [customDocs, setCustomDocs] = useState<CustomDoc[]>([])
  const [coreSources, setCoreSources] = useState<CoreSource[]>([])
  const [showDocList, setShowDocList] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [_indexResult, setIndexResult] = useState<{total: number, sources: string[]} | null>(null)
  const [indexProgress, setIndexProgress] = useState<IndexProgress>({ percent: 0, currentSource: null, completed: 0, total: 0 })
  // R08-05: pollIndexingStatus used to return its interval id as a cleanup
  // closure that nothing ever called — a stray interval every time Re-index
  // ran while a previous poll was still ticking (it never cleared the old
  // one before starting a new one), and one left running forever if
  // Settings unmounted mid-index. Tracking the id in a ref fixes both:
  // clear any existing interval before starting a new one, and clear it
  // on unmount.
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [docFreshness, setDocFreshness] = useState<DocFreshness | null>(null)

  // Documentation Suggestions state (self-learning)
  const [docSuggestions, setDocSuggestions] = useState<DocSuggestion[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [addingSuggestion, setAddingSuggestion] = useState<string | null>(null)

  // Trending Topics state (Phase 34 - Cutting-Edge Discovery)
  const [trendingSuggestions, setTrendingSuggestions] = useState<TrendingSuggestion[]>([])
  const [loadingTrending, setLoadingTrending] = useState(false)
  const [userStack, setUserStack] = useState<UserStack | null>(null)
  const [showTrending, setShowTrending] = useState(true)
  const [trendingEnabled, setTrendingEnabled] = useState(true)

  // Self-Knowledge state
  const [selfKnowledge, setSelfKnowledge] = useState<SelfKnowledgeEntry[]>([])
  const [loadingSelfKnowledge, setLoadingSelfKnowledge] = useState(false)
  // editingKnowledge removed - was unused (future: inline editing)
  const [newKnowledge, setNewKnowledge] = useState<NewKnowledge>({ subject: '', content: '', rationale: '' })
  const [addingKnowledge, setAddingKnowledge] = useState(false)
  const [showAddKnowledge, setShowAddKnowledge] = useState(false)
  
  // Toast notification state
  const [toast, setToast] = useState<{ open: boolean, message: string, variant: 'success' | 'error' | 'info' }>({ 
    open: false, message: '', variant: 'info' 
  })
  
  // Component Library viewer state

  // Legal notices modal state (LEG-MOD-01)
  
  // System Profile state
  const [systemProfile, setSystemProfile] = useState<SystemProfile | null>(null)
  // Note: deepScanning state moved to ScanContext (isDeepScanning)
  
  // AI Rules state
  const [aiRules, setAiRules] = useState<AIRule[]>([])
  const [aiRulesExamples, setAiRulesExamples] = useState<string[]>([])
  const [newRule, setNewRule] = useState<NewRule>({ rule: '', category: 'general', priority: 'high' })
  const [addingRule, setAddingRule] = useState(false)

  // U3-02: this used to fire all seven of these on mount regardless of
  // which tab (if any) the user was about to look at — opening Settings
  // on the About tab still fetched System's discovery stats, Alerts'
  // rules, Safety's policy and AI rules, and all five pieces of
  // Knowledge's state. Tracked which tabs have already loaded their own
  // data and load a tab's data once, the first time it becomes active
  // (including the initial tab on mount) — switching back to an
  // already-visited tab doesn't refetch.
  const loadedTabsRef = useRef<Set<string>>(new Set())

  const loadTabData = (tab: string) => {
    switch (tab) {
      case 'system':
        loadSystemInfoAndDiscoveries()
        loadSystemProfile()
        break
      case 'alerts':
        loadAlertRules()
        break
      case 'safety':
        loadPolicy()
        loadAiRules()
        break
      case 'knowledge':
        loadRagStatsAndIndexes()
        loadSelfKnowledge()
        checkIndexingStatus()
        loadDocSuggestions()
        loadTrendingSuggestions()
        break
      default:
        // ai/being/devices/security/vision/audio/about/debug each load
        // their own data internally — nothing owned by Settings itself.
        break
    }
  }

  useEffect(() => {
    if (!loadedTabsRef.current.has(activeTab)) {
      loadedTabsRef.current.add(activeTab)
      loadTabData(activeTab)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  useEffect(() => {
    // R08-05: stop the indexing poll if Settings unmounts mid-index —
    // pollIndexingStatus previously had no consumer for the cleanup it
    // computed, so this interval outlived the page.
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  // Load trending suggestions from GitHub
  const loadTrendingSuggestions = async () => {
    if (!trendingEnabled) return
    setLoadingTrending(true)
    try {
      const res = await fetch(`${API_BASE}/rag/trending?limit=10`)
      const data = await res.json()
      setTrendingSuggestions(data.suggestions || [])
      setUserStack(data.user_stack || null)
    } catch (err) {
      console.error('Failed to load trending suggestions:', err)
    } finally {
      setLoadingTrending(false)
    }
  }
  
  // Load documentation suggestions based on system discoveries
  const loadDocSuggestions = async () => {
    setLoadingSuggestions(true)
    try {
      const res = await fetch(`${API_BASE}/rag/suggestions`)
      const data = await res.json()
      setDocSuggestions(data.suggestions || [])
    } catch (err) {
      console.error('Failed to load doc suggestions:', err)
    }
    setLoadingSuggestions(false)
  }
  
  const handleAddSuggestion = async (docKey: string) => {
    setAddingSuggestion(docKey)
    try {
      const res = await fetch(`${API_BASE}/rag/suggestions/${docKey}/add`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setToast({ open: true, message: `Added ${data.title || docKey} to knowledge base`, variant: 'success' })
        // Remove from suggestions list
        setDocSuggestions(prev => prev.filter(s => s.doc_key !== docKey))
        loadRagStatsAndIndexes() // Refresh stats
      } else {
        setToast({ open: true, message: data.error || 'Failed to add documentation', variant: 'error' })
      }
    } catch (err) {
      console.error('Failed to add suggestion:', err)
      setToast({ open: true, message: 'Failed to add documentation', variant: 'error' })
    }
    setAddingSuggestion(null)
  }
  
  const handleDismissSuggestion = async (docKey: string) => {
    try {
      await fetch(`${API_BASE}/rag/suggestions/${docKey}/dismiss`, { method: 'POST' })
      setDocSuggestions(prev => prev.filter(s => s.doc_key !== docKey))
    } catch (err) {
      console.error('Failed to dismiss suggestion:', err)
    }
  }
  
  // Check if indexing is already running on page load and load freshness info
  const checkIndexingStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/docs/stats`)
      const data = await res.json()
      
      // Set freshness info
      if (data.freshness) {
        setDocFreshness(data.freshness)
      }
      
      // Check if indexing is running
      if (data.indexing?.is_running) {
        setIndexing(true)
        pollIndexingStatus()
      }
    } catch (err) {
      console.error('Failed to check indexing status:', err)
    }
  }

  // U3-02: these four used to be one loadSettings() firing all six fetches
  // together on every mount regardless of tab, and firing all six again on
  // every Knowledge-tab mutation (add source, reindex, add suggestion) that
  // only actually needed the RAG ones refreshed. Split by which tab owns
  // the data so loadTabData can load only what the active tab needs.

  /** System tab: host info + discovery cache stats. */
  const loadSystemInfoAndDiscoveries = async () => {
    try {
      const info = await getSystemInfo()
      setSystemInfo(info)
    } catch (err) {
      console.error('getSystemInfo failed', err)
    }

    try {
      const stats = await api.getDiscoveryStats()
      setDiscoveryStats(stats)
    } catch (err) {
      console.error('Failed to load discovery stats:', err)
    }
  }

  /** Alerts tab. */
  const loadAlertRules = async () => {
    try {
      const res = await fetch(`${API_BASE}/alerts/rules`)
      const data = await res.json()
      setAlertRules(data.rules || [])
    } catch (err) {
      console.error('Failed to load alert rules:', err)
    }
  }

  /** Safety tab: tool policy (AI rules load separately, see loadAiRules). */
  const loadPolicy = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/policy`)
      const data = await res.json()
      if (data.status === 'ok') {
        setPolicy(data.policy || { default_allow: true, tools: {} })
        setPolicyPath(data.path || '')
      }
    } catch (err) {
      console.error('Failed to load policy:', err)
    }
  }

  /** Knowledge tab: RAG corpus stats + configured indexes. */
  const loadRagStatsAndIndexes = async () => {
    try {
      const res = await fetch(`${API_BASE}/rag/stats`)
      const data = await res.json()
      setRagStats(data)
    } catch (err) {
      console.error('Failed to load RAG stats:', err)
    }

    try {
      const res = await fetch(`${API_BASE}/rag/indexes`)
      const data = await res.json()
      setRagIndexes(data.indexes || [])
    } catch (err) {
      console.error('Failed to load RAG indexes:', err)
    }
  }


  // System Profile functions
  const loadSystemProfile = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/system-profile`)
      const data = await res.json()
      if (data.status === 'loaded') {
        setSystemProfile({
          summary: data.summary,
          scan_time: data.profile?.scan_time || null,
          quick_scan_time: data.profile?.quick_scan_time || null,
        })
      }
    } catch (err) {
      console.error('Failed to load system profile:', err)
    }
  }
  
  const handleDeepScan = async () => {
    console.log('[Settings] handleDeepScan called')
    try {
      // Use context's deep scan - this also triggers refresh for all pages
      console.log('[Settings] Calling triggerDeepScan from context...')
      await triggerDeepScan()
      console.log('[Settings] triggerDeepScan completed, loading system profile...')
      // Reload the system profile to update the local display
      await loadSystemProfile()
      setToast({ open: true, message: 'Deep scan complete! All sections updated.', variant: 'success' })
    } catch (err) {
      console.error('Deep scan failed:', err)
      setToast({ open: true, message: 'Deep scan failed', variant: 'error' })
    }
  }
  
  // AI Rules functions
  const loadAiRules = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/ai-rules`)
      const data = await res.json()
      setAiRules(data.rules || [])
      setAiRulesExamples(data.examples || [])
    } catch (err) {
      console.error('Failed to load AI rules:', err)
    }
  }
  
  const handleAddRule = async () => {
    if (!newRule.rule.trim()) return
    setAddingRule(true)
    try {
      const res = await fetch(`${API_BASE}/settings/ai-rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRule)
      })
      const data = await res.json()
      if (data.success) {
        setAiRules(prev => [...prev, data.rule])
        setNewRule({ rule: '', category: 'general', priority: 'high' })
        setToast({ open: true, message: 'Rule added!', variant: 'success' })
      }
    } catch (err) {
      console.error('Failed to add rule:', err)
      setToast({ open: true, message: 'Failed to add rule', variant: 'error' })
    }
    setAddingRule(false)
  }
  
  const handleDeleteRule = async (ruleId: string) => {
    try {
      const res = await fetch(`${API_BASE}/settings/ai-rules/${ruleId}`, {
        method: 'DELETE'
      })
      if (res.ok) {
        setAiRules(prev => prev.filter(r => r.id !== ruleId))
        setToast({ open: true, message: 'Rule deleted', variant: 'info' })
      }
    } catch (err) {
      console.error('Failed to delete rule:', err)
    }
  }
  
  const handleToggleRule = async (rule: AIRule) => {
    try {
      const res = await fetch(`${API_BASE}/settings/ai-rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...rule, enabled: !rule.enabled })
      })
      if (res.ok) {
        setAiRules(prev => prev.map(r => 
          r.id === rule.id ? { ...r, enabled: !r.enabled } : r
        ))
      }
    } catch (err) {
      console.error('Failed to toggle rule:', err)
    }
  }
  
  const handleAddKnowledgeSource = async () => {
    if (!newSourceUrl) return
    
    setAddingSource(true)
    setAddSourceResult(null)
    
    try {
      const res = await fetch(`${API_BASE}/rag/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          url: newSourceUrl, 
          name: newSourceName || undefined,
          trust: false 
        })
      })
      const data = await res.json()
      
      if (data.success) {
        setAddSourceResult({ 
          success: true, 
          message: 'Added successfully!',
          title: data.title 
        })
        setNewSourceUrl('')
        setNewSourceName('')
        // Reload RAG stats and docs
        loadRagStatsAndIndexes()
        if (showDocList) loadRagDocuments()
      } else if (data.already_exists) {
        setAddSourceResult({ 
          success: false, 
          message: `Already exists: ${data.title}`,
          alreadyExists: true
        })
      } else {
        setAddSourceResult({ 
          success: false, 
          message: data.error || 'Failed to add source' 
        })
      }
    } catch (err) {
      setAddSourceResult({ success: false, message: 'Request failed' })
    }
    
    setAddingSource(false)
  }
  
  const loadRagDocuments = async () => {
    setLoadingDocs(true)
    try {
      const res = await fetch(`${API_BASE}/rag/documents`)
      const data = await res.json()
      setCustomDocs(data.custom_docs || [])
      setCoreSources(data.core_sources || [])
    } catch (err) {
      console.error('Failed to load RAG documents:', err)
    }
    setLoadingDocs(false)
  }
  
  const toggleDocList = () => {
    if (!showDocList && customDocs.length === 0 && coreSources.length === 0) {
      loadRagDocuments()
    }
    setShowDocList(!showDocList)
  }
  
  const handleReindex = async () => {
    setIndexing(true)
    setIndexResult(null)
    try {
      const res = await fetch(`${API_BASE}/settings/docs/index?max_docs=10000`, { method: 'POST' })
      const data = await res.json()
      
      if (data.status === 'started') {
        // Background indexing started - user can navigate away
        setToast({ 
          open: true, 
          message: 'Indexing started in background. You can navigate away safely.', 
          variant: 'success' 
        })
        // Poll for completion
        pollIndexingStatus()
      } else if (data.status === 'already_running') {
        setToast({ open: true, message: 'Indexing already in progress', variant: 'success' })
      } else {
        // Legacy sync response
        setIndexResult({ total: data.total_indexed || 0, sources: data.sources_indexed || [] })
        loadRagStatsAndIndexes()
        if (showDocList) loadRagDocuments()
        setToast({ open: true, message: `Indexed ${data.total_indexed || 0} documents`, variant: 'success' })
        setIndexing(false)
      }
    } catch (err) {
      console.error('Indexing failed:', err)
      setToast({ open: true, message: 'Indexing failed', variant: 'error' })
      setIndexing(false)
    }
  }
  
  const pollIndexingStatus = () => {
    // Clear any interval already running (Re-index clicked again, or the
    // mount-time check and a fresh Re-index both wanting to poll) instead
    // of letting a second one stack on top of it.
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/settings/docs/stats`)
        const data = await res.json()
        const status = data.indexing

        if (status) {
          // Update progress bar
          setIndexProgress({
            percent: status.progress_percent || 0,
            currentSource: status.current_source,
            completed: status.sources_completed?.length || 0,
            total: status.sources_total || 0
          })

          if (!status.is_running) {
            // Indexing completed
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
            setIndexing(false)
            setIndexProgress({ percent: 100, currentSource: null, completed: 0, total: 0 })

            if (status.error) {
              setToast({ open: true, message: `Indexing failed: ${status.error}`, variant: 'error' })
            } else {
              setIndexResult({ total: status.total_indexed || 0, sources: status.sources_completed || [] })
              setToast({ open: true, message: `Indexed ${status.total_indexed || 0} documents`, variant: 'success' })
              loadRagStatsAndIndexes()
              if (showDocList) loadRagDocuments()
            }
          }
        }
      } catch (err) {
        console.error('Failed to poll indexing status:', err)
      }
    }, 2000) // Poll every 2 seconds for smoother progress
  }
  
  // Self-Knowledge management functions
  const loadSelfKnowledge = async () => {
    setLoadingSelfKnowledge(true)
    try {
      const res = await fetch(`${API_BASE}/settings/knowledge/all`)
      const data = await res.json()
      setSelfKnowledge(data.entries || [])
    } catch (err) {
      console.error('Failed to load self-knowledge:', err)
    }
    setLoadingSelfKnowledge(false)
  }
  
  const handleAddSelfKnowledge = async () => {
    if (!newKnowledge.subject || !newKnowledge.content) return
    
    setAddingKnowledge(true)
    try {
      const res = await fetch(`${API_BASE}/settings/knowledge/teach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject: newKnowledge.subject,
          content: newKnowledge.content,
          rationale: newKnowledge.rationale || undefined
        })
      })
      const data = await res.json()
      if (data.success) {
        setNewKnowledge({ subject: '', content: '', rationale: '' })
        setShowAddKnowledge(false)
        loadSelfKnowledge()
        setToast({ open: true, message: 'Knowledge saved!', variant: 'success' })
      }
    } catch (err) {
      console.error('Failed to add knowledge:', err)
      setToast({ open: true, message: 'Failed to save knowledge', variant: 'error' })
    }
    setAddingKnowledge(false)
  }
  
  const handleDeleteKnowledge = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/settings/knowledge/${encodeURIComponent(id)}`, {
        method: 'DELETE'
      })
      if (res.ok) {
        loadSelfKnowledge()
        setToast({ open: true, message: 'Knowledge deleted', variant: 'info' })
      }
    } catch (err) {
      console.error('Failed to delete knowledge:', err)
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Settings sub-rail — the same NavRail component the dashboard uses,
       * rendered inside the center panel as a secondary navigation for the
       * 12 settings tabs. The dashboard's primary NavRail is already on the
       * left (provided by Layout.tsx); this sits to its right. */}
      <NavRail
        tabMode
        sections={SETTINGS_SECTIONS as NavRailSection[]}
        activeId={activeTab}
        onSelect={selectTab}
        searchable
        searchPlaceholder="Filter settings…"
        header={
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-md text-xs font-medium text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-all"
            aria-label="Back to dashboard"
          >
            <ArrowLeft className="h-4 w-4 shrink-0" />
            Back
          </button>
        }
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <main className="flex-1 p-6 md:p-8 overflow-auto">
          <div className="max-w-6xl mx-auto w-full">
            {/* U3-02: one Suspense boundary for every lazy tab body — Radix's
             * TabsContent only ever mounts the active panel, so at most one
             * of these is ever loading at a time. */}
            <Suspense fallback={<div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>}>
            <Tabs value={activeTab} onValueChange={selectTab}>

        {/* System Tab */}
        <TabsContent value="system" className="space-y-4" role="region" aria-label="System Info settings">
          <SystemTab
            systemInfo={systemInfo}
            discoveryStats={discoveryStats}
            systemProfile={systemProfile}
            isDeepScanning={isDeepScanning}
            onDeepScan={handleDeepScan}
          />
        </TabsContent>

        {/* AI Models Tab - the full picker on sysadmin, the compute-peer link
            on home (which run no model of their own) */}
        <TabsContent value="ai" className="space-y-4" role="region" aria-label="Models & Providers settings">
          {isHomeVariant ? <ComputePeerCard /> : <ModelSettings />}
        </TabsContent>

        {/* Knowledge Tab - ChromaDB + Self-Knowledge + RAG */}
        <TabsContent value="knowledge" className="space-y-4" role="region" aria-label="Knowledge settings">
          <KnowledgeTab
            selfKnowledge={selfKnowledge}
            loadingSelfKnowledge={loadingSelfKnowledge}
            onLoadSelfKnowledge={loadSelfKnowledge}
            showAddKnowledge={showAddKnowledge}
            setShowAddKnowledge={setShowAddKnowledge}
            newKnowledge={newKnowledge}
            setNewKnowledge={setNewKnowledge}
            addingKnowledge={addingKnowledge}
            onAddSelfKnowledge={handleAddSelfKnowledge}
            onDeleteKnowledge={handleDeleteKnowledge}
            ragStats={ragStats}
            ragIndexes={ragIndexes}
            docFreshness={docFreshness}
            indexing={indexing}
            indexProgress={indexProgress}
            onReindex={handleReindex}
            showDocList={showDocList}
            loadingDocs={loadingDocs}
            customDocs={customDocs}
            coreSources={coreSources}
            onToggleDocList={toggleDocList}
            docSuggestions={docSuggestions}
            loadingSuggestions={loadingSuggestions}
            addingSuggestion={addingSuggestion}
            onAddSuggestion={handleAddSuggestion}
            onDismissSuggestion={handleDismissSuggestion}
            trendingSuggestions={trendingSuggestions}
            loadingTrending={loadingTrending}
            userStack={userStack}
            showTrending={showTrending}
            setShowTrending={setShowTrending}
            trendingEnabled={trendingEnabled}
            setTrendingEnabled={setTrendingEnabled}
            onLoadTrendingSuggestions={loadTrendingSuggestions}
            setTrendingSuggestions={setTrendingSuggestions}
            showAddKnowledgeSource={showAddKnowledgeSource}
            setShowAddKnowledgeSource={setShowAddKnowledgeSource}
            newSourceUrl={newSourceUrl}
            setNewSourceUrl={setNewSourceUrl}
            newSourceName={newSourceName}
            setNewSourceName={setNewSourceName}
            addingSource={addingSource}
            addSourceResult={addSourceResult}
            onAddKnowledgeSource={handleAddKnowledgeSource}
          />
        </TabsContent>

        {/* Safety Tab - Consolidated AI Rules, Policy, and Guardrails */}
        <TabsContent value="safety" className="space-y-4" role="region" aria-label="Tool Permissions settings">
          <SafetyTab
            aiRules={aiRules}
            aiRulesExamples={aiRulesExamples}
            newRule={newRule}
            setNewRule={setNewRule}
            addingRule={addingRule}
            onAddRule={handleAddRule}
            onDeleteRule={handleDeleteRule}
            onToggleRule={handleToggleRule}
            policy={policy}
            setPolicy={setPolicy}
            savingPolicy={savingPolicy}
            setSavingPolicy={setSavingPolicy}
            policyPath={policyPath}
          />
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-4" role="region" aria-label="Alert Rules settings">
          <AlertsTab alertRules={alertRules} />
        </TabsContent>

        {/* Being Tab */}
        <TabsContent value="being" className="space-y-4" role="region" aria-label="Identity & Voice settings">
          <BeingTab />
        </TabsContent>

        {/* Devices Tab (G12/P7b — singular entity management) */}
        <TabsContent value="devices" className="space-y-4" role="region" aria-label="Devices settings">
          <DevicesTab />
        </TabsContent>

        {/* Security Tab */}
        <TabsContent value="security" className="space-y-4" role="region" aria-label="Trust Boundary settings">
          <SecurityTab />
        </TabsContent>

        {/* Vision Tab */}
        <TabsContent value="vision" className="space-y-4" role="region" aria-label="Vision settings">
          <VisionTab />
        </TabsContent>

        {/* Audio Tab */}
        <TabsContent value="audio" className="space-y-4" role="region" aria-label="Audio & Voice settings">
          <AudioSettings />
          <SpeakerProfilesCard onEnroll={() => setShowEnrollmentModal(true)} />
        </TabsContent>

        {/* About Tab */}
        <TabsContent value="about" className="space-y-4" role="region" aria-label="About settings">
          <AboutTab
            onOpenComponentLibrary={() => setShowComponentLibrary(true)}
            onOpenLegalNotices={() => setShowLegalNotices(true)}
          />
        </TabsContent>

        {/* Debug Tab — moved from the Layout top bar to the end of settings */}
        <TabsContent value="debug" className="space-y-4" role="region" aria-label="Debug settings">
          <DebugTab />
        </TabsContent>

            </Tabs>
            </Suspense>
          </div>
        </main>
      </div>
            
      {/* Toast Notifications */}
      <Toast
        open={toast.open}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        message={toast.message}
        variant={toast.variant}
      />

      {/* Component Library Viewer Modal */}
      {showComponentLibrary && (
        <ComponentLibraryViewer onClose={() => setShowComponentLibrary(false)} />
      )}

      {/* Legal Notices Modal */}
      <LegalNoticesModal open={showLegalNotices} onOpenChange={setShowLegalNotices} />

      {/* Voice Enrollment Modal */}
      {showEnrollmentModal && (
        <VoiceEnrollmentModal
          onClose={() => setShowEnrollmentModal(false)}
          onEnrolled={() => {
            setToast({ open: true, message: 'Speaker enrolled successfully!', variant: 'success' })
            setShowEnrollmentModal(false)
          }}
        />
      )}
    </div>
  )
}
