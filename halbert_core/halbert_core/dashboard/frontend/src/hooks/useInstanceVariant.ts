// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useInstanceVariant — this instance's Halbert variant, from GET /api/instance/info.
 *
 * The variant is a deployment fact about the instance the dashboard is
 * attached to (sysadmin, home), resolved backend-side the same
 * way service gating resolves it, so the UI and the launched services can
 * never disagree about what this instance is.
 *
 * One fetch on mount, no polling: a variant does not change while the page
 * is open — switching instances reloads the page — so a loop would only add
 * traffic. A failure leaves `null`, which callers must read as "unknown", not
 * "sysadmin": feature surfaces that hide things by variant stay open rather
 * than silently shrinking on the machine that needs them.
 */

import { useEffect, useState } from 'react';
import { apiUrl } from '@/lib/apiBase';

export function useInstanceVariant(): string | null {
  const [variant, setVariant] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl('/api/instance/info'));
        if (!res.ok) return;
        const data = (await res.json()) as { variant?: unknown };
        if (!cancelled && typeof data.variant === 'string') setVariant(data.variant);
      } catch {
        // Unknown variant — the caller keeps its unfiltered surface.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return variant;
}

export default useInstanceVariant;