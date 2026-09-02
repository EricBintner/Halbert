// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Being Events Hook
 *
 * React hook for receiving proactive events from the being via SSE.
 * Follows the pattern from useAgentStream.ts.
 *
 * Phase 7 / T7b.2.
 *
 * Snooze/dismiss send finding_id when present (the server resolves either
 * the ProactiveEvent id or the finding id) and only remove the event from
 * local state after a 2xx response — on failure the event stays visible and
 * an actionError is surfaced for the UI to render.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { apiUrl } from '@/lib/apiBase';
import type { AcousticAnomalyData } from '@/components/audio';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

/** The Four Whys of the finding an event projects (C2-02). */
export interface FindingWhy {
  /** What triggered this detection right now. */
  now: string;
  /** Consequence if ignored — the one line the row shows. */
  care: string;
  /** The reasoning / evidence. */
  so: string;
  /** Provenance refs (path:line, log cursors, snapshot ids). */
  trust: string[];
}

export interface BeingEvent {
  id: string;
  // The user-facing channel (proactive/events.py USER_FACING_EVENT_TYPES).
  // 'acoustic' is accepted alongside the wire types: today the backend
  // publishes acoustic anomalies as type 'finding' + category 'acoustic'
  // (DetectorRunner._EVENT_CATEGORY) — discriminate with isAcousticEvent();
  // the union member keeps a future direct-acoustic publisher type-safe.
  type:
    | 'finding'
    | 'acoustic'
    | 'visual_finding'
    | 'morning_report'
    | 'approval_request'
    | 'system_anomaly'
    | 'reflex_fired'
    | 'reflex_escalate'
    | 'reflex_command_proposed';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  body: string;
  finding_id?: string;
  proposal_id?: string | null;
  created_at: string;
  category?: string;
  /** Structured payload (O5): present on acoustic findings — the exact
   * AcousticAnomalyData contract the AcousticAnomalyModule renders. */
  data?: AcousticAnomalyData | null;
  /** The finding's four whys — the interrupt justifies itself (C2-02).
   * Absent on events that are not findings. */
  why?: FindingWhy | null;
  /** Config paths the finding touches; what a proposal would change. */
  affected_paths?: string[] | null;
}

/**
 * True when the event is a finding without a proposal yet — the row can
 * offer "Propose fix" (POST /api/findings/{id}/propose). Acoustic findings
 * have no config fix to propose.
 */
export function canProposeFix(event: BeingEvent): boolean {
  return (
    event.type === 'finding' &&
    !!event.finding_id &&
    !event.proposal_id &&
    !isAcousticEvent(event)
  );
}

/**
 * True when the event is an acoustic anomaly finding, whatever discriminates
 * it on the wire: the category DetectorRunner assigns today, or a direct
 * 'acoustic' event type from a future publisher.
 */
export function isAcousticEvent(event: BeingEvent): boolean {
  return event.type === 'acoustic' || event.category === 'acoustic';
}

interface UseBeingEventsResult {
  events: BeingEvent[];
  snooze: (event: BeingEvent, days?: number) => Promise<boolean>;
  dismiss: (event: BeingEvent, reason?: string) => Promise<boolean>;
  /** Ask for the finding's proposal (J3-7 manual path). On success the
   * event gains its proposal_id and stays in the list. */
  propose: (event: BeingEvent) => Promise<boolean>;
  /** Ids of events with an in-flight snooze/dismiss request. */
  pendingActions: Set<string>;
  /** Error from the most recent failed snooze/dismiss, if any. */
  actionError: string | null;
  clearActionError: () => void;
  clear: () => void;
}

// -----------------------------------------------------------------------------

export function useBeingEvents(): UseBeingEventsResult {
  const [events, setEvents] = useState<BeingEvent[]>([]);
  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(apiUrl('/api/being/events'));
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

  const actOnEvent = useCallback(
    async (event: BeingEvent, action: 'snooze' | 'dismiss', body: Record<string, unknown>, query?: string): Promise<boolean> => {
      // Server resolves either the event id or the finding id; prefer the
      // finding id whenever the event carries one.
      const targetId = event.finding_id ?? event.id;
      setActionError(null);
      setPendingActions((prev) => new Set(prev).add(event.id));
      try {
        const url = apiUrl(`/api/being/events/${encodeURIComponent(targetId)}/${action}${query ? `?${query}` : ''}`);
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const detail = await resp.text().catch(() => '');
          throw new Error(
            `Failed to ${action} event (HTTP ${resp.status})${detail ? `: ${detail.slice(0, 120)}` : ''}`
          );
        }
        // Only remove from local state once the server confirmed the action.
        setEvents((prev) =>
          prev.filter((e) => e.id !== event.id && e.id !== targetId && e.finding_id !== targetId)
        );
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error(`Failed to ${action} event:`, err);
        setActionError(message);
        return false;
      } finally {
        setPendingActions((prev) => {
          const next = new Set(prev);
          next.delete(event.id);
          return next;
        });
      }
    },
    []
  );

  const snooze = useCallback(
    (event: BeingEvent, days: number = 7) =>
      actOnEvent(event, 'snooze', { days, finding_id: event.finding_id }, `days=${days}`),
    [actOnEvent]
  );

  const dismiss = useCallback(
    (event: BeingEvent, reason: string = '') =>
      actOnEvent(event, 'dismiss', { reason, finding_id: event.finding_id }),
    [actOnEvent]
  );

  const propose = useCallback(async (event: BeingEvent): Promise<boolean> => {
    const findingId = event.finding_id;
    if (!findingId) {
      setActionError('This event is not linked to a finding');
      return false;
    }
    setActionError(null);
    setPendingActions((prev) => new Set(prev).add(event.id));
    try {
      const resp = await fetch(
        apiUrl(`/api/findings/${encodeURIComponent(findingId)}/propose`),
        { method: 'POST' }
      );
      if (!resp.ok) {
        const detail = await resp.text().catch(() => '');
        throw new Error(
          `Failed to propose a fix (HTTP ${resp.status})${detail ? `: ${detail.slice(0, 160)}` : ''}`
        );
      }
      const body = await resp.json().catch(() => ({}));
      const proposalId: string | undefined = body?.proposal?.id;
      if (proposalId) {
        setEvents((prev) =>
          prev.map((e) =>
            e.id === event.id || e.finding_id === findingId ? { ...e, proposal_id: proposalId } : e
          )
        );
      }
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('Failed to propose a fix:', err);
      setActionError(message);
      return false;
    } finally {
      setPendingActions((prev) => {
        const next = new Set(prev);
        next.delete(event.id);
        return next;
      });
    }
  }, []);

  const clearActionError = useCallback(() => setActionError(null), []);

  const clear = useCallback(() => {
    setEvents([]);
  }, []);

  return { events, snooze, dismiss, propose, pendingActions, actionError, clearActionError, clear };
}
