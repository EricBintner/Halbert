# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Every egress path checks the switch — including the ones in rag/.

`web/search_config.is_web_search_enabled()` documents itself as "what every
egress path checks", and `capabilities.py` has `CAP_WEB: False  # egress:
never on by preset (C3-08)`. Two paths reachable from the running daemon did
not check it:

- `GET /api/rag/trending` sends the *detected technology stack of this
  machine* to `api.github.com` as a search query, on Knowledge-tab open.
- `POST /api/rag/add` fetches an arbitrary URL through `add_url`.

The first is the worse of the two: it is unprompted, it happens on a tab
open rather than an explicit action, and the query is a description of what
is installed on the user's machine.

Local work must keep working with the switch off, which is why
`/trending/stack` — stack detection with no fetch — is asserted here too.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def web_off(monkeypatch):
    monkeypatch.setattr(
        "halbert_core.web.search_config.is_web_search_enabled", lambda: False
    )


@pytest.fixture
def web_on(monkeypatch):
    monkeypatch.setattr(
        "halbert_core.web.search_config.is_web_search_enabled", lambda: True
    )


class TestTrendingDiscovery:

    def test_no_request_leaves_the_machine_with_the_switch_off(self, web_off):
        from halbert_core.rag.trending_discovery import GitHubTrendingFetcher

        with patch("requests.get") as get:
            GitHubTrendingFetcher().search_trending(topics=["python"], limit=5)
        assert not get.called, (
            "the detected stack of this machine reached api.github.com with "
            "egress switched off"
        )

    def test_it_still_fetches_with_the_switch_on(self, web_on):
        from halbert_core.rag.trending_discovery import GitHubTrendingFetcher

        with patch("requests.get") as get:
            get.return_value.json.return_value = {"items": []}
            get.return_value.raise_for_status.return_value = None
            GitHubTrendingFetcher().search_trending(topics=["python"], limit=5)
        assert get.called

    def test_local_stack_detection_still_works_with_the_switch_off(self, web_off):
        from halbert_core.rag.trending_discovery import get_trending_engine

        # No network in this path; gating it would break offline work for no
        # privacy gain.
        stack = get_trending_engine().stack_detector.detect(force_refresh=True)
        assert isinstance(stack, dict)


class TestUrlIngestion:

    def test_add_url_fetches_nothing_with_the_switch_off(self, web_off, tmp_path):
        from halbert_core.rag.ingestion import RAGIngestionEngine

        engine = RAGIngestionEngine(data_dir=tmp_path)
        with patch("halbert_core.rag.ingestion.requests.get") as get:
            result = engine.add_url("https://example.com/docs")
        assert not get.called
        assert not result.success
        assert result.error and "egress" in result.error.lower()

    def test_the_refusal_names_the_switch_rather_than_failing_vaguely(
        self, web_off, tmp_path
    ):
        from halbert_core.rag.ingestion import RAGIngestionEngine

        engine = RAGIngestionEngine(data_dir=tmp_path)
        result = engine.add_url("https://example.com/docs")
        assert "web" in result.error.lower() or "switch" in result.error.lower(), (
            "a user who turned the switch off should be told that is why"
        )
