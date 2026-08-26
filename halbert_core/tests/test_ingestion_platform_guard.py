"""Tests for the journald platform guard in IngestionService (B9)."""
import logging
import shutil
import sys

import halbert_core.ingestion.service as svc
import halbert_core.utils.platform as plat
from halbert_core.ingestion.service import IngestionService, journald_available


def test_journald_available_false_on_non_linux(monkeypatch):
    monkeypatch.setattr(plat, "is_linux", lambda: False)
    assert journald_available() is False


def test_journald_available_requires_journalctl(monkeypatch):
    monkeypatch.setattr(plat, "is_linux", lambda: True)
    monkeypatch.setitem(sys.modules, "systemd", None)
    monkeypatch.setitem(sys.modules, "systemd.journal", None)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert journald_available() is False
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/journalctl")
    assert journald_available() is True


def test_start_skips_journald_thread_when_unavailable(caplog, monkeypatch, tmp_path):
    cfg = tmp_path / "ingestion.yml"
    cfg.write_text("sources:\n  hwmon:\n    enabled: false\n  journald:\n    enabled: true\n")
    monkeypatch.setattr(IngestionService, "_find_config", lambda self: str(cfg))
    monkeypatch.setattr(IngestionService, "_run_hwmon", lambda self: None)
    monkeypatch.setattr(svc, "journald_available", lambda: False)
    monkeypatch.setattr(IngestionService, "_instance", None)

    service = IngestionService()
    with caplog.at_level(logging.DEBUG, logger="halbert_core.ingestion.service"):
        assert service.start() is True
        service.stop()

    assert service._journald_thread is None
    assert service.stats.errors == 0
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and "Journald ingestion error" in r.getMessage()]
    assert [r for r in caplog.records if r.levelno == logging.DEBUG and "journald ingestion skipped" in r.getMessage()]


def test_run_journald_returns_early_when_unavailable(caplog, monkeypatch, tmp_path):
    cfg = tmp_path / "ingestion.yml"
    cfg.write_text("sources:\n  journald:\n    enabled: true\n")
    monkeypatch.setattr(IngestionService, "_find_config", lambda self: str(cfg))
    monkeypatch.setattr(svc, "journald_available", lambda: False)
    monkeypatch.setattr(IngestionService, "_instance", None)
    service = IngestionService()
    with caplog.at_level(logging.DEBUG, logger="halbert_core.ingestion.service"):
        service._run_journald()
    assert service.stats.errors == 0
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
