// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/**
 * The picker's data contract.
 *
 * Two rules hold this package together, and everything else follows from them:
 *
 * 1. **No role names.** Halbert, SourcePrep and LinuxBrain each name their
 *    model slots differently. The package renders whatever {@link AppRole}
 *    array it is handed and never mentions a slot by name.
 * 2. **No I/O.** The package performs no `fetch`. Every read and write goes
 *    through the injected {@link ModelPickerTransport}, so a host can back it
 *    with its own API, a Tauri command, or a stub in a test.
 *
 * Copy rule for anything rendered from this package: name providers, never
 * models. Model names come from the user's own configuration at runtime.
 */

/** Endpoint kinds the ecosystem knows how to talk to. */
export type ProviderId =
  | 'ollama'
  | 'lm-studio'
  | 'openai'
  | 'openai-compatible'
  | 'anthropic'
  | 'google'
  | 'azure-openai'

/** A configured place models can be fetched from. */
export interface SavedEndpoint {
  id: string
  name: string
  provider: ProviderId
  url: string
  /**
   * Present only for endpoints that need one. The picker treats this as
   * opaque, never logs it, and renders it masked.
   */
  apiKey?: string
}

/** What a model can do, as far as the host was able to determine. */
export interface ModelCapabilities {
  tools?: boolean
  vision?: boolean
  reasoning?: boolean
  /** Context ceiling in tokens, when known. */
  contextWindow?: number
}

/** A model offered by an endpoint. */
export interface DiscoveredModel {
  /** Wire name, exactly as the endpoint reports it. */
  id: string
  /** Display name; defaults to `id` when the endpoint offers nothing better. */
  name: string
  endpointId: string
  provider: ProviderId
  /** Runs on this machine — no data leaves it. Drives the privacy badge. */
  isLocal: boolean
  capabilities: ModelCapabilities
}

/**
 * One slot the host wants filled. The host owns the vocabulary: Halbert passes
 * `chat_model`, SourcePrep passes `small_model`, and the picker treats both as
 * opaque keys.
 */
export interface AppRole {
  id: string
  label: string
  description: string
  /** Only offer models that can call tools. */
  requiresTools?: boolean
  /** Only offer multimodal models. */
  requiresVision?: boolean
  /** An empty assignment is valid; the host has a fallback. */
  optional?: boolean
}

/** What a role currently points at. */
export interface RoleAssignment {
  endpointId: string
  model: string
  enabled: boolean
}

/**
 * Runtime tier. `auto` is the absence of a pin rather than a third mode — it
 * means "let the host route this turn".
 */
export type Tier = 'guide' | 'specialist' | 'vision' | 'auto'

/** A per-turn choice made from the pill, the popover, or a slash command. */
export interface ModelSelection {
  /** Exact model name. Pins the turn and bypasses the host's router. */
  model?: string
  tier?: Tier
  /** Which endpoint the model came from; disambiguates identical names. */
  endpointId?: string
}

export interface EndpointTestResult {
  ok: boolean
  message: string
  models?: string[]
}

/** One locally-running inference server. */
export interface LocalEngine {
  running: boolean
  url: string
  models: string[]
  version?: string | null
}

export interface LocalDiscovery {
  ollama: LocalEngine
  lmStudio: LocalEngine
}

/** Everything the picker reads and writes, in the host's own storage. */
export interface PickerConfig {
  endpoints: SavedEndpoint[]
  /** Keyed by {@link AppRole.id}. */
  assignments: Record<string, RoleAssignment>
  /**
   * Providers the host's chat runtime can actually call. Others stay listable
   * and testable but are excluded from role dropdowns and badged — the fix for
   * "tests green in settings, fails in chat".
   */
  chatCapableProviders: ProviderId[]
}

/**
 * The single seam between this package and any host.
 *
 * Keeping every call here is what lets the same components run against
 * Halbert's FastAPI routes, SourcePrep's daemon, or a plain object in a test —
 * and it is why extracting this package to its own repository is a move rather
 * than a rewrite.
 */
export interface ModelPickerTransport {
  loadConfig(): Promise<PickerConfig>
  /** Merge a partial config and return the result the host actually stored. */
  saveConfig(patch: Partial<PickerConfig>): Promise<PickerConfig>
  listModels(endpoint: SavedEndpoint): Promise<DiscoveredModel[]>
  testEndpoint(endpoint: SavedEndpoint): Promise<EndpointTestResult>
  /** Slot-level check: can this endpoint actually run this model? */
  testModel?(endpoint: SavedEndpoint, model: string): Promise<EndpointTestResult>
  /**
   * Probe the standard local ports. Optional because a host without a server
   * side (or without loopback access) simply omits it, and the picker degrades
   * to manual endpoint entry.
   */
  discoverLocal?(): Promise<LocalDiscovery>
}

/** Presentation metadata for a provider. Labels name vendors, never models. */
export interface ProviderDescriptor {
  id: ProviderId
  label: string
  /** Runs on the user's machine. */
  isLocal: boolean
  /** Requires a credential before it can list or answer. */
  needsApiKey: boolean
  /** Pre-filled when the user adds this provider. */
  defaultUrl?: string
}

export const PROVIDERS: readonly ProviderDescriptor[] = [
  { id: 'ollama', label: 'Ollama', isLocal: true, needsApiKey: false, defaultUrl: 'http://localhost:11434' },
  { id: 'lm-studio', label: 'LM Studio', isLocal: true, needsApiKey: false, defaultUrl: 'http://localhost:1234' },
  { id: 'openai', label: 'OpenAI', isLocal: false, needsApiKey: true, defaultUrl: 'https://api.openai.com/v1' },
  { id: 'anthropic', label: 'Anthropic', isLocal: false, needsApiKey: true, defaultUrl: 'https://api.anthropic.com' },
  { id: 'google', label: 'Google', isLocal: false, needsApiKey: true, defaultUrl: 'https://generativelanguage.googleapis.com' },
  { id: 'azure-openai', label: 'Azure OpenAI', isLocal: false, needsApiKey: true },
  { id: 'openai-compatible', label: 'OpenAI-compatible', isLocal: false, needsApiKey: false },
] as const

export function providerDescriptor(id: ProviderId): ProviderDescriptor {
  return (
    PROVIDERS.find((p) => p.id === id) ?? {
      id,
      label: id,
      isLocal: false,
      needsApiKey: false,
    }
  )
}
