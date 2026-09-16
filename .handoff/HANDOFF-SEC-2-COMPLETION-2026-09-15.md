# Handoff: SEC-2 completed and rebased — Fable review request

> **Document:** `.handoff/HANDOFF-SEC-2-COMPLETION-2026-09-15.md`
> **Status:** Review requested — the §3 table is closed, the branch is rebased onto current main, one item needs a founder ruling rather than a patch.
> **Date:** 2026-09-15
> **Branch:** `fix/sec-2-readonly-lane`, worktree `.claude/worktrees/sec-2-lane`. Six commits on top of `fa6491dc`, which is main's tip. **Not 537 behind — this branch is current.**
> **Supersedes:** `.handoff/HANDOFF-SEC-2-READONLY-LANE-REVIEW-2026-09-15.md`, whose §3 table is now closed and whose §3 "double classification" note was wrong in a way that matters (see §4).
> **Retires:** `worktree-sec-1-one-door`. Do not merge it; see §1.

---

## 1. Why this is a new branch, not the old one

`worktree-sec-1-one-door` carried nine commits and was described as "9 ahead of main, ~523 behind". By today it was 537 behind, and `git cherry` shows **six of the nine were already on main by patch-id** — they landed 2026-09-10 through the `7358e7ed` merge of `feat/sec-merge-verified`. A seventh, `71c7b88b` (SEC-D10), is on main in richer wording, with all of its side-files (the flatpak rename, `ai.halbert.dev`).

The genuinely unmerged delta was exactly the two commits made on 2026-09-15: `6d3a4914` (the SEC-2 lane) and `101241da` (sandbox + one door). Both are cherry-picked here onto current main. Merging the old branch instead would replay six commits that are already applied and drag a five-hundred-commit-old tree over the top of them.

## 2. The merge was not clean, and the collisions were load-bearing

Main's `safety.py` grew 306 lines while the branch was parked — A2 (AppleScript classifier), B3 (MCP tool risk), `execute_code`, and the `c1d844e5` skills-boundary fix. The branch rewrote the same file by 856/170. Four things a textual resolution gets wrong, all resolved here:

- **`capabilities.py`** — the branch predates `CAP_APPLESCRIPT` and `CAP_MCP_CLIENT`, so its side of the diff *deletes* both. Resolved as a union; all three capabilities present, `terminal_unsandboxed` given the docstring entry the module gives every other capability.
- **`_normalise_path` collided on name only.** Main's `(value) -> str` canonicalises a known path for comparison; the branch's `(token, cwd) -> Optional[str]` decides whether a token *is* a path. Both are needed. The branch's is renamed `_token_as_path`; main's keeps its three callers in the skills boundary check. Taking the branch's version would not have crashed — main guards with `normalised_path and …` — it would have made that check **stop matching**, which is the failure mode `c1d844e5` exists to prevent.
- **`_under` was a less careful duplicate** of main's segment-aware `_within_path`. Dropped; all callers rewritten.
- **`classify()` was refactored** by the branch into `classify()` + `_classify_builtin()`, and main's two dispatch arms landed in the right method by luck of matching context. Verified reachable by walking the AST, not by reading the diff.

## 3. The bug the merge exposed

`test_skills_trust.py::test_an_expanded_path_into_the_user_skill_dir_requires_confirmation` **was passing on main for the wrong reason.** Under pytest the skill dir is redirected to `/private/var/folders/…`, and main's `sensitive in path` substring test matched the literal `/var/`. The branch's segment-aware `_within_path` correctly refuses that substring — which is what exposed the real defect underneath:

**`SENSITIVE_PATHS` was never resolved, while the candidate was.** On macOS `/etc` is a symlink to `/private/etc` and `/var` to `/private/var`. `_classify_write` resolves its path with `realpath`; the elevation resolved with `normpath` only; the constants were resolved not at all. Each half matched a different spelling of the same file, and `/etc/` matched nothing once a candidate had been resolved.

This is the identical bug `101241da` fixed in `streaming/sandbox.py` — the other file that keeps a table of paths — and is fixed the same way: `_resolved_root` resolves every constant, `_token_as_path` returns the resolved spelling. Four tests pin it, including both spellings of one file classifying alike.

**Worth a reviewer's attention:** this means the `/etc/` protection in `safety.py` has been inert on macOS for as long as the candidate has been resolved. It is fixed here, but it is the kind of thing that wants a second pair of eyes on whether anything else compares a resolved path against an unresolved constant.

## 4. Two corrections to the previous handoff

**(a) "Double classification — same input, same framework — should agree" is wrong.** They are two different frameworks with different taxonomies. `_gate_command` → `check_command_safety` (local to `terminal.py`, `SafetyTier`, regex + injection, takes no `cwd`, knows nothing of `user_overrides`). `_wrap_for_execution` → `ToolSafetyFramework.classify` (`RiskLevel`, cwd-aware, overrides-aware). There is no shared scale on which they could agree.

**(b) Following from that, SEC-2's own headline does not hold on the terminal routes.** `check_command_safety` falls through to `SafetyTier.SAFE` (`terminal.py:213`); `/exec` and `/terminal/spawn` return `safety_tier` and `safety_warning` as advisory response fields and run the command. Only BLOCKED yields a 403. **On those routes a HIGH verdict means "run it jailed", never "ask".** The ask exists only where `requires_confirmation` is honoured — the agent tool path.

This reframes the §3 table upward rather than downward: SAFE on a terminal route did not merely skip a prompt, it **skipped the sandbox**. The nineteen entries were exactly the set that escaped both. An unrecognised command was, by comparison, contained.

**This is the one item left for a ruling, not a patch** — see §6.

## 5. What was done

All against runs, not readings. Commits in order:

| Commit | What |
|---|---|
| `5f0377d1` | `101241da` cherry-picked — sandbox fail-loud, `realpath`'d rules, `_NEVER_WRITABLE`, seatbelt `(allow network*)`, terminal one-door, `terminal_unsandboxed` |
| `eec67c16` | `6d3a4914` cherry-picked — the read-only lane |
| `7f10b0e0` | The merge resolution and the `realpath` hole of §3 |
| `b9a03097` | **The §3 bypass table — all nineteen closed** |
| `53d4ddff` | The adjacent items; the prompt rate as actually measured |
| `eb3c341e` | SUBVERBS edge-case pins; `SECURITY-TODO` reconciled |

**The nineteen bypasses.** Two mechanisms had failed. `True` vouches a whole binary, so the systemd `*ctl` family, `hostname` and `date` carried their writing verbs along; those became frozensets that keep the reporting spellings. `ifconfig`, `iwconfig`, `arp`, `dmesg`, `nvidia-smi`, `mokutil` and `sort -o` take the effect past a first operand that is an arbitrary interface or filename, so they are named in `EFFECTFUL_ARGS`.

The second mechanism is the interesting one and was the review's own root-cause finding: **a frozenset constrains only the first operand.** `git branch -D`, `git remote add`, `git tag v9` and `tailscale drive share` each hide the effect one word further in, behind a vouched verb. **`SUBVERBS`** answers that class — where a verb has a sub-table, the token after it must be absent (the bare verb lists) or vouched too. It enumerates the read-only spellings, not the effectful ones, so a subcommand nobody has read yet is refused rather than admitted: the same fail direction as the table above it.

Two commands left the table rather than narrow, because neither is expressible as a first-operand frozenset: **`scutil`**, because bare it opens an interactive session where `set` and `add` arrive over stdin; and **`xxd`**, because its second positional operand is an output file and `-r` reverts a dump into binary. `od` and `hexdump`, which only ever write to stdout, stay.

Twenty-six read-only spellings are pinned alongside, plus twenty-three awkward ones (`git -C /repo branch -D main`, `kubectl -n prod get secrets`, `git branch --set-upstream-to=…`), so the narrowing is shown to have cost nothing.

**The adjacent items.** Three were examined and found correct, and get pins rather than changes: `_has_unquoted_redirect` agrees with the shell on all eight disputed cases including `grep "a > b" file` and an escaped quote inside a double-quoted word; the empty-command carve-out reaches only a genuinely empty line, with `> /etc/passwd`, `;`, `&&` and `| sh` all gated; and nothing agent-side writes `command-allowlist.json` — read in one place, written nowhere, with a test that walks the tree to keep it so. `terminal_unsandboxed` is confirmed override-only: in `ALL_CAPABILITIES`, explicitly `False` in both presets, no probe, and both routes 503.

One was changed: **`kubectl get secrets -o yaml` prints the secret's contents**, and a secret living in a cluster has no filename for `SENSITIVE_PATHS` or `_command_reads_secret` to see — both are filename-based. That is the redaction invariant inverted. Only the resource name is named, so `kubectl get pods` is untouched. **`helm get` is the same shape and is deliberately NOT changed** — its exposure is less clear-cut, and it is raised here rather than guessed at.

**The ~11% was wrong, and was already wrong before this branch.** Measured against the 262-command `argv` corpus the research itself mined: this table prompts on **41 of 262, 15.6%**. At the cherry-pick commit it was 40/262, 15.3% — so the bypass fixes cost 0.3 points and the gap was never theirs. ~11% was the research *prototype*'s number (`measurement/safety.patched.py`), carried into a comment about a different table. Both claim sites now state the corpus, the count and the method.

## 6. What is left

**Needs a ruling (§4b).** The terminal routes jail rather than ask. Reconcile the two lanes, or state deliberately that the terminal's containment answer is the jail and the ask lives on the agent tool path. Either is defensible; neither is mine to decide, because it changes what a person sees when they type a command. If the ruling is "ask", `check_command_safety`'s fall-through to `SafetyTier.SAFE` is where it starts.

**Open, and larger than this branch.** The sandbox still reaches only `dashboard/routes/terminal.py`. `tools/executor.py` and `streaming/agent_pool.py` never wrap, so "one door" is one door for the terminal routes and not for the agent. Extending it needs its own design for writable paths per tool call.

**Not exercisable here.** Nothing has run under bubblewrap: `bwrap` does not exist on this host (macOS, `sandbox-exec` only) and every sandbox test monkeypatches `platform.system()`. This needs a Linux box, not another session on this Mac.

**For the reviewer to adjudicate.**
- `helm get` — same shape as the `kubectl` change, left alone.
- The 41 prompts include read-only commands that simply are not in the table — `mount`, `nvcc --version`, `conda env list`, `goenv version-name`, `kopia repository status`, `docker system df`. Each is a vouching decision, which is precisely the kind of decision this review exists to check, so none were added unilaterally. Adding them is how the 15.6% comes down.
- Whether anything else in the tree compares a resolved path against an unresolved constant (§3).

## 7. Verification

- `test_classifier_read_only.py` — **164 passed**, up from 72. The nineteen bypasses, the twenty-six read-only spellings, the twenty-three awkward ones, the four resolution tests, and the pins for the adjudicated carve-outs.
- Related suites (safety, applescript, mcp, skills, sandbox, secrets, terminal, editor, write-paths) — **1493 passed**, one failure, `test_executor_pool.py::test_background_kwarg_accepted`, which fails identically on the merge-base.
- Full suite vs. a merge-base baseline: see §8.
- Invocation, from the worktree: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py <paths>`. Bare `./wt_pytest.py` picks up the system Python, which has no `pytest-asyncio`, and silently skips the async tests.

## 8. Full-suite result

<!--FULLSUITE-->
