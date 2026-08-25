import { useState, useEffect, useCallback, useRef } from 'react'

export interface SourcePrepDaemonState {
  /** Is the SourcePrep daemon reachable on :8400? */
  isDaemonRunning: boolean
  /** True while the probe is in-flight (first load only). */
  isProbing: boolean
  /** The base URL for the daemon (e.g. http://localhost:8400). */
  daemonUrl: string
  /** Last error from a probe, if any. */
  error: string | null
}

interface UseSourcePrepDaemonOptions {
  /** Port to probe (default 8400). */
  port?: number
  /** Poll interval in ms (default 10000). */
  pollIntervalMs?: number
  /** Host to probe (default localhost). */
  host?: string
}

/**
 * Probes the SourcePrep daemon health endpoint to detect whether it's running.
 *
 * When the daemon is up, Halbert's native LLM picker should defer to
 * SourcePrep's dashboard for model management. When the daemon is down,
 * Halbert's native picker re-enables.
 *
 * Uses a lightweight fetch to /health with a short timeout. Polls at
 * the configured interval but skips polls while the tab is hidden.
 */
export function useSourcePrepDaemon({
  port = 8400,
  pollIntervalMs = 10000,
  host = 'localhost',
}: UseSourcePrepDaemonOptions = {}): SourcePrepDaemonState {
  const [isDaemonRunning, setIsDaemonRunning] = useState(false)
  const [isProbing, setIsProbing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const daemonUrl = `http://${host}:${port}`

  const probe = useCallback(async () => {
    // Cancel any in-flight probe
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const r = await fetch(`${daemonUrl}/health`, {
        signal: controller.signal,
        // Short timeout via AbortController
      })
      // Use a manual timeout race
      const timeoutId = setTimeout(() => controller.abort(), 3000)
      if (r.ok) {
        setIsDaemonRunning(true)
        setError(null)
      } else {
        setIsDaemonRunning(false)
        setError(`HTTP ${r.status}`)
      }
      clearTimeout(timeoutId)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Expected from timeout or cancellation — don't update state
      } else {
        setIsDaemonRunning(false)
        setError(err instanceof Error ? err.message : 'Connection failed')
      }
    } finally {
      setIsProbing(false)
    }
  }, [daemonUrl])

  useEffect(() => {
    // Initial probe
    void probe()

    // Set up polling
    const poll = () => {
      if (!document.hidden) {
        void probe()
      }
    }
    const interval = setInterval(poll, pollIntervalMs)

    return () => {
      clearInterval(interval)
      if (abortRef.current) {
        abortRef.current.abort()
      }
    }
  }, [probe, pollIntervalMs])

  return {
    isDaemonRunning,
    isProbing,
    daemonUrl,
    error,
  }
}
