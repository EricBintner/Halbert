## 1. Ground truth: `sandbox-exec` on this machine

```
$ sw_vers                       ProductVersion: 26.5.1  BuildVersion: 25F80  (arm64)
$ ls -l /usr/bin/sandbox-exec    -rwxr-xr-x 1 root wheel 102560 May 21 04:57
$ man 1 sandbox-exec | head      NAME
                                 sandbox-exec - execute within a sandbox (DEPRECATED)
$ sandbox-exec -p '(version 1)(allow default)' /bin/echo hi 2>err 1>out
  stdout:[hi] stderr:[]
```

Present, functional, **silent** — the deprecation lives only in the man page, nothing is printed at runtime. SBPL `version 1` accepts everything I needed: `deny default`, `subpath`, `literal`, `global-name`, `file-read*`/`file-read-data`/`file-read-metadata`, `file-write*`/`file-write-data`, `file-ioctl`, `process-exec`, `process-info*`, `sysctl-read`, `mach-lookup`, `network-outbound`, `system-socket`.

## 2. Two corrections to the brief, both load-bearing

**(a) Seatbelt is not allow-by-default.** `sandbox.py:136` says it is, and the whole profile is built on that premise. It is false:

```
$ sandbox-exec -p '(version 1)' /bin/echo hi
sandbox-exec: execvp() of '/bin/echo' failed: Operation not permitted   (exit 71)
```

A bare `(version 1)` denies everything. The profile at `sandbox.py:145-161` is therefore *already* deny-by-default — it just hands back nearly all of it with `(allow file-read*)` at :149 and `(allow file-write*)` at :150.

**(b) The current profile already denies network.** The brief says "no network restriction at all". Running the current profile verbatim:

```
ssh-private-key   READABLE     home-write   WRITABLE     tcp-outbound   denied
halbert-api-token READABLE     ps           BROKEN       nc-outbound    denied
chrome-profile    READABLE     log-show     BROKEN
keychain-dir      READABLE     launchctl    BROKEN
```

(unsandboxed baseline: everything READABLE/WRITABLE/OPEN/ok). So the current profile has it exactly backwards — it leaks every credential store, and breaks `ps`, `log show` and `launchctl`. It pays the whole cost of a sandbox and buys nothing.

## 3. Deny-by-default: the empirical minimum viable allow set

Deny-by-default does break dyld, and the break is one specific rule. `(deny default)(allow process-exec)(allow file-read* (subpath "/usr/lib") (subpath "/System") …)` gives:

```
$ ... /bin/sh -c 'echo shell-ok'
Abort trap: 6   (rc=134, no output)

$ log show --predicate 'sender == "Sandbox"' --style compact
Sandbox: sh(61375)     deny(1) file-read-data /
Sandbox: df(61381)     deny(1) file-read-data /
Sandbox: python3(61388) deny(1) file-read-data /
```

dyld reads the **data of `/` itself** before it maps the shared cache. Add `(allow file-read-data (literal "/"))` plus `(allow file-read-metadata)` and everything starts:

```
--- narrow3 sh ---     rc=0  shell-ok
--- narrow3 df ---     rc=0  114 lines
--- narrow3 vm_stat -- rc=0  Mach Virtual Memory Statistics…
--- narrow3 ls /etc -- rc=0  114 lines
```

That is the entire "dyld problem". No cryptex path, no `/var/db/dyld` (neither exists on macOS 26), no `(import "bsd.sb")`. Minimum viable set: `process-exec`, `process-fork`, `file-read-metadata`, `file-read-data` on `/`, and `file-read*` on the binary/library subpaths. Overhead is 14 ms per invocation.

## 4. `writable_paths` is dead for a reason nobody noticed — and it is the SEC-3 bug

Seatbelt matches the **resolved vnode**, not the text in the profile. Two identical profiles differing only in the spelling of one path:

```
=== profile says /tmp/sbxw (UNRESOLVED) ===
  touch /tmp/sbxw/a          → Operation not permitted
  touch /private/tmp/sbxw/b  → Operation not permitted
=== profile says /private/tmp/sbxw (RESOLVED) ===
  touch /tmp/sbxw/c          → rc=0
  touch /private/tmp/sbxw/d  → rc=0
```

A rule naming `/tmp/x` grants **nothing at all**. `validate_path` (`sandbox.py:80-92`) never calls `realpath`, so even once `writable_paths` is honoured, `terminal.py:268` passing `cwd="/tmp/foo"` would silently produce a rule that does nothing. This is literally SEC-3's "two different strings for one file", inside the sandbox layer. The fix is the same primitive: resolve once, use the resolved string for the rule.

The same property is what makes an allowlist worth more than a denylist. Symlink escape out of a consented read root:

```
$ ln -s ~/.ssh /private/tmp/sbxr/escape
$ sandbox-exec -f cand.sb /bin/cat /private/tmp/sbxr/escape/id_ed25519
cat: /private/tmp/sbxr/escape/id_ed25519: Operation not permitted
$ sandbox-exec -f cand.sb /bin/cat /private/tmp/sbxr/note.txt
hello-consented
```

A denylist can only refuse the secrets someone remembered to enumerate. This refuses everything not named, through symlinks, for free.

## 5. Two hard ceilings I could not work around

**Setuid binaries cannot be exec'd under *any* seatbelt profile.** Not a rule I got wrong — `(allow default)` does not help:

```
$ sandbox-exec -p '(version 1)(allow default)' /bin/ps aux
sandbox-exec: execvp() of '/bin/ps' failed: Operation not permitted
$ sandbox-exec -p '(version 1)(allow default)' /usr/bin/top -l 1 -n 0
sandbox-exec: execvp() of '/usr/bin/top' failed: Operation not permitted
$ ls -l /bin/ps /usr/bin/top
-rwsr-xr-x  1 root  wheel  /bin/ps
-r-sr-xr-x  1 root  wheel  /usr/bin/top
```

`ps` and `top` are permanently unavailable inside a seatbelt sandbox. (Copying `/bin/ps` to strip the bit fails too — SIGKILL 9, the copy breaks its platform code signature.) `pgrep`/`pkill` are not setuid and do work.

**`log show` refuses to run when sandboxed**, by its own choice, not the kernel's:

```
$ sandbox-exec -f min2.sb /usr/bin/log show --last 1m --style compact
log: Cannot run while sandboxed
```

`syslog` and `cat /private/var/log/system.log` still work, so log diagnostics degrade rather than vanish.

## 6. `mach-lookup` must be named service by service

Blanket `(allow mach-lookup)` re-opens the Keychain that the file rules just closed — securityd is a mach service, so denying `~/Library/Keychains` on disk buys nothing:

```
=== no mach-lookup ===
$ security list-keychains
security: SecKeychainCopySearchList: One or more parameters passed to a function were not valid.
=== blanket (allow mach-lookup) ===
$ security list-keychains
    "/Users/ericbintner/Library/Keychains/login.keychain-db"
    "/Library/Keychains/System.keychain"
$ security find-generic-password -s halbert-nonexistent-probe
security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.   ← a real query reached securityd
```

Three named services recover the diagnostics that need IPC without that: `com.apple.sysmond` (pgrep — the denial log named it directly), `com.apple.DiskArbitration.diskarbitrationd` (diskutil), `com.apple.system.opendirectoryd.libinfo`. With those three plus `(allow process-info*)`, and the Keychain still shut:

```
uname ok   sw_vers ok   sysctl ok    ifconfig ok   netstat ok    diskutil ok
syslog ok  systemlog ok pgrep ok     sysdiag ok    iostat ok     hostname ok
id ok      stat ok      grep ok      sed ok        perl ok       sqlite3 ok    openssl ok
du BROKEN  lsof BROKEN  nettop BROKEN
$ security list-keychains   → SecKeychainCopySearchList: … not valid.
```

`du -sh /private/etc` and `lsof -p 1` are BROKEN unsandboxed too (permissions, not the sandbox). Only `nettop` is a genuine loss.

I also probed the classic LaunchServices escape — `open` reaching launchservicesd to spawn an unsandboxed child. Blocked both with and without mach-lookup (`kLSNoExecutableErr`, then `_LSOpenURLsWithCompletionHandler() failed with error -54`); Calculator did not launch (`pgrep -x Calculator` → nothing, before and after).

## 7. Verdict on the ceiling

Ship it, and say what it is. Seatbelt is undocumented, deprecated, and has a history of escapes I cannot audit; it is a **second layer, not the layer**. But the honest comparison is not "seatbelt vs. a formally verified sandbox", it is "seatbelt vs. what is in the tree today", and today's profile actively leaks `~/.ssh`, the api-token and every browser cookie store to any command the classifier waves through. A deny-by-default profile that empirically refuses all four while leaving 17 of 22 real diagnostics working is a large, cheap, measurable improvement.

Two things it does **not** justify: (a) relaxing SEC-2's classifier — the sandbox does not contain writes to a consented `cwd`, does not contain `rm -rf` inside it, and cannot run under the agent's own execution path until it is wired there; (b) any claim of containment on Linux-without-bwrap or on a third platform, which is why `wrap_command` must raise rather than return the bare command at `sandbox.py:71` and `:78`.

## 8. Diff-ready code

Full file at `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/sb/new_seatbelt.py`; the generated profile it emits (verified above) at `.../scratchpad/sb/final.sb`. Replaces `sandbox.py:15`, `:48-50`, `:56-92`, `:133-163`.

```python
class SandboxUnavailable(RuntimeError):
    """Raised when this platform has no sandbox to run the command under."""

    def __init__(self, message: str, error_type: str = "unsupported_platform"):
        super().__init__(message)
        self.error_type = error_type


# The OS itself. dyld, the shell and every /usr/bin diagnostic live here; a
# profile that omits any of these aborts the process before main() runs.
_SYSTEM_READ_SUBPATHS = (
    "/bin", "/sbin",
    "/usr/bin", "/usr/sbin", "/usr/lib", "/usr/libexec", "/usr/share",
    "/System", "/Library/Preferences", "/private/etc",
    "/private/var/db/timezone", "/opt/homebrew",
)

# Machine state the diagnostics exist to read.
_STATE_READ_SUBPATHS = ("/private/var/log", "/private/var/run")

_DEV_READ = ("/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
             "/dev/dtracehelper", "/dev/tty")
_DEV_WRITE = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty",
              # libproc opens this read-write on the way to a process list.
              "/dev/dtracehelper")


def _resolve_once(path: str) -> Optional[str]:
    """The one string this path will be known by, or None if it is unusable.

    Seatbelt matches the *resolved* vnode, not the text in the profile: a rule
    naming ``/tmp/x`` grants nothing at all, because every open of it arrives at
    the kernel as ``/private/tmp/x``. Resolving here — once, and using the
    result for the rule — is the same discipline the file helpers need.
    """
    if not path or not path.startswith("/") or "\x00" in path:
        return None
    resolved = os.path.realpath(path)
    return resolved if resolved.startswith("/") else None


class Sandbox:
    def __init__(self, extra_read_paths: Optional[List[str]] = None):
        self._extra_read_paths = extra_read_paths or []

    def wrap_command(
        self, command: str,
        writable_paths: Optional[List[str]] = None,
        read_paths: Optional[List[str]] = None,
        allow_network: bool = False,
    ) -> str:
        """Wrap ``command`` with a sandbox execution.

        Raises SandboxUnavailable rather than handing back a bare command: a
        caller that asked to be contained and silently was not is worse than a
        caller that fails.
        """
        if not self.is_available():
            raise SandboxUnavailable(
                f"No sandbox available on {platform.system()}",
                error_type="unsupported_platform",
            )
        writable = [p for p in map(_resolve_once, writable_paths or []) if p]
        readable = [p for p in map(_resolve_once,
                                   list(read_paths or []) + self._extra_read_paths) if p]
        if platform.system() == "Linux":
            return self._wrap_bwrap(command, writable, readable)
        return self._wrap_seatbelt(command, writable, readable, allow_network)

    def _seatbelt_profile(self, writable, readable, allow_network) -> str:
        """A deny-by-default seatbelt profile.

        Allow-listing rather than deny-listing is what makes this worth having:
        the kernel matches resolved paths, so a symlink planted inside a
        consented directory resolves to a target outside the allow set and is
        refused. A deny-list can only refuse the secrets someone remembered.
        """
        def subpaths(kind, paths):
            if not paths:
                return None
            args = " ".join(f"(subpath {_seatbelt_str(p)})" for p in paths)
            return f"(allow {kind} {args})"

        def literals(kind, paths):
            args = " ".join(f"(literal {_seatbelt_str(p)})" for p in paths)
            return f"(allow {kind} {args})"

        rules = [
            "(version 1)",
            "(deny default)",
            # Setuid binaries (ps, top) cannot be exec'd under any seatbelt
            # profile; process-exec here is for everything else.
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            "(allow process-info*)",
            # Named one service at a time. Blanket mach-lookup reaches securityd
            # and reads the Keychain the file rules below just closed.
            '(allow mach-lookup (global-name "com.apple.sysmond")'
            ' (global-name "com.apple.DiskArbitration.diskarbitrationd")'
            ' (global-name "com.apple.system.opendirectoryd.libinfo"))',
            # dyld reads the data of "/" before it maps the shared cache.
            "(allow file-read-metadata)",
            '(allow file-read-data (literal "/"))',
            subpaths("file-read*", _SYSTEM_READ_SUBPATHS + _STATE_READ_SUBPATHS),
            literals("file-read*", _DEV_READ),
            literals("file-write-data", _DEV_WRITE),
            literals("file-ioctl", ("/dev/tty", "/dev/null", "/dev/dtracehelper")),
        ]
        # A writable directory is useless unread, and dangerous if the command
        # can write a script there and then run it.
        rules.append(subpaths("file-read*", readable + writable))
        rules.append(subpaths("file-write*", writable))
        if writable:
            args = " ".join(f"(subpath {_seatbelt_str(p)})" for p in writable)
            rules.append(f"(deny process-exec {args})")
        if allow_network:
            rules.append("(allow network-outbound (remote tcp) (remote unix-socket))")
            rules.append("(allow system-socket)")
        return "\n".join(r for r in rules if r)
```

Verified end-to-end through this code path (profile emitted by `_seatbelt_profile`, `writable_paths=["/tmp/sbxw"]` deliberately passed unresolved):

```
ssh-private-key denied   halbert-api-token denied   chrome-profile denied
keychain-dir    denied   home-write        denied   writable-path  WRITABLE
tcp-outbound    denied   nc-outbound       denied
/private/tmp/sbxw/y.sh → bad interpreter: Operation not permitted   (noexec holds)
NET=1 → http=200, and ~/.ssh/id_ed25519 still Operation not permitted
```

**Callers to change.** `terminal.py:267-269` and `:331-332` must now pass the realpath'd `cwd` in **both** `read_paths` and `writable_paths` (a cwd absent from the read set makes `ls .` fail: `ls: .: Operation not permitted`), catch `SandboxUnavailable` and return 503 rather than running bare, and decide `allow_network` from the classifier — a per-command bit, defaulting off.

**Tests.** All 14 in `halbert_core/tests/test_sandbox.py` pass today; `test_wrap_unsupported_platform_returns_command` (:76) and `test_wrap_unavailable_binary_returns_command` (:83) invert to `pytest.raises(SandboxUnavailable)`, the `validate_path` class (:14-42) is replaced by `_resolve_once` cases including `/tmp/x → /private/tmp/x`, and `test_wrap_macos_seatbelt` (:65) should assert `(deny default)` present and `(allow file-read*)` **absent**.