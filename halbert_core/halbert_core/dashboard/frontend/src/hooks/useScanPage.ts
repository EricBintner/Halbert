// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useScanPage - Common hook for page scan functionality
 * 
 * Phase 20D: Extracted from repeated pattern across 8+ pages
 * 
 * Features:
 * - Manages scanning state
 * - Handles scan API call
 * - Triggers data reload after scan
 * - Error handling with console logging
 */

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'

export type ScanType = 'backup' | 'service' | 'storage' | 'network' | 'security' | 'sharing' | 'all'

interface UseScanPageOptions {
  /** The scanner type to run */
  scanType: ScanType
  /** Callback to reload data after scan completes */
  onScanComplete?: () => Promise<void>
  /** Optional callback on scan error */
  onError?: (error: unknown) => void
}

interface UseScanPageReturn {
  /** Whether a scan is currently in progress */
  scanning: boolean
  /** Trigger a scan */
  handleScan: () => Promise<void>
}

/**
 * Hook for managing page scan state and triggering scans
 * 
 * @example
 * ```tsx
 * const { scanning, handleScan } = useScanPage({
 *   scanType: 'backup',
 *   onScanComplete: loadBackups,
 * })
 * 
 * return (
 *   <PageHeader
 *     scanning={scanning}
 *     onScan={handleScan}
 *   />
 * )
 * ```
 */
export function useScanPage({
  scanType,
  onScanComplete,
  onError,
}: UseScanPageOptions): UseScanPageReturn {
  const [scanning, setScanning] = useState(false)

  const handleScan = useCallback(async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries(scanType)
      if (onScanComplete) {
        await onScanComplete()
      }
    } catch (error) {
      console.error(`Scan failed for ${scanType}:`, error)
      if (onError) {
        onError(error)
      }
    } finally {
      setScanning(false)
    }
  }, [scanType, onScanComplete, onError])

  return { scanning, handleScan }
}

export default useScanPage
