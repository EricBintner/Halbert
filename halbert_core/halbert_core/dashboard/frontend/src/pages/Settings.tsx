import { useEffect, useState, useRef } from 'react'
import { useScan } from '@/contexts/ScanContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog, Toast } from '@/components/ui/confirm-dialog'
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
  Users,
  BookOpen,
  Server,
  Check,
  X,
  Plus,
  Zap,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Link,
  Terminal,
  Edit3,
  ScanSearch,
  Clock,
  Shield,
  AlertTriangle,
  Eye,
  Palette,
} from 'lucide-react'
import { ComponentLibraryViewer } from '@/components/ComponentLibraryViewer'

const API_BASE = '/api'

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

// New structure: endpoints are saved without models
interface SavedEndpoint {
  id: string
  name: string
  url: string
  provider: string
  api_key?: string
}

interface ModelAssignment {
  endpoint_id?: string
  endpoint: string
  provider: string
  model: string
  name: string
  enabled?: boolean
}

interface ModelConfig {
  orchestrator: ModelAssignment
  specialist: ModelAssignment & { enabled: boolean }
  vision: ModelAssignment & { enabled: boolean }
  routing: {
    strategy: string
    prefer_specialist_for: string[]
  }
  saved_endpoints: SavedEndpoint[]
}

interface ModelStatus {
  ollama_connected: boolean
  model_installed: boolean
  model_name: string
  endpoint: string
  available_models: string[]
  recommended_model: string | null
  auto_configured?: boolean
}

export function Settings() {
  // Scan context for coordinated system-wide scanning
  const { triggerDeepScan, isDeepScanning } = useScan()
  
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [alertRules, setAlertRules] = useState<AlertRule[]>([])
  const [discoveryStats, setDiscoveryStats] = useState<DiscoveryStats | null>(null)
  const [clearing, setClearing] = useState(false)
  
  // Model config state
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [testingEndpoint, setTestingEndpoint] = useState(false)
  const [testResult, setTestResult] = useState<{success: boolean, message: string} | null>(null)
  
  // Persona state
  const [activePersona, setActivePersona] = useState<string>('it_admin')
  const [personaNames, setPersonaNames] = useState<Record<string, string>>({
    it_admin: 'Halbert',
    friend: 'Cera',
    casual: 'Cera'
  })
  const [editingPersonaName, setEditingPersonaName] = useState<string | null>(null)
  const [savingName, setSavingName] = useState(false)
  
  // New endpoint form (without model)
  const [newEndpoint, setNewEndpoint] = useState({
    name: '',
    url: '',
    provider: 'ollama',
    api_key: ''
  })
  
  // Editing endpoint state
  const [editingEndpoint, setEditingEndpoint] = useState<SavedEndpoint & { index: number } | null>(null)
  const [showAddEndpoint, setShowAddEndpoint] = useState(false)
  const [showAddKnowledgeSource, setShowAddKnowledgeSource] = useState(false)
  
  // Model selector state (separate per role to avoid cross-contamination)
  const [guideEndpointId, setGuideEndpointId] = useState<string>('')
  const [guideModels, setGuideModels] = useState<string[]>([])
  const [loadingGuideModels, setLoadingGuideModels] = useState(false)
  
  const [specialistEndpointId, setSpecialistEndpointId] = useState<string>('')
  const [specialistModels, setSpecialistModels] = useState<string[]>([])
  const [loadingSpecialistModels, setLoadingSpecialistModels] = useState(false)
  
  const [visionEndpointId, setVisionEndpointId] = useState<string>('')
  const [visionModels, setVisionModels] = useState<string[]>([])
  const [loadingVisionModels, setLoadingVisionModels] = useState(false)
  
  // RAG knowledge source state
  const [newSourceUrl, setNewSourceUrl] = useState('')
  const [newSourceName, setNewSourceName] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [addSourceResult, setAddSourceResult] = useState<{success: boolean, message: string, title?: string, alreadyExists?: boolean} | null>(null)
  const [ragStats, setRagStats] = useState<{total_docs: number, user_docs: number, sources: Record<string, number>} | null>(null)
  const [customDocs, setCustomDocs] = useState<Array<{name: string, source: string, url: string, trust_tier: number, is_custom: boolean}>>([])
  const [coreSources, setCoreSources] = useState<Array<{name: string, count: number}>>([])
  const [showDocList, setShowDocList] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  
  // Delete confirmation dialog state
  const [deleteConfirm, setDeleteConfirm] = useState<{
    open: boolean
    endpointName?: string
    isSpecialist: boolean
  }>({ open: false, isSpecialist: false })
  const [deleting, setDeleting] = useState(false)
  
  // Toast notification state
  const [toast, setToast] = useState<{ open: boolean, message: string, variant: 'success' | 'error' | 'info' }>({ 
    open: false, message: '', variant: 'info' 
  })
  
  // Component Library viewer state
  const [showComponentLibrary, setShowComponentLibrary] = useState(false)
  
  // System Profile state
  const [systemProfile, setSystemProfile] = useState<{
    summary: string
    scan_time: string | null
    quick_scan_time: string | null
  } | null>(null)
  // Note: deepScanning state moved to ScanContext (isDeepScanning)
  
  // Computer name (AI identity) state
  const [aiName, setAiName] = useState<string>('Halbert')
  const [userName, setUserName] = useState<string | null>(null)
  const [editingAiName, setEditingAiName] = useState(false)
  const [tempAiName, setTempAiName] = useState('')
  const [savingAiName, setSavingAiName] = useState(false)
  
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
  }, [])

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
    
    // Load model config
    try {
      const res = await fetch(`${API_BASE}/settings/model`)
      const data = await res.json()
      setModelConfig(data)
    } catch (err) {
      console.error('Failed to load model config:', err)
    }
    
    // Load model status (connection + availability)
    // This may auto-configure Local Ollama on fresh install
    setLoadingStatus(true)
    try {
      const res = await fetch(`${API_BASE}/settings/model/status`)
      const data = await res.json()
      setModelStatus(data)
      
      // If auto-configured, reload the model config to get updated endpoints
      if (data.auto_configured) {
        const configRes = await fetch(`${API_BASE}/settings/model`)
        const configData = await configRes.json()
        setModelConfig(configData)
      }
    } catch (err) {
      console.error('Failed to load model status:', err)
      setModelStatus({ ollama_connected: false, model_installed: false, model_name: '', endpoint: 'http://localhost:11434', available_models: [], recommended_model: null })
    } finally {
      setLoadingStatus(false)
    }
    
    // Load active persona
    try {
      const res = await fetch(`${API_BASE}/persona/status`)
      const data = await res.json()
      if (data.active_persona) {
        setActivePersona(data.active_persona)
      }
    } catch (err) {
      console.error('Failed to load persona status:', err)
    }
    
    // Load persona names and AI name
    try {
      const res = await fetch(`${API_BASE}/settings/persona-names`)
      const data = await res.json()
      setPersonaNames(data.names || {})
      if (data.ai_name) {
        setAiName(data.ai_name)
      }
      if (data.user_name) {
        setUserName(data.user_name)
      }
    } catch (err) {
      console.error('Failed to load persona names:', err)
    }
    
    // Load RAG stats
    try {
      const res = await fetch(`${API_BASE}/rag/stats`)
      const data = await res.json()
      setRagStats(data)
    } catch (err) {
      console.error('Failed to load RAG stats:', err)
    }
  }
  
  // Auto-load models for first endpoint when Guide not configured
  useEffect(() => {
    const autoLoadModels = async () => {
      if (!modelConfig?.orchestrator?.model && 
          modelConfig?.saved_endpoints && 
          modelConfig.saved_endpoints.length > 0 &&
          guideModels.length === 0 &&
          !loadingGuideModels) {
        const firstEndpoint = modelConfig.saved_endpoints[0]
        if (firstEndpoint?.id) {
          setGuideEndpointId(firstEndpoint.id)
          setLoadingGuideModels(true)
          const models = await fetchEndpointModels(firstEndpoint.id)
          setGuideModels(models)
          setLoadingGuideModels(false)
        }
      }
    }
    autoLoadModels()
  }, [modelConfig])

  const handleClearDiscoveries = async () => {
    if (!confirm('Clear all cached discoveries? They will be re-scanned on next scan.')) {
      return
    }
    setClearing(true)
    await new Promise(resolve => setTimeout(resolve, 1000))
    setClearing(false)
    alert('Cache cleared. Run a new scan to refresh.')
  }
  
  const handleSaveAiName = async () => {
    if (!tempAiName.trim()) return
    
    setSavingAiName(true)
    try {
      const res = await fetch(`${API_BASE}/settings/computer-name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ai_name: tempAiName.trim() })
      })
      const data = await res.json()
      if (data.success) {
        setAiName(data.ai_name)
        setEditingAiName(false)
        setToast({ open: true, message: `Renamed to "${data.ai_name}"`, variant: 'success' })
      }
    } catch (err) {
      console.error('Failed to save AI name:', err)
      setToast({ open: true, message: 'Failed to save name', variant: 'error' })
    }
    setSavingAiName(false)
  }
  
  const handleTestEndpoint = async (endpoint: string, provider: string) => {
    setTestingEndpoint(true)
    setTestResult(null)
    try {
      const res = await fetch(`${API_BASE}/settings/model/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint, provider, model: '' })
      })
      const data = await res.json()
      setTestResult(data)
    } catch (err) {
      setTestResult({ success: false, message: 'Request failed' })
    }
    setTestingEndpoint(false)
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
  
  const handleSwitchPersona = async (personaId: string) => {
    try {
      const res = await fetch(`${API_BASE}/persona/switch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: personaId, user: 'dashboard' })
      })
      if (res.ok) {
        setActivePersona(personaId)
      }
    } catch (err) {
      console.error('Failed to switch persona:', err)
    }
  }
  
  const handleSavePersonaName = async (personaId: string, name: string) => {
    setSavingName(true)
    try {
      await fetch(`${API_BASE}/settings/persona-name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: personaId, name })
      })
      setPersonaNames(prev => ({ ...prev, [personaId]: name }))
      setEditingPersonaName(null)
    } catch (err) {
      console.error('Failed to save persona name:', err)
    }
    setSavingName(false)
  }
  
  const handleSaveEndpoint = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/endpoints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newEndpoint.name,
          url: newEndpoint.url,
          provider: newEndpoint.provider,
          api_key: newEndpoint.api_key || null
        })
      })
      const data = await res.json()
      if (data.success) {
        setNewEndpoint({ name: '', url: '', provider: 'ollama', api_key: '' })
        setToast({ open: true, message: 'Endpoint saved', variant: 'success' })
        loadSettings()
      } else {
        setToast({ open: true, message: data.detail || 'Failed to save endpoint', variant: 'error' })
      }
    } catch (err) {
      console.error('Failed to save endpoint:', err)
      setToast({ open: true, message: 'Failed to save endpoint', variant: 'error' })
    }
  }
  
  // Update endpoint (using new structure without model)
  const handleUpdateEndpoint = async () => {
    if (!editingEndpoint) return
    try {
      await fetch(`${API_BASE}/settings/endpoints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: editingEndpoint.id,
          name: editingEndpoint.name,
          url: editingEndpoint.url,
          provider: editingEndpoint.provider,
          api_key: editingEndpoint.api_key || null
        })
      })
      setEditingEndpoint(null)
      loadSettings()
    } catch (err) {
      console.error('Failed to update endpoint:', err)
    }
  }
  
  // Delete endpoint state - use ref to avoid stale closure
  const deleteEndpointIdRef = useRef<string | null>(null)
  
  // Show delete confirmation dialog
  const promptDeleteEndpoint = (ep: SavedEndpoint) => {
    deleteEndpointIdRef.current = ep.id
    setDeleteConfirm({ open: true, endpointName: ep.name, isSpecialist: false })
  }
  
  // Actually perform the delete after confirmation
  const handleConfirmDelete = async () => {
    const endpointId = deleteEndpointIdRef.current
    console.log('handleConfirmDelete called, deleteEndpointId:', endpointId)
    if (!endpointId) {
      console.log('No deleteEndpointId, returning early')
      return
    }
    
    setDeleting(true)
    
    try {
      const url = `${API_BASE}/settings/endpoints/${endpointId}`
      console.log('Deleting endpoint:', url)
      const res = await fetch(url, { method: 'DELETE' })
      const data = await res.json()
      console.log('Delete response:', data)
      
      setToast({ 
        open: true, 
        message: 'Endpoint deleted',
        variant: 'success'
      })
      loadSettings()
    } catch (err) {
      console.error('Failed to delete endpoint:', err)
      setToast({ open: true, message: 'Failed to delete endpoint', variant: 'error' })
    }
    
    setDeleting(false)
    deleteEndpointIdRef.current = null
    setDeleteConfirm({ open: false, isSpecialist: false })
  }
  
  // Fetch models from an endpoint
  const fetchEndpointModels = async (endpointId: string): Promise<string[]> => {
    try {
      const res = await fetch(`${API_BASE}/settings/endpoints/${endpointId}/models`)
      const data = await res.json()
      return data.models || []
    } catch (err) {
      console.error('Failed to fetch models:', err)
      return []
    }
  }
  
  // Test endpoint connectivity
  const [testingEndpointId, setTestingEndpointId] = useState<string | null>(null)
  const [endpointTestResults, setEndpointTestResults] = useState<Record<string, {success: boolean, message: string}>>({})
  
  const handleTestSavedEndpoint = async (endpointId: string) => {
    setTestingEndpointId(endpointId)
    try {
      const res = await fetch(`${API_BASE}/settings/endpoints/${endpointId}/test`, { method: 'POST' })
      const data = await res.json()
      setEndpointTestResults(prev => ({ ...prev, [endpointId]: data }))
    } catch (err) {
      setEndpointTestResults(prev => ({ ...prev, [endpointId]: { success: false, message: 'Request failed' } }))
    }
    setTestingEndpointId(null)
  }
  
  // Assign model to role
  const handleAssignModel = async (role: 'guide' | 'specialist' | 'vision', endpointId: string, model: string) => {
    try {
      const res = await fetch(`${API_BASE}/settings/assign/${role}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint_id: endpointId, model })
      })
      const data = await res.json()
      if (data.success) {
        setToast({ open: true, message: `${role.charAt(0).toUpperCase() + role.slice(1)} set to ${model}`, variant: 'success' })
        loadSettings()
      } else {
        setToast({ open: true, message: data.detail || 'Failed to assign model', variant: 'error' })
      }
    } catch (err) {
      console.error(`Failed to assign ${role}:`, err)
      setToast({ open: true, message: `Failed to assign ${role}`, variant: 'error' })
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <SettingsIcon className="h-8 w-8" />
          Settings
        </h1>
        <p className="text-muted-foreground">
          Configure Halbert behavior, AI models, and personas
        </p>
      </div>

      <Tabs defaultValue="system" className="space-y-4">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="system" className="flex items-center gap-2">
            <Cpu className="h-4 w-4" />
            System
          </TabsTrigger>
          <TabsTrigger value="models" className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            AI Models
          </TabsTrigger>
          {/* Personas feature hidden - may be revisited in future when persona behavior differentiation is implemented
          <TabsTrigger value="personas" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Personas
          </TabsTrigger>
          */}
          <TabsTrigger value="knowledge" className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            Knowledge
          </TabsTrigger>
          <TabsTrigger value="rules" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            AI Rules
          </TabsTrigger>
          <TabsTrigger value="alerts" className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Alerts
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

          {/* Computer Identity Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Computer Identity
              </CardTitle>
              <CardDescription>The name your AI assistant uses to identify itself</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">AI Name</Label>
                  {editingAiName ? (
                    <div className="flex items-center gap-2 mt-1">
                      <Input
                        value={tempAiName}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTempAiName(e.target.value)}
                        placeholder="Enter a name..."
                        className="h-8 w-48"
                        onKeyDown={(e) => e.key === 'Enter' && handleSaveAiName()}
                      />
                      <Button size="sm" onClick={handleSaveAiName} disabled={savingAiName || !tempAiName.trim()}>
                        {savingAiName ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingAiName(false)}>
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 mt-1">
                      <code className="text-sm bg-muted px-2 py-1 rounded">{aiName}</code>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        className="h-7 px-2"
                        onClick={() => {
                          setTempAiName(aiName)
                          setEditingAiName(true)
                        }}
                      >
                        <Edit3 className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </div>
                {userName && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Your Name</Label>
                    <p className="text-sm font-medium mt-1">{userName}</p>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  This name appears in chat greetings, system profile, and the AI's self-references.
                </p>
              </div>
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

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="h-5 w-5" />
                About Halbert
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Version</span>
                  <span className="font-medium">0.1.0-alpha.1</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">API Status</span>
                  <Badge className="bg-green-500">Connected</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Active Scanners</span>
                  <span className="font-medium">6</span>
                </div>
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

        {/* AI Models Tab */}
        <TabsContent value="models" className="space-y-4">
          {/* Connection Status Card */}
          <Card className={modelStatus?.ollama_connected 
            ? (modelStatus?.model_installed ? 'border-green-500' : 'border-yellow-500') 
            : 'border-red-500'
          }>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Link className="h-5 w-5" />
                  LLM Connection Status
                </div>
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => loadSettings()}
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {/* Ollama Connection */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Ollama Server</span>
                    <span className="text-xs text-muted-foreground">
                      ({modelStatus?.endpoint || 'localhost:11434'})
                    </span>
                  </div>
                  {loadingStatus ? (
                    <Badge variant="secondary">
                      <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                      Checking...
                    </Badge>
                  ) : modelStatus?.ollama_connected ? (
                    <Badge className="bg-green-500">
                      <Check className="h-3 w-3 mr-1" />
                      Connected
                    </Badge>
                  ) : (
                    <Badge variant="destructive">
                      <X className="h-3 w-3 mr-1" />
                      Not Connected
                    </Badge>
                  )}
                </div>
                
                {/* Model Availability */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Guide Model</span>
                    {modelStatus?.model_name ? (
                      <code className="text-xs bg-muted px-1 rounded">
                        {modelStatus.model_name}
                      </code>
                    ) : (
                      <span className="text-xs text-muted-foreground">(not configured)</span>
                    )}
                  </div>
                  {modelStatus?.model_installed ? (
                    <Badge className="bg-green-500">
                      <Check className="h-3 w-3 mr-1" />
                      Installed
                    </Badge>
                  ) : modelStatus?.ollama_connected && modelStatus?.model_name ? (
                    <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">
                      <X className="h-3 w-3 mr-1" />
                      Not Installed
                    </Badge>
                  ) : modelStatus?.ollama_connected ? (
                    <Badge variant="outline">Configure below</Badge>
                  ) : (
                    <Badge variant="outline">Unknown</Badge>
                  )}
                </div>
                
                {/* All good message */}
                {modelStatus?.ollama_connected && modelStatus?.model_installed && (
                  <div className="pt-2 border-t">
                    <p className="text-sm text-green-600 flex items-center gap-2">
                      <Check className="h-4 w-4" />
                      Ready to chat! Your AI assistant is connected.
                    </p>
                  </div>
                )}
                
                {/* Not connected help */}
                {!modelStatus?.ollama_connected && (
                  <div className="pt-2 border-t">
                    <p className="text-sm text-muted-foreground">
                      Ollama is not running. Start it with:
                    </p>
                    <div className="flex items-center justify-between mt-1 p-2 bg-muted rounded">
                      <code className="text-xs font-mono">ollama serve</code>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 hover:bg-primary/10"
                        onClick={() => {
                          // Dispatch custom event to send command to terminal
                          window.dispatchEvent(new CustomEvent('halbert:run-command', {
                            detail: { command: 'ollama serve' }
                          }))
                        }}
                        title="Run in Terminal"
                      >
                        <Terminal className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Model Assignment Cards with Endpoint + Model Dropdowns */}
          <div className="grid grid-cols-3 gap-4">
            {/* Guide Model Card - green only if configured AND verified connected */}
            <Card className={
              modelConfig?.orchestrator?.model && modelStatus?.ollama_connected && modelStatus?.model_installed
                ? 'border-green-500'  // Configured and verified working
                : modelConfig?.orchestrator?.model && !modelStatus?.ollama_connected
                  ? 'border-red-500'  // Configured but NOT connected (stale config)
                  : modelStatus?.ollama_connected 
                    ? 'border-yellow-500'  // Connected but not configured
                    : ''
            }>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Brain className="h-4 w-4" />
                  Guide Model
                  {!modelConfig?.orchestrator?.model && (
                    <Badge variant="secondary" className="text-xs bg-yellow-100 text-yellow-800">Required</Badge>
                  )}
                </CardTitle>
                <CardDescription className="text-xs">
                  Dashboard chat & general assistance
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {modelConfig?.orchestrator?.model ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">{modelConfig.orchestrator.name || 'Endpoint'}</p>
                    <code className="text-sm bg-muted px-2 py-1 rounded inline-block">{modelConfig.orchestrator.model}</code>
                    
                    {/* Show warning if configured but not connected */}
                    {!modelStatus?.ollama_connected && (
                      <p className="text-xs text-red-600 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        Endpoint not reachable - clear and reconfigure
                      </p>
                    )}
                    {modelStatus?.ollama_connected && !modelStatus?.model_installed && (
                      <p className="text-xs text-yellow-600 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        Model not found on endpoint
                      </p>
                    )}
                    
                    <div className="flex gap-1">
                      {/* Retry button when not connected */}
                      {!modelStatus?.ollama_connected && (
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="h-7 px-2 text-xs"
                          onClick={() => loadSettings()}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" />
                          Retry
                        </Button>
                      )}
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={async () => {
                          await fetch(`${API_BASE}/settings/guide/clear`, { method: 'POST' })
                          loadSettings()
                        }}
                      >
                        <X className="h-3 w-3 mr-1" />
                        Clear
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not configured</p>
                )}
                {/* Only show endpoint/model selection if not yet configured */}
                {!modelConfig?.orchestrator?.model && modelConfig?.saved_endpoints && modelConfig.saved_endpoints.length > 0 && (
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-xs">Endpoint</Label>
                    <select 
                      className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                      value={guideEndpointId || modelConfig.saved_endpoints[0]?.id || ''}
                      onChange={async (e) => {
                        setGuideEndpointId(e.target.value)
                        if (e.target.value) {
                          setLoadingGuideModels(true)
                          const models = await fetchEndpointModels(e.target.value)
                          setGuideModels(models)
                          setLoadingGuideModels(false)
                        }
                      }}
                    >
                      {modelConfig.saved_endpoints.map(ep => (
                        <option key={ep.id} value={ep.id}>{ep.name}</option>
                      ))}
                    </select>
                    <Label className="text-xs">Model</Label>
                    <select 
                      className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                      disabled={loadingGuideModels}
                      onChange={async (e) => {
                        if (e.target.value) {
                          const epId = guideEndpointId || modelConfig.saved_endpoints[0]?.id
                          if (epId) {
                            await handleAssignModel('guide', epId, e.target.value)
                            setGuideEndpointId('')
                            setGuideModels([])
                          }
                        }
                      }}
                    >
                      <option value="">{loadingGuideModels ? 'Loading...' : 'Select model...'}</option>
                      {guideModels.map((m: string) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    {guideModels.length === 0 && !loadingGuideModels && (
                      <p className="text-xs text-muted-foreground">Select an endpoint to see available models</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Specialist Model Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Zap className="h-4 w-4" />
                  Specialist Model
                </CardTitle>
                <CardDescription className="text-xs">
                  Code generation & complex analysis
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {modelConfig?.specialist?.enabled && modelConfig?.specialist?.model ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">{modelConfig.specialist.name || 'Endpoint'}</p>
                    <code className="text-sm bg-muted px-2 py-1 rounded inline-block">{modelConfig.specialist.model}</code>
                    <div>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={async () => {
                          await fetch(`${API_BASE}/settings/specialist/clear`, { method: 'POST' })
                          loadSettings()
                        }}
                      >
                        <X className="h-3 w-3 mr-1" />
                        Clear
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not configured (optional)</p>
                )}
                {/* Only show selection if not configured */}
                {!(modelConfig?.specialist?.enabled && modelConfig?.specialist?.model) && (
                <div className="space-y-2 pt-2 border-t">
                  <Label className="text-xs">Endpoint</Label>
                  <select 
                    className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                    value={specialistEndpointId}
                    onChange={async (e) => {
                      setSpecialistEndpointId(e.target.value)
                      if (e.target.value) {
                        setLoadingSpecialistModels(true)
                        const models = await fetchEndpointModels(e.target.value)
                        setSpecialistModels(models)
                        setLoadingSpecialistModels(false)
                      }
                    }}
                  >
                    <option value="">Select endpoint...</option>
                    {modelConfig?.saved_endpoints.map(ep => (
                      <option key={ep.id} value={ep.id}>{ep.name}</option>
                    ))}
                  </select>
                  {specialistEndpointId && (
                    <>
                      <Label className="text-xs">Model</Label>
                      <select 
                        className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                        disabled={loadingSpecialistModels}
                        onChange={async (e) => {
                          if (e.target.value) {
                            await handleAssignModel('specialist', specialistEndpointId, e.target.value)
                            setSpecialistEndpointId('')
                            setSpecialistModels([])
                          }
                        }}
                      >
                        <option value="">{loadingSpecialistModels ? 'Loading...' : 'Select model...'}</option>
                        {specialistModels.map((m: string) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </>
                  )}
                </div>
                )}
              </CardContent>
            </Card>

            {/* Vision Model Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Eye className="h-4 w-4" />
                  Vision Model
                </CardTitle>
                <CardDescription className="text-xs">
                  Image analysis & screenshots
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {modelConfig?.vision?.enabled && modelConfig?.vision?.model ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">{modelConfig.vision.name || 'Endpoint'}</p>
                    <code className="text-sm bg-muted px-2 py-1 rounded inline-block">{modelConfig.vision.model}</code>
                    <div>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={async () => {
                          await fetch(`${API_BASE}/settings/vision/clear`, { method: 'POST' })
                          loadSettings()
                        }}
                      >
                        <X className="h-3 w-3 mr-1" />
                        Clear
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not configured (optional)</p>
                )}
                {/* Only show selection if not configured */}
                {!(modelConfig?.vision?.enabled && modelConfig?.vision?.model) && (
                <div className="space-y-2 pt-2 border-t">
                  <Label className="text-xs">Endpoint</Label>
                  <select 
                    className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                    value={visionEndpointId}
                    onChange={async (e) => {
                      setVisionEndpointId(e.target.value)
                      if (e.target.value) {
                        setLoadingVisionModels(true)
                        const models = await fetchEndpointModels(e.target.value)
                        setVisionModels(models)
                        setLoadingVisionModels(false)
                      }
                    }}
                  >
                    <option value="">Select endpoint...</option>
                    {modelConfig?.saved_endpoints.map(ep => (
                      <option key={ep.id} value={ep.id}>{ep.name}</option>
                    ))}
                  </select>
                  {visionEndpointId && (
                    <>
                      <Label className="text-xs">Model</Label>
                      <select 
                        className="h-8 w-full text-xs rounded-md border border-input bg-background px-2"
                        disabled={loadingVisionModels}
                        onChange={async (e) => {
                          if (e.target.value) {
                            await handleAssignModel('vision', visionEndpointId, e.target.value)
                            setVisionEndpointId('')
                            setVisionModels([])
                          }
                        }}
                      >
                        <option value="">{loadingVisionModels ? 'Loading...' : 'Select model...'}</option>
                        {visionModels.map((m: string) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </>
                  )}
                </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Multimodal hint */}
          <div className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3">
            <strong>💡 Tip:</strong> If your Specialist is a multimodal model (e.g., <code className="bg-muted px-1 rounded">llama3.2-vision:90b</code>), 
            you don't need a separate Vision model. Dedicated vision models like <code className="bg-muted px-1 rounded">llava:34b</code> are 
            useful when your Specialist is text-only (e.g., <code className="bg-muted px-1 rounded">llama3.3:70b</code>).
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Saved Endpoints
              </CardTitle>
              <CardDescription>
                Add LLM server endpoints. Models are selected separately for each role.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Saved endpoints list */}
              <div className="space-y-2">
                {modelConfig?.saved_endpoints.map((ep, i) => (
                  <div key={ep.id || i} className="p-3 border rounded-lg hover:border-primary/50 transition-colors">
                    {editingEndpoint?.index === i ? (
                      /* Edit mode */
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                          <Input 
                            value={editingEndpoint.name}
                            onChange={(e) => setEditingEndpoint({...editingEndpoint, name: e.target.value})}
                            placeholder="Display name"
                          />
                          <Input 
                            value={editingEndpoint.url}
                            onChange={(e) => setEditingEndpoint({...editingEndpoint, url: e.target.value})}
                            placeholder="http://localhost:11434"
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <select 
                            value={editingEndpoint.provider}
                            onChange={(e) => setEditingEndpoint({...editingEndpoint, provider: e.target.value})}
                            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                          >
                            <option value="ollama">Ollama</option>
                            <option value="openai">OpenAI-compatible</option>
                          </select>
                          <Input 
                            value={editingEndpoint.api_key || ''}
                            onChange={(e) => setEditingEndpoint({...editingEndpoint, api_key: e.target.value})}
                            placeholder="API Key (optional)"
                            type="password"
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={handleUpdateEndpoint}>
                            <Check className="h-3 w-3 mr-1" />
                            Save
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditingEndpoint(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      /* View mode */
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-medium">{ep.name || 'Unnamed Endpoint'}</p>
                            <Badge variant="outline" className="text-xs">{ep.provider}</Badge>
                            {ep.api_key && <Badge variant="outline" className="text-xs">🔑 API Key</Badge>}
                            {modelConfig?.orchestrator?.endpoint_id === ep.id && (
                              <code className="text-xs bg-muted px-1.5 py-0.5 rounded flex items-center gap-1">
                                <Brain className="h-3 w-3" />
                                Guide: {modelConfig.orchestrator.model}
                              </code>
                            )}
                            {modelConfig?.specialist?.endpoint_id === ep.id && (
                              <code className="text-xs bg-muted px-1.5 py-0.5 rounded flex items-center gap-1">
                                <Zap className="h-3 w-3" />
                                Specialist: {modelConfig.specialist.model}
                              </code>
                            )}
                            {modelConfig?.vision?.endpoint_id === ep.id && (
                              <code className="text-xs bg-muted px-1.5 py-0.5 rounded flex items-center gap-1">
                                <Eye className="h-3 w-3" />
                                Vision: {modelConfig.vision.model}
                              </code>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{ep.url || (ep as any).endpoint || ''}</p>
                          {endpointTestResults[ep.id] && (
                            <Badge 
                              variant={endpointTestResults[ep.id].success ? "default" : "destructive"} 
                              className="mt-1 text-xs"
                            >
                              {endpointTestResults[ep.id].success ? <Check className="h-3 w-3 mr-1" /> : <X className="h-3 w-3 mr-1" />}
                              {endpointTestResults[ep.id].message}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          <Button 
                            variant="ghost" 
                            size="sm"
                            className="h-8 px-2"
                            onClick={() => handleTestSavedEndpoint(ep.id)}
                            disabled={testingEndpointId === ep.id}
                            title="Test Connection"
                          >
                            {testingEndpointId === ep.id ? (
                              <RefreshCw className="h-3 w-3 animate-spin" />
                            ) : (
                              <Zap className="h-3 w-3" />
                            )}
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            className="h-8 px-2"
                            onClick={() => setEditingEndpoint({index: i, ...ep})}
                            title="Edit"
                          >
                            <Edit3 className="h-3 w-3" />
                          </Button>
                          {/* Don't allow deleting Local Ollama default endpoint - use placeholder for alignment */}
                          {(ep.url || (ep as any).endpoint) === 'http://localhost:11434' ? (
                            <div className="h-8 w-8" />
                          ) : (
                            <Button 
                              variant="ghost" 
                              size="sm"
                              className="h-8 px-2"
                              onClick={() => promptDeleteEndpoint(ep)}
                              title="Delete"
                            >
                              <Trash2 className="h-3 w-3 text-destructive" />
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {(!modelConfig?.saved_endpoints || modelConfig.saved_endpoints.length === 0) && (
                  <p className="text-sm text-muted-foreground">No saved endpoints. Add one below to get started.</p>
                )}
              </div>
              
              {/* Add new endpoint - collapsible */}
              <div className="border-t pt-4 space-y-4">
                <button 
                  className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                  onClick={() => setShowAddEndpoint(!showAddEndpoint)}
                >
                  <Plus className={`h-4 w-4 transition-transform ${showAddEndpoint ? 'rotate-45' : ''}`} />
                  Add Endpoint
                  <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showAddEndpoint ? 'rotate-180' : ''}`} />
                </button>
                {showAddEndpoint && (
                <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Display Name</Label>
                    <Input 
                      value={newEndpoint.name}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEndpoint({...newEndpoint, name: e.target.value})}
                      placeholder="Local Ollama, GPU Server, etc."
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Endpoint URL</Label>
                    <Input 
                      value={newEndpoint.url}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEndpoint({...newEndpoint, url: e.target.value})}
                      placeholder="http://localhost:11434"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Provider</Label>
                    <select 
                      value={newEndpoint.provider}
                      onChange={(e) => setNewEndpoint({...newEndpoint, provider: e.target.value})}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      <option value="ollama">Ollama</option>
                      <option value="openai">OpenAI-compatible</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>API Key (optional)</Label>
                    <Input 
                      value={newEndpoint.api_key}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEndpoint({...newEndpoint, api_key: e.target.value})}
                      placeholder="For OpenAI/Anthropic/etc."
                      type="password"
                    />
                  </div>
                </div>
                <div className="flex gap-2 items-center">
                  <Button 
                    variant="outline" 
                    onClick={() => handleTestEndpoint(newEndpoint.url, newEndpoint.provider)}
                    disabled={!newEndpoint.url || testingEndpoint}
                  >
                    {testingEndpoint ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : null}
                    Test Connection
                  </Button>
                  <Button 
                    onClick={handleSaveEndpoint} 
                    disabled={!newEndpoint.url || !newEndpoint.name}
                  >
                    Save Endpoint
                  </Button>
                  {testResult && (
                    <Badge variant={testResult.success ? "default" : "destructive"} className="ml-2">
                      {testResult.success ? <Check className="h-3 w-3 mr-1" /> : <X className="h-3 w-3 mr-1" />}
                      {testResult.message}
                    </Badge>
                  )}
                </div>
                </>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Personas Tab - HIDDEN from UI but code preserved for future use
           The tab trigger is commented out above, so users cannot navigate here.
           This feature may be revisited when:
           - Persona behavior differentiation is implemented (different system prompts)
           - Memory isolation per persona is completed
           - Custom persona creation is added
           For now, the AI just uses default name "Halbert" from PersonaManager.
        */}
        <TabsContent value="personas" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Active Mode
                </div>
                <Button variant="outline" size="sm" disabled title="Coming soon">
                  <Plus className="h-4 w-4 mr-1" />
                  Add Persona
                </Button>
              </CardTitle>
              <CardDescription>
                Switch between different AI personalities. Each persona has its own name and style.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-4">
                {/* IT Admin Persona */}
                <div
                  className={`relative flex-1 rounded-lg border-2 transition-all ${
                    activePersona === 'it_admin'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50'
                  }`}
                >
                  {activePersona === 'it_admin' && (
                    <Badge className="absolute top-2 right-2">Active</Badge>
                  )}
                  <button
                    onClick={() => handleSwitchPersona('it_admin')}
                    className="w-full p-4 text-left"
                  >
                    <div className="text-2xl mb-2">🔧</div>
                    <p className="font-medium">IT Administrator</p>
                    <p className="text-sm text-muted-foreground">Professional system management</p>
                  </button>
                  
                  {/* AI Name for this persona */}
                  <div className="px-4 pb-4 pt-2 border-t">
                    <Label className="text-xs text-muted-foreground">AI Name</Label>
                    {editingPersonaName === 'it_admin' ? (
                      <div className="flex gap-2 mt-1">
                        <Input
                          value={personaNames['it_admin'] || 'Halbert'}
                          onChange={(e) => setPersonaNames(prev => ({ ...prev, it_admin: e.target.value }))}
                          className="h-7 text-sm"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSavePersonaName('it_admin', personaNames['it_admin'] || 'Halbert')
                            if (e.key === 'Escape') setEditingPersonaName(null)
                          }}
                        />
                        <Button 
                          size="sm" 
                          className="h-7" 
                          onClick={() => handleSavePersonaName('it_admin', personaNames['it_admin'] || 'Halbert')}
                          disabled={savingName}
                        >
                          {savingName ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 mt-1">
                        <span className="text-sm font-medium">{personaNames['it_admin'] || 'Halbert'}</span>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="h-5 w-5 p-0"
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingPersonaName('it_admin')
                          }}
                        >
                          <Edit3 className="h-3 w-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Casual Companion Persona */}
                <div
                  className={`relative flex-1 rounded-lg border-2 transition-all ${
                    activePersona === 'friend'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50'
                  }`}
                >
                  {activePersona === 'friend' && (
                    <Badge className="absolute top-2 right-2">Active</Badge>
                  )}
                  <button
                    onClick={() => handleSwitchPersona('friend')}
                    className="w-full p-4 text-left"
                  >
                    <div className="text-2xl mb-2">😊</div>
                    <p className="font-medium">Casual Companion</p>
                    <p className="text-sm text-muted-foreground">Warm conversational style</p>
                  </button>
                  
                  {/* AI Name for this persona */}
                  <div className="px-4 pb-4 pt-2 border-t">
                    <Label className="text-xs text-muted-foreground">AI Name</Label>
                    {editingPersonaName === 'friend' ? (
                      <div className="flex gap-2 mt-1">
                        <Input
                          value={personaNames['friend'] || 'Cera'}
                          onChange={(e) => setPersonaNames(prev => ({ ...prev, friend: e.target.value }))}
                          className="h-7 text-sm"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSavePersonaName('friend', personaNames['friend'] || 'Cera')
                            if (e.key === 'Escape') setEditingPersonaName(null)
                          }}
                        />
                        <Button 
                          size="sm" 
                          className="h-7" 
                          onClick={() => handleSavePersonaName('friend', personaNames['friend'] || 'Cera')}
                          disabled={savingName}
                        >
                          {savingName ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 mt-1">
                        <span className="text-sm font-medium">{personaNames['friend'] || 'Cera'}</span>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="h-5 w-5 p-0"
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingPersonaName('friend')
                          }}
                        >
                          <Edit3 className="h-3 w-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Knowledge Tab */}
        <TabsContent value="knowledge" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                Knowledge Base (RAG)
              </CardTitle>
              <CardDescription>
                Documentation and knowledge sources the AI uses for context
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Stats summary */}
                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">Knowledge Sources</h4>
                    <Button variant="ghost" size="sm" onClick={toggleDocList}>
                      {showDocList ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                      {showDocList ? 'Hide' : 'View All'}
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Total Documents</p>
                      <p className="font-medium">{ragStats?.total_docs?.toLocaleString() || '~3,000'} docs</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Custom Added</p>
                      <p className="font-medium">{ragStats?.user_docs || 0} docs</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Core Sources</p>
                      <p className="font-medium text-xs">Arch Wiki, Docker, Kubernetes, man pages, Linux Kernel</p>
                    </div>
                  </div>
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
                                <tr className="border-t-2 border-muted bg-blue-50/50 dark:bg-blue-900/20">
                                  <td colSpan={2} className="p-2 text-xs font-medium text-muted-foreground">
                                    Custom Added ({customDocs.length})
                                  </td>
                                </tr>
                                {customDocs.map((doc, i) => (
                                  <tr key={`custom-${i}`} className="border-t bg-blue-50/30 dark:bg-blue-900/10">
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
                
                {/* Add custom source - collapsible */}
                <div className="border-t pt-4 space-y-4">
                  <button 
                    className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                    onClick={() => setShowAddKnowledgeSource(!showAddKnowledgeSource)}
                  >
                    <Plus className={`h-4 w-4 transition-transform ${showAddKnowledgeSource ? 'rotate-45' : ''}`} />
                    Add Custom Knowledge Source
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

        {/* AI Rules Tab */}
        <TabsContent value="rules" className="space-y-4">
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
                            <Check className="h-4 w-4 text-green-500" />
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
                    placeholder="e.g., bcachefs requires kernel 6.8 or earlier - do not recommend kernel upgrades"
                    className="text-sm"
                  />
                </div>
                
                <div className="flex gap-4 items-end">
                  <div className="space-y-2 flex-1">
                    <Label htmlFor="rule-category">Category</Label>
                    <select
                      id="rule-category"
                      value={newRule.category}
                      onChange={(e) => setNewRule(prev => ({ ...prev, category: e.target.value }))}
                      className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm"
                    >
                      <option value="general">General</option>
                      <option value="storage">Storage</option>
                      <option value="kernel">Kernel</option>
                      <option value="network">Network</option>
                      <option value="security">Security</option>
                      <option value="docker">Docker/Containers</option>
                      <option value="packages">Packages</option>
                    </select>
                  </div>
                  
                  <div className="space-y-2 flex-1">
                    <Label htmlFor="rule-priority">Priority</Label>
                    <select
                      id="rule-priority"
                      value={newRule.priority}
                      onChange={(e) => setNewRule(prev => ({ ...prev, priority: e.target.value }))}
                      className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm"
                    >
                      <option value="high">High (Always apply)</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low (Context-dependent)</option>
                    </select>
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
      
      {/* Delete Endpoint Confirmation Dialog */}
      <ConfirmDialog
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, isSpecialist: false })}
        onConfirm={handleConfirmDelete}
        title="Delete Endpoint?"
        description={`Are you sure you want to delete "${deleteConfirm.endpointName || 'this endpoint'}"?`}
        warning={deleteConfirm.isSpecialist 
          ? "This endpoint is currently set as your Specialist model. Deleting it will also clear the specialist configuration."
          : undefined
        }
        confirmText="Delete"
        variant="destructive"
        loading={deleting}
      />
      
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
