"""What does a second maintenance pass on the allowlist buy?"""
import json, sys
from pathlib import Path
sys.path.insert(0, "/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad")
import proto
from proto import READ_ONLY, ANY, proto_classify

SCRATCH = Path("/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad")
rep = json.loads((SCRATCH / "report.json").read_text())

before = sum(1 for r in rep["argv"]["rows"]
             if r[1] in ("high", "critical") or proto_classify(r[0]) == "gated")

# One maintenance pass, taken straight off the residual list.
READ_ONLY.update({
    "who": ANY, "w": ANY, "last": ANY, "getenforce": ANY, "kextstat": ANY,
    "xrandr": frozenset({"--query", "-q"}), "efibootmgr": frozenset({"-v", "--verbose"}),
    "mdadm": frozenset({"--detail", "--examine", "-D", "-E"}),
    "swapon": frozenset({"--show", "-s"}), "testparm": frozenset({"-s", "--suppress-prompt"}),
    "pw-cli": frozenset({"info", "ls", "dump"}), "pipewire": frozenset({"--version"}),
    "powerprofilesctl": frozenset({"get", "list"}), "tlp-stat": ANY,
    "fdesetup": frozenset({"status", "list", "isactive"}),
    "socketfilterfw": frozenset({"--getglobalstate", "--getstealthmode",
                                 "--listapps", "--getblockall"}),
    "lxc": frozenset({"list", "info", "config"}),
    "prime-select": frozenset({"query"}), "route": frozenset({"-n", "get"}),
    "iw": frozenset({"dev", "list", "phy", "reg"}),
    "mas": frozenset({"list", "outdated", "info", "account"}),
    "docker": READ_ONLY["docker"] | {"system"},
    "snapper": READ_ONLY["snapper"] | {"-c"},
    "tailscale": READ_ONLY["tailscale"] | {"drive"},
    "systemctl": READ_ONLY["systemctl"] | {"--user", "--system", "--failed"},
    "snap": READ_ONLY["snap"] | {"services", "version"},
    "flatpak": READ_ONLY["flatpak"] | {"remote-ls"},
    "ollama": READ_ONLY["ollama"] | {"--version"},
    "mount": frozenset({"-t"}),
})
proto.READ_ONLY = READ_ONLY

after = sum(1 for r in rep["argv"]["rows"]
            if r[1] in ("high", "critical") or proto_classify(r[0]) == "gated")
n = len(rep["argv"]["rows"])
print(f"argv n={n}")
print(f"  1 allowlist pass  : {before:4d} prompt  ({100*before/n:.1f}%)")
print(f"  2 allowlist passes: {after:4d} prompt  ({100*after/n:.1f}%)")
print("  still prompting:")
for c, lvl, reason, rule, prov in rep["argv"]["rows"]:
    if lvl in ("high", "critical") or proto_classify(c) == "gated":
        print(f"    [{lvl:8s}] {c[:80]}")
