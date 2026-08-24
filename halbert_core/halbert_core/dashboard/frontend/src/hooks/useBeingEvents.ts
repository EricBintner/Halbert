/**
 * Being Events Hook
 *
 * React hook for receiving proactive events from the being via SSE.
 * Follows the pattern from useAgentStream.ts.
 *
 * Phase 7 / T7b.2.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface BeingEvent {
  id: string;
  type: 'finding' | 'morning_report' | 'approval_request' | 'system_anomaly';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  body: string;
  finding_id?: string;
  proposal_id?: string;
  created_at: string;
}

interface UseBeingEventsResult {
  events: BeingEvent[];
  snooze: (eventId: string, days?: number) => Promise<void>;
  dismiss: (eventId: string, reason?: string) => Promise<void>;
  clear: () => void;
}

// -----------------------------------------------------------------------------

export function useBeingEvents(): UseBeingEventsResult {
  const [events, setEvents] = useState<BeingEvent[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource('/api/being/events');
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: BeingEvent = JSON.parse(e.data);
        setEvents((prev) => {
          // Avoid duplicates
          if (prev.some((p) => p.id === event.id)) return prev;
          return [event, ...prev].slice(0, 100);
        });
      } catch (err) {
        console.error('Failed to parse being event:', err);
      }
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      // Auto-reconnect after 3 seconds
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = setTimeout(() => connect(), 3000);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, [connect]);

  const snooze = useCallback(async (eventId: string, days: number = 7) => {
    try {
      await fetch(`/api/being/events/${eventId}/snooze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });
      // Remove from local list
      setEvents((prev) => prev.filter((e) => e.id !== eventId));
    } catch (err) {
      console.error('Failed to snooze event:', err);
    }
  }, []);

  const dismiss = useCallback(async (eventId: string, reason: string = '') => {
    try {
      await fetch(`/api/being/events/${eventId}/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      // Remove from local list
      setEvents((prev) => prev.filter((e) => e.id !== eventId));
    } catch (err) {
      console.error('Failed to dismiss event:', err);
    }
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
  }, []);

  return { events, snooze, dismiss, clear };
}
