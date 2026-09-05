// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Toast } from '@/components/ui/confirm-dialog'
import { apiUrl } from '@/lib/apiBase'
import { Eye, Shield } from 'lucide-react'

// ─────────────────────────────────────────────────────────────────────────────
// Vision Settings (Phase 5: Privacy gates + Settings UI)
// ─────────────────────────────────────────────────────────────────────────────

export function VisionTab() {
  const [config, setConfig] = useState<any>(null)
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  // R08-07: the blocklist textarea used to PUT the whole config on every
  // keystroke. Track the in-progress edit locally and commit on blur —
  // null means "show the saved config value," matching the
  // defaultValue+onBlur pattern BeingTab uses for its own free-text fields.
  const [blocklistDraft, setBlocklistDraft] = useState<string | null>(null)

  useEffect(() => {
    loadConfig()
    loadStatus()
  }, [])

  const loadConfig = async () => {
    try {
      const resp = await fetch(apiUrl('/api/vision/config'))
      if (resp.ok) {
        const data = await resp.json()
        setConfig(data)
      }
    } catch (err) {
      console.error('Failed to load vision config:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadStatus = async () => {
    try {
      const resp = await fetch(apiUrl('/api/vision/status'))
      if (resp.ok) {
        setStatus(await resp.json())
      }
    } catch (err) {
      console.error('Failed to load vision status:', err)
    }
  }

  const updateConfig = async (field: string, value: boolean | number | string[]) => {
    setSaving(true)
    try {
      const body: Record<string, any> = {}
      body[field] = value
      const resp = await fetch(apiUrl('/api/vision/config'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (resp.ok) {
        await loadConfig()
        setToast('Saved')
        setTimeout(() => setToast(null), 2000)
      }
    } catch (err) {
      console.error('Failed to update vision config:', err)
      setToast('Save failed')
      setTimeout(() => setToast(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  const testScreenshot = async () => {
    setToast('Capturing...')
    try {
      const resp = await fetch(apiUrl('/api/vision/screenshot'))
      if (resp.ok) {
        setToast('Screenshot captured successfully')
      } else {
        const err = await resp.json().catch(() => ({}))
        setToast(`Failed: ${err.error || resp.statusText}`)
      }
    } catch (err) {
      setToast(`Failed: ${err}`)
    }
    setTimeout(() => setToast(null), 4000)
  }

  const testWebcam = async () => {
    setToast('Capturing...')
    try {
      const resp = await fetch(apiUrl('/api/vision/webcam'))
      if (resp.ok) {
        setToast('Webcam frame captured successfully')
      } else {
        const err = await resp.json().catch(() => ({}))
        setToast(`Failed: ${err.error || resp.statusText}`)
      }
    } catch (err) {
      setToast(`Failed: ${err}`)
    }
    setTimeout(() => setToast(null), 4000)
  }

  if (loading) {
    return <div className="text-muted-foreground">Loading vision settings...</div>
  }

  const deps = status?.dependencies || {}
  const depsOk = deps.mss && deps.cv2 && deps.numpy

  return (
    <div className="space-y-4">
      {toast && (
        <Toast open={true} message={toast} onClose={() => setToast(null)} />
      )}

      {/* Dependency status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Vision Dependencies
          </CardTitle>
          <CardDescription>
            Required packages for screen and webcam capture
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <span className={deps.mss ? 'text-success' : 'text-destructive'}>
              {deps.mss ? '✓' : '✗'} mss
            </span>
            <span className={deps.cv2 ? 'text-success' : 'text-destructive'}>
              {deps.cv2 ? '✓' : '✗'} opencv-python
            </span>
            <span className={deps.numpy ? 'text-success' : 'text-destructive'}>
              {deps.numpy ? '✓' : '✗'} numpy
            </span>
          </div>
          {!depsOk && (
            <p className="text-sm text-muted-foreground">
              Install with: pip install mss opencv-python
            </p>
          )}
        </CardContent>
      </Card>

      {/* Screen Capture */}
      <Card>
        <CardHeader>
          <CardTitle>Screen Capture</CardTitle>
          <CardDescription>
            When enabled, Halbert can take screenshots of your display to answer
            questions about what's on screen.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="screen-enabled">Enable screen capture</Label>
            <input
              id="screen-enabled"
              type="checkbox"
              checked={config?.screen_capture?.enabled ?? false}
              onChange={(e) => updateConfig('screen_capture_enabled', e.target.checked)}
              disabled={saving}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="screen-quality">JPEG Quality</Label>
            <Input
              id="screen-quality"
              type="number"
              min={1}
              max={100}
              value={config?.screen_capture?.quality ?? 85}
              onChange={(e) => updateConfig('screen_capture_quality', parseInt(e.target.value) || 85)}
              disabled={saving}
              className="w-20"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="screen-maxdim">Max dimension (px)</Label>
            <Input
              id="screen-maxdim"
              type="number"
              min={256}
              max={4096}
              value={config?.screen_capture?.max_dimension ?? 1568}
              onChange={(e) => updateConfig('screen_capture_max_dim', parseInt(e.target.value) || 1568)}
              disabled={saving}
              className="w-24"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="screen-monitor">Monitor index</Label>
            <Input
              id="screen-monitor"
              type="number"
              min={0}
              max={9}
              value={config?.screen_capture?.monitor_index ?? 1}
              onChange={(e) => updateConfig('screen_capture_monitor_index', parseInt(e.target.value) || 1)}
              disabled={saving}
              className="w-20"
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="screen-gray">Grayscale</Label>
              <p className="text-xs text-muted-foreground">30% smaller JPEGs. Text and UI perfectly readable.</p>
            </div>
            <input
              id="screen-gray"
              type="checkbox"
              checked={config?.screen_capture?.grayscale ?? false}
              onChange={(e) => updateConfig('screen_capture_grayscale', e.target.checked)}
              disabled={saving}
            />
          </div>
          <Button onClick={testScreenshot} disabled={saving || !config?.screen_capture?.enabled} variant="outline" size="sm">
            Test screen capture
          </Button>
        </CardContent>
      </Card>

      {/* Webcam */}
      <Card>
        <CardHeader>
          <CardTitle>Webcam</CardTitle>
          <CardDescription>
            When enabled, Halbert can capture frames from your camera to look at
            physical objects, hardware, or labels. The camera LED will light briefly.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="webcam-enabled">Enable webcam access</Label>
            <input
              id="webcam-enabled"
              type="checkbox"
              checked={config?.webcam?.enabled ?? false}
              onChange={(e) => updateConfig('webcam_enabled', e.target.checked)}
              disabled={saving}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="webcam-camera">Camera index</Label>
            <Input
              id="webcam-camera"
              type="number"
              min={0}
              max={9}
              value={config?.webcam?.camera_index ?? 0}
              onChange={(e) => updateConfig('webcam_camera_index', parseInt(e.target.value) || 0)}
              disabled={saving}
              className="w-20"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="webcam-quality">JPEG Quality</Label>
            <Input
              id="webcam-quality"
              type="number"
              min={1}
              max={100}
              value={config?.webcam?.quality ?? 85}
              onChange={(e) => updateConfig('webcam_quality', parseInt(e.target.value) || 85)}
              disabled={saving}
              className="w-20"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="webcam-maxdim">Max dimension (px)</Label>
            <Input
              id="webcam-maxdim"
              type="number"
              min={256}
              max={4096}
              value={config?.webcam?.max_dimension ?? 768}
              onChange={(e) => updateConfig('webcam_max_dim', parseInt(e.target.value) || 768)}
              disabled={saving}
              className="w-24"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="webcam-grayscale">Grayscale (smaller, no color)</Label>
            <input
              id="webcam-grayscale"
              type="checkbox"
              checked={config?.webcam?.grayscale ?? false}
              onChange={(e) => updateConfig('webcam_grayscale', e.target.checked)}
              disabled={saving}
            />
          </div>
          <Button onClick={testWebcam} disabled={saving || !config?.webcam?.enabled} variant="outline" size="sm">
            Test webcam capture
          </Button>
        </CardContent>
      </Card>

      {/* Redaction */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Sensitive Content Redaction
          </CardTitle>
          <CardDescription>
            Blurs screen regions containing passwords, API keys, and tokens
            before sending to the LLM. Adds ~50-200ms OCR overhead per capture.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="redaction-enabled">Enable redaction</Label>
            <input
              id="redaction-enabled"
              type="checkbox"
              checked={config?.redaction?.enabled ?? false}
              onChange={(e) => updateConfig('redaction_enabled', e.target.checked)}
              disabled={saving}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="redaction-blocklist">Custom blocklist keywords (one per line, empty = use defaults)</Label>
            <textarea
              id="redaction-blocklist"
              className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder={"password\ntoken\napi_key\nsecret\n..."}
              value={blocklistDraft ?? (config?.redaction?.blocklist ?? []).join('\n')}
              onChange={(e) => setBlocklistDraft(e.target.value)}
              onBlur={() => {
                if (blocklistDraft === null) return
                const lines = blocklistDraft.split('\n').map((s: string) => s.trim()).filter(Boolean)
                updateConfig('redaction_blocklist', lines)
                setBlocklistDraft(null)
              }}
              disabled={saving}
            />
            <p className="text-xs text-muted-foreground">
              Default blocklist covers: password, secret, token, api_key, credential,
              SSH keys, PEM blocks, and regex patterns for AWS/GitHub/Slack/Stripe keys.
              Custom keywords are case-insensitive substring matches.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Privacy note */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Privacy
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            All capture is local. Frames are sent only to your configured vision
            model endpoint. If your vision model is a cloud API (not localhost),
            screenshots and webcam frames will be sent to that external service.
            Consider using a locally served vision model for privacy.
            Images are not stored to disk unless you explicitly save the conversation.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}