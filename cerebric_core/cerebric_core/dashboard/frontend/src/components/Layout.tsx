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
  const { isDebugMode, setDebugMode } = useDebug()

  return (
    <div className="h-screen bg-background flex overflow-hidden">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-card border-r z-50">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center gap-2 px-6 py-3 border-b">
            <img src="/Cerebric.png" alt="Cerebric" className="h-6 w-6" />
            <span className="text-lg font-semibold">Cerebric</span>
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
                isDebugMode && "bg-amber-600 hover:bg-amber-700"
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
        {/* Page content */}
        <main className="flex-1 p-8 overflow-auto relative">
          {children}
        </main>

        {/* Side Panel - Chat/Terminal, always visible */}
        <SidePanel />
      </div>
    </div>
  )
}
