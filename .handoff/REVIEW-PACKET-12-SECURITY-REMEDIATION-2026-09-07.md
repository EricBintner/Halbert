# Review Packet 12: Security Remediation — SEC-1, SEC-9, and the SEC-2/SEC-3 Front Half

**Review Level:** **Fable**
**Domain:** Authentication boundary, Home Assistant governance, command classification, path containment, sandboxing
**Date:** 2026-09-07
**Branch:** `worktree-sec-1-one-door` (git worktree at `.claude/worktrees/sec-1-one-door`), base `7719fff1`
**Status:** Ready for review. Five commits landed and green. Two design decisions deliberately **not** landed and referred to you.

---

## 1. Executive Summary & Review Scope

On 2026-09-06 a three-pass adversarial audit of Halbert produced **186 confirmed findings** (12 critical, 50 high, 95 medium, 29 low) across two lenses — a standard appsec code audit and a UI/control-security audit. The findings, the resulting permission-and-consent design, and a 20-row implementation plan are in the companion documents listed in §2.

This packet covers the first tranche of remediation: **SEC-1** (the authentication boundary), **SEC-9** (Home Assistant governance), and the unambiguous front half of **SEC-2/SEC-3** (command execution and path containment).

The single most important thing for you to review is **not** the code that landed. It is the two things that did **not** land, and why. A research pass produced a full command-classifier rewrite and a full macOS seatbelt profile; adversarial critics then found five live defects in the first and a disqualifying one in the second. Both are documented in §5 with the evidence. **Landing either as proposed would have been landing known-defective code**, and the judgement call to hold them is the thing most worth a second opinion.

### What this work does not claim

The token boundary added in SEC-1 stops another *user account* on the machine, anything on the LAN, and any web page the owner visits. It does **not** stop code already running as the owner's own uid — that code can read the token file exactly as it can read the owner's ssh key. Raising that bar needs OS-level app sandboxing, not a secret. This is stated in the module docstring rather than implied away, and it is the honest ceiling of the current design.

---

## 2. Planning & Design Documents

| Document | Purpose |
|---|---|
| `.handoff/SECURITY-AUDIT-FINDINGS-2026-09-06.md` | All 186 confirmed findings with evidence, attack path, impact and fix. Machine-readable companion: `security-audit-findings-2026-09-06.json` |
| `documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` | The permission model: capability-vs-consent split, three first-run profiles, first-run copy, live controls, settings IA, five per-platform matrices |
| `.handoff/SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md` | Triage into 20 `SEC-*` rows, dependency graph, 12 founder decisions, the disclosure list, test gates |
| `.handoff/SECURITY-TODO.md` | Working checklist under the `SEC-*` rows (this branch) |
| `.handoff/SECURITY-AUDIT-REPORT-2026-09-06.html` | The readable report |

---

## 3. Git History & Code Commits

| Commit | Summary | Key files |
|---|---|---|
| `152f10c5` | **SEC-1** — one door: every listener authenticates | `dashboard/auth.py` (new), `dashboard/app.py`, `routes/websocket.py`, `federation/peer_middleware.py`, `mcp/server.py`, `audio/config.py`, `deploy/*.service`, `src-tauri/src/lib.rs`, `src/lib/apiBase.ts`, `components/AuthGate.tsx` |
| `3cd680db` | **SEC-9** — Home Assistant governance stops being decorative | `integrations/home_assistant/ha_governance.py`, `autonomy_gate.py`, `ha_tool.py`, `mcp/server.py`, `routes/home.py` |
| `75e3f47c` | **SEC-2/3 front half** — remove the shell, stop names becoming paths | `tools/system_info.py`, `persona/memory_purge.py`, `routes/editor.py` |
| `79dca611` | Two holes the audit missed — pager escape, credential reads (§4.4) | `streaming/pty.py`, `tools/safety.py` |
| `fcb381d3` | Acting on the self-review of all of the above (§5.4) | `autonomy_gate.py`, `ha_governance.py`, `apiBase.ts`, `useBeingEvents.ts`, `auth.py`, `memory_purge.py`, `simulator.py`, `cognitive_loop.py`, `deploy/*.service` |

Suite at `fcb381d3`: **Python 5711 passed / 0 failed**, frontend 986 passed, `tsc` and `cargo check` clean.

---

## 4. Key Files & Architectural Components

### 4.1 `dashboard/auth.py` — the door (new, ~380 lines)

The mechanism is the point, not the patch. Routers register through `mount_api`, which attaches `require_owner` unless the router authenticates itself — so a route added tomorrow is protected **by omission**. The previous design required 334 separate acts of remembering and got 19 of them.

- Per-launch token at `<state_dir>/api-token`, created `0600` in a `0700` directory via `os.open` so there is no world-readable window between create and chmod.
- Three credentials: `Authorization: Bearer`, `X-Halbert-Token` (the Tauri webview is cross-origin to its own sidecar and can never hold a cookie), and a session cookie for browsers.
- Host-header allowlist → 421. This is the only control that closes DNS rebinding; CORS never enters into it.
- Origin **and** credential checked on all four WebSocket handlers, before `accept()`.
- Browser handoff: a single-use HMAC ticket redeems at `/auth/enter` for an `HttpOnly; SameSite=Strict` cookie. `python -m halbert_core.dashboard.ticket` prints the URL; `scripts/halbert-kiosk.service` uses the same mechanism for its incognito Chromium.

**Found while building, not in the audit:** `/docs`, `/redoc` and `/openapi.json` served a complete machine-readable map of all 334 routes to any caller. Now off unless `HALBERT_DEV_DOCS=1`. Nothing in the tree, tests, scripts or CI consumed them.

### 4.2 `tests/test_route_auth_census.py` — the thing that keeps it true

Fails CI when a route appears without an auth dependency. **It also asserts its own walk depth**, and that assertion is load-bearing: this FastAPI version does not flatten an included router into `app.routes` — it appends an `_IncludedRouter` wrapper holding the real routes on `original_router` and the include-time dependencies on `include_context`. The first version of this census walked only the top level, saw **4 routes out of 334**, and passed.

### 4.3 `ha_governance.py` / `autonomy_gate.py`

Both SEC-9 criticals were **dead code**, not misconfiguration. Levels 2 and 3 keyed on `garage_door` and `water_valve` — neither is a Home Assistant domain (HA uses `cover` and `valve`) — so the confirm and forbid tiers matched nothing, ever, while `cover` sat in Level 1 and opened the garage with no confirmation. Unknown domains returned "act, log only", which is how `shell_command`, `python_script`, `hassio` and `homeassistant` auto-executed.

`evaluate_call()` now judges the union of `entity_id`, `data.entity_id` and `data.target.entity_id`, most-restrictive-wins, at all four call sites — including `home/cognitive_loop.py:194`, the one that runs unattended, which `fcb381d3` converted from `evaluate()`. Before it, `entity_id="switch.lamp", data={"entity_id": "switch.life_support"}` was judged as the lamp.

### 4.4 Two findings the 186-finding audit missed

Both were found by adversarial critics reviewing the *proposed* SEC-2 work, and both were live in the tree. Fixed in `79dca611`; both regression tests were confirmed to fail without their fix.

**(a) A pager is a shell escape.** `git log -1` classifies MEDIUM and **auto-runs with no confirmation**. It spawns a pager, and `git`/`systemctl`/`man` execute `$GIT_PAGER`/`$SYSTEMD_PAGER`/`$MANPAGER` *as a shell command*; `less` offers `!command` interactively. Writes into a live session's stdin are never re-classified (F128), so the pager is the bridge between "the classifier waved this through as read-only" and "there is a shell here now". Verified end to end through the real `PTYSession` on this machine — the pager ran as uid 501.

Fix: `_PAGER_NEUTERED` applied in `pty.py` before the caller's own env, so a session that deliberately wants a pager can still ask for one. Regression tests confirmed to **fail without the fix** (2 of 4).

**(b) Reading a credential was classified as harmless.** Measured before the fix:

```
read_file  /etc/shadow                 -> SAFE  conf=False
read_file  ~/.ssh/id_ed25519           -> SAFE  conf=False
read_file  ~/.aws/credentials          -> SAFE  conf=False
cat ~/.ssh/id_ed25519                  -> LOW   conf=False
```

`_classify_builtin` returned SAFE for every `read_file` path — "read-only" is a statement about the filesystem, not about harm. The `cat` route was no better: `SENSITIVE_PATHS` elevates by exactly one level, and SAFE→LOW still auto-runs. **Only MEDIUM→HIGH ever gated anything.**

Fix: a credential tier keyed on **filename**, not directory. A directory rule on `~/.ssh` or `/etc/ssh` would gate `sshd_config` — the file `routes/editor.py` exists to edit — and `known_hosts`. That is precisely the gate that fires on ordinary use and gets switched off, after which it protects nothing. Quote-tolerant, because a model writes `cat "/path/to/key"` about as often as the bare form and a check that only sees the bare form is one keystroke from being skipped.

---

## 5. Incomplete Work & Open Items

### 5.1 The command classifier rewrite — designed, measured, **not landed**

A research pass built the full replacement and measured it. The numbers are real and worth your attention:

| corpus | today | plan's "unknown → HIGH" | proposed allowlist | after one maintenance pass |
|---|---|---|---|---|
| Halbert's own argv (262) | 3.1% prompt | **82.8%** | **23.7%** |
| RAG shell corpus (11,133) | 14.0% | 84.0% | 83.3% |

Every figure above reproduces from `.handoff/research/sec-2-3/measurement/converge.py`. An
earlier draft of this packet carried a fourth column — 11.1% argv and 78.6% docs "after one
maintenance pass" — and **those two numbers do not reproduce from the committed script**, which
emits no second-pass figure at all. They are withdrawn. The convergence argument is therefore
unproven: 23.7% is what the allowlist measurably achieves, and whether maintenance halves it
again is a claim someone must re-measure before relying on it.

The implementation plan's stated direction — `unknown → HIGH` — takes the prompt rate on Halbert's own observation repertoire from 3.1% to **82.8%**. That is not a gate an owner keeps. The proposed allowlist (exact `(basename, first-arg)` lookup) converges instead.

**Two couplings the plan did not account for:**

1. The prefix bug and the default are **entangled**. 15 of 38 currently-SAFE argv commands (`lspci`, `lsmod`, `lscpu`, `lsusb`, `lsblk`, `findmnt`, `iptables -L`) are SAFE *only because* the alternation is a bare prefix match. Adding a word boundary without first replacing what the regex was doing pushes those into the default branch. (An earlier draft said 27; that was the row count of the three unanchored rules, not the number that stops matching under `\b`. `lsof` does not appear in the corpus at all.)
2. `RoleGate` caps `guest` at medium and `restricted` at low and **blocks** above the cap. Under `unknown → HIGH`, those speakers are not prompted — they are refused outright. Dashboard chat is unaffected (`speaker_role` defaults to `admin`); the voice path is not.

**Five live defects the critics found in the proposed patch** — this is why it is not landed:

| # | Defect | Evidence |
|---|---|---|
| 1 | `_is_read_only` keys on `basename`, so `/tmp/evil/ls` classifies SAFE | The identical check the audit calls arbitrary root execution in `halbert-exec-helper` |
| 2 | `man -P /tmp/evil/pwn ls` executes an arbitrary program and is in the table as read-only | Verified: `PWNED-VIA-MAN-PAGER euid=501` |
| 3 | **Quoting defeats the entire path analysis.** `_normalise_path('"/Users/…/.ssh/id_ed25519"')` → `None`, so the credential tier is skipped | One pair of quotes |
| 4 | `dscl .` is allowlisted on its first argument, but `.` is a node selector, not a verb — `-create`/`-delete`/`-passwd` follow it | |
| 5 | Two different segmenters compute the path analysis and the read-only verdict from different tokenisations of one string | This is *why* #3 exists |

Also: `user_overrides` is typed `Dict[str, RiskLevel]` and consumed as the read-only table's value type, which raises `TypeError` out of `classify()` — called unguarded from `executor.py`.

**Measured cost of landing it — and read the baseline.** Against `75e3f47c` the patch cost exactly **2 test failures**, both in `test_terminal_stream_bridge.py` (they execute `sleep 5`; the fix is `confirmed=True` — those tests are about timeouts, not classification).

Re-measured against `fcb381d3` it costs **24**. Twenty-two are in `test_secret_reads.py`: the patched module was cut before `79dca611` and so *reverts the credential-read gate*. Three of those are `TestDoesNotOverCorrect` cases — `cat /etc/ssh/sshd_config`, `ls ~/.ssh`, `grep Port /etc/ssh/sshd_config` — which is precisely the over-correction §6 asks you to watch for. **Landing this means merging the patch onto the credential tier, not replacing `safety.py` wholesale.**

And **two tests go vacuous**: `test_agent_pool_cwd_injection.py` keeps passing while its name, docstring and rationale become false.

**My recommendation:** land it, after fixing defects 1–5, keyed on `(head, argv[1])` rather than basename, with `user_overrides` wired to an "always allow this exact invocation" affordance so the residual is a finite queue the owner drains rather than a permanent tax. **But the shape is a product decision about how often Halbert is allowed to interrupt, and it should be yours.**

### 5.2 The macOS seatbelt profile — **do not land the proposal**

The current profile is nearly useless: `cat ~/.ssh/id_ed25519` succeeds inside it, writes to `$HOME` succeed, and the `/etc/ssh` deny rule at `sandbox.py:50` is dead. But the *proposed* replacement is worse, and one finding disqualifies it:

```
diskutil list    sandboxed rc=0  bytes=0
                 bare      rc=0  bytes=10455
launchctl list   sandboxed rc=1  bytes=0
                 bare      rc=0  bytes=21317
```

**`diskutil list` succeeds and returns nothing.** An agent whose entire job is observing the machine reads "no disks" and reasons from it. A sandbox may fail loudly; it may not fail quietly.

It also breaks `git`, `python3`, `brew` and `openssl` (missing `/Library/Frameworks`, `/usr/local`, `/Applications`), and omits `/Volumes` — where this repository lives. The proposed module does not import.

**A live product bug this uncovered:** the *current* seatbelt profile already blocks all network. Verified — sandboxed `curl` returns rc=6 / HTTP `000`; unsandboxed returns `200`. So `POST /api/terminal/exec` on macOS today cannot `curl`, `brew`, `git fetch` or `pip install`, on a machine-administration product. The code's own comment claims "permissive v1 mode… normal commands usable". That comment is false, and the audit's F138 was wrong in the same direction. **This is not filed as a finding anywhere and needs a decision: is default-deny network correct here (and the bug is that it is silent and undocumented), or is it a regression?**

### 5.3 `resolve_once` / path containment — not a drop-in

`utils/containment.py` and `tests/test_path_containment.py` are **untracked on disk** in the worktree; a research agent wrote them there. They are good work — the module correctly rejects `realpath` because on APFS `/etc/PASSWD` and `/etc/passwd` are one inode with two spellings and an NFD argument comes back NFD, so any check comparing resolved strings loses to pressing shift. It returns an open descriptor and makes `__fspath__` raise.

But it cannot be adopted at the editor route as the plan describes:

- On macOS with `root="/"` it refuses `/etc/hosts`, because `etc` is a symlink to `private/etc`. It **requires a root allowlist**, which turns a one-line swap into a product decision: which roots may the dashboard editor open?
- `ResolvedPath` cannot be threaded through `editor.py` — `path` is used as a *string* by `_current_text_and_readability`, `check_before_write`, `create_backup`, `get_backup_dir`, the provenance recorder and `FileReadResponse.path`. Adopting the descriptor means rewriting the backup, conflict-detection and provenance plumbing.
- It breaks the 7 tests in `test_write_paths_guarded.py:110-200`, which POST paths under pytest's `tmp_path` (`/var/folders/...` here, under no plausible editable root).
- `ResolvedPath.write_bytes` is `ftruncate(0)` then `write` — **a crash mid-write on `sshd_config` leaves it empty.** It needs the atomic-replace method before it is used for anything.

Platform facts verified on this machine: `O_TMPFILE`, `os.linkat` and `os.openat2` are all **absent**; `os.rename in os.supports_dir_fd` is **True**. The plan's stated `O_TMPFILE+linkat` primitive does not exist here.

### 5.4 What the self-review of this work found

After landing SEC-1, SEC-9 and the SEC-2/3 front half, a 24-agent adversarial pass was run against
those commits: did they close what they claim, can the new controls be bypassed, what did they break,
and **are the commit messages true**. It raised 81 issues; 17 were serious and put to independent
verifiers. **Zero were refuted.** The tables below account for 12 of the 17 — eight fixed, four still open. The remaining five were folded into the fixes rather than tracked separately (`scene` to Level 2, the fourth `evaluate_call` site, `simulate_command`'s shell, the deploy-unit comments, and the `guard_bind` claim); each is named in `fcb381d3`'s message. An earlier draft said "ten are fixed; the rest are below", which did not add up.

That pass is the most useful thing in this packet, because four of the seventeen were in code that had
already been reviewed, tested, committed and described as done.

**Fixed as a result** — see the commit for detail:

| Was | Reality |
|---|---|
| `evaluate_call` judged the whole payload | It read `entity_id` and `target.entity_id` only. HA merges `device_id`/`area_id`/`floor_id`/`label_id` into **every** entity service schema and `ha_client` POSTs `data` verbatim, so the gate ruled on a field the call would not act on. |
| The forbidden-entity list protects life-support | `entity_id: "all"` (HA's `ENTITY_MATCH_ALL`) starts with none of the prefixes. `switch.turn_off` + `{"entity_id": "all"}` at `act` autonomy turned off every switch in the house, auto-executed. |
| SEC-1 added a token boundary | `installAuthFetch` keyed on `apiBase()`, which returns the *active body* — so after a Presence Pill switch it sent this machine's token to a peer host on the LAN in cleartext. |
| SEC-1 broke nothing | `EventSource` carries no header and, in Tauri, no usable cookie — the proactive event feed was permanently 401 in the desktop app. |
| The persona containment fix was safe | It compared resolved files against an **unresolved** root, so every purge raised `ValueError` when `memory_root` sat behind a symlink — the ordinary macOS `/var` → `/private/var` case. Its own tests missed it because pytest's `tmp_path` is already resolved here. |
| "A non-loopback bind now refuses to start without a token" | False. `guard_bind` runs only in `python -m halbert_core.dashboard`; both deploy units, the systemd unit, `Halbert/main.py` and `app.py`'s `__main__` invoke uvicorn directly and never reach it. **The comment I wrote in those units told an operator the guard would catch them.** |
| "Unknown domains now confirm" | False at `orchestrate`, where Level 2 auto-executes with a cancel window. |
| "5720 passed" | Inflated by 21 tests for an unwired research module. |

**Still open, and for you to rule on.** The first three are one question — *how much do we trust a
loopback origin?* — and it is a design decision, not an oversight:

| Sev | Issue | Where |
|---|---|---|
| medium | The CORS allowlist still grants `localhost:3000` and `:5173` full credentialed access. With a session cookie in a browser, that is the one browser-reachable way around the new door. | `app.py:568` |
| medium | `origin_allowed` accepts **every** loopback origin, so a page on any other localhost port can open the PTY bridge and the live microphone stream using the owner's cookie. | `auth.py:286` |
| medium | `POST /auth/logout` is unauthenticated and revokes *all* sessions — a cross-origin denial of service. | `auth.py:525` |
| medium | `conversation` is Level 2, so at `orchestrate` the `conversation.process` laundering path still auto-executes. | `ha_governance.py` |

64 further issues were raised below the serious bar and not adversarially checked: 18 more overclaims,
16 new-defects, 11 weak tests, 10 unclosed findings, 6 dead code, 3 regressions. The full structured
output is in the workflow journal; the weak-test group is worth a look on its own, since a test that
passes for the wrong reason is how the persona regression shipped.

### 5.5 Still open in P0

`SEC-2` (classifier, above), `SEC-3` (path containment + the privileged write path — the two bash root helpers and the `sudo -n` fallback are untouched), `SEC-4` (one approval gate; policy engine deleted), `SEC-5`+`SEC-8` (capability/Lease + kill switch), `SEC-6` (two-phase boot and first run).

**`SEC-5` is hard-blocked on `SEC-D10`** — `config/platforms.yml` and `DECISIONS.md FDR-03` disagree on bundle identifiers and the ceiling table is keyed on them.

---

## 6. Review Directives for Fable

- **Rule on the classifier shape (§5.1).** This is the decision that matters most and it is a product judgement, not a security one: how often may Halbert interrupt its owner? Check the measured numbers against your own reading of the corpus method — the scripts, the corpus and the full per-command report are committed at `.handoff/research/sec-2-3/measurement/` (`mine.py` builds the corpus, `proto.py` is the prototype classifier, `converge.py` prints the table above, `verify.py` is its 47 assertions). **They carry hard-coded absolute paths to the tmp directory they were written in; repoint those at `measurement/` before running.** An earlier draft cited them at a `scratchpad/` path that existed on no machine but the author's.

  Then rule on: `(head, argv[1])` keying, the `user_overrides` affordance, and whether `RoleGate` refusing `restricted` speakers outright rather than prompting them is acceptable.
- **Rule on the sandbox (§5.2).** Given `diskutil list` returns rc=0 with no output under the proposal, and given the current profile already blocks all network silently — is the right answer a better profile, no sandbox with the classifier carrying the weight, or a sandbox that refuses to start rather than degrading? State the fail direction you want.
- **Adversarial pass on `dashboard/auth.py`.** Specifically: `_hostname_of` port and IPv6 handling; `origin_allowed` returning `True` on an absent Origin; whether the `?token=` WebSocket query parameter lands anywhere it should not; whether the ticket HMAC is over enough; and whether the ticket seen-set grows without bound.
- **Check the credential tier for over-correction (§4.4b).** The half of `test_secret_reads.py` that matters is `TestDoesNotOverCorrect`. If any case there starts prompting, the tier has been drawn as a directory rule again and needs narrowing, not widening.
- **Verify my two "audit missed this" claims.** Both are reproducible: the pager escape via `PTYSession` with `GIT_PAGER` set, and the credential reads via `ToolSafetyFramework`. If either is wrong I want to know before it reaches the roadmap.
- **Verification commands:**
  ```
  cd .claude/worktrees/sec-1-one-door
  arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests -q
  cd halbert_core/halbert_core/dashboard/frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run
  ```
  Plain `pytest` resolves `halbert_core` to the **main** tree and tests the wrong code — the wrapper is mandatory from a worktree.
