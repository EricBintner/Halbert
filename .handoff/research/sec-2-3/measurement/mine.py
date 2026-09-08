"""Mine a realistic command corpus from the Halbert tree."""
import ast, json, re, sys
from pathlib import Path

ROOT = Path("/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door")
SCRATCH = Path("/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad")

# --- A. argv lists Halbert itself executes -------------------------------
argv_cmds = {}
SUBPROC = {"run", "Popen", "check_output", "call", "check_call",
           "_run_command", "run_command", "create_subprocess_exec"}


def literal(node):
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    parts = []
    for el in node.elts:
        if isinstance(el, ast.Constant) and isinstance(el.value, str):
            parts.append(el.value)
        elif isinstance(el, ast.JoinedStr):
            buf = []
            for v in el.values:
                buf.append(str(v.value) if isinstance(v, ast.Constant) else "X")
            parts.append("".join(buf))
        elif isinstance(el, ast.Name):
            parts.append("X")
        else:
            return None
    if not parts or not parts[0] or parts[0].startswith("X"):
        return None
    return " ".join(parts)


pyfiles = [p for p in (ROOT / "halbert_core" / "halbert_core").rglob("*.py")
           if "__pycache__" not in str(p)]
for p in pyfiles:
    try:
        tree = ast.parse(p.read_text(errors="replace"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (
            fn.id if isinstance(fn, ast.Name) else None)
        if name not in SUBPROC or not node.args:
            continue
        cmd = literal(node.args[0])
        if cmd:
            argv_cmds.setdefault(cmd, f"{p.relative_to(ROOT)}:{node.lineno}")

# --- B. shell examples from the RAG doc corpus ---------------------------
BINS = (r"(ls|cat|head|tail|grep|find|df|du|ps|top|free|uptime|whoami|id|hostname"
        r"|uname|date|echo|pwd|systemctl|journalctl|ip|ifconfig|netstat|ss|ping|dig"
        r"|nslookup|traceroute|apt|apt-get|dnf|yum|pacman|brew|port|pip|pip3|npm"
        r"|docker|kubectl|helm|git|rsync|tar|gzip|unzip|curl|wget|ssh|scp|sudo|chmod"
        r"|chown|chgrp|mkdir|rmdir|rm|mv|cp|ln|touch|stat|file|wc|sort|uniq|awk|sed"
        r"|cut|tr|xargs|which|whereis|man|lsblk|blkid|mount|umount|fdisk|parted|mkfs"
        r"|fsck|dd|smartctl|lspci|lsusb|lsmod|modprobe|dmesg|sysctl|iptables|nft|ufw"
        r"|firewall-cmd|crontab|at|kill|killall|pkill|pgrep|nice|renice|nohup|screen"
        r"|tmux|zfs|zpool|btrfs|lvs|vgs|pvs|launchctl|diskutil|sw_vers|system_profiler"
        r"|scutil|networksetup|softwareupdate|pmset|defaults|codesign|spctl|csrutil"
        r"|dscl|plutil|osascript|nvram|ioreg|log|caffeinate|tmutil|hdiutil|installer"
        r"|openssl|nmap|tcpdump|htop|iostat|vmstat|sar|lsof|strace|ltrace|nc|telnet"
        r"|ethtool|nmcli|resolvectl|timedatectl|hostnamectl|loginctl|localectl|udevadm"
        r"|lsattr|chattr|getfacl|setfacl|usermod|useradd|groupadd|passwd|visudo"
        r"|update-grub|grub-mkconfig|dracut|mkinitcpio|update-initramfs|snap|flatpak"
        r"|zypper|emerge|xbps-install|apk)")
LEAD = re.compile(r"^\s*(?:\$|#|>>>)?\s*(" + BINS + r"\b[^\n]{0,160})$")
PROSE = re.compile(r"[.,:;!?]$|\b(the|a|an|is|are|will|can|should|to|and|or|of|for|with|you|your)\b")

doc_cmds = {}
for f in sorted((ROOT / "data").rglob("*.jsonl")):
    try:
        with f.open(errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 4000:
                    break
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                content = rec.get("content") or rec.get("text") or ""
                for raw in content.split("\n"):
                    raw = raw.strip()
                    if not (3 < len(raw) <= 160):
                        continue
                    m = LEAD.match(raw)
                    if not m:
                        continue
                    cmd = m.group(1).strip()
                    if PROSE.search(cmd):
                        continue
                    if cmd.count(" ") == 0:
                        continue
                    doc_cmds.setdefault(cmd, str(f.relative_to(ROOT)))
    except Exception as e:
        print("skip", f, e, file=sys.stderr)

# --- C. fenced bash blocks in repo markdown ------------------------------
md_cmds = {}
FENCE = re.compile(r"```(?:bash|sh|shell|console|zsh)\n(.*?)```", re.S)
for p in ROOT.rglob("*.md"):
    s = str(p)
    if "node_modules" in s or "/data/" in s:
        continue
    try:
        txt = p.read_text(errors="replace")
    except Exception:
        continue
    for block in FENCE.findall(txt):
        for raw in block.split("\n"):
            raw = raw.strip()
            if raw.startswith("$ "):
                raw = raw[2:].strip()
            if not (3 < len(raw) <= 160) or raw.startswith("#"):
                continue
            if not re.match(r"^" + BINS + r"\b", raw):
                continue
            if raw.count(" ") == 0:
                continue
            md_cmds.setdefault(raw, str(p.relative_to(ROOT)))

out = {"argv": argv_cmds, "docs": doc_cmds, "md": md_cmds}
(SCRATCH / "corpus.json").write_text(json.dumps(out, indent=1))
print("argv:", len(argv_cmds), "docs:", len(doc_cmds), "md:", len(md_cmds))
