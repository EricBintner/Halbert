# PKT-SCHED-P6 — Scheduled-work surface (list/history/cancel) + webhook normalizer + digest

Tier: **opus**   Milestone: **M4**   Effort: **S-M**
Collision lane: **D**   Merge order: **2/4 in D**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**SCHED-P6** — Scheduled-work surface (list/history/cancel) + webhook normalizer + digest.

## 2. User problem

Three pieces of already-real machinery are invisible or unguarded. (1) The dashboard's scheduler surface is dead client code: `lib/tauri.ts:209-218` exports `getScheduledJobs()` and `cancelScheduledJob()` against live endpoints (`dashboard/routes/settings.py:2963-2988`, `dashboard/routes/jobs.py:13-110`), and nothing in the frontend calls them — there is no scheduler page at all in `App.tsx`'s route table, so an operator cannot see what the machine has scheduled, when it last ran, what the receipt said, or cancel a job from the UI. The machine runs real scheduled work today (the detector sweep and the morning report via `scheduler/autonomous_tasks.py:527-560`) and speaks as the computer itself — but cannot answer "what do you have scheduled?" on any surface. (2) Any outbound URL Halbert accepts from config (webhook-style delivery targets) goes out unnormalized: no scheme restriction, no rejection of embedded userinfo, no present-but-blank rejection — the OpenClaw `src/cron/webhook-url.ts:16` pattern (HTTP(S) only, reject userinfo) has no Halbert analogue. (3) The weekly host-state digest exists (`proactive/morning_report.py:55-180`, a fixed-shape deterministic template behind `ProactiveGate`) but it only reports what it found: it never names what was deferred or could not be checked, and it never reads an approved write back before claiming it landed — `findings/proposals.py:36-66` records `execution_result` and nothing re-reads the changed record, so the digest can assert a change the disk does not show. Verdict source: FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md row SCHED-P6 = RESHAPE ("Ship dashboard list/history/cancel, webhook normalization, digest improvements. Defer user-created jobs and detached task registry."); deep-eval-group2-scheduler-terminal-voice.md SCHED-P6 section = "DEFER (with two exceptions)", exceptions being the dashboard page (OC23-C13 list/history/cancel half) and the digest improvements (HM20-C11), plus the webhook normalizer (OC18-C14, ~20 lines, applies now to any outbound URL from config) and HM16-M9 recorded in DECISIONS.md at effort 0.

## 3. What to build

Three deliverables, all founder-independent, landing together.

**A. Scheduler page — list / run history / cancel (OC23-C13 half).** New `halbert_core/halbert_core/dashboard/frontend/src/pages/ScheduledJobs.tsx` plus a `<Route path="/scheduled" element={<ScheduledJobs />}>` entry in `App.tsx` beside `/approvals` and a nav link in `components/Layout.tsx`. The page wires the existing dead functions: `getScheduledJobs()` (lib/tauri.ts:209) against `GET /api/settings/scheduler/jobs` (settings.py:2963) and `cancelScheduledJob(jobId)` (lib/tauri.ts:214) against `POST /api/settings/scheduler/jobs/{id}/cancel` (settings.py:2979). Per job render from the existing `ScheduledJob` interface (lib/tauri.ts:168-183): name/task, state, `next_run`, last receipt status, and liveness ages. A run-history section reads run receipts (the `scheduler/run_receipts.py` store) through the jobs detail route (routes/jobs.py:69 `get_job_details`); a receipt drawer classifies a failed lookup deterministically as one of `not-found | expired | corrupt | ambiguous` from receipt data fields — never from an error string (OpenClaw run-inspector-model.ts:131-138 pattern). Cancel is a confirmation-gated button that calls the existing route only — no new backend endpoint. All colours from `shared-tokens/tokens.css`; no emoji (drop the origin's `emoji` field); no create form (see exclusions). If the cancel route proves not to stop a scheduled job at fire time (HM16-M1: routes/jobs.py builds its own `SchedulerEngine` and calls `engine.cancel_job`, which writes `state='cancelled'` to JSON without touching APScheduler or `AutonomousExecutor.cancel_job` at executor.py:528), that is a SCHED-P1 dependency — this page surfaces the defect but does not fix it; note it in the PR description if observed.

**B. Webhook URL normalizer (OC18-C14, ~20 lines).** A small pure function — home it in `halbert_core/halbert_core/scheduler/executor.py`'s module neighbourhood or a new `scheduler/webhook_url.py` — that takes a configured outbound URL string and returns a normalized URL or raises a typed rejection: scheme must be `http` or `https`, embedded userinfo (`user:pass@host`) rejected, present-but-blank rejected, host required. Apply it at the point any outbound URL is read from config, so future delivery targets inherit the guard. Deterministic, no model, no network call at validation time.

**C. Weekly digest improvements (HM20-C11).** Two deterministic additions to `MorningReportGenerator.generate()` in `proactive/morning_report.py`: (1) a "coverage gaps / deferred" section naming what the sweep could not check and what was deferred, sourced from the same measured data the report already collects — the report currently lists only what it found; (2) read-back verification of approved writes: for each approved proposal whose `execution_result` is recorded in `findings/proposals.py:36-66`, re-read the changed record/file and compare against the digest recorded in the change ledger (LEDGER-1), reporting "landed" only when the read-back matches and "claimed but not present" when it does not. DETERMINISTIC TEMPLATE, never a model — the optional summarizer stays optional and untouched. The report speaks first person as the computer, grounded in measured data, per the standing frame.

Also record in DECISIONS.md at effort 0: HM16-M9 (no inference-slot field on the agent-facing scheduling tool — record the invariant, no code) and OC18-M6's delivery-destination invariant if not already present (a scheduled/autonomous message is delivered only to a destination named on the job or carried by its own session, never a globally shared last recipient).

## 4. What NOT to build

Per the RESHAPE verdict, the following from the original SCHED-P6 scope are NOT built here. (a) No create endpoint and no create/edit form — "a create endpoint on an engine that cannot cancel is not shippable"; creation is gated behind founder decision 7 and HM16-M2/M5 (SCHED-P1 lock/cancel fixes) — tail, needs a named consumer. (b) No NL schedule parser, no timezone-correct cron handling, no three job shapes (prompt/script-augmented/no_agent), no per-job durable notepad — all consumer-facing features for user-created jobs that do not exist — tail, founder decision 7. (c) No consent-first automation suggestion queue (HM16-C2/C3, HM10-C18) and no batch classifier script (HM16-C21) — needs the create-job API that does not exist — tail, founder decision 7; when built, proposals must respect the proactive dial and be staged, never executed. (d) No detached background-task registry (OC09-C1, effort L — one registry across scheduled job / subagent / execute_code / terminal block), no delivery outbox (HM16-C6), no notification-level idempotency keys (OC09-C3), no three-way completion status (OC18-C16) — deferred behind a named dashboard consumer ("Workloads rail" does not exist); dispatch after Theme 1 so receipts are trustworthy input — tail. (e) No run-receipt inspector taxonomy backend rework beyond the deterministic drawer classifier; no `mergeDecisionPage` cross-id merge logic — the full OC23-C21 inspector is sequenced after C13 and is largely N/A at this scope. (f) No hard-exit watchdog, launchd registration, or any supervisor path — gated by founder decision 2 and HM11-M2. (g) The cancel-route fire-time defect itself (HM16-M1, route builds its own engine and never calls `AutonomousExecutor.cancel_job`) is SCHED-P1's fix, not this unit's — this page depends on it but must not re-implement it.

## 5. Target files
- `halbert_core/halbert_core/dashboard/frontend/src/pages/ScheduledJobs.tsx` [new file]
- `halbert_core/halbert_core/scheduler/executor.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M, matching the packet header. The frontend half is the bulk: one new page (~200-300 lines of TSX following the existing pages' pattern — Approvals.tsx is the nearest analogue: a list from a lib/tauri.ts call plus a detail view), one route line in App.tsx, one nav entry in Layout.tsx, a small deterministic classifier function for the receipt drawer with a vitest table, and a route-shape test. The backend work is genuinely small: the webhook normalizer is ~20 lines of pure string/URL parsing plus a handful of pytest cases (scheme, userinfo, blank, no-host); the digest additions are two new deterministic sections inside an existing 230-line generator that already collects the inputs — the coverage-gaps section reuses the sweep's own skip/defer data, and the read-back compares two already-recorded values (change-ledger digest vs current file read). No new endpoints, no new dependencies, no schema changes, no migration (no users yet — leave superseded data unread). Sized up from pure-S only because the digest read-back touches the findings/proposals seam and the page must match the design-token and first-person-voice conventions exactly. No founder decision blocks any of the three deliverables — that is precisely why the RESHAPE kept them.

## 8. UX rationale

A new "Scheduled" entry in the dashboard nav (Layout.tsx) routing to `/scheduled`. The page speaks as the computer in first person, grounded in measured data: a header line like "I have N scheduled tasks; M ran in the last 24 hours" (counts from `getSchedulerStatus()`, lib/tauri.ts:204), then a list with one row per job — task name, state badge, next run time (relative, e.g. "in 3 hours"), last run receipt status (ok / error / delivery_failed / interrupted from the closed receipt status set), and a cancel action. Cancel opens a confirmation dialog ("Stop this scheduled task? Future runs will not fire.") and on confirm calls `cancelScheduledJob`; the row's state updates from the re-fetched list — staged-then-confirmed, never silently executed, matching the commands-staged rule. Clicking a row opens the receipt drawer: run history newest-first, each entry showing scheduled instant, started/completed timestamps, status, and error text when present; a failed receipt lookup renders the deterministic classification chip (not-found / expired / corrupt / ambiguous) with a one-line remediation hint. Empty state: "I have nothing scheduled right now." All colour, spacing, and typography from `shared-tokens/tokens.css` — never a hardcoded colour; run `scripts/check_contrast.py`. No emoji anywhere (the origin design's `emoji` field is dropped). No AI model named on any surface. The weekly digest's two new sections appear in the existing morning report's fixed template — "What I could not check" listing deferred/unchecked items, and "Verified writes" listing each approved write as landed (read-back match) or claimed-but-not-present — first person, measured data only, deterministic.

## 9. Acceptance criteria

1. Navigating to `/scheduled` renders the page; the list is populated from `GET /api/settings/scheduler/jobs` and shows the two production jobs (detector sweep, morning report) when the backend has them registered. 2. Cancelling a job from the UI issues `POST /api/settings/scheduler/jobs/{id}/cancel` exactly once after confirmation and the row reflects the cancelled state on refetch; no cancel fires without the confirmation step. 3. The receipt drawer renders run history for a job and classifies a failed receipt lookup into exactly one of the four deterministic buckets from receipt data (not from an error string). 4. The webhook normalizer accepts `https://host/path` and `http://host/path`, and rejects: a blank string, a scheme other than http(s) (`ftp://…`), embedded userinfo (`https://user:pass@host/…`), and a URL with no host — each rejection typed. 5. The morning report contains the two new sections when the generator runs: the coverage-gaps section names at least the sweep's deferred/unchecked items, and the read-back section reports "landed" only for approved writes whose current on-disk record matches the change-ledger digest, "claimed but not present" otherwise. 6. No emoji, no hardcoded colour, no model name, first-person voice throughout. 7. DECISIONS.md gains the HM16-M9 inference-slot invariant entry (and the delivery-destination invariant if absent). 8. Nothing in the original packet's deferred tail (create form, NL parser, suggestion queue, task registry) appears in the diff.

## 10. Verification (measured state, not model judgment)

Runnable checks against measured state, all from the repo root (this worktree):

1. Frontend unit tests: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/pages/ScheduledJobs.test.tsx` — the new test file must pass: (a) the page calls `getScheduledJobs` on mount and renders one row per returned job; (b) the cancel flow calls `cancelScheduledJob` only after the confirmation dialog confirm, not before; (c) the receipt classifier table: for each fixture receipt state (missing file, past-retention receipt, unparseable JSON, two receipts matching one id), the classifier returns the expected bucket — exit code 0.

2. Route-shape test (Python): `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "scheduled_jobs_route or scheduler_jobs" -x -q` — a test asserting the page's list call matches `routes/jobs.py`/`settings.py:2963` response shape (`{jobs: [...]}` with the `ScheduledJob` fields) passes.

3. Webhook normalizer tests: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "webhook_url" -x -q` — parametrized cases (valid http/https accepted; blank, non-http(s) scheme, userinfo-embedded, hostless each rejected with the typed error) pass, exit code 0.

4. Digest tests: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "morning_report" -x -q` — existing morning-report tests still pass, plus new cases: a report generated with a deferred sweep item contains the coverage-gaps section naming it; a report where the change ledger claims a write the fixture file does not contain renders "claimed but not present", and one where the file matches renders "landed".

5. Type check: `cd halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit` exits 0.

6. Contrast/tokens: `arch -arm64 .venv/bin/python scripts/check_contrast.py` reports no new violations attributable to the page's styles.

7. Full-suite regression: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` — failure count does not exceed the recorded main baseline for this merge-base (main is not green; baseline first).

8. Manual measured smoke: `make dev-web`, then `curl -s http://localhost:8000/api/settings/scheduler/jobs` returns HTTP 200 with a JSON body containing a `jobs` array, and loading `http://localhost:8000/scheduled` serves the page (HTTP 200) rendering those jobs.

## 11. Exclusions

All exclusions carry the RESHAPE verdict's destination labels. (1) User-created scheduled jobs — the create endpoint, NL schedule parser (HM16-M2), timezone-correct cron handling, three job shapes, per-job durable notepad (HM16-C15/M7), suggestion queue (HM16-C2/C3, HM10-C18), batch classifier (HM16-C21), delivery plan / failure destination (the OC18-C14 delivery-routing half), create-form UI (OC23-C13 create half) —→ **M5b tail / SCHED-P6 (tail)**, gated on founder decision 7 and the SCHED-P1 cancel/lock fixes (HM16-M1/M2/M5); needs a named consumer. (2) Detached background-task registry (OC09-C1), delivery outbox (HM16-C6), notification idempotency keys (OC09-C3), three-way completion status (OC18-C16), side-effect evidence on receipts (OC14-A18) —→ **M5b tail / SCHED-P6 (tail)**, gated on a named dashboard consumer (the "Workloads rail"); sequence after Theme 1 so receipts are trustworthy input. (3) Full run-receipt inspector with `mergeDecisionPage` and remediation codes (OC23-C21 beyond the drawer classifier) —→ **M5b tail**, sequenced after C13. (4) Cancel-route fire-time authority fix (HM16-M1), engine lock/flock (HM16-M5), owner pid+start-time identity (OC06-C13/M4), receipt terminalization on abandonment (OC18-M7), job-store permissions (HM16-M8) —→ **SCHED-P1** (Run ownership identity theme), a different unit; this unit depends on HM16-M1 for cancel to actually work but does not implement it. (5) Event-loop watchdog, startup-deadlock watchdog, launchd registration, hard-exit paths —→ **SCHED-P5 tail**, gated on founder decision 2 and HM11-M2 (no supervisor, no hard-exit watchdog). (6) Sleep/wake lease (OC22-C4), port guardian (OC22-C11), event-loop health (OC17-C4), tri-state readiness (OC17-C5) —→ **dropped per RESHAPE** (low value / laptop-only, explicitly deferred in the group-2 eval). (7) Marker-forgery Unicode folding (OC18-M5) —→ prompts/redaction workstream hand-off, not this unit. (8) No new npm or Python dependencies; no schema migration; superseded data left on disk unread.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
