import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

export interface DebugLogEntry {
  id: string
  timestamp: Date
  type: 'request' | 'response' | 'error' | 'info' | 'timing'
  category: 'chat' | 'api' | 'terminal' | 'system'
  message: string
  data?: unknown
  duration?: number
}

interface DebugContextType {
  isDebugMode: boolean
  setDebugMode: (enabled: boolean) => void
  logs: DebugLogEntry[]
  addLog: (entry: Omit<DebugLogEntry, 'id' | 'timestamp'>) => void
  clearLogs: () => void
  // Chat-specific debug info
  chatMetrics: {
    lastRequestTime?: number
    lastResponseTime?: number
    totalRequests: number
    totalTokensEstimate: number
    averageResponseTime: number
  }
  updateChatMetrics: (metrics: Partial<DebugContextType['chatMetrics']>) => void
}

const DebugContext = createContext<DebugContextType | null>(null)

export function DebugProvider({ children }: { children: ReactNode }) {
  const [isDebugMode, setIsDebugMode] = useState(() => {
    // Persist debug mode in localStorage
    return localStorage.getItem('halbert_debug_mode') === 'true'
  })
  const [logs, setLogs] = useState<DebugLogEntry[]>([])
  const [chatMetrics, setChatMetrics] = useState({
    totalRequests: 0,
    totalTokensEstimate: 0,
    averageResponseTime: 0,
  })

  const setDebugMode = useCallback((enabled: boolean) => {
    setIsDebugMode(enabled)
    localStorage.setItem('halbert_debug_mode', enabled.toString())
    if (enabled) {
      console.log('%c[Halbert Debug Mode Enabled]', 'color: #22c55e; font-weight: bold')
    }
  }, [])

  const addLog = useCallback((entry: Omit<DebugLogEntry, 'id' | 'timestamp'>) => {
    const newEntry: DebugLogEntry = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
    }
    setLogs(prev => [...prev.slice(-499), newEntry]) // Keep last 500 logs
    
    // Also log to console in debug mode
    const style = entry.type === 'error' 
      ? 'color: #ef4444' 
      : entry.type === 'timing' 
        ? 'color: #f59e0b'
        : entry.type === 'request'
          ? 'color: #3b82f6'
          : 'color: #22c55e'
    console.log(`%c[${entry.category.toUpperCase()}] ${entry.message}`, style, entry.data || '')
  }, [])

  const clearLogs = useCallback(() => {
    setLogs([])
  }, [])

  const updateChatMetrics = useCallback((metrics: Partial<DebugContextType['chatMetrics']>) => {
    setChatMetrics(prev => ({ ...prev, ...metrics }))
  }, [])

  return (
    <DebugContext.Provider value={{
      isDebugMode,
      setDebugMode,
      logs,
      addLog,
      clearLogs,
      chatMetrics,
      updateChatMetrics,
    }}>
      {children}
    </DebugContext.Provider>
  )
}

export function useDebug() {
  const context = useContext(DebugContext)
  if (!context) {
    throw new Error('useDebug must be used within a DebugProvider')
  }
  return context
}

// Hook for timing operations
export function useDebugTimer(category: DebugLogEntry['category']) {
  const { isDebugMode, addLog } = useDebug()
  
  const startTimer = useCallback((operation: string) => {
    if (!isDebugMode) return { end: () => {} }
    const start = performance.now()
    addLog({
      type: 'request',
      category,
      message: `Starting: ${operation}`,
    })
    return {
      end: (resultMessage?: string) => {
        const duration = performance.now() - start
        addLog({
          type: 'timing',
          category,
          message: resultMessage || `Completed: ${operation}`,
          duration,
        })
        return duration
      }
    }
  }, [isDebugMode, addLog, category])
  
  return { startTimer }
}
