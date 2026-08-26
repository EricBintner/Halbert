// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useIntersectionDock — watches an element's visibility via IntersectionObserver.
 *
 * At <25% visibility (scrolling out of view), triggers docking so the tile can
 * be parked in the right-column accordion. At >=25% (scroll back into view),
 * triggers undocking. Callbacks are held in refs so dock/undock handler changes
 * never re-create the observer.
 */

import { useRef, useEffect, useState } from 'react';

interface UseIntersectionDockOptions {
  /** Visibility threshold below which docking triggers (0-1). Default 0.25. */
  threshold?: number;
  /** Called when element docks (visibility drops below threshold). */
  onDock?: () => void;
  /** Called when element undocks (visibility rises above threshold). */
  onUndock?: () => void;
}

interface UseIntersectionDockResult {
  ref: React.RefObject<HTMLElement>;
  isDocked: boolean;
  visibility: number;
}

export function useIntersectionDock(
  options: UseIntersectionDockOptions = {}
): UseIntersectionDockResult {
  const { threshold = 0.25, onDock, onUndock } = options;
  const ref = useRef<HTMLElement>(null);
  const [isDocked, setIsDocked] = useState(false);
  const [visibility, setVisibility] = useState(1);
  const onDockRef = useRef(onDock);
  const onUndockRef = useRef(onUndock);

  // Keep callbacks in refs to avoid re-creating the observer
  useEffect(() => {
    onDockRef.current = onDock;
    onUndockRef.current = onUndock;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        const ratio = entry.intersectionRatio;
        setVisibility(ratio);

        if (ratio < threshold && !isDocked) {
          setIsDocked(true);
          onDockRef.current?.();
        } else if (ratio >= threshold && isDocked) {
          setIsDocked(false);
          onUndockRef.current?.();
        }
      },
      { threshold: [0, threshold, 0.5, 1.0] }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, isDocked]);

  return { ref, isDocked, visibility };
}
