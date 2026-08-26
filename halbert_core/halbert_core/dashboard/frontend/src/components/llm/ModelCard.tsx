// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Button } from '@/components/prep-primitives/Button';
import { Select } from '@/components/prep-primitives/Select';
import { SearchableSelect } from '@/components/prep-primitives/SearchableSelect';
import { InfoTooltip } from '@/components/prep-primitives/InfoTooltip';
import { cn } from '@/lib/utils';
import type { SavedEndpoint, EndpointTestResult, ModelSource } from '@/types/llm';
import { useState, type ReactNode } from 'react';
import { CheckCircle, AlertCircle, Download, Cloud, Server, Database, RefreshCw, Loader2 } from 'lucide-react';

export interface ModelCardProps {
  title: string;
  description: string;
  icon?: ReactNode;
  info?: string;
  infoLink?: string;
  
  // Current config
  enabled?: boolean;
  source?: ModelSource;
  endpoint?: string;
  model?: string;
  
  // Endpoint options
  endpoints: SavedEndpoint[];
  onEndpointChange?: (endpointId: string) => void;
  
  // Model selection
  availableModels?: string[];
  modelDetails?: Array<{ name: string; context_window?: string; context_tokens?: number; cost_tier?: string; batch_profile?: string; rate_limits?: { rpd?: number; rpm?: number }; batch_estimate?: { files_per_request: number; daily_file_capacity?: number }; license?: string; license_id?: string; license_url?: string; attribution?: string }>;
  onModelChange?: (model: string) => void;
  onRefreshModels?: () => void;
  loadingModels?: boolean;

  // On-demand Ollama Cloud models not in /api/tags (Phase 145: cloud discovery).
  // Shown in a separate "Cloud models (on-demand)" section when the user
  // toggles the "Show all cloud models" checkbox. Verified server-side via
  // /api/show, so only models the endpoint can actually serve are listed.
  cloudModels?: string[];
  loadingCloudModels?: boolean;
  onFetchCloudModels?: (endpointId: string) => Promise<string[]>;

  // HuggingFace download (optional)
  hfEnabled?: boolean;
  hfRepoId?: string;
  hfDownloaded?: boolean;
  hfDownloadProgress?: number;
  onHFDownload?: () => void;
  onSourceChange?: (source: ModelSource) => void;
  
  // Status
  status?: 'connected' | 'disconnected' | 'not-configured' | 'downloading' | 'loading';
  onTest?: () => void;
  testResult?: EndpointTestResult;
  testingConnection?: boolean;
  
  // Always on (keep loaded)
  alwaysOn?: boolean;
  onAlwaysOnChange?: (alwaysOn: boolean) => void;
  /** Show the "Always available (Keep loaded)" checkbox. Defaults to true.
   *  Callers should pass false for cloud endpoints (VRAM pinning is meaningless there). */
  showAlwaysOn?: boolean;


  
  hideModelSelector?: boolean;

  className?: string;
  disabled?: boolean;
}

/** Normalize a model name by stripping a trailing `:latest`. */
function stripLatest(name: string): string {
  return name.replace(/:latest$/, '');
}

/** True if `candidate` represents the same model as `saved` (handling `:latest`). */
function isSameModel(candidate: string, saved: string): boolean {
  if (candidate === saved) return true;
  if (candidate === `${saved}:latest`) return true;
  if (saved === `${candidate}:latest`) return true;
  return stripLatest(candidate) === stripLatest(saved);
}

export interface ModelOption {
  value: string;
  label: string;
  disabled?: boolean;
  /** Optional section header rendered by SearchableSelect. */
  group?: string;
}

export interface BuildModelOptionsArgs {
  model: string | undefined;
  availableModels: string[];
  modelDetails:
    | Array<{ name: string; [key: string]: unknown }>
    | undefined;
  loadingModels: boolean;
}

/**
 * Build the option list for the Model <Select>.
 *
 * Fixes a regression where a persisted `model` silently disappeared from
 * the dropdown whenever `availableModels` was empty (endpoint not yet
 * probed / probe failed / endpoint offline). The native <select> would
 * fall back to the empty-value placeholder, making it look as if nothing
 * was configured even though the backend still held the selection.
 *
 * Rules:
 *   1. If `model` is saved but NOT present in `availableModels`, prepend
 *      a synthetic `{ value: model, label: model }` so the native select
 *      can render the saved value.
 *   2. Only include the empty-value placeholder when `model` is unset.
 *      Otherwise the native select may prefer it over the saved value
 *      when no matching option exists.
 *   3. Carry the existing `blocked_by_policy` semantics onto entries
 *      derived from `availableModels`.
 */
export function buildModelOptions({
  model,
  availableModels,
  modelDetails,
  loadingModels,
}: BuildModelOptionsArgs): ModelOption[] {
  const hasSaved = !!model;
  const savedAlreadyListed =
    hasSaved && availableModels.some((m) => isSameModel(m, model!));

  const placeholder: ModelOption[] = hasSaved
    ? []
    : [{ value: '', label: loadingModels ? 'Loading models...' : 'Select a model...' }];

  const synthetic: ModelOption[] =
    hasSaved && !savedAlreadyListed ? [{ value: model!, label: model! }] : [];

  const fromAvailable: ModelOption[] = availableModels.map((m) => {
    const details = modelDetails?.find((d) => d.name === m);
    const isBlocked = (details as { blocked_by_policy?: boolean } | undefined)?.blocked_by_policy;
    return {
      value: m,
      label: isBlocked ? `🚫 ${m} (Blocked by IT)` : m,
      disabled: !!isBlocked,
    };
  });

  return [...placeholder, ...synthetic, ...fromAvailable];
}

/**
 * Build the "Cloud models (on-demand)" option group for the Model dropdown.
 *
 * Phase 145: on-demand Ollama Cloud models (verified server-side via /api/show)
 * that are NOT in /api/tags. Rendered under a section header only when the
 * user has toggled "Show all cloud models". Deduped against the pulled
 * `availableModels` set AND the currently-saved `model` so a cloud model
 * that is also subscribed (e.g. a `<name>:cloud` tag) or already selected never
 * appears twice.
 */
export function buildCloudModelOptions({
  cloudModels,
  availableModels,
  model,
  showCloud,
}: {
  cloudModels: string[];
  availableModels: string[];
  model?: string;
  showCloud: boolean;
}): ModelOption[] {
  if (!showCloud) return [];
  return cloudModels
    .filter(
      (cm) =>
        !availableModels.some((m) => isSameModel(m, cm)) &&
        !(model ? isSameModel(cm, model) : false),
    )
    .map((cm) => ({ value: cm, label: cm, group: 'Cloud models (on-demand)' }));
}

export function shouldShowAlwaysOn({
  showAlwaysOn,
  onAlwaysOnChange,
}: {
  showAlwaysOn?: boolean;
  onAlwaysOnChange?: (v: boolean) => void;
}): boolean {
  return (showAlwaysOn ?? true) && onAlwaysOnChange !== undefined;
}

export function ModelCard({
  title,
  description,
  icon,
  info,
  infoLink,
  source = 'endpoint',
  endpoint,
  model,
  endpoints,
  onEndpointChange,
  availableModels = [],
  modelDetails,
  onModelChange,
  onRefreshModels,
  loadingModels = false,
  cloudModels = [],
  loadingCloudModels = false,
  onFetchCloudModels,
  hfEnabled = false,
  hfRepoId,
  hfDownloaded = false,
  hfDownloadProgress,
  onHFDownload,
  onSourceChange,
  status = 'not-configured',
  onTest,
  testResult,
  testingConnection = false,
  alwaysOn = false,
  onAlwaysOnChange,
  showAlwaysOn,

  hideModelSelector = false,
  className,
  disabled = false,
}: ModelCardProps) {
  const isActive = status === 'connected';
  const isDownloading = status === 'downloading';
  const isLoading = status === 'loading';

  // Phase 145: on-demand Ollama Cloud model discovery. The checkbox is only
  // offered for Ollama endpoints (cloud-via-Ollama is the only case this
  // addresses). Toggling on lazily fetches the verified cloud model list
  // (cached client-side per endpoint by useLLMConfig) and reveals a separate
  // "Cloud models (on-demand)" section in the dropdown, deduped against the
  // pulled /api/tags set so subscribed cloud models aren't listed twice.
  const endpointProvider = endpoints.find((e) => e.id === endpoint)?.provider;
  const canShowCloud = endpointProvider === 'ollama' && !!onFetchCloudModels;
  const [showCloud, setShowCloud] = useState(false);
  const handleToggleCloud = (checked: boolean) => {
    setShowCloud(checked);
    if (checked && endpoint && onFetchCloudModels && cloudModels.length === 0 && !loadingCloudModels) {
      void onFetchCloudModels(endpoint);
    }
  };

  return (
    <div className={cn(
      'prep-card rounded-lg border bg-surface p-6 transition-colors flex flex-col',
      isActive ? 'border-success/50 shadow-[0_0_15px_rgba(var(--success),0.1)]' : 'border-border',
      disabled && 'opacity-60 pointer-events-none grayscale',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-surface-raised text-primary">
            {icon || <Database className="w-5 h-5" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold font-mono text-text">{title}</h3>
              {info && <InfoTooltip content={info} href={infoLink} />}
            </div>
            <p className="text-sm text-text-muted">{description}</p>
          </div>
        </div>
        <span className={cn(
          "text-xs px-2 py-1 rounded-full font-medium border flex items-center gap-1.5",
          status === 'connected' ? "bg-success-muted text-success border-success/20" :
          status === 'disconnected' ? "bg-error-muted text-error border-error/20" :
          status === 'downloading' ? "bg-info-muted text-info border-info/20" :
          status === 'loading' ? "bg-warning-muted text-warning border-warning/20" :
          "bg-surface-raised text-text-muted border-border"
        )}>
          {isLoading && <Loader2 className="w-3 h-3 animate-spin" />}
          {status === 'connected' ? 'Connected' :
           status === 'disconnected' ? 'Disconnected' :
           status === 'downloading' ? 'Downloading...' :
           status === 'loading' ? 'Loading...' : 'Not Configured'}
        </span>
      </div>
      
      <div className="flex-grow space-y-6">
        {/* Source Toggle (if HF enabled) */}
        {hfEnabled && onSourceChange && (
          <div className="p-1 bg-surface-raised rounded-lg flex gap-1 border border-border">
            <button
              onClick={() => onSourceChange('endpoint')}
              disabled={disabled}
              className={cn(
                'flex-1 px-3 py-2 text-xs rounded-md transition-all font-medium flex items-center justify-center gap-2',
                source === 'endpoint'
                  ? 'bg-surface text-text shadow-sm'
                  : 'text-text-muted hover:text-text hover:bg-surface/50'
              )}
            >
              <Server className="w-3 h-3" />
              Use Endpoint
            </button>
            <button
              onClick={() => onSourceChange('huggingface')}
              disabled={disabled}
              className={cn(
                'flex-1 px-3 py-2 text-xs rounded-md transition-all font-medium flex items-center justify-center gap-2',
                source === 'huggingface'
                  ? 'bg-surface text-text shadow-sm'
                  : 'text-text-muted hover:text-text hover:bg-surface/50'
              )}
            >
              <Cloud className="w-3 h-3" />
              Download from HF
            </button>
          </div>
        )}
        
        {/* Endpoint Mode */}
        {source === 'endpoint' && (
          <div className="space-y-4">
            {/* Endpoint Selector */}
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1.5">
                Endpoint
              </label>
              <Select
                value={endpoint || ''}
                onChange={(e) => onEndpointChange?.(e.target.value || '')}
                placeholder="Select endpoint..."
                disabled={disabled}
                options={[
                  ...endpoints.map((ep) => ({
                    value: ep.id,
                    label: `${ep.name} (${ep.provider})`,
                  })),
                  ...(endpoint ? [{ value: '__disconnect__', label: '✕  Disconnect' }] : []),
                ]}
                className="w-full"
              />
            </div>
            
            {/* Model Selector */}
            {endpoint && !hideModelSelector && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-muted mb-1.5">
                    Model
                  </label>
                  <div className="flex gap-2">
                    <SearchableSelect
                      value={model || ''}
                      onChange={(v) => onModelChange && onModelChange(v)}
                      disabled={disabled}
                      placeholder={loadingModels ? 'Loading models...' : 'Select a model...'}
                      options={[
                        ...buildModelOptions({
                          model,
                          availableModels,
                          modelDetails,
                          loadingModels,
                        }),
                        ...buildCloudModelOptions({
                          cloudModels,
                          availableModels,
                          model,
                          showCloud,
                        }),
                      ].filter((o) => o.value !== '')}
                      className="flex-1"
                    />
                    {onRefreshModels && (
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={onRefreshModels}
                        disabled={disabled || loadingModels}
                        title="Refresh models"
                        className="shrink-0"
                      >
                        <RefreshCw className={cn("w-4 h-4 text-text-muted", loadingModels && "animate-spin")} />
                      </Button>
                    )}
                    {canShowCloud && (
                      <label
                        className={cn(
                          "flex items-center gap-1 text-[10px] text-text-muted whitespace-nowrap shrink-0 select-none",
                          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
                        )}
                        title="Show on-demand Ollama Cloud models this endpoint can serve but that aren't in /api/tags. Candidates come from advanced.ollama_cloud_candidates in your LLM config (models.yml)."
                      >
                        <input
                          type="checkbox"
                          className="w-3 h-3 rounded border-border bg-surface text-primary focus-visible:ring-focus cursor-pointer"
                          checked={showCloud}
                          onChange={(e) => handleToggleCloud(e.target.checked)}
                          disabled={disabled || loadingCloudModels}
                        />
                        <Cloud className="w-3 h-3 shrink-0" />
                        Show all cloud models
                      </label>
                    )}
                  </div>
                  {/* Model Info: rate limits + batch estimate */}
                  {(() => {
                    if (!model || !modelDetails) return null;
                    const detail = modelDetails.find(d => d.name === model);
                    if (!detail) return null;
                    const rl = detail.rate_limits;
                    const be = detail.batch_estimate;
                    const bp = (detail as any).batch_profile as string | undefined;
                    if (!rl && !be && !bp) return null;
                    const parts: string[] = [];
                    if (detail.context_window) parts.push(`Context: ${detail.context_window} tokens`);
                    if (bp && bp !== 'off') {
                      const tierLabel = bp.charAt(0).toUpperCase() + bp.slice(1);
                      parts.push(`Batch: ${tierLabel}`);
                    }
                    if (rl?.rpd) parts.push(`Free: ${rl.rpd} req/day`);
                    if (be && be.files_per_request > 1) parts.push(`~${be.files_per_request} files/req`);
                    if (be?.daily_file_capacity) {
                      const cap = be.daily_file_capacity;
                      parts.push(`~${cap >= 1000 ? `${Math.round(cap / 1000)}k` : cap} files/day free`);
                    }
                    if (parts.length === 0) return null;
                    return (
                      <div className="mt-2 px-2.5 py-1.5 rounded bg-surface-raised/50 border border-border/50">
                        <div className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[10px] text-text-muted leading-normal">
                          {parts.map((p, i) => (
                            <span key={i} className="whitespace-nowrap">
                              {i > 0 && <span className="opacity-40 mr-1">·</span>}{p}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                  {/* Foundation-model licence + attribution notice (LEG-MOD-04). The
                      backend annotates /api/llm/proxy/models entries from
                      halbert_core.model.attribution; e.g. licences that mandate a
                      "Built with …" notice surface it here. */}
                  {(() => {
                    if (!model || !modelDetails) return null;
                    const detail = modelDetails.find((d) => isSameModel(d.name, model));
                    if (!detail || (!detail.license && !detail.attribution)) return null;
                    return (
                      <div
                        className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-text-muted leading-normal"
                        data-testid="model-license"
                      >
                        {detail.license && (
                          detail.license_url ? (
                            <a
                              href={detail.license_url}
                              target="_blank"
                              rel="noreferrer"
                              title="Model licence terms"
                              className="underline decoration-dotted underline-offset-2 hover:text-text"
                            >
                              {detail.license}
                            </a>
                          ) : (
                            <span title="Model licence terms">{detail.license}</span>
                          )
                        )}
                        {detail.attribution && (
                          <span
                            title="Attribution notice requested by the model licence"
                            className="px-1.5 py-0.5 rounded border border-border/60 bg-surface-raised/60 font-medium text-text"
                          >
                            {detail.attribution}
                          </span>
                        )}
                      </div>
                    );
                  })()}
                </div>
                
                {/* Always On Toggle */}
                {shouldShowAlwaysOn({ showAlwaysOn, onAlwaysOnChange }) && (
                  <label className={cn(
                    "flex items-center gap-2 text-sm select-none",
                    disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
                  )}>
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-border bg-surface text-primary focus-visible:ring-focus focus:ring-offset-surface cursor-pointer disabled:cursor-not-allowed"
                      checked={!!alwaysOn}
                      onChange={(e) => onAlwaysOnChange!(e.target.checked)}
                      disabled={disabled}
                    />
                    <span className="text-text-muted">Always available (Keep loaded)</span>
                  </label>
                )}


              </div>
            )}
          </div>
        )}
        
        {/* HuggingFace Mode */}
        {source === 'huggingface' && hfEnabled && (
          <div className="space-y-4">
            <div className="p-4 bg-surface-raised rounded-lg border border-border">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-text-muted">Model Repository</span>
                <code className="text-xs text-primary bg-primary-muted/20 px-1.5 py-0.5 rounded">{hfRepoId}</code>
              </div>
              
              {hfDownloaded ? (
                <div className="flex items-center gap-2 text-sm text-success font-medium bg-success-muted/10 p-3 rounded border border-success-muted/20">
                  <CheckCircle className="w-4 h-4" />
                  Downloaded & Ready
                </div>
              ) : isDownloading ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-text-muted">
                    <span>Downloading model files...</span>
                    <span>{hfDownloadProgress ? `${Math.round(hfDownloadProgress * 100)}%` : '...'}</span>
                  </div>
                  <div className="h-2 bg-border rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-info transition-all duration-300"
                      style={{ width: `${(hfDownloadProgress || 0) * 100}%` }}
                    />
                  </div>
                </div>
              ) : (
                <Button
                  onClick={onHFDownload}
                  disabled={disabled}
                  className="w-full"
                  icon={Download}
                >
                  Download Model
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* Test Connection Footer */}
      {onTest && source === 'endpoint' && endpoint && (
        <div className="mt-6 pt-4 border-t border-border">
          {testResult && (
            <div className={cn(
              'mb-3 p-3 rounded-md text-xs border flex items-start gap-2',
              testResult.success 
                ? 'bg-success-muted/10 text-success border-success-muted/20'
                : testResult.model_status === 'loading'
                  ? 'bg-warning-muted/10 text-warning border-warning-muted/20'
                  : testResult.model_status === 'not_found'
                    ? 'bg-info-muted/10 text-info border-info-muted/20'
                    : 'bg-error-muted/10 text-error border-error-muted/20'
            )}>
              {testResult.success ? (
                <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" />
              ) : testResult.model_status === 'loading' ? (
                <Loader2 className="w-4 h-4 shrink-0 mt-0.5 animate-spin" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span>{testResult.message}</span>
            </div>
          )}
          {testResult?.warnings?.map((w, i) => (
            <div key={i} className="mb-3 p-3 rounded-md text-xs border flex items-start gap-2 bg-warning-muted/10 text-warning border-warning-muted/20">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
          <Button
            size="sm"
            variant="secondary"
            onClick={onTest}
            loading={testingConnection}
            disabled={disabled}
            className="w-full bg-surface-raised hover:bg-border border-border text-text"
          >
            Test Connection
          </Button>
        </div>
      )}
    </div>
  );
}
