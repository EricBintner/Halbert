## Recommendation

**Hard-raise at the call site; decide the host's fitness once at startup; ship bubblewrap as a package dependency.** Three parts, in that order of importance:

1. `wrap_command` raises `SandboxUnavailable` — always, no risk threshold, no per-command degrade.
2. Whether *this host* may run a terminal at all is decided once, in the `CAP_TERMINAL` probe (`capabilities.py:81-95, 368-395`), not per command. No bwrap → `CAP_TERMINAL` False → the two routes 503 with a named error and the install line. The operator's escape hatch is a file they edit (`being.yml: capabilities: {terminal_unsandboxed: true}`), recorded once to `write_audit` at startup, and reflected in the `sandboxed` field `SpawnResponse` already carries (`terminal.py:107`).
3. Bubblewrap becomes a declared dependency in all four Linux packagings, so a default install is never in that state.

**Why not a risk threshold.** SEC-2 is simultaneously establishing that `_classify_command` defaults unknown to MEDIUM and that its SAFE rule is a bare prefix match. Gating containment on that score makes the sandbox exactly as good as the classifier it exists to backstop — the two layers would share one failure. Defence in depth requires they don't.

**Why not per-command consent.** Neither caller has an interactive channel: `/exec` (`terminal.py:266-269`) drains to completion and returns; `/sessions` (`terminal.py:331-332`) returns a session id. A prompt on every command is trained away in a week. Consent belongs in a file the operator edits deliberately, once.

**Why raising is nearly free today.** The only callers of `wrap_command` in the tree are `terminal.py:269` and `terminal.py:332`. The agent's own execution path — `tools/executor.py:623`, `asyncio.create_subprocess_shell(command, ...)` — never touches the sandbox, and `agent_pool.py:171` honestly publishes `"sandboxed": False`. So flipping the fail direction today breaks two HTTP routes on a bwrap-less Linux box and nothing else. **The install story must land before SEC-2 wires the agent in, not after** — that wiring is what turns this from a route error into "the assistant cannot do anything."

House pattern matched: `vision/screen_capture.py:61-67` defines `ScreenCaptureError(message, error_type=...)`; `:373-377` raises it with `error_type="unsupported_platform"`. Same shape below.

## The install story

Nothing in the tree declares bubblewrap. Verified:

- `packaging/arch/PKGBUILD` — `depends=('webkit2gtk-4.1' 'gtk3' 'python>=3.10' 'python-pip')`. No bubblewrap; `optdepends` lists only ollama.
- `packaging/flatpak/ai.halbert.dashboard.yml` — no bwrap module, and `--filesystem=home` anyway.
- `packaging/snap/snapcraft.yaml` — `confinement: classic`, no bubblewrap stage-package.
- `packaging/nix/default.nix` — `buildInputs = [ webkitgtk gtk3 glib pythonEnv ]`.
- `scripts/install-linux.sh:102-107` — installs `python3-pip` only.
- `deploy/halbert-host.service`, `packaging/systemd/system/halbert-dashboard.service` — no `ExecStartPre` capability check.

So today, raising turns a working Arch/Debian install into a broken one on first command. The install story has to become: `bubblewrap` in `depends`/`stage-packages`/`buildInputs`; `install-linux.sh` installs it alongside `python3-pip`; and the flatpak/snap cases get an explicit decision recorded — a classic-confinement snap and a `--filesystem=home` flatpak have already given away what the sandbox protects, so those two builds should set `terminal_unsandboxed` explicitly rather than pretend.

## Reviewing `_wrap_bwrap` (sandbox.py:107-121)

Every widening vector, worst first:

1. **The writable set is caller-supplied in the same request as the command** (`terminal.py:332`, `SpawnRequest.writable_paths`). The thing being contained names its own containment.
2. **`validate_path("/") is True`** — verified by running it. `--bind / /` re-binds the whole root read-write.
3. **`/proc`, `/dev`, `/tmp`, `/run` all pass `validate_path`** and would bind the host's over the `--proc`/`--dev`/`--tmpfs` the profile just set.
4. **`validate_path` is purely lexical.** It rejects `..` components but not symlinks; bwrap resolves the source on the host, so `/tmp/x → /` binds root. Same class of bug as SEC-3: two strings for one file.
5. **No `--unshare-net`, `--unshare-pid`, `--unshare-ipc`, `--unshare-uts`.** Full host network. `--proc /proc` without `--unshare-pid` still exposes host PIDs.
6. **No `--new-session`.** The process keeps the caller's controlling PTY, which is what bwrap's own `--new-session` warning is about (TTY input-injection back into the terminal).
7. **No `--die-with-parent`** — a backgrounded child outlives `manager.kill()`.
8. **No cap on the number of binds.**
9. Ordering: whether a later `--bind` overrides the earlier `--ro-bind / /` — **I could not test this.** No Linux host here (`uname -m` → `arm64`, macOS 26.5.1), `bwrap` is not installed, and the Docker daemon is down (`Cannot connect to the Docker daemon at unix:///var/run/docker.sock`). The fix below does not depend on the answer: `/` never reaches the argv.

The corrected invocation stops taking writable roots from the request. The instance's own directories are the writable set; a caller may only *narrow* it.

## The macOS profile — one audit claim is wrong, and a worse one is missing

Verified live on this Mac (macOS 26.5.1, arm64), running the real `Sandbox().wrap_command(...)` output:

```
[rc=0] read ~/.ssh: agent | config | id_ed25519
[rc=0] read shell history: 37 /Users/ericbintner/.zsh_history
[rc=0] write into $HOME: pwned
[rc=0] write outside writable set: wrote-anyway
[rc=0] read browser cookies: ActorSafetyLists | Address Validation Rules
[rc=6] network (curl): 000
```

**Correction: network is *not* unrestricted.** A `(version 1)` profile is default-deny for anything not explicitly allowed, and the profile allows no network operation. Differential test on the same box, same minute:

```
base profile           -> curl https://example.com  rc=6, 000
base + (allow network*) -> curl https://example.com  rc=0, 200
unsandboxed control     -> 200 ; nc -z 1.1.1.1 443 -> succeeded
```

**Worse, and unreported: the profile's only two read-denials are dead.** Seatbelt matches on the *resolved* path, and macOS aliases `/etc → /private/etc`, `/var → /private/var`, `/tmp → /private/tmp` (`os.path.realpath` confirms all three). Controlled test:

```
deny file-write* (subpath "/tmp")         -> echo x > /tmp/f  => WROTE       (rule dead)
deny file-write* (subpath "/private/tmp") -> echo x > /tmp/f  => Operation not permitted
deny file-read*  (subpath "/etc/ssh")         -> ls /etc/ssh => moduli       (rule dead)
deny file-read*  (subpath "/private/etc/ssh") -> ls /etc/ssh => Operation not permitted
```

So `_deny_read_subpaths = ["/etc/ssh", "/etc/ssl/private"]` (`sandbox.py:50`) protects nothing, and `(deny file-write* (subpath "/var/db"))` (`sandbox.py:155`) protects nothing. `/etc` happens to be covered because `/private/etc` is also in the list; `/var/db` has no such twin. Every seatbelt path constant must be `os.path.realpath`'d before it is emitted — again SEC-3's one primitive.

## Third branch: neither Linux nor Darwin

`sandbox.py:78` returns the command unwrapped. It is unreachable today (no Windows build), and there is no third sandbox to fall back to, so its only live effect is `test_sandbox.py:74-78`, which currently asserts that running unsandboxed *is* the correct behaviour — a test that documents the bug. It should raise `SandboxUnavailable(error_type="unsupported_platform")`, and the test should assert the raise. Note the codebase has a habit here: `config/being_config.py:552-556` treats Windows as "no `fcntl`, yield the lock anyway."

## Verified permissive fallthroughs

Confirmed from the audit's list:

| Location | Fallthrough | Severity |
|---|---|---|
| `streaming/sandbox.py:66-71`, `:78` | unavailable / unknown platform → command unwrapped | the subject |
| `vision/redact.py:184, 188, 193-195, 201` | four returns of the **unredacted** image when OCR is missing, the backend isn't Vision, or cv2 is absent — this is the screenshot path to the model | high |
| `config/being_config.py:552-556` | Windows → `yield True` with no flock; the caller believes it holds a cross-process lock | medium |
| `discovery/engine.py:100-105` | `if Darwin … else: linux scanners` | low |
| `rag/platform_loader.py:76` | `['darwin','macos'] if is_macos() else ['linux']` | low |

Missed by the audit:

| Location | Fallthrough |
|---|---|
| `context/extra_adapters.py:431-433` | input validation raises → `return {"safe": True, "blocked": False}`. A crashing validator reports *safe*. |
| `context/extra_adapters.py:445-447` | output filter raises → unfiltered LLM response returned |
| `integrations/modality_wiring.py:358-364` | `defang_user_input` returns the raw text when the demuxer is absent or raises — a T3 path, and the docstring says it "prevents prompt injection" |
| `tools/executor.py:623` | not a branch but an absence: the agent's own command path has neither sandbox nor injection check |

Three that fail **closed** and should be the lint's model: `ingestion/redaction.py:352-354` (unparseable candidate → redact), `integrations/secure_detector.py:64-68` (detector raises → `secure=True`), `dashboard/parent_watchdog.py:36-37` (EPERM → alive).

---

## Code

**`halbert_core/halbert_core/streaming/sandbox.py`** — replace lines 45-101 and 107-163:

```python
class SandboxUnavailable(RuntimeError):
    """No sandbox can be built for this command on this host.

    Carries ``error_type`` for the same reason ScreenCaptureError does: the
    route needs to say which thing is missing, not "sandbox failed".
    """

    def __init__(self, message: str, error_type: str = "unavailable"):
        super().__init__(message)
        self.error_type = error_type


class Sandbox:
    """Platform-specific command sandboxing."""

    #: Bind-mount targets a caller may never name. Binding any of these
    #: read-write undoes the profile that was just built around them.
    _NEVER_WRITABLE = frozenset({"/", "/proc", "/dev", "/sys", "/run", "/etc", "/usr", "/boot"})

    def __init__(self, deny_read_subpaths: Optional[List[str]] = None):
        # Seatbelt matches on the *resolved* path, and macOS aliases
        # /etc -> /private/etc. A rule naming the alias silently matches
        # nothing, which is how the only two read-denials in this profile
        # came to protect nothing at all.
        raw = deny_read_subpaths or ["/etc/ssh", "/etc/ssl/private"]
        self._deny_read_subpaths = [os.path.realpath(p) for p in raw]

    def wrap_command(
        self, command: str, writable_paths: Optional[List[str]] = None
    ) -> str:
        """Wrap ``command`` with a sandbox execution.

        Raises rather than returning the command unwrapped: a caller that
        asked for containment and got a bare string has no way to tell.
        Whether this host is allowed to run a terminal without one is a
        startup decision (capabilities.CAP_TERMINAL), not a per-command one.
        """
        system = platform.system()
        if system not in ("Linux", "Darwin"):
            raise SandboxUnavailable(
                f"No command sandbox on {system}",
                error_type="unsupported_platform",
            )
        if not self.is_available():
            binary = "bwrap" if system == "Linux" else "sandbox-exec"
            raise SandboxUnavailable(
                f"{binary} is not installed; install it or set "
                f"capabilities.terminal_unsandboxed in being.yml",
                error_type="missing_binary",
            )

        writable = self.resolve_writable(writable_paths)
        if system == "Linux":
            return self._wrap_bwrap(command, writable)
        return self._wrap_seatbelt(command, writable)

    def resolve_writable(self, requested: Optional[List[str]]) -> List[str]:
        """Resolve a requested writable set against the roots we own.

        The command and its writable set arrive in the same HTTP request, so
        a caller could previously name its own containment — ``/`` passed
        validate_path. A caller may now only narrow: anything not beneath a
        root this instance owns is dropped.
        """
        roots = [os.path.realpath(p) for p in (data_dir(), state_dir(), log_dir(), tempfile.gettempdir())]
        out: List[str] = []
        for p in requested or []:
            if not self.validate_path(p):
                continue
            # One resolution, used for the check and for the bind (SEC-3).
            real = os.path.realpath(p)
            if real in self._NEVER_WRITABLE:
                continue
            if any(real == r or real.startswith(r + os.sep) for r in roots):
                out.append(real)
        return out[:16]

    def validate_path(self, path: str) -> bool:
        """Lexical pre-filter. resolve_writable does the real containment."""
        if not path or not path.startswith("/"):
            return False
        if "\x00" in path or "\n" in path:
            return False
        if ".." in path.split("/"):
            return False
        return True

    def is_available(self) -> bool:
        """True if this platform's sandbox binary is installed."""
        system = platform.system()
        if system == "Linux":
            return shutil.which("bwrap") is not None
        if system == "Darwin":
            return shutil.which("sandbox-exec") is not None
        return False

    def _wrap_bwrap(self, command: str, writable: List[str]) -> str:
        argv = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--tmpfs", "/run",
            # --proc without --unshare-pid still shows every host PID, so the
            # namespace flags are part of the profile, not decoration.
            "--unshare-pid", "--proc", "/proc",
            "--unshare-ipc", "--unshare-uts", "--unshare-net",
            # Without --new-session the process keeps our controlling PTY and
            # can push characters back into it; bwrap warns about exactly this.
            "--new-session",
            "--die-with-parent",
        ]
        for p in writable:
            argv += ["--bind", p, p]
        argv += ["--", "/bin/sh", "-c", command]
        return " ".join(shlex.quote(a) for a in argv)

    def _seatbelt_profile(self, writable: List[str]) -> str:
        """Deny-by-default writes; only the paths we own are writable.

        Seatbelt's (version 1) default is deny, so network is already refused
        — verified: the same curl returns 000 under this profile and 200 with
        (allow network*) added. Every path here is realpath'd first: a rule
        naming /etc or /var/db matches nothing, because the kernel sees
        /private/etc and /private/var/db.
        """
        rules = [
            "(version 1)",
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow signal (target self))",
            "(allow file-read*)",
            "(allow file-read-metadata)",
        ]
        for p in writable:
            rules.append(f"(allow file-write* (subpath {_seatbelt_str(os.path.realpath(p))}))")
        for p in self._deny_read_subpaths:
            rules.append(f"(deny file-read* (subpath {_seatbelt_str(p)}))")
        return "\n".join(rules)
```

Add `import os, tempfile` and `from ..utils.paths import data_dir, state_dir, log_dir` at the top. `_wrap_seatbelt` is unchanged.

**`terminal.py`** — both call sites gain the same handler; `capabilities` decides, the route reports:

```python
        try:
            wrapped = Sandbox().wrap_command(command, writable_paths=request.writable_paths)
        except SandboxUnavailable as e:
            if not has_capability(CAP_TERMINAL_UNSANDBOXED):
                raise HTTPException(503, f"Refusing to run uncontained: {e}")
            # Consented once, in being.yml, and recorded at startup. Every
            # command still says so on the way out via SpawnResponse.sandboxed.
            wrapped = command
```

**`capabilities.py`** — add `CAP_TERMINAL_UNSANDBOXED = "terminal_unsandboxed"` to `ALL_CAPABILITIES`, default `False` in every preset (override-only, no probe), and in `probe()` emit once when it is on:

```python
        if self._capabilities.get(CAP_TERMINAL_UNSANDBOXED):
            write_audit("sandbox", "startup", str(uuid.uuid4()), ok=True,
                        summary="terminal running uncontained",
                        reason="being.yml capabilities.terminal_unsandboxed",
                        actor=ACTOR_SYSTEM)
```

**`scripts/lint_fail_direction.py`** — stdlib `ast` only, no new dependency. This is the scanner that found `extra_adapters.py:433` and `modality_wiring.py:364`:

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Flag safety transforms that fail open.

Two shapes, both real bugs found in this tree:
  1. a function returns its own input unchanged under a capability, platform
     or except guard -- a redactor that returns the unredacted image, a
     sandbox that returns the bare command;
  2. a permissive literal (True, {"safe": True}) returned from an except
     handler -- a validator that reports "safe" because it crashed.

An intentional fail-open needs `# fail-open: <why>` on the return line, so
every exemption is visible in the diff that introduces it.
"""
import ast, pathlib, sys

GUARD_TOKENS = ("available", "platform", "system()", "which(", "supported",
                "installed", "Windows", "Darwin", "Linux", "is None")


def _guard(node) -> str | None:
    if isinstance(node, ast.ExceptHandler):
        return "except"
    if isinstance(node, ast.If):
        t = ast.unparse(node.test)
        if t.startswith("not ") or any(k in t for k in GUARD_TOKENS):
            return f"if {t[:60]}"
    return None


def _permissive(value) -> bool:
    if isinstance(value, ast.Constant) and value.value is True:
        return True
    if isinstance(value, ast.Dict):
        return any(isinstance(v, ast.Constant) and v.value is True
                   for k, v in zip(value.keys, value.values)
                   if isinstance(k, ast.Constant) and k.value in ("safe", "allowed", "ok"))
    return False


def scan(root: pathlib.Path):
    for path in sorted(root.rglob("*.py")):
        src = path.read_text()
        lines = src.splitlines()
        try:
            tree = ast.parse(src, str(path))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
            for node in ast.walk(fn):
                guard = _guard(node)
                if not guard:
                    continue
                for st in node.body:
                    if not isinstance(st, ast.Return) or st.value is None:
                        continue
                    if "fail-open:" in lines[st.lineno - 1]:
                        continue
                    if isinstance(st.value, ast.Name) and st.value.id in params:
                        yield path, st.lineno, f"{fn.name} returns its input `{st.value.id}` under [{guard}]"
                    elif _permissive(st.value):
                        yield path, st.lineno, f"{fn.name} returns a permissive result under [{guard}]"


if __name__ == "__main__":
    found = list(scan(pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                                   else "halbert_core/halbert_core")))
    for path, line, why in found:
        print(f"{path}:{line}: {why}")
    sys.exit(1 if found else 0)
```

Run it against the tree as it stands and it prints the table above; the fixes and the `# fail-open:` annotations bring it to zero, and it stays at zero.

**Tests to change** (`halbert_core/tests/test_sandbox.py`): `test_wrap_unsupported_platform_returns_command:74-78` and `test_wrap_unavailable_binary_returns_command:81-86` currently assert the bug — both become `pytest.raises(SandboxUnavailable)` with the `error_type` checked. `test_absolute_path_valid:23` asserts `validate_path("/") is True`; keep it (it is a lexical filter) and add a `resolve_writable(["/"]) == []` test. `test_seatbelt_profile_contains_system_dir_denies:122-130` asserts `(deny file-write* (subpath "/etc"))` is present — under the deny-by-default profile there are no write-denials left to assert; replace it with a test that the emitted read-denies are realpath'd (`/private/etc/ssh`, not `/etc/ssh`).