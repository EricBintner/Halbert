# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Restore — the archive becomes the entity again.

The order is deliberate: open the tar, read the manifest, derive the
key, and decrypt and digest-check EVERY member in memory before a
single byte is written. A wrong passphrase fails on the first sealed
member with nothing touched; a tampered member fails its digest the
same way. Only when the whole archive checks out does the restore
write.

Files that exist and differ are quarantined beside themselves (the
same posture promotion takes) — a restore must never silently destroy
state it is not replacing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .encrypt import decrypt_file, derive_key
from .manifest import BACKUP_SCHEMA_VERSION, BackupManifest, ManifestError
from .vault import ARCHIVE_SUFFIX

logger = logging.getLogger('halbert.backup.restore')


class RestoreError(RuntimeError):
    """The archive cannot be trusted — nothing was written."""


@dataclass
class RestoreReport:
    entity_name: str = ""
    backup_date: str = ""
    memory_count: int = 0
    thread_count: int = 0
    files_restored: List[str] = field(default_factory=list)
    quarantined: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _read_archive(archive_path: Path) -> Dict[str, bytes]:
    with tarfile.open(archive_path, "r:*") as tar:
        return {m.name: tar.extractfile(m).read()
                for m in tar.getmembers() if m.isfile()}


def _destinations(manifest: BackupManifest) -> Dict[str, Path]:
    """member name → where it belongs on this machine."""
    from ..utils.paths import data_dir
    from ..utils.platform import get_config_dir
    from haloysius.paths import state_dir

    config_dir = Path(get_config_dir())
    data = Path(data_dir())
    persona = manifest.entity_name or "halbert"

    dests: Dict[str, Path] = {}
    for member in manifest.files:
        if member.startswith("config/"):
            dests[member] = config_dir / member[len("config/"):-len(".enc")]
        elif member == "databases/memories.json.enc":
            dests[member] = state_dir("personas", persona) / "memories.json"
        elif member == "databases/conversations.db.enc":
            dests[member] = data / "conversations.db"
        elif member == "databases/state_ledger.db.enc":
            dests[member] = data / "state_ledger.db"
        elif member == "databases/timeline.db.enc":
            dests[member] = data / "timeline.db"
        elif member == "databases/findings.db.enc":
            dests[member] = data / "findings" / "findings.db"
    return dests


def _quarantine_and_write(data: bytes, dest: Path, quarantined: List[str]) -> None:
    dest = Path(dest)
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() \
            != hashlib.sha256(data).hexdigest():
        aside = dest.with_name(f"{dest.name}.quarantined-{int(time.time())}")
        dest.rename(aside)
        quarantined.append(str(aside))
        logger.warning("%s diverged from the archive — quarantined to %s",
                       dest.name, aside.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def restore_backup(
    archive_path: Path,
    passphrase: str,
) -> RestoreReport:
    """Restore from a .halbert-backup archive.

    Raises RestoreError when the archive is unreadable, the passphrase is
    wrong, or a member fails its digest — in every case before a file is
    written.
    """
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise RestoreError(f"no such archive: {archive_path}")

    try:
        members = _read_archive(archive_path)
    except Exception as e:
        raise RestoreError(f"archive unreadable: {e}")

    raw_manifest = members.get("manifest.json")
    if raw_manifest is None:
        raise RestoreError("archive carries no manifest.json")
    try:
        manifest = BackupManifest.from_json(raw_manifest.decode())
    except ManifestError as e:
        raise RestoreError(f"manifest rejected: {e}")
    if manifest.schema_version != BACKUP_SCHEMA_VERSION:
        raise RestoreError(
            f"archive schema {manifest.schema_version} is not "
            f"{BACKUP_SCHEMA_VERSION} — this restore predates it")
    if not manifest.kdf_salt or not manifest.kdf_iterations:
        raise RestoreError("manifest carries no KDF parameters")

    key = derive_key(
        passphrase, bytes.fromhex(manifest.kdf_salt), manifest.kdf_iterations)

    # Decrypt + digest-check EVERYTHING first — nothing writes until the
    # whole archive proves itself.
    plaintext: Dict[str, bytes] = {}
    for member, entry in manifest.files.items():
        blob = members.get(member)
        if blob is None:
            raise RestoreError(f"manifest claims {member} but it is absent")
        if entry.get("encrypted"):
            try:
                pt = decrypt_file(blob, key, member)
            except Exception:
                raise RestoreError(
                    f"{member} will not decrypt — wrong passphrase or a "
                    f"tampered archive") from None
            if hashlib.sha256(pt).hexdigest() != entry.get("sha256"):
                raise RestoreError(
                    f"{member} decrypted but its digest does not match "
                    f"the manifest — do not trust this archive")
            plaintext[member] = pt
        else:
            plaintext[member] = blob

    # The signing key must parse as a real key — restoring a malformed
    # one would be a silent identity break (INTEG-08).
    warnings: List[str] = []
    body_key = plaintext.get("identity/body.key.enc")
    if body_key is not None and len(body_key) < 32:
        raise RestoreError(
            "identity/body.key.enc is not a plausible private key — "
            "refusing to install it")
    if manifest.key_exported and body_key is None:
        warnings.append(
            "manifest says the key was exported but the archive has no "
            "body.key.enc — identity was NOT restored")

    report = RestoreReport(
        entity_name=manifest.entity_name,
        backup_date=manifest.created_at,
        warnings=warnings,
    )

    # Entity-name drift is a warning, not a failure — a restore onto a
    # differently-named install is legitimate (it IS a different body).
    try:
        from ..identity import resolve_entity_name
        current = resolve_entity_name()
        if manifest.entity_name and current != manifest.entity_name:
            report.warnings.append(
                f"archive entity is {manifest.entity_name!r}, this node's "
                f"entity is {current!r} — restoring anyway")
    except Exception:
        pass

    dests = _destinations(manifest)
    quarantined: List[str] = []
    for member, data in plaintext.items():
        dest = dests.get(member)
        if dest is None:
            continue  # identity/did.txt and friends are informational
        _quarantine_and_write(data, dest, quarantined)
        report.files_restored.append(member)

    # The signing key goes through the file keystore — the portable
    # custody; resolve_signer picks it up on next boot.
    if body_key is not None:
        try:
            from ..crypto.storage import FileKeyStore, DEFAULT_KEY_ID
            FileKeyStore().store(DEFAULT_KEY_ID, body_key)
            report.files_restored.append("identity/body.key.enc")
        except Exception as e:
            report.warnings.append(
                f"body.key could not be stored ({type(e).__name__}: {e}) — "
                f"identity was NOT restored")

    report.quarantined = quarantined

    # Counts for the report.
    mem = plaintext.get("databases/memories.json.enc")
    if mem is not None:
        try:
            report.memory_count = len(json.loads(mem).get("memories", []))
        except Exception:
            pass
    conv = plaintext.get("databases/conversations.db.enc")
    if conv is not None:
        try:
            import sqlite3 as _s
            import tempfile
            with tempfile.NamedTemporaryFile(
                    suffix=".db", delete=False) as tf:
                tf.write(conv)
                tmp = Path(tf.name)
            try:
                c = _s.connect(f"file:{tmp}?mode=ro", uri=True)
                try:
                    report.thread_count = c.execute(
                        "SELECT COUNT(*) FROM conversations").fetchone()[0]
                finally:
                    c.close()
            finally:
                tmp.unlink(missing_ok=True)
        except Exception:
            pass

    report.warnings.append(
        "peers paired after this backup was taken need re-pairing")
    logger.warning(
        "Restored %s (%s): %d files, %d quarantined, %d warnings",
        report.entity_name, report.backup_date,
        len(report.files_restored), len(report.quarantined),
        len(report.warnings),
    )
    return report
