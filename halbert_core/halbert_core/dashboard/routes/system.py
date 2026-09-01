# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
System status API routes.
"""

from fastapi import APIRouter, Depends, Request
from typing import Dict, Any, List, Optional
import logging
import os
import platform
import socket
import threading
import psutil
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from ...system import display_power

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """
    Get current system status.
    
    Returns system metrics (CPU, memory, disk, uptime).
    """
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_temp = get_cpu_temp()
    
    # Memory
    memory = psutil.virtual_memory()
    
    # Disk
    disk = psutil.disk_usage('/')
    
    # Uptime
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = (datetime.now(timezone.utc) - boot_time).total_seconds()
    
    # Load average
    load_avg = psutil.getloadavg()
    
    return {
        "cpu": {
            "percent": cpu_percent,
            "temperature": cpu_temp,
            "cores": psutil.cpu_count()
        },
        "memory": {
            "total_gb": memory.total / (1024**3),
            "used_gb": memory.used / (1024**3),
            "available_gb": memory.available / (1024**3),
            "percent": memory.percent
        },
        "disk": {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent": disk.percent
        },
        "uptime": {
            "seconds": int(uptime_seconds),
            "boot_time": boot_time.isoformat()
        },
        "load_average": {
            "1min": load_avg[0],
            "5min": load_avg[1],
            "15min": load_avg[2]
        },
        "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
    }


def get_cpu_temp() -> Optional[float]:
    """Get CPU temperature if available."""
    try:
        temps = psutil.sensors_temperatures()
        
        # Try common sensor names
        for name in ['coretemp', 'k10temp', 'cpu_thermal']:
            if name in temps:
                entries = temps[name]
                if entries:
                    return entries[0].current
        
        return None
    
    except (AttributeError, Exception):
        return None


# -----------------------------------------------------------------------------
# Host identity
#
# The engaged surface opens with the machine speaking as itself — "I am
# <name> …" — so it needs cheap, always-available facts about the host:
# no system scan, no profile on disk, no LLM call. Everything here comes from
# psutil/platform and is safe to call on every app start.
# -----------------------------------------------------------------------------

# A pool this full is worth mentioning in the opening line.
_POOL_WARN_PERCENT = 90.0

# Pseudo/virtual filesystems that are not "storage the host cares about".
_SKIP_FSTYPES = {
    "devfs", "autofs", "tmpfs", "devtmpfs", "squashfs", "overlay",
    "proc", "sysfs", "cgroup", "cgroup2", "ramfs", "fuse.portal",
}


def _os_release() -> Dict[str, str]:
    """Distro name/version, per platform. Never raises."""
    system = platform.system()
    if system == "Linux":
        try:
            fields = {}
            with open("/etc/os-release", "r", encoding="utf-8") as fh:
                for line in fh:
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    fields[key.strip()] = value.strip().strip('"')
            return {
                "name": fields.get("NAME", "Linux"),
                "version": fields.get("VERSION_ID", ""),
                "pretty": fields.get("PRETTY_NAME", "Linux"),
            }
        except OSError:
            return {"name": "Linux", "version": "", "pretty": "Linux"}
    if system == "Darwin":
        version = platform.mac_ver()[0]
        return {
            "name": "macOS",
            "version": version,
            "pretty": f"macOS {version}".strip(),
        }
    version = platform.version()
    return {"name": system or "unknown", "version": version, "pretty": f"{system} {version}".strip()}


# Mount prefixes that are plumbing, not storage a person thinks about: macOS
# system/simulator volumes, snap loopbacks, container layers.
_SKIP_MOUNT_PREFIXES = (
    "/System/Volumes/",
    "/Library/Developer/CoreSimulator",
    "/private/var/vm",
    "/snap/",
    "/var/lib/docker",
    "/var/snap",
)

# Below this a "pool" is an app bundle or an EFI stub, not a disk.
_MIN_POOL_GB = 1.0


def _is_pool(mountpoint: str, fstype: str, total_bytes: int) -> bool:
    """Whether a mount is storage the host would describe as one of its pools."""
    if fstype in _SKIP_FSTYPES:
        return False
    if mountpoint == "/":
        return True
    if mountpoint.startswith(_SKIP_MOUNT_PREFIXES):
        return False
    return total_bytes >= _MIN_POOL_GB * (1024 ** 3)


def _storage_pools() -> List[Dict[str, Any]]:
    """Real mounted filesystems with usage. Unreadable mounts are skipped."""
    pools: List[Dict[str, Any]] = []
    seen_devices = set()
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        return pools
    for part in partitions:
        if part.device in seen_devices:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        if not _is_pool(part.mountpoint, part.fstype, usage.total):
            continue
        seen_devices.add(part.device)
        pools.append({
            "mount": part.mountpoint,
            "device": part.device,
            "fstype": part.fstype,
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_percent": usage.percent,
            "healthy": usage.percent < _POOL_WARN_PERCENT,
        })
    return pools


# psutil's interval=None form reports utilisation *since the caller thread's
# previous sample*. The first call on a thread has no previous sample and
# psutil documents the 0.0 it returns as meaningless — so the first call on
# each thread pays for one short blocking sample instead of reporting a lie to
# the greeting card, which then sits there until the next poll.
_CPU_PRIME_SECONDS = 0.1
_cpu_primed_threads: set = set()
_cpu_prime_lock = threading.Lock()


def _cpu_percent() -> float:
    """CPU utilisation, correct on the first call as well as the rest."""
    tid = threading.get_ident()
    with _cpu_prime_lock:
        primed = tid in _cpu_primed_threads
        if not primed:
            _cpu_primed_threads.add(tid)
    if not primed:
        return psutil.cpu_percent(interval=_CPU_PRIME_SECONDS)
    return psutil.cpu_percent(interval=None)


# Onboarding asks "What should I call this computer?" and stores the answer as
# ``ai_name`` in preferences.yml. That answer is the machine's name — the
# hostname is a technical fact about it, not what it is called. Everything
# user-facing leads with the chosen name; ``hostname`` stays in the payload for
# callers that need the real thing.
_FALLBACK_NAME = "Halbert"

# Suffixes a hostname picks up from mDNS/DHCP that nobody means as part of the
# name. Only stripped when we are falling back to the hostname at all.
_HOSTNAME_SUFFIXES = (".local", ".lan", ".home", ".localdomain")


def _chosen_name() -> Optional[str]:
    """The name the user picked in onboarding, or None if they never did.

    Deliberately distinguishes "picked" from "fell back": the caller needs to
    know whether it is holding a name or a hostname. Written by
    ``POST /api/settings/computer-name`` and the onboarding step.
    """
    try:
        from ...utils.platform import get_config_dir
        import yaml

        config_path = get_config_dir() / "preferences.yml"
        if not config_path.exists():
            return None
        with open(config_path, "r", encoding="utf-8") as fh:
            prefs = yaml.safe_load(fh) or {}
        name = prefs.get("ai_name")
        return str(name).strip() or None if name else None
    except Exception:
        # Preferences are a convenience here, never a hard dependency.
        return None


def _short_hostname(hostname: str) -> str:
    """A hostname without the plumbing suffix, for use as a fallback name."""
    for suffix in _HOSTNAME_SUFFIXES:
        if hostname.endswith(suffix):
            return hostname[: -len(suffix)]
    return hostname


def _display_name(hostname: str) -> str:
    """What this machine should be called, in that order of preference."""
    return _chosen_name() or _short_hostname(hostname) or _FALLBACK_NAME


def _humanize_uptime(seconds: int) -> str:
    """'18 days', '4 hours', '9 minutes' — one unit, the largest that fits."""
    if seconds >= 86400:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    if seconds >= 3600:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    minutes = max(1, seconds // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


@router.get("/identity")
async def get_host_identity() -> Dict[str, Any]:
    """Who this machine is, in the first person.

    Powers the engaged surface's opening line. Structured fields let the UI
    style each fact; ``first_person`` is the same facts as one sentence for
    callers (or personas) that just want the line.

    ``display_name`` is what the machine is called — the name chosen in
    onboarding. ``hostname`` is the DNS/system name, kept as a fact rather
    than presented as an identity.
    """
    hostname = socket.gethostname()
    display_name = _display_name(hostname)
    os_info = _os_release()
    kernel = platform.release()

    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = int((datetime.now(timezone.utc) - boot_time).total_seconds())

    cores = psutil.cpu_count(logical=True) or 0
    physical_cores = psutil.cpu_count(logical=False) or cores
    memory = psutil.virtual_memory()
    pools = _storage_pools()
    healthy_pools = [p for p in pools if p["healthy"]]

    try:
        load_avg = os.getloadavg()
    except (OSError, AttributeError):
        load_avg = (0.0, 0.0, 0.0)

    all_healthy = len(healthy_pools) == len(pools) and memory.percent < 90
    pool_word = "pool" if len(pools) == 1 else "pools"
    if all_healthy:
        health_clause = (
            f"All {cores} cores and {len(pools)} storage {pool_word} are healthy."
        )
    else:
        strained = [p["mount"] for p in pools if not p["healthy"]]
        health_clause = (
            f"{len(healthy_pools)} of {len(pools)} storage {pool_word} healthy"
            + (f" — {', '.join(strained)} running full." if strained else ".")
        )

    first_person = (
        f"I am {display_name} ({os_info['pretty']}, {platform.system()} {kernel}). "
        f"Uptime is {_humanize_uptime(uptime_seconds)}. {health_clause}"
    )

    return {
        "display_name": display_name,
        "hostname": hostname,
        "os": {
            "name": os_info["name"],
            "version": os_info["version"],
            "pretty": os_info["pretty"],
            "platform": platform.system(),
            "kernel": kernel,
            "arch": platform.machine(),
        },
        "uptime": {
            "seconds": uptime_seconds,
            "human": _humanize_uptime(uptime_seconds),
            "boot_time": boot_time.isoformat(),
        },
        "cpu": {
            "cores": cores,
            "physical_cores": physical_cores,
            "percent": _cpu_percent(),
            "temperature": get_cpu_temp(),
        },
        "memory": {
            "total_gb": round(memory.total / (1024 ** 3), 1),
            "used_gb": round(memory.used / (1024 ** 3), 1),
            "percent": memory.percent,
        },
        "storage": {
            "pools": pools,
            "healthy": len(healthy_pools),
            "total": len(pools),
        },
        "load_average": {
            "1min": round(load_avg[0], 2),
            "5min": round(load_avg[1], 2),
            "15min": round(load_avg[2], 2),
        },
        "all_healthy": all_healthy,
        "first_person": first_person,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }


# -----------------------------------------------------------------------------
# Screen power (Task P2)
#
# GET/POST /api/system/display — the hardware half of the standby tiers.
# The controller module (system/display_power.py) is best-effort and
# self-reports availability, so these endpoints are harmless on machines
# with no controllable hardware: they report available: false instead of
# gating. Two POST shapes share the endpoint:
#
#   {"idle_seconds": <number>}       P1's StandbyController tier report
#                                    (transition-only: 30/600/0 — mapped
#                                    by threshold, never equality)
#   {"backlight": 0..100, "blanked": bool}   direct control (admin/API)
#
# Precedence: the idle_seconds KEY wins when present — including when its
# value is unusable ("bogus", null), in which case the whole body is a
# no-op and any other fields in it are ignored. P1's traffic never mixes
# shapes; a mixed body is a client bug, and guessing which half it meant
# would be worse than doing nothing.
#
# Unknown-shape bodies and non-numeric values are HTTP no-ops: 200 with
# the current state, never a 500.
# -----------------------------------------------------------------------------

def _unavailable_state() -> Dict[str, Any]:
    """The status answer for a machine (or a moment) with no control."""
    return {
        "backlight": None,
        "blanked": False,
        "available": {
            "backlight": False,
            "backlight_device": None,
            "dpms": False,
        },
    }


def _apply_display_body(body: Dict[str, Any]) -> None:
    """Route one POST body onto the controller. Only valid values act;
    everything else falls through as a no-op."""
    if "idle_seconds" in body:
        idle = body["idle_seconds"]
        if isinstance(idle, bool) or not isinstance(idle, (int, float)):
            return  # non-numeric idle report: contract says no-op
        display_power.report_idle(idle)
        return
    backlight = body.get("backlight")
    if (
        isinstance(backlight, (int, float))
        and not isinstance(backlight, bool)
        and 0 <= backlight <= 100
    ):
        display_power.set_backlight(int(backlight))
    blanked = body.get("blanked")
    if isinstance(blanked, bool):
        display_power.set_blanked(blanked)


@router.get("/system/display")
async def get_display_state() -> Dict[str, Any]:
    """Current screen power state: backlight percent, DPMS blank flag, and
    what is controllable on this machine."""
    try:
        return display_power.status()
    except Exception:
        logger.debug("GET /system/display failed (best-effort)", exc_info=True)
        return _unavailable_state()


@router.post("/system/display")
async def post_display_state(request: Request) -> Dict[str, Any]:
    """Apply a display control request, then return the current state.

    Accepts P1's idle report (``{"idle_seconds": ...}``) or direct control
    (``{"backlight": 0..100, "blanked": bool}``). Unknown shapes, malformed
    JSON, and non-numeric values are no-ops — the caller always gets the
    current state with a 200, never a 500.
    """
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        try:
            # Off the event loop: the apply step may spawn xset, and a
            # display hiccup must never stall every other request behind
            # a blocking subprocess.
            await run_in_threadpool(_apply_display_body, body)
        except Exception:
            logger.debug("POST /system/display body failed (best-effort)", exc_info=True)
    try:
        return display_power.status()
    except Exception:
        logger.debug("POST /system/display status failed (best-effort)", exc_info=True)
        return _unavailable_state()
