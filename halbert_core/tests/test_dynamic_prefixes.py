# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the dynamic prefix database — fetch and cache credential formats."""
from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.dynamic_prefixes import (
    get_dynamic_prefixes,
    get_last_fetch_time,
    clear_cache,
    _load_cache,
    _save_cache,
    _parse_formats,
    _CACHE_FILE,
    _CACHE_TTL,
)


def _mock_urlopen(status=200, body=b""):
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


_SAMPLE_FORMATS = [
    {
        "name": "test_service_token",
        "service": "TestService",
        "description": "TestService API token",
        "pattern": r"\btst_[A-Za-z0-9]{30,}\b",
        "breach_risk": "high",
        "validation_endpoint": "https://api.testservice.com/v1/me",
    },
    {
        "name": "another_service_key",
        "service": "AnotherService",
        "description": "AnotherService key",
        "pattern": r"\bask_[A-Za-z0-9]{20,}\b",
        "breach_risk": "medium",
    },
]


class TestParseFormats:
    """_parse_formats validates and compiles format entries."""

    def test_valid_formats(self):
        parsed = _parse_formats(_SAMPLE_FORMATS)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "test_service_token"
        assert parsed[0]["service"] == "TestService"
        assert parsed[0]["pattern"] is not None

    def test_invalid_regex_skipped(self):
        formats = [
            {"name": "bad", "service": "Bad", "pattern": r"[invalid("},
            {"name": "good", "service": "Good", "pattern": r"\bgood_\w+\b"},
        ]
        parsed = _parse_formats(formats)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "good"

    def test_missing_fields_skipped(self):
        formats = [
            {"name": "no_service", "pattern": r"\btest\b"},
            {"name": "no_pattern", "service": "Test"},
            {"service": "no_name", "pattern": r"\btest\b"},
        ]
        parsed = _parse_formats(formats)
        assert len(parsed) == 0

    def test_non_dict_entries_skipped(self):
        formats = ["not a dict", 42, None, _SAMPLE_FORMATS[0]]
        parsed = _parse_formats(formats)
        assert len(parsed) == 1


class TestCacheOperations:
    """Cache save/load/clear operations."""

    def test_save_and_load_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            str(tmp_path / "prefix_cache.json"),
        )
        _save_cache(_SAMPLE_FORMATS)
        loaded = _load_cache()
        assert loaded is not None
        assert "formats" in loaded
        assert len(loaded["formats"]) == 2

    def test_load_nonexistent_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            str(tmp_path / "nonexistent.json"),
        )
        assert _load_cache() is None

    def test_clear_cache(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        _save_cache(_SAMPLE_FORMATS)
        assert os.path.exists(cache_path)
        clear_cache()
        assert not os.path.exists(cache_path)

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        # Write a cache with an old timestamp
        data = {
            "_fetched_at": time.time() - _CACHE_TTL - 3600,  # expired
            "formats": _SAMPLE_FORMATS,
        }
        with open(cache_path, "w") as f:
            json.dump(data, f)
        assert _load_cache() is None

    def test_get_last_fetch_time(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        _save_cache(_SAMPLE_FORMATS)
        ts = get_last_fetch_time()
        assert ts is not None
        assert abs(ts - time.time()) < 5  # within 5 seconds

    def test_get_last_fetch_time_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            str(tmp_path / "nonexistent.json"),
        )
        assert get_last_fetch_time() is None


class TestGetDynamicPrefixes:
    """get_dynamic_prefixes fetches and caches the prefix database."""

    def test_fetch_success(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        body = json.dumps(_SAMPLE_FORMATS).encode()
        mock = _mock_urlopen(status=200, body=body)
        with patch("urllib.request.urlopen", return_value=mock):
            result = get_dynamic_prefixes(force_refresh=True)

        assert len(result) == 2
        assert result[0]["name"] == "test_service_token"
        # Cache should have been written
        assert os.path.exists(cache_path)

    def test_fetch_failure_returns_empty(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = get_dynamic_prefixes(force_refresh=True)

        assert result == []

    def test_cache_hit_avoids_fetch(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        # Pre-populate cache
        _save_cache(_SAMPLE_FORMATS)

        with patch("urllib.request.urlopen") as mock_open:
            result = get_dynamic_prefixes()
            assert mock_open.call_count == 0  # no fetch

        assert len(result) == 2

    def test_fetch_with_formats_wrapper(self, tmp_path, monkeypatch):
        """The API may return {"formats": [...]} instead of a bare list."""
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        body = json.dumps({"formats": _SAMPLE_FORMATS}).encode()
        mock = _mock_urlopen(status=200, body=body)
        with patch("urllib.request.urlopen", return_value=mock):
            result = get_dynamic_prefixes(force_refresh=True)

        assert len(result) == 2

    def test_http_error_returns_empty(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / "prefix_cache.json")
        monkeypatch.setattr(
            "halbert_core.config.dynamic_prefixes._CACHE_FILE",
            cache_path,
        )
        mock = _mock_urlopen(status=404, body=b"Not Found")
        with patch("urllib.request.urlopen", return_value=mock):
            result = get_dynamic_prefixes(force_refresh=True)

        assert result == []
