// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * LiveRegion — the shell's two live regions (design §11): one polite
 * `role="status"` for the running commentary, one assertive `role="alert"`
 * for blocked-on-approval only.
 *
 * Visually hidden; fed by lib/announce. Assistive tech only speaks a live
 * region when its content CHANGES, so the same sentence twice ("New subject"
 * after "New subject") would be silent the second time. Each region therefore
 * empties first and fills a beat later, which makes every announcement a
 * change.
 *
 * That emptying is why the region is a QUEUE and not a variable. Two
 * sentences arriving in the same tick used to mean the second overwrote the
 * first before it was ever written — and `/model` always produces two (the
 * note in the stream, then the pill's switch announcement), so one of them
 * was always lost and what the user heard did not match what was on screen.
 * Each sentence now waits its turn.
 */

import { useEffect, useState } from 'react';
import { subscribeAnnouncements } from '../../lib/announce';

/** Empty → filled. Long enough to be a change, short enough to feel immediate. */
const REFILL_MS = 50;
/** How long a sentence stays in the region before the next one clears it. */
const HOLD_MS = 150;
/**
 * A burst is not a backlog. Beyond this, the oldest pending sentences are
 * dropped rather than made into a queue a screen-reader user has to sit
 * through before hearing anything current — the newest is always the one
 * that describes the screen they are on.
 */
const MAX_QUEUED = 4;

type RegionKey = 'status' | 'alert';

export function LiveRegion() {
  const [status, setStatus] = useState('');
  const [alertText, setAlertText] = useState('');

  useEffect(() => {
    const setters: Record<RegionKey, (text: string) => void> = {
      status: setStatus,
      alert: setAlertText,
    };
    const queues: Record<RegionKey, string[]> = { status: [], alert: [] };
    // The one timer per region that is currently in flight; also the flag for
    // "a drain is already running", so an announcement arriving mid-cycle
    // joins the queue instead of restarting it.
    const timers: Record<RegionKey, ReturnType<typeof setTimeout> | null> = {
      status: null,
      alert: null,
    };

    const drain = (key: RegionKey) => {
      const next = queues[key].shift();
      if (next === undefined) {
        timers[key] = null;
        return;
      }
      setters[key]('');
      timers[key] = setTimeout(() => {
        setters[key](next);
        // Held, not immediately overwritten: the sentence has to be in the
        // region long enough for assistive tech to pick the change up.
        timers[key] = setTimeout(() => drain(key), HOLD_MS);
      }, REFILL_MS);
    };

    const unsubscribe = subscribeAnnouncements((next, { assertive }) => {
      const key: RegionKey = assertive ? 'alert' : 'status';
      const queue = queues[key];
      queue.push(next);
      while (queue.length > MAX_QUEUED) queue.shift();
      if (!timers[key]) drain(key);
    });
    return () => {
      unsubscribe();
      if (timers.status) clearTimeout(timers.status);
      if (timers.alert) clearTimeout(timers.alert);
    };
  }, []);

  return (
    <>
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {status}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only">
        {alertText}
      </div>
    </>
  );
}

export default LiveRegion;
