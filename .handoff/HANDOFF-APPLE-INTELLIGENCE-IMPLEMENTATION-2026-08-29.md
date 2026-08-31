# Apple Intelligence Integration: Implementation Plan

**Date:** 2026-08-29
**Status:** Plan scrutinized and approved — implementation in progress. **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** that handoff's Finding 5 / S6 adds a scope boundary — Apple Intelligence is local-only; all mechanism work in this plan remains valid.
**Scope:** Build the mechanisms for Apple Intelligence to serve as the `secure_model` (and zero-setup `chat_model` on 16-24GB Macs) on qualifying Apple Silicon Macs, with Metal GPU detection gating availability. Apple Intelligence is local-only — it serves the Mac's own slots exclusively. It is never exposed as a peer/fleet compute backend: peer compute requests arriving at a Mac route to Ollama (7B-14B), not `apple-foundation`, and mDNS `compute_backends` advertises `ollama`/`vllm` only (see `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Finding 5).

**Reads with:**
- [`documentation/design/APPLE-INTELLIGENCE-MACOS-ON-DEVICE-STRATEGY.md`](../documentation/design/APPLE-INTELLIGENCE-MACOS-ON-DEVICE-STRATEGY.md)
- [`.handoff/HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`](./HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md)
- [`.handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](./HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md) — Finding 5 / S6 (Apple Intelligence is local-only, never a peer compute backend) and Finding 1 / S1 (variant gating of `secure_model` auto-provisioning)

---

## 1. Architecture Decision: Tauri + Swift Sidecar

Apple's `FoundationModels` framework is **Swift-only**. There is no Python binding, no Rust binding, and no C FFI. You cannot call `SystemLanguageModel` from Tauri's Rust core or from the Python backend.

**The solution is Option A from the design doc: a Swift sidecar binary.** Tauri v2 bundles it via `externalBin`, launches it on app start, and kills it on exit. The sidecar runs a tiny localhost HTTP server on `http://127.0.0.1:11435` that implements the OpenAI-compatible `/v1/chat/completions` wire format, mapped to `LanguageModelSession`. **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` (Finding 5):** the loopback binding is permanent by design, not an incidental implementation detail. Because the bridge speaks OpenAI-compatible HTTP, it would technically work as a peer-serving endpoint — loopback binding plus endpoint non-advertisement are the two guards that must hold forever. The bridge must never be bound to a LAN interface, registered with the federated compute endpoint (`compute_endpoint.py`), or advertised to peers. Loopback is not just `secure_model` enforcement; it is the peer-isolation boundary.

This plugs into infrastructure that already exists:
- `_call_openai_compatible()` in `client.py` already speaks the wire format
- `_is_local_url()` in `llm_config.py` already enforces loopback for `secure_model`
- The model-picker already supports local OpenAI-compatible endpoints
- Tauri's `externalBin` already bundles the Python API sidecar (`binaries/halbert-api`)

**No wire format changes. No Python-to-Swift bridge. No PyObjC.** The Python backend treats Apple Intelligence as just another OpenAI-compatible local endpoint with a distinct provider ID.

---

## 2. Availability Gating

Apple Intelligence is auto-provisioned only when ALL of:

| Check | Method | Threshold |
|-------|--------|-----------|
| Apple Silicon | `is_mac_apple_silicon()` (existing) | `arm64` architecture |
| macOS version | `platform.mac_ver()` | >= 15.1 (Sequoia / Darwin 24.1+) |
| Unified memory | `get_unified_memory_gb()` (existing) | >= 16GB (Halbert-specific floor) |
| Metal GPU | New `detect_metal_gpu()` | Metal support detected |
| Bridge running | Probe `http://127.0.0.1:11435/v1/health` | HTTP 200 (OR eligibility check passes) |

**Why 16GB, not Apple's 8GB official floor:** macOS + WindowServer (~4-5GB) + Halbert + dashboard + the on-device model (~2.5-3GB ANE) leaves nothing on an 8GB machine. 16GB is the Halbert-specific operational minimum.

**Metal gating rationale:** Metal is implied by Apple Silicon, but an explicit check is defensive — it catches VMs (UTM/Parallels on Apple Silicon hypervisor) that report `arm64` but have no Metal GPU, and it lets us display the GPU info in the UI.

**Variant prerequisite (added 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`):** hardware eligibility alone is not sufficient — auto-provisioning also requires the active variant to run local model slots (`sysadmin`). On `home`/`home-light` variants the provisioning is skipped entirely (see Section 4).

---

## 3. Provider Design: `apple-foundation`

A dedicated provider ID, not a reuse of `openai-compatible`:

- **Distinct UI badge:** "Apple Intelligence (Built-in)" with a Cpu/ANE icon
- **Explicit local-only enforcement (three layers, revised 2026-08-30):** (1) `isLocal: true` in the picker and loopback URL in `secure_model`; (2) the Swift bridge binds `127.0.0.1` only; (3) federation — the peer compute endpoint on a Mac routes peer requests to Ollama and never proxies to `apple-foundation`; mDNS `compute_backends` advertises `ollama`/`vllm` only; `PeerProvider.list_models()` exposes only Ollama models to peers (Finding 5)
- **Provider-specific routing:** The tier router and client can special-case `apple-foundation` (e.g. no API key needed, tool-calling via `@Tool` protocol, streaming via `streamRespond`)
- **Wire format:** Still OpenAI-compatible — the bridge implements `/v1/chat/completions`, so `_call_openai_compatible()` handles it with no new adapter

Constants:
```
APPLE_FOUNDATION_URL    = "http://127.0.0.1:11435"
APPLE_FOUNDATION_MODEL  = "apple-foundation-3b"
APPLE_FOUNDATION_PROVIDER = "apple-foundation"
```

Port 11435 is distinct from Ollama (11434) and LM Studio (1234).

---

## 4. Auto-Provisioning Logic

On first boot (no saved endpoints), when Apple Intelligence is available:

1. Register endpoint `ep_apple_foundation` with `provider: "apple-foundation"`, `name: "Apple Intelligence (On-Device)"`, `url: "http://127.0.0.1:11435"`
2. Assign `secure_model` to this endpoint + `apple-foundation-3b` model
3. **16-24GB Macs (single-model rule):** Also assign `chat_model` to the same endpoint + model — zero-setup conversation out of the box
4. **32GB+ Macs:** Leave `chat_model` unset — the user should configure cloud or a larger local model
5. Log: `"Apple Intelligence detected — configured as secure_model (and chat_model on <16-24GB>)"`

**Variant gating (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`):** steps 1-3 (endpoint registration and slot assignment) apply only on variants that run local model slots (`sysadmin`). If the active variant is `home` or `home-light`, skip the auto-provisioning entirely: Finding 1 / S1 removes `secure_model` from those variants (the slot stays for `sysadmin` only), and Findings 3 / 4 mean an HA node runs no local LLM at all — its `chat_model` and `specialist_model` resolve to the compute peer (`peer://workstation:8000`) and the workstation's picker governs. The provisioned endpoint is for this Mac's own Halbert only and is never exposed to peers (Finding 5).

This runs alongside the existing `ensure_local_ollama_endpoint()` call in `GET /llm/config`. If both Apple Intelligence and Ollama are available, both endpoints are registered; the slot assignments follow the rules above.

**Graceful degradation:** If the bridge isn't running (Swift binary not yet built/bundled), the endpoint is registered but connection-refused. `get_secure_model()` returns the configured slot; callers fall back to template thoughts or the chat model as they already do. The system is correct but inert until the bridge exists.

---

## 5. Pre-Existing Bugs Fixed as Part of This Work

### Bug 1: `secure_model` missing from model-picker transport
`modelPickerTransport.ts` `toAssignments()` and `RawLlmConfig` only map `chat_model`, `specialist_model`, `vision_model` — `secure_model` is defined as a role in `halbertModelRoles.ts` but the transport never sends or receives it. The picker can display the secure slot but cannot edit it.

**Fix:** Add `secure_model: RawSlot` to `RawLlmConfig` and `secure_model: toRoleAssignment(llm.secure_model)` to `toAssignments()`.

### Bug 2: `requiresLocal` filter requires an installed model (Edge Case 1 from handoff)
`RoleAssignmentRow.tsx` filters endpoints for `requiresLocal` roles by checking `model?.isLocal ?? false` — which requires a discovered model on that endpoint. The Apple Intelligence endpoint has no "installed models" in the Ollama sense (the model is built-in), so it would be filtered out of the Secure dropdown entirely.

**Fix:** Filter by `providerDescriptor(e.provider).isLocal` instead of requiring a discovered model. This also fixes the fresh-install Ollama case from the handoff.

---

## 6. File-by-File Change List

### Layer 1: Python Backend — Detection & Auto-Provisioning

#### 6.1 `halbert_core/halbert_core/utils/platform.py`
**Add:**
- `detect_metal_gpu() -> Optional[Dict[str, Any]]` — runs `system_profiler SPDisplaysDataType -json`, parses for Metal support, returns `{metal_version, gpu_name}` or None. Non-Mac returns None.
- `get_macos_version() -> Optional[Tuple[int, int]]` — returns `(major, minor)` from `platform.mac_ver()`, or None on non-Mac.
- `apple_intelligence_eligible(min_ram_gb: int = 16) -> bool` — composite: `is_mac_apple_silicon()` AND macOS >= 15.1 AND `get_unified_memory_gb() >= min_ram_gb` AND `detect_metal_gpu() is not None`.

**No changes to existing functions.**

#### 6.2 `halbert_core/halbert_core/model/hardware_detector.py`
**Add to `HardwareCapabilities` dataclass:**
- `metal_gpu: Optional[Dict[str, Any]] = None` — Metal GPU info (`{metal_version, gpu_name}`)
- `apple_intelligence_available: bool = False` — composite eligibility + bridge probe
- `apple_intelligence_bridge_running: bool = False` — whether the Swift bridge answered health probe

**Add method:**
- `detect_apple_intelligence_available() -> bool` — probes `http://127.0.0.1:11435/v1/health` (0.5s timeout); if bridge answers, returns True. Falls back to `apple_intelligence_eligible()` when bridge is not running (host qualifies but bridge not yet bundled).

**Update `detect()`:**
- On Apple Silicon: populate `metal_gpu` via `platform.detect_metal_gpu()`
- On Apple Silicon: populate `apple_intelligence_available` and `apple_intelligence_bridge_running` via the new method

**Update `to_dict()`:** include the three new fields.

#### 6.3 `halbert_core/halbert_core/model/client.py`
**Add to `OPENAI_COMPATIBLE_PROVIDERS`:**
```python
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "openai-compatible", "lm-studio", "apple-foundation"})
```

**`CHAT_CAPABLE_PROVIDERS`** automatically includes it (it's the union with `OPENAI_COMPATIBLE_PROVIDERS`).

**No new adapter needed** — `_call_openai_compatible()` handles the wire format. The bridge implements OpenAI's `/v1/chat/completions`.

**`get_secure_model()`** already works — it resolves the slot and returns `(model, url, provider)`.

#### 6.4 `halbert_core/halbert_core/model/llm_config.py`
**Add constants:**
```python
APPLE_FOUNDATION_URL = "http://127.0.0.1:11435"
APPLE_FOUNDATION_MODEL = "apple-foundation-3b"
APPLE_FOUNDATION_PROVIDER = "apple-foundation"
```

**Add functions:**
- `ensure_apple_foundation_endpoint() -> str` — like `ensure_ollama_endpoint()` but creates/returns the `apple-foundation` endpoint at `APPLE_FOUNDATION_URL` with name "Apple Intelligence (On-Device)".
- `auto_provision_apple_intelligence(hardware: HardwareCapabilities, variant: str) -> bool` — called on first boot when no endpoints are saved AND `hardware.apple_intelligence_available`:
  1. If `variant` is `home` or `home-light`: return False without registering anything — those variants run no local LLM (Findings 1 / 3 / 4)
  2. `ensure_apple_foundation_endpoint()`
  3. `set_slot("secure_model", APPLE_FOUNDATION_MODEL, ep_id)` (`secure_model` is sysadmin-only per Finding 1 / S1; the early return in step 1 already excludes `home`/`home-light`)
  4. If `hardware.unified_memory_gb` in [16, 24]: also `set_slot("chat_model", APPLE_FOUNDATION_MODEL, ep_id)`
  5. Log the provisioning
  6. Return True

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** the `variant` parameter above is new — Finding 1 / S1 removes `secure_model` from `home`/`home-light` variants, and code verification confirmed the current `auto_provision.py` assigns `secure_model` whenever the slot is empty with no variant check (that gating is work item W1). The step-1 early return also skips the `chat_model` assignment on `home`/`home-light`: per Findings 3 / 4 those variants' `chat_model`/`specialist_model` resolve to the compute peer and the workstation's picker governs — no local model is provisioned. GAP 6 below relocates this function to a new `model/auto_provision.py`; the `variant` parameter is added as part of that move. The provisioned endpoint serves this Mac's own Halbert only and is never advertised to peers (Finding 5).

**`_is_local_url()`** already accepts `127.0.0.1` — no change needed for `secure_model` enforcement.

#### 6.5 `halbert_core/halbert_core/model/config_wizard.py`
**Update `run_auto()` and `run_interactive()`:**
- Before the Ollama model lookup, check `hardware.apple_intelligence_available`
- If True: call `auto_provision_apple_intelligence(hardware, variant)` (the active variant, per the 2026-08-30 revision above — on `home`/`home-light` it returns False and nothing is provisioned) and log "Apple Intelligence (On-Device) detected — configured as secure model"
- On 16-24GB Macs (variants that run local slots, i.e. `sysadmin`): `chat_model` is set to Apple Intelligence; skip Ollama model lookup for chat (still list installed Ollama models for specialist if the user wants one). On `home`/`home-light` the `chat_model` is never set here — it resolves to the compute peer (Findings 3 / 4)
- On 32GB+ Macs: `chat_model` left unset; proceed with Ollama model lookup as today
- In `run_interactive()`: print Apple Intelligence info in the hardware summary

**Update `_build_config()`:**
- Add the Apple Intelligence endpoint to `saved_endpoints` when `hardware.apple_intelligence_available` AND the active variant runs local model slots (skipped on `home`/`home-light`, which run no local LLM — 2026-08-30 revision, Findings 3 / 4)
- Set `secure_model` slot to the Apple Intelligence endpoint + model — only when the active variant configures `secure_model` (not `home`/`home-light`, per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` Finding 1 / S1)

> **Note (2026-08-30):** this Mac auto-provision path is hardware-gated (Apple Silicon Macs only) and is orthogonal to the S4 wizard change from the simplification handoff — on `SBC_LOW_POWER` devices the wizard prompts for a compute peer address and offers no local models (`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` Finding 4). The wizard therefore has three divergent paths: Mac auto-provision (this section), SBC compute-peer (S4), and the default Ollama flow.

#### 6.6 `halbert_core/halbert_core/dashboard/routes/llm.py`
**Add:**
- `_probe_apple_foundation(url: str = "http://127.0.0.1:11435") -> Dict[str, Any]` — probes `/v1/models` (or `/v1/health`), returns `{running, url, models, version}` like the Ollama/LM Studio probes. Never raises.

**Update `discover_local_engines()`:**
- Add `apple_foundation` to the concurrent `ThreadPoolExecutor` probes (now 3 workers)
- Return shape: `{data: {ollama, lm_studio, apple_foundation}}`

**Update `get_llm_config()` (the first-boot path):**
- Before `ensure_local_ollama_endpoint()` (per GAP 5 below — the Apple Intelligence provisioning is idempotent and runs first), call `auto_provision_apple_intelligence(hardware, variant)` when no endpoints were saved and Apple Intelligence is eligible; on `home`/`home-light` variants it returns False and nothing is provisioned (2026-08-30 revision, Findings 1 / 3 / 4)
- This runs the hardware detection + bridge probe once on first boot

### Layer 2: Model-Picker Package (`packages/model-picker`)

#### 6.7 `packages/model-picker/src/types.ts`
**Update `ProviderId` union:**
```ts
export type ProviderId =
  | 'ollama'
  | 'lm-studio'
  | 'openai'
  | 'openai-compatible'
  | 'anthropic'
  | 'google'
  | 'azure-openai'
  | 'apple-foundation'  // NEW
```

**Update `PROVIDERS` array:**
```ts
{ id: 'apple-foundation', label: 'Apple Intelligence', isLocal: true, needsApiKey: false, defaultUrl: 'http://127.0.0.1:11435' },
```

**Update `LocalDiscovery` interface:**
```ts
export interface LocalDiscovery {
  ollama: LocalEngine
  lmStudio: LocalEngine
  appleFoundation: LocalEngine  // NEW
}
```

#### 6.8 `packages/model-picker/src/primitives/RoleAssignmentRow.tsx`
**Fix `requiresLocal` filter (Bug 2):**
```ts
// BEFORE: requires a discovered model on the endpoint
const endpointChoices = role.requiresLocal
  ? picker.chatCapableEndpoints.filter((e) => {
      const model = picker.models.find((m) => m.endpointId === e.id)
      return model?.isLocal ?? false
    })
  : picker.chatCapableEndpoints

// AFTER: filter by provider locality, not model existence
const endpointChoices = role.requiresLocal
  ? picker.chatCapableEndpoints.filter((e) => providerDescriptor(e.provider).isLocal)
  : picker.chatCapableEndpoints
```

This fixes both the Apple Intelligence case (built-in model, no Ollama-style listing) and the fresh-install Ollama case (no models pulled yet).

### Layer 3: Dashboard Frontend

#### 6.9 `halbert_core/halbert_core/dashboard/frontend/src/lib/modelPickerTransport.ts`
**Fix Bug 1 — add `secure_model` to transport:**

Update `RawLlmConfig`:
```ts
interface RawLlmConfig {
  saved_endpoints: RawEndpoint[]
  chat_model: RawSlot
  specialist_model: RawSlot
  vision_model: RawSlot
  secure_model: RawSlot  // NEW — was missing
}
```

Update `toAssignments()`:
```ts
function toAssignments(llm: RawLlmConfig): Record<string, RoleAssignment> {
  return {
    chat_model: toRoleAssignment(llm.chat_model),
    specialist_model: toRoleAssignment(llm.specialist_model),
    vision_model: toRoleAssignment(llm.vision_model),
    secure_model: toRoleAssignment(llm.secure_model),  // NEW
  }
}
```

**Update `discoverLocal()`:**
```ts
async discoverLocal(): Promise<LocalDiscovery> {
  const res = await fetch(apiUrl('/api/llm/discover'))
  const data = await unwrap(res)
  return {
    ollama: data.ollama,
    lmStudio: data.lm_studio,
    appleFoundation: data.apple_foundation,  // NEW
  }
}
```

#### 6.10 `halbert_core/halbert_core/dashboard/frontend/src/components/llm/ModelSettings.tsx`
**Add Apple Intelligence UI:**
- When `appleFoundation` engine is discovered (running: true), show a distinct banner/card: "Apple Intelligence — Built-in on-device model. Zero download, runs on the Apple Neural Engine."
- The `apple-foundation` provider appears in the providers accordion via `PROVIDERS` (no manual add needed)
- Use lucide-react `Cpu` icon (NOT an emoji — per project rules) for the Apple Intelligence provider card
- The ProviderCard for `apple-foundation` should not show an API key field (`needsApiKey: false`)
- When `apple-foundation` endpoint is saved and assigned to `secure_model`, show a privacy badge: "Local only — data never leaves this Mac"

**Add Metal GPU display:**
- In the hardware profile section (if one exists in ModelSettings, or add one), show Metal GPU info when detected: GPU name + Metal version
- Source: the `/api/llm/discover` response or a new `/api/hardware` endpoint field

#### 6.11 `halbert_core/halbert_core/dashboard/frontend/src/components/llm/QuickSetup.tsx`
**Update if it exists and references providers:**
- Add Apple Intelligence as a zero-setup option when available
- Show "No download required" callout vs Ollama's "Pull a model" flow

### Layer 4: Swift Bridge (Specified, Deferred to Separate Session)

#### 6.12 `tools/apple_intelligence_bridge/` (NEW — separate session)
- Swift SPM package: `Package.swift` with `FoundationModels` framework dependency
- `Sources/halbert-foundation-bridge/main.swift`:
  - HTTP server on port 11435 (using `Vapor` or raw `URLSession` + `DispatchQueue`)
  - `GET /v1/health` → `{status: "ok", availability: "available"|"unavailable"}`
  - `GET /v1/models` → `{data: [{id: "apple-foundation-3b", object: "model"}]}`
  - `POST /v1/chat/completions` → maps to `LanguageModelSession.respond()` / `streamRespond()`
  - `SystemLanguageModel.default.availability` guard — returns 503 when unavailable
  - `@Tool` schema bridging for Halbert's tool-calling format
  - Streaming via SSE (`stream: true` in the request body)
- **Peer isolation (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Finding 5):** the bridge binds `127.0.0.1` only and serves the local Halbert exclusively. It must never be registered with `federation/compute_endpoint.py`, advertised via mDNS `compute_backends`, or listed through `PeerProvider.list_models()` — Apple Intelligence is local-only (serving it as an inference endpoint for other machines risks violating Apple's developer terms, and the 3B personal model is a capability mismatch for peer workloads). Peer compute on a Mac routes to Ollama 7B-14B. Add a bridge test asserting the listener refuses non-loopback binds.

#### 6.13 `halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json`
**Update `externalBin`:**
```json
"externalBin": [
  "binaries/halbert-api",
  "binaries/halbert-foundation-bridge"
]
```

**Update `macOS.minimumSystemVersion`:** `"15.1"` (when Apple Intelligence support is bundled; keep `"11.0"` for builds without it)

**Add Tauri lifecycle management** (Rust side, `src-tauri/src/main.rs` or lib):
- On app launch: spawn `halbert-foundation-bridge` as a sidecar process
- On app exit: terminate the bridge process
- Only on macOS Apple Silicon (gate by architecture check in Rust)

### Tests

#### 6.14 `halbert_core/tests/test_apple_intelligence.py` (NEW)
- Test `detect_metal_gpu()` returns None on non-Mac (mock `is_macos`)
- Test `apple_intelligence_eligible()` with mocked platform functions:
  - Apple Silicon + macOS 15.1 + 16GB + Metal → True
  - Apple Silicon + macOS 14.0 + 16GB + Metal → False (old macOS)
  - Apple Silicon + macOS 15.1 + 8GB + Metal → False (insufficient RAM)
  - Apple Silicon + macOS 15.1 + 16GB + no Metal → False (no GPU)
  - Intel Mac + macOS 15.1 + 16GB → False (not Apple Silicon)
- Test `detect_apple_intelligence_available()` with mocked bridge health probe:
  - Bridge answers 200 → True, `bridge_running=True`
  - Bridge connection refused + eligible → True, `bridge_running=False`
  - Bridge connection refused + not eligible → False
- Test `ensure_apple_foundation_endpoint()` creates endpoint with correct provider/url/name
- Test `auto_provision_apple_intelligence(hardware, variant)`:
  - 16GB Mac, `sysadmin` variant: assigns both `secure_model` and `chat_model`
  - 24GB Mac, `sysadmin` variant: assigns both `secure_model` and `chat_model`
  - 32GB Mac, `sysadmin` variant: assigns only `secure_model`, leaves `chat_model` unset
  - 16GB Mac, `home` / `home-light` variant (added 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`): assigns neither slot and registers nothing — `secure_model` is not configured on HA variants (Finding 1 / S1) and `chat_model` resolves to the compute peer, not a local model (Findings 3 / 4)
  - Not eligible: no provisioning, returns False
- Test `_is_local_url("http://127.0.0.1:11435")` returns True
- Test `normalise()` keeps `apple-foundation` provider enabled for `secure_model`
- Test `auto_provision_apple_intelligence()` does NOT overwrite existing endpoints

#### 6.15 `packages/model-picker/src/types.test.ts` (or existing)
- Test `providerDescriptor('apple-foundation')` returns `{isLocal: true, needsApiKey: false}`
- Test `PROVIDERS` array includes `apple-foundation`

#### 6.16 `packages/model-picker/src/primitives/RoleAssignmentRow.test.tsx`
- Test `requiresLocal` role shows endpoints with local providers even when no model is discovered
- Test `apple-foundation` endpoint appears in Secure dropdown

#### 6.17 `halbert_core/halbert_core/dashboard/frontend/src/lib/modelPickerTransport.test.ts`
- Update `toAssignments` test to include `secure_model`
- Update `discoverLocal` test to include `apple_foundation`

### Documentation

#### 6.18 `documentation/design/APPLE-INTELLIGENCE-MACOS-ON-DEVICE-STRATEGY.md`
- Update with finalized provider ID (`apple-foundation`)
- Update with Metal-gated availability logic
- Update with the 16GB Halbert-specific threshold and rationale
- Mark Phase 1 (mechanism) and Phase 3 (auto-provisioning) as current implementation scope
- Mark Phase 2 (Swift bridge) as deferred to separate session
- Add the pre-existing bug fixes (secure_model transport, requiresLocal filter) to the roadmap
- Add the peer-compute boundary: Apple Intelligence is local-only (Mac's own slots); peer compute endpoints on a Mac route to Ollama; mDNS `compute_backends` lists `ollama`/`vllm` only (per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` Finding 5)

#### 6.19 `.handoff/HANDOFF-APPLE-INTELLIGENCE-IMPLEMENTATION-2026-08-29.md`
- This document (update after implementation with status and verification results, AND incorporate the 2026-08-30 simplification feedback — the local-only note per Finding 5 / S6, the variant gating per Finding 1 / S1, and the picker scoping per Finding 3 / S3)

---

## 7. Implementation Order

The work is ordered so each step is independently testable:

| Step | Files | What | Testable? |
|------|-------|------|-----------|
| 1 | `platform.py` | Metal detection + eligibility check | Yes — mock platform functions |
| 2 | `hardware_detector.py` | Wire eligibility into `HardwareCapabilities` | Yes — mock detection |
| 3 | `client.py` | Add `apple-foundation` to provider sets | Yes — import check |
| 4 | `llm_config.py` + `model/auto_provision.py` (per GAP 6) | Endpoint + auto-provisioning functions (variant-gated, 2026-08-30 revision) | Yes — unit tests with mocked hardware |
| 5 | `config_wizard.py` | Apple Intelligence in wizard flow | Yes — mock hardware |
| 6 | `llm.py` route | Discover probe + first-boot provisioning | Yes — route tests |
| 7 | `types.ts` (model-picker) | New provider + LocalDiscovery | Yes — type tests |
| 8 | `RoleAssignmentRow.tsx` | Fix `requiresLocal` filter | Yes — component tests |
| 9 | `modelPickerTransport.ts` | Fix `secure_model` + `appleFoundation` | Yes — transport tests |
| 10 | `ModelSettings.tsx` | Apple Intelligence UI + Metal display | Manual — visual |
| 11 | Tests | All test files | Yes |
| 12 | Docs | Design doc + this handoff — including the Apple Intelligence local-only note (Finding 5 / S6) and the variant scoping of the picker UI (S3) | N/A |

Steps 1-6 are Python backend (mechanism). Steps 7-10 are frontend (UI). Step 11-12 are verification and docs.

> **Variant scoping of steps 7-10 (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Finding 3 / S3):** the picker UI work applies to variants that render the model picker (`sysadmin` / workstation — which is where Macs sit, so the work remains valid). `home` / `home-light` variants do not render the model picker at all — they show a single "Compute Peer" setting, and the workstation's picker governs which models serve their requests. Those variants never see the `apple-foundation` provider UI.

The Swift bridge (steps 6.12-6.13) is a separate session — it requires Xcode, a Swift SPM package, and Tauri sidecar lifecycle code. The mechanism built in steps 1-10 is correct and inert without it; the bridge is the "last mile" that makes the endpoint actually answer.

---

## 8. What This Does NOT Do

- **Does not build the Swift bridge binary** — that's a separate session requiring Xcode and Swift compilation
- **Does not implement Tauri sidecar lifecycle** — also part of the Swift bridge session
- **Does not change the wire format** — the bridge speaks OpenAI-compatible, which `_call_openai_compatible()` already handles
- **Does not add new model adapters** — `apple-foundation` routes through the existing OpenAI-compatible path
- **Does not change `secure_model` enforcement** — `_is_local_url()` already accepts `127.0.0.1`
- **Does not touch the tier router** — `from_legacy_config()` already resolves `secure_model` via `_resolve_slot()`
- **Does not expose Apple Intelligence as a peer compute backend** (added 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Finding 5 / S6) — `apple-foundation` serves the Mac's own slots only; peer compute requests on a Mac route to Ollama; mDNS `compute_backends` lists `ollama`/`vllm` only; and `PeerProvider.list_models()` never includes `apple-foundation` models

---

## 9. Verification Plan

After implementation:

1. **Unit tests pass:** `pytest halbert_core/tests/test_apple_intelligence.py`
2. **Existing tests pass:** `pytest halbert_core/tests/` (no regressions in model config, hardware, wizard)
3. **Model-picker tests pass:** `cd packages/model-picker && npx vitest run`
4. **Frontend builds:** `cd halbert_core/dashboard/frontend && npm run build` (TypeScript compiles with new provider type)
5. **Transport tests pass:** `npx vitest run src/lib/modelPickerTransport.test.ts`
6. **On this Mac (M1, 16GB+):**
   - `python -c "from halbert_core.utils.platform import apple_intelligence_eligible; print(apple_intelligence_eligible())"` → `True`
   - `python -c "from halbert_core.utils.platform import detect_metal_gpu; print(detect_metal_gpu())"` → Metal info dict
   - Dashboard Settings → AI Models shows "Apple Intelligence" provider in the accordion
   - Secure (Local) dropdown includes "Apple Intelligence (On-Device)" endpoint
7. **On non-Mac (CI):** `apple_intelligence_eligible()` → `False`, no auto-provisioning, no UI changes visible
8. **Peer boundary (Finding 5, added 2026-08-30):** on a Mac running the federation scaffold, `PeerProvider.list_models()` against the Mac's compute endpoint returns only Ollama models (no `apple-foundation-3b`); the mDNS TXT record's `compute_backends` field contains `ollama` (and optionally `vllm`), never `apple_foundation`; and a request to the Mac's peer compute endpoint never routes to port 11435

---

## 10. Scrutiny Findings — Gaps Found in Original Plan

After reverse-engineering every code path the plan touches, 6 gaps were found and corrected before implementation:

### GAP 1: `is_safe_url()` doesn't recognize `apple-foundation` as local (CRITICAL)
- **File:** `dashboard/routes/llm.py` line 113
- **Issue:** `is_safe_url` only allows `("ollama", "lm-studio")` as local providers. `apple-foundation` falls through to the cloud-provider path, which blocks loopback IPs. All proxy calls (list models, test endpoint, test model) to `http://127.0.0.1:11435` would return "Invalid or unsafe URL".
- **Fix:** Add `"apple-foundation"` to the local providers tuple at line 113.

### GAP 2: `_ALLOWED_LOCAL_PORTS` missing port 11435 (CRITICAL)
- **File:** `dashboard/routes/llm.py` line 64
- **Issue:** Even with GAP 1 fixed, the fallback SSRF check at line 122 only allows loopback on ports in `_ALLOWED_LOCAL_PORTS = {11434, 1234, 1235}`. Port 11435 (Apple Intelligence bridge) is not included.
- **Fix:** Add `11435` to the set: `{11434, 1234, 1235, 11435}`.

> **2026-08-30 note (per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, Finding 5):** the GAP 1/2 allowances are for the Mac's own dashboard proxy route only. Do NOT replicate this allowance in `federation/compute_endpoint.py` — the peer compute endpoint never routes to `apple-foundation`, and port 11435 must never be reachable through it.

### GAP 3: `proxy_models()` doesn't handle `apple-foundation` in model listing (CRITICAL)
- **File:** `dashboard/routes/llm.py` line 529
- **Issue:** The OpenAI-style model listing branch is `elif req.provider in ("openai", "openai-compatible", "lm-studio", "anthropic"):`. `apple-foundation` is not in this tuple, so model listing returns empty even when the bridge is running.
- **Fix:** Add `"apple-foundation"` to the tuple.

### GAP 4: `proxy_test_model()` doesn't handle `apple-foundation` (MEDIUM)
- **File:** `dashboard/routes/llm.py` line 770
- **Issue:** The OpenAI-style test-model branch is `elif req.provider in ("openai", "openai-compatible", "lm-studio"):`. `apple-foundation` is not in this tuple, and there's no `else` branch — the function returns `success: false` with an empty message.
- **Fix:** Add `"apple-foundation"` to the tuple.

### GAP 5: Auto-provisioning ordering conflict with `ensure_local_ollama_endpoint` (MEDIUM)
- **File:** `dashboard/routes/llm.py` line 194, `model/llm_config.py` line 863
- **Issue:** `ensure_local_ollama_endpoint()` returns True only when no endpoints are saved AND Ollama is running. If it runs first and creates an endpoint, `auto_provision_apple_intelligence` would see a non-empty endpoint list and skip (per original plan's "no endpoints saved" check).
- **Fix:** `auto_provision_apple_intelligence` must be idempotent — it checks whether the `apple-foundation` endpoint already exists (not whether ANY endpoints exist), and only assigns slots that are currently empty. It runs BEFORE `ensure_local_ollama_endpoint` in the first-boot path.

### GAP 6: `auto_provision_apple_intelligence` placement causes import concern (LOW)
- **File:** `model/llm_config.py`
- **Issue:** The original plan puts `auto_provision_apple_intelligence` in `llm_config.py`, but it needs `HardwareCapabilities` from `hardware_detector.py`. `llm_config.py` is the "single owner of the llm_config section" and shouldn't import hardware detection — that's a separation of concerns violation.
- **Fix:** Put `auto_provision_apple_intelligence` in a new `model/auto_provision.py` module that imports from both `llm_config` and `hardware_detector`. The `llm_config.py` module only gets the `APPLE_FOUNDATION_*` constants and `ensure_apple_foundation_endpoint()`.

### Things verified CORRECT in the original plan:
- `_call_openai_compatible()` handles empty API key correctly (skips Authorization header) ✓
- `_call_with_tool_fallback()` retries without tools on 4xx — works for Apple Intelligence ✓
- `normalise()` accepts `apple-foundation` provider (it's in `CHAT_CAPABLE_PROVIDERS` via `OPENAI_COMPATIBLE_PROVIDERS`) ✓
- `_is_local_url("http://127.0.0.1:11435")` returns True (loopback) ✓
- `LOCAL_GPU_PROVIDERS` should NOT include `apple-foundation` (ANE ≠ GPU contention) ✓
- `proxy_test()` else branch handles `apple-foundation` without changes (uses OpenAI-style `/v1/models`) ✓
- `DISCLOSURE_PROVIDERS` in ModelSettings.tsx should NOT include `apple-foundation` (local, no cloud disclosure) ✓
- `secure_model` transport bug is real: `RawLlmConfig` and `toAssignments()` both omit `secure_model` ✓
- `requiresLocal` filter fix is correct: `providerDescriptor(e.provider).isLocal` is the right check ✓
- `configure_first_run_model()` already checks if `chat_model` is set, so Apple Intelligence taking it won't be overwritten ✓
