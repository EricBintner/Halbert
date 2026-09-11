# SEC-3 · The privileged write path

Everything below is from this tree at `3cd680db`, or from a command run on this machine (macOS 26.5.1, arm64, Darwin 25.5.0, sudo 1.9.17p2, Python 3.10.9).

---

## 1. The escalations that exist today

### 1a. The exec helper has no caller

```
$ grep -rn "halbert-exec-helper\|halbert_exec_helper" . | grep -v node_modules | grep -v '^./.git/'
packaging/polkit/com.halbert.editor.policy:44
packaging/polkit/install.sh:24
packaging/polkit/install.sh:25
packaging/polkit/halbert-exec-helper:9      (its own usage string)
```

No Python, TypeScript or Rust invokes it. `install.sh:24-25` copies it to `/usr/local/bin` and `com.halbert.editor.policy:35-46` registers it as a root-reachable polkit action. It is pure attack surface with zero product value.

### 1b. `exec "$@"` after a `basename` check — arbitrary root code execution

`halbert-exec-helper:58` takes `CMD_NAME=$(basename "$1")`, checks that **name** against the list, then `exec "$@"` at `:76` — running `$1` **as given**. Tested:

```
$ python probe.py
=== exec helper: basename bypass (argv[1] is a path) ===
rc=0 stdout='PWNED: /private/tmp/.../scratchpad/esc/evil/find executed, euid=501'
```

Literal argv, run as root via `pkexec /usr/local/bin/halbert-exec-helper <argv>`:

| # | argv | Result |
|---|---|---|
| E1 | `["/tmp/pwn/find"]` | **Root shell.** Any attacker-writable file named `find` (or any of the 40 names) executes as root. No cleverness required. |
| E2 | `["find", "/etc", "-maxdepth", "0", "-exec", "/bin/sh", "-c", "echo 'u ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/x", ";"]` | **Root shell.** Verified locally: `rc=0 stdout='ARBITRARY-SHELL euid=501'`. |
| E3 | `["sysctl", "-w", "kernel.core_pattern=|/tmp/pwn %P"]` | Root exec on the next crash of any process. `["sysctl","-w","kernel.modprobe=/tmp/pwn"]` is the same shape. |
| E4 | `["mount", "--bind", "/tmp/fake-sudoers", "/etc/sudoers"]` | Replaces any file or tree on the system with attacker content, no write to disk. |
| E5 | `["systemctl","link","/tmp/pwn.service"]` then `["systemctl","start","pwn.service"]` | Root `ExecStart=` from a user-writable unit file. |
| E6 | `["cat", "/etc/shadow"]` — also `head`/`tail`/`grep` | Read any file on the system as root. Not a bug in the check; it is what the list says. |
| E7 | `["hdparm","--security-erase","p","/dev/sda"]`, `["parted","-s","/dev/sda","mklabel","gpt"]`, `["zpool","destroy",...]`, `["btrfs","subvolume","delete",...]` | Destroys the disk. |
| E8 | `["iptables","-F"]`, `["ufw","disable"]` | Silently removes the firewall. |

E1 and E2 are verified on this machine; E3–E8 are read off the allowlist plus each tool's documented behaviour — I have no Linux here to run them on and am not asserting them as executed.

### 1c. The file helper: unnormalised string prefix, then `cat >`

`halbert-file-helper:31` is `[[ "$FILE_PATH" == "$allowed"* ]]`. Tested:

```
/etc/../root/.ssh/authorized_keys                  PASSED allowlist
/etc/../../../../root/.ssh/authorized_keys         PASSED allowlist
/var/lib/../../etc/sudoers.d/pwn                   PASSED allowlist
/usr/lib/systemd/../../../home/victim/.ssh/...     PASSED allowlist
/root/.ssh/authorized_keys                         REJECTED
```

(The `PASSED` rows then died at `[ ! -f ]` only because those paths don't exist on macOS — and the **write** branch at `:50-52` has no existence check at all, it goes straight to `cat >`.) Proven end to end against a rebased allowlist:

```
$ python probe2.py
write rc=0 stderr=''
victim file now: 'ATTACKER KEY\n'      # via <root>/etc/../secret/authorized_keys
```

Two more, same file:

- **Symlink follow.** `cat > "$FILE_PATH"` follows a symlink at the leaf. Verified: writing through a link under a permitted directory overwrote a target outside it (`target now: OVERWRITTEN-THROUGH-SYMLINK`). A root-writable `/var/lib/**` is enough.
- **`/etc/` is not a boundary.** Even with traversal fixed, `write /etc/sudoers.d/x` is permanent root, as are `/etc/ld.so.preload` and `/etc/pam.d/sudo`.

### 1d. The policy file: two of the three actions are decorative

`com.halbert.editor.policy` annotates `org.freedesktop.policykit.exec.path` on `com.halbert.exec` only (`:44`). pkexec selects an action *by* that annotation, so `pkexec halbert-file-helper` — the only helper anything actually calls — cannot match `com.halbert.editor.read` or `.write`. Those two actions, and their messages, never appear. (Structural claim from the file; the pkexec selection rule I could not test — no polkit on this machine.)

`com.halbert.exec` **does** match, and it ships `auth_admin_keep` (`:41`), so one password opens polkit's default caching window during which the agent can re-invoke E1–E8 with no further prompt.

---

## 2. The replacement

### 2a. O_TMPFILE + linkat is the wrong primitive

```
$ python -c "import os; print(hasattr(os,'O_TMPFILE'), hasattr(os,'linkat'))"
False False
```

`O_TMPFILE` does not exist on Darwin, and CPython has no `os.linkat` on any platform. Beyond portability, `linkat` cannot *replace* — `link(2)` fails `EEXIST` when the target exists, which is the editor's normal case — so an O_TMPFILE flow still needs a rename. (The `EEXIST` point is documented API behaviour; untested here.)

The portable primitive is **dirfd-relative create + `os.rename` with `src_dir_fd`/`dst_dir_fd`**. Both are in `os.supports_dir_fd` on this machine, `rename` never follows a symlink at its destination, and it is atomic within a directory. Tested:

```
1 traversal blocked: traversal
2 symlink leaf blocked: ContainmentError not_a_file
3 symlink dir blocked: NotADirectoryError 20 ENOTDIR
4 write ok: content='new\n' mode=644;  victim untouched: 'ORIGINAL\n'
```

Note case 3: `O_NOFOLLOW` on a symlinked *directory* gives `ENOTDIR` on Darwin where Linux gives `ELOOP` — catch `OSError`, never match errno.

One platform trap the walk must handle: on macOS `/etc`, `/var` and `/tmp` are themselves symlinks, so a strict walk cannot even reach them.

```
$ ls -ld /etc          lrwxr-xr-x  /etc -> private/etc
   /etc  O_NOFOLLOW open FAILED: 20 Not a directory
   /private/etc  O_NOFOLLOW open: OK
```

So: **realpath the configured roots once at startup, then walk strictly only below a resolved root.** That is exactly `RESOLVE_BENEATH` semantics — trust the root prefix, distrust everything under it — and needs no `openat2`, no ctypes, no Linux-only path.

### 2b. macOS gets no privileged write path

```
$ which pkexec                      → not found (exit 1)
$ sudo -n true                      → sudo: a password is required   (rc=1)
$ subprocess.run(['pkexec','true']) → FileNotFoundError: [Errno 2] 'pkexec'
$ subprocess.run(['sudo','-n','tee','/tmp/x'])
                                    → rc=1  stderr='sudo: a password is required\n'
```

Today `pkexec` raises `FileNotFoundError` at `editor.py:207`/`:261`, so macOS falls into `_write_with_sudo`, which cannot succeed. The two honest options are SMAppService + AuthorizationServices, or nothing.

**Recommend nothing.** A blessed helper is a permanently-installed root LaunchDaemon reachable over XPC by whatever can satisfy `SMAuthorizedClients` — a *larger* liability than the bash script it replaces, and directly in the T3/T4 blast radius. It needs a Developer ID that SEC-16 says the project does not have, so building it now means building an unverifiable thing. The cost of "no": on macOS, editing `/etc/ssh/sshd_config` from the dashboard is read-only, and the save hands the user a command. Revisit only after SEC-16 lands signing **and** there is real demand.

### 2c. Linux polkit: one action per verb, and never `_keep`

pkexec binds an action to a program path, so per-verb actions mean two entry points. That is worth the two files: a "Read system configuration file" prompt must not silently authorize a write, and the message a human reads before typing a password is the only place the distinction lives.

```xml
<action id="com.halbert.config.write">
  <description>Modify a system configuration file</description>
  <message>Authentication is required to modify a system configuration file</message>
  <defaults>
    <allow_any>no</allow_any>
    <allow_inactive>no</allow_inactive>
    <allow_active>auth_admin</allow_active>
  </defaults>
  <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/halbert/halbert-config-write</annotate>
</action>
```

`auth_admin`, **not** `auth_admin_keep`: the design premise is that a human sees each privileged write, and `_keep` deletes exactly that for the duration of polkit's caching window. `no` on `allow_any`/`allow_inactive`: a privileged config write requires a local, active seat. `com.halbert.exec` is deleted, not fixed.

---

## 3. The helper

`halbert_core/halbert_core/fs/containment.py` — the resolve-once primitive, shared by the helper and by the unprivileged routes:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Resolve a path once, and use that one resolution for both the check and
the open.

Every finding in SEC-3 is the same bug: a string is checked and a different
string is opened. A returned fd cannot drift between the two.
"""
import os
import secrets
import stat

_DIR = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)


class ContainmentError(Exception):
    """Raised when a path may not be opened (traversal, symlink, outside root)."""

    def __init__(self, message: str, error_type: str = "outside_root"):
        super().__init__(message)
        self.error_type = error_type


def resolve_roots(roots):
    """Roots are resolved once, at startup. On macOS /etc, /var and /tmp are
    symlinks into /private, so a strict walk cannot reach them by their
    conventional names; below a root nothing is trusted at all.
    """
    return tuple(os.path.realpath(r).rstrip("/") + "/" for r in roots)


def open_parent(path, roots):
    """(parent_fd, leaf, resolved) for `path`, following no symlink below the
    root. The caller records `resolved`, never `path`.
    """
    if not path.startswith("/"):
        raise ContainmentError("path must be absolute", "not_absolute")
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise ContainmentError("path must name a file", "not_a_file")
    if any(p in (".", "..") for p in parts):
        raise ContainmentError("path must be literal", "traversal")

    fd, walked = os.open("/", _DIR), ""
    try:
        for part in parts[:-1]:
            # ENOTDIR on Darwin, ELOOP on Linux -- both mean "a symlink was in
            # the way", so the errno is never matched on.
            nxt = os.open(part, _DIR, dir_fd=fd)
            os.close(fd)
            fd, walked = nxt, walked + "/" + part
        resolved = walked + "/" + parts[-1]
        if not any(resolved.startswith(r) for r in roots):
            raise ContainmentError("outside the permitted roots: " + resolved)
        return fd, parts[-1], resolved
    except Exception:
        os.close(fd)
        raise


def replace_atomically(path, content: bytes, roots) -> str:
    """Replace `path` with `content`, preserving mode and ownership.

    rename(2) does not follow a symlink at its destination, so a planted link
    is replaced rather than written through -- which is the failure the bash
    helper had.
    """
    fd, leaf, resolved = open_parent(path, roots)
    try:
        try:
            st = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode):
                raise ContainmentError("not a regular file: " + resolved, "not_a_file")
            mode, uid, gid = stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid
        except FileNotFoundError:
            mode, uid, gid = 0o600, -1, -1

        tmp = ".halbert-%s.tmp" % secrets.token_hex(8)
        tfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                      0o600, dir_fd=fd)
        try:
            os.write(tfd, content)
            os.fchmod(tfd, mode)
            if uid != -1:
                os.fchown(tfd, uid, gid)
            os.fsync(tfd)
        finally:
            os.close(tfd)
        os.rename(tmp, leaf, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
        return resolved
    finally:
        os.close(fd)


def read_contained(path, roots) -> bytes:
    fd, leaf, resolved = open_parent(path, roots)
    try:
        ffd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(ffd).st_mode):
                raise ContainmentError("not a regular file: " + resolved, "not_a_file")
            out = bytearray()
            while chunk := os.read(ffd, 1 << 16):
                out += chunk
            return bytes(out)
        finally:
            os.close(ffd)
    finally:
        os.close(fd)
```

`packaging/polkit/halbert-config-helper` — Python, verb from a closed enum, containment redone here because the caller's check is not evidence:

```python
#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Runs as root under pkexec. It reads or replaces one file under one of the
roots below, and it can do nothing else -- no shell, no argv passthrough, no
program name from the caller.

Editing any of DENIED is indistinguishable from "become root permanently",
and no human can be expected to notice which of those a save was.
"""
import sys

from halbert_core.fs.containment import (
    ContainmentError, read_contained, replace_atomically, resolve_roots)

ROOTS = resolve_roots(("/etc", "/usr/lib/systemd/system",
                       "/usr/local/lib/systemd/system", "/var/lib"))
DENIED = ("/etc/sudoers", "/etc/sudoers.d/", "/etc/pam.d/", "/etc/shadow",
          "/etc/gshadow", "/etc/ld.so.preload", "/etc/ld.so.conf.d/",
          "/etc/polkit-1/", "/etc/cron.d/", "/etc/crontab")

VERBS = ("read", "write")


def main(argv):
    if len(argv) != 3 or argv[1] not in VERBS:
        sys.stderr.write("usage: halbert-config-helper {read|write} <path>\n")
        return 2
    verb, path = argv[1], argv[2]
    if any(path.startswith(d) for d in DENIED):
        sys.stderr.write("refused: %s grants permanent root\n" % path)
        return 3
    try:
        if verb == "read":
            sys.stdout.buffer.write(read_contained(path, ROOTS))
        else:
            replace_atomically(path, sys.stdin.buffer.read(), ROOTS)
    except ContainmentError as e:
        sys.stderr.write("refused (%s): %s\n" % (e.error_type, e))
        return 3
    except OSError as e:
        sys.stderr.write("failed: %s\n" % e)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

The two polkit entry points are 2-line `sh` shims with a compile-time verb and no interpolation:

```sh
#!/bin/sh
exec /usr/libexec/halbert/halbert-config-helper write "$@"
```

**Delete:** `packaging/polkit/halbert-exec-helper`, `install.sh:22-25`, the `com.halbert.exec` action (`policy:34-46`), and `editor.py:214-232` and `:268-287`.

---

## 4. Helper resolution

**One compiled-in absolute path. No search, no `__file__`, no environment.**

```python
_HELPER = "/usr/libexec/halbert/halbert-config-write"

def helper_path() -> Optional[str]:
    """The installed helper, or None. Deliberately not a search: the repo
    working tree entry this replaces made the program that runs as root a
    file the same user -- and the agent -- can rewrite first.
    """
    from ...utils.platform import is_linux
    return _HELPER if is_linux() and os.path.isfile(_HELPER) else None
```

`editor.py:174` is the bug: a source checkout is writable by T1 and by the agent itself (T4), and that file was then executed as root. Also drop `os.access(p, os.X_OK)` at `:177` — it asks about the invoking user's rights, which is not the question, and it is a TOCTOU besides.

**A source install has no privileged path.** `packaging/polkit/install.sh` is what turns a checkout into an installed system; until it has run, `helper_path()` is `None` and the editor behaves exactly as it does on macOS. That is also the right behaviour in a dev worktree.

---

## 5. What the user sees instead

`_read_with_sudo` / `_write_with_sudo` are removed outright — proven above to be unreachable-by-success on macOS, and on Linux they bypassed the helper's allowlist entirely by handing `tee` an arbitrary path.

`FileReadResponse` gains `privileged_write: Literal["polkit", "unavailable"]` beside the existing `needs_sudo` (`editor.py:35`, already rendered as an orange chip at `ConfigEditor.tsx:465`). When it is `"unavailable"`, the save writes the proposed content to a staging file under `get_config_dir()/pending/` and returns **409 with the literal command**:

```
This file needs root, and Halbert has no privileged path on this machine.
The change is staged. To apply it yourself:

  sudo install -m 0644 -o root -g wheel \
    ~/Library/Application Support/halbert/pending/etc_ssh_sshd_config \
    /etc/ssh/sshd_config
```

The backup already exists (`editor.py:427-435`) and the refusal is already recorded on both planes with `ok=False` (`:466-472`) — that path needs no change. The user gets a complete answer rather than a shrug, and Halbert never holds root it cannot account for.

---

## Deferred to SEC-16

Only one thing: **whether macOS ever gets a privileged write path at all.** That requires a Developer ID signing identity, a `SMAppService` daemon plist, and an `SMAuthorizedClients` code requirement pinning the calling app — none of which can be built or tested without the certificate SEC-16 records as missing. Nothing above is blocked on it: Linux gets the full helper now, macOS gets honest read-only-plus-a-command now, and if SEC-16 lands signing the decision is reopened on its merits rather than by default.

**Also worth raising with the founder** (out of scope here, same class): `storage.py:521-523` and `:680` and `macos/thermal.py:81` call `sudo -n` against paths and expect NOPASSWD sudoers entries. If any such entry ships, `sudo -n` stops being harmless and every argument passed to it becomes a root-argument surface.

**Files:**
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/packaging/polkit/halbert-exec-helper` (delete)
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/packaging/polkit/halbert-file-helper` (replace)
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/packaging/polkit/com.halbert.editor.policy`
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/packaging/polkit/install.sh`
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/halbert_core/halbert_core/dashboard/routes/editor.py`
- `/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/halbert_core/halbert_core/fs/containment.py` (new)

**Probes** (re-runnable): `/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/probe.py`, `probe2.py`, `prim.py`