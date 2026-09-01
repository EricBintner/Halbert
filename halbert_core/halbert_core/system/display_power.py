# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Screen power daemon (Task P2): backlight and DPMS, best-effort.

An idle kiosk surface must not glow in a dark room (spec doc 15 §5.2). The
frontend already tiers its own visuals (P1's ``StandbyController``:
ultra-dim at 30s idle, software blackout at 10min); this module is the
hardware half of tier 3 — backlight writes through
``/sys/class/backlight/*/brightness`` and DPMS blanking through
``xset dpms force off`` under X11.

Contract with P1's ``StandbyController``: at every tier *transition* the
controller fire-and-forgets ``POST /api/system/display`` with
``{"idle_seconds": <number>}`` — 30 entering tier 1, 600 entering tier 2,
0 on any wake. This daemon maps that report by THRESHOLD, never equality:
the frontend's 1s idle tick means real traffic sends 30 *or* 31, 600 *or*
601. ``>= 600`` is hardware tier 2 (backlight to 0, DPMS off), ``>= 30``
is tier 1 (backlight to ~10%), ``<= 0`` is wake (restore the pre-tier
backlight level and force DPMS on). The pre-tier baseline is captured on
the FIRST dim report so a wake restores the user's actual level, not a
hardcoded default. Unknown-shape bodies and non-numeric idle reports are
no-ops (200 with current state, never a 500).

Liveness — a deliberate "neither": no heartbeat, no process-liveness
checking. This daemon lives in the SAME PROCESS as the dashboard app, so
the one case a heartbeat would cover — the app dead while the screen
glows at full brightness — is un-coverable from inside the dead app by
definition: nothing running in the dead process can observe its own death
and blank the panel in response. An in-process heartbeat would be theater.
If an appliance deployment ever wants dead-app blackout, the right shape is
an out-of-process watchdog that persists this module's tier state to disk
and blanks the panel when the app dies — a deployment decision, noted here
so the next reader does not re-derive it.

Everything here is best-effort. Every public method swallows its own
failures (logged at debug) and no-ops when the hardware is absent — macOS
dev machines, headless boxes, and Wayland sessions without xset all take
the graceful path. Consumers (the routes, the state machine's
wake-before-speak hook) treat the module as advisory only.

The sysfs walk itself (``iter_backlight_interfaces``) is shared with
``discovery/scanners/laptop.py``'s read-only backlight scan, so the writer
and the scanner describe the same devices with the same rules.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# sysfs root for backlight devices. Injectable per-controller so tests can
# point the daemon at a fake tree in a tmpdir.
DEFAULT_BACKLIGHT_BASE = Path("/sys/class/backlight")

# P1's tier boundaries (StandbyController.tsx). Mapped by threshold, never
# equality — the frontend's 1s idle tick means real traffic is 30 or 31,
# 600 or 601.
TIER1_IDLE_SECONDS = 30
TIER2_IDLE_SECONDS = 600

# What "dim" and "black" mean in hardware backlight percent.
TIER1_BACKLIGHT_PERCENT = 10
TIER2_BACKLIGHT_PERCENT = 0

# Restored by a wake that has no captured baseline (the tier was entered
# while the backlight read failed) — full-on rather than a silent dark
# screen.
DEFAULT_WAKE_PERCENT = 100

# xset answers quickly or it is hung; never let a display hiccup stall a
# voice turn behind it.
_XSET_TIMEOUT_SECONDS = 5.0


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def iter_backlight_interfaces(base: Any = None) -> Iterator[Tuple[str, Path, int, int]]:
    """Yield ``(name, device_dir, brightness, max_brightness)`` per sysfs
    backlight device under ``base`` (default ``/sys/class/backlight``).

    Read-only discovery, shared with ``discovery/scanners/laptop.py``'s
    backlight scan so the writer and the scanner walk the same directories
    with the same rules. Malformed or unreadable devices are skipped, and
    the function itself never raises.
    """
    root = Path(base) if base is not None else DEFAULT_BACKLIGHT_BASE
    try:
        if not root.is_dir():
            return
        entries = sorted(root.iterdir())
    except OSError:
        return
    for dev in entries:
        try:
            if not dev.is_dir():
                continue
            brightness_file = dev / "brightness"
            max_file = dev / "max_brightness"
            if not (brightness_file.exists() and max_file.exists()):
                continue
            brightness = int(brightness_file.read_text().strip())
            max_brightness = int(max_file.read_text().strip())
        except (OSError, ValueError):
            continue
        if max_brightness <= 0:
            continue
        yield dev.name, dev, brightness, max_brightness


def _default_run(cmd: List[str]) -> None:
    """Run one xset command. Nonzero exit is fine; timeouts raise and are
    swallowed by the caller."""
    subprocess.run(
        cmd, check=False, capture_output=True, timeout=_XSET_TIMEOUT_SECONDS
    )


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class DisplayPowerController:
    """Best-effort screen power control for one machine.

    Never raises into callers; every hardware interaction is advisory and
    no-ops when the hardware is absent. ``backlight_base``/``environ``/
    ``which``/``run`` are injectable so tests can drive the controller
    against a fake sysfs tree and a recording xset runner.
    """

    def __init__(
        self,
        *,
        backlight_base: Any = None,
        environ: Optional[Mapping[str, str]] = None,
        which: Optional[Callable[[str], Optional[str]]] = None,
        run: Optional[Callable[[List[str]], Any]] = None,
    ):
        self._base = (
            Path(backlight_base)
            if backlight_base is not None
            else DEFAULT_BACKLIGHT_BASE
        )
        self._environ: Mapping[str, str] = environ if environ is not None else os.environ
        self._which = which if which is not None else shutil.which
        self._run = run if run is not None else _default_run
        # First writable sysfs device, discovered once and cached.
        self._device: Optional[Tuple[str, Path, int]] = None
        self._device_scanned = False
        # 0 = full, 1 = dimmed, 2 = blacked out (the frontend's tiers).
        self._tier = 0
        # Backlight percent captured on the first dim report, so wake
        # restores the user's actual level.
        self._baseline_percent: Optional[int] = None
        self._blanked = False

    # -- backlight ------------------------------------------------------

    def _writable_device(self) -> Optional[Tuple[str, Path, int]]:
        """The first backlight device whose brightness file is writable."""
        if not self._device_scanned:
            self._device_scanned = True
            for name, dev, _brightness, max_brightness in iter_backlight_interfaces(
                self._base
            ):
                if os.access(dev / "brightness", os.W_OK):
                    self._device = (name, dev, max_brightness)
                    break
        return self._device

    def _read_percent(self) -> Optional[int]:
        device = self._writable_device()
        if device is None:
            return None
        _name, dev, max_brightness = device
        try:
            raw = int((dev / "brightness").read_text().strip())
        except (OSError, ValueError):
            return None
        return int(round(raw / max_brightness * 100))

    def _write_percent(self, percent: int) -> bool:
        device = self._writable_device()
        if device is None:
            return False
        _name, dev, max_brightness = device
        percent = max(0, min(100, int(percent)))
        raw = int(round(percent / 100 * max_brightness))
        try:
            (dev / "brightness").write_text(f"{raw}\n")
        except OSError as exc:
            logger.debug("backlight write failed (best-effort): %s", exc)
            return False
        return True

    # -- DPMS -----------------------------------------------------------

    def _dpms_available(self) -> bool:
        """X11 with an xset binary — Wayland and headless take the no-op."""
        return bool(self._environ.get("DISPLAY")) and self._which("xset") is not None

    def _dpms_force(self, state: str) -> bool:
        """``xset dpms force on|off``. Returns whether the display state
        actually changed — a nonzero xset exit (no X server behind the
        DISPLAY, e.g. XQuartz without a running server) is a failure, so
        the tracked blank state never claims more than happened."""
        if not self._dpms_available():
            return False
        try:
            result = self._run(["xset", "dpms", "force", state])
        except Exception as exc:
            logger.debug("xset dpms force %s failed (best-effort): %s", state, exc)
            return False
        returncode = getattr(result, "returncode", None)
        if returncode not in (None, 0):
            logger.debug(
                "xset dpms force %s exited %s (best-effort)", state, returncode
            )
            return False
        return True

    # -- public surface --------------------------------------------------

    def available(self) -> Dict[str, Any]:
        """What this machine's screen power can actually control."""
        device = self._writable_device()
        return {
            "backlight": device is not None,
            "backlight_device": device[0] if device else None,
            "dpms": self._dpms_available(),
        }

    def status(self) -> Dict[str, Any]:
        try:
            return {
                "backlight": self._read_percent(),
                "blanked": self._blanked,
                "available": self.available(),
            }
        except Exception as exc:
            logger.debug("display status failed (best-effort): %s", exc)
            return {
                "backlight": None,
                "blanked": False,
                "available": {
                    "backlight": False,
                    "backlight_device": None,
                    "dpms": False,
                },
            }

    def set_backlight(self, percent: Any) -> None:
        """Direct control (admin/API surface): backlight to 0-100 percent.
        Deliberately does not disturb the idle-tier baseline."""
        try:
            self._write_percent(percent)
        except Exception as exc:
            logger.debug("set_backlight failed (best-effort): %s", exc)

    def set_blanked(self, blanked: bool) -> None:
        """Direct control: force DPMS off/on. A no-op without X11."""
        try:
            if self._dpms_force("off" if blanked else "on"):
                self._blanked = bool(blanked)
        except Exception as exc:
            logger.debug("set_blanked failed (best-effort): %s", exc)

    def wake(self) -> None:
        """Undo any tier/blank: restore the pre-tier backlight level and
        force DPMS on. The state machine calls this before speaking."""
        try:
            if self._tier > 0:
                restore = self._baseline_percent
                self._tier = 0
                self._baseline_percent = None
                self._write_percent(
                    restore if restore is not None else DEFAULT_WAKE_PERCENT
                )
            if self._blanked and self._dpms_force("on"):
                self._blanked = False
        except Exception as exc:
            logger.debug("display wake failed (best-effort): %s", exc)

    def report_idle(self, idle_seconds: Any) -> None:
        """P1's idle report, mapped by threshold (never equality)."""
        try:
            if isinstance(idle_seconds, bool) or not isinstance(
                idle_seconds, (int, float)
            ):
                # Not a real report — the P1 contract says no-op, not error.
                return
            if idle_seconds >= TIER2_IDLE_SECONDS:
                self._enter_tier(2)
            elif idle_seconds >= TIER1_IDLE_SECONDS:
                self._enter_tier(1)
            elif idle_seconds <= 0:
                self.wake()
            # 0 < idle < TIER1: not a transition the frontend ever sends.
        except Exception as exc:
            logger.debug("idle report handling failed (best-effort): %s", exc)

    def _enter_tier(self, tier: int) -> None:
        if tier <= self._tier:
            # Already at or past this tier — never re-capture the baseline
            # (it would record the dimmed level as the user's level).
            return
        if self._tier == 0:
            current = self._read_percent()
            if current is not None:
                self._baseline_percent = current
        self._tier = tier
        if tier == 1:
            dim_to = TIER1_BACKLIGHT_PERCENT
            if self._baseline_percent is not None:
                # Never brighten on an idle report: a screen the user
                # already keeps below the tier-1 level stays where it is.
                dim_to = min(dim_to, self._baseline_percent)
            self._write_percent(dim_to)
        else:
            self._write_percent(TIER2_BACKLIGHT_PERCENT)
            if self._dpms_force("off"):
                self._blanked = True


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_controller: Optional[DisplayPowerController] = None
_controller_lock = threading.Lock()


def get_display_power() -> DisplayPowerController:
    """The process-wide controller (dashboard routes, state machine hook)."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = DisplayPowerController()
    return _controller


def reset_display_power() -> None:
    """Drop the singleton (tests; nothing else should need this)."""
    global _controller
    with _controller_lock:
        _controller = None


def wake() -> None:
    """Wake the screen. The state machine calls this before speaking so a
    speak from standby never talks at a black screen."""
    get_display_power().wake()


def status() -> Dict[str, Any]:
    return get_display_power().status()


def report_idle(idle_seconds: Any) -> None:
    get_display_power().report_idle(idle_seconds)


def set_backlight(percent: Any) -> None:
    get_display_power().set_backlight(percent)


def set_blanked(blanked: bool) -> None:
    get_display_power().set_blanked(blanked)