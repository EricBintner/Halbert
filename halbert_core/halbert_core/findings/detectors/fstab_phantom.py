"""
fstab phantom detector.

Parses /etc/fstab and checks whether each referenced device actually
exists on the system. Creates findings for entries that reference
non-existent devices (phantom mounts).

Phase 5 / T5c.2.
"""

from __future__ import annotations

import logging
import os
from typing import List

from ..store import Finding

logger = logging.getLogger(__name__)

# fstab options that make an entry non-blocking at boot
_NONBLOCKING_OPTIONS = {"noauto", "nofail", "x-systemd.automount"}


def _mount_unit_name(mount_point: str) -> str:
    """Escape a mount point into its systemd mount unit name.

    '/' becomes '-', the leading '-' (from the leading '/') is dropped,
    existing '-' chars are escaped as \\x2d, and other special characters
    are replaced with '-'. Root '/' maps to '-.mount'. Local
    implementation — no subprocess.

    Examples: /mnt/data -> mnt-data.mount, /boot/efi -> boot-efi.mount,
    / -> -.mount
    """
    if mount_point == "/":
        return "-.mount"
    escaped = mount_point.replace("-", "\\x2d").replace("/", "-")
    # Collapse the leading '-' produced by the leading '/'
    escaped = escaped.lstrip("-")
    # Minimally escape anything left that isn't unit-name safe
    escaped = "".join(
        c if (c.isalnum() or c in ":_.\\-") else "-" for c in escaped
    )
    return f"{escaped}.mount"


def _check_device_exists(device: str) -> bool:
    """Check if a device reference exists.

    Handles:
    - UUID=xxx  → check /dev/disk/by-uuid/xxx
    - LABEL=xxx → check /dev/disk/by-label/xxx
    - /dev/xxx  → check if the device node exists
    - Other     → assume it's a network/swap/special, skip
    """
    if device.startswith("UUID="):
        uuid = device[5:]
        path = f"/dev/disk/by-uuid/{uuid}"
        return os.path.exists(path)
    elif device.startswith("LABEL="):
        label = device[6:]
        path = f"/dev/disk/by-label/{label}"
        return os.path.exists(path)
    elif device.startswith("/dev/"):
        return os.path.exists(device)
    elif device in ("none", "swap", "tmpfs", "proc", "sysfs", "devpts"):
        return True  # Special filesystems, not device-backed
    else:
        # Network mounts (nfs, sshfs, etc.) — can't verify, assume exists
        return True


def _parse_fstab(path: str = "/etc/fstab") -> List[dict]:
    """Parse fstab into structured entries.

    Returns a list of dicts with keys: line_no, device, mount_point,
    fs_type, options, dump, pass.
    """
    entries: List[dict] = []
    if not os.path.isfile(path):
        return entries

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                fields = stripped.split()
                if len(fields) < 4:
                    continue
                entries.append({
                    "line_no": i,
                    "device": fields[0],
                    "mount_point": fields[1],
                    "fs_type": fields[2],
                    "options": fields[3] if len(fields) > 3 else "defaults",
                    "dump": fields[4] if len(fields) > 4 else "0",
                    "pass": fields[5] if len(fields) > 5 else "0",
                })
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
    return entries


class FstabPhantomDetector:
    """Detect fstab entries that reference non-existent devices."""

    def __init__(self, fstab_path: str = "/etc/fstab"):
        self.fstab_path = fstab_path

    def detect(self) -> List[Finding]:
        """Run detection and return a list of findings."""
        findings: List[Finding] = []
        entries = _parse_fstab(self.fstab_path)

        for entry in entries:
            device = entry["device"]
            if _check_device_exists(device):
                continue

            # Determine severity: entries with noauto/nofail/automount
            # options are NOT boot-blocking — the mount is skipped.
            mount_point = entry["mount_point"]
            options = set(entry["options"].split(","))
            nonblocking = bool(options & _NONBLOCKING_OPTIONS)

            if mount_point == "/" or mount_point == "/boot":
                severity = "critical"
                why_care = (
                    f"Boot may hang or fail waiting for this device. "
                    f"This is a critical mount point — if the device is "
                    f"missing at boot, the system may not boot at all."
                )
            elif nonblocking:
                severity = "info"
                why_care = (
                    f"This entry is non-blocking ({', '.join(sorted(options & _NONBLOCKING_OPTIONS))}). "
                    f"The mount will be skipped at boot with an error — "
                    f"boot is not blocked. The phantom device should "
                    f"still be fixed or removed to avoid failed mount units."
                )
            else:
                severity = "warning"
                why_care = (
                    f"Boot may hang or fail waiting for this device. "
                    f"Without nofail/noauto, systemd will block boot until "
                    f"the device times out."
                )

            findings.append(Finding(
                id="",
                detector="fstab_phantom",
                severity=severity,
                title=f"fstab phantom: {device}",
                description=(
                    f"fstab line {entry['line_no']} references device '{device}' "
                    f"which does not exist on this system. Mount point: "
                    f"{mount_point}, filesystem: {entry['fs_type']}."
                ),
                why_now=(
                    f"fstab entry references device '{device}' that was not "
                    f"found during configuration scan."
                ),
                why_care=why_care,
                why_so=(
                    f"fstab line {entry['line_no']} in {self.fstab_path} "
                    f"references '{device}', but no block device with that "
                    f"identifier was found. Checked /dev/disk/by-uuid/, "
                    f"/dev/disk/by-label/, and /dev/ directly."
                ),
                why_trust=[
                    f"{self.fstab_path}:{entry['line_no']}",
                ],
                affected_paths=[self.fstab_path],
                affected_services=[_mount_unit_name(mount_point)],
            ))

        return findings
