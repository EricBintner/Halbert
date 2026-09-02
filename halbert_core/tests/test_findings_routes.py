# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""GET /api/findings, GET /api/findings/{id}, POST /api/findings/{id}/propose.

The one reader the Findings page, the bell and MCP share (C2-03 / P1-10),
and the manual "propose fix" path (J3-7). Routed through create_app() so a
missing include_router (the devices 404) fails here, not in the browser.
"""
from __future__ import annotations

import pytest

from halbert_core.findings.store import FindingStore, Finding
from halbert_core.findings.proposals import ProposalStore, Proposal


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app

    return TestClient(create_app())


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from halbert_core.dashboard.routes import findings as routes

    db = str(tmp_path / "findings.db")
    fs = FindingStore(db_path=db)
    ps = ProposalStore(db_path=db)
    monkeypatch.setattr(routes, "_finding_store", lambda: fs)
    monkeypatch.setattr(routes, "_proposal_store", lambda: ps)
    return fs, ps


def _finding(title="SSH port conflict", detector="dropin_conflicts"):
    return Finding(
        id="", detector=detector, severity="warning", title=title,
        description="sshd_config and drop-in both set Port",
        why_now="detected during scan",
        why_care="service may not bind expected port",
        why_so="base sets Port=22, drop-in sets Port=2222",
        why_trust=["/etc/ssh/sshd_config:5"],
        affected_paths=["/etc/ssh/sshd_config"],
    )


class TestListFindings:
    def test_default_lists_open_with_the_four_whys(self, client, stores):
        fs, _ = stores
        fid = fs.add(_finding())
        dismissed = fs.add(_finding(title="dismissed"))
        fs.dismiss(dismissed, "nope")

        resp = client.get("/api/findings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert [f["id"] for f in body["findings"]] == [fid]
        f = body["findings"][0]
        assert f["why_now"] == "detected during scan"
        assert f["why_care"] == "service may not bind expected port"
        assert f["why_so"] == "base sets Port=22, drop-in sets Port=2222"
        assert f["why_trust"] == ["/etc/ssh/sshd_config:5"]
        assert f["affected_paths"] == ["/etc/ssh/sshd_config"]
        assert f["proposal_id"] is None
        assert "data" not in f  # transient, never persisted

    def test_status_all_includes_dismissed(self, client, stores):
        fs, _ = stores
        fs.add(_finding())
        dismissed = fs.add(_finding(title="dismissed"))
        fs.dismiss(dismissed, "nope")

        body = client.get("/api/findings", params={"status": "all"}).json()
        assert body["count"] == 2
        assert {f["status"] for f in body["findings"]} == {"open", "dismissed"}

    def test_unknown_status_is_400(self, client, stores):
        assert client.get("/api/findings", params={"status": "bogus"}).status_code == 400


class TestGetFinding:
    def test_returns_finding_and_linked_proposal(self, client, stores):
        fs, ps = stores
        fid = fs.add(_finding())
        pid = ps.add(Proposal(id="", finding_id=fid, action="chmod 600 x"))
        fs.link_proposal(fid, pid)

        body = client.get(f"/api/findings/{fid}").json()
        assert body["finding"]["id"] == fid
        assert body["finding"]["proposal_id"] == pid
        assert body["proposal"]["id"] == pid
        assert body["proposal"]["action"] == "chmod 600 x"

    def test_no_proposal_is_null(self, client, stores):
        fs, _ = stores
        fid = fs.add(_finding())
        body = client.get(f"/api/findings/{fid}").json()
        assert body["proposal"] is None

    def test_unknown_id_is_404(self, client, stores):
        assert client.get("/api/findings/nope").status_code == 404


class _StubGenerator:
    """Stands in for ProposalGenerator: records the call, creates a real
    proposal row (or none, mirroring 'no automatic fix')."""

    def __init__(self, fs, ps, fixable=True):
        self.fs, self.ps, self.fixable = fs, ps, fixable
        self.calls = []

    def generate_for_finding(self, finding_id):
        self.calls.append(finding_id)
        if not self.fixable:
            return None
        pid = self.ps.add(Proposal(id="", finding_id=finding_id, action="chmod 700 ~/.ssh"))
        self.fs.link_proposal(finding_id, pid)
        return pid


@pytest.fixture
def generator(stores, monkeypatch):
    from halbert_core.dashboard.routes import findings as routes

    fs, ps = stores
    gen = _StubGenerator(fs, ps)
    monkeypatch.setattr(routes, "_proposal_generator", lambda fs_, ps_: gen)
    return gen


class TestPropose:
    def test_creates_and_returns_the_proposal(self, client, stores, generator):
        fs, _ = stores
        fid = fs.add(_finding(detector="permissions_hygiene"))

        resp = client.post(f"/api/findings/{fid}/propose")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert generator.calls == [fid]
        assert body["status"] == "ok"
        assert body["finding_id"] == fid
        assert body["proposal"]["action"] == "chmod 700 ~/.ssh"
        assert body["proposal"]["status"] == "pending"
        assert fs.get(fid).proposal_id == body["proposal"]["id"]

    def test_unknown_finding_is_404(self, client, stores, generator):
        assert client.post("/api/findings/nope/propose").status_code == 404
        assert generator.calls == []

    def test_already_proposed_is_409_and_does_not_regenerate(self, client, stores, generator):
        fs, ps = stores
        fid = fs.add(_finding())
        pid = ps.add(Proposal(id="", finding_id=fid, action="x"))
        fs.link_proposal(fid, pid)

        resp = client.post(f"/api/findings/{fid}/propose")
        assert resp.status_code == 409
        assert pid in resp.json()["detail"]
        assert generator.calls == []

    def test_dismissed_finding_is_409(self, client, stores, generator):
        fs, _ = stores
        fid = fs.add(_finding())
        fs.dismiss(fid, "not a problem")
        assert client.post(f"/api/findings/{fid}/propose").status_code == 409
        assert generator.calls == []

    def test_no_automatic_fix_is_422(self, client, stores, generator):
        fs, _ = stores
        generator.fixable = False
        fid = fs.add(_finding())
        resp = client.post(f"/api/findings/{fid}/propose")
        assert resp.status_code == 422
        assert generator.calls == [fid]
