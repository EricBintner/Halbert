# PACKET → Fable: the lenses wrap-up

**You wrote** `.handoff/HANDOFF-OBSERVATION-LENSES-2026-09-04.md` (rev 2). This is
what has happened since, and the four things left that are yours.

## What changed while you were away

**Branch 1 (`fix/observation-sink`) is built, reviewed, fixed and pushed.** The
event ledger has an owner, an ingestion-time writer, a normalised sink, titles,
severity and retention. Full suite: `5535 passed, 14 skipped`.

Read these three, in this order — they contain things that change your document:

1. `.handoff/REVIEW-BRANCH1-OBSERVATION-SINK-2026-09-05.md` — the five findings.
2. `.handoff/RESULTS-BRANCH1-OBSERVATION-SINK-2026-09-05.md` — what was fixed, plus
   three further defects that scrutiny found and the review did not.
3. `DECISIONS.md`, the ten rows dated 2026-09-05.

**Two of your own claims were wrong and are corrected in the code.** Your §7 A2 row
contract omits `title` while §7 A2c ("redact the title") and §7 A4 (rendering
`[t{id}] Front door opened 07:41`) both assume one — so following the contract
literally left the mappers' prose discarded, which is the half of DEFECT-2 that
motivated the branch. And §7 A5's "count only `type = new`" makes your own
motivating example unreachable: Frigate assigns `sub_label` *after* an object is
first tracked, so `new` rows group as `front_door:person` and "that grey van, three
times" cannot happen. A5 now counts `end` rows.

## Decisions taken 2026-09-05 (all in `DECISIONS.md`)

| # | Decision |
|---|---|
| `CD-11` | The layer is **Lenses** — `~/.config/halbert/lenses/`, `kind: lens`. Chosen over Affinities because your §4 reframe made the layer an interpretation of the observation stream, which is the condition D10 itself named for preferring Lenses. |
| `CD-3` | **(b)** — selection is arithmetic and lens-independent: top N by (count, severity, recency), clamped by the dial. The lens file is **voice only**. No `observes:` block, and no "what this notices" prose either. |
| `CD-2` | **(a)** standing `BeingConfig.active_lens` — now *forced* by `CD-3` rather than merely preferred: a voice-only file carries no domains or keywords, so `SkillMatcher`'s `MIN_SCORE` can never fire. |
| `CD-7` | **(a)** — deterministic report first; the voiced version stays gated on `C4-07` plus persistence. |
| `CD-5` sub | Deferred, with `.handoff/HANDOFF-USER-INTEREST-MEMORY-RESEARCH-2026-09-05.md` opened so it cannot be dropped a third time. |
| — | A5 counts `end`; ledger rows carry severity from an explicit table; retention prunes at construction; `ERASURE_LIMITS` names the ledger; `title` joins the row contract. |

**Still open**: `CD-8`, `CD-9`, `CD-10`. They gate B4+ and C1b, not your work.

## Your four items

### 1. B7 — write the one built-in lens (`high`)

Now a much smaller object than your §8 B7 sketched, because `CD-3`(b) removed
selection from the file entirely. The whole thing is roughly:

```markdown
---
name: <yours>
kind: lens
---

## How it says so
- Understated. State the observation; let it carry its own weight.
- One sentence. Never two.

## What it does not do
- No metaphors unless the reader asked "why".
- No name-dropping hardware for flavour.
```

Constraints, all of them real:

- **Voice only.** The model receives three already-chosen rows and may phrase them.
  It may not choose them and may not add any. Nothing in the file may imply otherwise.
- **Inactive by default** (`active_lens` empty).
- No canon list, no analogy bank, no recommendations section — your §12 trim list,
  and the standing directive that the product never names or recommends AI models.
- `tests/test_skills_builtin.py:39` asserts `set(builtins) == EXPECTED` and `:44`
  asserts `skill.role`; a role-less lens turns both red. Add it to `EXPECTED` and
  scope the role assertion to `kind == "ops"` in the same commit.
- Ship exactly one. The shape has to be reviewable before a second exists.

The bar: your own §4.2 example — *"Third time that grey van's parked out front this
week."* — is entertaining with no wit devices in it at all. The file should make
that kind of sentence likely and a deployed metaphor unlikely.

### 2. Take the user-interest research brief (`high`)

`.handoff/HANDOFF-USER-INTEREST-MEMORY-RESEARCH-2026-09-05.md` is opened but only
framed. Its five question sets are the deliverable. The third — when a remembered
favourite can surface without reading as surveillance — is the one most likely to
sink the feature, and it is named as such.

### 3. Reconcile your document with what shipped (`med`)

`HANDOFF-OBSERVATION-LENSES-2026-09-04.md` is still rev 2 and is now wrong in
places. Needed: `title` in the §7 A2 row contract; A5 counting `end` in §7 and §10
D6; severity in the row contract; the `CD-11` naming through §8, §9 C3 and §10 D3
(D3's "lens is prose in this document, not an identifier" no longer holds — it *is*
the identifier now); `CD-2`/`CD-3`/`CD-7` marked decided in §13; §14's branch list
updated for what branch 1 actually shipped.

### 4. `ROADMAP.md` status columns (`med`)

`MIND-1`'s `C4-04` gains the partial-landing line the branch-1 done-evidence
specifies. `CFG-1` `A2-02` gains the path resolver. Note in the §4 Next bullet that
`CD-11` named the layer, so `LENS-1` has a name when it opens.

## Not yours

Branch 2 (B1+B2+B3), branch 3 (A3/A4/A5), branch 4 (C0/C1a) — opus and sonnet.
Subject-scoped erasure of occupancy rows and the periodic retention job are tasked
separately under `MIND-1`.

## One thing worth carrying into how you review

Two tests written during this work **passed while the defect they targeted was
present** — a worktree guard asserting on a namespace package that resolves locally
even when every submodule loads from another tree, and a redirect reading `MAPPING`
off a finder class when setuptools puts it on the module. Both were caught by
checking that the check worked. Your rev 2 caught the `MagicMock` version of this in
someone else's code; it is worth assuming it is present in your own.
