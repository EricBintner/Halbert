// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTimeline — the stored conversation, paged.
 *
 * One conversation. The first page (newest 50 turns) loads on mount; older
 * pages are fetched with `before=<oldest turn id>` and prepended; the turn
 * that just finished streaming is appended locally so the page does not have
 * to refetch to show what it just watched happen — with one narrow read
 * after it for the row ids the stream does not carry, because "Forget this"
 * needs them. A thread chip click loads the window `around=<turn id>`
 * instead (replacing the page and scrolling to that turn); `loadLatest`
 * returns to the newest page. Turns are grouped by local calendar day for
 * the dividers, and those labels follow the clock across midnight.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '@/lib/api';
import { isLocalTurnId } from '@/lib/turnFromSession';
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
  /**
   * Back to the newest page after a `loadAround`. Clears `anchored`.
   *
   * Resolves `true` only when a page actually came back. Failure is otherwise
   * the only outcome this hook reports (`loadFailed`), which leaves the one
   * caller that has to say something — the "Try again" button, pressed by
   * someone who cannot see the page fill — with nothing to say on success.
   * `false` also covers a call that coalesced with a request already in
   * flight: that call did not load anything, whatever the other one does.
   */
  loadLatest: () => Promise<boolean>;
  /** True while the page is a window around an earlier turn, not the newest page. */
  anchored: boolean;
  /**
   * No-op while `anchored`: the turn is already persisted and returns on
   * `loadLatest`. Otherwise the turn is appended and its stored row ids are
   * read back straight after — the stream carries the turn id and no row
   * ids, and "Forget this" redacts by row id.
   */
  appendLive: (turn: TimelineTurn) => void;
  /**
   * True when the mount-time load could not reach the server (network error,
   * backend restarting). An empty `turns` for this reason is not the same
   * as an empty `turns` because there is truly no history yet — a consumer
   * gating a "first time we've spoken" greeting on `turns.length === 0` must
   * also check `!loadFailed`, or a restart-timed request shows that greeting
   * over a real stored conversation. Cleared by any later successful load,
   * and by the start of a `loadLatest` — which writes it again if that
   * request fails too, so a retry that fails is a state TRANSITION and not a
   * silent re-write of `true` (the failure notice is announced on the
   * transition; see loadLatest).
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

/** Local midnight of a YYYY-MM-DD key, as a Date. */
export function dateOfDayKey(dayKey: string): Date {
  const [y, m, d] = dayKey.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/**
 * How long until the local calendar day rolls over.
 *
 * Built with the local Date constructor rather than by adding 86_400_000, so
 * a DST boundary makes the wait an hour longer or shorter instead of landing
 * the timer an hour on the wrong side of midnight.
 *
 * The floor is defensive, not load-bearing: `next` is the start of the
 * following local day, so it is always strictly after `now` and the shortest
 * honest answer is 1ms. It stays because the timer re-arms from its own
 * callback (see the effect below) — a 0 that ever did come out of a strange
 * clock would spin that chain instead of waiting.
 */
export function msUntilNextMidnight(now: Date = new Date()): number {
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return Math.max(1, next.getTime() - now.getTime());
}

/** 'Today' | 'Yesterday' | 'Thu, Jul 14' — with the year when it is not this year. */
export function dayLabel(dayKey: string, now: Date = new Date()): string {
  if (dayKey === dayKeyOf(now.getTime())) return 'Today';
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey === dayKeyOf(yesterday.getTime())) return 'Yesterday';
  const date = dateOfDayKey(dayKey);
  const options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' };
  if (date.getFullYear() !== now.getFullYear()) options.year = 'numeric';
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

/** True for a row the server has not named yet (turnFromSession folds -1). */
function unnamed(row: { messageId: number } | null): boolean {
  return row !== null && row.messageId < 0;
}

/** A turn appended live that still needs its row ids read back. */
function needsMessageIds(turn: TimelineTurn): boolean {
  return !isLocalTurnId(turn.turnId) && (unnamed(turn.user) || unnamed(turn.assistant));
}

/**
 * How long the second read-back waits (see hydrateMessageIds).
 *
 * Long enough for `end_turn` to finish writing a row the first read missed,
 * short enough that an admin who reaches for "Forget this" straight after
 * pressing Stop finds the whole turn forgettable by the time they have
 * confirmed.
 */
const HYDRATE_RETRY_MS = 1_500;

/**
 * The live copy of a turn, wearing the row ids the store gave the same turn.
 *
 * ONLY the ids. What is on screen is the turn the page watched happen —
 * its terminals, its diffs, the reply as it streamed — and re-reading a row
 * is not a reason to replace any of that. Returns the same object when
 * there is nothing to add, so a hydration that arrives after the server's
 * own copy has landed (a `loadLatest` racing it) is a no-op rather than a
 * re-render.
 */
function withMessageIds(local: TimelineTurn, stored: TimelineTurn): TimelineTurn {
  const user =
    local.user && unnamed(local.user) && stored.user && !unnamed(stored.user)
      ? { ...local.user, messageId: stored.user.messageId }
      : local.user;
  const assistant =
    local.assistant && unnamed(local.assistant) && stored.assistant && !unnamed(stored.assistant)
      ? { ...local.assistant, messageId: stored.assistant.messageId }
      : local.assistant;
  if (user === local.user && assistant === local.assistant) return local;
  return { ...local, user, assistant };
}

export function useTimeline(pageSize = 50): UseTimelineReturn {
  const [turns, setTurns] = useState<TimelineTurn[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [anchored, setAnchored] = useState(false);
  const [currentThread, setCurrentThread] = useState<TimelineCurrentThread | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  // Page loads supersede each other rather than blocking each other.
  //
  // This used to be a single boolean that every loader checked and returned
  // early on, so a request arriving during another one was silently dropped
  // — including the "Try again" button, whose whole contract (see
  // loadLatest) is that the admin perceives its outcome, and a deep link's
  // loadAround fired while the mount load was still running (R11-10). Now
  // each load takes a ticket; a response whose ticket is no longer the
  // newest writes nothing, which is also what an abort would have bought
  // without needing one plumbed through the shared api layer.
  const requestSeq = useRef(0);
  const nextTicket = () => ++requestSeq.current;
  const isCurrent = (ticket: number) => ticket === requestSeq.current;
  // Turn to scroll to once the page that contains it has rendered.
  const scrollTarget = useRef<string | null>(null);
  // Turns whose row ids are being read back right now (see hydrateMessageIds).
  const hydrating = useRef<Set<string>>(new Set());
  // Pending second attempts, so unmounting cancels them.
  const hydrateTimers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  // The local calendar day, as YYYY-MM-DD. State, not a call to Date.now()
  // inside the memo below: a page left open across midnight has to relabel
  // its dividers without anything else changing (see the timer below).
  const [today, setToday] = useState(() => dayKeyOf(Date.now()));

  // One timer, re-armed once a night — not one per render, and not a poll.
  //
  // The callback arms the next one itself, and does it whether or not the
  // day it just read differs from the one in state. Re-arming from a
  // `[today]` effect instead looks equivalent and is not: a timer that
  // fires a millisecond EARLY (a browser is not obliged to be late, and a
  // backwards clock step near midnight — an NTP correction — moves the
  // deadline under a pending timer) reads the same day key it already
  // holds, React bails out of the identical write, the effect never re-runs
  // and nothing schedules a replacement. The dividers then say "Today" over
  // a conversation from last week for as long as the page stays open.
  //
  // Firing late is still correct on its own terms: the day is read from the
  // clock at that moment, not assumed. A machine asleep over midnight wakes
  // up and relabels.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => {
      timer = setTimeout(() => {
        setToday(dayKeyOf(Date.now()));
        arm();
      }, msUntilNextMidnight());
    };
    arm();
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const ticket = nextTicket();
    api
      .getTimeline({ limit: pageSize })
      .then((page) => {
        if (cancelled || !isCurrent(ticket)) return;
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
        if (cancelled || !isCurrent(ticket)) return;
        console.warn('[TIMELINE] initial load failed:', err);
        setLoadFailed(true);
      })
      .finally(() => {
        if (!cancelled && isCurrent(ticket)) setLoading(false);
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
    if (!hasMore || turns.length === 0) return;
    const ticket = nextTicket();
    setLoading(true);
    try {
      const page = await api.getTimeline({ before: turns[0].turnId, limit: pageSize });
      if (!isCurrent(ticket)) return;
      setTurns((prev) => mergeOlder(page.turns, prev));
      setHasMore(page.hasMore);
      setLoadFailed(false);
    } catch (err) {
      if (!isCurrent(ticket)) return;
      console.warn('[TIMELINE] older page failed:', err);
    } finally {
      if (isCurrent(ticket)) setLoading(false);
    }
  }, [hasMore, turns, pageSize]);

  const loadAround = useCallback(async (turnId: string) => {
    if (!turnId) return;
    const ticket = nextTicket();
    setLoading(true);
    try {
      const page = await api.getTimeline({ around: turnId, limit: pageSize });
      if (!isCurrent(ticket)) return;
      if (page.turns.length === 0) return; // unknown id: keep what is on screen
      scrollTarget.current = turnId;
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setAnchored(true);
      setLoadFailed(false);
    } catch (err) {
      if (!isCurrent(ticket)) return;
      console.warn('[TIMELINE] around page failed:', err);
    } finally {
      if (isCurrent(ticket)) setLoading(false);
    }
  }, [pageSize]);

  const loadLatest = useCallback(async (): Promise<boolean> => {
    const ticket = nextTicket();
    setLoading(true);
    // `loadFailed` is the retry's ONLY outcome an admin can perceive: the
    // failure notice is announced on the transition into it (AgentChat), and
    // this is the call behind "Try again". Clearing it before the request and
    // writing it again in the catch is what makes a second failure a
    // transition at all — leaving `true` in place is a write React bails out
    // of, and the admin who pressed the button hears nothing and cannot tell
    // a failed retry from one that has not finished.
    setLoadFailed(false);
    try {
      const page = await api.getTimeline({ limit: pageSize });
      if (!isCurrent(ticket)) return false;
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setCurrentThread(page.currentThread);
      setAnchored(false);
      setLoadFailed(false);
      // Said out loud by the caller that asked for it. A retry that works is
      // otherwise silent: the page fills, which is not something a screen
      // reader announces, so the admin who pressed the button is left
      // listening to a button that appears to have done nothing.
      return true;
    } catch (err) {
      if (!isCurrent(ticket)) return false;
      console.warn('[TIMELINE] latest page failed:', err);
      setLoadFailed(true);
      return false;
    } finally {
      if (isCurrent(ticket)) setLoading(false);
    }
  }, [pageSize]);

  /**
   * Give a just-appended turn the row ids the store wrote for it.
   *
   * The stream tells the page which TURN was persisted (turn_persisted) and
   * never which rows, so `turnFromSession` folds both rows in at -1 — and
   * "Forget this" redacts by row id. The control was therefore missing on
   * the one turn an admin has just had, which is precisely the moment
   * someone realises what they pasted, and came back only after a reload.
   *
   * `around=<turn id>&limit=1` is the narrowest thing the timeline endpoint
   * can be asked (the store returns that turn alone: `list_turns` splits a
   * limit of 1 into 0 before and 1 from the anchor forwards), and only the
   * ids are taken from the answer. Nothing here touches `hasMore`,
   * `loading`, `currentThread` or the anchor: this is not a page load, and
   * a page that started paging while it was in flight must not be disturbed.
   *
   * A failure is left silent on screen. The ids come back on the next load
   * either way, and the alternative — a red banner because a background
   * read the admin never asked for did not answer — says nothing they can
   * act on. The turn keeps -1, so nothing offers to forget a row it cannot
   * name.
   *
   * ONE delayed second attempt, when the first came back with a row still
   * unnamed. This is not defensive retrying: it is the Stop case exactly.
   * `begin_turn` writes the user row before the model is called and
   * `end_turn` writes the reply as the turn unwinds, so a turn folded in the
   * instant the page stopped listening is read back BEFORE the store has
   * finished writing it. With a single read, that reply row stays unnamed
   * until an unrelated page load — and "Forget this" can only forget half of
   * the one turn someone pressed Stop because of. Two attempts, then it
   * waits for the next load: a poll for a row that may never be written
   * (a turn abandoned before `end_turn`) is a request loop with no end.
   */
  const hydrateMessageIds = useCallback(async (turn: TimelineTurn) => {
    const turnId = turn.turnId;

    const attempt = async (local: TimelineTurn, retriesLeft: number): Promise<void> => {
      if (hydrating.current.has(turnId)) return;
      hydrating.current.add(turnId);
      // The local turn as it stands after this read — used only to decide
      // whether asking again could tell us anything new.
      let merged = local;
      try {
        const page = await api.getTimeline({ around: turnId, limit: 1 });
        const stored = page.turns.find((t) => t.turnId === turnId);
        if (stored) {
          merged = withMessageIds(local, stored);
          setTurns((prev) => {
            const idx = prev.findIndex((t) => t.turnId === turnId);
            if (idx === -1) return prev;
            const next = withMessageIds(prev[idx], stored);
            if (next === prev[idx]) return prev;
            const copy = prev.slice();
            copy[idx] = next;
            return copy;
          });
        }
      } catch (err) {
        console.warn('[TIMELINE] could not read back the row ids of', turnId, err);
      } finally {
        hydrating.current.delete(turnId);
      }
      if (retriesLeft <= 0 || !needsMessageIds(merged)) return;
      const timer = setTimeout(() => {
        hydrateTimers.current.delete(timer);
        void attempt(merged, retriesLeft - 1);
      }, HYDRATE_RETRY_MS);
      hydrateTimers.current.add(timer);
    };

    await attempt(turn, 1);
  }, []);

  // A pending second attempt outlives nothing: the page can be closed in
  // the seconds between the two reads.
  useEffect(() => {
    const timers = hydrateTimers.current;
    return () => {
      timers.forEach(clearTimeout);
      timers.clear();
    };
  }, []);

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
    // A turn the store never confirmed has an id only this page knows, so
    // there is nothing to ask for; a turn that already carries its ids has
    // nothing to learn.
    if (needsMessageIds(turn)) void hydrateMessageIds(turn);
  }, [anchored, hydrateMessageIds]);

  // `today` is a dependency, not decoration: without it a page left open
  // across midnight kept yesterday's "Today" divider over today's turns
  // until the turn list next changed.
  const byDay = useMemo(() => groupByDay(turns, dateOfDayKey(today)), [turns, today]);

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
