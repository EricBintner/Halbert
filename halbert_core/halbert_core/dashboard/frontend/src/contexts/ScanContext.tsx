/**
 * ScanContext - Coordinates system-wide scanning across the app.
 * 
 * Three scan levels:
 * 1. Deep Scan - Full comprehensive scan (Settings page)
 * 2. System Scan - Quick scan of all sections (startup, refresh)
 * 3. Section Scan - Scan just one category (individual pages)
 * 
 * Usage:
 * - Deep scan triggers all sections to reload after completion
 * - System scan updates all sections
 * - Section scan updates just that section
 */

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'

interface ScanContextType {
  // Scan states
  isDeepScanning: boolean
  isSystemScanning: boolean
  sectionScanning: string | null  // Category currently being scanned
  
  // Last scan timestamps (for UI display)
  lastDeepScan: Date | null
  lastSystemScan: Date | null
  
  // Scan trigger functions
  triggerDeepScan: () => Promise<void>
  triggerSystemScan: () => Promise<void>
  triggerSectionScan: (category: string) => Promise<void>
  
  // Refresh counter - increments when scans complete to trigger page reloads
  refreshTrigger: number
  
  // Scan results (for showing in UI)
  lastScanSummary: string | null
}

const ScanContext = createContext<ScanContextType | null>(null)

export function useScan() {
  const context = useContext(ScanContext)
  if (!context) {
    throw new Error('useScan must be used within a ScanProvider')
  }
  return context
}

// Hook for pages to refresh when scans complete
export function useRefreshOnScan(loadData: () => void) {
  const { refreshTrigger } = useScan()
  
  useEffect(() => {
    if (refreshTrigger > 0) {
      loadData()
    }
  }, [refreshTrigger])
}

interface ScanProviderProps {
  children: React.ReactNode
}

export function ScanProvider({ children }: ScanProviderProps) {
  const [isDeepScanning, setIsDeepScanning] = useState(false)
  const [isSystemScanning, setIsSystemScanning] = useState(false)
  const [sectionScanning, setSectionScanning] = useState<string | null>(null)
  const [lastDeepScan, setLastDeepScan] = useState<Date | null>(null)
  const [lastSystemScan, setLastSystemScan] = useState<Date | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [lastScanSummary, setLastScanSummary] = useState<string | null>(null)

  // Deep scan - comprehensive system profile scan
  const triggerDeepScan = useCallback(async () => {
    if (isDeepScanning) return
    
    setIsDeepScanning(true)
    console.log('[Scan] Starting deep scan...')
    
    try {
      const res = await fetch('/api/settings/system-profile/scan', { method: 'POST' })
      const data = await res.json()
      
      if (data.status === 'complete') {
        setLastDeepScan(new Date())
        setLastScanSummary(data.summary?.split('\n')[0] || 'Scan complete')
        console.log('[Scan] Deep scan complete')
        
        // Trigger all pages to refresh their data via context
        setRefreshTrigger(prev => prev + 1)
        
        // Also dispatch window event for components that might not use the context
        window.dispatchEvent(new CustomEvent('halbert-scan-complete', { detail: { type: 'deep' } }))
      }
    } catch (err) {
      console.error('[Scan] Deep scan failed:', err)
    } finally {
      setIsDeepScanning(false)
    }
  }, [isDeepScanning])

  // System scan - quick scan of frequently-changing items
  const triggerSystemScan = useCallback(async () => {
    if (isSystemScanning) return
    
    setIsSystemScanning(true)
    console.log('[Scan] Starting system scan...')
    
    try {
      const res = await fetch('/api/settings/system-profile/quick-scan', { method: 'POST' })
      const data = await res.json()
      
      if (data.status === 'complete') {
        setLastSystemScan(new Date())
        setLastScanSummary(data.summary?.split('\n')[0] || 'Quick scan complete')
        console.log('[Scan] System scan complete')
        
        // Trigger all pages to refresh
        setRefreshTrigger(prev => prev + 1)
      }
    } catch (err) {
      console.error('[Scan] System scan failed:', err)
    } finally {
      setIsSystemScanning(false)
    }
  }, [isSystemScanning])

  // Section scan - scan just one category
  const triggerSectionScan = useCallback(async (category: string) => {
    if (sectionScanning) return
    
    setSectionScanning(category)
    console.log(`[Scan] Starting ${category} scan...`)
    
    try {
      const res = await fetch(`/api/settings/system-profile/scan-category/${category}`, { 
        method: 'POST' 
      })
      const data = await res.json()
      
      if (data.status === 'complete') {
        console.log(`[Scan] ${category} scan complete`)
        // Trigger refresh for this category
        setRefreshTrigger(prev => prev + 1)
      }
    } catch (err) {
      console.error(`[Scan] ${category} scan failed:`, err)
    } finally {
      setSectionScanning(null)
    }
  }, [sectionScanning])

  const value: ScanContextType = {
    isDeepScanning,
    isSystemScanning,
    sectionScanning,
    lastDeepScan,
    lastSystemScan,
    triggerDeepScan,
    triggerSystemScan,
    triggerSectionScan,
    refreshTrigger,
    lastScanSummary,
  }

  return (
    <ScanContext.Provider value={value}>
      {children}
    </ScanContext.Provider>
  )
}
