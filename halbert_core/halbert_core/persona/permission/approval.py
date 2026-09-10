# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Approval receipts: one answered confirmation, redeemable once.

A11-G9, under FD-6. An ask-every-use grant is only half a mechanism: the
other half is proving, at the moment of use, that THIS use was the one
the owner approved. Without that, "the owner confirmed a config write"
authorises every config write until someone notices.

So an approval mints a receipt and the use redeems it, and the receipt
binds three things at once:

* the **capability** -- approving a privileged read is not approving a
  config write;
* the **artefact digest** -- approving one diff is not approving a
  different one, which is the whole reason the confirmation showed the
  owner a literal diff in the first place;
* **once** -- a redeemed receipt is spent, so a retry loop cannot turn
  one "yes" into a hundred.

Shape lifted from ``dashboard/voice_relay.py``'s relay receipts, which
solved the same problem one door over: the server records what it
observed, hands out an opaque token, and the redemption is what carries
the authority -- never the caller's word about what was approved.

Bounded and TTL'd by construction: a handful of pending confirmations,
never a log of what was asked.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("halbert.permission.approval")


@dataclass(frozen=True)
class ApprovalReceipt:
    """What one answered confirmation authorises."""

    capability: str
    artefact_sha256: str
    #: Free-text label of what was shown, for the audit line. Never the
    #: artefact itself -- the digest is the binding fact.
    shown: str
    minted_at: float


def artefact_digest(text: str) -> str:
    """The digest a confirmation binds itself to.

    One function so the mint side and the use side cannot compute it
    differently -- which would be a receipt that never redeems, or worse,
    one that redeems for the wrong thing.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ApprovalReceipts:
    """Pending approvals: token -> what it authorises.

    Thread-safe: an approval is answered on the dashboard's request
    thread and redeemed on the turn's, which are not the same thread.
    """

    #: A confirmation is answered and acted on within a turn; ten minutes
    #: covers a slow reader without letting yesterday's yes stand for
    #: today's write.
    TTL_S = 600.0
    #: Small on purpose: more pending approvals than this is a stuck
    #: client, not a queue to serve.
    MAX_ENTRIES = 32

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: "OrderedDict[str, ApprovalReceipt]" = OrderedDict()
        self._now = time.time      # seam for the expiry test

    def mint(
        self,
        capability: str,
        *,
        artefact_sha256: str = "",
        shown: str = "",
    ) -> str:
        """Record one answered confirmation; return its opaque token."""
        now = self._now()
        with self._lock:
            expired = [
                t for t, r in self._pending.items()
                if now - r.minted_at > self.TTL_S
            ]
            for token in expired:
                self._pending.pop(token, None)
            token = secrets.token_urlsafe(24)
            self._pending[token] = ApprovalReceipt(
                capability=capability,
                artefact_sha256=artefact_sha256 or "",
                shown=shown,
                minted_at=now,
            )
            while len(self._pending) > self.MAX_ENTRIES:
                self._pending.popitem(last=False)
        return token

    def redeem(
        self,
        token: Optional[str],
        capability: str,
        *,
        artefact_sha256: str = "",
    ) -> Optional[ApprovalReceipt]:
        """Spend one receipt for exactly this capability and artefact.

        Returns None for an unknown, spent, expired, mismatched-capability
        or mismatched-artefact token -- every one of which means "this use
        was not approved", and none of which is distinguished to the
        caller, because a caller that could tell them apart could probe.
        """
        if not token:
            return None
        with self._lock:
            receipt = self._pending.pop(token, None)
        if receipt is None:
            return None
        if self._now() - receipt.minted_at > self.TTL_S:
            return None
        if receipt.capability != capability:
            logger.warning(
                "approval receipt redeemed for the wrong capability "
                "(approved %s, used for %s) — refused",
                receipt.capability, capability,
            )
            return None
        if receipt.artefact_sha256 != (artefact_sha256 or ""):
            logger.warning(
                "approval receipt redeemed against a different artefact "
                "for %s — refused", capability,
            )
            return None
        return receipt

    def size(self) -> int:
        with self._lock:
            return len(self._pending)

    def reset(self) -> None:
        """Test seam: drop every pending receipt."""
        with self._lock:
            self._pending.clear()


_RECEIPTS: Optional[ApprovalReceipts] = None
_RECEIPTS_LOCK = threading.Lock()


def get_approval_receipts() -> ApprovalReceipts:
    """The process-wide store; the confirm flow and the use meet here."""
    global _RECEIPTS
    with _RECEIPTS_LOCK:
        if _RECEIPTS is None:
            _RECEIPTS = ApprovalReceipts()
        return _RECEIPTS
