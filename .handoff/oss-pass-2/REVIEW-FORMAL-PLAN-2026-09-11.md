# REVIEW — OSS Pass-2 Formal Implementation Plan

Written 2026-09-11 by the review session (fable-tier). This reviews
`.handoff/oss-pass-2/FORMAL-IMPLEMENTATION-PLAN-2026-09-11.md` against the
authoritative verdicts, the four deep-evals, the actual codebase, the four OSS
origin checkouts, and the git state.

Evidence sources, all independent:

1. A deep-verification pass over the plan against the live tree (14 defect
   spot-checks, full path/symbol audit, full collision map, dependency audit,
   directive-compliance audit, activity-clock contract audit, git-state check).
2. An OSS spot-verification pass over the four origin checkouts
   (`/Volumes/Thunderbolt/AI/OSS/{hermes-agent,open-claude-code,openclaw,warp}`).
3. A five-lens adversarial review workflow (156 agents): verdict-consistency,
   directive-compliance, ux-value, oss-fidelity, packet-sufficiency — every
   finding then attacked by three independent refuters; only findings that
   survived with fewer than two refutes are reported as confirmed.
4. A completeness critic that looked for what every lens missed.

Verdict key: **plan-correct** (verified true), **plan-wrong** (verified false),
**plan-incomplete** (true as far as it goes, missing something material),
**partially-true** (right substance, wrong detail).

---

## 1. The plan's strong half — what survives review

The plan's technical diagnosis of the codebase is reliable. All 14
defect-claim spot-checks resolved TRUE or PARTIALLY-TRUE on substance:

| Claim | Verdict |
|---|---|
| SP-3 multi-tool dispatch drop | plan-correct (defect real; line cite stale — real site `state_machine.py:3426`) |
| MP-5 `_normalise_tool_calls` coerces to `{}` | plan-correct (`model/client.py:461-465`) |
| MP-2 Retry-After clamped to 60s + blocking sleep | plan-correct (`rate_limiter.py:61,109`; `tier_router.py:736`) |
| MP-3 `aiohttp.ClientTimeout(total=120)` kills streams | plan-correct (`llm_client.py:83,149,165,225,385`); abort hook genuinely absent |
| MP-4 char-only token estimates + name-keyed cache | plan-correct (`client.py:1228`, `_NUM_CTX_CACHE` keyed by name only) |
| SP-4a `/help` `/h` drift | plan-correct (`Terminal.tsx:281` handles them; `reserved.py:45-50` doesn't reserve them) |
| SURFACE-01a `expires_at` never compared | plan-correct (`approval/engine.py:158` sets it; no comparison exists) |
| OTHER-P6a `DebugContext.tsx:37` unguarded localStorage | plan-correct (real path `contexts/DebugContext.tsx:37`) |
| SCHED-P5 ten unbounded awaits | plan-correct (`app.py:1669-1779`, none wrapped in `wait_for`) |
| routes/settings.py is 3200+ lines | plan-correct (3491 lines) |
| DAEMON-01a needed (no flock/exit vocabulary) | plan-correct (nothing exists today) |
| SURFACE-01b 20+ setInterval | plan-correct (29 across `dashboard/frontend/src`) |
| Dependency graph (MEM-P6→MP-4, MP-3→MP-2, GW-A→CSC-06, DAEMON-01b→activity_clock+DAEMON-01a) | plan-correct — no backwards or fabricated edges |
| Directive compliance of the plan's own text | plan-correct — no model names on surfaces, no UI-executed commands, no `_is_home_variant` gating, no hardcoded colours/emoji |

The milestone restructuring (from the 28-unit Phase-3 logjam to cohesive
subsystem groupings) is a genuine improvement, correctly adopted from the
external review. The "milestones are themes, not serialization barriers"
principle is correct and correctly applied to CSC-06 and BIND-01a. The
correction of MP-5's accidental drop and activity_clock's missing builder are
both real fixes. The pushback on the external review's oversteps (restoring
text_hygiene, restoring the ~15 dropped packets, rejecting the rigid tactical
directives) is well-reasoned and stands.

The OSS spot-verification confirms the plan is origin-accurate in almost every
case: every mechanism the plan claims exists in an origin repo exists at the
cited files, with only two corrections (§3.4 below).

---

## 2. Blockers and majors — confirmed findings

### 2.1 Packet accounting is the plan's weakest claim (BLOCKER)

The plan's §7 says: "Every packet from the final critical report is accounted
for in this plan. No packet is dropped. No packet is unaccounted for." This is
false in five distinct ways.

**(a) The report's own counts are wrong, and the plan doesn't notice.** The
final report's per-section verdict tables yield ACCEPT 38 / RESHAPE 30 / DEFER
6 / REJECT 0 = 74 packets. Its own "Aggregate counts" table claims ACCEPT 27 /
RESHAPE 31 — and its ACCEPT row at line 232 lists 38 IDs while its count cell
says 27. The report header says "~84 proposed packets" but only 74 have
verdicts. The corrected plan must use the true counts (38/30/6/0, total 74)
and not repeat the erroneous 27.

**(b) F01–F20 appear nowhere in the plan.** Grep for F01..F20 in the formal
plan: zero hits. The final report §5 gives all 20 explicit dispositions
(read-now / read-later / skip). Excluding research reads from a build plan is
defensible — but the plan must SAY that, not claim blanket accounting.

**(c) Four buildable RESHAPE packets are silently dropped** — P3 (halt
residual), P5 (centralized SSRF/base-URL guard, which the report's own §3.16
names a cross-cutting primitive), CSC-05, and MEM-P4. None appears in any
milestone table, any M5b tail, or any named gate. The plan inherited the drop
from the report's own §4 waves, but its "no packet dropped" claim is still
false.

**(d) Two packets' buildable cores are missing; only their deferred tails are
carried.** T3 (RESHAPE: "Accept ledger/eval metric/convention. Defer stop-gate
seam") appears only as "T3 (tail): stop-gate seam" in M5b — the accepted
verification-evidence ledger, invented-completion eval metric, and
UI-verification convention are never dispatched. T6 (RESHAPE: "Accept CSP
test, npm install-script allowlist, narrow upstream tracking job. Defer
entitlement test") appears only as "T6 (tail): entitlement test." The accepted
halves of both vanish.

**(e) The 87-unit total is achieved by counting shared primitives and split
sub-units as units** — so 87 units ≠ 74 packets, and the framing "87 units
accounting for every packet" does not survive scrutiny even before the drops
in (c) and (d).

### 2.2 Label scrambles inherited from the report (MAJOR)

The report's master-table labels for the CSC and MEM packets are scrambled
relative to its own deep-evals, and the plan inherits the scramble as
incoherent fusions — rows that wear one packet's label over another packet's
content:

| Plan row | Report label it wears | Deep-eval content actually under that ID | What the plan row actually builds |
|---|---|---|---|
| CSC-01 | Conversation crash/recovery | CSC-01 = turn-boundary trust, decode integrity | deep-eval CSC-01's content (correct), under a label that belongs to CSC-03 |
| CSC-02 | Turn admission and identity | CSC-02 = deterministic context reclaim | fuses CSC-02's label + content with CSC-05's CH-A dependency and admission verification |
| CSC-03 (M5a) | Compaction phases — verify R-12 | CSC-03 = the conversation survives the process (SIGTERM flush, interrupted-turn marker, .clean_shutdown) | only the R-12 verification; the crash-survival content is homeless |
| MEM-P2 | (report MEM-P4 row) | MEM-P4 = promotion/recall boundary | MEM-P4's residual (product-boundary test), mislabeled MEM-P2 |
| MEM-P3 | (report OTHER-P1 row) | MEM-P3 = forgotten-request tombstones | OTHER-P1's backup/recovery, mislabeled MEM-P3; real MEM-P3 tombstones dropped |
| MEM-P6 | Provenance and redaction determinism | MEM-P6 = compaction gate follows the real number | deep-eval MEM-P6's content (correct), under a phantom label with no defining content anywhere |

Fix: re-key every CSC and MEM unit to the deep-eval (the authoritative detail
per the report's own §8). Make each plan row's scope, dependency, and
verification describe one packet, not a fusion of two.

### 2.3 The collision map is far broader than the plan's two flags (MAJOR)

The plan's only concurrency-control mechanism is the "merge last" note, applied
to 2 of 7 `state_machine.py` consumers and 0 of the other collisions. The full
map, generated from the plan's own Files columns:

| File | Units touching it | Plan flags it? |
|---|---|---|
| `agents/state_machine.py` (7) | SP-3, MP-5, DAEMON-01b, TT-05, CSC-01, CSC-02, SCHED-P4 | Partial (only DAEMON-01b + TT-05 "merge last") |
| `tools/safety.py` (4) | TT-03, TT-04a, P1, P6 | NO |
| `model/client.py` (3) | MP-5, MP-3, MP-4 | NO |
| `tools/executor.py` (3) | TT-01, TT-03, P1 | NO |
| `streaming/pty.py` (3) | CSC-06, GW-A, MP-6 | Partial (CSC-06+GW-A only) |
| `approval/engine.py` (2) | P2, SURFACE-01a | NO — and the two units CONFLICT (see 2.4) |
| `agents/conversation_sqlite.py` (2) | CSC-01, CSC-04 | NO |
| `agents/llm_client.py` (2) | MP-3, MEM-P6 | NO (cross-milestone M1×M3) |
| `model/llm_config.py` (2) | MP-4, BIND-01a | NO (cross-milestone M1×M2) |
| `dashboard/__main__.py` (2) | DAEMON-01a, CSC-06 | NO |
| `dashboard/app.py` (2) | DAEMON-01a, SCHED-P5 | NO |
| `scheduler/executor.py` (2) | SCHED-P6, SCHED-P2 | NO |
| `dashboard/routes/settings.py` (2) | BIND-01a, OTHER-P6b | YES (rebase risk noted) |

The corrected plan must extend merge-sequencing guidance to every row of this
table, not just the state machine.

### 2.4 approval/engine.py: an unresolved ownership conflict + inverted ordering (MAJOR)

Both P2 (M2) and SURFACE-01a (M4) claim approval-expiry enforcement — P2's
deep-eval proposes "make approvals expire," SURFACE-01a's row is "expired
approval rejected." Two cold sessions would both implement expiry in the same
419-line file and conflict. Worse, the ordering is inverted: P2 binds approvals
to artefact content-sha256 to prevent the approve-then-replace race, but the
approval it binds can still be a stale/expired one because `expires_at` is
never compared to now (`approval/engine.py:158` sets it; the `EXPIRED` sentinel
at `:28` is never assigned). Binding the artefact hash before enforcing expiry
hardens the wrong axis first — a tamper-proof reference to an authorization
that should have been refused on time grounds. Fix: assign expiry enforcement
to exactly one unit (SURFACE-01a, per the group-4 deep-eval) and state the
dependency explicitly: expiry enforcement lands before or with P2's artefact
binding.

### 2.5 MEM-P3 and OTHER-P1 build the same backup mechanism twice (MAJOR)

The plan's M3 has BOTH "MEM-P3: `halbert backup` (online backup API + verified
manifest), `halbert recover` (copy-first salvage)" AND "OTHER-P1: state backup /
create-only behavior" — two sessions writing `halbert backup` into
`continuity/` in the same milestone. This is an active duplicate build plus the
silent drop of an ACCEPT packet (the real MEM-P3 tombstones). Fix: merge into
one backup unit (OTHER-P1, which the report scopes as create-only) that absorbs
the durability items, and restore the tombstones unit as its own row.

### 2.6 The activity_clock contract is under-specified for all four consumers (MAJOR)

The plan's contract — `record_activity()`, `idle_seconds()`, `is_stalled()` —
reads as a single global clock, but every consumer needs independent or
namespaced instances: SCHED-P2 runs N concurrent jobs keyed per-`job_id`
(N independent idle clocks); SCHED-P4 and DAEMON-01b track per-turn/per-lock
age; MP-3 needs a per-stream activity timestamp. What's missing:

1. **Instancing semantics** — the plan never says whether consumers instantiate
   `ActivityClock()` per job/turn/stream or call `record_activity(key)` on a
   shared registry. This is the difference between a working and a broken
   consumer.
2. **Configurable `idle_timeout`** — the external review's version had it; the
   formal plan dropped it. SCHED-P2's whole point ("honest inactivity-based
   timeouts, not flat wall-clock") requires a per-consumer threshold.
3. **`source: str` tagging** — dropped from the review's version; DAEMON-01b's
   "one typed receipt per reclamation" needs it to name what was reclaimed.
4. **Thread/async safety** — MP-3 closes an aiohttp response "from a foreign
   thread"; SCHED-P2 runs on APScheduler worker threads. The contract is
   silent. (The existing `agents/turn_activity.py` uses a `threading.Lock` — a
   precedent worth carrying over.)

Corrected contract: a per-instance (or per-key) monotonic tracker with
`record_activity(source)`, `idle_seconds()`, `is_stalled(idle_timeout)`,
thread-safe, each consumer instantiating its own, built on `time.monotonic()`.

### 2.7 activity_clock's home: both docs are wrong, in different ways (MAJOR)

The final report says "extend the existing `agents/turn_activity.py`" for the
activity clock. That is a category error: `turn_activity.py` (lines 23-66) is a
**generation counter for race-safe cancellation** (`stamp()/claim()`), not an
idle-time clock — it has no `record_activity()/idle_seconds()/is_stalled()`.
The formal plan silently switches to a new `utils/activity_clock.py` without
noting the discrepancy or that `turn_activity.py` is unsuitable. The corrected
plan must build the new module AND state explicitly why `turn_activity.py` is
not the home (it tracks cancellation generations, not wall-clock idleness), so
no future session "consolidates" them.

### 2.8 File-path precision: a dozen stale or wrong paths/symbols (MAJOR)

| Unit | Plan cites | Reality |
|---|---|---|
| SP-3 | `state_machine.py:2669` | `:3426` (`response.tool_calls[0]`); 2669 is interest-recall code |
| MEM-P1 | `continuity/memory_v2.py` | does not exist; `memory_v2` is the Haloysius upstream, reached via `integrations/haloysius_memory_adapter.py` |
| VMV-1, VMV-6 | `voice/wake.py`, `voice/pipeline.py` | no `voice/` package; real: `audio/speech/wake_word.py`, `audio/pipeline.py` |
| text_hygiene | `mcp/metadata.py:strip_unicode_tags` | symbol doesn't exist; real: `mcp/metadata.py:66 sanitize_metadata_text()` |
| subprocess_env | "R-09's `build_child_env` pattern" | symbol doesn't exist; real: `mcp/client.py:153 child_env()` — and it is ALLOWLIST-based, while MP-6 needs a BLOCKLIST (strip credential-shaped names) |
| MEM-P6 | `agents/assembler.py` | real: `context/assembler.py` |
| MEM-P3 (backup) | `continuity/backup.py` | does not exist, and not marked "new" |
| OTHER-P6b | `dashboard/settings_reload_plan.py` | does not exist, and not marked "new" |
| VMV-3 | `routes/audio.py`, `frigate_tools.py` | real: `dashboard/routes/audio.py`, `integrations/frigate/frigate_tools.py` |
| SURFACE-01b | `usePolling.ts`, `SkillsSettings.tsx` | neither exists (new components); `setInterval` count is 29 |
| SCHED-P6 | `ScheduledJobs.tsx` | does not exist; the API exports are at `lib/tauri.ts:209-218` |
| OTHER-P6a | `DebugContext.tsx` | real: `contexts/DebugContext.tsx` (plural dir) |
| LOG-01 | "same 30-line `obs/logging.py` hub" | 66 lines; and `JsonFormatter` ALREADY exists at `:45` — the residual is the RotatingFileHandler + RedactingFilter + LogRecordFactory, not the formatter |
| GW-A | "55 bare `{'error': str(e)}`" in `mcp/server.py` | 18 sites, not 55 (inflated ~3x) |

The corrected plan must tag every file entry [exists @ path:line] or [new
file], and pair every line reference with an anchor (symbol name or distinctive
string) plus a "verified against <sha> on <date>" stamp, because line numbers
drift under concurrent sessions (the corpus itself warns of this;
`ConfirmationDialog.tsx`'s `dangerouslySetInnerHTML` moved from :52-57 to :90
already).

### 2.9 The handoff's deliverable spec omits the artifacts dispatch needs (MAJOR)

The handoff's §13 asks for a review, a verbose plan, and a return handoff. It
never asks for: the dispatch-packet template (the 11 fields have no defined
envelope), the machine-readable packet index/manifest (the ASCII dependency
graph has omissions and there is no per-unit registry), the complete hot-file
collision map (§11.3/§11.7 admit it's incomplete, with no deliverable to carry
the verified result), or the gate registry (founder-decision references are
bare numbers — "founder decision 2", "FD-3", "FD-4" — that resolve to nothing
in DECISIONS.md's unrelated numbering). The corrected plan adds all four.

### 2.10 "Verification-by-measured-state" is a principle, not a protocol (MAJOR)

The plan names the principle and gives per-unit one-liners, but there is no
integration-review protocol: no baseline-comparison procedure (which of main's
nonzero baseline failures are attributable), no per-milestone measured-state
checklist, no rule for frontend units (SURFACE-01a/b, SCHED-P6 — "staged not
executed", vitest/typecheck fan-out), and no attributable-failure rule. The
corrected plan defines it: (1) baseline pytest recorded on the merge-base
before any unit lands; (2) per-unit measured-state assertions as runnable
commands or test IDs; (3) a milestone-exit checklist of OS-observable state;
(4) frontend units verified by npm test/typecheck plus a named vitest file;
(5) a failure is yours iff absent from the recorded baseline.

### 2.11 The handoff forbids what the plan commands (MAJOR)

The handoff states twice (§0, §12) "Do not modify product code. This is a
planning task." The plan's tactical directive 1 says "SP-3 and SP-4a land
immediately." The receiving agent gets two authoritative-looking instructions
that forbid and command the same first action. The user has resolved this:
SP-3 and SP-4a land immediately as step 0 of execution, by user directive,
which supersedes the handoff's planning-only constraint. The corrected plan
and handoff both carry this reconciliation explicitly.

---

## 3. Minors and corrections

### 3.1 Effort labels understated (MINOR but consequential)

Effort labels drive dispatch batching. Several are understated against the
units' own deep-evals:

| Unit | Plan effort | Deep-eval effort |
|---|---|---|
| SP-3 | S ("one-line fix") | M (hot-file dispatch loop with confirmation-gate staging semantics; founder-noted behavior change) |
| MP-5 | S-M | L ("the largest item" in group3) |
| TT-05 | S | M+ |
| P2 | S | "massive, split" |

Labeling an L as S-M and an M as S means units get under-provisioned sessions
that run out of budget mid-build on the hottest files. The corrected plan
attaches the deep-eval's effort justification to each unit and re-labels.

### 3.2 Cross-packet riders are lost (MINOR)

MP-1's residual (the OC14-C22 reroute-notice text) is explicitly assigned to
ride MP-2 in the deep-eval and final report — but the plan's MP-2 row never
mentions it, and the M5a MP-1 row says "move to MP-2" without carrying the
content. A cold MP-2 session would ship without it. Fix: the MP-2 packet lists
the rider in its scope with the conditional ("if R-13 merged before dispatch,
include OC14-C22's slot-and-locality notice; text names slot and locality,
never the model"), and any cross-packet transfer is recorded in BOTH the
source packet's row and the destination packet's row.

### 3.3 Reconnect supervisor: a shared primitive the plan scatters (MINOR)

The report's §3.9 names a reconnect-supervisor primitive (candidate
`net/reconnect_supervisor.py`: backoff/jitter/stability-window, bounded
drop-oldest queue), needed by GW-A, VMV-4, VMV-2, MCP-C. The plan has no such
unit — GW-A, SCHED-P5 (thaw reconnect), SURFACE-01b ("reconnect owner"), and
the VMV-4 M5a residual each handle their own, recreating the
duplicate-primitive pattern the report's §3 exists to forbid. (The report
itself left this primitive out of its Wave-0 table, so this is a gap in both
docs.) Fix: add the primitive to the shared set and name its consumers.

### 3.4 OSS-origin corrections (MINOR — the plan is mostly origin-accurate)

Two corrections to what a reviewer or implementer would find:

1. **P2 (approval-bound-to-artifact) has no OSS reference implementation.** It
   is correctly attributed to openclaw in the section files
   (`packages/gateway-protocol/src/schema/exec-approvals.ts`,
   `src/infra/system-run-approval-binding.ts` — `mutableFileOperand{argvIndex,
   path, sha256}`, baseHash guard, envHash), and open-claude-code contains NO
   such mechanism (its permission layer is path-pattern-based). A reviewer told
   to look in open-claude-code would find nothing. The plan is origin-accurate;
   the dispatch packet must point at the openclaw files only.
2. **The Warp event replay ring is not in the checkout.** Warp's replay
   protocol lives in a separate private repo
   (`session-sharing-protocol`, declared at `Cargo.toml:282` but not vendored).
   What IS in the checkout: a bounded scrollback
   (`crates/warp_terminal/src/model/grid/flat_storage/mod.rs:89`) and
   `BoundedVecDeque` network logging. The closest OSS reference for a
   `since_seq` replay design is openclaw's `state.seqByRun`
   (`src/infra/agent-events.ts:265`). GW-A's packet must point there, not at
   warp.

Framing correction (not a defect): Hermes' "measured stop-gates" measure the
**exit codes of commands the agent already ran**
(`agent/verification_evidence.py:418,545`) — they do not probe port-bound or
file-hash OS state. The port/systemd/file-hash flavor is the plan's own
reinvention, and packets should say so rather than imply an OSS precedent.

### 3.5 sherpa-onnx is NOT a contract breach — cleared (MINOR, preemptive)

A review might suspect VMV-1's sherpa-onnx violates the two-hard-dependency
contract. It does not: `halbert_core/pyproject.toml:118-119` already lists
`sherpa-onnx>=1.10` and `onnxruntime>=1.16` under
`[project.optional-dependencies]`, and `openwakeword>=0.6` at `:124`. These
are existing lazy optional extras. The two-hard-dependency rule is the
**Haloysius** subtractive contract, which governs the upstream library — not
`halbert_core`, whose hard deps are already pydantic, rank-bm25, pyyaml,
watchdog, jsonschema, systemd-python, numpy, apscheduler, sqlalchemy. The
VMV-1 packet must state it is reusing an existing optional extra, to preempt
the objection.

### 3.6 Smaller confirmed corrections

- **Circuit breaker wording (A4):** the breaker is write-only — `record_failure`
  IS called (`tier_router.py:735`) but `is_circuit_open` has zero callers — so
  failures are recorded yet never read to remove a model from rotation. "Zero
  callers" is imprecise; "write-only" is exact.
- **SCHED-P5 drops the RSS log (VC-10):** the deep-eval's founder-independent
  core is bounded shutdown + unclean-exit sentinel + RSS log (HM11-C10) + thaw
  reconnect; the plan drops the RSS log and records only "LaunchAgent/supervisor"
  in the tail. Restore the RSS log to core; record the deferred sub-items
  (sleep/wake lease, port guardian, event-loop health, tri-state readiness) in
  M5b by name.
- **Support bundle has a false dependency (L3-19):** LOG-01+OTHER-P2 bundles the
  "redacted support bundle" into its scope, but the bundle depends on DIAG-01's
  doctor JSON existing — so the logging unit can't merge until DIAG-01 is done.
  Split: LOG-01 = JsonFormatter + RotatingFileHandler + RedactingFilter +
  LogRecordFactory + first-char pre-check; support bundle = a separate unit
  depending on DIAG-01 (doctor JSON) and LOG-01 (log tail reader).
- **Backup/recover must honor "no users yet" (critic gap):** the MEM-P3/OTHER-P1
  rows never state how they honor "leave superseded data on disk, unread, never
  delete." Add the explicit clause: salvage copies to a new location, never
  reads superseded rows into the live store, never overwrites live.
- **F01 is never tied to consumers (critic gap):** the report's
  highest-priority read-now (macOS host integration) is never linked to the
  buildable units it should inform. Annotate SCHED-P5, DIST-02, and DAEMON-01
  with "read F01 before dispatch."
- **The .handoff/oss-pass-2/ tree is untracked (critic gap):** the entire
  multi-session work product is one `git clean` away from gone. The corrected
  plan's tactical directives must include committing the corpus to the planning
  branch.
- **Test-baseline trap is named but not actionable (critic gap):** "baseline
  first" costs a full ~8500-test run per session and still leaves the session to
  eyeball which failures are pre-existing. The corrected plan names the
  known-red test files per hot file (the sonnet-merge survey established the
  current baseline: `test_agent_model_override.py`,
  `test_agent_model_selected_event.py`, `test_no_model_names_in_user_facing_source.py`,
  `test_num_ctx.py` — 23 failures, all from main's streaming-reasoning/num_ctx
  work).
- **DIAG-02 drops the FTS corruption-classifier fix (critic gap):** the deep-eval
  leads DIAG-02 with "fix `_is_fts_write_corruption_error`" — a confirmed
  data-loss classifier bug (bare "malformed" routes to fail-open). The plan
  drops it. Restore to DIAG-02's scope.

---

## 4. What the review REJECTS (and why)

The adversarial pass refuted 32 findings. The notable rejections — things a
naive reviewer might have "fixed" but should not:

- **"T1 should not gate the M0 primitives"** (L3-03) — refuted. T1 first is
  correct: it makes the suite trustworthy before anything depends on tests.
- **"DIAG-01 adds an unauthorized surface"** (L3-04) — refuted. The doctor is
  the report's universal diagnostic sink, explicitly ACCEPTed; it is a CLI
  subcommand and one API route, not a new conceptual surface.
- **"SCHED-P6's weekly digest could use a model"** (L2-3) — refuted. The
  deterministic-template rule is a standing directive; the packet pins it, but
  the plan as written does not open the door.
- **"MP-5's dependency on SP-3 is wrong"** (L3-08) — refuted. They share the
  tool-call path; sequencing SP-3 first is correct.
- **"OTHER-P5's mDNS fix is a directive violation"** (L3-12) — refuted. Fixing
  the raw-hostname broadcast IS the directive compliance, not a violation of it.
- **"SURFACE-01a belongs earlier than M4"** (L3-14) — refuted as a reordering;
  milestones are themes, not barriers, and SURFACE-01a has no M4-specific
  dependency — it may dispatch as early as its lane allows.
- **"M5a should note the sonnet batch may never merge"** (L3-16) — refuted as
  moot: the user has directed the sonnet batch merged as part of this work.
- **"The plan's milestone ordering is wrong"** (L3-20) — refuted. Themes, not
  barriers; the dependency graph, not the milestone number, gates dispatch.
- **"F01–F20 must be dispatched"** (VC-5) — refuted. They are research reads,
  not build packets; the plan must SAY they are excluded, not dispatch them.

---

## 5. Corrections adopted into the dispatch plan

Every confirmed finding above is adopted. The corrected dispatch system:

1. **True packet accounting** — 74 packets (38 ACCEPT / 30 RESHAPE / 6 DEFER),
   plus 20 research follow-ups (F01–F20) explicitly tracked as reads, plus the
   four restored drops (P3, P5, CSC-05, MEM-P4), plus the two restored cores
   (T3, T6), plus the real MEM-P3 tombstones. The accounting table maps every
   report packet to its disposition in the corrected plan.
2. **Re-keyed CSC/MEM units** to the deep-evals (§2.2).
3. **A full hot-file collision map** (§2.3) with merge-order lanes;
   approval/engine.py ownership resolved to SURFACE-01a with expiry-before-
   binding ordering (§2.4); MEM-P3/OTHER-P1 merged into one backup unit (§2.5).
4. **A corrected activity_clock contract** (per-instance, `idle_timeout`,
   `source`, thread-safe, `time.monotonic()`), in a new `utils/activity_clock.py`,
   with an explicit note on why `turn_activity.py` is not the home (§2.6, §2.7).
5. **Corrected file paths/symbols** throughout (§2.8), with [exists]/[new] tags,
   anchors, and verified-against-sha stamps.
6. **Four new deliverables**: the packet template, the machine-readable index,
   the collision map, the gate registry (§2.9).
7. **An operationalized integration-review protocol** (§2.10).
8. **The handoff/plan contradiction reconciled** by user directive (§2.11).
9. **Re-labeled efforts** (§3.1), **riders recorded in both rows** (§3.2),
   **reconnect-supervisor primitive added** (§3.3).
10. **OSS-origin corrections** (§3.4), **sherpa-onnx cleared** (§3.5),
    **smaller corrections** (§3.6).

The dispatch index, packet template, and per-milestone packets follow in
separate documents (`DISPATCH-INDEX-2026-09-11.md` and `PKT-*.md`).
