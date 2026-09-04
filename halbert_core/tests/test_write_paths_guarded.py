# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Every path that writes a config looks first.

The guard belongs on all of them, but it means something different on each.

``write_config`` is the agent acting: a refusal is Halbert declining to
overwrite a change it did not make. The editor is a *person* saving, and a
person who has had a file open in Monaco while something else changed it must
be TOLD, not silently blocked -- and told before their editor's copy lands on
top. ``expected_sha256`` is that conversation: the client says what it thinks
it is editing, and a mismatch is answered rather than applied.
"""

import os

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.continuity.provenance import FILE_CONTENT_PREDICATE, content_digest  # noqa: E402
from halbert_core.continuity.state_store import (  # noqa: E402
    ACTOR_USER, StateStore, default_state_db_path,
)
import halbert_core.dashboard.routes.editor as editor_routes  # noqa: E402
from halbert_core.tools.base import ToolRequest  # noqa: E402
from halbert_core.tools.write_config import WriteConfig  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture
def store():
    s = StateStore(db_path=str(default_state_db_path()))
    yield s
    s.close()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(editor_routes.router)
    return TestClient(app)


def _record(store, path, text, reason):
    from halbert_core.continuity.provenance import record_file_change

    record_file_change(
        path=str(path), reason=reason, actor=ACTOR_USER, request_id="seed",
        tool="test", after_text=text, store=store,
    )


class TestTheAgentsConfigWriter:
    def test_a_drifted_file_is_refused_and_left_alone(self, store, tmp_path):
        f = tmp_path / "app.yaml"
        f.write_text("port: 80\n")
        _record(store, f, "port: 80\n", "set the port")
        f.write_text("port: 8080\n")  # someone else

        result = WriteConfig().execute(ToolRequest(
            request_id="r1", tool="write_config", inputs={"path": str(f), "changes": {"port": 9090},
                                     "reason": "changing it again"},
            confirm=True, dry_run=False,
        ))

        assert result.ok is False
        assert "changed outside Halbert" in (result.error or "")
        assert "set the port" in (result.error or "")
        assert f.read_text() == "port: 8080\n"

    def test_a_preview_is_never_refused(self, store, tmp_path):
        """A dry run changes nothing, so there is nothing to protect. Refusing
        it would deny the reader the diff that explains the drift."""
        f = tmp_path / "app.yaml"
        f.write_text("port: 80\n")
        _record(store, f, "port: 80\n", "set the port")
        f.write_text("port: 8080\n")

        result = WriteConfig().execute(ToolRequest(
            request_id="r2", tool="write_config", inputs={"path": str(f), "changes": {"port": 9090}},
            confirm=False, dry_run=True,
        ))

        assert result.ok is True
        assert result.outputs["applied"] is False

    def test_an_unrecorded_file_still_applies(self, store, tmp_path):
        f = tmp_path / "fresh.yaml"
        f.write_text("port: 80\n")

        result = WriteConfig().execute(ToolRequest(
            request_id="r3", tool="write_config", inputs={"path": str(f), "changes": {"port": 9090},
                                     "reason": "asked to"},
            confirm=True, dry_run=False,
        ))

        assert result.ok is True and result.outputs["applied"] is True


class TestThePersonAtTheEditor:
    def test_a_save_with_the_right_expected_digest_lands(self, client, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("127.0.0.1 localhost\n")

        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "127.0.0.1 localhost\n::1 localhost\n",
            "expected_sha256": content_digest("127.0.0.1 localhost\n"),
            "reason": "added the v6 loopback",
        })

        assert r.status_code == 200 and r.json()["success"] is True
        assert "::1" in f.read_text()

    def test_a_save_against_a_stale_copy_is_answered_not_applied(self, client, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("127.0.0.1 localhost\n")
        stale = content_digest("something the editor loaded earlier\n")

        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "whatever Monaco held\n",
            "expected_sha256": stale,
        })

        assert r.status_code == 409, "a conflict is not a server error"
        assert "changed" in r.json()["detail"].lower()
        # The other change is intact.
        assert f.read_text() == "127.0.0.1 localhost\n"

    def test_a_save_with_no_expectation_still_checks_the_ledger(self, client, store, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("127.0.0.1 localhost\n")
        _record(store, f, "127.0.0.1 localhost\n", "first save")
        f.write_text("someone else edited this\n")

        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "the editor's copy\n",
        })

        assert r.status_code == 409
        assert f.read_text() == "someone else edited this\n"

    def test_a_new_file_is_not_blocked(self, client, tmp_path):
        f = tmp_path / "brand-new.conf"

        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "hello\n", "reason": "created it",
        })

        assert r.status_code == 200
        assert f.read_text() == "hello\n"


class TestTheEditorIsToldWhatItLoaded:
    def test_a_read_returns_the_digest_of_what_it_handed_over(self, client, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("127.0.0.1 localhost\n")

        body = client.get(f"/api/editor/file?path={f}").json()

        # Without this the client has nothing to send back as its
        # expectation, and the conversation about a stale tab cannot happen.
        assert body["sha256"] == content_digest("127.0.0.1 localhost\n")

    def test_the_digest_round_trips_into_an_accepted_save(self, client, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("one\n")

        loaded = client.get(f"/api/editor/file?path={f}").json()
        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "two\n",
            "expected_sha256": loaded["sha256"], "reason": "changed it",
        })

        assert r.status_code == 200
        assert f.read_text() == "two\n"

    def test_the_same_digest_after_someone_else_saves_is_refused(self, client, tmp_path):
        f = tmp_path / "hosts"
        f.write_text("one\n")
        loaded = client.get(f"/api/editor/file?path={f}").json()
        f.write_text("someone else\n")

        r = client.post("/api/editor/file", json={
            "path": str(f), "content": "two\n", "expected_sha256": loaded["sha256"],
        })

        assert r.status_code == 409
        assert f.read_text() == "someone else\n"
