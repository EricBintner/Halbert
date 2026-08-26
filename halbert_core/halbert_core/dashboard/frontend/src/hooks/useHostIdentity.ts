// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useHostIdentity — who this machine is, from GET /api/identity.
 *
 * The engaged surface opens with the machine speaking as itself, so this has
 * to resolve on first paint with no scan, no profile on disk and no model
 * loaded. The endpoint is psutil/platform only; this hook adds a slow poll so
 * uptime and pool health stay honest while the app is open.
 *
 * `display_name` is what the machine is *called* — the name chosen in
 * onboarding ("What should I call this computer?"). `hostname` is the DNS name,
 * a technical fact about the machine rather than its identity. Anything the
 * user reads should lead with `display_name`.
 *
 * One poll, many consumers: the mode switch, the greeting and the vitals panel
 * all want this data at different rates, so the fetch lives in a module-level
 * store that ticks at the shortest period any live consumer asked for. Three
 * components no longer mean three request loops.
 */

import { useEffect, useSyncExternalStore } from 'react';
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
  /** The name chosen in onboarding — what this machine is called. */
  display_name: string;
  /** The DNS/system hostname. A fact about the machine, not its name. */
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

export interface UseHostIdentityResult {
  identity: HostIdentity | null;
  loading: boolean;
  error: string | null;
}

const DEFAULT_POLL_MS = 30_000;

// -----------------------------------------------------------------------------
// Shared store — one fetch loop for every consumer
// -----------------------------------------------------------------------------

const listeners = new Set<() => void>();
const periods = new Map<number, number>();

let snapshot: UseHostIdentityResult = { identity: null, loading: true, error: null };
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight: Promise<void> | null = null;
let nextConsumerId = 1;

function emit(next: UseHostIdentityResult): void {
  snapshot = next;
  listeners.forEach((l) => l());
}

async function load(): Promise<void> {
  // Consumers mounting together share one request rather than racing.
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const res = await fetch(apiUrl('/api/identity'));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const identity = (await res.json()) as HostIdentity;
      emit({ identity, loading: false, error: null });
    } catch (err) {
      // Keep the last good identity across transient failures — the machine
      // does not stop being itself because one poll missed. Only surface an
      // error while we have never succeeded.
      emit({
        identity: snapshot.identity,
        loading: false,
        error: snapshot.identity
          ? snapshot.error
          : err instanceof Error
            ? err.message
            : String(err),
      });
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

function reschedule(): void {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
  if (periods.size === 0) return; // nobody mounted — stop polling entirely
  const shortest = Math.min(...periods.values());
  timer = setInterval(() => {
    void load();
  }, shortest);
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

function getSnapshot(): UseHostIdentityResult {
  return snapshot;
}

/**
 * Subscribe to the host's identity, refreshed at least every `pollMs`.
 *
 * The period is a request, not a guarantee: the shared loop runs at the
 * shortest period any mounted consumer asked for, so a component that only
 * needs the name can ask for a slow refresh without holding back the vitals.
 */
export function useHostIdentity(pollMs: number = DEFAULT_POLL_MS): UseHostIdentityResult {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    const id = nextConsumerId++;
    periods.set(id, pollMs);
    reschedule();
    void load();
    return () => {
      periods.delete(id);
      reschedule();
    };
  }, [pollMs]);

  return state;
}

/** Force a refresh (e.g. after the machine is renamed in settings). */
export function refreshHostIdentity(): Promise<void> {
  return load();
}

export default useHostIdentity;
