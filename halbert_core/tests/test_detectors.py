# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for findings detectors: fstab_phantom, permissions_hygiene,
dropin_conflicts."""

import os
import shutil
import tempfile

import pytest

from halbert_core.findings.detectors.fstab_phantom import (
    FstabPhantomDetector,
    _mount_unit_name,
)
from halbert_core.findings.detectors.permissions_hygiene import (
    PermissionsHygieneDetector,
)
from halbert_core.findings.detectors.dropin_conflicts import DropinConflictDetector


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _write_fstab(tmpdir, lines):
    path = os.path.join(tmpdir, "fstab")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


# A UUID that does not exist on any system
_PHANTOM = "UUID=00000000-0000-0000-0000-000000000000"


class TestFstabPhantom:
    def test_noauto_not_boot_blocking(self, tmpdir):
        fstab = _write_fstab(tmpdir, [f"{_PHANTOM} /mnt/data ext4 noauto 0 2"])
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "info"
        assert "skipped" in f.why_care.lower()
        assert "hang" not in f.why_care.lower()

    def test_nofail_not_boot_blocking(self, tmpdir):
        fstab = _write_fstab(tmpdir, [f"{_PHANTOM} /mnt/data ext4 defaults,nofail 0 2"])
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert findings[0].severity == "info"
        assert "skipped" in findings[0].why_care.lower()

    def test_automount_not_boot_blocking(self, tmpdir):
        fstab = _write_fstab(
            tmpdir, [f"{_PHANTOM} /mnt/data ext4 x-systemd.automount 0 2"]
        )
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert findings[0].severity == "info"

    def test_blocking_entry_uses_boot_hang_language(self, tmpdir):
        fstab = _write_fstab(tmpdir, [f"{_PHANTOM} /mnt/data ext4 defaults 0 2"])
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "hang" in findings[0].why_care.lower()

    def test_critical_mount_points_still_critical(self, tmpdir):
        fstab = _write_fstab(tmpdir, [f"{_PHANTOM} /boot ext4 defaults 0 2"])
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert findings[0].severity == "critical"

    def test_existing_device_no_finding(self, tmpdir):
        fstab = _write_fstab(tmpdir, ["tmpfs /tmp tmpfs defaults 0 0"])
        assert FstabPhantomDetector(fstab_path=fstab).detect() == []

    def test_mount_unit_escaping(self, tmpdir):
        fstab = _write_fstab(tmpdir, [f"{_PHANTOM} /mnt/data ext4 defaults 0 2"])
        findings = FstabPhantomDetector(fstab_path=fstab).detect()
        assert findings[0].affected_services == ["mnt-data.mount"]

    def test_mount_unit_name_helper(self):
        assert _mount_unit_name("/mnt/data") == "mnt-data.mount"
        assert _mount_unit_name("/boot/efi") == "boot-efi.mount"
        assert _mount_unit_name("/") == "-.mount"
        assert _mount_unit_name("/mnt/my-data") == "mnt-my\\x2ddata.mount"


class TestPermissionsHygiene:
    def _ssh_home(self, tmpdir, config_mode):
        ssh_dir = os.path.join(tmpdir, ".ssh")
        os.makedirs(ssh_dir, exist_ok=True)
        os.chmod(ssh_dir, 0o700)
        cfg = os.path.join(ssh_dir, "config")
        with open(cfg, "w") as f:
            f.write("Host example\n")
        os.chmod(cfg, config_mode)
        return tmpdir

    def _etc_empty(self, tmpdir):
        etc = os.path.join(tmpdir, "etc-empty")
        os.makedirs(etc, exist_ok=True)
        return etc

    def _config_findings(self, tmpdir, mode):
        self._ssh_home(tmpdir, mode)
        det = PermissionsHygieneDetector(
            home_dir=tmpdir, etc_dir=self._etc_empty(tmpdir)
        )
        return [f for f in det.detect() if f.affected_paths
                and f.affected_paths[0].endswith("config")]

    def test_ssh_config_600_accepted(self, tmpdir):
        assert self._config_findings(tmpdir, 0o600) == []

    def test_ssh_config_644_accepted(self, tmpdir):
        assert self._config_findings(tmpdir, 0o644) == []

    def test_ssh_config_664_flagged(self, tmpdir):
        findings = self._config_findings(tmpdir, 0o664)
        assert len(findings) == 1
        assert findings[0].detector == "permissions_hygiene"


class TestDropinConflicts:
    def test_additive_directives_no_false_positive(self, tmpdir):
        base = os.path.join(tmpdir, "systemd", "system", "svc.service")
        os.makedirs(os.path.dirname(base), exist_ok=True)
        with open(base, "w") as f:
            f.write(
                "[Unit]\nAfter=network.target\n\n"
                "[Service]\nEnvironment=FOO=1\nMemoryMax=1G\nExecStart=/bin/run\n"
            )
        dropin_dir = os.path.join(tmpdir, "systemd", "system", "svc.service.d")
        os.makedirs(dropin_dir, exist_ok=True)
        with open(os.path.join(dropin_dir, "10.conf"), "w") as f:
            f.write(
                "[Unit]\nAfter=remote-fs.target\n\n"
                "[Service]\nEnvironment=BAR=2\n"
            )

        findings = DropinConflictDetector(config_dir=tmpdir).detect()
        keys = [f.title for f in findings]
        assert not any("after" in t.lower() for t in keys)
        assert not any("environment" in t.lower() for t in keys)

    def test_override_directive_still_flagged(self, tmpdir):
        base = os.path.join(tmpdir, "systemd", "system", "svc.service")
        os.makedirs(os.path.dirname(base), exist_ok=True)
        with open(base, "w") as f:
            f.write("[Service]\nMemoryMax=2G\nExecStart=/bin/run\n")
        dropin_dir = os.path.join(tmpdir, "systemd", "system", "svc.service.d")
        os.makedirs(dropin_dir, exist_ok=True)
        with open(os.path.join(dropin_dir, "10.conf"), "w") as f:
            f.write("[Service]\nMemoryMax=1G\n")

        findings = DropinConflictDetector(config_dir=tmpdir).detect()
        assert any("memorymax" in f.title for f in findings)
