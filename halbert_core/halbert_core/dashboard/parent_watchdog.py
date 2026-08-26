# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Exit the backend when the process that launched it goes away.

The Tauri shell spawns the dashboard as a sidecar and kills it on a clean
quit, but nothing kills it when the shell is force-quit, crashes, or exits
through a path that skips Tauri's run-loop events. The shell therefore passes
its own pid in ``HALBERT_PARENT_PID``; this watchdog polls that pid and stops
the server once it is gone, so a stale uvicorn never keeps the port bound.

Nothing happens unless ``HALBERT_PARENT_PID`` is set, so plain
``uvicorn``/``python -m halbert_core.dashboard`` runs are unaffected.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("halbert.dashboard.parent_watchdog")

ENV_VAR = "HALBERT_PARENT_PID"
DEFAULT_INTERVAL_S = 2.0


def parent_alive(pid: int) -> bool:
    """True if ``pid`` still exists (signal 0 probe; EPERM counts as alive)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _default_stop() -> None:
    # SIGTERM lets uvicorn run its shutdown handlers; fall back to a hard exit
    # if the process is still around a few seconds later.
    logger.warning("Parent process gone — stopping the dashboard backend")
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)
    time.sleep(5.0)
    os._exit(0)


def watch(
    pid: int,
    *,
    interval_s: float = DEFAULT_INTERVAL_S,
    stop: Callable[[], None] = _default_stop,
    alive: Callable[[int], bool] = parent_alive,
) -> None:
    """Block until ``pid`` disappears, then call ``stop()``."""
    while alive(pid):
        time.sleep(interval_s)
    stop()


def start_parent_watchdog(
    env: Optional[dict] = None,
    *,
    interval_s: float = DEFAULT_INTERVAL_S,
    stop: Callable[[], None] = _default_stop,
) -> Optional[threading.Thread]:
    """Start the watchdog thread if ``HALBERT_PARENT_PID`` is set and valid.

    Returns the started daemon thread, or None when not configured.
    """
    raw = (env if env is not None else os.environ).get(ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        logger.warning(f"{ENV_VAR}={raw!r} is not a pid; parent watchdog disabled")
        return None
    if pid <= 0 or pid == os.getpid():
        logger.warning(f"{ENV_VAR}={pid} is not a usable parent pid; watchdog disabled")
        return None
    if not parent_alive(pid):
        logger.warning(f"{ENV_VAR}={pid} is already gone; stopping now")
        stop()
        return None
    thread = threading.Thread(
        target=watch,
        args=(pid,),
        kwargs={"interval_s": interval_s, "stop": stop},
        name="parent-watchdog",
        daemon=True,
    )
    thread.start()
    logger.info(f"Parent watchdog armed on pid {pid}")
    return thread
