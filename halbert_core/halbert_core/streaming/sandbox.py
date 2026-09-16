# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Command sandboxing for PTY-executed commands (B1c).

Wraps a command string with a platform-specific sandbox so agent-emitted
shell commands run with constrained write access:

- **Linux**: ``bwrap`` (bubblewrap) with the root mounted read-only and only
  the designated writable paths bind-mounted read-write.
- **macOS**: ``sandbox-exec`` with a permissive seatbelt profile that allows
  execution + broad reads, denies a few sensitive read paths, and restricts
  writes to the designated writable paths.
- **Other**: raises ``SandboxUnavailable``.

Two invariants this module now holds, both learned the expensive way
(2026-09-07 security remediation):

**Fail loudly or not at all.** A sandbox that cannot be built used to hand
the command back *unwrapped*, which no caller can detect. And a jail that
fails *silently* is worse than none: the previous seatbelt profile blocked
all network by accident (``curl`` returned rc=6 for everything), so the
product silently could not ``brew``/``git fetch``/``pip install`` while its
own comment claimed "normal commands usable". A machine that cannot curl
must say so; it must not lie in rc=0.

**Rules must name real paths.** Seatbelt matches the *resolved* vnode:
macOS aliases ``/etc`` → ``/private/etc``, ``/var`` → ``/private/var``,
``/tmp`` → ``/private/tmp``, so every rule written against the alias matched
nothing — the two read-denials this profile existed to provide protected
zero bytes. Every path constant here is ``os.path.realpath``'d first.

**The lanes are complementary, not stacked.** Callers classify first: a
vetted read-only command (SAFE/LOW) runs bare — vetting is what bought
that — and everything else runs jailed. Stacking both on the same commands
pays both costs to gain nothing on the overlap, and some commands
(``ps``/``top`` are setuid) physically cannot run under seatbelt at all.

**Network is out of scope for v1, explicitly.** The profile allows it.
Egress policy belongs to the command classifier and, after SEC-5/SEC-11, to
the Lease model — not to a filesystem sandbox that was accidentally
denying it. Writing that down is the difference between a choice and a bug.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shlex
import shutil
from typing import List, Optional

logger = logging.getLogger("halbert.streaming.sandbox")


class SandboxUnavailable(RuntimeError):
    """No sandbox can be built for this command on this host.

    Carries ``error_type`` for the same reason ScreenCaptureError does: the
    route needs to say which thing is missing, not "sandbox failed".
    """

    def __init__(self, message: str, error_type: str = "unavailable"):
        super().__init__(message)
        self.error_type = error_type


def _seatbelt_str(path: str) -> str:
    """Quote a path as a seatbelt string literal (double-quoted).

    shlex.quote produces shell quoting (single quotes / backslashes) which
    seatbelt does NOT understand — a bare ``/etc`` token is read as a variable
    reference ("unbound variable: /etc"). Seatbelt uses Lisp-style double-
    quoted strings, so we use json.dumps.
    """
    return json.dumps(path)


class Sandbox:
    """Platform-specific command sandboxing."""

    #: Bind-mount targets a caller may never name. Binding any of these
    #: read-write undoes the profile that was just built around them
    #: (``validate_path("/")`` was previously True, which beats bwrap's
    #: ``--ro-bind / /`` with a plain ``--bind / /``).
    _NEVER_WRITABLE = frozenset({
        os.path.realpath(p)
        for p in (
            "/", "/proc", "/dev", "/sys", "/run", "/etc", "/usr", "/boot",
            "/bin", "/sbin", "/lib", "/lib64", "/System", "/Library",
        )
    })

    def __init__(self, deny_read_subpaths: Optional[List[str]] = None):
        # Sensitive read paths to deny on macOS (extend as hardened).
        # Seatbelt matches on the *resolved* path, and macOS aliases
        # /etc -> /private/etc, so a rule naming the alias silently matches
        # nothing. Resolve every constant once, here.
        raw = deny_read_subpaths or ["/etc/ssh", "/etc/ssl/private"]
        self._deny_read_subpaths = [os.path.realpath(p) for p in raw]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wrap_command(
        self, command: str, writable_paths: Optional[List[str]] = None
    ) -> str:
        """Wrap ``command`` with a sandbox execution.

        Raises ``SandboxUnavailable`` rather than returning the command
        unwrapped: a caller that asked for containment and got a bare string
        had no way to tell. Whether this host may run a terminal without one
        is an operator decision (``capabilities.terminal_unsandboxed`` in
        being.yml), not a silent property of the call.
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
                f"{binary} is not installed; install it, or set "
                f"capabilities.terminal_unsandboxed: true in being.yml",
                error_type="missing_binary",
            )
        writable = self._resolve_writable(writable_paths or [])
        if system == "Linux":
            return self._wrap_bwrap(command, writable)
        return self._wrap_seatbelt(command, writable)

    def _resolve_writable(self, requested: List[str]) -> List[str]:
        """Resolved writable set, minus the paths that undo the profile.

        Seatbelt (and a symlink on Linux) makes ``/tmp/x`` a different string
        than the vnode the kernel sees, so the bind/rule must name the
        resolved path or it grants nothing — or worse, grants the wrong thing.
        A requested path that survives neither is dropped; a requested path
        in _NEVER_WRITABLE is refused outright, not narrowed.
        """
        out: List[str] = []
        for p in requested:
            if not self.validate_path(p):
                continue
            real = os.path.realpath(p)
            if real in self._NEVER_WRITABLE or any(
                real.startswith(r + os.sep) for r in self._NEVER_WRITABLE
            ):
                logger.warning("refusing writable sandbox path: %s", p)
                continue
            out.append(real)
        return out

    def validate_path(self, path: str) -> bool:
        """Validate a path is safe to bind writable in a sandbox profile.

        Must be absolute, contain no null bytes, and no ``..`` traversal
        component (rejects ``/a/../b`` but allows ``..`` inside a filename).
        """
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

    # ------------------------------------------------------------------
    # Linux: bwrap
    # ------------------------------------------------------------------

    def _wrap_bwrap(self, command: str, writable: List[str]) -> str:
        """bwrap: read-only root + writable bind mounts, then the command."""
        argv = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--tmpfs", "/run",
        ]
        for p in writable:
            # Bind the same path inside the sandbox read-write
            argv += ["--bind", p, p]
        argv += ["--", "/bin/sh", "-c", command]
        return " ".join(shlex.quote(a) for a in argv)

    # ------------------------------------------------------------------
    # macOS: sandbox-exec (seatbelt)
    # ------------------------------------------------------------------

    def _wrap_seatbelt(self, command: str, writable: List[str]) -> str:
        """sandbox-exec with a permissive profile + restricted writes."""
        profile = self._seatbelt_profile(writable)
        # sandbox-exec -p '<profile>' /bin/sh -c '<command>'
        return f"sandbox-exec -p {shlex.quote(profile)} /bin/sh -c {shlex.quote(command)}"

    def _seatbelt_profile(self, writable: List[str]) -> str:
        """Build the permissive seatbelt profile for v1.

        Seatbelt's ``(version 1)`` is deny-by-default for anything not named,
        then this profile hands back nearly everything: execution, broad
        reads, and — deliberately, after a silent-denial bug that made every
        sandboxed command unable to reach the network — network. What it
        actually denies is writes to system directories and reads under the
        credential-store paths from ``deny_read_subpaths``.

        Every path is resolved first: a rule written against ``/etc`` matches
        nothing, because the kernel only ever sees ``/private/etc``. That is
        not a hypothetical — it is exactly how the two read-denials in the
        previous profile came to protect nothing at all.
        """
        rules = [
            "(version 1)",
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow signal (target self))",
            "(allow file-read*)",
            "(allow file-write*)",
            # Explicit, not accidental: network policy is the classifier's
            # job (and the Lease's, after SEC-5), not this layer's. The
            # previous profile denied network *unintentionally*, which made a
            # machine-administration product unable to `curl`. See the module
            # docstring — a jail may fail loudly, it may not lie.
            "(allow network*)",
        ]
        # Deny writes to system directories (override the broad allow above).
        # Resolved, or the /etc alias protects nothing.
        system_dirs = [
            os.path.realpath(d)
            for d in ("/etc", "/usr", "/System", "/Library",
                      "/bin", "/sbin", "/var/db")
        ]
        for d in dict.fromkeys(system_dirs):
            rules.append(f"(deny file-write* (subpath {_seatbelt_str(d)}))")
        # Deny reads to credential-store paths (already resolved in __init__).
        for p in self._deny_read_subpaths:
            rules.append(f"(deny file-read* (subpath {_seatbelt_str(p)}))")
        return "\n".join(rules)
