# Research — presence controls in the wild: how others built them, and what happened

**Date:** 2026-09-16
**Status:** Research pass 2. **Nothing here is decided.** §8 proposes amendments to the v1 spec;
they are proposals.
**Companion documents:**
`RESEARCH-PRESENCE-SLIDER-CONTROL-LAW-2026-09-16.md` (pass 1: the control-law question, M1–M8,
F1–F6, C-1–C-10) and `documentation/superpowers/specs/2026-09-16-presence-slider-design.md`
(the v1 spec this pass is checked against).
**Question:** Pass 1 asked what a presence number *should* move. This pass asks what people who
actually shipped one built, what control they gave the user, and what happened next — across
consumer products, platform notification systems, embodied robots, and the 2021–2026 academic
record on proactive agents.
**Verification posture.** **Twenty-four sources were fetched and verified** — at their arXiv,
ACM, publisher, engineering-blog or author page, or extracted locally from PDF (§9.1). Six
claims rest on search snippets or on secondary reports where the primary was unreachable; each is
marked and quarantined in §9.2, and nothing in §0 or §8 rests on one alone.
**Naming.** Consumers by role. The two closed siblings are the companion consumer and the
persona-authoring consumer.

---

## §0 What the outcomes say, in one page

Twenty-plus systems, four kinds. Read together they are unusually consistent, and they validate
most of the v1 spec while correcting it in five places.

**1. The canonical failure is a threshold lowered for prominence — and it is our F3, in
production, in 1997.** Lumière had a user-adjustable value-of-assistance threshold, non-focus-
stealing windows and gentle timeouts. What shipped as the Office Assistant was "a relatively
simple rule-based system on top of the Bayesian query analysis system to bring the agent to the
foreground" — the research team's own words, with their own recorded concern "that this system
would be distracting to users" [P1]. Every complaint about Clippy for twenty years is that
substitution. The spec's *band-translates-never-scales* rule and shadow-first gate are the direct
countermeasures, and they are now grounded in the best-known negative outcome in the field.

**2. Nobody ships eleven levels.** Slack ships three (All / Mentions & DMs / Mute) [P2]. Apple
ships four interruption levels (passive / active / timeSensitive / critical) [P3]. Alexa ships a
binary Brief Mode [S1]. The Sims ships Off / Full [P6]. Meta's Omni is a fixed policy with no
user level at all [P4]. The v1 spec's six named rungs with a 0–10 presentation is at the *high*
end of anything deployed. Not wrong — but §8.1 asks whether the number or the names should be
the primary control.

**3. Slack independently arrived at our two central structural decisions.** Its 2026 rebuild
split *what to notify about* from *how it is delivered* — exactly the spec's admission/channel
split — and it **removed "Off" from the top-level control**, because "Off" silenced push but left
in-app badges live and confused people; it now reads as "Mentions with push disabled" [P2].
That is the spec's "hard off is not on the slider" and "channel is separate from admission",
reached by a different team on a different product. Outcome: a five-fold sustained increase in
settings engagement, fewer per-channel overrides, and a majority of users on the default.

**4. Budget as a control is win-win at scale, and the use-it-or-lose-it fear is empirically
wrong.** Pinterest's per-user volume system *reduced* notification volume while *raising*
click-through and site engagement [P8]. LinkedIn's Air Traffic Controller "cut member complaints
in half" and produced "double digit increases in member engagement site-wide" while making
per-member volume, channel and timing decisions [P9]. Fewer, better-placed interruptions beat
more. This is the strongest possible evidence for M2 as an axis and for `budget_per_day` being a
ceiling rather than a target.

**5. The novelty cliff is two to three weeks, and what would have prevented it is exactly the
thing we do not have yet.** Vector attachment declined after 2 weeks of a 30-week study [S4];
children lost interest after three sessions of repeated behaviour [P13]; a companion robot
"blended into the rest of my life" by week six [P14]. Guy Hoffman's post-mortem on Jibo, Kuri
and Anki: "its tricks get old quickly," and what users wanted instead was "follow-ups,
cross-conversation references, and overlapping dialogue" [P12]. That is `OPEN_LOOP` and
`ASSOCIATION` — the rungs the spec types but leaves unreachable. Pass 1's F5 ("the top half is
blocked on memory") is what the robot graveyard teaches.

**6. Ambient presence has a 2003 specification and a 2025 user study behind it.** Vertegaal's
CACM article on Attentive User Interfaces describes systems that "negotiate rather than impose
the volume and timing of their communications" and that "progressively signal their requests for
attention. Initially this may happen through a channel peripheral to the user's activity. AUIs
may then wait for user acknowledgment … before they take the foreground" [P21]. That is the
spec's "admitted but ambient" rung, stated twenty-three years ago. And the CHI 2025 Codellaborator
study (N=18, within-subject) found that "presence indicators and interaction context alleviated
disruptions and improved users' awareness of AI processes" while proactive agents alone "incur
workflow disruptions" [P15]. The presence pill is evidence-backed.

**7. Explicit user marks are what move a personal threshold — not inference.** Gmail Priority
Inbox treated importance "as ranking rather than classification because tuning the threshold
quickly is critical for user perceived performance," found it "difficult to algorithmically
determine the threshold," and settled on "manual intervention from users … when a user marks
messages in a consistent direction, we perform a real-time increment to their threshold." Error
on user-marked mail fell from 45 % (global model) to 31 % (per-user model plus per-user threshold)
[P7]. This is the correct shape for any future learning in our system: the reaction ledger's
*explicit* marks nudge a per-class band, and nothing inferred does.

**8. Scheduled proactivity has a characteristic failure: rigidity.** The CHI 2026 "Having Lunch
Now" study (12 participants, 14 days, twice-daily check-ins, 336 conversations) names "rigidity,
premature turn-taking, and overpromising" as the agent's problems, with participants who
"resisted or disengaged" [P16]. Our `SCHEDULED` rung — the morning report — needs to be
negotiable, not just deliverable.

**9. A proactive feature without a user control is the worst outcome on record.** Alexa's "By
the way" digressions are "a constant source of ire," Brief Mode does not reliably suppress them,
and the reported workaround is a daily routine that re-issues "stop by the way" [S1]. The slider
*is* the control; the lesson is that shipping without one is not an option.

**10. The most explicit production presence policy is Meta's, it is essentially our engine's
shape, and it was criticised anyway.** Omni bots message first only if the user sent ≥5 messages
in the last 14 days, send one follow-up, and stop if there is no reply [P4]. That is an earned-
invitation gate, a budget of one, and withdrawal-on-silence — our `InvitationLevel`,
`budget_per_day` and `Reaction.IGNORED`. The criticism was of the *objective* ("re-engagement and
user retention"), not the mechanism. C-3 and C-5 are right that the policy is necessary and not
sufficient; the objective must be well-judgedness, and it must be visibly so.

---

## §1 The canonical failure: Lumière → the Office Assistant

**What was designed** [P1, verified from Horvitz's own project page]. Lumière (Microsoft
Research, from 1993) used Bayesian models over "user background, actions, program state, and
natural language queries" to produce "probability distributions over areas where users might
need assistance" and — separately — "the likelihood that users would welcome interruptions."
The proactive-help half had three properties that matter here:

- a user-adjustable threshold: "users could wrap the help system around their own preferences
  for the value of assistance";
- non-intrusive presentation: "small windows that wouldn't steal focus";
- graceful expiry: recommendations "time out with a gentle apology if users did not hover or
  interact."

**What shipped** (Office 97, January 1997). The Bayesian *query* analysis shipped — "but is only
available when the user engages the system on their own." For the proactive tips, "the Office
team has employed a relatively simple rule-based system on top of the Bayesian query analysis
system to bring the agent to the foreground with a variety of tips." The researchers' recorded
reaction: "We had been concerned upon hearing this plan that this system would be distracting to
users — and hoped that future versions of the Office Assistant would employ our Bayesian approach
to guiding speculative assistance actions."

**Outcome.** The most ridiculed proactive agent in computing history, retired in 2001 (Office XP
shipped it off by default) and removed in Office 2007. Secondary accounts [S-Clippy, snippet]
add that the Bayesian trigger was judged "too cautious" and replaced so the assistant "would pop
up more often," and that the substituted rules fired on single-word cues ("Dear…" → letter).

**What it says to the spec.**
- *F3 was a real failure mode before it was a finding.* A threshold moved for prominence, by a
  team other than the one that calibrated it, is precisely what `band_shift`-as-translation and
  the derived-not-authored threshold rule (spec §7.5, §4) exist to prevent. The curve is data,
  but the band width is not on the curve — deliberately.
- *Lumière's three proactive properties map one-to-one:* user threshold → the slider; non-focus-
  stealing windows → `AMBIENT`; gentle timeout → the `HOLD` deadline and, per §8.6 below, an
  expiry on ambient indicators.
- *Shadow-first is the institutional countermeasure.* The substitution happened between research
  and product with no shared evidence. A shadow lane that both sides can read is the thing that
  was missing.

---

## §2 Production presence controls: what shipped, what the user could set, what happened

### 2.1 Slack — three tiers, activity split from delivery, "Off" retired

[P2, verified: Coronel & Kannan, Slack Engineering, 19 March 2026, updated 16 April 2026.]

The 2026 rebuild organises every preference into three tiers:

| Tier | Options |
|---|---|
| **What to notify about** | All new messages · **Mentions and DMs (default)** · Mute |
| **Push notifications** | Desktop and mobile (default) · desktop only · mobile only · disabled |
| **Advanced** | mobile-specific customisation, badge controls |

The design principles were named as calm, consistency, clarity. The architectural move was to
"decouple 'what' users see from 'how' they receive notifications, allowing independent control
over in-app awareness and push interruptions."

The legacy **"Off"** setting was retired from the first tier: it "created confusion because it
silenced push notifications but left in-app badges active." It is now interpreted at read time as
"Mentions with push disabled" — no migration.

**Outcomes:** settings engagement "increased 5-fold and sustained for weeks"; "decreased reliance
on per-channel overrides"; "majority of users adopted the 'Mentions and DMs' default setting"; a
measurable reduction in notification-related support tickets [InfoQ summary, snippet].

**What it says to the spec.** Direct validation of three decisions made independently:
admission (tier 1) is separate from channel (tier 2) — spec §7.2's `admits` vs `channel`; hard
off is not on the primary control — spec §3.1(b) and DECISIONS row 3; per-class overrides fall
away when the global control is legible — spec §9's hope. And a caution: three options, not
eleven, produced the engagement gain.

### 2.2 Apple — four interruption levels and a scheduled summary

[P3, verified: Apple developer documentation, `UNNotificationInterruptionLevel`.]

| Level | Lights screen | Sound | Breaks through Focus / DND | Entitlement |
|---|---|---|---|---|
| **passive** | no | no | no | no |
| **active** (default) | yes | yes | no | no |
| **timeSensitive** | yes | yes | yes | yes |
| **critical** | yes | yes | yes | yes |

`passive` is "for non-intrusive delivery … information that can wait for the user to check their
device naturally"; it appears in Notification Center without sound, vibration or screen wake.
Separately, iOS 15's Scheduled Summary batches selected apps' notifications to a chosen time of
day, and does not interact with Focus modes [OneSignal/Medium summaries, snippet].

**What it says to the spec.** `passive` **is** `AMBIENT`-plus-`PULL`: it lands somewhere
navigable and demands nothing. `timeSensitive`/`critical` bypassing Focus is C-10 (critical is
not on the slider) — and Apple gates the bypass behind an *entitlement*, i.e. the class is
assigned by a reviewed process, not by the sender's judgement. That is the spec's rule that
`LIFE_SAFETY`/`CRITICAL` reject overrides (§9). Scheduled Summary is bounded deferral to a fixed
time — `ResumeCondition.AT_TIME` — shipped to a billion devices.

### 2.3 Alexa — Brief Mode, Hunches, and the unsilenceable "By the way"

[S1, snippet/secondary: Amazon's Brief Mode help page returned 503; TechHive, PCWorld, Tom's
Guide, Gear Patrol, TechCrunch 2018.]

Alexa has three distinct proactive surfaces: **Hunches** (2018; "Alexa noticed the porch light
is on" → from 2021 can act automatically), **Brief Mode** (March 2018; "Alexa speaks less and may
play a short sound instead of giving a voice response"), and **"By the way…"** — an unsolicited
suggestion appended after a completed request.

**Outcome.** "By the way" is described as "a constant source of ire on the Alexa subreddit."
Brief Mode does not suppress it: "even with the Brief Mode setting enabled, 'by the way' will
still manage to crop up." The voice command "Alexa, stop by the way" works "temporarily," and the
documented durable workaround is "a routine that issues the 'stop By the Way' command every day."
Hunches got a real toggle; "By the way" did not.

**What it says to the spec.** This is the counter-example that justifies the whole feature: a
proactive class with *no admission control* is the worst-received thing in the survey. Note also
the structure of the failure — "By the way" is `SUBJECT_LINKED` in our vocabulary (it follows a
request the user just made), delivered `PUSH`, with no rung a user can lower it to. The spec's
4–5 rung ("admitted but ambient") is the missing setting.

### 2.4 Meta — Project Omni: an explicit policy, no user level

[P4, verified: Bellan, TechCrunch, 3 July 2025, from leaked training documents.]

The rules the bots follow: message first only if "(1) the user initiated conversation within 14
days, and (2) the user sent at least 5 messages to the bot during that timeframe"; send a single
follow-up; "cease messaging if there is no response to the initial follow-up attempt." Bots
"remember information about users." Stated goal, from internal documents: "improve re-engagement
and user retention." Reception: criticised for engagement-driven monetisation, for safety risks
mirroring the Character.AI litigation, and for weak privacy disclosures ("laughably bad," per the
Consumer Federation of America [aimagazine/WinBuzzer, snippet]).

**What it says to the spec.** Read as an engine configuration: the eligibility rule is an
*earned* gate (`InvitationLevel` above `SILENT`, or the new-relationship mute inverted); one
follow-up is `budget_per_day=1`; stop-on-no-reply is `Reaction.IGNORED` lowering the invitation.
Every piece exists in `haloysius.attunement`. Two lessons: first, the shape is right and it is
already ours; second, **the mechanism did not protect the feature from criticism, because the
objective was the problem.** C-3 (not reachable by persuasion) and C-5 (per-consumer ceilings)
are necessary; §8.8 argues the *objective* must also be visible on the surface.

### 2.5 ChatGPT Pulse — the biggest proactive LLM launch, delayed in three months

[P5, verified: Newton, Platformer, 25 September 2025; the pause via WSJ-sourced reports,
snippet S3.]

Pulse "proactively does research to deliver personalized updates based on your chats, feedback,
and connected apps like your calendar," as a morning briefing. Control was by curation ("letting
it know what's useful and what isn't"), not by frequency. Newton's assessment: "a notable step
toward … personalized tools that work for you continuously in the background," with the explicit
caveat that it parallels "another feed to scroll." On 1 December 2025 OpenAI declared a "code
red" and, per the WSJ memo, "work on … a more proactive and personalized version [of the]
ChatGPT assistant called Pulse has been delayed" to concentrate on the core product [S3].

**What it says to the spec.** Not a user-harm outcome — a priority outcome. Proactive features
are expensive, are judged against "another feed," and are the first thing cut when the core
needs attention. The design implication is that the presence feature must be *cheap to run in
shadow indefinitely* and must not depend on a model call per impulse — which `CD-3` and the
deterministic admission gate already ensure.

### 2.6 Google Now — proactive as a place you go

[S2, snippet: Wikipedia; Android Central; How-To Geek.]

Now cards (2012) "proactively delivered information … in the form of informational cards" —
flights, packages, commute — in "a feed of these cards." It had "loyal fans," "a branding
problem" against named assistants, and was absorbed into Assistant and then "Feed"
(2016–2017).

**What it says to the spec.** Google Now was proactive **without being push**: the cards waited
on a surface you swiped to. That is `PULL` presence, and it was well liked. It supports the
spec's claim that a great deal of "proactive" value is deliverable at the `PULL` and `AMBIENT`
channels with no interruption cost — which is why the curve's lower half is mostly channel
routing, not suppression.

### 2.7 The Sims — autonomy that never negates the player

[P6, verified: Brown, GMTK, 30 June 2023.]

Sim autonomy is utility-driven: objects "advertise" what they satisfy; Sims choose top-scoring
actions with randomisation "preventing robotic predictability." The governing design rule is
borrowed from improvisational comedy — **"yes, and"** — so that "autonomous systems build on
player actions rather than contradict them." Sims "will" address needs and act on traits; they
"won't" autonomously quit jobs, romance random Sims, or break established relationships, because
those "would undermine player narrative control." The system "should always try to maintain the
consistency of the player's story." The user-facing control is a single toggle (Off / Full in The
Sims 4; Off / Low / High in earlier titles [Fandom, snippet]).

**What it says to the spec.** "Yes, and" is the missing *stance* rule for the top rungs. A
`SPONTANEOUS` or `ASSOCIATION` utterance at 8–10 must build on what the person is doing — the
subject of the current thread, the task in the terminal, the thing they said an hour ago — and
must never redirect, contradict or open an unrelated line. That is a one-paragraph addition to
the `[ATTUNEMENT]` block for those classes (§8.2), and it is also the difference between a
companion and the zombie-with-more-output from pass 1 §1.3.

### 2.8 Gmail Priority Inbox — ranking, a per-user threshold, and explicit marks

[P7, verified: Aberdeen, Pacovsky & Slater, NIPS 2010 Workshop on Learning on Cores, Clusters
and Clouds; PDF extracted locally.]

Importance is "the probability that the user will perform an action on that mail" within a
window. The design decision that matters here, quoted in full:

> "We treat the problem as ranking rather than classification because tuning the threshold
> quickly is critical for user perceived performance. It is difficult to algorithmically
> determine the threshold that will make a given user happy … there is a large variation between
> user preferences for volume of important mail, which can not be correlated with their actions.
> Thus, we need some manual intervention from users to tune their threshold. When a user marks
> messages in a consistent direction, we perform a real-time increment to their threshold."

The threshold is tuned so that "our false negative rate is 3–4 times the false positive rate" —
deliberately biased toward under-flagging, because "users read mail they acknowledge is not
important." Error on user-marked mail: global model **45 %** → per-user models **38 %** → per-user
models plus per-user thresholds **31 %** (160k markings). Behavioural outcome: Priority Inbox
users "spent 6 % less time reading mail overall, and 13 % less time reading unimportant mail."

**What it says to the spec.** Three things. (i) A per-user *threshold*, distinct from the
per-user *model*, was worth 7 points on its own — the personal band matters. (ii) The threshold
moved on **explicit marks only**, in real time, in the direction of consistent marking — this is
the safe, proven form of M5 and the shape any v2 learning should take (§8.4). (iii) The
deliberate FN:FP asymmetry of 3–4:1 is a calibration precedent for the FP budget per rung
(spec §18): under-speaking is the cheaper error and should be tuned as such.

---

## §3 Budget as a control, at scale

### 3.1 Pinterest — per-user volume, volume down, engagement up

[P8, verified: Zhao, Narita, Orten & Egan, KDD 2018, abstract via kdd.org; the Pinterest
engineering post and ACM page returned 403.]

"A novel machine learning approach to decide notification volume for each user such that long
term user engagement is optimized," in two steps: utility prediction (a model predicts the value
of the next notification to this user) and budget allocation (the optimal weekly budget per
user under a global volume constraint). Deployed mid-2017. Outcome: "significantly reduced
notification volume and improved CTR of notifications and site engagement metrics compared with
the previous machine learning approach."

### 3.2 LinkedIn — Air Traffic Controller

[P9, verified: Shi & Fuad, LinkedIn Engineering, 1 March 2018.]

ATC is "the ultimate decision maker for notifications sent to our members," over a billion
requests a day, deciding per member: **volume** (against history and preferences), **channel**
(email / SMS / desktop / in-app / push, "based on device availability, member settings, and
predictive models for engagement and disable rates"), **delivery time** ("when members are most
likely to engage"), **aggregation** ("group these reminders together and send them in one
email"), and **filtering** of duplicates and expired items. Outcomes: "cut member complaints in
half"; "double digit increases in member engagement site-wide."

### 3.3 Duolingo — one notification a day, chosen by a bandit

[P10, verified: Yancey & Settles, KDD 2020; PDF extracted locally.]

The problem is *content* selection under a fixed cadence — one daily reminder — not volume. Two
complications make textbook bandits unsuitable: "'Fresh' templates (which have not been recently
seen) tend to have higher impact on user behavior … Otherwise, the bandit will converge to using
the same template for a given user day after day, which will get repetitive, desensitize users,
and fail to improve engagement in the long run"; and conditional eligibility ("sleeping arms").
The Recovering Difference Softmax algorithm adds a **recency penalty**; offline, reusing the last
template "hurts reward by 0.5 %." Online A/B after two weeks: **DAU +0.5 %, lessons +0.4 %, new-
user recurring retention +2 %**; re-evaluated against a holdout five months later. Reward is
defined as a lesson completed within two hours of the notification.

**What §3 says to the spec, together.**
- M2 is validated as an axis by two of the largest deployments in existence, and the direction of
  the effect — *fewer* interruptions, *more* engagement — refutes the use-it-or-lose-it worry in
  pass 1. `budget_per_day` as a ceiling (spec §12, C-2) is the right framing.
- ATC's five decisions are the spec's five axes: volume (budget), channel, delivery time
  (patience), aggregation (a digest is `SCHEDULED`), filtering (admission + recency). The
  correspondence is close enough that ATC is a useful sanity check on the vector's completeness.
- Duolingo quantifies the zombie effect: **repetition costs 0.5 %** even in one-line reminders.
  The engine has `W_QUIET_PERIOD` for *silence after a run of speech* but no *topic-recency*
  penalty; §8.3 proposes one for `ASSOCIATION` and `SPONTANEOUS`.
- All three learn from **logged outcomes offline first** (Pinterest's utility model, Duolingo's
  offline replay before the A/B). The shadow log is the family's equivalent and the spec's
  §7-style replay is the same method.

---

## §4 Embodied presence: what the robots learned

### 4.1 Jibo — proactive greeting valued, "social catalyst"

[P11, verified: Breazeal, Ostrowski, Singh & Park, MIT Media Lab, March 2019; the Science
Robotics 2024 follow-up (70+ parent–child pairs, 1–2 months) is S5, snippet — both the journal
page and PubMed were unreachable.]

Jibo "could identify and turn to attend to its users and interact proactively, unlike Amazon
Alexa, which required activation." In a month-long home study with older adults, "sustained
usage centred on social elements"; participants "showed notably higher engagement with Jibo
compared to the digital assistant," described it as "a really smart pet who can talk," and valued
its potential as a "social secretary — prompting you to get people together." In an assisted-
living deployment it "acted as a social catalyst, significantly increasing resident congregation
in common areas"; "human-human interactions increased substantially by the study's conclusion."

### 4.2 The post-mortem — "its tricks get old quickly"

[P12, verified: Hoffman, IEEE Spectrum, 1 May 2019.]

On Anki, Jibo and Kuri: "this kind of product may be fun to use for a while, but that its tricks
get old quickly." What users wanted and did not get: "follow-ups, cross-conversation references,
and overlapping dialogue — rather than isolated single interactions." Hoffman's diagnosis is
"canned simplicity," his prescription is "storytelling professionals who understand emotional
engagement and structured repetition," and he records that embodiment produced real attachment
("some even cried when robots said goodbye").

### 4.3 The novelty cliff, with numbers

- **Two weeks.** Weiss et al. observed "a decline in attachment levels with a Vector robot after
  just 2 weeks out of a 30-week study" [S4, via the ACM THRI 2025 review; both pages returned
  403].
- **Three sessions.** Children "did not show any interest in the robot anymore after three
  sessions when the robot used repeated behavior"; "children's social responses to the robot were
  drastically reduced by the third session" [P13, Leite et al.].
- **Six weeks.** Nine socially isolated students living with a robot kitten for six weeks: the
  robot "lost its shine" once "all programmed functions" were discovered, and "just kind of
  blended into the rest of my life again" — with the honest confound that "at a certain point,
  we kind of had other stuff to do." The kitten "had no autonomous initiating capabilities"
  [P14, Abendschein, Edwards & Edwards, 2022].
- **Two months.** Sung et al.'s Roomba study: "two months is the time" for adoption to settle
  [P13].

The Leite, Martinho & Paiva survey (IJSR 2013; PDF extracted) states the field's consensus
plainly: "the novelty effect quickly wears off and, after that, people lose interest and change
their attitudes towards the robots." Its factors for sustaining engagement, from §4:
**continuity and incremental behaviours** (routine behaviours such as greetings and farewells,
plus gradual variety), **affective interactions and empathy** (understanding the user's affective
state and reacting), memory and adaptation.

**What §4 says to the spec.**
- The shadow-review gate in spec §17 is **one week**. The cliff is at two. Move the gate to
  **two weeks minimum**, and instrument week 2–3 specifically (§8.5).
- Hoffman's "follow-ups, cross-conversation references" is `OPEN_LOOP` and `ASSOCIATION` named
  by a user population that did not get them. F5 stands: presence above the event-driven rungs
  is worth building only once those classes have producers. Until then the persona is Vector.
- Leite's "routine behaviours (greetings and farewells)" is a cheap, evidence-backed
  `SCHEDULED`-class behaviour — arrival and departure acknowledgments — that the engine already
  has hooks for (`Activity.ARRIVING`, `DEPARTING`; `ResumeCondition.ON_ARRIVAL`).
- Jibo's "social secretary" is `SUBJECT_LINKED` about *people*, and it was the valued behaviour.

---

## §5 The academic record on proactive agents, 2021–2026

### 5.1 Codellaborator — presence indicators reduce disruption (CHI 2025)

[P15, verified: Pu, Lazaro, Arawjo, Xia, Xiao, Grossman & Chen; DOI 10.1145/3706598.3713357;
arXiv 25 February 2025.]

Within-subject, N=18, three conditions of increasing AI salience: prompt-only; a proactive
agent; the proactive agent with **presence and context** (Codellaborator). Findings: proactive
agents "increased efficiency compared to prompt-only" but "incur workflow disruptions"; the
presence indicators and interaction context "alleviated disruptions and improved users'
awareness of AI processes"; users wanted "better control over when and how AI assistance
triggered"; the authors "underscore the need to adapt proactivity to programming processes."

*To the spec:* the single cleanest user-study result for M6. An ambient indicator of the agent's
attention — not more speech — is what reduced the cost of proactivity. The presence pill and the
"I have a thought" indicator (spec §14 delivery, §15) are grounded here.

### 5.2 "Having Lunch Now" — scheduled check-ins and their failure mode (CHI 2026)

[P16, verified: Abbas, Wohn, Jagtap, Rho, Kim & Lee; arXiv 2509.24073; DOI
10.1145/3772318.3790957.]

Twelve participants, fourteen days, a coaching agent that initiated check-ins "twice per day —
once in the morning to facilitate planning and once in the evening to support self-reflection";
336 conversations, 3,181 turns. Four response patterns: accepting, negotiating, reporting
progress, and "resisted or disengaged." Three named problems: **"rigidity, premature
turn-taking, and overpromising."**

*To the spec:* our `SCHEDULED` rung is a morning report. The failure mode of scheduled
proactivity is not volume — it is inflexibility. §8.3 proposes that a `SCHEDULED` impulse the
person defers or skips lowers its own priority for the next cycle, and that the report's stance
block forbids promising follow-through the system cannot track (which, until `OPEN_LOOP` exists,
is any follow-through).

### 5.3 LlamaPIE — a small model decides *when*, a large one decides *what* (ACL 2025 Findings)

[P17, verified: Chen, Batchelder, Liu, Smith & Gollakota; arXiv 2505.04066.]

An in-ear assistant that "operates in the background, anticipating user needs without
interrupting conversations," with "a small model that decides when to respond and a larger model
that generates the response," constrained to "concise responses that enhance conversations,"
on-device. User study: "strong preference for the proactive assistant over both a baseline with
no assistance and a reactive model."

*To the spec:* the two-stage split — a cheap deterministic-or-small decider for *whether/when*,
the expensive model only for *what* — is the architecture the spec already has (admission +
policy + `CD-3`, then the persona phrases). It is also the only shape that survives §2.5's
lesson about cost.

### 5.4 How people actually interrupt (2021)

[P18, verified: Edwards, Janssen, Gould & Cowan; arXiv 2106.02077.]

Elicited natural spoken interruptions from people engaged in complex tasks. "People interrupted
sooner when interruptions were urgent"; "varied phrasing and delivery of interruptions to reflect
urgency"; some "employed advance warning rituals before interrupting, though most rarely did so";
timing balanced "speed and accuracy," drawing on "task-related cues."

*To the spec:* severity should change *patience* and *register*, not only admission — which
`W_SEV` and the per-severity thresholds already do; the "advance warning ritual" is `ASK_FIRST`
delivered as a peripheral signal (§8.6).

### 5.5 Communication Policy Evolution — neither extreme wins (2026)

[P19, verified: Ma et al., 13 authors; arXiv 2606.14314, 12 June 2026.]

A communication policy is "how and when LLM agents should interact with users"; CPE evolves it
"through rollout and prompt-level evolving" without model modification. Finding: "neither
extreme is optimal — agents must calibrate communication frequency contextually, balancing the
costs of frequent interaction against information asymmetry."

*To the spec:* a scalar presence level is a *prior* on that calibration, not the calibration.
The curve sets the ceiling; receptivity and the band do the contextual part. Consistent with the
spec; no change.

### 5.6 The field has no shared definition (2026)

[P20, verified: Zargham, Ferguson, Sin, Munteanu & Kuzminykh; arXiv 2606.25149, workshop paper,
23 June 2026.]

"Fundamentally different behaviors — from simple reminders to advanced AI systems — are labeled
proactive." Existing design and evaluation approaches "are largely rooted in reactive interaction
paradigms." The challenge dimensions named: **"timing, appropriateness, user control,
transparency, and trust."**

*To the spec:* the `ImpulseClass` vocabulary is a concrete answer to the definitional gap, and
the five dimensions map onto the spec's axes (patience; admission; the slider; the suppression
log; shadow-first). Worth citing in the spec's problem statement.

---

## §6 Ambient and peripheral precedents

### 6.1 Attentive User Interfaces — the 2003 statement of "admitted but ambient"

[P21, verified: Vertegaal, *Communications of the ACM* 46(3):30–33, March 2003; PDF extracted.]

The premise: "user attention is a limited resource that must be conserved," and devices
"bombard users with requests for attention, regardless of the cost of their interruptions." The
proposal, quoted because it is the spec's mid-rung in 2003 language:

> "User interface designers and engineers are beginning to design computing devices that
> negotiate rather than impose the volume and timing of their communications with the user."

> "Instead of immediately taking the foreground — interrupting the ongoing activity of the user —
> AUIs can progressively signal their requests for attention. Initially this may happen through
> a channel peripheral to the user's activity. AUIs may then wait for user acknowledgment —
> provided through an attentive input device — before they take the foreground."

Vertegaal's metaphor is a traffic-light system: sensors predict "future focus," statistical
models set priority, and peripheral displays "negotiate turn-taking." AUIs "need not be fully
predictive" precisely because negotiation absorbs prediction error.

*To the spec:* (i) The 4–5 rung ("admitted but ambient") has direct precedent. (ii) "Wait for
user acknowledgment before they take the foreground" describes an `ASK_FIRST` that is *itself*
delivered ambiently — a question rendered as an indicator state, answered by attention rather
than speech. §8.6. (iii) "Need not be fully predictive" is the argument for why a deterministic
admission gate plus a cheap receptivity estimate suffices: the ambient tier corrects for the
estimate's errors.

### 6.2 Ambient Devices — what earned a place, what did not

[P22, verified: Sall, Everyday Industries, 15 June 2026; Ambient Devices founded 2001 from PARC
calm-tech research.]

The products that worked — the Ambient Orb, the Ambient Umbrella whose handle glows when rain is
forecast, the GlowCap pill bottle — "communicated through changes in color, light, or sound
without demanding active attention" and "earned placement in users' lives through simplicity."
The author's read on the present: "modern smart devices struggle maintaining peripheral
presence; they demand attention aggressively and fail unpredictably, contradicting foundational
ambient design philosophy." Weiser & Brown's principles as restated: minimal attention; inform
without overwhelming; periphery; non-verbal; functional when systems fail; minimum technology;
respect social norms.

*To the spec:* the `AMBIENT` channel's design brief. "Functional when systems fail" is a
requirement the spec's error handling (§17) meets — the indicator must degrade to a stable
state, never to flicker.

---

## §7 Companion outcomes

### 7.1 Usage does not predict loneliness; user profile does (AIES 2025)

[P23, verified: Liu, Pataranutaporn & Maes; arXiv 2410.21596; accepted AIES 2025.]

Survey of 404 regular companion-chatbot users; seven user profiles by cluster analysis. "Usage
does not directly predict loneliness"; ~50 % of loneliness variance is explained by neuroticism,
social network size and *problematic use patterns*. Companions "can either enhance or potentially
harm psychological well-being depending on user characteristics."

### 7.2 Mixed effects at population scale (CHI 2026)

[P24, verified: Yuan, Zhang, Aledavood, Zhang & Saha; arXiv 2509.22505; CHI 2026.]

Longitudinal Reddit data, stratified propensity-score matching and difference-in-differences,
plus 18 interviews. "Mixed effects": increased grief expression, interpersonal focus, loneliness
language, depression markers and suicidal-ideation mentions among users versus matched non-users;
interviews found both emotional validation and "over-reliance and social withdrawal." Framed
through Knapp's relationship-development model (initiation → escalation → bonding).

*What §7 says to the spec.* Neither study isolates *proactive initiation* as a variable — the
harms are associated with use patterns and user traits, not with who spoke first. That is a gap
in the literature, not evidence of safety. Two consequences: (i) C-5's per-consumer ceilings
remain the right instrument, because the risk is in the consumer's population, not in the
mechanism; (ii) the companion consumer's curve should treat `closes_after` and the daily budget
as *primary* safety controls, since "problematic use patterns" is the variable that predicted
harm and those are the two fields that bound use.

---

## §8 What this changes in the v1 spec

Proposals, cross-referenced to the spec. None is applied yet.

**§8.1 — Rung count and the primary control.** Every shipped control in §2 has two to four
positions; Slack's move *to* three produced a five-fold rise in settings engagement. The spec's
six rungs are defensible; eleven visible notches may not be. Proposal: the settings surface
leads with the **six named rungs and their first-person copy** as the primary control, with the
0–10 fine adjustment as a secondary affordance — the "linked control" pattern from pass 1 L14 —
rather than a bare 0–10 slider with copy beside it. Spec §15.

**§8.2 — "Yes, and" as a stance rule for the top rungs.** From The Sims [P6]: `SPONTANEOUS` and
`ASSOCIATION` utterances must build on the person's current subject, task or recent statement,
and must never redirect, contradict or open an unrelated line. Add to the `[ATTUNEMENT]` block
rendered for those classes; add a conformance vector. Spec §10, §18.

**§8.3 — Two anti-repetition rules.** From Duolingo [P10] and "Having Lunch Now" [P16]:
(a) a **topic-recency gate** — an `ASSOCIATION`/`SPONTANEOUS` impulse whose topic was raised
within N days is not admitted (a new suppression key, `presence:recent_topic`); (b) a
**deferred-schedule rule** — a `SCHEDULED` impulse the person skips or defers lowers its own
priority for the next cycle rather than repeating unchanged. Spec §10, §16.

**§8.4 — Explicit marks only, as the v2 learning contract.** From Gmail [P7]: if a per-user
adjustment is ever added, it moves a **per-class band offset** in real time on **explicit,
consistent reactions only** (`ENGAGED` / `DISMISSED` from a person), never on inferred silence.
Record this as the shape of M5 so nobody builds the inferred version. Spec §3 (non-goals) gets a
forward pointer; DECISIONS row 7 proposed.

**§8.5 — Move the shadow-review gate to two weeks and instrument the cliff.** From §4.3: the
novelty decline lands at two weeks. Spec §17's one-week gate is too early to see it. Proposal:
two weeks minimum, and the review reads week 1 versus week 2 reaction rates per class
specifically. Spec §17, §19.

**§8.6 — Ambient expiry and an ambient ask.** From Lumière's "time out with a gentle apology"
[P1] and Vertegaal's "wait for user acknowledgment before they take the foreground" [P21]:
(a) an `AMBIENT` indicator that is not acknowledged within `patience_s` **expires** to `PULL`
rather than persisting; (b) `ASK_FIRST` on a class whose channel ceiling is `AMBIENT` is rendered
as an indicator state, not as a spoken question. Spec §11, §14.

**§8.7 — Routine arrival and departure acknowledgments as a `SCHEDULED`-class behaviour.** From
Leite et al. [P13]: "routine behaviours (greetings and farewells)" are a named long-term
engagement factor, and the engine already has `ARRIVING`/`DEPARTING` and `ON_ARRIVAL`. Cheap,
grounded, and it gives the low rungs something to *be* besides silent. Spec §14 classification;
Halbert curve.

**§8.8 — Make the objective visible.** From Meta [P4]: a correct mechanism with a retention
objective was criticised for the objective. Proposal: the settings surface states, in the
system's own voice, what the presence control is *for* — and the preview (spec §15) shows what
was **held**, not only what was said, so the user can see the system choosing silence. This is
cheap, it is the transparency dimension from [P20], and it is the difference between our feature
and Omni's.

**§8.9 — Cite the definitional gap.** Spec §1 should cite [P20]: `ImpulseClass` is the
family's answer to "fundamentally different behaviors … are labeled proactive."

---

## §9 Sources

### 9.1 Fetched and verified on 2026-09-16

| Ref | Source | Method |
|---|---|---|
| P1 | Horvitz, *Lumiere: Bayesian Reasoning, User Modeling, and Automated Assistance* (project page) | page fetched |
| P2 | Coronel & Kannan, *How Slack Rebuilt Notifications*, Slack Engineering, 19 Mar 2026 (upd. 16 Apr 2026) | page fetched |
| P3 | Apple, `UNNotificationInterruptionLevel`, developer documentation | page fetched |
| P4 | Bellan, *Meta has found another way to keep you engaged: chatbots that message you first*, TechCrunch, 3 Jul 2025 | page fetched |
| P5 | Newton, *ChatGPT develops a Pulse*, Platformer, 25 Sep 2025 | page fetched |
| P6 | Brown, *The Genius AI Behind The Sims*, GMTK, 30 Jun 2023 | page fetched |
| P7 | Aberdeen, Pacovsky & Slater, *The Learning Behind Gmail Priority Inbox*, NIPS 2010 Workshop on Learning on Cores, Clusters and Clouds | PDF extracted locally |
| P8 | Zhao, Narita, Orten & Egan, *Notification Volume Control and Optimization System at Pinterest*, KDD 2018 | abstract via kdd.org |
| P9 | Shi & Fuad, *Air Traffic Controller: Member-First Notifications at LinkedIn*, LinkedIn Engineering, 1 Mar 2018 | page fetched |
| P10 | Yancey & Settles, *A Sleeping, Recovering Bandit Algorithm for Optimizing Recurring Notifications*, KDD 2020 | PDF extracted locally |
| P11 | Breazeal, Ostrowski, Singh & Park, *Designing social robots for older adults*, MIT Media Lab, Mar 2019 | page fetched |
| P12 | Hoffman, *Anki, Jibo, and Kuri: What We Can Learn from Social Robots That Didn't Make It*, IEEE Spectrum, 1 May 2019 | page fetched |
| P13 | Leite, Martinho & Paiva, *Social Robots for Long-Term Interaction: A Survey*, Int J Social Robotics, 2013 | PDF extracted locally |
| P14 | Abendschein, Edwards & Edwards, *Novelty Experience in Prolonged Interaction*, Frontiers in Robotics and AI, 2022 | page fetched |
| P15 | Pu et al., *Assistance or Disruption? … Proactive AI Programming Support*, CHI 2025 (DOI 10.1145/3706598.3713357) | arXiv page fetched |
| P16 | Abbas et al., *"Having Lunch Now"*, CHI 2026 (arXiv 2509.24073; DOI 10.1145/3772318.3790957) | arXiv page fetched |
| P17 | Chen et al., *LlamaPIE*, ACL 2025 Findings (arXiv 2505.04066) | arXiv page fetched |
| P18 | Edwards, Janssen, Gould & Cowan, *Eliciting Spoken Interruptions…*, arXiv 2106.02077, 2021 | arXiv page fetched |
| P19 | Ma et al., *Communication Policy Evolution for Proactive LLM Agents*, arXiv 2606.14314, Jun 2026 | arXiv page fetched |
| P20 | Zargham et al., *Proactive Systems in HCI and AI*, arXiv 2606.25149, Jun 2026 (workshop) | arXiv page fetched |
| P21 | Vertegaal, *Attentive User Interfaces*, CACM 46(3):30–33, Mar 2003 | PDF extracted locally |
| P22 | Sall, *Designing for the Periphery: Lessons from Ambient UX History*, Everyday Industries, 15 Jun 2026 | page fetched |
| P23 | Liu, Pataranutaporn & Maes, *Chatbot Companionship…*, AIES 2025 (arXiv 2410.21596) | arXiv page fetched |
| P24 | Yuan et al., *Mental Health Impacts of AI Companions…*, CHI 2026 (arXiv 2509.22505) | arXiv page fetched |

### 9.2 Snippet or secondary only — NOT verified at the primary

| Ref | Claim | Why unverified |
|---|---|---|
| S1 | Alexa "By the way" cannot be reliably disabled; Brief Mode does not suppress it; "stop by the way" is temporary | Amazon's Brief Mode help page returned 503; rests on TechHive, PCWorld, Tom's Guide, Gear Patrol, TechCrunch (2018) |
| S2 | Google Now history and reception | Wikipedia / Android Central / How-To Geek snippets |
| S3 | Pulse delayed under the December 2025 "code red" | WSJ memo as reported by MacRumors, Slashdot, Search Engine Land; the memo itself not seen |
| S4 | Vector attachment declined after 2 of 30 weeks (Weiss et al.) | quoted from the ACM THRI 2025 review's snippet; both the review and the primary returned 403 |
| S5 | Science Robotics 2024 Jibo deployment, 70+ parent–child pairs, 1–2 months | journal page 403; PubMed cookie wall |
| S-Clippy | The Bayesian trigger was judged "too cautious" and swapped so the assistant would "pop up more often"; single-word triggers | blog and secondary accounts; **the substitution itself is verified at P1**, the motive and the single-word detail are not |

### 9.3 Attempted, not retrieved

Pinterest engineering post and ACM page (403; abstract obtained via kdd.org instead); Semantic
Scholar Pinterest entry (empty); ACM THRI *Long-Term Interactions with Social Robots* (403);
Science Robotics *Social robots as conversational catalysts* (403, PubMed cookie wall); Amazon
Brief Mode help (503).

---

## §10 Discrepancies and cautions

**D1 — Clippy's motive.** That the Office team replaced the Bayesian trigger *because it was too
cautious* comes from secondary accounts. Horvitz's page verifies the replacement and the
research team's concern, not the reason. Cite the replacement, not the motive.

**D2 — Alexa's controls.** All of §2.3 rests on secondary reporting. The claim that "By the way"
has no durable off-switch is consistent across five sources over several years, which is
suggestive; it is not primary.

**D3 — Meta's rules** are from leaked training documents as reported by TechCrunch. They are
Meta's stated policy at the time of the leak, not observed behaviour.

**D4 — The Sims' "yes, and"** is a design principle as recounted by a journalist from Maxis
interviews, not a published design document.

**D5 — §7's companion studies do not isolate proactive initiation.** Neither P23 nor P24 tests
"the bot spoke first" as a variable. The absence of an identified harm from initiation is not
evidence of its safety.

**D6 — Duolingo's outcome is a content-selection outcome.** The cadence was fixed at one per
day; the +0.5 % DAU is from *which* reminder, not *whether*. It supports the recency penalty
(§8.3), not any claim about volume.

**D7 — Pinterest's numbers are qualitative in the abstract.** "Significantly reduced volume,"
"improved CTR" — the magnitudes are in the paper body, which was not retrievable.

**D8 — Codellaborator is N=18, one domain.** The presence-indicator finding is the best available
for M6 and it is a small programming-tool study; it has not been replicated for a household
persona.

---

*Pass 2 proposes nine amendments (§8) and validates the v1 spec's central structure — admission
separate from channel, hard off off the slider, budget as ceiling, thresholds derived, shadow
first — against independent production evidence. The remaining prerequisite is unchanged from
pass 1: nothing above the event-driven rungs is worth shipping until `OPEN_LOOP` and
`ASSOCIATION` have producers, because every embodied product that lacked them was abandoned at
week two.*
