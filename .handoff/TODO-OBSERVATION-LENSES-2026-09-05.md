# TODO: Observation lenses and the user-interest half — everything still open

**Date**: 2026-09-05 · **Status:** ACTIVE — the open-work list for this workstream
**ROADMAP rows:** `MIND-1` (`C4-04`), `STATE-1` (`J2-2`), `CFG-1` (`A2-02`), `SKILL-1`, `ATTN-2` (`C2-10`), `TRUST-1`; lens work is §4 Next
**Plan of record:** `.handoff/HANDOFF-OBSERVATION-LENSES-2026-09-04.md` (rev 2.1) · **tiers:** `.handoff/DISPATCH-OBSERVATION-LENSES-2026-09-05.md` · **research:** `.handoff/HANDOFF-USER-INTEREST-MEMORY-RESEARCH-2026-09-05.md`
**Rule:** `ROADMAP.md` alone says now / next / deferred. This file lists what is left and where each item lands; it moves nothing.

Written at the end of the fable wrap-up on `fix/observation-sink` (`06f873ee`).
Everything fable-shaped that could be done was done (§10); what remains is
founder calls, code for other tiers, and upstream asks.

---

## 1. Founder calls — nothing below them starts until they are made

| # | Call | Recommendation on file | Gates |
|---|---|---|---|
| `CD-8` | Clean-day report passes the gate at Balanced; lens stripped on critical days | gate exemption for `morning_report` unless the dial is `off`; B4's rule applies to the report (lenses §13) | branch 4 (C0, C1a), amending pending `C2-10` |
| `CD-9` | Deterministic sources for "destructive", "incident", "the turn's subject"; where the gate runs | B4a now on signals that exist, at the assemble call; B4b adds `is_destructive` / `is_incident` and the entity ∩ finding join (lenses §8 B4) | branch 5 (B4a), C2 |
| `CD-10` | A4 is the world-events input to `STATE-1`'s Eyes block; heading split first; affect half deferred | yes; heading split inside the existing bucket; defer the affect half explicitly (lenses §13) | branch 3 (A4) |
| `C4-07` | Deep Thinker = scheduled deterministic work; report LLM summary opt-in | ratify | branch 6 (C1b) |
| `C2-03` | Finding is the unit of attention | ratify (default) | C2, the capture aside |
| `RQ-1` | An interest is a memory_v2 `PersonaMemory` mirrored as an `ObservationStore` row; `StateStore` never holds a user fact; amend lenses A3's one line | yes | the user-interest writer |
| `RQ-2` | A `DECISIONS` row that memory_v2 user facts may be read into a turn (D1 forbade any Haloysius read path; `MEM-01` narrowed it without saying) | add the row | RECALL-v1 |
| `RQ-3` | Capture: explicit writer + arithmetic candidates + a person confirms; no model-chosen write; one dial-gated confirmation aside | as written (research §1) | the writer |
| `RQ-4` | v1 inference covers what this admin works on (intake vocabulary); hobbies explicit-only unless a user-editable noun file is tasked | say it on the surface; task the file | the candidate rule |
| `RQ-5` | Lenses invariant 5 splits: directives → editable file with source; facts → UI list with who / when / how and a forget that reports its reach | ratify | the Settings section |
| `RQ-6` | "Forget" vs "Stop using" while `ObservationStore` has only `mark_stale`; raise the three Haloysius asks (§9) | "Stop using" until delete exists | the forget orchestrator |
| `RQ-7` | Research: structural licence opt-out outside `data/`; **remove `linux/user-sources/` from `linux_system_docs.paths` in `data/manifest.json`**; pasted URL = per-action consent, anything Halbert chooses sits behind `CAP_WEB`; research is per-host | yes to all four. The manifest line is one edit with no code; it was **not** made in this pass because it changes what the licence gate labels while the directory still exists under `data/`, so the gate test must be run with it | "Study this" |
| `RQ-8` | Per-person facts on a home body: the row carries `speaker_role`; the writer refuses below `member` | yes, pending `W3-C03` | the writer |
| `RQ-9` | C2's aside rule ("inside a solicited reply, never a Halbert-initiated interrupt") becomes a `DECISIONS` row | add the row | lenses C2, capture, recall |
| `CD-1` gate | Open `LENS-1` | only after C1a has shipped and a week of Noticed sections has been read | branches 5, 6 |

## 2. Branch 1 residue — `MIND-1` (`C4-04`), on `fix/observation-sink` before or after merge

| Item | Tier | Note |
|---|---|---|
| Periodic retention job: `TimelineStore.cleanup(90)` runs at construction only; the daemon never restarts | sonnet · med | APScheduler under the heartbeat (`MEM-04`); `RETENTION_DAYS` is the constant |
| Subject-scoped erasure of `occupancy_change` rows (a named person's movement history; `timeline_events` has no `request_id`) | opus · high | `ERASURE_LIMITS` names the ledger as unreached today; keep that sentence true until this lands |
| DetectorRunner → `add_event`; rewrite `_scan_discovery` / `_check_critical_conditions` against `DiscoveryEngine` methods that exist | sonnet · high | until it lands a sysadmin ledger receives only VisualWatcher anomalies (dispatch §3.2) |
| `PatternInferrer.infer_from_timeline` needs a since-last-run watermark before anything schedules it (re-upserts its whole window; ~7× inflation at a daily cadence) | sonnet · med | or scope it out; nothing calls it today |
| The affective half: worries reach the prompt only by ~12 % random intrusion, emotions never; `to_prompt_block()` has no consumer | — | deferred explicitly under `CD-10`; `C4-05` territory |
| Merge branch 1 into main; the handoff exists in two versions (rev 2 + D10 on `fix/observation-text-normalisation`, rev 2.1 here, a descendant) — take this branch's copy | whoever merges | rebase before the RESULTS row; line numbers drift |

## 3. Branch 2 — `feat/skills-wired` = B1 + B2 + B3 (`SKILL-1`, opus, independent of branch 1)

Spec: lenses §8 B1–B3 and §14 branch 2; `CD-6` decided. Done evidence is written there. Reminders that came out of review:

- B1: trusted list only (`builtin` + `~/.config/halbert/skills`); no cwd; same-name override of a builtin refused or flagged; skill dirs into `SENSITIVE_PATHS` with the literal-`~/.config/` bug fixed; acceptance checks for the three routing effects that go live with the matcher alone.
- B2: the seam is `AgentStateMachine._build_messages`; cap per skill and in total with a logged marker; the lens cap (250) is a separate number.
- B3: install on `self.tools.safety` after intake, clear in the turn's `finally`, re-install on `confirm_action()` resume; classify the `cwd` tool argument; anchor the substring fallback to the first token; test a rule only the skill supplies (`zpool destroy*`), not `mkfs` which the base classifier already blocks.
- `DOCS-1` half done: `ROLE-SCOPED-SKILLS` §11 status claims corrected 2026-09-05. Still to do there: nothing until B1–B3 land, then flip the annotations.

## 4. Branch 3 — `feat/eyes-timeline` = A3 + A4 + A5 (`MIND-1`, `STATE-1`; after branch 1; needs `CD-10`)

- A3 (opus · max): state vs event across the twelve HA sites through `state_trackers._record`; new predicates into `RE_OBSERVABLE_PREDICATES`; PROBE for an HA subject = a live HA fetch; `decide()` on the answering path, never in recall. The row contract now carries `title` and `severity`; A3's table must say which HA state predicates get a `StateStore` triple as well as the timeline row.
- A4 (sonnet · xhigh): `[t{id}]` rows into the Eyes block at both render points, heading split inside the existing `observations` bucket; budget line deferred.
- A5 (sonnet · med): `TimelineStore.count_by_entity(...)` counting **`end`** rows (`DECISIONS.md` 2026-09-05), verification with new+update+end per object and a `sub_label` that arrives on `update`.

## 5. Branch 4 — `feat/report-observed` = C0 + C1a (`ATTN-2` `C2-10`; after branch 1; needs `CD-8`)

- C0-gate (sonnet · high) and C0-persist (sonnet · xhigh): the report reaches the user at Balanced on a clean day and survives a restart; a view renders the full body.
- C1a (sonnet · high): `observations_provider` on `MorningReportGenerator`, `## Noticed (last 24h)` with row ids before any summarizer; selection is arithmetic (A5, severity, recency, dial cap); `MorningReportTask.execute` gets its first test; `config_changes_provider` sentence corrected in the plan already.
- The week of Noticed sections that `CD-1` and `CD-5` both wait for starts when this ships.

## 6. Branch 5 — `feat/lens-format` = B5 remainder + B6 + B4a (needs `CD-9`; opens only when `LENS-1` opens)

- B5 remainder (opus · high): `suppress_on` in the frontmatter; the `active_skills` carve-out (`MessageIntake.active_lens`; `compose()`, `_skill_model_tier()`, `ContextAssembler._composed_skills()` stay ops-only); the `~/.config/halbert/lenses/` load path (`CD-11`); `kind` and the voice-only parse rule already shipped in `66ed1447`.
- B6 (sonnet · med): `lens_intensity` and `active_lens` on `BeingConfig` (four touch points each) and the BeingTab control; dial → row cap Off 0 / Subtle 1 / Flavorful 3.
- B4a (sonnet · xhigh): `suppress_lens()` at the assemble call on both paths over signals that exist.
- B7: done (`skills/builtin/understated/SKILL.md`, inactive).

## 7. Branch 6 — `feat/morning-lens` = C1b (opus · max; needs `CD-7`, `C4-07` ratified, persistence)

Observations-only input; `summarizer=None` unless `active_lens` is set and `lens_intensity != "off"`; pinned to `secure_model` with `:cloud` rejected **by tag** (`_is_local_url` is URL-only); scrub → model → scrub; turn-lock try-acquire; either the verbatim-title post-check or B4 applied to the report; make the scheduler's `enable_llm` flag real or delete it; a model handle threaded through `register_proactive_jobs` → `create_autonomous_task` → `MorningReportTask`.

## 8. After — B4b, C2, C3 (§4 Next)

- B4b (opus · high): `is_destructive` / `is_incident` on `MessageSignals`; the entity ∩ finding join with a `FindingStore` injected into the gate. Independent value for `TRUST-1`.
- C2 (opus · xhigh): recurrence remarks as an aside inside a solicited reply, one per `thread_id` per rolling window, sourced from A5 only; judged from a week of persisted reports first.
- C3 (sonnet · high): `/api/skills` with each entry's kind and source directory; raw markdown via `/api/editor/file`; provenance affordance over `[t{id}]`; no `dangerouslySetInnerHTML`; nothing named "observations" or bare "timeline".

## 9. The user-interest half — deferred per `CD-5`; the v1 shape once `RQ-1..9` are ratified and the C1a week has passed

| Piece | Tier | Spec |
|---|---|---|
| `remember` writer in `tools/executor.py`: deterministic phrase list, reason must be a substring of the user's message, `speaker_role ≥ member`, `redact_text` first, Tier-2 refused, echo the stored sentence | opus · high | research §1 |
| Candidate rule in `continuity/consolidation.py`: entity or domain on ≥ 3 distinct days in 30 across ≥ 3 non-ephemeral closed threads; status `candidate`, never injected; 30-day expiry | sonnet · med | research §1 |
| The one confirmation aside (dial-gated, C2-shaped, once per candidate) | opus · high | after B4a and C2's row |
| Interest row as a `PersonaMemory` with a Halbert-side dataclass (topic, origin, evidence, timestamps, status, actor, reason, body_id) and the derived `ObservationStore` `preference` row | opus · high | research §5 |
| Settings section "What I remember about you": list with who / when / how, Forget (or Stop using), Show forgotten; `GET/POST /api/memory/about-you…`; the deterministic "what do you remember about me" tool; edit = forget + re-record | sonnet · xhigh | research §2 |
| Forget orchestrator in `continuity/` mirroring `forget_request`: per-plane report, `complete=False` on a miss; `stale_reason` convention `forgotten_by_user:<turn>` / `lapsed:<date>` / `superseded_by:<id>` | opus · high | research §2, §5 |
| RECALL-v1 with tests T1–T9 asserted on the prompt and the store | opus · max | research §3 |
| Lapse sweep on APScheduler (`MEM-04`): inferred interests lapse at 90 days without evidence | sonnet · med | research §3 |
| "Study this": user-pasted URL verbatim (MEDIUM egress, audited) + `doc_suggester` as a Knowledge-tab suggestion; one writer into an XDG research scope of provenanced markdown files; staged into the SourcePrep knowledge project; citations open (`KNOW-1`); one honest delete; freshness re-fetch later | opus · xhigh | research §4 |
| Manifest line (`RQ-7`) and `ERASURE_LIMITS` text for the research plane | — | with the above |
| A user-editable noun file under `~/.config/halbert/` so inference can see nouns intake does not know (`RQ-4`) | sonnet · med | still no model |

## 10. Haloysius upstream asks (Phase-1 items, none blocking branches 1–4)

- `ObservationStore.delete()` that removes the row and its FTS row, with `PRAGMA secure_delete` as the ledger already does.
- `ObservationStore.save()` respects a user tombstone (`forgotten_by_user:*`) instead of un-staling any duplicate.
- `PersonaMemoryStore.teach()` / `update_preference()` set `memory.source = "user"` so a stated fact gets 0.9, not the inferred 0.7.
- Contradiction detection cannot see "no longer interested in X" (`_extract_subject` matches no subject); the Halbert writer handles negation until it can.
- Not needed: a `VIGILANCE` emotion category — branch 1 mapped it to `ANTICIPATION` (Plutchik's own model).

## 11. Side findings for their own rows

| Finding | Row |
|---|---|
| `rag/trending_discovery.py` sends the detected stack to `api.github.com` on Knowledge-tab open; `rag/freshness.py` calls HuggingFace — both ungated by `CAP_WEB` despite "every egress path gated" | `TRUST-1` |
| `add_url` fetches with no `CAP_WEB` check; `POST /api/rag/add` has no token dependency beyond loopback convention | `TRUST-1`, `KNOW-1` |
| `_is_local_url` is URL-only; no `:cloud` tag assertion exists in `model/` although `being_config.py` states the rule | `TRUST-1` (before any scheduled model call) |
| The scheduler's `enable_llm=False` is a dead flag nothing reads | `MIND-1` |
| `knowledge_scope` is parsed and composed but consumed nowhere; keep for the research scope binding or remove | `KNOW-1` |
| `_check_skill_safety` substring fallback over-blocks (`man mkfs` → CRITICAL) | `SKILL-1` B3 |
| `test_agent_pool_cwd_injection` pins "the framework still does not classify cwd"; update when B3 classifies it | `SKILL-1` B3 |
| `pages/Memory.tsx` is an unmounted ChromaDB browser whose Clear hard-deletes; do not mount it as the "about you" surface | `FENCE-1` |
| The Consolidator's `preferred_entity` rows are last-entity-wins and withheld from the vault; document as machine-work recurrence or retire | `LEDGER-1` |

## 12. Done in this pass, so nobody redoes it

- Rev 2 cherry-picked onto branch 1 and reconciled to rev 2.1 (`ea643a3b`, `5e7302b4`): `title`/`severity` in the row contract, A5 counts `end`, CD-11's noun throughout, branch 1 as shipped.
- B7 + the `kind` field with its parse-time voice-only rule (`66ed1447`); 107 skill tests green.
- `CD-1/4/5/6` logged; `SKILL-1` row; `MIND-1` `C4-04` and `CFG-1` `A2-02` partial lines; Lenses bullet under Next (`87f61bcf`).
- The research brief answered with nine founder calls (`06f873ee`).
- `ROLE-SCOPED-SKILLS` §11 status claims corrected; four stale `TemporalStateLedger` mentions corrected to the state ledger (`MEM-02`) — this commit.
