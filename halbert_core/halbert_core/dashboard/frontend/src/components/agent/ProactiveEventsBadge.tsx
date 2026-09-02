// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ProactiveEventsBadge — the Findings bell: live count and dropdown.
 *
 * Uses the useBeingEvents hook to receive findings via SSE. Shows a badge
 * with the count of unread findings and a dropdown listing recent ones
 * with their why (why_care as the second line — the interrupt justifies
 * itself, C2-02), snooze/dismiss, and "Propose fix" for findings that
 * have no proposal yet (J3-7 manual path).
 *
 * Snooze/dismiss only remove the row after the server confirms the action;
 * failures surface an inline error bar at the top of the dropdown.
 *
 * Phase 7 / T7b.2 wiring.
 */

import { useState, useRef, useEffect } from 'react'
import { Bell, X, Clock, AlertTriangle, AlertCircle, Info, CheckCircle, Loader2, Wrench } from 'lucide-react'
import { useBeingEvents, isAcousticEvent, canProposeFix, type BeingEvent } from '../../hooks/useBeingEvents'
import { AcousticAnomalyModule, type AcousticAnomalyData } from '../audio'

const SEVERITY_ICONS = {
  critical: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const SEVERITY_COLORS = {
  critical: 'text-error bg-error/10 border-error/30',
  warning: 'text-warning bg-warning/10 border-warning/30',
  info: 'text-info bg-info/10 border-info/30',
}

export function ProactiveEventsBadge() {
  const { events, snooze, dismiss, propose, pendingActions, actionError, clearActionError } = useBeingEvents()
  const [isOpen, setIsOpen] = useState(false)
  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  const dropdownRef = useRef<HTMLDivElement>(null)

  const unreadCount = events.filter(e => !readIds.has(e.id)).length

  useEffect(() => {
    if (!isOpen) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen])

  const toggleOpen = () => {
    setIsOpen(!isOpen)
    if (!isOpen) {
      setReadIds(new Set(events.map(e => e.id)))
    }
  }

  // Send the whole event — the hook prefers finding_id when present.
  const handleSnooze = async (event: BeingEvent) => {
    await snooze(event, 7)
  }

  const handleDismiss = async (event: BeingEvent) => {
    await dismiss(event, 'dismissed from badge')
  }

  const handlePropose = async (event: BeingEvent) => {
    await propose(event)
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={toggleOpen}
        className="relative p-2 rounded-lg hover:bg-muted transition-colors"
        title="Findings"
      >
        <Bell className="h-5 w-5 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-error text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-96 max-h-[500px] overflow-hidden rounded-lg border border-border bg-background shadow-xl z-50">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-medium text-foreground">Findings</span>
            <button onClick={() => setIsOpen(false)} className="p-1 hover:bg-muted rounded">
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>

          {actionError && (
            <div className="flex items-start gap-2 border-b border-error/30 bg-error/10 px-4 py-2">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-error" />
              <span className="flex-1 text-xs text-error break-words">{actionError}</span>
              <button
                onClick={clearActionError}
                className="p-0.5 hover:bg-error/20 rounded shrink-0"
                title="Dismiss error"
              >
                <X className="h-3 w-3 text-error" />
              </button>
            </div>
          )}

          <div className="max-h-[400px] overflow-y-auto">
            {events.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                <CheckCircle className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                Nothing needs your attention
              </div>
            ) : (
              events.map((event) => (
                <EventRow
                  key={event.id}
                  event={event}
                  pending={pendingActions.has(event.id)}
                  onSnooze={() => handleSnooze(event)}
                  onDismiss={() => handleDismiss(event)}
                  onPropose={() => handlePropose(event)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function EventRow({
  event,
  pending,
  onSnooze,
  onDismiss,
  onPropose,
}: {
  event: BeingEvent
  pending: boolean
  onSnooze: () => void
  onDismiss: () => void
  onPropose: () => void
}) {
  const Icon = SEVERITY_ICONS[event.severity] || Info
  const colorClass = SEVERITY_COLORS[event.severity] || SEVERITY_COLORS.info

  // The second line is the why (consequence if ignored) when the finding
  // carries one; the raw description is the fallback for events without.
  const secondLine = event.why?.care || event.body
  const proposeAction = canProposeFix(event) ? (
    <button
      onClick={onPropose}
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
    >
      <Wrench className="h-3 w-3" />
      Propose fix
    </button>
  ) : event.type === 'finding' && event.proposal_id ? (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Wrench className="h-3 w-3" />
      Fix proposed
    </span>
  ) : null

  // Acoustic anomalies (O5) render their dedicated module card — it shows
  // the structured payload (sound class, dB, severity tier) the generic row
  // cannot. Snooze/dismiss stay: the module's own buttons are decorative,
  // these two are the real finding actions.
  const acousticData: AcousticAnomalyData | null =
    isAcousticEvent(event) && event.data
      ? { ...event.data, finding_id: event.finding_id }
      : null

  const actionButtons = pending ? (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Loader2 className="h-3 w-3 animate-spin" />
      Working...
    </span>
  ) : (
    <>
      {proposeAction}
      <button
        onClick={onSnooze}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Clock className="h-3 w-3" />
        Snooze 7d
      </button>
      <button
        onClick={onDismiss}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <X className="h-3 w-3" />
        Dismiss
      </button>
    </>
  )

  return (
    <div className="border-b border-border px-4 py-3 hover:bg-muted/50">
      {acousticData ? (
        <div className="space-y-2">
          <AcousticAnomalyModule data={acousticData} />
          <div className="flex items-center gap-3">{actionButtons}</div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <div className={`rounded border px-1.5 py-0.5 ${colorClass}`}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground truncate">{event.title}</div>
            <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{secondLine}</div>
            <div className="flex items-center gap-3 mt-2">{actionButtons}</div>
          </div>
        </div>
      )}
    </div>
  )
}
