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
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidePanel } from './SidePanel'
import { useDebug } from '@/contexts/DebugContext'

const navigation = [
  // Overview
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  
  // Essential System Health
  { name: 'Services', href: '/services', icon: Server },
  { name: 'Storage', href: '/storage', icon: HardDrive },
  { name: 'Backups', href: '/backups', icon: Archive },
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
  const { isDebugMode, setDebugMode, chatMetrics } = useDebug()

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
            <Button 
              variant={isDebugMode ? "default" : "outline"}
              size="sm" 
              className={cn(
                "w-full text-xs",
                isDebugMode && "bg-emerald-600 hover:bg-emerald-700 text-white"
              )}
              onClick={() => setDebugMode(!isDebugMode)}
            >
              <Bug className="h-3 w-3 mr-2" />
              {isDebugMode ? 'Debug Mode ON' : 'Debug Mode'}
            </Button>
            <div className="text-xs text-muted-foreground">
              <p>v0.1.0 • Phase 11 {isDebugMode && '• DEV'}</p>
              <p>AI-First System Management</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main content + Chat Panel */}
      <div className="flex flex-1 ml-64 h-full">
        {/* Page content with optional debug footer */}
        <div className="flex-1 flex flex-col">
          <main className="flex-1 p-8 overflow-auto relative">
            {children}
          </main>
          
          {/* Debug Bar - matches sidebar footer height */}
          {isDebugMode && (
            <div className="border-t bg-slate-800 px-4 py-3 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-4">
                <span className="text-emerald-400 font-bold">🐛 Debug Mode</span>
                <span className="text-slate-400">DevTools Console (F12) for full logs</span>
              </div>
              <div className="flex items-center gap-6 text-slate-200">
                <span><span className="text-emerald-400">Requests:</span> {chatMetrics.totalRequests}</span>
                <span><span className="text-emerald-400">Tokens:</span> ~{chatMetrics.totalTokensEstimate}</span>
                <span><span className="text-emerald-400">Avg:</span> {chatMetrics.averageResponseTime > 0 ? `${chatMetrics.averageResponseTime.toFixed(0)}ms` : '-'}</span>
                <span><span className="text-emerald-400">Last:</span> {chatMetrics.lastResponseTime && chatMetrics.lastRequestTime ? `${(chatMetrics.lastResponseTime - chatMetrics.lastRequestTime).toFixed(0)}ms` : '-'}</span>
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
