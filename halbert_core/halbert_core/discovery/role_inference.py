# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Machine-role inference — what this computer is *for*.

Onboarding used to ask "what kind of user are you?" (casual / IT admin /
developer / AI professional). The answer was stored three places and read
by none, and the categories described the person, not the machine. The
redesign (HANDOFF-ONBOARDING-ROLE-INFERENCE-2026-09-07) asks the machine
question instead — workstation, server, home automation hub, multi-select —
and runs a fast probe first so the wizard *suggests* an answer from what it
found rather than making the user guess.

Two entry points:

- ``collect_probe_signals()`` runs the fast subset of the system profiler
  (hardware, desktop, services, containers, development, boot) plus an
  uptime read, and normalises it into a flat signals dict. A few seconds,
  never the full 30-60 s ``scan_all()``.
- ``infer_roles(signals)`` is a pure scoring function — the same input
  always produces the same roles, scores and reasoning, which is what
  makes it unit-testable and keeps the ambiguous cases (a 32 GB Mac mini,
  a NAS on an old Xeon) honest instead of hard-coded.

The roles themselves are declared in ``identity.VALID_MACHINE_ROLES`` so the
API, the prompt and the UI never carry separate lists.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from ..identity import VALID_MACHINE_ROLES

logger = logging.getLogger("halbert.discovery.role_inference")

# Service names that mark a home-automation stack. Kept as substrings to
# match the scanner's "notable" convention; deliberately excludes 'hass'
# (it substring-matches 'chassis').
HOME_AUTOMATION_SERVICES = (
    "homeassistant", "home-assistant", "hassio", "mosquitto", "mqtt",
    "zigbee2mqtt", "zwave", "deconz", "openhab", "node-red", "nodered",
    "frigate", "scrypted", "iobroker", "homekit", "homebridge",
)

# Services that mark a machine serving other machines.
SERVER_SERVICES = (
    "nginx", "apache", "httpd", "caddy",
    "postgres", "mysql", "mariadb", "mongo", "redis",
    "smbd", "nmbd", "nfs", "plex", "jellyfin", "minio",
)

# Zigbee/Z-Wave/Thread USB radios, matched against the USB device
# description strings the scanner collects (lsusb / IOUSB product names).
HOME_AUTOMATION_USB = (
    "zigbee", "z-wave", "zwave", "z-stick", "zstick", "sonoff",
    "conbee", "aeotec", "aeon labs", "skyconnect", "home assistant connect",
    "husbzb", "nortek", "cp210",  # cp210x is the usual Zigbee-stick UART
)

# Roles closer than this many points are suggested together (§5.4).
_TIE_MARGIN = 2


def collect_probe_signals(profiler=None) -> Dict[str, Any]:
    """Run the fast scan subset and normalise it into inference signals.

    Read-only: the ``_scan_*`` methods return dicts without mutating the
    stored profile, so probing never writes ``system_profile.json`` — that
    still belongs to the full scan at onboarding completion.
    """
    if profiler is None:
        from .scanners.system_profile import get_system_profiler

        profiler = get_system_profiler()

    # Call the _scan_* methods directly rather than scan_category(), which
    # mutates profiler.profile and saves it — the probe must be read-only.
    probes = {
        "os": profiler._scan_os,
        "hardware": profiler._scan_hardware,
        "desktop": profiler._scan_desktop,
        "services": profiler._scan_services_summary,
        "containers": profiler._scan_containers,
        "development": profiler._scan_development,
        "boot": profiler._scan_boot,
    }
    profile: Dict[str, Any] = {}
    for category, scan in probes.items():
        try:
            profile[category] = scan()
        except Exception as e:  # a missing category must not sink the probe
            logger.warning(f"probe: {category} scan failed: {e}")
            profile[category] = {}

    uptime_days: Optional[float] = None
    try:
        import psutil

        uptime_days = round((time.time() - psutil.boot_time()) / 86400, 1)
    except Exception:
        pass

    return extract_signals(profile, uptime_days=uptime_days)


def extract_signals(profile: Dict[str, Any],
                    uptime_days: Optional[float] = None) -> Dict[str, Any]:
    """Flatten a (partial) system profile into the signals infer_roles reads.

    Also usable on a completed ``scan_all()`` profile — same shape.
    """
    hw = profile.get("hardware") or {}
    desktop = profile.get("desktop") or {}
    services = profile.get("services") or {}
    containers = profile.get("containers") or {}
    development = profile.get("development") or {}
    os_info = profile.get("os") or {}

    cpu = hw.get("cpu") or {}
    memory = hw.get("memory") or {}
    cpu_cores = _as_int(cpu.get("cpu(s)"))
    ram_gb = _as_float(memory.get("total_gb"))
    cpu_model = str(cpu.get("model_name") or "")
    arch = str(os_info.get("arch") or "").lower()
    board_model = str((hw.get("motherboard") or {}).get("model") or "")
    usb_devices = [str(d) for d in (hw.get("usb_devices") or [])]

    notable = [
        str(s.get("name", ""))
        for s in (services.get("notable_services") or [])
    ]
    images = [str(c.get("image", "")) for c in (containers.get("containers") or [])]
    haystack = " ".join(notable + images).lower()
    usb_haystack = " ".join(usb_devices).lower()

    docker = containers.get("docker") or {}
    container_count = _as_int(docker.get("container_count")) or len(
        containers.get("containers") or [])

    has_display = bool(desktop.get("display_server")) or \
        desktop.get("session_type") == "gui"

    return {
        "has_display": has_display,
        "display_server": desktop.get("display_server"),
        "session_type": desktop.get("session_type"),
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "cpu_model": cpu_model,
        "arch": arch,
        "is_arm": arch in ("arm64", "aarch64") or arch.startswith("arm"),
        "gpus": list(hw.get("gpu") or []),
        "board_model": board_model,
        "form_factor": _guess_form_factor(board_model, cpu_model),
        "uptime_days": uptime_days,
        "has_docker": bool(docker.get("installed")),
        "container_count": container_count,
        "dev_tools": sorted((development.get("tools") or {}).keys()),
        "editors": list(development.get("editors") or []),
        "languages": sorted((development.get("languages") or {}).keys()),
        "notable_services": notable,
        "home_automation_detected": any(
            s in haystack for s in HOME_AUTOMATION_SERVICES),
        "home_automation_usb": [
            d for d in usb_devices
            if any(t in d.lower() for t in HOME_AUTOMATION_USB)
        ],
        "server_services": [
            s for s in notable
            if any(t in s.lower() for t in SERVER_SERVICES)
        ],
    }


def infer_roles(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Score the three roles against the signals and suggest the best.

    Returns ``{"roles": [...], "scores": {...}, "reasons": [...],
    "reasoning": "..."}`` — ``roles`` is the pre-checked suggestion, never
    empty (falls back to workstation, the most common answer).
    """
    scores = {role: 0 for role in VALID_MACHINE_ROLES}
    reasons: List[str] = []

    def add(role: str, points: int, why: str) -> None:
        scores[role] += points
        if why:
            reasons.append(why)

    has_display = bool(signals.get("has_display"))
    ram = signals.get("ram_gb")
    cores = signals.get("cpu_cores")
    uptime = signals.get("uptime_days")
    editors = signals.get("editors") or []
    dev_tools = signals.get("dev_tools") or []
    ha_services = bool(signals.get("home_automation_detected"))
    ha_usb = signals.get("home_automation_usb") or []
    server_svcs = signals.get("server_services") or []
    containers = signals.get("container_count") or 0
    has_docker = bool(signals.get("has_docker"))
    is_arm = bool(signals.get("is_arm"))
    small = signals.get("form_factor") == "small"

    # A probe that returned no evidence at all is a failed probe, not a
    # headless machine — "no display" may only score when something else
    # proved the scan ran. Without it the empty case must not guess.
    has_evidence = any(signals.get(k) for k in (
        "ram_gb", "cpu_cores", "uptime_days", "notable_services",
        "container_count", "dev_tools", "editors", "languages",
        "has_docker", "home_automation_detected", "home_automation_usb",
    ))

    # ── Workstation: someone sits at this machine ─────────────────────
    if has_display:
        add("workstation", 3, "a display and a graphical session")
        add("server", -2, "")
    elif has_evidence:
        add("workstation", -2, "")
        add("server", 3, "no desktop session — it runs headless")
    if editors:
        add("workstation", 2, f"editors installed ({', '.join(editors[:3])})")
    if dev_tools:
        add("workstation", 1,
            f"development tools ({', '.join(dev_tools[:4])})")
    if ram is not None and 8 <= ram <= 64:
        add("workstation", 1, f"{ram:g} GB of RAM")
    if uptime is not None and uptime > 30:
        add("workstation", -1, "")
        add("server", 1, f"up for {uptime:g} days without a reboot")
        add("home_automation_hub", 1, "")

    # ── Server: it runs services for other machines ───────────────────
    if server_svcs:
        add("server", 2,
            f"server software running ({', '.join(server_svcs[:4])})")
    if has_docker and containers > 3:
        add("server", 2, f"{containers} containers under Docker")
    if (ram is not None and ram > 64) or (cores is not None and cores > 16):
        add("server", 1, "server-class compute")

    # ── Home automation hub: it runs the house ────────────────────────
    if ha_services:
        add("home_automation_hub", 3,
            "home automation software (Home Assistant or its neighbours)")
    if ha_usb:
        add("home_automation_hub", 2,
            f"a Zigbee/Z-Wave radio ({ha_usb[0]})")
    if is_arm and ram is not None and ram <= 8:
        add("home_automation_hub", 2, "a small ARM board")
        add("server", -1, "")
    if small:
        add("home_automation_hub", 1, "a small-form-factor box")
    if server_svcs and len(server_svcs) >= 3:
        add("home_automation_hub", -1, "")

    roles = _pick(scores)
    return {
        "roles": roles,
        "scores": scores,
        "reasons": reasons[:6],
        "reasoning": _reasoning(roles, signals, reasons),
    }


def _pick(scores: Dict[str, int]) -> List[str]:
    """Apply the §5.4 tiebreaker to a score table; never returns []."""
    best = max(scores.values())
    if best <= 0:
        return ["workstation"]
    winners = [r for r in VALID_MACHINE_ROLES if scores[r] >= best - _TIE_MARGIN
               and scores[r] > 0]
    return winners or ["workstation"]


def _reasoning(roles: List[str], signals: Dict[str, Any],
               reasons: List[str]) -> str:
    """One sentence of evidence, in the machine's first person."""
    seen = "I found " + ", ".join(reasons[:3]) + "." if reasons \
        else "I did not find strong signals either way."
    labels = {"workstation": "a workstation", "server": "a server",
              "home_automation_hub": "a home hub"}
    named = " and ".join(labels[r] for r in roles)
    if len(roles) > 1:
        return f"{seen} I could be {named} — pick whichever fits."
    return f"{seen} I look like {named}."


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _guess_form_factor(board_model: str, cpu_model: str) -> str:
    """Coarse size bucket for the hub/server tiebreaks.

    Small: Mac mini, NUC, Raspberry Pi-class boards. Everything else is
    "unknown" — guessing wrong is worse than not guessing.
    """
    text = f"{board_model} {cpu_model}".lower()
    if re.search(r"macmini|mac mini|nuc|raspberry pi|rpi\d|odroid", text):
        return "small"
    return "unknown"
