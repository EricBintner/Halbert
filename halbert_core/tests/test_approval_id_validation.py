# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""F-C: an approval request_id must not be able to name a path.

``request_id`` arrives from the URL and reached ``requests_dir /
f"{request_id}.json"`` unvalidated — an id carrying ``../`` read, and the
approve/reject writes, outside the requests directory. The engine now refuses
ids that are not URL-safe-token-shaped at the storage boundary, and the
routes answer them with a clean 400 rather than a 500. Ids are
server-generated UUIDs (or ``test_<hex>``); anything else is hostile or
corrupt, and both get the same answer so the response discloses nothing.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.approval.engine import (  # noqa: E402
    ApprovalEngine,
    ApprovalRequest,
    InvalidApprovalId,
    validate_approval_id,
)


HOSTILE_IDS = [
    "../escape",
    "..%2fescape",          # URL-encoded traversal reaching the route raw
    "a/b",
    "a\\b",
    "../../etc/passwd-ish",
    ".hidden",
    "with space",
    "with:colon",
    "with;semicolon",
    "with'quote",
    "with\"dquote",
    "abs%00null",
]


def _engine(tmp_path):
    return ApprovalEngine(storage_dir=str(tmp_path / "approval"))


def _queue(engine, request_id="req-abc123", task="t"):
    engine.queue_request(ApprovalRequest(
        id=request_id, task=task, action="act", reasoning="why",
        confidence=0.9, risk_level="medium",
        system_state={}, affected_resources=[],
    ))


class TestValidateApprovalId:
    def test_uuid_shapes_pass(self):
        import uuid
        assert validate_approval_id(str(uuid.uuid4())) == str(uuid.uuid4()) or True
        # (validate returns its argument; assert it does not raise)
        validate_approval_id(str(uuid.uuid4()))
        validate_approval_id("test_1a2b3c4d")
        validate_approval_id("req_001")
        validate_approval_id("a" * 128)

    def test_hostile_ids_raise(self):
        for bad in HOSTILE_IDS:
            with pytest.raises(InvalidApprovalId):
                validate_approval_id(bad)

    def test_empty_and_overlong_raise(self):
        with pytest.raises(InvalidApprovalId):
            validate_approval_id("")
        with pytest.raises(InvalidApprovalId):
            validate_approval_id("a" * 129)


class TestTheStorageBoundary:
    def test_get_request_refuses_traversal(self, tmp_path):
        engine = _engine(tmp_path)
        with pytest.raises(InvalidApprovalId):
            engine.get_request("../escape")

    def test_save_refuses_traversal(self, tmp_path):
        engine = _engine(tmp_path)
        with pytest.raises(InvalidApprovalId):
            engine.queue_request(ApprovalRequest(
                id="../escape", task="t", action="a", reasoning="r",
                confidence=1.0, risk_level="low",
                system_state={}, affected_resources=[],
            ))
        # Nothing was written outside the requests dir.
        assert list((tmp_path).rglob("escape.json")) == []

    def test_decision_save_refuses_traversal(self, tmp_path):
        from halbert_core.approval.engine import ApprovalDecision
        engine = _engine(tmp_path)
        with pytest.raises(InvalidApprovalId):
            engine._save_decision(ApprovalDecision(
                request_id="../escape", approved=True, reason="",
                decided_by="test", decided_at="2026-01-01T00:00:00Z",
            ))

    def test_a_legitimate_request_still_roundtrips(self, tmp_path):
        engine = _engine(tmp_path)
        _queue(engine, "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
        got = engine.get_request("0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
        assert got is not None and got.id == "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


class TestTheRoutesAnswerCleanly:
    """The approve/reject/details routes turn a hostile id into a 400, and
    the per-route owner guard from F-A's approvals half holds on every
    route of the router (not just at the mount)."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_API_TOKEN", "test-token-not-a-real-credential")
        from halbert_core.dashboard.routes import approvals as approvals_routes

        app = FastAPI()
        app.include_router(approvals_routes.router, prefix="/api/approvals")
        yield TestClient(app, headers={
            "Authorization": "Bearer test-token-not-a-real-credential",
        })

    def test_details_answers_400_not_500(self, client):
        # ../ forms get normalized away by the HTTP client before the route
        # sees them; these are the single-segment ids that DO reach the
        # handler and must be refused there.
        for bad in ("with%20space", "with%3Acolon", "..%2E"):
            res = client.get(f"/api/approvals/{bad}")
            assert res.status_code == 400, f"{bad!r}: {res.status_code} {res.text}"
            assert "valid approval request id" in res.json()["detail"]

    def test_approve_answers_400_not_500(self, client):
        res = client.post("/api/approvals/with%20space/approve",
                          json={"approved": True})
        assert res.status_code == 400
        assert "valid approval request id" in res.json()["detail"]

    def test_reject_answers_400_not_500(self, client):
        res = client.post("/api/approvals/with%20space/reject",
                          json={"approved": False, "reason": "no"})
        assert res.status_code == 400
        assert "valid approval request id" in res.json()["detail"]

    def test_every_route_refuses_an_anonymous_caller(self, tmp_path):
        from halbert_core.dashboard.routes import approvals as approvals_routes

        app = FastAPI()
        app.include_router(approvals_routes.router, prefix="/api/approvals")
        anon = TestClient(app)
        # conftest's session fixture hands every TestClient the test token;
        # this suite is about the door, so take it back off (census pattern).
        anon.headers.pop("Authorization", None)
        checks = [
            anon.get("/api/approvals"),
            anon.get("/api/approvals/history"),
            anon.get("/api/approvals/proposals"),
            anon.get("/api/approvals/some-id"),
            anon.post("/api/approvals/some-id/approve", json={"approved": True}),
            anon.post("/api/approvals/some-id/reject", json={"approved": False}),
        ]
        for res in checks:
            assert res.status_code == 401, res.status_code