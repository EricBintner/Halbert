# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""GET /api/identity — the facts behind Halbert's first-person greeting.

The engaged surface opens with the machine identifying itself, so this endpoint
must answer from psutil/platform alone: no system scan, no profile on disk, no
model loaded. It identifies by the name chosen in onboarding, not the hostname.
"""

from collections import namedtuple

import pytest

from halbert_core.dashboard.routes import system as system_routes


Partition = namedtuple("Partition", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")


class TestPoolFiltering:

    def test_root_is_always_a_pool(self):
        assert system_routes._is_pool("/", "apfs", 1) is True

    def test_pseudo_filesystems_are_not_pools(self):
        assert system_routes._is_pool("/dev", "devfs", 10 * 1024 ** 3) is False
        assert system_routes._is_pool("/run", "tmpfs", 10 * 1024 ** 3) is False

    def test_platform_plumbing_is_not_a_pool(self):
        big = 100 * 1024 ** 3
        assert system_routes._is_pool("/System/Volumes/Data", "apfs", big) is False
        assert system_routes._is_pool(
            "/Library/Developer/CoreSimulator/Volumes/iOS_18", "apfs", big
        ) is False
        assert system_routes._is_pool("/snap/core/1234", "squashfs", big) is False

    def test_tiny_mounts_are_not_pools(self):
        assert system_routes._is_pool("/Volumes/SomeApp", "apfs", 100 * 1024 ** 2) is False

    def test_real_volumes_are_pools(self):
        assert system_routes._is_pool("/Volumes/Media", "apfs", 4 * 1024 ** 4) is True
        assert system_routes._is_pool("/home", "ext4", 500 * 1024 ** 3) is True

    def test_unreadable_mounts_are_skipped_not_fatal(self, monkeypatch):
        parts = [
            Partition("/dev/disk1", "/", "apfs", "rw"),
            Partition("/dev/disk2", "/Volumes/Locked", "apfs", "rw"),
        ]
        monkeypatch.setattr(system_routes.psutil, "disk_partitions", lambda all=False: parts)

        def usage(mount):
            if mount == "/Volumes/Locked":
                raise PermissionError("nope")
            return Usage(1024 ** 4, 1024 ** 3, 1024 ** 3, 12.5)

        monkeypatch.setattr(system_routes.psutil, "disk_usage", usage)

        pools = system_routes._storage_pools()
        assert [p["mount"] for p in pools] == ["/"]

    def test_a_pool_over_the_warn_threshold_is_unhealthy(self, monkeypatch):
        parts = [Partition("/dev/disk1", "/", "apfs", "rw")]
        monkeypatch.setattr(system_routes.psutil, "disk_partitions", lambda all=False: parts)
        monkeypatch.setattr(
            system_routes.psutil, "disk_usage",
            lambda mount: Usage(1024 ** 4, 1024 ** 4, 0, 97.0),
        )
        assert system_routes._storage_pools()[0]["healthy"] is False


class TestHumanizeUptime:

    @pytest.mark.parametrize("seconds,expected", [
        (30, "1 minute"),
        (60, "1 minute"),
        (600, "10 minutes"),
        (3600, "1 hour"),
        (7200, "2 hours"),
        (86400, "1 day"),
        (18 * 86400, "18 days"),
    ])
    def test_single_largest_unit(self, seconds, expected):
        assert system_routes._humanize_uptime(seconds) == expected


class TestChosenName:
    """Onboarding asks "What should I call this computer?" — that is the name."""

    def test_the_onboarding_name_wins_over_the_hostname(self, monkeypatch):
        monkeypatch.setattr(system_routes, "_chosen_name", lambda: "Macky-Mac")
        assert system_routes._display_name("Erics-Mac-Studio.local") == "Macky-Mac"

    def test_hostname_is_the_fallback_when_onboarding_never_ran(self, monkeypatch):
        monkeypatch.setattr(system_routes, "_chosen_name", lambda: None)
        assert system_routes._display_name("workstation") == "workstation"

    def test_app_name_is_the_last_resort(self, monkeypatch):
        monkeypatch.setattr(system_routes, "_chosen_name", lambda: None)
        assert system_routes._display_name("") == "Halbert"

    @pytest.mark.parametrize("hostname,expected", [
        ("Erics-Mac-Studio.local", "Erics-Mac-Studio"),
        ("box.lan", "box"),
        ("nas.home", "nas"),
        ("server.localdomain", "server"),
        ("plain", "plain"),
        ("has.dots.inside", "has.dots.inside"),
    ])
    def test_plumbing_suffixes_are_stripped_from_a_fallback_hostname(self, hostname, expected):
        assert system_routes._short_hostname(hostname) == expected

    def test_a_blank_or_whitespace_name_is_not_a_name(self, monkeypatch, tmp_path):
        (tmp_path / "preferences.yml").write_text("ai_name: '   '\n")
        monkeypatch.setattr(
            "halbert_core.utils.platform.get_config_dir", lambda: tmp_path
        )
        assert system_routes._chosen_name() is None

    def test_unreadable_preferences_are_not_fatal(self, monkeypatch, tmp_path):
        (tmp_path / "preferences.yml").write_text("{{ not: valid: yaml")
        monkeypatch.setattr(
            "halbert_core.utils.platform.get_config_dir", lambda: tmp_path
        )
        assert system_routes._chosen_name() is None

    async def test_identity_introduces_itself_by_the_chosen_name(self, monkeypatch):
        monkeypatch.setattr(system_routes, "_chosen_name", lambda: "Macky-Mac")

        identity = await system_routes.get_host_identity()

        assert identity["display_name"] == "Macky-Mac"
        assert identity["first_person"].startswith("I am Macky-Mac (")
        # The hostname is still reported — as a fact, not as the identity.
        assert identity["hostname"]
        assert identity["hostname"] not in identity["first_person"]


class TestCpuPercent:

    def test_first_sample_on_a_thread_is_not_the_meaningless_zero(self, monkeypatch):
        """psutil's interval=None form has no previous sample to compare to."""
        calls = []

        def fake_cpu_percent(interval=None):
            calls.append(interval)
            return 0.0 if interval is None else 37.5

        monkeypatch.setattr(system_routes.psutil, "cpu_percent", fake_cpu_percent)
        monkeypatch.setattr(system_routes, "_cpu_primed_threads", set())

        first = system_routes._cpu_percent()
        second = system_routes._cpu_percent()

        # First call takes a real (blocking) sample; later calls are free.
        assert calls[0] == system_routes._CPU_PRIME_SECONDS
        assert calls[1] is None
        assert first == 37.5
        assert second == 0.0

    async def test_identity_takes_a_real_sample_on_its_first_call(self, monkeypatch):
        """An idle machine can legitimately read 0%, so assert the mechanism."""
        intervals = []

        def fake_cpu_percent(interval=None):
            intervals.append(interval)
            return 12.5

        monkeypatch.setattr(system_routes.psutil, "cpu_percent", fake_cpu_percent)
        monkeypatch.setattr(system_routes, "_cpu_primed_threads", set())

        identity = await system_routes.get_host_identity()

        assert intervals[0] == system_routes._CPU_PRIME_SECONDS
        assert identity["cpu"]["percent"] == 12.5


class TestIdentityPayload:

    async def test_identity_is_answerable_with_no_scan(self):
        identity = await system_routes.get_host_identity()

        assert identity["hostname"]
        assert identity["os"]["kernel"]
        assert identity["os"]["platform"]
        assert identity["cpu"]["cores"] >= 1
        assert identity["memory"]["total_gb"] > 0
        assert identity["uptime"]["seconds"] >= 0
        assert identity["uptime"]["human"]
        assert identity["storage"]["total"] >= 1
        assert identity["storage"]["healthy"] <= identity["storage"]["total"]
        assert isinstance(identity["all_healthy"], bool)

    async def test_first_person_line_names_the_host(self):
        identity = await system_routes.get_host_identity()
        line = identity["first_person"]

        assert line.startswith(f"I am {identity['display_name']}")
        assert identity["os"]["kernel"] in line
        assert identity["uptime"]["human"] in line

    async def test_first_person_reports_strain_when_a_pool_is_full(self, monkeypatch):
        monkeypatch.setattr(system_routes, "_storage_pools", lambda: [
            {"mount": "/", "device": "d1", "fstype": "ext4",
             "total_gb": 500.0, "used_percent": 40.0, "healthy": True},
            {"mount": "/data", "device": "d2", "fstype": "ext4",
             "total_gb": 2000.0, "used_percent": 96.0, "healthy": False},
        ])

        identity = await system_routes.get_host_identity()

        assert identity["all_healthy"] is False
        assert "1 of 2 storage pools healthy" in identity["first_person"]
        assert "/data" in identity["first_person"]
