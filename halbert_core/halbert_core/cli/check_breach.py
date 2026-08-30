# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""CLI entry point: halbert-check-breach

Usage:
  halbert-check-breach <value> --hibp
  halbert-check-breach <value> --github
  halbert-check-breach <value> --hibp --github
  echo $PASSWORD | halbert-check-breach --hibp --stdin

Checks if a credential has been found in public breaches.

HIBP: sends only a SHA-1 hash prefix (5 chars) — the full hash never
leaves the machine (k-anonymity model).

GitHub: sends the full token to GitHub's API. GitHub is the issuing
service for GitHub tokens, so this is the same audience that would
discover the leak.
"""
from __future__ import annotations

import argparse
import json
import sys

from .compromise_detection import check_compromised


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="halbert-check-breach",
        description="Check if a credential has been compromised in public breaches.",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="The credential value to check (omit if using --stdin)",
    )
    parser.add_argument(
        "--hibp",
        action="store_true",
        help="Check passwords against Have I Been Pwned (k-anonymity, hash prefix only)",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="Check GitHub tokens against GitHub's API",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the credential value from stdin instead of an argument",
    )
    args = parser.parse_args()

    if args.stdin:
        value = sys.stdin.read().strip()
    elif args.value:
        value = args.value
    else:
        parser.error("provide a value argument or use --stdin")

    if not args.hibp and not args.github:
        parser.error("specify at least one check: --hibp and/or --github")

    result = check_compromised(
        value=value,
        enabled=True,
        hibp=args.hibp,
        github_scanning=args.github,
    )
    print(json.dumps(result, indent=2))
    if result.get("status") == "compromised":
        sys.exit(1)
    if result.get("status") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
