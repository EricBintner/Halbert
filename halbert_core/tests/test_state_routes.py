# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 read surface: "why is X configured this way" answers from the ledger."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.continuity.provenance import FILE_CONTENT_PREDICATE, record_file_change
from halbert_core.continuity.state_store import ACTOR_AGENT, ACTOR_USER
from halbert_core.dashboard.routes import state as state_routes
from halbert_core.obs.audit import set_audit_signer


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(state_routes.router, prefix="/api/state")
    return TestClient(app)


def _change(path, reason, actor, before=None, after="x\n", request_id="r1"):
    record_file_change(
        path=path, reason=reason, actor=actor, request_id=request_id,
        tool="editor", before_text=before, after_text=after,
    )


class TestWhy:
    def test_it_answers_with_before_after_actor_and_reason(self, client):
        """The definition-of-done sentence of LEDGER-1, end to end."""
        _change("/etc/ssh/sshd_config", "shipped default", ACTOR_AGENT,
                after="PermitRootLogin yes\n", request_id="r1")
        _change("/etc/ssh/sshd_config", "hardening after the audit finding",
                ACTOR_USER, before="PermitRootLogin yes\n",
                after="PermitRootLogin no\n", request_id="r2")

        body = client.get("/api/state/why",
                          params={"path": "/etc/ssh/sshd_config"}).json()

        assert body["found"] is True
        assert body["current"]["reason"] == "hardening after the audit finding"
        assert body["current"]["actor"] == ACTOR_USER
        assert body["current"]["request_id"] == "r2"
        assert body["superseded"]["reason"] == "shipped default"
        assert body["superseded"]["valid_to"] is not None

    def test_an_unknown_file_abstains_rather_than_guessing(self, client):
        _change("/etc/known.conf", "a reason", ACTOR_USER)
        body = client.get("/api/state/why",
                          params={"path": "/etc/never-touched.conf"}).json()
        assert body["found"] is False
        assert body["current"] is None and body["superseded"] is None

    def test_an_explicit_subject_works_too(self, client):
        _change("/etc/a.conf", "because", ACTOR_USER)
        body = client.get("/api/state/why", params={
            "subject": "file:/etc/a.conf", "predicate": FILE_CONTENT_PREDICATE,
        }).json()
        assert body["found"] is True

    def test_no_subject_and_no_path_is_not_found_not_an_error(self, client):
        r = client.get("/api/state/why")
        assert r.status_code == 200 and r.json()["found"] is False


class TestHistoryAndJoin:
    def test_history_is_oldest_first_and_each_row_carries_its_reason(self, client):
        _change("/etc/a.conf", "first", ACTOR_USER, after="1\n", request_id="r1")
        _change("/etc/a.conf", "second", ACTOR_USER, before="1\n",
                after="2\n", request_id="r2")

        rows = client.get("/api/state/history", params={
            "subject": "file:/etc/a.conf"}).json()
        assert [r["reason"] for r in rows] == ["first", "second"]
        assert rows[0]["closed_reason"] == "superseded: second"

    def test_by_request_joins_to_the_audit_record(self, client):
        _change("/etc/a.conf", "because", ACTOR_USER, request_id="req-42")
        rows = client.get("/api/state/by-request",
                          params={"request_id": "req-42"}).json()
        assert len(rows) == 1 and rows[0]["request_id"] == "req-42"

    def test_an_unknown_request_is_empty(self, client):
        assert client.get("/api/state/by-request",
                          params={"request_id": "nope"}).json() == []
