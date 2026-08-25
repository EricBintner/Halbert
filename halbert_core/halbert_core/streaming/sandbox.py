"""Command sandboxing for PTY-executed commands (B1c).

Wraps a command string with a platform-specific sandbox so agent-emitted
shell commands run with constrained write access:

- **Linux**: ``bwrap`` (bubblewrap) with the root mounted read-only and only
  the designated writable paths bind-mounted read-write.
- **macOS**: ``sandbox-exec`` with a permissive seatbelt profile that allows
  execution + broad reads, denies a few sensitive read paths, and restricts
  writes to the designated writable paths.
- **Other**: no sandbox (the command is returned unchanged).

Profiles are intentionally permissive for v1 — tighten based on testing. The
``validate_path`` gate rejects non-absolute paths, null bytes, and ``..``
traversal components before they reach a bind/profile string (injection
defense). See OPUS-HANDOFF §B1c and CROSS-CODEBASE-PATTERN-INVENTORY (OCC
sandbox.mjs / Sandbox.wrapCommand).
"""

from __future__ import annotations

import logging
import platform
import shlex
import shutil
from typing import List, Optional

logger = logging.getLogger("halbert.streaming.sandbox")


class Sandbox:
    """Platform-specific command sandboxing."""

    def __init__(self, deny_read_subpaths: Optional[List[str]] = None):
        # Sensitive read paths to deny on macOS (extend as hardened)
        self._deny_read_subpaths = deny_read_subpaths or ["/etc/ssh", "/etc/ssl/private"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wrap_command(
        self, command: str, writable_paths: Optional[List[str]] = None
    ) -> str:
        """Wrap ``command`` with a sandbox execution.

        Only validated paths from ``writable_paths`` are bound writable. If the
        platform sandbox binary is unavailable, the command is returned
        unchanged (with a warning) rather than failing the terminal.
        """
        writable = [p for p in (writable_paths or []) if self.validate_path(p)]
        if not self.is_available():
            logger.warning(
                "Sandbox unavailable on %s; running command unsandboxed",
                platform.system(),
            )
            return command

        system = platform.system()
        if system == "Linux":
            return self._wrap_bwrap(command, writable)
        if system == "Darwin":
            return self._wrap_seatbelt(command, writable)
        return command

    def validate_path(self, path: str) -> bool:
        """Validate a path is safe to bind writable in a sandbox profile.

        Must be absolute, contain no null bytes, and no ``..`` traversal
        component (rejects ``/a/../b`` but allows ``..`` inside a filename).
        """
        if not path or not path.startswith("/"):
            return False
        if "\x00" in path:
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
        """Build a seatbelt profile string allowing exec + reads, denying a
        few sensitive read paths, and restricting writes to ``writable``."""
        rules = [
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow signal (target self))",
            "(allow file-read*)",
            "(allow file-read-metadata*)",
            "(deny file-write*)",
            "(deny file-write* (subpath \"/private/etc\"))",
        ]
        for p in self._deny_read_subpaths:
            rules.append(f"(deny file-read* (subpath {shlex.quote(p)}))")
        for p in writable:
            # Re-allow writes only to the designated paths
            rules.append(f"(allow file-write* (subpath {shlex.quote(p)}))")
        # Allow writes to a few tmp/scratch locations so basic commands work
        rules.append("(allow file-write* (subpath \"/tmp\"))")
        rules.append("(allow file-write* (subpath \"/private/tmp\"))")
        return "(version 1)\n" + "\n".join(rules)