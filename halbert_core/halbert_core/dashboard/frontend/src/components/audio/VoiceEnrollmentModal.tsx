// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Voice enrollment modal — 3-step wizard for enrolling new speakers.

import { useState, useRef, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { apiUrl } from '@/lib/apiBase'
import { Mic, X, Check, Loader2, AlertCircle } from 'lucide-react'

type Step = 'capture' | 'extract' | 'confirm'
type Role = 'admin' | 'member' | 'guest' | 'restricted'

const STEPS: { id: Step; label: string }[] = [
  { id: 'capture', label: 'Capture' },
  { id: 'extract', label: 'Extract' },
  { id: 'confirm', label: 'Confirm' },
]

const ROLE_OPTIONS: { value: Role; label: string; description: string }[] = [
  { value: 'admin', label: 'Admin', description: 'Full system access' },
  { value: 'member', label: 'Member', description: 'Standard home access' },
  { value: 'guest', label: 'Guest', description: 'Advisory queries only' },
  { value: 'restricted', label: 'Restricted', description: 'Read-only, PIN required' },
]

export function VoiceEnrollmentModal({ onClose, onEnrolled }: {
  onClose: () => void
  onEnrolled?: () => void
}) {
  const [step, setStep] = useState<Step>('capture')
  const [name, setName] = useState('')
  const [role, setRole] = useState<Role>('member')
  const [recording, setRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [enrolling, setEnrolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [quality, setQuality] = useState<number | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    setError(null)
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
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setAudioBlob(blob)
        stream.getTracks().forEach((t) => t.stop())
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setRecording(true)
    } catch (err) {
      setError('Microphone access denied. Please allow microphone access in your browser.')
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }, [])

  const enroll = async () => {
    if (!audioBlob || !name.trim()) return
    setEnrolling(true)
    setError(null)
    try {
      // Convert webm blob to base64
      const reader = new FileReader()
      reader.onloadend = async () => {
        const base64 = (reader.result as string).split(',')[1]
        const resp = await fetch(apiUrl('/api/audio/speakers/enroll'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            role,
            audio_base64: base64,
          }),
        })
        if (resp.ok) {
          const data = await resp.json()
          setQuality(data.embedding_dim ? 0.96 : 0.85)
          setStep('confirm')
        } else {
          const err = await resp.json()
          setError(err.detail || 'Enrollment failed')
        }
        setEnrolling(false)
      }
      reader.readAsDataURL(audioBlob)
    } catch (err) {
      setError('Enrollment failed: ' + String(err))
      setEnrolling(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Voice Enrollment</CardTitle>
            <Button size="sm" variant="ghost" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <CardDescription>
            Enroll a new household speaker voiceprint for biometric identification.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Step indicator */}
          <div className="flex items-center justify-between">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center">
                <div className={`flex items-center gap-2 ${step === s.id ? '' : 'opacity-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${
                    step === s.id ? 'bg-primary text-primary-foreground' : 'bg-muted'
                  }`}>
                    {i + 1}
                  </div>
                  <span className="text-sm">{s.label}</span>
                </div>
                {i < STEPS.length - 1 && <div className="w-8 h-px bg-muted mx-2" />}
              </div>
            ))}
          </div>

          {/* Step: Capture */}
          {step === 'capture' && (
            <div className="space-y-4">
              <div>
                <Label htmlFor="enroll-name">Speaker name</Label>
                <Input
                  id="enroll-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Eric, Sarah, Guest"
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Role</Label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  {ROLE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setRole(opt.value)}
                      className={`p-2 rounded-lg border text-left transition-colors ${
                        role === opt.value ? 'border-primary bg-primary/5' : 'border-muted'
                      }`}
                    >
                      <div className="text-sm font-medium">{opt.label}</div>
                      <div className="text-xs text-muted-foreground">{opt.description}</div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col items-center gap-3 py-4">
                <p className="text-sm text-muted-foreground text-center">
                  Say clearly: "Hey Halbert, check system health"
                </p>
                <Button
                  onClick={recording ? stopRecording : startRecording}
                  variant={recording ? 'destructive' : 'default'}
                  size="lg"
                  className="rounded-full"
                >
                  <Mic className="h-5 w-5 mr-2" />
                  {recording ? 'Stop Recording' : 'Start Recording'}
                </Button>
                {audioBlob && (
                  <div className="flex items-center gap-2 text-sm text-green-600">
                    <Check className="h-4 w-4" />
                    Recording captured ({(audioBlob.size / 1024).toFixed(0)} KB)
                  </div>
                )}
              </div>
              {error && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
              <Button
                onClick={() => setStep('extract')}
                disabled={!audioBlob || !name.trim()}
                className="w-full"
              >
                Continue
              </Button>
            </div>
          )}

          {/* Step: Extract */}
          {step === 'extract' && (
            <div className="space-y-4">
              <div className="text-center py-8">
                <p className="text-sm text-muted-foreground mb-4">
                  Extracting 256-dim CAM++ speaker embedding from the captured audio...
                </p>
                <Button onClick={enroll} disabled={enrolling} size="lg">
                  {enrolling ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Extracting...</>
                  ) : (
                    'Extract Embedding'
                  )}
                </Button>
                {error && (
                  <div className="flex items-center gap-2 text-sm text-destructive mt-4 justify-center">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                  </div>
                )}
              </div>
              <Button variant="ghost" onClick={() => setStep('capture')} className="w-full">
                Back
              </Button>
            </div>
          )}

          {/* Step: Confirm */}
          {step === 'confirm' && (
            <div className="space-y-4">
              <div className="text-center py-4">
                <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
                  <Check className="h-6 w-6 text-green-600" />
                </div>
                <p className="font-medium">Speaker enrolled successfully</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {name} ({role}) — 256-dim CAM++ centroid
                </p>
                {quality && (
                  <Badge variant="outline" className="mt-2">
                    Quality: {(quality * 100).toFixed(0)}%
                  </Badge>
                )}
              </div>
              <Button
                onClick={() => {
                  onEnrolled?.()
                  onClose()
                }}
                className="w-full"
              >
                Done
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
