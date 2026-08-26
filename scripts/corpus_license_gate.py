#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Build-time licence gate for the Halbert RAG corpus.

LEG-CRIT-01 step 3 / LEG-MAJ-05 — the assertion that stops non-commercial or
copyleft content from entering a bundle that cannot legally carry it.

Two modes:

  plan    (default)  What *would* ship for a channel, and why everything else
                     is excluded. Run before packaging to build the file list.

  audit   (--bundle) What a real tree actually contains. Run after staging and
                     again on the extracted bundle. Non-zero exit = do not ship.

The audit is not a path allowlist: it reads JSONL records too, because a single
file used to mix CC BY-NC SS64 pages with Halbert-authored guides. A path check
alone would have shipped them.

Usage:
    # what would ship
    python scripts/corpus_license_gate.py --channel macos-app-store

    # gate a staged bundle (exit 1 on any violation)
    python scripts/corpus_license_gate.py --channel macos-pro --bundle build/data

    # every channel at once, machine-readable
    python scripts/corpus_license_gate.py --all-channels --json

    # replacement-coverage contracts only
    python scripts/corpus_license_gate.py --coverage

Exit codes:
    0  clean
    1  violations found (or coverage gaps with --coverage)
    2  usage / configuration error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "halbert_core"))

try:
    from halbert_core.corpus.license_policy import LicensePolicy
except ImportError as exc:  # pragma: no cover - misconfigured checkout
    print(f"error: cannot import the licence policy engine: {exc}", file=sys.stderr)
    print("       expected halbert_core/halbert_core/corpus/license_policy.py", file=sys.stderr)
    raise SystemExit(2)


GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
NC = "\033[0m"


def _c(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{NC}" if enabled else text


def plan(policy: LicensePolicy, channel: str, colour: bool, verbose: bool) -> Dict[str, Any]:
    report = policy.evaluate(channel)
    ch = policy.channel(channel)

    print(f"\n{_c('CHANNEL', YELLOW, colour)} {channel} — {ch.description}")
    print(
        f"  commercial={ch.commercial}  drm={ch.drm}  "
        f"data_roots={','.join(ch.data_roots)}  max_copyleft={ch.max_copyleft}"
    )
    print(f"\n  {_c('SHIPS', GREEN, colour)} ({len(report.included)} paths)")
    for decision in report.included:
        print(f"    + {decision.path:<40} {decision.license_spdx}")

    print(f"\n  {_c('EXCLUDED', RED, colour)} ({len(report.excluded)} paths)")
    shown: Dict[str, int] = {}
    for decision in report.excluded:
        reason = decision.reasons[0] if decision.reasons else "?"
        if not verbose:
            # Collapse the long tail of "wrong platform" exclusions.
            if reason.startswith("data root"):
                shown[reason] = shown.get(reason, 0) + 1
                continue
        print(f"    - {decision.path:<40} {decision.license_spdx}")
        for reason_line in decision.reasons:
            print(f"      {_c('·', DIM, colour)} {reason_line}")
    for reason, count in sorted(shown.items()):
        print(f"    - {_c(f'({count} paths)', DIM, colour)} {reason}")

    if report.advisories:
        print(f"\n  {_c('ADVISORY', YELLOW, colour)}")
        for advisory in sorted(set(report.advisories)):
            print(f"    ! {advisory}")

    return report.to_dict()


def audit(policy: LicensePolicy, channel: str, bundle: Path, colour: bool) -> Dict[str, Any]:
    advisories: List[str] = []
    violations = policy.audit_tree(bundle, channel, advisories=advisories)
    label = f"{channel} :: {bundle}"
    if violations:
        print(f"\n{_c('FAIL', RED, colour)} {label} — {len(violations)} violation(s)")
        for violation in violations:
            print(f"  ✗ {violation}")
    else:
        print(f"\n{_c('PASS', GREEN, colour)} {label} — no licence violations")
    for advisory in advisories:
        print(f"  {_c('!', YELLOW, colour)} {advisory}")
    return {
        "violations": [v.to_dict() for v in violations],
        "advisories": advisories,
    }


def coverage(policy: LicensePolicy, colour: bool) -> Dict[str, List[str]]:
    gaps = policy.coverage_gaps()
    print(f"\n{_c('COVERAGE CONTRACTS', YELLOW, colour)}")
    for contract in policy.coverage_contracts:
        cid = contract.get("id", "unnamed")
        missing = gaps.get(cid, [])
        if missing:
            print(f"  {_c('✗', RED, colour)} {cid}: {len(missing)} uncovered")
            for key in missing[:20]:
                print(f"      missing replacement for: {key}")
            if len(missing) > 20:
                print(f"      ... and {len(missing) - 20} more")
        else:
            print(f"  {_c('✓', GREEN, colour)} {cid}: quarantined content is 100% replaced")
            print(f"      {contract.get('quarantined')} -> {contract.get('replacement')}")
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--channel",
        action="append",
        dest="channels",
        default=None,
        help="Distribution channel (repeatable). Default: all channels in plan mode.",
    )
    parser.add_argument("--all-channels", action="store_true", help="Evaluate every channel")
    parser.add_argument(
        "--bundle",
        default=None,
        help="Audit a real corpus tree (the directory that becomes `data/` in the bundle)",
    )
    parser.add_argument("--coverage", action="store_true", help="Check replacement-coverage contracts only")
    parser.add_argument(
        "--print-paths",
        action="store_true",
        help="Print the includable corpus paths for one channel, one per line (for build scripts)",
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report on stdout")
    parser.add_argument("--verbose", action="store_true", help="List every excluded path individually")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colour")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root")
    args = parser.parse_args()

    colour = sys.stdout.isatty() and not args.no_color

    try:
        policy = LicensePolicy.load(repo_root=Path(args.repo_root))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result: Dict[str, Any] = {}
    failed = False

    if args.print_paths:
        if not args.channels or len(args.channels) != 1:
            print("error: --print-paths needs exactly one --channel", file=sys.stderr)
            return 2
        try:
            for path in policy.included_paths(args.channels[0]):
                print(path)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.coverage:
        gaps = coverage(policy, colour)
        result["coverage"] = gaps
        failed = any(gaps.values())
        if args.json:
            print(json.dumps(result, indent=2))
        return 1 if failed else 0

    channels = args.channels or (sorted(policy.channels) if (args.all_channels or not args.bundle) else None)
    if not channels:
        print("error: --bundle needs at least one --channel", file=sys.stderr)
        return 2

    for channel in channels:
        try:
            policy.channel(channel)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.bundle:
        bundle = Path(args.bundle)
        if not bundle.exists():
            print(f"error: bundle path does not exist: {bundle}", file=sys.stderr)
            return 2
        result["audits"] = {}
        for channel in channels:
            outcome = audit(policy, channel, bundle, colour)
            result["audits"][channel] = outcome
            failed = failed or bool(outcome["violations"])
    else:
        result["plans"] = {}
        for channel in channels:
            result["plans"][channel] = plan(policy, channel, colour, args.verbose)
        gaps = coverage(policy, colour)
        result["coverage"] = gaps
        failed = any(gaps.values())

    print()
    if args.json:
        print(json.dumps(result, indent=2))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
