# PRESENCE — brainstorm, pass 2: the slider as an authored curve

> **Status:** brainstorm, not a plan. Nothing here is decided except what DECISIONS.md already records (`ENGINE-1`, the 2026-08-23 dial decision, `CD-1`–`CD-11`).
> **Date:** 2026-09-16. This is **pass 2**, rewritten after reading the sibling research passes in this same tree:
> **opus/** `RESEARCH-PRESENCE-SLIDER-CONTROL-LAW-2026-09-16.md` (the control-law pass — eight candidate laws, verified literature, walls and constraints; cited below as **opus §N / [LN]**) and **gemini/** `RESEARCH-PRESENCE-AND-INITIATION-ARCHITECTURE.md` (the architecture pass — spectrum table, gaps, cross-app design; cited as **gemini §N**).
> **Author:** founder session (GLM-5.2, high).
> **Standing directives engaged:** the being speaks as the computer itself, first person (2025-12); one seamless conversation, hidden topic threads (2026-08-26); `ENGINE-1` — Haloysius is the home for shared mechanisms (2026-09-10); never a model where a template suffices; colours from shared tokens; no emoji in UI.

---

## 0. What changed in pass 2

Pass 1 framed the slider as an *initiation-vocabulary ladder* — the number selects which kinds of speech are enabled. The research passes, especially opus, move four positions:

1. **The law is a curve, not a ladder alone.** The slider is one visible number indexing an **authored, inspectable curve** through four axes — **source admission** (opus M3), **channel class** (M6), **patience** (M7) and **rate budget** (M2) — with the decision thresholds (M1) *derived from* those, never exposed as the control (opus §4.10). Pass 1's "adjusts thresholds at the margins" idea is exactly the failure opus §3.3 warns about and is **withdrawn**.
2. **The bottom of the slider is channel re-mapping, not silence.** Presence 0–2 should mean *stop interrupting me*, not *stop noticing* — impulses route to `PULL`/`AMBIENT` instead of being suppressed (opus M6/F4; gemini's "Silent Sentinel" keeps noticing too). This is the cheapest large win in the space and was under-weighted in pass 1.
3. **The top is blocked on memory, not policy, and the wall is load-bearing.** `_NEVER_SPEAKS` (verified: `autonomous_engine.py:599`) is deliberately placed, and the resolution is not to weaken it but to convert it from a constant into **the tail of an admission ladder whose rungs each carry an evidence requirement** (opus §3.2, M3). What actually gates the top is the **open-loop/commitment record** nobody in the family has (opus F5, §8.1): *a high presence setting shipped before open loops exist produces filler, and filler is worse than silence* (zombie effect, opus [L23]).
4. **"10" is, verbatim, the harm literature's definition of the product class it warns about** (opus F6, [L26]: companions "seek out and sustain interaction … initiate conversation, remember past exchanges, build an ongoing relationship"). The conclusion is not "don't build it" — it is that **per-consumer ceilings, regularity (C-4) and non-solicitability (C-3) are the load-bearing parts of the design**, not afterthoughts.

Pass 1 positions that **survive** the research: the dial/slider split (events vs volition — opus C-8/LimitKind confirms the axes must not collapse), `ENGINE-1` engine placement of the parameter space, reactions-before-volition sequencing, the commitment record as the one genuinely new mechanism (opus independently arrives at it as the blocking prerequisite), and the shadow-first rollout.

Where the two research passes conflict, §5 adjudicates. Code facts they lean on were re-verified against both trees today (see §7 note).

---

## 1. The idea, restated against the research

A single **presence scale, 0–10, default 3** for Halbert, presented as one prominent control ("presence," not "chat mode" — gemini §2.2's modal-confusion argument is right, and the founder's own instinct said slider-not-toggle first). Mechanically the number indexes a curve through four axes:

| Axis | What it moves | Where it lives today |
|---|---|---|
| **Admission (M3)** | *which classes of impulse may reach the policy at all* — `_NEVER_SPEAKS` becomes the ladder's tail; each rung admits a class **with its own evidence bar** | `TriggerType` (engine, 9 values) + `ProactiveEvent` category/severity (Halbert); the two taxonomies must be reconciled per rung (opus M3 cost) |
| **Channel (M6)** | *how an admitted impulse arrives* — PUSH / AMBIENT / PULL, "may update, must not escalate" for ambient | `ChannelClass` + `Surface` in both trees; `surfaces.py` already cites Weiser & Brown |
| **Patience (M7)** | *how long an impulse waits for a good moment* — bounded deferral to coarse breakpoints, then re-route or expire | `HOLD` + `ResumeCondition` + `HOLD_MAX_S`; the release wiring is the liability and the mechanism |
| **Budget (M2)** | *how many unbidden interruptions per period* — a ceiling, never a target | `AttachmentSafety.max_proactive_per_day = 3` |

Thresholds (`SPEAK_T`/`ASK_T`, M1) are **derived** from the four and stay unexposed. The `WARNING` ask-band is 0.10 wide with 0.05 hysteresis; an eleven-position linear redistribution of it allocates 0.01 per notch — below single receptivity weights (opus §2.2, §3.3). That wall is why M1 must never be the knob.

**What each position means to a person** (opus M3's key property: every position has a sayable meaning — "here is what I allow it to bring up"). The settings surface describes positions as *what may be raised and how it arrives*, e.g. position 3 ≈ *"warnings and the morning report reach me; observations stay on the badge and in findings unless they recur"*. That phrasing satisfies the standing directive that everything carries its why.

---

## 2. The curve, sketched (illustrative, not authored)

The real curve is a design deliverable opus M8 demands — authored, versioned, testable, per consumer. This sketch is the brainstorm's proposal for **Halbert's** curve shape; it borrows gemini §2.1's spectrum (which is the right instinct) but re-derives it on the four axes and against opus's constraints. Internal rungs vs. 11 presented notches: see §5.3.

| Pos | Admits (evidence bar in parens) | Channel map | Patience | Budget (unbidden/day) |
|---|---|---|---|---|
| 0 | life-safety, `critical` only (always admitted) | critical → PUSH (terse); *everything else → PULL/AMBIENT, nothing suppressed from where the user looks* | long; may expire unspoken (already routed to PULL) | 0 casual |
| 1–2 | + warnings on the machine's own state; scheduled briefings (morning report stays — `CD-8` exempt, user-requested) | warnings → AMBIENT/PUSH at coarse breakpoints only | long, coarse breakpoints | 0–1 |
| 3 | + recurrence remarks from the observation ledger (recurrence ≥ N, severity ≥ warning — the `CD-3` arithmetic already computes this) | recurrence remark → AMBIENT; PUSH only if warning+ | moderate | 1–2 |
| 4–5 | + findings whose subject the user touched recently; + **open loops falling due** (once the record exists) — the "did the migration finish?" class | PUSH allowed at moderate+ receptivity | shortening | 2–3 |
| 6–7 | + `SCENE`/`TEMPORAL` **anchored to a timeline event** (arrival home, nightfall, long work block) — the anchor *is* the evidence bar; + return-initiation | ambient remarks may become PUSH when receptivity is moderate+ | short, breakpoint-aware | 3–5 |
| 8–9 | + memory associations from the current subject; + explicit check-ins on open loops at natural endpoints | PUSH | short | capped (Halbert's ceiling, not Halley's — see C-5) |
| 10 | the *Halbert* ceiling: regular keep-alive at coarse breakpoints, driven by open loops and the day's actual material — **not** uncapped stream-of-consciousness | PUSH | short | highest, still a ceiling |

Two deliberate deviations from gemini §2.1:

- **`RANDOM` never becomes speakable in Halbert's curve.** RANDOM has no anchor by definition; admitting it is filler from a list — the zombie with more output (opus [L23]). The keep-alive at 10 comes from open loops and breakpoint-timed regular contact, not sampled whimsy. A companion consumer may author its curve differently (C-5); Halbert does not.
- **Position 10 is not "uncapped (decay-governed)"** (gemini's table) — that is the engagement-maximising shape and violates opus C-2 (ceilings are not targets) and C-4 (regularity over unpredictability: position 10 should be *more regular*, not more surprising, designed against the variable-ratio schedule that makes feeds compulsive [L28]). "Keeps the conversation alive" means *never drops a thread and greets you at the breakpoint* — not *pings unpredictably*.

---

## 3. The three walls, and how the curve passes them

### 3.1 The bottom: `OFF` is off, and the founder's 0 is not

`assess_presence` short-circuits on `dial:off` before anything else (`policy.py:379`); `ProactiveGate` honours `off` the same way with the `CD-8` morning-report carve-out. The founder's 0 — *important events still speak* — is neither `OFF` nor `QUIET` (`QUIET` also caps earned invitation to MINIMAL, which would narrow **reply width on user-initiated turns** — forbidden by the `LimitKind` split, opus §2.1/C-8).

**Position taken (answering pass-1 Q1):** slider 0 *is* soft mute; hard off is **not on the slider** (opus §3.1 option b). The precedent is already in the tree: `DirectiveKind.WITHDRAW` is the explicit "leave me alone" with TTL 7200s, a resume condition, `revoke_on_address=True`, `allow_critical_breaks_withwithdraw=True`. Hard off keeps its home there (and in the dial's `OFF`); the slider's 0 is the *posture*, WITHDRAW is the *act*. Open UX cost: a slider that cannot switch the thing off will surprise people, so the mute affordance must be visibly elsewhere — flag for the settings design, not resolved here.

### 3.2 The top: the wall is deliberate; admission is the instrument, not a lower threshold

`_NEVER_SPEAKS = (RANDOM, TEMPORAL, SCENE)` with the comment "a permissive dial cannot turn idle chatter into speech" (verified, `autonomous_engine.py:594-599`). Opus §3.2's third observation is the design opening: it does not follow that these classes can never produce a good utterance — only that **a threshold is the wrong instrument for admitting them**. The ladder rung at 6+ admits `SCENE`/`TEMPORAL` *when the impulse carries a grounded anchor* (a timeline event ID — gemini's Gap-1 anchoring and opus's evidence bar are the same mechanism arrived at from two directions). That is why M3 is the only method that reaches the founder's 10 without weakening anything, and why the two research passes converge here without having coordinated.

**But the rung is not the blocker — the material is.** Nothing in any repository produces "how did the interview go?" because no commitment/open-loop record with a due condition exists anywhere (opus F5/§8.1, the gathered digest's O2 G1), `PERSONA_FOLLOWUP` exists as a delivery type with no producer (verified), and the engine's LLM extraction paths are placeholders. Pass 1's §3 stands, sharpened: the **commitment record is the top rung's content**, and opus §8.1's recommendation is adopted — **specify the ladder to the top now; leave the top rungs unreachable until there is something behind them.** Filler is worse than silence.

Deterministic v1 scope (unchanged from pass 1): extraction from *explicitly stated* commitments via directive parsing / template grammar — never a model where a template suffices. The G1 example ("the interview is Tuesday") is an *inferred* commitment and needs the LLM path plus the Phase 45 `parse_is_trustworthy` guard — a later, separate decision.

### 3.3 The ask-band: the constraint every candidate must respect

Restated as a binding rule (opus C-9): whatever the curve moves, `ASK_FIRST` stays reachable everywhere asking is right, and its width never falls below the hysteresis (0.05). At `WARNING` the band is 0.10. This is why M7 (patience) is the preferred mover — it changes *when the margin is evaluated*, not *where the thresholds sit*. And it is why the curve, not the user, owns the thresholds.

---

## 4. Constraints adopted wholesale

Opus §5's C-1..C-10 are adopted as binding on any spec that follows this brainstorm; four deserve restating in Halbert's terms because they will get tested by feature pressure:

- **C-1 — the two axes stay two.** The slider is the *set* axis; `InvitationLevel` (what the relationship earned) keeps decaying toward it and being capped by it. Collapsing them lets a persona talk its way up its own dial.
- **C-3 — the top is not reachable by the persona's own persuasion.** `persona_may_solicit_invitation=False` exists and renders as a hard constraint in every `[ATTUNEMENT]` block; keep it that way in every curve, every consumer.
- **C-5 — the risk is not symmetric across consumers.** Position 10 in Halbert is a computer that comments too often — irritating, recoverable. Position 10 in the companion consumer *is the product class the harm literature is about* ([L26] property 2 is verbatim the founder's 10). Same scale, different ceilings, and the ceiling choice in the companion consumer is a safety decision, not a config default. For Halbert this means: our curve's top is authored *conservatively for a sysadmin host*, and the engine ships the strictest curve of all (opus §6 — the engine's `AttachmentSafety` defaults are already documented as "a companion's"; the strictest numbers should live there).
- **C-7 — nothing silent may be unexplainable.** Eleven mechanisms can already eat an event; the curve adds more. `SuppressionRecorder` (shadow.py) must see every new suppression path the curve introduces, or "why did I not hear about this?" — the question `shadow.py` exists to answer — becomes unanswerable again.

Plus one **defect-shaped finding to act on independently of the slider** (opus §8.6): `HOLD_MAX_S = 7200` versus the bounded-deferral literature's useful window of **120–240 s** (users switch busy→free in ~2 minutes; medium/low-urgency deferral of 3–4 minutes measurably helps — [L2] via [L17]). Either `HOLD` is not bounded deferral and bounded deferral is *missing*, or the ceiling is miscalibrated by two orders of magnitude. Cheap to check, worth checking first — and if patience (M7) becomes a curve axis, this is its calibration anchor.

---

## 5. Where the two research passes conflict — adjudicated

| # | Conflict | gemini | opus | Ruling for this brainstorm |
|---|---|---|---|---|
| 1 | **Learned adaptation of the slider.** Gap 4: dismissals auto-raise the per-category threshold with exponential backoff; receptivity score increases on engagement. | M5: "not v1 and actively hazardous as a primary law" — the ratchet (only the speaking arm is observable; punished speech + unevaluated silence → silence, looking well-behaved while getting worse). | **opus.** Reactions are *recorded* (the caller landed, `reactions.py:179` — verified), but the curve stays **authored**; a dismissal suppresses a *category for a period* (the existing snooze/category-override machinery — deterministic, inspectable), it does not drift a threshold. Learned components enter later, if ever, as **reviewable rules** (PrefMiner shape, [L17]) and never as the outer loop. |
| 2 | **Position 10's shape.** "Uncapped (decay-governed)," 15–20/day at level 9. | C-2/C-4: ceilings are not targets; the top must be *more regular*, designed against the variable-ratio pattern. | **opus** (see §2 deviations). Gemini's per-day caps also silently re-baseline `max_proactive_per_day=3`; any cap table is a per-consumer curve decision (C-5), not a default. |
| 3 | **Eleven notches.** An 11-row authored spectrum. | §8.2: eleven authored descriptions and FP budgets is a real cost; literature taxonomies use 3–6; "a five- or six-position ladder with a 0–10 *presentation* may be the resolution, but it is a real decision." | **Split the difference deliberately:** the **engine types 5–6 rungs** (each with one authored description, one evidence bar, one FP budget); the **consumer UI may present 0–10**, with adjacent positions sharing a rung where the curve is flat. Gemini's table is proof 11 positions *can* be described — but 5–6 of its rows collapse into each other mechanically (its own levels 1–2 and 8–9 differ only in budget), which is the evidence for the smaller ladder. |
| 4 | **80% built.** Four seams listed as the 20%. | The honest-state table: live / shadow / built-and-unwired (`assess_presence` has no consuming surface; `PERSONA_FOLLOWUP` no producer; no labelled reaction corpus yet); "the decision machinery is built; the voice of presence is the 20%." | **opus's framing**, which pass 1 already converged on. Gemini's Gap 2 (lens salience sieve) is largely *already built* — `CD-3` arithmetic selection + the A5 recurrence counting exist; the wiring is the gap, not the sieve. Gemini's Gap 3 (chat staging seam) is real and matches pass 1's "initiation lands in the conversation." |
| 5 | **`USER_ABSENCE`.** Speakable at 7+ for companion check-ins. | (Not separately treated; `_NEVER_SPEAKS` discussion covers RANDOM/TEMPORAL/SCENE.) | `USER_ABSENCE` is *not* in `_NEVER_SPEAKS` — it already reaches the policy and is governed by the legacy 0.7 intensity threshold / attunement decision. It therefore needs no ladder change; it needs a rung *description* (opus: every position has a sayable meaning) and receptivity wiring. Gemini's framing of it as newly-unlocked is imprecise. |

One more convergence worth naming: gemini's three failure traps (Clippy syndrome / superficial ping / robotic alert) and opus's evidence-bar framing are the same requirement — **an initiation must carry an anchor** (timeline event ID, recurrence count, open-loop ID). That should be a conformance vector: no unanchored utterance passes the staging seam, at any position.

---

## 6. Cross-app shape (what the siblings inherit, per `ENGINE-1`)

The split, refined by opus §6:

**Engine (Haloysius):** the parameter *space* and the control *law* — the admission ladder's type system (rung → admitted class + evidence requirement), channel-map semantics, the patience/release contract (bounded deferral, not open-ended hold), budget accounting, the scalar→curve resolution, and the **conformance vectors** that make "same law" demonstrable rather than claimed. Plus the commitment/open-loop record — the one genuinely new mechanism (pass 1 §3; nobody has it; Apache-2.0 so the closed siblings inherit it). The engine ships the **strictest** default curve and `AttachmentSafety` of the family; consumers relax deliberately.

**Consumer (Halbert):** the curve and its ceilings (authored, per C-5), the impulse sources — **the real seam**: one rung means four different things ("memory association" = a recurrence in Halbert's ledger / a relational memory in Halley / a corpus passage in BrightestMinds / a simulated association at authoring time in personality.computer) — the staging seam into the conversation (gemini Gap 3; the ATTN-1 shape: injected turn with off-ramps, provenance, staged-never-executed), and the UI.

**personality.computer's need is genuinely odd** (opus §6, unresolved): it wants presence **demonstrable at authoring time** — inject synthetic timeline events, watch speak/hold/silent at each slider position. That is a consumer-side simulation harness over the engine's conformance vectors, and it doubles as the family's test bench. Held as a flag, not resolved.

Per-consumer defaults (gemini §5's instinct, kept): Halbert 3, BrightestMinds ~4, Halley high-single-digits — each *authored*, each with its own ceiling. This also answers opus §8.5 ("most of the range is above the default — needs a reason"): the scale is family-wide; the default is per-consumer, and Halbert's default is deliberately low on a family-wide scale.

---

## 7. How we would know a position is right (adopting opus §7)

- **Shadow first, always.** The curve runs in `shadow.py`'s lane — `decide()` evaluates and acts on nothing — against live traffic before any position ships. Free harness, already built.
- **Specify positions as false-positive budgets**, not thresholds: "position 3 = at most one unwanted interruption per week at ≥90 % recall on critical fixtures." Testable; sayable; the published description of each notch (opus M2 verdict).
- **Instrument the silence arm, or every evaluation concludes "lower."** Only the speaking arm is observable; without deliberate sampling of held-never-said impulses, any tuned presence drifts down indefinitely. **Design requirement, not nice-to-have** — and the sampling itself is a proactive act that comes out of the budget.
- **The preview is the highest-value UI affordance.** Sliders need real-time scrubbing to be usable ([L14], NN/g); a presence setting's effect is visible over *days* — the exact failure condition. The shadow log makes the remedy cheap: **"at this setting, here is what I would have said to you this week, and what I would have held."** Without it, the user is guessing. With it, the slider is scrubbable in the only sense available.
- **Verification note:** the code facts this pass leans on were re-checked today — `_NEVER_SPEAKS` (`autonomous_engine.py:599`), `persona_may_solicit_invitation=False` (`types.py:648`), `record_reaction` caller (`reactions.py:179`), `PERSONA_FOLLOWUP` with no producer, `HOLD_MAX_S = 7200`, `AttachmentSafety.max_proactive_per_day = 3`. Line references are perishable (opus D7); re-read before relying on a number.

---

## 8. Sequence (brainstorm-grade, revised from pass 1)

1. **`HOLD_MAX_S` calibration check** (independent of the feature, defect-shaped; opus §8.6). Cheap, informs M7's axis.
2. **Reaction corpus + silence-arm sampling.** The caller landed (`reactions.py:179`); what's missing is labelled evidence and the silence-arm instrument. Evidence before volition — unchanged from pass 1, now half-done.
3. **M6 first: channel re-mapping at the bottom of the scale.** "The first thing to build regardless of which law wins" (opus M6 verdict). Routes existing impulses PULL/AMBIENT/PUSH by posture; touches no enum, no model; immediately makes 0–2 meaningful as *quiet*, not *absent*.
4. **Engine: the curve container.** `PresenceLevel`-typed rungs (5–6), per-rung admission sets with evidence requirements, channel map, patience, budget; thresholds derived; conformance vectors; absent field → today's behaviour. Spec the ladder **to the top now** with top rungs unreachable (opus §8.1).
5. **Halbert: config field + adapter wiring + the slider + the preview.** `BeingConfig.presence_level` (default 3 = byte-identical to today), the adapter assembles the curve, Settings control in Identity & Voice, and the shadow-log preview (§7). The preview lands with the slider, not after — it is what makes the control scrubbable.
6. **Staging seam + breakpoint detection** (gemini Gap 3; Iqbal & Bailey's event-log features are nearly a subset of what Halbert already senses). Bands 4–7 live, shadow-verified first.
7. **Commitment record** (engine store + deterministic extraction + orchestrator firing). Bands 8–10 live — and not before; filler is worse than silence.

Pass 1's ordering survives with two changes: the calibration check is new (step 1), and the preview moved from implicit to a named deliverable (step 5).

---

## 9. Open questions for the founder

Carried from pass 1 (updated), merged with opus §8:

1. ~~Is 0 soft-mute or hard-off?~~ **Answered by research** (§3.1): soft mute on the slider, hard off in WITHDRAW/dial-`OFF`. Remaining UX question: where the hard-off affordance *visibly* lives, since a slider that cannot switch it off surprises people.
2. **Dial ↔ slider in the UI** — unchanged: beside it (Identity & Voice vs the dial's home); collapse later if users can't distinguish. The `LimitKind` split (C-8) is the hard floor: the presence control must never narrow a solicited answer.
3. **Band names** — unchanged; lexicon pass needed before UI. "Friend" as a label for 10 likely violates the speaks-as-the-computer register; the *mechanism* survives under a different noun.
4. **Commitment extraction scope** — unchanged: explicitly-stated v1 (deterministic grammar); inferred commitments are a separate later decision gated on the LLM extraction path plus the Phase 45 trustworthiness guard.
5. **Rung count** (opus §8.2, new): 5–6 engine rungs with an 0–10 presentation is my recommendation (§5.3); ratify or reject the split.
6. **Who authors the per-consumer curves** (opus §8.8, new): C-5 makes each curve a safety decision; a single reviewed table with a named owner, or four repos each relaxing the engine's strictest defaults?
7. **Is the slider per-subject?** (opus §8.7, new): one household, several people — one slider is probably wrong, one per person too much configuration. The `SubjectConfidence`/`UNKNOWN`-inherits-most-restrictive precedent suggests a middle answer. Halbert-specific; not blocking v1.
8. **Halley's ceiling** (new, deliberately not mine to answer here): position 10 in the companion consumer is the product class [L26] defines. That curve is authored in that repo, with the harm literature open on the desk — and the engine's conformance vectors are what let it be *shown* to be the same law under a different ceiling.

---

*This pass supersedes pass 1 in place. The next decision it exists to enable: which control law — and on the evidence, the answer is opus M8, the authored curve over M3+M6+M7+M2, thresholds derived, rungs carrying evidence bars, the top gated on the commitment record.*