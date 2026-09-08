import os, json, platform, shlex, shutil
from typing import List, Optional
def _seatbelt_str(path):
    return json.dumps(path)
# Diff-ready replacement for the macOS half of
# halbert_core/halbert_core/streaming/sandbox.py

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
    "/System",
    "/Library/Preferences",
    "/private/etc",
    "/private/var/db/timezone",
    "/opt/homebrew",
)

# Machine state the diagnostics exist to read.
_STATE_READ_SUBPATHS = ("/private/var/log", "/private/var/run")

_DEV_READ = (
    "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
    "/dev/dtracehelper", "/dev/tty",
)
_DEV_WRITE = (
    "/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty",
    # libproc opens this read-write on the way to a process list.
    "/dev/dtracehelper",
)


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
    """Platform-specific command sandboxing."""

    def __init__(self, extra_read_paths: Optional[List[str]] = None):
        self._extra_read_paths = extra_read_paths or []

    def wrap_command(
        self,
        command: str,
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
        readable = [
            p for p in map(_resolve_once, list(read_paths or []) + self._extra_read_paths) if p
        ]

        system = platform.system()
        if system == "Linux":
            return self._wrap_bwrap(command, writable, readable)
        return self._wrap_seatbelt(command, writable, readable, allow_network)

    def is_available(self) -> bool:
        system = platform.system()
        if system == "Linux":
            return shutil.which("bwrap") is not None
        if system == "Darwin":
            return shutil.which("sandbox-exec") is not None
        return False

    def _wrap_seatbelt(
        self, command: str, writable: List[str], readable: List[str], allow_network: bool
    ) -> str:
        profile = self._seatbelt_profile(writable, readable, allow_network)
        return f"sandbox-exec -p {shlex.quote(profile)} /bin/sh -c {shlex.quote(command)}"

    def _seatbelt_profile(
        self, writable: List[str], readable: List[str], allow_network: bool
    ) -> str:
        """A deny-by-default seatbelt profile.

        Allow-listing rather than deny-listing is what makes this worth having:
        the kernel matches resolved paths, so a symlink planted inside a
        consented directory resolves to a target outside the allow set and is
        refused. A deny-list can only refuse the secrets someone remembered.
        """
        def subpaths(kind: str, paths) -> Optional[str]:
            if not paths:
                return None
            args = " ".join(f"(subpath {_seatbelt_str(p)})" for p in paths)
            return f"(allow {kind} {args})"

        def literals(kind: str, paths) -> str:
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
