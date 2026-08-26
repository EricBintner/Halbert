import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import type { SavedEndpoint, LLMProvider, EndpointTestResult, ComputeNode, AdminPolicy } from '@/types/llm';
import { Plus, Trash2, Edit2, Play, CheckCircle, AlertCircle, Server, Lock, Wand2, Zap } from 'lucide-react';
import { Button } from '@/components/prep-primitives/Button';
import { Select } from '@/components/prep-primitives/Select';
import { InfoTooltip } from '@/components/prep-primitives/InfoTooltip';
import { PlanDropdown, type PlanLimitsTable } from './PlanDropdown';
import { ProbeButton } from './ProbeButton';
import { CloudDisclosureModal } from '@/components/legal';
import { apiUrl } from '@/lib/apiBase';

// ── LEG-MOD-02: Cloud provider disclosure helpers ──────────────────
// A provider triggers the data-flow disclosure modal when it is a known
// cloud provider (OpenAI, Anthropic, Google, Azure) or an Ollama endpoint
// pointing at ollama.com (Ollama Cloud). Local Ollama / LM Studio do not.
const _CLOUD_PROVIDERS = new Set(['openai', 'anthropic', 'google', 'azure-openai', 'openai-compatible']);

function _isCloudProviderForDisclosure(provider: LLMProvider, url: string): boolean {
  const p = String(provider).toLowerCase();
  if (_CLOUD_PROVIDERS.has(p)) return true;
  // Ollama Cloud: ollama.com host
  if (p === 'ollama') {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host === 'ollama.com' || host.endsWith('.ollama.com')) return true;
    } catch { /* invalid url — treat as local */ }
  }
  return false;
}

function _providerDisplayName(provider: LLMProvider): string {
  const p = String(provider);
  const map: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    google: 'Google',
    'azure-openai': 'Azure OpenAI',
    'openai-compatible': 'OpenAI-compatible',
    ollama: 'Ollama Cloud',
  };
  return map[p] ?? p;
}

export interface EndpointManagerProps {
  endpoints: SavedEndpoint[];
  onAdd: (endpoint: Omit<SavedEndpoint, 'id'>) => void;
  onEdit: (endpoint: SavedEndpoint) => void;
  onDelete: (id: string) => void;
  onTest: (endpoint: SavedEndpoint) => Promise<EndpointTestResult>;
  computeNodes?: ComputeNode[];
  onEndpointNodeChange?: (endpointId: string, nodeId: string | null) => void;
  adminPolicy?: AdminPolicy | null;
  className?: string;
}

const PROVIDER_OPTIONS: { value: LLMProvider; label: string; hint?: string }[] = [
  { value: 'ollama', label: 'Ollama', hint: 'http://localhost:11434' },
  { value: 'lm-studio', label: 'LM Studio', hint: 'http://localhost:1234' },
  { value: 'openai', label: 'OpenAI', hint: 'https://api.openai.com/v1' },
  { value: 'openai-compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic (Claude)', hint: 'https://api.anthropic.com' },
  { value: 'google', label: 'Google (Gemini)', hint: 'https://generativelanguage.googleapis.com' },
  { value: 'azure-openai' as LLMProvider, label: 'Azure OpenAI', hint: 'https://<resource>.openai.azure.com' },
];

const LOCAL_PROVIDERS = new Set<string>(['ollama', 'lm-studio']);

/**
 * Derive Ollama Cloud plan tier from a concurrent value.
 * 1 → free, 2-3 → pro, 4-10 → max. Values outside the 1-10 range fall back to
 * "off" (0) or "max" (>10, defensive — clamp).
 */
function ollamaCloudTier(n: number): 'off' | 'free' | 'pro' | 'max' {
  if (n <= 0) return 'off';
  if (n === 1) return 'free';
  if (n <= 3) return 'pro';
  return 'max';
}

const OLLAMA_CLOUD_OPTIONS = [
  { value: '1', label: '1 (free)' },
  { value: '2', label: '2' },
  { value: '3', label: '3 (pro)' },
  { value: '4', label: '4' },
  { value: '5', label: '5' },
  { value: '6', label: '6' },
  { value: '7', label: '7' },
  { value: '8', label: '8' },
  { value: '9', label: '9' },
  { value: '10', label: '10 (max)' },
] as const;

// Provider key map → concurrency_limits.json provider key.
// Ollama is split between local OSS and Ollama Cloud at runtime via URL host.
const PROVIDER_TO_TABLE_KEY: Partial<Record<LLMProvider, string>> = {
  openai: 'openai',
  anthropic: 'anthropic',
  google: 'google_gemini',
};

const PROVIDER_NEEDS_CLOUD_PLAN: LLMProvider[] = ['openai', 'anthropic', 'google'];

function providerNeedsCloudPlan(p: LLMProvider, url: string): boolean {
  if (PROVIDER_NEEDS_CLOUD_PLAN.includes(p)) return true;
  // ollama → cloud only when host is ollama.com
  if (p === 'ollama') {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === 'ollama.com' || host.endsWith('.ollama.com');
    } catch {
      return false;
    }
  }
  return false;
}

function mapProviderToTableKey(p: LLMProvider, url: string): string {
  if (p === 'ollama') {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host === 'ollama.com' || host.endsWith('.ollama.com')) return 'ollama_cloud';
    } catch {
      // fall through
    }
    return 'ollama_local';
  }
  return PROVIDER_TO_TABLE_KEY[p] ?? String(p);
}

export function EndpointManager({
  endpoints,
  onAdd,
  onEdit,
  onDelete,
  onTest,
  computeNodes,
  onEndpointNodeChange,
  adminPolicy,
  className,
}: EndpointManagerProps) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, EndpointTestResult>>({});
  
  const [formName, setFormName] = useState('');
  const [formProvider, setFormProvider] = useState<LLMProvider>('ollama');
  const [formUrl, setFormUrl] = useState('');
  const [formApiKey, setFormApiKey] = useState('');
  const [formLocalConcurrency, setFormLocalConcurrency] = useState(1);
  const [formCloudConcurrency, setFormCloudConcurrency] = useState(1);
  // Dropdown selection (e.g. "max", "tier_3", "auto", "custom").
  const [formPlanTier, setFormPlanTier] = useState<string | undefined>(undefined);

  // LEG-MOD-02: Cloud API data-flow disclosure consent state.
  // When the user adds/saves a cloud-type endpoint, we intercept and show
  // the CloudDisclosureModal first. The pending action is replayed on accept.
  const [showCloudDisclosure, setShowCloudDisclosure] = useState(false);
  const [pendingCloudAction, setPendingCloudAction] = useState<(() => void) | null>(null);
  const [pendingCloudProvider, setPendingCloudProvider] = useState<string>('');
  // Fetch plan-limits table once on mount; PlanDropdown
  // renders only after this resolves (cloud providers).
  const [planLimits, setPlanLimits] = useState<PlanLimitsTable | null>(null);
  useEffect(() => {
    fetch(apiUrl('/llm/plan-limits'))
      .then((r) => r.json())
      .then((body) => {
        const data = body?.data ?? body;
        setPlanLimits(data && typeof data === 'object' && 'providers' in data ? (data as PlanLimitsTable) : null);
      })
      .catch(() => setPlanLimits(null));
  }, []);

  const resetForm = () => {
    setFormName('');
    setFormProvider('ollama');
    setFormUrl('');
    setFormApiKey('');
    setFormLocalConcurrency(1);
    // 0 (sentinel for "auto") so a fresh add of
    // a cloud-Ollama endpoint that never engages the dropdown surfaces the
    // plan-tier warning instead of silently saving with the legacy default.
    setFormCloudConcurrency(0);
    setFormPlanTier(undefined);
    setShowAddForm(false);
    setEditingId(null);
  };

  const handleAdd = () => {
    if (!formName.trim() || !formUrl.trim()) return;
    const doAdd = () => {
      onAdd({
        name: formName.trim(),
        provider: formProvider,
        url: formUrl.trim(),
        api_key: formApiKey.trim() || undefined,
        local_concurrency: formLocalConcurrency,
        cloud_concurrency: formCloudConcurrency,
        plan_tier: formPlanTier,
      });
      resetForm();
    };
    // LEG-MOD-02: gate cloud providers behind the disclosure consent modal.
    if (_isCloudProviderForDisclosure(formProvider, formUrl)) {
      setPendingCloudProvider(_providerDisplayName(formProvider));
      setPendingCloudAction(() => doAdd);
      setShowCloudDisclosure(true);
    } else {
      doAdd();
    }
  };

  const handleEdit = (ep: SavedEndpoint) => {
    setEditingId(ep.id);
    setFormName(ep.name);
    setFormProvider(ep.provider);
    setFormUrl(ep.url);
    setFormApiKey(ep.api_key || '');
    setFormLocalConcurrency(ep.local_concurrency ?? 1);
    setFormCloudConcurrency(ep.cloud_concurrency ?? 0);
    setFormPlanTier(ep.plan_tier);
    setShowAddForm(false);
  };

  const handleSaveEdit = () => {
    if (!editingId || !formName.trim() || !formUrl.trim()) return;
    const doSave = () => {
      onEdit({
        id: editingId,
        name: formName.trim(),
        provider: formProvider,
        url: formUrl.trim(),
        api_key: formApiKey.trim() || undefined,
        local_concurrency: formLocalConcurrency,
        cloud_concurrency: formCloudConcurrency,
        plan_tier: formPlanTier,
      });
      resetForm();
    };
    // LEG-MOD-02: gate cloud providers behind the disclosure consent modal.
    if (_isCloudProviderForDisclosure(formProvider, formUrl)) {
      setPendingCloudProvider(_providerDisplayName(formProvider));
      setPendingCloudAction(() => doSave);
      setShowCloudDisclosure(true);
    } else {
      doSave();
    }
  };

  const handleTest = async (ep: SavedEndpoint) => {
    setTestingId(ep.id);
    try {
      const result = await onTest(ep);
      setTestResults((prev) => ({ ...prev, [ep.id]: result }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [ep.id]: { success: false, message: 'Test failed' },
      }));
    }
    setTestingId(null);
  };

  const providerNeedsApiKey = (provider: LLMProvider) =>
    provider === 'openai' || provider === 'anthropic' || provider === 'openai-compatible' || provider === 'google' || (provider as string) === 'azure-openai';

  // EA-C5: Filter providers by admin policy allowlist
  const isProviderAllowed = (provider: string): boolean => {
    if (!adminPolicy) return true;
    const p = provider.toLowerCase();
    if (LOCAL_PROVIDERS.has(p) && adminPolicy.provider.allow_local_providers) return true;
    if (adminPolicy.provider.blocked_providers.length > 0) {
      if (adminPolicy.provider.blocked_providers.map(x => x.toLowerCase()).includes(p)) return false;
    }
    if (adminPolicy.provider.allowed_providers.length > 0) {
      return adminPolicy.provider.allowed_providers.map(x => x.toLowerCase()).includes(p);
    }
    return true;
  };

  const filteredProviderOptions = PROVIDER_OPTIONS.filter(o => isProviderAllowed(o.value));
  const lockedEndpoints = adminPolicy?.provider.locked_endpoints ?? [];
  const canAddEndpoints = adminPolicy?.provider.allow_user_endpoints ?? true;
  const canEditApiKeys = adminPolicy?.provider.allow_user_api_keys ?? true;

  const providerDefaultUrl = (provider: LLMProvider) =>
    PROVIDER_OPTIONS.find((o) => o.value === provider)?.hint ?? '';

  const hasAutofill = (provider: LLMProvider) => {
    const hint = providerDefaultUrl(provider);
    return hint && !hint.includes('<'); // exclude templates like <resource>
  };

  const handleProviderChange = (provider: LLMProvider) => {
    const prevDefault = providerDefaultUrl(formProvider);
    setFormProvider(provider);
    // Auto-populate URL if empty or still matches previous provider's default
    if (!formUrl || formUrl === prevDefault) {
      const newDefault = providerDefaultUrl(provider);
      if (newDefault && !newDefault.includes('<')) {
        setFormUrl(newDefault);
      } else {
        setFormUrl('');
      }
    }
  };

  return (
    <>
    <div className={cn('prep-card rounded-lg border border-border bg-surface p-6', className)}>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-text flex items-center gap-2">
            <Server className="w-5 h-5 text-primary" />
            <InfoTooltip 
              content="Learn about supported LLM providers." 
              href="https://docs.sourceprep.io/guides/models" 
            />
            Saved Endpoints
          </h3>
          <p className="text-sm text-text-muted mt-1">Manage local and remote LLM server connections</p>
        </div>
      </div>

      {/* EA-C6: Locked Endpoints (IT-configured) */}
      {lockedEndpoints.length > 0 && (
        <div className="space-y-2 mb-4">
          <p className="text-xs font-medium text-amber-400 flex items-center gap-1">
            <Lock className="w-3 h-3" /> Configured by IT
          </p>
          {lockedEndpoints.map((le, i) => (
            <div key={`locked-${i}`} className="p-3 border border-amber-500/30 rounded-lg bg-amber-500/5">
              <div className="flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span className="font-medium text-sm text-text">{le.name || 'IT Endpoint'}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-surface-raised text-text-muted border border-border">
                  {le.provider || 'unknown'}
                </span>
              </div>
              <code className="text-xs text-text-subtle font-mono truncate block mt-1">{le.url || ''}</code>
            </div>
          ))}
        </div>
      )}

      {/* Endpoint List */}
      <div className="space-y-3 mb-6">
        {endpoints.length === 0 ? (
          <div className="text-sm text-text-muted py-8 text-center bg-surface-raised rounded-lg border border-dashed border-border">
            No saved endpoints found
          </div>
        ) : (
          endpoints.map((ep) => (
            <div
              key={ep.id}
              className={cn(
                "p-4 border rounded-lg transition-colors",
                editingId === ep.id 
                  ? "bg-surface-raised border-primary/50" 
                  : "border-border hover:border-border-subtle bg-surface"
              )}
            >
              {editingId === ep.id ? (
                // Edit form inline
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Display Name</label>
                      <input
                        placeholder="Display Name"
                        value={formName}
                        onChange={(e) => setFormName(e.target.value)}
                        className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">Provider</label>
                      <Select
                        value={formProvider}
                        onChange={(e) => handleProviderChange(e.target.value as LLMProvider)}
                        options={filteredProviderOptions.map((o) => ({ value: o.value, label: o.label }))}
                        className="w-full"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-text-muted mb-1">Endpoint URL</label>
                    <div className="flex gap-2">
                      <input
                        placeholder={providerDefaultUrl(formProvider) || 'Endpoint URL'}
                        value={formUrl}
                        onChange={(e) => setFormUrl(e.target.value)}
                        className="flex-1 bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      {hasAutofill(formProvider) && formUrl !== providerDefaultUrl(formProvider) && (
                        <button
                          type="button"
                          onClick={() => setFormUrl(providerDefaultUrl(formProvider))}
                          className="px-2.5 py-2 rounded border border-border bg-surface-raised text-text-muted hover:text-primary hover:border-primary/40 transition-colors text-xs flex items-center gap-1 shrink-0"
                          title={`Autofill: ${providerDefaultUrl(formProvider)}`}
                        >
                          <Wand2 className="w-3.5 h-3.5" />
                          Autofill
                        </button>
                      )}
                    </div>
                  </div>
                  {providerNeedsApiKey(formProvider) && (
                    <div>
                      <label className="block text-xs font-medium text-text-muted mb-1">API Key</label>
                      {canEditApiKeys ? (
                        <>
                          <input
                            placeholder="API Key"
                            type="password"
                            value={formApiKey}
                            onChange={(e) => setFormApiKey(e.target.value)}
                            className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
                          />
                          {formProvider === 'google' && (
                            <p className="text-[10px] text-amber-400/80 mt-1.5 flex items-center gap-1">
                              <AlertCircle className="w-3 h-3 shrink-0" />
                              Google Gemini sends the API key as a URL parameter (visible in HTTP logs). For enterprise, consider Vertex AI.
                            </p>
                          )}
                        </>
                      ) : (
                        <div className="flex items-center gap-2 px-3 py-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-400">
                          <Lock className="w-3.5 h-3.5 shrink-0" />
                          <span>API key managed by IT (from environment variable)</span>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Phase 56: Concurrency settings */}
                  <div className="pt-2 border-t border-border/50 mt-1">
                    <div className="flex items-center gap-1.5 mb-2">
                      <Zap className="w-3.5 h-3.5 text-primary" />
                      <label className="text-xs font-medium text-text-muted">Concurrency</label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      {providerNeedsCloudPlan(formProvider, formUrl) && planLimits ? (
                        /* Plan-tier dropdown for cloud providers */
                        <div className="col-span-2">
                          <PlanDropdown
                            providerKey={mapProviderToTableKey(formProvider, formUrl)}
                            value={formPlanTier}
                            customConcurrent={formCloudConcurrency}
                            limits={planLimits}
                            onChange={({ plan_tier, cloud_concurrency }) => {
                              setFormPlanTier(plan_tier || undefined);
                              setFormCloudConcurrency(cloud_concurrency);
                            }}
                          />
                        </div>
                      ) : !LOCAL_PROVIDERS.has(formProvider) ? (
                        /* Cloud provider, plan limits not yet loaded — fall back to numeric */
                        <div className="col-span-2">
                          <label className="block text-[10px] text-text-subtle mb-1">Concurrent API Requests</label>
                          <Select
                            size="sm"
                            value={String(formCloudConcurrency)}
                            onChange={(e) => setFormCloudConcurrency(Number(e.target.value))}
                            options={[1,2,3,4,5,6,8,10,12,16,20].map(n => ({ value: String(n), label: String(n) }))}
                            className="w-full"
                          />
                          <p className="text-[9px] text-text-subtle mt-0.5">Max parallel API calls across all pipeline stages</p>
                        </div>
                      ) : (
                        /* Ollama / LM Studio (local OSS): local + cloud concurrency */
                        <>
                          <div>
                            <label className="block text-[10px] text-text-subtle mb-1">Local GPU</label>
                            <Select
                              size="sm"
                              value={String(formLocalConcurrency)}
                              onChange={(e) => setFormLocalConcurrency(Number(e.target.value))}
                              options={[1,2,3,4].map(n => ({ value: String(n), label: String(n) }))}
                              className="w-full"
                            />
                            <p className="text-[9px] text-text-subtle mt-0.5">Models in VRAM</p>
                          </div>
                          <div>
                            <label className="block text-[10px] text-text-subtle mb-1">Cloud Models</label>
                            <Select
                              size="sm"
                              value={String(Math.max(1, Math.min(10, formCloudConcurrency || 1)))}
                              onChange={(e) => setFormCloudConcurrency(Number(e.target.value))}
                              options={OLLAMA_CLOUD_OPTIONS as unknown as Array<{value: string; label: string}>}
                              className="w-full"
                            />
                            <p className="text-[9px] text-text-subtle mt-0.5">Proxied (kimi, gemini…)</p>
                            <p className="text-[9px] text-text-subtle mt-0.5">
                              Ollama cloud = {ollamaCloudTier(formCloudConcurrency || 1)}
                            </p>
                          </div>
                        </>
                      )}
                    </div>
                    {formProvider === 'ollama' && (formLocalConcurrency > 1 || formCloudConcurrency > 1) && (
                      <div className="mt-4 p-2.5 rounded bg-amber-500/10 border border-amber-500/20 flex gap-2 items-start text-amber-500/90 leading-tight">
                        <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <div className="text-[11px]">
                          <strong>Ollama requires manual startup configuration to run concurrently.</strong> Start your Ollama server with <code className="bg-amber-500/20 px-1 py-0.5 rounded font-mono mx-0.5 text-[10px]">OLLAMA_NUM_PARALLEL={formLocalConcurrency + formCloudConcurrency}</code> (the sum: <strong>{formLocalConcurrency}</strong> local-GPU model{formLocalConcurrency === 1 ? '' : 's'} + <strong>{formCloudConcurrency}</strong> cloud-routed call{formCloudConcurrency === 1 ? '' : 's'}). Otherwise, requests will queue sequentially.
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 pt-2">
                    <div className="flex gap-2 justify-end w-full">
                      <Button 
                        onClick={resetForm}
                        variant="outline"
                        size="sm"
                      >
                        Cancel
                      </Button>
                      <Button 
                        onClick={handleSaveEdit}
                        size="sm"
                      >
                        Update
                      </Button>
                    </div>
                    <span className="text-[10px] text-text-subtle mr-1">
                      (Remember to click "Save Settings" below)
                    </span>
                  </div>
                </div>
              ) : (
                // Display mode
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm text-text">{ep.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-surface-raised text-text-muted border border-border">
                        {ep.provider}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <code className="text-xs text-text-subtle font-mono truncate max-w-[200px]">
                        {ep.url}
                      </code>
                      {computeNodes && computeNodes.length > 0 && onEndpointNodeChange && (
                        <Select
                          size="sm"
                          value={ep.compute_node_id || ''}
                          onChange={(e) => onEndpointNodeChange(ep.id, e.target.value || null)}
                          options={[
                            { value: '', label: 'Auto (default node)' },
                            ...computeNodes.map((n) => ({
                              value: n.id,
                              label: `${n.name}${n.gpu_name ? ` · ${n.gpu_name}` : ''}`
                            }))
                          ]}
                          className="max-w-[180px]"
                        />
                      )}
                    </div>
                    {ep.provider === 'ollama' && (ep.cloud_concurrency ?? 0) > 0 && (
                      <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-primary text-xs font-medium">
                        <Zap className="w-3 h-3" />
                        <span>Ollama cloud = <strong>{ollamaCloudTier(ep.cloud_concurrency ?? 0)}</strong></span>
                        <span className="opacity-70">({ep.cloud_concurrency} concurrent)</span>
                      </div>
                    )}
                    {testResults[ep.id] && (
                      <div className={cn(
                        'text-xs mt-2 flex items-center gap-1.5',
                        testResults[ep.id].success ? 'text-success' : 'text-error'
                      )}>
                        {testResults[ep.id].success ? (
                          <CheckCircle className="w-3.5 h-3.5" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5" />
                        )}
                        {testResults[ep.id].message}
                      </div>
                    )}
                    {/* Empirical capacity probe.
                        Cloud-only — local providers don't need it. */}
                    {providerNeedsCloudPlan(ep.provider, ep.url) && (
                      <div className="mt-3">
                        <ProbeButton
                          endpointId={ep.id}
                          burstSize={20}
                          onApply={(recommended) => {
                            // Apply writes to the same cloud_concurrency field
                            // the Plan dropdown writes to — the two controls
                            // are complementary.
                            onEdit({
                              ...ep,
                              cloud_concurrency: recommended,
                              plan_tier: 'custom',
                            });
                          }}
                        />
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 ml-4">
                    <Button
                      onClick={() => handleTest(ep)}
                      disabled={testingId === ep.id}
                      variant="ghost"
                      size="icon-sm"
                      className={cn(testingId === ep.id && "opacity-70")}
                      aria-label="Test Connection"
                    >
                      <Play className={cn("w-4 h-4", testingId === ep.id && "animate-pulse")} />
                    </Button>
                    <Button
                      onClick={() => handleEdit(ep)}
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Edit"
                    >
                      <Edit2 className="w-4 h-4" />
                    </Button>
                    <Button
                      onClick={() => onDelete(ep.id)}
                      variant="ghost"
                      size="icon-sm"
                      className="hover:bg-error-muted/10 hover:text-error"
                      aria-label="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Add New Endpoint */}
      {showAddForm ? (
        <div className="p-4 border border-border rounded-lg bg-surface-raised/50 space-y-4 animate-in fade-in slide-in-from-top-2">
          <h4 className="text-sm font-semibold font-mono text-text">Add New Endpoint</h4>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1">Display Name</label>
              <input
                placeholder="e.g. Local Ollama"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1">Provider</label>
              <Select
                value={formProvider}
                onChange={(e) => handleProviderChange(e.target.value as LLMProvider)}
                options={filteredProviderOptions.map((o) => ({ value: o.value, label: o.label }))}
                className="w-full"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Endpoint URL</label>
            <div className="flex gap-2">
              <input
                placeholder={providerDefaultUrl(formProvider) || 'e.g., http://localhost:11434'}
                value={formUrl}
                onChange={(e) => setFormUrl(e.target.value)}
                className="flex-1 bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {hasAutofill(formProvider) && formUrl !== providerDefaultUrl(formProvider) && (
                <button
                  type="button"
                  onClick={() => setFormUrl(providerDefaultUrl(formProvider))}
                  className="px-2.5 py-2 rounded border border-border bg-surface-raised text-text-muted hover:text-primary hover:border-primary/40 transition-colors text-xs flex items-center gap-1 shrink-0"
                  title={`Autofill: ${providerDefaultUrl(formProvider)}`}
                >
                  <Wand2 className="w-3.5 h-3.5" />
                  Autofill
                </button>
              )}
            </div>
          </div>
          {providerNeedsApiKey(formProvider) && (
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1">API Key</label>
              {canEditApiKeys ? (
                <>
                  <input
                    placeholder="sk-..."
                    type="password"
                    value={formApiKey}
                    onChange={(e) => setFormApiKey(e.target.value)}
                    className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  {formProvider === 'google' && (
                    <p className="text-[10px] text-amber-400/80 mt-1.5 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3 shrink-0" />
                      Google Gemini sends the API key as a URL parameter (visible in HTTP logs). For enterprise, consider Vertex AI.
                    </p>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-2 px-3 py-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-400">
                  <Lock className="w-3.5 h-3.5 shrink-0" />
                  <span>API key managed by IT (from environment variable)</span>
                </div>
              )}
            </div>
          )}
          {/* Phase 56: Concurrency settings */}
          <div className="pt-2 border-t border-border/50 mt-1">
            <div className="flex items-center gap-1.5 mb-2">
              <Zap className="w-3.5 h-3.5 text-primary" />
              <label className="text-xs font-medium text-text-muted">Concurrency</label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {providerNeedsCloudPlan(formProvider, formUrl) && planLimits ? (
                /* Plan-tier dropdown for cloud providers */
                <div className="col-span-2">
                  <PlanDropdown
                    providerKey={mapProviderToTableKey(formProvider, formUrl)}
                    value={formPlanTier}
                    customConcurrent={formCloudConcurrency}
                    limits={planLimits}
                    onChange={({ plan_tier, cloud_concurrency }) => {
                      setFormPlanTier(plan_tier || undefined);
                      setFormCloudConcurrency(cloud_concurrency);
                    }}
                  />
                </div>
              ) : !LOCAL_PROVIDERS.has(formProvider) ? (
                <div className="col-span-2">
                  <label className="block text-[10px] text-text-subtle mb-1">Concurrent API Requests</label>
                  <Select
                    size="sm"
                    value={String(formCloudConcurrency)}
                    onChange={(e) => setFormCloudConcurrency(Number(e.target.value))}
                    options={[1,2,3,4,5,6,8,10,12,16,20].map(n => ({ value: String(n), label: String(n) }))}
                    className="w-full"
                  />
                  <p className="text-[9px] text-text-subtle mt-0.5">Max parallel API calls across all pipeline stages</p>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-[10px] text-text-subtle mb-1">Local GPU</label>
                    <Select
                      size="sm"
                      value={String(formLocalConcurrency)}
                      onChange={(e) => setFormLocalConcurrency(Number(e.target.value))}
                      options={[1,2,3,4].map(n => ({ value: String(n), label: String(n) }))}
                      className="w-full"
                    />
                    <p className="text-[9px] text-text-subtle mt-0.5">Models in VRAM</p>
                  </div>
                  <div>
                    <label className="block text-[10px] text-text-subtle mb-1">Cloud Models</label>
                    <Select
                      size="sm"
                      value={String(Math.max(1, Math.min(10, formCloudConcurrency || 1)))}
                      onChange={(e) => setFormCloudConcurrency(Number(e.target.value))}
                      options={OLLAMA_CLOUD_OPTIONS as unknown as Array<{value: string; label: string}>}
                      className="w-full"
                    />
                    <p className="text-[9px] text-text-subtle mt-0.5">Proxied (kimi, gemini…)</p>
                    <p className="text-[9px] text-text-subtle mt-0.5">
                      Ollama cloud = {ollamaCloudTier(formCloudConcurrency || 1)}
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="flex gap-2 pt-2">
            <Button
              onClick={handleAdd}
              size="sm"
            >
              Add Endpoint
            </Button>
            <Button 
              onClick={resetForm}
              variant="outline"
              size="sm"
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : canAddEndpoints ? (
        <button
          onClick={() => setShowAddForm(true)}
          className="w-full py-3 border border-dashed border-border rounded-lg text-sm text-text-muted hover:text-text hover:border-primary/50 hover:bg-surface-raised transition-all flex items-center justify-center gap-2 group"
        >
          <Plus className="w-4 h-4 group-hover:scale-110 transition-transform" />
          Add New Endpoint
        </button>
      ) : (
        <div className="w-full py-3 border border-dashed border-amber-500/30 rounded-lg text-sm text-amber-400/70 bg-amber-500/5 flex items-center justify-center gap-2">
          <Lock className="w-4 h-4" />
          Endpoint management is restricted by IT policy
        </div>
      )}
    </div>

      {/* LEG-MOD-02: Cloud API data-flow disclosure consent modal */}
      <CloudDisclosureModal
        open={showCloudDisclosure}
        onOpenChange={(o) => {
          setShowCloudDisclosure(o);
          if (!o) setPendingCloudAction(null);
        }}
        providerName={pendingCloudProvider}
        onAccept={() => {
          if (pendingCloudAction) pendingCloudAction();
          setPendingCloudAction(null);
        }}
        onDecline={() => {
          setPendingCloudAction(null);
        }}
      />
    </>
  );
}
