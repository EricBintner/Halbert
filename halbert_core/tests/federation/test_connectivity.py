# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P4a: Internet connectivity detection tests.

Verifies the ConnectivityProbe caching, online/offline detection, and
force_recheck behavior using mocked HTTP responses.
"""

import time
from unittest.mock import patch, MagicMock

import pytest

from halbert_core.federation.connectivity import ConnectivityProbe


class TestConnectivityProbe:
    def test_online_when_http_responds(self):
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.head", return_value=mock_resp):
            assert probe.is_online() is True

    def test_online_even_on_4xx(self):
        """Any HTTP response means the internet is reachable."""
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.head", return_value=mock_resp):
            assert probe.is_online() is True

    def test_offline_on_connection_error(self):
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        with patch("requests.head", side_effect=Exception("DNS failure")):
            assert probe.is_online() is False

    def test_offline_on_timeout(self):
        import requests as req_module
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        with patch("requests.head", side_effect=req_module.Timeout("timed out")):
            assert probe.is_online() is False

    def test_cache_prevents_repeated_probes(self):
        """Within the cache interval, is_online() should not re-probe."""
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=30)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.head", return_value=mock_resp) as mock_head:
            probe.is_online()
            probe.is_online()
            probe.is_online()
            assert mock_head.call_count == 1

    def test_cache_expires(self):
        """After the cache interval, is_online() re-probes."""
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.05)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.head", return_value=mock_resp) as mock_head:
            probe.is_online()
            time.sleep(0.06)
            probe.is_online()
            assert mock_head.call_count == 2

    def test_force_recheck_bypasses_cache(self):
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=30)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.head", return_value=mock_resp) as mock_head:
            probe.is_online()
            assert mock_head.call_count == 1
            probe.force_recheck()
            assert mock_head.call_count == 2

    def test_transition_from_offline_to_online(self):
        """Simulate network recovery: first probe fails, second succeeds."""
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        import requests as req_module
        with patch("requests.head", side_effect=[req_module.ConnectionError("down"), mock_resp]):
            assert probe.is_online() is False
            time.sleep(0.02)
            assert probe.is_online() is True

    def test_transition_from_online_to_offline(self):
        """Simulate network loss: first probe succeeds, second fails."""
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=0.01)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        import requests as req_module
        with patch("requests.head", side_effect=[mock_resp, req_module.ConnectionError("down")]):
            assert probe.is_online() is True
            time.sleep(0.02)
            assert probe.is_online() is False

    def test_thread_safe_concurrent_calls(self):
        """Concurrent calls should not cause errors — at most one probe."""
        import threading
        probe = ConnectivityProbe(probe_url="https://example.com", cache_interval=30)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        results = []
        with patch("requests.head", return_value=mock_resp) as mock_head:
            def call_probe():
                results.append(probe.is_online())
            threads = [threading.Thread(target=call_probe) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert all(r is True for r in results)
            assert len(results) == 10
            # At most one actual HTTP probe (cache serves the rest)
            assert mock_head.call_count <= 2  # allow for race on first entry

    def test_default_probe_url_is_set(self):
        probe = ConnectivityProbe()
        assert probe.probe_url is not None
        assert probe.probe_url.startswith("https://")

    def test_custom_cache_interval(self):
        probe = ConnectivityProbe(cache_interval=60)
        assert probe.cache_interval == 60
