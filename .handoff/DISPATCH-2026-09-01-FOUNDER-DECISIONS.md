# Founder Decisions — everything the 2026-09-01 audit found that only you can close

**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §7. Each row: what is undecided, what is blocked on it, the default the packets will assume if you say nothing. Evidence ids index `.handoff/audit-2026-09-01/AUDIT-FINDINGS-DETAIL.md`. Drafts for the legal items: `.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md`.

## A. Gates on shipping and security (decide first)

| Id | Decision | Blocks | Default assumed |
|---|---|---|---|
| `SEC-05` | After merging `feat/security-review-01`, MCP config queries fail closed on any host whose `latest.json` is empty — on macOS the ConfigWatcher never runs, so MCP config tools refuse until a snapshot is taken. Accept fail-closed and add a first-run/onboarding snapshot step (recommended), or relax to an allow-root policy? | SONNET-01 merge lands either way; the macOS UX depends on this | Fail-closed + tool-description note; snapshot step filed as follow-up |
| `FDR-01` | Ratify DCO-with-relicensing-grant (text already in `CONTRIBUTING.md`) vs a full CLA | inbound licence posture | none — remains open |
| `FDR-02` | One §7 App Store exception text (two conflicting texts live: `CONTRIBUTING.md:320` vs `APP-STORE-DISTRIBUTION-STRATEGY.md` §2.1); commit `LICENSE-EXCEPTION-APPSTORE`; SPDX `WITH` form | App Store build | none |
| `FDR-03` | Bundle identifiers (three schemes in flight + a fourth linux id; `tauri.conf.json` hard-codes `ai.halbert.dashboard` for every target; no entitlements; `scripts/build-macos.sh` has no per-channel injection) | App Store + Pro packaging | none |
| `FDR-04` | Pro pricing/update window/renewal/refund/device count; commit `HALBERT-PRO-COMMERCIAL-TERMS.md`; Ed25519 offline keys; Lemon Squeezy EULA | Pro channel | none |
| `FDR-05/06` | Copyright first year 2024 vs 2025; outbound licence stays `GPL-3.0-or-later` | headers | keep as is |
| `FDR-07` | App Store build stays a sandboxed remote companion (open-core boundary) | packaging | yes |
| `FDR-08` | `macos-private-api` (transparent floating voice HUD) — acceptable in the App Store target or Pro-channel only? | HUD ship channel; `VM-28`, `U2-29` | Pro-only |
| `LEG-GATE` | **Resolved by SONNET-05 (2026-09-02)** — gate is green (`config/dependency-licenses.yml`, `test_corpus_license_gate.py` 51/51). `webrtc-audio-processing`'s crate licence was verified BSD-3-Clause (not a concern). Two items still need your call — see "SONNET-05 additions" below: `opencv-python` bundling LGPL FFmpeg in its wheel, `openwakeword`'s default pretrained models being CC-BY-NC | App Store build | see below |
| `R9-F01` | Wyoming server: default disabled, or loopback-only unless a token is configured? | OPUS-02 Task 3 | loopback + token required |
| `R10-F1`/`SE-16` | Pairing confirmation lives on the desktop UI (WS event) — confirm that surface | OPUS-03 Task 3 | desktop confirmation + 60 s PIN expiry |

## B. Feature scope calls ("finish current features" needs a yes/no on each)

| Id | Decision | Default |
|---|---|---|
| `SE-05` | Wire `ComputeRouter.route()` (cloud > local > peer > WoL > template) into the turn path, or leave it a Phase 9.3 decision layer | wire for the HOME variant only |
| `VM-STT` | Confirm spoken-input → agent-turn is in scope now (no task in doc 16 owns it) | yes (OPUS-02 Task 2) |
| `VM-22` | Python consumer for the Rust AEC loopback socket 18400 — build, or mark `audio_capture.rs` dormant given the browser-is-the-audio-terminal decision | dormant |
| `VM-01/02` | Voice: is getUserMedia-denied a full machine `error` for keyboard-only users? Severity-2 acoustic wakes still suppressed by the "quiet" dial/safe mode? | keep v1 behaviour |
| `R04-POOL` | Enable the agent PTY pool at startup (after `R04-F3/F4`) or keep the subprocess executor and mark B7 unshipped | keep subprocess; mark B7 unshipped |
| `R04-F2`/`TERM-08` | Wire the watched-shell → thread pipeline and mount `TasksColumn`/`YourShellRegion` (the terminal direction: shells watched by the AI, indicator lights), or relabel B7/B8/B9/B22/C1a–d as built-unwired and remove dead endpoints | relabel now; wiring is a named follow-up |
| `LOOP-01` | `HomeCognitiveLoop`: instantiate at startup gated on the home capability (draft saved by SONNET-02), or delete it and the HA-strategy claims that it is "the automation engine" | instantiate (feature-complete path) |
| `U6-DESIGN-01` | Registry "probe beats preset" silently re-enables SourcePrep on home nodes where the package is importable; U6 says home never uses it | explicit False override on home unless `being.yml` opts in |
| `U4-20` | Build the Swift FoundationModels bridge sidecar (no source exists anywhere), or hide `apple-foundation` until it exists | hide until built |
| `RAG-13` | 13 corpus JSONL files (71 MB) are gitignored — **bigger than it sounds, see the "SONNET-05 additions" note below**: those 13 files are 4 entire manifest sources, ~half the corpus by document count; track them, or publish the HF datasets and make onboarding download them | publish HF + download |
| `RAG-14` | How a new install obtains the ~20-hour knowledge index: ship the built index (≈490 MB) as a release/HF asset, or a UI-driven background build | ship as asset |
| `RAG-21` | Two knowledge systems still exposed: legacy ChromaDB doc indexing (`routes/rag.py`, Settings › docs, CLI `rag-add`) no longer feeds the agent — retire it? | retire |
| `R08-01` | GPU/Containers/Development/Network/Sharing/Apps pages: re-rail, sub-views, or remove routes | re-rail under "System" |
| `CC-02` | SendToChat "new conversation" affordance: implement `new_thread` or remove | remove (one seamless chat) |
| `ORPHAN-02` | Frigate: 8 backend routes + a backend-served SPA route with zero frontend code — keep? | keep, mark backend-only |
| `RNC-11`/`HA-01` | Keep `feat/rust-native-core` parked (recommended; push it as backup) and record the Rust deferral in `MASTER-TODO`/the scoping doc, which still say "start R0/R1 now" | park + record |
| `RNC-06` | Same-path doc collision: commit main's sanity review under the current name and rename the branch's external-review file later (a), or rename main's now (b) | (a) |
| `MD-04` | Adopt the 7-line mark as primary and 4-line as micro? (story labels them "Proposed") | undecided; code defaults unchanged |
| `VMK-09` | Brand SVG naming: keep tier names + add 5/7/8 (a), or migrate everything to numeric `{N}lines` names (b) | (a) |
| `U3-26` | The gitignored 283-line chat-UI precursor doc in the `chat-ui-audit` worktree: subsumed by `documentation/design/11-…`? | subsumed; discard |
| `ENV-01` | Python floor: 3.10 (metadata/venv/PKGBUILD) or 3.11 (README/INSTALLATION/CI/handoff) | stay 3.10; fix docs |
| `SEM-01..03` | Terminology forks: "Self" vs "Identity" for "The Being"; "Compute Mesh" vs "Mesh Computing" vs "Continuity Grid"; "Unified Mode" vs "One Halbert" vs "Shared Presence" (UI says "Singular Entity"/"Independent Node"). Rename cost grows with each merge | none |
| `MKT-01` | Marketing web-v7 messaging Q1–Q8; the early-access form is a client-side no-op (`MKT-03`) — wire to a real sink or remove the success message | remove success message until a sink exists |
| `U6-D2/D4/Q3/Q4` | Ratify the AI-resolved U6 decisions already merged: <4 GB = offload-only (4 GB stays local-capable); home-light merged into home; keep `vision_model`; keep `advance_turn` (its premise "haloysius is always present" contradicts `pyproject`'s own cognition-extra comment) | ratified as merged |
| `SEC-03` | Retarget the unredacted rebuild script to the unified `halbert` project (recommended) vs a second legacy project | retarget |

## C. Runs that need your hardware or your queue
- `HW-01`/`VM-15`: 22-row hardware validation matrix on the N150 + 10" touch panel (0 results; notes claiming P2/O3/O5 unbuilt are stale).
- `HW-02/03/04`: N150 procurement checklist; N150 install checklist (references the removed `home-light`); N150 ↔ compute-host peer-offload checklist (all prerequisites on main after OPUS-03).
- `SE-28`: one real two-machine LAN validation of pairing + compute peer.
- `VM-27`: one real-audio run of `/voice` (sherpa-onnx extra + Piper voice).
- `SEC-04`: the unredacted SourcePrep rebuild (SONNET-01 retargets the script; run while locked, never concurrently with another build).
- `RAG-05`/`U4-14`: **ready now** — `assigned_to_role` landed this session (`sourceprep_template.yml`, 4 role mappings + tests, see the SONNET-05 results doc). Re-apply the template to the live daemon (`SourcePrepSetup().apply()`) whenever it's next safe to touch (it was reported wedged this session, see below).
- `U4-08`: **ready now** — the CUDA compatibility doc moved to `data/linux/nvidia-docs/nvidia_cuda_compatibility.jsonl` and was force-added past the `*.jsonl` gitignore trap (see `RAG-13` note below — do not assume a new corpus file is tracked without checking). Re-embed (stage 2 of `scripts/staged_knowledge_embed.py`, or a full `apply()` re-run) whenever next safe.
- `RAG-01`: commit the daemon-side scope fixes in the CoDRAG checkout (`/Volumes/4TB-BAD/HumanAI/CoDRAG`, uncommitted `search.py` +85/`models.py` +1/`index.py` +6 edits the running daemon depends on) — a clean daemon launch silently reverts Halbert to 1-chunk file-head responses. Re-confirmed 2026-09-02: still uncommitted, and two more files have drifted uncommitted since the original audit (`scripts/dev.sh`, `src/prep/dashboard/vite.config.ts`) — not reviewed for content, just flagged as present.
- **Daemon health (new, 2026-09-02):** SONNET-01 found the SourcePrep daemon's `/status` endpoint hanging and `pipeline/status`'s `any_running` flag stuck `true` for over an hour with no CPU activity — likely needs a `prep.cli serve` restart before any of the three re-embed/re-apply items above can run safely. Not restarted this session (shared infrastructure, ~9 other concurrent `prep mcp` clients).
- `SEC-14`: the SourcePrep daemon answers `/projects` without a bearer (CoDRAG).
- `MD-05`: something re-created `dashboard/frontend/src/components/brand/HalbertMark.tsx` at 08:41 today (deleted on main in `493956ab`) alongside the 35 SVGs — identify which tool/session did it so it does not recur.

## SONNET-05 additions (2026-09-02, doc/CI/licence/knowledge-index dispatch)

**Licence classifications (`LEG-GATE`, resolved) — decide only the flagged item:**
All 9 previously-unclassified dependencies are now registered in
`config/dependency-licenses.yml`, sourced from PyPI/crates.io metadata and,
for two ambiguous ones, primary source (fetched COPYING files directly).
`test_corpus_license_gate.py` is 51/51, `scripts/check_appstore_deps.py`
passes clean. Full sourcing notes live inline in the register; summary:

| Dependency | Licence | Needs your call? |
|---|---|---|
| `mss` (python) | MIT | No |
| `sherpa-onnx` (python) | Apache-2.0 | No |
| `openwakeword` (python) | Apache-2.0 (code) | **Yes, see below** |
| `pyacoustid` (python) | MIT | No (chromaprint note below, not a blocker today) |
| `cpal` (rust) | Apache-2.0 | No |
| `webrtc-audio-processing` (rust) | BSD-3-Clause | No — verified, not the `LEG-GATE` row's flagged concern (see below) |
| `@halbert/design-system`, `@halbert/model-picker` (npm) | First-party, `LicenseRef-Halbert-FirstParty` | No |
| `opencv-python` (python) | Apache-2.0 (code) | **Yes, see below** |

1. **`opencv-python` bundling LGPL FFmpeg** — its own code is Apache-2.0
   (permissive), but the published PyPI wheels are documented
   (opencv/opencv-python#353) to bundle an FFmpeg build under LGPL-2.1 (Qt5
   under LGPL-3.0 too, on non-headless Linux wheels only). This register's
   SPDX-classification model can only see a package's own declared licence —
   it cannot see what's bundled inside a wheel, so it will never catch this
   automatically. Two things need your call before shipping the `vision`
   extra in an App Store build: (a) whether the macOS wheel actually used is
   the one bundling FFmpeg or a `WITH_FFMPEG=OFF` build relying on
   AVFoundation instead, and (b) if FFmpeg is bundled, whether it's linked
   dynamically (satisfies LGPL's relink obligation) or statically, and
   whether App Store code-signing/sandboxing breaks a user's practical
   ability to relink. Full notes: `config/dependency-licenses.yml`'s
   `opencv-python` entry.
2. **`openwakeword`'s default pretrained models are CC-BY-NC** — its own
   code is Apache-2.0 (fine), but its documented default wake-word models
   use CC-BY-NC-4.0/CC-BY-NC-SA-4.0 due to training-data restrictions. This
   is a content-licensing question analogous to the SS64 corpus quarantine
   (`LEG-CRIT-01`), not a code-copyleft one — `check_appstore_deps.py`
   cannot see it at all (it only reads package manifests, not what a
   package downloads at runtime). Halbert's own `pyproject.toml` extra
   comment says the wake-word feature "requires a trained 'Hey Halbert'
   model" — i.e. a custom-trained model, not the stock ones — but confirm
   no default pretrained model ships or auto-downloads in a commercial
   build before this extra reaches a release channel.
3. **`webrtc-audio-processing` — resolved, no action needed.** crates.io
   flags it "non-standard" only because its `Cargo.toml` uses
   `license-file = "COPYING"` instead of an SPDX string; fetched the actual
   COPYING files (both the Rust crate's and the vendored C++ library's, a
   PulseAudio fork of Google's original) directly and both are verbatim
   BSD-3-Clause. Nothing to decide here — listed only so the `LEG-GATE`
   row above doesn't read as still-open on this point.
4. **`pyacoustid`/chromaprint — not a blocker, flagged for awareness.**
   chromaprint (the separately-installed system library pyacoustid calls at
   runtime, never a pip dependency) is MIT for its own code but
   incorporates LGPL-2.1 FFmpeg fragments and is commonly described as LGPL
   as a whole. Nothing in this repo bundles a compiled chromaprint binary
   today — users provide their own (e.g. via Homebrew) — so there is
   nothing to decide now. Only relevant if a future build ever
   vendors/statically links chromaprint instead of dynamically loading the
   user's system copy.

**Knowledge-index plumbing (`U4-08`, `RAG-06`/`U4-14`) — code done, run
pending your queue, see §C above for the exact re-embed/re-apply steps and
the daemon-health caveat blocking them right now.**

**Role-scope mapping gap, not a decision item, just a heads-up:** of
`config/roles.py`'s 9 `*_admin` scopes, only 4
(network/service/storage/security) have a matching `skills/builtin/*/SKILL.md`
role today; `credentials_admin`/`shell_admin`/`package_admin`/`boot_admin`/
`sharing_admin` stage real host config but no skill names them, so a query
scoped to one of those roles still falls back to the keyword heuristic (not
wrong, just not as precise as it could be). If a future skill is added for
one of those domains, it needs its own `assigned_to_role` entry added to
`sourceprep_template.yml` — this isn't blocked on anything, just not done
because no such skill exists yet.

**`RAG-13` is bigger than the original audit's phrasing suggested.** "13
corpus JSONL files (71 MB) gitignored" underclaims it: verified today that
those 13 files are **four entire manifest sources** — `arch_wiki` (2,397
docs), `tldr_pages` (7,049 docs, split across all four platform
subdirectories), `macos_man_pages` (5,280 docs), and six of `common_tools`'
seven files (68 docs) — roughly **half of the corpus's claimed 28,869
documents**, present only on `/Volumes/4TB-BAD/Halbert`'s local disk, never
in git history on any branch. Full file list and sizes now in
`documentation/RAG-DATA-SOURCES-2026-08-24.md` §1.1. This raises the
stakes on the existing `RAG-13` decision (track them vs. publish+download
via HuggingFace) — a fresh clone today builds half a knowledge base with no
error or warning.

**`RAG-07` — daemon API limitation, not fixed, needs CoDRAG-side work.**
`_reconcile_scopes` in `sourceprep_setup.py` computes which corpus paths to
add/remove from a scope by diffing against the daemon's `GET
/projects/{id}/scopes` response — but that response's per-scope objects
carry `path_count` (an int), not the actual `paths` list, so the diff always
reads "nothing currently assigned" and can never remove a path a template
stopped listing (it keeps re-adding the full wanted list every run, which
looks idempotent but silently can't shrink). No per-scope detail endpoint
exists in this client to fix it against, and confirming whether the daemon
has one at all needs a live, healthy daemon to probe — deferred this
session (daemon reported wedged, see the note above). Documented in the
code (`sourceprep_setup.py::_reconcile_scopes` docstring) rather than
guessed at; likely needs a CoDRAG-side response-shape change.
