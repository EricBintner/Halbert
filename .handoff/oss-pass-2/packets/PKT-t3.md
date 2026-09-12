# PKT-T3 — Verification-evidence ledger + invented-completion eval metric + UI-verify convention

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**T3** — Verification-evidence ledger + invented-completion eval metric + UI-verify convention.

## 2. User problem

Halbert edits its own code and its session notes record repeated premature-success episodes: a turn ends with the machine saying, in first person, that something is fixed or verified, when no verify command was actually run — or was run before the last edit, or was run in a way whose exit status proves nothing (a `||` chain, a backgrounded job, a piped command where the failing stage is not the exit code). Today there is no measured record of "what was actually proven": grep for `verification_evidence|verify_on_stop|verification_status|mark_workspace_edited` over core and tests returns nothing. The per-turn mutation digest (`security/turn_digest.py`, R-06) records what a turn *touched*, but nothing records what a turn *proved*, and nothing goes stale when the next edit lands. For a machine that speaks as the computer itself, grounded in measured data, claiming completion without measured evidence is a direct violation of the voice contract — it is the machine asserting a state of itself it never measured. The founder's recorded failure mode (T3 deep-eval: "the founder's own session notes record repeated premature-success episodes") is the target. Additionally, the merged R-15 eval harness (scorecard + JSONL rows under `halbert_core/evals/`) has no metric dimension for invented completion claims, and there is no written convention distinguishing state-read proof from rendered-UI proof for UI work — a failure mode the founder has personally hit (a UI change "verified" by reading component state while the rendered surface was broken).

## 3. What to build

Three accepted items per the RESHAPE verdict, in one branch, file-disjoint from all hot work.

(1) Verification-evidence ledger — new file `halbert_core/halbert_core/agents/verification_evidence.py`, ported from hermes `agent/verification_evidence.py` with the attributability parser and canonical-vs-ad-hoc distinction kept verbatim. Three SQLite tables (meta / verification_events / verification_state) in one database under `HALBERT_DATA_DIR` (the `utils/platform.py:347` resolver), WAL mode with busy_timeout and the documented fd-leak-aware transaction contextmanager. Feed it from two existing seams, no new ones: (a) the executor's command-result path — where `_run_command` in `tools/executor.py` already produces `exit_code` (`:1013`) and where `record_effect` is already invoked for terminal commands (`:714-723`), also call `record_terminal_result(command, exit_code, cwd)`; (b) the existing write-plane digest feed (`tools/executor.py:645-647`, `record_effect` for WRITE_PLANE_TOOLS) — alongside it, call `mark_workspace_edited(paths)` which stamps `last_edit_at` and merges changed paths (bounded to 200) without touching `last_event_id`. The ledger's core rules, ported verbatim: quote-aware `_split_shell_segments`; `_exit_status_is_attributable` (backgrounding `&`, pipes `|`/`|&`, and `||` disqualify; an `&&` chain proves each member only when exit 0); npm/pnpm/yarn/bun and pytest-spelling equivalence classes; commands are matched against the workspace's canonical verify commands (port — and only port — the ~30-line static detection from hermes `agent/coding_context.py:466-492 detect_project_facts` / `:502-514 project_facts_for`; ad-hoc commands count only when no canonical commands exist for the workspace); `verification_status()` reports `stale` purely by timestamp comparison between `last_event_id`'s recorded time and `last_edit_at` — never a flag someone must remember to clear. Hard constraint from the section file: every command string passes through the Tier-2 scrub (`ingestion/redaction_registry.py`) before persisting, so a secret typed into a shell never lands in a ledger row. The ledger measures exit codes of commands ALREADY RUN — it never runs anything itself and never probes OS state.

(2) Invented-completion-claim rate as an eval metric — S effort, extends the merged R-15 harness. A new deterministic battery beside the consolidation pattern (`halbert_core/evals/consolidation/` carries `rows-*.jsonl` + `SCORECARD-*.md`): scripted turns whose writes are driven directly through the two feed seams, each ending with a completion-style utterance; the metric is the fraction of completion claims made while `verification_status()` is not `passed` for the touched workspace. Rows land as JSONL plus a scorecard section in the same arm/status/recall shape the R-15 scorecard already uses — no model calls anywhere in the instrument (the claim side is templated utterances, the measured side is the ledger).

(3) UI-verify convention — one paragraph added to `documentation/contributing/TESTING.md` (the repo's existing testing-conventions doc): a two-layer verification discipline for UI work stating that state-read proof (component state, store contents, API responses) is not rendered-UI proof; any change touching the dashboard surface is verified by observing the rendered output (screenshot or browser automation against the running app), not by reading state alone. Costs a paragraph, names a failure mode the founder has hit.

DEFERRED (M5b tail, per the verdict and backlog row "T3 (tail) | Stop-gate seam — after the real handler exists"): the stop-gate seam in `agents/state_machine.py` and the verify-on-stop nudge. Do not touch `state_machine.py` in this packet — it is the hottest file in the tree and R-01/R-06/R-12 all touch it; the section file confirmed there is currently no consumer seam (`finish_reason` at `agents/llm_client.py:42/277/489` is a response dataclass field with no consumer). The ledger is built so the later seam is a pure consumer of `verification_status()`.

## 4. What NOT to build

- The stop-gate seam in `agents/state_machine.py` (an ordered list of pure gate callables returning continue(nudge)/pass with a per-turn attempt counter) — deferred to the M5b tail, to be wired in one branch after the opus-tier state-machine work (R-01/R-06/R-12 residue) settles. The section file's grep proves there is no place to hang it today.
- The verify-on-stop nudge (synthesising one bounded `"role": "user"` follow-up at turn end when changed paths are code and status is not `passed`, max_attempts=2, config switch defaulting on) — rides on the stop-gate seam; deferred with it. The FD-2 default-on decision is recorded but nothing is built.
- Anything that RUNS checks: the ledger never executes a command, never spawns a verify run, never probes OS state (open ports, file existence, process lists). It consumes exit statuses of commands already run through the existing executor path. This is the explicit correction in the registry note (hermes :418,545 measures exit codes of commands ALREADY RUN, not OS probes).
- No changes to `tools/executor.py` beyond the two additive feed calls; no changes to `security/turn_digest.py` at all — the ledger is a consumer of the digest's feed sites, not a modification of the digest.
- No turn blocking: nothing in this packet can refuse, delay, or gate a turn. The ledger is passive and additive.
- No OS-state "verification" of its own claims: no port sniffing, no "did the file get written" re-reads as evidence rows — command exit codes only.
- No new hard dependency: stdlib sqlite3 only (Haloysius subtractive contract — exactly two hard dependencies, `pyyaml` and `requests`, stays intact).
- No UI surface: nothing renders the ledger in the dashboard in this packet; a findings/registry surfacing (DIAG-01 style) is a later consumer.
- No migrations or back-compat shims: the SQLite schema is create-only at first open; there are no users with old ledgers.

## 5. Target files
- `halbert_core/halbert_core/agents/verification_evidence.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M, and the RESHAPE is what keeps it M. The ledger is the bulk of it: three SQLite tables with WAL/busy_timeout, the shell-segment parser, the attributability rules, the canonical-command detection (~30 ported lines), and the two seam call-sites — the deep-eval prices this at M with no hot files touched, and the two feed seams already exist (`tools/executor.py:645-647` and the command-result path at `:1013`), so no plumbing is invented. The eval metric is S: it reuses the merged R-15 harness shape (templated arms, JSONL rows, scorecard section) and adds one computed column over ledger state — no model calls, no new framework. The convention paragraph is S by construction. What would have pushed this packet past M — the stop-gate seam plus the verify-on-stop nudge, both M and hot-file-sensitive on `state_machine.py` — is exactly what the RESHAPE defers to the M5b tail, so the accepted slice lands at M. Prerequisites: none beyond the two named seams; it is a consumer of R-06's merged digest feed and R-15's merged harness, both on main.

## 8. UX rationale

The user-facing effect is on the one seamless conversation: the machine stops saying "fixed" or "verified" about itself without measured backing — and when the stop-gate tail later lands, the ledger this packet builds is what makes the one bounded follow-up honest ("I edited these paths and nothing has been run against them since; the last passing evidence predates the edit"). Until then the value is silent: every claim the machine makes can be checked against `verification_status()`, and the invented-completion metric gives the founder a measured rate for the failure mode instead of anecdote. Nothing new appears on any surface in this packet: no panels, no pills, no conversation-list elements, no emoji, no colour (there is no UI at all). The ledger speaks only through the existing voice when queried; it never interrupts a turn, never stages a command, and never executes one — consistent with "commands staged from the UI are staged, never executed" and with the first-person, measured-data contract: the machine reports what it measured (exit codes of commands actually run, staleness by timestamp) and nothing else. No model is ever named; the eval battery uses templated utterances and ledger rows, so the metric itself never touches a model.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/agents/verification_evidence.py` exists and imports cleanly with only stdlib + in-repo imports; no third hard dependency appears in the Haloysius contract.
2. Parser table tests pass: each shell-segmentation case (`&&`, `||`, `|`, `|&`, `&`, quoted segments) is classified with the correct attributability — `||`, pipes, and backgrounding disqualify; an `&&` chain proves each member only at exit 0.
3. Equivalence-class tests pass: npm/pnpm/yarn/bun spellings and pytest-spelling variants of a workspace's canonical verify commands are recognised as the same command; ad-hoc commands count only when no canonical commands exist.
4. Staleness test passes: record a passing verify event, then call `mark_workspace_edited` with a code path, and `verification_status()` reports `stale` by timestamp comparison with no flag cleared by hand; a fresh passing event clears staleness.
5. Seam tests pass: driving `record_terminal_result` and `mark_workspace_edited` through the executor's existing feed paths records rows (command strings Tier-2-scrubbed before persisting — a secret-shaped token in a command never lands verbatim in a ledger row).
6. Self-prune/bounds tests pass: changed-path merge is bounded to 200 entries; WAL/busy_timeout transaction behaves under the documented fd-leak class.
7. The invented-completion-claim battery runs inside the existing eval harness and emits JSONL rows plus a scorecard section in the R-15 shape, computing the claim-while-not-passed rate from ledger state with zero model calls.
8. `documentation/contributing/TESTING.md` contains the two-layer UI-verification paragraph (state-read proof is not rendered-UI proof).
9. `agents/state_machine.py` is untouched by the branch (verified by diff), and no nudge/row is ever appended to a conversation.
10. No baseline regression: the branch's test failures are a subset of the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures at 2026-09-11).

## 10. Verification (measured state, not model judgment)

From a git worktree, run the new ledger test module plus the eval battery deterministically (never bare pytest — the editable install pins halbert_core to the main tree):

`arch -arm64 ./wt_pytest.py halbert_core/tests/agents/test_verification_evidence.py`

(or, from the main tree root: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/agents/test_verification_evidence.py -q`)

That module must contain, and pass, the measured checks: the parser table (one parametrized case per `&&`/`||`/`|`/`|&`/`&`/quoted segment asserting attributable vs disqualified), the equivalence-class test (npm/pnpm/yarn/bun and pytest spellings of one canonical command), the staleness test (record pass → `mark_workspace_edited` → assert `verification_status() == "stale"`; record fresh pass → assert not stale), the seam test (drive the executor feed paths, assert scrubbed rows in the SQLite store under a tmp `HALBERT_DATA_DIR`), and the self-prune test (changed-path list capped at 200). Then run the eval battery's row emitter (the new battery's `run_all`-equivalent beside `halbert_core/evals/consolidation/`) and assert on disk: a `rows-*.jsonl` whose rows carry the invented-completion-claim rate column computed from ledger state, and a `SCORECARD-*.md` section in the R-15 arm/status shape — zero model calls asserted by the harness's own gate. Finally, `git diff --name-only main...HEAD | grep agents/state_machine.py` must return nothing (measured proof the deferred seam stayed deferred), and a full `arch -arm64 ./wt_pytest.py halbert_core/tests` run's failure list must diff-clean against the recorded 2026-09-11 baseline.

## 11. Exclusions

Stop-gate seam (`agents/state_machine.py` gate-callable list + per-turn attempt counter) → M5b tail, per backlog row "T3 (tail) | Stop-gate seam — after the real handler exists"; to be wired in one branch after the opus-tier state-machine residue settles, as a pure consumer of `verification_status()`. Verify-on-stop nudge (bounded `"role": "user"` follow-up, max_attempts=2, config switch defaulting on per FD-2) → same M5b tail, same branch; it rides on the seam. Dashboard surfacing of ledger state (a findings/registry view in the DIAG-01 shape) → later consumer packet once DIAG-01's registry exists; this packet builds no UI. Reference reading for the deferred seam: hermes F13 decompiled agent loop → READ-LATER per the backlog ("If the state-machine stop-gate seam (T3) needs a reference"), consulted when the tail is dispatched, not now. Anything beyond ~30 lines of hermes `agent/coding_context.py` canonical-command detection is out of scope — the rest of HM04-C3 (coding-context enrichment) is not this packet's and goes nowhere here. No migration, back-compat, or deletion of any superseded data, per the standing no-users rule.

---

## OSS reference

hermes agent/verification_evidence.py:418,545 (exit codes of commands ALREADY RUN, not OS probes).

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
