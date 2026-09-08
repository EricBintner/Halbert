# APPLE-1: Apple FoundationModels integration path is wrong — HTTP endpoint assumption is unbuildable as designed

**Date:** 2026-09-07
**Severity:** High (functional — secure_model is inert; security-adjacent — triggers SEC-15)
**Status:** Open, needs investigation
**Discovered by:** Devin session 2026-09-07

## Summary

The `secure_model` slot is configured to point at `http://127.0.0.1:11435` serving model `apple-foundation-3b` via provider `apple-foundation`. This assumes a Swift sidecar binary (`halbert-foundation-bridge`) that exposes Apple's FoundationModels framework as an OpenAI-compatible HTTP server on loopback port 11435.

**That sidecar was never built.** Nothing listens on port 11435. More fundamentally, the assumption that Apple FoundationModels can be served over HTTP is an architectural choice from a 2026-08-29 design doc that was never validated against the actual framework API — and the framework API does not speak HTTP.

## What Apple FoundationModels actually is

Verified on this machine (M1 Ultra, macOS 26.5.1, Xcode SDK MacOSX26.5):

```
$ swift -e 'import FoundationModels; print(SystemLanguageModel.default.availability)'
available
```

FoundationModels is a **native Swift framework** (`/System/Library/Frameworks/FoundationModels.framework`). The API surface is:

- `SystemLanguageModel.default` — the root interface to the on-device model
- `SystemLanguageModel.default.availability` — `.available` / `.unavailable` / `.unavailable(reason)`
- `LanguageModelSession(model:instructions:tools:)` — stateful session
- `session.respond(to:)` — single-shot generation (async)
- `session.streamRespond(to:)` — streaming generation (async sequence)
- `@Tool` protocol — native tool calling
- `@Generable` — guided structured output

There is **no HTTP server**, **no REST API**, **no CLI**, and **no network interface**. The framework is called directly from Swift code via `async` functions. The `fm` CLI mentioned as "Option B" in the design doc does not exist on this system (`which fm` → not found).

## What the config currently says

From the live backend (`GET /llm/config/effective`):

```json
"secure_model": {
    "enabled": true,
    "endpoint_id": "ep_e452090a",
    "model": "apple-foundation-3b"
}
```

Endpoint `ep_e452090a`:
```json
{
    "id": "ep_e452090a",
    "name": "Apple Intelligence (On-Device)",
    "provider": "apple-foundation",
    "url": "http://127.0.0.1:11435",
    "api_key": ""
}
```

The endpoint was auto-provisioned by `auto_provision_apple_intelligence()` in `halbert_core/halbert_core/model/auto_provision.py`, which registered it because `hardware.apple_intelligence_bridge_running` returned `True` at some prior boot. The bridge probe (`_probe_apple_foundation_bridge`, `hardware_detector.py` line 383) checks `http://127.0.0.1:11435/v1/models` — which currently returns nothing.

## Why the bridge probe may have passed previously

The probe in `hardware_detector.py` lines 383-400:

```python
def _probe_apple_foundation_bridge(self) -> bool:
    try:
        import requests as _requests
        resp = _requests.get("http://127.0.0.1:11435/v1/models", timeout=0.5)
        return resp.status_code == 200
    except Exception:
        return False
```

This returns `False` now (nothing on 11435). The endpoint registration that did happen must have come from a prior session where something was briefly on that port, or the provisioning ran before the bridge check was added. Either way, the endpoint is now inert: registered in config, but unreachable.

## The three options from the design doc (all unverified)

From `documentation/design/APPLE-INTELLIGENCE-MACOS-ON-DEVICE-STRATEGY.md`:

| Option | Mechanism | Status |
|--------|-----------|--------|
| A: Swift sidecar | Swift binary bundles with Tauri, serves OpenAI HTTP on 11435 | Never built. The `tools/apple_intelligence_bridge` SPM package was never created. |
| B: `fm` CLI | macOS built-in `fm exec` CLI | Does not exist on macOS 26.5.1. |
| C: PyObjC bridge | Python → PyObjC → FoundationModels.framework | Never attempted. Would add a hard dependency (PyObjC), violating the subtractive contract. |

**Option A is the planned path but has a deeper problem:** it assumes wrapping `LanguageModelSession.respond(to:)` (an async Swift function) behind an HTTP server is straightforward. It may be, but nobody has written the code, and the design doc's "Phase 1: Swift Bridge Prototype" was never executed.

## What needs to happen

1. **Investigation:** Validate whether Option A (Swift HTTP sidecar) is buildable. Write a minimal Swift SPM package that creates a `LanguageModelSession` and serves `POST /v1/chat/completions` via a tiny HTTP server (Swift NIO or Hummingbird). Confirm streaming (`streamRespond`) maps to SSE. Confirm `@Tool` protocol maps to OpenAI tool-calling JSON.

2. **Alternative investigation:** If the HTTP sidecar is too heavy, evaluate whether the Tauri Rust core can call FoundationModels via Swift FFI (Rust → `extern "C"` → Swift), eliminating the HTTP layer entirely. This would make `apple-foundation` a true on-device provider with no network hop, not even loopback.

3. **Interim hardening:** Until a working integration exists, `auto_provision_apple_intelligence()` should NOT register the endpoint. The current code registers it when `apple_intelligence_bridge_running` is True, but the bridge doesn't exist. The probe should be removed or made to always return False until the bridge is built. This prevents the config from pointing at a dead endpoint, which triggers SEC-15.

4. **Config cleanup:** The existing `ep_e452090a` endpoint and `secure_model` assignment should be cleared from the user's config, since they point at nothing.

## Why this is High, not Critical

The secure_model being inert is a functional gap, not a security hole by itself. The security hole is SEC-15 (the fallback leaks to cloud). But this issue is the trigger condition that makes SEC-15 reachable in practice — if the bridge worked, the secure turn would never fall back. Fixing SEC-15 is the priority; fixing this is what stops the fallback from being needed.

## Related

- **SEC-15** — the cloud-leak bug this issue triggers
- `documentation/design/APPLE-INTELLIGENCE-MACOS-ON-DEVICE-STRATEGY.md` — the original design doc (Option A)
- `.handoff/HANDOFF-APPLE-INTELLIGENCE-IMPLEMENTATION-2026-08-29.md` — implementation plan (never executed)
- `halbert_core/halbert_core/model/auto_provision.py` — auto-provisioning that registers the dead endpoint
- `halbert_core/halbert_core/model/hardware_detector.py` lines 383-400 — the bridge probe
- `halbert_core/halbert_core/model/llm_config.py` lines 81-89 — `APPLE_FOUNDATION_*` constants
