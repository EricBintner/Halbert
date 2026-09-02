# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 step 7b: "forget that", across both planes.

EventLog.erase() had zero callers outside its own tests in either repo, so
this was an unbuilt feature rather than a broken one. What it removes is the
*words*: the facts and their timeline stay, because what was true and when is
not the thing being forgotten.
"""

import pytest

from halbert_core.continuity.provenance import (
    ERASURE_LIMITS,
    forget_request,
    record_file_change,
)
from halbert_core.continuity.state_store import (
    ACTOR_USER,
    UNRECORDED,
    StateStore,
    default_state_db_path,
)
from halbert_core.continuity.vault import VaultProjector, vault_root
from halbert_core.obs.audit import audit_log, erase_audit_by_request, set_audit_signer


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("HALBERT_PERSONA_ID", "testpersona")
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _ledger():
    return StateStore(db_path=str(default_state_db_path()))


SECRET = "because I am hiding it from my flatmate"


def _seed():
    record_file_change(path="/etc/private.conf", reason=SECRET,
                       actor=ACTOR_USER, request_id="req-9", tool="editor",
                       after_text="x\n")
    record_file_change(path="/etc/other.conf", reason="keep this one",
                       actor=ACTOR_USER, request_id="req-1", tool="editor",
                       after_text="y\n")


def _all_audit_bytes():
    return "".join(str(e.payload) for e in audit_log().read_all())


class TestBothPlanes:
    def test_the_words_are_gone_from_both(self):
        _seed()
        assert SECRET in _all_audit_bytes()

        report = forget_request("req-9")

        assert report["ledger_rows"] >= 1
        assert report["audit_records"] >= 1
        assert report["complete"] is True
        assert SECRET not in _all_audit_bytes()

        store = _ledger()
        assert all(r.reason != SECRET for r in store.by_request("req-9"))
        store.close()

    def test_the_audit_bytes_are_gone_from_disk(self, tmp_path):
        _seed()
        forget_request("req-9")
        for shard in (tmp_path / "logs" / "audit").glob("*.jsonl"):
            assert "flatmate" not in shard.read_text(encoding="utf-8")

    def test_the_chain_still_verifies_afterwards(self):
        """The salted-commitment design is what makes this possible at all."""
        _seed()
        forget_request("req-9")
        assert audit_log().verify().ok

    def test_the_facts_and_their_timeline_survive(self):
        _seed()
        forget_request("req-9")

        store = _ledger()
        rows = store.current_state(subject="file:/etc/private.conf")
        assert len(rows) == 1, "the fact was deleted, not forgotten"
        assert rows[0].reason == UNRECORDED
        assert rows[0].valid_from is not None
        store.close()

    def test_another_request_is_untouched(self):
        _seed()
        forget_request("req-9")
        assert "keep this one" in _all_audit_bytes()

    def test_it_is_idempotent(self):
        _seed()
        assert forget_request("req-9")["audit_records"] >= 1
        second = forget_request("req-9")
        assert second["audit_records"] == 0 and second["ledger_rows"] == 0
        assert second["complete"] is True, "already forgotten is not a failure"

    def test_an_unknown_request_is_not_an_error(self):
        report = forget_request("never-existed")
        assert report["complete"] is True
        assert report["ledger_rows"] == 0 and report["audit_records"] == 0

    def test_an_empty_request_id_is_reported_not_raised(self):
        report = forget_request("")
        assert report["complete"] is False and report["errors"]


class TestTheVaultFollows:
    def test_the_note_stops_carrying_the_words_and_a_rebuild_keeps_it_that_way(self):
        _seed()
        VaultProjector().rebuild()
        assert any(SECRET in p.read_text() for p in vault_root().rglob("*.md"))

        assert forget_request("req-9")["vault_rebuilt"] is True
        assert not any(SECRET in p.read_text() for p in vault_root().rglob("*.md"))

        VaultProjector().rebuild()
        assert not any(SECRET in p.read_text() for p in vault_root().rglob("*.md"))


class TestHonesty:
    def test_the_report_states_what_it_did_not_reach(self):
        """INTEG-05: a surface must not claim more than it can show."""
        _seed()
        report = forget_request("req-9")
        assert report["limits"] == ERASURE_LIMITS
        assert "memory_v2" in ERASURE_LIMITS
        assert "conversation messages" in ERASURE_LIMITS

    def test_a_partial_failure_is_reported_not_hidden(self, monkeypatch):
        import halbert_core.continuity.state_store as ss

        _seed()
        # forget_request imports StateStore at call time, so the patch goes
        # on the defining module.
        monkeypatch.setattr(
            ss, "StateStore", lambda **kw: (_ for _ in ()).throw(OSError("locked")))
        report = forget_request("req-9")

        assert report["complete"] is False
        assert any("ledger" in e for e in report["errors"])
        # the audit half still ran
        assert report["audit_records"] >= 1

    def test_erasure_is_not_described_as_a_wipe(self):
        """_rewrite is mkstemp + os.replace; the old shard's blocks are not
        overwritten, so "unrecoverable" flat would overclaim."""
        assert "filesystem has not yet reused" in ERASURE_LIMITS


class TestTheRoute:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from halbert_core.dashboard.routes import state as state_routes

        app = FastAPI()
        app.include_router(state_routes.router, prefix="/api/state")
        return TestClient(app)

    def test_it_forgets_and_reports(self, client):
        _seed()
        body = client.post("/api/state/forget", params={"request_id": "req-9"}).json()

        assert body["complete"] is True
        assert body["ledger_rows"] >= 1 and body["audit_records"] >= 1
        assert body["limits"] == ERASURE_LIMITS
        assert SECRET not in _all_audit_bytes()

    def test_it_is_not_reachable_by_a_get(self, client):
        """Destructive, so a prefetch or a crawler must not trigger it."""
        assert client.get("/api/state/forget",
                          params={"request_id": "req-9"}).status_code == 405


class TestTheAuditHelperAlone:
    def test_it_returns_zero_rather_than_raising_on_an_unknown_request(self):
        assert erase_audit_by_request("nope") == 0

    def test_an_empty_request_id_is_zero(self):
        assert erase_audit_by_request("") == 0
