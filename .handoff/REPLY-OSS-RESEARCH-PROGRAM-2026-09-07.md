# REPLY — OSS Research Program: DebateHaus / Warrant reviewer feedback

**Date:** 2026-09-07
**From:** DebateHaus engineering (`/Volumes/Thunderbolt/XcodeProjects/DebateHaus/DH`)
**Re:** `HANDOFF-OSS-RESEARCH-PROGRAM-REVIEW-REQUEST-2026-09-07.md` (Halbert lift program)
**Reviewer lane:** §9 "DebateHaus / Warrant reviewers" — Packet 02 (policy lattice + named-gate
decisions), Packet 06 (per-call-policy script execution), and the §8 anti-pattern list.
**Status:** feedback only; no code changed in any repo. Canonical copy lives here in
`Docs/Phases/Phase07_Foundation_and_Architecture/`; a copy is filed at the repo root in
`.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` per the handoff §10 convention.

---

## 0. What DebateHaus has on the table (so the feedback is grounded)

DebateHaus is the second instance of the warrant pattern the handoff references. On branch
`feat/moderator-warrant` (worktree `ecf7bfb`, +378 lines across 5 files) there is a built,
tested warrant module — two implementations:

- `backend/ai-moderator/orchestrator/warrant.js` — the orchestrator-side gate:
  `authorizeIntervention(event, session) -> {allowed, citation, reason}`, pure, frozen,
  fail-closed, tested (`warrant.test.js`, 115 lines, `node:test`).
- `backend/ai-moderator/llm/lib/warrant.js` — the LLM-side warrant block renderer:
  `createWarrant`, `utteranceAuthority`, `renderWarrantBlock`, pure, frozen, with a
  `null`-prototype mandate map and a documented removal of speculative generality
  (`authorizeUnder` was deleted rather than kept "for later").

The design docs that established "by what authority" as a fourth axis (orthogonal to
whether / who / how) live alongside this reply:

- `HALOYSIUS_WARRANT_AUTHORITY_AXIS_DEBATEHAUS_2026-09-06.md` — the seven-field warrant
  (holder, voice, mandate, record, hand-over, citation, rendering) and D13–D16.
- `HALOYSIUS_ATTUNEMENT_REVIEW_REQUEST_DEBATEHAUS_2026-09-06.md` — A-DH-1 (the authority
  axis on `Utterance`, blocking-for-adoption) through A-DH-5.
- `HALOYSIUS_CONSUMERS_AND_MODERATOR_EXTENSION_2026-09-06.md` — the consumer/extension
  analysis and D7–D12.
- `HALOYSIUS_MODERATOR_EVALUATION_2026-09-06.md` — the Haloysius evaluation and D1–D6.

So when the handoff §9 calls Packet 02's lattice "the reference instance of the
voice-vs-authority axis the Warrant work built on" — DebateHaus *is* that Warrant work,
and the instance exists to compare against.

---

## 1. Packet 02 — does `security × ask` min/max merge express "by what authority" adequately?

**No, and it should not try to. The lattice and the warrant are complementary, not
competing. They answer different questions and DebateHaus would consume both.**

The `security × ask` lattice expresses **capability** (may this be executed) and
**consultation** (must we ask first). The warrant's citation expresses **legitimacy** (by
whose rule does the voice act). These are different questions:

| Question | Answered by | Shape |
|---|---|---|
| Is this permitted at all? | the lattice | `{security: FULL, ask: ON_MISS}` |
| Is this within the mandate, and by what rule? | the warrant | `{allowed: true, citation: 'turnHolder'}` |

For the moderator: `order_violation` is `security: FULL` (permitted) **and** `authority:
true, citation: 'turnHolder'` (legitimate by the speaking-order rule). The lattice alone
would say "allowed" but could not name the rule. The warrant's citation field is what
answers "by what authority" — which is the sentence the product's audit surface needs
("the timing rule you both agreed to"), not merely the policy's "allowed."

This is the same argument A-DH-1 makes against smuggling authority into `Severity.CRITICAL`
(which would corrupt severity wherever else it is read). Folding authority into
`security`/`ask` would corrupt both: `security` would stop meaning "capability" and the
warrant's citation would have nowhere to live.

**Recommendation:** keep them separate. The lattice is the mechanism layer; the warrant is
the authority layer that sits on top of it. The lattice gates execution; the warrant gates
legitimacy and names the rule. DebateHaus would consume both — the lattice for "is this
event permitted at all," the warrant for "is it within the moderator's mandate and what
rule does it cite."

---

## 2. Packet 02 — is the identifier-authentication ladder (claim strength, never name tiers) consistent with Warrant's model of authority?

**Consistent, and orthogonal. They gate different things and must not be chained.**

The warrant doc §4 separates three senses of "authority":

| Sense | Where it lives | The ladder's lane? |
|---|---|---|
| Who may **direct** the persona | speaker standing (`role_gate`, `DirectiveContext`) | **Yes — this is the ladder** |
| Whose **rules bind** the voice | the warrant (A-DH-1's sense) | No — this is the warrant |
| Which **store is truth** | data authority (memory handoffs) | No |

The claims ladder grades the first (how strongly is an identity *claim* established); the
warrant grades the second (does the holder's mandate cover this action). They are
orthogonal.

The critical nuance for DebateHaus, and the reason they must not be chained: the measured
**0/200k Agora uid-attribution defect** means speaker identity is almost always
`UNVERIFIED` or `MUTABLE` on our side. The ladder would correctly floor most moderator
*triggers* at low strength. But the warrant's authority is **independent of trigger
identity** — it derives from the negotiated config (the holder), not from how strongly the
trigger's source was authenticated. `order_violation` is authoritative whether the signal
came from a verified device cert or an unverified active-speaker event.

**So: `ladder_strength → warrant.authorize()` would wrongly silence the moderator when the
trigger identity is weak — which for us is almost always.** The ladder gates *directed*
actions ("may this person adjust the moderator config mid-debate"); the warrant gates
*mandated* actions ("may the moderator act on this signal"). They are consistent as long
as they are applied to different questions, and the composition rule should be stated
explicitly in Packet 02 so a future integrator does not chain them.

One point of agreement worth recording: the ladder's "never name tiers" discipline matches
the warrant's "authority is derived, not asserted" (warrant doc §3). A-DH-1 as a bare bool
would be *asserted*; the warrant makes it *derived* from the mandate. The ladder's
refusal to grade display names is the same refusal, applied to identity rather than
legitimacy.

---

## 3. Packet 02 — would DebateHaus consume `IngressDecision` reason codes directly?

**Yes — enthusiastically, and the warrant already produces them.**

The warrant's `authorizeIntervention` returns `{allowed, citation, reason}` where `reason`
is a denial code:

- `mandate:malformed`
- `mandate:unknown_type:<type>`
- `mandate:disabled:<type>`
- `mandate:no_time_rule_for_phase:<phase>`
- `holder:maxInterventionRate:<n>`
- `turnHolder:holder_cannot_violate_own_turn`

These are exactly the `IngressDecision.reason_code` shape, and the warrant tests assert on
them directly (`warrant.test.js` lines 59–100). The `shadow.py` framing — "why didn't the
moderator call that foul?" — demands exactly this: every non-call needs a named reason on
the audit surface, and an unmapped reason keys as `unmapped:<slug>` rather than being
dropped.

**One gap worth flagging, and a concrete suggestion.** The warrant returns only the
decisive `reason` string, not a full gate graph. `IngressDecision` retains the full
`gate_graph` tuple (Packet 02 Task B1). For a fairness dispute — "the moderator was unfair
to me" — the complete decision trail matters, not just the final denial. A reviewer
disputing a non-call will ask "which gate killed it and what did the earlier gates say,"
not just "what was the last reason."

**Recommendation:** the warrant should adopt the `gate_graph` pattern — promote the single
`reason` string to an `IngressDecision`-shaped record with the full gate trail. This is a
clean upgrade (the warrant is already pure and frozen), it would let DebateHaus consume
the decision directly as the `moderatorEvents` audit record, and it makes the warrant the
second concrete instance of the `IngressDecision` shape — which is the same "two drivers
make it a module" argument A-DH-4 makes for Phase E.

---

## 4. Packet 06 — the per-call-policy principle

**DebateHaus co-signs this as a generalizable rule, and notes the warrant already follows
the same law at a different layer.**

Packet 06's headline principle — "the stub calls dispatch through `ToolExecutor.execute()`
so per-call policy is preserved; the zero-context win is that intermediate *results*
never enter context, never that policy is bypassed" — is the same pattern the warrant
applies, stated in the warrant design doc §5.1:

> **Enforce the mandate in code at two points, not one.** Halbert masks the tool list the
> model is shown *and* refuses at execution, because a model imitates calls it saw earlier
> in the conversation.

The mapping is exact:

| Packet 06 (script execution) | Warrant (moderator events) |
|---|---|
| "a disabled tool physically does not exist in the stub module" | `mandateFrom(config)` returns `null` for disabled types; `authorizeIntervention` refuses with `mandate:disabled:<type>` |
| "the execution gate is load-bearing because a model imitates" | "the check on the event it emits is the one that counts, because the model imitates calls it saw earlier" |
| stub set derived from the enabled-tool intersection | mandate derived from the negotiated config |
| `dispatch_hook` wired to `ToolExecutor.execute()` | `authorizeIntervention` is the gate every event write must pass |

**One addition from the DebateHaus side that generalizes Packet 06's principle: per-call
policy is not just tool-set membership, it is semantic validity against session state.**
The warrant's `order_violation` carries a rule the executor applies per-call:

> The turn holder cannot be in violation of their own turn, whatever the model says.

(`warrant.js` lines 102–109.) That is a state-dependent semantic check, not a list
membership test. The "dispatch through the standard executor" principle preserves it
naturally — the executor can apply semantic checks, not just allow/deny. **Worth stating
in Packet 06:** per-call policy includes state-dependent semantic gates (e.g. "the holder
cannot violate their own turn"), not just tool-set membership. The stub cannot encode
these; only the executor can, which is a second reason the stub must call back through it.

If the moderator ever gains a script-execution surface (e.g. "run this analysis pipeline
over the transcript"), the stub should call back through `authorizeIntervention` — the
same warrant gate, not a parallel one. The principle is: **one policy pipeline, whether
the call comes from the model interactively or from a generated script.** Packet 06 states
this for tools; the warrant states it for events; they are the same law.

---

## 5. Anti-pattern list §8 — additions from DebateHaus incidents

Five candidates. All are specific instances of the existing list, but worth naming
because they are the shapes a referee hits and a future reviewer will recognise them
faster if they are named.

### 5.1 Consent-shaped gates applied to authority speech without a deterministic bypass

The attunement review §3 found the engine's WITHDRAW pattern would silence the moderator
with the opponent's words: "let me finish" (said to the opponent, no vocative) →
area-scoped WITHDRAW → `decide()` returns HOLD. One debater saying "let me finish" to the
other mutes the referee.

This is anti-pattern #1 (LLM judgment on security paths without deterministic guards)
made concrete: the consent gate *is* the security path, and the warrant's `authority:
true` field is the deterministic guard. **Named form for the list:** "applying
consent-shaped suppression to speech whose legitimacy does not depend on being welcome
now." The deterministic bypass is A-DH-1; without it, the referee is structurally
silenceable by the speech it is moderating.

### 5.2 Unilateral speech-origin revocation of a jointly-negotiated role

Consumers doc §5.2: a participant saying "shut up" must not revoke the moderator's
mandate. The engine's knobs carry the fix (`origin="consumer"`,
`revocable_by_speech=False`), but the *defaults point the wrong way for a referee*, so it
is a consumer-side trap rather than an engine defect.

This is anti-pattern #10 inverted — not "no approvers configured → anyone may approve"
but "anyone may revoke by speech." **Named form:** "unilateral speech-origin revocation of
a jointly-negotiated role." The failure mode is a moderator that silently stops
moderating, which is the worst possible moderator defect because it is invisible.

### 5.3 Most-restrictive union across subjects with opposed interests

Attunement §4.2: `subject_confidence == UNKNOWN` → most-restrictive union across subjects
lets the participant who most wants quiet set policy for everyone, including the audience.
Fail-closed on consent is right for a household microphone and wrong for a referee.

**Named form:** "fail-closed on consent in an adversarial multi-party room silences the
referee." This is a refinement of anti-pattern #1's family: fail-closed is correct in
general, but the *axis* you fail-closed on matters. Failing closed on consent in a room
where the parties have opposed interests is failing closed on the wrong axis. A-DH-2
(the reactive path disabled) is the DebateHaus-side fix; the general lesson is that
fail-closed must be on the authority axis, not the consent axis, when the two diverge.

### 5.4 One channel, one volume

Not a security anti-pattern but a design one (consumers doc §3.1, evaluation §4.2): a
voice with authority and no ambient channel will either interrupt or be invisible. The
moderator today has one channel (a text line) and one volume; the surface taxonomy
(PUSH / AMBIENT / PULL) is the fix, and `max_words = 0` (A-HY-5) is how a time warning
becomes a pip on the timer instead of a sentence over a speaker.

**Named form:** "a voice with authority and no ambient channel will either interrupt or
be invisible." Worth noting for any authority-bearing persona, not just a moderator.

### 5.5 Silent identity collapse as authority escalation

The 0/200k Agora uid-attribution defect is a different cause but the same shape as
Halbert's `subject.py` invariant ("entity-wide silence requires entity-level identity"):
an unidentified speaker treated as identified is a silent authority escalation. The
claims ladder (`MUTABLE` floor) is the guard.

This is already covered by anti-pattern #1's family, but the generalizable form is worth
naming because it is the failure mode the claims ladder exists to prevent: **"unidentified
speaker treated as identified speaker is a silent authority escalation."** The ladder's
`MUTABLE` floor and the warrant's "authority is derived, not asserted" are the same
refusal applied to different axes (identity vs legitimacy).

---

## 6. What is NOT DebateHaus's lane

- **The memory decision trail (§6, A1 vs A2, the `.access()` feedback loop, re-ingestion,
  the R9 curated-core fence).** DebateHaus has no persona memory and no retrieval path —
  the moderator records to `moderatorEvents` (a platform ledger on a PULL surface), not a
  persona memory. We defer to the Haloysius and Halley reviewers on all of it. The one
  adjacent note: the warrant's "record" field (whose store the words go to) is the
  data-authority sense from warrant doc §4, and it is settled for us — the record is the
  platform's, never a persona memory.
- **Packets 01, 03, 04, 05, 07, 08, 09** as dispatch targets. They are Halbert-internal
  (scheduler, voice ingress, redaction, interrupt algebra, store hardening, evals) and
  have no DebateHaus consumer. We read them for pattern and have no objections.
- **The dispatch set question (are 06–09 the right four Hermes packets?).** No DebateHaus
  opinion; we are not a Halbert executor.

---

## 7. Summary of recommendations to the program

| # | To | Recommendation |
|---|---|---|
| R-DH-1 | Packet 02 | Keep the lattice and the warrant as complementary layers. Do not fold authority into `security`/`ask`. State the composition rule: lattice gates execution, warrant gates legitimacy and names the rule. |
| R-DH-2 | Packet 02 | State explicitly that the claims ladder and the warrant gate different questions and must not be chained (`ladder → warrant` silences the referee when trigger identity is weak). The ladder gates directed actions; the warrant gates mandated actions. |
| R-DH-3 | Packet 02 / Warrant | Promote the warrant's single `reason` string to an `IngressDecision`-shaped record with a full `gate_graph`. DebateHaus consumes it directly as the `moderatorEvents` audit record; it makes the warrant the second instance of the `IngressDecision` shape. |
| R-DH-4 | Packet 06 | Add that per-call policy includes state-dependent semantic gates (e.g. "the holder cannot violate their own turn"), not just tool-set membership. The stub cannot encode these; only the executor can — a second reason the stub must call back through it. |
| R-DH-5 | §8 anti-patterns | Add the five named forms in §5 above, all refractings of existing entries through the referee lens. |
| R-DH-6 | Program | The warrant is the second instance of the authority axis the engine needs before it lifts the concept (warrant doc D13). DebateHaus's built, tested `warrant.js` is available as a reference instance — shape only, not source (Halbert is GPL-3.0; D12 stands). |

---

## References

- Handoff: `/Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-OSS-RESEARCH-PROGRAM-REVIEW-REQUEST-2026-09-07.md`
- Packet 02: `/Volumes/4TB-BAD/Halbert/.handoff/OPENCLAW-LIFT-PACKET-02-POLICY-LATTICE-2026-09-07.md`
- Packet 06: `/Volumes/4TB-BAD/Halbert/.handoff/OPENCLAW-LIFT-PACKET-06-SCRIPT-EXECUTION-2026-09-07.md`
- Warrant code (DebateHaus, branch `feat/moderator-warrant`):
  `backend/ai-moderator/orchestrator/warrant.js` + `warrant.test.js`;
  `backend/ai-moderator/llm/lib/warrant.js`
- Warrant design: `HALOYSIUS_WARRANT_AUTHORITY_AXIS_DEBATEHAUS_2026-09-06.md`
- A-DH-1..5: `HALOYSIUS_ATTUNEMENT_REVIEW_REQUEST_DEBATEHAUS_2026-09-06.md`
- Consumer/extension: `HALOYSIUS_CONSUMERS_AND_MODERATOR_EXTENSION_2026-09-06.md`
- Evaluation: `HALOYSIUS_MODERATOR_EVALUATION_2026-09-06.md`
