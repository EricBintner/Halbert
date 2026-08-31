// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useEffect, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Terminal } from './pages/Terminal'
import { Services } from './pages/Services'
import { Storage } from './pages/Storage'
import { GPU } from './pages/GPU'
import { Containers } from './pages/Containers'
import { Development } from './pages/Development'
import { Network } from './pages/Network'
import { Sharing } from './pages/Sharing'
import { Findings } from './pages/Findings'
import { Backups } from './pages/Backups'
import { Apps } from './pages/Apps'
import { Approvals } from './pages/Approvals'
import { Settings } from './pages/Settings'
import { Home } from './pages/Home'
import { Onboarding } from './components/Onboarding'
import { DebugProvider } from './contexts/DebugContext'
import { ScanProvider } from './contexts/ScanContext'
import { PageContextProvider } from './contexts/PageContext'
import { ShellModeProvider } from './contexts/ShellModeContext'
import { apiUrl } from '@/lib/apiBase'

function App() {
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [checkingOnboarding, setCheckingOnboarding] = useState(true)
  const startupScanTriggered = useRef(false)

  // Check onboarding status and run quick scan on app startup
  useEffect(() => {
    const initializeApp = async () => {
      try {
        // Check if onboarding is complete
        const statusRes = await fetch(apiUrl('/api/settings/onboarding/status'))
        const status = await statusRes.json()
        
        if (!status.onboarding_complete) {
          // First time - show onboarding
          setShowOnboarding(true)
        } else if (status.has_system_profile && !startupScanTriggered.current) {
          // Run full scan on startup to refresh all system data (only once)
          startupScanTriggered.current = true
          console.log('Running full scan on startup...')
          fetch(apiUrl('/api/settings/system-profile/scan'), { method: 'POST' })
            .then(res => res.json())
            .then(data => {
              console.log('Full scan complete:', data.summary?.split('\n')[0])
              // Dispatch event to notify all pages to refresh
              window.dispatchEvent(new CustomEvent('halbert-scan-complete', { detail: { type: 'system' } }))
            })
            .catch(err => console.warn('Startup scan failed:', err))
        }
      } catch (err) {
        console.error('Failed to check onboarding status:', err)
      } finally {
        setCheckingOnboarding(false)
      }
    }
    
    initializeApp()
  }, [])

  const handleOnboardingComplete = () => {
    setShowOnboarding(false)
    // The onboarding already ran a deep scan, so profile data is available
    // Force a page reload to ensure all components pick up the fresh data
    window.location.reload()
  }

  // Show nothing while checking onboarding status
  if (checkingOnboarding) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  return (
    <DebugProvider>
      <ScanProvider>
          <Onboarding open={showOnboarding} onComplete={handleOnboardingComplete} />
          <Router>
            <PageContextProvider>
              <ShellModeProvider>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/terminal" element={<Terminal />} />
                    <Route path="/services" element={<Services />} />
                    <Route path="/storage" element={<Storage />} />
                    <Route path="/gpu" element={<GPU />} />
                    <Route path="/containers" element={<Containers />} />
                    <Route path="/development" element={<Development />} />
                    <Route path="/network" element={<Network />} />
                    <Route path="/sharing" element={<Sharing />} />
                    <Route path="/findings" element={<Findings />} />
                    {/* Legacy path: the page was renamed from Security to Findings
                     * to resolve the name overlap with Settings > Security. */}
                    <Route path="/security" element={<Navigate to="/findings" replace />} />
                    <Route path="/backups" element={<Backups />} />
                    <Route path="/apps" element={<Apps />} />
                    <Route path="/approvals" element={<Approvals />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/home" element={<Home />} />
                  </Routes>
                </Layout>
              </ShellModeProvider>
            </PageContextProvider>
          </Router>
      </ScanProvider>
    </DebugProvider>
  )
}

export default App
