// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useScan } from '@/contexts/ScanContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Toast } from '@/components/ui/confirm-dialog'
import { api } from '@/lib/api'
import type { SystemInfo } from '@/lib/tauri'
import { getSystemInfo } from '@/lib/tauri'
import { 
  Settings as SettingsIcon, 
  Bell, 
  Cpu, 
  Database,
  RefreshCw,
  Trash2,
  Info,
  Brain,
  BookOpen,
  Check,
  X,
  Plus,
  Zap,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Edit3,
  ScanSearch,
  Clock,
  Shield,
  AlertTriangle,
  Palette,
  Lock,
  FileCode,
  Sparkles,
} from 'lucide-react'
import { ComponentLibraryViewer } from '@/components/ComponentLibraryViewer'
import { PageHeader, DataVersionCard } from '@/components/domain'
import { ModelSettings } from '@/components/llm'
import { LegalNoticesModal } from '@/components/legal'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

interface AlertRule {
  id: string
  name: string
  description: string
  severity: string
  enabled: boolean
}

interface DiscoveryStats {
  total: number
  by_type: Record<string, number>
}

// ─────────────────────────────────────────────────────────────────────────────
// Being Settings Component (Phase 6 / T6c.1)
// ─────────────────────────────────────────────────────────────────────────────

interface EndpointModel {
  endpointId: string
  endpointName: string
  model: string
}

function BeingSettings() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [availableModels, setAvailableModels] = useState<Record<string, EndpointModel[]>>({})
  const [modelsLoading, setModelsLoading] = useState(false)

  useEffect(() => {
    loadConfig()
    loadAvailableModels()
  }, [])

  const loadConfig = async () => {
    try {
      const resp = await fetch(`${API_BASE}/settings/being`)
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
      }
    } catch (e) {
      console.error('Failed to load being config:', e)
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableModels = async () => {
    try {
      setModelsLoading(true)
      const resp = await fetch(`${API_BASE}/llm/config`)
      if (!resp.ok) return
      const data = await resp.json()
      const endpoints = data?.data?.saved_endpoints || data?.saved_endpoints || []
      const grouped: Record<string, EndpointModel[]> = {}
      await Promise.all(endpoints.map(async (ep: any) => {
        try {
          const modelResp = await fetch(`${API_BASE}/api/llm/proxy/models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: ep.provider, url: ep.url, ...(ep.api_key ? { api_key: ep.api_key } : {}) }),
          })
          if (!modelResp.ok) return
          const modelData = await modelResp.json()
          const models: string[] = modelData?.data?.models || modelData?.models || []
          if (models.length) {
            grouped[ep.id] = models.map((m: string) => ({
              endpointId: ep.id,
              endpointName: ep.name,
              model: m,
            }))
          }
        } catch { /* endpoint unreachable, skip */ }
      }))
      setAvailableModels(grouped)
    } catch (e) {
      console.error('Failed to load available models:', e)
    } finally {
      setModelsLoading(false)
    }
  }

  const saveConfig = async (updates: Record<string, any>) => {
    setSaving(true)
    try {
      const resp = await fetch(`${API_BASE}/settings/being`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
        setToast('Saved')
        setTimeout(() => setToast(null), 2000)
      } else {
        const err = await resp.json()
        setToast(`Error: ${err.detail || 'Failed to save'}`)
        setTimeout(() => setToast(null), 3000)
      }
    } catch (e) {
      setToast('Error: Network failure')
      setTimeout(() => setToast(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Loading being config...</CardContent></Card>
  }

  if (!config) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Failed to load config</CardContent></Card>
  }

  return (
    <div className="space-y-4">
      {/* Character (Phase 3) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            Character
          </CardTitle>
          <CardDescription>
            Name, communication style, and custom instructions for your computer.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Name */}
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              defaultValue={config.name || ''}
              placeholder="Halbert"
              onBlur={(e) => {
                if (e.target.value !== (config.name || '')) {
                  saveConfig({ name: e.target.value })
                }
              }}
            />
            <p className="text-xs text-muted-foreground">
              What you call your computer.
            </p>
          </div>

          {/* Communication Style */}
          <div className="space-y-2">
            <Label>Communication Style</Label>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {(['concise', 'balanced', 'detailed', 'analytical', 'casual'] as const).map((style) => (
                <Button
                  key={style}
                  variant={(config.archetype_id || 'balanced') === style ? 'default' : 'outline'}
                  onClick={() => saveConfig({ archetype_id: style })}
                  disabled={saving}
                  className="capitalize"
                >
                  {style}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {(config.archetype_id || 'balanced') === 'concise' && 'Fast, minimal words, imperative commands.'}
              {(config.archetype_id || 'balanced') === 'balanced' && 'Clear, calm, factual, helpful.'}
              {config.archetype_id === 'detailed' && 'Explanatory, instructional. Explains why before acting.'}
              {config.archetype_id === 'analytical' && 'Systems-focused, design-oriented, addresses root causes.'}
              {config.archetype_id === 'casual' && 'Approachable, light touch, conversational.'}
            </p>
          </div>

          {/* Voice Presentation */}
          <div className="space-y-2">
            <Label>Voice Presentation</Label>
            <div className="grid grid-cols-3 gap-2">
              {([
                { key: 'not_defined', label: 'Not Defined' },
                { key: 'male', label: 'Male' },
                { key: 'female', label: 'Female' },
              ] as const).map(({ key, label }) => (
                <Button
                  key={key}
                  variant={config.voice_presentation === key ? 'default' : 'outline'}
                  onClick={() => saveConfig({ voice_presentation: key })}
                  disabled={saving}
                >
                  {label}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              How the voice is characterized in conversation.
            </p>
          </div>

          {/* Conversation Model */}
          <div className="space-y-2">
            <Label>Conversation Model</Label>
            <Select
              value={config.model ? `${config.model_endpoint_id || ''}:${config.model}` : ''}
              onChange={(e) => {
                const val = e.target.value
                if (!val) {
                  saveConfig({ model: '', model_endpoint_id: '' })
                } else {
                  const sepIdx = val.indexOf(':')
                  const endpointId = val.substring(0, sepIdx)
                  const model = val.substring(sepIdx + 1)
                  saveConfig({ model, model_endpoint_id: endpointId })
                }
              }}
              disabled={saving || modelsLoading}
            >
              <option value="">Default (System Agent Model)</option>
              {Object.entries(availableModels).map(([epId, models]) => (
                <optgroup key={epId} label={models[0]?.endpointName || epId}>
                  {models.map((m) => (
                    <option key={`${epId}:${m.model}`} value={`${epId}:${m.model}`}>
                      {m.model}
                    </option>
                  ))}
                </optgroup>
              ))}
              {modelsLoading && <option disabled>Loading models...</option>}
            </Select>
            <p className="text-xs text-muted-foreground">
              Override the system agent model for this persona. Default uses the global chat model.
            </p>
          </div>

          {/* Custom Instructions */}
          <div className="space-y-2">
            <Label>Custom Instructions</Label>
            <textarea
              className="w-full min-h-[100px] font-sans text-sm rounded-md border border-input bg-background px-3 py-2 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              defaultValue={config.custom_personality_prompt || ''}
              placeholder="e.g. Always show the full shell command before asking for confirmation. Keep status updates brief."
              onBlur={(e) => {
                if (e.target.value !== (config.custom_personality_prompt || '')) {
                  saveConfig({ custom_personality_prompt: e.target.value })
                }
              }}
            />
            <p className="text-xs text-muted-foreground">
              Plain text instructions injected directly into system guidance.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Voice Setting */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Voice
          </CardTitle>
          <CardDescription>
            How the being refers to itself in conversation
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label>Self-reference style</Label>
            <div className="grid grid-cols-3 gap-2">
              <Button
                variant={config.voice === 'first_person' ? 'default' : 'outline'}
                onClick={() => saveConfig({ voice: 'first_person' })}
                disabled={saving}
                className="flex flex-col items-center gap-1 h-auto py-3"
              >
                <span className="font-medium">First Person</span>
                <span className="text-xs opacity-70">"I", "my", "me"</span>
              </Button>
              <Button
                variant={config.voice === 'the_computer' ? 'default' : 'outline'}
                onClick={() => saveConfig({ voice: 'the_computer' })}
                disabled={saving}
                className="flex flex-col items-center gap-1 h-auto py-3"
              >
                <span className="font-medium">The Computer</span>
                <span className="text-xs opacity-70">"this system", "it"</span>
              </Button>
              <Button
                variant={config.voice === 'hybrid' ? 'default' : 'outline'}
                onClick={() => saveConfig({ voice: 'hybrid' })}
                disabled={saving}
                className="flex flex-col items-center gap-1 h-auto py-3"
              >
                <span className="font-medium">Hybrid</span>
                <span className="text-xs opacity-70">Mixed context</span>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Proactivity Setting */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Proactivity
          </CardTitle>
          <CardDescription>
            How assertively the being opens conversations on its own
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label>Proactivity dial</Label>
            <div className="grid grid-cols-4 gap-2">
              {(['off', 'quiet', 'balanced', 'assertive'] as const).map((level) => (
                <Button
                  key={level}
                  variant={config.proactivity === level ? 'default' : 'outline'}
                  onClick={() => saveConfig({ proactivity: level })}
                  disabled={saving}
                  className="capitalize"
                >
                  {level}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              {config.proactivity === 'off' && 'The being never initiates conversation.'}
              {config.proactivity === 'quiet' && 'Only critical alerts trigger proactive messages.'}
              {config.proactivity === 'balanced' && 'Warnings and critical alerts trigger proactive messages.'}
              {config.proactivity === 'assertive' && 'All findings, including info-level, trigger proactive messages.'}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Quiet Hours */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Quiet Hours
          </CardTitle>
          <CardDescription>
            Suppress non-critical notifications during these hours
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {config.quiet_hours ? (
            <div className="flex items-center gap-2">
              <Input
                type="time"
                defaultValue={config.quiet_hours.start}
                onChange={(e) => {
                  saveConfig({ quiet_hours: { ...config.quiet_hours, start: e.target.value } })
                }}
                className="w-32"
              />
              <span className="text-muted-foreground">to</span>
              <Input
                type="time"
                defaultValue={config.quiet_hours.end}
                onChange={(e) => {
                  saveConfig({ quiet_hours: { ...config.quiet_hours, end: e.target.value } })
                }}
                className="w-32"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => saveConfig({ quiet_hours: null })}
                disabled={saving}
              >
                Disable
              </Button>
            </div>
          ) : (
            <Button
              variant="outline"
              onClick={() => saveConfig({ quiet_hours: { start: '22:00', end: '07:00' } })}
              disabled={saving}
            >
              Enable quiet hours
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Morning Report */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Morning Report
          </CardTitle>
          <CardDescription>
            A daily summary of system health and findings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {config.morning_report?.enabled ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Input
                  type="time"
                  defaultValue={config.morning_report.time || '08:00'}
                  onChange={(e) => {
                    saveConfig({ morning_report: { ...config.morning_report, time: e.target.value } })
                  }}
                  className="w-32"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => saveConfig({ morning_report: { enabled: false } })}
                  disabled={saving}
                >
                  Disable
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-sm text-muted-foreground">Timezone:</label>
                <Input
                  type="text"
                  defaultValue={config.timezone || 'local'}
                  placeholder="local"
                  onChange={(e) => {
                    saveConfig({ timezone: e.target.value })
                  }}
                  className="w-48"
                />
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              onClick={() => saveConfig({ morning_report: { enabled: true, time: '08:00' } })}
              disabled={saving}
            >
              Enable morning report
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Purpose */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Edit3 className="h-5 w-5" />
            Purpose
          </CardTitle>
          <CardDescription>
            Free text — what this machine is for, in your words
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="w-full min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            defaultValue={config.purpose || ''}
            placeholder="e.g. Keep this machine fast and secure for daily development work."
            onBlur={(e) => {
              if (e.target.value !== config.purpose) {
                saveConfig({ purpose: e.target.value })
              }
            }}
          />
        </CardContent>
      </Card>

      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg border bg-background px-4 py-2 text-sm shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}

/**
 * The tabs this page has, in the order they are shown. Also the whitelist for
 * `?tab=`: Radix renders no panel for a value with no trigger, so an
 * unrecognised one would leave the page showing its tab strip and nothing
 * else. An unknown tab is not an error worth a message — it is a stale or
 * mistyped link — so it opens the first tab, which is what a bare /settings
 * does too.
 */
const SETTINGS_TABS = ['system', 'ai', 'knowledge', 'safety', 'alerts', 'being', 'about'] as const
const DEFAULT_SETTINGS_TAB = SETTINGS_TABS[0]

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
  const activeTab = settingsTabFromParam(searchParams.get('tab'))
  const selectTab = useCallback((next: string) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      params.set('tab', next)
      return params
    }, { replace: true })
  }, [setSearchParams])

  // Scan context for coordinated system-wide scanning
  const { triggerDeepScan, isDeepScanning } = useScan()
  
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [alertRules, setAlertRules] = useState<AlertRule[]>([])
  const [discoveryStats, setDiscoveryStats] = useState<DiscoveryStats | null>(null)
  
  // Policy state
  const [policy, setPolicy] = useState<{default_allow: boolean, tools: Record<string, {allow: boolean}>}>({
    default_allow: true,
    tools: {}
  })
  const [policyPath, setPolicyPath] = useState<string>('')
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [clearing, setClearing] = useState(false)
  
  // Editing endpoint state
  const [showAddKnowledgeSource, setShowAddKnowledgeSource] = useState(false)
  
  // RAG knowledge source state
  const [newSourceUrl, setNewSourceUrl] = useState('')
  const [newSourceName, setNewSourceName] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [addSourceResult, setAddSourceResult] = useState<{success: boolean, message: string, title?: string, alreadyExists?: boolean} | null>(null)
  const [ragStats, setRagStats] = useState<{total_docs: number, user_docs: number, sources: Record<string, number>} | null>(null)
  const [ragIndexes, setRagIndexes] = useState<Array<{name: string, doc_count: number, indexed_at: string, source_file: string, embedding_model: string, build_time_seconds: number}>>([])
  const [customDocs, setCustomDocs] = useState<Array<{name: string, source: string, url: string, trust_tier: number, is_custom: boolean}>>([])
  const [coreSources, setCoreSources] = useState<Array<{name: string, count: number}>>([])
  const [showDocList, setShowDocList] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [_indexResult, setIndexResult] = useState<{total: number, sources: string[]} | null>(null)
  const [indexProgress, setIndexProgress] = useState<{
    percent: number, 
    currentSource: string | null, 
    completed: number, 
    total: number
  }>({ percent: 0, currentSource: null, completed: 0, total: 0 })
  const [docFreshness, setDocFreshness] = useState<{
    last_indexed_at: string | null,
    docs_at_last_index: number,
    info: string
  } | null>(null)
  
  // Documentation Suggestions state (self-learning)
  interface DocSuggestion {
    doc_key: string
    doc_name: string
    doc_url: string
    doc_description: string
    doc_category: string
    discovery_id: string
    discovery_name: string
    confidence: number
    reason: string
    priority: number
  }
  const [docSuggestions, setDocSuggestions] = useState<DocSuggestion[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [addingSuggestion, setAddingSuggestion] = useState<string | null>(null)
  
  // Trending Topics state (Phase 34 - Cutting-Edge Discovery)
  interface TrendingSuggestion {
    name: string
    full_name: string
    description: string
    url: string
    doc_url: string
    stars: number
    language: string
    relevance_score: number
    reason: string
    stack_match: string[]
    has_docs: boolean
  }
  interface UserStack {
    runtimes: string[]
    package_managers: string[]
    tools: string[]
    editors: string[]
  }
  const [trendingSuggestions, setTrendingSuggestions] = useState<TrendingSuggestion[]>([])
  const [loadingTrending, setLoadingTrending] = useState(false)
  const [userStack, setUserStack] = useState<UserStack | null>(null)
  const [showTrending, setShowTrending] = useState(true)
  const [trendingEnabled, setTrendingEnabled] = useState(true)
  
  // Self-Knowledge state
  interface SelfKnowledgeEntry {
    id: string
    type: string
    subject: string
    content: string
    rationale?: string
    source: string
    created_at?: string
  }
  const [selfKnowledge, setSelfKnowledge] = useState<SelfKnowledgeEntry[]>([])
  const [loadingSelfKnowledge, setLoadingSelfKnowledge] = useState(false)
  // editingKnowledge removed - was unused (future: inline editing)
  const [newKnowledge, setNewKnowledge] = useState({ subject: '', content: '', rationale: '' })
  const [addingKnowledge, setAddingKnowledge] = useState(false)
  const [showAddKnowledge, setShowAddKnowledge] = useState(false)
  
  // Toast notification state
  const [toast, setToast] = useState<{ open: boolean, message: string, variant: 'success' | 'error' | 'info' }>({ 
    open: false, message: '', variant: 'info' 
  })
  
  // Component Library viewer state
  const [showComponentLibrary, setShowComponentLibrary] = useState(false)

  // Legal notices modal state (LEG-MOD-01)
  const [showLegalNotices, setShowLegalNotices] = useState(false)
  
  // System Profile state
  const [systemProfile, setSystemProfile] = useState<{
    summary: string
    scan_time: string | null
    quick_scan_time: string | null
  } | null>(null)
  // Note: deepScanning state moved to ScanContext (isDeepScanning)
  
  // AI Rules state
  interface AIRule {
    id: string
    rule: string
    category: string
    priority: string
    enabled: boolean
    created_at?: string
  }
  const [aiRules, setAiRules] = useState<AIRule[]>([])
  const [aiRulesExamples, setAiRulesExamples] = useState<string[]>([])
  const [newRule, setNewRule] = useState({ rule: '', category: 'general', priority: 'high' })
  const [addingRule, setAddingRule] = useState(false)

  useEffect(() => {
    loadSettings()
    loadSystemProfile()
    loadAiRules()
    loadSelfKnowledge()
    checkIndexingStatus()
    loadDocSuggestions()
    loadTrendingSuggestions()
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
        loadSettings() // Refresh stats
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

  const loadSettings = async () => {
    // Load system info
    try {
      const info = await getSystemInfo()
      setSystemInfo(info)
    } catch (err) {
      console.error('getSystemInfo failed', err)
    }

    // Load alert rules
    try {
      const res = await fetch(`${API_BASE}/alerts/rules`)
      const data = await res.json()
      setAlertRules(data.rules || [])
    } catch (err) {
      console.error('Failed to load alert rules:', err)
    }

    // Load discovery stats
    try {
      const stats = await api.getDiscoveryStats()
      setDiscoveryStats(stats)
    } catch (err) {
      console.error('Failed to load discovery stats:', err)
    }
    
    // Load policy
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
    

    // Load RAG stats
    try {
      const res = await fetch(`${API_BASE}/rag/stats`)
      const data = await res.json()
      setRagStats(data)
    } catch (err) {
      console.error('Failed to load RAG stats:', err)
    }
    
    // Load RAG indexes
    try {
      const res = await fetch(`${API_BASE}/rag/indexes`)
      const data = await res.json()
      setRagIndexes(data.indexes || [])
    } catch (err) {
      console.error('Failed to load RAG indexes:', err)
    }
  }
  
  const handleClearDiscoveries = async () => {
    if (!confirm('Clear all cached discoveries? They will be re-scanned on next scan.')) {
      return
    }
    setClearing(true)
    await new Promise(resolve => setTimeout(resolve, 1000))
    setClearing(false)
    alert('Cache cleared. Run a new scan to refresh.')
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
        loadSettings()
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
        loadSettings()
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
    const interval = setInterval(async () => {
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
            clearInterval(interval)
            setIndexing(false)
            setIndexProgress({ percent: 100, currentSource: null, completed: 0, total: 0 })
            
            if (status.error) {
              setToast({ open: true, message: `Indexing failed: ${status.error}`, variant: 'error' })
            } else {
              setIndexResult({ total: status.total_indexed || 0, sources: status.sources_completed || [] })
              setToast({ open: true, message: `Indexed ${status.total_indexed || 0} documents`, variant: 'success' })
              loadSettings()
              if (showDocList) loadRagDocuments()
            }
          }
        }
      } catch (err) {
        console.error('Failed to poll indexing status:', err)
      }
    }, 2000) // Poll every 2 seconds for smoother progress
    
    // Store interval ID for cleanup
    return () => clearInterval(interval)
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
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        icon={<SettingsIcon className="h-8 w-8" />}
        title="Settings"
        description="Configure Halbert behavior, AI models, and system settings"
        hideScanButton
      />

      <Tabs value={activeTab} onValueChange={selectTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-7">
          <TabsTrigger value="system" className="flex items-center gap-2">
            <Cpu className="h-4 w-4" />
            System
          </TabsTrigger>
          <TabsTrigger value="ai" className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            AI Models
          </TabsTrigger>
          <TabsTrigger value="knowledge" className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            Knowledge
          </TabsTrigger>
          <TabsTrigger value="safety" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Safety
          </TabsTrigger>
          <TabsTrigger value="alerts" className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Alerts
          </TabsTrigger>
          <TabsTrigger value="being" className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Being
          </TabsTrigger>
          <TabsTrigger value="about" className="flex items-center gap-2">
            <Info className="h-4 w-4" />
            About
          </TabsTrigger>
        </TabsList>

        {/* System Tab */}
        <TabsContent value="system" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5" />
                System Information
              </CardTitle>
            </CardHeader>
            <CardContent>
              {systemInfo ? (
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Hostname</p>
                    <p className="font-medium">{systemInfo.hostname}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Operating System</p>
                    <p className="font-medium">{systemInfo.os_name} {systemInfo.os_version}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Kernel</p>
                    <p className="font-medium">{systemInfo.kernel_version}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">CPU Cores</p>
                    <p className="font-medium">{systemInfo.cpu_count}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Memory</p>
                    <p className="font-medium">
                      {Math.round(systemInfo.total_memory_mb / 1024)} GB total
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Loading system info...</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                Discovery Cache
              </CardTitle>
              <CardDescription>Manage cached system discoveries</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{discoveryStats?.total || 0} discoveries cached</p>
                  <p className="text-sm text-muted-foreground">
                    {Object.entries(discoveryStats?.by_type || {})
                      .map(([type, count]) => `${count} ${type}`)
                      .join(', ')
                    }
                  </p>
                </div>
                <Button variant="outline" onClick={handleClearDiscoveries} disabled={clearing}>
                  {clearing ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Trash2 className="h-4 w-4 mr-2" />}
                  Clear Cache
                </Button>
              </div>
            </CardContent>
          </Card>
          
          {/* System Profile Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ScanSearch className="h-5 w-5" />
                System Profile
              </CardTitle>
              <CardDescription>
                Deep system awareness for AI context. Run a deep scan after major changes or updates.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {systemProfile ? (
                <>
                  <div className="p-3 bg-muted rounded-lg font-mono text-xs whitespace-pre-wrap max-h-48 overflow-auto">
                    {systemProfile.summary}
                  </div>
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4" />
                      Last deep scan: {systemProfile.scan_time ? new Date(systemProfile.scan_time).toLocaleString() : 'Never'}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No system profile yet. Run a deep scan to create one.</p>
              )}
              <div className="flex gap-2">
                <Button 
                  onClick={handleDeepScan} 
                  disabled={isDeepScanning}
                  variant="outline"
                >
                  {isDeepScanning ? (
                    <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Scanning...</>
                  ) : (
                    <><ScanSearch className="h-4 w-4 mr-2" />Run Deep Scan</>
                  )}
                </Button>
                <p className="text-xs text-muted-foreground self-center">
                  Scans hardware, packages, services, security, and more (~30-60 sec)
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI Models Tab - includes model config and knowledge sources */}
        <TabsContent value="ai" className="space-y-4">
          <ModelSettings />


        </TabsContent>

        {/* Knowledge Tab - ChromaDB + Self-Knowledge + RAG */}
        <TabsContent value="knowledge" className="space-y-4">
          {/* Data Version & Freshness - Phase 54 */}
          <DataVersionCard />

          {/* Self-Knowledge Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Brain className="h-5 w-5" />
                  Self-Knowledge
                </div>
                <Button variant="ghost" size="sm" onClick={loadSelfKnowledge}>
                  <RefreshCw className={`h-4 w-4 ${loadingSelfKnowledge ? 'animate-spin' : ''}`} />
                </Button>
              </CardTitle>
              <CardDescription>
                What Halbert knows about itself and your system. Teach it new things or edit existing knowledge.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Add new knowledge - collapsible */}
                <div className="space-y-3">
                  <button 
                    className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                    onClick={() => setShowAddKnowledge(!showAddKnowledge)}
                  >
                    <Plus className={`h-4 w-4 transition-transform ${showAddKnowledge ? 'rotate-45' : ''}`} />
                    Teach Something New
                    <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showAddKnowledge ? 'rotate-180' : ''}`} />
                  </button>
                  {showAddKnowledge && (
                    <div className="p-4 border rounded-lg space-y-3 bg-muted/30">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label>Subject</Label>
                          <Input 
                            value={newKnowledge.subject}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, subject: e.target.value})}
                            placeholder="e.g., bcachefs pool, main server" 
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Content</Label>
                          <Input 
                            value={newKnowledge.content}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, content: e.target.value})}
                            placeholder="What is it? What does it do?" 
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label>Why does it exist? (optional)</Label>
                        <Input 
                          value={newKnowledge.rationale}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, rationale: e.target.value})}
                          placeholder="The reason or purpose behind this..." 
                        />
                      </div>
                      <Button 
                        onClick={handleAddSelfKnowledge} 
                        disabled={!newKnowledge.subject || !newKnowledge.content || addingKnowledge}
                      >
                        {addingKnowledge ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
                        Save Knowledge
                      </Button>
                    </div>
                  )}
                </div>

                {/* Knowledge entries list */}
                {loadingSelfKnowledge ? (
                  <div className="p-4 text-center text-muted-foreground">
                    <RefreshCw className="h-4 w-4 animate-spin inline mr-2" />
                    Loading...
                  </div>
                ) : selfKnowledge.length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground border rounded-lg">
                    No self-knowledge yet. Teach Halbert something!
                  </div>
                ) : (
                  <div className="border rounded-lg divide-y max-h-96 overflow-y-auto">
                    {selfKnowledge.map((entry) => (
                      <div key={entry.id} className="p-3 hover:bg-muted/30 transition-colors">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <Badge variant="outline" className="text-xs">{entry.type.replace(/_/g, ' ')}</Badge>
                              <span className="font-medium">{entry.subject}</span>
                            </div>
                            <p className="text-sm text-muted-foreground line-clamp-2">{entry.content}</p>
                            {entry.rationale && entry.rationale !== entry.content && (
                              <p className="text-xs text-muted-foreground mt-1 italic">Why: {entry.rationale}</p>
                            )}
                          </div>
                          {entry.source === 'user' && (
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => handleDeleteKnowledge(entry.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* RAG Knowledge Sources Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                Documentation (RAG)
              </CardTitle>
              <CardDescription>
                Linux documentation and knowledge sources the AI uses for context
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Stats summary */}
                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">Indexed Sources</h4>
                    <div className="flex items-center gap-2">
                      <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={handleReindex}
                        disabled={indexing}
                      >
                        {indexing ? (
                          <><RefreshCw className="h-4 w-4 mr-1 animate-spin" />Indexing...</>
                        ) : (
                          <><Database className="h-4 w-4 mr-1" />Re-index</>
                        )}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={toggleDocList}>
                        {showDocList ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                        {showDocList ? 'Hide' : 'View All'}
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Total Documents</p>
                      <p className="font-medium">{ragStats?.total_docs?.toLocaleString() || 'Loading...'} docs</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Custom Added</p>
                      <p className="font-medium">{ragStats?.user_docs || 0} docs</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Last Indexed</p>
                      <p className="font-medium text-xs">
                        {docFreshness?.last_indexed_at 
                          ? new Date(docFreshness.last_indexed_at).toLocaleDateString() 
                          : 'Never'}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Updates</p>
                      <p className="font-medium text-xs text-success dark:text-success">
                        Core docs updated with releases
                      </p>
                    </div>
                  </div>
                  {indexing && (
                    <div className="mt-3 p-3 bg-info/10 rounded text-sm text-info dark:text-info">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center">
                          <RefreshCw className="h-3 w-3 mr-2 animate-spin" />
                          <span>Indexing documents...</span>
                        </div>
                        <span className="text-xs">You can navigate away safely</span>
                      </div>
                      <div className="w-full bg-info-muted dark:bg-info rounded-full h-2.5 mb-1">
                        <div 
                          className="bg-info h-2.5 rounded-full transition-all duration-300"
                          style={{ width: `${indexProgress.percent}%` }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-xs text-info dark:text-info">
                        <span>{indexProgress.currentSource ? `Processing: ${indexProgress.currentSource}` : 'Starting...'}</span>
                        <span>{indexProgress.percent}% ({indexProgress.completed}/{indexProgress.total} sources)</span>
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Expandable document list */}
                {showDocList && (
                  <div className="border rounded-lg overflow-hidden">
                    <div className="max-h-80 overflow-y-auto">
                      {loadingDocs ? (
                        <div className="p-4 text-center text-muted-foreground">
                          <RefreshCw className="h-4 w-4 animate-spin inline mr-2" />
                          Loading documents...
                        </div>
                      ) : (
                        <table className="w-full text-sm">
                          <thead className="bg-muted/50 sticky top-0">
                            <tr>
                              <th className="text-left p-2 font-medium">Name</th>
                              <th className="text-right p-2 font-medium">Docs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {/* Core sources first */}
                            <tr className="bg-muted/30">
                              <td colSpan={2} className="p-2 text-xs font-medium text-muted-foreground">
                                Core Knowledge Base
                              </td>
                            </tr>
                            {coreSources.map((source, i) => (
                              <tr key={`core-${i}`} className="border-t">
                                <td className="p-2">{source.name}</td>
                                <td className="p-2 text-right text-muted-foreground">{source.count.toLocaleString()}</td>
                              </tr>
                            ))}
                            {/* Custom docs below */}
                            {customDocs.length > 0 && (
                              <>
                                <tr className="border-t-2 border-muted bg-info-muted/50 dark:bg-info/20">
                                  <td colSpan={2} className="p-2 text-xs font-medium text-muted-foreground">
                                    Custom Added ({customDocs.length})
                                  </td>
                                </tr>
                                {customDocs.map((doc, i) => (
                                  <tr key={`custom-${i}`} className="border-t bg-info-muted/30 dark:bg-info/10">
                                    <td className="p-2">
                                      <span className="font-medium">{doc.name}</span>
                                      {doc.url && (
                                        <a href={doc.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-muted-foreground hover:text-foreground">
                                          <ExternalLink className="h-3 w-3 inline" />
                                        </a>
                                      )}
                                    </td>
                                    <td className="p-2 text-right">
                                      <Badge variant="outline" className="text-xs">Custom</Badge>
                                    </td>
                                  </tr>
                                ))}
                              </>
                            )}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                )}
                
                {/* RAG Indexes (Phase 27) */}
                {ragIndexes.length > 0 && (
                  <div className="border-t pt-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-info" />
                      <span className="font-medium">Search Indexes</span>
                      <Badge variant="secondary" className="text-xs">{ragIndexes.length} indexes</Badge>
                    </div>
                    <div className="grid gap-2">
                      {ragIndexes.map((idx) => (
                        <div 
                          key={idx.name}
                          className="flex items-center justify-between p-2 bg-info/5 border border-info/20 rounded-lg"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm">{idx.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                              <Badge variant="outline" className="text-xs">{idx.doc_count.toLocaleString()} docs</Badge>
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Indexed {idx.indexed_at} • {idx.embedding_model}
                            </p>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {idx.build_time_seconds.toFixed(1)}s
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Suggested Documentation (Self-Learning) */}
                {docSuggestions.length > 0 && (
                  <div className="border-t pt-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-warning" />
                        <span className="font-medium">Suggested Documentation</span>
                        <Badge variant="secondary" className="text-xs">{docSuggestions.length} found</Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">Based on your system</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Halbert detected services on your system that have documentation available.
                    </p>
                    <div className="space-y-2">
                      {docSuggestions.slice(0, 5).map((suggestion) => (
                        <div 
                          key={suggestion.doc_key}
                          className="flex items-center justify-between p-2 bg-warning/5 border border-warning/20 rounded-lg"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm">{suggestion.doc_name}</span>
                              <Badge variant="outline" className="text-xs">{suggestion.doc_category}</Badge>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                              {suggestion.reason}
                            </p>
                          </div>
                          <div className="flex items-center gap-1 ml-2">
                            <Button 
                              size="sm" 
                              variant="ghost"
                              className="h-7 px-2"
                              onClick={() => handleAddSuggestion(suggestion.doc_key)}
                              disabled={addingSuggestion === suggestion.doc_key}
                            >
                              {addingSuggestion === suggestion.doc_key ? (
                                <RefreshCw className="h-3 w-3 animate-spin" />
                              ) : (
                                <Plus className="h-3 w-3" />
                              )}
                              <span className="ml-1 text-xs">Add</span>
                            </Button>
                            <Button 
                              size="sm" 
                              variant="ghost"
                              className="h-7 px-2 text-muted-foreground hover:text-foreground"
                              onClick={() => handleDismissSuggestion(suggestion.doc_key)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {loadingSuggestions && (
                      <div className="text-xs text-muted-foreground flex items-center gap-2">
                        <RefreshCw className="h-3 w-3 animate-spin" />
                        Loading suggestions...
                      </div>
                    )}
                  </div>
                )}
                
                {/* Trending Topics (Phase 34 - Cutting-Edge Discovery) */}
                <div className="border-t pt-4 space-y-3">
                  <button 
                    className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                    onClick={() => setShowTrending(!showTrending)}
                  >
                    <Zap className={`h-4 w-4 text-warning transition-transform ${showTrending ? '' : '-rotate-90'}`} />
                    <span>Trending on GitHub</span>
                    {trendingSuggestions.length > 0 && (
                      <Badge variant="secondary" className="text-xs bg-warning/10 text-warning">
                        {trendingSuggestions.length} found
                      </Badge>
                    )}
                    <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showTrending ? 'rotate-180' : ''}`} />
                  </button>
                  
                  {showTrending && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-muted-foreground">
                          Emerging tools relevant to your tech stack
                          {userStack && (
                            <span className="ml-1">
                              ({[...userStack.runtimes, ...userStack.tools].slice(0, 3).join(', ')})
                            </span>
                          )}
                        </p>
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={trendingEnabled}
                              onChange={(e) => setTrendingEnabled(e.target.checked)}
                              className="h-3 w-3"
                            />
                            Auto-discover
                          </label>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-2"
                            onClick={() => loadTrendingSuggestions()}
                            disabled={loadingTrending}
                          >
                            <RefreshCw className={`h-3 w-3 ${loadingTrending ? 'animate-spin' : ''}`} />
                          </Button>
                        </div>
                      </div>
                      
                      {loadingTrending ? (
                        <div className="text-xs text-muted-foreground flex items-center gap-2 py-4">
                          <RefreshCw className="h-3 w-3 animate-spin" />
                          Fetching trending repos from GitHub...
                        </div>
                      ) : trendingSuggestions.length > 0 ? (
                        <div className="space-y-2">
                          {trendingSuggestions.slice(0, 5).map((repo) => (
                            <div 
                              key={repo.full_name}
                              className="flex items-center justify-between p-2 bg-warning/5 border border-warning/20 rounded-lg"
                            >
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <a 
                                    href={repo.url} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="font-medium text-sm hover:underline flex items-center gap-1"
                                  >
                                    {repo.name}
                                    <ExternalLink className="h-3 w-3" />
                                  </a>
                                  <Badge variant="outline" className="text-xs">{repo.language || 'Multi'}</Badge>
                                  <span className="text-xs text-muted-foreground">⭐ {repo.stars.toLocaleString()}</span>
                                </div>
                                <p className="text-xs text-muted-foreground truncate">
                                  {repo.description || repo.reason}
                                </p>
                                {repo.stack_match.length > 0 && (
                                  <div className="flex items-center gap-1 mt-1">
                                    <span className="text-xs text-warning">Related to:</span>
                                    {repo.stack_match.slice(0, 3).map((match) => (
                                      <Badge key={match} variant="secondary" className="text-xs px-1 py-0">
                                        {match}
                                      </Badge>
                                    ))}
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-1 ml-2">
                                {repo.has_docs && (
                                  <Button 
                                    size="sm" 
                                    variant="ghost"
                                    className="h-7 px-2"
                                    onClick={() => window.open(repo.doc_url || repo.url, '_blank')}
                                  >
                                    <BookOpen className="h-3 w-3" />
                                    <span className="ml-1 text-xs">Docs</span>
                                  </Button>
                                )}
                                <Button 
                                  size="sm" 
                                  variant="ghost"
                                  className="h-7 px-2 text-muted-foreground hover:text-foreground"
                                  onClick={() => setTrendingSuggestions(prev => prev.filter(s => s.full_name !== repo.full_name))}
                                >
                                  <X className="h-3 w-3" />
                                </Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground py-2">
                          No trending repos found for your stack. Try refreshing or check your GitHub token.
                        </p>
                      )}
                    </div>
                  )}
                </div>
                
                {/* Add custom source - collapsible */}
                <div className="border-t pt-4 space-y-4">
                  <button 
                    className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                    onClick={() => setShowAddKnowledgeSource(!showAddKnowledgeSource)}
                  >
                    <Plus className={`h-4 w-4 transition-transform ${showAddKnowledgeSource ? 'rotate-45' : ''}`} />
                    Add Custom Documentation
                    <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showAddKnowledgeSource ? 'rotate-180' : ''}`} />
                  </button>
                  {showAddKnowledgeSource && (
                  <>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>URL</Label>
                      <Input 
                        value={newSourceUrl}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewSourceUrl(e.target.value)}
                        placeholder="https://docs.example.com/" 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Name (optional)</Label>
                      <Input 
                        value={newSourceName}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewSourceName(e.target.value)}
                        placeholder="Example Documentation" 
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button 
                      onClick={handleAddKnowledgeSource} 
                      disabled={!newSourceUrl || addingSource}
                    >
                      {addingSource ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
                      Add Source
                    </Button>
                    {addSourceResult && (
                      <Badge variant={addSourceResult.success ? "default" : addSourceResult.alreadyExists ? "secondary" : "destructive"}>
                        {addSourceResult.success ? <Check className="h-3 w-3 mr-1" /> : <X className="h-3 w-3 mr-1" />}
                        {addSourceResult.message}
                        {addSourceResult.success && addSourceResult.title && `: ${addSourceResult.title}`}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Add any documentation URL and Halbert will index it for context-aware responses.
                    Auto-detects docs from ReadTheDocs, wikis, /docs/ paths, and more.
                  </p>
                  </>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Safety Tab - Consolidated AI Rules, Policy, and Guardrails */}
        <TabsContent value="safety" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Custom AI Rules
              </CardTitle>
              <CardDescription>
                Define rules and guardrails for edge cases the AI should always follow.
                These override general advice when they apply to your specific setup.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Existing rules - shown first */}
              {aiRules.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="h-8 w-8 mx-auto mb-3 opacity-50" />
                  <p className="font-medium">No custom rules yet</p>
                  <p className="text-sm mt-1">
                    Add rules below to help the AI understand your specific setup and edge cases.
                  </p>
                  {aiRulesExamples.length > 0 && (
                    <div className="mt-4 text-left max-w-lg mx-auto">
                      <p className="text-xs font-medium mb-2">Example rules:</p>
                      <ul className="text-xs space-y-1 text-muted-foreground">
                        {aiRulesExamples.map((ex, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-primary">•</span>
                            <span>{ex}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {aiRules.length} rule{aiRules.length !== 1 ? 's' : ''} active. 
                    The AI will always consider these when providing advice.
                  </p>
                  {aiRules.map((rule) => (
                    <div
                      key={rule.id}
                      className={`flex items-start justify-between p-3 rounded-lg border ${
                        rule.enabled ? 'bg-background' : 'bg-muted/50 opacity-60'
                      }`}
                    >
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant={rule.priority === 'high' ? 'default' : 'outline'} className="text-xs">
                            {rule.priority}
                          </Badge>
                          <Badge variant="secondary" className="text-xs">
                            {rule.category}
                          </Badge>
                          {!rule.enabled && (
                            <Badge variant="outline" className="text-xs text-muted-foreground">
                              Disabled
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm">{rule.rule}</p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleRule(rule)}
                          title={rule.enabled ? 'Disable rule' : 'Enable rule'}
                        >
                          {rule.enabled ? (
                            <Check className="h-4 w-4 text-success" />
                          ) : (
                            <X className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteRule(rule.id)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {/* Add new rule form - at bottom */}
              <div className="space-y-4 p-4 border rounded-lg bg-muted/30">
                <div className="space-y-2">
                  <Label htmlFor="new-rule">Add a New Rule</Label>
                  <Input
                    id="new-rule"
                    value={newRule.rule}
                    onChange={(e) => setNewRule(prev => ({ ...prev, rule: e.target.value }))}
                    placeholder="e.g., My NAS mounts may be offline - don't treat unmounted network shares as errors"
                    className="text-sm"
                  />
                </div>
                
                <div className="flex gap-4 items-end">
                  <div className="space-y-2 flex-1">
                    <Label htmlFor="rule-category">Category</Label>
                    <Select
                      id="rule-category"
                      value={newRule.category}
                      onChange={(e) => setNewRule(prev => ({ ...prev, category: e.target.value }))}
                    >
                      <option value="general">General</option>
                      <option value="storage">Storage</option>
                      <option value="kernel">Kernel</option>
                      <option value="network">Network</option>
                      <option value="security">Security</option>
                      <option value="docker">Docker/Containers</option>
                      <option value="packages">Packages</option>
                    </Select>
                  </div>
                  
                  <div className="space-y-2 flex-1">
                    <Label htmlFor="rule-priority">Priority</Label>
                    <Select
                      id="rule-priority"
                      value={newRule.priority}
                      onChange={(e) => setNewRule(prev => ({ ...prev, priority: e.target.value }))}
                    >
                      <option value="high">High (Always apply)</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low (Context-dependent)</option>
                    </Select>
                  </div>
                  
                  <Button 
                    onClick={handleAddRule}
                    disabled={!newRule.rule.trim() || addingRule}
                    size="sm"
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Add Rule
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tool Policy Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Lock className="h-5 w-5" />
                Tool Policy
              </CardTitle>
              <CardDescription>
                Control which tools the AI can execute. Tools not explicitly configured follow the default policy.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Default Allow</p>
                    <p className="text-sm text-muted-foreground">
                      When enabled, tools are allowed unless explicitly denied
                    </p>
                  </div>
                  <Button
                    variant={policy.default_allow ? "default" : "outline"}
                    size="sm"
                    disabled={savingPolicy}
                    onClick={async () => {
                      setSavingPolicy(true)
                      try {
                        const newPolicy = { ...policy, default_allow: !policy.default_allow }
                        await fetch(`${API_BASE}/settings/policy`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ policy: newPolicy })
                        })
                        setPolicy(newPolicy)
                      } catch (err) {
                        console.error('Failed to update policy:', err)
                      }
                      setSavingPolicy(false)
                    }}
                  >
                    {policy.default_allow ? (
                      <><Check className="h-4 w-4 mr-1" /> Enabled</>
                    ) : (
                      <><X className="h-4 w-4 mr-1" /> Disabled</>
                    )}
                  </Button>
                </div>
              </div>
              
              <div className="space-y-2">
                <h4 className="font-medium text-sm">Tool Overrides</h4>
                <p className="text-sm text-muted-foreground">
                  Click to toggle individual tool permissions
                </p>
                <div className="grid gap-2 mt-2">
                  {Object.entries(policy.tools || {}).map(([toolName, config]) => (
                    <div key={toolName} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                      <div className="flex items-center gap-2">
                        <FileCode className="h-4 w-4" />
                        <span className="font-mono text-sm">{toolName}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant={config.allow ? "default" : "destructive"}
                          size="sm"
                          disabled={savingPolicy}
                          onClick={async () => {
                            setSavingPolicy(true)
                            try {
                              await fetch(`${API_BASE}/settings/policy/tool`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ tool: toolName, allow: !config.allow })
                              })
                              setPolicy(prev => ({
                                ...prev,
                                tools: { ...prev.tools, [toolName]: { allow: !config.allow } }
                              }))
                            } catch (err) {
                              console.error('Failed to update tool policy:', err)
                            }
                            setSavingPolicy(false)
                          }}
                        >
                          {config.allow ? 'Allowed' : 'Denied'}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={savingPolicy}
                          onClick={async () => {
                            setSavingPolicy(true)
                            try {
                              await fetch(`${API_BASE}/settings/policy/tool/${toolName}`, {
                                method: 'DELETE'
                              })
                              setPolicy(prev => {
                                const newTools = { ...prev.tools }
                                delete newTools[toolName]
                                return { ...prev, tools: newTools }
                              })
                            } catch (err) {
                              console.error('Failed to delete tool policy:', err)
                            }
                            setSavingPolicy(false)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  {Object.keys(policy.tools || {}).length === 0 && (
                    <p className="text-sm text-muted-foreground p-3">
                      No tool overrides configured. All tools follow the default policy.
                    </p>
                  )}
                </div>
              </div>
              
              <div className="pt-4 border-t">
                <p className="text-xs text-muted-foreground">
                  Policy file: <code className="px-1 py-0.5 bg-muted rounded">{policyPath || 'config/policy.yml'}</code>
                </p>
              </div>
            </CardContent>
          </Card>

        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Alert Rules
              </CardTitle>
              <CardDescription>
                Configure when alerts are triggered
              </CardDescription>
            </CardHeader>
            <CardContent>
              {alertRules.length === 0 ? (
                <p className="text-sm text-muted-foreground">Loading alert rules...</p>
              ) : (
                <div className="space-y-4">
                  {alertRules.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between p-3 rounded-lg border"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{rule.name}</p>
                          <Badge variant="outline" className="text-xs">
                            {rule.severity}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">{rule.description}</p>
                      </div>
                      <Badge variant={rule.enabled ? "default" : "outline"}>
                        {rule.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Being Tab */}
        <TabsContent value="being" className="space-y-4">
          <BeingSettings />
        </TabsContent>

        {/* About Tab */}
        <TabsContent value="about" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="h-5 w-5" />
                About Halbert
              </CardTitle>
              <CardDescription>
                AI-powered Linux system assistant
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <h4 className="font-medium">Version</h4>
                <p className="text-sm text-muted-foreground">Development Build</p>
              </div>
              
              <div className="space-y-2">
                <h4 className="font-medium">Developer Tools</h4>
                <p className="text-sm text-muted-foreground mb-3">
                  Explore the UI component library used to build Halbert.
                </p>
                <Button variant="outline" onClick={() => setShowComponentLibrary(true)}>
                  <Palette className="h-4 w-4 mr-2" />
                  View Component Library
                </Button>
              </div>

              <div className="space-y-2">
                <h4 className="font-medium">Legal & Third-Party Notices</h4>
                <p className="text-sm text-muted-foreground mb-3">
                  Licenses and attributions for Halbert, its RAG corpus sources,
                  software dependencies, and bundled foundation models.
                </p>
                <Button variant="outline" onClick={() => setShowLegalNotices(true)}>
                  <Shield className="h-4 w-4 mr-2" />
                  View Legal Notices
                </Button>
              </div>
              
              <div className="space-y-2">
                <h4 className="font-medium">Links</h4>
                <div className="flex flex-wrap gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <a href="https://github.com" target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="h-4 w-4 mr-1" />
                      GitHub
                    </a>
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <a href="/docs" target="_blank" rel="noopener noreferrer">
                      <BookOpen className="h-4 w-4 mr-1" />
                      Documentation
                    </a>
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      
      {/* Component Library Viewer */}
      {showComponentLibrary && (
        <ComponentLibraryViewer onClose={() => setShowComponentLibrary(false)} />
      )}

      {/* Legal Notices Modal (LEG-MOD-01) */}
      <LegalNoticesModal open={showLegalNotices} onOpenChange={setShowLegalNotices} />
      
      {/* Toast Notifications */}
      <Toast 
        open={toast.open}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        message={toast.message}
        variant={toast.variant}
      />
    </div>
  )
}
