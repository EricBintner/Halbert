# Handoff: Onboarding Role Inference — Scan-First, Suggest, Confirm

**To:** External design reviewer / Implementation AI
**From:** Eric (founder) / GLM-5.2 session
**Date:** 2026-09-07
**Status:** Design proposed by founder direction. Open questions for external review before implementation.

---

## 1. The problem in one sentence

The onboarding wizard asks the user to pick a "user type" from four cards (Casual User, IT Admin, Developer, AI Professional) — but the answer is stored in three places and never read back by anything, and the categories themselves are the wrong question.

---

## 2. What exists today (the code, plainly)

### 2.1 The four cards

The onboarding component (`halbert_core/halbert_core/dashboard/frontend/src/components/Onboarding.tsx`, lines 46-71) defines four single-select user types:

```
Casual User      — "Home user, general computing"
IT Admin         — "System administration, servers"
Developer        — "Software development, DevOps"
AI Professional  — "Machine learning, data science"
```

The user picks exactly one. There is no multi-select. The selection is sent to the backend as `user_type: string` on the `/api/settings/onboarding/complete` POST.

### 2.2 Where the answer goes

The backend (`halbert_core/halbert_core/dashboard/routes/settings.py`, lines 1056-1127) stores `user_type` in three places:

1. **`system_profile.json`** → `profile["user_settings"]["user_type"]` (line 1078)
2. **`onboarding_complete` marker file** → third line of the file (line 1090)
3. **`preferences.yml`** → `prefs["user_type"]` (line 1104)

### 2.3 Where the answer is read back

**Nowhere.** A grep across the entire codebase for `user_type` returns only the write sites listed above. No backend route, no frontend component, no chat prompt builder, no scanner, no MCP server, and no config reader ever looks at `user_type` again. The field is collected, stored in three places, and completely ignored.

The only fields from `preferences.yml` that are read back are `ai_name` and `user_name` — both used by the identity resolver (`halbert_core/identity.py`) and the prompt builder.

### 2.4 The flow today

```
1. Welcome screen (static intro, no scan yet)
2. Configure screen:
   - "What's your name?" → adminName
   - "What should I call this computer?" → computerName (prefilled with hostname)
   - "How do you primarily use this computer?" → single-select from 4 cards
3. User clicks "Scan System & Complete Setup"
4. POST /api/settings/onboarding/complete → runs full scan_all() + saves everything
5. Scan results screen (shows profile summary)
6. Complete screen → reload
```

The scan runs *after* the user has already picked their role. The scan results are not used to inform the role selection.

---

## 3. Why the current categories are wrong

### 3.1 They ask about the person, not the machine

Halbert manages a *machine*. The scan already discovers what the machine has (GPUs, dev tools, running services, network topology, RAM, CPU, display). What the scan *cannot* infer is **what role this computer plays in the user's life** — and that's the thing that should drive defaults.

Asking "are you a developer?" tells you about the user's identity. Asking "is this a workstation or a server?" tells you how to configure the dashboard.

### 3.2 Developer and AI Professional are redundant with the scan

The scan already detects:
- GPUs (Apple Silicon, NVIDIA, AMD) — `hardware.gpu`
- Dev tools (git, node, python, rust, go, java, docker, cargo, cmake) — `development.tools` and `development.languages`
- Editors (vscode, vim, emacs, etc.) — `development.editors`
- AI accelerators — separate scanner at `discovery/scanners/ai_accelerator.py`

Asking someone "are you an AI professional?" and then *also* scanning their machine for GPUs is redundant. A developer and a non-developer on the same workstation get the same Halbert. The machine's *role* is what matters, not the user's job title.

### 3.3 IT Admin is the wrong framing

"IT Admin" is a job title, not a machine role. The real question is whether this computer is a server (headless, runs services for other machines) or a workstation (someone sits at it). An IT admin might use a workstation to manage servers — the workstation itself isn't a server.

### 3.4 "Casual User" leads nowhere

The "Home user, general computing" category is a dead end. If someone is a home user, the natural next question is "does this machine run your home automation?" — but the current design never asks. "Home" should lead into home automation, not into a generic bucket.

### 3.5 People are multiple things

A user might be a developer who also runs home automation and trains ML models. Single-select forces them into one box. The current design has no way to express "this machine is both my daily workstation and my home automation hub."

---

## 4. The proposed redesign

### 4.1 The new question: "What is this computer for?"

Replace the four single-select user-type cards with three multi-select role toggles. The question changes from "what kind of user are you?" to "what role does this computer play?"

**Workstation** — A computer someone sits at and uses day-to-day. Your Mac, your Linux desktop, your laptop. Full interactive UI: chat, voice, terminal, proactive suggestions. This is the default and the most common answer.

**Server** — A real server: x86, rack-mounted or a beefy headless box, multiple drives, runs services for *other* machines (VMs, containers, databases, web servers). Not a Raspberry Pi — a Pi running services for the house is a Home Automation Hub, not a server. A server is something you'd find in a closet with a UPS and a fan. Halbert focuses on service health, uptime, resource monitoring, and alerting rather than interactive features.

**Home Automation Hub** — This computer runs the house. It might be a Pi, a Mac mini in a closet, or a dedicated NUC. It runs Home Assistant, HomeKit, or similar. Halbert connects to it, discovers entities (lights, sensors, locks, thermostats), and can trigger automations. This is where the "Home" path leads — not into a dead-end "casual user" bucket, but into actual home automation integration.

### 4.2 Multi-select

A machine can be more than one thing:
- Your daily Mac Studio = **Workstation** (you sit at it) + **Home Automation Hub** (it also runs HA in a container)
- A Mac mini in the closet = **Server** + **Home Automation Hub**
- A rack server = **Server** only
- Your laptop = **Workstation** only

The UI uses toggle chips, not radio cards. The user can select any combination.

### 4.3 Scan-first: suggest a role before the user picks

The key insight from the founder: **the scan should run before the user picks a role**, so Halbert can suggest a role based on what it found. The user still has the final say — they can adjust the suggestion — but the default is informed by real data, not a blind guess.

### 4.4 The new flow

```
1. Welcome screen (same as today — static intro)
2. User clicks "Get Started"
3. Quick probe runs (2-3 seconds):
   - Hardware: CPU, RAM, GPU, form factor
   - Desktop: is there a GUI session / display server?
   - Services: what's running? (web servers, databases, HA, MQTT, etc.)
   - Containers: Docker/Podman present? How many?
   - Development: dev tools installed?
   - Boot: uptime (how long has it been up?)
   This is a subset of scan_all() — skip packages, security, scheduled tasks,
   users, virtualization, kernel details. Just the signals needed for inference.
4. Inference runs on the probe results → produces a suggested role (or roles)
   with a score and a human-readable reason for each.
5. Configure screen:
   - "What's your name?" → adminName (same as today)
   - "What should I call this computer?" → computerName (same as today)
   - "What is this computer for?" → multi-select toggles, with the suggested
     role(s) pre-checked. Below the toggles, a line of reasoning:
     "Based on what I found: this machine has a display, 64 GB of RAM,
      and development tools installed. It looks like a Workstation."
   - User can adjust. They can pick more than one.
6. User clicks "Scan System & Complete Setup"
7. POST /api/settings/onboarding/complete → runs the FULL scan_all()
   (with the role context) + saves everything
8. Scan results screen (same as today)
9. Complete screen → reload
```

The quick probe is a new intermediate step. It is not the full scan — it's a fast subset that takes 2-3 seconds and only collects the signals needed for role inference. The full scan still runs at the end (step 7), same as today.

---

## 5. The inference logic

### 5.1 What the scan already collects

The `SystemProfiler.scan_all()` method (`halbert_core/halbert_core/discovery/scanners/system_profile.py`, line 71) collects 15 categories. The ones relevant to role inference:

| Category | Key fields | Relevance |
|---|---|---|
| `hardware` | `cpu.model_name`, `cpu.cpu(s)`, `memory.total_gb`, `gpu[]`, `motherboard.model`, `usb_devices[]` | Form factor, compute power, GPU presence, USB devices (Zigbee sticks) |
| `desktop` | `display_server`, `desktop_environment`, `session_type` | Is there a GUI? (`gui`/`x11`/`wayland`/`quartz-compositor` vs absent/headless) |
| `services` | `running_count`, `notable_services[]` (names + state) | What's running? (web servers, databases, HA, MQTT, SSH, file sharing) |
| `containers` | `docker`, `podman`, `container_count` | Docker present? How many containers? |
| `development` | `languages{}`, `tools{}`, `editors[]` | Dev tools installed? |
| `boot` | `boot_time` (uptime string) | How long has it been up? |
| `os` | `type` (macos/linux), `distro` | Platform context |

Notable services currently tracked (from `_scan_services_summary`, line 752):
- Containers: docker, podman, containerd
- Remote access: sshd, ssh
- Web servers: nginx, apache2, httpd, caddy
- Databases: postgresql, mysql, mariadb, mongodb, redis
- File sharing: smbd, nmbd, nfs-server
- Printing: cups
- Security: fail2ban, ufw, firewalld
- Scheduling: cron, anacron
- VPN: tailscaled
- Backup/sync: syncthing, restic, borg

**Gap:** Home Assistant, MQTT, and Zigbee/Z-Wave are NOT in the notable services list. This needs to be added for the inference to detect Home Automation Hub. See Open Question Q3.

### 5.2 The scoring function

A scoring function, not a hard classifier — because of ambiguous cases (a 32GB Mac mini, a NAS on an old Intel CPU, etc.). Each role gets a score; the highest score(s) are suggested.

**Workstation score** (high when someone sits at this machine):
- `+3` has a GUI session / display server (`desktop.session_type == "gui"` or `desktop.display_server` is present)
- `+2` has editors installed (vscode, vim, emacs, etc. — from `development.editors`)
- `+1` has dev tools (git, node, python, etc. — from `development.tools`)
- `+1` RAM in 8-64 GB range
- `-2` no desktop session at all (headless)
- `-1` uptime > 30 days (workstations reboot; servers and hubs don't)

**Server score** (high when this machine serves others):
- `+3` no desktop session (headless — `desktop.session_type` is None/absent)
- `+2` running web servers / databases / file sharing services (from `services.notable_services`: nginx, apache, postgresql, mysql, smbd, nfs, etc.)
- `+2` Docker with multiple containers (`containers.docker.installed` and `containers.docker.container_count > 3`)
- `+1` SSH enabled, no interactive users
- `+1` RAM > 64 GB or CPU > 16 cores
- `+1` long uptime (> 30 days)
- `-2` has a GUI session (someone sits at it — it's a workstation that also runs services)
- `-1` it's a Pi / ARM with low RAM (that's a hub, not a server — see below)

**Home Automation Hub score** (high when this machine runs the house):
- `+3` Home Assistant / HomeKit / MQTT service detected (from `services.notable_services` — **requires adding HA/MQTT to the notable list**, see Q3)
- `+2` Zigbee/Z-Wave USB device detected (from `hardware.usb_devices` — **requires adding Zigbee/Z-Wave vendor IDs to the USB scanner**, see Q3)
- `+2` ARM CPU + low RAM (1-8 GB) → likely a Pi
- `+1` small form factor (Mac mini, NUC, Pi — inferred from `hardware.motherboard.model` or `os.distro`)
- `+1` long uptime + few interactive users
- `-1` has many server-class services (web server + DB + file sharing → it's a server, not a hub)
- `-1` high core count / high RAM (overkill for a hub, probably a server or workstation)

### 5.3 How ambiguous cases resolve

**32 GB Mac mini (headless, in a closet, running HA in Docker):**
- No desktop session → Workstation: -2, Server: +3, Hub: +2 (HA detected)
- Docker with containers → Server: +2
- No web servers/databases → Server stays at +5
- HA service detected → Hub: +3
- Small form factor (Mac mini) → Hub: +1
- Result: Server=5, Hub=6 → suggest **Server + Home Automation Hub** (both pre-checked)

**32 GB Mac mini (on a desk, with a display, running HA in Docker):**
- Has desktop session → Workstation: +3, Server: -2, Hub: +2
- HA service detected → Hub: +3
- Small form factor → Hub: +1
- Result: Workstation=3, Hub=6 → suggest **Workstation + Home Automation Hub** (both pre-checked)

**NAS on old Intel Xeon (headless, SMB/NFS running, 8 containers, no HA):**
- No desktop → Server: +3
- File sharing services → Server: +2
- Docker with 8 containers → Server: +2
- Long uptime → Server: +1
- Result: Server=8, Hub=0, Workstation=-2 → suggest **Server** only

**Mac Studio on a desk (64 GB, M2 Ultra, display, dev tools, no HA):**
- Has desktop → Workstation: +3
- Editors installed → Workstation: +2
- Dev tools → Workstation: +1
- RAM 64 GB → Workstation: +1
- Result: Workstation=7, Server=-2, Hub=0 → suggest **Workstation** only

**Raspberry Pi 4 (4 GB, ARM, headless, HA running, Zigbee USB stick):**
- No desktop → Server: +3, Hub: +0 (no desktop doesn't help hub)
- HA service → Hub: +3
- Zigbee USB → Hub: +2
- ARM + low RAM → Hub: +2, Server: -1
- Small form factor → Hub: +1
- Result: Hub=8, Server=2 → suggest **Home Automation Hub** only

**Mac Studio that also runs HA in Docker (64 GB, display, dev tools, HA container):**
- Has desktop → Workstation: +3
- Editors → Workstation: +2
- Dev tools → Workstation: +1
- RAM → Workstation: +1
- HA service → Hub: +3
- Result: Workstation=7, Hub=3 → suggest **Workstation** (primary), note that HA was detected and offer Hub as a secondary toggle

### 5.4 The tiebreaker rule

- If one role scores >= 3 points higher than the next, suggest only that role (pre-checked).
- If two roles score within 2 points of each other, suggest both (both pre-checked), with a note: "This could be a Workstation or a Home Automation Hub — I see both a display and Home Assistant running."
- If all three score within 2 points (rare), suggest the highest, note the ambiguity, let the user decide.

---

## 6. What each role actually does (the consumption side)

This is the part that makes the roles not theater. Today `user_type` is stored and never read. The new `roles` list must be consumed.

### 6.1 Default landing page

| Role | Landing page |
|---|---|
| Workstation | Dashboard (overview) |
| Server | Compute / fleet view |
| Home Automation Hub | Dashboard with entity panel |
| Workstation + Hub | Dashboard (overview) — the workstation landing, with the home panel visible |

### 6.2 Default panel visibility

| Panel | Workstation | Server | Home Automation Hub |
|---|---|---|---|
| Dashboard overview | yes | yes | yes |
| Home / entities | only if HA detected | no | yes (primary) |
| Terminal | yes | yes | yes |
| Compute / fleet | yes | yes (primary) | no |
| GPU | yes (if GPU present) | yes (if GPU present) | no |
| Containers | yes | yes (primary) | only if Docker present |
| Services | yes | yes (primary) | yes |
| Storage | yes | yes | yes |
| Network | yes | yes | yes |
| Security / Findings | yes | yes | yes |
| Approvals | yes | yes | yes |
| Development | yes (if dev tools detected) | no | no |

### 6.3 Interactive features

| Feature | Workstation | Server | Home Automation Hub |
|---|---|---|---|
| Chat | full | remote-only (headless) | full |
| Voice | yes | no (headless) | yes |
| Terminal | yes | yes | yes |
| Proactive suggestions | yes | alerts only | yes (entity-focused) |

### 6.4 Scan emphasis

| Role | What the scan prioritizes |
|---|---|
| Workstation | Full scan, all categories |
| Server | Service enumeration, network topology, disk health, container status |
| Home Automation Hub | Entity discovery, HA integration, device inventory, sensor history |

### 6.5 Proactivity mode

| Role | What Halbert proactively surfaces |
|---|---|
| Workstation | Suggestions, notifications |
| Server | Alerts on service degradation, disk full, container crash |
| Home Automation Hub | Alerts on device offline, automation failures, sensor anomalies |

### 6.6 Prompt builder context

The roles list is fed into the system prompt so the AI knows its context:
"You are running on a machine the user has identified as a Workstation and a Home Automation Hub. It has a display, 64 GB of RAM, and development tools installed."

This replaces the dead `user_type` field in the prompt builder. The AI adapts its language and suggestions to the machine's role rather than to a user job title.

### 6.7 Optional: free-text "anything else?"

An optional free-text field at the end of onboarding: "Anything else we should know about this machine or how you use it?" — fed into the prompt builder. This captures context that doesn't fit into the three roles (e.g., "this is my media server," "this machine is for ML training only," "this is a kiosk"). See Open Question Q6.

---

## 7. The API changes

### 7.1 New endpoint: quick probe

```
GET /api/settings/onboarding/probe
```

Returns the signals needed for role inference, without running the full scan. This is a new endpoint.

Response:
```json
{
  "signals": {
    "has_display": true,
    "display_server": "quartz-compositor",
    "session_type": "gui",
    "ram_gb": 64,
    "cpu_cores": 24,
    "cpu_model": "Apple M2 Ultra",
    "gpus": ["Apple M2 Ultra"],
    "form_factor": "desktop",
    "uptime_days": 12,
    "has_docker": true,
    "container_count": 3,
    "dev_tools": ["git", "node", "python3", "cargo"],
    "editors": ["vscode", "vim"],
    "notable_services": [
      {"name": "com.docker.docker", "state": "running"},
      {"name": "homeassistant", "state": "running"}
    ],
    "usb_devices": ["Sonoff_Zigbee_Stick"]
  },
  "suggestion": {
    "roles": ["workstation"],
    "scores": {"workstation": 7, "server": -2, "home_automation_hub": 0},
    "reasoning": "This machine has a display, 64 GB of RAM, and development tools installed. It looks like a Workstation."
  }
}
```

### 7.2 Changed endpoint: complete onboarding

```
POST /api/settings/onboarding/complete
```

Request body changes:
```json
{
  "computer_name": "Macky-Mac",
  "admin_name": "Eric",
  "roles": ["workstation", "home_automation_hub"],
  "notes": "optional free-text from the user"
}
```

`user_type: str` → `roles: list[str]` (values: `"workstation"`, `"server"`, `"home_automation_hub"`). The `notes` field is optional.

### 7.3 Storage changes

- `preferences.yml`: `prefs["user_type"]` → `prefs["roles"]` (a list). Keep `ai_name` and `user_name` as-is.
- `onboarding_complete` marker file: third line changes from a single string to a comma-separated list (or JSON array — see Q4).
- `system_profile.json`: `user_settings.user_type` → `user_settings.roles` (a list). Add `user_settings.notes` if provided.

### 7.4 Backward compatibility

Existing installs have `user_type: "casual"` (or similar) in their `preferences.yml` and `onboarding_complete` file. The migration path:
- On reading `preferences.yml`, if `roles` is absent but `user_type` is present, map the old values: `casual`/`developer`/`ai_professional` → `["workstation"]`, `it_admin` → `["server"]`. Log a one-time info message.
- On next onboarding or settings change, the old `user_type` is replaced with `roles`.
- See Open Question Q5 for whether to force a re-onboard.

---

## 8. Open questions for external review

### Q1: Should the quick probe be a separate endpoint, or should the existing scan run first?

**Option A:** New `/onboarding/probe` endpoint that runs a fast subset (hardware, desktop, services, containers, development, boot — skip packages, security, scheduled_tasks, users, virtualization, kernel). ~2-3 seconds. The full scan runs later at step 7.

**Option B:** Run the existing `scan_all()` first (30-60 seconds), then infer the role from the full results, then show the suggestion. No new endpoint needed. But the user waits 30-60 seconds before seeing the role suggestion, which makes the onboarding feel slow.

**Recommendation:** Option A. The probe is fast and the full scan runs at the end anyway. The user gets a suggestion in 2-3 seconds and can adjust it while the full scan hasn't run yet.

### Q2: Should the inference logic live in the backend or the frontend?

**Option A:** Backend. The `/onboarding/probe` endpoint returns both the signals and the suggestion (scores + reasoning). The frontend just renders it. This keeps the inference logic in Python, where it can be tested independently and where it has access to the scanner internals.

**Option B:** Frontend. The backend returns only the signals; the frontend computes the scores and reasoning. This keeps the inference logic in TypeScript, closer to the UI, but duplicates the signal-gathering logic and makes it harder to test.

**Recommendation:** Option A. The inference is a backend concern — it's the same kind of logic the scanner already does, and it should be testable in Python.

### Q3: The scanner does not currently detect Home Assistant, MQTT, or Zigbee/Z-Wave USB sticks. Should we add these signals?

The notable services list (`_scan_services_summary`, line 752) does not include `homeassistant`, `hass`, `mqtt`, `mosquitto`, or `zigbee2mqtt`. The USB device scanner (`_scan_hardware`, line 380) collects USB device names but does not look for Zigbee/Z-Wave vendor IDs specifically.

Without these signals, the Home Automation Hub role can only be inferred from ARM+low RAM (Pi) and small form factor — which misses Mac minis and NUCs running HA in Docker.

**Recommendation:** Add `homeassistant`, `hass`, `mqtt`, `mosquitto`, `zigbee2mqtt`, `deconz` to the notable services list. Add Zigbee/Z-Wave USB vendor ID matching to the USB scanner (Sonoff, ConBee, Z-Stick, etc.). This is a small, well-scoped change to the scanner.

### Q4: Should the `onboarding_complete` marker file format change?

Today the file is three lines: `computer_name\nadmin_name\nuser_type`. Changing `user_type` to a list means either:
- Comma-separated: `computer_name\nadmin_name\nworkstation,home_automation_hub`
- JSON array: `computer_name\nadmin_name\n["workstation", "home_automation_hub"]`

Or: stop storing roles in the marker file at all (they're already in `preferences.yml` and `system_profile.json`). The marker file's purpose is just to signal "onboarding is done" — it doesn't need to carry the roles.

**Recommendation:** Stop storing roles in the marker file. The file becomes just `computer_name\nadmin_name` (or even just a timestamp). Roles live in `preferences.yml` and `system_profile.json` where they belong.

### Q5: Should existing users be re-onboarded?

Users who already completed onboarding have a dead `user_type` field. Should we:
- **Option A:** Force re-onboarding (delete `onboarding_complete`, show the wizard again). Aggressive but ensures everyone gets roles.
- **Option B:** Silently migrate (map old `user_type` to new `roles` on read, per section 7.4). The user never sees the wizard again. They can change their roles in Settings later.
- **Option C:** Show a one-time prompt: "We've updated how we classify machines. Want to re-do setup?" with a yes/skip.

**Recommendation:** Option B. Forcing re-onboarding is hostile. The migration map is simple. Add a Settings page section where users can see and change their roles later.

### Q6: Should there be a free-text "anything else?" field?

An optional text field at the end of onboarding, fed into the prompt builder. Captures context that doesn't fit the three roles.

**Pros:** The AI gets richer context. Handles edge cases ("this is a media server," "this is a kiosk," "this machine is for ML training only").
**Cons:** Another field in onboarding. The three roles + the scan might already be enough.

**Recommendation:** Include it, but make it clearly optional and collapsible. Default: collapsed with a "Anything else we should know?" toggle. If filled, it goes into `preferences.yml` as `notes` and into the prompt builder.

### Q7: Should the roles be editable after onboarding?

If roles drive landing page, panel visibility, and prompt context, the user needs a way to change them without re-running the whole wizard.

**Recommendation:** Yes. Add a "Machine Role" section to the Settings page (or the Being tab, since it's about identity). Shows the current roles as toggle chips, same as onboarding. Saving updates `preferences.yml` and `system_profile.json` and triggers a reload.

### Q8: Is "Home Automation Hub" the right name, or should it be "Home Hub" / "Smart Home" / "Automation"?

The user (founder) used "home automation" in the discussion. The three names under consideration:
- **Home Automation Hub** — precise, but long
- **Home Hub** — shorter, but vague
- **Smart Home** — consumer-friendly, but implies consumer IoT rather than HA/sensors/automations

**Recommendation:** "Home Automation Hub" in the backend/API (`home_automation_hub`), displayed as "Home Hub" in the UI with a subtitle "Runs home automation — Home Assistant, sensors, lights, locks." The API value is unambiguous; the UI label is clean.

---

## 9. Implementation plan (proposed order)

1. **Scanner additions (Q3):** Add HA/MQTT/Zigbee to notable services and USB scanner. Small, well-scoped, testable independently.
2. **Inference function (Q2):** Python function that takes scan signals and returns scores + reasoning. Unit-testable with mock signals.
3. **Probe endpoint (Q1):** New `/onboarding/probe` route that runs the fast subset and calls the inference function.
4. **Backend changes:** `OnboardingData.user_type: str` → `roles: list[str]`. Update storage in `preferences.yml`, `system_profile.json`, and the marker file (Q4). Add migration logic (section 7.4).
5. **Frontend onboarding rework:** New flow with probe → suggestion → multi-select toggles. Replace the four cards.
6. **Consumption side (section 6):** Wire roles to landing page defaults, panel visibility, prompt builder. This is the part that makes roles not theater.
7. **Settings page (Q7):** Add a "Machine Role" section for post-onboarding editing.
8. **Free-text field (Q6):** Optional, can be deferred.

Steps 1-3 can be done independently. Step 4-5 are coupled. Step 6 is the largest and can be phased (start with prompt builder context, then panel visibility, then landing page).

---

## 10. Files referenced

| File | What it does |
|---|---|
| `halbert_core/halbert_core/dashboard/frontend/src/components/Onboarding.tsx` | The onboarding wizard component (373 lines). The four cards are at lines 46-71. |
| `halbert_core/halbert_core/dashboard/routes/settings.py` | Backend onboarding endpoints. `/onboarding/status` at line 995, `/onboarding/complete` at line 1056. `OnboardingData` model at line 1049. |
| `halbert_core/halbert_core/discovery/scanners/system_profile.py` | The system profiler. `scan_all()` at line 71 (15 categories). `_scan_services_summary` at line 740 (notable services list). `_scan_hardware` at line 380 (USB devices). `_scan_development` at line 1630 (dev tools). `_scan_desktop` at line 1690 (display session). |
| `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` | App startup. Checks onboarding status at line 63, shows wizard if not complete. |
| `halbert_core/halbert_core/dashboard/frontend/src/main.tsx` | Entry point. `installAuthFetch()` at line 14, `AuthGate` wraps `App` at line 21. |
| `halbert_core/halbert_core/identity.py` | Identity resolver. Reads `ai_name` and `user_name` from `preferences.yml`. Does NOT read `user_type`. |
| `halbert_core/halbert_core/dashboard/frontend/vite.config.ts` | Vite config. Recently fixed to inject API token in dev proxy (commit 6138d4c6). |

---

## 11. What the founder said (the direction this design comes from)

> "I like multi-select but we really need to give them purpose and give each one clear meaning. Developer and AI pro both seem useless, and Home needs to lead into home automation. IT admin isn't correct either should be more like Is this computer a workstation or server (and make it clear we aren't talking about raspberry pi server...?"

> "Ok all this said, we should technically already know what the user intends to do with this machine based on the specs, we should probably give the users the option, but suggest an option. Obviously there will be ambiguous cases (a 32GB mac mini, a NAS server built on an old intel CPU, etc) but that and scanning the rest of the network and peripherals should give a clear direction."

The design in this document is a direct response to these two statements. The three roles replace the four user types. The scan-first probe implements the "suggest an option" direction. The scoring function handles the ambiguous cases.
