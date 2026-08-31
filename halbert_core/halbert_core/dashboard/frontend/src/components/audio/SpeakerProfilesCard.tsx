// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Speaker profiles card — lists enrolled voiceprints with role management.

import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { apiUrl } from '@/lib/apiBase'
import { User, Plus, Trash2, Mic, Loader2, AlertCircle } from 'lucide-react'

interface Speaker {
  speaker_id: string
  name: string
  role: string
  sample_count: number
  threshold: number
  embedding_dim: number
  created_at: number
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  member: 'Member',
  guest: 'Guest',
  restricted: 'Restricted',
}

const ROLE_DESCRIPTIONS: Record<string, string> = {
  admin: 'Full system access (ZFS, SSH, deadbolts, alarms)',
  member: 'Standard home access (lights, thermostat, media)',
  guest: 'Advisory queries and safe lighting only',
  restricted: 'Read-only info. PIN required for privileged actions.',
}

export function SpeakerProfilesCard({ onEnroll }: { onEnroll?: () => void }) {
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{
    [id: string]: { matched: boolean; score: number; threshold: number }
  }>({})
  const [testError, setTestError] = useState<string | null>(null)
  const [sherpaInstalled, setSherpaInstalled] = useState<boolean | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)

  const loadSpeakers = useCallback(async () => {
    try {
      const [speakerResp, statusResp] = await Promise.all([
        fetch(apiUrl('/api/audio/speakers')),
        fetch(apiUrl('/api/audio/status')),
      ])
      if (speakerResp.ok) {
        const data = await speakerResp.json()
        setSpeakers(data.speakers || [])
      }
      if (statusResp.ok) {
        const status = await statusResp.json()
        setSherpaInstalled(status.sherpa_onnx_installed ?? false)
      }
    } catch (err) {
      console.error('Failed to load speakers:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSpeakers()
  }, [loadSpeakers])

  const deleteSpeaker = async (id: string) => {
    if (!confirm('Delete this speaker profile? This cannot be undone.')) return
    try {
      await fetch(apiUrl(`/api/audio/speakers/${id}`), { method: 'DELETE' })
      await loadSpeakers()
    } catch (err) {
      console.error('Failed to delete speaker:', err)
    }
  }

  const testSpeaker = async (id: string) => {
    setTesting(id)
    setTestError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks, { type: 'audio/webm' })
        const reader = new FileReader()
        reader.onloadend = async () => {
          const base64 = (reader.result as string).split(',')[1]
          try {
            const resp = await fetch(apiUrl(`/api/audio/speakers/${id}/test`), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ audio_base64: base64 }),
            })
            if (resp.status === 503) {
              setTestError('Speaker verification unavailable (sherpa-onnx not installed)')
              setTesting(null)
              return
            }
            if (resp.ok) {
              const data = await resp.json()
              setTestResult({
                ...testResult,
                [id]: {
                  matched: data.matched,
                  score: data.score,
                  threshold: data.threshold,
                },
              })
            } else {
              const err = await resp.json().catch(() => ({}))
              setTestError(err.detail || 'Verification failed')
            }
          } catch (err) {
            setTestError('Network error: ' + String(err))
          }
          setTesting(null)
        }
        reader.readAsDataURL(blob)
      }
      mediaRecorderRef.current = recorder
      recorder.start()
      // Capture 2 seconds of audio
      setTimeout(() => {
        if (recorder.state === 'recording') recorder.stop()
      }, 2000)
    } catch (err) {
      setTestError('Microphone access denied. Please allow microphone access.')
      setTesting(null)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading speaker profiles...
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <User className="h-5 w-5" />
          Household Voice Biometrics
        </CardTitle>
        <CardDescription>
          Enrolled speaker voiceprints and permission gates. Speaker roles
          control which tools the agent can execute on voice commands.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {speakers.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Mic className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No speakers enrolled yet.</p>
            <p className="text-xs mt-1">
              Enroll household members to enable role-based voice commands.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {speakers.map((speaker) => (
              <div
                key={speaker.speaker_id}
                className="flex items-center justify-between p-3 rounded-lg border"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{speaker.name}</span>
                    <Badge variant="outline">{ROLE_LABELS[speaker.role] || speaker.role}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {ROLE_DESCRIPTIONS[speaker.role] || ''}
                  </p>
                  {testResult[speaker.speaker_id] && (
                    <p className="text-xs">
                      Match: {testResult[speaker.speaker_id].matched ? 'Yes' : 'No'}
                      {' '}({(testResult[speaker.speaker_id].score * 100).toFixed(0)}%)
                      {' — threshold '}
                      {(testResult[speaker.speaker_id].threshold * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => testSpeaker(speaker.speaker_id)}
                    disabled={testing === speaker.speaker_id}
                    title={sherpaInstalled === false
                      ? 'sherpa-onnx not installed — speaker verification unavailable'
                      : 'Capture 2s of audio and verify against this voiceprint'}
                  >
                    {testing === speaker.speaker_id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      'Test'
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => deleteSpeaker(speaker.speaker_id)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        <Button onClick={onEnroll} className="w-full" variant="outline">
          <Plus className="h-4 w-4 mr-2" />
          Enroll New Household Voice
        </Button>

        {testError && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            {testError}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
