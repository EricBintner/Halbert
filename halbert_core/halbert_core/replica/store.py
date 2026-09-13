# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The satellite's replica store — the canonical host's mind, kept warm.

A body peer receives snapshots from its canonical host and keeps them
here, read-only, for recall and for promotion. Three rules shape the
code:

- **Trust but verify.** The satellite intentionally trusts the canonical
  for the *content* of entity state — that is the relationship — but the
  digest check and the structural parse catch a corrupted push and (more
  importantly) a sender that is not the canonical it thought it paired.
  Only known payload names are accepted; a manifest can never steer a
  file outside the replica dir.

- **Swap atomically.** ``canonical_replica`` is a symlink into
  ``canonical_replica.d/snapshot-<ts>``. A receive validates everything,
  writes the new snapshot dir beside the old, and repoints the link with
  one ``os.replace`` — readers always see a complete snapshot, never a
  half-written one.

- **0700.** The replica is a copy of the entity's autobiography, as
  sensitive as the source; the directory is owner-only.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger('halbert.replica.store')

#: The only payload names a replica accepts (security review 2026-09-13:
#: client-supplied filenames never reach a path join; anything not in this
#: set is refused before it is looked at).
KNOWN_PAYLOADS = frozenset({"memories.json", "conversations.db"})

#: Snapshots kept on disk — the current plus two back generations for the
#: postmortem question "what did the mind look like when it broke?".
_KEEP_SNAPSHOTS = 3


class ReplicaValidationError(ValueError):
    """A pushed snapshot failed verification — digest, shape, or content."""


@dataclass
class ReplicaMeta:
    """What is stored about the current replica."""
    source_node_id: str
    created_at: str            # when the canonical took the snapshot
    received_at: str           # when this satellite stored it
    memory_count: int
    thread_count: int
    file_digests: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReplicaMeta":
        return cls(
            source_node_id=d.get("source_node_id", ""),
            created_at=d.get("created_at", ""),
            received_at=d.get("received_at", ""),
            memory_count=int(d.get("memory_count", 0)),
            thread_count=int(d.get("thread_count", 0)),
            file_digests=dict(d.get("file_digests") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_node_id": self.source_node_id,
            "created_at": self.created_at,
            "received_at": self.received_at,
            "memory_count": self.memory_count,
            "thread_count": self.thread_count,
            "file_digests": self.file_digests,
        }


class ReplicaStore:
    """Holds the canonical host's snapshot on a satellite.

    Layout under ``<replica_dir>`` (default ``data_dir/canonical_replica``):

    - ``canonical_replica`` — a symlink to the live snapshot dir, repointed
      atomically on each receive.
    - ``canonical_replica.d/snapshot-<ts>/`` — the snapshot dirs, each with
      the payload files and a ``meta.json``.

    Args:
        replica_dir: the symlink path. Defaults to
            ``<data_dir>/canonical_replica``.
    """

    def __init__(self, replica_dir: Optional[Path] = None):
        if replica_dir is None:
            from ..utils.paths import data_dir
            replica_dir = Path(data_dir()) / "canonical_replica"
        self._link = Path(replica_dir)
        self._snapshots_root = self._link.parent / f"{self._link.name}.d"

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def path(self) -> Path:
        """The replica directory — resolve through it, never write into it
        except via receive()."""
        return self._link

    def _current_dir(self) -> Optional[Path]:
        """The live snapshot dir, or None when there is no replica."""
        try:
            target = os.readlink(self._link)
        except OSError:
            return None
        resolved = Path(target)
        if not resolved.is_absolute():
            resolved = self._link.parent / resolved
        return resolved if resolved.is_dir() else None

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def receive(
        self,
        staging_dir: Path,
        manifest: Dict[str, Any],
        source_node_id: str = "",
    ) -> ReplicaMeta:
        """Validate a pushed snapshot and swap it in.

        ``manifest`` is ``{"files": {name: {"sha256": ..., "size": ...,
        "method": ...}}, "created_at": ...}`` — the same shape the snapshot
        engine produces. Order is deliberate: digest first (a file that is
        not what the manifest claims is never parsed), then structural
        validation (JSON parses, SQLite passes quick_check), then the
        atomic repoint. Any failure leaves the previous replica untouched.

        Raises ReplicaValidationError on any check failure.
        """
        staging_dir = Path(staging_dir)
        files = manifest.get("files") or {}
        self._check_manifest_names(files)

        digests: Dict[str, str] = {}
        memory_count = 0
        thread_count = 0

        for name, entry in files.items():
            src = staging_dir / name
            if not src.is_file():
                raise ReplicaValidationError(
                    f"manifest claims {name} but it is absent from the payload")
            expected = (entry or {}).get("sha256") or ""
            actual = _sha256_file(src)
            if not expected or not _eq_hex(actual, expected):
                raise ReplicaValidationError(
                    f"{name}: digest mismatch (expected {expected[:12]}…, "
                    f"got {actual[:12]}…)")
            digests[name] = actual
            if name == "memories.json":
                memory_count = self._validate_memories(src)
            elif name == "conversations.db":
                thread_count = self._validate_threads(src)

        new_dir = self._snapshots_root / f"snapshot-{int(time.time() * 1000)}"
        new_dir.mkdir(parents=True, mode=0o700)
        os.chmod(new_dir, 0o700)
        for name in files:
            shutil.copy2(staging_dir / name, new_dir / name)

        meta = ReplicaMeta(
            source_node_id=source_node_id or manifest.get("source_node_id", ""),
            created_at=manifest.get("created_at", ""),
            received_at=datetime.now(timezone.utc).isoformat(),
            memory_count=memory_count,
            thread_count=thread_count,
            file_digests=digests,
        )
        (new_dir / "meta.json").write_text(json.dumps(meta.to_dict(), indent=2))

        # The commit point: repoint the link in one rename. A crash before
        # this leaves the previous replica live; a crash after leaves a
        # stray snapshot dir, pruned on the next receive.
        tmp_link = self._link.parent / f".{self._link.name}.tmp"
        try:
            tmp_link.unlink()
        except FileNotFoundError:
            pass
        os.symlink(new_dir, tmp_link)
        os.replace(tmp_link, self._link)

        self._prune()
        logger.info(
            "Replica updated from %s: %d files, %d memories, %d threads",
            meta.source_node_id or "canonical", len(files),
            memory_count, thread_count,
        )
        return meta

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def meta(self) -> Optional[ReplicaMeta]:
        """Metadata for the current replica, or None when there is none."""
        current = self._current_dir()
        if current is None:
            return None
        meta_path = current / "meta.json"
        try:
            return ReplicaMeta.from_dict(json.loads(meta_path.read_text()))
        except Exception:
            return None

    def is_valid(self) -> bool:
        """Does the current replica hold everything its meta claims?"""
        current = self._current_dir()
        meta = self.meta()
        if current is None or meta is None:
            return False
        for name, digest in meta.file_digests.items():
            f = current / name
            if not f.is_file() or _sha256_file(f) != digest:
                return False
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_manifest_names(self, files: Dict[str, Any]) -> None:
        for name in files:
            if name not in KNOWN_PAYLOADS or "/" in name or "\\" in name:
                raise ReplicaValidationError(
                    f"refusing unknown or hostile payload name: {name!r}")

    def _validate_memories(self, path: Path) -> int:
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            raise ReplicaValidationError(f"memories.json does not parse: {e}")
        memories = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(memories, list):
            raise ReplicaValidationError(
                "memories.json parses but has no memories list")
        return len(memories)

    def _validate_threads(self, path: Path) -> int:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                verdict = conn.execute("PRAGMA quick_check").fetchone()
                if not verdict or verdict[0] != "ok":
                    raise ReplicaValidationError(
                        f"conversations.db failed quick_check: {verdict}")
                return conn.execute(
                    "SELECT COUNT(*) FROM conversations").fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise ReplicaValidationError(f"conversations.db unreadable: {e}")

    def _prune(self) -> None:
        """Keep the newest few snapshot dirs; the rest are dead weight."""
        try:
            dirs = sorted(
                (d for d in self._snapshots_root.iterdir() if d.is_dir()),
                key=lambda d: d.name,
            )
        except FileNotFoundError:
            return
        current = self._current_dir()
        for old in dirs[: max(0, len(dirs) - _KEEP_SNAPSHOTS)]:
            if current is not None and old == current:
                continue
            shutil.rmtree(old, ignore_errors=True)


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _eq_hex(a: str, b: str) -> bool:
    """Constant-time digest compare — the manifest is attacker-adjacent."""
    import hmac
    return hmac.compare_digest(a.lower(), b.lower())
