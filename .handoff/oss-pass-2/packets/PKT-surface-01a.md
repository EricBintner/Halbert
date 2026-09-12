# PKT-SURFACE-01a — Approval expiry enforcement + stale-tone + LTR defence

Tier: **opus**   Milestone: **M4**   Effort: **S**
Collision lane: **I**   Merge order: **1/3 in I**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**SURFACE-01a** — Approval expiry enforcement + stale-tone + LTR defence.

## 2. User problem

Three confirmed, security-relevant surface defects on the one screen where a person authorises privileged action and the one page that reports measured host state.

(1) Approval expiry is never enforced (OC23-M6, security defect). In halbert_core/halbert_core/approval/engine.py, ApprovalStatus.EXPIRED exists (:28) but is never assigned anywhere in the codebase. request_approval() writes expires_at when timeout_seconds is given (:155-158), but get_pending_requests() (:317-333) filters only on data.get('status') == 'pending' and never compares expires_at to now. The decision choke point, dashboard/routes/approvals.py approve_request (:225-244), guards with `if approval_req.status != 'pending'` — nothing else. Net effect: an approval request whose timeout has lapsed is still served by GET /api/approvals/pending (list_pending_approvals, routes/approvals.py:60) and can still be approved by POST /api/approvals/{id}/approve, after which the linked proposal pipeline executes the changes. A timed-out approval can still be approved. Packet P2 (artefact binding) depends on this landing first — binding a stale approval is worse than no binding.

(2) Stale-tone: the dashboard shows dead data as live (OC23-C15, violates 'grounded in measured data'). pages/Dashboard.tsx fetchMetrics (:48-63) polls getSystemMetrics() every 2s via setInterval; the catch branch only console.errors and never timestamps the last success. systemStatus keeps its last value, so when the backend wedges, the CPU/memory meters (:155-182) keep rendering a red bar (cpu_percent > 80 → text-error) or amber bar over data of unknown age — the exact inverse of speaking from measured data.

(3) Trojan-source / bidi gap on the approval surface (OC23-M1). components/agent/ConfirmationDialog.tsx renders the model-supplied description via dangerouslySetInnerHTML (:88-91). HTML-escaping already landed (renderDescription :51-57 escapes before its markdown pass; ConfirmationDialog.escaping.test.ts exists), but the container has no dir attribute and no bidi-control defence: Unicode bidi override/embed controls (U+202A–U+202E, U+2066–U+2069) or RTL script in a command description can visually reorder the command the operator is about to authorise — 'approve rm -rf /tmp/x' displayed as something benign. The 46-line escaping test has zero bidi coverage. This is the one screen where a privileged action is authorised; visual truth there is the whole security model.

## 3. What to build

Three independent slices, one branch, lane I merge order 1/3.

SLICE 1 — approval expiry enforcement (halbert_core/halbert_core/approval/engine.py):
- Add an engine helper, e.g. `ApprovalEngine.is_expired(request, now=None) -> bool` (staticmethod is fine): returns False when request.expires_at is None, else parses via the existing tolerant ApprovalEngine.parse_timestamp (:413-419, handles both the UTC 'Z' form from _get_timestamp and the legacy '+00:00Z' malformation, and the naive local form written at :158) and compares against now (default: datetime.now(timezone.utc); if the parsed stamp is naive, compare against naive utcnow — do not mix aware/naive).
- Sweep in get_pending_requests() (:317-333): after loading each status=='pending' request, if is_expired, set request.status = ApprovalStatus.EXPIRED.value ('expired'), persist via _save_request, and exclude it from the returned list. This makes EXPIRED an assigned, durable state and guarantees GET /api/approvals/pending never serves an expired request.
- Enforce at the decision choke point in the same engine (this packet owns engine.py in lane I; routes/approvals.py belongs to P2's lane): expose a narrow guard the route can call — e.g. raise/return a typed 'expired' outcome from a small `check_decidable(request)` — OR, minimally and in-scope, have get_request() (:335-350) return the request with status flipped to 'expired' (and persisted) when expired, so the route's existing `status != 'pending'` check at approvals.py:243 rejects the approve with 400 'Request already expired' with no route change. Prefer the get_request flip: zero changes outside engine.py, both list and decide paths closed.
- Do NOT touch consent/store.py or persona/permission/consent.py — they have their own working TTL ladder (_is_lapsed/expired at consent.py:244-271); this packet is the approval engine only.

SLICE 2 — stale-tone override (halbert_core/halbert_core/dashboard/frontend/src/pages/Dashboard.tsx):
- Track `const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null)`; set it (Date.now()) only inside the try branch after setSystemStatus (:52). Leave the catch branch as-is apart from NOT clearing systemStatus (keep last data visible — the defect is the tone, not the retention).
- Derive `const stale = lastSuccessAt == null ? loading : Date.now() - lastSuccessAt > STALE_MS` with STALE_MS ~ 3x the 2s poll (e.g. 10_000).
- When stale: neutralise the threshold tones on the CPU/memory/disk meters — the (cpu_percent > 80 && "text-error") / (memory_percent > 85 && "text-warning") classnames and the [&>div]:bg-error / [&>div]:bg-warning Progress overrides (:155-182, :354-355) collapse to the default muted tone, and render one subdued line in first-person machine voice naming the age: e.g. 'My sensors stopped answering {n}s ago; showing the last values I measured.' Colours only from shared-tokens (text-muted-foreground family); no emoji; never a model name. Recovery is automatic on the next successful poll.

SLICE 3 — LTR trojan-source defence (halbert_core/halbert_core/dashboard/frontend/src/components/agent/ConfirmationDialog.tsx):
- Add dir="ltr" to the description container (:88-91, the dangerouslySetInnerHTML div) and to the tool-name box (:81) so RTL/bidi content cannot reorder what the operator reads on the authorisation surface.
- Belt-and-braces in renderDescription (:51-57): after escapeHtml, strip the bidi control codepoints (U+202A-U+202E, U+2066-U+2069, U+200E, U+200F) from the source text — they survive HTML escaping unchanged and are pure visual-attack surface here. Keep the existing escape-before-markdown order untouched.
- Extend ConfirmationDialog.escaping.test.ts with bidi cases (assert controls are stripped and the rendered string contains no ‪-‮/⁦-⁩), plus a DOM-level assertion (render the component, read the container's dir attribute === 'ltr').

Tests: new halbert_core/tests/test_approval_expiry.py covering: fresh pending request is returned; request with expires_at in the past is marked 'expired', persisted, and absent from get_pending_requests; get_request on an expired id returns status 'expired'; request with expires_at in the future stays pending; naive-legacy and '+00:00Z' stamps both parse (use parse_timestamp). Vitest: extend ConfirmationDialog.escaping.test.ts; add a Dashboard stale-tone test (mock getSystemMetrics to succeed once then reject; advance fake timers past STALE_MS; assert the error/warning tone classes are absent and the staleness line is present).

## 4. What NOT to build

Everything else in SURFACE-01's RESHAPE is someone else's unit or a deferred tail; per the deep-eval 'If RESHAPE' line, build only this packet's slice:
- Typed refresh policy (OC23-M4, the 20+ setInterval sweep incl. this file's own 2s poll) → SURFACE-01b, which also owns the skills settings page (HM10-C20) and the reconnect owner (OC23-C12), and depends on the M0/M3 reconnect_supervisor primitive. Do not start converting setInterval sites here; this packet only adds lastSuccessAt to one existing poll.
- Live progress-draft compositor over SSE (OC18-C1, touches state_machine.py/turn_event_tee.py) → deferred to the M5b tail after the opus-tier state-machine work; the deep-eval sequences it after lane A settles.
- Wizard back-navigation with answer replay (OC07-C4) → deferred until BIRTH-1 (first-conversation redesign) opens; backlog line 495 lists SURFACE-01 tail (compositor/wizard/blueprint) as 'real consumers + design decisions' for M5b.
- Automation blueprint catalog (HM16-C1) → deferred until a POST /api/jobs job-creation API exists; not this packet.
- Stat-based change watcher (HM18-C5) → deferred to its skills-reload feature packet (A13-G2 consumer).
- Low items (sparkline tiles, keyboard-shortcut catalog, context-usage breakdown, tool tally, sender identity, Ollama cache, WS disconnect test, JSON-schema form, React pair drift test) → attach to their natural home packets per the deep-eval; none are built here.
- No route-layer redesign: do not rewrite dashboard/routes/approvals.py beyond what the engine-side flip achieves (P2 owns that file's lane next in lane I and will build artefact binding on top of this expiry behaviour).
- No TTL/timeout policy changes (no new default expiry values, no config surface) — enforcement of the already-written expires_at only. No migrations: pre-existing pending request files on disk are simply swept to 'expired' on read if lapsed; nothing is deleted.
- Do not 'fix' RISK_CONFIG's icon glyphs or any other visual language in ConfirmationDialog beyond the dir/bidi defence — escaping is already landed and visual restyle is out of scope.

## 5. Target files
- `halbert_core/halbert_core/approval/engine.py`
- `halbert_core/halbert_core/dashboard/frontend/src/components/Dashboard.tsx`
- `halbert_core/halbert_core/dashboard/frontend/src/components/ConfirmationDialog.tsx`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S, as the registry and deep-eval rate it, and the code confirms it: Slice 1 is one tolerant-parse helper plus a sweep in get_pending_requests and a status flip in get_request — all inside the single 419-line engine.py this packet owns in lane I, reusing the existing parse_timestamp; no other file needs to change for enforcement because the route's status != 'pending' guard catches the flip. Slice 2 is one useState, one derived boolean, and conditional classnames on three meter blocks in a 382-line page — no new components, no API change, no dependency (it deliberately does NOT wait on SURFACE-01b's typed refresh policy). Slice 3 is a dir attribute on two elements, one character-strip pass inside the already-escaped renderDescription, and test additions to an existing 46-line vitest file. Tests are one new focused pytest module plus extensions to existing vitest files. No M0/M3 primitive is required, no hot lane-A file is touched, and the deep-eval explicitly says 'may dispatch early'. The three slices share a branch cleanly because they are three files in three different layers with zero overlap.

## 8. UX rationale

All three slices protect trust on the two surfaces where the machine must be truthful: the meter page and the authorisation dialog.
- Stale-tone is the standing directive 'grounded in measured data' applied to tone: when my sensors stop answering, the meters stop shouting. A red CPU bar is a claim about the present; over data of unknown age it is a false claim, and a wedged backend currently manufactures exactly that. The override keeps the last values visible (context is useful) but strips the alarm tone and says, in first person, how old the data is — the machine admits the gap instead of performing confidence. Muted-token colour, no emoji, one quiet line; recovery is silent and automatic.
- Expiry enforcement makes 'this approval timed out' a fact the system states, not a loophole: an operator who returns to a stale prompt and clicks approve gets a plain refusal ('Request already expired') instead of silently authorising an action whose justification may no longer hold. The dialog never names a model and never executes — it stages; expiry just makes the staging honest about time.
- LTR defence is invisible when it works: the command reads left-to-right exactly as the machine wrote it, so what the operator authorises is what the operator read. On the one screen where a privileged action is authorised, visual truth is the security model; no user ever sees the defence, and no copy changes are needed beyond what exists.

## 9. Acceptance criteria

1. Engine: an ApprovalRequest whose expires_at (any of the three on-disk forms: UTC 'Z', legacy '+00:00Z', naive local) lies in the past is (a) absent from get_pending_requests(), (b) persisted with status 'expired' in its requests/*.json file, and (c) returned by get_request() with status 'expired', so POST /api/approvals/{id}/approve fails with the existing 400 'Request already expired' path. A request with expires_at in the future, or None, behaves exactly as before.
2. Dashboard: with getSystemMetrics succeeding then failing for longer than the staleness threshold, the CPU/memory/disk meters render no text-error/text-warning or [&>div]:bg-error/[&>div]:bg-warning classes, the staleness line with the measured age is visible, and on the next successful poll the threshold tones return.
3. ConfirmationDialog: the description container and tool box carry dir="ltr"; a description containing U+202E or U+2067 renders with those controls stripped; all pre-existing escaping tests still pass unchanged.
4. No file outside the three target files (plus the two named test files) is modified; no emoji introduced; any new colour reference comes from shared-tokens; no approval data is deleted.

## 10. Verification (measured state, not model judgment)

Backend (from the worktree; every Python run needs the arch prefix): `arch -arm64 ./wt_pytest.py halbert_core/tests/test_approval_expiry.py -v` — the new module must pass: (a) expired pending request swept to status 'expired', persisted, and excluded from get_pending_requests; (b) get_request returns 'expired' for a lapsed id; (c) future/None expires_at untouched; (d) all three timestamp forms parse via ApprovalEngine.parse_timestamp. Then the attributable-failure gate: `arch -arm64 ./wt_pytest.py halbert_core/tests -x -q` — failures must match the recorded 2026-09-11 baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures); anything new is yours.
Frontend: root fan-out `npm test` and `npm run typecheck` (exit 0), plus the named vitest files: `npx vitest run src/components/agent/ConfirmationDialog.escaping.test.ts` from halbert_core/halbert_core/dashboard/frontend — existing escaping cases green plus new bidi cases asserting stripped U+202A–U+202E/U+2066–U+2069 and a rendered-container dir === 'ltr' DOM assertion; and the Dashboard stale-tone vitest — fake-timer run where getSystemMetrics succeeds once then rejects past the threshold: assert absence of text-error/text-warning/[&>div]:bg-error classes on the meter blocks and presence of the staleness copy, then a successful poll restores tones.
End-to-end measured check of the defect that motivated slice 1: seed a request JSON with status 'pending' and a past expires_at under the approval data dir, start the backend (`make dev-web`), and `curl -s http://localhost:8000/api/approvals/pending` must NOT contain the id, while `curl -s -X POST http://localhost:8000/api/approvals/<id>/approve -H 'Content-Type: application/json' -d '{"approved":true}'` returns HTTP 400 with 'already expired' in the body. Exit codes and HTTP status are the measurement; no model judgment anywhere.

## 11. Exclusions

Per the deep-eval RESHAPE line and dispatch index: typed refresh policy + skills settings page + reconnect owner go to SURFACE-01b (already indexed, depends on the M0/M3 reconnect_supervisor primitive — do not duplicate it). Progress-draft compositor, wizard back-navigation, blueprint catalog, and change watcher go to the M5b tail per backlog line 495 ('SURFACE-01 (tail): Compositor/wizard/blueprint — real consumers + design decisions'), with wizard replay additionally gated on BIRTH-1 and the blueprint catalog on a POST /api/jobs API. The low items (sparklines, keyboard catalog, context-usage breakdown, tool tally, sender identity, Ollama cache, WS disconnect test, JSON-schema form, React pair drift test) attach to their feature packets per the deep-eval. Artefact binding on approvals is P2's, next in lane I — this packet lands expiry first precisely so P2 never binds a stale approval; P3 follows last in the lane. Nothing here is dropped per RESHAPE outright except the low-priority leftovers, which the deep-eval assigns to natural homes rather than deleting. Approval-route redesign and TTL policy/config changes are not deferred — they are simply out of this packet's ownership (route file belongs to P2's lane; no new expiry defaults are authorised by any verdict).

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
