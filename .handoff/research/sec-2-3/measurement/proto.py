"""Prototype of the proposed classifier, measured against the same corpus."""
import json, os, re, sys
from collections import Counter
from pathlib import Path

SCRATCH = Path("/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad")

# ---- the proposed READ_ONLY table (binary -> True | frozenset of subcommands)
ANY = True
READ_ONLY = {
    # coreutils / inspection
    "ls": ANY, "dir": ANY, "vdir": ANY, "cat": ANY, "head": ANY, "tail": ANY,
    "less": ANY, "more": ANY, "wc": ANY, "sort": ANY, "uniq": ANY, "cut": ANY,
    "tr": ANY, "column": ANY, "nl": ANY, "od": ANY, "xxd": ANY, "strings": ANY,
    "basename": ANY, "dirname": ANY, "readlink": ANY, "realpath": ANY,
    "stat": ANY, "file": ANY, "du": ANY, "df": ANY, "tree": ANY,
    "pwd": ANY, "whoami": ANY, "id": ANY, "groups": ANY, "hostname": ANY,
    "uname": ANY, "date": ANY, "uptime": ANY, "echo": ANY, "printf": ANY,
    "printenv": ANY, "env": ANY, "which": ANY, "whereis": ANY, "type": ANY,
    "command": ANY, "man": ANY, "info": ANY, "apropos": ANY, "whatis": ANY,
    "locate": ANY, "getent": ANY, "locale": ANY, "tty": ANY, "arch": ANY,
    # search
    "grep": ANY, "egrep": ANY, "fgrep": ANY, "rg": ANY, "ag": ANY, "ack": ANY,
    # process / memory
    "ps": ANY, "top": ANY, "htop": ANY, "btop": ANY, "free": ANY, "vmstat": ANY,
    "iostat": ANY, "mpstat": ANY, "sar": ANY, "pgrep": ANY, "pidof": ANY,
    "lsof": ANY, "vm_stat": ANY, "pstree": ANY, "jobs": ANY,
    # hardware / host facts
    "lspci": ANY, "lsusb": ANY, "lscpu": ANY, "lsmod": ANY, "lsblk": ANY,
    "findmnt": ANY, "blkid": ANY, "dmidecode": ANY, "sensors": ANY,
    "nvidia-smi": ANY, "rocm-smi": ANY, "nvcc": ANY, "mokutil": ANY,
    "sw_vers": ANY, "system_profiler": ANY, "ioreg": ANY, "smartctl": ANY,
    "systemd-detect-virt": ANY, "systemd-analyze": ANY, "hostnamectl": ANY,
    "localectl": ANY, "timedatectl": ANY, "loginctl": ANY,
    # network read-only
    "ping": ANY, "ping6": ANY, "traceroute": ANY, "dig": ANY, "host": ANY,
    "nslookup": ANY, "ss": ANY, "netstat": ANY, "ifconfig": ANY, "arp": ANY,
    "resolvectl": ANY, "scutil": ANY, "wg": frozenset({"show"}),
    "ip": frozenset({"addr", "a", "link", "l", "route", "r", "neigh", "n",
                     "-j", "-json", "-d", "-br", "-4", "-6", "-s"}),
    "iptables": frozenset({"-L", "-S", "--list", "--list-rules"}),
    "nft": frozenset({"list"}),
    "tailscale": frozenset({"status", "ip", "netcheck", "version", "whois"}),
    # service / log
    "journalctl": ANY, "dmesg": ANY,
    "systemctl": frozenset({"status", "show", "cat", "list-units", "list-timers",
                            "list-sockets", "list-unit-files", "list-jobs",
                            "list-dependencies", "is-active", "is-enabled",
                            "is-failed", "is-system-running", "get-default",
                            "show-environment", "--version"}),
    "launchctl": frozenset({"list", "print", "print-disabled", "dumpstate"}),
    "service": frozenset({"--status-all"}),
    # packaging (query verbs only)
    "brew": frozenset({"list", "ls", "info", "outdated", "config", "deps",
                       "search", "home", "--version", "--prefix", "--cellar",
                       "leaves", "uses", "desc", "tap-info", "doctor"}),
    "port": frozenset({"installed", "list", "info", "outdated", "echo"}),
    "apt": frozenset({"list", "show", "search", "policy", "depends", "rdepends"}),
    "apt-cache": ANY, "apt-mark": frozenset({"showhold", "showauto", "showmanual"}),
    "dpkg": frozenset({"-l", "-L", "-s", "-S", "--list", "--status", "--search"}),
    "dpkg-query": ANY,
    "rpm": frozenset({"-q", "-qa", "-qi", "-ql", "-qf", "--query"}),
    "dnf": frozenset({"list", "info", "search", "check-update", "repoquery",
                      "history", "repolist"}),
    "yum": frozenset({"list", "info", "search", "check-update", "repolist"}),
    "pacman": frozenset({"-Q", "-Qi", "-Ql", "-Qs", "-Qe", "-Qdt", "-Qdtq",
                         "-Si", "-Ss", "-F"}),
    "checkupdates": ANY, "mas": frozenset({"list", "outdated", "info"}),
    "snap": frozenset({"list", "info", "find", "changes", "connections"}),
    "flatpak": frozenset({"list", "info", "search", "history", "remotes"}),
    "pip": frozenset({"list", "show", "freeze", "check", "--version"}),
    "pip3": frozenset({"list", "show", "freeze", "check", "--version"}),
    "npm": frozenset({"ls", "list", "view", "outdated", "config", "--version"}),
    # containers / orchestration (read verbs)
    "docker": frozenset({"ps", "images", "info", "inspect", "logs", "version",
                         "stats", "port", "top", "diff", "history", "events"}),
    "podman": frozenset({"ps", "images", "info", "inspect", "logs", "version",
                         "stats", "port", "top", "diff", "history"}),
    "kubectl": frozenset({"get", "describe", "logs", "top", "explain",
                          "api-resources", "version", "cluster-info", "diff"}),
    "helm": frozenset({"list", "ls", "status", "get", "history", "show",
                       "search", "version", "template"}),
    "virsh": frozenset({"list", "dominfo", "domstate", "net-list", "pool-list"}),
    "VBoxManage": frozenset({"list", "showvminfo"}),
    # storage / backup (read verbs)
    "zfs": frozenset({"list", "get", "holds", "version"}),
    "zpool": frozenset({"list", "status", "get", "history", "iostat", "version"}),
    "btrfs": frozenset({"filesystem", "subvolume", "device", "scrub", "qgroup"}),
    "snapper": frozenset({"list", "list-configs", "get-config", "status"}),
    "diskutil": frozenset({"list", "info", "apfs", "cs"}),
    "tmutil": frozenset({"destinationinfo", "latestbackup", "listbackups",
                         "listlocalsnapshots", "status", "machinedirectory"}),
    "rclone": frozenset({"listremotes", "ls", "lsd", "lsjson", "about", "version"}),
    "kopia": frozenset({"repository", "snapshot", "policy"}),
    "exportfs": frozenset({"-v", "-s"}),
    "mount": frozenset(),  # bare `mount` only: no operands = read the table
    # source control
    "git": frozenset({"status", "log", "diff", "show", "branch", "remote",
                      "describe", "blame", "shortlog", "ls-files", "rev-parse",
                      "config", "tag", "stash", "reflog", "grep", "cat-file"}),
    # misc read
    "gsettings": frozenset({"get", "list-keys", "list-schemas", "list-recursively"}),
    "defaults": frozenset({"read", "read-type", "domains"}),
    "dscl": frozenset({"."}),  # `dscl . -read/-list` — see _dscl_readonly below
    "pactl": frozenset({"list", "info", "stat", "get-sink-volume",
                        "get-default-sink", "get-default-source"}),
    "iw": frozenset({"dev", "list", "phy"}), "iwconfig": ANY,
    "aa-status": ANY, "fail2ban-client": frozenset({"status", "get"}),
    "fpcalc": ANY, "ollama": frozenset({"list", "ps", "show"}),
    "crontab": frozenset({"-l"}),
    "sysctl": frozenset({"-a", "-n", "-A", "-e"}),  # bare `sysctl name` reads
    "csrutil": frozenset({"status"}), "spctl": frozenset({"--status", "--assess"}),
    "pmset": frozenset({"-g"}), "nvram": frozenset({"-p", "-x"}),
    "networksetup": frozenset({"-listallnetworkservices", "-getinfo",
                               "-listallhardwareports", "-getdnsservers"}),
    "codesign": frozenset({"-d", "-dv", "--display", "-v", "--verify"}),
    "plutil": frozenset({"-p", "-lint", "-convert"}),
    "softwareupdate": frozenset({"-l", "--list"}),
    "log": frozenset({"show", "stats"}),
    "ethtool": frozenset(),  # bare `ethtool <iface>` reads; flags below write
    "nmcli": frozenset({"device", "connection", "general", "networking",
                        "radio", "monitor", "-t", "-f", "-g"}),
    "firewall-cmd": frozenset({"--list-all", "--state", "--get-zones",
                               "--get-active-zones", "--list-services"}),
    "ufw": frozenset({"status"}),
    "lsattr": ANY, "getfacl": ANY, "udevadm": frozenset({"info", "monitor"}),
    "fuser": ANY, "nice": frozenset(),
}

# Flags that turn an allowlisted read verb into a write verb.
EFFECTFUL_FLAGS = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fls",
             "-fprint", "-fprint0", "-fprintf"},
    "locate": set(),
    "iptables": {"-F", "-X", "-Z", "-A", "-I", "-D", "-P", "-R", "-N"},
    "nft": {"add", "delete", "flush", "insert", "replace"},
    "ethtool": {"-s", "-K", "-G", "-C", "-A", "-p", "-r", "--change"},
    "sysctl": {"-w", "-p", "--write", "--load"},
    "git": {"--exec-path"},
    "btrfs": {"delete", "balance", "resize"},
    "zfs": {"destroy", "rollback", "receive"},
    "helm": {"--set"},
    "plutil": {"-convert", "-replace", "-insert", "-remove"},
    "log": {"collect", "erase", "config"},
}

# `find` is only read-only with an -exec-free argument list; it is common
# enough in real use to keep, but it needs its own entry.
READ_ONLY["find"] = ANY

SHELL_META = re.compile(r"[;&|`]|\$\(|>>?|<\(")


def head_and_args(seg):
    toks = seg.split()
    i = 0
    while i < len(toks) and (toks[i] in ("sudo", "doas", "env", "command", "nice")
                            or "=" in toks[i]):
        i += 1
    if i >= len(toks):
        return None, []
    return toks[i].rsplit("/", 1)[-1], toks[i + 1:]


def is_read_only(seg):
    head, args = head_and_args(seg)
    if head is None:
        return False
    entry = READ_ONLY.get(head)
    if entry is None:
        return False
    bad = EFFECTFUL_FLAGS.get(head, set())
    if any(a in bad for a in args):
        return False
    if entry is ANY:
        return True
    if not args:
        return True          # bare invocation of a query tool reads
    return args[0] in entry


def proto_classify(command):
    """SAFE if every segment is a read-only invocation, else 'gated'."""
    if SHELL_META.search(command):
        # a chained/redirected line: every segment must still be read-only
        segs = [s.strip() for s in re.split(r"&&|\|\||;|\|", command) if s.strip()]
        if ">" in command or "$(" in command or "`" in command:
            return "gated"
        return "safe" if segs and all(is_read_only(s) for s in segs) else "gated"
    return "safe" if is_read_only(command) else "gated"


corpus = json.loads((SCRATCH / "corpus.json").read_text())
rep = json.loads((SCRATCH / "report.json").read_text())

for bucket in ("argv", "docs", "md"):
    rows = rep[bucket]["rows"]
    n = len(rows)
    today_prompt = sum(1 for r in rows if r[1] in ("high", "critical"))
    plan_a_prompt = sum(1 for r in rows
                        if r[1] in ("high", "critical")
                        or r[2] == "Unrecognized command pattern"
                        or r[2].startswith("Accesses sensitive path"))
    proto_prompt = 0
    residual = []
    for cmd, lvl, reason, rule, prov in rows:
        if lvl in ("high", "critical"):
            proto_prompt += 1
            continue
        if proto_classify(cmd) == "gated":
            proto_prompt += 1
            residual.append((cmd, prov))
    print(f"\n=== {bucket}  n={n} ===")
    print(f"  today                     prompts/blocks: {today_prompt:6d}  {100*today_prompt/n:5.1f}%")
    print(f"  plan (unknown->HIGH)      prompts/blocks: {plan_a_prompt:6d}  {100*plan_a_prompt/n:5.1f}%")
    print(f"  proposal (allowlist+HIGH) prompts/blocks: {proto_prompt:6d}  {100*proto_prompt/n:5.1f}%")
    if bucket == "argv":
        print("  residual that still prompts under the proposal:")
        for c, p in residual[:40]:
            print(f"    {c[:88]:<88} {p}")
