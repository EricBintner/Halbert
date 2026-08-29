# Halbert Multi-Instance — Implementation Plan & Design

**Date:** 2026-08-29
**Status:** Reviewed & Updated 2026-08-29 — See companion review & UI architecture spec: `HALBERT-MULTI-INSTANCE-REVIEW-FEEDBACK.md`

---

## 1. Objective

Run two Halbert instances on the same machine: a **host sysadmin** instance and a **home automation** instance. Each has its own persona, memory, data directory, SourcePrep project, and integration scope. They share the same codebase but run as separate processes with different environment variables.

**Design principle:** No `InstanceManager`. No in-process multiplexing. Two daemon processes, isolated by env vars, each with their own port and data directory. This is the simplest approach that works and avoids the complexity of a registry/coordinator.

---

## 2. Current State (What Already Works)

The codebase already has env-var-driven parameterization from Phase 1:

### 2.1 Persona Identity (`cognition_wiring.py:32-50`)

```python
def _get_persona_id() -> str:
    return os.environ.get("HALBERT_PERSONA_ID", "halbert")

def _get_scene_context() -> str:
    env_ctx = os.environ.get("HALBERT_SCENE_CONTEXT", "").strip()
    if env_ctx:
        return env_ctx
    # Falls back to platform-derived default
```

`PersonaCognition` is created with `persona_id` and `scene_context` from these env vars. The `ThoughtGenerator` uses `persona_id.capitalize()` as the display name.

### 2.2 Data Directory (`ha_config.py:55-61`, `frigate_config.py:92-98`)

Both HA and Frigate configs load from `HALBERT_DATA_DIR`:

```python
data_dir = os.environ.get("HALBERT_DATA_DIR", os.path.expanduser("~/.local/share/halbert"))
return Path(data_dir) / "ha_config.json"
```

The general path resolver (`utils/paths.py:47-52`) uses `Halbert_DATA_DIR` (capital H) for the broader config/data/log paths:

```python
def data_dir() -> str:
    if os.environ.get("Halbert_DATA_DIR"):
        return os.environ["Halbert_DATA_DIR"]
    if _is_root():
        return "/var/lib/halbert"
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return os.path.join(xdg, "halbert")
```

**Inconsistency noted:** Two different env var names for the data dir — `HALBERT_DATA_DIR` (used by HA/Frigate config) and `Halbert_DATA_DIR` (used by the general path resolver). This must be unified.

### 2.3 SourcePrep Project (`sourceprep_client.py:38-52`)

```python
def resolve_default_project_id() -> str:
    pid = os.environ.get("SOURCEPREP_PROJECT_ID", "").strip()
    if pid:
        return pid
    # Falls back to .sourceprep/project.json in the project root
```

Each instance can point at a different SourcePrep project: `halbert-host` for the sysadmin instance, `ha-config` for the home instance.

### 2.4 Being Config (`config/being_config.py:171-172`)

```python
def _default_config_path() -> Path:
    return get_config_dir() / "being.yml"
```

`get_config_dir()` respects `Halbert_CONFIG_DIR`, so each instance loads its own `being.yml` personality file.

### 2.5 Wyoming Voice Agent (`wyoming_agent.py`)

```python
class WyomingConfig:
    @classmethod
    def from_env(cls) -> "WyomingConfig":
        return cls(
            host=os.environ.get("WYOMING_HOST", "0.0.0.0"),
            port=int(os.environ.get("WYOMING_PORT", "10400")),
            ...
        )
```

Each instance gets its own Wyoming port.

---

## 3. Proposed Architecture

### 3.1 Two-Process Model

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SHARED HOST MACHINE                            │
│                                                                        │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐   │
│  │   halbert-host.service      │    │   halbert-home.service      │   │
│  │   (systemd unit)            │    │   (systemd unit)            │   │
│  │                             │    │                             │   │
│  │  Env:                       │    │  Env:                       │   │
│  │   HALBERT_PERSONA_ID=halbert│    │   HALBERT_PERSONA_ID=home   │   │
│  │   HALBERT_SCENE_CONTEXT=    │    │   HALBERT_SCENE_CONTEXT=    │   │
│  │     "Linux sysadmin"        │    │     "smart home automation" │   │
│  │   HALBERT_DATA_DIR=         │    │   HALBERT_DATA_DIR=         │   │
│  │     ~/.local/share/halbert  │    │     ~/.local/share/halbert- │   │
│  │                             │    │       home                  │   │
│  │   HALBERT_CONFIG_DIR=       │    │   HALBERT_CONFIG_DIR=       │   │
│  │     ~/.config/halbert       │    │     ~/.config/halbert-home  │   │
│  │   SOURCEPREP_PROJECT_ID=    │    │   SOURCEPREP_PROJECT_ID=    │   │
│  │     halbert-host            │    │     ha-config               │   │
│  │   HALBERT_PORT=8000         │    │   HALBERT_PORT=8001         │   │
│  │   WYOMING_PORT=10400        │    │   WYOMING_PORT=10401        │   │
│  │                             │    │                             │   │
│  │  Port 8000 (dashboard API)  │    │  Port 8001 (dashboard API)  │   │
│  │  Port 10400 (Wyoming voice) │    │  Port 10401 (Wyoming voice) │   │
│  └─────────────────────────────┘    └─────────────────────────────┘   │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   SourcePrep Daemon (shared)                    │   │
│  │   Projects: halbert-host, ha-config                             │   │
│  │   Port: 8400                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   Ollama (shared)                               │   │
│  │   Port: 11434                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 What's Shared vs Isolated

| Component | Shared? | Notes |
|-----------|---------|-------|
| Codebase | Shared | Same pip install, same Python venv |
| SourcePrep daemon | Shared | One daemon, multiple projects |
| Ollama | Shared | One Ollama instance, multiple models |
| Dashboard API port | **Isolated** | 8000 (host) / 8001 (home) |
| Wyoming voice port | **Isolated** | 10400 (host) / 10401 (home) |
| Data directory | **Isolated** | Separate `ha_config.json`, `frigate_config.json`, memory DBs |
| Config directory | **Isolated** | Separate `being.yml` personality files |
| SourcePrep project | **Isolated** | `halbert-host` vs `ha-config` |
| Persona cognition | **Isolated** | Separate `PersonaCognition` instances, separate memory stores |
| HA WebSocket event stream | **Isolated** | Only the home instance connects to HA |
| Frigate MQTT | **Isolated** | Only the home instance subscribes to Frigate |
| Frontend | **Isolated** | Each instance serves its own React build |

### 3.3 Frontend Routing

Each instance serves its own frontend on its own port. The frontend is the same codebase but configured at build time (or runtime via env injection) with the correct API base URL.

**Option A (build-time):** Vite env var `VITE_API_BASE_URL` baked into the build. Requires separate builds per instance.

**Option B (runtime):** The frontend reads `window.location.origin` as the API base. Since each instance serves both the API and the frontend on the same port, this works with zero configuration. **This is the recommended approach** and appears to already be how the frontend works (it uses relative `/api/` paths).

### 3.4 HACS Integration

The HACS custom integration (`custom_components/halbert/`) connects to a single Wyoming agent. For multi-instance, the HA conversation entity should connect to the **home** instance's Wyoming port (10401), not the host instance's. This is configured in the HA integration's config flow (host:port field).

---

## 4. Implementation Plan

### 4.1 Unify Data Dir Env Var (Bug Fix)

**Problem:** `HALBERT_DATA_DIR` (all caps, used by HA/Frigate) and `Halbert_DATA_DIR` (mixed case, used by `utils/paths.py`) are two different env vars. Both must be set for full isolation, which is error-prone.

**Fix:** Make `utils/paths.py` check `HALBERT_DATA_DIR` first, then fall back to `Halbert_DATA_DIR` for backward compatibility. Same for config dir.

**Files:**
- `halbert_core/halbert_core/utils/paths.py` — add `HALBERT_DATA_DIR` as primary, `Halbert_DATA_DIR` as fallback
- `halbert_core/halbert_core/integrations/home_assistant/ha_config.py` — already uses `HALBERT_DATA_DIR` (no change)
- `halbert_core/halbert_core/integrations/frigate/frigate_config.py` — already uses `HALBERT_DATA_DIR` (no change)

**Estimated lines:** ~10 lines changed in `paths.py`.

### 4.2 Dashboard Port from Env Var

**Problem:** The dashboard currently hardcodes the uvicorn port. For multi-instance, each process needs its own port.

**Fix:** Read `HALBERT_PORT` env var in the uvicorn launch (or in `app.py`'s `__main__` block).

**Files:**
- `halbert_core/halbert_core/dashboard/app.py` — add `if __name__ == "__main__"` block reading `HALBERT_PORT` (default 8000)

**Estimated lines:** ~5 lines.

### 4.3 Systemd Unit Files

Create template systemd unit files for both instances:

**Files:**
- `deploy/halbert-host.service` — host sysadmin instance
- `deploy/halbert-home.service` — home automation instance
- `deploy/README.md` — deployment instructions

**Example unit (host):**
```ini
[Unit]
Description=Halbert Host Sysadmin
After=network.target

[Service]
Type=simple
User=halbert
Environment=HALBERT_PERSONA_ID=halbert
Environment=HALBERT_SCENE_CONTEXT=Linux system administration
Environment=HALBERT_DATA_DIR=/var/lib/halbert
Environment=HALBERT_CONFIG_DIR=/etc/halbert
Environment=SOURCEPREP_PROJECT_ID=halbert-host
Environment=HALBERT_PORT=8000
Environment=WYOMING_PORT=10400
ExecStart=/opt/halbert/bin/uvicorn halbert_core.dashboard.app:app --host 0.0.0.0 --port ${HALBERT_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Example unit (home):**
```ini
[Unit]
Description=Halbert Home Automation
After=network.target homeassistant.service

[Service]
Type=simple
User=halbert
Environment=HALBERT_PERSONA_ID=home
Environment=HALBERT_SCENE_CONTEXT=smart home automation
Environment=HALBERT_DATA_DIR=/var/lib/halbert-home
Environment=HALBERT_CONFIG_DIR=/etc/halbert-home
Environment=SOURCEPREP_PROJECT_ID=ha-config
Environment=HALBERT_PORT=8001
Environment=WYOMING_PORT=10401
ExecStart=/opt/halbert/bin/uvicorn halbert_core.dashboard.app:app --host 0.0.0.0 --port ${HALBERT_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### 4.4 Instance-Aware Startup Logging

**Problem:** When two instances start, the logs are indistinguishable. Each instance should log its persona_id and port on startup.

**Fix:** Add a startup log line in `app.py` that includes the persona_id, scene_context, data_dir, and port.

**Files:**
- `halbert_core/halbert_core/dashboard/app.py` — add identity logging at the top of `startup_event`

**Estimated lines:** ~5 lines.

### 4.5 Cross-Instance Awareness (Optional, Future)

If the host instance needs to know about the home instance (e.g., "is the home automation running?"), add a lightweight health check endpoint that one instance can call against the other.

**This is NOT part of Phase 7 MVP.** It's a future enhancement. The two instances are independent and don't communicate with each other.

### 4.6 Frontend Instance Badge

**Problem:** When running two instances, the user needs to know which one they're looking at.

**Fix:** Add a small badge in the frontend header showing the persona_id. This can be injected via an API endpoint (`GET /api/instance/info`) that returns the persona_id, scene_context, and port.

**Files:**
- `halbert_core/halbert_core/dashboard/routes/` — add instance info endpoint
- `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` — add badge

**Estimated lines:** ~20 lines backend, ~15 lines frontend.

---

## 5. What Does NOT Need to Change

These components are already env-var-driven and require no changes:

| Component | Why It Works |
|-----------|-------------|
| `cognition_wiring.py` | Already reads `HALBERT_PERSONA_ID` and `HALBERT_SCENE_CONTEXT` |
| `ha_config.py` | Already reads `HALBERT_DATA_DIR` |
| `frigate_config.py` | Already reads `HALBERT_DATA_DIR` |
| `sourceprep_client.py` | Already reads `SOURCEPREP_PROJECT_ID` and `SOURCEPREP_URL` |
| `wyoming_agent.py` | Already reads `WYOMING_HOST` and `WYOMING_PORT` |
| `being_config.py` | Loads from `get_config_dir()` which respects `Halbert_CONFIG_DIR` |
| `ha_config_bridge.py` | Reads `HA_SOURCEPREP_PROJECT_ID` and `SOURCEPREP_URL` |
| `ha_governance.py` | Stateless, no instance-specific config |
| `ha_event_stream.py` | Uses `ha_config.py` which is already isolated |
| `ha_event_mapper.py` | Uses `cognition_wiring.py` singletons which are already isolated |

---

## 6. Risk Analysis

### 6.1 Singleton Collision (Low Risk)

Both instances run in separate processes, so Python module-level singletons (`_cognition`, `_agent_instance`, etc.) are naturally isolated. There is no shared memory space.

### 6.2 Port Conflict (Medium Risk)

If both instances try to bind the same port, one will fail. This is mitigated by:
- Different `HALBERT_PORT` values in systemd units (8000 vs 8001)
- Different `WYOMING_PORT` values (10400 vs 10401)
- Startup logging that shows which port each instance is using

### 6.3 SourcePrep Project Confusion (Low Risk)

Each instance points at a different `SOURCEPREP_PROJECT_ID`. If the user misconfigures, both instances could search the same project. This is a config error, not a code bug, and the startup logging will make it visible.

### 6.4 Memory Store Collision (Medium Risk)

`PersonaMemoryStore` uses a SQLite database. If both instances use the same `HALBERT_DATA_DIR`, they'll share the same memory DB, which could cause persona confusion. This is mitigated by different `HALBERT_DATA_DIR` values in the systemd units.

**Additional safeguard:** The memory store should include `persona_id` in its database filename (e.g., `memory_{persona_id}.db`) so even if data dirs overlap, the DBs are separate. This is a ~2 line change in `cognition_wiring.py`.

### 6.5 File Watcher Conflict (Low Risk)

The config watcher (`config.watcher`) monitors host config files. Only the host instance should run it. The home instance should skip it. Currently, the watcher only starts on Linux and if a config-registry.yml is found, so the home instance naturally won't start it unless it has its own config registry.

---

## 7. Testing Plan

### 7.1 Unit Tests

- Test that `HALBERT_DATA_DIR` env var correctly isolates HA config, Frigate config, and being config paths
- Test that `HALBERT_PERSONA_ID` produces different cognition instances
- Test that `SOURCEPREP_PROJECT_ID` produces different SourcePrep clients
- Test that `WYOMING_PORT` produces different Wyoming configs
- Test that `HALBERT_PORT` is read correctly

### 7.2 Integration Test (Manual)

1. Start host instance with default env vars
2. Start home instance with home env vars
3. Verify each instance has its own:
   - Dashboard (different ports)
   - HA config (only home has HA configured)
   - Being config (different personality)
   - SourcePrep project (different project IDs)
4. Send a message to each instance and verify different personas respond

---

## 8. Implementation Order

| Step | Description | Lines Changed | Risk |
|------|-------------|---------------|------|
| 1 | Unify `HALBERT_DATA_DIR` env var in `paths.py` | ~10 | Low |
| 2 | Add `HALBERT_PORT` env var to uvicorn launch | ~5 | Low |
| 3 | Add persona_id to memory DB filename | ~2 | Low |
| 4 | Add instance identity startup logging | ~5 | Low |
| 5 | Add `GET /api/instance/info` endpoint | ~15 | Low |
| 6 | Add frontend instance badge | ~15 | Low |
| 7 | Create systemd unit files | ~60 (new files) | None |
| 8 | Create deployment README | ~80 (new file) | None |
| 9 | Unit tests | ~100 (new file) | None |

**Total estimated:** ~200 lines of code changes + ~140 lines of new config/docs files.

---

## 9. Open Questions for Feedback

1. **Env var naming:** Should we standardize on `HALBERT_*` (all caps) or `Halbert_*` (mixed case)? The codebase currently uses both. Recommendation: standardize on `HALBERT_*` with backward-compatible fallback.

2. **Frontend badge:** Is showing the persona_id in the header sufficient for distinguishing instances, or should we use a color-coded badge (e.g., blue for host, green for home)?

3. **Memory DB isolation:** Should the memory DB always include `persona_id` in the filename (defensive), or should we rely solely on `HALBERT_DATA_DIR` separation (simpler)?

4. **Cross-instance communication:** Do we need the host instance to be aware of the home instance? E.g., "Halbert, is the home automation working?" — the host would need to call the home instance's health endpoint. This is explicitly out of scope for Phase 7 but worth considering for Phase 8.

5. **Single-instance fallback:** Should we support a "combined" mode where one process runs both personas? This would require an `InstanceManager` and is explicitly rejected in the strategy doc, but worth confirming.

6. **Ollama model selection:** Should the home instance default to a smaller model (e.g., Qwen 3.5 4B) while the host uses a larger one? This is a `HALBERT_MODEL` env var that already exists — just a deployment config question.

7. **Log file separation:** Should each instance log to a separate file? Currently `Halbert_LOG_DIR` env var exists for this. The systemd units should set it.

---

## 10. Files to Read for Context

- `halbert_core/halbert_core/integrations/cognition_wiring.py:32-50` — persona_id and scene_context env vars
- `halbert_core/halbert_core/utils/paths.py:47-52` — data_dir and config_dir env vars
- `halbert_core/halbert_core/integrations/home_assistant/ha_config.py:55-61` — HA config path
- `halbert_core/halbert_core/integrations/frigate/frigate_config.py:92-98` — Frigate config path
- `halbert_core/halbert_core/integrations/sourceprep_client.py:38-52` — SourcePrep project ID resolution
- `halbert_core/halbert_core/integrations/wyoming_agent.py:38-55` — Wyoming config from env
- `halbert_core/halbert_core/config/being_config.py:171-172` — Being config path
- `halbert_core/halbert_core/dashboard/app.py:626-646` — Wyoming startup (delayed thread)
- `.handoff/HOME-AUTOMATION-IMPLEMENTATION-STRATEGY.md:58-77` — Phase roadmap
