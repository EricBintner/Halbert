import { cn } from '@/lib/utils';
import { isLocalProvider } from './provider-utils';
import { ModelCard } from './ModelCard';
import { AdvancedLLMSettings } from './AdvancedLLMSettings';
import { EndpointManager } from './EndpointManager';
import { LLMAssignmentBlockCard } from './stubs/LLMAssignmentBlockCard';
import { LLMAssignmentsPipeline } from './stubs/LLMAssignmentsPipeline';
import { ConcurrencyResetPanel } from './stubs/ConcurrencyResetPanel';
import { Select } from '@/components/prep-primitives/Select';
import { Button } from '@/components/prep-primitives/Button';
import { InfoTooltip } from '@/components/prep-primitives/InfoTooltip';
import type { 
  LLMConfig,
  SavedEndpoint,
  EndpointTestResult,
  ModelSource,
  AssignmentMode,
  PrepTaskId,
  ComputeNode,
  AdminPolicy,
} from '@/types/llm';
import { Cpu, Info, Plus, Save, Trash2, Edit2 } from 'lucide-react';
import { useState } from 'react';

export interface AIModelsSettingsProps {
  config: LLMConfig;
  onConfigChange: (config: LLMConfig) => void;
  
  // Endpoint operations
  onAddEndpoint: (endpoint: Omit<SavedEndpoint, 'id'>) => void;
  onEditEndpoint: (endpoint: SavedEndpoint) => void;
  onDeleteEndpoint: (id: string) => void;
  onTestEndpoint: (endpoint: SavedEndpoint) => Promise<EndpointTestResult>;
  
  // Model operations
  onFetchModels: (endpointId: string, slot?: string) => Promise<string[]>;
  onTestModel: (slotType: 'embedding' | 'small' | 'large' | 'code' | 'coordinator') => Promise<EndpointTestResult>;
  onClearTestResult?: (slot: string) => void;
  
  // HuggingFace operations
  onHFDownload: (slotType: 'embedding') => void;
  
  // UI state
  availableModels?: Record<string, string[]>; // endpointId -> models
  modelDetails?: Record<string, Array<{ name: string; context_window?: string; cost_tier?: string }>>;
  loadingModels?: Record<string, boolean>;
  // On-demand Ollama Cloud models not in /api/tags (Phase 145: cloud discovery).
  // Per-endpoint, lazy-fetched when the user toggles "Show all cloud models".
  cloudModels?: Record<string, string[]>;
  loadingCloudModels?: Record<string, boolean>;
  onFetchCloudModels?: (endpointId: string) => Promise<string[]>;
  testingSlot?: 'embedding' | 'small' | 'large' | 'code' | 'coordinator' | null;
  testResults?: Record<string, EndpointTestResult>;
  
  fileCount?: number;
  className?: string;

  // Compute settings (moved from Global Settings → AI Gateway)
  maxActiveProjects?: number | 'infinite';
  onMaxActiveProjectsChange?: (val: number | 'infinite') => void;
  schedulerStatus?: import('@/types/llm').SchedulerStatus | null;

  // Compute node management (Phase 45D)
  computeNodes?: ComputeNode[];
  onComputeNodeAdd?: (node: Omit<ComputeNode, 'id'>) => void;
  onComputeNodeUpdate?: (nodeId: string, updates: Partial<ComputeNode>) => void;
  onComputeNodeDelete?: (nodeId: string) => void;
  onEndpointNodeChange?: (endpointId: string, nodeId: string | null) => void;

  // Phase 44: Mapped mode operations
  onAssignmentBlockAdd?: () => void;
  onAssignmentBlockDelete?: (blockId: string) => void;
  onAssignmentBlockEndpointChange?: (blockId: string, endpointId: string) => void;
  onAssignmentBlockModelChange?: (blockId: string, model: string) => void;
  onAssignmentBlockAddTask?: (blockId: string, taskId: PrepTaskId) => void;
  onAssignmentBlockRemoveTask?: (blockId: string, taskId: PrepTaskId) => void;
  onAssignmentBlockTest?: (blockId: string) => Promise<EndpointTestResult>;
  assignmentBlockTestResults?: Record<string, EndpointTestResult>;
  assignmentBlockTesting?: string | null;

  // EA-C10: Admin policy for provider/model restrictions
  adminPolicy?: AdminPolicy | null;

  /** Fires when the user clicks "Apply [Structured|Assigned] mode".
   *  Consumers should flush any pending debounced save, then call switchAssignmentMode. */
  onModeApply?: (mode: AssignmentMode, blocks?: LLMConfig['assignment_blocks']) => Promise<void> | void;

  /** Phase 119 Task 16: Base URL for the SourcePrep daemon. When provided,
   *  the Pipeline Activity header surfaces a developer-mode wrench icon that
   *  opens an inline panel for resetting discovered concurrency ceilings on
   *  `cloud:*` nodes (POST /compute/concurrency/clear). Hidden when omitted. */
  baseUrl?: string;
}

// Recommended models per slot.
// Phase 112: quality-first cloud-centric stack.
// Small + Coordinator share gemini-3-flash-preview:cloud (JSON-reliable,
// 1M ctx, no thinking overhead). Large = kimi-k2.5:cloud for deep reasoning.
// qwen3 base family removed (8b/14b/30b) in favor of the cloud stack or
// gemma3 for air-gapped fallback. qwen3-coder retained for code slot.
// See docs/Phase112_Gemini/SWARM_UI_PLAN_v2.md §4.
const RECOMMENDED_MODELS: Record<string, string[]> = {
  embedding: ['nomic-embed-text', 'nomic-embed-code'],
  small: ['gemini-3-flash-preview:cloud', 'gemma3:12b'],
  large: ['kimi-k2.5:cloud', 'gemma3:27b'],
  coordinator: ['gemini-3-flash-preview:cloud', 'gemma3:27b'],
  code: ['qwen3-coder-next:cloud', 'qwen3-coder:30b'],
};

/** Check if a model name matches an entry in the available list (handles ':latest' suffix) */
function modelInList(model: string, list: string[]): boolean {
  return list.some(
    (m) => m === model || m === `${model}:latest` || model === `${m}:latest`
      || m.replace(/:latest$/, '') === model.replace(/:latest$/, '')
  );
}

/** Find the first recommended model present in the available list */
function findRecommended(slot: string, list: string[]): string | undefined {
  const recs = RECOMMENDED_MODELS[slot] ?? [];
  for (const rec of recs) {
    const match = list.find(
      (m) => m === rec || m === `${rec}:latest` || m.replace(/:latest$/, '') === rec.replace(/:latest$/, '')
    );
    if (match) return match;
  }
  return undefined;
}

// ── Compute Node CRUD Panel (Phase 45D) ──────────────────────

function ComputeNodePanel({
  nodes,
  endpoints,
  onAdd,
  onUpdate,
  onDelete,
}: {
  nodes: ComputeNode[];
  endpoints: SavedEndpoint[];
  onAdd?: (node: Omit<ComputeNode, 'id'>) => void;
  onUpdate?: (nodeId: string, updates: Partial<ComputeNode>) => void;
  onDelete?: (nodeId: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<'local' | 'remote' | 'cloud'>('local');
  const [formGpuName, setFormGpuName] = useState('');

  const resetForm = () => {
    setFormName('');
    setFormType('local');
    setFormGpuName('');
    setAdding(false);
    setEditingId(null);
  };

  const handleAdd = () => {
    if (!formName.trim() || !onAdd) return;
    onAdd({
      name: formName.trim(),
      type: formType,
      max_concurrent: 1,
      gpu_name: formGpuName.trim() || undefined,
      endpoint_ids: [],
    });
    resetForm();
  };

  const handleSaveEdit = () => {
    if (!editingId || !formName.trim() || !onUpdate) return;
    onUpdate(editingId, {
      name: formName.trim(),
      type: formType,
      gpu_name: formGpuName.trim() || undefined,
    });
    resetForm();
  };

  const startEdit = (node: ComputeNode) => {
    setEditingId(node.id);
    setFormName(node.name);
    setFormType(node.type);
    setFormGpuName(node.gpu_name || '');
    setAdding(false);
  };

  if (nodes.length === 0 && !onAdd) return null;

  return (
    <div className="space-y-2 pt-2 border-t border-border">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-text-subtle">Compute Nodes</label>
        {onAdd && !adding && !editingId && (
          <button
            onClick={() => { resetForm(); setAdding(true); }}
            className="text-[10px] text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            Add Node
          </button>
        )}
      </div>

      {/* Node list */}
      <div className="space-y-2">
        {nodes.map((node) => {
          const endpointCount = endpoints.filter(
            (ep) => ep.compute_node_id === node.id
          ).length;

          if (editingId === node.id) {
            return (
              <div key={node.id} className="p-3 rounded border border-primary/40 bg-surface-raised space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] font-medium text-text-muted mb-1">Name</label>
                    <input
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full bg-surface border border-border rounded px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-medium text-text-muted mb-1">Type</label>
                    <Select
                      size="sm"
                      value={formType}
                      onChange={(e) => setFormType(e.target.value as 'local' | 'remote' | 'cloud')}
                      options={[
                        { value: 'local', label: 'Local' },
                        { value: 'remote', label: 'Remote (LAN)' },
                        { value: 'cloud', label: 'Cloud' },
                      ]}
                      className="w-full"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] font-medium text-text-muted mb-1">GPU / Hardware</label>
                    <input
                      value={formGpuName}
                      onChange={(e) => setFormGpuName(e.target.value)}
                      placeholder="e.g. RTX 4090, M3 Max"
                      className="w-full bg-surface border border-border rounded px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button onClick={resetForm} variant="outline" size="sm">Cancel</Button>
                  <Button onClick={handleSaveEdit} size="sm">Save</Button>
                </div>
              </div>
            );
          }

          return (
            <div
              key={node.id}
              className="flex items-center gap-3 p-2.5 rounded border border-border bg-surface-raised group"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className={cn(
                    'w-1.5 h-1.5 rounded-full shrink-0',
                    node.type === 'cloud' ? 'bg-blue-400' : node.type === 'remote' ? 'bg-amber-400' : 'bg-emerald-400'
                  )} />
                  <span className="text-xs font-medium text-text truncate">{node.name}</span>
                  <span className="text-[10px] text-text-muted capitalize">({node.type})</span>
                </div>
                <p className="text-[10px] text-text-muted mt-0.5 pl-3">
                  {endpointCount} endpoint{endpointCount !== 1 ? 's' : ''}
                  {node.gpu_name ? ` · ${node.gpu_name}` : ''}
                  {node.gpu_vram_gb ? ` · ${node.gpu_vram_gb}GB` : ''}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                {onUpdate && (
                  <button
                    onClick={() => startEdit(node)}
                    className="p-1 rounded hover:bg-surface transition-colors text-text-muted hover:text-text"
                    title="Edit node"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                )}
                {onDelete && (
                  <button
                    onClick={() => onDelete(node.id)}
                    className="p-1 rounded hover:bg-error-muted/10 transition-colors text-text-muted hover:text-error"
                    title="Delete node"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add form */}
      {adding && onAdd && (
        <div className="p-3 rounded border border-dashed border-primary/40 bg-surface-raised/50 space-y-3 animate-in fade-in slide-in-from-top-1">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[10px] font-medium text-text-muted mb-1">Name</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. GPU Server 2"
                className="w-full bg-surface border border-border rounded px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-[10px] font-medium text-text-muted mb-1">Type</label>
              <Select
                size="sm"
                value={formType}
                onChange={(e) => setFormType(e.target.value as 'local' | 'remote' | 'cloud')}
                options={[
                  { value: 'local', label: 'Local' },
                  { value: 'remote', label: 'Remote (LAN)' },
                  { value: 'cloud', label: 'Cloud' },
                ]}
                className="w-full"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[10px] font-medium text-text-muted mb-1">GPU / Hardware</label>
              <input
                value={formGpuName}
                onChange={(e) => setFormGpuName(e.target.value)}
                placeholder="e.g. RTX 4090, M3 Max"
                className="w-full bg-surface border border-border rounded px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button onClick={resetForm} variant="outline" size="sm">Cancel</Button>
            <Button onClick={handleAdd} size="sm" disabled={!formName.trim()}>Add Node</Button>
          </div>
        </div>
      )}

      <p className="text-[9px] text-text-muted opacity-70">
        Assign endpoints to compute nodes to control which hardware runs each model.
      </p>
    </div>
  );
}


export function AIModelsSettings({
  config,
  onConfigChange,
  onAddEndpoint,
  onEditEndpoint,
  onDeleteEndpoint,
  onTestEndpoint,
  onFetchModels,
  onTestModel,
  onClearTestResult,
  onHFDownload,
  availableModels = {},
  modelDetails = {},
  loadingModels = {},
  cloudModels = {},
  loadingCloudModels = {},
  onFetchCloudModels,
  testingSlot,
  testResults = {},
  fileCount = 0,
  className,
  maxActiveProjects,
  onMaxActiveProjectsChange,
  schedulerStatus,
  computeNodes,
  onComputeNodeAdd,
  onComputeNodeUpdate,
  onComputeNodeDelete,
  onEndpointNodeChange,
  onAssignmentBlockTest,
  assignmentBlockTestResults = {},
  assignmentBlockTesting,
  adminPolicy,
  onModeApply,
  baseUrl,
}: AIModelsSettingsProps) {
  const savedMode: AssignmentMode = config.assignment_mode ?? 'structured';
  const [draftMode, setDraftMode] = useState<AssignmentMode>(savedMode);
  const isDraftDirty = draftMode !== savedMode;

  const endpointProviderFor = (endpointId: string | undefined) =>
    config.saved_endpoints.find((e) => e.id === endpointId)?.provider;
  // Ensure we always have at least one block in mapped mode to avoid an empty screen
  const blocks = config.assignment_blocks?.length ? config.assignment_blocks : (draftMode === 'mapped' ? [{ id: `block-${Date.now()}`, endpoint_id: '', model: '', tasks: [] }] : []);

  // Compute which tasks are assigned across all blocks
  const assignedTasks: PrepTaskId[] = blocks.flatMap((b) => b.tasks);

  // Mapped mode block handlers
  const handleBlockAdd = () => {
    onConfigChange({
      ...config,
      assignment_blocks: [
        ...(config.assignment_blocks || []),
        { id: `block-${Date.now()}`, endpoint_id: '', model: '', tasks: [] }
      ]
    });
  };

  const handleBlockDelete = (blockId: string) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).filter(b => b.id !== blockId)
    });
  };

  const handleBlockEndpointChange = (blockId: string, endpointId: string) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, endpoint_id: endpointId, model: '' } : b
      )
    });
  };

  const handleBlockModelChange = (blockId: string, model: string) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, model } : b
      )
    });
  };

  const handleBlockAddTask = (blockId: string, taskId: PrepTaskId) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, tasks: [...b.tasks, taskId] } : b
      )
    });
  };

  const handleBlockRemoveTask = (blockId: string, taskId: PrepTaskId) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, tasks: b.tasks.filter(t => t !== taskId) } : b
      )
    });
  };

  const handleBlockEnableReasoningChange = (blockId: string, enabled: boolean) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, enable_reasoning: enabled } : b
      )
    });
  };

  const handleBlockAlwaysOnChange = (blockId: string, alwaysOn: boolean) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, always_on: alwaysOn } : b
      )
    });
  };

  const handleBlockConcurrencyChange = (blockId: string, concurrency: number) => {
    onConfigChange({
      ...config,
      assignment_blocks: (config.assignment_blocks || []).map(b => 
        b.id === blockId ? { ...b, concurrency } : b
      )
    });
  };
  
  const handleEmbeddingSourceChange = (source: ModelSource) => {
    onClearTestResult?.('embedding');
    onConfigChange({
      ...config,
      embedding: { ...config.embedding, source },
    });
  };
  
  const handleEmbeddingEndpointChange = async (endpointId: string) => {
    onClearTestResult?.('embedding');
    if (!endpointId || endpointId === '__disconnect__') {
      onConfigChange({
        ...config,
        embedding: { ...config.embedding, endpoint_id: undefined, model: undefined },
      });
      return;
    }
    onConfigChange({
      ...config,
      embedding: { ...config.embedding, endpoint_id: endpointId, model: undefined },
    });
    const models = await onFetchModels(endpointId, 'embedding');
    const suggested = findRecommended('embedding', models);
    if (suggested) {
      onConfigChange({
        ...config,
        embedding: { ...config.embedding, endpoint_id: endpointId, model: suggested },
      });
    }
  };
  
  const handleEmbeddingModelChange = (model: string) => {
    onClearTestResult?.('embedding');
    onConfigChange({
      ...config,
      embedding: { ...config.embedding, model },
    });
  };
  
  const handleSmallModelEndpointChange = async (endpointId: string) => {
    onClearTestResult?.('small');
    if (!endpointId || endpointId === '__disconnect__') {
      onConfigChange({
        ...config,
        small_model: { ...config.small_model, endpoint_id: undefined, model: undefined, enabled: false },
      });
      return;
    }
    onConfigChange({
      ...config,
      small_model: { ...config.small_model, endpoint_id: endpointId, model: undefined, enabled: true },
    });
    // Fetch models for the dropdown but don't auto-select — user must choose
    void onFetchModels(endpointId, 'small_model');
  };
  
  const handleSmallModelChange = (model: string) => {
    onClearTestResult?.('small');
    onConfigChange({
      ...config,
      small_model: { ...config.small_model, model, enabled: true },
    });
  };

  const handleSmallAlwaysOnChange = (always_on: boolean) => {
    onConfigChange({
      ...config,
      small_model: { ...config.small_model, always_on },
    });
  };


  
  const handleLargeModelEndpointChange = async (endpointId: string) => {
    onClearTestResult?.('large');
    if (!endpointId || endpointId === '__disconnect__') {
      onConfigChange({
        ...config,
        large_model: { ...config.large_model, endpoint_id: undefined, model: undefined, enabled: false },
      });
      return;
    }
    onConfigChange({
      ...config,
      large_model: { ...config.large_model, endpoint_id: endpointId, model: undefined, enabled: true },
    });
    // Fetch models for the dropdown but don't auto-select — user must choose
    void onFetchModels(endpointId, 'large_model');
  };
  
  const handleLargeModelChange = (model: string) => {
    onClearTestResult?.('large');
    onConfigChange({
      ...config,
      large_model: { ...config.large_model, model, enabled: true },
    });
  };

  const handleLargeAlwaysOnChange = (always_on: boolean) => {
    onConfigChange({
      ...config,
      large_model: { ...config.large_model, always_on },
    });
  };


  
  const handleCodeModelEndpointChange = async (endpointId: string) => {
    onClearTestResult?.('code');
    if (!endpointId || endpointId === '__disconnect__') {
      onConfigChange({
        ...config,
        code_model: { ...config.code_model, endpoint_id: undefined, model: undefined, enabled: false },
      });
      return;
    }
    onConfigChange({
      ...config,
      code_model: { ...config.code_model, endpoint_id: endpointId, model: undefined, enabled: true },
    });
    // Fetch models for the dropdown but don't auto-select — user must choose
    void onFetchModels(endpointId, 'code_model');
  };
  
  const handleCodeModelChange = (model: string) => {
    onClearTestResult?.('code');
    onConfigChange({
      ...config,
      code_model: { ...config.code_model, model, enabled: true },
    });
  };

  const handleCodeAlwaysOnChange = (always_on: boolean) => {
    onConfigChange({
      ...config,
      code_model: { ...config.code_model, always_on },
    });
  };


  // ── Swarm Coordinator handlers ─────────────────────────────
  // The coordinator slot drives Phase 1 (planning) and Phase 3 (synthesis) of
  // the Swarm pipeline. When `inherit_from_large` is true, the backend falls
  // back to large_model. Toggling inherit is non-destructive — we preserve
  // the user's previously picked endpoint/model so unchecking restores it.
  const coordinatorSlot = config.coordinator_model ?? { enabled: false, inherit_from_large: true };
  const coordinatorInherits = coordinatorSlot.inherit_from_large !== false;

  const handleCoordinatorInheritChange = (inherit: boolean) => {
    onClearTestResult?.('coordinator');
    onConfigChange({
      ...config,
      coordinator_model: { ...coordinatorSlot, inherit_from_large: inherit },
    });
  };

  const handleCoordinatorEndpointChange = async (endpointId: string) => {
    onClearTestResult?.('coordinator');
    if (!endpointId || endpointId === '__disconnect__') {
      onConfigChange({
        ...config,
        coordinator_model: { ...coordinatorSlot, endpoint_id: undefined, model: undefined, enabled: false, inherit_from_large: true },
      });
      return;
    }
    onConfigChange({
      ...config,
      coordinator_model: { ...coordinatorSlot, endpoint_id: endpointId, model: undefined, enabled: true, inherit_from_large: false },
    });
    void onFetchModels(endpointId, 'coordinator_model');
  };

  const handleCoordinatorModelChange = (model: string) => {
    onClearTestResult?.('coordinator');
    onConfigChange({
      ...config,
      coordinator_model: { ...coordinatorSlot, model, enabled: true, inherit_from_large: false },
    });
  };

  const handleCoordinatorAlwaysOnChange = (always_on: boolean) => {
    onConfigChange({
      ...config,
      coordinator_model: { ...coordinatorSlot, always_on },
    });
  };




  // Determine status for each slot
  const getEmbeddingStatus = () => {
    // A successful test result always means connected
    if (testResults['embedding']?.success) return 'connected';
    if (config.embedding.source === 'huggingface') {
      if (config.embedding.hf_download_progress !== undefined && config.embedding.hf_download_progress < 1) {
        return 'downloading';
      }
      return config.embedding.hf_downloaded ? 'connected' : 'not-configured';
    }
    if (!config.embedding.endpoint_id || !config.embedding.model) return 'not-configured';
    const epModels = availableModels[config.embedding.endpoint_id] || [];
    if (epModels.length === 0) return 'loading';
    return modelInList(config.embedding.model, epModels) ? 'connected' : 'disconnected';
  };
  
  const getSlotStatus = (slot: { enabled: boolean; endpoint_id?: string; model?: string }, slotKey: string) => {
    // A successful test result always means connected
    if (testResults[slotKey]?.success) return 'connected';
    if (!slot.endpoint_id || !slot.model) return 'not-configured';
    // Check if the endpoint still exists in saved_endpoints
    const epExists = config.saved_endpoints.some(e => e.id === slot.endpoint_id);
    if (!epExists) return 'disconnected';
    const epModels = availableModels[slot.endpoint_id] || [];
    // Only show 'loading' if a fetch is actually in progress
    if (epModels.length === 0) {
      return loadingModels[slot.endpoint_id] ? 'loading' : 'connected';
    }
    return modelInList(slot.model, epModels) ? 'connected' : 'disconnected';
  };
  

  return (
    <div className={cn('prep-ai-models-settings space-y-8', className)}>
      {/* Header + Mode Toggle */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold font-mono flex items-center gap-2 text-text">
              <Cpu className="w-6 h-6 text-primary" />
              AI Models
              <InfoTooltip 
                content="Learn how to choose and configure models." 
                href="https://docs.sourceprep.io/guides/models" 
              />
            </h2>
            <p className="text-sm text-text-muted mt-1">Configure LLMs for embedding and analysis</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="p-1 bg-surface-raised rounded-lg flex items-center border border-border">
              <div className="flex items-center gap-1 border-r border-border/50 pr-2 mr-2">
                <button
                  onClick={() => setDraftMode('structured')}
                  className={cn(
                    'px-4 py-1.5 text-xs rounded-md transition-all font-medium',
                    draftMode === 'structured'
                      ? 'bg-surface text-text shadow-sm'
                      : 'text-text-muted hover:text-text hover:bg-surface/50'
                  )}
                >
                  Structured
                </button>
                <button
                  onClick={() => setDraftMode('mapped')}
                  className={cn(
                    'px-4 py-1.5 text-xs rounded-md transition-all font-medium',
                    draftMode === 'mapped'
                      ? 'bg-surface text-text shadow-sm'
                      : 'text-text-muted hover:text-text hover:bg-surface/50'
                  )}
                >
                  Assigned
                </button>
              </div>
              <button
                onClick={async () => {
                  if (!isDraftDirty) return;
                  const newBlocks =
                    draftMode === 'mapped' && (config.assignment_blocks?.length ?? 0) === 0
                      ? [{ id: `block-${Date.now()}`, endpoint_id: '', model: '', tasks: [] }]
                      : (config.assignment_blocks ?? []);
                  await onModeApply?.(draftMode, newBlocks);
                }}
                disabled={!isDraftDirty}
                className={cn(
                  'inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
                  isDraftDirty
                    ? 'bg-primary text-surface hover:bg-primary/90 shadow-sm'
                    : 'bg-transparent text-text-muted cursor-not-allowed opacity-50'
                )}
              >
                <Save className="w-3.5 h-3.5" />
                Apply {draftMode === 'structured' ? 'Structured' : 'Assigned'} mode
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Two-column layout: Left (Embed) + Right (mode toggle + model cards OR assignment blocks) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* ══════ LEFT COLUMN — unchanged in both modes ══════ */}
        <div className="flex flex-col gap-6">
          {/* Embedding Model */}
          <ModelCard
            title="Embedding Model"
            description="Vector encoding for semantic search"
            icon={
              <svg className="w-5 h-5 text-info" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
              </svg>
            }
            info="Recommended: Built-in ONNX (nomic-embed-text-v1.5) — works offline, no Ollama needed. Alternatively, use nomic-embed-text via Ollama or an OpenAI-compatible cloud provider."
            source={config.embedding.source}
            endpoint={config.embedding.endpoint_id}
            model={config.embedding.model}
            endpoints={config.saved_endpoints}
            onEndpointChange={handleEmbeddingEndpointChange}
            availableModels={availableModels[config.embedding.endpoint_id || ''] || []}
            onModelChange={handleEmbeddingModelChange}
            onRefreshModels={() => config.embedding.endpoint_id && onFetchModels(config.embedding.endpoint_id)}
            loadingModels={loadingModels[config.embedding.endpoint_id || '']}
            cloudModels={cloudModels[config.embedding.endpoint_id || ''] || []}
            loadingCloudModels={loadingCloudModels[config.embedding.endpoint_id || '']}
            onFetchCloudModels={onFetchCloudModels}
            hfEnabled={true}
            hfRepoId="nomic-ai/nomic-embed-text-v1.5"
            hfDownloaded={config.embedding.hf_downloaded}
            hfDownloadProgress={config.embedding.hf_download_progress}
            onHFDownload={() => onHFDownload('embedding')}
            onSourceChange={handleEmbeddingSourceChange}
            status={getEmbeddingStatus()}
            onTest={() => onTestModel('embedding')}
            testResult={testResults['embedding']}
            testingConnection={testingSlot === 'embedding'}
          />

        </div>

        {/* ══════ RIGHT COLUMN — conditional content ══════ */}
        <div className="flex flex-col gap-6">
          {draftMode === 'structured' ? (
            <>
              {/* Fast Model */}
              <ModelCard
                title="Single / Fast Model"
                description="Fast analysis & parsing"
                icon={
                  <svg className="w-5 h-5 text-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                }
                info="Use a single powerful model here (like Claude/GPT) to handle both Fast and Thinking tasks, or combine a smaller local model with a larger one below."
                infoLink="https://docs.sourceprep.io/guides/models"
                endpoint={config.small_model.endpoint_id}
                model={config.small_model.model}
                alwaysOn={config.small_model.always_on}
                showAlwaysOn={isLocalProvider(endpointProviderFor(config.small_model.endpoint_id))}
                onAlwaysOnChange={handleSmallAlwaysOnChange}

                endpoints={config.saved_endpoints}
                onEndpointChange={handleSmallModelEndpointChange}
                availableModels={availableModels[config.small_model.endpoint_id || ''] || []}
                modelDetails={modelDetails[config.small_model.endpoint_id || '']}
                onModelChange={handleSmallModelChange}
                onRefreshModels={() => config.small_model.endpoint_id && onFetchModels(config.small_model.endpoint_id)}
                loadingModels={loadingModels[config.small_model.endpoint_id || '']}
                cloudModels={cloudModels[config.small_model.endpoint_id || ''] || []}
                loadingCloudModels={loadingCloudModels[config.small_model.endpoint_id || '']}
                onFetchCloudModels={onFetchCloudModels}
                status={getSlotStatus(config.small_model, 'small')}
                onTest={() => onTestModel('small')}
                testResult={testResults['small']}
                testingConnection={testingSlot === 'small'}
              />

              {/* Code Model */}
              <ModelCard
                title="Code Model"
                description="Code-aware edge discovery (Optional)"
                icon={
                  <svg className="w-5 h-5 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                }
                info="Optional code-specialized model for inferring cross-file relationships. Falls back to the Fast model if not configured. Best with code-tuned models like qwen2.5-coder or deepseek-coder."
                infoLink="https://docs.sourceprep.io/guides/models"
                endpoint={config.code_model?.endpoint_id}
                model={config.code_model?.model}
                alwaysOn={config.code_model?.always_on}
                showAlwaysOn={isLocalProvider(endpointProviderFor(config.code_model?.endpoint_id))}
                onAlwaysOnChange={handleCodeAlwaysOnChange}

                endpoints={config.saved_endpoints}
                onEndpointChange={handleCodeModelEndpointChange}
                availableModels={availableModels[config.code_model?.endpoint_id || ''] || []}
                modelDetails={modelDetails[config.code_model?.endpoint_id || '']}
                onModelChange={handleCodeModelChange}
                onRefreshModels={() => config.code_model?.endpoint_id && onFetchModels(config.code_model.endpoint_id)}
                loadingModels={loadingModels[config.code_model?.endpoint_id || '']}
                cloudModels={cloudModels[config.code_model?.endpoint_id || ''] || []}
                loadingCloudModels={loadingCloudModels[config.code_model?.endpoint_id || '']}
                onFetchCloudModels={onFetchCloudModels}
                status={getSlotStatus(config.code_model ?? { enabled: false }, 'code')}
                onTest={() => onTestModel('code')}
                testResult={testResults['code']}
                testingConnection={testingSlot === 'code'}
              />

              {/* Thinking Model (also Swarm Worker) */}
              <ModelCard
                title="Thinking Model"
                description="Deep reasoning · Swarm worker (Optional)"
                disabled={!config.small_model.model}
                icon={
                  <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                }
                endpoint={config.large_model.endpoint_id}
                model={config.large_model.model}
                alwaysOn={config.large_model.always_on}
                showAlwaysOn={isLocalProvider(endpointProviderFor(config.large_model.endpoint_id))}
                onAlwaysOnChange={handleLargeAlwaysOnChange}

                endpoints={config.saved_endpoints}
                onEndpointChange={handleLargeModelEndpointChange}
                availableModels={availableModels[config.large_model.endpoint_id || ''] || []}
                modelDetails={modelDetails[config.large_model.endpoint_id || '']}
                onModelChange={handleLargeModelChange}
                onRefreshModels={() => config.large_model.endpoint_id && onFetchModels(config.large_model.endpoint_id)}
                loadingModels={loadingModels[config.large_model.endpoint_id || '']}
                cloudModels={cloudModels[config.large_model.endpoint_id || ''] || []}
                loadingCloudModels={loadingCloudModels[config.large_model.endpoint_id || '']}
                onFetchCloudModels={onFetchCloudModels}
                status={getSlotStatus(config.large_model, 'large')}
                onTest={() => onTestModel('large')}
                testResult={testResults['large']}
                testingConnection={testingSlot === 'large'}
              />

              {/* Swarm Coordinator — routes planning/synthesis to a fast, JSON-reliable model */}
              <div className="flex flex-col gap-2">
                <div className="rounded-md border border-border/60 bg-surface-raised/40 px-3 py-2 text-[11px] text-text-muted leading-relaxed">
                  <span className="font-medium text-text">Swarm Coordinator (Optional):</span>{' '}
                  During Deep Enrichment, SourcePrep fans out per-file analysis to the Thinking Model
                  (the Worker) and uses a separate model to plan clusters and synthesize domain modules.
                  Assign a fast, JSON-reliable model here (e.g. Gemini Flash) to avoid token exhaustion
                  on reasoning-heavy workers like Kimi. Leave inherited to use the Thinking Model for both.
                </div>
                <ModelCard
                  title="Swarm Coordinator"
                  description={coordinatorInherits ? 'Inheriting Thinking Model' : 'Cluster routing & large-context synthesis'}
                  disabled={!config.large_model.model || coordinatorInherits}
                  icon={
                    <svg className="w-5 h-5 text-info" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2l2.39 4.84L20 8l-4 3.9.94 5.48L12 14.77l-4.94 2.6L8 11.9 4 8l5.61-1.16L12 2z" />
                    </svg>
                  }
                  info="Routes large-context planning and synthesis to a fast, JSON-reliable model (e.g. Gemini Flash). If left inherited, the Thinking Model handles both worker and coordinator roles."
                  infoLink="https://docs.sourceprep.io/guides/models"
                  endpoint={coordinatorSlot.endpoint_id}
                  model={coordinatorSlot.model}
                  alwaysOn={coordinatorSlot.always_on}
                  showAlwaysOn={isLocalProvider(endpointProviderFor(coordinatorSlot.endpoint_id))}
                  onAlwaysOnChange={handleCoordinatorAlwaysOnChange}
                  endpoints={config.saved_endpoints}
                  onEndpointChange={handleCoordinatorEndpointChange}
                  availableModels={availableModels[coordinatorSlot.endpoint_id || ''] || []}
                  modelDetails={modelDetails[coordinatorSlot.endpoint_id || '']}
                  onModelChange={handleCoordinatorModelChange}
                  onRefreshModels={() => coordinatorSlot.endpoint_id && onFetchModels(coordinatorSlot.endpoint_id)}
                  loadingModels={loadingModels[coordinatorSlot.endpoint_id || '']}
                  cloudModels={cloudModels[coordinatorSlot.endpoint_id || ''] || []}
                  loadingCloudModels={loadingCloudModels[coordinatorSlot.endpoint_id || '']}
                  onFetchCloudModels={onFetchCloudModels}
                  status={coordinatorInherits ? 'not-configured' : getSlotStatus(coordinatorSlot, 'coordinator')}
                  onTest={() => onTestModel('coordinator')}
                  testResult={testResults['coordinator']}
                  testingConnection={testingSlot === 'coordinator'}
                />
                <label className={cn(
                  'flex items-center gap-2 text-xs select-none pl-1',
                  !config.large_model.model ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                )}>
                  <input
                    type="checkbox"
                    className="w-3.5 h-3.5 rounded border-border bg-surface text-primary focus:ring-primary focus:ring-offset-surface cursor-pointer disabled:cursor-not-allowed"
                    checked={coordinatorInherits}
                    onChange={(e) => handleCoordinatorInheritChange(e.target.checked)}
                    disabled={!config.large_model.model}
                  />
                  <span className="text-text-muted">Inherit from Thinking Model (recommended for simple setups)</span>
                </label>
              </div>
            </>
          ) : (
            <>
              {/* Mapped Mode: Unassigned Tasks Banner */}
              <LLMAssignmentsPipeline blocks={blocks} fileCount={fileCount} />

              {/* Assignment Blocks */}
              {blocks.map((block) => (
                <LLMAssignmentBlockCard
                  key={block.id}
                  id={block.id}
                  endpointId={block.endpoint_id}
                  model={block.model}
                  tasks={block.tasks}
                  enableReasoning={block.enable_reasoning}
                  endpoints={config.saved_endpoints}
                  availableModels={availableModels[block.endpoint_id] || []}
                  loadingModels={loadingModels[block.endpoint_id]}
                  assignedTasks={assignedTasks}
                  onEndpointChange={handleBlockEndpointChange}
                  onModelChange={handleBlockModelChange}
                  onRefreshModels={(eid) => onFetchModels(eid)}
                  onAddTask={handleBlockAddTask}
                  onRemoveTask={handleBlockRemoveTask}
                  onEnableReasoningChange={handleBlockEnableReasoningChange}
                  onAlwaysOnChange={handleBlockAlwaysOnChange}
                  onConcurrencyChange={handleBlockConcurrencyChange}
                  onDelete={handleBlockDelete}
                  onTest={onAssignmentBlockTest ? (bid) => onAssignmentBlockTest(bid) : undefined}
                  testResult={assignmentBlockTestResults[block.id]}
                  testingConnection={assignmentBlockTesting === block.id}
                />
              ))}

              {/* Add Assignment Button */}
              <button
                onClick={handleBlockAdd}
                className="w-full py-3 border border-dashed border-border rounded-lg text-sm text-text-muted hover:text-text hover:border-primary/50 hover:bg-surface-raised transition-all flex items-center justify-center gap-2 group"
              >
                <Plus className="w-4 h-4 group-hover:scale-110 transition-transform" />
                Add LLM Assignment
              </button>
            </>
          )}
        </div>
      </div>

      {/* Advanced LLM Settings */}
      <AdvancedLLMSettings
        value={config.advanced ?? {
          enforce_cloud_token_safety: true,
          max_thinking_budget: 24576,
        }}
        onChange={(advanced) => onConfigChange({ ...config, advanced })}
      />

      {/* Endpoint Manager */}
      <EndpointManager
        endpoints={config.saved_endpoints}
        onAdd={onAddEndpoint}
        onEdit={onEditEndpoint}
        onDelete={onDeleteEndpoint}
        onTest={onTestEndpoint}
        computeNodes={computeNodes}
        onEndpointNodeChange={onEndpointNodeChange}
        adminPolicy={adminPolicy}
      />

      {/* Compute Profile — Enterprise/Team only */}
      {onMaxActiveProjectsChange && adminPolicy && (
        <div className="rounded-lg border border-border bg-surface p-4 space-y-4">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></svg>
            <h3 className="text-sm font-semibold text-text">Compute Profile</h3>
          </div>

          {onMaxActiveProjectsChange && maxActiveProjects !== undefined && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-subtle">Max Active Projects (Local Performance)</label>
              <Select
                size="sm"
                value={String(maxActiveProjects)}
                onChange={(e) => {
                  const val = e.target.value;
                  onMaxActiveProjectsChange(val === 'infinite' ? 'infinite' : parseInt(val));
                }}
                options={[
                  { value: '1', label: '1 (Conservative)' },
                  { value: '2', label: '2' },
                  { value: '3', label: '3 (Standard)' },
                  { value: '4', label: '4' },
                  { value: '5', label: '5' },
                  { value: 'infinite', label: 'Unlimited' },
                ]}
                className="w-full"
              />
              <p className="text-[10px] text-text-muted leading-relaxed">
                This is a local performance safeguard to prevent your computer from overloading. It limits how many projects can run LLM pipelines simultaneously. Increase it if your hardware can handle the concurrency.

              </p>
            </div>
          )}

          {/* Compute Nodes — CRUD Panel */}
          <ComputeNodePanel
            nodes={computeNodes ?? config.compute_nodes ?? []}
            endpoints={config.saved_endpoints}
            onAdd={onComputeNodeAdd}
            onUpdate={onComputeNodeUpdate}
            onDelete={onComputeNodeDelete}
          />
        </div>
      )}

      {/* Pipeline Activity — visible to all users.
          Phase 119 Task 16: also home for the developer-mode "reset
          discovered concurrency ceiling" wrench. The block renders if
          there is *either* live activity OR cloud nodes for which a
          ceiling reset is meaningful, so power users can reach the
          control even when the queue is empty. */}
      {schedulerStatus && (() => {
        const nodeEntries = Object.entries(schedulerStatus.nodes);
        const hasActivity = nodeEntries.some(([, n]) => n.current_load > 0 || n.queued.length > 0);
        const cloudNodeIds = nodeEntries
          .map(([nid]) => nid)
          .filter((nid) => nid.startsWith('cloud:'));
        const showResetPanel = Boolean(baseUrl) && cloudNodeIds.length > 0;
        if (!hasActivity && !showResetPanel) return null;
        return (
          <div className="rounded-lg border border-border bg-surface p-4 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <label className="text-xs font-medium text-text-subtle pt-0.5">Pipeline Activity</label>
              {showResetPanel && (
                <div className="shrink-0">
                  <ConcurrencyResetPanel
                    cloudNodeIds={cloudNodeIds}
                    baseUrl={baseUrl as string}
                  />
                </div>
              )}
            </div>
            {nodeEntries.map(([nodeId, node]) => {
              if (node.current_load === 0 && node.queued.length === 0) return null;
              const activeEntries = Object.entries(node.active);
              return (
                <div key={nodeId} className="space-y-1.5">
                  {activeEntries.length > 0 && (
                    <div className="space-y-1">
                      {activeEntries.map(([projId, stageId]) => (
                        <div key={projId} className="flex items-center gap-2 text-[10px] px-2 py-1 rounded bg-primary/5 border border-primary/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" />
                          <span className="text-text-muted truncate">{projId.slice(0, 12)}</span>
                          <span className="text-primary font-medium">{stageId}</span>
                          <span className="ml-auto text-text-muted">{node.current_load}/{node.max_concurrent}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {node.queued.length > 0 && (
                    <div className="space-y-1">
                      {node.queued.map((q, i) => (
                        <div key={i} className="flex items-center gap-2 text-[10px] px-2 py-1 rounded bg-amber-500/5 border border-amber-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                          <span className="text-text-muted truncate">{q.project_id.slice(0, 12)}</span>
                          <span className="text-amber-500 font-medium">queued: {q.stage}</span>
                          <span className="ml-auto text-text-muted">{Math.round(q.waiting_seconds)}s</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })()}

      {/* Info Card */}
      <div className="rounded-lg bg-surface-raised border border-border p-4 flex gap-3">
        <Info className="w-5 h-5 text-info shrink-0 mt-0.5" />
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold font-mono text-text">Model Recommendations (Ollama)</h4>
            <a href="https://docs.sourceprep.io/guides/model-advisor" target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">Setup Advisor →</a>
          </div>
          <ul className="text-xs text-text-muted space-y-1.5 list-disc pl-4">
            <li><strong>Embedding:</strong> nomic-embed-text-v1.5 (Built-in ONNX — no Ollama needed)</li>
            <li>
              <strong>Fast:</strong> <a href="https://ollama.com/library/qwen3" target="_blank" rel="noreferrer" className="text-primary hover:underline">qwen3:8b</a> (5.2GB) — strong quality for fast tasks. Alt: qwen3:14b (9.3GB) for better output
            </li>
            <li>
              <strong>Thinking:</strong> <a href="https://ollama.com/library/qwen3" target="_blank" rel="noreferrer" className="text-primary hover:underline">qwen3:8b</a> (5.2GB) — strong reasoning. Alt: qwen3:14b (9.3GB) or qwen3:30b MoE (19GB) for better quality
            </li>
            <li><strong>Code:</strong> <a href="https://ollama.com/library/qwen3-coder" target="_blank" rel="noreferrer" className="text-primary hover:underline">qwen3-coder:30b</a> MoE (19GB, 3.3B active) — best code model. Alt: qwen2.5-coder:7b (optional — falls back to Fast model)</li>
            <li><strong>Swarm Coordinator:</strong> Gemini 3 Flash or any fast, JSON-reliable cloud model. Used to plan clusters and synthesize domain modules during Deep Enrichment. Optional — falls back to Thinking Model.</li>
            <li><strong>Compression:</strong> LOD extracts code at configurable detail levels (no model needed)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
