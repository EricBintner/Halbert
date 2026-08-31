// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Bell } from 'lucide-react'

export interface AlertRule {
  id: string
  name: string
  description: string
  severity: string
  enabled: boolean
}

interface AlertsTabProps {
  alertRules: AlertRule[]
}

/** The Alerts tab: read-only list of configured alert rules. */
export function AlertsTab({ alertRules }: AlertsTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="h-5 w-5" />
          Alert Rules
        </CardTitle>
        <CardDescription>
          Configure when alerts are triggered
        </CardDescription>
      </CardHeader>
      <CardContent>
        {alertRules.length === 0 ? (
          <p className="text-sm text-muted-foreground">Loading alert rules...</p>
        ) : (
          <div className="space-y-4">
            {alertRules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between p-3 rounded-lg border"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{rule.name}</p>
                    <Badge variant="outline" className="text-xs">
                      {rule.severity}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{rule.description}</p>
                </div>
                <Badge variant={rule.enabled ? "default" : "outline"}>
                  {rule.enabled ? "Enabled" : "Disabled"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}