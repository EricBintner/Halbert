# Halbert Pro — Commercial Terms & End User License Agreement (EULA)

**Effective Date:** 2026-09-14  
**Status:** Ratified (`DECISIONS.md` `FDR-04`, 2026-09-14)  
**Publisher:** Magnetic Anomaly LLC / Eric Bintner  
**Merchant of Record:** Lemon Squeezy LLC  
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**  

---

## 1. Scope & Relationship to Open Source Core

Halbert Core is free software licensed under the **GNU General Public License Version 3.0 or later** (`GPL-3.0-or-later`). Nothing in these Commercial Terms limits, restricts, or overrides your rights to inspect, modify, compile, or redistribute the open-source source code under the terms of the GPL-3.0.

These Commercial Terms govern your purchase, licensing, and receipt of official, pre-compiled, Developer ID-signed, and Apple-notarized binary releases of **Halbert Pro** for macOS distributed through our Merchant of Record.

Pursuant to the binding mechanism constraint ratified in `DECISIONS.md` (2026-09-04):
> Halbert Pro does not enforce artificial feature paywalls or functional restrictions within the shared GPL core engine. The commercial product conveyed is the hardened, Apple-notarized, unsandboxed macOS binary release, accompanied by automated Sparkle background updates and official maintenance support.

---

## 2. License Grant (Personal Custodian License)

Upon receipt of payment and issuance of a cryptographic license key, Magnetic Anomaly LLC grants you a personal, non-exclusive, non-transferable commercial license to execute official Halbert Pro binaries under the following terms:

1. **Named Licensee:** The license is granted to a single designated individual (the "Custodian").
2. **Device Allowance:** You may install, activate, and run official Halbert Pro binaries on up to **ten (10) physical or virtual computing machines** owned, leased, or directly administered by you for personal, domestic, or professional use.
3. **Multi-Node Cluster Operation:** Concurrent execution across your personal multi-node cluster (e.g. primary workstation, laptop, homelab servers, and appliance nodes) is explicitly permitted and encouraged under a single license.
4. **Organizational / Multi-User Teams:** If Halbert Pro is deployed across multiple users within a commercial team or organization, one separate license must be acquired per active administrator/custodian.

---

## 3. Pricing, Update Window & Perpetual Fallback

### 3.1 Standard & Promotional Pricing
* **Standard Purchase:** **$29 USD** (one-time perpetual license).
* **Launch Promotion:** **$24 USD** (promotional introductory price for early adopters).

### 3.2 12-Month Update Window
Every Halbert Pro purchase includes **twelve (12) consecutive months of official software updates, security patches, and new feature releases**, delivered automatically via the Sparkle update stream.

### 3.3 Lifetime Perpetual Fallback (The Ardour / JetBrains Model)
Your license **never expires for versions released within your update window**:
* When your 12-month update window lapses, your software **does not cease operating, does not degrade into a trial, and does not enter a crippled state**.
* You retain the perpetual right to download, install, and execute the final release published during your active 12-month window forever.

### 3.4 Optional Update Renewal
At or after the conclusion of your 12-month update window, you may optionally extend your update entitlement for an additional twelve (12) months:
* **Renewal Price:** **$19 USD / year** (approximately 35% loyalty discount).
* **Non-Compulsory:** Renewal is strictly optional. If you choose not to renew, your existing software remains fully functional for life.

---

## 4. Cryptographic Offline Verification (Zero Telemetry)

Halbert is designed from first principles to safeguard operator privacy and system sovereignty:
1. **Offline Ed25519 Signatures:** Your license key is an offline cryptographic certificate containing your licensee identity, purchase date, update window expiration, and maximum node allowance. It is digitally signed with the maintainer's master private key at checkout.
2. **Zero Phone-Home:** The Halbert Pro desktop application verifies license validity completely offline against an embedded public key. The binary **never phones home, transmits device fingerprints, or contacts an activation server** during startup or normal execution.
3. **Zero Telemetry:** The application contains no usage beacons, analytics SDKs, or remote telemetry collectors.

---

## 5. Sparkle Update Stream Mechanics

Official binary updates are distributed via the Sparkle application updater framework:
1. Halbert Pro periodically checks the secure release feed (`appcast.xml`).
2. If a published update carries a release timestamp within your active update window (`release_date <= license.updates_until`), the update downloads, verifies its signature, and installs seamlessly.
3. If an update is published after your update window has concluded, the updater will notify you of the new release and provide the option to renew your update window, while continuing to run your current version uninterrupted.

---

## 6. Refund Policy

We offer a **14-day "No Questions Asked" Money-Back Guarantee**:
* If Halbert Pro does not meet your operational requirements, or proves incompatible with your hardware or workflows, you may request a 100% full refund within **fourteen (14) calendar days** of the original purchase date.
* Refund requests can be initiated through Lemon Squeezy's customer portal or by emailing `support@halbert.computer`.
* Upon refund issuance, the associated license key is retired from future Sparkle update streams.

---

## 7. Merchant of Record & Tax Compliance

All orders, payment processing, invoicing, and order delivery are fulfilled by our Merchant of Record:
* **Lemon Squeezy LLC** (a Stripe company), 222 S. Main Street, Suite 500, Salt Lake City, UT 84101, USA.
* Lemon Squeezy acts as the legal reseller and Merchant of Record, collecting and remitting worldwide sales tax, Value Added Tax (EU/UK VAT), and GST in compliance with local regulations.
* Financial information (credit card numbers, bank details) is processed directly by Lemon Squeezy and is never received, stored, or accessible by Halbert servers.

---

## 8. Companion Applications (Apple App Stores)

In addition to Halbert Pro for macOS, the Halbert project distributes companion applications:
* **Platforms:** Apple Mac App Store, iOS, iPadOS, and visionOS.
* **Pricing:** **100% Free** (zero in-app purchases, zero recurring subscription fees).
* **Functionality:** Sandboxed remote companion clients providing ambient voice interaction, cluster vitals monitoring, FaceID action approval, and camera/vision ingestion.
* **Legal Terms:** Companion builds are distributed pursuant to Apple Media Services Terms and Conditions and our single-sourced **GPLv3 Section 7 Additional Permission** ([`LICENSE-EXCEPTION-APPSTORE`](../../LICENSE-EXCEPTION-APPSTORE)). Companion clients pair seamlessly with both self-hosted open-source nodes and Halbert Pro installations.

---

## 9. Disclaimer of Operational Liability

Halbert Pro executes administrative commands and monitors live operating system environments. You acknowledge and agree that you are solely responsible for reviewing staged system actions and maintaining verified backups of all critical systems, as set forth in [`DISCLAIMER.md`](DISCLAIMER.md) and [`TERMS.md`](TERMS.md).
