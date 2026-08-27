// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * LiveRegion — the shell's two live regions (design §11): one polite
 * `role="status"` for the running commentary, one assertive `role="alert"`
 * for blocked-on-approval only.
 *
 * Visually hidden; fed by lib/announce. Assistive tech only speaks a live
 * region when its content CHANGES, so the same sentence twice ("New subject"
 * after "New subject") would be silent the second time. Each region empties
 * first and fills a beat later, which makes every announcement a change.
 */

import { useEffect, useState } from 'react';
import { subscribeAnnouncements } from '../../lib/announce';

const REFILL_MS = 50;

export function LiveRegion() {
  const [status, setStatus] = useState('');
  const [alertText, setAlertText] = useState('');

  useEffect(() => {
    const timers: Record<'status' | 'alert', ReturnType<typeof setTimeout> | null> = {
      status: null,
      alert: null,
    };
    const unsubscribe = subscribeAnnouncements((next, { assertive }) => {
      const key = assertive ? 'alert' : 'status';
      const set = assertive ? setAlertText : setStatus;
      set('');
      const pending = timers[key];
      if (pending) clearTimeout(pending);
      timers[key] = setTimeout(() => set(next), REFILL_MS);
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
