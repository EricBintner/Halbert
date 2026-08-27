// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTimeline — the stored conversation, paged.
 *
 * One conversation. The first page (newest 50 turns) loads on mount; older
 * pages are fetched with `before=<oldest turn id>` and prepended; the turn
 * that just finished streaming is appended locally so the page does not have
 * to refetch to show what it just watched happen. A thread chip click loads
 * the window `around=<turn id>` instead (replacing the page and scrolling to
 * that turn); `loadLatest` returns to the newest page. Turns are grouped by
 * local calendar day for the dividers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '@/lib/api';
import type { TimelineCurrentThread, TimelineTurn } from '@/types/timeline';

export interface TimelineDay {
  /** Local calendar day, YYYY-MM-DD. */
  dayKey: string;
  /** 'Today' | 'Yesterday' | 'Thu, Jul 14' (+ ', 2025' when not this year). */
  label: string;
  turns: TimelineTurn[];
}

export interface UseTimelineReturn {
  turns: TimelineTurn[];
  hasMore: boolean;
  /** True during the first load and while any page is in flight. */
  loading: boolean;
  loadOlder: () => Promise<void>;
  /**
   * Replace the page with the window around `turnId` (a thread chip click)
   * and scroll to that turn once it is rendered. Sets `anchored`.
   */
  loadAround: (turnId: string) => Promise<void>;
  /** Back to the newest page after a `loadAround`. Clears `anchored`. */
  loadLatest: () => Promise<void>;
  /** True while the page is a window around an earlier turn, not the newest page. */
  anchored: boolean;
  /** No-op while `anchored`: the turn is already persisted and returns on `loadLatest`. */
  appendLive: (turn: TimelineTurn) => void;
  /**
   * True when the mount-time load could not reach the server (network error,
   * backend restarting). An empty `turns` for this reason is not the same
   * as an empty `turns` because there is truly no history yet — a consumer
   * gating a "first time we've spoken" greeting on `turns.length === 0` must
   * also check `!loadFailed`, or a restart-timed request shows that greeting
   * over a real stored conversation. Cleared by any later successful load.
   */
  loadFailed: boolean;
  currentThread: TimelineCurrentThread | null;
  setCurrentThread: Dispatch<SetStateAction<TimelineCurrentThread | null>>;
  byDay: TimelineDay[];
}

const pad = (n: number) => String(n).padStart(2, '0');

/** Local calendar day of an epoch-ms timestamp, as YYYY-MM-DD. */
export function dayKeyOf(timestampMs: number): string {
  const d = new Date(timestampMs);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 'Today' | 'Yesterday' | 'Thu, Jul 14' — with the year when it is not this year. */
export function dayLabel(dayKey: string, now: Date = new Date()): string {
  if (dayKey === dayKeyOf(now.getTime())) return 'Today';
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey === dayKeyOf(yesterday.getTime())) return 'Yesterday';
  const [y, m, d] = dayKey.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' };
  if (y !== now.getFullYear()) options.year = 'numeric';
  return date.toLocaleDateString('en-US', options);
}

/** Group turns (already oldest-first) into consecutive local days. */
export function groupByDay(turns: TimelineTurn[], now: Date = new Date()): TimelineDay[] {
  const days: TimelineDay[] = [];
  for (const turn of turns) {
    const dayKey = dayKeyOf(turn.timestamp);
    const last = days[days.length - 1];
    if (last && last.dayKey === dayKey) {
      last.turns.push(turn);
    } else {
      days.push({ dayKey, label: dayLabel(dayKey, now), turns: [turn] });
    }
  }
  return days;
}

/** Older page in front of what is loaded, without duplicating overlaps. */
function mergeOlder(older: TimelineTurn[], current: TimelineTurn[]): TimelineTurn[] {
  const seen = new Set(current.map((t) => t.turnId));
  return [...older.filter((t) => !seen.has(t.turnId)), ...current];
}

/** Attribute selector for a turn article; ids are uuids but quote anyway. */
function turnSelector(turnId: string): string {
  return `[data-turn-id="${turnId.replace(/"/g, '\\"')}"]`;
}

export function useTimeline(pageSize = 50): UseTimelineReturn {
  const [turns, setTurns] = useState<TimelineTurn[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [anchored, setAnchored] = useState(false);
  const [currentThread, setCurrentThread] = useState<TimelineCurrentThread | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const inFlight = useRef(false);
  // Turn to scroll to once the page that contains it has rendered.
  const scrollTarget = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    inFlight.current = true;
    api
      .getTimeline({ limit: pageSize })
      .then((page) => {
        if (cancelled) return;
        setTurns(page.turns);
        setHasMore(page.hasMore);
        setCurrentThread(page.currentThread);
        setLoadFailed(false);
      })
      .catch((err) => {
        // The endpoint degrades to empty {turns: [], ...} on the server,
        // never a 500 — this catch is only reachable for an actual
        // transport failure (network down, backend mid-restart). `turns`
        // still lands empty either way, so `loadFailed` is the only signal
        // a consumer has to tell that apart from a genuinely new install.
        if (cancelled) return;
        console.warn('[TIMELINE] initial load failed:', err);
        setLoadFailed(true);
      })
      .finally(() => {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pageSize]);

  // After a loadAround the target article exists only once React has
  // committed the new page, so the scroll waits for that commit.
  useEffect(() => {
    const target = scrollTarget.current;
    if (!target) return;
    const el = document.querySelector(turnSelector(target));
    if (!el) return;
    scrollTarget.current = null;
    el.scrollIntoView({ block: 'center' });
  }, [turns]);

  const loadOlder = useCallback(async () => {
    if (inFlight.current || !hasMore || turns.length === 0) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ before: turns[0].turnId, limit: pageSize });
      setTurns((prev) => mergeOlder(page.turns, prev));
      setHasMore(page.hasMore);
      setLoadFailed(false);
    } catch (err) {
      console.warn('[TIMELINE] older page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [hasMore, turns, pageSize]);

  const loadAround = useCallback(async (turnId: string) => {
    if (inFlight.current || !turnId) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ around: turnId, limit: pageSize });
      if (page.turns.length === 0) return; // unknown id: keep what is on screen
      scrollTarget.current = turnId;
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setAnchored(true);
      setLoadFailed(false);
    } catch (err) {
      console.warn('[TIMELINE] around page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [pageSize]);

  const loadLatest = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ limit: pageSize });
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setCurrentThread(page.currentThread);
      setAnchored(false);
      setLoadFailed(false);
    } catch (err) {
      console.warn('[TIMELINE] latest page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [pageSize]);

  const appendLive = useCallback((turn: TimelineTurn) => {
    // While anchored the page is a historical window (loadAround), not the
    // tail of the conversation: splicing a live turn onto it would assert
    // an adjacency that is false (a "Today" turn at the end of, say, last
    // Tuesday's window). The turn is already persisted server-side, so it
    // is dropped here and simply reappears on the next loadLatest.
    if (anchored) return;
    setTurns((prev) => {
      const idx = prev.findIndex((t) => t.turnId === turn.turnId);
      if (idx === -1) return [...prev, turn];
      const next = prev.slice();
      next[idx] = turn;
      return next;
    });
  }, [anchored]);

  const byDay = useMemo(() => groupByDay(turns), [turns]);

  return {
    turns,
    hasMore,
    loading,
    loadOlder,
    loadAround,
    loadLatest,
    anchored,
    appendLive,
    loadFailed,
    currentThread,
    setCurrentThread,
    byDay,
  };
}

export default useTimeline;
