# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Per-peer credential store with token hashes and revocation.

Implements findings C1 and M14 from the federated multi-node review.

C1 — Single token system with MCP Phase 4b
------------------------------------------
The peer token and the MCP bearer token are the *same* credential.  This
class stores tokens indexed by ``node_id``; the MCP HTTP/SSE transport
(Phase 4b) and the peer compute endpoint both validate against this
store.  There is one ``Authorization: Bearer <token>`` header, one
validation path, and one revocation path.

M14 — Per-peer tokens, rotation, and revocation
-----------------------------------------------
Each satellite gets its own token (not one shared PSK).  Tokens are
stored as SHA-256 hashes — the raw token is never persisted to disk, so
a filesystem compromise of ``peers.json`` does not reveal usable
credentials.  Revocation is surgical: ``revoke_peer(node_id)`` marks
one peer's token as invalid; all other peers continue working.

Storage
-------
``~/.config/halbert/peers.json`` (or ``$HALBERT_CONFIG_DIR/peers.json``).
The file contains::

    {
      "peers": [
        {
          "node_id": "living-room-pi",
          "node_name": "Living Room Pi 5",
          "role": "satellite",
          "token_hash": "sha256:abc123...",
          "paired_at": "2026-08-29T12:00:00Z",
          "last_seen": "2026-08-29T14:30:00Z",
          "revoked": false,
          "endpoint": "http://192.168.1.50:8000",
          "capabilities": ["gpu_llm", "sourceprep"]
        }
      ]
    }

Thread safety
-------------
The config is loaded once at startup and cached.  Mutations
(``add_peer``, ``revoke_peer``) acquire a lock, update the in-memory
dict, and persist atomically (write to temp file + rename).  The
``verify_token`` path is lock-free — it reads the cached dict which is
only replaced atomically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PeerCredential:
    """A single paired peer node's credential record.

    The raw token is NEVER stored here — only its SHA-256 hash.
    The raw token exists only in the peer's own config and in memory
    during the pairing handshake.

    Compute direction (P4d)
    -----------------------
    ``compute_direction`` explicitly states which way compute requests
    flow from *this node's* perspective:

    - ``"outbound"`` — this node sends compute requests to the peer.
      This is the default and the canonical singular-entity direction:
      the HA server (always-on mind) offloads to the workstation (GPU).

    - ``"inbound"`` — this node receives compute requests from the peer.
      The workstation's peers.json lists the HA server with this
      direction.

    Both directions are supported so that either node can be the compute
    issuer.  The default is ``"outbound"`` (HA → workstation).
    """

    node_id: str                           # unique identifier (hostname or user-provided)
    node_name: str                         # human-readable display name
    role: str                              # "compute_provider" | "satellite" (legacy, kept for compat)
    token_hash: str                        # "sha256:<hex>"
    paired_at: str                         # ISO 8601 timestamp
    last_seen: Optional[str] = None        # ISO 8601, updated on each authenticated request
    revoked: bool = False                  # True = token rejected immediately
    endpoint: Optional[str] = None         # "http://192.168.1.50:8000" (for Desktop→Satellite MCP proxy)
    capabilities: List[str] = field(default_factory=list)  # ["gpu_llm", "sourceprep", "vision"]
    compute_direction: str = "outbound"    # "outbound" (local→peer) | "inbound" (peer→local)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PeerCredential":
        return cls(
            node_id=d["node_id"],
            node_name=d.get("node_name", d["node_id"]),
            role=d.get("role", "satellite"),
            token_hash=d["token_hash"],
            paired_at=d.get("paired_at", ""),
            last_seen=d.get("last_seen"),
            revoked=d.get("revoked", False),
            endpoint=d.get("endpoint"),
            capabilities=d.get("capabilities", []),
            compute_direction=d.get("compute_direction", "outbound"),
        )

    def is_compute_target(self) -> bool:
        """True if this peer is a compute offload target (outbound direction)."""
        return self.compute_direction == "outbound"

    def is_compute_source(self) -> bool:
        """True if this peer sends compute requests to us (inbound direction)."""
        return self.compute_direction == "inbound"


# ---------------------------------------------------------------------------
# Token hashing
# ---------------------------------------------------------------------------

def hash_token(raw_token: str) -> str:
    """Hash a raw token for storage. Returns 'sha256:<hex>'.

    We hash rather than encrypt because:
    1. We never need to recover the raw token (we compare hashes).
    2. SHA-256 is sufficient for PSKs that are 32+ bytes of random data.
    3. No key management burden (no encryption key to protect).
    """
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def verify_token_hash(raw_token: str, stored_hash: str) -> bool:
    """Constant-time comparison of a raw token against a stored hash."""
    computed = hash_token(raw_token)
    # hmac.compare_digest is constant-time to prevent timing attacks
    import hmac
    return hmac.compare_digest(computed, stored_hash)


# ---------------------------------------------------------------------------
# Config store
# ---------------------------------------------------------------------------

class PeersConfig:
    """Manages paired peer credentials on disk.

    Singleton per process.  Loaded once at startup, mutations are
    atomic (temp-file + rename).  Thread-safe for concurrent reads and
    serialized writes.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the peer config store.

        Args:
            config_path: Override path to peers.json.  Defaults to
                ``$HALBERT_CONFIG_DIR/peers.json`` or
                ``~/.config/halbert/peers.json``.
        """
        self._path = config_path or self._default_path()
        self._lock = threading.Lock()
        self._peers: Dict[str, PeerCredential] = {}  # node_id -> credential
        self._load()

    @staticmethod
    def _default_path() -> Path:
        """Resolve peers.json path from env vars (Phase 7 unification)."""
        config_dir = (
            os.environ.get("HALBERT_CONFIG_DIR")
            or os.environ.get("Halbert_CONFIG_DIR")
            or os.path.expanduser("~/.config/halbert")
        )
        return Path(config_dir) / "peers.json"

    def _load(self) -> None:
        """Load peers from disk. Missing file = empty config (first boot)."""
        if not self._path.exists():
            logger.info("peers.json not found at %s — first boot or no peers paired", self._path)
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            for peer_data in data.get("peers", []):
                cred = PeerCredential.from_dict(peer_data)
                self._peers[cred.node_id] = cred
            logger.info("Loaded %d peer(s) from %s", len(self._peers), self._path)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse peers.json: %s — starting with empty config", e)

    def _save(self) -> None:
        """Atomically persist peers to disk (temp file + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"peers": [p.to_dict() for p in self._peers.values()]}
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.rename(self._path)  # atomic on POSIX

    # ------------------------------------------------------------------
    # Read operations (lock-free, read cached dict)
    # ------------------------------------------------------------------

    def get_peer(self, node_id: str) -> Optional[PeerCredential]:
        """Get a peer by node_id. Returns None if not found."""
        return self._peers.get(node_id)

    def list_peers(self, include_revoked: bool = False) -> List[PeerCredential]:
        """List all peers. Excludes revoked by default."""
        return [
            p for p in self._peers.values()
            if include_revoked or not p.revoked
        ]

    def list_compute_targets(self) -> List[PeerCredential]:
        """List peers that this node can offload compute to (outbound direction).

        P4d — In the singular-entity model, the HA server (always-on mind)
        offloads compute to the workstation.  This returns peers with
        ``compute_direction="outbound"`` that are not revoked.
        """
        return [
            p for p in self._peers.values()
            if not p.revoked and p.is_compute_target()
        ]

    def verify_token(self, raw_token: str) -> Optional[PeerCredential]:
        """Verify a bearer token against all stored peer tokens.

        Returns the matching PeerCredential if valid, None if not found
        or revoked.  This is the hot path — called on every authenticated
        request via ``require_peer_auth`` (peer_middleware.py).

        TODO(federation-9.1): For large peer counts (25+), replace
        linear scan with a dict lookup keyed on token_hash.  For now,
        linear scan is fine — N is small and the comparison is
        constant-time per peer.
        """
        for peer in self._peers.values():
            if peer.revoked:
                continue
            if verify_token_hash(raw_token, peer.token_hash):
                return peer
        return None

    # ------------------------------------------------------------------
    # Write operations (lock + atomic save)
    # ------------------------------------------------------------------

    def add_peer(
        self,
        node_id: str,
        node_name: str,
        role: str,
        raw_token: str,
        endpoint: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        compute_direction: str = "outbound",
    ) -> PeerCredential:
        """Pair a new peer. Generates a credential with hashed token.

        Raises ValueError if node_id already exists (use revoke_peer +
        add_peer to re-pair).

        Args:
            compute_direction: "outbound" (this node offloads to peer,
                default) or "inbound" (peer offloads to this node).
        """
        with self._lock:
            if node_id in self._peers:
                raise ValueError(f"Peer {node_id!r} already paired — revoke first to re-pair")
            cred = PeerCredential(
                node_id=node_id,
                node_name=node_name,
                role=role,
                token_hash=hash_token(raw_token),
                paired_at=datetime.now(timezone.utc).isoformat(),
                endpoint=endpoint,
                capabilities=capabilities or [],
                compute_direction=compute_direction,
            )
            self._peers[node_id] = cred
            self._save()
            logger.info(
                "Paired new peer: %s (%s) as %s, direction=%s",
                node_id, node_name, role, compute_direction,
            )
            return cred

    def revoke_peer(self, node_id: str) -> bool:
        """Revoke a peer's token. The token is immediately invalid.

        Returns True if the peer was found and revoked, False if not found.
        The peer record is retained (for audit) but marked revoked=True.
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return False
            peer.revoked = True
            self._save()
            logger.warning("Revoked peer: %s (%s)", node_id, peer.node_name)
            return True

    def update_last_seen(self, node_id: str) -> None:
        """Update last_seen timestamp for a peer (called on each authed request).

        TODO(federation-9.1): Throttle disk writes — don't save on every
        request.  Batch updates every 60s or on shutdown.
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return
            peer.last_seen = datetime.now(timezone.utc).isoformat()
            # TODO(federation-9.1): throttle _save() — for now, save every time
            self._save()

    def generate_token(self) -> str:
        """Generate a cryptographically random token for a new peer.

        Uses ``secrets.token_urlsafe(32)`` — 43 characters of URL-safe
        base64, ~256 bits of entropy.
        """
        import secrets
        return secrets.token_urlsafe(32)
