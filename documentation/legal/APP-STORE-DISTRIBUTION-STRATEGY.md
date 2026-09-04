# Mac App Store Distribution Strategy (GPLv3 §7 Exception)

**Date:** 2026-08-25
**Status:** Architecture complete; **§7 decisions taken 2026-09-04** — the channel is no longer a
licensing blocker. Remaining work is packaging code, tracked as `DIST-1` in `ROADMAP.md`.
**Covers:** `LEG-CRIT-03` — GPL-3.0 vs. Mac App Store conflict strategy
**Depends on:** `LEG-CRIT-02` (CLA / DCO relicensing rights)
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

---

## 1. The conflict, stated precisely

Halbert Core is GPL-3.0-or-later. Apple's Mac App Store imposes terms on
recipients of an application that GPLv3 forbids a distributor from imposing.
Two clauses collide:

**GPLv3 §6 — Installation Information.** Conveying object code in a "User
Product" obliges the distributor to supply the information required to install
and run modified versions on that product. Apple's signing and provisioning
regime means a recipient cannot install a modified build of an App Store app on
their own machine through the store's mechanism.

**GPLv3 §10 — No further restrictions.** "You may not impose any further
restrictions on the exercise of the rights granted or affirmed under this
License." The App Store's licence agreement restricts the number of devices, the
users, and redistribution — restrictions GPLv3 explicitly forbids a distributor
from adding. Apple's FairPlay DRM wrapper adds a technical restriction on top.

This is not a novel or contested reading; it is why VLC was removed from the iOS
App Store in 2011 and why GNU Go was removed in 2010. The Free Software
Foundation's position is settled. Shipping GPL-3.0 code to the Mac App Store
without addressing this is an infringement of the project's own licence — which,
uniquely, only the copyright holders can cure.

---

## 2. The remedy: a GPLv3 §7 additional permission

GPLv3 §7 lets copyright holders add "additional permissions" — terms that grant
rights beyond the licence's defaults. An App Store exception is the standard
instrument, used by projects that ship copyleft code through Apple's channels.

### 2.1 Proposed exception text

> **Apple Mac App Store Exception**
>
> As a special exception, the copyright holders of Halbert grant you additional
> permission under GNU GPL version 3 section 7 to convey the resulting object
> code of this work through the Apple Mac App Store, notwithstanding sections 6
> and 10 of the GNU General Public License version 3, and to accept the Apple
> Media Services Terms and Conditions insofar as they apply to that conveyance.
>
> This additional permission applies only to conveyance through the Apple Mac
> App Store. It does not apply to any other means of conveying this work, and it
> does not extend to any third-party code incorporated into this work whose
> copyright holders have not granted an equivalent permission.
>
> If you modify this work, you may extend this exception to your version, but you
> are not obliged to do so. If you do not wish to extend it, delete this
> paragraph from your version.

The final clause is deliberate: it preserves a downstream fork's freedom to drop
the exception, which is what keeps the grant *additional* rather than
restrictive.

### 2.2 Where it goes

| Location | Content |
|----------|---------|
| `LICENSE-EXCEPTION-APPSTORE` (repo root) | The exception text, verbatim |
| `LICENSE` | Unchanged GPL-3.0 text, with a pointer to the exception file |
| `README.md` licensing section | One paragraph, linking both |
| SPDX headers on covered source files | `GPL-3.0-or-later WITH LicenseRef-Halbert-AppStore-Exception` |
| `documentation/contributing/CONTRIBUTING.md` | Contributors grant the exception on their contributions |

The SPDX form matters: a per-file `WITH` clause is how an automated scanner —
and a future maintainer — knows which files are covered and which are not.

---

## 3. Who can actually grant it

**Only the copyright holders.** Today that is Eric Bintner, sole author, so the
grant is his to make unilaterally. That will stop being true the moment the first
external contribution lands under the current inbound=outbound GPL-3.0 terms in
`CONTRIBUTING.md`, which convey no relicensing or exception-granting right.

After that point, adding or amending this exception needs the agreement of every
contributor whose code is in the App Store target. That is the fragmentation
`LEG-CRIT-02` exists to prevent.

**This is a sequencing constraint, not a paperwork detail.** The CLA/DCO decision
must land *before* the project accepts external contributions, or the App Store
channel becomes progressively harder to open and eventually impossible without
tracking down every past contributor.

---

## 4. Open-core boundary: what the App Store binary actually contains

The exception covers Halbert's own code. It cannot be granted over anyone else's.
So the App Store target must be architecturally constrained, not just legally
papered over.

`config/platforms.yml` already defines the App Store build as a **sandboxed
companion client** (`ai.halbert.macos.free`), distinct from the unsandboxed
`macos-pro` build sold through LemonSqueezy. That distinction is the boundary.

```
                        ┌──────────────────────────────────────────┐
                        │  Halbert Core (GPL-3.0-or-later)          │
                        │  agents · RAG · policy · runtime          │
                        │  + App Store exception                    │
                        └──────────────────┬───────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
   ┌──────────▼──────────┐      ┌──────────▼──────────┐      ┌─────────▼──────────┐
   │ oss-linux           │      │ macos-pro           │      │ macos-app-store    │
   │ AppImage/deb/rpm    │      │ LemonSqueezy, paid  │      │ sandboxed, free    │
   │ GPL-3.0, no DRM     │      │ unsandboxed, no DRM │      │ Apple DRM          │
   │ no exception needed │      │ no exception needed │      │ EXCEPTION REQUIRED │
   │ copyleft corpus OK  │      │ no CC BY-NC         │      │ no CC BY-NC        │
   │                     │      │                     │      │ no strong copyleft │
   └─────────────────────┘      └─────────────────────┘      └────────────────────┘
```

Note that `macos-pro` needs **no** exception: LemonSqueezy is direct
distribution with no DRM and no additional restrictions on recipients. Selling
GPL software is explicitly permitted. Only the App Store channel has the problem,
and only because of Apple's terms.

### 4.1 Constraints on the App Store target

| Constraint | Why | Enforced by |
|------------|-----|-------------|
| No strong-copyleft third-party library linked in | The §7 exception cannot cover someone else's GPL code | `scripts/check_appstore_deps.py` |
| No weak-copyleft library statically linked | LGPL relinking obligations are unsatisfiable inside App Store DRM | same |
| No GNU FDL corpus content | GFDL 1.3 §2 forbids the technical measures Apple applies | `scripts/corpus_license_gate.py` |
| No CC BY-NC corpus content | Paid-channel adjacency; non-commercial terms | same |
| No privileged helper, no `polkit`, no daemon install | App Sandbox forbids it | Apple review |

The first two are checked automatically on every `--channel macos-app-store`
build. `scripts/build-macos.sh` refuses to package if either fails.

### 4.2 The one copyleft dependency in the tree

`systemd-python` is LGPL-2.1-or-later. It is guarded in `halbert_core/pyproject.toml`
by `platform_system == 'Linux'`, so pip never installs it on macOS, and
`scripts/build-macos.sh` passes `--exclude-module systemd` to PyInstaller as a
second line of defence. `check_appstore_deps.py` verifies that the marker is
still present rather than trusting the convention — remove the marker and the
App Store build fails, by design.

`pyinstaller` is GPL-2.0-or-later but build-time only, and its bootloader carries
a linking exception explicitly permitting distribution of frozen applications
under any licence. Nothing of PyInstaller's own GPL code reaches the shipped
binary beyond that exception-covered bootloader.

Everything else across Python, Rust and npm is MIT, BSD, Apache-2.0 or ISC. The
full register is `config/dependency-licenses.yml`.

### 4.3 Sandbox isolation

The App Store client is sandboxed (`com.apple.security.app-sandbox`). This is a
legal constraint as much as a technical one: a sandboxed app cannot do the
privileged system administration that makes Halbert Pro valuable, which is
precisely what keeps the two products distinct and the open-core boundary honest.

The App Store client is a **remote companion**: it connects to a Halbert instance
running elsewhere (a Linux server, a home lab, or a Pro install on the same Mac)
and provides chat, monitoring and a terminal. It does not administer the Mac it
runs on.

Entitlements the App Store target needs:

```xml
<key>com.apple.security.app-sandbox</key><true/>
<key>com.apple.security.network.client</key><true/>
<key>com.apple.security.files.user-selected.read-write</key><true/>
```

Entitlements it must **not** request, because they contradict either the sandbox
or the product boundary: `com.apple.security.temporary-exception.*`,
`com.apple.security.inherit` for privileged helpers, and any Full Disk Access
equivalent.

`src-tauri/tauri.conf.json` currently sets `macOS.entitlements: null` and a single
`ai.halbert.dashboard` identifier for all targets. Both need per-channel values
before submission — see §7.

---

## 5. What is *not* solved by the exception

The exception cures the §6/§10 conflict for Halbert's own code. It does not
address:

* **Corpus content licences.** GFDL and CC BY-NC restrictions are the upstream
  authors' terms, not Halbert's, and no exception the project grants can waive
  them. Handled separately by the corpus gate — see
  `documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md`.
* **Third-party code.** Covered by the dependency constraint in §4.1.
* **Model weights.** Ollama/MLX models are downloaded by the user at runtime, not
  bundled. Each model carries its own publisher terms and attribution
  obligations, which Halbert reads from the licence text the runtime ships with
  the model (`LEG-MOD-04`). Bundling weights into an App Store build would open
  a separate licensing question and should not be done without reviewing each
  bundled model's licence.
* **Apple's own review requirements.** Independent of licensing, and independently
  capable of rejecting the build.

---

## 6. Sequencing

```
LEG-CRIT-02  CLA / DCO decision              ─┐
                                              ├─→  §7 exception can be granted durably
LEG-CRIT-03  Founder approves exception text ─┘
                    │
                    ├─→  LICENSE-EXCEPTION-APPSTORE committed
                    ├─→  SPDX headers updated on covered files
                    ├─→  CONTRIBUTING.md updated
                    │
                    └─→  App Store target buildable:
                             scripts/build-macos.sh --channel macos-app-store
                                 ├── corpus gate      (automated, passing)
                                 ├── dependency gate  (automated, passing)
                                 ├── per-channel bundle id + entitlements  (TODO)
                                 └── notarization + submission
```

The two automated gates are implemented and passing today. Everything downstream
of them is blocked on the founder decision.

---

## 7. Decisions required from the founder

**All four were taken on 2026-09-04.** Recorded in `DECISIONS.md` as `FDR-01`, `FDR-02`,
`FDR-03` and `FDR-07`; the reasoning is kept below because the constraints still bind.

1. **§7 exception text — approved as written in §2.1**, and committed verbatim to
   `LICENSE-EXCEPTION-APPSTORE` at the repository root. That file is now the sole
   operative grant; `CONTRIBUTING.md` and the distribution-channels doc point at it
   instead of paraphrasing, and `tests/test_appstore_exception_single_source.py`
   fails the build if a second wording reappears. The warning that motivated the
   single-sourcing stands: once builds are conveyed under a text, that text cannot
   be quietly retracted for versions already shipped. Counsel review before first
   submission remains advisable.

2. **`LEG-CRIT-02` — DCO with an explicit relicensing grant**, not a full CLA. The
   text was already in `CONTRIBUTING.md` and already enforced by
   `.github/workflows/dco.yml`; 2026-09-04 ratified it. Lighter contributor friction,
   sufficient for a single-maintainer project.

3. **The App Store client stays a sandboxed remote companion** (`FDR-07`). The whole
   open-core boundary rests on this. If the App Store build ever grows local
   administration features, the licensing analysis, the entitlements and the product
   differentiation all have to be redone.

4. **Bundle identifiers reconciled** (`FDR-03`): `ai.halbert.home` (App Store),
   `ai.halbert.pro` (direct DMG), `ai.halbert.dashboard` (dev, internal and Linux —
   matching the already-published flatpak app-id rather than renaming it).
   **Not yet applied:** `config/platforms.yml` still says `ai.halbert.macos.*`, and
   `scripts/build-macos.sh` still has no per-channel identifier or entitlements
   injection. Per-channel entitlements files (§4.3) do not exist yet. That is the
   `DIST-1` work.

### Still open

* **`FDR-04`** — Halbert Pro's price, update window, renewal, refund policy and device
  count, and then `HALBERT-PRO-COMMERCIAL-TERMS.md`. This blocks the Pro *product*
  (licence keys, Sparkle, Lemon Squeezy). It does **not** block either build channel.
* **`FDR-05` / `FDR-06`** — copyright first year, and confirming `-or-later` over
  `-only`. Each is a one-word answer that becomes expensive after external
  contributions land.
* **The SPDX `WITH LicenseRef-Halbert-AppStore-Exception` header rewrite** across
  ~1,036 files — deliberately deferred as a large mechanical commit.

A note on mechanism, decided alongside the above: because the core is
`GPL-3.0-or-later`, a recipient receives the source and may remove a licence check,
so per-feature gating of core code is not durably enforceable. The enforceable paid
artifact is the signed, notarized, auto-updating binary and its update stream.

---

---

## 8. Related

* `documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md` — corpus gate (`LEG-CRIT-01`, `LEG-MAJ-05`)
* `documentation/legal/LEGAL-AND-LICENSING-TODO.md` — master action plan
* `config/dependency-licenses.yml` — third-party licence register
* `config/platforms.yml` — per-channel build configuration
* `scripts/check_appstore_deps.py` — dependency copyleft gate
