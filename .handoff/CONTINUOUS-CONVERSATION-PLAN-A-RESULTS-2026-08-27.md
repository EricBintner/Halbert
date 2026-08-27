# Continuous Conversation — Plan A: Execution Results

**Date:** 2026-08-27
**Branch:** `feat/continuous-conversation` (worktree
`~/.config/superpowers/worktrees/Halbert/continuous-conversation`) — **not merged to `main`**.
**Base:** `6c90faa` · **Head:** `d70ba46` · 87 commits · 18,314 insertions / 2,618 deletions
across 86 files.
**Read with:** `.handoff/CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md` (what led here) and
`.handoff/CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md` (the plan itself).

## 1. What landed

All **33 of 33** tasks completed — 27 `DONE`, 6 `DONE_WITH_CONCERNS` (A5, A6b, A6c, A9c,
A11, A12b). Nothing reported BLOCKED, so the run never had to stop for intervention.

Every number below was measured directly on the branch, not taken from a reviewing agent:

| Check | Result |
|---|---|
| Backend suite | `4 failed, 1546 passed` — the 4 are the documented pre-existing model-client vision-fallback failures (`test_phase_d_integration.py`, `test_tool_calling_bridge.py`) |
| `tests/test_thread_e2e.py` (the spec §14 gate) | 4 passed |
| Frontend | 17 files / 126 tests passed |
| `npx tsc --noEmit` | clean |
| `scripts/check_literal_colors.py` | exit 0 — 268 literal palette classes across 35 files, 0 clashing dark neutrals |
| `scripts/check_contrast.py` | exit 0 — every licensed pair clears its WCAG floor in both themes |
| Bot trailers across all 87 commits | none |

Baseline before the run was 1119 backend / 45 frontend, so the branch adds ~427 backend and
81 frontend tests.

Spec §14's definition of done is met: the second message sees the first, `new_thread`
pauses, `tick()` closes with an indexed receipt, a later "as we did…" message gets a
`Pulled in:` hint with no tool call; the timeline renders stored turns with roles and day
dividers; the dropdown, "New Conversation" and session footer are gone; `/api/conversations`
has no callers left in `src/`; `TerminalTile` replays `session.output` on mount, so terminal
tiles from earlier turns no longer go blank.

## 2. Verification of the fixes nobody re-reviewed

The execution harness ran, per task, implementer → spec review (up to 3 fix rounds) → code
quality review (up to 2 fix rounds). A fixed round cap has a structural flaw worth naming:
**the loop ends on a fix, not on a review.** When the last round still found issues, a fixer
addressed them and the task moved on with those findings recorded as `unresolved_quality` —
which overstates the situation, but nothing had confirmed them either.

That left **65 findings across 24 tasks** in an unverified state. A second read-only pass
audited all 65 against the current code — one agent per task establishing RESOLVED /
PARTIAL / NOT_RESOLVED by reproduction rather than argument, then a skeptic per claimed
failure instructed to refute it:

| Outcome | Count |
|---|---|
| Resolved — the defect cannot occur in the current code | 56 |
| Reproduced, but refuted as plan-specified behaviour rather than a defect | 8 |
| Survived adversarial review | **1** |

The single survivor was A4's own performance guard: `TestLargeInputPerformance`'s 250ms
wall-clock assertion could not detect the regression its docstring claimed to guard —
measured on its own message, head 75ms, the bound reverted 114ms, and the original unbounded
A4 code 165ms all pass. Fixed in `d70ba46`, which adds
`test_entity_extraction_stops_at_the_scan_limit`: a marker placed past `_ENTITY_SCAN_LIMIT`
must not be harvested as an entity while the domain boolean must still see it. Verified to
fail on both regression shapes — deleting the slice at the call site with the constant left
alone, and blowing the constant up — and to pass on head.

The eight refutations are worth trusting: each skeptic reproduced the mechanics and then
showed the behaviour was written into the plan or the contracts verbatim (the grow-only
`num_ctx` cache, the A8b budget numbers, `_receipt_snippet`'s matching order, and so on).

## 3. Open follow-ups

Ranked. None of these block the branch; the first one can degrade a working install.

### 3.1 `num_ctx` ceiling has no producer — operational risk

`model/client.py` — `compute_num_ctx`'s `model_max` parameter has no caller anywhere in the
tree. `_do_llm_call` reads `options.get("num_ctx_max")` but nothing sets it, so every model
falls back to `_NUM_CTX_DEFAULT_MAX = 32768`. Before this branch a call with no `options`
sent no `options` block at all and Ollama used its own small default; now every local call
sets an explicit `num_ctx` that grows monotonically per model up to 32k — roughly +2GB of KV
cache for a 7B, enough to OOM a GPU that was previously fine.

This is a **gap in the plan, not a defect in the implementation**: `A10.md` and
`plan-a-contracts.md:138` both prescribe `ceiling = model_max or 32768` and name no source
for `model_max`. The discovery mechanism already exists —
`dashboard/routes/llm.py::_ollama_show_detail` returns `context_tokens`. Either wire that
into `num_ctx_for_model`, or lower `_NUM_CTX_DEFAULT_MAX` until it is wired. Worth doing
before this reaches a machine with a small GPU.

### 3.2 `SendToChat` still promises a new conversation

`src/components/SendToChat.tsx` ships a `newConversation` flag (Shift+click, the
`MessageSquarePlus` "Discuss in new chat" icon, the tooltip "Continue in chat (Shift+click
for new)"), and right-click hard-codes `newConversation: true`. Nothing reads it any more —
`Layout.tsx`, `AgentChat.tsx` and the `hostConversation` bridge all ignore the field. So the
UI offers a new conversation and silently does nothing, which contradicts the one-conversation
model directly. Outside Plan A's §14 scope; it should either map to `new_thread` or the
affordance should go.

### 3.3 "Forget this" is missing exactly when it is wanted

`Timeline.tsx` — `redactableIds` filters to `messageId >= 0`, and a turn appended live
through `turnFromSession` carries `-1` until the next page load. So the control is absent on
the turn the admin has just had, which is precisely the moment someone realises they pasted a
secret, and appears only after a reload.

### 3.4 Smaller items

- `Timeline.tsx` — the `role="feed"` container owns `<section>` day groups, with the
  `role="article"` turns one level below. ARIA's feed pattern expects articles as the feed's
  own children; the intervening section can cost position announcements in some readers.
- `useTimeline.ts:230` — `byDay` is memoised on `[turns]` while `groupByDay` defaults `now`
  to call time, so a page left open across midnight keeps yesterday's "Today" divider until
  the turn list next changes. Cosmetic, self-correcting.
- `documentation/FEATURES.md:359` still advertises `| /api/conversations | GET/POST/DELETE |
  Chat history |`. A12c removed the router, the frontend wrappers and the API-REFERENCE.md
  section, and `tests/test_legacy_conversations_removed.py` pins the 404 — this second table
  was missed.
- `TerminalTile.tsx:189` — `bg-[#1a1b26]` is still a literal hex, and
  `check_literal_colors.py` does not catch the `-[#hex]` arbitrary-value form, so the gate
  passes over it. Spec §11 names this line; Plan B carries the token fixes.
- `threads.py` — `begin_turn` is `@_locked` on a `threading.RLock` and is called
  synchronously from the asyncio path, so a contended write can block the event loop for up
  to `busy_timeout` (5s). Deliberate and documented; the asyncio turn lock already serialises
  turns.
- `model/client.py:606` — `payload["options"]` is now always populated, where it used to be
  set only `if options:`. Every in-tree caller passes explicit options, so nothing regresses
  today.

## 4. What this branch deliberately does not do

Deferred to Plan B/C, as the plan says: live terminal sessions keeping a thread from
auto-closing; the inbound secret scrubber; task notifications in the continuity hint; and
everything in the watched-terminal / task-column / StatusLight track. `compact_boundaries`
ships with no writers — compaction stays default-off.

**Plans B and C are still unwritten.** Their required contents are enumerated in
`.handoff/CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md` §2 and §3.

## 5. Merging

The branch is clean and rebased on nothing newer than `6c90faa`; `main` has moved on with
concurrent work from other sessions. A merge is doc-and-code disjoint from the model-picker
work but has not been attempted — run the suites again after merging, since neither branch
has seen the other.

## 6. Notes on the method, for the next plan

What worked: one implementer per task with a fresh context and the full task text on disk;
spec-compliance review separated from code-quality review; a hard stop on BLOCKED that never
had to fire; reviewers on the strongest model while mechanical implementers ran cheap.

What to change: **budget a verification pass over the last round's findings.** A fixed round
cap ends on a fix, so its final findings are unverified by construction. Here that pass cost
33 agents against 180 for the run itself, and turned 65 alarming-looking entries into one
real item — which is exactly why it was worth running rather than either trusting or
panicking about them.
