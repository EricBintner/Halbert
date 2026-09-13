# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vault engine — one encrypted tar that IS the entity.

``create_backup`` gathers the whole entity into a ``.halbert-backup``
archive:

- **identity/** — the body's signing key (when its custody permits
  export — a hardware-held key is not exportable and the manifest says
  so) and the public ``did:key`` in plaintext.
- **config/** — being.yml, peers.json, models.yml, preferences.yml.
- **databases/** — memories.json and the SQLite stores, snapshotted
  through the Phase 1 engine (online backup, never a live-file copy).

Everything sensitive is AES-256-GCM under a passphrase-derived key —
the archive may sit on a USB stick, a NAS, anywhere the user trusts
their passphrase. The write is atomic: a temp file renamed over the
target, so a crash mid-backup never leaves a torn archive.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .encrypt import (
    CryptoUnavailable,
    check_crypto_available,
    derive_key,
    encrypt_file,
    new_salt,
    DEFAULT_KDF_ITERATIONS,
)
from .manifest import BACKUP_SCHEMA_VERSION, BackupManifest
from ..replica.snapshot import SnapshotTarget, create_snapshot

logger = logging.getLogger('halbert.backup.vault')

ARCHIVE_SUFFIX = ".halbert-backup"
_MANIFEST_NAME = "manifest.json"
_MODEL_MANIFEST_NAME = "model-manifest.json"
_DID_NAME = "identity/did.txt"
_KEY_NAME = "identity/body.key.enc"

#: Config files that travel with the entity (config_dir).
_CONFIG_FILES = ("being.yml", "peers.json", "models.yml", "preferences.yml")

#: Databases beyond the Phase-1 replication set — host-local stores that
#: are still the entity's autobiography, snapshotted the same way.
_EXTRA_DBS = (
    ("state_ledger.db", "state_ledger.db"),
    ("timeline.db", "timeline.db"),
    ("findings.db", "findings/findings.db"),
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _database_targets() -> List[SnapshotTarget]:
    """memories + conversations + the host-local continuity stores."""
    from ..replica.snapshot import replication_targets
    from ..utils.paths import data_dir

    targets = replication_targets()
    base = Path(data_dir())
    for name, rel in _EXTRA_DBS:
        targets.append(SnapshotTarget(
            source=base / rel, method="sqlite_backup", name=name))
    return targets


def _signer_export() -> Tuple[Optional[bytes], str, str]:
    """(private_bytes, did, custody) — the identity tier.

    A hardware-held key answers (None, did, custody): the did still
    travels (plaintext), the manifest records key_exported=False, and
    the operator learns the key stayed in hardware rather than guessing
    the archive forgot it.
    """
    try:
        from ..crypto.storage import resolve_signer
        signer = resolve_signer()
    except Exception as e:
        logger.warning("signer resolution failed during backup: %s", e)
        return None, "", ""
    if signer is None:
        return None, "", ""
    custody = signer.custody
    try:
        private = signer.private_bytes()
    except Exception:
        private = None
    if private is None or custody == "hardware":
        return None, signer.did, custody
    return private, signer.did, custody


def _config_dir() -> Path:
    from ..utils.platform import get_config_dir
    return Path(get_config_dir())


def _member_map() -> Dict[str, str]:
    """Vault member name → its restored location kind, for the manifest
    reader and the restore engine. Single source for the archive layout."""
    return {
        "identity/body.key.enc": "keystore",
        "identity/did.txt": "keystore",
        **{f"config/{n}.enc": "config" for n in _CONFIG_FILES},
        **{f"databases/{n}.enc": "data" for n, _ in
           (("memories.json", ""), ("conversations.db", ""), *_EXTRA_DBS)},
        "model-manifest.json": "models",
    }


def create_backup(
    passphrase: str,
    export_path: Path,
    node_id: str = "",
    entity_name: str = "",
) -> Path:
    """Create a .halbert-backup archive inside export_path (a directory).

    Returns the archive's path. Raises CryptoUnavailable when the crypto
    stack is absent — there is no plaintext fallback for an archive that
    carries the body's private key.
    """
    if not check_crypto_available():
        raise CryptoUnavailable(
            "cryptography is not installed — the vault cannot encrypt.")

    export_path = Path(export_path)
    export_path.mkdir(parents=True, exist_ok=True)

    # Gather the payload: plaintext bytes per member name.
    members: Dict[str, bytes] = {}
    plaintext_digests: Dict[str, Dict[str, Any]] = {}

    # Identity
    private, did, custody = _signer_export()
    if did:
        members[_DID_NAME] = did.encode()
        plaintext_digests[_DID_NAME] = {
            "sha256": _sha256_bytes(members[_DID_NAME]),
            "size": len(members[_DID_NAME]), "encrypted": False}
    if private is not None:
        members[_KEY_NAME] = private

    # Config
    config_dir = _config_dir()
    for name in _CONFIG_FILES:
        src = config_dir / name
        if src.is_file():
            member = f"config/{name}.enc"
            members[member] = src.read_bytes()

    # Databases — through the snapshot engine for a consistent copy.
    snap = create_snapshot(_database_targets())
    for name in snap.manifest:
        member = f"databases/{name}.enc"
        members[member] = (snap.staging_dir / name).read_bytes()

    # Encrypt
    salt = new_salt()
    key = derive_key(passphrase, salt, DEFAULT_KDF_ITERATIONS)
    encrypted: Dict[str, bytes] = {}
    for member, plaintext in members.items():
        if member.endswith(".enc"):
            ct = encrypt_file(plaintext, key, member)
            encrypted[member] = ct
            plaintext_digests[member] = {
                "sha256": _sha256_bytes(plaintext),
                "size": len(plaintext), "encrypted": True}
        else:
            encrypted[member] = plaintext  # did.txt — public by design

    # The model manifest travels plaintext: model weights are rebuildable
    # state — the archive carries WHERE to fetch them, not the weights.
    models_yml = config_dir / "models.yml"
    model_manifest: Optional[Dict[str, Any]] = None
    if models_yml.is_file():
        try:
            import yaml
            model_manifest = yaml.safe_load(models_yml.read_text())
        except Exception:
            model_manifest = None

    if not node_id:
        try:
            import os as _os
            import socket
            node_id = (_os.environ.get("HALBERT_PERSONA_ID", "halbert")
                       + "-" + socket.gethostname())
        except Exception:
            node_id = "unknown"
    if not entity_name:
        try:
            from ..identity import resolve_entity_name
            entity_name = resolve_entity_name()
        except Exception:
            entity_name = ""

    manifest = BackupManifest(
        schema_version=BACKUP_SCHEMA_VERSION,
        node_id=node_id,
        entity_name=entity_name,
        created_at=datetime.now(timezone.utc).isoformat(),
        kdf_salt=salt.hex(),
        kdf_iterations=DEFAULT_KDF_ITERATIONS,
        files=plaintext_digests,
        model_manifest=model_manifest,
        key_custody=custody,
        key_exported=private is not None,
    )

    # Pack the tar in memory, then write atomically.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_bytes(tar, _MANIFEST_NAME, manifest.to_json().encode())
        if model_manifest is not None:
            _add_bytes(tar, _MODEL_MANIFEST_NAME,
                       json.dumps(model_manifest).encode())
        for member, data in encrypted.items():
            _add_bytes(tar, member, data)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = export_path / f"halbert-{stamp}{ARCHIVE_SUFFIX}"
    fd, tmp = tempfile.mkstemp(dir=str(export_path),
                               prefix=".halbert-backup-", suffix=".tmp")
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(buf.getvalue())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, archive)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    logger.warning(
        "Backup written: %s (%d members, %d encrypted, key %s)",
        archive.name, len(encrypted),
        sum(1 for m in encrypted if m.endswith(".enc")),
        "exported" if private is not None else f"NOT exported (custody={custody or 'none'})",
    )
    return archive


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def list_backups(export_path: Path) -> List[BackupManifest]:
    """Read the manifest of every archive in a directory."""
    out: List[BackupManifest] = []
    export_path = Path(export_path)
    if not export_path.is_dir():
        return out
    for archive in sorted(export_path.glob(f"*{ARCHIVE_SUFFIX}")):
        try:
            with tarfile.open(archive, "r:*") as tar:
                member = tar.extractfile(_MANIFEST_NAME)
                if member is None:
                    continue
                out.append(BackupManifest.from_json(member.read().decode()))
        except Exception as e:
            logger.debug("skipping unreadable archive %s: %s", archive.name, e)
    return out
