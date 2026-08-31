# Home Automation Simplification: Remove secure_model, SourcePrep, and Model Picker from HA Variants

**Date:** 2026-08-30 (code-verified revision same day — see Section 12)
**Status:** Architectural Feedback & Simplification Proposal — accepted direction; code-impact claims verified against the actual codebase and corrected inline (marked "**Code-verified correction**")
**Origin:** Hardware planning session for the dedicated HA/SnapRAID backup server (Intel N150, 16GB RAM)
**Context:** Informed by `HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md`, `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`, `SECURE-MODEL-AND-LIGHT-VARIANT-2026-08-29.md`, `HOME-AUTOMATION-DESIGN-2026-08-27.md`, and `HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md`

---

## 1. Executive Summary

A hardware planning session for a dedicated Home Assistant + SnapRAID backup server (Intel N150, 16GB RAM) surfaced a series of architectural questions about what the HA Halbert variant actually needs. The conclusion, reached through systematic analysis of the HA use case, is that **the `home` and `home-light` variants are carrying significant complexity that the HA use case does not require**:

1. **`secure_model` should be removed from HA variants.** Home automation's sensitive data lives behind HA's API abstractions — the LLM never sees credentials.
2. **SourcePrep should be removed from HA variants.** The HA Halbert's world is live HA state, not documentation.
3. **The model picker is unnecessary for HA nodes.** With no local LLM and no `secure_model`, there is nothing to pick — the HA node is a pure client of the workstation's compute endpoint.
4. **The 1B model tier and constrained-device quantization research should be dropped.** Devices with <=4GB RAM should offload all LLM work, not attempt local inference.
5. **Apple Intelligence is not a peer-offload target.** It is macOS-only, ANE-bound, and potentially restricted by Apple's terms.

This document provides the reasoning, the concrete changes, and the impact on the existing scaffolded code.

---

## 2. The Hardware Context That Drove This Analysis

The target machine is an **Intel N150 (Twin Lake, 4C/4T, 6W TDP)** mini-ITX board (CWWK CW-M2) with **16GB DDR5 SO-DIMM**, serving as:

1. A **SnapRAID backup server** (nightly sync of the main rig's data to 10+ HDDs via an LSI 9211-8i HBA)
2. A **Home Assistant hub** (HA OS, 24/7 smart home control)
3. A **Halbert `home-light` node** (the "home" identity — cognition, voice, HA integration)

The N150 is paired with a high-end workstation (Mac Studio or Linux GPU rig) via the federated peer architecture (`HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md`). The workstation is the **Compute Host**; the N150 is an **Ambient Sentinel**.

The initial question was whether 10x HDDs would overwhelm the N150's CPU. The answer is no — SnapRAID's CPU cost scales with data volume, not drive count, and runs nightly at 3 AM. But the analysis revealed that the **Halbert stack's assumptions about what the HA node needs to run locally are over-specified**, and simplifying them has cascading benefits.

---

## 3. Finding 1: Remove `secure_model` from `home` / `home-light` Variants

### 3.1 The Problem

The `secure_model` slot (`SECURE-MODEL-AND-LIGHT-VARIANT-2026-08-29.md`) was designed for the sysadmin use case: reasoning about SSH configs, credentials, network topology, and other sensitive system files where the prompt itself is sensitive even if the answer isn't. The slot enforces local-only endpoint resolution (`_is_local_url()` rejects all non-loopback URLs) to guarantee sensitive data never leaves the machine.

This slot was then applied to the `home` and `home-light` variants without examining whether the HA use case has the same sensitivity profile.

### 3.2 The Analysis: What Sensitive Data Does an HA Server Actually Have?

A systematic enumeration of sensitive data on a home automation server and whether the LLM ever sees it:

| Data | Where it lives | Does the LLM see it? |
| :--- | :--- | :--- |
| HA long-lived access token | `being.yml` / `ha_config.yml` | **No** — the HA client (`ha_client.py`) uses it internally for API calls. The LLM calls HA tools (`turn_on`, `lock_door`), never sees the token. |
| Zigbee/Z-Wave network keys | HA's encrypted storage (ZHA/Zigbee2MQTT) | **No** — managed by HA's integration layer, not exposed to external integrations. |
| Camera RTSP credentials | Frigate config (`frigate.yml`) | **No** — Frigate connects to cameras internally. Halbert subscribes to MQTT events ("person detected"), not credentials. |
| Smart lock PINs | HA's encrypted storage | **No** — HA exposes `lock.lock`/`unlock` services. The LLM calls the service, never sees the PIN. |
| Voice biometric embeddings | SQLite (`speaker_profiles` table) | **No** — CAM++ comparison happens in the audio pipeline (`halbert_core/audio/`), not the LLM. The LLM receives "speaker: eric, role: admin" as a string. |
| User presence/occupancy patterns | HA state history / Halbert memory | **Maybe** — the LLM reasons about "nobody's been home for 6 hours." Privacy-sensitive but not credential-sensitive. |
| Network topology | HA device registry | **Maybe** — the LLM might know "there are 47 devices on the network." Mildly sensitive but not a credential. |
| HA `secrets.yaml` contents | HA's own secret management | **No** — HA resolves `!secret` references internally before exposing values to integrations. |

**The pattern: the LLM interacts with HA through tool calls that abstract away credentials.** The LLM says "turn on the kitchen lights" and the HA client handles the API authentication. The LLM never sees the token, the network key, the RTSP URL, or the lock PIN.

### 3.3 The Edge Cases (and Why They Don't Require `secure_model`)

The edge cases where home automation *might* encounter sensitive data:

| Edge case | Why `secure_model` isn't needed |
| :--- | :--- |
| "Halbert, why can't I connect to the garage camera?" | Halbert might inspect Frigate config, which contains RTSP credentials. But it should report "camera unreachable at 192.168.1.50" without exposing the password. This is a **redaction** task (`redact_text()`), not an LLM reasoning task. The `describe_secret` Tier 2 path already does this without a model. |
| "Check my HA automations for problems" | HA YAML automations reference `!secret` values, but HA resolves those internally. The YAML the LLM sees has `entity_id: sensor.temperature`, not secrets. |
| "What's my network topology?" | The LLM sees entity names and device counts, not network keys or passwords. |

**Even these edge cases don't require a local model.** They require *redaction* (don't expose the credential in the response), which is a deterministic function, not an LLM reasoning task.

### 3.4 The Sysadmin Work That DOES Need `secure_model` — and Where It Happens

Any sysadmin work on the HA device itself (inspecting configs, reading logs, diagnosing issues, debugging automations) is **done FROM the workstation's Halbert instance**, not from the HA node's own Halbert. The federated architecture's Fleet Cockpit (`fleet_proxy.py`) lets the workstation's Halbert connect to the N150 as an MCP client and inspect its configs remotely. The workstation's `secure_model` (a capable 7B-14B local model) handles the sensitive reasoning. The N150's Halbert never needs to do this.

### 3.5 The Contradiction in the Current Recommendations

The low-power hardware handoff (`HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` section 7.1) establishes model capability by parameter count:

| Parameter class | Good at | Struggles with |
| :--- | :--- | :--- |
| 1B-1.5B | "fast cognitive monologue summarization, low thermal impact" | Tool calling, structured JSON, privacy scrubbing |
| 2B-3B | "reliable tool calling, structured JSON output, safe privacy scrubbing" | — |
| 3.8B-4B | "strong reasoning, reliable schema adherence" | — |

The `secure_model` role needs the 2B-3B capabilities (tool calling, JSON, scrubbing) — but the 1B tier (recommended for <=4GB devices as `secure_model`) only offers "summarization and low thermal impact." **Halbert's own capability table contradicts its own `secure_model` recommendation.** A 1B model can summarize text, but asking it to reliably classify sensitivity, produce structured JSON for tool calls, or reason about whether a config contains credentials is pushing it past its competence.

### 3.6 Resolution

**Remove `secure_model` from the `home` and `home-light` variants entirely.**

- The slot remains available in the `sysadmin` variant (where it is genuinely needed)
- The `home` / `home-light` variant does not configure `secure_model`, does not load it, does not display it in the UI
- The `SLOTS` tuple in `llm_config.py` remains unchanged (4 slots) — the variant simply leaves `secure_model` unconfigured
- The model picker UI hides the `secure_model` row when the variant is `home` or `home-light`

### 3.7 Code Impact

> **Code-verified correction (2026-08-30):** the original version of this table named `dashboard/app.py` as the skip site ("already partially done") — in reality **nothing** secure_model-related is skipped for any variant today, and secure_model is actively *auto-assigned* on Apple-Silicon Macs with no variant check. Corrected impact list:

| File | Change |
| :--- | :--- |
| `halbert_core/halbert_core/model/auto_provision.py` + `halbert_core/halbert_core/dashboard/routes/llm.py` | **The real S1 change.** `auto_provision.py:66-71` assigns Apple Intelligence to `secure_model` whenever the slot is empty ("mandatory local slot"), with no variant check, triggered from `GET /llm/config` (`routes/llm.py:~208-217`). Gate it on the active variant (`cognition_wiring._get_variant()`). |
| `halbert_core/halbert_core/model/config_wizard.py` | `run_auto()` / `_build_config` write `secure_model` during wizard flows with no variant input. Add variant awareness; note `save_config` deep-merges all slots, so HA variants must write the slot **empty**, not omit it. |
| `halbert_core/halbert_core/dashboard/routes/agent.py` + `halbert_core/halbert_core/model/tier_router.py` | The secure turn gate (`agent.py:465-476`) resolves `get_secure_model()` per turn with no variant check. "The variant simply never sets it" (3.6) is insufficient while auto-provisioning can set it — skip the dedicated branch for `home`/`home-light` so resolution falls through to the existing local-guide/fail-closed chain (`agent.py:419-428`). |
| `halbert_core/halbert_core/config/being_config.py` | `VALID_VARIANTS` already includes `"home-light"`; no change to the variant list. Optional docstring note on the `variant` field. |
| `halbert_core/halbert_core/model/llm_config.py` | **No change.** `default_llm_config()` already ships `secure_model` empty for every variant (`:158`), and the module is deliberately variant-free; `normalise()` re-materialises all four SLOTS keys on every read, so removal is impossible and unnecessary. |
| `halbert_core/halbert_core/dashboard/frontend/src/lib/halbertModelRoles.ts` | Add `variants: ["sysadmin"]` to the `secure_model` role (`:21`); leave the other three roles untagged. |
| `halbert_core/halbert_core/dashboard/frontend/src/components/llm/ModelSettings.tsx` | **Filtering belongs here (host side), not in the shared package.** Filter out roles whose `variants` excludes the active variant before passing them to `useModelPicker` (existing precedent: the `displayRoles` memo, `:384-392`). |
| `packages/model-picker/src/types.ts` (+ `primitives/RoleAssignmentRow.tsx`) | Optional: add `variants?: string[]` to `AppRole` (`types.ts:71-83`) as an opaque host-supplied field, preserving the package's no-role-names rule. The row component itself renders exactly one role (`RoleAssignmentRow.tsx:38-46`) and must not filter. Correct path: `packages/model-picker/src/primitives/RoleAssignmentRow.tsx`. |
| `config/models.yml` | The repo template ships `secure_model` empty. No change needed — the HA variant simply never fills it (now that auto-provisioning is gated). |
| **Prerequisite (S1 + S3):** `halbert_core/halbert_core/dashboard/routes/instance.py` | `GET /api/instance/info` reads only the `HALBERT_VARIANT` env var (`:33`) while backend gating uses `cognition_wiring._get_variant()` (being.yml > env > sysadmin, `cognition_wiring.py:81-93`). Unify on `_get_variant()` or the UI will render the sysadmin picker/secure_model row for a being.yml-set home variant. |

---

## 4. Finding 2: Remove SourcePrep from `home` / `home-light` Variants

### 4.1 The Problem

The low-power hardware handoff (section 6) describes an "HA-scoped SourcePrep corpus" — indexing HA YAML automations, entity registry, Frigate zones, and device manuals — as a lightweight alternative to the full sysadmin corpus (~150MB vs ~220MB, ~120MB RAM vs ~1.2GB RAM). The `home` variant (Tier 2) recommends "Local HA-scoped SourcePrep."

**Code-verified correction (2026-08-30):** the original claim that "the `home-light` variant already skips SourcePrep (it points `SOURCEPREP_URL` to a remote workstation or runs in un-indexed fallback mode)" is **false**. No code path skips SourcePrep for any variant: the retrieval backend and adapter are constructed unconditionally (`dashboard/routes/agent.py:136-142`, `context/adapters.py:340-343,429,455`, `context/extra_adapters.py:559`, `integrations/app_seam.py:404` via `cognition_wiring.py:144-146`), `SOURCEPREP_URL` defaults to `http://localhost:8400` (`integrations/sourceprep_client.py:68`), and an unreachable daemon merely fails open to empty results. Pointing `SOURCEPREP_URL` at a workstation is a docs-only recommendation (`deploy/README.md:124`), not implemented behavior. **S2 is therefore real gating work in the wiring code** — leaving `SOURCEPREP_URL` unconfigured is not a mechanism (see 4.5/4.6). The `home` variant additionally runs the config watcher with a SourcePrep reindex callback (`app.py:616-622`) and the HA-config SourcePrep bridge (4.6).

### 4.2 The Analysis: What the HA Halbert Actually Does

The HA Halbert's interactions are **action-oriented voice queries about live state**, not exploratory research sessions:

| User says | Where the answer comes from | SourcePrep needed? |
| :--- | :--- | :--- |
| "Turn on the kitchen lights" | HA tool call (`light.turn_on`) | No |
| "Is the front door locked?" | HA state query (`lock.front_door`) | No |
| "Did anything happen last night?" | Persona memory (episodic log of HA events + Frigate detections) | No |
| "I'm going to bed" | HA automations (lock doors, dim lights, arm alarm) | No |
| "Why is the living room cold?" | HA sensor state (thermostat, windows) + reasoning | No |
| "What's the temperature in the garage?" | HA sensor query | No |
| "Turn off everything downstairs" | HA tool call (area-based service call) | No |
| "What devices do I have in the living room?" | HA area registry (`ha_discovery.py`) | No |

The HA Halbert's world is **live HA state** — sensors, entities, events. It gets that directly from the HA WebSocket event stream. It doesn't need to look anything up in a documentation index to answer "is the door locked?" The answer is a sensor reading, not a RAG retrieval.

### 4.3 When SourcePrep Would Theoretically Help (and Why It Doesn't in Practice)

| Scenario | Why it doesn't happen via the HA node |
| :--- | :--- |
| "How do I configure my Zigbee network?" | That's a sysadmin question. You'd ask it from your workstation's Halbert, which has the full sysadmin SourcePrep corpus. You wouldn't say this to a voice satellite in the kitchen. |
| "What does this HA automation do?" | Debugging an automation YAML is sysadmin work. Done at the workstation, not via voice. |
| "The kitchen light won't turn on, help me debug" | Halbert can see the entity state directly (`light.kitchen: unavailable`). It doesn't need documentation to say "the light entity is showing unavailable — likely a Zigbee mesh issue or the bulb is off." That's reasoning over live state, not RAG. |
| "What's the network topology?" | HA's device registry has this. `ha_discovery.py` enumerates entities. No RAG needed. |

The HA-scoped SourcePrep corpus sounds useful in theory, but in practice:
- **Voice queries are short and action-oriented**, not exploratory research sessions
- **Live HA state answers most questions** without needing to retrieve documentation
- **Anything complex enough to need documentation retrieval is sysadmin work**, which happens at the workstation

### 4.4 The Correct Architecture

| Node | SourcePrep role |
| :--- | :--- |
| **HA node (N150)** | No SourcePrep. Not local, not remote. The HA Halbert doesn't query it. No `SOURCEPREP_URL` configured. |
| **Workstation** | Runs SourcePrep with the full sysadmin corpus. The workstation's Halbert uses it for sysadmin work, including diagnosing the N150 remotely via the fleet cockpit / MCP path. |
| **HA node as a target** | The workstation's SourcePrep *could* index the N150's HA config files (via MCP remote inspection) so the sysadmin can query "what automations are on the HA server?" from the workstation. But this is the workstation querying, not the N150. |

### 4.5 Resolution

**Remove SourcePrep from `home` and `home-light` variants entirely.**

- No `SOURCEPREP_URL` configuration — and, in code, explicit variant gating in the wiring layers (absence alone is not a mechanism; see the 4.1 correction)
- No ChromaDB dependency
- No RAG scrapers (the 46-file `rag/` directory is already excluded from `home-light`, but should also be excluded from `home`)
- No SourcePrep daemon (local or remote)
- The `SourcePrepRetrievalBackend` is not instantiated
- The agent answers from conversational context + live HA state, not from a documentation index

### 4.6 Code Impact

| File | Change |
| :--- | :--- |
| `halbert_core/halbert_core/dashboard/routes/agent.py` | `rag_service = SourcePrepAdapter()` (`:136-142`) runs for every variant. Pass `None` for `home`/`home-light` (verify the agent state machine tolerates a missing rag_service) and skip the retrieval wiring in `create_agent_context_assembler`. |
| `halbert_core/halbert_core/context/adapters.py` + `halbert_core/halbert_core/context/extra_adapters.py` | `SourcePrepAdapter.__init__` auto-creates the backend (`adapters.py:337-343`); `create_wired_context_assembler` (`:429`), `create_agent_context_assembler` (`:455`), and `create_extended_context_assembler` (`extra_adapters.py:559`) wire it unconditionally. Add a variant gate or a `set_retrieval_enabled(False)` seam. |
| `halbert_core/halbert_core/integrations/cognition_wiring.py` + `app_seam.py` | `_ensure_app_seam_wired()` calls `wire_halbert_seam()` with default `skip_retrieval=False` — the parameter already exists (`app_seam.py:376`). Pass `skip_retrieval=True` for HA variants. |
| `halbert_core/halbert_core/integrations/home_assistant/ha_config_bridge.py` + `dashboard/routes/home.py` + `ha_config_tools.py` | **Missed by the original analysis.** The HA-config SourcePrep surface is the home variant's primary SourcePrep dependency: `HA_SOURCEPREP_ENABLED` defaults to `"1"` (`ha_config_bridge.py:44-49`), `/home/config-search` + `/home/config-search/status` endpoints are live for all variants (`routes/home.py:178-192`), and `ha_config_tools.py` is vestigial (its `register_ha_config_tools` is never called). Remove or default-disable for HA variants. |
| `halbert_core/halbert_core/dashboard/app.py` | `app.py` never initializes SourcePrep directly — its only touchpoint is the config watcher (skipped for `home-light` only, `:600`), which for `home` starts with `create_sourceprep_reindex_callback()` (`:616-622`). Drop the reindex callback (keep `create_detector_trigger_callback`) or widen the watcher skip to both HA variants. |
| `halbert_core/halbert_core/config/being_config.py` | No `SOURCEPREP_URL` field exists there — the variable is environment-only (`sourceprep_client.py:68`, `sourceprep_setup.py:132`, `ha_config_bridge.py:46`). Optional docstring note on the `variant` field only. |
| `halbert_core/pyproject.toml` | `[light]` already excludes `chromadb` and `sentence-transformers`; `[rag-legacy]` bundles `chromadb` and must never be installed on HA nodes. See the 4.7 correction for the packaging decision. |
| `deploy/README.md` + `deploy/halbert-home.service` | Update HA deployment docs (SourcePrep daemon listed as prerequisite at `:13`; `SOURCEPREP_PROJECT_ID=ha-config` at `:102` and in the unit file). |
| `halbert_core/tests/test_ha_phase3.py` | HA-variant tests currently set `SOURCEPREP_URL` and assume the bridge; after S2 they must assert the retrieval backend is *absent* for home/home-light. |

### 4.7 What Remains: Memory Embeddings (NOT SourcePrep)

**Important distinction:** Persona memory embeddings are NOT SourcePrep. They are how Halbert stores and retrieves episodic memory ("what happened last night", "when did Eric last talk to me"). This is a local CPU operation that runs fine on the N150 and cannot be offloaded (memory is per-node, per-identity).

**Packaging flag — code-verified correction (2026-08-30): option (a) is rejected; the original dependency attribution was wrong.**

- The **on-path persona memory embedder** is `haloysius.memory.embeddings.MemoryEmbedder` (wired via `cognition_wiring.py:122`), which tries the Phase 72 **ONNX/Ollama embedder first**, `sentence-transformers` only as a legacy fallback, and TF-IDF last (`haloysius memory/embeddings.py:250-261`). `sentence-transformers` lives in **haloysius's own optional `[embeddings]` extra** (which pins `torch`), not in halbert_core.
- halbert_core's own `sentence-transformers` consumer (`rag/embeddings.py` `EmbeddingManager`, all-MiniLM-L6-v2) feeds only the eval/browser-only `HybridMemorySystem`, which is fenced off the agent path (`dashboard/routes/agent.py:137-138`). Adding it to halbert_core's `[light]` would wire a dependency into the wrong package without touching the memory that actually runs on a home node.
- `sentence-transformers` also drags in `torch` — exactly the weight `[light]` was created to avoid.

**Revised recommendation:** keep `[light]` unchanged; serve memory embeddings on HA nodes via **Ollama (`nomic-embed-text`) or the haloysius ONNX embedder** (matching `deploy/README.md:131-133`'s existing "Ollama handles embeddings" guidance), with `haloysius[embeddings]` as the optional local-transformer upgrade — optionally surfaced as a `[home]` extra = `[light]` + `[cognition]`. Before any packaging change, verify which memory path the HA persona actually consumes: the dashboard agent path currently wires `memory_service=None` with receipts/FTS5 recall (`agent.py:144-146`); if that is the operative path on a home node, no packaging change is needed at all.

---

## 5. Finding 3: No Model Picker for HA Nodes

### 5.1 The Problem

The federated handoff's `PeerProvider` is specified to call `GET /api/compute/v1/models` on the workstation to discover what models are available — so the satellite *can* know what models the workstation has. But there is no UI surface for the user to pick which one.

> **Code-verified correction (2026-08-30):** two inaccuracies. (1) `PeerProvider.list_models()` is an unimplemented scaffold stub (`model/providers/peer.py:178`); the compute endpoint's models route returns an empty stub (`federation/compute_endpoint.py:236-240`) — no HTTP call exists anywhere in the federation scaffold yet. (2) "The satellite's model picker only shows local endpoints" is false: the picker ships 8 providers including OpenAI/Anthropic/Google/Azure/openai-compatible (`packages/model-picker/src/types.ts` PROVIDERS), and `ModelSettings.tsx:307-344` lets users add cloud providers. The accurate gap: **the picker has no peer-compute integration** — `peer` is not in the `ProviderId` union, the UI reads/writes only the local `models.yml` via `/llm/config`, and no backend caller ever creates a `peer://` endpoint (`llm_config.ensure_endpoint` is never invoked with one).

The federated handoff (finding M11) specifies which slots can peer-offload:
- `chat_model`: CAN peer-offload
- `specialist_model`: CAN peer-offload
- `vision_model`: CAN peer-offload (if peer advertises `vision` capability)
- `secure_model`: MUST NOT peer-offload (local-only by architectural rule)

### 5.2 The Simplification

With `secure_model` removed from HA variants (Finding 1) and all LLM work offloaded to the workstation (Finding 4), the HA node has **no local models to pick from**. It does not need a model picker UI. It needs:

1. A single **"compute peer" setting** — the workstation's address (IP or hostname, with optional Tailscale hostname)
2. The workstation's own model picker determines which models serve the HA node's requests
3. The HA node's `chat_model` and `specialist_model` both resolve to `peer://workstation:8000` — the same endpoint, the same model list

This eliminates the need to build a remote model picker into the HA node's UI entirely. The HA node is a pure client of the workstation's compute endpoint. The workstation's `PeerProvider.list_models()` response is used internally by the `ComputeRouter` to know what's available, but the user does not need to pick a specific model on the HA node — the workstation's configuration governs.

### 5.3 Resolution

**Do not build a remote model picker for HA nodes.** The HA node's settings UI should have:

- A "Compute Peer" field (hostname:port or Tailscale address)
- A "Test Connection" button (validates the peer link and reports available models)
- No model selection dropdown — the workstation's model picker governs

If the user wants to change which model serves the HA node, they change it on the workstation's model picker, and the HA node picks it up automatically on the next request.

### 5.4 Code Impact

| File | Change |
| :--- | :--- |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` + `components/llm/ModelSettings.tsx` | The picker is mounted unconditionally at `Settings.tsx:2241` (`<ModelSettings />` in the `ai` tab). When the active variant (via `GET /api/instance/info` — see the instance.py prerequisite in 3.7) is `home`/`home-light`, render a new ComputePeerCard (hostname:port / Tailscale address + "Test Connection" hitting the peer health probe) instead. Reuse the fleet plumbing (`PeerPairingModal.tsx`, `DiscoveredPeerCard.tsx`, `dashboard/routes/peers.py`). The `ChatModelPill` surface also needs a decision: hide or render read-only. |
| `halbert_core/halbert_core/model/llm_config.py` | When variant is `home` / `home-light`, `chat_model` and `specialist_model` resolve to the peer endpoint. No local model configuration is expected. |
| `halbert_core/halbert_core/federation/compute_router.py` | **Corrected:** `ComputeRouter` has no slot concept and `route()` raises `NotImplementedError` (`:233`); `list_models()` is a `PeerProvider` method, not a `ComputeRouter` one, and health probing is `_probe_peer_health` (`:235`). When implemented, `route()` must resolve `chat_model`/`specialist_model` to the peer endpoint; `list_models()` is used for health checking, not user selection. |
| `halbert_core/halbert_core/model/providers/peer.py` + `model/client.py` + `model/tier_router.py` + `model/providers/__init__.py` | **Prerequisite the original analysis missed:** `peer` is registered nowhere in the model stack — not in `CHAT_CAPABLE_PROVIDERS` (`client.py:72-74`), `tier_router.py`, or `providers/__init__.py` — so `llm_config.py:411-413` currently disables any peer-provider slot as "not chat-capable." Register the provider (and wire `ensure_endpoint('peer://...')` + `set_slot` when pairing) before any Compute Peer setting can function. |

### 5.5 Note on the Sysadmin Variant

The sysadmin variant still needs the full model picker (local + remote models, all 4 slots). This simplification applies only to `home` and `home-light`. A sysadmin box that runs local models AND offloads to a peer needs to pick which model goes in which slot — that's the existing model picker's job, extended with peer-discovered models (per the federated handoff's Phase 9.2).

---

## 6. Finding 4: <=4GB Devices = Offload Only, No Local AI

### 6.1 The Problem

The low-power hardware handoff (section 7) spends significant effort making 1B models viable on Pi 4 2GB:
- Parameter size evaluation for 1B-4B models
- Quantization strategies (`Q4_K_M`, `Q2_K`, `IQ3_S`, `IQ2_XXS`)
- "Smaller model vs extreme quantization" tradeoff analysis
- The recommendation to "prefer a 2B model at Q4_K_M over a 4B model at Q2_K"

This engineering effort optimizes for a scenario that **should not exist**. A Raspberry Pi with 4GB RAM should not be attempting local LLM inference. It should offload all LLM work to a compute peer and use template thoughts when the peer is asleep.

### 6.2 The Analysis

| Device | RAM | Local LLM viable? | Recommendation |
| :--- | :--- | :--- | :--- |
| Pi 4 (2GB) | 2GB | No — OOM on any model | Offload only. Template thoughts when peer asleep. |
| Pi 4 (4GB) | 4GB | Marginal — 1B model fits but is inadequate for `secure_model`'s responsibilities | Offload only. Template thoughts when peer asleep. |
| Pi 5 (4GB) | 4GB | Marginal — same as above | Offload only. Template thoughts when peer asleep. |
| Pi 5 (8GB) | 8GB | Yes — 3B Q4 fits (~2.5GB), 10-15 tok/s | Offload preferred. 3B local as fallback. |
| N100 (8GB) | 8GB | Yes — 3B Q4 fits | Offload preferred. 3B local as fallback. |
| N150 (16GB) | 16GB | Yes — 4B Q4 fits (~2.5GB), 10-15 tok/s | Offload preferred. 4B local as fallback. |

> **Code-verified correction (2026-08-30):** in code, `SBC_LOW_POWER` is strictly **<4GB** — a 4GB host classifies as `ENTRY_8GB` (`hardware_detector.py:423-424`, whose own comment names "Pi 5 4GB"), and `ENTRY_8GB` has local-model support `True` (`compute_router.py:263`). The 4GB rows above ("offload only") therefore conflict with 6.3's own concession that "the `ENTRY_8GB` profile (4-8GB) MAY use a local 3B model as fallback." **Decision required before S4:** either (a) move the classification boundary so 4GB hosts classify `SBC_LOW_POWER` (change `>= 4` at `hardware_detector.py:423`, update `compute_router._hardware_supports_local_model` at `:263` and `test_hardware_profile_fallback.py:31-53`), or (b) keep the code's classification and correct this table/docs to "<4GB = offload-only; 4GB = `ENTRY_8GB` with optional 3B fallback." The handoff did not acknowledge this conflict.

The 1B model tier exists solely to make <=4GB devices "work" with local AI. But:
- A 1B model is inadequate for `secure_model`'s responsibilities (per Halbert's own capability table — see section 3.5)
- With `secure_model` removed from HA variants (Finding 1), there is no mandatory local model requirement for HA nodes
- The `chat_model` and `specialist_model` are offloaded to the workstation
- Cognitive monologue uses template thoughts (`HALBERT_LLM_THOUGHTS=0`)
- Therefore: **no HA node needs a local LLM at all**, regardless of RAM

The 1B tier, the IQ2_XXS quantization research, and the "2B Q4 vs 4B Q2" tradeoff analysis are solving a problem that the federated architecture already solves (offload + template thoughts fallback).

### 6.3 Resolution

**Drop the 1B model tier as a supported configuration. Document <=4GB as offload-only.**

- The `SBC_LOW_POWER` hardware profile (<=4GB) should not attempt local model loading
- The `ComputeRouter` on `SBC_LOW_POWER` devices uses: peer offload (when available) -> template thoughts (when peer asleep). No local model fallback tier.
- The `ENTRY_8GB` profile (4-8GB) MAY use a local 3B model as fallback, but offloading is preferred
- Product documentation should state: "Devices with 4GB RAM or less require a compute peer for LLM functionality. Local inference is not supported on these devices."

### 6.4 Code Impact

| File | Change |
| :--- | :--- |
| `halbert_core/halbert_core/model/hardware_detector.py` | **Corrected:** `_classify_hardware()` (`:392-427`) only returns the `HardwareProfile` enum — it contains no model recommendation. The budget logic lives in `recommend_budget()` (`:429-490` — where the "1B tier" exists only as emergent arithmetic: 2GB × 0.6 / 0.65 ≈ 1B params at `:451-455`) and `get_installation_commands()` (`:492-525`). Make both return "offload only" for `SBC_LOW_POWER`: zeroed `max_params` with an explicit offload-only note, and skip the `ollama pull` block in favor of peer-configuration guidance. |
| `halbert_core/halbert_core/federation/compute_router.py` | **Already implemented and tested:** `_hardware_supports_local_model()` (`:254-265`) excludes `sbc_low_power`, pinned by `test_hardware_profile_fallback.py:31-33`. The remaining work is implementing `route()` itself (currently `NotImplementedError`, `:233`) to honor peer -> template thoughts with no local attempt and no 1B tier. |
| `halbert_core/halbert_core/model/config_wizard.py` | **New functionality, not a modification:** the wizard has no hardware-profile gating, no peer/offload concept, and no variant parameter today (its only model prompt is "Guide model name", `:209-213`; `run_auto`/`run_interactive` at `:79,:135`). Add: skip local-model listing on `SBC_LOW_POWER`, prompt for a compute peer address, and teach `_build_config` to write a peer endpoint (also `Halbert/main.py:1379-1425` for the CLI surface). |
| `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` | Section 7 (Local LLM Assessment) should be revised: the 1B tier is dropped, the 2B-3B tier is the minimum for local inference (8GB+ hosts only), and <4GB is offload-only (subject to the 6.2 boundary decision). Note the 1B/Q2_K/IQ2_XXS quantization tradeoff material exists **only in that doc** — code contains no such strings; both modules are deliberately model-name-agnostic. |

### 6.5 What This Eliminates

- The 1B-1.5B parameter class as a supported `secure_model` configuration
- The `Q2_K` / `IQ2_XXS` extreme quantization research
- The "smaller model vs extreme quantization" tradeoff analysis
- The `SBC_LOW_POWER` local model fallback path in `ComputeRouter`
- The cognitive overhead of supporting a model tier that is inadequate for its intended role

---

## 7. Finding 5: Apple Intelligence Is Not a Peer-Offload Target

### 7.1 The Problem

The Apple Intelligence integration (`HANDOFF-APPLE-INTELLIGENCE-IMPLEMENTATION-2026-08-29.md`) added `apple-foundation` as a local provider with Metal GPU detection and auto-provisioning. The federated handoff (finding M13) notes that the Compute Host pillar lists "Ollama / vLLM / MLX" but omits Apple Intelligence, and recommends adding it as a first-class compute source.

The implication is that a Mac Studio compute host could serve peer compute requests via Apple Intelligence — i.e., a Linux satellite sends a prompt to the Mac, the Mac runs it through Apple Intelligence on the ANE, and returns the result.

### 7.2 The Analysis

**Technical feasibility:** The peer link is an OpenAI-compatible HTTP endpoint (`/api/compute/v1/chat/completions`). It doesn't care what backend the Mac uses. If the Mac's compute endpoint routes incoming peer requests through `apple-foundation`, it would technically work.

**Two problems:**

1. **Apple's terms of service.** Apple Intelligence is designed for on-device personal use. Serving it as an inference endpoint for other machines — even your own on your own network — may violate Apple's developer terms. This is a legal question that is unresolved. Building a product feature on top of an uncertain legal foundation is risky.

2. **Capability mismatch.** Apple Intelligence's 3B model is optimized for short, personal, on-device interactions (summarization, writing tools, Siri responses). It is not a general-purpose 7B-14B class model. Using it as a `specialist_model` offload target for a Linux satellite's complex reasoning tasks would likely underperform compared to an Ollama 7B-14B model on the same Mac.

### 7.3 Resolution

**Apple Intelligence is for the Mac's own use only. Peer compute endpoints on a Mac route to Ollama (7B-14B), not Apple Intelligence.**

The Mac runs two local model backends:
- **Apple Intelligence** (via `apple-foundation`) — for the Mac's own `chat_model` / `secure_model` (personal, on-device, ANE-accelerated)
- **Ollama 7B-14B** — for serving peer compute requests from Linux satellites

The compute endpoint (`compute_endpoint.py`) on the Mac should route peer requests to Ollama, not to `apple-foundation`. The Mac's own Halbert UI can use either backend (configured via the Mac's model picker).

### 7.4 Code Impact

| File | Change |
| :--- | :--- |
| `halbert_core/halbert_core/federation/compute_endpoint.py` | When serving peer requests, route to the Ollama backend, not `apple-foundation`. The peer compute endpoint should not expose Apple Intelligence as an available model to peers. Concretely today: the models-route TODO at `:231-232` ("Query the local Ollama / Apple Intelligence / vLLM instances") and the `_submit_to_broker` docstring at `:257` must say Ollama/vLLM only — this binds when the `TODO(federation-9.3)` implementation lands. |
| `halbert_core/halbert_core/federation/peer_discovery.py` | The mDNS TXT record's `compute_backends` field should list `ollama` (and optionally `vllm`), not `apple_foundation`. Peers should not attempt to use Apple Intelligence. Apple-foundation appears at `:35,:37,:42-47,:82,:272,:282,:292-293`. |
| `halbert_core/halbert_core/model/providers/peer.py` | `PeerProvider.list_models()` should receive only the Ollama model list from the Mac, not Apple Intelligence models. Also remove the `:45` models.yml example metadata `peer_capabilities: [gpu_llm, apple_foundation, vision]`. |
| `halbert_core/halbert_core/federation/peers_config.py` | **Missed by the original table:** `:88` capabilities comment lists `apple_foundation` — remove. |
| `halbert_core/halbert_core/federation/README.md` | **Missed by the original table:** `:35` lists Apple Intelligence as a compute foundation; `:105` phase row "9.10 \| Apple Intelligence \| apple-foundation as advertised peer capability" — rewrite 9.10 as the negative constraint (advertise `ollama`/`vllm` only; Apple Intelligence is never a peer backend). |
| `halbert_core/tests/federation/test_peer_discovery.py` | **Missed by the original table:** `:36` builds a peer with `compute_backends=["ollama", "apple_foundation"]` and `:43` asserts `txt["compute_backends"] == "ollama,apple_foundation"` (`:119` likewise). This test fails unless updated in the same change. |
| `HANDOFF-APPLE-INTELLIGENCE-IMPLEMENTATION-2026-08-29.md` | Add a note: Apple Intelligence is local-only (Mac's own use). Not exposed as a peer compute backend. |

---

## 8. Summary: What the HA Node Actually Needs

After all simplifications, the HA node (N150 or similar) runs:

| Component | RAM | Purpose | Offloadable? |
| :--- | :--- | :--- | :--- |
| Linux OS (headless) | ~1GB | Runs everything | No |
| Home Assistant | ~2GB | The "body" — controls the house | No (this IS the HA controller) |
| Halbert `home-light` daemon | ~300MB | Cognition, HA event stream, persona memory, dashboard | No (the home identity lives here) |
| Wyoming voice (sherpa-onnx ASR + Piper TTS) | ~300MB | Voice in/out — ONNX runtime, not LLM | No (real-time audio can't tolerate network latency) |
| Memory embeddings (sentence-transformers all-MiniLM-L6-v2) | ~200MB | Persona memory retrieval — NOT SourcePrep, NOT RAG | No (memory is per-node, per-identity) |
| Template thoughts (cognitive monologue / `advance_turn`) | ~0 CPU, ~0 RAM | Deterministic templated responses when workstation asleep | N/A (this IS the fallback) |
| SnapRAID (nightly sync, peak) | ~2GB | Backup — unrelated to Halbert | No (local to the drives) |
| **Total** | **~6GB** | **16GB gives 10GB headroom** | |

**No LLM runs on the HA node.** Not for chat, not for specialist reasoning, not for secure operations, not for cognitive monologue. The HA node is a cognition + voice + HA-control node that delegates all language model work to the workstation.

### What Is Offloaded to the Workstation

| Offloaded | How | When workstation is asleep |
| :--- | :--- | :--- |
| `chat_model` (conversation LLM) | `peer://workstation:8000` via ComputeRouter | Template thoughts — no LLM response |
| `specialist_model` (complex reasoning) | `peer://workstation:8000` via ComputeRouter | Deferred or template thoughts |
| SourcePrep (RAG) | Not configured on HA node. Workstation runs it for its own sysadmin use. | N/A |
| Sysadmin for the HA device | Workstation's Halbert connects to HA node via MCP (fleet cockpit) | Not applicable — sysadmin is interactive, done when you're at the workstation |

---

## 9. Impact on the Federated Scaffold

The federated handoff scaffolded 28 files for Phase 9+. The simplifications in this document affect several of them:

| Scaffolded file | Impact |
| :--- | :--- |
| `federation/compute_router.py` | **Verified:** both simplification properties are already the scaffolded state — `_hardware_supports_local_model()` excludes `sbc_low_power` (`:254-265`) and the file contains zero `secure_model` references. The remaining work is implementing `route()` (`NotImplementedError`, `:233`) to honor peer -> template thoughts. |
| `federation/compute_endpoint.py` | On Mac compute hosts: route peer requests to Ollama, not `apple-foundation` (spec-comment fix now; binds at federation-9.3 implementation). |
| `federation/peer_discovery.py` | mDNS TXT record `compute_backends` lists `ollama` / `vllm`, not `apple_foundation`. |
| `federation/tool_allowlist.py` | No change — verified. `PEER_ALLOWED_TOOLS` including `search_knowledge` remains correct because the allowlist executes on the workstation (which keeps SourcePrep). `test_secure_model_no_offload.py` and `test_peer_tool_allowlist.py` continue to pass unchanged. |
| `model/providers/peer.py` | `PeerProvider.can_serve_slot("secure_model")` returns `False` (unchanged — `:80,:86,:102-103,:253-261`). For HA variants, `secure_model` doesn't exist at all, so this is moot. **Verified gap:** the provider is registered nowhere in the model stack (`peer` missing from `CHAT_CAPABLE_PROVIDERS`, `tier_router.py`, `providers/__init__.py`) — S3 requires registration. |
| `model/llm_config.py` | HA variants leave `secure_model` unconfigured. `chat_model` and `specialist_model` resolve to peer endpoint. No code change to the module itself (ships empty; variant-free by design). |
| `model/hardware_detector.py` | `SBC_LOW_POWER` profile recommends offload-only, no local model — in `recommend_budget()`/`get_installation_commands()`, not `_classify_hardware()` (see 6.4). |
| `federation/__init__.py` | **Scaffold bug found during verification (not in the original table):** `__all__` (`:53`) and the lazy import (`:77-79`) reference `PeerAuthMiddleware`, which `peer_middleware.py` does not define (it defines `require_peer_auth`/`optional_peer_auth`/`PeerContext`) — `halbert_core.federation.PeerAuthMiddleware` raises `ImportError`. Fix alongside S6; also stale docstring refs at `peers_config.py:211` and `tests/federation/test_token_revocation.py:122`. |

---

## 10. Recommended Implementation Order

These simplifications should be implemented BEFORE the federated Phase 9 work, because they reduce the scope of what Phase 9 needs to build:

| Step | Change | Builds on |
| :--- | :--- | :--- |
| **S0** | **Prerequisites/decisions surfaced by code verification (2026-08-30):** (1) unify variant resolution — `GET /api/instance/info` reads env only while backend gating uses `cognition_wiring._get_variant()` (being.yml first), so S1/S3 UI gating and backend gating can disagree; (2) decide the 4GB classification boundary (see 6.2); (3) confirm which memory path the HA persona actually consumes before touching packaging (see 4.7). | `routes/instance.py`, `cognition_wiring.py`, `hardware_detector.py`, `pyproject.toml` |
| **S1** | Remove `secure_model` from `home` / `home-light` variants — the real work is gating `auto_provision.py`, `config_wizard.py`, and the `agent.py` secure turn gate, plus hiding the role in `ModelSettings.tsx` | `SECURE-MODEL-AND-LIGHT-VARIANT-2026-08-29.md` |
| **S2** | Remove SourcePrep from `home` / `home-light` variants — variant-gate the adapter/assembler/app-seam wiring, the config-watcher reindex callback, and the HA-config bridge surface (see corrected 4.6) | `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` section 6 |
| **S3** | Replace model picker with "Compute Peer" setting for HA variants — includes registering `PeerProvider` in the model stack and persisting the peer endpoint into `chat_model`/`specialist_model` | `@halbert/model-picker`, `halbertModelRoles.ts`, `providers/peer.py` |
| **S4** | Drop 1B model tier. `SBC_LOW_POWER` = offload only — clamp `recommend_budget()`/`get_installation_commands()`, add wizard compute-peer prompt (new functionality), implement `ComputeRouter.route()` | `hardware_detector.py`, `config_wizard.py`, `compute_router.py` |
| **S5** | **Revised:** serve HA memory embeddings via Ollama/ONNX (haloysius path); do NOT add `sentence-transformers` to halbert_core extras. Optionally add a `[home]` extra = `[light]` + `[cognition]`. | `pyproject.toml`, see 4.7 correction |
| **S6** | Document Apple Intelligence as local-only. Peer compute routes to Ollama on Mac — plus `peer.py`/`peers_config.py`/`federation/README.md` references and the `test_peer_discovery.py` assertion | `compute_endpoint.py`, `peer_discovery.py`, see 7.4 |
| **S7** | Update `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` to reflect: no 1B tier, no SourcePrep for HA, <4GB = offload only (per the 6.2 boundary decision) | Documentation |

After S1-S7, the federated Phase 9 work (peer auth, compute endpoint, router, discovery) has a cleaner target: the HA node is a pure compute client with no local models, no SourcePrep, no `secure_model`, and no model picker.

---

## 11. Open Questions for the Halbert Team

> **2026-08-30 code-verification update:** Q2 is resolved — see the 4.7 correction (reject option (a); the on-path embedder is haloysius's ONNX/Ollama `MemoryEmbedder`, not halbert_core's `sentence-transformers`). Q1 now has its evidence base recorded: the exact per-variant service-skip matrix in `dashboard/app.py` shows `home` = `home-light` + scheduler/proactive jobs + config watcher + terminal reaper + HA-config seeding (Section 12). Q3 and Q4 remain open.

1. **Should `home` and `home-light` merge?** With SourcePrep and `secure_model` removed from both, the remaining difference is whether the scheduler/config-watcher/terminal/ingestion services run. If `home` is just `home-light` + those services, and those services are sysadmin features that an HA node doesn't need, should `home` be retired in favor of `home-light` as the single HA variant?

2. ~~**Should the `[light]` extra include `sentence-transformers`?**~~ **Resolved 2026-08-30** — no: the dependency attribution was wrong (see 4.7). Serve memory embeddings via Ollama (`nomic-embed-text`) or the haloysius ONNX embedder; keep `[light]` unchanged; `haloysius[embeddings]` is the optional upgrade.

3. **What happens to `vision_model` on HA nodes?** The federated handoff says `vision_model` can peer-offload "if peer advertises `vision` capability." For HA nodes using Frigate, does the HA Halbert need `vision_model` at all, or does Frigate handle all vision processing and Halbert just consumes MQTT events? If the latter, `vision_model` can also be removed from HA variants.

4. **The `advance_turn` cognitive monologue on HA nodes.** With template thoughts as the only option (no local LLM, no offload for monologue per finding H8 in the federated handoff), is the cognitive monologue useful at all for HA? Or should `advance_turn` be disabled entirely on HA variants, with cognition happening only on explicit user/automation triggers?

---

## 12. Code Verification Addendum (2026-08-30)

Every code-impact claim in sections 3-9 was verified against the working tree by a 16-agent survey (10 doc groups, 5 code areas, repo-wide sweep) on 2026-08-30. This section is the authoritative, file-anchored work list. Where it conflicts with the prose above, this section wins (the prose has been corrected inline where flatly wrong, marked "**Code-verified correction**").

### 12.1 Decisions Required Before Implementation

| ID | Decision | Why it blocks work |
| :--- | :--- | :--- |
| **D1** | Unify variant resolution: make `GET /api/instance/info` (`dashboard/routes/instance.py:33`) use `cognition_wiring._get_variant()` (being.yml > env > sysadmin) instead of reading `HALBERT_VARIANT` env only. | Backend service gating and frontend feature flags currently disagree: a being.yml-set variant gates backend services while the UI still renders the sysadmin picker and secure_model row. Blocks S1/S3/S4 UI work. |
| **D2** | 4GB boundary: either 4GB hosts classify `SBC_LOW_POWER` (move `>= 4` at `hardware_detector.py:423`, update `compute_router.py:263` + `test_hardware_profile_fallback.py:31-53`) or docs say "<4GB = offload-only" and 4GB stays `ENTRY_8GB` with optional 3B fallback. | The 6.2 table and 6.3 bullet contradict each other and the code. Blocks S4. |
| **D3** | Confirm which memory path the HA persona consumes on a home node: the receipts/FTS5 path (`agent.py:144-146` wires `memory_service=None`) or the haloysius `MemoryEmbedder` path (`cognition_wiring.py:122`). | If FTS5 is operative, S5 needs no packaging change at all. |
| **D4** | Open question 11.1 (merge `home`/`home-light`) — evidence base: the per-variant service-skip matrix in `dashboard/app.py`. For BOTH home and home-light: ingestion service (`:431-432`), startup discovery scan (`:455-456`). For home-light ONLY: scheduler + proactive jobs (`:476-477`; the else-branch at `:478-594` — detector sweep, morning report, VisualWatcher — runs for home), config watcher (`:600-601`), terminal reaper (`:637`), HA-config seeding (`:647-654`). Never gated: all routers incl. rag/ChromaDB (`:272-306`), HA event stream (`:657-676`), Wyoming (`:678-698`), Frigate (`:700-732`). | Determines whether S2's watcher gating collapses into the merge. |

### 12.2 Verified Work Items by Step

| ID | Step | Work item | Files (verified) | Size |
| :--- | :--- | :--- | :--- | :--- |
| W1 | S1 | Gate Apple Intelligence auto-provisioning of `secure_model` by variant (`auto_provision.py:66-71` assigns whenever empty; triggered from `GET /llm/config` at `routes/llm.py:~208-217`) | `model/auto_provision.py`, `dashboard/routes/llm.py` | small |
| W2 | S1 | Add variant awareness to the config wizard's secure_model writes (`run_auto`, `_build_config` at `config_wizard.py:101-107, 262-299, 323-327`; `save_config` deep-merges slots — write empty, don't omit) | `model/config_wizard.py` | small |
| W3 | S1 | Variant-gate the secure turn gate (`agent.py:465-476` resolves `get_secure_model()` per turn; `tier_router.py:136` likewise) — skip the dedicated branch for home/home-light so it falls through to the local-guide/fail-closed chain (`agent.py:419-428`) | `dashboard/routes/agent.py`, `model/tier_router.py` | small |
| W4 | S1 | Add `variants: ["sysadmin"]` to the secure_model role (`halbertModelRoles.ts:21`); optional `variants?: string[]` field on `AppRole` (`packages/model-picker/src/types.ts:71-83`, opaque host-supplied) | `halbertModelRoles.ts`, `packages/model-picker/src/types.ts` | trivial |
| W5 | S1 | Filter roles by active variant host-side in `ModelSettings.tsx` before `useModelPicker` (precedent: `displayRoles` memo `:384-392`; also `AgentChat.tsx:183` renders roles unconditionally). Do NOT filter inside the shared package (`RoleAssignmentRow.tsx:38-46` renders exactly one role; package rule: no role-name logic) | `ModelSettings.tsx`, `AgentChat.tsx` | small |
| W6 | S1 | Restrict secure_model documentation in `deploy/README.md` to the sysadmin instance (`:111-113` per-instance guidance, `:122` "keep secure_model pointing at localhost" in the LAN-offload section) | `deploy/README.md` | trivial |
| W7 | S2 | Variant-gate the agent-path SourcePrep adapter: `rag_service = SourcePrepAdapter()` at `agent.py:136-142` runs for every variant — pass None for home/home-light and verify the state machine tolerates it | `dashboard/routes/agent.py` | small |
| W8 | S2 | Variant-gate the assembler factories: `SourcePrepAdapter.__init__` auto-creates the backend (`adapters.py:337-343`); `create_wired_context_assembler` (`:429`), `create_agent_context_assembler` (`:455`), `create_extended_context_assembler` (`extra_adapters.py:559`) wire it unconditionally — add a variant gate or `set_retrieval_enabled(False)` seam | `context/adapters.py`, `context/extra_adapters.py` | medium |
| W9 | S2 | Pass `skip_retrieval=True` to `wire_halbert_seam()` for HA variants (parameter already exists, `app_seam.py:376`; called unconditionally at `cognition_wiring.py:141-149`) | `integrations/cognition_wiring.py`, `integrations/app_seam.py` | trivial |
| W10 | S2 | Drop the config-watcher SourcePrep reindex callback for `home` (watcher currently skipped for home-light only, `app.py:600-601`; reindex callback at `:616-622` from `config/watcher.py:174-193`) — keep `create_detector_trigger_callback` | `dashboard/app.py`, `config/watcher.py` | small |
| W11 | S2 | Retire the HA-config SourcePrep surface: `HA_SOURCEPREP_ENABLED` defaults `"1"` (`ha_config_bridge.py:44-49`), `/home/config-search`(+`/status`) endpoints live for all variants (`routes/home.py:178-192`), `ha_config_tools.py` is vestigial (its `register_ha_config_tools` is never called — `agent.py:224-225` registers only `register_ha_tools`). Remove or default-disable; decide deletion of the dead tool module | `integrations/home_assistant/ha_config_bridge.py`, `ha_config_tools.py`, `dashboard/routes/home.py` | medium |
| W12 | S2 | Update HA-path tests that assume SourcePrep presence (`test_ha_phase3.py:30` sets `SOURCEPREP_URL`) to assert absence for home/home-light; keep the sysadmin backend unit tests | `halbert_core/tests/test_ha_phase3.py` | small |
| W13 | S2 | Deployment artifacts: drop SourcePrep prerequisites from `deploy/README.md` (`:13` daemon, `:102` `SOURCEPREP_PROJECT_ID=ha-config`, `:124` LAN-offload rec) and `deploy/halbert-home.service` (`Environment=SOURCEPREP_PROJECT_ID=ha-config`) | `deploy/README.md`, `deploy/halbert-home.service` | trivial |
| W14 | S3 | Register `PeerProvider` in the model stack — `peer` is missing from `CHAT_CAPABLE_PROVIDERS` (`model/client.py:72-74`), `tier_router.py`, and `providers/__init__.py`, so `llm_config.py:411-413` disables any peer slot as "not chat-capable." Prerequisite for any Compute Peer setting | `model/client.py`, `model/tier_router.py`, `model/providers/__init__.py`, `model/providers/peer.py` | large |
| W15 | S3 | Build the ComputePeerCard settings surface and mount it instead of `<ModelSettings />` for home/home-light (`Settings.tsx:2241`, unconditionally mounted). Reuse fleet plumbing (`PeerPairingModal.tsx`, `DiscoveredPeerCard.tsx`, `routes/peers.py`, `routes/compute.py`). Decide the `ChatModelPill` surface (hide vs read-only) | `pages/Settings.tsx`, `components/llm/ModelSettings.tsx`, `ChatModelPill.tsx` | medium |
| W16 | S3 | Persist the peer endpoint and resolve both slots to it: `peer://` exists in the backend (`providers/peer.py:37-47, 149-150`) but nothing creates a peer endpoint (no `peer` in the picker's `ProviderId` union, `types.ts:23-32`; `ensure_endpoint` never called with one, `llm_config.py:825-840`). On pairing: `ensure_endpoint('peer://...')` + `set_slot('chat_model'/'specialist_model', ...)` | `model/llm_config.py`, `model/providers/peer.py`, `modelPickerTransport.ts` | medium |
| W17 | S4 | Clamp `recommend_budget()` to offload-only for `SBC_LOW_POWER` (`hardware_detector.py:429-490`; the "1B tier" is emergent arithmetic at `:451-455`) and make `get_installation_commands()` (`:492-525`) skip the `ollama pull` block in favor of peer guidance; verify `pick_installed_model()` (`:194-228`) and `config_wizard.find_installed_model` (`:65-77`) select nothing on a zeroed budget | `model/hardware_detector.py` | small |
| W18 | S4 | Implement `ComputeRouter.route()` (currently `NotImplementedError`, `compute_router.py:233`) honoring peer -> template thoughts with no local attempt. The SBC skip itself already exists and is tested (`:254-265`, `test_hardware_profile_fallback.py:31-33`) — no edit needed there | `federation/compute_router.py` | medium |
| W19 | S4 | Wizard compute-peer flow (new functionality): `config_wizard.py` has no profile gating, no peer concept, and no variant parameter today; add SBC_LOW_POWER skip of local-model listing, a compute-peer address prompt, and a peer endpoint shape in `_build_config`; surface via `Halbert/main.py:1379-1425` | `model/config_wizard.py`, `Halbert/main.py` | medium |
| W20 | S5 | Per D3: if the haloysius embedder path is operative, serve HA memory embeddings via Ollama (`nomic-embed-text`) / ONNX and optionally add `[home]` extra = `[light]` + `[cognition]`; never install `[rag-legacy]` (bundles chromadb) on HA nodes. Do NOT add `sentence-transformers` to halbert_core extras | `halbert_core/pyproject.toml`, `deploy/README.md` | small |
| W21 | S5 | Verification pass the original analysis missed: confirm the Memory dashboard page renders a sane `chromadb_available: false` state on a home node (`routes/memory.py:40-56` calls `index.chroma_index.get_index`; try/except-guarded at `:46,56` but confirm no warning spam) | `dashboard/routes/memory.py`, `memory/hybrid.py` | small |
| W22 | S6 | Strip `apple_foundation` from the mDNS contract: `peer_discovery.py:35,37,42-47,82,272,282,292-293`; `compute_endpoint.py:231-232,257`; `providers/peer.py:45`; `peers_config.py:88`; `federation/README.md:35,105` (rewrite phase 9.10 as the negative constraint) | see files | small |
| W23 | S6 | Update `test_peer_discovery.py:36,43,119` which currently **asserts** `compute_backends == "ollama,apple_foundation"` — fails unless updated in the same change | `halbert_core/tests/federation/test_peer_discovery.py` | trivial |
| W24 | S6 | Fix the `PeerAuthMiddleware` export bug found during verification: `federation/__init__.py:53,77-79` imports a class `peer_middleware.py` does not define (it defines `require_peer_auth`/`optional_peer_auth`/`PeerContext`) — `halbert_core.federation.PeerAuthMiddleware` raises `ImportError`. Also stale refs at `peers_config.py:211`, `test_token_revocation.py:122` | `federation/__init__.py` | trivial |
| W25 | S7 | Revise `HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` section 7 (drop 1B tier and Q2_K/IQ2_XXS material — code contains no such strings; only generic Q4_K_M at `model/loader.py:24`, `providers/ollama.py:388`) and the stale "<=4GB" comments at `hardware_detector.py:34`, `compute_router.py:29,258` per D2 | doc + docstrings | small |

### 12.3 Verified No-Change Items

- `llm_config.py` — ships `secure_model` empty for all variants (`:158`); variant-free by design; `normalise()` re-materialises all four slots. Do not add variant coupling.
- `federation/tool_allowlist.py` — `PEER_ALLOWED_TOOLS` incl. `search_knowledge` stays (allowlist executes on the workstation, which keeps SourcePrep).
- `model/providers/peer.py` secure_model refusals (`:80,86,102-103,253-261`) and `test_secure_model_no_offload.py` / `test_peer_tool_allowlist.py` — pass unchanged.
- The 28-file federated scaffold list — no file added or removed; only the purpose/expectations of `peer_discovery.py`, `compute_endpoint.py`, `compute_router.py`, `peer.py` and two test files change (plus the net-new ComputePeerCard, which sits outside the scaffold).
- `config/models.yml` — template ships `secure_model` empty (verify the shipped default; the sweep flagged it for confirmation).
