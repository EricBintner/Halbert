// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Onboarding Component (Phase 14: Self-Awareness)
 *
 * First-time setup wizard flow:
 * 1. Welcome - introduction; the machine quietly probes itself in the
 *    background while this screen is up
 * 2. Configure - ask for name, computer name, and what this computer is
 *    for (multi-select machine roles, pre-checked from the probe)
 * 3. Scanning - run deep system scan
 * 4. Scan Results - show what was discovered
 * 5. Complete - success message, then close
 */

import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Progress } from './ui/progress'
import { Badge } from './ui/badge'
import {
  Cpu,
  HardDrive,
  Network,
  Shield,
  Check,
  Loader2,
  Monitor,
  Server,
  Home as HomeIcon
} from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'
import { RestoreFromBackup } from './onboarding/RestoreFromBackup'

interface OnboardingProps {
  open: boolean
  onComplete: (roles: string[]) => void
}

interface ScanProgress {
  stage: string
  progress: number
  details?: string
}

interface ProbeSuggestion {
  roles: string[]
  scores: Record<string, number>
  reasons: string[]
  reasoning: string
}

interface ProbeResult {
  signals: Record<string, unknown>
  suggestion: ProbeSuggestion
}

// What this computer is for — multi-select, replacing the old four
// single-select "user type" cards (stored three places, read by none).
// UI labels come from the handoff's Q8 ruling: the API value is
// `home_automation_hub`, the chip says "Home Hub".
const machineRoles = [
  {
    id: 'workstation',
    label: 'Workstation',
    icon: Monitor,
    description: 'A computer someone sits at and uses day to day'
  },
  {
    id: 'server',
    label: 'Server',
    icon: Server,
    description: 'Headless, runs services for other machines'
  },
  {
    id: 'home_automation_hub',
    label: 'Home Hub',
    icon: HomeIcon,
    description: 'Runs home automation — Home Assistant, sensors, lights'
  },
]

const roleLabel = (id: string) =>
  machineRoles.find(r => r.id === id)?.label ?? id

export function Onboarding({ open, onComplete }: OnboardingProps) {
  const [step, setStep] = useState<'welcome' | 'configure' | 'scanning' | 'scan_results' | 'restore' | 'complete'>('welcome')
  const [computerName, setComputerName] = useState('')
  const [adminName, setAdminName] = useState('')
  const [suggestedName, setSuggestedName] = useState('')
  const [roles, setRoles] = useState<string[]>([])
  const [rolesTouched, setRolesTouched] = useState(false)
  const [notes, setNotes] = useState('')
  const [probe, setProbe] = useState<ProbeResult | null>(null)
  const [probePending, setProbePending] = useState(false)
  const [scanProgress, setScanProgress] = useState<ScanProgress>({ stage: '', progress: 0 })
  const [scanResult, setScanResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  // Fetch suggested name and run the quick probe while the welcome screen
  // is up — by the time the user reaches Configure the machine usually
  // already knows what it is.
  useEffect(() => {
    if (open && step === 'welcome') {
      fetch(apiUrl('/api/settings/onboarding/status'))
        .then(res => res.json())
        .then(data => {
          setSuggestedName(data.suggested_name || 'My Computer')
          setComputerName(data.suggested_name || '')
        })
        .catch(err => console.error('Failed to get onboarding status:', err))

      setProbePending(true)
      fetch(apiUrl('/api/settings/onboarding/probe'))
        .then(res => res.ok ? res.json() : null)
        .then((data: ProbeResult | null) => setProbe(data))
        .catch(err => console.warn('Role probe failed:', err))
        .finally(() => setProbePending(false))
    }
  }, [open, step])

  // Pre-check the suggested roles — only until the user touches the
  // toggles; their answer always wins over the inference.
  useEffect(() => {
    if (probe && !rolesTouched) {
      setRoles(probe.suggestion.roles)
    }
  }, [probe, rolesTouched])

  const toggleRole = (id: string) => {
    setRolesTouched(true)
    setRoles(prev =>
      prev.includes(id) ? prev.filter(r => r !== id) : [...prev, id]
    )
  }

  const startScanAndComplete = async () => {
    setStep('scanning')
    setError(null)

    // Simulate progress stages (actual scan is one API call)
    const stages = [
      { stage: 'Detecting OS and kernel...', progress: 10 },
      { stage: 'Scanning hardware (CPU, RAM, GPU)...', progress: 25 },
      { stage: 'Discovering network configuration...', progress: 40 },
      { stage: 'Analyzing storage and filesystems...', progress: 55 },
      { stage: 'Enumerating services...', progress: 70 },
      { stage: 'Checking security settings...', progress: 85 },
      { stage: 'Finalizing system profile...', progress: 95 },
    ]

    // Start showing progress
    let stageIndex = 0
    const progressInterval = setInterval(() => {
      if (stageIndex < stages.length) {
        setScanProgress(stages[stageIndex])
        stageIndex++
      }
    }, 800)

    try {
      // Complete onboarding with settings AND run scan in one call
      const response = await fetch(apiUrl('/api/settings/onboarding/complete'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          computer_name: computerName || suggestedName,
          admin_name: adminName || 'Admin',
          roles: roles.length ? roles : ['workstation'],
          notes: notes.trim() || undefined,
        }),
      })

      clearInterval(progressInterval)

      if (!response.ok) {
        throw new Error('Setup failed')
      }

      const result = await response.json()
      setScanResult(result)
      setScanProgress({ stage: 'Complete!', progress: 100 })

      // Move to scan_results step after a brief pause
      setTimeout(() => setStep('scan_results'), 1000)

    } catch (err) {
      clearInterval(progressInterval)
      setError('Failed to complete setup. Please try again.')
      setStep('configure')
    }
  }


  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-[600px]">

        {/* Welcome Step */}
        {step === 'welcome' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">Welcome to Halbert</DialogTitle>
              <DialogDescription className="text-base">
                Let me introduce myself. This will only take a moment.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-3 p-3 border rounded-lg">
                  <Cpu className="h-8 w-8 text-primary" />
                  <div>
                    <p className="font-medium">Hardware Detection</p>
                    <p className="text-sm text-muted-foreground">CPU, RAM, GPU</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 border rounded-lg">
                  <HardDrive className="h-8 w-8 text-primary" />
                  <div>
                    <p className="font-medium">Storage Analysis</p>
                    <p className="text-sm text-muted-foreground">Disks, filesystems</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 border rounded-lg">
                  <Network className="h-8 w-8 text-primary" />
                  <div>
                    <p className="font-medium">Network Config</p>
                    <p className="text-sm text-muted-foreground">Interfaces, DNS</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 border rounded-lg">
                  <Shield className="h-8 w-8 text-primary" />
                  <div>
                    <p className="font-medium">Security Status</p>
                    <p className="text-sm text-muted-foreground">Firewall, updates</p>
                  </div>
                </div>
              </div>

              <p className="text-sm text-muted-foreground text-center">
                This scan takes about 30-60 seconds and runs entirely on your machine.
              </p>

              {error && (
                <p className="text-sm text-destructive text-center">{error}</p>
              )}

              <Button onClick={() => setStep('configure')} className="w-full" size="lg">
                Get Started
              </Button>

              {/* Recovery door (Phase 2.7): a machine that used to be an
                  entity skips the tour — it restores its backup. */}
              <Button
                variant="link"
                className="w-full text-muted-foreground"
                onClick={() => setStep('restore')}
              >
                Restore from a backup instead
              </Button>
            </div>
          </>
        )}

        {/* Restore Step — the State Vault's onboarding door */}
        {step === 'restore' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">Restore from Backup</DialogTitle>
              <DialogDescription className="text-base">
                Point me at a vault archive and this machine becomes that
                entity again.
              </DialogDescription>
            </DialogHeader>

            <RestoreFromBackup
              onRestored={async () => {
                try {
                  await fetch(apiUrl('/api/settings/onboarding/complete'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      computer_name: computerName || suggestedName,
                      admin_name: adminName || 'Admin',
                      roles: roles.length ? roles : ['workstation'],
                    }),
                  })
                } catch (e) {
                  console.error('onboarding completion after restore failed:', e)
                }
                onComplete(roles.length ? roles : ['workstation'])
              }}
            />

            <Button variant="ghost" className="w-full" onClick={() => setStep('welcome')}>
              Back
            </Button>
          </>
        )}

        {/* Scanning Step */}
        {step === 'scanning' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">Scanning Your System</DialogTitle>
              <DialogDescription className="text-base">
                Discovering everything about this machine...
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-8">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <span className="text-sm font-medium">{scanProgress.stage}</span>
                </div>
                <Progress value={scanProgress.progress} className="h-2" />
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-sm text-muted-foreground">
                <div className={scanProgress.progress >= 25 ? 'text-primary' : ''}>
                  <Check className={`h-4 w-4 mx-auto mb-1 ${scanProgress.progress >= 25 ? 'text-green-500' : ''}`} />
                  Hardware
                </div>
                <div className={scanProgress.progress >= 55 ? 'text-primary' : ''}>
                  <Check className={`h-4 w-4 mx-auto mb-1 ${scanProgress.progress >= 55 ? 'text-green-500' : ''}`} />
                  Storage
                </div>
                <div className={scanProgress.progress >= 85 ? 'text-primary' : ''}>
                  <Check className={`h-4 w-4 mx-auto mb-1 ${scanProgress.progress >= 85 ? 'text-green-500' : ''}`} />
                  Services
                </div>
              </div>
            </div>
          </>
        )}

        {/* Configure Step */}
        {step === 'configure' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">Personalize Your Experience</DialogTitle>
              <DialogDescription className="text-base">
                A few quick settings to get started.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5 py-4">
              {/* Admin Name */}
              <div className="space-y-2">
                <Label htmlFor="admin-name">What's your name?</Label>
                <Input
                  id="admin-name"
                  value={adminName}
                  onChange={(e) => setAdminName(e.target.value)}
                  placeholder="Your name"
                />
                <p className="text-xs text-muted-foreground">
                  The AI will address you by this name
                </p>
              </div>

              {/* Computer Name */}
              <div className="space-y-2">
                <Label htmlFor="computer-name">What should I call this computer?</Label>
                <Input
                  id="computer-name"
                  value={computerName}
                  onChange={(e) => setComputerName(e.target.value)}
                  placeholder={suggestedName}
                />
                <p className="text-xs text-muted-foreground">
                  This is how the computer refers to itself ("I am {computerName || suggestedName}")
                </p>
              </div>

              {/* Machine roles — multi-select, suggested by the probe */}
              <div className="space-y-2">
                <Label>What is this computer for?</Label>
                <div className="grid grid-cols-3 gap-2">
                  {machineRoles.map((role) => (
                    <button
                      key={role.id}
                      onClick={() => toggleRole(role.id)}
                      className={`flex flex-col items-start gap-1 p-3 border rounded-lg text-left transition-colors ${
                        roles.includes(role.id)
                          ? 'border-primary bg-primary/5'
                          : 'hover:border-primary/50'
                      }`}
                    >
                      <role.icon className={`h-5 w-5 ${roles.includes(role.id) ? 'text-primary' : 'text-muted-foreground'}`} />
                      <p className="font-medium text-sm">{role.label}</p>
                      <p className="text-xs text-muted-foreground">{role.description}</p>
                    </button>
                  ))}
                </div>
                {probePending && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Taking a quick look at this machine…
                  </p>
                )}
                {!probePending && probe?.suggestion.reasoning && (
                  <p className="text-xs text-muted-foreground">
                    {probe.suggestion.reasoning}
                  </p>
                )}
                {roles.length === 0 && !probePending && (
                  <p className="text-xs text-muted-foreground">
                    Pick at least one — more than one is fine.
                  </p>
                )}
              </div>

              {/* Optional free-text — becomes the machine's purpose, which
                  the prompt already renders. */}
              <div className="space-y-2">
                <Label htmlFor="machine-notes">Anything else I should know about this machine? <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Input
                  id="machine-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. it also serves media to the house"
                />
              </div>

              {error && (
                <p className="text-sm text-destructive text-center">{error}</p>
              )}

              <Button
                onClick={startScanAndComplete}
                className="w-full"
                size="lg"
                disabled={roles.length === 0}
              >
                Scan System & Complete Setup
              </Button>
            </div>
          </>
        )}

        {/* Scan Results Step */}
        {step === 'scan_results' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">System Detected!</DialogTitle>
              <DialogDescription className="text-base">
                Here's what I learned about {computerName || suggestedName}.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {scanResult && (
                <div className="p-4 bg-muted rounded-lg text-sm">
                  <pre className="text-xs whitespace-pre-wrap text-muted-foreground max-h-64 overflow-auto font-mono">
                    {scanResult.profile_summary || scanResult.summary || 'System profile created successfully.'}
                  </pre>
                </div>
              )}

              <Button onClick={() => { setStep('complete'); setTimeout(() => onComplete(roles), 2000) }} className="w-full" size="lg">
                Finish Setup
              </Button>
            </div>
          </>
        )}

        {/* Complete Step */}
        {step === 'complete' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl text-center">You're All Set!</DialogTitle>
            </DialogHeader>

            <div className="py-8 text-center space-y-4">
              <div className="mx-auto w-16 h-16 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center">
                <Check className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <p className="text-muted-foreground">
                {computerName || suggestedName} is ready.
              </p>
              <div className="flex justify-center gap-1.5">
                {roles.map(r => (
                  <Badge key={r} variant="secondary">{roleLabel(r)}</Badge>
                ))}
              </div>
            </div>
          </>
        )}

      </DialogContent>
    </Dialog>
  )
}
