"""
Tests for Phase 3: Config Dependency Edges & Blast-Radius

Tests the ConfigEdgeExtractor's ability to extract dependency edges from
parsed config files (systemd units, includes, fstab, file references, drop-ins)
and the SourcePrepClient's push_external_edges / get_impact methods.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from halbert_core.config.edge_extractor import (
    ConfigEdge,
    ConfigEdgeExtractor,
    _file_node_id,
    _resolve_unit_path,
)


@pytest.fixture
def temp_canon_dir(tmp_path):
    """Create a temporary canon directory with test config files."""
    canon_dir = tmp_path / "canon"
    canon_dir.mkdir()

    configs = []

    nginx_service = {
        "path": "/etc/systemd/system/nginx.service",
        "hash": "hash1",
        "kind": "ini",
        "sections": {
            "Unit": {
                "Description": "nginx web server",
                "Requires": "network.target",
                "After": "network.target",
            },
            "Service": {
                "ExecStart": "/usr/sbin/nginx -g 'daemon off;'",
                "EnvironmentFile": "/etc/default/nginx",
                "PIDFile": "/run/nginx.pid",
            },
        },
        "lines": [
            {"n": 1, "text": "[Unit]"},
            {"n": 2, "text": "Description=nginx web server"},
            {"n": 3, "text": "Requires=network.target"},
            {"n": 4, "text": "After=network.target"},
            {"n": 5, "text": "[Service]"},
            {"n": 6, "text": "ExecStart=/usr/sbin/nginx -g 'daemon off;'"},
            {"n": 7, "text": "EnvironmentFile=/etc/default/nginx"},
            {"n": 8, "text": "PIDFile=/run/nginx.pid"},
        ],
    }
    configs.append(nginx_service)

    nginx_default = {
        "path": "/etc/default/nginx",
        "hash": "hash2",
        "kind": "text",
        "lines": [
            {"n": 1, "text": "NGINX_OPTS=\"-c /etc/nginx/nginx.conf\""},
        ],
    }
    configs.append(nginx_default)

    nginx_conf = {
        "path": "/etc/nginx/nginx.conf",
        "hash": "hash3",
        "kind": "text",
        "lines": [
            {"n": 1, "text": "worker_processes auto;"},
            {"n": 2, "text": "include /etc/nginx/conf.d/*.conf;"},
            {"n": 3, "text": "ssl_certificate /etc/ssl/certs/dummy.pem;"},
        ],
    }
    configs.append(nginx_conf)

    conf_d_file = {
        "path": "/etc/nginx/conf.d/site.conf",
        "hash": "hash4",
        "kind": "text",
        "lines": [
            {"n": 1, "text": "server { listen 80; }"},
        ],
    }
    configs.append(conf_d_file)

    network_target = {
        "path": "/lib/systemd/system/network.target",
        "hash": "hash5",
        "kind": "ini",
        "sections": {"Unit": {"Description": "Network"}},
        "lines": [{"n": 1, "text": "[Unit]"}, {"n": 2, "text": "Description=Network"}],
    }
    configs.append(network_target)

    mount_unit = {
        "path": "/lib/systemd/system/mnt-data.mount",
        "hash": "hash7",
        "kind": "ini",
        "sections": {"Unit": {"Description": "Mount /mnt/data"}},
        "lines": [{"n": 1, "text": "[Unit]"}, {"n": 2, "text": "Description=Mount /mnt/data"}],
    }
    configs.append(mount_unit)

    fstab = {
        "path": "/etc/fstab",
        "hash": "hash6",
        "kind": "text",
        "lines": [
            {"n": 1, "text": "# device  mount  type  opts  dump pass"},
            {"n": 2, "text": "/dev/sda1  /mnt/data  ext4  defaults  0  2"},
        ],
    }
    configs.append(fstab)

    for cfg in configs:
        fname = f"{cfg['hash']}.json"
        with open(canon_dir / fname, "w") as f:
            json.dump(cfg, f)

    return str(canon_dir), [c["path"] for c in configs]


class TestConfigEdgeExtractorSystemd:
    """Test systemd directive extraction."""

    def test_requires_edge(self, temp_canon_dir):
        canon_dir, known_paths = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        requires_edges = [e for e in edges if e.kind == "requires"]
        assert len(requires_edges) >= 1
        assert any(
            e.source == _file_node_id("/etc/systemd/system/nginx.service")
            and e.target == _file_node_id("/lib/systemd/system/network.target")
            for e in requires_edges
        )

    def test_after_edge(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        after_edges = [e for e in edges if e.kind == "after"]
        assert len(after_edges) >= 1
        assert any(
            e.source == _file_node_id("/etc/systemd/system/nginx.service")
            and e.target == _file_node_id("/lib/systemd/system/network.target")
            for e in after_edges
        )

    def test_environment_file_edge(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        configures_edges = [e for e in edges if e.kind == "configures"]
        assert len(configures_edges) >= 1
        assert any(
            e.source == _file_node_id("/etc/systemd/system/nginx.service")
            and e.target == _file_node_id("/etc/default/nginx")
            for e in configures_edges
        )

    def test_no_duplicate_references_for_systemd_directives(self, temp_canon_dir):
        """EnvironmentFile should produce 'configures' edge only, not also 'references'."""
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        nginx_to_default = [
            e for e in edges
            if e.source == _file_node_id("/etc/systemd/system/nginx.service")
            and e.target == _file_node_id("/etc/default/nginx")
        ]
        assert len(nginx_to_default) == 1
        assert nginx_to_default[0].kind == "configures"

    def test_executes_edge_skips_non_config(self, temp_canon_dir):
        """ExecStart references binaries which are not config files — no edge created."""
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        executes_edges = [e for e in edges if e.kind == "executes"]
        assert len(executes_edges) == 0

    def test_edge_metadata_contains_directive(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        requires_edges = [e for e in edges if e.kind == "requires"]
        assert len(requires_edges) >= 1
        assert requires_edges[0].metadata.get("directive") == "Requires"
        assert requires_edges[0].metadata.get("extractor") == "systemd"


class TestConfigEdgeExtractorIncludes:
    """Test include directive extraction."""

    def test_nginx_include_glob(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        include_edges = [
            e for e in edges
            if e.kind == "includes"
            and e.source == _file_node_id("/etc/nginx/nginx.conf")
        ]
        assert len(include_edges) >= 1
        assert any(
            e.target == _file_node_id("/etc/nginx/conf.d/site.conf")
            for e in include_edges
        )


class TestConfigEdgeExtractorReferences:
    """Test file-reference extraction."""

    def test_reference_to_known_config_only(self, temp_canon_dir):
        """References to non-config files (e.g. SSL certs) are skipped — only known configs get edges."""
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        ref_edges = [
            e for e in edges
            if e.kind == "references"
            and e.source == _file_node_id("/etc/nginx/nginx.conf")
        ]
        assert len(ref_edges) == 0

    def test_reference_to_nginx_conf_from_default(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        ref_edges = [
            e for e in edges
            if e.source == _file_node_id("/etc/default/nginx")
            and e.target == _file_node_id("/etc/nginx/nginx.conf")
        ]
        assert len(ref_edges) >= 1


class TestConfigEdgeExtractorFstab:
    """Test fstab -> mount unit extraction."""

    def test_fstab_mount_unit_correspondence(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        fstab_edges = [
            e for e in edges
            if e.source == _file_node_id("/etc/fstab")
            and e.kind == "corresponds_to"
        ]
        assert len(fstab_edges) >= 1
        assert any(
            "mnt-data.mount" in e.target for e in fstab_edges
        )

    def test_mount_point_to_unit_conversion(self):
        assert ConfigEdgeExtractor._mount_point_to_unit("/") == "-.mount"
        assert ConfigEdgeExtractor._mount_point_to_unit("/mnt/data") == "mnt-data.mount"
        assert ConfigEdgeExtractor._mount_point_to_unit("/var/log") == "var-log.mount"


class TestConfigEdgeExtractorDedup:
    """Test edge deduplication."""

    def test_no_duplicate_edges(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)
        edges = extractor.extract_all()

        seen = set()
        for e in edges:
            key = (e.source, e.target, e.kind)
            assert key not in seen, f"Duplicate edge: {key}"
            seen.add(key)


class TestConfigEdgeFormat:
    """Test edge serialization format."""

    def test_to_dict_has_required_fields(self):
        edge = ConfigEdge(
            source="file:/etc/foo",
            target="file:/etc/bar",
            kind="requires",
            metadata={"directive": "Requires"},
        )
        d = edge.to_dict()
        assert d["source"] == "file:/etc/foo"
        assert d["target"] == "file:/etc/bar"
        assert d["kind"] == "requires"
        assert d["origin"] == "config"
        assert d["metadata"]["directive"] == "Requires"

    def test_to_dict_without_metadata(self):
        edge = ConfigEdge(
            source="file:/etc/foo",
            target="file:/etc/bar",
            kind="includes",
        )
        d = edge.to_dict()
        assert "metadata" not in d
        assert d["origin"] == "config"


class TestSourcePrepClientExtensions:
    """Test SourcePrepClient push_external_edges and get_impact."""

    def test_push_external_edges_calls_post(self):
        from halbert_core.integrations.sourceprep_client import SourcePrepClient

        client = SourcePrepClient(base_url="http://localhost:8400", project_id="test")
        with patch.object(client, "_post") as mock_post:
            mock_post.return_value = {"accepted": 5}
            edges = [
                {"source": "file:/etc/a", "target": "file:/etc/b", "kind": "requires"},
            ]
            result = client.push_external_edges(edges, replace_origin="config")
            assert result["accepted"] == 5
            call_args = mock_post.call_args
            body = call_args[0][1]
            assert body["edges"] == edges
            assert body["replace_origin"] == "config"

    def test_push_external_edges_without_replace(self):
        from halbert_core.integrations.sourceprep_client import SourcePrepClient

        client = SourcePrepClient(base_url="http://localhost:8400", project_id="test")
        with patch.object(client, "_post") as mock_post:
            mock_post.return_value = {"accepted": 1}
            edges = [
                {"source": "file:/etc/a", "target": "file:/etc/b", "kind": "includes"},
            ]
            client.push_external_edges(edges)
            call_args = mock_post.call_args
            body = call_args[0][1]
            assert "replace_origin" not in body

    def test_get_impact_builds_correct_url(self):
        from halbert_core.integrations.sourceprep_client import SourcePrepClient

        client = SourcePrepClient(base_url="http://localhost:8400", project_id="test")
        with patch("halbert_core.integrations.sourceprep_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"target": {}, "dependents": []}
            mock_get.return_value = mock_resp

            result = client.get_impact("/etc/fstab")
            assert "dependents" in result
            call_url = mock_get.call_args[0][0]
            assert "file:/etc/fstab" in call_url
            assert "impact" in call_url

    def test_get_impact_accepts_node_id_format(self):
        from halbert_core.integrations.sourceprep_client import SourcePrepClient

        client = SourcePrepClient(base_url="http://localhost:8400", project_id="test")
        with patch("halbert_core.integrations.sourceprep_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"target": {}, "dependents": []}
            mock_get.return_value = mock_resp

            client.get_impact("file:/etc/systemd/system/nginx.service")
            call_url = mock_get.call_args[0][0]
            assert "file:/etc/systemd/system/nginx.service" in call_url


class TestConfigEdgeExtractorSync:
    """Test the sync method that extracts + pushes to SourcePrep."""

    def test_sync_calls_push_with_replace_origin(self, temp_canon_dir):
        canon_dir, _ = temp_canon_dir
        extractor = ConfigEdgeExtractor(canon_dir=canon_dir)

        mock_client = MagicMock()
        mock_client.push_external_edges.return_value = {"accepted": 5}

        result = extractor.sync(mock_client)

        assert result["extracted"] >= 1
        assert result["accepted"] == 5
        call_kwargs = mock_client.push_external_edges.call_args
        assert call_kwargs[1]["replace_origin"] == "config"

    def test_sync_with_no_edges(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        extractor = ConfigEdgeExtractor(canon_dir=str(empty_dir))

        mock_client = MagicMock()
        result = extractor.sync(mock_client)

        assert result["accepted"] == 0
        assert result["extracted"] == 0
        mock_client.push_external_edges.assert_not_called()
