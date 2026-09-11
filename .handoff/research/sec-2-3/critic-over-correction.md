Two things changed in the tree while I was reviewing it, so state my findings against: a concurrent session landed the SEC-2 classifier rewrite into `halbert_core/halbert_core/tools/safety.py` (uncommitted, `git diff --stat` = +376/−110) partway through. `sandbox.py` and `editor.py` are untouched. Everything below is measured against that live state.

# What the six recommendations got wrong

## A. The classifier — landed, and three of its gates fire on ordinary use

**A1. `SECRET_PATHS` gates the product's flagship file.** `/etc/ssh` is in the set (`safety.py`, verified by reading `f.SECRET_PATHS`), and SECRET runs *before* the read-only table by design. Measured now:

```
high  conf=True  :: cat /etc/ssh/sshd_config
high  conf=True  :: cat ~/.ssh/config
high  conf=True  :: cat ~/.ssh/known_hosts
high  conf=True  :: ls ~/.ssh
```

`sshd_config` is the file `routes/editor.py` exists to edit; `~/.ssh/config` and `known_hosts` are ordinary troubleshooting reads. The seatbelt doc independently puts `/etc/ssh` in `_deny_read_subpaths` (`streaming/sandbox.py:50`), so the same file is gated twice for the same non-reason. **Cheaper correct version:** SECRET is a *filename* rule, not a directory rule — `id_*` (not `*.pub`), `*.pem`, `*.key`, `identity`, plus `/etc/shadow` and `/etc/sudoers`. Reading `sshd_config` and `known_hosts` is not the harm; reading a private key is. A directory-scoped SECRET on `~/.ssh` and `/etc/ssh` is precisely the gate that fires on ordinary use and gets switched off.

**A2. `user_overrides` is a loosening knob that the docstring calls a tightening knob, and it crashes.** `safety.py:543` types it `Dict[str, RiskLevel]` and `:548` documents it as "mapping command patterns to risk levels". `safety.py:802` consumes it as the read-only table's value type (`True` or a frozenset). With the documented type:

```
safe   conf=False :: wipe
RAISED TypeError: argument of type 'RiskLevel' is not iterable :: wipe --all
```

So an entry whose declared intent is `RiskLevel.CRITICAL` makes the bare command classify **SAFE**, and the same entry with any argument raises out of `classify()` — which is called unguarded at `tools/executor.py:447-453`. Fix the type or the consumer, and add the case to `verify.py`; it has 47 assertions and none of them pass a `user_overrides`.

**A3. The "always allow" button in the classifier doc is keyed on the basename alone** (`self.user_overrides.get(head)`, `safety.py:802`). Approving `systemctl show` once therefore allowlists `systemctl start`, `systemctl link`, `systemctl mask`. That is a privilege escalation delivered through the consent UI, and it is reachable by T3: injected text causes an unrecognised `systemctl …`, the owner clears the prompt with "always allow", and `systemctl` is permanently vouched for. Key it on `(head, argv[1])`, and make the button unavailable when the HIGH came from a reason other than `matched_rule="default"`.

**A4. Literal-`argv[1]` lookup refuses common invocations.** Measured:

```
high  conf=True  :: git -C /srv/app status
high  conf=True  :: docker --context default ps
```

while `git log -1`, `systemctl --user status foo` and `journalctl --user -u x` pass. The rule is inconsistent because `--user` happens to be in the frozensets and `-C`/`--context` are not. Either skip a per-binary allowlist of inert flags before the lookup (and accept that `git -c`, `docker --config`, `systemctl --root` must *not* be on it), or say plainly that a leading flag always falls to HIGH — but do not leave it accidental.

**A5. The redirection guard is a raw substring test.** `safety.py:818`, `if ">" in command: return False`:

```
high  conf=True  :: grep 'a > b' /etc/hosts
```

Any quoted `>` in a search pattern, a `--format` string or a JSON body prompts. Split segments first, then look for an unquoted redirection operator in each — `_shell_segments` already exists two lines below.

## B. Missed entirely: an allowlisted read-only command opens an interactive shell escape

`systemctl status nginx`, `git log -1` and `man sshd_config` all classify SAFE and auto-run. In a PTY they start a pager. `streaming/pty.py:289` does `child_env = dict(os.environ)`, so the child inherits the owner's `PAGER`/`LESS`/`GIT_PAGER`. Verified on this machine, real PTY:

```
$ python3 /tmp/pgr.py     # pty.fork(); GIT_PAGER='sh -c ...'; execvp git log -1
ESCAPE-RAN-AS-uid=501
```

`less` then offers `!command`, and **stdin into a live session is ungated** — `routes/terminal.py:356`, `routes/websocket.py:135`, `routes/terminal.py:407`, `streaming/agent_pool.py:264`. So the classifier auto-runs a command that opens a program whose input path deliberately bypasses the classifier. None of the six documents connects those two facts.

**Cheapest correct fix, and it costs no prompt:** `pty.py:290` already has a `self._env` overlay. Set `PAGER=cat GIT_PAGER=cat SYSTEMD_PAGER=cat MANPAGER=cat LESSSECURE=1` for agent-owned sessions, and append `--no-pager` where the binary takes it. (`LESSSECURE` is documented in `man 1 less` at line 2059 of the rendered page on this machine.) That closes more than the entire `EFFECTFUL_ARGS` table does.

Corollary for the chokepoint doc: gating `write_stdin` on "a newline-terminated write" is not soundable. A caller sends `cat /etc/shadow` and `\n` as two `POST /sessions/{id}/input` calls and every per-write classification sees a fragment. Refusing only `kind == "agent-pool"` also leaves `/stage` and user sessions — which is where the pager lands — wide open. The env fix is the control; the stdin gate is not.

## C. The sandbox proposals break the product on both platforms

**C1. The two proposals are mutually incompatible and both rewrite `sandbox.py`.** `wrap_command(command, writable_paths, read_paths, allow_network)` with a deny-by-default profile, versus `wrap_command(command, writable_paths)` with `(allow file-read*)` retained and an unconditional `--unshare-net`. Whichever lands second silently reverts the other's threat model.

**C2. The network claim in the brief is backwards, and the real state is a live product bug nobody filed.** Running the *actual current* `Sandbox().wrap_command` output:

```
CURRENT PROFILE  network: '000' rc=6
UNSANDBOXED      network: '200' rc=0
```

`(version 1)` seatbelt is default-deny and the profile at `sandbox.py:145-161` allows no network operation. So `POST /exec` and `POST /sessions` today cannot `curl`, `brew update`, `apt`, `git fetch` or `pip install` — on a machine-administration product. The sandbox-fail-direction doc then proposes `--unshare-net` for bwrap, making Linux match. That is the fail-closed that turns a working install into a broken one, and it is already half-shipped.

**C3. Both proposals destroy process visibility.** Verified here:

```
$ sandbox-exec -p '(version 1)(allow default)' /bin/ps aux
sandbox-exec: execvp() of '/bin/ps' failed: Operation not permitted
```

`ps` and `top` are setuid and cannot exec under *any* seatbelt profile; on Linux the sibling proposal adds `--unshare-pid`, so `ps aux` shows only the sandbox. The seatbelt doc reports this and ships anyway. **The structural error is that the sandbox and the allowlist are being applied to the same set of commands, so you pay both costs and gain nothing on the overlap.** Apply them to complementary sets: the vetted read-only lane runs unsandboxed (that is what vetting bought), and the sandbox goes on the unrecognised/HIGH lane where containment is the actual question. That also removes the reason to fight `ps`.

**C4. `resolve_writable` restricted to `data_dir/state_dir/log_dir/tmp` breaks the shell.** `routes/terminal.py:268` is literally `writable = [request.cwd] if request.cwd else None`. A user opening a terminal in `~/projects/foo` gets `writable == []`. Pair that with the deny-by-default read profile — whose own doc notes `ls .` fails when cwd is absent from the read set — and the terminal cannot list or write its own working directory. **Cheaper:** cwd is consented by being requested; put the realpath'd cwd in both sets and reserve the never-writable check for `/`, `/proc`, `/dev`, `/sys`, `/usr`, `/boot`, `/etc`. Also: `out[:16]` silently truncates — refuse a too-large set, do not drop paths and let the command fail mysteriously.

**C5. `--new-session` breaks interactive PTY sessions.** It setsid's the child, detaching the controlling terminal the manager allocated, so job control and Ctrl-C stop working — bwrap's own manual warns about it. I could **not** test this: no Linux available (`darwin/arm64`), `bwrap` not installed, Docker daemon down. Apply it to `/exec` (drained to completion) only, never to `/sessions`.

**C6. `CAP_TERMINAL: False` is not a 503.** `dashboard/app.py:918` uses it to decide whether `start_terminal_subsystem()` runs at all; the feature disappears rather than reporting why. And `sandbox-exec` is marked DEPRECATED in its own man page on this machine — binding CAP_TERMINAL to its presence schedules a future macOS release that silently removes the terminal.

**C7. Theatre: the sandbox badge is absent exactly when it matters.** `TerminalTile.tsx:334` renders the chip only `{session.sandboxed && …}` — the *dangerous* state renders nothing — and `agent_pool.py:171` hardcodes `"sandboxed": False`, so every agent tile is permanently in the silent state. The sandbox-fail-direction doc's consent story rests on "reflected in the `sandboxed` field `SpawnResponse` already carries" (`terminal.py:110`, computed at `:348`). It is not reflected anywhere a person can see. One line in the tile: render a loud chip for `false`.

**C8. Bubblewrap-as-dependency does not reach flatpak or snap.** The doc's own answer is to set `terminal_unsandboxed` explicitly for those two builds — i.e. the two most-installed Linux formats ship in the fail-open state, and the fail-closed buys nothing there. That is fine, but it must be stated in the packaging and in `SpawnResponse`, not left to read as "Linux is contained."

## D. SEC-3 — one fail-closed is already breaking real files, and one control is theatre

**D1. Two containment primitives are being built, which is the bug SEC-3 exists to kill.** `halbert_core/halbert_core/utils/containment.py` exists in the tree now (untracked, `resolve_once` → `ResolvedPath`); the privileged-write doc proposes `halbert_core/halbert_core/fs/containment.py` with a different API (`open_parent`/`replace_atomically`). "One primitive, used everywhere" cannot survive two modules named `containment`. Take `utils/containment.py` — it is written and its 21 tests pass.

**D2. That primitive refuses to read the two most-read config files on the machine.** Run against the tree's own code:

```
REFUSED /etc/resolv.conf  reason=symlink
REFUSED /etc/localtime    reason=symlink
OK      /etc/hosts
OK      /etc/ssh/sshd_config
```

`ls -l /private/etc | grep '^l'` on this machine shows `aliases`, `localtime`, `resolv.conf`. On Linux add `/etc/os-release`, `/etc/mtab`, and Debian's `/etc/alternatives` farm — which I could **not** verify, no Linux host here. A symlink at the *leaf* is not an escape; where it points is. **Cheaper correct version:** on a leaf symlink, `readlink` and re-walk the target from the root set, refusing only when the target lands outside — and say so: "resolv.conf points to /var/run/resolv.conf, outside the editable roots". Refusing the link itself makes the editor useless for network and time troubleshooting, and the operator gets a reason they cannot act on. Same for the `st_nlink > 1` write refusal: keep it for the root helper, drop it for writes to a file the caller already owns.

**D3. Theatre: the helper's `DENIED` list.** `ROOTS` includes `/etc` and `/usr/lib/systemd/system`. `DENIED` blocks sudoers, pam.d, shadow, ld.so.preload, polkit-1, cron. It does not block `/etc/systemd/system/*.service` — an `ExecStart=` that runs as root, and the single thing this editor exists to write — nor `/etc/ssh/sshd_config`, `/etc/profile.d/`, `/etc/environment`, `/etc/logrotate.d/` (postrotate), `/etc/apt/apt.conf.d/` (`DPkg::Post-Invoke`), `/etc/rc.local`, `/etc/network/if-up.d/`, `/etc/kernel/postinst.d/`. It enumerates roughly ten of forty-plus root-equivalent paths while the product's main use case is one of the forty. It will read as "the helper cannot be used to get root," and that is false. Either delete it, or label it a typo-guard in the docstring and put the real control where D4 says.

**D4. The per-write `auth_admin` prompt is the one the owner learns to clear — and its information content is zero.** `packaging/polkit/com.halbert.editor.policy:13,25,37`: all three `<message>` strings are static ("Authentication is required to modify system configuration files") and name no file; `:18,:30,:42` all ship `auth_admin_keep`. The privileged-write doc's fix drops `_keep` and keeps the static message, so the owner gets N identical password prompts per editing session that say nothing about which file or what change. **Cheaper correct version:** the review belongs in Halbert's own UI — the diff, the resolved target path, the backup `editor.py:427-435` already writes — and polkit does one `auth_admin` per editing session. Prompt *density* is what gets clicked through; prompt *information* is what makes a gate hold. (I could not test polkit message interpolation — no polkit on this machine — but the shipped strings are static regardless.)

**D5. The `sudo -n` fallback fires exactly where the allowlist is absent.** `routes/editor.py:266-267` reaches `_write_with_sudo` on `returncode == 127` and `:271-272` on `FileNotFoundError` — i.e. when the helper is missing, which is the source-install case. The doc calls it "unreachable-by-success on macOS"; on Linux it is reachable precisely in the configuration with no allowlist. Removing it is right; the reason is stronger than stated. Note the consequence to write down or the line gets re-added: after dropping the repo-working-tree entry at `editor.py:176-181`, every dev worktree has no privileged path and root files are read-only there.

## E. Two confirmations, not critiques

- `approval/simulator.py:176-182` really does `subprocess.run(f"{command} {dry_run_flag}", shell=True)`. Worse than reported: `:169-173` scans for `'rm -rf'`, `'dd if='`, `'mkfs'`, appends a warning string — and then executes anyway. `warnings` is never consulted before the `subprocess.run`. A check that detects the danger and runs the command is theatre in its purest form.
- The default branch really is `RiskLevel.HIGH` now, and it is uncommitted. Before the allowlist landed mid-review I measured 29/35 = **83%** of ordinary sysadmin commands prompting; after it, 3/35 = 9% (`docker compose ps`, `curl -sS localhost:8765/api/health`, `python3 --version`). The lesson for sequencing: the two-line default flip existed alone in the working tree for a window, and in that window the tree had maximum friction *and* the `find … -exec` bypass still open. Land them as one commit or not at all.

**Also:** `Intent(actor="agent"|"owner")` filled in by the call site (chokepoint doc) is not authorization — every call site can write `actor="owner"`. Derive it from the request/session context inside `gate.py`, or the field is decoration.

**Scratch/probe files:** `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/{cls,friction,pass,p3,p4}.py`, `/tmp/pgr.py`. I removed a stray untracked file named `--no-pager` from the worktree root.