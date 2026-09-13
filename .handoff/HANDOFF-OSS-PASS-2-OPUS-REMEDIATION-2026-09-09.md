# Handoff — opus-tier oss-pass-2 remediation

Written 2026-09-09, for whoever (or whichever agent) picks up the opus-tier half of the oss-pass-2 remediation. Sonnet-tier work was executed the same day in a separate session; see "What's already done" below before touching anything — do not re-derive or collide with it.

## What this is

The second OSS reverse-engineering pass (`.handoff/OSS-REVERSE-ENGINEERING-PASS-2-2026-09-09.md`) audited every module Halbert lifted from OpenClaw/Hermes and found: **the ported modules are solid, often stronger than the origin** (fail-closed defaults, no model names, DB constraints instead of cursor discipline) — **the wiring seams are not**. 181 confirmed gaps (20 high), 105 confirmed bugs. The remediation plan (`.handoff/oss-pass-2/remediation_plan.md`) turns that into fifteen packets, R-01…R-15.

This handoff covers the **11 packets (+ two phases of a twelfth) tiered opus/xhigh-or-max** in a companion triage doc: `.handoff/OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md`. Read that file's tier table first — it has the *why* for every tier assignment. This handoff is the dispatch brief; the actual phase-by-phase spec for each packet lives in `remediation_plan.md` §4 and is **not duplicated here** — line numbers and phase text drift, and the remediation plan is the refuter-corrected source of truth. Read the packet's own section there before writing code.

## What's already done (sonnet-tier, do not redo or collide)

Branch `fix/remediation-sonnet-batch-1`, worktree `.claude/worktrees/remediation-sonnet-batch-1` (not yet merged to main as of this writing). Commits `a3cbc598`, `54e05f81`, `275d9a39`:

- **R-15 (eval harness) — done**, Phases A/B/C all landed: `continuity/recall_eval.py`, `continuity/verdict.py`, `continuity/eval_consolidation.py` and their tests. Two gaps explicitly deferred and flagged in the tier-assignment doc: A02-G15 (fingerprint-skip replay, low/optional) and A02-G3 (a RECOVERY arm over `ReceiptIndex` — genuinely new mechanism design, not a bug fix; the audit's own proposed fix needs per-question retrieval the current `Arm.policy(thread, region) -> Retained` contract can't carry without either breaking the pinned "policy sees only the region" test or restructuring how `_run_arm` builds the answerer). **If your packet touches `continuity/recall_eval.py` or `continuity/verdict.py`, diff against this branch first** — none of the 11 opus packets list those files, so this should be a non-issue, but check.
- **R-03, R-13, R-12 Phase A** are queued sonnet-tier work, not yet started as of this handoff. If you reach them before the sonnet session does, coordinate — don't duplicate.

None of R-15/R-03/R-13/R-12A appear in the opus packets' file lists below, so there should be zero overlap. The one thing to actually check before starting: `agents/state_machine.py` and `dashboard/routes/agent.py` are hot files shared across *most* of the opus packets themselves (see below) — that conflict is between opus packets, not with the sonnet branch.

## The opus-tier packets

From `.handoff/oss-pass-2/remediation_plan.md` §4. Model/effort per the tier-assignment doc:

| Packet | Title | Effort | FD gates (still open) | Depends on |
|---|---|---|---|---|
| R-01 | Talk-door ordering, interrupt algebra | max | FD-1, FD-2 | — (file-disjoint, can start immediately) |
| R-08 | Permission lattice: ask axis, approvals, leases, halt | xhigh | FD-5, FD-6, FD-7 | — (file-disjoint, can start immediately) |
| R-09 | MCP client boundary | high | FD-8, FD-9, FD-10 | — (file-disjoint, can start immediately) |
| R-05 | Redaction registry, Tier-2 choke point | high | FD-15, FD-24 | — (blocks R-06/R-07/R-10) |
| R-06 | Echo guard, display projection, turn digest | high | FD-16 | R-05 |
| R-07 | execute_code hardening | xhigh | FD-17, FD-18 | R-05 |
| R-10 | Speech egress: one pipeline, budget hint, sanitizer | high | FD-4 | R-05 |
| R-04 | Conversation store + state ledger hardening | xhigh | FD-11 | — (feeds R-11/R-12/R-14) |
| R-02 | Claims, admission graph, guest routes, voice provenance | xhigh | FD-14 | R-08 |
| R-11 | Skills plane | xhigh | FD-19, FD-20 | R-04 |
| R-14 | Memory promotion follow-through | xhigh | FD-22 | R-04; Phase D needs a Haloysius Option C coexistence review |
| R-12 (Phases B/C only) | Session tree: compaction v0 rotation writer + branch summaries | high | FD-3 | R-04 (Phase A is sonnet-tier, done separately) |

**Dispatch order** (plan's own, dependencies-first): R-01 → R-09 → R-08 → R-05 → R-06 → R-10 → R-07 → R-04 → R-02 → R-11 → R-14 → R-12. R-01/R-08/R-09 are mutually file-disjoint and the natural first wave — good candidates for parallel worktrees or an `ultracode` fan-out if you want that (it's an explicit opt-in; this handoff doesn't invoke it, it just notes the packets are shaped for it).

**Named hot files** shared across ≥2 opus packets (sequence within a worktree, or split by file if running packets in parallel): `agents/state_machine.py` (R-01, R-05, R-06, R-07, R-10, R-11), `dashboard/routes/agent.py` (R-01, R-06, R-11), `agents/conversation_sqlite.py` (R-04, R-11, R-12), `agents/threads.py` (R-12, R-14), `tools/executor.py` (R-06, R-09, R-11), `tools/safety.py` (R-09, R-11), `tools/role_gate.py` (R-02, R-08), `mcp/config.py`/`mcp/server.py` (R-05 owns the response seam/registry call; R-09 owns loader/transport).

## Founder decisions — the real blocker

Most of these packets have phases explicitly gated on a founder decision (FD-N) that has **not been decided yet**. The remediation plan gives every FD a recommended default (`remediation_plan.md` §7), but per the packets' own STOP conditions, several are hard gates — read the packet's STOP conditions before assuming the default is safe to just run with.

Separately, and **not yet reconciled with the FD-N list**: `.handoff/oss-pass-2/section_permissions-consent-security.md` has its own "Open founder decisions" list (F-A1…F-A11) from the discovery half of the same pass, produced independently of the FD-N numbering in the remediation plan. There is real overlap — e.g. F-A7 ("do internal tool results route through `redact_result`?") is the same question as FD-24 and is *resolved by* R-05/R-07/R-09 per the plan; F-A5 (sealed secrets) and FD-15 (redaction min length) sit in the same neighborhood. Whoever answers founder decisions for this dispatch should treat the FD-N list in `remediation_plan.md` §7 as authoritative for packet-gating purposes, and check F-A1–F-A11 for anything the FD-N list missed, not the reverse.

**Practical recommendation**: don't block the file-disjoint first wave (R-01, R-08, R-09) on FD answers — start the ungated phases (each packet's own phase breakdown marks which phases are gated vs. not) and surface the specific FD question when that phase is actually reached, the way the packets themselves are written to do (STOP and report, don't guess).

## Execution conventions (same as the sonnet work)

- **Worktree**: `.claude/worktrees/<name>` off main, one per packet or per parallel batch. `git worktree add .claude/worktrees/<name> -b fix/<name>`.
- **Tests**: from the worktree root, `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py halbert_core/tests/ -q`. **Use the venv python explicitly** — `./wt_pytest.py`'s shebang resolves to system python3, which is missing `pytest-asyncio` and fails on `--asyncio-mode=auto`. The wrapper exists because the shared venv's editable install pins imports to the main tree; it strips that and re-resolves to the worktree's own `halbert_core`.
- **TDD**: every packet's own "origin tests to mirror" list names real test files in the two origin repos, both present on this machine: `/Volumes/Thunderbolt/AI/openclaw` and `/Volumes/Thunderbolt/AI/OSS/hermes-agent`. Re-derive Halbert-side tests from those named tests' *behavior*, not by copying — the origin uses different fixtures/framework (TS/Vitest for openclaw, pytest for hermes). Red-first, as the sonnet work did.
- **Commits**: pathspec-scoped (`git add <specific files>`, never `-A`), no attribution trailers (project + global CLAUDE.md rule), one commit per phase or per coherent fix group.
- **Line numbers drift**: `audit_overview.md`/`merged_audits.json` line numbers are refuter-corrected but still drift as the tree moves. Re-open the actual file before trusting a cited line.
- **The six lost-audit units** (A06 scheduler, A08 store, A10 tts, A11 lattice, A13 skills, A15 heartbeat — relevant to R-03/R-04/R-09/R-10/R-11) have truncated fix text in `lost_units_digest.md`; `lost_units_verdicts.md` has the refuter's full per-item reasoning and is the one to read for those.
- **STOP conditions are real, not decoration**: every packet in `remediation_plan.md` §4 lists STOP conditions (e.g. R-09: "do not port SSRF guards, OAuth or discovery locks — refuted"; R-08: "no LLM anywhere in the evaluator"). These encode refuted gaps and standing directives — violating one re-opens a question the audit already closed.

## Verifying a clean baseline

Before starting any packet, confirm main + your worktree pass cleanly: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py halbert_core/tests/ -q` should show 0 failures (7776 passed, 15 skipped, 6 xfailed as of `fix/remediation-sonnet-batch-1` on top of main `f22a57b4`). If your worktree shows pre-existing failures unrelated to your packet, stop and report rather than attributing them to your own change.
