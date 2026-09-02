# Halbert Roadmap

> **This is the only document that says now / next / deferred.** Root `TODO.md`, `.handoff/MASTER-TODO.md` §0/§3, the two 2026-08-29 master indexes, and the "Now" lists in the HA strategy and the experimental README are superseded by this file; they remain as history.
> **Rules:** (1) one doc says now/next/deferred; (2) a row moves only on evidence from a `.handoff/RESULTS-*.md` doc or a commit on `main`; (3) one owner resyncs; (4) every handoff carries a status from DRAFT / ACTIVE / LANDED / SUPERSEDED-BY / DEFERRED and a ROADMAP row id; (5) no bare "Phase N" — use the row ids below; (6) "done" means wired in production and tested, never "documented" or "code units exist".
> **Decisions** are logged in `DECISIONS.md`. Concept model and evidence: `documentation/design/CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md`.

## 1. Direction in force (2026-09-01, founder)

The full Rust rebuild is deferred and a Linux OS is far future. Current features get completed and tested first. "Current features" are the rows in §3.

## 2. Status snapshot (main `25ba6ab5`, 2026-09-02 morning)

| Gate | State |
|---|---|
| Python suite | 19 failed / 4,710 passed after SONNET-03 (remaining: cv2 extra ×13, licence gate ×2, `test_llm_config_parse_cache` ×2, `test_multi_instance` ×1, `test_frontend_no_relative_urls` ×1); root suite red on two SPDX headers |
| Frontend suites | design-system green, model-picker 103/103, dashboard green after SONNET-04 (+14 new test files), `tsc` clean, literal-colour ratchet re-baselined |
| CI | red until SONNET-05: `vision` extra not installed, SPDX headers |
| Merged since 2026-09-01 | shell redesign, Opus 01–05 batch, security-review-01 + SONNET-01 residuals (R1-F4, R2-P3/P4/P5), SONNET-02 cleanup, SONNET-03 (registry, secure-model gate, api-key redaction, tier-router cleanup), SONNET-04 (dead routes, approvals badge, ratchet, lazy tabs, dead affordances) |
| In flight | SONNET-05 (CI/tests/docs); alignment fix branches `fix/identity-block`, `fix/one-name`, `fix/frontend-presence-labels`, `fix/findings-surface`, `fix/background-runtime`, `fix/web-search-switch` (2026-09-02) |
| Open from SONNET-01 | the unredacted SourcePrep rebuild was not run (daemon `/status` hangs; restart `prep.cli serve` first); `SEC-14` daemon `/projects` unauthenticated (CoDRAG) |

## 3. Now — definition of done per workstream

| Id | Workstream | Definition of done | Status / evidence | Gating decision |
|---|---|---|---|---|
| CI-1 | CI green | Python suite green in CI with the `vision` extra; ratchet green; SPDX test green; census green | 26 local failures in SONNET-03/04/05 scope; SPDX `DEV-02` | — |
| ID-1 | Identity on every turn | `messages[0]` begins with name / platform / body / voice on chat, voice and MCP paths; one name resolver used by greeting, Presence Pill, MCP `serverInfo`; `identity.xml` no longer says "assistant" | Missing on the turn path (`C1-01`, `T1-01`); six name sources (`C1-02`) | `C1-02` identity rule (ratify) |
| ATTN-1 | Proof slice 1: proactive finding → conversation → proposal → approval → execution → receipt | A drop-in conflict on a synthetic `/etc` yields a finding with four whys, a conversation turn with off-ramps, a real diff proposal, approval with the critical phrase where due, an applied edit with backup, and a receipt in the timeline; CI e2e test | Detect/finding/gate wired; both joints missing (`J3-7`, `J3-10`, `C2-02`, `C2-11`, `J3-12`) | `C2-03` Finding is the unit of attention |
| ATTN-2 | Attention surface | `GET /api/findings`; `/findings` lists FindingStore findings; Dashboard `/` is the ranked attention list; attention state on the Presence Pill in every layout; morning report on by default at Balanced and persisted | `C2-03`, `C2-08`, `C2-10`, `C2-14`, `P1-10` | `T1-11` noun set |
| MIND-1 | Background work runs | Scheduler registers jobs (or the heartbeat replaces it); six-hourly sweep and morning report demonstrably run from the dashboard; `ThreadManager.tick` called; findings become worries; cognition persists across restart | Blocked: scheduler cannot register a job (`C4-01`); no unprompted tick (`C4-02`); Eyes do not feed the mind (`C4-04`); not persisted (`C4-05`) | `C4-10` heartbeat |
| STATE-1 | Proof slice 2: "how are you" with evidence | Deterministic Eyes pre-step (identity, vitals, open findings, recent changes) with citable observation ids before PLANNING; thresholds behind adjectives; macOS says when a sensor is unavailable; eval golden | Shape wired, grounding opportunistic (`J2-2`, `J2-3`, `P1-02`) | — |
| LEDGER-1 | Change ledger ("I remember why") | Every write path (approval execution, editor save, diff apply, watcher-observed change) records path, before/after, actor, reason; `recall_memory` answers "why is X configured this way" from it; config-diff shows before/after | Missing (`J4-1`, `J4-2`, `C2-15`, `A1-03`) | — |
| TRUST-1 | One trust chain | Chat executor has audit + dry-run/diff for mutations; unknown commands classify HIGH; one approvals API with the phrase gate on critical; XDG safe-mode flag consulted by every actor; web search and cloud are switches, off by default, visible in Settings; API keys masked on read; non-loopback bind refuses without a token | `C3-01/02/04/05/08/09/19` | `C3-14` single decide(); `C3-08`; `C3-19` |
| LD-1 | Linked Devices journey | Pair through Settings › Linked Devices with host-side approval (no YAML); token lands where the compute link reads it; active body persists across reload; canonical host reports Singular; `persona_id_override` written; `body_name` in the prompt; `PeerToolProxy` injected; one two-process test and one real two-machine run | Backend wired and tested; UI cannot complete it (`W4-02/03/05/06/09`, `W3-S04`, `A1-07`, `SE-28`) | `SE-05` ComputeRouter (recommend HOME only); `R2-F6` outbound token custody |
| SHELL-1 | Conversation sees the page | Page context injected into the turn; agent `navigate`/summon into the centre; proactive events in the timeline; Cmd+\ rail collapse; `/terminal` is a real PTY; shortcuts bail inside `.xterm`; run-from-Host-Focus does not pop the dashboard | Layout wired and green (`W5-SHELL-01`); links stubbed (`W5-CONV-02/03`, `W5-PROACT-01`, `W5-TERM-01`, `W5-KEYS-01/02`, `W5-BUG-01`) | — |
| TERM-1 | Terminals | Watched shell writes blocks, pool enabled at startup, TasksColumn/YourShellRegion mounted, legacy Terminal page retired, aggregate StatusLight in the top bar | Agent half real; user half unwired (`T-3/5/6/8`) | `R04-POOL` / `R04-F2` (recommend wire) |
| VOICE-1 | Voice Mode tested | One real-audio run (Piper voice + sherpa-onnx) with TTS/mark sync and a spoken round trip; `/voice` served by the appliance deployment; N150 matrix ≥ 1 pass recorded; banned labels off the surface | Chain wired overnight; 0 real-audio runs; `W3-S09`, `VM-27`, `VM-15`, `T1-05/06` | `VM-22`, `FDR-08` |
| HOME-1 | Home body | Env-only install gets the home preset; wizard peer prompt fires on home; HomeCognitiveLoop instantiated behind `CAP_HA_CONNECTION` with proposals through the why pipeline; Home page grouped by area with honest 403 handling; Frigate queue capped and snapshots routed to vision; Wyoming deploy docs match the new defaults; home proof slices 1H/2H defined | `W3-S01/S02/S07/S08/S11/S12/S13`, `U6-BUG-01/03/04` | `LOOP-01` (recommend instantiate); `W3-C07` v1 scope |
| CFG-1 | One config and data story | One path resolver; stores honour `HALBERT_DATA_DIR` at call time; `policy.yml` written and read from the same dir; typed `capabilities` on `BeingConfig` survive a Settings save; env as seed only; `HALOYSIUS_DATA_HOME` under `data_dir()` | `A2-01/02/03/04/08/19` | `A2-05` split being.yml (schedule after P0s) |
| GATE-1 | One gating model | `feature_flags.py` deleted; `is_home_variant()` callers replaced by capabilities; registry honours `HALBERT_VARIANT`; `CAP_SOURCEPREP` probes reachability; `CAP_WEB`/`CAP_CLOUD_LLM`/`CAP_PEER_COMPUTE` exist; circular secure-model gate fixed | SONNET-03 landed `fc55d245` (env variant, secure gate), `97d66158` (SourcePrep presence probe), `b338b599` (registry reset fixture); `CAP_WEB` in `fix/web-search-switch`; `feature_flags.py` and `is_home_variant()` callers still open (`A1-05`) | `U6-DESIGN-01` (implemented per default: home preset overrides probe) |
| MCP-1 | MCP usable | `get_findings`, `get_proposals`, `search_knowledge` work; identity in the configured voice; discoveries/events read persisted state or the server is mounted in the dashboard; `set_autonomy_level` uses the locked composite; id-less `tools/call` does not execute; macOS snapshot path decided | 7/18 tools work (`MCP-01..06`, `C3-10`) | `MCP-04` topology; `SEC-05` |
| CLI-1 | CLI coherent | `halbert` opens the conversation; `halbert license`/`info` work when installed; legacy persona/RAG commands hidden; CLI-REFERENCE regenerated | `CLI-01..04` | `CLI-01` |
| KNOW-1 | Knowledge reaches a fresh install | One corpus number; retrieval works without a hidden dependency (sidecar + prebuilt index, or fallback retriever); citations open; `assigned_to_role` in the template; CUDA doc where retrieval sees it; CoDRAG daemon-side fixes committed | `P1-05/11/12`, `RAG-01/06/13/14`, `U4-08/14` | `P1-11`, `RAG-13/14` |
| FENCE-1 | Scaffold fenced, dead code gone | Status headers on unwired federation modules; UI stops polling `/api/peers/discovered`; `runtime/`, `cascade_router.py`, dead autonomous tasks, legacy PersonaManager path deleted; caller-less routes frozen; governance singletons out of `routes/settings.py`; `redaction.py` moved to a leaf package | `A1-06/08/10/11/12/13/14/15`, `PICK-04`, `PERS-02` | `A1-11` self-knowledge owner |
| SURF-1 | Pages become modules (why-law order) | FindingCard, ApprovalCard, one Vitals, DriveHealth from SMART; Settings tabs and rail derived from capabilities on a home body | `C2-12/13`, `W3-C04` | — |
| BIRTH-1 | First conversation | Onboarding as a first conversation with background scan and real progress; asks name, purpose, body; model step inline; capability-gated scan; platform-aware copy; tests | `W1-04/05/06/11/16` | — |
| DOCS-1 | Docs tell the truth | README in the marketing voice with no model names and no "assistant"; FEATURES rewritten from this table; ARCHITECTURE rewritten to the real chat path; philosophy implementation table and autobiography section rewritten; CLI-REFERENCE and CONFIGURATION regenerated; banners applied to superseded plans; package descriptions unified | `A4-09/21`, `A1-16`, `C4-08`, `T1-02/03/16`, `P1-08/09` | `T1-03` product line |

## 4. Next (after every §3 row is green)

- Agent container image and CI publish (`R0.9/R0.10`, zero Rust dependency) and the sidecar compose draft — the first deployment item with no Rust dependency.
- Marketing site extension (blocked on Q1–Q8 and on `TRUST-1`, `KNOW-1`, `ATTN-1` being true).
- App Store companion as the Remote Client (same app, no backend, Presence Pill + pairing token) — after `LD-1` and `TRUST-1`.
- HA Add-on thin wrapper over the published image.
- `halbert-sh` PTY proxy; multi-persona Phase 3 polish; Plan C (background tasks, notifications).

## 5. Deferred by direction (2026-09-01)

Rust crates (`feat/rust-native-core`, parked, pushed as backup), `halbertd`, the MQTT device bus, Z-Wave/Matter/BLE native, the turnkey appliance image, HalbertOS, Windows, the Wayland HUD, the blue-sky pillars and their review request. Revive triggers are the L0–L3 gates in the Rust plan §16. Nothing here is scheduled.

## 6. Key to legacy phase numbers

"Phase 7/8" in `.handoff/ROADMAP-2026-08-23.md` = ATTN-1/STATE-1; "Phase 7/8" in the multi-instance design and TASK-PACKET-01 = LD-1/HOME-1; "Phase 7" in the singular-entity plan = LD-1 (pairing UI); "Phase 9.x" in the federation handoffs = LD-1 (9.1 auth, 9.3 compute) or FENCE-1 (9.5/9.7/9.8/9.9 scaffold); the retired `docs/PhaseNNN` sequence cited in `app.py` comments has no row.
