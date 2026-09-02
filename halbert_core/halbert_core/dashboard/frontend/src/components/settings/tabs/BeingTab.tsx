// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'
import {
  Trash2,
  Brain,
  Plus,
  Zap,
  Edit3,
  Clock,
  Bell,
  Sparkles,
  Eye,
} from 'lucide-react'

const API_BASE = apiUrl('/api')

// ─────────────────────────────────────────────────────────────────────────────
// Being Settings (Phase 6 / T6c.1)
// ─────────────────────────────────────────────────────────────────────────────

function BeingSettings() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [personas, setPersonas] = useState<any[]>([])
  const [activePersonaId, setActivePersonaId] = useState<string>('default')
  const [showNewPersona, setShowNewPersona] = useState(false)
  const [newPersonaName, setNewPersonaName] = useState('')

  useEffect(() => {
    loadConfig()
    loadPersonas()
  }, [])

  const loadConfig = async () => {
    try {
      const resp = await fetch(`${API_BASE}/settings/being`)
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
        setActivePersonaId(data.config.persona_id || 'default')
      }
    } catch (e) {
      console.error('Failed to load personality config:', e)
    } finally {
      setLoading(false)
    }
  }

  const loadPersonas = async () => {
    try {
      const resp = await fetch(`${API_BASE}/persona/list`)
      if (resp.ok) {
        const data = await resp.json()
        setPersonas(data.personas || [])
        setActivePersonaId(data.active_id || 'default')
      }
    } catch (e) {
      console.error('Failed to load personas:', e)
    }
  }

  const createPersona = async () => {
    if (!newPersonaName.trim()) return
    try {
      const resp = await fetch(`${API_BASE}/persona`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: newPersonaName.trim() }),
      })
      if (resp.ok) {
        setShowNewPersona(false)
        setNewPersonaName('')
        await loadPersonas()
      }
    } catch (e) {
      setToast('Error: Failed to create persona')
      setTimeout(() => setToast(null), 3000)
    }
  }

  const activatePersona = async (id: string) => {
    if (id === activePersonaId) return
    try {
      const resp = await fetch(`${API_BASE}/persona/${id}/activate`, { method: 'POST' })
      if (resp.ok) {
        setActivePersonaId(id)
        await loadConfig()
        setToast('Persona switched')
        setTimeout(() => setToast(null), 2000)
      }
    } catch (e) {
      setToast('Error: Failed to switch persona')
      setTimeout(() => setToast(null), 3000)
    }
  }

  const deletePersona = async (id: string) => {
    if (!confirm('Delete this persona? This cannot be undone.')) return
    try {
      const resp = await fetch(`${API_BASE}/persona/${id}`, { method: 'DELETE' })
      if (resp.ok) {
        await loadPersonas()
      } else {
        const err = await resp.json()
        setToast(`Error: ${err.detail || 'Failed to delete'}`)
        setTimeout(() => setToast(null), 3000)
      }
    } catch (e) {
      setToast('Error: Network failure')
      setTimeout(() => setToast(null), 3000)
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
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Loading personality config...</CardContent></Card>
  }

  if (!config) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Failed to load config</CardContent></Card>
  }

  return (
    <div className="space-y-4">
      {/* Persona Switcher */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Personas
          </CardTitle>
          <CardDescription>
            Switch between personas or create a new one. Only one persona is active at a time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            {personas.map((p) => (
              <div
                key={p.id}
                className={`group relative rounded-lg border p-4 cursor-pointer transition-colors min-w-[160px] ${
                  p.id === activePersonaId
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'border-input hover:border-primary/50'
                }`}
                onClick={() => activatePersona(p.id)}
              >
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${p.id === activePersonaId ? 'bg-primary' : 'bg-muted-foreground/30'}`} />
                  <span className="font-medium text-sm">{p.display_name}</span>
                </div>
                {p.id === activePersonaId && (
                  <span className="text-xs text-primary mt-1 block">Active</span>
                )}
                {p.id !== activePersonaId && personas.length > 1 && (
                  <button
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                    onClick={(e) => { e.stopPropagation(); deletePersona(p.id) }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
            {/* New persona button / input */}
            {showNewPersona ? (
              <div className="rounded-lg border border-primary p-4 min-w-[200px]">
                <Input
                  autoFocus
                  placeholder="Persona name..."
                  value={newPersonaName}
                  onChange={(e) => setNewPersonaName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') createPersona()
                    if (e.key === 'Escape') { setShowNewPersona(false); setNewPersonaName('') }
                  }}
                  className="mb-2"
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={createPersona} disabled={!newPersonaName.trim()}>Create</Button>
                  <Button size="sm" variant="outline" onClick={() => { setShowNewPersona(false); setNewPersonaName('') }}>Cancel</Button>
                </div>
              </div>
            ) : (
              <button
                className="rounded-lg border border-dashed border-input p-4 min-w-[160px] flex flex-col items-center justify-center gap-1 text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
                onClick={() => setShowNewPersona(true)}
              >
                <Plus className="h-5 w-5" />
                <span className="text-sm">New Persona</span>
              </button>
            )}
          </div>
        </CardContent>
      </Card>

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
            How the agent refers to itself in conversation
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
            How assertively the agent opens conversations on its own
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
              {config.proactivity === 'off' && 'Halbert never starts a conversation on its own.'}
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

// ─────────────────────────────────────────────────────────────────────────────
// Senses Settings (Vision autonomy — being.yml senses.vision)
// ─────────────────────────────────────────────────────────────────────────────

function SensesSettings() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const resp = await fetch(`${API_BASE}/settings/being`)
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data.config)
      }
    } catch (e) {
      console.error('Failed to load senses config:', e)
    } finally {
      setLoading(false)
    }
  }

  const saveSenses = async (updates: Record<string, any>) => {
    setSaving(true)
    try {
      const current = config.senses?.vision || {}
      const newVision = { ...current, ...updates }
      const resp = await fetch(`${API_BASE}/settings/being`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ senses: { vision: newVision } }),
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
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Loading senses config...</CardContent></Card>
  }

  if (!config) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground">Failed to load config</CardContent></Card>
  }

  const vision = config.senses?.vision || {}

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Vision Autonomy
          </CardTitle>
          <CardDescription>
            Control how proactively the being uses screen capture. The system-level
            enable/disable gate is in the Vision tab — these settings control what the
            being is allowed to do with vision once it is enabled.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="vision-enabled">Enable proactive vision</Label>
              <p className="text-xs text-muted-foreground">
                Persona-level consent for autonomous screen monitoring.
              </p>
            </div>
            <input
              id="vision-enabled"
              type="checkbox"
              checked={vision.enabled ?? false}
              onChange={(e) => saveSenses({ enabled: e.target.checked })}
              disabled={saving}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="proactive-monitoring">Background monitoring</Label>
              <p className="text-xs text-muted-foreground">
                Periodically capture the active window and scan for error patterns.
              </p>
            </div>
            <input
              id="proactive-monitoring"
              type="checkbox"
              checked={vision.proactive_monitoring ?? false}
              onChange={(e) => saveSenses({ proactive_monitoring: e.target.checked })}
              disabled={saving}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="capture-on-intent">Auto-capture on visual intent</Label>
              <p className="text-xs text-muted-foreground">
                When you ask "what's on my screen", capture automatically before planning.
              </p>
            </div>
            <input
              id="capture-on-intent"
              type="checkbox"
              checked={vision.capture_on_intent ?? true}
              onChange={(e) => saveSenses({ capture_on_intent: e.target.checked })}
              disabled={saving}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="capture-on-error">Auto-capture on tool failure</Label>
              <p className="text-xs text-muted-foreground">
                OCR the screen when a command fails, for diagnostic context. Opt-in.
              </p>
            </div>
            <input
              id="capture-on-error"
              type="checkbox"
              checked={vision.capture_on_error ?? false}
              onChange={(e) => saveSenses({ capture_on_error: e.target.checked })}
              disabled={saving}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="vision-interval">Monitoring interval (seconds)</Label>
              <p className="text-xs text-muted-foreground">
                How often to check the screen when background monitoring is on. Min 10.
              </p>
            </div>
            <Input
              id="vision-interval"
              type="number"
              min={10}
              max={600}
              value={vision.interval_seconds ?? 60}
              onChange={(e) => saveSenses({ interval_seconds: parseInt(e.target.value) || 60 })}
              disabled={saving}
              className="w-24"
            />
          </div>
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

/** The Being tab's content: identity/voice settings plus vision autonomy. */
export function BeingTab() {
  return (
    <>
      <BeingSettings />
      <SensesSettings />
    </>
  )
}