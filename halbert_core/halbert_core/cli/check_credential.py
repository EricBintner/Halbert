# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""CLI entry point: halbert-check-credential

Usage:
  halbert-check-credential <value> --service github
  halbert-check-credential <value> --service openai
  echo $TOKEN | halbert-check-credential --service github --stdin

Checks if a credential is still active by calling the issuing service's
API. The credential is sent over HTTPS to the service itself — not to
any LLM vendor. This is the same call a human would make to test a key.
"""
from __future__ import annotations

import argparse
import json
import sys

from .credential_validation import validate_credential, available_services


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="halbert-check-credential",
        description="Check if a credential is still active against the issuing service's API.",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="The credential value to check (omit if using --stdin)",
    )
    parser.add_argument(
        "--service", "-s",
        required=True,
        help=f"Service to check against. Available: {', '.join(available_services())}",
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

    result = validate_credential(
        value=value,
        service=args.service,
        enabled=True,
    )
    print(json.dumps(result, indent=2))
    if result.get("status") == "invalid":
        sys.exit(1)
    if result.get("status") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
