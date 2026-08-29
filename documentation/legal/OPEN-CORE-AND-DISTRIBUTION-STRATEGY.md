# Halbert Open-Core, Licensing & Distribution Strategy

**Date:** 2026-08-29  
**Status:** Living Strategy & Architecture Document  
**Scope:** Core Engine (GPL-3.0), Home Automation & Wyoming Voice Pipeline, Mac App Store Sandbox Strategy ("Halbert Home"), Direct Unsandboxed Pro Build ("Halbert Pro"), Pricing & Solo-Developer Sustainability.  
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

---

## 1. Executive Summary

Halbert is a **local-first AI assistant and automation orchestrator** bridging two complementary domains:
1. **Linux System Administration** (systemd, journald logs, storage, hardware telemetry, config snapshots).
2. **Smart Home Automation & Voice** (Home Assistant client, Wyoming voice protocol TCP server, Frigate NVR MQTT stream, SourcePrep HA configuration RAG).

This strategy defines how Halbert maintains a **100% Free and Open Source Software (FOSS)** core while building a clean, sustainable **Pro desktop monetization model** ($24–$29 one-time perpetual) that aligns with the Home Assistant community and strictly complies with Apple Mac App Store sandboxing and anti-steering rules.

---

## 2. The Open-Core Boundary & Product Matrix

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    HALBERT ECOSYSTEM                                    │
├────────────────────────────────────────────┬────────────────────────────────────────────┤
│         OPEN-SOURCE CORE (GPL-3.0)         │            COMMERCIAL DESKTOP              │
│       (Server / Homelab / Linux / HA)      │          (macOS & Windows Clients)         │
├────────────────────────────────────────────┼────────────────────────────────────────────┤
│ • Full Python Engine & LangGraph Agent     │ • Halbert Home (Mac App Store - FREE)      │
│ • Linux CLI & Local Web Dashboard (:8000)  │   - Sandboxed (Apple compliant)            │
│ • Home Assistant Client & Config Bridge    │   - Menu Bar / Global Hotkey Companion     │
│ • Wyoming Voice TCP Server (:10401)        │   - Wyoming voice satellite streaming      │
│ • Frigate NVR Event Ingestion & Scanners   │   - Connects to remote HA/Halbert host     │
│ • HAOS Add-on / Docker Containers          │                                            │
│ • systemd services (`halbert-home.service`)│ • Halbert Pro (Lemon Squeezy - $24–$29)    │
│ • Linux native packages (apt, AUR, snap)   │   - Unsandboxed Apple-Notarized DMG / MSI  │
│                                            │   - Local Mac & Linux Sysadmin Cockpit     │
│                                            │   - Multi-Host Fleet SSH / Tailscale       │
│                                            │   - Integrated Local Ollama & Model Tuner  │
│                                            │   - Sparkle Silent Auto-Updates            │
│                                            │   - Includes all Halbert Home features     │
└────────────────────────────────────────────┴────────────────────────────────────────────┘
```

---

## 3. Surface & Feature Breakdown

| Capability / Surface | OSS Core (Linux/HAOS) | Halbert Home (Mac App Store) | Halbert Pro (Direct Notarized DMG / MSI) |
|---|:---:|:---:|:---:|
| **Price** | Free (GPL-3.0) | **Free** | **$24 – $29 One-Time Perpetual** |
| **Target Platforms** | Linux, Server VMs, Docker, HAOS | macOS (App Store) | macOS (Direct DMG), Windows (MSI) |
| **Distribution Method** | `apt`, `pip`, Docker, HA Add-on | Apple Mac App Store | Lemon Squeezy / Polar.sh |
| **Sandbox Status** | Unsandboxed | **Sandboxed** (`com.apple.security.app-sandbox`) | **Unsandboxed** (Hardened Runtime + Notarized) |
| **Home Assistant Integration** | ✅ Full Server/Bridge | ✅ Remote Client UI | ✅ Remote Client UI |
| **Wyoming Voice Assistant** | ✅ Full TCP Server | ✅ Desktop Voice Satellite | ✅ Desktop Voice Satellite |
| **Global Menu Bar Hotkey** (`Cmd+Shift+Space`) | — | ✅ Included | ✅ Included |
| **Frigate Rich Camera Alerts** | ✅ MQTT ingestion | ✅ Notification Toasts | ✅ Notification Toasts + AI Visualizer |
| **Local Mac Sysadmin (`IOKit`, `powermetrics`)**| — | ❌ Blocked by Apple Sandbox | ✅ Full access |
| **Local Process & Daemon Lifecycle** | ✅ Systemd | ❌ Blocked by Apple Sandbox | ✅ Full Launchd & Ollama Manager |
| **Multi-Host Server Fleet Cockpit** | ❌ Localhost only | ❌ Single Host | ✅ Connect & manage multiple remote nodes |
| **Auto-Updates** | `apt-get` / `docker pull` | Mac App Store Auto-Update | Built-in Sparkle / Silent Updater |

---

## 4. The Home Assistant Community & Mac Strategy

### 4.1 Home Assistant User Expectations
1. **Self-Hosted Core Must Be Free**: The server components (`wyoming_agent.py`, `halbert-home.service`, HA integration tools, and Docker images) are 100% GPL-3.0. Home Assistant users will never adopt a tool that paywalls the server or add-on.
2. **Desktop Convenience Is a High-Value Paid Service**: Most HA users run their smart home server on a headless NUC, Proxmox VM, or Raspberry Pi in a server closet, but spend their workday on an Apple Silicon Mac or Windows PC.
3. **The Friction of Existing HA Desktop Tools**:
   * Official Mac companion is a wrapper around the mobile web UI.
   * Browsers require maintaining dedicated open tabs on port 8123 / 8001.
   * There is no native, low-latency, system-wide voice & AI companion.

### 4.2 Why the Free App Store "Halbert Home" App Wins
* **Instant Discoverability**: Non-technical Mac users and HA enthusiasts find "Halbert Home" directly in the Mac App Store.
* **Frictionless Onboarding**: One-click install from the App Store with automatic iCloud sync of server connection profiles.
* **Top-of-Funnel Trust**: Users experience the speed and reliability of Halbert's native desktop voice and smart-home controls without opening a terminal or paying upfront.

---

## 5. Apple Mac App Store & Sandbox Compliance

### 5.1 The Sandboxing Boundary
Mac App Store guidelines mandate that all distributed binaries run within Apple's App Sandbox. This creates a hard technical boundary:

* **What fits inside the Sandbox (`Halbert Home`)**:
  * `com.apple.security.network.client`: Connecting over HTTP/WebSocket/TCP to local and remote Halbert / Home Assistant instances.
  * `com.apple.security.device.microphone`: Capturing desktop audio for streaming to the Wyoming voice engine.
  * `com.apple.security.files.user-selected.read-write`: Exporting logs or saving snapshots explicitly chosen by the user.
* **What is forbidden by the Sandbox**:
  * Reading raw kernel/hardware sensors via `powermetrics` or private `IOKit` paths without user prompts.
  * Spawning, managing, or terminating background system daemons (`launchctl`, `systemctl`).
  * Direct filesystem monitoring of arbitrary root paths (`/etc`, `/var/log`).

### 5.2 Complying with Review Guidelines & Anti-Steering (Rule 3.1.1 & 4.2)
1. **Standalone Product Framing (Guideline 4.2 - Minimum Functionality)**:
   * "Halbert Home" is not submitted as a "crippled trial" or "demo."
   * It is presented and fully functional as a **complete Home Assistant Desktop Voice & Monitoring Companion**.
2. **No External Store Steering (Guideline 3.1.1)**:
   * The App Store client contains **no buttons, links, or text** saying "Upgrade to Pro on Lemon Squeezy" or "Buy Sysadmin version on our website."
   * In the Settings / About screen, standard links to **"Documentation"** and **"Open Source Project"** (`https://halbert.dev`) are included.
   * On the public website, users can read the documentation and explore the full **Halbert Ecosystem** (including the Direct Unsandboxed Pro DMG).

---

## 6. Monetization & Commercial Architecture

### 6.1 Pricing Model
* **Model**: **$24 – $29 One-Time Perpetual License**.
* **Updates**: Includes **12 months of application updates**. Optional update renewals thereafter (~$12–$15/yr), but existing versions continue to work indefinitely.
* **No Recurring SaaS Subscription**: Running local LLMs and local home automation has zero recurring cloud compute costs for the developer. A one-time perpetual license matches the self-hosted community ethos and maximizes conversion.

### 6.2 License Key Verification (Offline Ed25519)
* Pro builds distributed via Lemon Squeezy use offline **Ed25519 cryptographic license keys**.
* Zero telemetry and zero phone-home requirement: the desktop app verifies the digital signature of the license key locally using a bundled public key.

---

## 7. Licensing & Contributor IP Governance

1. **Halbert Core Engine**: Licensed under **GNU General Public License v3.0 or later (`GPL-3.0-or-later`)**.
2. **Mac App Store Exception (GPLv3 §7)**:
   * Applied to the App Store target to resolve the GPLv3 §6/§10 conflict with Apple DRM:
   ```text
   As a special exception, the copyright holders of Halbert grant permission
   to convey the object code of this work through the Apple Mac App Store,
   notwithstanding Sections 6 and 10 of GNU GPLv3.
   ```
3. **Contributor IP Governance (`LEG-CRIT-02`)**:
   * Contributors must submit changes under a **Developer Certificate of Origin (DCO)** with an explicit commercial distribution & App Store exception grant in `CONTRIBUTING.md`.
   * This ensures the founder retains the legal right to package and distribute official desktop builds without requiring 100% individual sign-off from future contributors.

---

## 8. Implementation & Release Sequencing

```
Phase 1: OSS Core & Home Automation (Current)
  ├── Harden Home Assistant client, config bridge, and Wyoming TCP voice agent
  ├── Package Linux systemd services (`deploy/halbert-home.service`)
  └── Publish Home Assistant Community Add-on / Docker image

Phase 2: Free "Halbert Home" Mac App Store Release
  ├── Configure Tauri sandbox entitlements (`network.client`, `microphone`)
  ├── Build Menu Bar Voice Satellite (`NSStatusItem` + `Cmd+Shift+Space`)
  ├── Apply GPLv3 §7 Mac App Store Exception
  └── Submit `ai.halbert.home` to Mac App Store Review

Phase 3: Paid "Halbert Pro" Direct Release ($24–$29)
  ├── Build Unsandboxed Apple-Notarized DMG with Hardened Runtime
  ├── Implement multi-host remote server fleet cockpit
  ├── Integrate local Mac system monitoring (`IOKit`, `powermetrics`)
  ├── Wire Lemon Squeezy checkout & Ed25519 offline license verification
  └── Enable Sparkle silent auto-updates
```
