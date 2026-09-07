# Security remediation — state of the work

**Date:** 2026-09-07
**Branch:** `worktree-sec-1-one-door` (worktree at `.claude/worktrees/sec-1-one-door`), base main `7719fff1`
**Status:** Seven commits, unmerged. Suite green. Two design rulings and one identifier reconcile outstanding.
**Review packet:** `.handoff/REVIEW-PACKET-12-SECURITY-REMEDIATION-2026-09-07.md`

This is the state document. `SECURITY-TODO.md` is the working checklist; Review Packet 12 is what
goes to a reviewer. If those three disagree, this one is stale — check the commits.

---

## 1. What happened, in order

**2026-09-06 — the audit.** Two lenses, as asked: a standard appsec code audit and a UI/control
security audit. Three adversarial passes, 205 agents. 167 raw findings from 16 finder dimensions over
a six-surface recon; per-subsystem adjudication against the real files; then a completeness critic and
a sweep of the packages no dimension had touched. Every finding that survived was put to verifiers
instructed to refute it and to default to refuted when they could not confirm it from code.

**Result: 186 confirmed** — 12 critical, 50 high, 95 medium, 29 low. 28 candidates were refuted and
are recorded as checked rather than dropped.

**2026-09-06 — the design.** Three independent proposals (least-privilege, product-experience,
reviewer-defensible), scored by three judges (engineering, adversary, owner), synthesised from the
reviewer-defensible spine. Produced the capability-vs-consent split, three first-run profiles, the
first-run copy, the live controls, the settings IA, and five per-platform permission matrices.

**2026-09-06 — the plan.** 186 findings triaged into 20 `SEC-*` rows with testable definitions of
done, a dependency graph, twelve founder decisions, the corrections owed to the published legal
documents, and the test gates.

**2026-09-07 — remediation, five commits.** SEC-1, SEC-9, the front half of SEC-2/SEC-3, two holes
the audit itself missed, and the fixes falling out of a self-review of all of it.

**2026-09-07 — the self-review.** 24 agents against the landed commits: did they close what they
claim, can the new controls be bypassed, what did they break, and are the commit messages true.
81 issues raised, 17 serious, put to independent verifiers. **Zero refuted.** Four were in code that
had already been reviewed, tested, committed and described as done.

---

## 2. Where everything lives

All on this branch as of `3345bbeb`.

| Artefact | Path |
|---|---|
| 186 findings, full evidence | `.handoff/SECURITY-AUDIT-FINDINGS-2026-09-06.md` |
| The same, machine-readable | `.handoff/security-audit-findings-2026-09-06.json` |
| Readable report | `.handoff/SECURITY-AUDIT-REPORT-2026-09-06.html` |
| The permission and consent design | `documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` |
| 20 `SEC-*` rows, decisions, test gates | `.handoff/SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md` |
| Working checklist | `.handoff/SECURITY-TODO.md` |
| Review handoff | `.handoff/REVIEW-PACKET-12-SECURITY-REMEDIATION-2026-09-07.md` |
| SEC-2/3 research and its critiques | `.handoff/research/sec-2-3/` — **not wired, see its README** |

The audit corpus was written into the main working tree and left untracked; `3345bbeb` brought it
onto this branch. Before that, the reasoning behind six commits existed only as untracked files on
one machine.

**Read the dates.** The findings, design and plan describe the tree as it was on 2026-09-06 and speak
in the present tense about code that has since changed.

---

## 3. What landed

| Commit | What |
|---|---|
| `152f10c5` | **SEC-1** — one door: every listener authenticates |
| `3cd680db` | **SEC-9** — Home Assistant governance stops being decorative |
| `75e3f47c` | **SEC-2/3 front half** — remove the shell, stop names becoming paths |
| `79dca611` | Two holes the 186-finding audit missed |
| `fcb381d3` | Acting on the self-review of all of the above |
| `e6d67197` | Reconcile the packet with what actually landed |
| `3345bbeb` | Put the audit corpus on the branch it produced |

**Scope:** 65 files. Excluding the documentation corpus: **+3005 / −229** across code and config, of
which **1174 lines are eight new test files** (six Python, two frontend) and 217 more are changes to
six existing ones.

### SEC-1 — the authentication boundary

~315 of 334 routes had no authentication of any kind, and loopback was being treated as an
authorization boundary. It is not one: every process running as the owner is already on loopback, and
so is a web page that has rebound its own hostname to 127.0.0.1.

The mechanism is the point. Routers register through `mount_api`, which attaches `require_owner`
unless the router authenticates itself, so a route added tomorrow is protected **by omission**. The
previous design needed 334 separate acts of remembering and got 19.

Also: Host-header allowlist (the only control that closes DNS rebinding — CORS never sees it); Origin
*and* credential checks on all four WebSocket handlers before `accept()`; `_is_local_client` no longer
answers "yes" when it cannot tell; MCP's "open mode" deleted; Wyoming and both deploy units bound to
loopback; a browser handoff by single-use HMAC ticket so a browser and the kiosk unit keep working.

**Found while building, not in the audit:** `/docs`, `/redoc` and `/openapi.json` served a complete
machine-readable map of all 334 routes to any caller.

### SEC-9 — Home Assistant governance

Both criticals were **dead code**, not misconfiguration. Levels 2 and 3 keyed on `garage_door` and
`water_valve`; neither is a Home Assistant domain (HA uses `cover` and `valve`), so the confirm and
forbid tiers matched nothing, ever, while `cover` sat in Level 1 and opened the garage with no
confirmation. Unknown domains returned "act, log only" — which is how `shell_command`,
`python_script`, `hassio` and `homeassistant` auto-executed.

### SEC-2/3 front half

Shell removed from `system_info.py` — `get_service_status` interpolated a *model-supplied* name into
`create_subprocess_shell`, and was invisible to the command classifier because that only inspects
`run_command`. Persona purge traversal closed. `backup_id` traversal closed.

### The two the audit missed

Both found by critics reviewing the *proposed* SEC-2 work, both live, both with regression tests
confirmed to fail without their fix:

- **A pager is a shell escape.** `git log -1` auto-runs at MEDIUM, spawns a pager, and the pager
  executes `$GIT_PAGER` as a shell command. Verified running as uid 501 through the real `PTYSession`.
  The classifier decides at spawn what a session may do; a pager invalidates that the moment it opens.
- **Reading a credential was harmless.** `read_file /etc/shadow` → SAFE. `cat ~/.ssh/id_ed25519` →
  LOW. `SENSITIVE_PATHS` elevates by one level and only MEDIUM→HIGH gates, so it never fired for a read.

---

## 4. The numbers, verified

| | |
|---|---|
| Python suite | **5711 passed, 15 skipped, 0 failed** |
| Frontend | **986 passed** (108 files) |
| `tsc --noEmit` | clean |
| `cargo check` | clean |

Run them yourself:

```
cd .claude/worktrees/sec-1-one-door
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests -q
cd halbert_core/halbert_core/dashboard/frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run
```

`wt_pytest.py` is mandatory from a worktree. Plain `pytest` resolves `halbert_core` to the **main**
tree through an editable-install meta-path finder and silently tests the wrong code, so any count
produced with it is meaningless. `node_modules` exists only in the main tree; symlink it in.

---

## 5. What is open

### Deliberately not landed, and referred for a ruling

**The command classifier.** Designed and measured. The implementation plan's own proposal —
`unknown → HIGH` — takes the prompt rate on Halbert's own command repertoire from **3.1% to 82.8%**.
That is not a gate an owner keeps. The allowlist alternative converges to ~11%, but its patch has five
live defects, including a `basename`-keyed identity check that repeats the exact mistake the audit
calls arbitrary root execution in `halbert-exec-helper`, and a quoting bypass that skips the whole
credential tier. Two couplings the plan missed: the prefix bug and the default are entangled (27 of 38
currently-SAFE commands are SAFE only because the regex is a bare prefix match), and `RoleGate` would
*refuse* rather than prompt for `guest`/`restricted` speakers.

**The macOS seatbelt profile.** The proposal makes `diskutil list` return rc=0 with **zero bytes**. An
agent whose job is observing the machine reads "no disks" and reasons from it. A sandbox may fail
loudly; it may not fail quietly. It also breaks `git`, `python3`, `brew` and `openssl`, and omits
`/Volumes` — where this repository lives.

**The path primitive.** Good work, not a drop-in: on macOS with `root="/"` it refuses `/etc/hosts`
because `etc` is a symlink to `private/etc`, so it needs a root allowlist — a product decision.
`ResolvedPath` cannot be threaded through `editor.py`, which uses the path as a string in six places.
And `write_bytes` is `ftruncate(0)` then `write`: a crash mid-write on `sshd_config` leaves it empty.

### Seven serious self-review issues still open

Three of them are one question — **how much do we trust a loopback origin?** — and that is a design
decision, not an oversight: the CORS allowlist still grants `localhost:3000` and `:5173` credentialed
access; `origin_allowed` accepts every loopback origin, so a page on any other localhost port can open
the PTY bridge and the live microphone stream with the owner's cookie; and `/auth/logout` is
unauthenticated and revokes all sessions.

Also open: `conversation` at Level 2 still auto-executes at `orchestrate`; and `guard_bind` runs on
one code path while five others bind without it.

### A live product bug, undecided

The **current** seatbelt profile already blocks all network — sandboxed `curl` returns rc=6 and HTTP
`000`; bare returns `200`. So `POST /api/terminal/exec` on macOS cannot `curl`, `brew`, `git fetch` or
`pip install`, on a machine-administration product. The code's own comment claims "permissive v1
mode… normal commands usable". That is false, and audit finding F138 was wrong in the same direction.
**Needs a ruling:** is default-deny correct here, with the bug being that it is silent and
undocumented — or is this a regression?

### Blocked on a decision

`SEC-D10` — `config/platforms.yml` and `DECISIONS.md FDR-03` disagree on bundle identifiers, and the
per-channel ceiling table is keyed on them. This hard-blocks **SEC-5**, the capability/Lease model,
which is the largest remaining P0 item.

### Still open in P0

`SEC-2` (classifier), `SEC-3` (path containment and the privileged write path — the two bash root
helpers and the `sudo -n` fallback are untouched), `SEC-4` (one approval gate; policy engine deleted),
`SEC-5` + `SEC-8` (capability/Lease + kill switch), `SEC-6` (two-phase boot and first run).

---

## 6. Method notes worth carrying forward

Two of these cost real time and would cost it again.

**A census that walks the wrong tree passes.** The first `test_route_auth_census.py` checked **4 routes
out of 334** and was green. This FastAPI version does not flatten an included router into `app.routes`
— it appends an `_IncludedRouter` wrapper holding the real routes on `original_router` and the
include-time dependencies on `include_context`. The test now asserts its own walk depth, because a
security test that silently checks nothing is worse than no test.

**A fixture can fail to build the shape it protects.** The persona containment fix shipped a
regression — resolved files compared against an unresolved root, so every purge raised `ValueError`
behind a symlink, the ordinary macOS `/var` → `/private/var` case. Its own tests missed it because
pytest's `tmp_path` is *already resolved* on this machine. Build the adversarial shape explicitly.

**Every regression test here was checked against its own absence.** Revert the fix, watch the test
fail, restore. A test that passes before and after proves nothing, and two of them nearly shipped that
way.

**Research agents write into the working tree.** Two produced files unasked — one wrote a 291-line
module into `halbert_core/`, another applied a classifier patch and reverted it mid-review. Stage
explicitly; never `git add -A` while a research workflow is running.

**The self-review was the highest-value hour.** Zero of its 17 serious findings were refuted, and four
were in code already committed and described as done. Reviewing your own confident claims against the
code catches a different class of thing than writing more tests does.

---

## 7. Picking this up

1. Read Review Packet 12 §5 first — it is what the outstanding decisions are.
2. `SEC-D10` unblocks the largest remaining item; it is a five-minute reconcile of two files.
3. The classifier and sandbox rulings are product decisions about how often Halbert may interrupt its
   owner and whether a sandbox that fails silently is worse than none. Both have measured evidence in
   `.handoff/research/sec-2-3/`.
4. Nothing in `.handoff/research/sec-2-3/` is wired. Do not import it without reading its README and
   the three critiques beside it.
5. The branch is unmerged and the suite is green. It can merge as-is; what it cannot do is claim SEC-2
   or SEC-3 are finished.
