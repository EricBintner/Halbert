# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A07-G8 — the third bit of the interrupt algebra.

Stop and steer were the only two verbs a running tool could hear, and they
answer different questions. Stop ends the command. Steer waits for the batch
boundary — which, during a five-minute backup or a build, is five minutes
away. So a steward who typed "when that finishes, also rotate the logs"
watched their words sit unread, with nothing on the surface saying so, and if
they gave up and pressed stop the steer went with it (A07-G3).

Yield is the third bit: *stop waiting for this command without ending it*.
The command keeps running in its own shell; the tool returns what it has;
the boundary arrives now, and the steer is delivered there.

The registry here is deliberately one bit per session and nothing else. It
does not own processes — the terminal session manager already does that, and
a pool session whose block is open is never reaped and never re-acquired, so
a yielded block keeps its shell by the rules that already exist.

Two properties the bit has to have, both learned from the failure they
prevent:

- **It only exists while a tool is running.** A steer that arrives between
  two tool calls has a boundary of its own coming in milliseconds. If the
  request leaked past the execution it was raised against, the *next*
  command would detach the moment it started — abandoned for a steer that
  had already been delivered.
- **Ending an execution clears only your own.** The token is why. Tool calls
  within one turn are sequential, but the `end` of a cancelled execution can
  land after the next `begin`, and a clear from the dead one would eat a
  live request.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# session_id -> token of the execution currently running under it
_running: Dict[str, str] = {}

# session_ids with a yield asked for and not yet consumed
_requested: Set[str] = set()


def begin(session_id: Optional[str]) -> Optional[str]:
    """Mark a tool execution as running for ``session_id``.

    Returns a token to pass back to :func:`end`, or None when there is no
    session to key on — ``current_agent_session`` is None outside a turn,
    and a bit keyed on None would be a global flag every tool reads.
    """
    if not session_id:
        return None
    token = uuid.uuid4().hex
    with _lock:
        _running[session_id] = token
        # A request left over from an execution that never consumed it is
        # not this execution's to inherit.
        _requested.discard(session_id)
    return token


def end(session_id: Optional[str], token: Optional[str]) -> None:
    """Mark the execution finished, dropping any request it did not consume."""
    if not session_id or not token:
        return
    with _lock:
        if _running.get(session_id) != token:
            # A late `end` from an execution that has already been replaced.
            return
        _running.pop(session_id, None)
        _requested.discard(session_id)


def request(session_id: Optional[str]) -> bool:
    """Ask the running tool to yield. False when nothing is running."""
    if not session_id:
        return False
    with _lock:
        if session_id not in _running:
            return False
        _requested.add(session_id)
    logger.debug("yield requested for session %s", session_id)
    return True


def consume(session_id: Optional[str]) -> bool:
    """Read the bit and clear it. True at most once per request."""
    if not session_id:
        return False
    with _lock:
        if session_id not in _requested:
            return False
        _requested.discard(session_id)
    return True


def pending(session_id: Optional[str]) -> bool:
    """Peek. For surfaces and tests; the consumption point uses consume()."""
    if not session_id:
        return False
    with _lock:
        return session_id in _requested


def reset() -> None:
    """Drop all state. Tests only."""
    with _lock:
        _running.clear()
        _requested.clear()
