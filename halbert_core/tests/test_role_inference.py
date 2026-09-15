# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Machine-role inference — the scoring function and the probe's
signal extraction.

The fixtures are the handoff's own ambiguous cases
(HANDOFF-ONBOARDING-ROLE-INFERENCE-2026-09-07 §5.3): a headless Mac mini
running Home Assistant is server+hub, the same mini on a desk is
workstation+hub, a NAS on an old Xeon is a server, a Pi with a Zigbee
stick is a hub. If these change, the design changed — update both.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.discovery.role_inference import (
    extract_signals,
    infer_roles,
)


def _signals(**over):
    base = {
        "has_display": False,
        "display_server": None,
        "session_type": None,
        "ram_gb": None,
        "cpu_cores": None,
        "cpu_model": "",
        "arch": "x86_64",
        "is_arm": False,
        "gpus": [],
        "board_model": "",
        "form_factor": "unknown",
        "uptime_days": None,
        "has_docker": False,
        "container_count": 0,
        "dev_tools": [],
        "editors": [],
        "languages": [],
        "notable_services": [],
        "home_automation_detected": False,
        "home_automation_usb": [],
        "server_services": [],
    }
    base.update(over)
    return base


class TestInferRoles:
    def test_headless_mac_mini_running_ha_is_server_and_hub(self):
        s = _signals(
            ram_gb=32, cpu_cores=8, form_factor="small",
            has_docker=True, container_count=6, uptime_days=45,
            home_automation_detected=True,
        )
        out = infer_roles(s)
        assert set(out["roles"]) == {"server", "home_automation_hub"}

    def test_desk_mac_mini_running_ha_is_workstation_and_hub(self):
        s = _signals(
            has_display=True, display_server="quartz-compositor",
            session_type="gui", ram_gb=32, cpu_cores=8,
            form_factor="small", has_docker=True, container_count=2,
            home_automation_detected=True,
        )
        out = infer_roles(s)
        assert set(out["roles"]) == {"workstation", "home_automation_hub"}

    def test_nas_on_old_xeon_is_server_only(self):
        s = _signals(
            ram_gb=16, cpu_cores=4, cpu_model="Intel Xeon E3",
            has_docker=True, container_count=8, uptime_days=90,
            server_services=["smbd", "nfs-server"],
        )
        out = infer_roles(s)
        assert out["roles"] == ["server"]

    def test_desktop_workstation_with_dev_tools(self):
        s = _signals(
            has_display=True, display_server="quartz-compositor",
            session_type="gui", ram_gb=64, cpu_cores=24,
            cpu_model="Apple M2 Ultra",
            dev_tools=["git", "node", "python3", "cargo"],
            editors=["code", "vim"],
        )
        out = infer_roles(s)
        assert out["roles"] == ["workstation"]

    def test_raspberry_pi_with_ha_and_zigbee_is_hub(self):
        s = _signals(
            ram_gb=4, cpu_cores=4, arch="aarch64", is_arm=True,
            form_factor="small", uptime_days=60,
            home_automation_detected=True,
            home_automation_usb=["Sonoff Zigbee 3.0 USB Dongle"],
        )
        out = infer_roles(s)
        assert out["roles"] == ["home_automation_hub"]

    def test_workstation_that_also_runs_ha_suggests_workstation(self):
        # Handoff §5.3's last case: a strong workstation that also runs HA
        # in a container suggests Workstation only — the gap (7 vs 3) is
        # past the tie margin, so the hub stays an un-checked toggle.
        s = _signals(
            has_display=True, session_type="gui", ram_gb=64,
            cpu_cores=24, cpu_model="Apple M2 Ultra",
            dev_tools=["git"], editors=["code"],
            has_docker=True, container_count=1,
            home_automation_detected=True,
        )
        out = infer_roles(s)
        assert out["roles"] == ["workstation"]
        assert out["scores"]["home_automation_hub"] > 0

    def test_no_signals_defaults_to_workstation(self):
        out = infer_roles(_signals())
        assert out["roles"] == ["workstation"]

    def test_reasoning_is_first_person_and_names_the_roles(self):
        out = infer_roles(_signals(has_display=True, session_type="gui",
                                   ram_gb=16, cpu_cores=8))
        assert out["reasoning"].startswith("I found")
        assert "workstation" in out["reasoning"]

    def test_reasoning_for_ambiguous_pick_offers_the_choice(self):
        out = infer_roles(_signals(
            has_display=True, session_type="gui", ram_gb=32,
            home_automation_detected=True, form_factor="small",
        ))
        assert "pick whichever fits" in out["reasoning"]


class TestExtractSignals:
    def test_full_profile_shape(self):
        profile = {
            "os": {"arch": "arm64"},
            "hardware": {
                "cpu": {"model_name": "Apple M2 Ultra", "cpu(s)": "24"},
                "memory": {"total_gb": 64.0},
                "gpu": ["Apple M2 Ultra"],
                "motherboard": {"model": "Mac14,14"},
                "usb_devices": ["Sonoff Zigbee 3.0 USB Dongle"],
            },
            "desktop": {"display_server": "quartz-compositor",
                        "session_type": "gui"},
            "services": {"notable_services": [
                {"name": "com.docker.docker", "state": "running"},
                {"name": "homeassistant", "state": "running"},
                {"name": "nginx", "state": "running"},
            ]},
            "containers": {"docker": {"installed": True,
                                      "container_count": 5},
                           "containers": [
                               {"image": "ghcr.io/home-assistant/home-assistant"},
                           ]},
            "development": {"tools": {"git": "2.4", "node": "22"},
                            "editors": ["code"],
                            "languages": {"python3": "3.12"}},
            "boot": {},
        }
        s = extract_signals(profile, uptime_days=3.0)
        assert s["has_display"] is True
        assert s["ram_gb"] == 64.0
        assert s["cpu_cores"] == 24
        assert s["is_arm"] is True
        assert s["has_docker"] is True
        assert s["container_count"] == 5
        assert s["home_automation_detected"] is True  # service or image
        assert s["home_automation_usb"]  # the Zigbee stick
        assert "nginx" in s["server_services"]
        assert s["dev_tools"] == ["git", "node"]

    def test_container_images_count_toward_ha_detection(self):
        profile = {
            "services": {"notable_services": []},
            "containers": {"docker": {"installed": True},
                           "containers": [
                               {"image": "lscr.io/linuxserver/homeassistant"},
                               {"image": "mosquitto"},
                           ]},
        }
        s = extract_signals(profile)
        assert s["home_automation_detected"] is True

    def test_empty_profile_yields_safe_signals(self):
        s = extract_signals({})
        assert s["has_display"] is False
        assert s["home_automation_detected"] is False
        assert infer_roles(s)["roles"] == ["workstation"]
