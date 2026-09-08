# DECISION MEMO F-4 — The Prompted Heartbeat: build one, and on what substrate?

**Date:** 2026-09-07 · **Level/effort:** fable/med · **For:** founder decision · **Origin:** packet 03 Phase C (`.handoff/OPENCLAW-LIFT-PACKET-03-SCHEDULER-DURABILITY-2026-09-07.md`) and the master plan's parking row (`.handoff/OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md` §"Decisions parked"), with the Hermes addendum absorbed.
**No code in this memo. Recommendation is mine; the decision is yours.**

---

## 1. The question, precisely

A **prompted heartbeat** would be a scheduled LLM turn, fired on a clock with no user present, that reviews assembled state and decides whether to interrupt the user — notify or stay silent. That is the thing OpenClaw built and Hermes pointedly did not. Contrast with what Halbert already runs: zero-LLM liveness (receipts, statuses, monitor-hash suppression) and the thread-tick heartbeat — housekeeping only, no prompt and no reply (`dashboard/app.py:689-821`).

The real question is narrower than "heartbeat or not": **is there a class of noticing that Halbert's deterministic machinery cannot do, worth paying an LLM judgment path for — and if so, is now the time to open one?**

## 2. What the merged scheduler already delivers without an LLM

Verified on main after waves 1–2 (`feat/lift-wave1-merge`, `feat/lift-wave2-merge`):

- **Idleness is free for check-on-X work.** The monitor-hash gate (`scheduler/monitor_hash.py`) hashes a cheap probe each tick; unchanged source → the agent run is suppressed entirely; changed → a capped unified diff is injected. Hash persisted *before* the run, so a failed run doesn't re-alert forever. `detector_sweep` is the named first member; the set is added to one deliberate line at a time, and `morning_report`/`timeline_retention` are deliberately excluded so they can never be silently suppressed.
- **Crashes and sleeps are survivable.** Bounded staggered boot catch-up (`catchup.py`, wired in `app.py`'s `register_proactive_jobs` — the boot path itself runs behind the same monitor gate), sliding-window restart budgets with a clock-rollback hold (`restart_budget.py`, wired into the executor at `executor.py:168/:348`), and run receipts persisted before side effects with dead-owner boot recovery (`run_receipts.py`).
- **"Are my automations alive and did I get told" is answerable.** Receipts carry the closed Hermes status set `ok / error / delivery_failed / blocked_config`, and consumers must ask `delivered_to_user()` rather than test `== ok` — run success ≠ user notified, and config-refused is distinct from error. This is the data the indicator light needs.
- **The thread-tick heartbeat** runs every `heartbeat_s` (60 s default), skips beats while `_turn_lock` is held, fails soft per beat, and does closes + consolidation only — zero token spend, peers inert.

The desire that originally motivated a heartbeat — "check on things periodically; don't silently drop them; don't burn tokens when nothing changed; tell me honestly what ran" — is now satisfied except for one residue: **cross-source judgment**. A hash can notice that one thing changed; only a model can notice that three unremarkable things together are worth one sentence. Whether that residue justifies an LLM path is the actual decision.

## 3. The three options

**Option A — No prompted heartbeat (Hermes's answer).** Extend the monitor-hash gate to more check-on-X jobs as they appear (cost: one named line + one probe script each, any executor), add Hermes's ticker epoch-marker files (heartbeat age / success age / last error / catch-up counter — one small session at most) so "ticker dead" is distinguishable from "nothing due," and rely on receipts + the closed taxonomy for everything else. Cost: near zero, recurring cost zero. What you give up: cross-source proactive noticing — permanently, until this memo is revisited.

**Option B — Build it on `HomeCognitiveLoop`** (`home/cognitive_loop.py`; built, tested, **zero production callers** — verified by grep). Tempting because it exists. Rejected as the substrate: (i) it is a *home-domain* loop — perceive/reason/act over HA entities, Frigate events, occupancy, `AutonomyGate` — not a general assistant heartbeat; (ii) the Halbert attunement plan (`PLAN-ATTUNEMENT-HALBERT-2026-09-06.md`) lists its `assess_presence` wiring and, in P7, an unverified defect class (stance re-emission per tick compounding under WITHDRAW) that must be proven idempotent *before* the loop is wired anywhere; (iii) it has never run in production. Adopting it as the heartbeat conflates two deliveries — enable the home loop on its own merits after its attunement preconditions land, not as a heartbeat host. Cost if forced: 4+ sessions, blocked on attunement.

**Option C — Build it as a scheduler job under the OpenClaw ground rules** (packet 03 Phase C, recorded): NO_REPLY/`HEARTBEAT_OK` suppression with the documented model failure modes (punctuation-wrapped, JSON-wrapped, trailing-token-after-substantive — OpenClaw bug #19537); zero-token idle short-circuit on an empty scratch buffer; an explicit `heartbeat_respond(notify, text)` decision, never implicit delivery; settlements; phase-aware budgets; fail-closed with a reason code. The D-7 utility slot (merged: `model/utility_slot.py`, fail-soft ladder, no hardcoded model IDs) gives it a cheap-model path that doesn't burn the chat slot. Estimate: **3 sessions** (pure policy modules + tests; executor/scratch/utility-slot wiring; dogfood against a suppression-matcher parity suite) **plus one precondition**: every notify decision routes through the attunement `decide()` machinery — see §5.

## 4. Recommendation

**Choose A now; hold C as the designed-and-blessed answer for later; explicitly not B.** Reasons:

1. **The deterministic floor just shipped and is unexercised.** Receipts, statuses, catch-up, and the monitor gate merged this week and have not yet run long enough to tell us what they miss. Building the LLM layer before observing the floor's gaps answers a question we haven't yet heard asked.
2. **House doctrine: never a model where a deterministic mechanism suffices** — the same directive the tiered-sensitivity design ratified, and Hermes is the incident-proven external demonstration that receipts + a closed enum + hash gates cover the whole monitoring-shaped demand. Both OSS projects confirm the ground rules; only one of them ships the component.
3. **Every remaining gap is interruption judgment, and interruption judgment is attunement's.** A heartbeat that decides to speak, without `decide()` — dials, standing requests, severity thresholds, PolicyStability dwell, the suppression log (A-HB-25) — would build a second, competing speaker-gate. Halbert should have exactly one.
4. **The evidence instrument exists and the standard is set.** The 09-A consolidation scorecard (`halbert_core/evals/consolidation/SCORECARD-2026-09-07.md`) ran the deterministic arms and kept `LLM_SUMMARY` SKIPPED-GATE-CLOSED — the R5 precedent: an LLM path opens when a scorecard proves it beats the cheap baseline, not before. An open-ended "review state and maybe speak" prompt is the least scorecard-able LLM surface in the program, and its core mechanism (silence suppression) is the exact surface whose model failure modes OpenClaw had to document one bug at a time.

**Evidence that would change this recommendation:** (i) the attunement suppression log, once live, accumulating a real "missed proactive opportunity" class — things `decide()` would have spoken on had a turn ever fired; (ii) a named feature you want that is irreducibly synthetic (a daily cross-domain digest "by feel," not the deterministic `morning_report`); (iii) the monitor-hash set growing to the point where diff-injection, not judgment, is the bottleneck. Any of the three ⇒ build C, with the suppression-matcher parity suite as its gate.

## 5. Attunement interaction (binding constraint)

Coordinate before any build, regardless of option: tick-fires-at-REFLECTING is pinned attunement-branch work (HB-D1 in `PLAN-ATTUNEMENT-HALBERT-2026-09-06.md` — currently the directive is parsed *after* the reply is written on every path, blocking and verified), and the Haloysius Phase-B handoff (`/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-ATTUNEMENT-PHASE-B-WIRING-AND-FOLLOWUPS-2026-09-06.md`) is complete on the engine side with Halbert-side wiring outstanding. If C is ever built, `heartbeat_respond` does not deliver — it *proposes* into `decide()`; PULL-channel and life-safety rules then apply for free. Option A today touches none of this, which is part of its appeal: it spends no attunement coordination budget while that workstream is mid-flight.

## 6. Decision line

> **F-4 is decided: Halbert ships no prompted heartbeat. Liveness and "check on X" coverage come from the merged receipts, the closed status taxonomy, catch-up, and an extensible monitor-hash gate — deterministic, zero-token, and honest about delivery. The OpenClaw heartbeat protocol (silence suppression, idle short-circuit, explicit notify, settlements, phase budgets, fail-closed) stays recorded in packet 03-C as the pre-approved design; it is built only after the attunement wiring it must route through exists and after running the deterministic floor shows a gap it provably cannot close. `HomeCognitiveLoop` is not, and never becomes, the heartbeat's substrate.**

---

*Sources: packet 03 (`OPENCLAW-LIFT-PACKET-03-SCHEDULER-DURABILITY-2026-09-07.md`, Phase C + Hermes addendum); `OSS-REVIEW-OPENCLAW-2026-09-07.md` §4; `OSS-REVIEW-HERMES-2026-09-07.md` §4/§5; `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md` (parking + wave-1/2 merge logs); `PLAN-ATTUNEMENT-HALBERT-2026-09-06.md` (HB-D1, P7); `halbert_core/evals/consolidation/SCORECARD-2026-09-07.md`. In-repo verification: `scheduler/{catchup,restart_budget,run_receipts,monitor_hash}.py` merged and wired (`executor.py`, `dashboard/app.py:548/:603`); receipts carry `ok/error/delivery_failed/blocked_config`; thread-tick heartbeat `app.py:689-821`; `HomeCognitiveLoop` zero production callers; D-7 utility slot at `model/utility_slot.py` (commit 5f78d9aa).*
