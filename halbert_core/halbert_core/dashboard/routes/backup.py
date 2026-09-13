# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Backup routes — create, list, restore the State Vault.

Every route is local-admin: a backup exports the entity's private
signing key (the most sensitive file the node holds), and a restore
overwrites the entity's whole state. Neither is a thing a remote peer
may ask for — including the trust_anchor phone: it promotes replicas,
it does not get to rewrite the mind from scratch.

Passphrases travel in the request body, never the query string —
URLs land in access logs; bodies do not.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...federation.peer_middleware import require_local_admin

logger = logging.getLogger('halbert.dashboard.routes.backup')

router = APIRouter()

_ADMIN = [Depends(require_local_admin)]


class BackupNowRequest(BaseModel):
    passphrase: str = Field(..., min_length=1)
    export_path: str = Field("", description="Directory for the archive; defaults to <data_dir>/backups")


class RestoreRequest(BaseModel):
    archive_path: str
    passphrase: str = Field(..., min_length=1)


class InspectRequest(BaseModel):
    archive_path: str


def _default_export_dir() -> Path:
    from ...utils.paths import data_dir
    return Path(data_dir()) / "backups"


@router.post("/api/backup/now", dependencies=_ADMIN)
async def backup_now(req: BackupNowRequest) -> Dict[str, Any]:
    """Create a vault archive now."""
    from ...backup.encrypt import CryptoUnavailable
    from ...backup.vault import create_backup
    out = Path(req.export_path) if req.export_path else _default_export_dir()
    try:
        archive = create_backup(req.passphrase, out)
    except CryptoUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"backup failed: {e}")
    return {"status": "created", "archive": str(archive)}


@router.get("/api/backup/history", dependencies=_ADMIN)
async def backup_history(export_path: str = "") -> List[Dict[str, Any]]:
    """Manifests of the archives in a directory."""
    from ...backup.vault import list_backups
    out = Path(export_path) if export_path else _default_export_dir()
    return [m.to_dict() for m in list_backups(out)]


@router.post("/api/backup/inspect", dependencies=_ADMIN)
async def backup_inspect(req: InspectRequest) -> Dict[str, Any]:
    """Read an archive's manifest — the preview the OOBE restore shows
    before the passphrase is asked for. The manifest is plaintext by
    design; nothing secret is inside it."""
    import tarfile
    from ...backup.manifest import BackupManifest, ManifestError
    archive = Path(req.archive_path)
    if not archive.is_file():
        raise HTTPException(status_code=404, detail="no such archive")
    try:
        with tarfile.open(archive, "r:*") as tar:
            member = tar.extractfile("manifest.json")
            if member is None:
                raise HTTPException(status_code=400, detail="archive carries no manifest")
            manifest = BackupManifest.from_json(member.read().decode())
    except HTTPException:
        raise
    except (ManifestError, tarfile.TarError) as e:
        raise HTTPException(status_code=400, detail=f"archive unreadable: {e}")
    return {
        "entity_name": manifest.entity_name,
        "node_id": manifest.node_id,
        "created_at": manifest.created_at,
        "schema_version": manifest.schema_version,
        "file_count": len(manifest.files),
        "key_exported": manifest.key_exported,
        "key_custody": manifest.key_custody,
    }


@router.post("/api/backup/restore", dependencies=_ADMIN)
async def restore(req: RestoreRequest) -> Dict[str, Any]:
    """Restore the entity from a vault archive."""
    from ...backup.restore import RestoreError, restore_backup
    try:
        report = restore_backup(Path(req.archive_path), req.passphrase)
    except RestoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"restore failed: {e}")
    return {
        "status": "restored",
        "entity_name": report.entity_name,
        "backup_date": report.backup_date,
        "memory_count": report.memory_count,
        "thread_count": report.thread_count,
        "files_restored": report.files_restored,
        "quarantined": report.quarantined,
        "warnings": report.warnings,
    }


@router.get("/api/backup/config", dependencies=_ADMIN)
async def backup_config() -> Dict[str, Any]:
    """Backup destination/schedule — honest v1: the default export dir,
    no scheduler yet (scheduled backups land with the export target)."""
    return {
        "export_path": str(_default_export_dir()),
        "schedule_s": None,
    }
