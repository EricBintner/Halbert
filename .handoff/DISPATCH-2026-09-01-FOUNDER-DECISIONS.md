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
| `LEG-GATE` | The App Store dependency-licence gate is red (10 unclassified deps). SONNET-05 classifies them; you decide only if one turns out copyleft (`opencv-python` wheels bundle FFmpeg; `pyacoustid` needs chromaprint; `webrtc-audio-processing` crate licence) | App Store build | classify; escalate copyleft |
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
| `RAG-13` | 13 corpus JSONL files (71 MB) are gitignored; track them, or publish the HF datasets and make onboarding download them | publish HF + download |
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
- `RAG-05`/`U4-14`: re-apply the template to the live daemon after `assigned_to_role` lands; `U4-08`: re-embed after the CUDA doc moves.
- `RAG-01`: commit the daemon-side scope fixes in the CoDRAG checkout (`/Volumes/4TB-BAD/HumanAI/CoDRAG`, uncommitted `search.py`/`models.py`/`index.py` edits the running daemon depends on) — a clean daemon launch silently reverts Halbert to 1-chunk file-head responses.
- `SEC-14`: the SourcePrep daemon answers `/projects` without a bearer (CoDRAG).
- `MD-05`: something re-created `dashboard/frontend/src/components/brand/HalbertMark.tsx` at 08:41 today (deleted on main in `493956ab`) alongside the 35 SVGs — identify which tool/session did it so it does not recur.
