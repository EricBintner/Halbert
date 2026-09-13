# OSS Pass 2 — Discovery Backlog Prioritization

**Date:** 2026-09-11  
**Scope:** All discovery packets from `.handoff/oss-pass-2/` (74 packets across 12 workstreams) plus the `coverage_report.md` F01–F20 follow-up units, filtered against the merged/pending remediation packets R-01–R-15.  
**Sources:** `AGENTS.md`, `.handoff/oss-pass-2/section_*.md`, `.handoff/oss-pass-2/coverage_report.md`, `.handoff/oss-pass-2/remediation_plan.md`, `.handoff/OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md`, `.handoff/OSS-PASS-2-OPUS-REMEDIATION-2026-09-09.md`, `.handoff/STATE-OF-WORK-2026-09-10.md`.

## Scoring key

- **Value** (1–10): security, data-loss, correctness, or user-facing leverage of the packet.
- **Effort** (1–10): estimated implementation and verification cost (S≈3, M≈5, L≈8).
- **V/E**: value/effort ratio; higher is earlier.
- **Buildable**: whether the packet has **no** founder decision and **no** blocking unstarted dependency.
- **FD**: founder decision gate(s); `(default)` means the source recommends a default but the decision is still open.
- **R / Conflicts**: overlap with merged remediation packets, or architectural conflicts that require re-scoping/deferral.

## 1. Prioritized packet ranking

Packets are ranked by V/E and grouped into tiers. Within each tier the order is V/E descending, then value descending.

### Tier 1 — dispatch first (V/E ≥ 1.67, mostly ready now)

| Rank | Packet | Workstream | Value | Effort | V/E | Buildable | Founder gate | Rationale & conflicts / remediation |
|------|--------|------------|-------|--------|-----|-----------|--------------|----------------------------------------|
| 1 | **MP-1** | Models / providers / cost | 10 | 3 | 3.33 | Partial core | FD 1, 2 (defaults known) | Locality and utility-slot solidity; smallest, highest-leverage packet in the workstream. R-13 (sonnet, status complete per tier assignment) covers much of the utility-slot ladder; this packet remains the broader locality rule and the normalise/is_local_model enforcement. |
| 2 | **MEM-P1** | Memory | 9 | 4 | 2.25 | Yes | none | Read-side trust axis: ownership, visibility, forget tombstones, injection counter. Deterministic, no founder decision, touches `conversation_sqlite.py` search methods. R-14 (memory promotion follow-through, merged) overlaps the A01 read-side gaps; this packet owns the search/filter seam. |
| 3 | **SP-4** | Skills / prompts / learning | 8 | 4 | 2.00 | Yes | none | Slash-command catalog: no founder decision, small hot surface, unblocks SP-6. Must reserve names via `skills/reserved.py` and avoid inventing UI copy. |
| 4 | **MCP-A** | MCP / channels / gateway / protocol | 10 | 5 | 2.00 | Yes | none (defaults can be taken) | Child-process boundary: env whitelist, spawn, reader limit, liveness race. Highest-value packet in this workstream. **Covered in merged R-09** (child env whitelist, frame bounds, config-path critical); dispatch only to verify residual items and close MCP client gaps. |
| 5 | **CSC-03** | Conversation / session / compaction | 10 | 5 | 2.00 | Partial core | FD 2 (auto-continue; resume half only) | Conversation survives the process: crash/clean-shutdown markers, interrupted row, startup sweep. Core is buildable; only the auto-continue resume behavior is founder-gated. |
| 6 | **OTHER-P2** | Other | 8 | 4 | 2.00 | Yes | none | Redacting, correlated logging: closes A03-G9 and reuses A03-G5 ordering. No founder decision; coordinate with P4 / R-05 so `redact_error_text` has one owner. |
| 7 | **TT-05** | Terminal / tools / subagents | 9 | 5 | 1.80 | Yes | none | Tool-loop guardrails and malformed-call recovery; fixes HM01-C13, OC14 family, A07-G5. Sequence after TT-03 only if both touch `state_machine.py` in the same tree. |
| 8 | **VMV-2** | Voice / media / vision | 9 | 5 | 1.80 | Yes | none | One spoken egress: streaming reasoning scrubber, spoken-text normalization, output activity tracker, audio drop accounting, replayable event tail. **Partly covered by merged R-10** (speech egress pipeline); re-scope to local ASR/TTS surfaces and BYO-provider wiring. |
| 9 | **MCP-B** | MCP / channels / gateway / protocol | 9 | 5 | 1.80 | Partial | FD 3 (hint direction; default in packet) | Result and description hygiene: cap, strip, provenance. **Largely covered by merged R-09** (metadata sanitizer, `destructiveHint → HIGH`, `provenance='mcp'`); dispatch only if residual cap/strip items remain after R-09. |
| 10 | **DIAG-01** | Dashboard / app / onboarding / diagnostics | 9 | 5 | 1.80 | Yes | none | `halbert doctor` and the readiness endpoint. Retires the LLM judgement in `SystemHealthCheckTask`; uses the existing Finding/Proposal/Approval architecture. Coordinate with DIAG-02 on `conversation_sqlite.py` read-only probes. |
| 11 | **DIAG-02** | Dashboard / app / onboarding / diagnostics | 9 | 5 | 1.80 | Yes | none | Store integrity on the diagnostics seam: WAL, zeroed-file, path-default, degraded-mode surfaces. **Heavily covered by merged R-04** (conversation store / state ledger hardening); re-scope to the doctor-facing diagnostic surface and verify R-04 fixtures. |
| 12 | **T1** | Testing / evals / QA / ops | 9 | 5 | 1.80 | Partial | FD 3 (raise vs redirect for live-DB guard; default raise) | Test-run blast radius: hermetic env, live-DB guard, ancestry subprocess test. First packet in the testing workstream; gates T2 and T4. |
| 13 | **OTHER-P4** | Other | 9 | 5 | 1.80 | Yes | none | One bounded-execution helper with typed error outcomes: closes A06 timeout own-bug and feeds A04/A02. **Partly overlaps merged R-07** (execute_code hardening); this packet is the generic `_call_with_timeout` migration and dead-code removal. |
| 14 | **MEM-P6** | Memory | 9 | 5 | 1.80 | Partial core | FD Q2 (deterministic v0 summarizer half only) | Compaction gate and replay harness: deterministic context reclaim. Core gate buildable; LLM summarizer half gated by Q2. **Partly overlaps merged R-12** Phases B/C (deterministic compaction v0); Phase A still pending, so the gate is still needed. |
| 15 | **SCHED-P1** | Scheduler / heartbeat / daemon / watchdog | 10 | 6 | 1.67 | Partial | FD 1 (owner `start_time` field; small) | Receipt truth and job-record authority: the scheduler cannot count streaks until receipts are trustworthy. **R-03 is pending (sonnet batch)** and covers much of the scheduler durability; if R-03 lands first, this packet shrinks to surface/registry items. |
| 16 | **TT-01** | Terminal / tools / subagents | 10 | 6 | 1.67 | Yes | none | Shell executor hardening: process groups, bounded output/spill, child environment fences, stop semantics. First packet in this workstream; gates TT-02/TT-03/TT-04. Touches `tools/executor.py` and `streaming/pty.py`. |
| 17 | **T2** | Testing / evals / QA / ops | 8 | 5 | 1.60 | No | FD 1; prereq T1 | Suite integrity and the async ratchet: fixes async-blocking routes and reconciles the isolated runner. Must wait for T1 and the isolated-runner CI decision. |
| 18 | **T4** | Testing / evals / QA / ops | 8 | 5 | 1.60 | Yes | none | Wire contracts and the model-name surface eval; extends the no-model-name-in-user-facing-source test. **Partly covered by merged R-15** (eval harness / verdict contract); re-scope to the user-facing source scanner and BOUNDARY.md. |
| 19 | **T5** | Testing / evals / QA / ops | 8 | 5 | 1.60 | Partial | FD 4 (bundle contents/destination; default local) | Doctor, diagnostics and host-truth: artifact SHA-256 verification, redaction coverage registry, redacted support bundle. Deterministic health findings; bundle stays local and staged. |
| 20 | **VMV-3** | Voice / media / vision | 8 | 5 | 1.60 | Yes | none | Inbound media bounds and leak-free media/status surfaces: caps image/audio/video/document sizes and hardens the `images` route and guest path. |

### Tier 2 — high value, sequence after Tier 1 or after a founder call (V/E 1.14–1.60)

| Rank | Packet | Workstream | Value | Effort | V/E | Buildable | Founder gate | Rationale & conflicts / remediation |
|------|--------|------------|-------|--------|-----|-----------|--------------|----------------------------------------|
| 21 | **LOG-01** | Dashboard / app / onboarding / diagnostics | 7 | 5 | 1.40 | Yes | none | Log file, tail, Logs page, support bundle. No shared hot files; sequence after DIAG-01 for the doctor JSON and redaction variant. |
| 22 | **SCHED-P2** | Scheduler / heartbeat / daemon / watchdog | 8 | 5 | 1.60 | Yes | none | Honest timeouts: changes `misfire_grace_time` from total to idle, fixes A06 own-bug 3. Independent of P1. |
| 23 | **SP-1** | Skills / prompts / learning | 9 | 6 | 1.50 | Partial | FD 1 (hide vs list-as-setup_needed) | Honest and scanned skill catalog: parser fixes, content scan, `skill_for_path`, truncation. **Partly covered by merged R-11** (skills plane); re-scope to catalog-UI integration and scanner tuning. |
| 24 | **SP-3** | Skills / prompts / learning | 9 | 6 | 1.50 | Partial | FD 2 (dispatch all tool calls; default yes) | Turn-loop seams: sequential multi-tool dispatch and the stop-gate chain. Changes what a running turn does; needs review and a clear default. |
| 25 | **T3** | Testing / evals / QA / ops | 9 | 6 | 1.50 | No | FD 2; prereq T1 | Verification before "done": stop-gate, nudge on unverified edits, `detect_project_facts`. Blocked on T1 and the nudge-default decision. |
| 26 | **MP-2** | Models / providers / cost | 9 | 6 | 1.50 | Partial | FD 4 (Retry-After ceiling; default 600 s) | Provider failure semantics: typed reasons, Retry-After handling, cancellation, safe transport shutdown. Order inside is C6 first. |
| 27 | **TT-03** | Terminal / tools / subagents | 9 | 6 | 1.50 | No | FD 1 (per-origin approval defaults, deny-list file, timeout) | Command classifier v2 and the confirmation gate. Builds after TT-01's `text_hygiene`; needs the founder's deny-list and timeout posture. |
| 28 | **CMD-A** | MCP / channels / gateway / protocol | 6 | 4 | 1.50 | No | prereq SP-4 and P3 | One command table: routes slash commands through `skills/reserved.py` and the frontend. Blocked on SP-4 and the permissions self-modification packet. |
| 29 | **OTHER-P3** | Other | 6 | 4 | 1.50 | Yes | none | Measured, not assumed: foreign-module assertions, sensor-unavailable handling, bench hooks. No shared hot files. |
| 30 | **P1** | Permissions / consent / security | 9 | 6 | 1.50 | Partial | FD-A9 (network-egress binaries HIGH; default HIGH) | Command gate rebuild: argv normalization, two-tier classifier, `write_config`/`schedule_cron` call sites. Core buildable; the network-egress default gates one sub-item. |
| 31 | **MEM-P3** | Memory | 10 | 7 | 1.43 | Partial | FD 1 (venv rebuild; rest buildable) | Store durability: WAL gate, verified backup, salvage, durable-write helper. **R-04 (merged) overlaps A08/A16 store issues**; this packet is the backup/salvage layer and the durable-write helper. Do not duplicate R-04 fixtures. |
| 32 | **CSC-01** | Conversation / session / compaction | 10 | 7 | 1.43 | Partial | FD 6 (internal results through redaction core) | Turn-boundary trust and decode: provenance on `ExecutionResult`, coerce-before-redact. Core buildable once FD 6 is ratified. |
| 33 | **GW-A** | MCP / channels / gateway / protocol | 7 | 5 | 1.40 | Partial | FD 8 (C7 inside B6; default yes) | Event stream reconnect and typed errors; coordinates with the terminal reattach work so replay is wired once. |
| 34 | **OTHER-P6** | Other | 7 | 5 | 1.40 | Yes | none | Settings reload plan and dashboard storage hygiene: no-migration, additive fields, slot-named reload table, invalid-config visibility. |
| 35 | **SCHED-P4** | Scheduler / heartbeat / daemon / watchdog | 7 | 5 | 1.40 | Partial | FD 4 (turn deadline ceiling; not blocking) | Turn liveness and local-model priority: interrupt algebra, `turn_activity.py`, tool budget. Core buildable; default ceiling is a narrow decision. |
| 36 | **SP-2** | Skills / prompts / learning | 7 | 5 | 1.40 | Partial | FD 3 (malicious-intent clause scope; default intent inference) | Prompt assembly honesty and untrusted-content fencing; depends on SP-3 for batching clause and A07-G4 delimiters. |
| 37 | **MEM-P2** | Memory | 8 | 6 | 1.33 | No | prereq MEM-P1 | Promotion mechanics and product-boundary test. **Overlaps merged R-14** (A01 bugs); build after MEM-P1 and verify R-14 coverage. |
| 38 | **CSC-02** | Conversation / session / compaction | 8 | 6 | 1.33 | Partial | FD Q2 (summarizer half only) | Deterministic context reclaim and window-relative budgets. Core buildable; the LLM summarizer half can ship later. |
| 39 | **CSC-06** | Conversation / session / compaction | 8 | 6 | 1.33 | Partial | none for M2/M3/M6; prereq R04-POOL/R04-F2 for M1/M4 | Terminal reattach and desktop boot. Split M2/M3/M6 (desktop boot, reconnect, auth codes) from M1/M4 (watched shell); the latter waits on the terminal workstream's watched-shell wiring. |
| 40 | **TT-02** | Terminal / tools / subagents | 8 | 6 | 1.33 | No | prereq TT-01 | Child-process boundary fence: env propagation, trusted execution, detached context. Builds after TT-01's kill helper; coordinate with P5/R-09 on MCP env. |
| 41 | **VMV-1** | Voice / media / vision | 8 | 6 | 1.33 | Partial core | none for core; FD for C4 (wake phrase to persona home; default no) | Wake word that fires: Darwin+arm64 probe, 1280-sample accumulator, cooldown, dead-mic flag. Core buildable; the persona-home follow-on is gated off by default. |
| 42 | **VMV-6** | Voice / media / vision | 8 | 6 | 1.33 | Partial core | none for core; FD for C11 (BYO shell-command STT/TTS provider; default yes) | Audio runtime footprint, BYO providers, capability assertions, runtime health. Core ready; BYO provider tail can default to on/off. |
| 43 | **MCP-C** | MCP / channels / gateway / protocol | 8 | 6 | 1.33 | Partial | FD 7 (trust the on-disk schema cache; default yes) | Server lifecycle and discovery: fingerprinted schema cache, lazy first-call connection, list_changed. **Small overlap with R-09** (list_changed/breaker/pagination); the cache/discovery layer is new. |
| 44 | **OTHER-P5** | Other | 8 | 6 | 1.33 | Partial | FD 4 (node_id switch; core can proceed) | Atomic durable files and minted identity: closes A06 ledger fsync bug and A12-G8. Node-id switch is founder-gated; the atomic-writer migration is not. |
| 45 | **MP-3** | Models / providers / cost | 8 | 6 | 1.33 | No | prereq MP-2 C6; also needs merged interrupt algebra | Transport liveness: cancel in-flight, abort hooks, slow/silent server fixture. Ship after MP-2. |
| 46 | **MEM-P4** | Memory | 8 | 6 | 1.33 | No | prereq MEM-P2, MEM-P3; FD 5 narrow (score-component presentation) | Continuity doctor and promotion inspector. **Overlaps merged R-14** (promotion liveness/recency); this is the UI/doctor surface. |
| 47 | **P2** | Permissions / consent / security | 10 | 8 | 1.25 | No | FD-A1 (approval timeout), FD-A10 (standing allow-rules) | Approvals bound and fail closed; policy descriptor registry. **R-08 (merged) covers the ask-axis / approval enforcement**; this packet owns the presentation builder and descriptor registry. |
| 48 | **DAEMON-01** | Dashboard / app / onboarding / diagnostics | 10 | 8 | 1.25 | No | FD 1 (attach vs refuse on second launch) | One backend per data dir: exit vocabulary, PID-safe identity, boot forensics, wedge reclamation. **R-03 (pending)** would supply heartbeat/daemon pieces; coordinate. |
| 49 | **P4** | Permissions / consent / security | 10 | 8 | 1.25 | No | FD-A4 (LAN local providers), FD-A5 (sealed secrets), FD-A7 (05-C internal tool results) | Egress, secrets and redaction seams. **R-05 and R-06 (merged) cover the redaction registry and echo guard**; this packet is the egress path, LAN-provider, SecretRef, and sealed-secrets boundary. |
| 50 | **DIST-02** | Dashboard / app / onboarding / diagnostics | 5 | 4 | 1.25 | No | prereq DIST-1 signing identity and entitlements | Signing, entitlements, usage strings, login item. macOS packaging; defer until DIST-1 infrastructure exists and signing identity is decided. |
| 51 | **CSC-04** | Conversation / session / compaction | 9 | 7 | 1.29 | No | FD 1, FD 9 (WAL posture, startup integrity) | Conversation-store hardening II: corruption classifier, fail-closed, `HALBERT_DATA_DIR`, search fallbacks. **Heavily overlapped by merged R-04**; re-scope to diagnostic/reporting surfaces. |
| 52 | **SCHED-P3** | Scheduler / heartbeat / daemon / watchdog | 9 | 7 | 1.29 | No | FD 3 (standing orders), FD 5 (per-job failure isolation) | Failure containment, admission, kill switch. Needs P1 receipt truth first. |
| 53 | **VMV-4** | Voice / media / vision | 9 | 7 | 1.29 | Yes | none (never-delete replay tail is a default note, not a build gate) | Voice ingress hardening and turn replay: shared-room rule, turn replay, per-turn event tail. **R-02 (merged) covers voice provenance**; this packet owns the replay harness. |
| 54 | **MP-6** | Models / providers / cost | 9 | 7 | 1.29 | No | FD 3 (credential as reference; default yes) | Credential custody at process and wire boundaries: scrubbed child env, `allow_redirects=False`, token_env indirection. Security-shaped; coordinate with P5/R-09. |
| 55 | **BIND-01** | Dashboard / app / onboarding / diagnostics | 9 | 7 | 1.29 | Partial | FD 3 (file-delivery convention), FD 4 (allowed-hosts on credentials) | Bind what was checked to what is touched: artifact-bound approval, base-hash guard, allowed-hosts. Core path-policy work is standing-directive; two sub-items are founder-gated. |
| 56 | **VMV-5** | Voice / media / vision | 7 | 6 | 1.17 | Partial core | FD 1 (day journal; default not yet) | Screen and vision truthfulness (M3) plus the day journal (C14). Core M3 buildable; **defer the day journal** until `vision/redact.py` is reviewed for exposure. |

### Tier 3 — defer / re-scope / gated / low V/E (V/E ≤ 1.14 or blocked on founder decisions and unstarted infrastructure)

| Rank | Packet | Workstream | Value | Effort | V/E | Buildable | Founder gate | Rationale & conflicts / remediation |
|------|--------|------------|-------|--------|-----|-----------|--------------|----------------------------------------|
| 57 | **TERM-02** | Dashboard / app / onboarding / diagnostics | 7 | 6 | 1.17 | No | FD 2 (agent reads user shell), FD 7 (agent proposes MCP install) | Watched-terminal read and close tools. No consumer until TERM-1's `YourShellRegion` is mounted and A05-G2 projection is fixed. |
| 58 | **OTHER-P1** | Other | 7 | 6 | 1.17 | No | FD 1, FD 2 (secrets at rest, create-only backup) | State backup, create-only. Founder-gated; restore is explicitly deferred per the no-migration directive. |
| 59 | **MEM-P5** | Memory | 8 | 8 | 1.00 | No | FD 2, 3, 4, 6 (reflex lifecycle, write-approval, vault, machine-owned vault) | Staged writes, the vault rule, and prospective memory on reflexes. Multiple founder decisions; cannot start without rulings. |
| 60 | **CH-A** | MCP / channels / gateway / protocol | 8 | 7 | 1.14 | No | FD 4, FD 5 (heartbeat cognition tick, stop survives restart) | Turn provenance at the talk door. Blocked on packet 07-B/C and the A09/A07 ingress fixes (R-01/R-02 merged may cover much). |
| 61 | **P3** | Permissions / consent / security | 9 | 8 | 1.13 | No | FD-A2, FD-A6, FD-A7 (D3-P5 review, durable undo, 05-C internal results) | Self-modification: write-approval gate, config-key fence, honest config writes. Needs the D3-P5 review and durable-undo decision. |
| 62 | **P5** | Permissions / consent / security | 9 | 8 | 1.13 | No | FD-A8 (OSV preflight; default off), FD-A4 (LAN local providers) | Third-party process boundary and file-path primitives. **R-09 (merged) covers the MCP child boundary**; the file-read/write guards and OSV tail are founder-gated. |
| 63 | **CSC-05** | Conversation / session / compaction | 10 | 9 | 1.11 | No | FD 4, 7, 8 (side question shape, system channel, clarify verb) | Turn admission, identity and mid-turn verbs. Hottest packet; split into 05a/05b and sequence after CSC-01/CSC-03. **R-01 (merged) covers the interrupt algebra** but not the admission/new-verbs layer. |
| 64 | **P6** | Permissions / consent / security | 8 | 8 | 1.00 | No | FD-A3, FD-A11, FD-A12 (signing identity, SECURITY.md boundary, retention) | Door, OS-grant axis, doctor/lint, runtime/state hygiene. Large surface; needs signing identity and security-boundary decisions. |
| 65 | **SP-5** | Skills / prompts / learning | 7 | 7 | 1.00 | No | FD 7 (curator defaults); prereq SK-3, SK-5 | Curator invariants (SK-6/SK-7). Requires skill write path and memory C8; defer until SP-1/SP-3 land. |
| 66 | **SP-6** | Skills / prompts / learning | 7 | 7 | 1.00 | No | FD 4, 5, 6; prereq SP-4, SP-5 | Authoring commands and evidence shapes (`/learn`, `/review`, `/plan`). Needs slash-command table, write path, and egress.web_fetch. |
| 67 | **TT-04** | Terminal / tools / subagents | 9 | 9 | 1.00 | Partial | FD 2 (wake lane; default no) | Background registry, yield, wake, and watched-terminal surface. Largest terminal packet; split C (registry/yield) from B (watched terminal/status). Record-only lane is buildable, wake lane is founder-gated. |
| 68 | **TT-06** | Terminal / tools / subagents | 7 | 7 | 1.00 | No | FD 5 (SubagentManager production consumer) | Subagent manager correctness. M1/M2 fixes buildable regardless; the production wiring is founder-gated. |
| 69 | **SCHED-P5** | Scheduler / heartbeat / daemon / watchdog | 8 | 8 | 1.00 | Partial core | FD 2 (LaunchAgent / background work outlives app) | Process lifecycle / daemon packet. Core is founder-independent; the launchd/supervisor tail is gated. |
| 70 | **MP-4** | Models / providers / cost | 7 | 7 | 1.00 | No | FD 6, 7 (keep_alive, cost arithmetic) | Measured context and residency. `keep_alive` and cost figure are founder decisions; instrument usage rows now and hold arithmetic. |
| 71 | **T6** | Testing / evals / QA / ops | 6 | 6 | 1.00 | No | FD 5, 6, 7 (CSP, npm install scripts, security-regression rulepack engine) | Posture contracts: Tauri CSP, npm install-script allowlist, security-regression rulepack. Needs the security audit plist fix and founder tooling choices. |
| 72 | **SURFACE-01** | Dashboard / app / onboarding / diagnostics | 8 | 9 | 0.89 | No | FD 5, 6 (progress card rail, guest status strip) | Progress, staleness, polling, approvals, rendering, onboarding, skills UI. Too large for one branch; split into 01a/01b/01c and sequence after DIAG/scheduler surfaces. |
| 73 | **MP-5** | Models / providers / cost | 8 | 9 | 0.89 | No | prereq MP-2 C6 | Local-model output robustness: grammar/payload/fence repair, schema coercion. Large; ship after MP-2. |
| 74 | **SCHED-P6** | Scheduler / heartbeat / daemon / watchdog | 8 | 9 | 0.89 | No | FD 6, 7 (timezone posture, user-created schedules) | Scheduled-work surface: list/history/cancel first, create after P1/P3 and founder decisions. |

## 2. Cross-cutting mechanisms

### Required nine starter mechanisms

| Mechanism | Affected workstreams | One-line implication for Halbert |
|-----------|----------------------|----------------------------------|
| Untrusted-data delimiters | Conversation, Skills, Terminal, Voice, Models | Every injection of tool output, skill text, or model stream into a prompt must be bounded by deterministic start/end markers so the assembler can redact or strip by section. |
| Process-start-time ownership | Scheduler, Terminal, MCP, Dashboard | Run receipts and parent/child identity must carry `(pid, start_time)` to survive PID reuse on macOS; bare PID checks are a data-loss bug. |
| Approval bound to artefact | Permissions, Terminal, Dashboard, Memory | A consent record must name the canonical artefact (resolved path, argv+cwd, diff sha256, capability digest) it approved; generic tool-name approval is not sufficient. |
| One SSRF guard | Permissions, MCP, Models, Dashboard | All network egress from tools, MCP servers, and provider calls must route through one deterministic capability/host allowlist; no per-caller override. |
| Trusted-directory resolution | Memory, Dashboard, Other, Permissions | `data_dir()`/`state_dir()` must be resolved at call time and single-sourced; importing-time `Path.home()` defaults cause production data to leak into tests. |
| Environment allowlists | MCP, Terminal, Models, Voice | Child processes (stdio MCP servers, shells, code kernels, local-model subprocesses) receive a positive allowlist plus explicit config env, not `os.environ` wholesale. |
| `halbert doctor` | Dashboard, Testing, Permissions, Scheduler | Health checks return the existing `Finding` shape (severity, id, fix hint) and feed a CLI/dashboard panel; no LLM judgement; fixes are staged proposals. |
| Verification-before-done | Testing, Terminal, Conversation | Code-edit turns must run a verification step before success; the nudge is bounded to one extra local call and never blocks indefinitely. |
| Event replay rings | MCP, Terminal, Voice, Conversation | Terminal/voice/MCP/event streams must expose a monotonic `(seq, epoch)` tail so reconnect, reattach, and replay are deterministic and bounded. |

### Additional mechanisms appearing in three or more workstreams

| Mechanism | Affected workstreams | One-line implication |
|-----------|----------------------|----------------------|
| Deterministic sanitization / redaction at choke points | Conversation, Permissions, MCP, Voice, Models, Dashboard | Scrub secrets, reasoning blocks, and override phrases in one function before any model, display, log, or TTS surface; models never make redaction decisions. |
| Typed reason codes / structured error envelopes | Scheduler, Terminal, Models, Testing, Voice | Replace message-string parsing with a closed `Reason`/`Error` taxonomy so every denial, timeout, and provider failure is machine-readable and log-safe. |
| Bounded reads, buffers, retries, caches | Memory, Conversation, Voice, MCP, Models, Other | Every read, frame, output spill, retry window, and LRU cache must have a documented byte/time/call ceiling to prevent OOM, hang, and volume fill. |
| Fail-closed policy evaluation | Permissions, Terminal, Scheduler, MCP, Skills | Missing, unreadable, or malformed evidence must produce `Denied`/`UNVERIFIED`, not a default allow or a model guess. |
| fd-pinned filesystem ops | Permissions, Other, Dashboard, Memory | Use `O_NOFOLLOW`, `fstat`, directory fsync, and `os.replace` patterns to close symlink/hardlink/TOCTOU races for all sensitive reads and writes. |
| Lexical + resolved-path containment | Permissions, Terminal, Other, MCP | Classifiers must see the normalized, `realpath`-resolved path and compare path components, not raw prefixes or symlink aliases. |
| Quarantine-then-promote ingestion | Memory, Permissions, MCP, Skills | Untrusted skill/model/MCP/data artefacts are scanned and staged before promotion; no live replacement of a running module. |
| Content-addressed manifests / rollback receipts | Memory, Permissions, Other, Dashboard | Every durable write that mutates config or state leaves a sha256-pinned receipt and a `.bak`/rotate path so rollback is deterministic and old data is left unread, never deleted. |
| Process groups / owned-process reaping | Scheduler, Terminal, MCP, Voice | Spawned processes must set `start_new_session`, track `(pid, start_time)`, and reap on timeout/close to avoid orphan servers and zombie PTYs. |
| Per-job or per-resource failure isolation | Scheduler, Terminal, Models, Testing | A failing scheduled job or tool must disable that job, not escalate to global safe mode; streaks must be per-receipt, not per-daemon. |
| Read-only probes that do not mutate schema/config | Memory, Dashboard, Testing | `doctor`, diagnostics, and tests must read state read-only and fail closed on a live store path, never create tables or rewrite config. |
| Replayable event tails with monotonic seq/epoch | MCP, Voice, Terminal, Conversation | All event producers (`turn_event_tee`, PTY, MCP, voice) append `(seq, ts, epoch)` rows so consumers reconnect and replay without inventing state. |
| Output/activity watchdogs based on observed progress | Voice, Terminal, Scheduler, Models | Use stream bytes, playback ms, tool heartbeats, or model chunks to detect stalls, not wall-clock alone. |
| Environment scrubbing and positive child-context markers | MCP, Terminal, Models, Permissions | Child contexts receive `HALBERT_CHILD_CONTEXT` and a minimal allowlist; tools use it to distinguish self-executions from arbitrary scripts. |
| Context detachment for background work | Terminal, Scheduler, MCP | Background turns, completions, and scheduled jobs run with their own `ContextVars` so a user-turn security context does not leak into a later autonomous turn. |
| Single-source policy registries / shared projection | Permissions, Skills, Dashboard | Capability classes, risk levels, and skill `allowed_tools` must be compiled from one registry and projected through one display seam. |
| Deterministic scanners / validators, not model decisions | Permissions, Skills, Memory | Threat scans, skill content scans, and promotion boundary tests run deterministic regex/AST/sha checks; the model is never asked to judge safety. |
| CAS / config version checks and merge-patch writes | Dashboard, Permissions, Other | Config writes use a known base sha/ETag, merge-patch, and additive columns; invalid config is surfaced, not silently defaulted. |
| No silent fallback to defaults when config is invalid | Dashboard, Models, Permissions | A malformed model slot, skill, or setting must refuse or repair, not silently fall back to a hard-coded default. |
| Staged proposals / dry-run / approval workflows | Permissions, Terminal, Dashboard | Every autonomous write is a proposal first; `apply` only after deterministic diff, artefact-bound approval, and a logged receipt. |
| No unsolicited proactive model-authored messages | Scheduler, Skills, Memory | Completions, morning reports, and proactive nudges are persisted as inert transcript rows and gated by the proactivity dial; the machine never starts a turn unbidden. |
| Model / provider abstraction without exposing model names | Models, Dashboard, Testing | User-facing surfaces name connection slots and capabilities, never concrete model/provider names; no model-name leakage in diagnostics or URLs. |

## 3. F01–F20 follow-up units, filtered against R-01–R-15

**Remediation status baseline**
- Merged (opus tier, per `STATE-OF-WORK-2026-09-10.md` §1): **R-01, R-02, R-04, R-05, R-06, R-07, R-08, R-09, R-10, R-11, R-12 Phases B/C, R-14**.
- Status as of 2026-09-11: the sonnet batch (**R-03, R-13, R-15, R-12 Phase A**) is reported complete in `OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md` and the current session context, though not yet merged to `main`; treat as pending-merge rather than still-open.

| Follow-up | Priority (per coverage report) | R-01–R-15 coverage | Recommendation |
|-----------|--------------------------------|--------------------|----------------|
| **F01** — macOS host integration (`openclaw/apps/macos`) | highest | Not covered by any merged R packet. | **Recommended top follow-up.** Directly feeds DAEMON-01, DIST-02, TERM-02, and the OS-grant work in P6. Highest value for a macOS-resident daemon. |
| **F02** — agents tool admission (`openclaw/src/agents`) | highest | Partly covered by merged **R-01** (interrupt algebra), **R-08** (permission lattice), **R-02** (guest/voice provenance). | Large remaining mass; dispatch only after verifying what R-01/R-08/R-02 already closed. Rank as second-tier discovery. |
| **F03** — MCP server side (`openclaw/src/mcp`) | highest | Not covered; R-09 was MCP **client** boundary. | **Recommended top follow-up.** Needed to close the B6 audit and decide remote-MCP OAuth/gateway/server policy. |
| **F04** — skill workshop governance (`openclaw/src/skills/workshop`) | highest | Partly covered by merged **R-11** (Halbert skills plane). | The lifecycle/propose/review/apply layer is distinct from R-11's parser/catalog fixes. High, but defer until SP-1/SP-5 land. |
| **F05** — origin rationale docs (`hermes/openclaw docs`) | highest (per file) | Not covered. | **Recommended top follow-up.** Cheapest unit; repairs the systematic refutation/justification weakness found across audits. |
| **F06** — config/state durability (`openclaw/src/config` + `src/state`) | highest | Partly covered by merged **R-04** (conversation store/state ledger) and **R-12** (compaction). | Config and state durability remain largely unread and include a real lost-update on `models.yml`. **Recommended top follow-up.** |
| **F07** — gateway auth/approval (`openclaw/src/gateway`) | high | Heavily covered by merged **R-01**, **R-02**, **R-08**. | Largely subsumed; only useful for edge cases not closed by the merged remediation. |
| **F08** — CLI self-diagnosis and update (`hermes_cli/`) | high | Not covered. | Halbert's `halbert doctor` and update path are unbuilt. **Recommended as a medium-high follow-up** once `DIAG-01` is dispatched. |
| **F09** — first run and onboarding (`openclaw/src/cli` + `src/wizard`) | high | Not covered. | **Recommended top follow-up.** BIRTH-1 and onboarding are the first user surface and are the least-read UI area. |
| **F10** — plugin capability contract (`openclaw/src/plugin-sdk`) | high | Not covered. | Medium value; revisit only if Halbert decides to admit third-party extensions. |
| **F11** — control UI patterns (`openclaw/ui/`) | high | Not covered. | **Recommended top follow-up.** SURF-1 depends on these patterns; take state/streaming/deep-link behavior, not visual language. |
| **F12** — Hermes plugin runtime (`hermes/plugins/`) | high | Not covered. | Low value until a plugin consumer exists; keep as reference. |
| **F13** — reference agent loop (`open-claude-code/src`) | high | Partly covered by merged **R-01**, **R-07**, **R-08**. | Faithful reconstruction of the agent loop/terminal/tool dispatch; useful as ground truth for TT and CSC. **Recommended as a medium-high follow-up.** |
| **F14** — secrets at rest and broker (`openclaw/src/secrets`) | high | Partly covered by **R-05** (redaction registry), **R-08** (permission lattice), and P4. | Defer sealed-secrets subsystem until a concrete consumer exists; the credential-as-reference pattern is already in MP-6/P4. |
| **F15** — command surface (`openclaw/src/commands`) | medium | Not covered. | Low until slash/command registry depth is needed beyond SP-4. |
| **F16** — Hermes tools remainder (`hermes/tools/`) | medium | Partly covered by **R-07** and terminal packets. | Not urgent; dispatch only after tool admission is stable. |
| **F17** — desktop RPC bridge (`hermes/tui_gateway/` + `apps/desktop`) | medium | Not covered. | Relevant if Halbert ever separates the Tauri shell from the backend daemon; low priority now. |
| **F18** — protocol and host SDK contracts (`openclaw/packages/ai`) | low | Not covered. | Reference-only for typed wire contracts; low priority. |
| **F19** — cross-cutting primitives (`openclaw/src/shared`) | low | Not covered. | Small but dense; useful only as a sanity-check on Halbert's own shared primitives. |
| **F20** — deterministic policy extension (`openclaw/extensions/policy`) | low | Partly covered by **R-08**. | Low priority until Halbert needs a pluggable policy engine. |

### Recommended top 5–7 genuinely uncovered, high-value follow-ups

1. **F01** — macOS host integration (highest; no merged coverage; unlocks DAEMON-01/DIST-02/OS-grant).
2. **F03** — MCP server side (highest; R-09 left the server boundary untouched; closes B6 audit).
3. **F05** — origin rationale docs (highest per file; fixes the justification gap that repeatedly caused refutations).
4. **F06** — config/state durability (highest; includes a live lost-update on `models.yml`; partly covered by R-04/R-12 but the `src/config` mass is unread).
5. **F09** — first run and onboarding (high; the pre-configuration surface and capability probe are almost unread).
6. **F11** — control UI patterns (high; SURF-1 needs state/streaming/deep-link patterns).
7. **F13** — reference agent loop (high; ground truth for terminal/tool dispatch and the agent loop; small enough to be a quick read).

**Caveat:** 21 of 46 units in the discovery pass are operationally thin, and `openclaw` agents/UI/apps, Hermes desktop/UI, MCP, provider configuration, onboarding, TUI, PTY bridging, dashboard-equivalent UX, plugins, and self-update remain shallow. Treat the above recommendations as targeted second-pass reads, not as fully-verified build plans.

## 4. Recommended first-wave dispatch order

### A. Ready now

These packets require no founder decision and have no blocking unstarted dependency. They can be dispatched in parallel worktrees where file ownership is respected.

- **MP-1** (Models) — locality / utility-slot; smallest high-leverage packet.
- **MEM-P1** (Memory) — read-side trust axis; deterministic, no founder gate.
- **SP-4** (Skills) — slash-command catalog; no founder gate.
- **CSC-03** core (Conversation) — crash/clean markers and interrupted row; auto-continue is the only gated half and can be stubbed with the recommended default.
- **OTHER-P2** (Other) — redacting correlated logging.
- **OTHER-P4** (Other) — bounded-execution helper.
- **OTHER-P3** (Other) — measured, not assumed.
- **OTHER-P6** (Other) — settings reload and storage hygiene.
- **TT-01** (Terminal) — shell executor hardening; gates the rest of the terminal workstream.
- **TT-05** (Terminal) — tool-loop guardrails; can run in parallel with TT-01 if `state_machine.py` ownership is respected.
- **VMV-1** core (Voice) — wake-word correctness.
- **VMV-2** (Voice) — one spoken egress; re-scope to items not in merged R-10.
- **VMV-3** (Voice) — inbound media bounds.
- **VMV-4** (Voice) — voice ingress hardening and turn replay.
- **VMV-5** core M3 (Voice) — screen/vision truthfulness; defer the day journal.
- **VMV-6** core (Voice) — audio runtime footprint and BYO providers.
- **MCP-A** (MCP) — child-process boundary; **verify against merged R-09 before duplicating effort**.
- **DIAG-01** (Dashboard) — `halbert doctor`.
- **DIAG-02** (Dashboard) — store integrity diagnostics; **verify against merged R-04 before duplicating effort**.
- **LOG-01** (Dashboard) — logging and support bundle surface.
- **T4** (Testing) — wire contracts and model-name surface eval.
- **SCHED-P2** (Scheduler) — honest timeouts.
- **SCHED-P4** core (Scheduler) — turn liveness; only the ceiling default is gated.
- **SCHED-P5** core (Scheduler) — daemon lifecycle core; launchd tail is gated.

**Shared-file sequencing notes**
- `agents/conversation_sqlite.py`: MEM-P1 (search methods) and MEM-P3 (open path) can run in parallel; merge MEM-P3 first.
- `tools/executor.py`: one owner per function; TT-01/TT-03/TT-05/TT-04/P1/P5 coordinate via a file-ownership queue.
- `agents/state_machine.py`: CSC-05, TT-05, SP-3, VMV-2, VMV-4, MP-1, P2, P4 all touch it; schedule in the order above or use separate worktrees and a merge pass.
- `dashboard/routes/agent.py`: VMV-4, CH-A, GW-A, MP-1/MP-2, CSC-05 share admission/display seams.
- `dashboard/app.py`: DAEMON-01, DIAG-01, LOG-01, SURFACE-01, P6 share lifespan/router code.

### B. Needs founder decisions first

Dispatch these only after the listed decision is ratified (recommended defaults are in the section files and above). Items already touched by merged remediation should be re-scoped first.

| Decision | Packets unblocked | Source / default |
|----------|-------------------|------------------|
| **Memory FD 1** (Python 3.12 / SQLite pin) | MEM-P3 (full packet) | Rebuild venv on 3.12; do not switch journal mode on live stores. |
| **Memory FD 2–6** (reflex lifecycle, write-approval, vault, machine-owned vault, recall-intent) | MEM-P5 | Multiple decisions; recommended defaults are off/staged. |
| **Memory FD Q2** (deterministic v0 summarizer) | MEM-P6 rotation writer | Yes to receipt-concatenation v0; LLM summarizer waits for the eval scorecard. |
| **Conversation FD 1, 6, 9** (WAL posture, internal tool results redaction, startup integrity) | CSC-01, CSC-04 | Gate new WAL files on version predicate; route internal results through redaction core; run throttled `PRAGMA quick_check` at boot. |
| **Conversation FD 2, 4, 7, 8** (auto-continue, side question shape, system channel, clarify verb) | CSC-03 resume half, CSC-05 | No auto-run of crashed turns; ephemeral hidden thread for side questions; declared system channel; clarify as a second verb on `AWAITING_CONFIRMATION`. |
| **Permissions FD-A1, A2, A4, A5, A7–A12** (approval timeout, D3-P5 review, LAN providers, sealed secrets, 05-C, OSV, network-egress, standing allow-rules, signing/security boundary, retention) | P1, P2, P3, P4, P5, P6 | Defaults listed in `section_permissions-consent-security.md` §261. |
| **Scheduler FD 1, 3, 5, 6, 7** (start-time field, standing orders, per-job failure isolation, timezone, user-created schedules) | SCHED-P1, SCHED-P3, SCHED-P6 | Add `owner_start_time`; yes to per-job auto-disable; ship list/history/cancel before user-created schedules. |
| **Terminal FD 1, 2, 5, 7** (per-origin approval defaults, wake lane, subagent consumer, MCP install proposal) | TT-03, TT-04 wake lane, TT-06, TERM-02 FD-7 | Deny unattended HIGH for scheduler/MCP; ask with 10-minute bound for voice/dashboard; no background turn starts unbidden. |
| **Skills FD 1–7** (catalog visibility, multi-tool dispatch, malicious intent, `/review`, `/plan`, proposals, curator) | SP-1, SP-2, SP-3, SP-5, SP-6 | Vanish unmet `requires` from model catalog; sequential multi-tool; intent inference; curator defaults in §177 of source. |
| **MCP FD 3–8** (hint direction, heartbeat tick, stop survives restart, OAuth, schema cache trust, B6 typed errors) | MCP-B, MCP-C, CH-A, GW-A | Hints raise floor only; no OAuth now; yes to fingerprinted cache; typed errors in `consent/denials.py`. |
| **Voice FD 1, 4, 6, 7** (day journal, BYO STT/TTS providers, shared-room wake phrase, symbol expansion) | VMV-5 day journal, VMV-6 BYO tail | No day journal yet; BYO providers off by default; require wake phrase with multiple speakers; no symbol expansion. |
| **Models FD 1–7** (locality fail-closed, catalog probe opt-in, credential reference, Retry-After ceiling, cloud fallback notice, keep_alive, cost arithmetic) | MP-1, MP-2, MP-4, MP-6 | Defaults in `section_models-providers-cost.md` §171. |
| **Dashboard FD 1–9** (attach vs refuse, terminal read, file-delivery, allowed-hosts, progress card, guest status strip, MCP install proposal, backup, doctor --fix) | DAEMON-01, TERM-02, BIND-01, SURFACE-01, DIAG-01 `--fix` | Defaults in `section_dashboard-app-onboarding-diagnostics.md` §195. |
| **Testing FD 1–4** (isolated runner, nudge default, live-DB guard, bundle destination) | T1, T2, T3, T5 | Defaults in `section_testing-evals-qa-ops.md` §128. |
| **Other FD 1–7** (backup secrets, create-only, audit log checkpoint, node_id, somatic undo, browser automation, log redaction) | OTHER-P1, OTHER-P5 | Defaults in `section_other.md` §143. |

### C. Defer / re-scope

These packets are contradictory to Halbert's architecture, low value without a consumer, dependent on unstarted infrastructure, macOS-packaging-only, back-compat, model-name/provider-specific, or unsolicited proactive behavior.

- **DIST-02** — macOS signing/entitlements/login item. Defer until `DIST-1` (signing identity and entitlement files) is built and a founder decision exists.
- **CSC-05** — turn admission / mid-turn verbs. Split into 05a (admission/idempotency/A07 fixes) and 05b (executor integrity / new verbs). The full packet is too large for one branch; defer 05b until 05a and the founder decisions (FD 4/7/8) are settled.
- **SURFACE-01** — progress/staleness/onboarding/skills UI. Split into 01a (status/progress), 01b (hygiene), 01c (onboarding/settings/skills/scheduler UX). Defer 01c until BIRTH-1/first-run design and the scheduler job-creation API exist.
- **MEM-P5** — staged writes, vault, prospective memory. Multiple founder decisions; also depends on the F-3 curated-core and continuity write-approval. Defer until the memory-boundary decisions are ratified.
- **VMV-5** — day journal (C14). Defer until `vision/redact.py` is reviewed and the founder explicitly opts in; keep the screen-truthfulness M3 slice in Tier 2.
- **MCP-A / MCP-B** — if `R-09` is confirmed merged, re-scope these to verification-only rather than new implementation; the core child-env whitelist, frame bounds, and metadata hygiene are already landed.
- **DIAG-02 / MEM-P3 / CSC-04** — re-scope to diagnostic/reporting surfaces after `R-04` (conversation store / state ledger hardening) is verified; do not re-implement the A08/A16 fixtures already in R-04.
- **MP-5** — local-model output robustness. Large, and depends on MP-2 C6; defer until MP-2 is merged.
- **MP-4** — measured context/residency. Defer the cost figure (FD 7) and `keep_alive` (FD 6); instrument usage rows now and hold arithmetic.
- **SCHED-P6** — user-created scheduled jobs. Defer the create endpoint/form until P1/P3 land and the founder names the first job type; ship list/history/cancel first.
- **TT-06** — subagent manager production wiring. Fix M1/M2 regardless, but defer production consumer wiring until a concrete consumer is named.
- **SP-5 / SP-6** — curator and authoring commands. Defer until SP-1 (catalog), SP-3 (multi-tool), and the `/learn`/`/review` consumers exist.
- **F07 / F14 / F16 / F20** — largely covered by merged R-01/R-02/R-08/R-05/R-07/R-11; treat as verification reads, not new packets.
- **Any packet proposing Linux/systemd-specific daemons, migrations, back-compat shims, unsolicited proactive model messages, or provider/model-name surfaces** — re-scope or reject per the standing directives in `AGENTS.md`.

---

## Verification & caveats

- **Report path:** `/Volumes/4TB-BAD/Halbert/.handoff/OSS-PASS-2-DISCOVERY-BACKLOG-PRIORITIZATION-2026-09-11.md` (the requested path did not exist, so no numeric suffix was needed).
- **No code was changed; no tests were run; no commit was made.**
- **Coverage limitations:** The discovery pass itself notes that 21 of 46 units are operationally thin, and large areas (`openclaw` agents/UI/apps, Hermes desktop/UI, MCP server side, provider configuration, onboarding, TUI, PTY bridging, dashboard-equivalent UX, plugins, self-update) remain shallow. Rankings therefore rely on density signals and the verifier-corrected sources, not on complete reads.
- **Remediation overlap:** Several discovery packets (notably `MCP-A`, `MCP-B`, `VMV-2`, `SP-1`, `DIAG-02`, `MEM-P3`, `P4`, `P2`, `MEM-P2`, `MEM-P4`, `CSC-04`, `MP-1`, `T4`) overlap with the merged opus/sonnet remediation packets. The dispatch plan assumes those remediation packets are verified merged before work starts; if any are not, the corresponding discovery packet must be re-ranked.
- **Founder decisions:** The `Ready now` group is strict about *no* open founder decisions. Packets with recommended-but-unratified defaults are placed in `B. Needs founder decisions first`.
- **Shared hot files:** `agents/state_machine.py`, `dashboard/app.py`, `dashboard/routes/agent.py`, `tools/executor.py`, and `agents/conversation_sqlite.py` are touched by multiple high-priority packets. The dispatch order and worktree ownership notes above must be respected to avoid rebase collisions.
