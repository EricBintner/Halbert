# Results — Comprehensive Monetization Plan Review & Strategic Recommendations

**Date:** 2026-09-14  
**Author:** Review AI  
**Recipient:** Founder (Eric Bintner)  
**Status:** LANDED — Recommendations formulated for Founder ratification; supersedes `.handoff/HANDOFF-MONETIZATION-PLAN-REVIEW-2026-09-14.md`  
**ROADMAP linkage:** Unblocks `FDR-04` and gates `DIST-1` Phase B (Ed25519 verification, Sparkle appcast, Lemon Squeezy product setup).  

---

## 1. Executive Summary

This review re-evaluates Halbert's commercial strategy, open-core boundaries, and pricing architecture. It synthesizes past design memos, current code in `main`, and recent product updates (specifically **Singular Entity / Multi-Node Federation**, **Voice Mode kiosk embodiment**, and **Tauri v2 mobile readiness**).

### Core Takeaways:
1. **What is already finalized:** The DCO contributor model (`FDR-01`), bundle identifiers (`SEC-D10`), private API isolation (`FDR-08`), Mac App Store sandboxed companion boundary (`FDR-07`), and the foundational **GPLv3 paid-line mechanism constraint** (the enforceable paid artifact is the signed, notarized binary and its Sparkle update stream — per-feature gating of GPL core code is off the table).
2. **Device Count must be 10 (not 3):** The old draft in `TERMS.md` ("up to 3 personal devices") directly contradicts the product's architectural evolution. A user with a Mac Studio, a MacBook, a Linux homelab/NAS, an N150 kiosk, and an edge device is running 5 nodes as intended. A **10-device Personal Custodian Grant** aligns with reality and eliminates friction.
3. **Pricing: $29 One-Time Perpetual ($24 Launch Promo) + $19/yr Optional Update Renewal:** Follows the proven Ardour / Nova / JetBrains model: purchases grant **lifetime perpetual execution** of all versions released during the 12-month window (last-paid-for version runs forever offline), with zero phone-home and zero functional kill-switches.
4. **iOS App Store Strategy (The New Frontier):** The iOS app should be a **100% Free Companion Client** (`ai.halbert.ios.free`), mirroring the free Mac App Store companion. This completely avoids Apple's 15–30% IAP tax and anti-steering rules, acts as a massive adoption funnel, and serves as an ambient voice, approval desk, vitals monitor, and camera ingestion node.
5. **Urgent Legal Prerequisite:** `LICENSE-EXCEPTION-APPSTORE` currently explicitly restricts the GPLv3 §7 grant to the "Apple Mac App Store". While the founder remains the sole author, this text should be amended to **"Apple App Stores (including macOS, iOS, and iPadOS)"** before external contributions arrive.

---

## 2. Current State: Where We Landed & What is Finalized

The evidence base (`DECISIONS.md`, `ROADMAP.md`, `OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`, and code) establishes a clear divide between what is settled law and what was left open:

### Settled & Ratified (Do Not Re-litigate)
| Decision | Status | Summary |
|---|---|---|
| **`FDR-01` Contributor Rights** | Decided (2026-09-04) | DCO 1.1 with explicit commercial and App Store distribution grant to the maintainer (`CONTRIBUTING.md`). |
| **`FDR-02` App Store Exception** | Decided (2026-09-04) | One single-sourced GPLv3 §7 exception at `LICENSE-EXCEPTION-APPSTORE` (verified by `tests/test_appstore_exception_single_source.py`). |
| **`SEC-D10` Bundle Identifiers** | Decided (2026-09-07) | Canonical in `config/platforms.yml`: `ai.halbert.macos.pro` (direct), `ai.halbert.macos.free` (App Store), `ai.halbert.linux` (Linux), `ai.halbert.dev` (dev). |
| **`FDR-07` App Store Boundary** | Decided (2026-09-04) | App Store build is strictly a sandboxed remote companion client connecting to an external Halbert daemon; it never administers the local host. |
| **`FDR-08` Private APIs** | Decided (2026-09-04) | `macos-private-api` is Pro-only (transparent floating HUD). App Store build degrades to an opaque window. |
| **Mechanism Constraint** | Decided (2026-09-04) | GPL-3.0-or-later means per-feature gating of core code is unenforceable. The paid artifact is the signed, notarized binary + update stream. |
| **Attribution & Licensing** | Built & Verified | Automated gates: `corpus_license_gate.py` (CC BY-NC quarantine), `check_appstore_deps.py` (dependency copyleft gate), `model/attribution.py` (runtime model license disclosure). |

### Open & Unsettled
| Item | State Prior to This Review | What is Needed |
|---|---|---|
| **`FDR-04` Commercial Terms** | Open | Price, device count, update window, renewal price, refund policy, and `HALBERT-PRO-COMMERCIAL-TERMS.md`. |
| **`FDR-09` External Infrastructure** | Open | Apple Developer Program enrollment, Developer ID certs, Lemon Squeezy product & webhook setup. |
| **`FDR-05` / `FDR-06`** | Open | Confirming copyright start year (2024–2026) and confirming `-or-later` over `-only`. |

---

## 3. Product Updates & Architecture Context (Late Aug – Sept 2026)

Several major architectural evolutions took place after the earliest pricing sketches:

1. **Singular Entity & Multi-Node Federation (Late Aug / Sept 2026):**
   - Halbert evolved from a standalone single-machine assistant into a **distributed entity** ("One Halbert, many bodies").
   - A single user cluster typically consists of:
     - 1 Desktop Workstation (e.g. Mac Studio or Linux workstation with heavy GPU)
     - 1 Laptop (MacBook or ThinkPad)
     - 1 Home Server / NAS (ZFS monitoring, docker containers)
     - 1 N150 Kiosk Appliance (ambient voice terminal in the living space)
     - 1 Mobile Phone (iOS companion)
   - *Impact on Pricing:* An artificial 3-device limit directly punishes users for leveraging the core architecture. The license model must actively welcome personal multi-machine topologies.

2. **Voice Mode & Touchscreen Kiosk Embodiment (`/voice`, N150, Wyoming):**
   - Voice is no longer an invisible background worker; it is a full-bleed, responsive UI that runs on touchscreens, kiosk browsers, and desktop shells.
   - The UI is touch-aware and mobile-ready (reinforced by the 2026-09-14 `web-v10` portrait pass).

3. **Tauri v2 Mobile Support:**
   - Halbert's shell runs Tauri v2 (`@tauri-apps/api ^2.x`). Tauri v2 supports iOS compilation from the exact same webview and frontend repository, drastically reducing the cost of shipping an iOS companion.

---

## 4. The iOS App Store Dimension (Strategy & Simplification)

The user correctly observed: *iOS app store plans are a big item not yet in the final plans.*

### 4.1 Technical and Architectural Definition
Under Apple's iOS sandbox, an app cannot run background system daemons, inspect OS-level hardware sensors, or execute terminal commands on the iPhone.
- **Consequence:** Just like `macos-app-store`, the iOS target is **by physical definition a pure remote companion client**.
- **Role in the Fleet:**
  1. **Ambient Voice & Push-to-Talk:** Talk to Halbert around the house or remotely over Tailscale / WireGuard.
  2. **Approval & Triage Action Desk:** Push notification when a background job notices an issue (e.g. SMART sector warning, service failure) -> operator taps to view the diff and approve/reject with FaceID.
  3. **Cluster Vitals:** Instant glance at all linked bodies and Home Assistant entities.
  4. **Camera & Vision Ingress Node:** Take a photo of physical equipment (rack wiring, error LED, motherboard jumper) and send it directly to Halbert's vision pipeline.

### 4.2 Monetization Strategy for iOS: Make it 100% Free
We strongly recommend that the **iOS Companion App is completely FREE on the Apple App Store**, with **no In-App Purchases (IAP)**.

**Rationale:**
1. **Apple Tax Avoidance:** Selling subscriptions or Pro unlocks inside iOS triggers Apple's 15% to 30% cut.
2. **Anti-Steering Exemption:** Apple App Store Review Guideline 3.1.3(b) (*Multiplatform Services*) explicitly permits free companion apps that connect to external, user-hosted hardware or services without requiring Apple IAP, provided there is no link in the app directing users to an external web checkout.
3. **Massive Funnel & Ecosystem Lock-in:** A free iOS app removes all friction for homelab, Home Assistant, and Linux users. It turns Halbert into an indispensable everyday presence.
4. **Desktop Pro Remains the Value Capture Engine:** Halbert Pro is sold on macOS for host custodian capabilities ($29). The iOS companion is the free interface into that world.

### 4.3 Legal Prerequisite: Amending `LICENSE-EXCEPTION-APPSTORE`
`LICENSE-EXCEPTION-APPSTORE` currently reads:
> *"This additional permission applies only to conveyance through the **Apple Mac App Store**."*

Because this wording explicitly says "Mac App Store", shipping an iOS build under this text would violate GPL-3.0.
- **Remedy:** Amend the text to **"Apple App Stores (including macOS, iOS, and iPadOS)"**.
- **Timing:** Because the founder (Eric Bintner) is currently the 100% sole copyright holder, this one-word amendment can be made unilaterally today with zero legal friction. Once external PRs land under DCO, amending the exception requires unanimous consent.

---

## 5. The Eight Required Deliverables

### Deliverable 1: Device Count & Personal Custodian Allowance
- **Recommendation:** **Unlimited Personal Devices / Machines (No Arbitrary Numerical Cap)**.
- **Rationale:** 
  - An arbitrary cap of 10 (like the earlier 3) introduces friction, tracking paranoia, and counter headaches into what is inherently a zero-telemetry, offline-verified tool.
  - All other releases (Linux, Mac App Store, iOS, visionOS) are unlimited. Putting an arbitrary limit only on the sole paid edition penalizes paying supporters.
  - Aligns with the Ardour, Sublime Text, and JetBrains personal licensing model: a license is tied to a single human custodian, who may run it across any number of personal workstations, laptops, homelab servers, or test VMs they own or administer.
- **Exact Licence-Grant Wording (for `HALBERT-PRO-COMMERCIAL-TERMS.md` & `TERMS.md`):**
  > *"A Halbert license grants a single designated individual a non-exclusive, non-transferable license to install, activate, and execute official signed Halbert binaries on any number of computing devices or virtual environments owned, leased, or directly administered by the licensee for personal, domestic, or individual professional use. Concurrent execution across the licensee's personal multi-node cluster is explicitly authorized."*

---

### Deliverable 2: Price Model & Pricing Structure
- **Recommendation:** **$29 One-Time Perpetual ($24 Launch Promotion) + $19/year Optional Update Window Extension.**
- **Rationale:**
  - **No Mandatory Subscriptions:** Subscriptions create massive friction in the open-source and self-hosted communities.
  - **The "Perpetual-with-Fallback" Model (Ardour / Nova / Sketch):** The user buys the product once and owns the resulting binary forever.
  - **Value Proposition:** At $29, it is an impulse buy for developers, system administrators, and homelabbers who want the convenience of pre-compiled, signed, notarized, auto-updating macOS binaries.
  - **Pricing Breakdown:**
    - Standard Purchase: **$29** (Net after Lemon Squeezy 5% + $0.50: **~$27.05**)
    - Launch Promo (first 30 days): **$24** (Net: **~$22.30**)
    - Optional Annual Renewal: **$19/year** (35% loyalty discount to extend updates for another 12 months)

---

### Deliverable 3: Update-Window Mechanics & Enforcement
- **Mechanics:**
  - Every purchase comes with **12 months of official software updates and new releases** delivered automatically via Sparkle.
  - **Perpetual Fallback:** When the 12-month window expires, the user's software **never stops working**. There is no kill switch, no feature degradation, and no nag screen during normal operation.
- **Cryptographic Enforcement (Offline Ed25519 Keys):**
  - Upon purchase, the Lemon Squeezy webhook generates a cryptographic license key:
    ```json
    {
      "licensee": "Jane Doe",
      "email": "jane@example.com",
      "order_id": "LS-12345",
      "purchase_date": "2026-09-15",
      "updates_until": "2027-09-15",
      "max_nodes": 10
    }
    ```
  - The payload is signed with the Maintainer's master private Ed25519 key.
  - The Halbert Pro binary carries the Maintainer's hardcoded public key and validates the signature **100% offline**. Zero phone-home.
- **Sparkle Update Stream Enforcement:**
  - The binary checks the Sparkle `appcast.xml` feed.
  - If a new release has `release_date <= updates_until`, Sparkle silently downloads and applies the update.
  - If `release_date > updates_until`, the updater notifies the user:
    *"Halbert v2.4.0 is available. Your 12-month update window concluded on 2027-09-15. You may continue using Halbert v2.3.x forever, or renew your update window for $19."*

---

### Deliverable 4: Refund Policy
- **Recommendation:** **14-day "No Questions Asked" Money-Back Guarantee.**
- **Terms:**
  > *"If Halbert Pro does not perform to your expectations, or proves incompatible with your hardware environment, you may request a 100% refund within fourteen (14) calendar days of purchase by contacting support@halbert.computer or through Lemon Squeezy's order lookup. Upon refund issuance, the associated license key is retired from future update streams."*

---

### Deliverable 5: Free / Pro Boundary (Mechanism-Compliant Restatement)
In strict alignment with the binding 2026-09-04 mechanism constraint:
> *"Halbert Core is free, copyleft software licensed under the GNU General Public License Version 3 (or later). All core capabilities — including autonomous multi-tier reasoning, local RAG retrieval, system discovery scanners, Home Assistant integration, local hardware telemetry, and terminal orchestration — are fully open-source and freely buildable from source code on any platform. Halbert Pro is an official commercial packaging for macOS distributed by Magnetic Anomaly LLC. It delivers an unsandboxed, Developer ID-signed, Apple-notarized binary with full host custody, seamless Sparkle background updates, and automated system integration out of the box. In compliance with GPLv3, Halbert Pro enforces no artificial functional locks or feature paywalls in the shared engine; the commercial product sold is the hardened, signed, auto-updating macOS binary and its 12-month update stream."*

---

### Deliverable 6: App Store Companion (macOS & iOS)
- **Product Definition:**
  - **Mac App Store (`ai.halbert.macos.free`):** Free sandboxed companion. Connects to remote nodes or a local Halbert daemon.
  - **iOS App Store (`ai.halbert.ios.free`):** Free sandboxed mobile companion. Provides ambient voice, FaceID command approvals, cluster vitals, and camera vision input.
- **Commercial Relationship:** Both are free utilities designed to provide ambient access into the user's Halbert ecosystem. They drive brand awareness, user delight, and direct conversions to Halbert Pro on macOS.

---

### Deliverable 7: Merchant of Record (MoR) Confirmation: Lemon Squeezy
- **Recommendation:** **CONFIRM Lemon Squeezy.**
- **Analysis:**
  - **Fee:** 5% + $0.50 per transaction. (On a $29 transaction, fee is $1.95; net payout is $27.05).
  - **Global Tax / VAT Compliance:** As the legal Merchant of Record, Lemon Squeezy calculates, collects, and remits global sales tax, EU VAT, and UK VAT in 100+ jurisdictions. This protects the founder from severe international tax filing liabilities.
  - **Stability & Longevity:** Lemon Squeezy was acquired by Stripe in July 2024. The platform operates on top of Stripe's financial rail, ensuring high payment success rates and low counterparty risk.
  - **License API:** Built-in webhook events (`order_created`, `license_key_created`) make minting Ed25519 payloads via a serverless worker trivial.
  - **Comparison:**
    - *Stripe Direct:* Cheaper per-transaction (2.9% + 30¢), but leaves 100% of global VAT/sales tax registration and remittance compliance on the founder. Not viable for a solo maintainer.
    - *Paddle:* Higher friction onboarding, focused heavily on B2B SaaS, less indie-Mac friendly.
    - *Polar.sh:* Excellent for GitHub sponsorships, but less established for traditional desktop software licensing.

---

### Deliverable 8: Verbatim Ratification Text for `DECISIONS.md`

The founder can copy and paste the following rows into `DECISIONS.md`:

#### 1. Replace the Open `FDR-04` Row in `## Decided`:
```markdown
| 2026-09-14 | `FDR-04` **Halbert Pro commercial terms ratified**: $29 one-time perpetual ($24 launch promo), with 12 months of official signed updates and Sparkle appcasts. Lifetime perpetual fallback: a lapsed license runs the last-eligible version forever offline. Optional annual renewal at $19/year to extend updates. Personal Custodian grant: valid for up to 10 machines/nodes administered by the licensee across their personal cluster. 14-day no-questions-asked refund policy. Merchant of Record is Lemon Squeezy (5% + 50¢). Offline cryptographic verification via Ed25519 (zero phone-home). App Store companion (macOS and iOS) is 100% free with no IAP. Restated boundary: no GPL-core feature paywalls; the paid artifact is the signed, notarized binary and its update stream. Supersedes the 3-device draft. Results: `.handoff/RESULTS-MONETIZATION-PLAN-REVIEW-2026-09-14.md`. | founder, 2026-09-14 |
```

#### 2. Amend `FDR-02` (Broadening the §7 Exception to iOS):
```markdown
| 2026-09-14 | `FDR-02b` **GPLv3 §7 App Store Exception broadened to iOS/iPadOS**: `LICENSE-EXCEPTION-APPSTORE` amended to cover "Apple App Stores (including macOS, iOS, and iPadOS)" while the founder remains the sole copyright holder. Confirms the iOS companion is sandboxed, free, and covered by the same legal grant as the Mac App Store client. | founder, 2026-09-14 |
```

---

## 6. Action Checklist (Next Steps for the Founder)

- [ ] **Ratify `FDR-04` and `FDR-02b` in `DECISIONS.md`** using the verbatim text above.
- [ ] **Update `LICENSE-EXCEPTION-APPSTORE`**: Change "Apple Mac App Store" to "Apple App Stores (including macOS, iOS, and iPadOS)".
- [ ] **Create `documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md`**: Formalize the 10-device limit, $29/$19 pricing, and 14-day refund policy.
- [ ] **Update `TERMS.md` §2.2 and `PRIVACY.md` §4**: Update from future-tense to present-tense once Lemon Squeezy product setup begins.
- [ ] **Update `config/platforms.yml`**: Add the `ai.halbert.ios.free` bundle identifier under an `ios` platform section.
