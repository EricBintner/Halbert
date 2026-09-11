# TODO: Observation lenses and the user-interest half — everything still open

**Date**: 2026-09-05 · **Updated**: 2026-09-06 · **Status:** ACTIVE — the open-work list for this workstream

> **2026-09-06 — branches 1 and 2 are merged to `main` (`755a3e29`, `3efd3145`).**
> Verified on the merged tree, not from the branch logs: full suite `5598 passed,
> 14 skipped`. §2's first two residue rows and the whole of §3 are done and struck
> through below. Nothing else in this file has moved.
>
> **Landed:** A0, A1, A2, A2b, A2c · B1, B2, B3 · B5's `kind` field · B7 · the
> worktree-isolation conftest · retention pruning at construction · `ERASURE_LIMITS`
> naming the ledger · severity at the sink · `title` in the row contract.
>
> **2026-09-06/07 update.** `CD-8`, `CD-9` and `CD-10` are decided
> (`DECISIONS.md`), so **branches 3, 4 and 5 are unblocked**. `C4-07` and
> `C2-03` are still unratified and gate only branch 6 and C2. §11's two egress
> leaks are closed (`841697cf`), as are subject-scoped occupancy erasure, the
> daily retention job and `DOCS-1`.
>
> **2026-09-07 — branch 3 is merged (`21a52e61`).** A3, A4 and A5 are done;
> full suite `5667 passed, 14 skipped`. Two things the work settled that the
> spec left implicit: motion is event-only (a moment, not a condition), and
> both observation headers are now paid for only once a line fits under them,
> which the pre-A4 code did not need and the split does.
>
> **Still open, in dependency order:** branch 4 (C0/C1a) → the `CD-1` gate →
> branches 5 and 6 → §8 and §9. `RQ-1..9` gate §9 only. `C4-07` and `C2-03`
> are still unratified and gate branch 6 and C2.
>
> **2026-09-07 — every open branch is merged (`58ce4b1d`); `git branch
> --no-merged main` is empty.** Six merges beyond branch 3: SEC-9 and SEC-2/3,
> the guest persona (twice — that worktree is live), `feat/attunement-halbert`
> (which contained all nine of `fix/observation-text-normalisation`, so §2's
> merge row is discharged and rev 2.1 won as it said it should), and the Rust
> crates. Full suite `6221 passed, 15 skipped, 6 xfailed`, plus one pre-existing
> flake named in the handoff. **Six conflicts, three of them judgment calls, are
> written up for review in `HANDOFF-INTEGRATION-MERGE-PASS-2026-09-07.md` — one
> of them changed what `feat/guest-persona` intended and wants its owner's
> sign-off.**
>
> **2026-09-07 — scrutiny pass (`e37ee1be`).** A4 was merged built, tested and
> reaching no prompt: both render points accepted `world_observations` and no
> caller passed one. Wired, plus three defects only visible end to end (a
> duplicated arrival line, grounding that changed mid-turn, an unheaded tool
> list under the "not instructions" header). `ERASURE_LIMITS` had been amended
> to credit `forget_subject`, which nothing calls — corrected, with a test.
> Full suite `5698 passed`.
>
> **Built and deliberately not yet wired** — neither is a defect, both are
> stated so nobody reads them as live:
> - `TimelineStore.count_by_entity` (A5) has no caller until C1a consumes it
>   (branch 4, next).
> - `TimelineStore.forget_subject` has no caller and no user-facing door. It
>   belongs with the forget orchestrator in `RQ-6`, which the research brief
>   already owns; `ERASURE_LIMITS` no longer claims otherwise.
> - A3 registered the HA predicates as re-observable and `decide()` returns
>   PROBE on a stale lock row, but nothing *consults* `decide()` on the
>   answering path — the classification is right and no caller acts on it.
>   Defining PROBE for an HA subject as a live Home Assistant fetch is the
>   remaining half, and belongs with whoever owns the answering path.
>
> **Highest-value thing not in any branch:** §11's first two rows. Two egress paths
> reach the network with no `CAP_WEB` gate, against a stated invariant that every
> egress path is gated. That is a live leak, not a plan gap, and it outranks the
> remaining lens work.
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
| Periodic retention job: `cleanup(90)` runs at construction (**landed**); the daemon that never restarts still grows | sonnet · med | APScheduler under the heartbeat (`MEM-04`); `RETENTION_DAYS` is the constant |
| Subject-scoped erasure of `occupancy_change` rows (a named person's movement history; `timeline_events` has no `request_id`) | opus · high | `ERASURE_LIMITS` names the ledger as unreached today; keep that sentence true until this lands |
| DetectorRunner → `add_event`; rewrite `_scan_discovery` / `_check_critical_conditions` against `DiscoveryEngine` methods that exist | sonnet · high | until it lands a sysadmin ledger receives only VisualWatcher anomalies (dispatch §3.2) |
| `PatternInferrer.infer_from_timeline` needs a since-last-run watermark before anything schedules it (re-upserts its whole window; ~7× inflation at a daily cadence) | sonnet · med | or scope it out; nothing calls it today |
| The affective half: worries reach the prompt only by ~12 % random intrusion, emotions never; `to_prompt_block()` has no consumer | — | deferred explicitly under `CD-10`; `C4-05` territory |
| ~~Merge branch 1 into main; the handoff exists in two versions (rev 2 + D10 on `fix/observation-text-normalisation`, rev 2.1 here, a descendant) — take this branch's copy~~ **DONE 2026-09-07** | — | Merged as part of `c26222c8`; rev 2.1 kept, as this row said to |

## 3. ~~Branch 2 — `feat/skills-wired` = B1 + B2 + B3~~ — **DONE, merged `3efd3145`**

All three of DEFECT-1's breaks are closed. What the work found on top of the
spec, all measured before the fix:

- `default_skill_dirs()` reads `Path.cwd()`, so with cwd = `$HOME` the daemon
  loaded **twelve unrelated Claude Code skills** from `~/.claude/skills` as
  Halbert skills — which B2 would have put into `messages[0]`. `daemon_skill_dirs()`
  is builtin + `~/.config/halbert/skills` and nothing else.
- `SENSITIVE_PATHS` held literal tildes while `_classify_write` compares against
  expanded paths, so `~/.ssh/`, `~/.gnupg/` and `~/.config/` matched nothing. A
  write to `$HOME/.config/halbert/skills/evil.md` was MEDIUM with no confirmation.
- A same-named user file replaced a builtin outright, dropping its
  `protected_paths`. Refused now, at WARNING.
- `cwd` was never classified: `rm grub.cfg` with `cwd=/boot` was MEDIUM with no
  confirmation while `cd /boot && rm grub.cfg` was HIGH.
- The blocked-command fallback matched anywhere in the string, so `man mkfs` was
  CRITICAL and blocked. Anchored to the head of each shell segment.

**Left open deliberately:** `which mkfs.ext4` is still blocked by the *base*
classifier's own unanchored `mkfs\.` regex — the same defect one level down,
with a far wider blast radius to change. Its own row in §11.

Original spec, kept for reference:

- B1: trusted list only (`builtin` + `~/.config/halbert/skills`); no cwd; same-name override of a builtin refused or flagged; skill dirs into `SENSITIVE_PATHS` with the literal-`~/.config/` bug fixed; acceptance checks for the three routing effects that go live with the matcher alone.
- B2: the seam is `AgentStateMachine._build_messages`; cap per skill and in total with a logged marker; the lens cap (250) is a separate number.
- B3: install on `self.tools.safety` after intake, clear in the turn's `finally`, re-install on `confirm_action()` resume; classify the `cwd` tool argument; anchor the substring fallback to the first token; test a rule only the skill supplies (`zpool destroy*`), not `mkfs` which the base classifier already blocks.
- `DOCS-1`: `ROLE-SCOPED-SKILLS` §11 status claims corrected 2026-09-05. **Now due**: B1–B3 have landed, so flip the §12 annotations from "verified end to end against the live daemon" (it was verified through a directly-constructed matcher) to what is now actually true.

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
- ~~B4a: `suppress_lens()` at the assemble call on both paths over signals that exist.~~ **DONE 2026-09-10** on `feat/user-interest-memory`, because RECALL-v1 could not stop keeping a second copy of the list until it existed. `halbert_core/skills/suppression.py`, wired at `_composed_prompt_block`; it drops lens-kind matches only, and refuses an explicitly invoked lens out loud on the response stream. `lens_intensity` is read but not yet a `BeingConfig` field — B6 adds it, and absent reads as "" rather than "off".
- B7: done (`skills/builtin/understated/SKILL.md`, inactive).

## 7. Branch 6 — `feat/morning-lens` = C1b (opus · max; needs `CD-7`, `C4-07` ratified, persistence)

Observations-only input; `summarizer=None` unless `active_lens` is set and `lens_intensity != "off"`; pinned to `secure_model` with `:cloud` rejected **by tag** (`_is_local_url` is URL-only); scrub → model → scrub; turn-lock try-acquire; either the verbatim-title post-check or B4 applied to the report; make the scheduler's `enable_llm` flag real or delete it; a model handle threaded through `register_proactive_jobs` → `create_autonomous_task` → `MorningReportTask`.

## 8. After — B4b, C2, C3 (§4 Next)

- B4b (opus · high): `is_destructive` / `is_incident` on `MessageSignals`; the entity ∩ finding join with a `FindingStore` injected into the gate. Independent value for `TRUST-1`.
- C2 (opus · xhigh): recurrence remarks as an aside inside a solicited reply, one per `thread_id` per rolling window, sourced from A5 only; judged from a week of persisted reports first.
- C3 (sonnet · high): `/api/skills` with each entry's kind and source directory; raw markdown via `/api/editor/file`; provenance affordance over `[t{id}]`; no `dangerouslySetInnerHTML`; nothing named "observations" or bare "timeline".

## 9. The user-interest half — **the loop is built and green on `feat/user-interest-memory`**, 2026-09-10

`RQ-1`, `RQ-3`, `RQ-5`, `RQ-6` and `RQ-8` were live-decided while building and are recorded in `DECISIONS.md`. What ships on the branch is the whole explicit path: **say it → stored → mirrored → listed → it colours a turn → stop using it → turns stop carrying it → remember it again → forget it → gone from both planes.** `tests/test_interest_lifecycle.py` asserts exactly that sequence with nothing stubbed between the tool and the disk; if it passes, the feature works.

The **inferred** path is built too, as of the same day. Recurrence proposes, a person decides, and the machine forgets its own guesses on a clock it never applies to a person's words:

**noticed on 3 distinct days across 3 non-ephemeral threads in 30 → candidate → asked once, or answered from the list → confirmed → recalled → lapses at 90 days without evidence.**

`tests/test_interest_aside.py` walks that end to end with nothing stubbed. Both confirmation doors call one promotion (`continuity/confirm.py`) so a candidate confirmed by voice cannot behave differently from one confirmed by button.

| Piece | Tier | Spec |
|---|---|---|
| ~~`remember` writer: deterministic phrase list, reason must be a substring of the user's message, `speaker_role ≥ member`, `redact_text` first, Tier-2 refused, echo the stored sentence~~ | **DONE** | `tools/remember.py` |
| ~~Candidate rule: entity or domain on ≥ 3 distinct days in 30 across ≥ 3 non-ephemeral closed threads; status `candidate`, never injected; 30-day expiry~~ | **DONE** | `Consolidator.propose_interests`, on the idle tick |
| ~~The one confirmation aside (dial-gated, C2-shaped, once per candidate)~~ | **DONE** | `continuity/interest_aside.py`; `tools/confirm_interest.py` and the Settings "Noticed, not remembered" section are its two answers |
| ~~Interest row as a `PersonaMemory` with a Halbert-side dataclass and the derived `ObservationStore` `preference` row~~ | **DONE** | `continuity/interests.py` |
| ~~Settings section "What I remember about you"; `GET/POST /api/memory/about-you…`; the deterministic "what do you remember about me" tool~~ | **DONE** | `continuity/about_you.py`, `tools/about_you_tool.py`, `dashboard/routes/memory.py`, `AboutYouCard.tsx` |
| ~~Forget orchestrator mirroring `forget_request`: per-plane report, `complete=False` on a miss; the `stale_reason` convention~~ | **DONE** | `continuity/forget_interest.py` — two verbs per `RQ-6` |
| ~~RECALL-v1 asserted on the prompt and the store~~ | **DONE** | `continuity/recall_interest.py`, wired at `state_machine._interest_block` |
| ~~Lapse sweep (`MEM-04`): inferred interests lapse at 90 days without evidence~~ | **DONE** | `continuity/interest_sweep.py`, once a day off the idle tick rather than its own scheduler job — proposing and retiring are two halves of one mechanism |
| "Study this": user-pasted URL verbatim (MEDIUM egress, audited) + `doc_suggester` as a Knowledge-tab suggestion; one writer into an XDG research scope of provenanced markdown files; staged into the SourcePrep knowledge project; citations open (`KNOW-1`); one honest delete; freshness re-fetch later | opus · xhigh | research §4 |
| Manifest line (`RQ-7`) and `ERASURE_LIMITS` text for the research plane | — | with the above |
| A user-editable noun file under `~/.config/halbert/` so inference can see nouns intake does not know (`RQ-4`) | sonnet · med | still no model |

**Four traps, each measured rather than reasoned about, that the next person here will otherwise re-find:**

- **No colon in the canonical content.** The engine's `_extract_subject` matches `interested in X` and returns `interest in X`, which is what makes a withdrawal supersede rather than accumulate beside the interest. `"User is interested in: sailing"` extracts `None`, and with no subject every interest reads as contradicting every other — six stated interests collapsed to two, and "sailing" replaced "thinkpads". The research brief's §5 prescribes the colon form and is **wrong** about it.
- **A stated fact needs the `user_stated` tag, not just the provenance.** §10 below says a writer "must set `source="user"` itself". Measured against the engine as it stands, that alone calibrates at **0.7** — the inferred confidence. `0.9` needs `Provenance.USER_ORGANIC` *and* the tag, which is what `teach()` does internally.
- **The record carries the status, not the mirror.** RECALL-v1 reads status from the `PersonaMemory`, because under Singular Entity the observation store is body-local and does not travel. Marking only the mirror stale means the person asked for a fact to stop being used and it kept appearing.
- **`smart_add` merges; it does not replace.** A candidate and its confirmation share an id *and* their content, so the second is treated as a duplicate and merged — the write returns success and the status stays `candidate`. Promotion mutates the row and calls `_save_to_disk`, then `confirm_memory()` for the engine's own confirmation count. This is the fourth appearance of one shape in this workstream: a green-looking write that changed nothing.
- **Read the store through `cognition_wiring`, never `PersonaMemoryStore` directly.** `routes/memory.py` has a module-local body-local accessor for the peer endpoints, which is right for a peer and wrong for anything user-facing: `_create_memory_store()` returns a proxy to the canonical host, so a Settings page on the body-local one shows an empty list on the very node where the writes went somewhere else.

## 10. Haloysius upstream asks — four landed 2026-09-06; a fifth fixed 2026-09-10; two still open

**Unmerged and load-bearing:** Halbert's about-you tests now depend on Haloysius `fix/sqlite-thread-affinity` (`95ecaad`), which is on a branch, not `main`. `ObservationStore` and `RecallEventRecorder` each cached one `sqlite3.Connection` per instance, and a connection belongs to the thread that opened it — so the dashboard routes (event-loop thread) and `remember` (agent turn) could not share a store. The forget endpoint reported that it could not reach the observation plane, which is the worst place for it to surface. In `RecallEventRecorder`, which is fail-soft by contract, the same fault was *silent*: recall events stopped being recorded on every thread but the first. Fixed with per-thread connections; 64,616 engine tests green. **Check out that branch or merge it, or Halbert's route tests fail.**

Two asks stand, both found while building the forget path:

- **`ObservationStore.delete_by_memory(memory_id)`**, symmetric with `mark_stale_by_memory`. Nothing returns a row by `source_memory_id`, so a hard forget enumerates the mirror through FTS and keeps only exact `source_memory_id` matches. The search is the enumeration, never the decision — but a topic with no shared FTS token is unreachable, and the report has to say the plane was not reached rather than claim it was.
- **A public metadata setter on `PersonaMemoryStore`.** `confirm_memory`, `correct_memory` and `add_keywords` each mutate and persist, but there is no general one, so `_set_status` mutates the object from `get()` and persists through `_save_to_disk`. A peer-backed store may expose neither, which is why that function returns a reason instead of a bool.

Original four, on Haloysius `main`, pushed. API facts: [`/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-OBSERVATION-LENSES-UPSTREAM-ASKS-2026-09-06.md`](file:///Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-OBSERVATION-LENSES-UPSTREAM-ASKS-2026-09-06.md). Nothing in §9 waits on the engine any more.

| Ask | Landed |
|---|---|
| `ObservationStore.delete()` with `PRAGMA secure_delete` | `2648e72` |
| `save()` respects a `forgotten_by_user:` tombstone | `2648e72` |
| `teach()` / `update_preference()` set `source = "user"` | `324f186` |
| Contradiction detection sees "no longer interested in X" | `4f95418` |
| A `VIGILANCE` emotion category | not needed, as branch 1 assumed — `EmotionCategory.ANTICIPATION` is present in both persona modules |

What changes on our side:

- **`ERASURE_LIMITS`**: the observation plane is reached now, so the sentence naming it unreached stops being true once we call `delete()`. It removes the row, retires the external-content FTS entry (a reused rowid would otherwise inherit its terms), runs under `secure_delete` and ends with a WAL truncate checkpoint — the engine's test asserts the phrase is absent from `observations.db` **and** `observations.db-wal`. `False` on a miss is the per-plane report's `complete=False`.
- **`RQ-6` is no longer forced**: both verbs exist. "Stop using" is `mark_stale(id, f"{USER_TOMBSTONE_PREFIX}{turn}")` — reversible, auditable, and no longer resurrectable by a consolidation pass, which is what `save()` returning `None` buys. "Forget" is `delete()`. `USER_TOMBSTONE_PREFIX` is importable from `haloysius.memory_v2.observation_store`, so our `stale_reason` convention and the engine's check cannot drift apart.
- **The `remember` writer**: if it builds its own `PersonaMemory` rather than calling `teach()`, it must set `source="user"` itself — `metadata["source"]` calibrates nothing. A stated interest then clears the ≥ 0.7 extraction threshold in `Consolidator._extract_observations` immediately.
- **Negation**: only "interested in X" is covered upstream (both polarities, trailing "anymore" stripped, the subject qualified so it cannot collide with a same-noun memory). "No longer uses X", "stopped X" and the rest still match nothing, so the writer keeps handling those — ask upstream with the phrasing if we want them. Contradiction detection is still gated on the embedder clearing `similarity_threshold` (0.85) at `smart_add` step 2.

## 11. Side findings for their own rows

| Finding | Row |
|---|---|
| `rag/trending_discovery.py` sends the detected stack to `api.github.com` on Knowledge-tab open; `rag/freshness.py` calls HuggingFace — both ungated by `CAP_WEB` despite "every egress path gated" | `TRUST-1` |
| `add_url` fetches with no `CAP_WEB` check; `POST /api/rag/add` has no token dependency beyond loopback convention | `TRUST-1`, `KNOW-1` |
| ~~`_is_local_url` is URL-only; no `:cloud` tag assertion exists in `model/` although `being_config.py` states the rule~~ — **fixed as SEC-21, 2026-09-08**: `is_local_model()` at five sites; it had fired live (both chat and specialist were `:cloud`) | `TRUST-1` |
| The scheduler's `enable_llm=False` is a dead flag nothing reads | `MIND-1` |
| `knowledge_scope` is parsed and composed but consumed nowhere; keep for the research scope binding or remove | `KNOW-1` |
| ~~`_check_skill_safety` substring fallback over-blocks (`man mkfs` → CRITICAL)~~ — **fixed** `875d8f95` | `SKILL-1` B3 |
| The **base** classifier's `mkfs\.` regex is unanchored the same way: `which mkfs.ext4` is CRITICAL and blocked. Not fixed with B3 — the base pattern set is large and loosening its matching could unblock something genuinely dangerous | `TRUST-1` |
| ~~`test_agent_pool_cwd_injection` pins "the framework still does not classify cwd"~~ — **narrowed to the base classifier, with a companion asserting the skill pass now does** (`875d8f95`) | `SKILL-1` B3 |
| `pages/Memory.tsx` is an unmounted ChromaDB browser whose Clear hard-deletes; do not mount it as the "about you" surface | `FENCE-1` |
| The Consolidator's `preferred_entity` rows are last-entity-wins and withheld from the vault; document as machine-work recurrence or retire | `LEDGER-1` |

## 12. Done in this pass, so nobody redoes it

- Rev 2 cherry-picked onto branch 1 and reconciled to rev 2.1 (`ea643a3b`, `5e7302b4`): `title`/`severity` in the row contract, A5 counts `end`, CD-11's noun throughout, branch 1 as shipped.
- B7 + the `kind` field with its parse-time voice-only rule (`66ed1447`); 107 skill tests green.
- `CD-1/4/5/6` logged; `SKILL-1` row; `MIND-1` `C4-04` and `CFG-1` `A2-02` partial lines; Lenses bullet under Next (`87f61bcf`).
- The research brief answered with nine founder calls (`06f873ee`).
- `ROLE-SCOPED-SKILLS` §11 status claims corrected; four stale `TemporalStateLedger` mentions corrected to the state ledger (`MEM-02`) — this commit.
