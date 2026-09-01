# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task P2: the screen power daemon — backlight + DPMS, best-effort.

Covers ``halbert_core.system.display_power`` (the controller and the sysfs
discovery helper the laptop scanner now shares), the ``GET/POST
/api/system/display`` routes, and the P1 idle-report contract. Everything
runs against a fake sysfs tree in ``tmp_path`` with a recording xset runner
— no test requires Linux hardware, X11, or a real backlight.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes.system import router as system_router
from halbert_core.system import display_power as dp


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _RecordingRunner:
    """xset stand-in: records commanded argv, never touches a display."""

    def __init__(self, fail: bool = False):
        self.commands: List[List[str]] = []
        self._fail = fail

    def __call__(self, cmd):
        self.commands.append(list(cmd))
        if self._fail:
            raise RuntimeError("xset exploded")


def _fake_sysfs(
    tmp_path: Path,
    *,
    name: str = "acpi_video0",
    brightness: int = 70,
    max_brightness: int = 100,
) -> Path:
    """A fake /sys/class/backlight with one readable device."""
    base = tmp_path / "backlight"
    dev = base / name
    dev.mkdir(parents=True, exist_ok=True)
    (dev / "brightness").write_text(str(brightness))
    (dev / "max_brightness").write_text(str(max_brightness))
    return base


def _controller(
    tmp_path: Path,
    *,
    brightness: int = 70,
    max_brightness: int = 100,
    display=":0",
    xset=True,
    runner=None,
    base=None,
):
    """A controller pointed at a fake sysfs tree and a recording xset.

    Returns ``(controller, runner)`` so tests can assert on both the
    backlight file and the DPMS commands.
    """
    if base is None:
        base = _fake_sysfs(
            tmp_path, brightness=brightness, max_brightness=max_brightness
        )
    if runner is None:
        runner = _RecordingRunner()
    environ = {"DISPLAY": display} if display else {}
    controller = dp.DisplayPowerController(
        backlight_base=base,
        environ=environ,
        which=lambda name: "/usr/bin/xset" if (name == "xset" and xset) else None,
        run=runner,
    )
    return controller, runner


def _brightness_file(controller) -> Path:
    device = controller._writable_device()
    assert device is not None
    return device[1] / "brightness"


# ---------------------------------------------------------------------------
# Shared sysfs discovery (used by the writer and the laptop scanner)
# ---------------------------------------------------------------------------

class TestIterBacklightInterfaces:

    def test_yields_readable_devices_in_name_order(self, tmp_path):
        base = _fake_sysfs(tmp_path, name="b_panel", brightness=42, max_brightness=100)
        _fake_sysfs(tmp_path, name="a_ambient", brightness=7, max_brightness=10)
        # Not a device: a plain file directly under the root.
        (base / "README").write_text("not a device")
        # A directory missing max_brightness is skipped.
        incomplete = base / "c_broken"
        incomplete.mkdir()
        (incomplete / "brightness").write_text("5")
        # A device with garbage contents is skipped, not fatal.
        garbage = base / "d_garbage"
        garbage.mkdir()
        (garbage / "brightness").write_text("not-a-number")
        (garbage / "max_brightness").write_text("100")

        found = list(dp.iter_backlight_interfaces(base))

        assert [f[0] for f in found] == ["a_ambient", "b_panel"]
        assert found[0][2:] == (7, 10)
        assert found[1][2:] == (42, 100)
        assert found[0][1] == base / "a_ambient"

    def test_missing_base_yields_nothing(self, tmp_path):
        assert list(dp.iter_backlight_interfaces(tmp_path / "nope")) == []

    def test_zero_max_brightness_is_skipped(self, tmp_path):
        base = _fake_sysfs(tmp_path, brightness=5, max_brightness=0)
        assert list(dp.iter_backlight_interfaces(base)) == []


# ---------------------------------------------------------------------------
# Controller: status, direct control, DPMS
# ---------------------------------------------------------------------------

class TestDisplayPowerController:

    def test_status_reads_percent_and_availability(self, tmp_path):
        controller, runner = _controller(tmp_path)
        assert runner.commands == []

        status = controller.status()

        assert status["backlight"] == 70
        assert status["blanked"] is False
        assert status["available"] == {
            "backlight": True,
            "backlight_device": "acpi_video0",
            "dpms": True,
        }

    def test_set_backlight_scales_to_device_max(self, tmp_path):
        base = _fake_sysfs(tmp_path, brightness=128, max_brightness=255)
        controller, _ = _controller(tmp_path, base=base)

        controller.set_backlight(40)

        assert _brightness_file(controller).read_text().strip() == "102"
        assert controller.status()["backlight"] == 40

    def test_set_backlight_clamps_out_of_range(self, tmp_path):
        controller, _ = _controller(tmp_path, max_brightness=255)

        controller.set_backlight(150)
        assert _brightness_file(controller).read_text().strip() == "255"
        controller.set_backlight(-3)
        assert _brightness_file(controller).read_text().strip() == "0"

    def test_set_blanked_forces_dpms_and_tracks_state(self, tmp_path):
        controller, runner = _controller(tmp_path)

        controller.set_blanked(True)
        assert runner.commands == [["xset", "dpms", "force", "off"]]
        assert controller.status()["blanked"] is True

        controller.set_blanked(False)
        assert runner.commands[-1] == ["xset", "dpms", "force", "on"]
        assert controller.status()["blanked"] is False

    def test_dpms_unavailable_without_display_or_binary(self, tmp_path):
        no_display, runner_a = _controller(tmp_path, display=None)
        assert no_display.status()["available"]["dpms"] is False
        no_display.set_blanked(True)
        assert runner_a.commands == []
        assert no_display.status()["blanked"] is False

        no_xset, runner_b = _controller(tmp_path, xset=False)
        assert no_xset.status()["available"]["dpms"] is False
        no_xset.set_blanked(True)
        assert runner_b.commands == []
        assert no_xset.status()["blanked"] is False

    def test_xset_failure_is_swallowed(self, tmp_path):
        controller, _ = _controller(tmp_path, runner=_RecordingRunner(fail=True))

        controller.set_blanked(True)  # must not raise
        assert controller.status()["blanked"] is False

    def test_nonzero_xset_exit_is_not_a_blank(self, tmp_path):
        # DISPLAY set + xset installed but no X server behind it (e.g.
        # XQuartz not running): the command runs, fails, and the tracked
        # state must not claim the screen blanked.
        commands: List[List[str]] = []

        class _FailedExit:
            returncode = 1

            def __call__(self, cmd):
                commands.append(list(cmd))
                return self

        controller, _ = _controller(tmp_path, runner=_FailedExit())

        controller.set_blanked(True)
        assert commands == [["xset", "dpms", "force", "off"]]
        assert controller.status()["blanked"] is False

        controller.report_idle(600)  # tier 2 still dims the backlight
        assert _brightness_file(controller).read_text().strip() == "0"
        assert controller.status()["blanked"] is False

    def test_missing_hardware_is_a_full_noop(self, tmp_path):
        controller, runner = _controller(
            tmp_path, base=tmp_path / "no-sysfs", display=None, xset=False
        )

        status = controller.status()
        assert status == {
            "backlight": None,
            "blanked": False,
            "available": {"backlight": False, "backlight_device": None, "dpms": False},
        }
        # None of these may raise, and none may touch a runner.
        controller.report_idle(30)
        controller.report_idle(600)
        controller.wake()
        controller.set_backlight(50)
        controller.set_blanked(True)
        assert runner.commands == []

    def test_write_failure_is_swallowed(self, tmp_path):
        base = _fake_sysfs(tmp_path)
        controller, _ = _controller(tmp_path, base=base)
        assert controller.status()["backlight"] == 70  # discovered

        # Break the device between discovery and the next write.
        brightness_file = base / "acpi_video0" / "brightness"
        brightness_file.unlink()
        brightness_file.mkdir()

        controller.set_backlight(50)  # must not raise
        assert controller.status()["backlight"] is None


# ---------------------------------------------------------------------------
# P1 idle-report mapping — thresholds, never equality
# ---------------------------------------------------------------------------

class TestIdleReportMapping:

    def test_thirty_and_thirty_one_both_dim_to_tier1(self, tmp_path):
        for idle_seconds in (30, 31):
            controller, runner = _controller(tmp_path)
            controller.report_idle(idle_seconds)
            assert _brightness_file(controller).read_text().strip() == "10", (
                f"idle_seconds={idle_seconds}"
            )
            # Tier 1 is a dim, not a blank: no DPMS command.
            assert runner.commands == []

    def test_below_thirty_is_a_noop(self, tmp_path):
        controller, runner = _controller(tmp_path)

        controller.report_idle(29)

        assert _brightness_file(controller).read_text().strip() == "70"
        assert runner.commands == []

    def test_six_hundred_and_six_hundred_one_blank_and_force_dpms_off(
        self, tmp_path
    ):
        for idle_seconds in (600, 601):
            controller, runner = _controller(tmp_path)
            controller.report_idle(idle_seconds)
            assert _brightness_file(controller).read_text().strip() == "0", (
                f"idle_seconds={idle_seconds}"
            )
            assert runner.commands == [["xset", "dpms", "force", "off"]]
            assert controller.status()["blanked"] is True

    def test_repeated_tier_reports_do_not_re_capture_baseline(self, tmp_path):
        controller, runner = _controller(tmp_path)

        controller.report_idle(30)   # -> 10, baseline 70 captured
        controller.report_idle(600)  # -> 0, baseline must NOT become 10
        controller.report_idle(601)  # already tier 2: no further action

        assert _brightness_file(controller).read_text().strip() == "0"
        assert runner.commands == [["xset", "dpms", "force", "off"]]

        controller.report_idle(0)  # wake restores the user's real level

        assert _brightness_file(controller).read_text().strip() == "70"
        assert runner.commands[-1] == ["xset", "dpms", "force", "on"]
        assert controller.status()["blanked"] is False

    def test_tier2_without_tier1_still_restores_the_real_level(self, tmp_path):
        controller, _ = _controller(tmp_path)

        controller.report_idle(600)
        controller.report_idle(0)

        assert _brightness_file(controller).read_text().strip() == "70"

    def test_tier1_never_brightens_an_already_dim_screen(self, tmp_path):
        controller, _ = _controller(tmp_path, brightness=4)

        controller.report_idle(30)

        # The user keeps this screen at 4% — an idle report must not raise
        # it to the tier-1 target.
        assert _brightness_file(controller).read_text().strip() == "4"

        controller.report_idle(0)
        assert _brightness_file(controller).read_text().strip() == "4"

    def test_zero_report_when_awake_is_a_noop(self, tmp_path):
        controller, runner = _controller(tmp_path)

        controller.report_idle(0)

        assert _brightness_file(controller).read_text().strip() == "70"
        assert runner.commands == []

    def test_wake_restores_full_when_no_baseline_was_capturable(
        self, tmp_path, monkeypatch
    ):
        controller, _ = _controller(tmp_path)
        # The tier arrived while the backlight read failed — no baseline.
        monkeypatch.setattr(controller, "_read_percent", lambda: None)
        controller.report_idle(30)
        monkeypatch.undo()

        controller.report_idle(0)

        # Full-on rather than staying dark: better a lit screen than a
        # silent black one.
        assert _brightness_file(controller).read_text().strip() == "100"

    def test_non_numeric_idle_reports_are_noops(self, tmp_path):
        controller, runner = _controller(tmp_path)

        controller.report_idle("30")
        controller.report_idle(None)
        controller.report_idle([600])

        assert _brightness_file(controller).read_text().strip() == "70"
        assert runner.commands == []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pytest.fixture
def display_env(monkeypatch, tmp_path):
    """Route handlers drive a fake-sysfs controller, never the real one."""
    controller, runner = _controller(tmp_path)
    monkeypatch.setattr(dp, "get_display_power", lambda: controller)
    return controller, runner


@pytest.fixture
def client():
    """Fresh app mounting the system router exactly as app.py mounts it."""
    app = FastAPI()
    app.include_router(system_router, prefix="/api")
    return TestClient(app)


class TestDisplayRoutes:

    def test_get_returns_current_state(self, client, display_env):
        r = client.get("/api/system/display")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["backlight"] == 70
        assert body["blanked"] is False
        assert body["available"]["backlight"] is True
        assert body["available"]["dpms"] is True

    def test_post_idle_tier1_dims_backlight(self, client, display_env):
        r = client.post("/api/system/display", json={"idle_seconds": 30})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 10

    def test_post_idle_tier2_blanks_and_dpms_off(self, client, display_env):
        controller, runner = display_env

        r = client.post("/api/system/display", json={"idle_seconds": 601})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 0
        assert r.json()["blanked"] is True
        assert runner.commands == [["xset", "dpms", "force", "off"]]

    def test_post_idle_zero_wakes(self, client, display_env):
        client.post("/api/system/display", json={"idle_seconds": 30})
        client.post("/api/system/display", json={"idle_seconds": 600})

        r = client.post("/api/system/display", json={"idle_seconds": 0})

        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 70
        assert r.json()["blanked"] is False

    def test_post_non_numeric_idle_is_a_noop_not_an_error(self, client, display_env):
        r = client.post("/api/system/display", json={"idle_seconds": "thirty"})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 70

    def test_post_boolean_idle_is_a_noop(self, client, display_env):
        r = client.post("/api/system/display", json={"idle_seconds": True})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 70

    def test_post_direct_backlight(self, client, display_env):
        r = client.post("/api/system/display", json={"backlight": 42})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 42

    def test_post_out_of_range_backlight_is_ignored(self, client, display_env):
        r = client.post("/api/system/display", json={"backlight": 250})
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 70

    def test_post_direct_blank(self, client, display_env):
        controller, runner = display_env

        r = client.post("/api/system/display", json={"blanked": True})
        assert r.status_code == 200, r.text
        assert r.json()["blanked"] is True
        assert runner.commands == [["xset", "dpms", "force", "off"]]

    def test_post_unknown_shape_is_a_noop(self, client, display_env):
        for body in ({}, {"foo": 1}, {"backlight": "bright"}, {"blanked": "yes"}):
            r = client.post("/api/system/display", json=body)
            assert r.status_code == 200, (body, r.text)
            assert r.json()["backlight"] == 70
            assert r.json()["blanked"] is False

    def test_post_malformed_json_is_a_noop(self, client, display_env):
        r = client.post(
            "/api/system/display", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] == 70

    def test_get_never_500s_when_status_raises(self, client, monkeypatch, display_env):
        def _boom():
            raise RuntimeError("sysfs fell over")

        monkeypatch.setattr(dp, "status", _boom)
        r = client.get("/api/system/display")
        assert r.status_code == 200, r.text
        assert r.json()["backlight"] is None
        assert r.json()["blanked"] is False


# ---------------------------------------------------------------------------
# Laptop scanner reuse — the sysfs walk lives in one place
# ---------------------------------------------------------------------------

class TestLaptopScannerBacklightReuse:

    def test_scan_backlight_builds_discoveries_from_shared_helper(
        self, tmp_path, monkeypatch
    ):
        from halbert_core.discovery.scanners.laptop import LaptopScanner

        base = _fake_sysfs(tmp_path, brightness=42, max_brightness=200)
        monkeypatch.setattr(dp, "DEFAULT_BACKLIGHT_BASE", base)

        discoveries = LaptopScanner()._scan_backlight()

        assert len(discoveries) == 1
        assert discoveries[0].name == "backlight-acpi_video0"
        assert discoveries[0].source == str(base / "acpi_video0")
        assert discoveries[0].data["percent"] == 21
        assert discoveries[0].data["max_brightness"] == 200
