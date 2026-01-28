import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { 
  LayoutDashboard, 
  Server,
  Archive,
  CheckCircle, 
  HardDrive, 
  Wifi,
  Share2,
  Shield,
  Settings,
  Bug,
  Cpu,
  Container,
  Code2,
  Package,
  Loader2,
  ScanSearch,
  Bot,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidePanel } from './SidePanel'
import { ConfigEditor } from './ConfigEditor'
import { useDebug } from '@/contexts/DebugContext'

const navigation = [
  // Overview
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Agent', href: '/agent', icon: Bot },
  
  // Essential System Health
  { name: 'Services', href: '/services', icon: Server },
  { name: 'Storage', href: '/storage', icon: HardDrive },
  { name: 'Backups', href: '/backups', icon: Archive },
  { name: 'Apps', href: '/apps', icon: Package },
  { name: 'Security', href: '/security', icon: Shield },
  
  // Networking
  { name: 'Network', href: '/network', icon: Wifi },
  { name: 'Sharing', href: '/sharing', icon: Share2 },
  
  // Dev & Advanced
  { name: 'Containers', href: '/containers', icon: Container },
  { name: 'GPU', href: '/gpu', icon: Cpu },
  { name: 'Development', href: '/development', icon: Code2 },
  
  // Utility
  { name: 'Approvals', href: '/approvals', icon: CheckCircle },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const { isDebugMode, setDebugMode, chatMetrics, logs, clearLogs } = useDebug()
  
  // Global config editor state (triggered from chat "Edit Config" button)
  const [editingConfigPath, setEditingConfigPath] = useState<string | null>(null)
  
  // Indexing status state (moved from Settings)
  const [indexing, setIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState<{
    percent: number
    currentSource: string | null
    completed: number
    total: number
  }>({ percent: 0, currentSource: null, completed: 0, total: 0 })
  
  // System scan status state
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<{
    percent: number
    currentPhase: string | null
  }>({ percent: 0, currentPhase: null })
  
  // Listen for open-config-editor events from chat
  useEffect(() => {
    const handleOpenConfigEditor = (e: CustomEvent<{ filePath: string }>) => {
      console.log('[Layout] Opening config editor for:', e.detail.filePath)
      setEditingConfigPath(e.detail.filePath)
    }
    
    window.addEventListener('halbert:open-config-editor', handleOpenConfigEditor as EventListener)
    return () => {
      window.removeEventListener('halbert:open-config-editor', handleOpenConfigEditor as EventListener)
    }
  }, [])
  
  // Poll for indexing and scan status
  useEffect(() => {
    const checkStatus = async () => {
      // Check indexing status
      try {
        const res = await fetch('/api/settings/docs/stats')
        const data = await res.json()
        const status = data.indexing
        
        if (status?.is_running) {
          setIndexing(true)
          setIndexProgress({
            percent: status.progress_percent || 0,
            currentSource: status.current_source,
            completed: status.sources_completed?.length || 0,
            total: status.sources_total || 0
          })
        } else {
          setIndexing(false)
        }
      } catch (err) {
        // Silently fail - indexing status is non-critical
      }
      
      // Check system scan status
      try {
        const res = await fetch('/api/settings/system-profile/scan/status')
        const data = await res.json()
        
        if (data.is_running) {
          setScanning(true)
          setScanProgress({
            percent: data.progress_percent || 0,
            currentPhase: data.current_phase
          })
        } else {
          setScanning(false)
        }
      } catch (err) {
        // Silently fail - scan status is non-critical
      }
    }
    
    // Check immediately on mount
    checkStatus()
    
    // Poll every 2 seconds
    const interval = setInterval(checkStatus, 2000)
    return () => clearInterval(interval)
  }, [])
  
  // Listen for screenshot capture requests from chat input
  useEffect(() => {
    const handleCaptureScreenshot = async () => {
      try {
        // Use html2canvas to capture the window
        const html2canvas = (await import('html2canvas')).default
        const canvas = await html2canvas(document.body, {
          useCORS: true,
          logging: false,
        })
        
        // Convert to base64 (strip the data URL prefix for the API)
        const dataUrl = canvas.toDataURL('image/png')
        const base64 = dataUrl.replace(/^data:image\/\w+;base64,/, '')
        
        // Dispatch event to add screenshot to chat
        window.dispatchEvent(new CustomEvent('halbert:add-screenshot', {
          detail: {
            dataUrl,  // Full data URL for preview
            base64,   // Just base64 for API
            name: `Screenshot ${new Date().toLocaleTimeString()}`
          }
        }))
        
        console.log('[Layout] Screenshot captured and dispatched to chat')
      } catch (err) {
        console.error('[Layout] Failed to capture screenshot:', err)
      }
    }
    
    window.addEventListener('halbert:capture-screenshot', handleCaptureScreenshot)
    return () => {
      window.removeEventListener('halbert:capture-screenshot', handleCaptureScreenshot)
    }
  }, [])
  
  return (
    <div className="h-screen bg-background flex overflow-hidden">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-card border-r z-50">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center gap-2 px-6 py-3 border-b">
            <img src="/Halbert.png" alt="Halbert" className="h-6 w-6" />
            <span className="text-lg font-semibold">Halbert</span>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-4 space-y-1">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {item.name}
                </Link>
              )
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t space-y-2">
            {/* System Scan Status */}
            {scanning && (
              <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-600 dark:text-emerald-400">
                <div className="flex items-center gap-2 mb-1.5">
                  <ScanSearch className="h-3 w-3 animate-pulse" />
                  <span className="font-medium">Scanning...</span>
                  <span className="text-[10px] ml-auto">{scanProgress.percent}%</span>
                </div>
                <div className="w-full bg-emerald-200 dark:bg-emerald-900 rounded-full h-1.5">
                  <div 
                    className="bg-emerald-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${scanProgress.percent}%` }}
                  />
                </div>
                <p className="text-[10px] mt-1 truncate">
                  {scanProgress.currentPhase || 'Starting...'}
                </p>
              </div>
            )}
            {/* Indexing Status */}
            {indexing && (
              <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded text-xs text-blue-600 dark:text-blue-400">
                <div className="flex items-center gap-2 mb-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span className="font-medium">Indexing...</span>
                  <span className="text-[10px] ml-auto">{indexProgress.percent}%</span>
                </div>
                <div className="w-full bg-blue-200 dark:bg-blue-900 rounded-full h-1.5">
                  <div 
                    className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${indexProgress.percent}%` }}
                  />
                </div>
                <p className="text-[10px] mt-1 truncate">
                  {indexProgress.currentSource || 'Starting...'}
                </p>
              </div>
            )}
            {/* Version and Debug row */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <p>v0.1.1</p>
              <Button 
                variant={isDebugMode ? "default" : "ghost"}
                size="icon"
                className={cn(
                  "h-6 w-6",
                  isDebugMode && "bg-emerald-600 hover:bg-emerald-700 text-white"
                )}
                onClick={() => setDebugMode(!isDebugMode)}
                title={isDebugMode ? 'Debug ON' : 'Debug'}
              >
                <Bug className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content + Chat Panel */}
      <div className="flex flex-1 ml-64 h-full overflow-hidden">
        {/* Page content with optional debug footer */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <main className="flex-1 p-8 overflow-auto relative z-0">
            {editingConfigPath ? (
              <ConfigEditor
                filePath={editingConfigPath}
                onClose={() => setEditingConfigPath(null)}
              />
            ) : (
              children
            )}
          </main>
          
          {/* Debug Panel - non-overlaying, stats on left, logs on right */}
          {isDebugMode && (
            <div className="border-t bg-slate-800 h-48 flex text-xs font-mono">
              {/* Left: Stats */}
              <div className="w-48 border-r border-slate-700 p-3 flex flex-col gap-2">
                <div className="text-emerald-400 font-bold flex items-center gap-1">
                  <Bug className="h-3 w-3" /> Debug Mode
                </div>
                <div className="space-y-1 text-slate-300">
                  <div><span className="text-emerald-400">Requests:</span> {chatMetrics.totalRequests}</div>
                  <div><span className="text-emerald-400">Tokens:</span> ~{chatMetrics.totalTokensEstimate}</div>
                  <div><span className="text-emerald-400">Avg:</span> {chatMetrics.averageResponseTime > 0 ? `${chatMetrics.averageResponseTime.toFixed(0)}ms` : '-'}</div>
                  <div><span className="text-emerald-400">Last:</span> {chatMetrics.lastResponseTime && chatMetrics.lastRequestTime ? `${(chatMetrics.lastResponseTime - chatMetrics.lastRequestTime).toFixed(0)}ms` : '-'}</div>
                </div>
              </div>
              {/* Right: Logs */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-700 bg-slate-750">
                  <span className="text-slate-300">Logs ({logs.length})</span>
                  <button onClick={clearLogs} className="text-slate-400 hover:text-slate-200 text-[10px]">Clear</button>
                </div>
                <div className="flex-1 overflow-auto p-2">
                  {logs.length === 0 ? (
                    <div className="text-slate-500 text-center py-4">No logs yet. Interact with the app to see logs.</div>
                  ) : (
                    logs.slice().reverse().map(log => (
                      <div key={log.id} className={cn(
                        "py-0.5",
                        log.type === 'error' && "text-red-400",
                        log.type === 'timing' && "text-amber-400",
                        log.type === 'request' && "text-blue-400",
                        log.type === 'response' && "text-green-400",
                        log.type === 'info' && "text-slate-300"
                      )}>
                        <span className="text-slate-500">[{log.timestamp.toLocaleTimeString()}]</span>
                        <span className="text-slate-400 ml-1">[{log.category}]</span>
                        <span className="ml-1">{log.message}</span>
                        {log.duration && <span className="text-slate-500 ml-1">({log.duration.toFixed(0)}ms)</span>}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Side Panel - Chat/Terminal, always visible */}
        <SidePanel />
      </div>
    </div>
  )
}
