# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The backup manifest — what the archive claims to contain.

One JSON document inside every ``.halbert-backup`` archive, kept
plaintext on purpose: a restore must be able to read what it is about
to trust (entity, date, schema version, KDF parameters) before the
passphrase is asked for. File integrity lives in the per-file digests
here; file *secrecy* lives in the encryption, not in the manifest.

Key-hierarchy note — the plan sketched both "files encrypted with the
master key" (2.2) and "per-file keys wrapped by the master key" (2.3).
Resolved to the simpler model: ONE master key per archive
(PBKDF2-derived, random salt), a fresh random nonce per file, and the
member name bound as AEAD additional data. Wrapped per-file keys earn
their keep when members are independently updatable or keys are
separately distributed — a vault archive is written atomically in one
pass, so the envelope would add machinery without adding security.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

BACKUP_SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """The manifest is missing what a restore needs."""


@dataclass
class BackupManifest:
    """The archive's table of contents and trust anchor."""
    schema_version: int
    node_id: str
    entity_name: str
    created_at: str
    # KDF parameters the restore needs to re-derive the master key —
    # plaintext by design, they are not secret.
    kdf_salt: str = ""         # hex
    kdf_iterations: int = 0
    # {archive member name: {"sha256": <of the PLAINTEXT>, "size": n,
    #                        "encrypted": bool}}
    files: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Model slots → download URLs + hashes, plaintext (rebuildable state).
    model_manifest: Optional[Dict[str, Any]] = None
    # Where the signing key lived when the archive was made, and whether
    # its bytes are inside — a hardware-held key is not exportable and
    # the manifest says so rather than silently omitting it.
    key_custody: str = ""
    key_exported: bool = False

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "entity_name": self.entity_name,
            "created_at": self.created_at,
            "kdf_salt": self.kdf_salt,
            "kdf_iterations": self.kdf_iterations,
            "files": self.files,
            "model_manifest": self.model_manifest,
            "key_custody": self.key_custody,
            "key_exported": self.key_exported,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BackupManifest":
        for required in ("schema_version", "node_id", "created_at", "files"):
            if required not in d:
                raise ManifestError(f"manifest is missing {required!r}")
        return cls(
            schema_version=int(d["schema_version"]),
            node_id=str(d["node_id"]),
            entity_name=str(d.get("entity_name", "")),
            created_at=str(d["created_at"]),
            kdf_salt=str(d.get("kdf_salt", "")),
            kdf_iterations=int(d.get("kdf_iterations", 0)),
            files=dict(d["files"]),
            model_manifest=d.get("model_manifest"),
            key_custody=str(d.get("key_custody", "")),
            key_exported=bool(d.get("key_exported", False)),
        )

    @classmethod
    def from_json(cls, s: str) -> "BackupManifest":
        try:
            return cls.from_dict(json.loads(s))
        except json.JSONDecodeError as e:
            raise ManifestError(f"manifest is not JSON: {e}")
