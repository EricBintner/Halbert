# Halbert Multi-Instance — Architectural & UI Design Review Feedback

**Date:** 2026-08-29  
**Review Target:** `/Volumes/4TB-BAD/Halbert/.handoff/HALBERT-MULTI-INSTANCE-DESIGN.md`  
**Phase:** Phase 7 of Home Automation Implementation Strategy  
**Focus:** UI navigation disambiguation, multi-instance switching, single vs. multi-node personas, onboarding flow, and resolution of Section 9 Open Questions.

---

## 1. Executive Summary & Core Architectural Verdict

The two-process architecture proposed in `HALBERT-MULTI-INSTANCE-DESIGN.md` (no `InstanceManager`, no in-process multiplexing, isolated daemons on separate ports configured via environment variables) is **100% the correct engineering decision**. It prevents Python GIL contention, module-level singleton collisions (`_cognition`, `_app_seam`), and database lock contention in SQLite.

However, the design document’s frontend strategy (§4.6: "Frontend Instance Badge") was **insufficient for real-world user workflows**. Simply displaying a persona badge in the header when a user navigates to port 8000 vs 8001 leaves the navigation ambiguous:
1. It left a static `Home` tab in the host sysadmin’s sidebar (`Overview > Home`), creating a category error on desktop workstations.
2. It forced users to manually manage browser tabs and ports rather than having a seamless, unified application experience.
3. It did not define how a desktop workstation Halbert interacts with or views a remote home server Halbert.

This document formally records the complete architectural, UI/UX, and operational feedback to resolve these gaps.

---

## 2. The Core Problem: Embodiment & Navigation Conflation

Halbert’s core philosophical thesis is **somatic self-awareness**: Halbert is not a floating chat bot; Halbert is *the machine it runs on*.

* **Desktop / Host Halbert:** Monitors local CPU/GPU/Metal, battery, open terminals, watched configs (`~/.zshrc`, `/etc/hosts`), local packages, apps, and dev workflows.
* **Home Automation Halbert:** Monitors 24/7 telemetry, physical rooms/areas, Zigbee/Z-Wave meshes, Home Assistant states, Frigate cameras, and Wyoming voice satellites.

When both instances exist (either co-located on one machine across ports 8000/8001 or split across a laptop and a home server), having a static `Home` tab in the local desktop sidebar conflates their bodies and confuses the user.

---

## 3. The UI Solution: Persona-Aware Sidebar + Top-Bar Instance Switcher

### 3.1 Dynamic Sidebar Filtering in `Layout.tsx`

The navigation rail in `Layout.tsx` dynamically adapts based on the active instance's identity:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [● H]  [ 🖥️ Studio Mac (Host) ▾ ]    [ (Engaged: Studio Mac) | (Dashboard) ]         [ ⚡ Index 100% ] [ ⚙️ ]   │
├─────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────┤
│ OVERVIEW                        │                                                                               │
│   Dashboard (Host Vitals)       │   Studio Mac — Apple M2 Max • 64GB Unified Memory • macOS Sonoma              │
│ SYSTEM                          │                                                                               │
│   Services                      │   Active Terminal Sessions: 2                                                 │
│   Storage                       │   Watched Configs: /etc/hosts, ~/.zshrc                                       │
│   Backups                       │   GPU / Metal Inference: Active                                               │
│   Apps                          │                                                                               │
│   Security                      │                                                                               │
│ DEVELOPMENT                     │                                                                               │
│   Containers                    │                                                                               │
│   GPU / ML Engine               │                                                                               │
│   Development                   │                                                                               │
│ UTILITY                         │                                                                               │
│   Approvals                     │                                                                               │
│   Settings                      │                                                                               │
└─────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────┘
```

* **When viewing Host Halbert (`persona_id="halbert"`):** The `Home` tab is completely hidden. Sidebar focuses strictly on host operations.
* **When viewing Home Halbert (`persona_id="home"`):** The `Home` tab is prominently rendered under `Overview`. Development/GPU tabs are hidden if unconfigured on the server.

### 3.2 The Top-Bar Instance Switcher

Upgrading §4.6 of the design document: rather than a passive badge, Halbert introduces an **Instance Switcher Dropdown** in the top shell bar.

Clicking `[ 🖥️ Studio Mac (Host) ▾ ]` opens:
```
┌───────────────────────────────────────────────────┐
│ SWITCH HALBERT INSTANCE                           │
├───────────────────────────────────────────────────┤
│ ● 🖥️ Studio Mac (Host)                             │
│   Local Sysadmin • Port 8000 • macOS              │
├───────────────────────────────────────────────────┤
│ ○ 🏠 Home Automation                               │
│   Smart Home Hub • Port 8001 (or 192.168.1.150)  │
│   HA Connected • 42 Entities Active               │
├───────────────────────────────────────────────────┤
│ + Pair / Connect Another Instance...              │
└───────────────────────────────────────────────────┘
```

Selecting `[ 🏠 Home Automation ]` updates the frontend `apiBase` to target port 8001 (or the remote LAN/Tailscale host). The entire UI—both **Browsing Mode** (sidebar + pages) and **Engaged Mode** (`HostShell` chat + vitals)—seamlessly switches to the home instance without requiring a page reload or separate browser window.

---

## 4. Onboarding Flow: Intent & Role Discovery

During first run (or in Settings > Instance Role), Halbert explicitly asks the user:

> **"What role should this Halbert play on this machine?"**
>
> 1. **Personal Computer / Workstation Assistant (Default on Desktops/Laptops)**  
>    *Monitors local performance, terminal sessions, local development, and system services.*  
>    *(Configures `HALBERT_PERSONA_ID=halbert`, port 8000, disables local Home tab).*
>
> 2. **Dedicated Home Automation Hub (Default on Home Servers / Headless)**  
>    *Acts as the ambient cognitive layer for Home Assistant, Frigate, sensors, and room voice satellites.*  
>    *(Configures `HALBERT_PERSONA_ID=home`, port 8001/8000, enables Home tab and Wyoming TCP server).*
>
> 3. **All-in-One (Single Always-On Machine running both roles)**  
>    *This machine serves as my daily driver AND my 24/7 Home Assistant server.*  
>    *(Enables all tabs including Home).*

If Option 1 (Workstation) is selected:
> *"Do you have a Home Automation Halbert running on another port or machine?"*  
> If yes, the user provides the local/network endpoint (`http://localhost:8001` or `http://home-server.local:8000`), immediately populating the Top-Bar Switcher.

---

## 5. Resolution of the 7 Open Questions from `HALBERT-MULTI-INSTANCE-DESIGN.md` §9

| # | Question from Design Doc §9 | Formal Resolution |
|---|-----------------------------|-------------------|
| **1** | **Env Var Naming:** `HALBERT_*` vs `Halbert_*` | **Standardize on `HALBERT_*` (all-caps POSIX standard).** Update `utils/paths.py` to check `HALBERT_DATA_DIR` and `HALBERT_CONFIG_DIR` first, falling back to `Halbert_*` for backward compatibility. |
| **2** | **Frontend Badge vs Switcher** | **Upgrade badge to a top-bar Instance Switcher Dropdown.** Use color-coded badges: Charcoal/Steel for `host`, Vermilion/Amber for `home`. |
| **3** | **Memory DB Isolation** | **Defensive naming.** Use `memory_{persona_id}.db` inside `HALBERT_DATA_DIR`. Even if paths accidentally collide, SQLite databases remain strictly isolated. |
| **4** | **Cross-Instance Awareness** | **Phase 7 (MVP):** Isolated processes + UI switcher.<br>**Phase 8 (Future):** Add lightweight peer delegation where Host Halbert can forward smart-home queries ("turn off office lights") to Home Halbert (`/api/home/delegate`). |
| **5** | **Single-Process Combined Mode** | **Firmly Rejected.** Maintain the two-process architecture. It guarantees zero singleton pollution and scales identically to multi-machine setups. |
| **6** | **Ollama Model Selection** | **Host Instance:** Defaults to larger reasoning model (e.g. Qwen 2.5 14B / Cloud tier) for complex sysadmin/dev tasks.<br>**Home Instance:** Defaults to lightweight low-latency model (e.g. Qwen 2.5 3B / Llama 3.2 3B) optimized for real-time Wyoming voice and high-frequency event processing. |
| **7** | **Log File Separation** | Standardize on `HALBERT_LOG_DIR`. Set separate log paths in systemd units (`/var/log/halbert` vs `/var/log/halbert-home` or `~/.local/state/halbert` vs `~/.local/state/halbert-home`). |

---

## 6. Implementation Checklist & File Reference

### Backend (`halbert_core`)
- [ ] `halbert_core/halbert_core/utils/paths.py`: Unify `HALBERT_DATA_DIR`, `HALBERT_CONFIG_DIR`, `HALBERT_LOG_DIR`.
- [ ] `halbert_core/halbert_core/integrations/cognition_wiring.py`: Use `memory_{persona_id}.db` for SQLite store.
- [ ] `halbert_core/halbert_core/dashboard/app.py`: Read `HALBERT_PORT` from env var on startup; log instance metadata.
- [ ] `halbert_core/halbert_core/dashboard/routes/instance.py`: Add `GET /api/instance/info` returning `{ persona_id, scene_context, port, role, features: { home, gpu } }`.

### Frontend (`dashboard/frontend`)
- [ ] `src/lib/apiBase.ts`: Add dynamic instance endpoint switching.
- [ ] `src/components/Layout.tsx`: Filter `navSections` based on `instanceInfo.features.home`.
- [ ] `src/components/shell/InstanceSwitch.tsx`: Add top-bar instance dropdown selector with status pills.
- [ ] `src/components/Onboarding.tsx`: Add machine role selection step.

### Deployment & Config
- [ ] `deploy/halbert-host.service`: Systemd unit for host sysadmin instance (port 8000, Wyoming 10400).
- [ ] `deploy/halbert-home.service`: Systemd unit for home automation instance (port 8001, Wyoming 10401).
