// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Findings Page - Security scan findings and hardening status.
 *
 * Renamed from Security to resolve the route/name overlap with the
 * Settings > Security tab (MCP trust gates). This page is the findings
 * engine: the results of security discovery scans.
 *
 * Based on Phase 9 research: docs/Phase9/deep-dives/08-security-hardening.md
 */

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { 
  Shield, 
  RefreshCw, 
  Loader2,
  Lock,
  Users,
  Key,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { SystemItemActions, StatusBadge, PageHeader } from '@/components/domain'
import { useScanPage } from '@/hooks'

interface FindingItem {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: Record<string, unknown>
}

export function Findings() {
  const [findings, setFindings] = useState<FindingItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadFindings()
  }, [])

  const loadFindings = async () => {
    try {
      const data = await api.getDiscoveries('security')
      setFindings(data.discoveries || [])
    } catch (error) {
      console.error('Failed to load findings:', error)
    } finally {
      setLoading(false)
    }
  }

  const { scanning, handleScan } = useScanPage({
    scanType: 'security',
    onScanComplete: loadFindings,
  })

  const getIcon = (item: FindingItem) => {
    if (item.name.includes('ssh')) return <Key className="h-5 w-5 text-info" />
    if (item.name.includes('sudo')) return <Users className="h-5 w-5 text-purple-500" />
    if (item.name.includes('fail2ban')) return <Shield className="h-5 w-5 text-success" />
    if (item.name.includes('update')) return <RefreshCw className="h-5 w-5 text-warning" />
    return <Lock className="h-5 w-5 text-muted-foreground" />
  }

  const stats = {
    total: findings.length,
    secure: findings.filter(s => s.severity === 'success').length,
    warnings: findings.filter(s => s.severity === 'warning').length,
    issues: findings.filter(s => s.severity === 'critical').length,
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        icon={<Shield className="h-8 w-8" />}
        title="Findings"
        description="Security scan findings and hardening status"
        scanning={scanning}
        onScan={handleScan}
      />

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Checks</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <Shield className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Secure</p>
                <p className="text-2xl font-bold text-success">{stats.secure}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-success" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Warnings</p>
                <p className="text-2xl font-bold text-warning">{stats.warnings}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-warning" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Issues</p>
                <p className="text-2xl font-bold text-error">{stats.issues}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-error" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Findings */}
      {findings.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <Shield className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No Findings Yet</h3>
            <p className="text-muted-foreground mb-4">
              Click Scan to check your security configuration.
            </p>
            <Button variant="outline" onClick={handleScan} disabled={scanning}>
              <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
              Scan for Findings
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {findings.map((item) => (
            <Card key={item.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    {getIcon(item)}
                    <div>
                      <h3 className="font-medium">{item.title}</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        {item.description}
                      </p>
                      
                      {/* Show details for SSH */}
                      {item.name === 'ssh-config' && Array.isArray(item.data.issues) && (
                        <div className="mt-2 space-y-1">
                          {(item.data.issues as string[]).map((issue: string, i: number) => (
                            <div key={i} className="flex items-center gap-2 text-sm text-warning">
                              <AlertTriangle className="h-3 w-3" />
                              {issue}
                            </div>
                          ))}
                        </div>
                      )}
                      
                      {/* Show sudo users */}
                      {item.name === 'sudo-users' && Array.isArray(item.data.users) && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {(item.data.users as string[]).slice(0, 5).map((user: string) => (
                            <Badge key={user} variant="outline">{user}</Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={item.status} severity={item.severity} />
                    <SystemItemActions
                      item={{
                        name: item.title,
                        type: 'security',
                        id: `security/${item.id}`,
                        description: item.description,
                        status: item.status,
                        data: {
                          severity: item.severity,
                        },
                        context: `Security Item: ${item.title}\nStatus: ${item.status}\nDescription: ${item.description}`,
                      }}
                      size="sm"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Security Tips */}
      <Card>
        <CardHeader>
          <CardTitle>Security Recommendations</CardTitle>
          <CardDescription>Best practices for system hardening</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 text-sm">
            <div className="flex items-start gap-3">
              <Key className="h-4 w-4 mt-0.5 text-muted-foreground" />
              <div>
                <p className="font-medium">Use SSH keys instead of passwords</p>
                <p className="text-muted-foreground">Disable PasswordAuthentication in sshd_config</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Shield className="h-4 w-4 mt-0.5 text-muted-foreground" />
              <div>
                <p className="font-medium">Enable fail2ban</p>
                <p className="text-muted-foreground">Protect against brute-force attacks</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <RefreshCw className="h-4 w-4 mt-0.5 text-muted-foreground" />
              <div>
                <p className="font-medium">Enable automatic security updates</p>
                <p className="text-muted-foreground">Keep your system patched against vulnerabilities</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* AI Analysis Panel */}
      <AIAnalysisPanel
        type="security"
        title="Findings"
        canAnalyze={findings.length > 0}
        buildContext={() => {
          const parts = [`## Findings Analysis Context\n`]
          parts.push(`- ${stats.total} security checks`)
          parts.push(`- ${stats.secure} secure`)
          parts.push(`- ${stats.warnings} warnings`)
          parts.push(`- ${stats.issues} issues\n`)

          // List security issues
          const issues = findings.filter(s => s.severity === 'critical' || s.severity === 'warning')
          if (issues.length > 0) {
            parts.push(`### Issues Detected:`)
            issues.forEach(i => parts.push(`- ${i.title}: ${i.description}`))
          }
          
          return parts.join('\n')
        }}
        researchQuestion="Analyze my security configuration and identify vulnerabilities or hardening recommendations."
      />
    </div>
  )
}
