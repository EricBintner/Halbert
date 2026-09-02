// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Audio settings tab — mirrors VisionSettings pattern.

import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { apiUrl } from '@/lib/apiBase'
import type { SpeakerStatus } from '@/components/voice/SpeakerBadge'
import { AudioLines, Mic, Volume2, Shield, AlertTriangle, Music, Loader2, Moon } from 'lucide-react'

interface AudioConfig {
  enabled: boolean
  local_mic: { enabled: boolean; device_index: number; sample_rate: number; aec_enabled: boolean }
  wyoming_ingress: { enabled: boolean; host: string; port: number }
  acoustic_events: { enabled: boolean; energy_floor_db: number; check_interval_s: number }
  speaker_id: { enabled: boolean; threshold: number }
  tts: { enabled: boolean; voice_model: string }
  privacy: {
    delete_raw_after_transcription: boolean
    ignore_tv_media: boolean
    quiet_hours: { start: string; end: string } | null
  }
}

interface AudioStatus {
  enabled: boolean
  available: boolean
  sherpa_onnx_installed: boolean
  state: string
  /** Last identified speaker (O4) — null until a speech turn has run;
   * absent on the static fallback payload (no coordinator). */
  speaker?: SpeakerStatus | null
  engines: {
    vad: boolean
    asr: boolean
    tts: boolean
    speaker_id: boolean
    audio_tagger: boolean
  }
}

export function AudioSettings() {
  const [config, setConfig] = useState<AudioConfig | null>(null)
  const [status, setStatus] = useState<AudioStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [quietHours, setQuietHours] = useState<{ start: string; end: string } | null>(null)

  const loadConfig = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/audio/config'))
      if (resp.ok) setConfig(await resp.json())
    } catch (err) {
      console.error('Failed to load audio config:', err)
    }
  }, [])

  const loadStatus = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/audio/status'))
      if (resp.ok) setStatus(await resp.json())
    } catch (err) {
      console.error('Failed to load audio status:', err)
    }
  }, [])

  const loadQuietHours = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/settings/being'))
      if (resp.ok) {
        const data = await resp.json()
        const cfg = data.config || data
        setQuietHours(cfg.quiet_hours ?? null)
      }
    } catch (err) {
      console.error('Failed to load being config:', err)
    }
  }, [])

  useEffect(() => {
    Promise.all([loadConfig(), loadStatus(), loadQuietHours()]).finally(() => setLoading(false))
  }, [loadConfig, loadStatus, loadQuietHours])

  const updateConfig = async (patch: Partial<AudioConfig> & Record<string, any>) => {
    setSaving(true)
    try {
      await fetch(apiUrl('/api/audio/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      await loadConfig()
      await loadStatus()
    } catch (err) {
      console.error('Failed to update audio config:', err)
    } finally {
      setSaving(false)
    }
  }

  const updateQuietHours = async (value: { start: string; end: string } | null) => {
    setSaving(true)
    try {
      await fetch(apiUrl('/api/settings/being'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quiet_hours: value }),
      })
      await loadQuietHours()
    } catch (err) {
      console.error('Failed to update quiet hours:', err)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-muted-foreground">Loading audio settings...</div>
  }

  if (!config) {
    return <div className="text-muted-foreground">Failed to load audio configuration.</div>
  }

  return (
    <div className="space-y-4">
      {/* Dependencies status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AudioLines className="h-5 w-5" />
            Audio Dependencies
          </CardTitle>
          <CardDescription>
            The audio subsystem uses sherpa-onnx for all inference (zero PyTorch).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm">sherpa-onnx</span>
            <Badge variant={status?.sherpa_onnx_installed ? 'default' : 'destructive'}>
              {status?.sherpa_onnx_installed ? 'Installed' : 'Not installed'}
            </Badge>
          </div>
          {!status?.sherpa_onnx_installed && (
            <p className="text-xs text-muted-foreground">
              Install with: pip install halbert-core[audio-inference]
            </p>
          )}
        </CardContent>
      </Card>

      {/* Master switch */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            Audio Subsystem
          </CardTitle>
          <CardDescription>
            Master switch for audio. All audio features are OFF by default and
            must be explicitly enabled.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <Label htmlFor="audio-enabled">Enable audio subsystem</Label>
            <Switch
              id="audio-enabled"
              checked={config.enabled}
              onCheckedChange={(v) => updateConfig({ enabled: v })}
              disabled={saving}
            />
          </div>
        </CardContent>
      </Card>

      {/* Local microphone */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            Local Microphone
          </CardTitle>
          <CardDescription>
            Host built-in microphone capture via Rust cpal. Audio is sent to the
            Python backend via a loopback TCP socket (not Tauri IPC).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="mic-enabled">Enable local microphone</Label>
            <Switch
              id="mic-enabled"
              checked={config.local_mic.enabled}
              onCheckedChange={(v) => updateConfig({ local_mic_enabled: v })}
              disabled={saving || !config.enabled}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="aec-enabled">
              Acoustic Echo Cancellation (AEC)
              <span className="text-xs text-muted-foreground ml-2">
                Required for desktop duplex
              </span>
            </Label>
            <Switch
              id="aec-enabled"
              checked={config.local_mic.aec_enabled}
              onCheckedChange={() => {}}
              disabled={!config.local_mic.enabled}
            />
          </div>
        </CardContent>
      </Card>

      {/* Wyoming ingress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Volume2 className="h-5 w-5" />
            Wyoming TCP Satellites
          </CardTitle>
          <CardDescription>
            Accept audio from ESP32 / Pi satellites via the Wyoming protocol
            (binary framing on TCP port 10400).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="wyoming-enabled">Enable Wyoming ingress</Label>
            <Switch
              id="wyoming-enabled"
              checked={config.wyoming_ingress.enabled}
              onCheckedChange={(v) => updateConfig({ wyoming_ingress_enabled: v })}
              disabled={saving || !config.enabled}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="wyoming-host">Listen host</Label>
              <Input
                id="wyoming-host"
                value={config.wyoming_ingress.host}
                readOnly
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="wyoming-port">Listen port</Label>
              <Input
                id="wyoming-port"
                type="number"
                value={config.wyoming_ingress.port}
                onChange={(e) => updateConfig({ wyoming_ingress_port: parseInt(e.target.value) || 10400 })}
                disabled={saving}
                className="mt-1"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Speaker ID */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Speaker Identification
          </CardTitle>
          <CardDescription>
            Biometric speaker identification using CAM++ 256-dim embeddings.
            Enrolled speakers are assigned roles that gate tool access.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="speaker-id-enabled">Enable speaker identification</Label>
            <Switch
              id="speaker-id-enabled"
              checked={config.speaker_id.enabled}
              onCheckedChange={(v) => updateConfig({ speaker_id_enabled: v })}
              disabled={saving || !config.enabled}
            />
          </div>
          <div>
            <Label htmlFor="speaker-threshold">
              Verification threshold: {config.speaker_id.threshold.toFixed(2)}
            </Label>
            <Input
              id="speaker-threshold"
              type="number"
              step="0.05"
              min="0.5"
              max="0.95"
              value={config.speaker_id.threshold}
              onChange={(e) => updateConfig({ speaker_id_threshold: parseFloat(e.target.value) || 0.75 })}
              disabled={saving}
              className="mt-1"
            />
          </div>
        </CardContent>
      </Card>

      {/* Acoustic events */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Acoustic Event Detection
          </CardTitle>
          <CardDescription>
            Ambient sound classification using CED-tiny. Detects smoke alarms,
            glass breaks, water leaks, and mechanical anomalies.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <Label htmlFor="acoustic-enabled">Enable acoustic event detection</Label>
            <Switch
              id="acoustic-enabled"
              checked={config.acoustic_events.enabled}
              onCheckedChange={(v) => updateConfig({ acoustic_events_enabled: v })}
              disabled={saving || !config.enabled}
            />
          </div>
        </CardContent>
      </Card>

      {/* TTS */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Volume2 className="h-5 w-5" />
            Text-to-Speech (Piper)
          </CardTitle>
          <CardDescription>
            Neural TTS via Piper VITS models (OHF-Voice/piper1-gpl fork).
            Runs entirely on CPU via ONNX Runtime.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="tts-enabled">Enable text-to-speech</Label>
            <Switch
              id="tts-enabled"
              checked={config.tts.enabled}
              onCheckedChange={(v) => updateConfig({ tts_enabled: v })}
              disabled={saving || !config.enabled}
            />
          </div>
          <div>
            <Label htmlFor="tts-voice">Voice model path</Label>
            <Input
              id="tts-voice"
              value={config.tts.voice_model}
              placeholder="/path/to/en_US-amy-medium.onnx"
              onChange={(e) => updateConfig({ tts_voice_model: e.target.value })}
              disabled={saving}
              className="mt-1"
            />
          </div>
        </CardContent>
      </Card>

      {/* Privacy */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Acoustic Privacy
          </CardTitle>
          <CardDescription>
            Privacy controls for audio capture. Raw audio is never stored to
            disk unless explicitly enabled.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="delete-raw">Delete raw audio after transcription</Label>
            <Switch
              id="delete-raw"
              checked={config.privacy.delete_raw_after_transcription}
              onCheckedChange={(v) => updateConfig({ privacy_delete_raw_after_transcription: v })}
              disabled={saving}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="ignore-tv">Ignore background TV/media speech</Label>
            <Switch
              id="ignore-tv"
              checked={config.privacy.ignore_tv_media}
              onCheckedChange={(v) => updateConfig({ privacy_ignore_tv_media: v })}
              disabled={saving}
            />
          </div>
        </CardContent>
      </Card>

      {/* Quiet hours */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Moon className="h-5 w-5" />
            Quiet Hours
          </CardTitle>
          <CardDescription>
            Suppress proactive speech and alerts during quiet hours. The
            modality-voice engine enforces this for voice delivery; the
            proactive gate uses it for alert suppression. Life-safety events
            (smoke, gas, CO) always bypass quiet hours.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="quiet-enabled">Enable quiet hours</Label>
            <Switch
              id="quiet-enabled"
              checked={quietHours !== null}
              onCheckedChange={(v) => {
                if (v) {
                  updateQuietHours({ start: '22:00', end: '07:00' })
                } else {
                  updateQuietHours(null)
                }
              }}
              disabled={saving}
            />
          </div>
          {quietHours && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="quiet-start">Start time</Label>
                <Input
                  id="quiet-start"
                  type="time"
                  value={quietHours.start}
                  onChange={(e) => setQuietHours({ ...quietHours, start: e.target.value })}
                  onBlur={() => quietHours && updateQuietHours(quietHours)}
                  disabled={saving}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="quiet-end">End time</Label>
                <Input
                  id="quiet-end"
                  type="time"
                  value={quietHours.end}
                  onChange={(e) => setQuietHours({ ...quietHours, end: e.target.value })}
                  onBlur={() => quietHours && updateQuietHours(quietHours)}
                  disabled={saving}
                  className="mt-1"
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Music recognition note */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Music className="h-5 w-5" />
            Music Recognition
          </CardTitle>
          <CardDescription>
            Ambient music fingerprinting via Chromaprint / AcoustID.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Music identification requires network access for the AcoustID API
            lookup. Offline (no network): fingerprints are generated but song
            names are not resolved.
          </p>
        </CardContent>
      </Card>

      {saving && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Saving...
        </div>
      )}
    </div>
  )
}
