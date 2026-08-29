# Founder Action Items & Decision Matrix

**Maintainer:** Eric Bintner  
**Updated:** 2026-08-29  
**Status:** Living Executive Action Checklist  
**Governing Strategy:** [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md)

---

## 1. Executive Decisions Required

- [ ] **`FDR-DEC-01` Formalize DCO Relicensing & Commercial Rights (`LEG-CRIT-02`)**
  - **Decision**: Update `documentation/contributing/CONTRIBUTING.md` with explicit Developer Certificate of Origin (DCO) language that grants the project maintainer the right to distribute binaries via proprietary channels (Apple Mac App Store, Microsoft Store, Lemon Squeezy) and apply GPLv3 §7 exceptions.
  - **Why Critical**: Must be committed *before* accepting external pull requests to prevent copyright fragmentation.

- [ ] **`FDR-DEC-02` Approve GPLv3 §7 Mac App Store Exception Text (`LEG-CRIT-03`)**
  - **Decision**: Approve the exception text in [`documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`](documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md) §2.1.
  - **Action**: Commit `LICENSE-EXCEPTION-APPSTORE` and update SPDX headers on covered files.

- [ ] **`FDR-DEC-03` Confirm Bundle Identifiers & Packaging Namespaces**
  - **Decision**: Align Tauri configuration and build scripts:
    - **Free App Store Companion**: `ai.halbert.home` (Display name: *Halbert Home*)
    - **Paid Direct Pro Edition**: `ai.halbert.pro` (Display name: *Halbert Pro*)
    - **Linux / Internal Daemon**: `ai.halbert.dashboard`

- [ ] **`FDR-DEC-04` Lock Pricing & Perpetual Terms for Halbert Pro**
  - **Decision**: Set Halbert Pro launch price at **$29 one-time perpetual** ($24 early-bird promotion), including 12 months of application updates. No recurring SaaS subscription.

---

## 2. Accounts & Infrastructure Setup

- [ ] **`FDR-INF-01` Apple Developer Program Account Provisioning**
  - Verify Apple Developer Program membership ($99/year) under Magnetic Anomaly LLC or individual developer account.
  - Create **Mac App Store Provisioning Profile** with App Sandbox enabled for `ai.halbert.home`.
  - Create **Developer ID Application Certificate** for signing direct unsandboxed DMGs for `ai.halbert.pro`.
  - Set up `notarytool` credentials in local macOS keychain for automated CI notarization.

- [ ] **`FDR-INF-02` Lemon Squeezy / Payment Merchant Setup**
  - Create product entry for **Halbert Pro** ($29 one-time).
  - Configure automated webhook or license key issuance.
  - Generate master Ed25519 private/public keypair:
    - Private key: Stored securely for generating license keys.
    - Public key: Hardcoded into Halbert Pro binary for offline local verification.

- [ ] **`FDR-INF-03` Home Assistant Community Add-on Repository**
  - Set up public GitHub repository `EricBintner/halbert-ha-addon` (or under organization).
  - Configure `repository.yaml` and `config.yaml` to enable 1-click install within Home Assistant OS (HAOS) Supervisor.

---

## 3. Product & Release Milestones

### Milestone 1: Open-Source Core & Home Assistant Backend
- [ ] Verify `deploy/halbert-home.service` runs reliably alongside `homeassistant.service`.
- [ ] Confirm `wyoming_agent.py` TCP server connects seamlessly with Home Assistant Voice Pipelines (Settings → Voice Assistants).
- [ ] Test Frigate NVR MQTT event ingestion on live camera streams.
- [ ] Publish multi-architecture Docker images (`linux/amd64`, `linux/arm64`) to GitHub Container Registry (`ghcr.io`).

### Milestone 2: Free "Halbert Home" Mac App Store Release
- [ ] Configure `src-tauri/tauri.conf.json` with sandbox entitlements:
  - `com.apple.security.app-sandbox`
  - `com.apple.security.network.client`
  - `com.apple.security.device.microphone`
- [ ] Implement Menu Bar companion UI (`NSStatusItem`) with global hotkey (`Cmd+Shift+Space`) for low-latency Wyoming voice streaming.
- [ ] Build, sign, and test the `.pkg` package via `scripts/build-macos.sh --channel macos-app-store`.
- [ ] Submit to Apple Mac App Store review.

### Milestone 3: Paid "Halbert Pro" Direct DMG Release ($24–$29)
- [ ] Configure `scripts/build-macos.sh --channel macos-pro` with Hardened Runtime (unsandboxed) and notarization.
- [ ] Implement multi-node remote host connection manager (SSH / mTLS / Tailscale).
- [ ] Integrate local Mac hardware sensors (`IOKit`, `powermetrics`) and launchd process manager.
- [ ] Wire offline Ed25519 license key activation modal in settings.
- [ ] Enable Sparkle silent auto-updates.

---

## 4. Community Launch & Distribution Channels

- [ ] **Home Assistant Community**: Post release announcement on Home Assistant Community Forums (Share Your Projects / Voice Assistant category).
- [ ] **Reddit**: Post release showcases on `r/homeassistant`, `r/selfhosted`, `r/homelab`, and `r/LocalLLaMA`.
- [ ] **Hacker News**: Submit "Show HN: Halbert – Local-First AI & Wyoming Voice for Home Assistant and Linux".
- [ ] **Documentation Site**: Publish `halbert.dev` featuring clear ecosystem navigation between OSS self-hosted backend, free App Store companion, and Pro desktop edition.
