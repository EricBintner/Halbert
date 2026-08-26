// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
export interface PlanLimitTier {
  tier_key: string;
  tier_label: string;
  concurrent: number;
  source_url: string;
}

export interface PlanLimitProvider {
  label: string;
  auto_detect: boolean;
  auto_detect_reason?: string;
  tiers: PlanLimitTier[];
}

export interface PlanLimitsTable {
  version: number;
  providers: Record<string, PlanLimitProvider>;
}

export interface PlanDropdownProps {
  /** Provider key in the limits table — e.g. "ollama_cloud", "openai". */
  providerKey: string;
  /** Current selection. Either a tier_key, "auto", "custom", or undefined. */
  value: string | undefined;
  /** Custom override value (used when value === "custom"). */
  customConcurrent: number;
  /** Pre-fetched limits table. Required for storybook; in production the
   * EndpointManager fetches once and passes down. */
  limits: PlanLimitsTable;
  /** Called when the user picks a tier OR types a custom number. */
  onChange: (next: { plan_tier: string; cloud_concurrency: number }) => void;
}

const SENTINEL_AUTO = 'auto';
const SENTINEL_CUSTOM = 'custom';

export function PlanDropdown(props: PlanDropdownProps) {
  const { providerKey, value, customConcurrent, limits, onChange } = props;
  const provider = limits.providers[providerKey];

  if (!provider) {
    return (
      <div className="text-xs text-amber-400">
        No plan options for provider <code>{providerKey}</code>.
      </div>
    );
  }

  // No local state — `customConcurrent` is the single source of truth (parent-controlled).
  // The input below is fully controlled; every change fires onChange so the
  // parent updates customConcurrent on the next render.
  const selectedTier = provider.tiers.find((t) => t.tier_key === value);

  // Compute the active concurrent based on selection.
  const activeConcurrent =
    value === SENTINEL_AUTO ? 0 :  // 0 = "auto" sentinel for backend
    value === SENTINEL_CUSTOM ? (customConcurrent || 1) :
    (selectedTier?.concurrent ?? 0);

  const sourceUrl = selectedTier?.source_url ?? provider.tiers[0]?.source_url ?? '';

  let sourceHost = '';
  if (sourceUrl) {
    try {
      sourceHost = new URL(sourceUrl).host;
    } catch {
      sourceHost = '';
    }
  }

  return (
    <div className="space-y-1.5">
      <label className="text-[11px] uppercase tracking-wider text-text-muted">Plan</label>
      <select
        className="w-full bg-surface-raised border border-border rounded px-2 py-1 text-sm"
        value={value ?? ''}
        onChange={(e) => {
          const next = e.target.value;
          if (next === '') {
            onChange({ plan_tier: '', cloud_concurrency: 0 });
          } else if (next === SENTINEL_AUTO) {
            onChange({ plan_tier: SENTINEL_AUTO, cloud_concurrency: 0 });
          } else if (next === SENTINEL_CUSTOM) {
            onChange({ plan_tier: SENTINEL_CUSTOM, cloud_concurrency: customConcurrent || 1 });
          } else {
            const tier = provider.tiers.find((t) => t.tier_key === next);
            onChange({ plan_tier: next, cloud_concurrency: tier?.concurrent ?? 0 });
          }
        }}
      >
        {(value === undefined || value === '') && (
          <option value="" disabled>— pick a plan —</option>
        )}
        {provider.auto_detect && (
          <option value={SENTINEL_AUTO}>Auto-detect from headers (recommended)</option>
        )}
        {provider.tiers.map((t) => (
          <option key={t.tier_key} value={t.tier_key}>
            {t.tier_label} ({t.concurrent} concurrent)
          </option>
        ))}
        <option value={SENTINEL_CUSTOM}>Custom…</option>
      </select>

      {value === SENTINEL_CUSTOM && (
        <input
          type="number"
          min={1}
          max={1000}
          value={customConcurrent || 1}
          onChange={(e) => {
            const parsed = parseInt(e.target.value || '1', 10);
            const safe = Number.isFinite(parsed) ? parsed : 1;
            const clamped = Math.max(1, Math.min(1000, safe));
            onChange({ plan_tier: SENTINEL_CUSTOM, cloud_concurrency: clamped });
          }}
          className="w-full bg-surface-raised border border-border rounded px-2 py-1 text-sm"
        />
      )}

      {sourceHost && (
        <p className="text-[10px] text-text-muted">
          <span aria-hidden="true">ⓘ</span> From{' '}
          <a href={sourceUrl} target="_blank" rel="noreferrer" className="underline">
            {sourceHost}
          </a>
        </p>
      )}

      <div className="text-[11px] text-text-base mt-2 pt-2 border-t border-border">
        Active: <strong>{activeConcurrent === 0 ? 'auto' : `${activeConcurrent} concurrent`}</strong>
        {value === SENTINEL_AUTO && provider.auto_detect_reason && (
          <span className="ml-1 text-text-muted">({provider.auto_detect_reason})</span>
        )}
      </div>
    </div>
  );
}
