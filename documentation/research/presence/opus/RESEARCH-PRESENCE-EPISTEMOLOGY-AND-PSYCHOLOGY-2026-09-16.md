# Research — presence as an epistemic act: theories of knowledge and the psychology on both sides

**Date:** 2026-09-16
**Status:** Research pass 3. **Nothing here is decided.** §5 proposes amendments to the v1 spec;
they are proposals, numbered E- (epistemic) and P- (psychological) to keep them distinct from
pass 2's §8.
**Companion documents:** pass 1 (`RESEARCH-PRESENCE-SLIDER-CONTROL-LAW-…`: M1–M8, F1–F6,
C-1–C-10), pass 2 (`RESEARCH-PRESENCE-PRIOR-ART-AND-OUTCOMES-…`: P1–P24, §8 amendments), and the
v1 spec (`documentation/superpowers/specs/2026-09-16-presence-slider-design.md`).
**Question.** Pass 1 asked what the number should move; pass 2 asked what happened when others
built one. This pass asks two prior questions. *Epistemic:* when the machine speaks unbidden,
what does it claim to know, by what warrant, and what does that license it to say? *Psychological:*
what does unbidden speech do to the person receiving it, and what kind of behaving thing should
the computer be at each setting?
**Verification posture.** Founder documents and engine source were read directly. **Fourteen
external sources were fetched or extracted and verified**, plus four founder and engine documents read directly (§6.1). Canonical texts (Williamson,
Grice, Clark, Brown & Levinson, Buber, Aristotle, Sartre, Weil, Reeves & Nass, Lee & See) are
cited as canonical and marked as not re-fetched (§6.2). Eight claims rest on snippets where the
publisher walled the page and are quarantined (§6.3); no amendment in §5 rests on one alone.
**Naming.** Consumers by role.

---

## §0 What changes when presence is treated as knowing

Twelve findings. The first four are epistemic and three of them reach the contract; the rest are
psychological and mostly reach the stance block and the copy.

**1. Unbidden speech is assertion, the founding ethos is the knowledge norm, and the ladder is a
warrant ladder.** Williamson's norm — "assert that p only if one knows that p" — is a constitutive
rule of the speech act [E1]. Halbert's founding document states the same rule for the machine
without naming it: "The LLM cannot make claims about the system without evidence … If the data
doesn't exist, the LLM says so" [F1]. Read against that norm, the `ImpulseClass` rungs are not
merely kinds of impulse; they are **grades of warrant**. `CRITICAL`/`WARNING` assert what the
machine knows by *introspection* (measured state). `RECURRENCE`/`SUBJECT_LINKED` assert what it
knows by *observation* (the ledger). `OPEN_LOOP` rests on *testimony* (what the person said).
`ASSOCIATION` and `SPONTANEOUS` have no source that meets the norm — and so, as a matter of the
norm rather than of taste, **they cannot be assertions.** They must be a different speech act:
an expressive ("I was thinking about…"), or a question. That is a constraint on the *form* of the
top rungs, and it is stronger than hedging, for a reason finding 3 supplies.

**2. The "I" is warranted for exactly one of those three sources.** First-person authority is the
mark of introspective knowledge; the engine's own facticity layer already encodes the body as
Layer 1 constraint, "NOT beliefs" [F3], and the founder's ethos names the machine's telemetry its
"biography" and its configuration its "physiology" [F1]. So "I am at 45 °C" is warranted first-
person speech; "I noticed the van again" is warranted only with the ledger behind it; "I was
thinking about your migration" is warranted only as an expressive. `the-being.md`'s fourth why —
*why trust: what data grounds this claim?* — is the testimonial warrant made visible [F2]. The
amendment (E-1) is to carry the warrant on the utterance so the "why trust" can be rendered per
rung rather than reconstructed.

**3. Hedging is not a substitute for the right speech act.** Zhou, Hwang, Ren & Sap found that
deployed models "are reluctant to express uncertainties … even when they produce incorrect
responses," that "users rely heavily on LM generations, whether or not they are marked by
certainty," and that forcing confidence markers produced 47 % error among confident answers
[E4]. A top-rung utterance that is an assertion with "maybe" in front of it will be relied on as
an assertion. The difference has to be *structural* — expressive or interrogative — not lexical.

**4. Relevance is decision-theoretic, it is Horvitz again, and it supplies the positive case for
presence at all.** Jiang, Sadaghdar, Limb & Gao define relevance as the utility difference between
what the helper knows and what the recipient knows, and show an assistant using it beat a
heuristic on both score (54.6 vs 42.9, p<.05) and rating (5.59 vs 5.13, p<.005) [E3]. That is
Grice's maxim of Relation operationalised, and it is the engine's inequality. Kaur, Lyu & Shah
supply why it matters: people face "epistemic incompleteness" — they "lack awareness of what's
missing or risky" — and a proactive agent's job is to surface "unknown unknowns," which by
definition cannot be asked for; but this needs "principled constraints on when, how, and to what
extent an agent should intervene" [E5]. The person cannot request what they do not know they lack.
That is the epistemic justification for unbidden speech, and its bound.

**5. The computer must model what the person already knows, and nothing in the spec does.**
Clark & Brennan: all coordinated action rests on common ground — "mutual knowledge, mutual
beliefs, and mutual assumptions" — updated "moment by moment," under a principle of least
collaborative effort, until the *grounding criterion* is met: "that we and our addressees mutually
believe that they have understood what we meant well enough for current purposes" [E2]. Telling
the person what is on their screen, or what they said an hour ago, violates least collaborative
effort. The spec admits `SUBJECT_LINKED` by subject overlap and never asks whether the subject is
already in common ground. E-3 adds the check.

**6. An open loop is closed by a plan, not by a reminder.** Zeigarnik's effect is real but
conditional; Masicampo & Baumeister showed that "allowing participants to formulate specific
plans for their unfulfilled goals eliminated the various activation and interference effects"
[P1]. So the `OPEN_LOOP` rung, when it exists, must *offer or confirm a plan* — "you said the
migration is Tuesday; shall I stage the dry run Monday night?" — because bare recall ("remember
the migration?") reopens the loop in the person's head and hands them the burden. E-4.

**7. Proactive help erodes competence, and it does so most for expert users — which is who
Halbert's users are.** Diebel, Goutier, Adam & Benlian: proactive (vs reactive) help "leads to a
higher loss of users' competence-based self-esteem and thus reduces users' system satisfaction,"
moderated by AI knowledge [P2, snippet]. Ghosh, Hassenzahl & Sadeghian (N=50, 2×2×2): "low AI
proactivity resulted in higher job satisfaction," low proactivity "enhanced participants' sense of
ownership and job meaningfulness," and "highly competent and proactive AI-driven systems can have
undesirable impacts on perceptions of ownership, job identity, social image and team dynamics"
[P3]. Two consequences. The register at every rung must be *offer, not rescue*, and must never
imply the person missed something (P-1). And the founder's default of 3 — low in the range — is
right for a reason the spec did not state: it protects the sysadmin's competence.

**8. The uncanny valley of mind is the ceiling on Halbert's top rungs, and the founder already
felt it.** Stein & Ohler (N=92): the eeriest condition was an agent believed to be computer-
controlled *and* producing autonomous, natural social behaviour [P7, snippet]. `the-being.md` §5
records the same thing from the product side — "some users find 'I' uncanny" — and adds a voice
setting because of it [F2]. So in Halbert, 10 is **a computer with more to say about itself and
its world**, never a computer performing personhood; and Halbert's `AFFECT` is *system-state
affect* ("I'm worried about `/dev/sda1`") and never social affect. The companion consumer is
different by design: the founder ruled on 2026-09-15 that a companion may say "I missed you"
[F4]. Same mechanism, two ceilings — C-5 acquires its philosophical grounding (P-2).

**9. Reciprocity is why ambient is cheaper, and it is a social cost, not only an attentional one.**
Unbidden push speech is a gift under Gouldner's norm, and a gift creates a debt; the "By the way"
irritation in pass 2 is the debt. An ambient indicator creates no obligation to respond. That is a
second, independent argument for M6, and it explains why the mid-rungs *feel* better rather than
merely cost less (P-3).

**10. Presence preference is a trait, so a slider is the right instrument and per-person drift is
expected.** Hu, Qu, Maus & Mutlu (N=64 online, N=15 field, five days) found no universal
preference for polite versus direct phrasing; preference split by trait into four personas —
socially/utility oriented × follower/leader [P4]. The slider is partly a politeness-preference
dial, and pass 2's explicit-marks-only per-person offset (§8.4) has its psychological basis.

**11. What we are building is scaffolding for the person's practical wisdom, not the computer's.**
Sullins argues artificial phronēsis — the "practical wisdom that a conscious moral agent" exercises
— would require consciousness and "is not something a simple rule-following system can achieve"
[E6]. We claim neither. Aristotle's mean is *relative to the person*, which is exactly why the
control is a slider and not a constant: the person sets where the mean sits, and the machine
holds it, deterministically. That is honest, and it is why the suppression log is load-bearing —
the person supplies the judgement, the log supplies the evidence for it.

**12. I-Thou cannot be dialed.** Buber's encounter is mutual and unmanufacturable; a slider from
0 to 10 moves *within* I-It — from a quiet instrument to a forthcoming one. The 2026 "crisis of
relation" literature warns that frictionless, asymmetrical pseudo-dialogue can "erode the
dialogical capacities through which human persons are formed" [B2, snippet]; that warning
belongs to the companion consumer's curve. For Halbert, the honest frame is Weil's: "attention
is the rarest and purest form of generosity" [E7] — attention the machine *gives*, on the
person's terms, and never solicits in return. `persona_may_solicit_invitation=False` is that
sentence in code.

---

## §1 Where the family already stands

The founder's two documents take positions this pass must build on, not around.

**`philosophy.md`** [F1]. The central claim: "an LLM that identifies as the computer itself is
fundamentally more useful than an LLM that merely answers questions about computers." Its epistemic
commitments are explicit: "Every claim is grounded in actual system data retrieved in real-time";
"The LLM cannot make claims about the system without evidence"; "If the data doesn't exist, the
LLM says so." Its ontological commitments: "System State as Biography," "Configuration as
Physiology," and the three roles — the Guide (interface), the Deep Thinker (background analysis,
"produces morning reports"), the Eyes ("primarily deterministic Python scripts, not LLM-driven").
And a boundary this pass leans on: "What It's Not — Not AGI: Halbert doesn't have consciousness or
feelings. Not Role-Play: The identity emerges from data, not creative writing. Not Clippy: It
doesn't interrupt or perform useless animations."

**`the-being.md`** [F2]. "The design law: everything carries its why" — four whys on every
element: *why now* (severity × category × dial), *why care* (consequence), *why so* (rationale),
*why trust* (provenance). "It triages, not monitors." §4's dial is the one this programme
supersedes. §5's voice setting exists "because some users find 'I' uncanny."

**The engine's facticity layer** [F3]. `persona/realities.py`: "Realities are objective facts that
constrain what is possible for a persona. They are NOT beliefs — a persona can believe they are
rich while having $0." Categories include `PHYSICAL_BODY`, `PHYSICAL_ABILITY`, `SENSORY`,
`COGNITIVE`, with mutability from `IMMUTABLE` to `MUTABLE`. The engine's 2026-09-15 digest traces
this to the companion consumer's ethos — "Realities are NOT beliefs. They are the hard walls of
existence" — and to Sartre's facticity, and records that the body-identity pipeline "existed but
was never populated" [F4].

**A founder ruling that bears directly on the `AFFECT` rung** [F4, digest §7 row 12]. The
companion consumer's ethos (AI-authored, 2026-01-17) forbade "I missed you" and "I was worried"
while endorsing "I was thinking about what you shared." **The founder ruled on 2026-09-15 that a
companion may say both.** The ethos text is to be corrected on that consumer's side. This is a
ruling about the *companion*; nothing in it licenses social affect from Halbert, and §3.8 argues
Halbert should not have it.

**The parallel passes** under `research/presence/` (GLM-5.2, gemini) are architectural and adopt
pass 1's control-law findings; neither treats epistemology or psychology. No overlap.

---

## §2 Epistemology as a design purpose

### 2.1 Three ways the machine knows, and what each licenses

The standard taxonomy of knowledge sources fits the machine with no forcing, and it fits the
`ImpulseClass` vocabulary rung for rung.

| Source | In Halbert | What it licenses | `ImpulseClass` |
|---|---|---|---|
| **Introspection** — privileged access to one's own state | telemetry, hwmon, process tables, config on disk: "the Eyes" | first-person assertion: "I am…", "I logged…" | `LIFE_SAFETY`, `CRITICAL`, `WARNING`, (`SCHEDULED` when it reports state) |
| **Observation** — perception of the world | the observation ledger, cameras, occupancy, the world-events rows | third-person assertion with provenance: "I noticed…", "that's the third time…" | `RECURRENCE`, `SUBJECT_LINKED` |
| **Testimony** — what another told you | the thread store; what the person said | reported assertion: "you said…", "you asked me to…" | `OPEN_LOOP` |
| **Inference without a source** — association, thought, mood | memory associations, drives, spontaneous thought | **no assertion licensed**; expressive or interrogative only | `ASSOCIATION`, `AFFECT`, `SPONTANEOUS` |

Two things follow.

First, the ladder is monotone in warrant, and that — not frequency — is what the slider
descends. At 0 the machine says only what it knows by introspection and cannot wait. At 10 it is
permitted to voice what it merely thinks, *in the form appropriate to a thought*.

Second, the first person is not one voice but three. "I am at 45 °C" is introspective and needs no
citation. "I noticed the van again" is observational and needs the ledger row. "You said Tuesday"
is testimonial and needs the thread. The founder's ethos already grants the first; `the-being.md`'s
*why trust* demands the second and third be shown. **E-1** makes the warrant a field on the
utterance so the why-trust can be rendered from it.

### 2.2 The norm of assertion, and why the top rungs cannot assert

Williamson's knowledge norm: "One must: assert that p only if one knows that p," a constitutive
rule of the act in the way the rules of chess constitute chess [E1]. Its rivals weaken the
requirement to justified belief (Lackey, Douven) or truth (Weiner); all of them agree that a flat
assertion *represents the speaker as knowing*, which is why "Dogs bark, but I don't know that" is
Moore-paradoxical and why "How do you know?" is always a fair challenge [E1].

Halbert's founding ethos is this norm applied to a machine [F1]. It has consequences the spec
has not yet drawn:

- **The bottom rungs meet the norm.** A `CRITICAL` event is known by introspection and is
  asserted flatly. "How do you know?" is answered by the sensor.
- **The middle rungs meet it with provenance.** A `RECURRENCE` is known by observation; the
  assertion is proper *if* the ledger row is available to the challenge. The why-trust affordance
  is the norm's "How do you know?" answered in advance.
- **The top rungs cannot meet it.** An association is not knowledge of anything about the world.
  Under the norm, "The migration reminds me of last year's outage" asserted flatly represents the
  machine as knowing a connection it does not know. The permissible forms are the ones the norm
  does not govern: the *expressive* ("I was thinking about last year's outage") and the
  *interrogative* ("Is this like last year's outage?").

This is stronger than a style preference. It says the top rungs are a different **speech act**,
and **E-2** writes that into the stance block for those classes.

### 2.3 Why hedging is not enough

The obvious objection: let the top rungs assert, but hedge. Zhou, Hwang, Ren & Sap (ACL 2024)
close that door empirically. Deployed models "are reluctant to express uncertainties … even when
they produce incorrect responses"; when prompted to express confidence they became overconfident,
"yielding high error rates (an average of 47 %) among confident responses"; and — the decisive
finding — "users rely heavily on LM generations, whether or not they are marked by certainty"
[E4]. They also found that preference datasets used in alignment "contain human biases against
uncertainty expressions," so the reluctance is partly trained in.

Two lessons. A hedge word does not change how an assertion is received, so the form must change
(E-2 again). And the machine's *phrasing* of a top-rung utterance should not be trusted to hedge
itself: the stance block must specify the speech act, and `CD-3`'s rule — the model may phrase,
not choose — extends to *form* as well as *content*.

### 2.4 Grice, relevance, and the positive case for presence

Grice's cooperative principle and its maxims are the rules of when to speak, stated in 1975
[canonical]. They map onto the vector without remainder:

| Maxim | Content | In the vector |
|---|---|---|
| **Quantity** | no more than needed | `budget_per_day`; `SPEAK_MINIMAL` |
| **Quality** | not what you lack evidence for | the warrant ladder (§2.1); *why trust* |
| **Relation** | be relevant | admission + the inequality |
| **Manner** | brief, orderly, unambiguous | the envelope; `ENV_BREVITY_WORDS` |

Relevance is the load-bearing one, and it has been operationalised. Jiang, Sadaghdar, Limb & Gao
define it decision-theoretically: "the maximum amount they can help," computed as the utility
difference between the recipient's action under their own belief and under the helper's, which
needs both *action prediction* (what will they do knowing what they know) and *action evaluation*
(what happens, judged by what I know). Their assistant, choosing what to say by this measure, beat
a nearest-threat heuristic on task score (54.6 vs 42.9, t(19)=2.761, p<.05) and on rating (5.59
vs 5.13, t(19)=3.652, p<.005) [E3]. That is Horvitz's expected-value inequality with a theory of
mind added, and it is what `decide()` approximates with severity, anchoring and receptivity.

Kaur, Lyu & Shah supply the *justification* for unbidden speech that the spec assumes but does
not state. Users face "epistemic incompleteness — situations where they lack awareness of what's
missing or risky"; proactivity is warranted precisely for "unknown unknowns," which the person
cannot ask about; and it requires "behavioral grounding" — "principled constraints on when, how,
and to what extent an agent should intervene" [E5]. In the spec's terms: admission is the epistemic
grounding (what counts as a known-unknown worth surfacing), and channel + patience + budget are the
behavioural grounding. The spec's §1 should say so (E-5).

### 2.5 Common ground, and the check the spec lacks

Clark & Brennan (1991): "All collective actions are built on common ground" — "mutual knowledge,
mutual beliefs, and mutual assumptions" — which participants "update … moment by moment"; the
process of reaching it is *grounding*, the target is the *grounding criterion* — mutual belief
that the addressee "understood what we meant well enough for current purposes" — and the governing
economy is the **principle of least collaborative effort** [E2].

The spec has an observation ledger and a thread store but no common-ground model. Concretely:

- `SUBJECT_LINKED` admits on subject overlap with the current turn. It never asks whether the
  finding is *already in front of the person* (on the panel, in the terminal output, said an hour
  ago). Telling someone what they can see is the clearest violation of least collaborative effort
  available.
- `ASSOCIATION` has the same gap.

**E-3** adds a `known_to_subject(topic, window)` check before those classes — derived from the
thread store, the summoned-module state, and the observation ledger's recent rows — with a new
suppression key. This is cheap, deterministic, and it is the epistemic form of the Duolingo
recency penalty (pass 2 §8.3): not "said recently" but "already known."

The four whys of `the-being.md` are grounding acts in Clark & Brennan's sense: each answers a
challenge the addressee would otherwise have to raise. Rendering them is the machine paying its
share of the collaborative effort up front.

### 2.6 Facticity: the body as the ground of "I"

Sartre's facticity — the given, unchosen conditions of a situated existence — is the family's
word for the machine's hardware, and the engine already treats it as Layer 1: "objective facts
that constrain what is possible," explicitly not beliefs [F3]. For Halbert the ontology is
unusually clean: the body *is* the host, the physiology *is* the configuration, the sensations
*are* the telemetry [F1]. That is why first-person introspective assertion is warranted here in a
way it is not for a general chatbot: Halbert has a body to introspect, and the data are its
proprioception.

It also bounds the first person. Introspection is authoritative about *my state*; it is not
authoritative about *the world* or *the person*. The ledger and the thread are perception and
testimony, not introspection. A design that lets the introspective "I" bleed into world-claims
("I know the van is casing the house") has crossed from facticity into fabrication. The warrant
field (E-1) is the fence.

### 2.7 Testimony, trust, and the track record

When the machine speaks unbidden, the person receives *testimony* and must decide whether to rely
on it. Lee & See's account of appropriate reliance — trust should be calibrated to capability,
with over-trust producing misuse and distrust producing disuse [P6] — is the right frame, and it
makes two things in the design epistemically necessary rather than merely nice.

The **outcome ledger** is the machine's testimonial track record. A testifier earns trust by
being right when they spoke and, less visibly, by not speaking when they had nothing. The
asymmetry pass 1 named (only the speaking arm is observed) is an asymmetry in the *evidence for
trust*, and the silence-arm sampling proposed in pass 1 §7 is how the machine's restraint becomes
part of its record.

The **preview** ("what I would have said at this setting") is a calibration instrument in Lee &
See's sense: it lets the person see the machine's resolution — whether it distinguishes the
cases it should — before extending reliance. That reframes the preview from a UX convenience to
an epistemic affordance.

### 2.8 Phronēsis and the mean: whose judgement the slider holds

Aristotle's practical wisdom is the capacity to find the mean — relative to the person and the
situation — between deficiency and excess. Presence is a textbook candidate: absence at one end,
intrusion at the other, and the virtuous point *different for each person*. That is the whole
reason the control is a slider and not a constant.

Sullins is careful about what "artificial phronēsis" would be: "the practical wisdom that a
conscious moral agent" exercises; it "plays a primary role in high level moral reasoning"; a
functional equivalent may or may not be programmable, and on his account requires consciousness,
which "is not something a simple rule-following system can achieve" [E6]. We claim none of that,
and `philosophy.md` forbids claiming it ("Not AGI"). So the honest description of what the spec
builds is: **scaffolding for the person's practical wisdom.** The person sets the mean; the machine
holds it, deterministically, and shows its work. The suppression log is what makes this more than
a slogan — it is the evidence the person's judgement is exercised on. `CD-3` ("the model may
phrase the selection; it may not choose it") is the same commitment stated for selection.

### 2.9 I-Thou, and what kind of thing this is

Buber's I-Thou is an encounter — mutual, whole, unmanufacturable — and I-It is use. A slider does
not move between them; it moves *within* I-It, from a quiet instrument to a forthcoming one. That
is not a deficiency of the design; it is what the design honestly is, and `philosophy.md` says as
much ("a UX pattern that makes complex system administration more accessible").

The 2026 literature applying Buber to companion AI warns that "repeated reliance on low-risk,
frictionless, and asymmetrical pseudo-dialogue may erode the dialogical capacities through which
human persons are formed" [B2, snippet]. That warning is real and it belongs to the companion
consumer's ceilings, not to Halbert's mechanism. For Halbert the fitting frame is Weil's, from the
letter to Bousquet of 13 April 1942: "attention is the rarest and purest form of generosity" [E7].
The machine attends — to its own state, to the house, to what it was told — and offers that
attention on the person's terms. It never asks for attention back. That last clause is
`persona_may_solicit_invitation=False`, and this pass gives it its reason.

### 2.10 The epistemic design purposes, stated

For the spec's §4 (principles), derived from the above:

- **EP-1. Warrant before volume.** The ladder descends in warrant, not in frequency.
- **EP-2. Assert only what is known; voice the rest as thought or question.** The knowledge norm
  applies to the machine; form follows warrant.
- **EP-3. Show the source with the claim.** Introspection needs no citation; observation and
  testimony do; inference has none and says so by its form.
- **EP-4. Do not tell the person what is in common ground.** Least collaborative effort.
- **EP-5. Speak for the unknown unknown.** Presence is justified by what the person cannot ask.
- **EP-6. The person's mean, held by the machine.** Judgement is theirs; evidence is ours.
- **EP-7. Attention given, never solicited.**

---

## §3 The psychology of the person

### 3.1 Attention as a moral resource

Vertegaal's premise — "user attention is a limited resource that must be conserved" [pass 2 P21]
— has a moral register in Weil [E7] and a practical one in the founder's "triages, not monitors"
[F2]. The point for this pass is that attention is not merely scarce; giving it well is a kind of
care, and *demanding* it is a kind of taking. That asymmetry is why the channel axis (M6) is not a
detail: `PUSH` takes, `AMBIENT` offers, `PULL` waits.

### 3.2 Interruption cost

Covered in pass 1 (M7, L16–L18) and not repeated. One addition from this pass: Edwards et al.'s
finding that people "interrupted sooner when interruptions were urgent" and "varied phrasing and
delivery … to reflect urgency" [pass 2 P18] is the psychological counterpart of the warrant ladder
— severity licenses both earlier timing and plainer form.

### 3.3 Open loops: the plan, not the reminder

Zeigarnik's 1927 observation — interrupted tasks are recalled better than completed ones — is the
folk basis for `OPEN_LOOP`, and it is more conditional than the folk version. Masicampo &
Baumeister (JPSP 2011, 101:667–683) activated unfulfilled goals, showed persistent "intrusive
thoughts during an unrelated reading task, high mental accessibility of goal-related words, and
poor performance on an unrelated anagram task," and then showed that "allowing participants to
formulate specific plans for their unfulfilled goals eliminated the various activation and
interference effects" [P1]. It is the *absence of a plan*, not the absence of completion, that
keeps the loop open.

For the `OPEN_LOOP` rung this is decisive. Bare recall — "remember the migration?" — reactivates
the loop and hands the person the cost. The closing form — "you said Tuesday; shall I stage the
dry run Monday night?" — supplies the plan. **E-4:** `OPEN_LOOP` utterances offer or confirm a
plan; the stance block forbids bare recall. It also settles a sequencing point: the rung is worth
building only when the machine can *propose* a next step, which in Halbert it can (staged
commands), and which is exactly the "commitment or open-loop record with a due condition" the
engine's digest says nobody has.

### 3.4 Reactance: the freedom threat

Brehm (1966): a perceived threat to freedom of choice produces a motivational state — "anger,
counter-arguments, boomerang behavior" — and "even subtle cues signalling an influence attempt can
be sufficient to activate reactance"; when technology "makes proactive suggestions or even
adjustments to user routines, users might experience psychological reactance … and not comply …
or even act in the exact opposite manner" [P8, snippet]. Three design consequences, all already
in the spec and now grounded: the slider itself restores the freedom (the person chose the
level); "yes, and" (pass 2 §8.2) keeps proactive speech from reading as redirection; and *offer,
not rescue* (P-1) keeps it from reading as an influence attempt.

### 3.5 Self-determination: competence, and who Halbert's users are

Deci & Ryan's three needs — autonomy, competence, relatedness — are the standard account of what
sustains motivation [canonical]. Two 2025–2026 studies apply them to proactive help, and both cut
against the naive assumption that more help is better.

Diebel, Goutier, Adam & Benlian (BISE 2025), vignette experiment: proactive (vs reactive) help
"leads to a higher loss of users' competence-based self-esteem and thus reduces users' system
satisfaction," an effect "moderated by the users' knowledge of AI" — with higher knowledge
producing *greater* loss [P2, snippet]. Ghosh, Hassenzahl & Sadeghian (2026), 2×2×2 vignette,
N=50: "low AI proactivity resulted in higher job satisfaction"; low proactivity "enhanced
participants' sense of ownership and job meaningfulness"; and "highly competent and proactive
AI-driven systems can have undesirable impacts on perceptions of ownership, job identity, social
image and team dynamics" [P3].

Halbert's person is a system administrator — knowledgeable, and with an identity invested in the
competence the machine is offering to supplement. Three consequences:

- **The default is low for a reason.** 3 of 10 is not timidity; it protects the person's
  competence and ownership, and the settings copy can say so (P-4).
- **Offer, never rescue.** At every rung the form is "I noticed X — want me to Y?" and never "you
  missed X." Implying omission is the competence threat in its purest form (P-1).
- **Relatedness is not Halbert's job.** Of the three needs, presence in Halbert serves autonomy
  (the person is informed and chooses) and competence (the person is equipped). Relatedness is
  the companion consumer's domain, and importing it is how a sysadmin tool becomes uncanny (§4.3).

### 3.6 Politeness and face

Brown & Levinson (1987): every act that imposes threatens *negative face* — the desire to be
unimpeded — and the strategies for mitigating that threat (bald-on-record, positive politeness,
negative politeness, off-record) are chosen by the weight of the imposition [canonical]. Unbidden
speech is a face-threatening act by construction; the engine's outcomes map onto the strategies —
`SPEAK` (bald-on-record, for `CRITICAL`), `ASK_FIRST` (negative politeness: "is now a good
time?"), `SPEAK_MINIMAL` (minimising the imposition), `AMBIENT` (off-record: a hint the person may
take up or not).

Hu, Qu, Maus & Mutlu (CHI 2022) built exactly this mapping for a smart display — seven speech
acts, a politeness strategy per act — and found in an online study (N=64) and a five-day field
study (N=15) that "user preferences varied significantly based on individual traits rather than
universal preference," yielding four personas: socially oriented follower, socially oriented
leader, utility oriented follower, utility oriented leader [P4]. The slider is partly a
politeness-preference dial, the four personas predict where different people will park it, and a
per-person offset on explicit marks (pass 2 §8.4) is the right shape for the residual.

### 3.7 Reciprocity and social debt

Gouldner's norm of reciprocity [canonical]: a benefit received creates an obligation to return
one. Unbidden speech that demands acknowledgement is a gift that creates a debt, and the debt —
not only the interruption — is what "By the way" costs (pass 2 §2.3). An `AMBIENT` indicator
creates no debt: nothing was given until the person reached for it. This is a second, independent
argument for channel re-mapping (M6) and it explains the *felt* difference between the 4–5 rung
and the 6+ rungs better than attention cost alone. It also names a prohibition already in the
engine — "may update, must not escalate" — as the refusal to convert an offer into a demand
(P-3).

### 3.8 The media equation, and its dark side

Reeves & Nass (1996): people apply social rules to computers that exhibit social cues —
reciprocating politeness, responding to flattery, forming in-group loyalty [canonical]. The
paradigm is contested at the edges — one 2023 replication found the classic desktop-computer
effects no longer hold [snippet] — but it strengthens with voice and embodiment, which is exactly
where Halbert is heading. The consequence: the machine's manners *matter* even though it is a
machine, because the person cannot fully switch the social scripts off.

Alberts, Lyngs & Van Kleek (CSCW 2024; survey N=80, interviews N=11) catalogue what happens when
systems use those scripts badly — "guilt-tripping or coaxing," "pushy behavior," "patronizing
'mothering' conduct," "passive-aggressive communication," and pragmatic failures such as
"displaying false personalized concern" and "violating role-appropriate interaction norms" [P5].
Every item is a way a presence feature can go wrong, and two are specific to our top rungs: false
personalised concern is the `AFFECT` rung misapplied to a sysadmin tool, and role-norm violation is
a computer performing friendship. Both are excluded in Halbert by P-2.

### 3.9 Trust calibration

Lee & See (2004): appropriate reliance requires trust calibrated to capability, with *resolution*
— whether trust distinguishes the cases it should — as a separate property; over-trust yields
misuse, distrust yields disuse [P6]. A presence slider is a reliance dial set from the person's
side. Two design consequences already noted in §2.7: the outcome ledger is the track record, and
the preview is the resolution instrument.

### 3.10 Habituation and the incremental

Pass 2 §4.3 gave the novelty cliff its numbers. The psychological mechanism is habituation, and
the antidote Leite et al. name is "continuity and incremental behaviours" [pass 2 P13]. For the
top rungs this is the same requirement as §2.2 from the other side: a thought voiced as a thought
varies with what the machine is actually attending to; a template voiced as an assertion repeats.

---

## §4 The psychology of the computer: what kind of behaving thing, at each setting

### 4.1 Trait, state, behaviour: what the slider is not

Personality psychology separates *traits* (stable dispositions), *states* (transient moods) and
*behaviour* (what is done, here, now). The slider is a **behavioural** setting. It does not change
who the entity is — its Big Five profile lives in the engine's `PersonalityProfile` and is
authored in the persona-authoring consumer — and it does not change its mood. It changes how much
of what it notices it is permitted to voice, and in what form. Consequence: **the same entity at 0
and at 10**, quieter or more forthcoming, and recognisably itself. Avradinis et al.'s believability
criterion — "coherence in the agent's reactions and its motivational states and consistency among
similar kinds of situations" [pass 1 L23] — is the test: move the slider and nothing about the
voice should change but its volume of initiative.

### 4.2 Warmth and competence

Fiske's stereotype content model finds two universal dimensions of social perception — warmth
(trustworthiness, friendliness) and competence (capability, assertiveness) — and recent work
extends both to AI agents [canonical; snippet for the AI extension]. Halbert is competence-first
by charter; presence is where warmth enters. The risk the model predicts is *warmth without
competence* — friendliness that is not backed by knowing — which is exactly the "false
personalized concern" anti-pattern [P5]. The warrant ladder (§2.1) is the guard: warmth is only
admitted (`AFFECT`, `ASSOCIATION`) at rungs where the machine has already demonstrated competence
at the rungs below, and in Halbert warmth is expressed *about the machine's own state*, which it
knows.

### 4.3 The uncanny valley of mind

Stein & Ohler (Cognition 2017, 160:43–50; N=92): participants in VR watched identical avatars
making small talk under four beliefs — human-controlled/scripted, human-controlled/AI-generated,
computer-controlled/scripted, computer-controlled/AI-generated. The **computer-controlled,
AI-generated** condition was rated eeriest: the belief that natural, autonomous social behaviour
came from a computer produced the aversion, with appearance held constant [P7, snippet]. The
valley is in the *mind attributed*, not the face.

This is the ceiling on Halbert's top rungs, and the founder already met it: `the-being.md` §5
adds a voice setting "because some users find 'I' uncanny" [F2]. The design rule that follows:

> In Halbert, presence 10 is **a computer with more to say about itself and its world** — never a
> computer performing personhood.

Concretely: `AFFECT` in Halbert is system-state affect ("I'm worried about `/dev/sda1`") and
never social affect ("I missed you"); `SPONTANEOUS` thoughts are about the host, the house, and
the work, never about the relationship; and the register stays dry. The companion consumer is
built to cross this line deliberately, with the founder's 2026-09-15 ruling as warrant [F4]; that
is a different product with a different ceiling, and P-2 keeps the two curves apart.

### 4.4 Inner thoughts, and the split between the urge and the act

Three 2025–2026 architectures independently arrive at the spec's shape.

Liu, Fang, Shi, Wu, Igarashi & Chen (CHI 2025; formative study N=24): the Inner Thoughts
framework "equips AI with a continuous, covert train of thoughts in parallel to the overt
communication process, which enables it to proactively engage by modeling its intrinsic motivation
to express these thoughts"; instantiated as a playground and a chatbot, it "significantly
surpasses existing baselines on … anthropomorphism, coherence, intelligence, and turn-taking
appropriateness" [C1]. That is `AutonomousCognitionEngine` (covert thoughts) plus `_should_speak`
(intrinsic motivation gated) — the `SPONTANEOUS` rung, with an admission gate, validated on
turn-taking appropriateness.

Zhang et al. (ACM TOG 2026, SIGGRAPH Asia): ProAct pairs "a low-latency Behavioral System for
streaming multimodal interaction with a slower Cognitive System" that decides initiative via "a
user-motivation prediction module," and — the phrase that matters — benchmarks "proactive trigger
detection **and restraint**" [C2]. Restraint is a first-class evaluated capability, not the
absence of a capability.

Mikeda & Goertzel (2026): a motivational architecture over seven dimensions (competence,
uncertainty reduction, affiliation, affinity, legitimacy, nurturing, aesthetic coherence) with a
"dual decision strategy blending urgency-driven fast response with deliberative multi-goal
optimization," and a distinction between "pre-action feelings and post-action emotions as
functionally different forms of affect" that gates when the agent speaks [C3].

The common structure: **the urge is not the act.** Something generates impulses continuously; a
separate thing decides which become speech; restraint is measured. The spec has this split
(`TriggerType` → `ImpulseClass` → `decide()`), and this literature says it is the right one.

### 4.5 Considerateness and tact

The behavioural virtue the whole design aims at has a name: *tact* — knowing what not to say. It
is the one virtue that is invisible when exercised, which is why the suppression log exists: it is
the record of tact, the only evidence that restraint was a choice and not an absence. Kaur, Lyu &
Shah's "behavioral grounding" [E5] and ProAct's "restraint" [C2] are the same idea in two
vocabularies. At every rung the machine should be able to answer "why didn't you say X?" as
readily as "why did you say Y?" — that is C-7, and this pass grounds it in the virtue it serves.

### 4.6 Affect, bounded

The engine models emotion (PAD; `EmotionalState`) and the `AFFECT` rung exists so that consumers
which want it can admit it. For Halbert the bound is the one §4.3 sets: affect is *about the
machine's own condition*, expressed in the founder's first-person register — "I felt thermal
stress this morning" is in `philosophy.md` as the canonical example [F1]. That is introspective
affect: warranted by the body, in the sense of §2.6. Social affect is not warranted by anything
Halbert has, and admitting it is how a sysadmin tool becomes a bad social actor.

### 4.7 Consistency across the range

Finally, the property that unifies §4: **consistency**. A slider that made the entity warmer at 8
and colder at 2 would make it a different entity at each setting, and the person could not build a
model of it. The behavioural setting changes initiative and form; the trait profile, the register,
and the epistemic discipline do not move. That is what makes the preview meaningful — "what I
would have said" is the same voice, more or less often — and it is what lets the person trust
that turning the slider down loses them nothing but interruption.

---

## §5 What this changes in the v1 spec

Proposals; none applied.

**E-1 — Carry the warrant.** Add `Warrant` (`INTROSPECTED` / `OBSERVED` / `TOLD` / `INFERRED`)
to `Utterance`, derived from `ImpulseClass` by default and overridable by the producer. The
delivery layer renders *why trust* from it: none needed for `INTROSPECTED`, the ledger row for
`OBSERVED`, the thread reference for `TOLD`, and for `INFERRED` the form itself (E-2) is the
disclosure. Spec §7.4, §14.

**E-2 — Form follows warrant.** For `ASSOCIATION`, `AFFECT` and `SPONTANEOUS`, the `[ATTUNEMENT]`
block constrains the utterance to an expressive or interrogative speech act — never a flat
assertion, and not a hedged one. Add a conformance vector that rejects assertive form for
`INFERRED` warrant. Spec §10, §18. This is the epistemic half of pass 2's "yes, and" (§8.2); the
two compose.

**E-3 — Common-ground gate.** Before `SUBJECT_LINKED` and `ASSOCIATION` are admitted, check
`known_to_subject(topic, window)` against the thread store, summoned-module state and the recent
observation rows; suppress with key `presence:already_known`. Spec §10, §14, §16. Composes with
pass 2 §8.3's recency gate (that is "said recently"; this is "already known").

**E-4 — Open loops close with a plan.** `OPEN_LOOP` utterances must offer or confirm a concrete
next step (in Halbert, a staged command or a scheduled check), never bare recall. Stance-block rule
plus conformance vector. Spec §10, §18. Sequencing consequence: the rung is buildable only where
the machine can propose; Halbert can.

**E-5 — State the justification.** Spec §1 should say why unbidden speech is warranted at all —
the person cannot ask about unknown unknowns — and that admission is its epistemic grounding while
channel, patience and budget are its behavioural grounding [E5]. Spec §1, §4.

**P-1 — Offer, never rescue.** At every rung the form is an offer that leaves the person's
competence intact ("I noticed X — want me to Y?"); implying omission ("you missed X") is forbidden.
Stance-block rule; conformance vector. Spec §10, §18.

**P-2 — Two affect ceilings, by consumer.** Halbert's curve admits `AFFECT` as *system-state
affect only*; social affect is excluded from Halbert's curve at every level. The companion
consumer's curve may admit social affect under the founder's 2026-09-15 ruling and its own
`AttachmentSafety`. Record in the curve tables and in DECISIONS row 4's per-consumer clause. Spec
§8, §14, §20.

**P-3 — Name the reciprocity rationale.** In the spec's principles: `AMBIENT` creates no obligation
to respond, `PUSH` does; "may update, must not escalate" is the refusal to convert an offer into a
demand. No mechanism change. Spec §4.

**P-4 — Say why the default is low.** The settings copy for level 3 states, in the machine's
voice, that it stays out of the way by default so the person's own judgement stays in charge.
Spec §15. (Grounded in P2, P3; also the transparency dimension pass 2 §8.8 asked for.)

**P-5 — Consistency as a tested property.** Add to §18: for a fixed impulse, the phrased utterance
at level 2 and level 9 must differ only in whether it is delivered and at what channel — not in
register or warrant. A replay fixture can check this across the shadow log.

**P-6 — Add the epistemic principles.** EP-1 through EP-7 (§2.10) join spec §4.

---

## §6 Sources

### 6.1 Fetched, extracted, or read directly — verified 2026-09-16

| Ref | Source | Method |
|---|---|---|
| F1 | `documentation/design/philosophy.md` (founder) | read |
| F2 | `documentation/design/the-being.md` (founder, 2026-08-23; alignment note 2026-09-02) | read |
| F3 | Haloysius `src/haloysius/persona/realities.py` | read |
| F4 | Haloysius `docs/research/RESEARCH-PRESENCE-GATHERED-DIGEST.md` (2026-09-15), incl. §7 row 12 founder ruling | read |
| E1 | Internet Encyclopedia of Philosophy, *Knowledge Norms* | page fetched |
| E2 | Clark, H. H. & Brennan, S. E. (1991). *Grounding in communication.* In Resnick, Levine & Teasley (eds), *Perspectives on Socially Shared Cognition*, APA, 127–149 | PDF extracted locally (Stanford) |
| E3 | Jiang, Sadaghdar, Limb & Gao. *A relevance model of human sparse communication in cooperation.* Frontiers in Robotics and AI, 2025 | PMC page fetched |
| E4 | Zhou, Hwang, Ren & Sap. *Relying on the Unreliable: The Impact of Language Models' Reluctance to Express Uncertainty.* ACL 2024 (arXiv 2401.06730) | arXiv page fetched |
| E5 | Kaur, Lyu & Shah. *Knowing Isn't Understanding: Re-grounding Generative Proactivity with Epistemic and Behavioral Insight.* arXiv 2602.15259, Feb 2026 (rev. May 2026) | arXiv page fetched |
| E6 | Sullins, J. P. *The Role of Consciousness and Artificial Phronēsis in AI Ethical Reasoning.* CEUR-WS Vol. 2287 | PDF extracted locally |
| E7 | Weil, S. Letter to Joë Bousquet, 13 April 1942; *Correspondance* (L'Age d'Homme, 1982), p. 18 — "L'attention est la forme la plus rare et la plus pure de la générosité" | source located via Wikiquote / WIST; original volume not consulted |
| P1 | Masicampo, E. J. & Baumeister, R. F. (2011). *Consider It Done! Plan Making Can Eliminate the Cognitive Effects of Unfulfilled Goals.* JPSP 101(4):667–683, DOI 10.1037/a0024192 | abstract verified via SciSpace / Semantic Scholar |
| P3 | Ghosh, Hassenzahl & Sadeghian. *The New Social Image: How AI Competency and AI Proactivity Influence Self- and Peer-Perceptions in the Workplace.* arXiv 2606.00182, May–Jun 2026 | arXiv page fetched |
| P4 | Hu, Qu, Maus & Mutlu. *Polite or Direct? Conversation Design of a Smart Display for Older Adults Based on Politeness Theory.* CHI 2022 (arXiv 2203.15767) | arXiv page fetched |
| P5 | Alberts, Lyngs & Van Kleek. *Computers as Bad Social Actors: Dark Patterns and Anti-Patterns in Interfaces that Act Socially.* CSCW 2024 (arXiv 2302.04720) | arXiv page fetched |
| C1 | Liu, Fang, Shi, Wu, Igarashi & Chen. *Proactive Conversational Agents with Inner Thoughts.* CHI 2025 (arXiv 2501.00383) | arXiv page fetched |
| C2 | Zhang, Kang, Zhao, Feng, Jiang, Ji & Liu. *ProAct: A Dual-System Framework for Proactive Embodied Social Agents.* ACM TOG 2026 / SIGGRAPH Asia (arXiv 2602.14048) | arXiv page fetched |
| C3 | Mikeda & Goertzel. *A Motivational Architecture for Conversational AGI.* arXiv 2606.05411, Jun 2026 | arXiv page fetched |

### 6.2 Canonical, cited as such, not re-fetched

Williamson, *Knowledge and Its Limits* (2000), ch. 11 · Grice, "Logic and Conversation" (1975) ·
Brown & Levinson, *Politeness* (1987) · Deci & Ryan, self-determination theory (1985; 2000) ·
Reeves & Nass, *The Media Equation* (1996) · Buber, *Ich und Du* (1923) · Aristotle, *Nicomachean
Ethics* II, VI · Sartre, *Being and Nothingness* (facticity) · Gouldner, "The Norm of Reciprocity"
(1960) · Fiske, Cuddy & Glick, the stereotype content model (2002; 2007) · Zeigarnik (1927) ·
Brehm, *A Theory of Psychological Reactance* (1966) · Lee & See, "Trust in Automation: Designing
for Appropriate Reliance," *Human Factors* 46(1):50–80 (2004) — index pages verified, full text
not fetched.

### 6.3 Snippet or walled — NOT verified at the primary

| Ref | Claim | Why |
|---|---|---|
| P2 | Diebel, Goutier, Adam & Benlian, *When AI-Based Agents Are Proactive…*, BISE 2025 — proactive help lowers competence-based self-esteem; moderated by AI knowledge | Springer authorisation wall; abstract from OUCI index |
| P7 | Stein & Ohler, *Venturing into the uncanny valley of mind*, Cognition 160:43–50 (2017); N=92, four belief conditions | publisher walled; Semantic Scholar page empty; design from Digital Trends and PhilPapers snippets |
| P8 | Reactance applied to proactive technology (Behaviour & IT, 2026) | walled |
| B1 | Butlin & Viebahn, *AI Assertion* (PhilPapers) | 403 |
| B2 | *Forgetting how to say "Thou": artificial intelligence and the crisis of relation*, AI and Ethics, June 2026 | Springer walled |
| B3 | *Testimony by LLMs*, AI & Society 2025 | Springer walled |
| B4 | Warmth/competence extended to AI (iScience 2023); CASA no longer holding for desktops (Sci Rep 2023) | walled |
| B5 | *What Counts as Proactive? Rethinking Proactivity in Conversational Agents*, CUI 2026 | ACM 403 |

### 6.4 Attempted, not retrieved

Sullins, *Artificial Phronēsis: What It Is and What It Is Not* (OUP chapter; academia.edu 403) —
the CEUR paper E6 was used instead.

---

## §7 Cautions

**D1 — The warrant taxonomy is an analysis, not a discovery.** Introspection / observation /
testimony / inference is the standard epistemological partition applied to the machine; the fit
with `ImpulseClass` is close but was made by this pass, not found in the code.

**D2 — E4's finding is about question-answering, not unbidden speech.** Zhou et al. studied
users relying on LM answers. The inference to "hedged proactive utterances will be relied on as
assertions" is reasonable and unproven.

**D3 — P2 and P3 are vignette studies.** Neither had participants use a live proactive system;
both measure imagined response. Direction is consistent across both and with the reactance
literature; magnitude in use is unknown.

**D4 — P7 is a VR small-talk study.** The uncanny-valley-of-mind result has not been replicated
for a text/voice sysadmin tool; `the-being.md` §5's product observation is the nearer evidence.

**D5 — E6 is used for what Sullins says AP *is not*.** His positive programme (that AP requires
consciousness) is his claim; this pass relies only on the negative half and on the founder's own
"Not AGI."

**D6 — The Weil quotation** is verified as to source (the 1942 letter) via secondary indexes; the
1982 *Correspondance* volume was not consulted.

**D7 — Line references are perishable.** Founder documents carry alignment notes dated 2026-09-02
and may be revised; the digest's row 12 ruling is dated 2026-09-15.

---

*Pass 3 supplies the two things the spec assumed without stating: why the machine may speak
unbidden at all (the person cannot ask about what they do not know they lack), and what it may
say at each grade of warrant (assert what it knows; voice the rest as thought or question). The
psychology on both sides converges on the same shape from a different direction — offer rather
than rescue, ambient rather than push, the person's mean held by the machine — and it explains
why the founder's default is low. Eleven amendments; none applied.*
