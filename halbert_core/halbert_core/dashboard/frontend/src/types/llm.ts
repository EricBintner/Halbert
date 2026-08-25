/**
 * LLM Configuration Types
 *
 * Copied from @prep/ui types.ts — the subset needed by the LLM model picker
 * components. This is the shared schema between Halbert and SourcePrep.
 * When the unified-model-picker design is fully realized, both apps will
 * read/write the same YAML file using these types.
 */

// ============================================================
// Task IDs (for mapped mode — Halbert hides this by default)
// ============================================================

export type PrepTaskId =
  | 'catalogue'
  | 'inferred_edges'
  | 'enrichment'
  | 'group_reasoning'
  | 'clustering'
  | 'atlas'
  | 'deepening'
  | 'search_intent'
  | 'audit'
  | 'augmentation';

export const ALL_TASK_IDS: PrepTaskId[] = [
  'inferred_edges', 'catalogue', 'enrichment', 'group_reasoning', 'clustering',
  'atlas', 'deepening', 'search_intent', 'audit', 'augmentation',
];

export const TASK_LABELS: Record<PrepTaskId, string> = {
  catalogue: 'Catalogue Summarization',
  inferred_edges: 'Inferred Edge Discovery',
  enrichment: 'Deep Reasoning',
  group_reasoning: 'Group Reasoning',
  clustering: 'Module Synthesis',
  atlas: 'Atlas Generation',
  deepening: 'Deepening Loop',
  search_intent: 'Search Preprocessing',
  audit: 'Automated Audits',
  augmentation: 'Trace Augmentation',
};

export const TASK_TAGS: Record<PrepTaskId, string> = {
  inferred_edges: 'Code',
  catalogue: 'Fast',
  search_intent: 'Fast',
  augmentation: 'Fast',
  enrichment: 'Reasoning (optional)',
  group_reasoning: 'Reasoning (recommended)',
  clustering: 'Reasoning (optional)',
  atlas: 'Reasoning (optional)',
  deepening: 'Reasoning (optional)',
  audit: 'Reasoning (optional)',
};

export type CloudPreference = 'local-preferred' | 'cloud-preferred' | 'neutral';

export const TASK_CLOUD_PREF: Record<PrepTaskId, CloudPreference> = {
  catalogue: 'local-preferred',
  search_intent: 'local-preferred',
  augmentation: 'local-preferred',
  inferred_edges: 'neutral',
  enrichment: 'neutral',
  group_reasoning: 'cloud-preferred',
  clustering: 'neutral',
  atlas: 'cloud-preferred',
  deepening: 'cloud-preferred',
  audit: 'cloud-preferred',
};

// ============================================================
// LLM Configuration Types
// ============================================================

export type AssignmentMode = 'structured' | 'mapped';

export interface LLMAssignmentBlock {
  id: string;
  endpoint_id: string;
  model: string;
  tasks: PrepTaskId[];
  enable_reasoning?: boolean;
  always_on?: boolean;
  concurrency?: number;
}

export type LLMProvider = 'ollama' | 'openai' | 'openai-compatible' | 'lm-studio' | 'anthropic' | 'google';

export type ModelSource = 'endpoint' | 'huggingface';

export type ComputeHardwareProfile = 'apple_silicon' | 'nvidia' | 'amd' | 'intel' | 'cloud';

export interface ComputeNode {
  id: string;
  name: string;
  type: 'local' | 'remote' | 'cloud';
  hardware_profile?: ComputeHardwareProfile;
  max_concurrent: number;
  gpu_name?: string;
  gpu_vram_gb?: number;
  endpoint_ids: string[];
}

export interface SavedEndpoint {
  id: string;
  name: string;
  provider: LLMProvider;
  url: string;
  api_key?: string;
  compute_node_id?: string | null;
  local_concurrency?: number;
  cloud_concurrency?: number;
  plan_tier?: string;
}

export interface EmbeddingConfig {
  source: ModelSource;
  endpoint_id?: string;
  model?: string;
  hf_repo_id?: string;
  hf_downloaded?: boolean;
  hf_model_path?: string;
  hf_download_progress?: number;
}

export interface LLMSlotConfig {
  enabled: boolean;
  endpoint_id?: string;
  model?: string;
  always_on?: boolean;
  concurrency?: number;
}

export interface AdvancedLLMSettings {
  enforce_cloud_token_safety: boolean;
  max_thinking_budget: number;
}

export interface LLMConfig {
  assignment_mode?: AssignmentMode;
  embedding: EmbeddingConfig;
  small_model: LLMSlotConfig;
  large_model: LLMSlotConfig;
  code_model: LLMSlotConfig;
  coordinator_model?: LLMSlotConfig & { inherit_from_large?: boolean };
  advanced?: AdvancedLLMSettings;
  saved_endpoints: SavedEndpoint[];
  compute_nodes?: ComputeNode[];
  assignment_blocks?: LLMAssignmentBlock[];
  model_context_cache?: Record<string, number>;
}

export type ModelSlotType = 'embedding' | 'small' | 'large' | 'code' | 'coordinator';

export interface HFDownloadStatus {
  model_type: ModelSlotType;
  status: 'idle' | 'downloading' | 'complete' | 'error';
  progress?: number;
  bytes_downloaded?: string;
  error?: string;
}

export type ModelReadinessStatus = 'not_found' | 'downloaded' | 'loading' | 'ready' | 'error' | 'unknown';

export interface ModelStatusResult {
  status: ModelReadinessStatus;
  message: string;
  model: string;
  provider: string;
  details?: Record<string, unknown>;
}

export interface EndpointTestResult {
  success: boolean;
  message: string;
  models?: string[];
  model_status?: ModelReadinessStatus;
  warnings?: string[];
  recommendations?: Record<string, any>;
}

// ============================================================
// Scheduler / Concurrency Types (used by AIModelsSettings props)
// ============================================================

export interface SchedulerNodeStatus {
  max_concurrent: number;
  current_load: number;
  active: Record<string, string>;
  queued: Array<{
    project_id: string;
    stage: string;
    waiting_seconds: number;
  }>;
}

export interface SchedulerStatus {
  nodes: Record<string, SchedulerNodeStatus>;
}

// ============================================================
// Admin Policy Types (used by EndpointManager)
// ============================================================

export interface ProviderPolicy {
  allowed_providers: string[];
  blocked_providers: string[];
  allow_local_providers: boolean;
  allow_user_endpoints: boolean;
  allow_user_api_keys: boolean;
  locked_endpoints: Array<Record<string, any>>;
}

export interface ModelPolicy {
  allowed_models: string[];
  blocked_models: string[];
  require_approved_models: boolean;
  allow_any_local_model: boolean;
  slot_overrides?: Record<string, {
    allowed_models?: string[];
    blocked_models?: string[];
    require_approved_models?: boolean;
  }>;
}

export interface DataPolicy {
  never_send_globs: string[];
  redact_patterns: string[];
  block_unapproved_cloud: boolean;
  allowed_destinations: string[];
}

export interface SyncPolicy {
  require_s3_https: boolean;
  allowed_s3_endpoints: string[];
}

export interface NetworkPolicy {
  block_metadata_endpoints: boolean;
  allowed_ports: number[];
}

export interface BudgetPolicy {
  monthly_token_limit: number;
  monthly_cost_limit_usd: number;
  alert_threshold_percent: number;
}

export interface AdminPolicy {
  provider: ProviderPolicy;
  model: ModelPolicy;
  data: DataPolicy;
  sync: SyncPolicy;
  network: NetworkPolicy;
  budgets: BudgetPolicy;
  enforcement_mode: 'suggest' | 'enforce';
}

// ============================================================
// Slot Status Types
// ============================================================

export interface LLMSlotStatus {
  endpoint_id?: string;
  model?: string;
  status: 'connected' | 'disconnected' | 'unknown';
  latency_ms?: number;
  error?: string;
}

export interface RunningTask {
  task_id: PrepTaskId;
  project_id: string;
  stage: string;
  started_at: number;
}

export interface SwarmPhaseBucket {
  active: number;
  model: string | null;
}

export interface SwarmPhasesBreakdown {
  coordinator: SwarmPhaseBucket;
  workers: SwarmPhaseBucket;
  synthesizer: SwarmPhaseBucket;
}

export interface LLMSlotsStatus {
  assignment_mode?: AssignmentMode;
  running_task_id?: PrepTaskId | null;
  running_tasks?: RunningTask[];
  embedding: LLMSlotStatus;
  small_model: LLMSlotStatus;
  large_model: LLMSlotStatus;
  code_model: LLMSlotStatus;
  coordinator_model?: LLMSlotStatus;
  swarm_phases?: SwarmPhasesBreakdown | null;
}
