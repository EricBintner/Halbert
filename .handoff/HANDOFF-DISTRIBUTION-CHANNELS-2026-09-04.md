# macOS Distribution Channels — design

**Date:** 2026-09-04
**Status:** ACTIVE
**ROADMAP row:** `DIST-1`
**Founder approval:** given this session (open-core line deferred; legal blockers cleared now)
**Supersedes in part:** `documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` (2026-08-29)
**Canonical for legal:** `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` (2026-08-25)
**Closes:** `FDR-01`, `FDR-02`, `FDR-03`, `FDR-07`, `FDR-08`
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

---

## 1. Why this exists

The 2026-08-29 open-core strategy doc asserted a three-tier product matrix, prices,
a contributor licence posture and a bundle-identifier scheme as though they were
settled. `DECISIONS.md` recorded all of it as **open**. This design closes the
subset that is genuinely decidable today — the legal grants and the build-channel
plumbing — and states plainly what is still deferred and why.

Two founder decisions taken this session frame it:

1. **Where the free/paid feature line sits is deferred.** Halbert Pro remains a
   real product, sold through Lemon Squeezy, signed and notarized. What is not
   yet decided is which capabilities sit on which side.
2. **The legal blockers are cleared now**, out of band from the `ROADMAP.md` §3
   feature rows, because they gate accepting external pull requests and cost
   nothing from those rows.

## 2. A constraint that narrows the deferred decision

Halbert core is `GPL-3.0-or-later`. A recipient of any binary also receives the
source and may remove a licence check and redistribute the result. Per-feature
licence gating of GPL code is therefore not durably enforceable.

The enforceable paid artifact is **the signed, notarized, auto-updating binary and
its update stream** — the model Ardour and Krita use — not a feature set withheld
from the source. Gating features would require Pro-only code outside the GPL core,
which contradicts the "100% FOSS core" claim the strategy doc makes.

This does not decide where the line goes. It bounds the mechanisms available when
that decision is taken.

## 3. Two nouns that are not the same noun

The tree currently conflates these, and the conflation is why the strategy doc and
`platforms.yml` disagree:

| Term | Means |
|---|---|
| `macos-pro` | A **build channel**: unsandboxed, Hardened Runtime, Developer ID signed, distributed as a direct DMG. A `scripts/build-macos.sh --channel` value. |
| **Halbert Pro** | A **product**: what is sold through that channel. Its price, terms and licence mechanism are `FDR-04`, still open. |
| `macos-app-store` | A **build channel**: sandboxed, Mac App Store provisioned, no private API. |
| **Halbert Home** | A **product**: the free sandboxed remote companion shipped through that channel. |

A channel can exist and build cleanly before its product's commercial terms exist.
That is exactly the state after this work.

## 4. The open-core boundary, as far as it is decided

Decided (`FDR-07`): **the App Store build stays a sandboxed remote companion.** It
connects to a Halbert instance running elsewhere and does not administer the Mac it
runs on. The whole licensing analysis rests on this; if the App Store build ever
grows local administration, the analysis, the entitlements and the product
differentiation must all be redone.

Deferred: which capabilities beyond that boundary are free versus paid. Notably the
fleet cockpit — `NodeFleetCockpit.tsx` is written, tested and mounted nowhere. The
2026-08-29 doc lists it as Pro-only, which collides with the 2026-08-31 Singular
Entity decision making multi-body identity the core architecture. Not resolved here.

## 5. Units of work

Each unit is independently testable and independently revertible.

### Unit 1 — exactly one §7 exception text

Three texts exist today: `APP-STORE-DISTRIBUTION-STRATEGY.md` §2.1 (narrow,
considered, with a third-party carve-out and a fork-freedom clause),
`CONTRIBUTING.md` §3 (a broader paraphrase reaching "other digital distribution
platforms"), and `OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` §7.2 (a third, shorter
form). Publishing two different additional permissions is a live hazard: once
conveyed under a text it cannot be quietly retracted for versions already shipped.

- Commit `LICENSE-EXCEPTION-APPSTORE` at the repo root, verbatim from §2.1.
- Replace `CONTRIBUTING.md` §3 with a pointer to that file.
- Remove the third variant from the strategy doc.
- Add pointers from `LICENSE`, `README.md` §License, `documentation/legal/LICENSE.md`.
- **Test:** assert the tree contains exactly one exception text.

SPDX form is `GPL-3.0-or-later WITH LicenseRef-Halbert-AppStore-Exception`. The
tree-wide header rewrite that applies it to ~1,036 files is **explicitly deferred**
— it is a large mechanical commit that would collide with concurrent sessions.

### Unit 2 — ratify the DCO (`FDR-01`)

The DCO 1.1 text, the `Signed-off-by:` mechanics and the maintainer commercial
grant are already committed in `CONTRIBUTING.md` and already enforced by
`.github/workflows/dco.yml` + `scripts/check-dco.sh`. Nothing to draft; what is
missing is ratification. This unit is a `DECISIONS.md` row plus resolving the
"CLA vs DCO is open" language wherever it survives.

**Amendment made during execution.** `LEGAL-AND-LICENSING-TODO.md` §5.2 carries a
substantive caution that the original plan would have ticked past: DCO 1.1 certifies
provenance and contains no words of grant, so whether the §2 commercial grant
attached to the `Signed-off-by` trailer binds a *third-party* contributor is
unsettled. On the conservative reading the §7 exception is grantable only over the
founder's own copyright.

This costs nothing today — every commit in the repository is the founder's — and it
begins to bite the moment external code is merged into the App Store target. So the
caution is **carried forward and elevated**, not deleted: recorded on the
`LEG-CRIT-02` item with its two remedies (add a CLA with an assent step, or take
per-contributor permission for third-party code reaching the App Store target) and a
trigger — revisit at the first external pull request. Ratifying the DCO chose
option (b) knowingly; it did not make the analysis go away.

### Unit 3 — bundle identifiers (`FDR-03`)

| Target | Identifier |
|---|---|
| Mac App Store | `ai.halbert.home` |
| Direct DMG | `ai.halbert.pro` |
| Dev / internal | `ai.halbert.dashboard` |
| Linux packages | `ai.halbert.dashboard` |

`config/platforms.yml:226,239` currently says `ai.halbert.macos.pro` /
`ai.halbert.macos.free`; `tauri.conf.json:5` hard-codes `ai.halbert.dashboard` for
every target.

A fourth conflict the earlier drafts missed: `platforms.yml:216` gives linux
`ai.halbert.linux`, while the shipped flatpak manifest is
`packaging/flatpak/ai.halbert.dashboard.yml` with `app-id: ai.halbert.dashboard`.
Resolution: linux takes `ai.halbert.dashboard`, matching the published app-id
rather than renaming it.

`tauri.conf.json` keeps `ai.halbert.dashboard` for dev builds; per-channel
identifiers are injected at build time.

### Unit 4 — entitlements and per-channel injection

`scripts/build-macos.sh` has channel-aware corpus and dependency gates but **no
identifier or entitlements injection at all**. `tauri.conf.json` sets
`macOS.entitlements: null`.

- `src-tauri/entitlements.mas.plist` — `app-sandbox`, `network.client`,
  `device.microphone`, `files.user-selected.read-write`.
- `src-tauri/entitlements.mac.plist` — Hardened Runtime, no sandbox.
- Injection in `build-macos.sh` keyed on `--channel`, setting both the identifier
  and the entitlements file.
- Neither plist may request `temporary-exception.*`, `inherit` for privileged
  helpers, or any Full Disk Access equivalent — those contradict the sandbox or
  the product boundary.

Both channels are first-class here. `macos-pro` is built and signed in this phase.

### Unit 5 — private-API channel split (`FDR-08`)

`tauri.conf.json:13` sets `macOSPrivateApi: true`, which the floating voice HUD
needs for its transparent window (`floating_panel.rs:19` already flags the
conflict). Private API use is grounds for App Store rejection.

Decision: **Pro-only.** The App Store channel builds with the flag off and the
voice HUD degrades to an opaque window rather than failing to open. Gated by a test
asserting the App Store channel config has private API disabled.

### Unit 6 — correct the record

- Rewrite `OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` as a short, accurate
  distribution-channels doc: the two nouns of §3, the constraint of §2, the
  decided boundary of §4, and honest status on everything else. Remove the false
  "(Current)" claims (no Dockerfile exists in the tree; no HA add-on repo exists;
  no apt/deb packaging exists — `packaging/` has arch, flatpak, nix, polkit, snap,
  systemd only), the Windows MSI target (deferred by the 2026-08-31 HA strategy
  decision), the separate menu-bar app with iCloud profile sync (superseded by
  `ROADMAP.md:54` — same app, remote-client mode), the pricing section (`FDR-04`),
  and the third exception text.
- `DECISIONS.md`: `FDR-01`, `FDR-02`, `FDR-03`, `FDR-07`, `FDR-08` → decided.
  `FDR-04` → deferred with its blocker named. `FDR-05`, `FDR-06` stay open.
- `ROADMAP.md`: one row for the distribution channels, sequenced after `LD-1` and
  `TRUST-1`, recording that the legal blockers are cleared.
- `FOUNDER-TODO.md`: tick `FDR-DEC-01`, `-02`, `-03`.

## 6. Phase B — planned, not built here

Blocked on `FDR-04` (pricing, update window, renewal, refund, device count) and on
Apple Developer Program enrollment, both external to the repo:

- Developer ID Application certificate and a real notarization run.
- Ed25519 offline licence verification (zero telemetry, bundled public key).
- Sparkle appcast and silent updates.
- Lemon Squeezy product, webhook and EULA.
- `documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md`.

Named here so the sequencing survives; none of it is written in Phase A.

## 7. Out of scope

- Per-feature tier-gating machinery. The line is deferred, and §2 suggests it may
  never be the right mechanism.
- The tree-wide SPDX header rewrite.
- Anything about domain names.

## 8. Testing

| Unit | Test |
|---|---|
| 1 | `tests/test_appstore_exception_single_source.py` — the exception file exists and retains its three scope clauses; no paraphrase survives anywhere but the rationale doc. Verified non-vacuous by reintroducing a paraphrase and watching it fail. |
| 2 | `check-dco.sh` still passes; no "CLA vs DCO open" language survives |
| 3 | Every identifier in `platforms.yml` is one of the four agreed values |
| 4 | Both plists parse; the MAS plist requests only the four allowed entitlements and none of the forbidden ones; `build-macos.sh --gate-only` resolves an identifier and an entitlements path per channel |
| 5 | The App Store channel config has private API disabled |
| 6 | `tests/test_legal_metadata.py` stays green |
