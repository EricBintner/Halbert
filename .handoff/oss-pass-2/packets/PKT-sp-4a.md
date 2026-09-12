# PKT-SP-4a — Fix /help /h drift in RESERVED_SLASH_BUILTINS

Tier: **sonnet**   Milestone: **M2**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Land immediately (step 0), by user directive.**

---

## 1. Packet

**SP-4a** — Fix /help /h drift in RESERVED_SLASH_BUILTINS.

## 2. User problem

The terminal page handles two slash commands the skills plane does not know about. Terminal.tsx dispatches on slash-command literals in two places in the same file: handleSlashCommand (line 153, the pre-execution hint path) and handleAICommand (line 260, the execution path). handleAICommand claims '/explain' '/e' '/fix' '/f' '/dryrun' '/d' — and at lines 281-287 also claims '/help' and '/h', rendering the "Available Commands" card. But RESERVED_SLASH_BUILTINS in halbert_core/halbert_core/skills/reserved.py (the frozenset at lines 45-50) lists only {model, explain, e, fix, f, dryrun, d}. 'help' and 'h' appear nowhere in reserved.py (verified by grep: zero matches). The consequence is a live name trap: the loader's refusal at skills/loader.py:261-279 calls is_reserved_skill_name(), which reads RESERVED_SLASH_BUILTINS via _static_reserved_names(), so a skill named 'help' (or carrying alias 'h') is admitted at load and then shadowed at the composer — the user types /help meaning the built-in help card and the skill either never fires or, worse, fires in a context where the user meant the terminal's own help. R-11 restored "live reserved names" as an invariant (A13-G13) but its audit compared against the reserved mechanism, not against what Terminal.tsx actually handles; this drift is the concrete residue. This is a real bug today, S effort, and per the dispatch index it is a step-0 live-defect fix to land immediately alongside SP-3.

## 3. What to build

One edit plus one pinning test, both in the existing pattern of the file. (1) In halbert_core/halbert_core/skills/reserved.py, add "help" and "h" to the RESERVED_SLASH_BUILTINS frozenset (lines 45-50), and extend the comment block at lines 40-44 so it names the full set the terminal page owns: /explain /fix /dryrun /help with single-letter aliases (dashboard/frontend/src/pages/Terminal.tsx — note BOTH dispatch sites, handleSlashCommand ~line 153 and handleAICommand ~line 260, so the next editor does not fix only one). No other code path changes: is_reserved_skill_name(), _static_reserved_names(), and the loader refusal at loader.py:261 pick the new names up automatically because they all derive from the frozenset. (2) In halbert_core/tests/test_skills_reserved.py, extend test_slash_builtins_are_reserved (line 51) with assert is_reserved_skill_name("help") and assert is_reserved_skill_name("h"), and add a new drift-pinning test, e.g. test_every_terminal_slash_command_is_reserved, that does what test_channel_registry.py:723-774 already does — locate Terminal.tsx on disk relative to the repo root (halbert_core/dashboard/frontend/src/pages/Terminal.tsx), read it as text, regex-extract every quoted slash literal compared in the dispatch chains (pattern over the `slashCmd === '/x'` and `lower === '/x'` comparisons, e.g. re.findall(r"(?:slashCmd|lower)\s*===\s*'(/[a-z]+)'", text)), strip the leading '/', and assert each extracted name is a member of RESERVED_SLASH_BUILTINS. That test is the actual drift guard: the next time anyone adds a /command to Terminal.tsx without reserving it, CI fails instead of shipping a shadow. Skip the test gracefully (pytest.skip) if the TSX file is absent, matching how the repo treats frontend-coupled tests. No frontend changes, no loader changes, no new module.

## 4. What NOT to build

Do not build the one-table command registry (skills/commands.py) deriving RESERVED_SLASH_BUILTINS from a data table — that is SP-4 proper, RESHAPE-deferred per the deep-eval verdict, gated to M5b until a second command surface (terminal channel, MCP) exists or command count passes ~8. Do not add description-aware tiered fuzzy scoring for the completion dropdown, the tolerant level normaliser for the four graded settings, or the activation "why" rendering — all SP-4 deferred scope. Do not build CMD-A's command-turn-context type, build-time registry assertion, or registry-owned executors — CMD-A is DEFER-gated in M5b, and the backlog explicitly says this drift fix does not need CMD-A. Do not touch the frontend: no edits to Terminal.tsx's dispatch, help text, or the dryrun card. Do not refactor handleSlashCommand/handleAICommand duplication — the two dispatch sites are pre-existing structure; the fix is the reserved set, not the frontend. Do not reserve names Terminal.tsx does not handle (no speculative '/models', '/modelfoo' — slashCommands.ts:47 documents those as deliberately unclaimed). Do not touch CORE_TOOL_NAMES, CONDITIONAL_TOOL_NAMES, _SCHEMA_REGISTRIES, or the live-source machinery — A13-G13's live half is healthy and unrelated.

## 5. Target files
- `halbert_core/halbert_core/skills/reserved.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S, as rated in the dispatch index. The code change is two string literals in one frozenset plus a comment update; the test is ~25 lines following a pattern already established twice in the repo (test_slash_builtins_are_reserved at test_skills_reserved.py:51 and the TSX-reading precedent at test_channel_registry.py:774). The only judgment call is the extraction regex for the drift test, and it is bounded because Terminal.tsx uses one consistent comparison idiom (`slashCmd === '/x'`, `lower === '/x'`). No dependency on any other unit, no new files on the product side, no cross-package coordination — it fits in a single commit on the step-0 worktree beside SP-3.

## 8. UX rationale

No new surface and no visible change for a user who never installs a 'help' skill — which is the point. The user-facing guarantee being restored: /help and /h in the watched terminal always render the built-in "Available Commands" card (explain/fix/dryrun/help), and a skill can never silently occupy that keystroke. This respects the standing rules untouched: commands staged never executed (the help card is a suggestion render, no execution path), no conversation list implications, no model involvement anywhere (the refusal is a deterministic frozenset membership check at load — never a model where a template suffices), no model named on any surface, no emoji added (the help text already contains a pre-existing ⚠️ in the dryrun card; out of scope here, named in exclusions), and no colour work since nothing renders differently.

## 9. Acceptance criteria

1. RESERVED_SLASH_BUILTINS in halbert_core/halbert_core/skills/reserved.py contains exactly the eight prior names plus "help" and "h" (ten total): {model, explain, e, fix, f, dryrun, d, help, h}. 2. is_reserved_skill_name("help") and is_reserved_skill_name("h") both return True, and a skill whose name is 'help' or whose aliases include 'h' is refused at load by the existing check at skills/loader.py:261-279 (the existing alias-refusal test pattern at test_skills_reserved.py:95 covers the mechanism; no new loader test needed, but the name-level assertions are explicit). 3. The new drift test extracts the slash literals from Terminal.tsx and passes: every name the terminal dispatches on (explain, e, fix, f, dryrun, d, help, h) is a member of RESERVED_SLASH_BUILTINS. 4. Removing "help" from the frozenset makes the new drift test fail (mutation check, run once by hand during development, not committed). 5. The full pre-existing test_skills_reserved.py suite still passes unmodified — no regressions in the tool-name, alias, or bundled-skill checks.

## 10. Verification (measured state, not model judgment)

From the worktree root, run: arch -arm64 ./wt_pytest.py halbert_core/tests/test_skills_reserved.py — expect exit code 0 with all tests passing, including the extended test_slash_builtins_are_reserved and the new test_every_terminal_slash_command_is_reserved (the wt_pytest.py wrapper is mandatory from a worktree: the shared venv's editable install pins halbert_core imports to the main tree, and bare pytest would test the wrong code and pass while doing it; also mandatory is the arch -arm64 prefix, without which pydantic_core dies with an incompatible-architecture ImportError). Then run the negative control once: temporarily delete "help" from RESERVED_SLASH_BUILTINS, re-run the same command, and confirm the new drift test FAILS (nonzero exit, assertion naming 'help'); restore the line. Also confirm the targeted run collects the new test: the pytest output line for test_skills_reserved.py shows one more passed test than the baseline run on the merge-base. No frontend run is required — the TSX is read as text, not executed.

## 11. Exclusions

Full command registry (one data table backing slash channel, composer, and reserved set), fuzzy completion scoring, level normaliser, activation-"why" rendering — all to SP-4, recorded in M5b (founder-decision-gated, per the RESHAPE verdict: build only when a second command surface exists or command count > ~8). CMD-A command-turn-context type, build-time registry assertion, registry-owned executors — to CMD-A in M5b (gated on SP-4's OC03-C5 plus OC03-C6 from permissions; backlog line 489 records the gate). The duplicate dispatch structure in Terminal.tsx (handleSlashCommand vs handleAICommand) — left as-is; a frontend consolidation would belong to a terminal-surface unit, not this one; if no such unit exists it is dropped per RESHAPE as not worth standalone effort. The pre-existing ⚠️ emoji in Terminal.tsx's dryrun preview (violates the no-emoji-in-UI rule but predates this unit and is unrelated to the reserved-name drift) — not fixed here; candidate for an M5b tail sweep of UI-rule violations or a future terminal-surface unit; if neither materialises, dropped per RESHAPE. Reserving unclaimed names like '/models' or '/modelfoo' — dropped per RESHAPE: slashCommands.ts:47 documents them as deliberately unclaimed and sendable, so reserving them would be a behaviour change, not a drift fix.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

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
