# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Look before you write.

open-claude-code refuses to edit a file that has not been read in this session
(``read.mjs:hasBeenRead``, enforced by ``edit.mjs`` and ``write.mjs``). For a
coding agent that prevents a clobbered file. For a steward that edits ``/etc``
on the only machine it has, the same mistake costs the boot, the network, or
the session it is being used through.

Halbert can do better than a set of paths, and nearly for free. The ledger
already records every file's ``content_sha256``, so comparing the bytes on
disk against the digest it holds is a compare-and-swap that:

* survives a restart (the set does not);
* notices a change made by another process (the set cannot);
* can say *when* the file was last as Halbert remembers it, and why it thought
  so -- a refusal that is an answer rather than a shrug.

This is also where the freshness question belongs. ``82f25ff2`` kept
``continuity/freshness`` out of *recall* -- "a recall that silently probed the
filesystem would stop being a ledger read while still answering like one" --
and that argument is about reading. A write path that probes the host is not a
ledger read pretending to be one; probing is the whole operation.

**The guard never fails closed.** A ledger that cannot be read is a database
problem; refusing every write because of one would turn it into an
unadministrable machine. Every uncertain case proceeds and says why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from .provenance import (
    DIGEST_ABSENT,
    DIGEST_UNREADABLE,
    FILE_CONTENT_PREDICATE,
    content_digest,
)
from .recall import subject_for_path

logger = logging.getLogger(__name__)

__all__ = ["GuardResult", "check_before_write", "read_for_guard"]


def read_for_guard(path: str) -> "tuple[Optional[str], bool]":
    """The text on disk, and whether something stopped us looking.

    Returns ``(text, unreadable)``. ``unreadable`` is True only when the file
    is there and the read was refused -- a root-owned key, a directory we may
    not traverse.

    Every caller used to test ``os.path.exists`` and then swallow the
    exception, which threw away exactly the distinction that matters:
    ``None`` meant *absent* and *unreadable* alike, and the guard read it as
    absent. ``open`` already separates them, and separates them better than a
    probe can. ``os.path.exists`` and ``lexists`` are both wrong here --
    ``exists`` swallows the PermissionError raised when the parent directory
    is unreadable (``/etc/ssl/private``, mode 0700) and answers False for a
    file that is plainly there, while ``lexists`` answers True for a dangling
    symlink, which is the one case that really is gone. So: no probe. Ask for
    the bytes, and let the error say which kind of nothing this is.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), False
    except FileNotFoundError:
        # Includes a symlink whose target is gone: absent, correctly.
        return None, False
    except OSError:
        # PermissionError, EACCES on a parent, EIO, a device that will not
        # read. The file's existence is not in question; our access is.
        return None, True
    except Exception:  # pragma: no cover - defensive
        return None, True


@dataclass(frozen=True)
class GuardResult:
    """Whether this write may proceed, and what the ledger knows."""

    #: False only when the file demonstrably changed outside Halbert.
    ok: bool
    #: One sentence, always set. On a refusal it names what changed and when
    #: Halbert last saw the file as it remembers it.
    detail: str
    #: The digest the ledger holds, when it holds a real one.
    recorded_digest: Optional[str] = None
    #: The digest of what is on disk right now.
    on_disk_digest: Optional[str] = None
    #: The reason recorded alongside ``recorded_digest``.
    recorded_reason: Optional[str] = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


def _is_sentinel(digest: Optional[str]) -> bool:
    """True for a recorded value that was never a real digest."""
    return bool(digest) and digest.split(":", 1)[0] == DIGEST_UNREADABLE


def check_before_write(
    path: str,
    *,
    current_text: Optional[str],
    unreadable: bool = False,
    store: Any = None,
) -> GuardResult:
    """May Halbert write to ``path``?

    Args:
        path: the file about to be written.
        current_text: what is on disk right now, or None when there is no
            file. The caller reads it -- it needs the bytes anyway, for the
            before-digest it will record.
        unreadable: True when ``current_text`` is None because the read was
            refused rather than because the file is absent. Use
            :func:`read_for_guard`, which returns both. Without this the
            guard cannot tell "gone" from "not allowed to look", and it
            refused privileged writes saying the file had been removed.
        store: an open :class:`StateStore`, or None when no ledger is
            available.
    """
    on_disk = content_digest(current_text)

    if store is None:
        return GuardResult(
            True, "no ledger available; the write could not be checked against one",
            on_disk_digest=on_disk,
        )

    try:
        rows = store.current_state(
            subject=subject_for_path(path), predicate=FILE_CONTENT_PREDICATE
        )
    except Exception as e:
        logger.warning("write guard could not read the ledger for %s: %s", path, e)
        return GuardResult(
            True, f"the ledger could not be checked ({e}); the write proceeds",
            on_disk_digest=on_disk,
        )

    if not rows:
        return GuardResult(
            True, "the ledger has no record of this file yet",
            on_disk_digest=on_disk,
        )

    triple = rows[0]
    recorded = triple.object
    reason = getattr(triple, "reason", None)

    if _is_sentinel(recorded):
        # The write that recorded this could not be read back. Comparing bytes
        # against "we could not look" and refusing would turn an admitted gap
        # into a permanent block on the file.
        return GuardResult(
            True,
            "the last recorded write could not be read back, so there is "
            "nothing to compare against",
            on_disk_digest=on_disk, recorded_reason=reason,
        )

    if recorded == DIGEST_ABSENT:
        if unreadable:
            return GuardResult(
                True,
                "the ledger records this file as absent and it could not be "
                "read to check, so the write proceeds unconfirmed",
                on_disk_digest=on_disk, recorded_reason=reason,
            )
        if current_text is None:
            return GuardResult(
                True, "the ledger records this file as absent, and it is",
                on_disk_digest=on_disk, recorded_reason=reason,
            )
        return GuardResult(
            False,
            "this file is recorded as absent, but something is there now: it "
            "was created outside Halbert since the ledger last looked"
            + (f" ({reason})" if reason else ""),
            recorded_digest=recorded, on_disk_digest=on_disk, recorded_reason=reason,
        )

    if unreadable:
        # Not "gone". Refusing here made the privileged save path -- the case
        # the config editor exists for -- unreachable behind a refusal that
        # said something untrue about the file.
        return GuardResult(
            True,
            "this file could not be read for comparison, so there is nothing "
            "to compare against; the write proceeds and its before-digest is "
            "recorded as unknown",
            recorded_digest=recorded, on_disk_digest=on_disk, recorded_reason=reason,
        )

    if current_text is None:
        return GuardResult(
            False,
            "the ledger holds content for this file but it is no longer on "
            "disk: it was removed outside Halbert"
            + (f". Last recorded reason: {reason}" if reason else ""),
            recorded_digest=recorded, on_disk_digest=on_disk, recorded_reason=reason,
        )

    if recorded == on_disk:
        return GuardResult(
            True, "on disk exactly as the ledger last recorded it",
            recorded_digest=recorded, on_disk_digest=on_disk, recorded_reason=reason,
        )

    return GuardResult(
        False,
        "this file has changed outside Halbert since the ledger last saw it. "
        + (f"The last change Halbert recorded was: {reason}. " if reason else "")
        + "Read it before writing, so the change is not overwritten unseen.",
        recorded_digest=recorded, on_disk_digest=on_disk, recorded_reason=reason,
    )
