# Critique: what the six recommendations get wrong

## 0. The baseline in the brief is stale, and it matters

HEAD is **`75e3f47c`**, not `3cd680db`. It landed part of SEC-2/SEC-3 already (`tools/system_info.py` → argv, `persona/memory_purge.py` containment, `editor.py` `backup_id: str = Field(..., pattern=r"^\d{8}-\d{6}$")`), and its message explicitly defers the classifier "pending the measured recognition rate." Every SEC-3 line citation in the brief and in `resolve-once`/`privileged-write` is **8–9 lines stale**: `startswith('/')` is at `editor.py:348` and `:388` (not 339/379), `get_file_helper_path` at `:177`, `read_file_content` `:191`, `write_file_content` `:244`, `_write_with_sudo` `:277`.

The suite is **5694 collected**, not 5616.

```
$ arch -arm64 .venv/bin/python ./wt_pytest.py halbert_core/tests -q --collect-only | tail -1
5694 tests collected in 5.18s
```

`utils/containment.py` and `tests/test_path_containment.py` are **untracked on disk** — the concurrent session left them there. They pass (35 with `test_sandbox.py`).

---

## 1. SEC-2's classifier is the *cheapest* of the six, not the riskiest — measured

I applied `scratchpad/safety.patched.py` whole and ran the **entire** suite, not a 900-test sweep:

```
$ cp scratchpad/safety.patched.py halbert_core/halbert_core/tools/safety.py
$ arch -arm64 .venv/bin/python ./wt_pytest.py halbert_core/tests -q -p no:randomly
FAILED test_terminal_stream_bridge.py::TestRunCommandStreaming::test_timeout_kills_the_child_and_closes_the_terminal
FAILED test_terminal_stream_bridge.py::TestStateMachineTerminalRelay::test_closing_the_stream_mid_command_releases_everything
2 failed, 5677 passed, 15 skipped in 172.22s
```

The default-only change (`RiskLevel.MEDIUM` → `HIGH` at `safety.py:670-676`) costs **the same 2 tests**. Baseline for that file is green (`23 passed`).

So `chokepoint`'s landing order is backwards. It puts the classifier at **step 5**, "last so you know everything before it was green," ahead of a new `gate.py`, 59 call-site conversions and a seatbelt edit — all with *unmeasured* cost. The classifier is the only one of the six with a full-suite number, that number is 2, and it closes a critical. It goes first.

## 2. Two tests go *vacuous* under the classifier change — nobody caught this

`test_agent_pool_cwd_injection.py` still passes, but stops testing what it says.

`:34-44 test_the_base_classifier_still_does_not_classify_cwd` asserts `ls` + hostile cwd is SAFE. Under the patch it still is — but only because `/tmp && touch /tmp/PWNED` doesn't normalise to a sensitive path. The base classifier now *does* read cwd (`_paths_touched` threads it). The test's name, docstring, and the "which is why the quoting stays" rationale are all false while the assertion passes.

`:46-58 test_but_a_skill_protecting_the_path_does_classify_it` asserts only `r.requires_confirmation`. Measured with the patch and **no skill installed**:

```
rm grub.cfg cwd=/boot    high    conf=True   File deletion
```

That test would now pass if `set_skill_safety` (`safety.py:342`) were deleted. It stops testing skills entirely. Both need rewriting in the same commit or B3's guarantee silently loses its only coverage.

Also confirmed: `user_overrides` is assigned at `safety.py:341` and read nowhere in the repo. `classifier-shape` is right that wiring it is what makes the residual drainable — but note the HIGH path already resumes properly (`state_machine.py:2734-2757` → `AWAITING_CONFIRMATION`; `confirm_action:1169` runs the turn to completion), so a prompt is not a dead end.

## 3. `resolve_once` cannot be used at the editor route as described — measured

`resolve-once` and `privileged-write` both say "one primitive, used everywhere." On macOS it cannot be used with `root="/"` at all:

```
root=/ -> /etc/hosts               REFUSED reason=symlink   'etc' in /etc/hosts is a symlink
root=/ -> /private/etc/hosts       OK
root=/ -> /var/folders/.../app.yaml REFUSED reason=symlink  'var' in ... is a symlink
root=/etc -> hosts                 OK      on_disk=/private/etc/hosts
```

The primitive **requires a root allowlist**. That turns `editor.py:388` from a one-line swap into a product decision (which roots may the dashboard editor open?), and it breaks the **7 tests** in `test_write_paths_guarded.py:110-200` — every one POSTs a path under pytest's `tmp_path`, which is `/var/folders/...` here and under no plausible editable root. Neither report names this file.

**Worse, `ResolvedPath` cannot be threaded through the route.** `__fspath__` raises (`containment.py:71-75`), but `path` is used as a *string* at `editor.py:384-440`: `_current_text_and_readability(path)`, `check_before_write(path, ...)`, `create_backup(BackupCreateRequest(path=path))`, `get_backup_dir(file_path)`, the provenance recorder, and `FileReadResponse.path`. Adopting the descriptor means rewriting the backup, conflict-detection and provenance plumbing off strings. That is not a co-passenger on the classifier commit.

## 4. The two containment modules conflict, and the tracked one is non-atomic

`utils/containment.py` exists; `fs/containment.py` (`privileged-write`) does not. They are different APIs for the same job — landing both recreates exactly the "two spellings for one file" that SEC-3 exists to end.

Pick `utils/containment.py`, but fix it first: `ResolvedPath.write_bytes` (`containment.py:98-102`) is `ftruncate(0)` then `write`. A crash mid-write on `/etc/ssh/sshd_config` leaves it empty. `privileged-write`'s `replace_atomically` is right and belongs *in* that module as a method.

Verified on this machine: `os.rename in os.supports_dir_fd` → **True**; `O_TMPFILE`, `os.linkat`, `os.openat2` → all **False/absent**. So the plan's stated `O_TMPFILE+linkat` is not a primitive this tree has, and `os.rename(src_dir_fd=, dst_dir_fd=)` is.

The `st_nlink > 1` write refusal is free here — `find /private/etc -type f -links +1 | wc -l` → **0**. Unverified on Linux; I have no Linux host (no Docker daemon).

## 5. The seatbelt profile breaks git, python and brew — and lies silently about diskutil

This is the finding that should stop the profile rewrite. I ran the proposed `new_seatbelt.py` against 25 real commands:

```
of the commands that work unsandboxed: 17 ok, 8 BROKEN

/usr/bin/python3 --version  BROKEN  xcrun: unable to load libxcrun (dlopen(/Applications/Xcode.app/...
git --version               BROKEN  xcrun: unable to load libxcrun (dlopen(/Applications/Xcode.app/...
project venv python         BROKEN  dyld: Library not loaded: /Library/Frameworks/Python.framework/...
brew --version              BROKEN  /usr/local/bin/brew: Operation not permitted
openssl version             BROKEN  dyld: Library not loaded: @rpath/libssl.3.dylib
dscl . -list /Users         BROKEN  Operation failed with error: eServerError
```

`_SYSTEM_READ_SUBPATHS` has `/Library/Preferences` but not `/Library/Frameworks`; `/opt/homebrew` but not `/usr/local`; no `/Applications` (so the Xcode `git`/`python3` shims die); and no `/Volumes` — **this repo lives on `/Volumes/4TB-BAD`**.

And the disqualifying one, re-run without a pipe so `head` cannot be blamed:

```
diskutil list    sandboxed rc=0    bytes=0
                 bare      rc=0    bytes=10455
launchctl list   sandboxed rc=1    bytes=0
                 bare      rc=0    bytes=21317
```

**`diskutil list` succeeds and returns nothing.** An agent whose entire job is observing the machine reads "no disks" and reasons from it. A sandbox may fail loudly; it may not fail quietly. The report's "17 of 22 diagnostics working" was measured on a hand-picked `/usr/bin` list and marked `diskutil ok` — it was checking exit status, not output.

Two things I tested that the report got *right* and I want on the record: the profile survives a real PTY (I expected `/dev/ttysNNN` to be missing from `_DEV_WRITE`; fds are inherited, `printf 'hello\n'` returns `b'hello\r\n'` through `pty.fork`), and today's profile really is as bad as claimed —

```
cat ~/.ssh/id_ed25519  → -----BEGIN OPENSSH PRIVATE KEY-----
echo pwned > ~/...     → wrote
ls /etc/ssh            → moduli ssh_config     # the deny rule at sandbox.py:50 is DEAD
curl https://example.com → rc=6, 000            # network IS already blocked
```

So the brief's "no network restriction at all" is **false**, and the `/etc/ssh` deny is dead exactly as `sandbox-fail-direction` says.

Minor but real: `new_seatbelt.py` **does not import** — `NameError: name 'Optional' is not defined` (line 38), then `NameError: name '_seatbelt_str' is not defined` (line 116). I shimmed both to test it. "Diff-ready" it is not.

## 6. A sandbox test breaks under *both* proposals, and neither names it

`test_sandbox.py:88-101 test_invalid_writable_paths_filtered` asserts `"--bind /var/log /var/log" in wrapped` and `"--bind /tmp/ok /tmp/ok" in wrapped`. Both proposals realpath the writable set, and `os.path.realpath` runs against the **real macOS filesystem** even with `platform.system` monkeypatched to `"Linux"`:

```
/var/log  -> /private/var/log
/tmp/ok   -> /private/tmp/ok
```

So the Linux bwrap test fails on the dev box. The reports name `:74`, `:81`, `:122` — not this one.

The two `Sandbox` APIs also conflict outright: `seatbelt` proposes `Sandbox(extra_read_paths)` / `wrap_command(command, writable_paths, read_paths, allow_network)`; `sandbox-fail-direction` proposes `Sandbox(deny_read_subpaths)` / `wrap_command(command, writable_paths)` + `resolve_writable` + `_NEVER_WRITABLE`. Both cannot land.

## 7. Two smaller corrections

**The simulator is half a finding.** `approval/simulator.py:169-176` executes only when `dry_run_flag` is truthy. `settings.py:2881` (the `run_command` tool preview) passes **no flag**, so it does not execute. Only `POST /api/settings/simulate/command` (`settings.py:2796-2807`), which reads `dry_run_flag` from the request body, does. Still worth deleting; not a critical, and not model-reachable as `chokepoint` implies.

**`write_config.py` is the ungated write nobody scoped.** `grep -n "SENSITIVE\|expanduser\|classify\|safety" halbert_core/halbert_core/tools/write_config.py` → **no matches**. Reachable from MCP via `mcp/server.py:479,539` (`approve_proposal`). SEC-3's plan covers `editor.py` and the polkit helpers and misses this one entirely.

**The `/input` gap is real and cheap.** `session_manager.py:131-132` publishes `kind` and `owner` for every session through `GET /sessions`; `get()` at `:110` does not filter. So `POST /sessions/{id}/input` (`terminal.py:356`) writes raw bytes into an agent-pool bash. But the fix is a `kind()` accessor plus a refusal in three routes — it does **not** need `gate.py` and must not be held hostage to that refactor.

---

## Landing order I would actually use

**1 — SEC-2 classifier.** `safety.patched.py` as-is; `confirmed=True` in the two `test_terminal_stream_bridge.py` calls; rewrite the two now-vacuous tests in `test_agent_pool_cwd_injection.py:34-58`; wire `user_overrides` at the read-only lookup so the residual is drainable. **Measured cost: 2 tests.** Closes the critical.

**2 — SEC-3 deletions only, no new primitive.** Delete `packaging/polkit/halbert-exec-helper` (E1/E2 root-shell, verified executed), its `com.halbert.exec` action, `install.sh:22-25`; delete `_read_with_sudo`/`_write_with_sudo` (`editor.py:223`, `:277`); drop the repo-working-tree entry from `get_file_helper_path` (`editor.py:184`) — the file that ran as root was one the agent could rewrite. **Cost: zero existing tests** (`grep -rln "api/editor/file" halbert_core/tests/` → only the census and `test_write_paths_guarded.py`, neither of which touches these). That is also the warning: nothing catches a mistake here, so this commit brings its own tests. Add the `/input` + `/stage` + WS `stdin` agent-pool refusal here.

**3 — `wrap_command` raises `SandboxUnavailable`.** `test_sandbox.py:74` and `:81` invert. Profile **untouched**. Bubblewrap into `packaging/arch/PKGBUILD` etc. in the same commit or the Linux install breaks.

**4+ — deferred:** the seatbelt profile, `resolve_once` adoption at the routes, `gate.py` + the census.

## What I cut, and what that leaves open

**Cut the seatbelt profile rewrite.** It breaks git, python and brew, and reports `diskutil` as an empty success. It needs a second measurement pass: an allow set derived from `Sandbox` denial logs for the *installed* toolchain (`/Applications`, `/Library/Frameworks`, `/usr/local`, `/Volumes`), plus a rule that an empty-but-successful sandboxed result is surfaced as a sandbox failure rather than an observation. **Open until then:** on macOS a `/exec` command still reads `~/.ssh` and writes `$HOME`. That is T1 — a process already running as the owner — and SEC-1 closed the unauthenticated route. With commit 1 in, unknown commands no longer reach that shell without a prompt, so it is no longer a critical. I would give it one more measurement cycle, not one more quarter.

**Cut `resolve_once` adoption at `editor.py`.** Needs the editable-roots decision plus the string→descriptor plumbing rewrite. **Open until then:** `path.startswith('/')` at `editor.py:348`/`:388`. But the *privileged* half dies in commit 2 — no `sudo -n tee`, no repo-tree helper, no exec helper — so what remains is an owner-authenticated route writing files as the owner, which is what a config editor is. The traversal-to-root escalation goes with the helper, not with the route.

**Cut `gate.py` and the AST census.** Right end state, 59 call sites, cannot share a commit with anything. Its own PR, after 1–3 are green.

**Files:** `halbert_core/halbert_core/tools/safety.py`, `.../streaming/sandbox.py`, `.../utils/containment.py`, `.../dashboard/routes/editor.py`, `.../dashboard/routes/terminal.py`, `.../streaming/session_manager.py`, `.../tools/write_config.py`, `halbert_core/tests/test_write_paths_guarded.py`, `halbert_core/tests/test_agent_pool_cwd_injection.py`, `halbert_core/tests/test_sandbox.py`.
**Probes (re-runnable):** `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/` — `toolchain_probe.py`, `silent_probe.py`, `current_profile_probe.py`, `pty_probe.py`, `cwd_probe.py`, `cls_probe2.py`.