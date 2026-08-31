# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the SecurityConfig dataclass and being config integration."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

import pytest
import yaml

try:
    import fcntl
except ImportError:  # Windows — the flock tests are skipped there
    fcntl = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.being_config import (
    BeingConfig,
    SecurityConfig,
    load_being_config,
    save_being_config,
    being_config_lock,
    update_being_config,
    VALID_OPERATIONAL_TIERS,
    VALID_SECRET_TIERS,
)


class TestSecurityConfigDefaults:
    def test_defaults(self):
        s = SecurityConfig()
        assert s.operational_tier == "cloud_ok"
        assert s.secret_tier == "local_only"
        assert "/etc/hosts" in s.public_files
        assert s.extra_secret_keys == []

    def test_validate_ok(self):
        s = SecurityConfig()
        s.validate()  # should not raise

    def test_validate_bad_operational_tier(self):
        s = SecurityConfig(operational_tier="bogus")
        with pytest.raises(ValueError, match="operational_tier"):
            s.validate()

    def test_validate_bad_secret_tier(self):
        s = SecurityConfig(secret_tier="bogus")
        with pytest.raises(ValueError, match="secret_tier"):
            s.validate()

    def test_to_dict(self):
        s = SecurityConfig(operational_tier="local_only", extra_secret_keys=["serial"])
        d = s.to_dict()
        assert d["operational_tier"] == "local_only"
        assert d["extra_secret_keys"] == ["serial"]

    def test_from_dict(self):
        d = {
            "operational_tier": "redact",
            "secret_tier": "cloud_ok_acknowledged",
            "public_files": ["/etc/myapp"],
            "extra_secret_keys": ["license"],
        }
        s = SecurityConfig.from_dict(d)
        assert s.operational_tier == "redact"
        assert s.secret_tier == "cloud_ok_acknowledged"
        assert s.public_files == ["/etc/myapp"]
        assert s.extra_secret_keys == ["license"]

    def test_from_dict_ignores_unknown_keys(self):
        d = {"operational_tier": "local_only", "bogus": "value"}
        s = SecurityConfig.from_dict(d)
        assert s.operational_tier == "local_only"


class TestBeingConfigIntegration:
    def test_default_security(self):
        bc = BeingConfig()
        assert isinstance(bc.security, SecurityConfig)
        assert bc.security.operational_tier == "cloud_ok"

    def test_from_dict_with_security(self):
        d = {
            "voice": "first_person",
            "security": {
                "operational_tier": "local_only",
                "secret_tier": "cloud_ok_acknowledged",
                "public_files": ["/etc/myapp"],
                "extra_secret_keys": ["serial"],
            },
        }
        bc = BeingConfig.from_dict(d)
        assert bc.security.operational_tier == "local_only"
        assert bc.security.secret_tier == "cloud_ok_acknowledged"
        assert bc.security.public_files == ["/etc/myapp"]
        assert bc.security.extra_secret_keys == ["serial"]

    def test_from_dict_without_security(self):
        d = {"voice": "hybrid"}
        bc = BeingConfig.from_dict(d)
        assert bc.security.operational_tier == "cloud_ok"  # default

    def test_to_dict_includes_security(self):
        bc = BeingConfig()
        bc.security.operational_tier = "redact"
        d = bc.to_dict()
        assert "security" in d
        assert d["security"]["operational_tier"] == "redact"

    def test_validate_propagates_to_security(self):
        bc = BeingConfig()
        bc.security.operational_tier = "bogus"
        with pytest.raises(ValueError, match="operational_tier"):
            bc.validate()

    def test_valid_security_passes_validation(self):
        bc = BeingConfig()
        bc.security.operational_tier = "local_only"
        bc.security.secret_tier = "cloud_ok_acknowledged"
        bc.validate()  # should not raise


class TestLoadSaveWithSecurity:
    def test_save_and_load_security(self, tmp_path):
        bc = BeingConfig()
        bc.security.operational_tier = "local_only"
        bc.security.secret_tier = "cloud_ok_acknowledged"
        bc.security.extra_secret_keys = ["serial", "license"]

        path = str(tmp_path / "being.yml")
        save_being_config(bc, path)

        # Verify the YAML has the security section
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert "security" in raw
        assert raw["security"]["operational_tier"] == "local_only"
        assert raw["security"]["secret_tier"] == "cloud_ok_acknowledged"
        assert "serial" in raw["security"]["extra_secret_keys"]

        # Load it back
        loaded = load_being_config(path)
        assert loaded.security.operational_tier == "local_only"
        assert loaded.security.secret_tier == "cloud_ok_acknowledged"
        assert loaded.security.extra_secret_keys == ["serial", "license"]

    def test_load_without_security_section(self, tmp_path):
        """A being.yml without a security section should use defaults."""
        path = str(tmp_path / "being.yml")
        with open(path, "w") as f:
            yaml.dump({"voice": "hybrid", "proactivity": "balanced"}, f)

        loaded = load_being_config(path)
        assert loaded.security.operational_tier == "cloud_ok"
        assert loaded.security.secret_tier == "local_only"


class TestVolatileUnlock:
    """The 'until restart' escape hatch relocks once per process, not per load."""

    def _write_volatile_unlock(self, path):
        with open(path, "w") as f:
            yaml.dump({"security": {
                "secret_tier": "cloud_ok_acknowledged",
                "volatile_unlock": True,
            }}, f)

    def test_first_load_relocks(self, tmp_path):
        """A stale volatile unlock from a previous process relocks on load."""
        path = str(tmp_path / "being.yml")
        self._write_volatile_unlock(path)

        loaded = load_being_config(path)
        assert loaded.security.secret_tier == "local_only"
        assert loaded.security.volatile_unlock is False

        # And the relock is persisted, so later processes see clean state
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["security"]["secret_tier"] == "local_only"
        assert raw["security"].get("volatile_unlock") in (None, False)

    def test_second_load_same_process_does_not_relock(self, tmp_path):
        """The 'until restart' unlock must survive loads within one process.

        Regression: load_being_config is called per request (dashboard) and
        per tool call (MCP), so relocking on every load made the volatile
        option self-defeating — the very next read after unlocking relocked.
        """
        path = str(tmp_path / "being.yml")
        # Simulate: this process already did its first-load check...
        with open(path, "w") as f:
            yaml.dump({"voice": "hybrid"}, f)
        load_being_config(path)  # benign file → guard consumed
        # ...then the user unlocked 'until restart'
        self._write_volatile_unlock(path)

        loaded = load_being_config(path)
        assert loaded.security.secret_tier == "cloud_ok_acknowledged"
        assert loaded.security.volatile_unlock is True

        # And the file on disk still carries the marker for the NEXT process
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["security"]["volatile_unlock"] is True

    def test_new_process_still_relocks(self, tmp_path):
        """A fresh path (i.e. a fresh process's first load) relocks."""
        path = str(tmp_path / "being.yml")
        self._write_volatile_unlock(path)

        loaded = load_being_config(path)
        assert loaded.security.secret_tier == "local_only"


@pytest.mark.skipif(os.name != "posix", reason="flock cross-process tests need fcntl")
class TestCrossProcessLock:
    """REV-01 F4: an advisory flock serializes cross-process writes to being.yml.

    The dashboard and the MCP server are separate processes that both do
    load-modify-save on being.yml. Without a cross-process lock, an MCP
    ``set_autonomy_level`` save can persist a stale object and silently
    revert a UI relock. Each test here holds the flock from outside —
    exactly as another process would — and verifies the lock is real.

    The lock file lives beside being.yml (``<being.yml>.lock``), matching
    the platform split of ``model/client.py``'s ``llm_advisory_lock``
    (fcntl.flock on POSIX, lock-free fallback on Windows).
    """

    LOCK_WAIT_S = 0.4       # how long to let the background thread block
    JOIN_WAIT_S = 5.0       # generous join timeout

    @staticmethod
    def _lock_file(path):
        return path + ".lock"

    def _hold_external_lock(self, path):
        """Acquire the config's flock as an unrelated process would."""
        fd = os.open(self._lock_file(path), os.O_CREAT | os.O_WRONLY, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @staticmethod
    def _release_external_lock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def _write_yaml(self, path, data):
        with open(path, "w") as f:
            yaml.dump(data, f)

    def test_save_creates_lock_file_beside_config(self, tmp_path):
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(), path)
        assert os.path.exists(self._lock_file(path))

    def test_load_blocks_until_external_lock_released(self, tmp_path):
        """A load must not read while another process holds the lock."""
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(voice="first_person"), path)

        fd = self._hold_external_lock(path)
        done = threading.Event()
        result = {}
        try:
            t = threading.Thread(
                target=lambda: result.__setitem__("cfg", load_being_config(path)) or done.set()
            )
            t.start()
            time.sleep(self.LOCK_WAIT_S)
            assert not done.is_set(), "load should block behind the external lock"

            # While blocked, the external process changes the file
            self._write_yaml(path, {"voice": "hybrid"})
            self._release_external_lock(fd)
            done.wait(self.JOIN_WAIT_S)
            t.join(self.JOIN_WAIT_S)
        finally:
            if not done.is_set():
                self._release_external_lock(fd)
        assert done.is_set()
        # The load saw the freshly written file, not a pre-lock snapshot
        assert result["cfg"].voice == "hybrid"

    def test_save_blocks_until_external_lock_released(self, tmp_path):
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(voice="first_person"), path)

        fd = self._hold_external_lock(path)
        done = threading.Event()
        try:
            t = threading.Thread(
                target=lambda: save_being_config(BeingConfig(voice="hybrid"), path) or done.set()
            )
            t.start()
            time.sleep(self.LOCK_WAIT_S)
            assert not done.is_set(), "save should block behind the external lock"
            self._release_external_lock(fd)
            done.wait(self.JOIN_WAIT_S)
            t.join(self.JOIN_WAIT_S)
        finally:
            if not done.is_set():
                self._release_external_lock(fd)
        assert done.is_set()
        with open(path) as f:
            assert yaml.safe_load(f)["voice"] == "hybrid"

    def test_update_being_config_does_not_revert_a_concurrent_relock(self, tmp_path):
        """The F4 scenario, end to end.

        An MCP-style load-modify-save (update_being_config) starts while
        the config is unlocked; the dashboard relocks it from another
        process mid-cycle. The update must load under the lock — so it
        builds on the relocked state — and its save must not restore the
        unlock.
        """
        path = str(tmp_path / "being.yml")
        unlocked = BeingConfig()
        unlocked.security.secret_tier = "cloud_ok_acknowledged"
        save_being_config(unlocked, path)

        fd = self._hold_external_lock(path)
        done = threading.Event()
        result = {}

        def mcp_set_autonomy_level():
            result["cfg"] = update_being_config(
                lambda c: setattr(c, "autonomy_level", "act"), path
            )
            done.set()

        try:
            t = threading.Thread(target=mcp_set_autonomy_level)
            t.start()
            time.sleep(self.LOCK_WAIT_S)
            assert not done.is_set(), "update should block behind the external lock"

            # The dashboard (another process) relocks while it holds the lock
            with open(path) as f:
                raw = yaml.safe_load(f)
            raw["security"]["secret_tier"] = "local_only"
            self._write_yaml(path, raw)
            self._release_external_lock(fd)
            done.wait(self.JOIN_WAIT_S)
            t.join(self.JOIN_WAIT_S)
        finally:
            if not done.is_set():
                self._release_external_lock(fd)
        assert done.is_set()

        assert result["cfg"].autonomy_level == "act"
        assert result["cfg"].security.secret_tier == "local_only"
        # Both changes survive on disk: the relock was not reverted
        with open(path) as f:
            final = yaml.safe_load(f)
        assert final["security"]["secret_tier"] == "local_only"
        assert final["autonomy_level"] == "act"

    def test_update_being_config_persists_and_returns(self, tmp_path):
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(autonomy_level="observe"), path)

        cfg = update_being_config(
            lambda c: setattr(c, "autonomy_level", "act"), path
        )
        assert cfg.autonomy_level == "act"
        assert load_being_config(path).autonomy_level == "act"

    def test_update_being_config_rejects_invalid_result(self, tmp_path):
        """A mutator that would persist an invalid config leaves the file alone."""
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(voice="first_person"), path)

        with pytest.raises(ValueError, match="Invalid voice"):
            update_being_config(lambda c: setattr(c, "voice", "bogus"), path)

        assert load_being_config(path).voice == "first_person"

    def test_lock_is_reentrant_within_the_holding_thread(self, tmp_path):
        """save/load called inside being_config_lock must not deadlock."""
        import fcntl

        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(), path)

        with being_config_lock(path) as acquired:
            assert acquired is True
            save_being_config(BeingConfig(voice="hybrid"), path)  # nested → no-op lock
        assert load_being_config(path).voice == "hybrid"

    def test_lock_timeout_fails_open(self, tmp_path):
        """The lock is advisory: on timeout callers proceed (like llm_advisory_lock)."""
        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(), path)

        fd = self._hold_external_lock(path)
        try:
            with being_config_lock(path, timeout_s=0.2) as acquired:
                assert acquired is False
        finally:
            self._release_external_lock(fd)

    def test_windows_falls_back_to_lock_free(self, tmp_path, monkeypatch):
        """No fcntl on Windows — same behavior as before the lock existed."""
        import halbert_core.config.being_config as bc
        monkeypatch.setattr(bc.platform, "system", lambda: "Windows")

        path = str(tmp_path / "being.yml")
        save_being_config(BeingConfig(voice="hybrid"), path)
        assert load_being_config(path).voice == "hybrid"
        assert not os.path.exists(self._lock_file(path))
