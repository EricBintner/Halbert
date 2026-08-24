/**
 * ProactiveEventsBadge — bell icon with live event count and dropdown.
 *
 * Uses the useBeingEvents hook to receive proactive events via SSE.
 * Shows a badge with the count of unread events and a dropdown panel
 * listing recent events with snooze/dismiss actions.
 *
 * Snooze/dismiss only remove the row after the server confirms the action;
 * failures surface an inline error bar at the top of the dropdown.
 *
 * Phase 7 / T7b.2 wiring.
 */

import { useState, useRef, useEffect } from 'react'
import { Bell, X, Clock, AlertTriangle, AlertCircle, Info, CheckCircle, Loader2 } from 'lucide-react'
import { useBeingEvents, type BeingEvent } from '../../hooks/useBeingEvents'

const SEVERITY_ICONS = {
  critical: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const SEVERITY_COLORS = {
  critical: 'text-red-400 bg-red-500/10 border-red-500/30',
  warning: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  info: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
}

export function ProactiveEventsBadge() {
  const { events, snooze, dismiss, pendingActions, actionError, clearActionError } = useBeingEvents()
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

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={toggleOpen}
        className="relative p-2 rounded-lg hover:bg-zinc-800 transition-colors"
        title="Proactive events"
      >
        <Bell className="h-5 w-5 text-zinc-400" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-96 max-h-[500px] overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl z-50">
          <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
            <span className="text-sm font-medium text-zinc-200">Proactive Events</span>
            <button onClick={() => setIsOpen(false)} className="p-1 hover:bg-zinc-800 rounded">
              <X className="h-4 w-4 text-zinc-400" />
            </button>
          </div>

          {actionError && (
            <div className="flex items-start gap-2 border-b border-red-500/30 bg-red-500/10 px-4 py-2">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-red-400" />
              <span className="flex-1 text-xs text-red-400 break-words">{actionError}</span>
              <button
                onClick={clearActionError}
                className="p-0.5 hover:bg-red-500/20 rounded shrink-0"
                title="Dismiss error"
              >
                <X className="h-3 w-3 text-red-400" />
              </button>
            </div>
          )}

          <div className="max-h-[400px] overflow-y-auto">
            {events.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-zinc-500">
                <CheckCircle className="h-8 w-8 mx-auto mb-2 text-zinc-600" />
                No active events
              </div>
            ) : (
              events.map((event) => (
                <EventRow
                  key={event.id}
                  event={event}
                  pending={pendingActions.has(event.id)}
                  onSnooze={() => handleSnooze(event)}
                  onDismiss={() => handleDismiss(event)}
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
}: {
  event: BeingEvent
  pending: boolean
  onSnooze: () => void
  onDismiss: () => void
}) {
  const Icon = SEVERITY_ICONS[event.severity] || Info
  const colorClass = SEVERITY_COLORS[event.severity] || SEVERITY_COLORS.info

  return (
    <div className="border-b border-zinc-800 px-4 py-3 hover:bg-zinc-800/50">
      <div className="flex items-start gap-2">
        <div className={`rounded border px-1.5 py-0.5 ${colorClass}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-zinc-200 truncate">{event.title}</div>
          <div className="text-xs text-zinc-400 mt-0.5 line-clamp-2">{event.body}</div>
          <div className="flex items-center gap-3 mt-2">
            {pending ? (
              <span className="flex items-center gap-1 text-xs text-zinc-500">
                <Loader2 className="h-3 w-3 animate-spin" />
                Working...
              </span>
            ) : (
              <>
                <button
                  onClick={onSnooze}
                  className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <Clock className="h-3 w-3" />
                  Snooze 7d
                </button>
                <button
                  onClick={onDismiss}
                  className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <X className="h-3 w-3" />
                  Dismiss
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
