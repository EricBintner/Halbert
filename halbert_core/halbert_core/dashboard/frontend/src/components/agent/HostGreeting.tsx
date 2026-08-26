// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * HostGreeting — the conversation's opening state, spoken by the machine.
 *
 * This replaces the generic "AI assistant" landing card. The thesis of the
 * project is that Halbert *is* the host, so the first thing on screen is the
 * host identifying itself from live telemetry — hostname, OS, kernel, uptime,
 * cores, storage health — not a cartoon offering to answer questions about
 * Linux.
 *
 * Starter prompts are derived from what the machine actually looks like right
 * now (a full pool, a hot CPU), so they read as the host noticing its own
 * state rather than as canned suggestions.
 */

import { useHostIdentity, type HostIdentity } from '../../hooks/useHostIdentity';

interface HostGreetingProps {
  /** Fill a starter prompt into the composer. */
  onPrompt?: (prompt: string) => void;
  className?: string;
}

interface Starter {
  label: string;
  prompt: string;
  urgent?: boolean;
}

/** Prompts drawn from the host's current condition, most specific first. */
function startersFor(identity: HostIdentity | null): Starter[] {
  const starters: Starter[] = [];
  if (identity) {
    const strained = identity.storage.pools.filter((p) => !p.healthy);
    if (strained.length > 0) {
      starters.push({
        label: `Why is ${strained[0].mount} full?`,
        prompt: `Why is ${strained[0].mount} at ${strained[0].used_percent}% and what can I safely reclaim?`,
        urgent: true,
      });
    }
    if (identity.memory.percent >= 85) {
      starters.push({
        label: 'What is using my memory?',
        prompt: 'What is using my memory right now? Show the top processes by RSS.',
        urgent: true,
      });
    }
    starters.push({
      label: 'How are you feeling?',
      prompt: 'How are you feeling? Walk me through your current vitals and anything that looks off.',
    });
    starters.push({
      label: 'What changed recently?',
      prompt: 'What changed on you recently — packages, services, configuration?',
    });
  }
  starters.push({
    label: 'Show me your storage',
    prompt: 'Show me your storage layout: pools, mount points and free space.',
  });
  starters.push({
    label: 'What is running?',
    prompt: 'What services are running, and is anything failing or restarting?',
  });
  return starters.slice(0, 4);
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</span>
      <span className="text-xs font-mono text-zinc-300">{value}</span>
    </div>
  );
}

export function HostGreeting({ onPrompt, className = '' }: HostGreetingProps) {
  const { identity, loading, error } = useHostIdentity();
  const starters = startersFor(identity);

  return (
    <div className={`flex flex-col justify-center h-full px-6 py-8 max-w-2xl mx-auto ${className}`}>
      {/* Identity line — the host speaking in the first person */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`h-2 w-2 rounded-full ${
            identity?.all_healthy ? 'bg-emerald-400' : identity ? 'bg-amber-400' : 'bg-zinc-600'
          } ${identity ? 'animate-pulse' : ''}`}
        />
        <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
          {loading && !identity ? 'coming online' : identity?.all_healthy ? 'nominal' : 'attention'}
        </span>
      </div>

      <p className="text-lg leading-relaxed text-zinc-200">
        {identity ? (
          <>
            I am <span className="font-mono text-emerald-300">{identity.hostname}</span>{' '}
            <span className="text-zinc-400">
              ({identity.os.pretty}, {identity.os.platform} {identity.os.kernel})
            </span>
            . Uptime is <span className="text-zinc-100">{identity.uptime.human}</span>.{' '}
            {identity.all_healthy ? (
              <>
                All {identity.cpu.cores} cores and {identity.storage.total} storage
                {identity.storage.total === 1 ? ' pool' : ' pools'} are healthy.
              </>
            ) : (
              <>
                {identity.storage.healthy} of {identity.storage.total} storage
                {identity.storage.total === 1 ? ' pool' : ' pools'} healthy across{' '}
                {identity.cpu.cores} cores.
              </>
            )}{' '}
            What would you like to inspect or configure?
          </>
        ) : error ? (
          <span className="text-zinc-400">
            I cannot read my own vitals right now ({error}). The backend may still be
            starting — ask me anything and I will try.
          </span>
        ) : (
          <span className="text-zinc-500">Reading my own vitals…</span>
        )}
      </p>

      {/* Vital facts */}
      {identity && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-5 border-t border-zinc-800">
          <Fact label="CPU" value={`${identity.cpu.cores} cores · ${identity.cpu.percent.toFixed(0)}%`} />
          <Fact
            label="Memory"
            value={`${identity.memory.used_gb.toFixed(1)} / ${identity.memory.total_gb.toFixed(0)} GB`}
          />
          <Fact label="Load" value={identity.load_average['1min'].toFixed(2)} />
          <Fact
            label="Storage"
            value={`${identity.storage.healthy}/${identity.storage.total} healthy`}
          />
        </div>
      )}

      {/* Starters derived from the host's actual condition */}
      <div className="flex flex-wrap gap-2 mt-6">
        {starters.map((s) => (
          <button
            key={s.label}
            onClick={() => onPrompt?.(s.prompt)}
            className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
              s.urgent
                ? 'bg-amber-500/10 border-amber-500/40 text-amber-300 hover:bg-amber-500/20'
                : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default HostGreeting;
