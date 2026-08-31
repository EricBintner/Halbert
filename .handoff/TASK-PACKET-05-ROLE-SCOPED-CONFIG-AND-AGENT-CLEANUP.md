# Task Packet 05: Agent Context Plumbing & Role-Scoped Config Harvesting

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U4)  
**Domain:** Role-Scoped File Harvesting and SourcePrep Scopes  
**Target Date:** 2026-08-29  
**Status (verified 2026-08-30):** **Task 5.1 is OBSOLETE — do not implement.** The founder decision on 2026-08-30 was to *remove* the `context` field from `SendMessageRequest` (done; see `MASTER-TODO.md` § 3). This packet now covers **Task 5.2 (role harvester) and Task 5.3 (scoped registration) only**. `config/role_harvester.py` does not exist yet; `test_role_harvester.py` must be created.  
**Governing Documents:**
- [`.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md)
- [`.handoff/PLAN-ROLE-SCOPED-CONFIG-HARVESTING-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/PLAN-ROLE-SCOPED-CONFIG-HARVESTING-2026-08-26.md)
- [`.handoff/TODO-ROLE-SCOPED-CONFIG-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TODO-ROLE-SCOPED-CONFIG-2026-08-27.md)

---

## 1. Executive Summary & Objective

This packet addresses two core backend items:
1. **Agent Request Context Plumbing:** Resolving the dangling `context: Optional[Dict[str, Any]]` field on `SendMessageRequest` in [`dashboard/routes/agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/agent.py) so external callers can seed structured context into the agent's turn.
2. **Role-Scoped Configuration Harvesting:** Implementing the design specified in `ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`, enabling Halbert to automatically categorize host configuration files into functional roles (e.g. `web_server`, `database`, `media_center`, `container_host`) and index them into role-specific SourcePrep retrieval scopes.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 5.1: ~~Wire `SendMessageRequest.context` into `ConversationContext`~~ — OBSOLETE (2026-08-30)
> **Erratum:** the `context` field was **removed** from `SendMessageRequest` by founder decision on 2026-08-30 (checked off in `MASTER-TODO.md` § 3). This task contradicts that decision and must not be implemented.
- **File:** [`halbert_core/halbert_core/dashboard/routes/agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/agent.py)
  1. In `send_message()` and `process()` methods:
     - Check if `request.context` is populated.
     - Thread `request.context` into `AgentRunner.step()` / `ConversationContext.observations` as a dedicated observation block (`ObservationType.CLIENT_CONTEXT`).
  2. In [`halbert_core/halbert_core/context/assembler.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/context/assembler.py):
     - Format seeded client context into the system prompt's structured working memory section.

### Task 5.2: Implement Role-Scoped Config Harvester
- **File:** `halbert_core/halbert_core/config/role_harvester.py`
  1. Define `ServerRole` enumeration and signature rules:
     - `WEB_SERVER`: Nginx, Apache, Caddy configs (`/etc/nginx`, `/etc/caddy`, etc.)
     - `DATABASE`: PostgreSQL, MySQL, Redis, SQLite configs (`/etc/postgresql`, `/etc/mysql`, `/etc/redis`)
     - `CONTAINER_HOST`: Docker daemon, Compose files, Podman configs (`/etc/docker`, `~/.docker`)
     - `HOME_AUTOMATOR`: Home Assistant, Zigbee2MQTT, Mosquitto configs
     - `MEDIA_CENTER`: Plex, Jellyfin, Sonarr, Radarr configs
  2. Implement `RoleConfigHarvester.scan_host(root_path="/") -> Dict[ServerRole, List[Path]]`.
  3. Write discovered manifests to `~/.local/share/halbert/harvested_roles/<role>.json`.

### Task 5.3: Register Role-Scoped Projects in SourcePrep
- **File:** [`halbert_core/halbert_core/integrations/host_config_registration.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/host_config_registration.py)
  1. Extend registration logic to register harvested role file manifests under dynamic scopes: `scope: "role_web"`, `scope: "role_database"`, etc.
  2. Wire the harvester into the discovery background loop in [`dashboard/app.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/app.py).

---

## 3. Verification & Test Plan

1. **Context Plumbing Unit Tests:**
   ```bash
   pytest halbert_core/tests/test_agent_context_plumbing.py -v
   ```
2. **Role Harvester Unit Tests:**
   ```bash
   pytest halbert_core/tests/test_role_harvester.py -v
   ```
3. **End-to-End Discovery Smoke Test:**
   ```bash
   python scripts/boot_smoke.py
   ```
