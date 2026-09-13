# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""CLI entry points: halbert-backup / halbert-restore.

The vault for the terminal — the same engines the dashboard routes
call, for the operator at a shell instead of a browser. The passphrase
is read interactively when --passphrase is absent so it never lands in
shell history.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


def _passphrase(args) -> str:
    if args.passphrase:
        return args.passphrase
    first = getpass.getpass("Backup passphrase: ")
    second = getpass.getpass("Confirm passphrase: ")
    if first != second:
        print("passphrases do not match", file=sys.stderr)
        sys.exit(2)
    if not first:
        print("a backup passphrase may not be empty", file=sys.stderr)
        sys.exit(2)
    return first


def backup_main() -> None:
    parser = argparse.ArgumentParser(
        prog="halbert-backup",
        description="Create an encrypted State Vault archive of this entity.",
    )
    parser.add_argument(
        "--path", required=True,
        help="Directory the .halbert-backup archive is written to")
    parser.add_argument(
        "--passphrase", default=None,
        help="Encryption passphrase; prompted interactively when absent")
    args = parser.parse_args()

    from ..backup.encrypt import CryptoUnavailable
    from ..backup.vault import create_backup
    try:
        archive = create_backup(_passphrase(args), Path(args.path))
    except CryptoUnavailable as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"backup failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Backup created: {archive}")


def restore_main() -> None:
    parser = argparse.ArgumentParser(
        prog="halbert-restore",
        description="Restore this entity from a .halbert-backup archive.",
    )
    parser.add_argument("--path", required=True, help="The archive file")
    parser.add_argument(
        "--passphrase", default=None,
        help="Decryption passphrase; prompted interactively when absent")
    args = parser.parse_args()

    passphrase = args.passphrase or getpass.getpass("Backup passphrase: ")
    from ..backup.restore import RestoreError, restore_backup
    try:
        report = restore_backup(Path(args.path), passphrase)
    except RestoreError as e:
        print(f"restore refused: {e}", file=sys.stderr)
        sys.exit(4)
    except Exception as e:
        print(f"restore failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Restored {report.entity_name or 'the entity'} "
          f"(backup {report.backup_date}): "
          f"{report.memory_count} memories, {report.thread_count} threads")
    for w in report.warnings:
        print(f"  warning: {w}", file=sys.stderr)
    for q in report.quarantined:
        print(f"  quarantined: {q}", file=sys.stderr)


if __name__ == "__main__":
    backup_main()
