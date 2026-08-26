# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
System status API routes.
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any, List
import os
import platform
import socket
import threading
import psutil
from datetime import datetime, timezone

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


def get_cpu_temp() -> float | None:
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
# Host identity (Sovereign Host shell)
#
# The Engaged surface opens with Halbert speaking as the machine — "I am
# <hostname> …" — so it needs cheap, always-available facts about the host:
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

    Powers the Sovereign Host greeting. Structured fields let the UI style
    each fact; ``first_person`` is the same facts as one sentence for callers
    (or personas) that just want the line.
    """
    hostname = socket.gethostname()
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
        f"I am {hostname} ({os_info['pretty']}, {platform.system()} {kernel}). "
        f"Uptime is {_humanize_uptime(uptime_seconds)}. {health_clause}"
    )

    return {
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
