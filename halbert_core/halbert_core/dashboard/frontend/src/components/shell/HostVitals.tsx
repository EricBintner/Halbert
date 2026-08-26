// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * HostVitals — the machine's own body readout, top of the context stage.
 *
 * Headed by the name the machine was given, with the hostname kept below it
 * as a technical fact alongside the OS and kernel.
 *
 * Permanently mounted in engaged mode. It is not a widget the user summons;
 * it is the host's proprioception, always on screen, so "I am running hot" is
 * something you can see as well as be told.
 */

import { useHostIdentity } from '../../hooks/useHostIdentity';

interface HostVitalsProps {
  className?: string;
}

// Vitals refresh faster than identity facts like uptime need to.
const VITALS_POLL_MS = 5_000;

function barColor(percent: number): string {
  if (percent >= 90) return 'bg-error';
  if (percent >= 75) return 'bg-warning';
  return 'bg-success';
}

function Meter({ label, percent, detail }: { label: string; percent: number; detail?: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-[10px]">
        <span className="uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className="font-mono text-foreground">{detail ?? `${clamped.toFixed(0)}%`}</span>
      </div>
      <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor(clamped)}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

export function HostVitals({ className = '' }: HostVitalsProps) {
  const { identity, error } = useHostIdentity(VITALS_POLL_MS);

  if (!identity) {
    return (
      <div className={`px-3 py-3 text-[11px] text-muted-foreground ${className}`}>
        {error ? `Vitals unavailable (${error})` : 'Reading vitals…'}
      </div>
    );
  }

  const { cpu, memory, storage, uptime, load_average: load } = identity;
  const strained = storage.pools.filter((p) => !p.healthy);

  return (
    <div className={`px-3 py-3 space-y-3 ${className}`}>
      {/* Who and how long */}
      <div className="flex items-center gap-2 min-w-0">
        <span
          className={`h-2 w-2 rounded-full shrink-0 ${
            identity.all_healthy ? 'bg-success' : 'bg-warning'
          }`}
        />
        <span
          className="font-mono text-xs text-foreground truncate"
          title={`${identity.display_name} · ${identity.hostname}`}
        >
          {identity.display_name}
        </span>
        <span className="ml-auto text-[10px] font-mono text-muted-foreground shrink-0">
          up {uptime.human}
        </span>
      </div>

      <div
        className="text-[10px] font-mono text-muted-foreground truncate"
        title={`${identity.hostname} · ${identity.os.pretty} · ${identity.os.kernel} · ${identity.os.arch}`}
      >
        {identity.hostname} · {identity.os.pretty} · {identity.os.kernel}
      </div>

      {/* Body readout */}
      <div className="space-y-2.5">
        <Meter
          label="CPU"
          percent={cpu.percent}
          detail={`${cpu.percent.toFixed(0)}% · ${cpu.cores} cores${
            cpu.temperature ? ` · ${cpu.temperature.toFixed(0)}°C` : ''
          }`}
        />
        <Meter
          label="Memory"
          percent={memory.percent}
          detail={`${memory.used_gb.toFixed(1)} / ${memory.total_gb.toFixed(0)} GB`}
        />
        <Meter
          label="Load"
          percent={cpu.cores ? (load['1min'] / cpu.cores) * 100 : 0}
          detail={`${load['1min'].toFixed(2)} ${load['5min'].toFixed(2)} ${load['15min'].toFixed(2)}`}
        />
      </div>

      {/* Storage pools */}
      <div className="space-y-1 pt-1">
        <div className="flex items-baseline justify-between text-[10px]">
          <span className="uppercase tracking-wide text-muted-foreground">Storage</span>
          <span className="font-mono text-foreground">
            {storage.healthy}/{storage.total} healthy
          </span>
        </div>
        <div className="space-y-1">
          {storage.pools.slice(0, 5).map((pool) => (
            <div key={pool.mount} className="flex items-center gap-2 text-[10px] font-mono">
              <span
                className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                  pool.healthy ? 'bg-success/70' : 'bg-error'
                }`}
              />
              <span className="truncate text-foreground flex-1" title={pool.mount}>
                {pool.mount}
              </span>
              <span className={pool.healthy ? 'text-muted-foreground' : 'text-error'}>
                {pool.used_percent.toFixed(0)}%
              </span>
            </div>
          ))}
          {storage.pools.length > 5 && (
            <div className="text-[10px] font-mono text-muted-foreground">
              +{storage.pools.length - 5} more
            </div>
          )}
        </div>
        {strained.length > 0 && (
          <p className="text-[10px] text-warning pt-0.5">
            {strained.length === 1
              ? `${strained[0].mount} is running full.`
              : `${strained.length} pools are running full.`}
          </p>
        )}
      </div>
    </div>
  );
}

export default HostVitals;
