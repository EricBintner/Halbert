# Founder Decision Drafts — FDR-DEC-01…04 (U5)

> **Status: SUPERSEDED for FDR-DEC-01/02/03 (decided 2026-09-04).** The exception
> text drafted in FDR-DEC-02 below is now committed as `LICENSE-EXCEPTION-APPSTORE`
> at the repository root — **that file is the operative grant; the copy below is a
> historical draft and must not be quoted as the licence.** FDR-DEC-04 (pricing) is
> still open. See `DECISIONS.md` and
> `.handoff/HANDOFF-DISTRIBUTION-CHANNELS-2026-09-04.md`.

**Date:** 2026-08-31
**Author:** GLM-5.3 (drafting only — every decision below is the founder's; no model closes these)
**Purpose:** All four U5 deliverables drafted and ready for sign-off. Per the batch plan, this is
where the AI's work **stops**: approve, amend, or reject each draft, then commit the approved text.
**Governing docs:** `FOUNDER-TODO.md`, `documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`,
`documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`, `TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md`
**Erratum honored:** the packet's `src-tauri/tauri.conf.json` path is wrong; the real file is
`halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json`.

---

## FDR-DEC-01 — DCO commercial-rights language (NEEDS RATIFICATION, not drafting)

**Finding:** the requested DCO text is **already committed** — `documentation/contributing/CONTRIBUTING.md`
contains the full "Licensing & Contribution Terms" section: DCO 1.1 (the four certifications),
`Signed-off-by:` mechanics, the dual-distribution/commercial grant to the maintainer, and an
App Store §7 clause. There is nothing left to draft; what is missing is the founder's explicit
ratification that this committed text is the final inbound license.

**Decision requested:** ratify the committed section as-is, or amend it. Two points flagged from
earlier review passes that the founder has not yet ruled on:

1. **DCO, not CLA** — the strategy doc (§7.2) leaves CLA-vs-DCO open; CONTRIBUTING.md implements
   the lighter DCO-with-relicensing-grant option. Ratifying it closes that question. Recommended:
   yes — sufficient for a single-maintainer project.
2. **"GPL-3.0-or-later"** — the license statement uses the or-later form throughout. If the intent
   is GPL-3.0-only, every statement must change before external contributions land. Recommended:
   keep or-later.
3. **Copyright year "2024-2026"** on SPDX headers — flagged in the 2026-08-25 legal pass as
   founder-pending (is 2024 the correct first year of authorship?). Unresolved.

---

## FDR-DEC-02 — `LICENSE-EXCEPTION-APPSTORE` (drafted below) + SPDX form

**Conflict found in-tree:** two DIFFERENT §7 exception texts already exist —

- `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` §2.1: the considered text —
  scope-limited to the Mac App Store only, explicit third-party-code carve-out, and the
  downstream-fork-freedom clause that keeps the grant additional rather than restrictive.
- `documentation/contributing/CONTRIBUTING.md` §3: a broader paraphrase ("…or other digital
  distribution platforms that impose usage rules, DRM, or application sandboxing…").

These cannot both be the exception. **Recommended: the strategy doc's §2.1 text** — it is the
narrower, legally-considered remedy (VLC/GNU-Go precedent), and the broader "other digital
distribution platforms" phrasing dilutes the scope limitation that makes the exception defensible.
If approved, CONTRIBUTING.md §3 should be replaced by a pointer to the committed
`LICENSE-EXCEPTION-APPSTORE` file so there is exactly one text.

### Draft: `LICENSE-EXCEPTION-APPSTORE` (repo root, to commit verbatim on approval)

```
APPLE MAC APP STORE EXCEPTION
Additional permission under GNU GPL version 3 section 7

As a special exception, the copyright holders of Halbert grant you additional
permission under GNU GPL version 3 section 7 to convey the resulting object
code of this work through the Apple Mac App Store, notwithstanding sections 6
and 10 of the GNU General Public License version 3, and to accept the Apple
Media Services Terms and Conditions insofar as they apply to that conveyance.

This additional permission applies only to conveyance through the Apple Mac
App Store. It does not apply to any other means of conveying this work, and it
does not extend to any third-party code incorporated into this work whose
copyright holders have not granted an equivalent permission.

If you modify this work, you may extend this exception to your version, but you
are not obliged to do so. If you do not wish to extend it, delete this
paragraph from your version.

Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
```

### SPDX header form

The packet's proposed `GPL-3.0-or-later WITH MacAppStore-Exception` uses an identifier that is
not in the SPDX exception list; `WITH` requires a valid exception identifier or a LicenseRef.
**Recommended form** (also what the strategy doc §2.2 specifies):

```
SPDX-License-Identifier: GPL-3.0-or-later WITH LicenseRef-Halbert-AppStore-Exception
```

Apply to files compiled into the App Store target (halbert_core Python, src-tauri Rust/TS
sources) via `scripts/add_spdx_headers.py` once the exception file is committed. **Note:** a
tree-wide header rewrite is a large mechanical commit — it is staged work, not part of the
sign-off itself.

---

## FDR-DEC-03 — Bundle identifiers (three-way conflict; decision + diffs below)

Three incompatible schemes currently exist:

| Source | App Store build | Paid direct build | Internal/daemon |
|---|---|---|---|
| `FOUNDER-TODO.md` (FDR-DEC-03) | `ai.halbert.home` | `ai.halbert.pro` | `ai.halbert.dashboard` |
| `config/platforms.yml` | `ai.halbert.macos.free` | `ai.halbert.macos.pro` | — |
| `tauri.conf.json` (actual) | `ai.halbert.dashboard` (all targets) | same | same |

**Recommended:** adopt the FDR-DEC-03 scheme — `ai.halbert.home` (App Store), `ai.halbert.pro`
(direct DMG), `ai.halbert.dashboard` (the current OSS/internal identifier, unchanged). Rationale:
shorter, product-aligned, matches the announced product names, and keeps one stable identifier for
the internal build. On approval, the changes are:

```diff
# config/platforms.yml
-      bundle_id: "ai.halbert.macos.pro"
+      bundle_id: "ai.halbert.pro"
-      bundle_id: "ai.halbert.macos.free"
+      bundle_id: "ai.halbert.home"
```

`tauri.conf.json` stays `ai.halbert.dashboard` for dev builds; the per-channel identifiers are
injected at build time by `scripts/build-macos.sh --channel {macos-app-store,macos-pro}` (verify
the injection exists when Task 6.3 lands — if the script does not yet override the identifier
per channel, that override is the implementation work this decision unblocks). Entitlements:
per-channel `entitlements.mas.plist` (sandbox, network.client, device.microphone,
files.user-selected.read-write) and `entitlements.mac.plist` (Hardened Runtime, no sandbox) still
need creating under `src-tauri/` — staged work after the decision.

---

## FDR-DEC-04 — Halbert Pro commercial terms (drafted below)

### Draft: `documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md`

```markdown
# Halbert Pro — Commercial Terms & License Architecture

**Status:** DRAFT for founder approval (FDR-DEC-04)
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

## 1. The product

Halbert Pro is the paid, unsandboxed desktop edition of Halbert: direct
distribution (notarized DMG / MSI) through Lemon Squeezy, with Hardened
Runtime, multi-host fleet management, local Mac sysadmin tooling, and Sparkle
silent auto-updates. Halbert Core remains GPL-3.0-or-later forever; Pro is a
convenience-and-capability product on top of it, not a paywall on it.

## 2. Price

- **$29 one-time perpetual license** — launch promotion **$24** until
  {FOUNDER: set end date}.
- Includes **12 months of application updates** from the date of purchase.
- After the update window, the last-downloaded version keeps working
  indefinitely — the license never expires, and nothing phones home.
- Optional update renewal thereafter: **$12–$15/year** (founder to fix the
  number before launch).
- **No subscription, no SaaS tier.** Local-first software has zero recurring
  cloud cost; the pricing matches the self-hosted community ethos
  (open-core strategy §6.1).

## 3. License key architecture — offline Ed25519

- On purchase, the merchant webhook (Lemon Squeezy) generates an Ed25519-signed
  license key containing: product id, edition (Pro), purchase timestamp, and
  update-window expiry — signed with the **master private key**, which lives
  only on the merchant webhook server.
- The **public key is hardcoded into the Pro binary**. Activation and every
  update-window check verify the signature **locally** — zero telemetry, zero
  phone-home, no account.
- A valid key grants: perpetual use of every version released before the
  embedded update-window expiry. Later versions may be purchased via renewal;
  the app never disables itself.

## 4. What the license grants

- One perpetual license per purchase, for use by the purchaser on their
  personal machines.
- Source-code rights remain governed by GPL-3.0-or-later (Halbert is open
  core; buying Pro buys convenience and the bundled desktop experience, not
  different source rights).
- The GPLv3 §7 App Store exception does NOT apply to the Pro channel: direct
  distribution has no Apple terms to cure (app-store strategy §4).

## 5. Refunds & support

{FOUNDER: to set — recommended 14-day no-questions refund via Lemon Squeezy
defaults; community support via GitHub, no SLA.}
```

---

## Executive checklist after sign-off (from FOUNDER-TODO.md §2–3)

1. Commit `LICENSE-EXCEPTION-APPSTORE` + the CONTRIBUTING.md §3 pointer fix (FDR-DEC-02).
2. Ratify CONTRIBUTING.md licensing section (FDR-DEC-01) and the identifier scheme (FDR-DEC-03)
   — then the platforms.yml diff above.
3. Commit `HALBERT-PRO-COMMERCIAL-TERMS.md` with the founder-set values (FDR-DEC-04).
4. Tree-wide SPDX header update (`LicenseRef-Halbert-AppStore-Exception`) — staged mechanical work.
5. Infrastructure (founder-only): Apple Developer Program, Lemon Squeezy + Ed25519 keys,
   `EricBintner/halbert-ha-addon` repo.

**Everything above the line is drafted and ready; the decisions are the founder's.**