# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The snapshot engine — consistent copies of entity-level state.

``create_snapshot`` produces a staging directory of the files that make up
the entity's autobiography, each with a SHA-256 in the manifest. The push
loop uploads that staging dir; the receiver verifies digests before
swapping it in.

Two snapshot methods, because the two sources differ:

- ``file_copy`` — for files the writer publishes atomically. PersonaMemory
  writes memories.json via temp+fsync+rename, so a plain ``shutil.copy2``
  can never observe a torn file — it sees either the last rename or the
  next.
- ``sqlite_backup`` — for conversations.db. ``Connection.backup()`` is the
  online API: it snapshots committed pages while writers keep working, and
  never carries an uncommitted transaction into the copy.

The target list is a parameter, not a constant, because Phase 2's vault
snapshot reuses this engine with a wider list.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

logger = logging.getLogger('halbert.replica.snapshot')

SnapshotMethod = Literal["file_copy", "sqlite_backup"]


@dataclass(frozen=True)
class SnapshotTarget:
    """One file to carry into the snapshot."""
    source: Path
    method: SnapshotMethod
    name: str  # filename inside the staging dir / manifest


@dataclass
class SnapshotResult:
    """What a snapshot produced: a staging dir and its manifest."""
    staging_dir: Path
    manifest: Dict[str, Dict[str, Any]]  # name -> {sha256, size, method}
    created_at: str
    missing: List[str] = field(default_factory=list)  # sources that did not exist


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _sqlite_backup(source: Path, dest: Path) -> None:
    """Copy a SQLite database through the online backup API.

    The source is opened read-only — a snapshot mutates nothing. Committed
    pages only: a transaction still open at copy time does not appear.
    """
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def create_snapshot(targets: List[SnapshotTarget]) -> SnapshotResult:
    """Snapshot each target into a fresh staging dir.

    Missing sources are recorded in ``result.missing`` rather than failing
    the snapshot — a fresh install legitimately has no memories.json or
    conversations.db yet, and the satellite should learn "nothing yet" as
    a fact, not as an error.
    """
    staging = Path(tempfile.mkdtemp(prefix="halbert-replica-"))
    manifest: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []

    for target in targets:
        if not target.source.exists():
            missing.append(target.name)
            continue
        dest = staging / target.name
        if target.method == "sqlite_backup":
            _sqlite_backup(target.source, dest)
        else:
            shutil.copy2(target.source, dest)
        manifest[target.name] = {
            "sha256": _sha256_file(dest),
            "size": dest.stat().st_size,
            "method": target.method,
        }

    result = SnapshotResult(
        staging_dir=staging,
        manifest=manifest,
        created_at=datetime.now(timezone.utc).isoformat(),
        missing=missing,
    )
    logger.info(
        "Snapshot %s: %d files, %d missing (%s)",
        staging.name, len(manifest), len(missing),
        ", ".join(manifest) or "nothing",
    )
    return result


def replication_targets() -> List[SnapshotTarget]:
    """The standard replication set — the entity's autobiography.

    memories.json resolves through haloysius's own ``state_dir`` (its data
    home is ~/.local/share/haloysius, not halbert's data_dir — the two are
    different trees and confusing them snapshots an empty path).
    conversations.db is the canonical thread store under halbert's
    data_dir.
    """
    from haloysius.paths import state_dir
    from ..identity import resolve_persona_id
    from ..utils.paths import data_dir

    persona_id = resolve_persona_id()
    return [
        SnapshotTarget(
            source=state_dir("personas", persona_id) / "memories.json",
            method="file_copy",
            name="memories.json",
        ),
        SnapshotTarget(
            source=Path(data_dir()) / "conversations.db",
            method="sqlite_backup",
            name="conversations.db",
        ),
    ]


def create_replication_snapshot() -> SnapshotResult:
    """Convenience: snapshot the standard replication set."""
    return create_snapshot(replication_targets())
