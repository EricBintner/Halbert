/**
 * DiscoveryCard - Reusable card component for displaying discoveries.
 * 
 * Based on Phase 9 research: docs/Phase11/02-COMPONENT-LIBRARY.md
 * 
 * Shows:
 * - Discovery title and description
 * - Status badge with severity color
 * - Quick actions
 * - Chat button for @mention
 */

import { 
  Archive, 
  Server, 
  HardDrive, 
  Shield, 
  Cpu,
  Network,
  Container,
  Clock,
  Activity,
  AlertCircle,
  CheckCircle,
  Info,
  MessageCircle,
  MoreHorizontal,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

interface Discovery {
  id: string
  type: string
  name: string
  title: string
  description: string
  icon?: string
  severity: 'critical' | 'warning' | 'info' | 'success'
  status?: string
  status_detail?: string
  mention: string
  actions?: Array<{
    id: string
    label: string
    icon?: string
  }>
}

interface DiscoveryCardProps {
  discovery: Discovery
  compact?: boolean
  onChatClick?: (discovery: Discovery) => void
  onActionClick?: (discovery: Discovery, actionId: string) => void
}

const typeIcons: Record<string, React.ElementType> = {
  backup: Archive,
  service: Server,
  storage: HardDrive,
  filesystem: HardDrive,
  security: Shield,
  process: Cpu,
  network: Network,
  container: Container,
  task: Clock,
  performance: Activity,
  hardware: Cpu,
  gpu: Cpu,
}

const severityColors: Record<string, string> = {
  critical: 'bg-destructive text-destructive-foreground',
  warning: 'bg-yellow-500 text-white',
  info: 'bg-blue-500 text-white',
  success: 'bg-green-500 text-white',
}

const severityIcons: Record<string, React.ElementType> = {
  critical: AlertCircle,
  warning: AlertCircle,
  info: Info,
  success: CheckCircle,
}

export function DiscoveryCard({ 
  discovery, 
  compact = false,
  onChatClick,
  onActionClick,
}: DiscoveryCardProps) {
  const TypeIcon = typeIcons[discovery.type] || Activity
  const SeverityIcon = severityIcons[discovery.severity] || Info

  if (compact) {
    return (
      <div className="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
        <div className="flex-shrink-0">
          <TypeIcon className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{discovery.name}</p>
          <p className="text-xs text-muted-foreground truncate">{discovery.status || discovery.description}</p>
        </div>
        <Badge className={severityColors[discovery.severity]} variant="secondary">
          {discovery.status || discovery.severity}
        </Badge>
      </div>
    )
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-md bg-primary/10">
              <TypeIcon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">{discovery.title}</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                {discovery.mention}
              </CardDescription>
            </div>
          </div>
          <Badge className={severityColors[discovery.severity]} variant="secondary">
            <SeverityIcon className="h-3 w-3 mr-1" />
            {discovery.status || discovery.severity}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          {discovery.description}
        </p>
        
        {discovery.status_detail && (
          <p className="text-xs text-muted-foreground mb-4">
            {discovery.status_detail}
          </p>
        )}

        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => onChatClick?.(discovery)}
          >
            <MessageCircle className="h-4 w-4 mr-1" />
            Chat
          </Button>
          
          {discovery.actions?.slice(0, 2).map((action) => (
            <Button 
              key={action.id}
              variant="outline" 
              size="sm"
              onClick={() => onActionClick?.(discovery, action.id)}
            >
              {action.label}
            </Button>
          ))}

          {(discovery.actions?.length || 0) > 2 && (
            <Button variant="ghost" size="sm">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface DiscoveryListProps {
  discoveries: Discovery[]
  variant?: 'cards' | 'compact' | 'table'
  onChatClick?: (discovery: Discovery) => void
  onActionClick?: (discovery: Discovery, actionId: string) => void
}

export function DiscoveryList({
  discoveries,
  variant = 'cards',
  onChatClick,
  onActionClick,
}: DiscoveryListProps) {
  if (discoveries.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No discoveries found</p>
        <p className="text-xs">Try running a scan to discover system resources</p>
      </div>
    )
  }

  if (variant === 'compact') {
    return (
      <div className="space-y-2">
        {discoveries.map((discovery) => (
          <DiscoveryCard
            key={discovery.id}
            discovery={discovery}
            compact
            onChatClick={onChatClick}
            onActionClick={onActionClick}
          />
        ))}
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {discoveries.map((discovery) => (
        <DiscoveryCard
          key={discovery.id}
          discovery={discovery}
          onChatClick={onChatClick}
          onActionClick={onActionClick}
        />
      ))}
    </div>
  )
}
