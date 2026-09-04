# Halbert Distribution Channels & Open-Core Boundary

**Date:** 2026-09-04 (rewritten; supersedes the 2026-08-29 draft of the same name)
**Status:** Decided where marked; open items name their blocker
**Canonical for the legal analysis:** [`APP-STORE-DISTRIBUTION-STRATEGY.md`](APP-STORE-DISTRIBUTION-STRATEGY.md)
**Design of record:** `.handoff/HANDOFF-DISTRIBUTION-CHANNELS-2026-09-04.md`
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

---

## 1. What this document is

Halbert is a local-first AI assistant that identifies as the machine it runs on. It
is distributed as free software and it is also sold. This document says how those
two facts fit together: which build channels exist, what each one may contain, and
which questions are settled versus still open.

The 2026-08-29 draft this replaces asserted prices, a product matrix, a contributor
licence posture and a bundle-identifier scheme as though all were settled. They were
not; `DECISIONS.md` recorded every one of them as open. This rewrite keeps what was
true, closes what could be closed, and marks the rest honestly.

## 2. Two nouns that are not the same noun

Conflating these is why the previous draft and `config/platforms.yml` disagreed with
each other and with the code. They are kept apart deliberately:

| Term | Kind | Means |
|---|---|---|
| `macos-app-store` | **build channel** | Sandboxed, Mac App Store provisioned, no private API. A `scripts/build-macos.sh --channel` value. |
| `macos-pro` | **build channel** | Unsandboxed, Hardened Runtime, Developer ID signed, direct DMG. Also a `--channel` value. |
| **Halbert Home** | **product** | The free sandboxed remote companion shipped through the App Store channel. |
| **Halbert Pro** | **product** | What is sold through the direct channel. Price and terms are `FDR-04`, still open. |

A channel can exist, build and pass its gates before its product's commercial terms
exist. That is precisely the state this document describes: the channels are being
made real now; Halbert Pro's terms are not yet set.

## 3. A constraint on where the paid line can go

Halbert core is `GPL-3.0-or-later`. Anyone who receives a binary also receives the
source, and may remove a licence check and redistribute the result. **Per-feature
licence gating of GPL code is therefore not durably enforceable.**

The enforceable paid artifact is the *signed, notarized, auto-updating binary and its
update stream* — the model Ardour and Krita use. Withholding features from the source
instead would require Pro-only code living outside the GPL core, which would end the
"the core is free software" claim this project makes.

This does not decide where the line goes. It bounds the mechanisms available when that
decision is taken, and it is recorded here so the decision is not taken in ignorance
of it.

## 4. The open-core boundary

**Decided (`FDR-07`): the App Store build stays a sandboxed remote companion.** It
connects to a Halbert instance running elsewhere — a Linux server, a home lab, or an
unsandboxed install on the same Mac — and provides conversation, monitoring and voice.
It does not administer the Mac it runs on.

Everything rests on this. If the App Store build ever grows local administration
features, the licensing analysis, the entitlements and the product differentiation all
have to be redone from the start.

The boundary is a *technical fact*, not a commercial preference: Apple's sandbox
forbids reading raw hardware sensors, spawning or managing system daemons, and
monitoring arbitrary root paths. That is the same line in both directions, which is
what makes it honest and stable.

**Deferred: which capabilities beyond that boundary are free versus paid.** The
previous draft listed the multi-host fleet cockpit as paid-only. That collides with the
2026-08-31 Singular Entity decision, which makes multi-body identity the core
architecture rather than an upsell. `NodeFleetCockpit.tsx` is written, tested and
mounted nowhere; mounting it is this commercial decision, not a wiring fix. Unresolved.

## 5. Channels

| | `macos-app-store` | `macos-pro` | Linux packages |
|---|---|---|---|
| Product | Halbert Home (free) | Halbert Pro (sold) | OSS core (free) |
| Sandbox | `com.apple.security.app-sandbox` | unsandboxed, Hardened Runtime | n/a |
| Bundle id | `ai.halbert.home` | `ai.halbert.pro` | `ai.halbert.dashboard` |
| Signing | Mac App Store provisioning | Developer ID + notarization | distro-native |
| Private API | **off** (`FDR-08`) | on | n/a |
| Licence | `GPL-3.0-or-later` + App Store §7 exception | `GPL-3.0-or-later` | `GPL-3.0-or-later` |
| Corpus | FDL/NC content barred by the gate | full | full |
| Updates | Mac App Store | Sparkle (Phase B) | distro package manager |

Dev and internal builds keep `ai.halbert.dashboard`; per-channel identifiers are
injected at build time.

### 5.1 What fits inside the sandbox

Entitlements the App Store target requests, and no others:

```
com.apple.security.app-sandbox
com.apple.security.network.client
com.apple.security.device.microphone
com.apple.security.files.user-selected.read-write
```

It must **not** request `com.apple.security.temporary-exception.*`,
`com.apple.security.inherit` for privileged helpers, or any Full Disk Access
equivalent — each contradicts either the sandbox or the product boundary in §4.

### 5.2 Private API (`FDR-08`)

The floating voice HUD needs a transparent window, which on macOS needs Tauri's
private-API path. Private API use is grounds for App Store rejection. **Decided: Pro
channel only.** The App Store build ships without it and the HUD degrades to an opaque
window rather than failing to open.

Note for whoever implements it: this is not one switch. `macos-private-api` is a
compile-time Cargo feature (`src-tauri/Cargo.toml`), `macOSPrivateApi` in
`tauri.conf.json` is only its runtime half, and `floating_panel.rs` calls
`.transparent(true)` unconditionally. Turning it off per channel needs a feature gate
and an opaque fallback path in Rust, not a JSON edit.

### 5.3 App Store review, beyond licensing

Apple's review can reject a build for reasons independent of any of the above.

* **Minimum functionality (4.2).** Halbert Home is submitted as a complete Home
  Assistant desktop companion, not a trial or a demo of something else.
* **Anti-steering (3.1.1).** The App Store build carries no link, button or text
  pointing at the paid direct download. Links to documentation and to the open-source
  project are ordinary and permitted. The website may describe the whole ecosystem;
  the shipped App Store binary may not.

## 6. Licensing

1. **Core:** `GPL-3.0-or-later`. Confirming it stays *or-later* rather than *only* is
   `FDR-06`, still open — a one-word answer that would otherwise require changing every
   statement and ~1,036 file headers.
2. **Mac App Store exception:** one text, at [`LICENSE-EXCEPTION-APPSTORE`](../../LICENSE-EXCEPTION-APPSTORE)
   in the repository root. It is scope-limited to conveyance through the Mac App Store,
   carves out third-party code, and may be dropped by a downstream fork — which is what
   keeps it an *additional permission* rather than a restriction. **Do not paraphrase it
   anywhere.** Three divergent wordings existed in this tree before 2026-09-04; a second
   wording is a second, different grant, and a text cannot be quietly retracted for
   builds already conveyed under it.
3. **Contributor terms (`FDR-01`, decided):** DCO 1.1 with an explicit commercial and
   App Store grant to the maintainer, in
   [`CONTRIBUTING.md`](../contributing/CONTRIBUTING.md), enforced by
   `.github/workflows/dco.yml`. A DCO rather than a full CLA: lighter contributor
   friction, sufficient for a single-maintainer project. Contributions accepted into the
   core repository remain available in source form under the GPL in perpetuity.
4. **Corpus content** is governed separately — no exception this project grants can
   waive an upstream author's terms. See
   [`CORPUS-LICENSING-ARCHITECTURE.md`](CORPUS-LICENSING-ARCHITECTURE.md).
5. **Model weights** are downloaded by the user at runtime, never bundled. Each carries
   its own publisher terms, read from the licence text the runtime ships with the model.

## 7. Where things actually stand

Written honestly, because the previous draft marked unbuilt things "Current".

**Exists and works:** the Python engine and agent; the local dashboard; the Home
Assistant client and config bridge; the Wyoming voice TCP server; Frigate MQTT event
ingestion; systemd units in `deploy/`; Linux packaging for Arch, Flatpak, Nix and Snap;
the corpus licence gate and the App Store dependency gate, both automated and passing.

**Does not exist yet:** any `Dockerfile` (there is none in the tree); a Home Assistant
add-on repository; apt/deb packaging; Developer ID certificates; notarization; licence
key verification; Sparkle; a Lemon Squeezy product.

**Works, but not yet compliant to ship.** `scripts/build-macos.sh` produces a bundle
and passes both licence gates, but it does not copy `LICENSE` or
`LICENSE-EXCEPTION-APPSTORE` into the `.app`. GPLv3 §4 requires conveying the licence
with the object code, and an additional permission reaches nobody who never receives
it. The `halbert license` notice likewise still says plain `GPL-3.0-or-later`. Both
are part of `DIST-1`; neither is a licensing question, both are packaging work.

**Deferred by earlier decisions:** Windows as a target (2026-08-31, HA strategy §8).

## 8. Sequencing

**Phase A — channels buildable.** One exception text committed and single-sourced; DCO
ratified; bundle identifiers reconciled across `platforms.yml`, `tauri.conf.json` and
the flatpak manifest; per-channel entitlements plists; identifier and entitlements
injection in `build-macos.sh`; the private-API split. Both channels are first-class
here — `macos-pro` is built and signed in this phase, not after it.

**Phase B — the Pro product.** Blocked on `FDR-04` (price, update window, renewal,
refund, device count) and on Apple Developer Program enrollment, both external to this
repository: Developer ID certificate and a real notarization run; Ed25519 offline
licence verification with a bundled public key and no phone-home; Sparkle appcast;
Lemon Squeezy product, webhook and EULA; `HALBERT-PRO-COMMERCIAL-TERMS.md`.

**Not scheduled:** per-feature tier gating (the line of §4 is deferred, and §3 suggests
it may never be the right mechanism); the tree-wide SPDX `WITH` header rewrite.

## 9. Related

* [`APP-STORE-DISTRIBUTION-STRATEGY.md`](APP-STORE-DISTRIBUTION-STRATEGY.md) — the GPLv3 §6/§10 analysis, the exception rationale, the dependency review
* [`CORPUS-LICENSING-ARCHITECTURE.md`](CORPUS-LICENSING-ARCHITECTURE.md) — corpus gate
* [`LEGAL-AND-LICENSING-TODO.md`](LEGAL-AND-LICENSING-TODO.md) — master action plan
* `config/platforms.yml` — per-channel build configuration
* `scripts/build-macos.sh`, `scripts/check_appstore_deps.py`, `scripts/corpus_license_gate.py`
