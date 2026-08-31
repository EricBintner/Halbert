// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Acoustic anomaly module — renders acoustic event cards in conversation.
//
// Registered in the module registry as 'acoustic-anomaly' (O5) and rendered
// by the proactive-events badge for acoustic findings.
// Shows sound class, location, confidence, dB level, and severity tier.
//
// The action buttons (View Camera / Mute / Call Emergency) have no handlers
// yet, so they are hidden by default (showActions): a dead destructive
// button on a life-safety card is worse than no button. A caller that wires
// them up opts in.

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, Camera, VolumeX, Phone } from 'lucide-react'

export interface AcousticAnomalyData {
  finding_id?: string
  sound_class: string
  confidence: number
  area_id: string
  decibel_level: number
  anomaly_severity: number  // 0-3
  source: string
  timestamp: string
  action_taken?: string
}

export interface AcousticAnomalyModuleProps {
  data: AcousticAnomalyData
  /** Render the (currently unwired) action buttons. Default: false. */
  showActions?: boolean
}

const SEVERITY_LABELS = ['Info', 'Warning', 'Confirm', 'Critical']
const SEVERITY_COLORS = [
  'bg-blue-100 text-blue-700',
  'bg-yellow-100 text-yellow-700',
  'bg-orange-100 text-orange-700',
  'bg-red-100 text-red-700',
]

export function AcousticAnomalyModule({ data, showActions = false }: AcousticAnomalyModuleProps) {
  const severity = data.anomaly_severity || 0
  const severityLabel = SEVERITY_LABELS[severity] || 'Info'
  const severityColor = SEVERITY_COLORS[severity] || SEVERITY_COLORS[0]
  const isCritical = severity >= 3

  return (
    <Card className={isCritical ? 'border-destructive' : ''}>
      <CardContent className="space-y-3 py-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className={`h-5 w-5 ${isCritical ? 'text-destructive' : 'text-yellow-500'}`} />
            <span className="font-medium">
              {isCritical ? 'Critical Acoustic Anomaly' : 'Acoustic Observation'}
            </span>
          </div>
          <Badge className={severityColor} variant="outline">
            {severityLabel}
          </Badge>
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted-foreground">Sound: </span>
            <span className="font-medium">{data.sound_class}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Confidence: </span>
            <span className="font-medium">{(data.confidence * 100).toFixed(0)}%</span>
          </div>
          <div>
            <span className="text-muted-foreground">Location: </span>
            <span className="font-medium">{data.area_id || 'Unknown'}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Peak: </span>
            <span className="font-medium">{data.decibel_level.toFixed(0)} dB</span>
          </div>
          <div>
            <span className="text-muted-foreground">Source: </span>
            <span className="font-medium">{data.source}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Time: </span>
            <span className="font-medium">
              {new Date(data.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>

        {/* Action taken */}
        {data.action_taken && (
          <div className="text-sm p-2 rounded bg-muted">
            <span className="text-muted-foreground">Action: </span>
            {data.action_taken}
          </div>
        )}

        {/* Action buttons — hidden unless the caller wires them up
            (showActions): no handler means no button, especially the
            destructive one on a life-safety card. */}
        {showActions && (
        <div className="flex gap-2">
          <Button size="sm" variant="outline">
            <Camera className="h-3 w-3 mr-1" />
            View Camera
          </Button>
          <Button size="sm" variant="outline">
            <VolumeX className="h-3 w-3 mr-1" />
            Mute / False Alarm
          </Button>
          {isCritical && (
            <Button size="sm" variant="destructive">
              <Phone className="h-3 w-3 mr-1" />
              Call Emergency
            </Button>
          )}
        </div>
        )}
      </CardContent>
    </Card>
  )
}
