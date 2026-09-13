# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Promotion — the satellite becomes the canonical host.

When the canonical host is gone for good, the operator promotes the
body that holds the warmest replica. The steps are deliberately
conservative:

- The replica must be valid — a corrupt replica promoted is a corrupt
  mind owned.
- Local state that diverged from the replica is *quarantined*, never
  silently overwritten: a memory the satellite recorded while the
  canonical was unreachable is moved aside to ``<file>.quarantined-<ts>``
  and survives for the operator to reconcile by hand.
- being.yml drops its canonical pointers — which is also the fence:
  with no canonical URL, ``sync-replica`` answers 409 to any stale
  canonical that comes back later (the receiver-side split-brain guard).
- The cached stores in cognition_wiring are cleared so the next call
  rebuilds against local files instead of a dead proxy.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .store import ReplicaStore

logger = logging.getLogger('halbert.replica.promotion')


@dataclass
class PromotionResult:
    success: bool
    old_canonical_url: str = ""
    replica_timestamp: str = ""
    memory_count: int = 0
    thread_count: int = 0
    quarantined: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _install(replica_file: Path, dest: Path, quarantined: List[str]) -> None:
    """Move the replica file into the live position.

    If a live file already exists and differs from the replica's, it is
    quarantined beside itself first — divergent local state is preserved,
    not overwritten.
    """
    dest = Path(dest)
    if dest.is_file() and _sha256_file(dest) != _sha256_file(replica_file):
        aside = dest.with_name(f"{dest.name}.quarantined-{int(time.time())}")
        dest.rename(aside)
        quarantined.append(str(aside))
        logger.warning(
            "Local %s diverged from the replica — quarantined to %s",
            dest.name, aside.name,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(replica_file, dest)


def _clear_store_caches() -> None:
    """Drop the cached memory/observation stores so the next call rebuilds
    against the newly-local files."""
    try:
        from ..integrations import cognition_wiring as cw
        cw._persona_memory_store = None
        cw._persona_memory_store_failed = False
        cw._observation_store = None
        cw._observation_store_failed = False
    except Exception as e:
        logger.debug("Store cache clear (non-fatal): %s", e)


def promote_to_canonical(replica: Optional[ReplicaStore] = None) -> PromotionResult:
    """Promote this satellite's warm replica to active state.

    Returns a PromotionResult; ``success=False`` + ``error`` on any
    failure — no partial promotions: if anything raises before the
    config write, the node stays a body.
    """
    replica = replica or ReplicaStore()

    if not replica.is_valid():
        return PromotionResult(
            success=False,
            error="no valid replica — nothing trustworthy to promote",
        )
    meta = replica.meta()

    try:
        from ..utils.paths import data_dir
        from ..identity import resolve_persona_id
        from ..integrations.cognition_wiring import (
            _get_canonical_memory_url,
            _get_canonical_thread_url,
        )
        from ..config.being_config import load_being_config, save_being_config
        from haloysius.paths import state_dir

        persona_id = resolve_persona_id()
        quarantined: List[str] = []

        memories_src = replica.path() / "memories.json"
        threads_src = replica.path() / "conversations.db"
        if memories_src.is_file():
            _install(
                memories_src,
                state_dir("personas", persona_id) / "memories.json",
                quarantined,
            )
        if threads_src.is_file():
            _install(
                threads_src,
                Path(data_dir()) / "conversations.db",
                quarantined,
            )

        old_url = _get_canonical_memory_url()
        cfg = load_being_config()
        cfg.canonical_memory_url = ""
        cfg.canonical_thread_url = ""
        cfg.peer_token = ""
        save_being_config(cfg)

        _clear_store_caches()

        result = PromotionResult(
            success=True,
            old_canonical_url=old_url,
            replica_timestamp=meta.created_at if meta else "",
            memory_count=meta.memory_count if meta else 0,
            thread_count=meta.thread_count if meta else 0,
            quarantined=quarantined,
        )
        logger.warning(
            "PROMOTED to canonical: %d memories, %d threads from %s; "
            "%d file(s) quarantined",
            result.memory_count, result.thread_count,
            result.replica_timestamp, len(quarantined),
        )
        return result
    except Exception as e:
        logger.exception("Promotion failed")
        return PromotionResult(success=False, error=f"{type(e).__name__}: {e}")
