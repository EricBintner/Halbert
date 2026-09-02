# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""FED-01 / R10-F10 / R10-F11: say "not built" rather than "broken".

Five /api/fleet/* routes raised NotImplementedError, which FastAPI turns
into a 500 — telling an operator this node has failed when in fact this part
of the Fleet Cockpit was never written. And parse_txt_record called int() on
a field some other machine chose to broadcast, so one peer advertising
nonsense could raise straight out of the discovery loop.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from halbert_core.federation.peer_discovery import parse_txt_record


@pytest.fixture
def client():
    from halbert_core.dashboard.app import create_app
    return TestClient(create_app())


UNBUILT = [
    ("get", "/api/fleet/n1/info"),
    ("get", "/api/fleet/n1/telemetry"),
    ("post", "/api/fleet/n1/inspect"),
    ("get", "/api/fleet/n1/logs"),
    ("get", "/api/fleet/n1/discoveries"),
]


@pytest.mark.parametrize("method,path", UNBUILT)
def test_an_unbuilt_fleet_route_is_never_a_500(client, method, path):
    resp = client.post(path, json={}) if method == "post" else client.get(path)
    assert resp.status_code != 500, "an unwritten feature reported as a crash"
    # 404 when the peer is unknown (checked first), 501 when it is known but
    # the feature does not exist. Either is honest; a 500 is not.
    assert resp.status_code in (404, 501, 422)


class TestATxtRecordIsUntrusted:

    @pytest.mark.parametrize("api_port", ["not-a-port", "", None, "80 80", "1e5"])
    def test_an_unparsable_port_falls_back_instead_of_raising(self, api_port):
        parsed = parse_txt_record({"node_id": "n1", "api_port": api_port})
        assert parsed["port"] == 8000

    def test_a_good_port_is_still_used(self):
        assert parse_txt_record({"api_port": "9001"})["port"] == 9001

    def test_an_empty_record_still_parses(self):
        parsed = parse_txt_record({})
        assert parsed["node_id"] == "unknown"
        assert parsed["port"] == 8000
        assert parsed["capabilities"] == []
