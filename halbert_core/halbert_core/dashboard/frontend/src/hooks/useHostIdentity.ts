// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useHostIdentity — who this machine is, from GET /api/identity.
 *
 * The Sovereign Host surface opens with Halbert speaking as the host, so this
 * has to resolve on first paint with no scan, no profile on disk and no model
 * loaded. The endpoint is psutil/platform only; this hook adds a slow poll so
 * uptime and pool health stay honest while the app is open.
 */

import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '@/lib/apiBase';

export interface HostStoragePool {
  mount: string;
  device: string;
  fstype: string;
  total_gb: number;
  used_percent: number;
  healthy: boolean;
}

export interface HostIdentity {
  hostname: string;
  os: {
    name: string;
    version: string;
    pretty: string;
    platform: string;
    kernel: string;
    arch: string;
  };
  uptime: { seconds: number; human: string; boot_time: string };
  cpu: { cores: number; physical_cores: number; percent: number; temperature: number | null };
  memory: { total_gb: number; used_gb: number; percent: number };
  storage: { pools: HostStoragePool[]; healthy: number; total: number };
  load_average: { '1min': number; '5min': number; '15min': number };
  all_healthy: boolean;
  first_person: string;
  timestamp: string;
}

interface UseHostIdentityResult {
  identity: HostIdentity | null;
  loading: boolean;
  error: string | null;
}

const DEFAULT_POLL_MS = 30_000;

export function useHostIdentity(pollMs: number = DEFAULT_POLL_MS): UseHostIdentityResult {
  const [identity, setIdentity] = useState<HostIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(apiUrl('/api/identity'));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as HostIdentity;
        if (cancelled) return;
        hasLoadedRef.current = true;
        setIdentity(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        // Keep the last good identity across transient failures — the host
        // does not stop being itself because one poll missed.
        if (!hasLoadedRef.current) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    const timer = setInterval(load, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollMs]);

  return { identity, loading, error };
}

export default useHostIdentity;
