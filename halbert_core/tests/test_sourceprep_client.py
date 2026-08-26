# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SourcePrepClient project-id resolution (env -> project.json -> '')."""

import json
from unittest.mock import patch

from halbert_core.integrations.sourceprep_client import (
    SourcePrepClient,
    resolve_default_project_id,
)
from halbert_core.integrations.sourceprep_retrieval_backend import (
    SourcePrepRetrievalBackend,
)


def test_project_id_from_env(monkeypatch):
    monkeypatch.setenv("SOURCEPREP_PROJECT_ID", "abc")
    assert SourcePrepClient().project_id == "abc"
    assert resolve_default_project_id() == "abc"


def test_project_id_from_project_json(tmp_path, monkeypatch):
    marker_dir = tmp_path / ".sourceprep"
    marker_dir.mkdir()
    (marker_dir / "project.json").write_text(json.dumps({"id": "pid-1"}))
    monkeypatch.delenv("SOURCEPREP_PROJECT_ID", raising=False)
    monkeypatch.setenv("SOURCEPREP_PROJECT_ROOT", str(tmp_path))
    assert SourcePrepClient().project_id == "pid-1"


def test_project_id_missing_is_empty_and_search_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("SOURCEPREP_PROJECT_ID", raising=False)
    monkeypatch.setenv("SOURCEPREP_PROJECT_ROOT", str(tmp_path))
    client = SourcePrepClient()
    assert client.project_id == ""
    backend = SourcePrepRetrievalBackend(client=client)
    with patch("halbert_core.integrations.sourceprep_client.requests.post") as post:
        assert backend.search("x") == []
        post.assert_not_called()
