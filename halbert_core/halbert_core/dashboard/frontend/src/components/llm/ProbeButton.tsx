// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react';
import { Activity, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '@/components/prep-primitives/Button';
import { cn } from '@/lib/utils';
import { apiBase } from '@/lib/apiBase';

// ── Types ─────────────────────────────────────────────────────────

/** Phase 119 Phase C: per-probe payload returned by POST /compute/endpoint-probe. */
export interface ProbeResult {
  endpoint_id: string;
  probed_at: number;
  burst_size: number;
  wall_clock_ms: { p50: number; p90: number; p99: number };
  saturation_point: number | null;
  saturation_method: 'latency_staircase' | 'header' | 'none';
  recommended_concurrent: number | null;
  successes: number;
  errors: number;
  histogram_path: string | null;
}

export interface ProbeButtonProps {
  /** Saved endpoint id to probe. Required — probing the form-only state isn't supported. */
  endpointId: string;
  /** How many parallel requests to fire (default 20, max 50). */
  burstSize?: number;
  /** Daemon base URL. Defaults to same-origin. */
  baseUrl?: string;
  /** Called when the user clicks "Apply" on a successful probe — parent updates the cap. */
  onApply?: (recommendedConcurrent: number) => void;
  /** Called whenever a probe completes (errors included). Useful for parent telemetry. */
  onProbeComplete?: (result: ProbeResult | null, error?: string) => void;
  /** Optional: pre-supplied result for storybook. */
  initialResult?: ProbeResult;
  /** Optional: force a particular state for storybook. */
  initialState?: ProbeButtonState;
  /** Optional: how many seconds the probe took (for the inline summary). */
  initialDurationMs?: number;
  className?: string;
}

export type ProbeButtonState = 'idle' | 'probing' | 'done' | 'error';

// ── Component ─────────────────────────────────────────────────────

export function ProbeButton(props: ProbeButtonProps) {
  const {
    endpointId,
    burstSize = 20,
    baseUrl,
    onApply,
    onProbeComplete,
    initialResult,
    initialState,
    initialDurationMs,
    className,
  } = props;

  const [state, setState] = useState<ProbeButtonState>(initialState ?? (initialResult ? 'done' : 'idle'));
  const [result, setResult] = useState<ProbeResult | null>(initialResult ?? null);
  const [error, setError] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState<number>(initialDurationMs ?? 0);

  const root = (baseUrl ?? apiBase()).replace(/\/$/, '');

  const handleProbe = async () => {
    setState('probing');
    setError(null);
    const start = performance.now();
    try {
      const resp = await fetch(`${root}/compute/endpoint-probe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint_id: endpointId, burst_size: burstSize }),
      });
      const body = await resp.json();
      if (!resp.ok) {
        const msg =
          body?.error?.message ??
          body?.detail?.error?.message ??
          `Probe failed (HTTP ${resp.status})`;
        throw new Error(msg);
      }
      const data: ProbeResult = body?.data ?? body;
      setResult(data);
      setDurationMs(performance.now() - start);
      setState('done');
      onProbeComplete?.(data);
    } catch (e: any) {
      const msg = e?.message ?? 'probe failed';
      setError(msg);
      setState('error');
      onProbeComplete?.(null, msg);
    }
  };

  const handleApply = () => {
    if (result?.recommended_concurrent != null) {
      onApply?.(result.recommended_concurrent);
    }
  };

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className={cn('space-y-2', className)} data-testid="probe-button">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleProbe}
          disabled={state === 'probing'}
          className={cn(state === 'probing' && 'opacity-70')}
        >
          {state === 'probing' ? (
            <>
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              Probing {burstSize} parallel requests…
            </>
          ) : (
            <>
              <Activity className="w-3.5 h-3.5 mr-1.5" />
              Probe Capacity
            </>
          )}
        </Button>
        {state === 'idle' && !result && (
          <span className="text-[10px] text-text-subtle">
            Fires {burstSize} parallel cheap requests, measures latency curve.
          </span>
        )}
      </div>

      {state === 'error' && error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded border border-error/40 bg-error/10 px-3 py-2 text-xs text-error"
        >
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <div>
            <strong>Probe failed.</strong> {error}
          </div>
        </div>
      )}

      {state === 'done' && result && (
        <div className="rounded border border-success/40 bg-success/5 px-3 py-2 text-xs space-y-1.5">
          <div className="flex items-center gap-1.5 text-success font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Probed in {(durationMs / 1000).toFixed(1)}s · {result.successes}/{result.burst_size} ok
            {result.errors > 0 && (
              <span className="text-error/80 ml-1">({result.errors} errors)</span>
            )}
          </div>

          <ProbeSummaryGrid result={result} />

          {result.recommended_concurrent != null && (
            <div className="flex items-center gap-2 pt-1.5 border-t border-success/20">
              <Button type="button" size="sm" onClick={handleApply} disabled={!onApply}>
                Apply {result.recommended_concurrent} to plan
              </Button>
              <span className="text-[10px] text-text-subtle">
                {result.saturation_method === 'header'
                  ? 'From provider headers'
                  : `Detected via latency staircase at ${result.saturation_point} concurrent`}
              </span>
            </div>
          )}

          {result.recommended_concurrent == null && (
            <p className="text-[10px] italic text-text-subtle pt-1">
              No saturation detected within {result.burst_size} concurrent — endpoint
              has more headroom than this probe sampled.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────

function ProbeSummaryGrid({ result }: { result: ProbeResult }) {
  const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n)}ms`);
  return (
    <dl className="grid grid-cols-3 gap-2 text-[11px]">
      <div>
        <dt className="text-text-subtle">p50</dt>
        <dd className="tabular-nums font-medium text-text">{fmt(result.wall_clock_ms.p50)}</dd>
      </div>
      <div>
        <dt className="text-text-subtle">p90</dt>
        <dd className="tabular-nums font-medium text-text">{fmt(result.wall_clock_ms.p90)}</dd>
      </div>
      <div>
        <dt className="text-text-subtle">p99</dt>
        <dd className="tabular-nums font-medium text-text">{fmt(result.wall_clock_ms.p99)}</dd>
      </div>
      <div className="col-span-3 flex items-center gap-2 text-[11px] pt-1">
        <span className="text-text-subtle">Saturation:</span>
        <span className="font-medium text-text">
          {result.saturation_point != null
            ? `${result.saturation_point} concurrent`
            : 'none detected'}
        </span>
      </div>
    </dl>
  );
}

export default ProbeButton;
