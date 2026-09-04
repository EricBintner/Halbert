# Founder Action Items & Decision Matrix

**Maintainer:** Eric Bintner  
**Updated:** 2026-09-04  
**Status:** Living Executive Action Checklist  
**Channels & boundary:** [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md)  
**Canonical for the legal analysis:** [`documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`](documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md)  
**Decisions of record:** [`DECISIONS.md`](DECISIONS.md) — this file is a checklist, not an authority

---

## 1. Executive Decisions Required

- [x] **`FDR-DEC-01` DCO relicensing & commercial rights (`LEG-CRIT-02`)** — **decided 2026-09-04.**
  DCO 1.1 with an explicit commercial and App Store grant to the maintainer, not a full CLA.
  The text was already committed in `documentation/contributing/CONTRIBUTING.md` and already
  enforced by `.github/workflows/dco.yml`; this was a ratification, not a drafting task.

- [x] **`FDR-DEC-02` GPLv3 §7 Mac App Store exception text (`LEG-CRIT-03`)** — **decided 2026-09-04.**
  `LICENSE-EXCEPTION-APPSTORE` committed at the repo root, verbatim from
  [`APP-STORE-DISTRIBUTION-STRATEGY.md`](documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md) §2.1.
  The two other wordings that existed in the tree are now pointers to it.
  - **Still open, deliberately:** the SPDX `WITH LicenseRef-Halbert-AppStore-Exception` header
    rewrite across ~1,036 files. Deferred as a large mechanical commit, not part of the decision.

- [x] **`FDR-DEC-03` Bundle identifiers & packaging namespaces** — **decided 2026-09-04.**
  `ai.halbert.home` (App Store) / `ai.halbert.pro` (direct DMG) / `ai.halbert.dashboard`
  (dev, internal **and Linux**). Linux takes `dashboard` to match the already-published
  `packaging/flatpak/ai.halbert.dashboard.yml` app-id rather than renaming it — a fourth
  conflict the earlier drafts missed.
  - **Still open:** applying it. `config/platforms.yml` still says `ai.halbert.macos.*`, and
    `scripts/build-macos.sh` has no per-channel injection at all. Tracked as `DIST-1` in `ROADMAP.md`.

- [ ] **`FDR-DEC-04` Lock pricing & perpetual terms for Halbert Pro** — **still yours to set.**
  Three different numbers are written down and none is a decision: this file previously said
  $29 with a $24 early-bird, the 2026-08-29 draft said "$24–$29", and
  [`TERMS.md`](documentation/legal/TERMS.md) adds a 3-device limit the drafts omit.
  Needed: price, update window, renewal, refund policy, device count — then
  `documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md` (draft in
  `.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md`, three placeholders).
  - **Blocks** Ed25519 licence verification, Sparkle and the Lemon Squeezy product — but **not**
    the build channels, which are `DIST-1` and proceed without it.
  - **Constraint on the mechanism, decided 2026-09-04:** `GPL-3.0-or-later` means a recipient
    receives the source and may remove a licence check, so per-feature gating of core code is not
    durably enforceable. The enforceable paid artifact is the signed, notarized, auto-updating
    binary and its update stream. Where the free/paid line falls is still deferred.

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
