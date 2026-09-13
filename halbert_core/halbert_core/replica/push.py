# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Push a snapshot to every paired body peer.

The canonical's half of warm standby: take the staging dir the snapshot
engine produced, pack it as a tar (manifest.json + the payload files),
and POST it to each body peer's ``/api/peers/sync-replica``.

The bearer token is the peer's ``outbound_token`` — the credential the
satellite minted for exactly this door at pairing time (F-D). A peer with
no outbound token has never completed the reverse-pairing; the report
says so rather than pushing a 401.

A tar body rather than multipart: python-multipart is not in the install
set, and a streamed tar carries the same files with no new dependency.
The member list is flat and allowlisted on the receive side.
"""
from __future__ import annotations

import io
import json
import logging
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .snapshot import SnapshotResult
from .store import KNOWN_PAYLOADS

logger = logging.getLogger('halbert.replica.push')

MANIFEST_NAME = "manifest.json"

#: Members the receiver may extract — the payloads plus the manifest.
ALLOWED_MEMBERS = KNOWN_PAYLOADS | {MANIFEST_NAME}


@dataclass
class PushReport:
    peer_id: str
    success: bool
    error: Optional[str] = None
    status_code: Optional[int] = None


def pack_snapshot_tar(snapshot: SnapshotResult, source_node_id: str = "") -> bytes:
    """Pack a staging dir into a tar: manifest.json + the payload files."""
    manifest = {
        "files": snapshot.manifest,
        "created_at": snapshot.created_at,
        "source_node_id": source_node_id,
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        payload = json.dumps(manifest).encode()
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        for name in snapshot.manifest:
            if name not in KNOWN_PAYLOADS:
                continue
            tar.add(str(snapshot.staging_dir / name), arcname=name)
    return buf.getvalue()


def unpack_snapshot_tar(body: bytes, dest_dir: Path) -> Dict[str, Any]:
    """Extract an allowlisted member set from a pushed tar.

    Members are read through ``extractfile`` into named files — never
    ``extractall`` — so a member name can never steer a write outside
    ``dest_dir``. Anything not in ALLOWED_MEMBERS is skipped unread.
    Returns the parsed manifest.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {}
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:*") as tar:
        for member in tar.getmembers():
            if member.name not in ALLOWED_MEMBERS or not member.isfile():
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            data = f.read()
            if member.name == MANIFEST_NAME:
                manifest = json.loads(data.decode())
            else:
                (dest_dir / member.name).write_bytes(data)
    if not manifest:
        raise ValueError("replica payload carried no manifest.json")
    return manifest


def push_snapshot_to_peers(
    snapshot: SnapshotResult,
    http_post: Optional[Callable[..., Any]] = None,
    source_node_id: str = "",
    timeout: float = 60.0,
) -> List[PushReport]:
    """POST the snapshot to every non-revoked body peer.

    ``http_post`` is the transport seam (requests.post in production, a
    stub in tests): called as ``http_post(url, data=bytes, headers=…,
    timeout=…)`` and expected to return a response with ``status_code``
    and ``text``.
    """
    if http_post is None:
        import requests
        http_post = requests.post

    from ..federation.peer_middleware import get_peers_config

    body = pack_snapshot_tar(snapshot, source_node_id=source_node_id)
    reports: List[PushReport] = []

    for peer in get_peers_config().list_peers():
        if peer.role != "body" or peer.revoked or not peer.endpoint:
            continue
        if not peer.outbound_token:
            reports.append(PushReport(
                peer.node_id, False,
                "no push credential — the reverse-pairing never completed "
                "(re-pair this body)"))
            continue
        url = peer.endpoint.rstrip("/") + "/api/peers/sync-replica"
        try:
            resp = http_post(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {peer.outbound_token}",
                    "Content-Type": "application/x-tar",
                },
                timeout=timeout,
            )
            ok = 200 <= resp.status_code < 300
            reports.append(PushReport(
                peer.node_id, ok,
                None if ok else f"HTTP {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            ))
        except Exception as e:
            reports.append(PushReport(peer.node_id, False, f"{type(e).__name__}: {e}"))
        logger.info("Replica push to %s: %s", peer.node_id,
                    "ok" if reports[-1].success else reports[-1].error)

    return reports
