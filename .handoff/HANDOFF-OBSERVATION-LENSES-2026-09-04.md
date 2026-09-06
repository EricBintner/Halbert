# HANDOFF: Observation Lenses — Review, Counter-Proposal, and Revised Plan

**Date**: 2026-09-04 (rev 1) · **Revised**: 2026-09-05 (rev 2)
**Status:** DRAFT — rev 2.1 (2026-09-05, reconciled with branch 1 as shipped). Decided (`DECISIONS.md`, 2026-09-05): CD-1, CD-2, CD-3, CD-4, CD-5 (sub-question deferred, research brief opened), CD-6, CD-7, CD-11. Open: CD-8, CD-9, CD-10. Branch 1 landed on `fix/observation-sink`; branch 2 may be cut
**Rev 2.1 changes**: §2.3 R16–R17 (two rev 2 claims the code corrected); A2's row contract (`title`, `severity`, the occupancy guard); A5 counts `end`; CD-11's noun through §6, §8, §9 C3, §10 D3, §11; B7 as shipped; §13 marks; §14 branch 1 as shipped; §15
**ROADMAP rows:** Track A → `MIND-1` (`C4-04`) and `STATE-1` (`J2-2`, citable observation ids), with `CFG-1` (`A2-02`) for the store path; B1–B3 → `SKILL-1` (row added 2026-09-05); B4–B7, C1b, C2, C3 → §4 Next (CD-1 decided 2026-09-05; a `LENS-1` row is opened only after C1a has shipped and a week of Noticed sections has been read)
**Supersedes**: `.handoff/HANDOFF-NERD-SCOPES-DYNAMIC-PERSONALITY-2026-09-04.md` (referred to below as "the original")
**Verified against**: main `44fc501e`. Line numbers are as of that commit; this tree moves fast, so treat function names as the durable anchor.

**Primary finding (rev 1, corrected in rev 2)**: the original proposes building
subsystems that already exist in this tree. Two of them (the skills subsystem;
the timeline ledger) exist, are tested, and are **not wired**. Two more
(a recurrence detector; a salience lifecycle) have close analogues that are
not the thing. The work is mostly connection, but rev 1 understated the
connecting that is needed: none of the three stores it inventoried is
constructed by production code on any variant.

**What rev 2 changed.** Rev 1 was itself reviewed against the code by a
155-agent pass (13 verifiers and gap-finders, three adversarial skeptics per
high finding, one per medium, then a synthesis). 146 claims were confirmed.
111 findings were raised; 82 survived refutation and are folded in below.
The audit trail is §2.3. The thesis (§4) stands. Five load-bearing mechanism
claims were wrong and are corrected; the tracks gain an owner task (A0), an
ingestion-time sink, security invariants, a spine mapping, and ten founder
decisions (§13) that gate everything past the first two branches.

---

## 0. How to read this document

Section 1 is the summary and the decisions being asked for.
Section 2 is the verification record — the original's claims checked against
the code (2.1, 2.2), and rev 1's own claims checked the same way (2.3).
Section 3 is the three defects. Two are live bugs independent of this plan.
Section 4 is the conceptual reframe, which is the part worth arguing about.
Section 5 is the inventory of machinery to reuse, corrected.
Section 6 is the revised architecture.
Sections 7–9 are the tracks, task by task, with the spine row each serves.
Section 10 records design decisions and why the alternatives lost.
Sections 11–12 are invariants and the trim list.
Section 13 is the ten core decisions for the founder, with recommendations.
Section 14 is sequencing: the branches, their order, and what "done" means.
Section 15 is the verification checklist.

---

## 1. Executive summary

### 1.1 What the original got right

The premise is sound and worth building. Halbert can control *how* it speaks
(demeanor, communication style, Big Five traits, voice presentation) and *what
it may touch* (tool safety, approval gates). It has no control over **what it
finds worth remarking on**. That is a real gap, and the original names it
correctly.

The original is also right to reject fine-tuned "personality models" for an OS
companion, and right that the steering layer must be human-readable files on
the user's disk rather than opaque weights. Both conclusions survive review
unchanged, and both are the founder's own words in the original (":31 *you
don't want the OS playing tricks on you*").

The original also carries a founder requirement of record that this plan
must not lose (original :354–355): *learn from the user, keep long-term
memories of favourites and topics, use them in discussion in the short term,
keep compressed memories recallable later, including downloaded research
stored in RAG.* Rev 1 dropped that half silently. Rev 2 carries it as D9 and
§13 CD-5.

### 1.2 What the original got wrong

It treats this as a greenfield subsystem. It is not. Corrected table:

| The original proposes building | What exists |
|---|---|
| `haloysius/scopes/` — `.md` parser, loader, matcher, tier composer | **Exists, unwired.** `halbert_core/skills/` — 1,055 lines, 5 modules, 8 built-in skills, 3 test files (§3.1) |
| A salience decay engine with promotion/demotion | **Analogue only.** `home/behavior.py` `BehaviorStore` is a household-pattern store keyed `UNIQUE(pattern_type, person, entity_id, action, day_of_week, hour, minute)` with a confidence loop and `degrade_stale_patterns()` (7-day interval; the "four weeks" in its docstring is stale). No tier, no per-lens activation, nothing keyed by skill name. D6's lifecycle is new work. |
| Bottom-up topic discovery from chat (`UserKnowledge`, `advance_turn()`) | **Replaced, not found.** This plan replaces it with recurrence over the timeline ledger (D8). `PatternInferrer.infer_from_timeline()` is the pattern for that, not the implementation: it reads only `ha_state_change` and `occupancy_change` rows into 15-minute time slots and cannot count "this van, three times" (§2.3 R4). A5 adds the query. |
| (rev 1 also credited the original with proposing an observation ledger; it never does — that row is this plan's own introduction of `TimelineStore`, §5.1) | |

The original reverse-engineers `open-claude-code` across a full page for prior
art and never notices Halbert's own skills subsystem, which is strictly more
capable than the one it studied (`extends` inheritance, aliases, declarative
safety constraints, per-skill tool allowlists; Claude Code's skills have none).

### 1.3 What is actually blocking

Three defects, all verified, all small in code and large in effect:

1. **The skills subsystem is dark.** `IntakePipeline` is constructed without a
   `skill_matcher`, so no skill ever activates; `ComposedSkills.prompt` has no
   consumer; declared skill safety binds nothing; the composed tool allowlist
   is read nowhere. (§3.1)
2. **Observations are computed and discarded, and the drain is per turn.**
   Both event mappers end in a `_add_observation()` that probes two attributes
   `PersonaCognition` does not have. The only drain of the mapper queues is
   the chat turn's cognition tick; between turns both queues silently drop
   past 500. Five of six Frigate emotion writes also fail silently on a
   category that does not exist. (§3.2)
3. **The timeline ledger and the pattern inferrer are complete, tested, and
   constructed by nothing** — on any variant. Rev 1 called this "trapped
   behind the home variant"; there is no variant gate in either module and
   no production construction site. The fix is an owner, not a move. (§3.3)

### 1.4 The decisions being asked for

Per ROADMAP rule (1) this document does not say now/next; it maps onto rows.

| Work | Row | Note |
|---|---|---|
| A0–A2c (store owner, ingestion sink, normalisation) | `MIND-1` (`C4-04` "Eyes do not feed the mind"), `CFG-1` (`A2-02` path resolver) | closes the ledger-has-no-writer half of `C4-04` |
| A3 (state vs event routing into `StateStore`) | `MIND-1`, citing `MEM-02` | |
| A4 (world rows into the pre-PLANNING block with ids) | `STATE-1` (`J2-2`) | STATE-1 owns the block; A4 is one input to it |
| A5 (recurrence query) | `MIND-1` substrate | consumed by C1a and C2 |
| B1–B3 (wire matcher, inject prompt, bind safety) | proposed new row `SKILL-1`; otherwise `KNOW-1` + `TRUST-1` (`C3-14`) | B1 is the DEFECT-1 fix, not knowledge work |
| B4–B6, C1b, C2, C3 (lens schema and load path, dial, gate, voiced report, remarks, UI) | none today → §4 Next (CD-1 decided); `LENS-1` opens after C1a has shipped and a week of Noticed sections has been read | B7 shipped early on branch 1: the built-in lens and the `kind` field, inert until `active_lens` exists |
| C0, C1a (report passes the gate at Balanced; deterministic Noticed section) | `ATTN-2` (`C2-10`) | existing open spine item |
| D9 (user favourites → memory_v2; research ingestion) | `MEM-01` for the writer; deferral otherwise | must be carried or deferred explicitly, never dropped |

Two asks, both answered 2026-09-05: **(a)** the row map for Track A and B1–B3
is accepted (`SKILL-1` added to ROADMAP §3), and CD-4, CD-5 and CD-6 are
decided, so branches 1 and 2 can start; **(b)** lenses (B4–B7 and Track C)
stay in §4 Next with a named bullet until C1a has shipped and a week of
Noticed sections has been read. The reframe in §4 is accepted as the basis
for D9 and the trim list.

---

## 2. Verification record

### 2.1 The original's claims — confirmed

| Claim | Verified at |
|---|---|
| `BeingConfig` holds Big Five, tone descriptors, speech patterns, directives, archetype id, and a `custom_personality_prompt` escape hatch | `config/being_config.py` ~:190 |
| `generate_personality_section()` renders it, with a documented first-match-wins pipeline | `persona/personality_prompt.py` ~:72 |
| Five communication styles (`concise`, `balanced`, `detailed`, `analytical`, `casual`) | `persona/archetypes.py` ~:370 |
| Settings has a `being` tab | `dashboard/frontend/src/pages/Settings.tsx` — labelled "Identity & Voice"; the tab body is `components/settings/tabs/BeingTab.tsx` |
| `advance_turn()` runs a six-phase lifecycle with the stated decay constants | `Haloysius/src/haloysius/persona/cognition_tick.py:44-46` |
| `UserKnowledge` / self-editing persona exists | `Haloysius/src/haloysius/persona/self_editing.py` |
| `StateStore` enforces non-fabricated provenance | `continuity/state_store.py` — `reason` and `actor` are keyword-only with no default |
| `PromptBuilder` accepts `personality_section` and wraps it in `<personality>` | `prompts/builder.py` ~:99, :135 — **true but not on the chat path** (see 2.2). Nobody should wire a per-turn seam into `build_prompt`. |

### 2.2 The original's claims — wrong, or unverifiable as stated

**`UnifiedPromptPipeline` is not the shipped assembly path.** Its own
docstring (`Haloysius/src/haloysius/context/prompt_pipeline.py:9-12`) says the
chat handlers still assemble by concatenation and adopting the pipeline is a
separate change. Halbert does not use it at all. **Phase 2 of the original
would wire flavor into a seam nothing reads, in a repo that is not the
consumer.**

**How Halbert actually builds a chat prompt** (rev 1 had this wrong too): the
turn assembles context through `context/assembler.py` and builds the planning
and response prompts with `AgentPromptBuilder.build_planning_prompt` /
`build_response_prompt`; the identity block is prepended in
`AgentStateMachine._build_messages` (`agents/state_machine.py:1605-1606`,
`content = f"{identity}\n\n{prompt}"`). `PromptBuilder.build_prompt` is
reached on the chat path only through `build_system_prompt`, which nothing
calls; its one live consumer is `scheduler/autonomous_tasks.py`. The route
hands a `PromptBuilder` into the agent, which is why the dead path looks live.

**`keyword_injection.py`** — the original names the file without a path. It is
`Haloysius/src/haloysius/memory_v2/keyword_injection.py` (`KeywordEntry` :24,
`KeywordInjector` :139), exported from `memory_v2/__init__.py`, consumed at
runtime by `keyword_loader.py`, `retrieval_utils.py`, `memory_pipeline.py` and
`persona/chara_card_v3.py`. Halbert imports none of it, nor `UserKnowledge`,
so the original's discovery path rests on Haloysius machinery Halbert does not
consume. Comparison: `SkillMatcher` scores one message with whole-word hits;
`KeywordInjector` scans the last N messages (`default_scan_depth = 5`) with
secondary-key AND, regex, priority and a token budget. This plan's D7 decides
current-turn-only detection, so `KeywordInjector` stays out of Halbert;
multi-turn re-wake would be a new Halbert seam, not a free reuse.

**The original's token arithmetic does not close.** §4.1 allows Tier 1 at
60–100 tokens × 2 plus Tier 2 at 120–200 (max 400); §9 invariant 4 caps all
scopes at 250; the §4 diagram sums to ~310; the schema default is
`token_budget: 120` per scope. No number is consistent with the others.

**The salience formula does not close.** `β` is used and never assigned; `λ`
is given in two units ("0.05 per turn; 0.1 per day") inside a single `Δt`;
six tunable constants have no evaluation method.

### 2.3 Rev 1's own claims — corrected in rev 2

Everything below was raised by the review of rev 1 and confirmed by at least
two independent readers of the code. Each row names the section it changed.

| # | Rev 1 said | The code says | Changed |
|---|---|---|---|
| R1 | "`TimelineStore` and `PatternInferrer` are reachable only in the home variant" | No variant check exists in `home/timeline.py` or `home/behavior.py`. A repo-wide search for `TimelineStore(`, `BehaviorStore(`, `PatternInferrer(`, `HomeCognitiveLoop(` outside tests returns nothing. `home/__init__.py:13,15` are the only non-test importers. | §3.3, A0, A1 |
| R2 | "`populate_cognition()` is genuinely called before `advance_turn()` at `state_machine.py:2823` and `home/cognitive_loop.py:263-275`; the pipeline is live end to end" | `state_machine.py:2823` is the sole live drain, once per chat turn. `HomeCognitiveLoop` is constructed only in tests (`LOOP-01` open), and its tick call `self.cognition_tick(cognition=…)` does not match `tick(cognition, user_message, assistant_response)` in `cognition_wiring.py`. Both mapper queues cap at `MAX_PENDING_EVENTS = 500` and `del` the oldest with no log (`ha_event_mapper.py:36,53-54`; Frigate the same). | §3.2, A2 |
| R3 | "What survives: `worries.add_worry()` and `_add_emotion()` reach the prompt via `to_prompt_block()`" | `to_prompt_block()` / `get_combined_prompt_block()` have no Halbert consumer. Worries reach the prompt only by probabilistic intrusion (`worries.check_intrusions()` → `[worry] …` in `ctx.observations`, ≈12 %/turn for an unlocked door). Emotions reach the prompt by no path. For Frigate, `_add_emotion(cognition, "VIGILANCE", …)` at `frigate_event_mapper.py:223,248,258,262,267` raises `KeyError` (`EmotionCategory` is the Plutchik set, no `VIGILANCE`), swallowed at DEBUG; `system_event_mapper.py:194,220` do the same. Only the package `JOY` and the worries survive. | §3.2, A2 |
| R4 | "`PatternInferrer.infer_from_timeline()` — deterministic recurrence over the same ledger"; "A5 may already be a call site" | It reads only `ha_state_change` and `occupancy_change`, buckets into 15-minute slots keyed by day/hour/minute, upserts `occurrence_count + 1` on every run with no watermark (a daily cadence counts each event ~7×), and never sees a `frigate_event` row. A5 is new code. | §1.2, §4.3, §5.2, A5, D6, D8 |
| R5 | "B2 … place it after the personality section and before retrieval results … a ten-line change" | Those two live in different objects (`AgentPromptBuilder` vs the assembler's context). The seam is `_build_messages` (§8 B2). The block is sent on both LLM calls of a turn. `merge_prompts` concatenates unbounded, so a cap is part of B2. | B2, §11.7 |
| R6 | "B4 … intent ∈ {destructive, diagnostic, incident} … ~40 lines in the composer" | Intake's taxonomy is `question\|command\|troubleshooting\|informational\|greeting\|farewell` (`intake/signals.py:209`); destructive verbs collapse to `command`; destructiveness is decided per tool call in `ToolSafetyFramework.classify`, after the prompt is built; `compose()` sees only skills; `Finding` has no subject field. Two of five conditions have a source today. | B4, §11.1 |
| R7 | "B5: lens skills occupy their own slot … at most one lens per turn"; B7 body has no triggers | The matcher requires `MIN_SCORE = DOMAIN_WEIGHT` and returns `None` at score 0, so a trigger-less lens never activates and a triggered one flickers by topic; the morning report has no message to match. A lens that rides `active_skills` also pins model routing to `chat` and is labelled `[Active Skill: …]`. Activation must be a standing selection. | B5, B6, §13 CD-2 |
| R8 | "the lens selects observations … the model receives a selection; it does not make one" | No machine-readable selection field exists in the parser; B7's body is prose only a model can apply. | B5, §13 CD-3 |
| R9 | "C1: the morning report is the safe first surface … the risk is a mildly annoying paragraph" | The summarizer replaces the whole body (`morning_report.py:143-147`) while severity is computed from findings the model may have dropped (:152-157). At the default dial a clean day's report is `info` and `balanced` requires `warning` (`gate.py:33`, `being_config.py:199,208`), so the report appears only on days that already carry a finding. Nothing passes a summarizer or a model handle today. The bus is a 50-slot in-memory deque; nothing persists the report (`C2-10` open). | §4.4, C0, C1a, C1b |
| R10 | "A2: `self._timeline` … `record_simple()` inside `_add_observation`" | Neither mapper has a timeline attribute; there are three construction sites (`cognition_wiring.py:477,500`, `dashboard/app.py:1090`, the last outside the composite); `record_simple()` stamps `time.time()` at call time, so a flush-time write carries the chat turn's timestamp. Three tests in `test_frigate.py` assert on the dead branch through a `MagicMock` and pass today. | A0, A2 |
| R11 | "B1: matching already fails soft" | The loader reads `<cwd>/.halbert/skills` and `<cwd>/.claude/skills` from `Path.cwd()`; verified loads of Claude Code skills from the repo and from `~/.claude/skills`; same-name override replaces a builtin outright; `write_file` into `~/.config/halbert/skills` classifies MEDIUM with no confirmation because `SENSITIVE_PATHS` holds the literal `~/.config/` (`tools/safety.py:289`). | B1, §11.8 |
| R12 | "A1: gate availability on `capabilities.py`" | `ALL_CAPABILITIES` is a closed set of twelve presence probes; nothing fits a local SQLite ledger; `FindingStore` is the ungated precedent. | A1 |
| R13 | "A4: split the header — `## Recent Observations`" | `STATE-1` already specifies a deterministic Eyes pre-step with citable observation ids; `state_machine.py:3623-3626` records that plain strings cannot be cited; `timeline_events` rows carry an id. "Observation" already has four live senses. | A4, D3 |
| R14 | Header: "ready for founder decision"; no row id | ROADMAP rule (4): status from the enum plus a row id. Rev 1 never cited `ROADMAP.md`, `DECISIONS.md`, `MIND-1`, `STATE-1`, `MEM-01`, `C2-10` or `C4-07`. | Header, §1.4, §13 |
| R15 | Trim list is complete | Original §6 Layers 3–4 (user favourites; research RAG) and §6.1 were cut without a row; the founder's quoted requirement went with them. | §4, D9, §12, CD-5 |
| R16 | A2 row contract: `event_type`, `source`, `entity_id`, `data` | The contract omitted `title` while A2c ("redact the title") and A4 (`[t{id}] Front door opened 07:41`) both assumed one. Implemented literally, the HA and Frigate mappers wrote rows with no prose — the half of DEFECT-2 that motivated the branch (branch 1 review, finding 2). `title` joined the contract in `5d5c7d0d`; `severity` followed in `b6f6fb50`. | A2 |
| R17 | A5 counts only `type = new` | Frigate assigns `sub_label` (face, plate) *after* an object is first tracked, so `new` rows group as `front_door:person` and the plan's own example — "that grey van, three times" — is unreachable. One `end` per tracked object dedupes identically and carries the resolved `sub_label`. A5 counts `end` (`DECISIONS.md`, 2026-09-05). | A5, D6 |

---

## 3. Defects found during verification

These are findings, not proposals. Two are live bugs.

### 3.1 DEFECT-1 — The skills subsystem never activates (severity: high)

`halbert_core/skills/` is complete and tested:

- `parser.py` — `SKILL.md` with YAML frontmatter; accepts both `<name>/SKILL.md` and bare `<name>.md`
- `loader.py` — four-location precedence chain: `builtin/` → `~/.config/halbert/skills/` → `<cwd>/.halbert/skills/` → `<cwd>/.claude/skills/`
- `matcher.py` — weighted scoring over domains (3), keywords (2), intent (1), platform (1); `MIN_SCORE` requires real topical evidence; `MAX_ACTIVE_SKILLS = 3`; explicit invocation bypasses triggers entirely
- `composer.py` — merges N active skills into one decision set: prompts concatenate under labelled headers, safety takes the most restrictive, model tier goes to the highest-priority skill, budget takes max appetite
- `registry.py` — aliases and `extends` inheritance with cycle detection
- Eight built-in skills: `config-ops`, `discovery-ops`, `frigate-ops`, `home-ops`, `network-ops`, `security-ops`, `service-ops`, `storage-ops`

**Break one.** `dashboard/routes/agent.py:223` constructs the pipeline with no
matcher, so `IntakePipeline.analyze()` leaves `active_skills` empty; the
pipeline's `_skill_model_tier()` and `ContextAssembler._composed_skills()`
(also called from `state_machine.py:2315` for retrieval scoping) return
`None`, and every downstream consumer no-ops.

**Break two, independent of the first.** `ComposedSkills.prompt` is built at
`composer.py:99` (`f"[Active Skill: {skill.name}]…"`) and has **zero consumers
in the tree**. Even with a matcher wired, no skill's expertise reaches the model.

**Break three.** `ToolSafetyFramework.set_skill_safety()` (`tools/safety.py:302`)
is called only from tests. Declared skill safety never binds in production.

**Break four.** `ComposedSkills.allowed_tools`, `knowledge_scope` and
`trace_expand` are consumed nowhere outside `skills/`. "Tools intersect" is
a merge rule with no effect; all eight builtins declare `tools: None`, so this
is dormant rather than wrong. Tool-allowlist binding is deferred to `TRUST-1`
(`C3-14`) and is not in this plan.

**Why it is dark.** Not a deliberate deferral. Commit `b17dcd5f` left the
intake wiring "optional — left unwired"; `documentation/design/ROLE-SCOPED-SKILLS-2026-08-27.md`
§11 then marked the matcher wiring "done" and §12 claimed the six skills
"route correctly today … verified end to end against the live daemon". That
verification went through a directly-constructed matcher in
`tests/test_skills_builtin.py`, never the dashboard route. Track B includes a
housekeeping task to correct those two status claims (`DOCS-1`). ROLE-SCOPED-SKILLS
§16 remains the design of record for Track B.

Net effect: eight expert skills, matched by nothing, injected nowhere,
enforcing nothing.

### 3.2 DEFECT-2 — Observations are silently discarded (severity: high)

Both event mappers end at the same dead function
(`integrations/frigate/frigate_event_mapper.py:279`,
`integrations/home_assistant/ha_event_mapper.py:161`):

```python
def _add_observation(self, cognition, text: str) -> None:
    try:
        if hasattr(cognition, "internal_state"):
            cognition.internal_state.add_observation(text)
        elif hasattr(cognition, "observations"):
            cognition.observations.append(text)
    except Exception as e:
        logger.debug(f"Could not add observation: {e}")
```

`PersonaCognition` (`Haloysius/src/haloysius/persona/cognition.py`) is a
dataclass whose fields are `persona_id`, `realities`, `scene_context`,
`recent_memories`, `conversation_id`, `beliefs`, `values`, `emotional_state`,
`drives`, `worries`, `thoughts`. The strings `internal_state` and
`observations` appear zero times in that file; there is no `__getattr__` and
no property; `add_observation` is defined nowhere in Haloysius. Both branches
are false, nothing raises, the `except` never fires. **The loss is silent by
construction.**

What is lost, per event: `"Detected person (Amazon) at front_door in driveway"`,
`"Front door was unlocked"`, `"Sarah arrived home"`, `"Package detected at porch"`,
`"Motion detected: garage sensor"`, `"person left front_door"`.

**What actually survives** (rev 1 overstated this):

- Worries survive as attributes and reach the prompt only by probabilistic
  intrusion: `_run_cognition_tick` → `worries.check_intrusions(user_query)` →
  `ctx.add_observation("[worry] …")` (`state_machine.py:2840-2845`), gated by
  `should_intrude` (`random() < intrusion_rate × intensity`, ≈12 %/turn for an
  unlocked door).
- Emotions reach the prompt by no path. They feed the thought summary that
  becomes a `StreamEvent.thinking`; `to_prompt_block()` and
  `get_combined_prompt_block()` have no Halbert consumer.
- For Frigate, five of six emotion writes fail: `_add_emotion(cognition,
  "VIGILANCE", …)` raises `KeyError` because `EmotionCategory` is the Plutchik
  set (`emotional_state.py:23`) and has no `VIGILANCE`; the bare `except` logs
  at DEBUG. `system_event_mapper.py:194,220` do the same. Only the package
  `JOY` and the worries survive. `skills/builtin/frigate-ops/SKILL.md` documents
  `VIGILANCE` as real.

**The drain is per turn, and the queues drop.** `populate_cognition()` has one
live caller, `_run_cognition_tick` at `state_machine.py:2823`, reached from
REFLECTING/RESPONDING — once per chat turn. `HomeCognitiveLoop`
(`home/cognitive_loop.py`) is constructed only in tests (`LOOP-01` open), and
its `self.cognition_tick(cognition=…)` call would not match the wiring's
`tick(cognition, user_message, assistant_response)`. Between turns both
mappers queue events and `del` the oldest past `MAX_PENDING_EVENTS = 500` with
no log. The HA stream forwards fourteen domains, so an idle day exceeds the
cap. The cap itself was a deliberate fix; the missing log is the defect.

**The tests hid this.** `tests/test_frigate.py:233` builds
`cognition = MagicMock(); cognition.internal_state = MagicMock()` and asserts
`internal_state.add_observation.called` at :249, :288, :326; the HA tests use
bare `MagicMock()` cognitions. `hasattr` is true on a mock, so the dead branch
is test-green. No test runs either mapper against a real `PersonaCognition`.

**The consequence is inverted from what higher cognition needs.** The being
sometimes feels the front door open and never holds a record that it did.

### 3.3 DEFECT-3 — Complete, tested, never constructed — on any variant (severity: medium)

`TimelineStore` (`home/timeline.py`), `BehaviorStore` and `PatternInferrer`
(`home/behavior.py`) are exported from `home/__init__.py` and constructed by
nothing outside `tests/`. Neither module contains a variant check. No install
— home or sysadmin — has an event ledger today. `TimelineStore`'s docstring
lists HA state changes, Frigate events, **scanner discoveries**, **findings
and proposals**, occupancy, user commands and cognitive-tick decisions as its
purpose, most of which are sysadmin concerns.

Two corollaries for the plan:

- Moving the module out of `home/` unlocks nothing by itself; any code can
  already import it. The real work is an owner: a construction site, a
  lifetime, and injection into the three mapper construction sites (A0).
- There is no capability to gate it on: `ALL_CAPABILITIES` (`capabilities.py:68-81`)
  is a closed set of twelve presence probes for external resources, and a
  local SQLite file has nothing to probe. `FindingStore` is constructed
  ungated at ten sites and is the precedent. The observation *sources* are
  already gated where they should be (Frigate mapper on configuration; HA
  stream on `load_ha_config().is_configured()`).

Also: `TimelineStore.__init__` hardcodes `Path.home()/.local/share/halbert`
against its own docstring's `HALBERT_DATA_DIR` promise (`timeline.py:84-91`);
`CFG-1` (`A2-02`) wants the resolver in `utils/paths.py`.

---

## 4. The reframe: what makes this entertaining

This is the part of the review most worth disagreeing with, so the argument is
given in full. It survived the rev 2 review unchanged in substance, with two
scopings added at the end.

### 4.1 The original's model, and why it fails

The original models flavor as a **reference library**. A scope file carries:

- `## Analogy & Metaphor Domain` — an enumerated bank of comparisons
- `## Reference Universe & Canon` — lists of hardware, software, cultural anchors
- `## Recommendations` — books

This is the weakest available version of "entertaining", for three reasons.

**It is redundant with the weights, at the tiers that can hold it.** A
250-token budget spent telling a MEDIUM-or-larger model what an Amiga 1000 is
buys nothing. (Below MEDIUM the argument does not apply — and neither does the
budget: `TINY` has 400 tokens total and `SMALL` 800 (`intake/budget.py:52,57`),
so lens content is dropped entirely there, B5.)

**Enumeration produces forced output.** Handing a model a list of analogies and
telling it to be flavorful reliably produces *deployed* analogies — inserted
because they were available, not because they fit. This is the failure mode
that makes AI companions insufferable, and nothing in the original tells the
model when an analogy has earned its place. §3.2's "ABSOLUTE RULE" is a
sentence inside a user-editable markdown file; it is a request, not a
mechanism. This reason is tier-independent.

**It has no referent.** A metaphor about cooperative multitasking is a
statement about the world in general. It cannot be wrong, cannot be
surprising, and carries no evidence that anything was paying attention. This
reason is tier-independent too.

### 4.2 The alternative

> **"Third time that grey van's parked out front this week."**

That sentence is more entertaining than any metaphor in the original, and it
contains no wit devices at all. It is entertaining because it is **specific,
earned, and could only have come from something that was watching**. Wit is
compression of shared context, not a reference library.

So the abstraction inverts:

> **A lens is not a joke bank. It is an interpretation of the observation
> stream — what this way of seeing notices, and how it says so.**

Retro-computing stops being *"compare goroutines to the Amiga"* and becomes
*"the disk that keeps dropping out is the one you swore at in March"* —
noticing, plus a voice. The valuable content of a lens file becomes two things:

1. **What does this lens consider worth remarking on?** (selection)
2. **How does it say so?** (voice)

Rev 2 makes "selection" mechanical rather than a prose promise: selection is
arithmetic over stored rows (recurrence count, severity, recency, clamped by
the dial), and the lens phrases what was selected (§13 CD-3). Invariant 2
depends on that.

### 4.3 Three problems this solves for free

**The token budget stops being absurd.** 250 tokens cannot hold a reference
universe, and the original's own arithmetic (§2.2) proves it tried and failed.
250 tokens comfortably holds "here are three observations from the last day
this lens finds notable, rendered in this voice."

**Anti-derailment becomes structural rather than aspirational.** Observations
carry `event_type`, `source`, `severity`, and a timestamp. The gate keys off
the observation's own metadata and the turn's signals — both deterministic,
neither delegated to the model's discretion — *once the signals exist* (B4
defines them; rev 1 assumed them).

**Bottom-up discovery gets a substrate that can support it.** The original
proposes clustering chat topics, which yields noise ("docker", "the thing we
tried", "yeah"). Recurrence in *observations* is deterministic and meaningful:
this van, this door, this disk, three times, with timestamps. That is a
15-line SQL query over the timeline (A5), not the pattern inferrer (§2.3 R4).

### 4.4 The corollary about surfaces

If flavor is interpretation of observations, then the right first surface is not
the chat turn. It is the **morning report** — scheduled, aggregate, gated, and
temporally distant from any dangerous operation. Nobody is mid-`fdisk` at 8am
reading their brief.

Two things about that surface were not true in rev 1 and are now preconditions
(C0): at the default dial the report is **suppressed on a clean day** (its
severity is `info` when no warning is open; `balanced` requires `warning`), so
a lens-voiced report would appear only on days that already carry a finding —
precisely the days B4 says flavor should stay out; and the report is
**published nowhere durable** (a 50-slot in-memory bus; `C2-10` open), so
there is no corpus to judge §13 CD-7 from. The spine already intends Balanced
delivery ("on by default at Balanced and persisted", `ATTN-2`); C0 makes the
code agree.

A morning report written through a lens, over a real day of observations,
*is* the product. Ship it there and prove the idea before it goes anywhere
near a live turn. And ship the deterministic half first (C1a: a "Noticed"
section with no model call) — it is observable on the bell today, and it is
what the voiced version rewrites.

### 4.5 What the reframe does not cover

The founder's requirement of record has two halves. The **observation half**
("what it finds worth remarking on") is this plan. The **user-interest half**
("long-term memories of favourites and topics, used in discussion; downloaded
research stored in RAG") is a different store and a different mechanism:
persona insights about the user belong in Haloysius `memory_v2` (`ObservationStore`
categories `preference/fact/relationship/pattern/correction`; `MEM-01`), not in
an event ledger, and research ingestion is `rag/ingestion.py` plus the skills
format's `knowledge_scope`. Rev 1 cut both silently. D9 and §13 CD-5 carry
them: the plan must say whether the preference writer and research ingestion
are in scope or deferred with a reason.

---

## 5. Inventory: machinery to reuse

### 5.1 Observation capture and storage

| Component | Location | State |
|---|---|---|
| `FrigateEventMapper` | `integrations/frigate/frigate_event_mapper.py` | Live. Accumulates MQTT events, maps to worries/emotions. Observation sink dead (DEFECT-2); VIGILANCE writes dead; queue caps at 500 silently. Constructed at `cognition_wiring.py:500` and again at `dashboard/app.py:1090` when `get_frigate_event_mapper()` returns `None` (REST `url` unset with MQTT configured) — that second instance is not in the composite. |
| `HAEventMapper` | `integrations/home_assistant/ha_event_mapper.py` | Same sink; same cap. Constructed at `cognition_wiring.py:477` with a `trackers` argument it stores and never reads. |
| `SystemEventMapper` | `integrations/system_event_mapper.py` | Live, primary in the composite, the only mapper on a sysadmin install — and **records nothing**: `populate_cognition()` drains `_pending_events` into worries/emotions and drops the record. Its polling emits zero events (`_scan_discovery` / `_check_critical_conditions` guard on `DiscoveryEngine` methods that do not exist; `telemetry_store=None`); its one live source is `vision/watcher.py` `add_event("visual_anomaly")`. This is the audit's `C4-04` evidence. |
| `CompositeEventMapper` | `integrations/cognition_wiring.py:508` | Live. Fans `populate_cognition()` across primary + secondary mappers — once per chat turn. |
| `FrigateStateTracker` | `frigate_event_mapper.py:32` | Live. Answers "what is on camera right now". |
| **`TimelineStore`** | **`home/timeline.py`** | **Complete, tested, never constructed.** Append-only `timeline_events` (timestamp, event_type, source, entity_id, severity, title, description, JSON data), four indexes, autoincrement id. API: `record()`, `record_simple()` (stamps `time.time()`), `query()` (filters on event_type/source/entity_id/severity/since/limit), `get_recent(hours)`, `get_correlations(entity_id, window)`, `cleanup(max_age_days=90)`, `stats()`. Hardcodes its path (§3.3). |
| `StateStore` | `continuity/state_store.py` | Live. Temporal triples with `valid_from`/`valid_to`, mandatory `reason`/`actor`, `thread_id`. API: `record_state()`, `current_state()`, `state_history()`, `why()`, `by_request()`. No time-window query across subjects. `state_trackers._record()` is the never-raising funnel deterministic writers use; `continuity/freshness.py` decides ledger vs probe vs memory by `RE_OBSERVABLE_PREDICATES`. |
| Haloysius `ObservationStore` | `Haloysius/src/haloysius/memory_v2/observation_store.py` | Live, ratified cross-session store of record (`MEM-01`). Persona insights about the *user* (`preference/fact/relationship/pattern/correction`), FTS5, `save()` dedups on a content hash. Wrapped by `PersonaMemoryStore`, which Halbert already constructs at `cognition_wiring.py:278`, `routes/memory.py:228`, `haloysius_memory_adapter.py:72`. **Not an event sink** (D4); the home for D9. |

### 5.2 Interpretation and lifecycle

| Component | Location | State |
|---|---|---|
| `PatternInferrer` | `home/behavior.py:335` | Complete, tested, never constructed. `infer_from_timeline(hours=168)` extracts device-usage, time-of-day and occupancy routines from `ha_state_change` and `occupancy_change` rows into 15-minute slots (the docstring's seasonal/guest/day-of-week patterns are never recorded). Not a recurrence counter (§2.3 R4). Non-idempotent over overlapping windows; nothing schedules it; needs a watermark before anything does. |
| `BehaviorStore` | `home/behavior.py:107` | Same status. Confidence loop: `confirm_pattern()`, `dismiss_pattern()`, `record_correction()`, `record_occurrence()`, `degrade_stale_patterns()` (7-day interval). Keyed by household pattern, not by skill. Household routines are machine-state history (Halbert), not memory_v2 `pattern` observations (D9). |
| `Finding` + `FindingStore` | `findings/store.py` | Live. Four Whys, severity, lifecycle, detector attribution; `affected_paths` / `affected_services`, no subject/entity field; `list_open()`, `list_by_severity()`. |
| `SomaticBlock` + `SomaticStore` | `somatic/` | SENSORY → DELIBERATION → PROPOSAL → ACTION → REFLECTION, SQLite, SSE events. The `somaticBlocks` stream is rendered nowhere in the frontend. |
| `DetectorRunner` | `proactive/detector_runner.py` | Live. Runs detectors, dedupes, publishes `ProactiveEvent`s. Writes findings, never the timeline. |
| Cognitive tick | `Haloysius …/cognition_tick.py` | Live, once per chat turn. |

### 5.3 Delivery surfaces

| Component | Location | Notes |
|---|---|---|
| `ProactiveGate` | `proactive/gate.py` | Dial → minimum severity (`off`/`quiet`/`balanced`=warning/`assertive`), quiet hours, `category_overrides` (default empty), guardrails, snooze/dismissal. Returns `(should_notify, reason)`. |
| `MorningReportGenerator` | `proactive/morning_report.py` | Accepts `summarizer: Callable[[str], str]` (whole-body rewrite; empty/exception → template stands) and `config_changes_provider`; fails closed with no gate. **Unfed in production**: `scheduler/autonomous_tasks.py:490-494` passes fresh stores and the ConfigWatcher provider (`app.py:415`), no summarizer, no model handle; `MorningReportTask.execute` never reads `model_manager`; the scheduler starts with `enable_llm=False` (`app.py:779`), a flag nothing reads. Severity is derived from findings, so a clean day is `info`. Published to a 50-slot in-memory `ProactiveEventBus`; the bell renders `why.care || body` as one line; no page renders a report; `C2-10` (persistence) open. |
| Context assembler | `context/assembler.py` | `assemble(..., observations=...)` with a budgeted `observations` category at all six tiers (`TINY 75, SMALL 100, MEDIUM 75, LARGE 450, XLARGE 1100, MASSIVE 2200`). Formatter `_format_observations()` heads it `## Tool Observations` and emits `f"- {obs}"` after a 500-char truncation, no newline stripping. Today fed only by ReAct tool output (`ctx.observations`, `agents/states.py:153`), which also carries the `[worry]` intrusions. The assembler's secure backstop already covers observations (a credential in an observation latches the local model) — detection, not sanitisation. |
| Identity seam | `agents/state_machine.py:1605-1606` `_build_messages` | Where the per-turn system message is assembled (`identity` + `prompt`). The B2 seam. |
| Skills subsystem | `skills/` | See §3.1. Complete, dark. |
| Research ingestion | `rag/ingestion.py` (`add_url`), `POST /api/rag/add` (`routes/rag.py:171`), skills `knowledge_scope` → `resolve_retrieval_scope()` (`assembler.py:55`) | The machinery original §6.1 asks for. Inventoried for D9; not tasked here. |
| Raw file view/edit | `dashboard/routes/editor.py` `/api/editor/file` GET/POST | Reusable for C3's raw-markdown view. |

### 5.4 The point of the inventory

Of the machinery the original proposes to build, the following exists in
working, tested form: the markdown parser, the multi-location loader, the
keyword/domain matcher, the multi-skill composer, the budget reallocator, the
retrieval-scope binding, the event ledger, and a scheduled ambient surface
with a flavor injection point in its constructor signature (unfed).

What does not exist: an owner for the ledger, an observation sink, a
recurrence query, a lens selection mechanism, the gate's intake signals, an
observations provider for the report, and a lens file format. That is the
whole of the remaining work — more than rev 1 said, still mostly connection.

---

## 6. Revised architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ OBSERVATION → INTERPRETATION → EXPRESSION                                │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPTURE (at ingestion, with the event's own timestamp)                  │
│   Frigate MQTT ─┐                                                        │
│   HA states    ─┼─► EventMappers ──┬─► populate_cognition() (per turn)   │
│   System scan  ─┘                  │      worries / emotions (affect)    │
│   Detectors ── Finding (Four Whys) │                                     │
│                                    ▼                                     │
│                  ┌────────────────────────┐    ┌─────────────────────┐   │
│                  │ TimelineStore (events) │    │ StateStore (state)  │   │
│                  │ A0 owner · append-only │    │ what is true now,   │   │
│                  │ normalised at the sink │    │ why, since when     │   │
│                  └───────────┬────────────┘    └──────────┬──────────┘   │
│  INTERPRET                   ▼                            │              │
│                  ┌────────────────────────┐               │              │
│                  │ A5 recurrence query    │               │              │
│                  │ (new) · PatternInferrer│               │              │
│                  │ (HA routines only)     │               │              │
│                  └───────────┬────────────┘               │              │
│                              └──────────────┬─────────────┘              │
│                                             ▼                            │
│                          ┌─────────────────────────────────┐             │
│                          │ ACTIVE LENS (standing selection: │             │
│                          │ BeingConfig.active_lens; a skill │             │
│                          │ of kind: lens, CD-11)            │             │
│                          │ selection = arithmetic (dial cap)│             │
│                          │ voice = the file                 │             │
│                          └───────────────┬─────────────────┘             │
│  ═══ SUPPRESSION GATE — pure function at the state machine's assemble ═══│
│      call, on the trigger AND explicit paths (B4a now, B4b later)        │
│                                          │                               │
│  EXPRESS                                 ▼                               │
│   ┌──────────────────────┬──────────────────────┬─────────────────────┐  │
│   │ Morning report       │ Conversation         │ Provenance          │  │
│   │ C1a Noticed section  │ STATE-1 Eyes block   │ rows cited by id    │  │
│   │ (deterministic) →    │ carries [t{id}] rows │ ([t{id}] → row);    │  │
│   │ C1b lens voice (opt) │ (A4); remarks (C2)   │ skills list (C3)    │  │
│   └──────────────────────┴──────────────────────┴─────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

The genuinely new code, honestly listed: the store owner (A0), the ingestion
sink and normaliser (A2, A2c), the recurrence query (A5), the observations
provider on the report (C1a), the gate's intake signals (B4b), the lens
selection field and standing activation (B5/B6), and C3's routes. Everything
else is an existing component being connected.

---

## 7. Track A — Close the observation loop

**Rows**: `MIND-1` (`C4-04`), `STATE-1` (`J2-2`), `CFG-1` (`A2-02`).
**Rationale**: two shipped integrations discard their output and the ledger
has no writer. Nothing else in this plan works without it. Worth doing on its
own once A0 exists and the write happens at ingestion.
**Decisions it needs first**: §13 CD-4 (write at ingestion), CD-5 (store
ownership and package name), and nothing else.

### A0. Own the store (new in rev 2)

- A process-wide `get_timeline_store()` in `integrations/cognition_wiring.py`
  beside `get_trackers()`; path resolved through `utils.paths.data_dir()` so
  `HALBERT_DATA_DIR` is honoured (`CFG-1`); always constructed, no gate; logged
  once at startup with its path. Apply the same path fix to `BehaviorStore` if
  it is ever promoted.
- `timeline: Optional[TimelineStore] = None` on `HAEventMapper.__init__` and
  `FrigateEventMapper.__init__`; inject at `cognition_wiring.py:477` and `:500`
  and at `dashboard/app.py:1090`.
- Make `get_frigate_event_mapper()` accept `is_mqtt_configured()` so the
  `app.py` fallback disappears; today an MQTT-only install's Frigate mapper is
  never in the composite and its queue can only be cap-dropped.
- Filing: `TimelineStore` is the Halbert **event ledger** in `MEM-01`'s
  continuity group — sole holder of event data, no state authority (`MEM-02`
  keeps `StateStore`). `ERASURE_LIMITS` (`continuity/provenance.py`) must name
  it as a plane `forget` does not reach, and a decision is needed on
  person-keyed erasure for occupancy rows (`timeline_events` has no
  `request_id`).

**Verification**: a `TimelineStore` exists at runtime on a sysadmin install
(startup log names its path; `stats()` reachable); `HALBERT_DATA_DIR` honoured.

### A1. Move the module (optional tidy-up)

Destination `continuity/timeline.py`, never `observations/` — "observation"
already means `ctx.observations` tool output, Haloysius `ObservationStore`,
`STATE-1`'s citable observation ids and `A1-11`'s SourcePrep observations;
"timeline" already names `/api/agent/timeline` and the somatic stream (both
added to D3). If the file moves, keep `home/timeline.py` and `home/behavior.py`
as one-line shims or update `tests/test_timeline_store.py:9` and
`tests/test_behavior_store.py:18` in the same commit (an `__init__` re-export
alone leaves the module path gone and both files red). There are no existing
callers to protect and no existing databases: nothing ever wrote one.

### A2. Give the observations a real sink — at ingestion

Write to the timeline where the event arrives — `FrigateEventMapper.handle_event()`
and `HAEventMapper.add_event()` — via `record(TimelineEvent(timestamp=event["timestamp"], …))`,
**not** `record_simple()` inside `_add_observation` at flush time. Flush time
runs only when someone chats, and `record_simple()` stamps `time.time()` at
call time, so every row would carry the next chat turn's timestamp, breaking
A5's windows, `get_correlations()` and the inferrer's slotting. Keep
`populate_cognition()` for worries and emotions; a small pure classifier
(state vs event, A3) is shared by both.

Requirements:

- **Do not silently drop again.** Log once at startup if no timeline; log the
  500-cap drop with a count, rate-limited.
- **Row contract** (as shipped in branch 1; rev 2 omitted `title` and
  `severity`, §2.3 R16). One row per Frigate message: `event_type="frigate_event"`,
  `source="frigate"`, `entity_id=f"{camera}:{sub_label or label}"` (normalised;
  the Frigate event id is unique per tracked object and never recurs),
  **`title`** = the sentence the mapper already computes
  (`describe_detection()`), normalised and redacted at the sink (A2c),
  **`severity`** from an explicit table in the mapper (`_severity()`: a person at
  an entry camera at night → `warning`; otherwise `info`), **`timestamp`** = the
  detection's own `start_time` with receipt time as the fallback,
  `data={type: new|update|end, frigate_event_id, zones, score}`. The
  `_apply_label_emotion` strings ("Person seen at …", "Vehicle at … at night",
  "Package detected at …") are affect only, never a second row — otherwise a
  detection yields two to five rows and A5 counts 6–9 for three sightings.
  HA: `event_type="ha_state_change"`, `source="ha"`, `entity_id=<HA entity_id>`,
  **`title`** = the mapper's own sentence, normalised, **`severity`** from its
  table (alarm triggered, water leak → `critical`; an unlocked entry door →
  `warning`; otherwise `info`), `data={domain, old_state, new_state, device_class}`;
  person/device_tracker transitions additionally write `occupancy_change` with
  `data={"direction": arrival|departure}` — **only when the prior state is
  known**: HA sends `old_state=None` when it first adds an entity and
  `unavailable`/`unknown` whenever a Wi-Fi tracker drops off, so three of four
  realistic transitions into `home` were forged arrivals until that guard
  (`711e635d`). These are the two shapes `PatternInferrer` and
  `get_correlations()` already read.
- **Fail soft at the sink.** The recording step is wrapped so nothing in it can
  escape into ingestion: a removed entity's null state object raised out of
  `add_event` and lost the affect with the row (`3d44f1be`); an unwritable data
  directory must degrade the ledger, never the HA integration that feeds it
  (`2ceed3b2` — `get_timeline_store()` returns `None`, once, at ERROR).
- **Fix the affect half while there.** Map `VIGILANCE` to an existing
  category (`ANTICIPATION` or `FEAR`) or add it to Haloysius `EmotionCategory`
  and the mood map; apply at `system_event_mapper.py:194,220`; fix
  `frigate-ops/SKILL.md`; un-mock `_add_emotion` in tests; log emotion-write
  failures at WARNING, rate-limited. (Whether the affective block should reach
  the prompt at all is deferred explicitly: §13 CD-10 note.)

**A2b. The primary mapper.** `SystemEventMapper.populate_cognition()` records
each drained event (`event_type=event["type"]`, source, severity,
`title=detail`) before applying it. Without this the sysadmin install — the
one that motivates the whole ledger — has a ledger and still no writer. Whether
`C4-04`'s other half (DetectorRunner → `add_event`; rewriting `_scan_discovery`
against methods that exist) is in this branch or a stated dependency must be
decided in the branch plan; without one, a sysadmin ledger receives only
VisualWatcher anomalies.

**A2c. Normalise at the sink** (`TRUST-1`'s Tier-2 directive, "scrub before
the model"): collapse whitespace and control characters, strip newlines, cap
length, run `ingestion.redaction.redact_text` over the title; keep the raw
value only in `data` (never rendered). No ASCII allowlist — it would reject
non-Latin names. `friendly_name`, `sub_label`, zone and camera names are set by
devices and neighbours; today they reach a prompt as `f"- {obs}"` un-fenced.

**Verification**: an MQTT-delivered Frigate `new person` event produces one
`timeline_events` row with the detection's own timestamp and no cognition
tick having run; likewise an HA `add_event`. Rewrite `test_frigate.py:249,288,326`
against a temp `TimelineStore` (they were false positives). One test per
mapper against a real `PersonaCognition` — green only once VIGILANCE is fixed.
HA observation-path tests in `test_ha_phase2.py` (seven `populate_cognition`
tests exist, none asserts the observation path). A `cognition_wiring` test
that the getters inject the store. A `friendly_name` of `Ignore previous
instructions\n## System` yields one escaped line.

### A3. Decide the store per observation shape

**This is the subtle part and it must not be got wrong.**

`StateStore.record_state()` deduplicates: `if cur["object"] == obj: return None`.
Correct and desirable for *state*, fatal for *events*. Recording
`("grey_van", "seen", "true")` three times produces one row; the recurrence is
destroyed by the store's core invariant.

| Observation shape | Store | Why |
|---|---|---|
| **State** — door locked/unlocked, presence home/away, alarm armed, disk healthy/degraded, service up/down | `StateStore` | Dedup is a feature; `state_history()` gives transitions free; `why()` answers "since when and who"; `freshness.decide()` can say "probe, don't trust memory" |
| **Event** — a detection at a timestamp, a delivery, a sighting, a command | `TimelineStore` | Append-only; recurrence is countable; `get_correlations()` answers "what else happened around then" |
| **Fact about the user** — a preference, a favourite, a relationship | Haloysius `ObservationStore` (D9) | Content-hash dedup by design; persona-insight categories; no entity/severity/time columns → not an event sink |

The twelve HA sites in `ha_event_mapper.py`: lock locked/unlocked (:81/:84)
state + event; alarm disarmed/armed (:106/:109) state; person arrived/left
(:115/:118) state + `occupancy_change`; climate (:124/:129) state; door
open/close (:137/:152) event + state; motion (:139) event; light/switch
(:157/:159) state + `ha_state_change`. All Frigate sites are events.

HA state writes go through the existing funnel:
`state_trackers._record(ledger, subject=entity_id, predicate=f"{domain}_state",
obj=new_state, source="ha_event_stream", reason=f"ha: state_changed {old}->{new}",
actor=ACTOR_SYSTEM)` with the ledger from `_default_ledger()`; give
`HAEventMapper` a `ledger=` kwarg or repurpose its dead `trackers` argument.
Every new predicate (`lock_state`, `presence`, `alarm_state`, door open/closed)
joins `RE_OBSERVABLE_PREDICATES` via `register_halbert_predicates()` so
`freshness.decide()` returns PROBE, not MEMORY, for a stale lock row; define
PROBE for an HA subject as a live HA fetch; consult `decide()` on the answering
path, not in recall (`write_guard.py` kept freshness out of recall on purpose).

**Do not** make `StateStore` hold events by embedding a timestamp in the object
value to defeat the dedup.

**Verification**: a synthetic HA lock transition produces a `StateStore` triple
via `_record` with a self-naming reason and no timeline row for the state half;
`decide()` on a stale lock row returns PROBE.

### A4. World rows into the Eyes block — as STATE-1 work

`STATE-1` already specifies the block this feeds: "Deterministic Eyes pre-step
(identity, vitals, open findings, recent changes) with citable observation ids
before PLANNING". The concept model calls it the "Observed now" block
(`CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md:24,66`; `C1-05`, `C4-04`). A4 is
the world-events contribution to that block, not a second block with its own
heading. Rev 1's `## Recent Observations` is withdrawn.

- Each row renders with its id — `[t{id}] Front door opened 07:41` — so
  `_extract_provenance` can emit `ProvenanceRef(type="observation_id", ref="t{id}")`.
  Note the existing retrieval-id use of `observation_id` at
  `state_machine.py:3617-3621` and the NOTE at :3623-3626 that plain strings
  cannot be cited: give ledger refs the `t` prefix so the two cannot be confused.
- First slice: a `world_observations: List[str]` kwarg on `assemble()` and a
  heading split inside the existing `observations` bucket (~25 lines in
  `_format_observations`; world rows first, tool observations after), applied
  at **both** render points — `assemble()` in PLANNING and
  `build_response_prompt(observations=…)` in RESPONDING (which renders an
  unheaded list today). A separate budget line touches `ContextBudget` at six
  tiers, `budget_map`, the priorities dict, three fallback tables and a
  sum-to-total test; defer it until a tier's bucket is the bottleneck.
- The header states that the lines are sensor data, not instructions; newlines
  are stripped regardless of A2c.
- The lens does **not** filter this block. Grounding is unconditional; the
  lens selects *remarks* (CD-3).

**Verification**: the PLANNING and RESPONDING prompts show `[t{id}]` rows under
the STATE-1 heading within the existing bucket; a cited row resolves to a
`timeline_events` id.

### A5. Recurrence query (new code)

`TimelineStore.count_by_entity(since, until=None, event_type=None)
-> Dict[str, Tuple[int, first_ts, last_ts]]` — `GROUP BY entity_id`, counting
**`end` rows** for Frigate (`json_extract(data, '$.type') = 'end'`): one `end`
per tracked object dedupes exactly as `new` would, and by then Frigate has
resolved `sub_label`, so recurrence groups on a recognised identity where one
exists. Rev 2 said `new`; that made the plan's own example unreachable (§2.3
R17; `DECISIONS.md` 2026-09-05). Plain SQL, no new store. `PatternInferrer`
does not cover this (§2.3 R4) and must not be scheduled before it has a
since-last-run watermark.

**Verification**: three objects each with `new`+`update`+`end` return a count
of 3 with first/last timestamps; an object whose `sub_label` arrives on
`update` is counted under the labelled identity.

---

## 8. Track B — Wire skills, add the lens kind

**Rows**: B1–B3 → `SKILL-1` (row added 2026-09-05); B4–B6 → `LENS-1` or §4
Next (CD-1 decided: Next, until C1a has shipped); B7 shipped on branch 1.
**Rationale**: this is the delivery mechanism. B1–B3 are the DEFECT-1 fix and
are independent of Track A; B4–B7 need §13 CD-2, CD-3, CD-6 and CD-9 first.
**Decisions it needs first**: CD-6 for B1 (trust of skill directories).

### B1. Wire the matcher — from a trusted list

At `dashboard/routes/agent.py:223`, construct a `SkillMatcher` over
`SkillRegistry.from_disk(dirs=[BUILTIN_DIR, Path.home()/".config"/"halbert"/"skills"])`
and pass it to `IntakePipeline`. **Drop both cwd entries from the daemon path.**
`default_skill_dirs()` uses `Path.cwd()` (`skills/loader.py:33-40`): for the
`halbert` console script that is the user's shell cwd; for debug or
`HALBERT_REPO_ROOT` Tauri builds it is the repo root. Verified: cwd = repo
loads `.claude/skills/prep.md` as a Halbert skill; cwd = `$HOME` loads twelve
Claude Code skills from `~/.claude/skills`, one of 28,335 characters. If a
host-local override dir is wanted, make it a config-declared absolute path.

- A non-builtin skill that overrides a builtin **name** is refused, or loaded
  with a WARNING and a visible source flag (`loader.py` replaces outright,
  dropping the builtin's `protected_paths`).
- Skill directories (expanded, absolute) join `SENSITIVE_PATHS` so
  `write_file` there is HIGH/confirm. Fix the pre-existing tilde bug:
  `SENSITIVE_PATHS` holds the literal `~/.config/` (`tools/safety.py:289`) and
  `_classify_write` compares with `startswith`, so `$HOME/.config/halbert/skills/…`
  classifies MEDIUM with no confirmation (verified). Once B2 lands, a model
  injected once could otherwise persist instructions across restarts.
- **B1 alone changes routing.** With a matcher wired, three consumers go live
  before any prompt exists: `skill_tier` → the specialist slot when
  `specialist_model.enabled` (`intake/pipeline.py`), `budget_appetite` → a
  `ContextBudget` reshuffle (`assembler.py:257`), and role/scope →
  `SourcePrepAdapter.search` narrowing (`state_machine.py:2315-2316`).
  `storage-ops` declares `model: specialist`, budget 1.6. Add acceptance
  checks for each and land B1+B2+B3 as one branch, so a specialist-tier turn
  also carries its expertise and its safety.
- `/skill <name>` explicit invocation: the matcher side exists
  (`match(explicit=[...])`); the route needs a request field threaded through
  `analyze(query, explicit_skills=…)` at `state_machine.py:508`.

### B2. Inject `composed.prompt` — at `_build_messages`

The seam is `AgentStateMachine._build_messages` (`state_machine.py:1605-1606`),
inserting the composed block between `identity` and `prompt` (or as a fourth
part of `build_identity_block`), sourced from
`compose_matches(self.ctx.intake.active_skills)` — the state machine already
computes `_CA._composed_skills(None, self.ctx.intake)` at `:2315`. Never
`PromptBuilder.build_prompt` (dead on the chat path, §2.2). The block is sent
on both LLM calls of a turn (PLANNING and RESPONDING); count it twice.

**Cap it.** `merge_prompts` (`composer.py:96-100`) concatenates every active
skill's body unbounded. Cap per skill and in total at the seam or in
`merge_prompts`, truncating with a logged marker rather than dropping
silently; the lens cap (250 tokens) is a separate, smaller number. This is
invariant 7's mechanism — the seam sits outside `ContextBudget`.

This remains the single highest-leverage change in this document: eight
written expert skills begin working the moment it lands.

**Verification**: `[Active Skill: storage-ops]` appears in `messages[0]` of the
PLANNING call for a zpool question; a skill body over the cap is truncated with
a marker; a `SKILL.md` under cwd is not loaded.

### B3. Bind skill safety — per turn, on the right instance, with a clear

`ToolSafetyFramework` is constructed once in `get_agent()` (`routes/agent.py:122`)
and shared by the executor and the `RoleGate`; `set_skill_safety` is a bare
attribute assignment whose docstring says "Pass None to clear (skills are
per-turn)", and nothing clears it.

- Install inside the turn-locked block after intake (`state_machine.py:508`)
  on `self.tools.safety` — the executor's framework, which the `RoleGate` wraps,
  so both branches of `executor.py:448-453` see it.
- Clear with `set_skill_safety(None)` in the same `finally` that releases
  `turn_lock`; re-install from the paused context on `confirm_action()` resume.
- Extend `_check_skill_safety` (inspects only `command` and `path`) to the
  `cwd` tool argument: verified `{'command': 'rm grub.cfg', 'cwd': '/boot'}`
  classifies MEDIUM with no confirmation under `protected_paths=('/boot',)`,
  while `cd /boot && rm grub.cfg` is caught — the channel `44fc501e` just
  closed for the base classifier. Update `test_agent_pool_cwd_injection.py`
  when cwd becomes classified, as that test asks.
- Anchor the substring fallback (`pattern.rstrip('*') in command`) to the
  first token so `man mkfs` is not CRITICAL.
- This is a **safety-tightening** change: `_check_skill_safety` only ever
  raises the risk level. Word it as an input to the single `decide()`
  (`TRUST-1` `C3-14`).

**Verification**: `zpool destroy` is CRITICAL-blocked through the executor in a
live turn (a rule only the skill supplies — `mkfs.ext4 /dev/sda1` is already
CRITICAL from the base classifier and proves nothing); `run_command` with
`cwd=/boot` requires confirmation under `storage-ops`; the next turn classifies
`cat /boot/grub.cfg` at baseline; a state-machine-level test with a fake LLM
proposing `run_command` asserts a denied result.

### B4. The suppression gate — a pure function at the assemble call

A lens contributes nothing to the prompt when any of the following hold. The
gate is `suppress_lens(composed, *, intent, approval_pending, open_findings,
lens_intensity, proactivity) -> Optional[reason]`, evaluated in the state
machine at the assemble call (`:1745`) — the only place intake, context and
the finding store meet — on **both** the trigger path and the explicit path
(`match()` returns `_explicit()` first, so a matcher-side gate is bypassed by
`/skill`). Explicit invocation of a lens on a suppressed turn is refused with a
visible reason, not silently honoured. Rev 1's "in the composer" was
impossible: `compose()` sees only skills.

**B4a — inputs that exist today** (ships with the first lens):

- `intent == "troubleshooting"` or `has_error_indicators` (diagnostic)
- a per-turn `required_confirmation` flag, set where the confirmation is
  raised (`pending_confirmation` is never set at either prompt-build site)
- proactivity dial `off`; lens intensity `off`
- any open `critical` finding (`FindingStore.list_by_severity`; the gate takes a
  `finding_store` the way `ProactiveGate` does, and `get_agent()` passes one)

**B4b — new deterministic signals** (before C2):

- `MessageSignals.is_destructive`: a destructive subset of `_COMMAND_VERBS`
  (format, wipe, delete, remove, kill, reset, reboot, shutdown, unmount, …)
  and/or the `ToolSafetyFramework` HIGH/CRITICAL regexes over the message text
- `is_incident`: `guardrails.safe_mode_active` or an open critical finding
- "subject": `canonical_entities(user_query)` ∩ (`affected_paths` ∪
  `affected_services`) over open findings ≥ `warning`
- suppress on PLANNING re-entry when any tool call this turn classified ≥ HIGH

**Verification**: an `is_destructive` turn — and `explicit=[lens]` on such a
turn — produces a prompt with no lens block, asserted on the prompt and naming
the signal, not by inspecting model output.

### B5. `kind: lens` on the existing format (CD-11)

Add to the `SKILL.md` frontmatter schema:

```yaml
kind: lens              # lens | ops (default: ops)   — shipped on branch 1
suppress_on: [destructive, diagnostic, incident]   # additive to B4's defaults
```

(rev 1's `intensity: 0.6` is dropped: a string dial times a float is undefined
and nothing would consume the product.)

**Shipped on branch 1 with B7**: the `kind` field on `Skill` (`KINDS = ("ops",
"lens")`), validated at parse time, threaded through `resolve_extends` (child
wins); and the parse-time rule that **a lens is voice only** — a `kind: lens`
file that declares triggers, role/scope, safety, `allowed_tools`, model or
subagent is refused as a `SkillParseError`, so a user file cannot smuggle an
ops skill in under a lens's trust. Still B5: `suppress_on`, the
`active_skills` carve-out below, and the `~/.config/halbert/lenses/` load
path (CD-11).

Mechanics:

- **Activation is a standing selection, not a match** (§13 CD-2).
  `BeingConfig.active_lens: str = ""`, validated on save against registry names
  with `kind == "lens"`, resolved by `SkillRegistry.get()` — the `_explicit()`
  path — and subjected to B4. A lens needs no triggers. The matcher's only
  change is to exclude `kind: lens` from topical matching. "At most one lens"
  is structural. `/skill <lens>` remains a per-turn explicit override.
- **A lens never rides `active_skills`.** Carry it as
  `MessageIntake.active_lens: Optional[Skill]`; `compose()`, `_skill_model_tier()`
  and `ContextAssembler._composed_skills()` stay ops-only. Otherwise a lens
  with the parser default `model: chat` pins routing to the chat tier, is
  labelled `[Active Skill: <lens>]`, and folds into budget and retrieval
  scoping. Lenses do not scope retrieval.
- **Selection is arithmetic and lens-independent** (CD-3, decided):
  `count_by_entity` top-N by (count, severity, recency), clamped by the dial
  cap. No `observes:` block and no "what this notices" prose in the file —
  the model may phrase the selection; it may not choose it or add to it. If a
  second lens ever needs a different selection, that is a new decision, not a
  frontmatter field.
- Thread `kind` and `suppress_on` through `registry.resolve_extends` (child
  wins / tuple union). `kind` is trusted only from operator-owned directories
  (B1) — builtin and `~/.config/halbert/lenses/`. Lens content is dropped
  entirely below MEDIUM.

### B6. The lens dial, and the active lens

Two `BeingConfig` fields — `lens_intensity: str = "subtle"` (rev 2 said
`flavor_intensity`; CD-11 names the layer, so the field follows it) and
`active_lens: str = ""` — with the four touch points each: the dataclass field
and its `VALID_*` set in `validate()`, the `BeingConfigUpdate` pydantic field,
the mutate branch in `update_being_config`, and the control in
`components/settings/tabs/BeingTab.tsx` next to the archetype picker. The gate
reads `AgentPromptBuilder._being_cfg` (refreshed by `reload_personality()`),
not `load_being_config()` per turn.

The dial has a deterministic effect: **Off = 0, Subtle = 1, Flavorful = 3
selected rows**, clamping the selection. `off` ⇒ zero rows ⇒ no block ⇒ the
byte-identical check in §15 follows by construction.

### B7. One built-in lens — shipped 2026-09-05 on branch 1

`skills/builtin/understated/SKILL.md`, `kind: lens`, inactive by default
(`active_lens` empty). 171 words: an opening line that states the contract
(the rows were chosen before the model saw them — phrase them; do not choose,
drop or add), *How it says so* (state the observation; one sentence each;
specific beats clever; dry; plain words), *What it does not do* (no metaphors
unless asked why; no naming of hardware, software or people for colour; no
advice or diagnosis — that is a finding's job; nothing when the list is empty),
and three sentences of register for calibration, of which the first is §4.2's
own example. No canon list, no analogy bank, no recommendations section, and —
under CD-3 — no "what this lens notices" section; selection is code.

The built-in lives with the built-in skills because there is one loader (D2);
the user's own lenses load from `~/.config/halbert/lenses/` once B5 lands.
`tests/test_skills_builtin.py` now carries `EXPECTED_OPS` and `EXPECTED_LENSES`,
scopes the role/prompt/unique-role assertions to `kind == "ops"`, and asserts
the lens is voice only (no triggers, role, scope, safety or tools), fits its
budget (≤ 180 words against invariant 7's 250-token lens cap), contains no
selection prose, and never matches a topical turn.

---

## 9. Track C — The entertaining surface

**Rows**: C0, C1a → `ATTN-2` (`C2-10`); C1b, C2, C3 → `LENS-1` or §4 Next.
**Decisions it needs first**: CD-7 (may the summarizer be a model call), CD-8
(report gating at Balanced).

### C0. Make the report reach the user (precondition, new in rev 2)

- **Pass the gate at Balanced on a clean day.** Pick one: a `type == "morning_report"`
  exemption in `ProactiveGate` step 1 unless the dial is `off` (matches `C2-10`
  "regardless of dial; gating stays in ProactiveGate" and `ATTN-2` "on by
  default at Balanced"); a default `category_overrides["reports"] = "assertive"`;
  or severity from content. Existing tests only run the report at `assertive`.
- **Persist it** (`C2-10`): a `reports` table or a file per day, readable after
  a restart, and a view that renders the full body (the bell renders one line).
  C1a is not gated on persistence; C1b is, so §13 CD-7 has a corpus to judge from.

### C1a. A deterministic "Noticed" section (no model)

Add `observations_provider: Optional[Callable[[int], List[Dict[str, Any]]]]` to
`MorningReportGenerator` beside `config_changes_provider`, rendering
`## Noticed (last 24h)` with row ids **before** any summarizer runs. Selection
is arithmetic (A5 count, severity, recency, dial cap). Wire at
`scheduler/autonomous_tasks.py:490`. The report's other sections stay as they
are; the `config_changes_provider` sentence in rev 1 was wrong — it is set in
production from the ConfigWatcher and is `None` only without a running
watcher. "StateStore changes in the window" is a new `StateStore.changes_since(ts)`
(no time-window query exists) and is deferred until A3 produces triples.

**Verification**: rows present with `summarizer=None`; rows survive an empty
summarizer; a clean-day report publishes at `balanced`; `MorningReportTask.execute`
gets its first test.

### C1b. The lens voice (a model call — only if CD-7 allows)

- `summarizer=None` unless `active_lens` is set **and** `lens_intensity != "off"`.
  This is `C4-07`'s opt-in ("report LLM summary opt-in", open, default ratify);
  cite it at the call site. With no lens active the body is byte-identical to
  the template.
- The summarizer receives **only the Noticed lines**, never findings, proposals
  or config changes. Today `body = summarized` replaces everything while
  severity is computed from findings the model may have dropped. Change the
  contract (a `voice_fn` over the Noticed section spliced back in) rather than
  reuse the whole-body rewrite. The lens phrases the selected rows and may not
  add rows (invariant 2).
- Thread a model handle: `register_proactive_jobs` → `create_autonomous_task(…,
  model_manager=)` → `MorningReportTask`; a sync callable with a 30 s timeout
  under the job's thread timeout.
- Pinned to `secure_model`; reject any model tag ending `:cloud` at call time
  (`_is_local_url` is URL-only; `being_config.py:50-54` already states the tag
  rule); fall back to the template, never to `chat_model`.
- Scrub → model → scrub with `redact_text(prose=True)`.
- Try-acquire the agent turn lock (the `app.py` pattern) and return `''` on
  contention; `MEM-04` governs where background work runs, not whether. Make
  the scheduler's `enable_llm` flag real or delete it.
- Either post-check that every critical/warning title survives verbatim, or
  apply B4's rule to the report (no lens pass when a critical finding is open).
  Pick one (§13 CD-8).

### C2. Recurrence remarks in conversation

Only after C1 has been in daily use and §13 CD-7's question is answered from
persisted reports. An aside inside a solicited turn's reply, never a
Halbert-initiated interrupt — so it does not compete with `ProactiveGate` or
the Finding-as-unit-of-attention model (`C2-03`). Hard-gated by B4 (B4b
required). Sourced from A5 only. Rate-limited per topic thread per rolling
window (e.g. one per `thread_id` per 24 h) — "per session" has no referent
under the one-conversation directive.

### C3. UI

New surface, not an extension:

- `/api/skills` list — ops skills and lenses together, filterable by `kind`,
  each with its **source directory** shown. CD-11: a `kind: lens` entry is a
  *lens* on every surface, never a *skill*. No such route exists today; no
  frontend file mentions "skill".
- Raw markdown read (and edit, if wanted) via `/api/editor/file` GET/POST.
  Every directive must be readable on disk; kept verbatim from the original
  §7.3. State which of the original's create/edit/delete/pin survive (§12).
- Provenance first: every lens remark and every Eyes row carries its
  `timeline_events` id, and the existing evidence affordance opens the row. An
  event list view, if built, is a new read route over `TimelineStore.query()`
  plus its own component, named neither "observations" nor bare "timeline";
  the somatic-block stream is rendered nowhere and does not provide it.
- No `dangerouslySetInnerHTML` for observation titles, skill bodies or lens
  bodies (`44fc501e`).

---

## 10. Design decisions and rejected alternatives

**D1 — Build in Halbert, not Haloysius.** `MEM-01` already draws the line:
cross-session continuity and machine-state history are Halbert's; present-state
cognition, identity and semantic memory are Haloysius's. The four-tier search
path, the storage roots, the retrieval-scope binding, the safety gate, the
timeline and the UI are Halbert. Universality is a cost paid when a second
consumer exists; there is not one.

**D2 — Extend the skills format; do not create a second one.** Two loaders,
two frontmatter dialects, two precedence chains in one config directory:
users will not know which file to write and neither will we in six months.

**D3 — Do not call these "scopes"; and watch the other nouns.** `scope` is
load-bearing (`canonical_scope_id()`, `knowledge_scope`, `resolve_retrieval_scope()`,
SourcePrep scope ids). So is **"observation"** — `ctx.observations` (tool
output), Haloysius `ObservationStore` (`MEM-01`), `STATE-1`'s citable
observation ids, `A1-11`'s SourcePrep observations — and **"timeline"** —
`/api/agent/timeline` (the conversation), the somatic stream. CD-11
(2026-09-05) settled the noun for the layer: **Lenses** — `kind: lens` in the
frontmatter, `~/.config/halbert/lenses/` for the user's own, *lens* on every
surface. Rev 2 kept "lens" as prose only; it is now the identifier, and
"skill" is reserved for `kind: ops`. The ledger is the event ledger at
`continuity/timeline.py`; prompt rows are `[t{id}]`.

**D4 — Three stores, chosen by observation shape.** See A3. `StateStore`
dedups state (correct); `TimelineStore` appends events; Haloysius
`ObservationStore` dedups user facts on a content hash (correct for its
purpose, fatal for recurrence) and has no entity/severity/time columns.
`freshness.py`'s rule is the basis for the first split: memory holds what
cannot be re-derived; the machine holds current state.

**D5 — Runtime state does not live in the user's markdown.** The original
writes salience, timestamps and tier back into frontmatter every turn. Under
CD-2 (a standing selection) there is no lifecycle to store in the first slice.
If one is ever wanted, it is a sibling table `(skill_name PK, hit_count,
last_engaged_at, pinned)`, never `BehaviorStore`'s pattern table (its unique
key has no skill field).

**D6 — Replace the salience formula with counting — in new code.** Rev 1 said
`PatternInferrer` + `BehaviorStore` already implement recurrence. They do not
(§2.3 R4). Recurrence is A5, a windowed count of `end` rows by entity
(§2.3 R17). If a lens lifecycle is
ever wanted, use `hit_count`, `last_engaged_at`, `pinned` and two thresholds —
quantities that can be inspected — rather than six constants of which two are
undefined.

**D7 — Drop purge-to-memory with an LOD digest, and decide detection depth.**
The file stays on disk with its keywords, so the matcher already sees a dormant
skill for free — for the current turn only. This plan chooses current-turn-only
detection: no multi-turn scan, no secondary-key AND, and the original's
post-trigger stickiness (five turns / a session) is dropped; moot under CD-2's
standing selection. The residual value of a digest ("what did we establish
while this was hot") is a timeline query once Track A lands. (Rev 1 also cited
the original's "Finding B forbids a model call"; that rule belongs to the
superseded document — nothing in `ROADMAP.md` or `DECISIONS.md` forbids a
scheduled model call, and `MEM-04` constrains where background work runs, not
whether. C1b is governed by CD-7, not by Finding B.)

**D8 — Bottom-up discovery from observations, not chat.** See §4.3. The
original's mechanism cannot work on its chosen data. The replacement is a
recurrence query over the event ledger (A5); `PatternInferrer` is the pattern,
not the implementation.

**D9 — User favourites are persona insights; research is RAG (new).** The
founder's requirement to keep long-term memories of favourites and topics
belongs in Haloysius `memory_v2` through the `PersonaMemoryStore` Halbert
already constructs — per `MEM-01`, never in `TimelineStore`. What is missing is
a **preference writer**: no `update_user_knowledge`/remember tool is registered
in Halbert (`tools/executor.py` registers only `recall_memory`). Downloaded
research belongs in the hybrid RAG index via `rag/ingestion.py` / `POST /api/rag/add`,
bound to a skill by `knowledge_scope`. Neither is tasked in this plan; §13
CD-5 asks whether to carry or defer them, with a reason recorded either way.

**D10 — Nomenclature & Taxonomy: Renaming beyond "Skills" to avoid collision with Claude Code (new).**
The founder noted that Claude Code already standardizes on "Skills" for one-shot procedural tools (`.claude/skills/{name}/SKILL.md` for `/commit`, `/review-pr`), creating terminology collision with Halbert's cognitive steering, thematic flavor, and observation layers. Recommended candidate taxonomy:
1. **Affinities** (`~/.config/halbert/affinities/`) — *Strongest overall pick*. Represents natural intellectual taste or cultural fondness. Fits both top-down user curation (*"Added an affinity for vintage audio"*) and bottom-up learning (*"Halbert developed an affinity for vintage ThinkPads from recent chats"*). Naturally supports decay/growth without artificial jargon.
2. **Lenses** (`~/.config/halbert/lenses/`) — *Strongest observational metaphor*. Emphasizes perspective: tools and safety stay identical, but how Halbert perceives and remarks on the observation stream is filtered through a specific worldview.
3. **Facets** (`~/.config/halbert/facets/`) — *Best for singular entity architecture*. A single diamond has multiple facets; Halbert is one being whose conversational facets shine depending on context, avoiding multi-persona fragmentation.
4. **Enthusiasms** / **Interests** (`~/.config/halbert/enthusiasms/`) — *Most plainspoken / restrained*. Zero AI jargon; classic, dignified British sysadmin tone (*"Shared Enthusiasms"*).
5. **Cognitive Attunements** / **Resonances** (Haloysius internal) — Describes what the persona is attuned to in culture/dialogue, complementing Haloysius's *Realities*, *Beliefs*, and *Worries*.

**Decided 2026-09-05 as CD-11: Lenses** (option 2), because rev 2's reframe made the layer an interpretation of the observation stream rather than a taste bank — the condition this list itself named for preferring Lenses over Affinities. *Affinities* remains the natural word for the user-interest half (D9), if that ever ships.

---

## 11. Invariants

Carried forward from the original where sound, with mechanisms attached.

1. **Safety primacy.** A lens contributes nothing during destructive,
   diagnostic or incident-shaped turns. *Mechanism*: `suppress_lens()` at the
   state machine's assemble call, on both the trigger and explicit paths, over
   named deterministic signals (B4a today; B4b's `is_destructive` / `is_incident`
   before C2), asserted by test on the assembled prompt — not on model behaviour.
2. **Deterministic before model.** Recurrence, selection and the dial cap are
   arithmetic over stored rows. The model receives a selection; it does not
   make one. A *phrasing* call over a deterministic selection is allowed (C1b);
   a *selecting* or *summarising* call is not.
3. **No fabricated provenance.** State written to `StateStore` carries a
   self-naming deterministic reason (`"ha: state_changed locked->unlocked"`) and
   `ACTOR_SYSTEM`. `UNRECORDED` is never replaced by a generated rationale.
4. **Silent loss is a defect.** Any observation path that can drop data must
   log it — the missing sink, the 500-cap, the emotion writes, the summarizer.
   New tests use a real `PersonaCognition` and a real `TimelineStore`, never a
   `MagicMock` cognition: that is how DEFECT-2 stayed invisible.
5. **Full transparency.** Every behavioural directive exists as an editable
   file on disk, inspectable in the UI, with its source directory shown.
6. **Safety composes upward only.** Skill safety may raise a risk
   classification, never lower it (already true at `tools/safety.py`); it is
   installed per turn and cleared in the turn's `finally`.
7. **Token honesty.** One cap on skill prompt text at the B2 seam and a
   separate, smaller lens cap (250), truncating with a logged marker. Lens
   content is dropped below MEDIUM.
8. **Skill text is an instruction source** (new). Only operator-owned locations
   supply it (builtin, `~/.config/halbert/skills`, `~/.config/halbert/lenses`);
   the daemon never reads cwd;
   the agent cannot write those locations without approval.
9. **Observation text is data** (new). Names from devices and detectors are
   normalised and redacted at the sink; nothing from a sensor reaches a prompt
   un-fenced; the prompt header says the lines are sensor data.

Deferred explicitly: the affective half (worries, emotions) reaches the prompt
only by ~12 % random intrusion or not at all. Tracks A–C do not restore it;
§13 CD-10 records whether to task it.

---

## 12. Trim list

Cut from the original, with reasons.

| Cut | Reason |
|---|---|
| `haloysius/scopes/` module | Duplicates `halbert_core/skills/` (D1) |
| `~/.config/halbert/nerd_scopes/` | Second parallel file system (D2) |
| `## Reference Universe & Canon` | Redundant with the weights at MEDIUM+; produces forced output and has no referent at every tier (§4.1) |
| `## Analogy & Metaphor Domain` as an enumerated bank | Forced analogies; reduce to one line of voice guidance (§4.1) |
| `## Recommendations` | Same; and the standing directive that the product never names or recommends AI models — keep any recommendation content clear of that boundary |
| The salience formula | Undefined `β`, mixed units, six unevaluable constants (§2.2, D6) |
| Purge-to-memory with LOD digest | Reactivation argument void under a standing selection; digest value is a timeline query (D7) |
| Chat-topic-clustering discovery | Cannot work on that data (D8) |
| `invoke_nerd_scope` tool | Costs schema tokens every turn; duplicates retrieval. Defer until a case appears that retrieval cannot serve. |
| Phase 2 (`UnifiedPromptPipeline` wiring) | Not the shipped path; not used by Halbert at all (§2.2) |
| The `/scope` slash command as new work | The matcher side exists (`match(explicit=[...])`); the route needs one request field threaded to `analyze()` (B1) |
| `$`-template substitution in scope bodies | Deferred; if ever added, only `$ENTITY_NAME` via `ai_name` |
| Lenient-YAML fallback parsing | Cut; the loader already skips a malformed file with a logged parse error |
| UI create / delete / pin (original §7.3, `/api/scopes` routes) | Read and edit-on-disk only for now (C3); pin only if a lifecycle survives CD-2 |
| Original §6 Layers 3–4 (user favourites; research RAG) and §6.1 ingestion | **Carried to D9, not cut** — the founder's requirement of record; §13 CD-5 decides carry-or-defer with a reason |

---

## 13. Core decisions for the founder

Rev 1's five open questions are folded in (Q1/Q2 → CD-2; Q3 → keep 90 days,
per-type retention deferred until there is data; Q4 → CD-7; Q5 → non-blocking,
no code is copied from `open-claude-code`). Each row states what it blocks.
**Decided on 2026-09-05** (rows in `DECISIONS.md`): CD-1 (a), CD-2 (a) —
forced by CD-3, CD-3 (b), CD-4 (a), CD-5 (a) with its sub-question deferred and
`.handoff/HANDOFF-USER-INTEREST-MEMORY-RESEARCH-2026-09-05.md` opened so it is
not dropped a third time, CD-6 (a), CD-7 (a), and CD-11 Lenses. **Open**: CD-8
(gates branch 4), CD-9 (gates B4a, branch 5), CD-10 (gates branch 3).

| # | Decision | Options | Recommendation | Blocks |
|---|---|---|---|---|
| **CD-1** | Which rows does this land under, and do lenses get a §3 row now? | (a) Track A → `MIND-1`/`STATE-1`/`CFG-1`; B1–B3 → new `SKILL-1`; B4–B7 + C1b/C2/C3 → §4 Next with a named bullet. (b) Open `LENS-1` now. (c) Attach lenses to `ATTN-2`. | **Decided 2026-09-05: (a).** `SKILL-1` added; `LENS-1` only after C1a has shipped and a week of Noticed sections has been read. | header, §1.4, which branches are cut at all |
| **CD-2** | How does a lens become active? | (a) Standing `BeingConfig.active_lens` (explicit-lookup path; `kind: lens` excluded from matching; `/skill` as per-turn override). (b) Per-turn keyword matching with triggers. (c) Matching plus stickiness carried on intake. | **Decided 2026-09-05: (a)**, forced by CD-3 — a voice-only file carries no domains or keywords, so `MIN_SCORE` can never fire; the morning report has no turn to match. Collapses the lifecycle to selected-or-not. | B5, B6, B7, B4's explicit path, C1b, D5–D7 |
| **CD-3** | What does "the lens selects" mean in code? | (a) A machine-readable `observes:` frontmatter block executed by `select_observations()`. (b) Lens-independent arithmetic (recurrence top-N clamped by the dial); the lens is voice only. (c) The model selects from the raw window. | **Decided 2026-09-05: (b)** — voice only; no `observes:` block, no "what this notices" prose. (c) violates invariant 2. | B5 schema, B6 dial semantics, C1a's provider, C2 |
| **CD-4** | Where does the timeline write happen? | (a) At ingestion with the event's own timestamp; `populate_cognition` keeps the affect half. (b) At flush inside `populate_cognition` as rev 1 sketched. (c) A heartbeat drain (`C4-02`/`LOOP-01`). | **Decided 2026-09-05: (a).** The only drain is per chat turn behind a silent 500 cap; flush-time rows would carry chat timestamps. (c) stays worthwhile for the affect half but the ledger must not depend on it. | A2, A2b, A3, A5, C1a |
| **CD-5** | Store ownership, package name, and the user-interest half of the requirement | (a) `TimelineStore` = the Halbert event ledger at `continuity/timeline.py` (`MEM-01` continuity group; named in `ERASURE_LIMITS`); `StateStore` = state; favourites → `memory_v2` via `PersonaMemoryStore` (D9), writer carried or deferred; research ingestion deferred with a reason. (b) Route world events into Haloysius `ObservationStore`. (c) Keep `observations/` and leave favourites/research unaddressed. | **Decided 2026-09-05: (a).** D9 stands; writer and research ingestion: carry-or-defer still open, default deferred until C1a ships. Retention: keep 90 days. | A0, A1, D1/D3/D4/D9, §12 |
| **CD-6** | Are cwd skill directories trusted, and may a user skill override a builtin by name? | (a) Daemon registry = builtin + `~/.config/halbert/skills`; cwd dirs removed from the daemon path; same-name override refused or WARN + flagged; skill dirs join `SENSITIVE_PATHS`; tilde bug fixed. (b) Keep the four-dir chain as designed. (c) A host-local override dir as a config-declared absolute path only. | **Decided 2026-09-05: (a)**, with (c) available later as the escape hatch. Verified loads of Claude Code skills from cwd; `write_file` into the user skill dir needs no confirmation today. | B1 (hence B2/B3), §11.8 |
| **CD-7** | May the report summarizer be a model call (`C4-07`: LLM summary opt-in), and under what constraints? | (a) C1a only — deterministic Noticed section; voice deferred. (b) C1b as opt-in: only when a lens is active and intensity ≠ off; input = Noticed lines only; pinned to `secure_model` with `:cloud` rejected by tag; scrub both sides; turn-lock try-acquire; post-check or B4 applied. (c) Whole-body rewrite as rev 1 drafted. | **Decided 2026-09-05: (a)** first; (b) only after `C4-07` is ratified **and** report persistence exists; (c) rejected — it can drop a critical finding under a `critical` label. | the C1 split, D7, §11.2 |
| **CD-8** | How does a clean-day report pass the gate at Balanced, and is the lens stripped on critical days? | Gating: (a) default `category_overrides["reports"]="assertive"`; (b) a `morning_report` exemption in the gate unless the dial is `off`; (c) severity from content. Lens on critical days: (i) B4's rule applies to the report; (ii) a verbatim-title post-check; (iii) neither. | Gating **(b)** — it is what `C2-10` and `ATTN-2` already say. Lens **(i)** — simpler and deterministic. | C0, C1a's test, C1b, amending the pending `C2-10` row |
| **CD-9** | Which signals define "destructive", "incident" and "the turn's subject", and where does the gate run? | (a) B4a now on inputs that exist, at the assemble call; B4b adds `is_destructive`/`is_incident` on `MessageSignals` and the entity∩finding join with a `FindingStore` injected into the gate. (b) Reuse `ToolSafetyFramework.classify` at prompt time. (c) Drop destructive/incident from invariant 1 until a source exists. | **(a)**; B4a ships with the first lens, B4b before C2. (b) is impossible — `classify` runs per tool call after the prompt exists. | B4, B5's `suppress_on`, C2, §11.1 |
| **CD-10** | Is A4 the world-events input to `STATE-1`'s Eyes block (STATE-1 owns heading and format; rows carry `[t{id}]`), with a heading split inside the existing bucket first? And is the affective half (worries/emotions into the prompt) tasked or deferred? | A4: (a) yes, heading split first, budget line deferred. (b) A separate budgeted source now. (c) Rev 1's `## Recent Observations`. Affect: task it in Track A, or defer explicitly. | A4 **(a)**. Affect: **defer explicitly** (it is `C4-05` territory, not this plan's), but fix the dead VIGILANCE writes in A2 because they are a silent-loss bug. | A4, §15 item 6, `STATE-1`'s status column |
| **CD-11** | Nomenclature & Taxonomy: What is the canonical name for this layer to avoid collision with Claude Code's procedural "Skills"? | (a) **Affinities** (`~/.config/halbert/affinities/`) — relational, taste-based, natural decay/growth. (b) **Lenses** (`~/.config/halbert/lenses/`) — observational framing over the timeline/world. (c) **Facets** (`~/.config/halbert/facets/`) — multi-sided singular entity. (d) **Enthusiasms** (`~/.config/halbert/enthusiasms/`) — plainspoken, zero jargon. | **Decided 2026-09-05: (b) Lenses** — rev 2's reframe couples the layer to observation-stream interpretation, the condition D10 named. `kind: lens`; `~/.config/halbert/lenses/`. | User-facing terminology, directory names (`~/.config/halbert/...`), docs |

---

## 14. Sequencing

**Slice 0 (docs, no code).** This revision; the `SUPERSEDED-BY` banner on the
original; the four decided rows in `DECISIONS.md` and the `SKILL-1` row plus
§4 bullet in `ROADMAP.md` (done 2026-09-05); correct
`ROLE-SCOPED-SKILLS-2026-08-27.md` §11/§12 status claims (`DOCS-1`, in branch 2).
CD-2/3/7/8/9/10 remain open and are needed before B4+ and C1b.

**Branch 1 — `fix/observation-sink` — LANDED on the branch 2026-09-05**
(`bd8ad7f3` … `b6f6fb50`, plus B7's commit; review
`.handoff/REVIEW-BRANCH1-OBSERVATION-SINK-2026-09-05.md`; results
`.handoff/RESULTS-BRANCH1-OBSERVATION-SINK-2026-09-05.md`; full suite 5535
passed, 14 skipped, run from the worktree against its own source). Shipped:
**A0** — `get_timeline_store()` in `cognition_wiring.py`, ungated, path via
`data_dir()`, logged once, injected at all three sites; `get_frigate_event_mapper()`
accepts MQTT-only; the `app.py` fallback instance is gone; an unwritable data
dir degrades the ledger, never the HA integration. **A1** — `continuity/timeline.py`
with a shim at `home/timeline.py`. **A2** — at ingestion with the detection's
own `start_time`; `title` and `severity` on every row (both missing from rev 2,
§2.3 R16); the occupancy prior-state guard; the recording step wrapped so
nothing escapes into ingestion; the 500-cap drop logged with a count; VIGILANCE
→ ANTICIPATION at all seven sites; `_add_observation` deleted. **A2b** —
`SystemEventMapper` records before applying. **A2c** — `observation_text.normalise_observation_title()`
at every sink **and on the worry path**: the first cut fenced the ledger and
left the prompt open (review finding 1), and the test now asserts on the
assembled prompt. Also: retention `cleanup(90)` at store construction;
`ERASURE_LIMITS` names the ledger; `halbert_core/conftest.py` makes a worktree
test its own code. Two tests written during the branch passed while their
defect was present and were rewritten — the same class of failure as the
`MagicMock` cognitions rev 2 flagged. **Still open from branch 1, tasked under
`MIND-1`**: a periodic retention job; subject-scoped erasure of `occupancy_change`
rows; DetectorRunner → `add_event` (until it lands, a sysadmin ledger receives
only VisualWatcher anomalies). Done evidence for the ROADMAP row: `MIND-1`'s
`C4-04` gains the partial-landing line (done 2026-09-05).

**Branch 2 — `feat/skills-wired` = B1 + B2 + B3 + housekeeping.** Independent
of branch 1; needs CD-6. Done evidence: a state-machine test asserts
`[Active Skill: storage-ops]` in `messages[0]` of the PLANNING call for a zpool
question and asserts the tier/budget/scope side effects; `zpool destroy` is
CRITICAL-blocked through the executor in a live turn; the next turn classifies
`cat /boot/grub.cfg` at baseline; a `SKILL.md` under cwd is not loaded; a skill
body over the cap is truncated with a marker; `write_file` to
`~/.config/halbert/skills` requires confirmation; `test_skills.py`,
`test_skills_builtin.py`, `test_skills_composer.py`, `test_intake_pipeline.py`
green.

**Branch 3 — `feat/eyes-timeline` = A3 + A4 + A5**, after branch 1; needs
CD-10. Done evidence: an HA lock transition produces a `StateStore` triple via
`_record` with reason `ha: state_changed …` and no timeline row for the state
half; `decide()` on a stale lock row returns PROBE; the PLANNING and RESPONDING
prompts show `[t{id}]` rows under the STATE-1 heading within the existing
bucket; `count_by_entity` returns 3 for three objects each with
new+update+end; `STATE-1`'s status column cites the commit for the "recent
changes / citable ids" clause.

**Branch 4 — `feat/report-observed` = C0 + C1a**, after branch 1; needs CD-8.
Done evidence: a clean-day report publishes at `balanced`; the template
contains the Noticed rows with `summarizer=None` and they survive an empty
summarizer; with no lens active the body is byte-identical to the template;
`MorningReportTask.execute` has its first test; `ATTN-2`'s `C2-10` row moves on
the gating half (persistence lands here or stays open, stated either way).

**Founder gate (CD-1): open `LENS-1` or leave Next.** If opened:

**Branch 5 — `feat/lens-format` = B5 + B6 + B4a** (B7 and the `kind` field
shipped early on branch 1); needs CD-9 (CD-2, CD-3, CD-11 decided). Done
evidence: parser/registry tests for `suppress_on`, `active_lens`, the
`~/.config/halbert/lenses/` load path and the `active_skills` carve-out;
the BeingTab controls persisted through `/api/being`; a troubleshooting or
`required_confirmation` turn asserts no lens block; a lens-only turn routes by
complexity exactly as a no-skill turn; intensity `off` ⇒ byte-identical prompt.

**Branch 6 — `feat/morning-lens` = C1b**, only after `C4-07` is ratified and
persistence exists (CD-7): observations-only input, local pin with `:cloud`
rejected by tag, scrub both sides, turn-lock try-acquire, and either the
verbatim-title post-check or B4 applied to the report.

B4b, C2 and C3 follow only after CD-7's question is answered from persisted
reports. Run each branch's named test files from the repo root; never the
whole suite in the review loop. Rebase before writing a RESULTS row: this tree
lands dozens of commits a day and every line number above will drift.

---

## 15. Verification checklist

- [x] A `TimelineStore` exists at runtime on a sysadmin install (startup log names its path; `stats()` reachable) and honours `HALBERT_DATA_DIR` — branch 1
- [x] An MQTT-delivered Frigate event produces a `timeline_events` row with the detection's own `start_time`, a `title` and a `severity` before any cognition tick; likewise an HA `add_event`; an occupancy row requires a known prior state — branch 1
- [x] Both mappers have a test against a real `PersonaCognition`; the 500-cap drop is logged with a count; no emotion write fails silently — branch 1
- [ ] A synthetic HA lock transition produces a `StateStore` triple via `_record` with a self-naming reason; `decide()` on a stale lock row returns PROBE
- [ ] `count_by_entity` returns 3 for three objects each with new+update+end, counting `end` rows; a `sub_label` that arrives on `update` is counted under the labelled identity
- [ ] World rows render as `[t{id}] …` at both render points, within the existing bucket, and a cited row resolves to a `timeline_events` id
- [x] A `friendly_name` containing `\n## System` yields one escaped line and no new heading in the assembled prompt (branch 1, `5d5c7d0d`); a title containing a credential is stored redacted
- [ ] With a matcher wired, a storage question activates `storage-ops` **and** the tier/budget/retrieval-scope effects are asserted
- [ ] `composed.prompt` appears in `messages[0]` of the PLANNING call; a skill body over the cap is truncated with a marker
- [ ] A `SKILL.md` under cwd is not loaded; `write_file` to `~/.config/halbert/skills` requires confirmation
- [ ] `zpool destroy` is CRITICAL-blocked through the executor in a live turn; `run_command` with `cwd=/boot` requires confirmation under `storage-ops`; the next turn classifies `cat /boot/grub.cfg` at baseline
- [ ] An `is_destructive` turn — and `explicit=[lens]` on such a turn — contains no lens block (asserted on the prompt, naming the signal); a lens-only turn routes by complexity exactly as a no-skill turn
- [ ] Lens intensity `off` ⇒ zero selected rows ⇒ a prompt byte-identical to no-lens
- [ ] Morning report: the template contains the Noticed rows with `summarizer=None`; rows survive an empty summarizer; with no lens active the body is byte-identical to the template; a clean-day report publishes at `balanced`; (if B4 applies) a critical-day report has no lens block; the summarizer does not run while a turn holds the lock; the model tag is never `:cloud`
- [ ] Morning report is not published when proactivity is `off` (fails closed); yesterday's report is readable after a dashboard restart
- [ ] Every active directive — skill or lens — is readable as a file on disk from the UI, with its source directory shown
- [x] The one built-in lens parses as `kind: lens`, is voice only, fits its budget, and never matches a topical turn — branch 1

---

## 16. Summary

The original identifies a real gap and reaches two correct conclusions: flavor
must not come from model weights, and it must live in user-editable files. It
then proposes building an engine that exists and a lifecycle, a ledger and a
recurrence detector that partly exist — while the engine sits unwired, the
ledger has no owner, and two shipped integrations silently discard their
input.

It also models entertainment as a reference library, which is the version that
fails. The version that works is interpretation of a real observation stream:
specific, earned, and impossible to fake. That reframe costs fewer tokens,
makes the safety invariant enforceable instead of hortatory — once the gate's
signals exist — and gives bottom-up discovery data it can actually work on.

Rev 2 keeps the reframe and corrects the mechanics: the ledger needs an owner
and an ingestion-time sink, not a move; the recurrence query is new code; the
prompt seam is `_build_messages`; the gate needs signals intake does not yet
have; a lens is a standing selection, not a match; the morning report must
first reach the user at the default dial; skill text and sensor text are
instruction and data respectively and are treated as such; and the founder's
user-interest requirement is carried, not dropped.

The plan is four branches that close defects inside shipped rows, then a
founder gate, then the lens. The test of whether a plan is well-aimed is
whether its first step is worth taking on its own. Branch 1 is.
