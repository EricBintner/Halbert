"""Classify the mined corpus with THIS worktree's ToolSafetyFramework."""
import json, os, sys
from collections import Counter
from pathlib import Path

WORKTREE = "/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door"
PKG_PARENT = os.path.join(WORKTREE, "halbert_core")
_KEEP = ("builtins", "_frozen_importlib", "_frozen_importlib_external")
sys.meta_path = [f for f in sys.meta_path if type(f).__module__ in _KEEP]
for name in [m for m in sys.modules if m == "halbert_core" or m.startswith("halbert_core.")]:
    del sys.modules[name]
sys.path.insert(0, PKG_PARENT)
import halbert_core
real = os.path.realpath(halbert_core.__file__)
assert real.startswith(os.path.join(PKG_PARENT, "halbert_core")), real
print("resolved:", real)

from halbert_core.tools.safety import ToolSafetyFramework

SCRATCH = Path("/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad")
corpus = json.loads((SCRATCH / "corpus.json").read_text())
fw = ToolSafetyFramework()

report = {}
for bucket, cmds in corpus.items():
    counts = Counter()
    rows = []
    for cmd, prov in cmds.items():
        r = fw.classify("run_command", {"command": cmd})
        counts[r.risk_level.value] += 1
        rows.append((cmd, r.risk_level.value, r.reason, r.matched_rule, prov))
    report[bucket] = {"counts": dict(counts), "n": len(cmds), "rows": rows}
    total = len(cmds) or 1
    print(f"\n=== {bucket}  n={len(cmds)} ===")
    for lvl in ("safe", "low", "medium", "high", "critical"):
        c = counts.get(lvl, 0)
        print(f"  {lvl:9s} {c:6d}  {100*c/total:5.1f}%")
    unrec = sum(1 for r in rows if r[2] == "Unrecognized command pattern")
    sens = sum(1 for r in rows if r[2].startswith("Accesses sensitive path"))
    print(f"  -> hit the default branch (would flip to HIGH): {unrec} ({100*unrec/total:.1f}%)")
    print(f"  -> sensitive-path fallthrough (MEDIUM today):    {sens} ({100*sens/total:.1f}%)")

(SCRATCH / "report.json").write_text(json.dumps(report, indent=1))
