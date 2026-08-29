# Handoff: secure_model Slot — Architecture & Reasoning

**Date:** 2026-08-29
**Status:** Implemented, tested, pushed to `origin/main`
**Commits:** `8e3c2002`, `3029943d`, `552b99d1`, `cca3591a`

---

## 1. What Was Built

A 4th model slot (`secure_model`) was added to Halbert's multi-instance model architecture, alongside the existing `chat_model`, `specialist_model`, and `vision_model` slots. The slot is **local-only enforced** — it can only resolve to endpoints running on loopback or unspecified IP addresses. Cloud endpoints are rejected at normalisation time.

### Files touched (full list)

**Backend — model slot infrastructure:**
- `halbert_core/model/llm_config.py` — `SLOTS` tuple, `default_llm_config()`, `normalise()` local-only enforcement via `_is_local_url()`
- `halbert_core/model/client.py` — `get_secure_model()` returns `(model, url, provider)` or `(None, "", "")`
- `halbert_core/model/__init__.py` — exports `get_secure_model`
- `halbert_core/model/config_wizard.py` — empty slot in wizard defaults, validation loop checks 4 slots
- `halbert_core/model/tier_router.py` — slot resolution in `from_legacy_config`, docstring updated
- `halbert_core/model/config_layers.py` — layer schema warning includes `secure_model`
- `halbert_core/model/hardware_detector.py` — `SBC_LOW_POWER` and `ENTRY_8GB` profiles for low-power devices

**Backend — variant & BeingConfig:**
- `halbert_core/config/being_config.py` — `VALID_VARIANTS` now includes `"home-light"`; added `ha_url`/`ha_token` fields
- `halbert_core/integrations/cognition_wiring.py` — `_get_variant()` reads `BeingConfig.variant` before env var
- `halbert_core/dashboard/app.py` — `home-light` variant skips scheduler, config watcher, terminal sessions, ingestion, discovery; seeds HA config from `being.yml`

**Config & deploy:**
- `config/models.yml` — `secure_model` empty slot in repo template
- `deploy/halbert-home.service`, `deploy/halbert-host.service` — removed dead `HALBERT_MODEL` env var
- `deploy/README.md` — 4-slot model config docs, LAN/Tailscale GPU offload, light install instructions
- `halbert_core/pyproject.toml` — `[light]`, `[rag-legacy]`, `[full]` optional extras

**Frontend — model picker UI:**
- `packages/model-picker/src/types.ts` — `requiresLocal?: boolean` on `AppRole`
- `packages/model-picker/src/useModelPicker.ts` — filters non-local models when `requiresLocal` is set
- `packages/model-picker/src/primitives/RoleAssignmentRow.tsx` — endpoint dropdown filtered to local-only for `requiresLocal` roles
- `halbert_core/dashboard/frontend/src/lib/halbertModelRoles.ts` — 4th role: `secure_model` with `requiresLocal: true, optional: true`

**Tests:**
- `tests/test_secure_model.py` — 21 tests (slot existence, defaults, local-only enforcement, normalise, resolve_from)
- `tests/test_being_config.py` — 10 tests (home-light variant validation, HA field serialization)
- `tests/test_llm_routes.py`, `tests/test_tier_router_config.py`, `tests/test_llm_config_layers.py` — updated all 3-slot assertions to 4-slot

---

## 2. Why a 4th Slot — The Reasoning

### The problem it solves

Halbert processes system configuration, secrets, and operational data. The existing slots route traffic to whatever endpoint the user configured — including cloud providers (OpenAI, Anthropic, Google). For routine chat and specialist reasoning, cloud traffic is acceptable and often desirable (larger models, better reasoning).

But certain operations should **never** leave the machine:
- **Secret description** — the `describe_secret` Tier 2 path in `SecurityConfig` already enforces this architecturally (no model, deterministic response). But if a local model is ever reintroduced for open-ended questions about secrets, it must be guaranteed local.
- **Sensitive config analysis** — when Halbert reasons about SSH keys, credentials, or network topology, the prompt itself is sensitive even if the answer isn't a secret value.
- **Air-gapped / home-light operation** — the `home-light` variant runs on N100/Pi devices that may have no internet. A slot that can only resolve to a local model guarantees the system degrades gracefully offline.

### Why a slot, not a flag

A separate slot (rather than a "local_only" boolean on `chat_model`) was chosen because:

1. **Model independence** — the secure model can be a different, smaller model than the chat model. A user might run `qwen3:4b` locally for secure operations while routing chat to a larger cloud model. The slot lets them pick independently.
2. **Routing flexibility** — `tier_router.py` resolves slots independently. Adding a slot means the router can direct secure operations to it without conditionally overriding the chat model's endpoint at call time.
3. **UI clarity** — a 4th row in the model picker settings makes the local-only constraint visible and configurable. A boolean flag would be hidden in a config file.
4. **Consistency** — the existing architecture already has 3 slots with independent endpoint/model pairs. A 4th slot follows the same pattern — no new code paths, just a new entry in `SLOTS`.

### Why local-only enforcement is in `normalise()`, not at call time

The enforcement lives in `llm_config.normalise()`, which runs on every config read. If a user configures `secure_model` with a cloud endpoint URL, the slot is **silently disabled** at load time with a warning log — not rejected with an error. This is intentional:

- **Fail safe, not fail loud** — a misconfigured secure_model should not prevent the system from starting. The slot stays disabled, and callers get `(None, "", "")`, which they handle as "no secure model configured."
- **Defence in depth** — even if a user somehow bypasses the UI's local-only filtering and writes a cloud URL into `models.yml`, `normalise()` catches it on the next read. The UI filter is a convenience; `normalise()` is the enforcement.
- **Robust URL parsing** — `_is_local_url()` uses `urllib.parse` + `ipaddress` to check for loopback (`127.0.0.0/8`, `::1`) and unspecified (`0.0.0.0`, `::`) addresses. Hostnames like `localhost` are resolved. This is not a string match.

### What `secure_model` is NOT

- **Not a per-turn pin** — the `Tier` type in the model picker (`'guide' | 'specialist' | 'vision' | 'auto'`) does not include `'secure'`. Users don't pick "secure" from the chat pill. The backend routes to `secure_model` when it determines an operation requires local-only inference.
- **Not hardcoded to a model name** — the slot ships empty (`model: ""`, `enabled: false`). The user picks which local model to assign. No model names are hardcoded anywhere in the codebase.
- **Not a security boundary by itself** — the slot guarantees the model endpoint is local. It does not guarantee the model itself is trustworthy, that the prompt contains no sensitive data, or that the output is safe. It is one layer in a defence-in-depth strategy.

---

## 3. How It Works

### Configuration flow

1. User opens Settings -> AI Models in the dashboard
2. The 4th row "Secure (Local)" appears with `requiresLocal: true`
3. The endpoint dropdown shows only local endpoints (Ollama, LM Studio)
4. The model dropdown shows only models from local endpoints
5. User picks an endpoint + model, or leaves it unassigned (optional)
6. Save writes to `models.yml` under `llm_config.secure_model`

### Runtime resolution

1. `llm_config.load()` reads `models.yml`, runs `normalise()`
2. `normalise()` checks `secure_model` endpoint URL via `_is_local_url()`
3. If the URL is not local, the slot is disabled with a warning log
4. `client.get_secure_model()` calls `_store.resolve("secure_model")`
5. Returns `(model, url, provider)` if enabled, or `(None, "", "")` if not
6. Callers check for `None` and fall back to alternative behavior

### Local-only enforcement (`_is_local_url`)

```python
def _is_local_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    if host in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        # Hostname — resolve and check
        try:
            resolved = socket.getaddrinfo(host, None)
            for family, _, _, _, sockaddr in resolved:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_loopback or ip.is_unspecified:
                    return True
        except Exception:
            pass
        return False
```

---

## 4. The `home-light` Variant

A secondary deliverable was the `home-light` variant for thin clients (N100, Raspberry Pi). This is distinct from `secure_model` but related — both serve the "low-power, local-first" use case.

### What `home-light` skips at startup
- Ingestion service (journald, hwmon)
- Discovery scan (hardware scanners)
- Scheduler + proactive jobs (morning report, detector sweep, VisualWatcher)
- Config watcher (no local config tree to watch)
- Terminal session manager (no local shell on thin clients)

### What `home-light` still starts
- HA WebSocket event stream (core home automation functionality)
- Wyoming voice agent (if configured)
- Frigate MQTT subscriber (if configured)

### HA config seeding
`home-light` can store Home Assistant credentials directly in `being.yml` (`ha_url`, `ha_token`) instead of requiring a separate `ha_config.yml`. At startup, if these fields are present, they're written to the HA config so the event stream can connect. This makes `being.yml` the single file a home-light user needs to deploy.

### Variant resolution priority
`_get_variant()` in `cognition_wiring.py` follows the same pattern as `_get_persona_id()` and `_get_scene_context()`:
1. `BeingConfig.variant` (from `being.yml`)
2. `HALBERT_VARIANT` env var
3. Default: `"sysadmin"`

---

## 5. Dependency Trimming

`pyproject.toml` was restructured with optional extras:

| Extra | Includes | Use case |
|-------|----------|----------|
| `[light]` | Core deps only, no heavy ML | home-light variant, N100/Pi |
| `[rag-legacy]` | `chromadb`, `sentence-transformers` | Hosts that need the old RAG pipeline |
| `[full]` | Everything (`[light]` + `[rag-legacy]` + all heavy deps) | Full sysadmin install on capable hardware |

Heavy libraries (`chromadb`, `sentence-transformers`) moved from hard dependencies to `[rag-legacy]`. A `home-light` install pulls only the core FastAPI + Ollama client stack.

---

## 6. Test Coverage

| Test file | Tests | What's covered |
|-----------|-------|----------------|
| `test_secure_model.py` | 21 | Slot in `SLOTS`, default config, local-only enforcement (loopback, unspecified, hostname, cloud rejection), `normalise()` disable behavior, `resolve_from()` |
| `test_being_config.py` | 10 | `home-light` variant validation, `ha_url`/`ha_token` defaults, YAML round-trip, None-stripping |
| `test_llm_config_layers.py` | 49 (updated) | All `_models()` assertions updated to 4-slot, `slot_layers` includes `secure_model` |
| `test_llm_routes.py` | (updated) | API shape assertion includes `secure_model` |
| `test_tier_router_config.py` | (updated) | Repo template check includes `secure_model` |
| model-picker package | 103 | `requiresLocal` filtering in `modelsForRole`, `AppRole` type, no regressions |

**Pre-existing failures (not caused by this work):**
- `test_llm_routes.py` and 1 test in `test_llm_config_layers.py` fail on Python 3.9 due to `contextlib.aclosing` import in `agent.py` (requires Python 3.10+). These are unrelated to `secure_model`.

---

## 7. Review Checklist for Another AI

- [ ] Verify `_is_local_url()` handles all edge cases: IPv6 loopback (`::1`), IPv6 unspecified (`::`), hostnames that resolve to loopback, hostnames that resolve to non-loopback
- [ ] Verify `normalise()` disables the slot (not crashes) when a cloud URL is configured
- [ ] Verify `get_secure_model()` returns `(None, "", "")` when slot is disabled/unconfigured
- [ ] Verify the UI endpoint dropdown for `secure_model` shows only local endpoints
- [ ] Verify the UI model dropdown for `secure_model` shows only local models
- [ ] Verify `home-light` variant skips scheduler, config watcher, terminal sessions
- [ ] Verify `home-light` still starts HA event stream
- [ ] Verify `being.yml` `ha_url`/`ha_token` round-trips through YAML correctly
- [ ] Verify no hardcoded model names anywhere in the codebase
- [ ] Verify `HALBERT_MODEL` env var is fully removed from systemd units (not just renamed)
- [ ] Verify `[light]` extras in `pyproject.toml` don't pull `chromadb` or `sentence-transformers`
