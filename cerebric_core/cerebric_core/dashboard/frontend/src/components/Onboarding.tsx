/**
 * Onboarding Component (Phase 14: Self-Awareness)
 * 
 * First-time setup wizard flow:
 * 1. Welcome - introduction
 * 2. Configure - ask for name, computer name, user type
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
  Settings, 
  Check,
  Loader2,
  User,
  Briefcase,
  Brain
} from 'lucide-react'

interface OnboardingProps {
  open: boolean
  onComplete: () => void
}

interface ScanProgress {
  stage: string
  progress: number
  details?: string
}

const userTypes = [
  { 
    id: 'casual', 
    label: 'Casual User', 
    icon: User, 
    description: 'Home user, general computing' 
  },
  { 
    id: 'it_admin', 
    label: 'IT Admin', 
    icon: Briefcase, 
    description: 'System administration, servers' 
  },
  { 
    id: 'developer', 
    label: 'Developer', 
    icon: Settings, 
    description: 'Software development, DevOps' 
  },
  { 
    id: 'ai_professional', 
    label: 'AI Professional', 
    icon: Brain, 
    description: 'Machine learning, data science' 
  },
]

export function Onboarding({ open, onComplete }: OnboardingProps) {
  const [step, setStep] = useState<'welcome' | 'configure' | 'scanning' | 'scan_results' | 'complete'>('welcome')
  const [computerName, setComputerName] = useState('')
  const [adminName, setAdminName] = useState('')
  const [suggestedName, setSuggestedName] = useState('')
  const [userType, setUserType] = useState('casual')
  const [scanProgress, setScanProgress] = useState<ScanProgress>({ stage: '', progress: 0 })
  const [scanResult, setScanResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  // Fetch suggested name on mount
  useEffect(() => {
    if (open && step === 'welcome') {
      fetch('/api/settings/onboarding/status')
        .then(res => res.json())
        .then(data => {
          setSuggestedName(data.suggested_name || 'My Computer')
          setComputerName(data.suggested_name || '')
        })
        .catch(err => console.error('Failed to get onboarding status:', err))
    }
  }, [open, step])

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
      const response = await fetch('/api/settings/onboarding/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          computer_name: computerName || suggestedName,
          admin_name: adminName || 'Admin',
          user_type: userType,
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
              <DialogTitle className="text-2xl">Welcome to Cerebric</DialogTitle>
              <DialogDescription className="text-base">
                Let's set up your AI-powered Linux assistant. This will only take a moment.
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
            </div>
          </>
        )}
        
        {/* Scanning Step */}
        {step === 'scanning' && (
          <>
            <DialogHeader>
              <DialogTitle className="text-2xl">Scanning Your System</DialogTitle>
              <DialogDescription className="text-base">
                Discovering everything about your Linux setup...
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
              
              {/* User Type */}
              <div className="space-y-2">
                <Label>How do you primarily use this computer?</Label>
                <div className="grid grid-cols-2 gap-2">
                  {userTypes.map((type) => (
                    <button
                      key={type.id}
                      onClick={() => setUserType(type.id)}
                      className={`flex items-center gap-3 p-3 border rounded-lg text-left transition-colors ${
                        userType === type.id 
                          ? 'border-primary bg-primary/5' 
                          : 'hover:border-primary/50'
                      }`}
                    >
                      <type.icon className={`h-5 w-5 ${userType === type.id ? 'text-primary' : 'text-muted-foreground'}`} />
                      <div>
                        <p className="font-medium text-sm">{type.label}</p>
                        <p className="text-xs text-muted-foreground">{type.description}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              
              {error && (
                <p className="text-sm text-destructive text-center">{error}</p>
              )}
              
              <Button onClick={startScanAndComplete} className="w-full" size="lg">
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
              
              <Button onClick={() => { setStep('complete'); setTimeout(() => onComplete(), 2000) }} className="w-full" size="lg">
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
                {computerName || suggestedName} is ready to help you manage your Linux system.
              </p>
              <Badge variant="secondary">{userTypes.find(t => t.id === userType)?.label}</Badge>
            </div>
          </>
        )}
        
      </DialogContent>
    </Dialog>
  )
}
