# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 step 7a: the write paths that recorded nothing, or recorded blanks.

Four paths, three failure modes:

- **approval execution, config branch** — already wrote both planes, but with
  ``UNRECORDED`` and a uuid4 that severed the join to the approval;
- **approval execution, chmod branch** — audit only, and would have stayed
  audit-only if routed through the content recorder (see the mode-predicate
  tests below);
- **diff apply** and **the config watcher** — recorded nothing at all.
"""

import os
from unittest import mock

import pytest

from halbert_core.continuity.provenance import (
    FILE_CONTENT_PREDICATE,
    FILE_MODE_PREDICATE,
    content_digest,
    record_file_change,
    record_file_mode_change,
)
from halbert_core.continuity.state_store import (
    ACTOR_SYSTEM,
    ACTOR_USER,
    UNRECORDED,
    StateStore,
    default_state_db_path,
)
from halbert_core.obs.audit import audit_log, set_audit_signer


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _ledger():
    return StateStore(db_path=str(default_state_db_path()))


def _last_audit():
    return audit_log().read_all()[-1].payload


class TestChmodNeedsItsOwnPredicate:
    """The silent half-record this exists to prevent."""

    def test_a_chmod_writes_both_planes(self, tmp_path):
        target = tmp_path / "id_rsa"
        target.write_text("key", encoding="utf-8")

        record_file_mode_change(
            path=str(target), mode_octal="600",
            reason="permissions hygiene finding", actor=ACTOR_USER,
            request_id="proposal-7", tool="chmod", before_mode="0o644",
        )

        payload = _last_audit()
        assert payload["reason"] == "permissions hygiene finding"
        assert payload["actor"] == ACTOR_USER

        store = _ledger()
        rows = store.by_request("proposal-7")
        assert len(rows) == 1
        assert rows[0].predicate == FILE_MODE_PREDICATE
        assert rows[0].object == "600"
        store.close()

    def test_the_content_recorder_would_have_dropped_it_silently(self, tmp_path):
        """Why the separate predicate exists, pinned as behaviour.

        A chmod does not change content, so a second content-keyed record
        finds the digest unchanged, takes record_state's no-op branch, and
        discards the row AND its reason -- while the audit half still lands,
        so "a record exists" would pass with half the contract missing.
        """
        target = tmp_path / "id_rsa"
        target.write_text("key", encoding="utf-8")
        text = target.read_text(encoding="utf-8")

        record_file_change(path=str(target), reason="first", actor=ACTOR_USER,
                           request_id="req-1", tool="editor", after_text=text)
        record_file_change(path=str(target), reason="the chmod's reason",
                           actor=ACTOR_USER, request_id="req-2", tool="chmod",
                           before_text=text, after_text=text)

        store = _ledger()
        assert store.by_request("req-2") == [], "expected the no-op branch"
        assert _last_audit()["reason"] == "the chmod's reason"   # audit half landed
        # and the mode predicate is what keeps it whole
        record_file_mode_change(path=str(target), mode_octal="600",
                                reason="the chmod's reason", actor=ACTOR_USER,
                                request_id="req-3", tool="chmod")
        assert len(store.by_request("req-3")) == 1
        store.close()

    def test_mode_and_content_coexist_on_one_file(self, tmp_path):
        target = tmp_path / "f.conf"
        target.write_text("a\n", encoding="utf-8")
        record_file_change(path=str(target), reason="content", actor=ACTOR_USER,
                           request_id="r1", tool="editor", after_text="a\n")
        record_file_mode_change(path=str(target), mode_octal="600",
                                reason="mode", actor=ACTOR_USER,
                                request_id="r2", tool="chmod")
        store = _ledger()
        preds = {t.predicate for t in store.current_state(subject=f"file:{target}")}
        assert preds == {FILE_CONTENT_PREDICATE, FILE_MODE_PREDICATE}
        store.close()

    def test_strict_lets_an_audit_failure_reach_the_caller(self, tmp_path):
        """An approved privileged change that cannot be accounted for must
        not stand: its caller rolls the mode back (R06-F4)."""
        with mock.patch("halbert_core.obs.audit.write_audit",
                        side_effect=RuntimeError("audit sink unavailable")):
            with pytest.raises(RuntimeError):
                record_file_mode_change(
                    path="/etc/x", mode_octal="600", reason="r",
                    actor=ACTOR_USER, request_id="r1", tool="chmod", strict=True,
                )

    def test_without_strict_a_failed_audit_is_only_logged(self, tmp_path):
        """Recording must not break the change it describes, by default."""
        with mock.patch("halbert_core.obs.audit.write_audit",
                        side_effect=RuntimeError("audit sink unavailable")):
            record_file_mode_change(
                path="/etc/x", mode_octal="600", reason="r",
                actor=ACTOR_USER, request_id="r1", tool="chmod",
            )   # must not raise


class TestApprovalExecutionProvenance:
    """The approver's words reach the ledger, and the join survives."""

    def _generator(self, tmpdir):
        from halbert_core.findings.proposal_generator import ProposalGenerator
        from halbert_core.findings.proposals import ProposalStore
        from halbert_core.findings.store import FindingStore

        db = os.path.join(tmpdir, "findings.db")
        wc = mock.MagicMock()
        wc.execute.return_value = mock.MagicMock(ok=True, outputs={"diff": "", "applied": True})
        blast = mock.MagicMock()
        blast.calculate.return_value = mock.MagicMock(
            level="low", score=1, to_dict=lambda: {"level": "low"})
        return ProposalGenerator(
            finding_store=FindingStore(db_path=db),
            proposal_store=ProposalStore(db_path=db),
            approval_engine=mock.MagicMock(),
            write_config=wc,
            blast_radius=blast,
        ), wc

    def test_the_config_branch_passes_the_reason_and_a_shared_request_id(self, tmp_path):
        gen, wc = self._generator(str(tmp_path))
        change = {"action": "edit", "path": "/etc/a.conf", "config_changes": {"a": 1}}

        gen._apply_change(change, [], reason="the approver's own words",
                          request_id="proposal-42")

        req = wc.execute.call_args[0][0]
        assert req.inputs["reason"] == "the approver's own words"
        assert req.inputs["actor"] == ACTOR_USER
        assert req.request_id == "proposal-42", "the join to the approval was severed"

    def test_no_stated_reason_is_unrecorded_not_invented(self, tmp_path):
        gen, wc = self._generator(str(tmp_path))
        gen._apply_change({"action": "edit", "path": "/etc/a.conf",
                           "config_changes": {}}, [], request_id="proposal-1")
        assert wc.execute.call_args[0][0].inputs["reason"] == UNRECORDED

    def test_the_chmod_branch_records_on_the_mode_predicate(self, tmp_path):
        gen, _ = self._generator(str(tmp_path))
        target = tmp_path / "id_rsa"
        target.write_text("key", encoding="utf-8")
        os.chmod(target, 0o644)

        gen._apply_change({"action": "chmod", "path": str(target), "mode": "600"},
                          [], reason="permissions hygiene", request_id="proposal-9")

        store = _ledger()
        rows = store.by_request("proposal-9")
        assert len(rows) == 1
        assert rows[0].predicate == FILE_MODE_PREDICATE
        assert rows[0].reason == "permissions hygiene"
        store.close()


class TestDiffApplyProvenance:
    """Driven through the real route, not by grepping source."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import halbert_core.dashboard.routes.agent as agent_routes
        from halbert_core.agents.conversation_sqlite import SqliteConversationStore
        from halbert_core.agents.threads import ThreadManager
        from halbert_core.intake.signals import analyze_message

        store = SqliteConversationStore(str(tmp_path / "threads.db"))
        tm = ThreadManager(store)
        monkeypatch.setattr(agent_routes, "_thread_manager", lambda: tm)
        monkeypatch.setattr(agent_routes, "_agent_instance", None)
        app = FastAPI()
        app.include_router(agent_routes.router)

        def seed(diffs):
            turn = tm.begin_turn("add a share", analyze_message("add a share"), "sess-1")
            tm.end_turn(turn, assistant_text="here", blocks=[],
                        terminal_block_ids=[], diff_proposals=diffs)

        yield TestClient(app), seed
        store.close()

    def test_applying_a_diff_records_both_planes(self, client, tmp_path):
        api, seed = client
        target = tmp_path / "out" / "smb.conf"
        seed([{"diff_id": "d1", "file_path": str(target),
               "new_content": "[scanner]\n", "status": "pending"}])

        assert api.post("/api/agent/diff/dead-session/d1/apply").status_code == 200
        assert target.read_text() == "[scanner]\n"

        payload = _last_audit()
        assert payload["tool"] == "diff_apply"
        assert payload["request_id"] == "diff-d1"
        assert payload["actor"] == ACTOR_USER
        assert payload["after_sha256"] == content_digest("[scanner]\n")

        store = _ledger()
        rows = store.by_request("diff-d1")
        assert len(rows) == 1
        assert rows[0].predicate == FILE_CONTENT_PREDICATE
        assert rows[0].reason == UNRECORDED    # none stated; never invented
        store.close()

    def test_the_request_id_is_derived_from_the_diff_not_a_uuid(self, client, tmp_path):
        """So a re-apply joins the same rows instead of minting unrelated ones."""
        api, seed = client
        a, b = tmp_path / "a.conf", tmp_path / "b.conf"
        seed([{"diff_id": "d1", "file_path": str(a), "new_content": "1\n", "status": "pending"},
              {"diff_id": "d2", "file_path": str(b), "new_content": "2\n", "status": "pending"}])

        api.post("/api/agent/diff/dead-session/d1/apply")
        api.post("/api/agent/diff/dead-session/d2/apply")

        store = _ledger()
        assert [r.request_id for r in store.by_request("diff-d1")] == ["diff-d1"]
        assert [r.request_id for r in store.by_request("diff-d2")] == ["diff-d2"]
        store.close()

    def test_a_failed_write_does_not_record_a_ledger_row(self, client, tmp_path):
        """/nowhere is unwritable; the record must not claim it landed."""
        api, seed = client
        seed([{"diff_id": "d9", "file_path": "/nowhere/x.conf",
               "new_content": "x", "status": "pending"}])
        api.post("/api/agent/diff/dead-session/d9/apply")

        store = _ledger()
        assert store.by_request("diff-d9") == []
        store.close()


class TestWatcherProvenance:
    """The watcher is Linux-gated, so drive _record_changes directly."""

    def _watcher(self, tmp_path):
        from halbert_core.config.watcher import ConfigWatcher

        w = ConfigWatcher.__new__(ConfigWatcher)
        import collections
        import threading
        w._change_lock = threading.Lock()
        w._changes = collections.deque(maxlen=100)
        w._last_state = {}
        w._baseline_taken = False
        return w

    def test_an_observed_change_reaches_both_planes(self, tmp_path):
        target = tmp_path / "sshd_config"
        target.write_text("PermitRootLogin yes\n", encoding="utf-8")
        w = self._watcher(tmp_path)

        w._record_changes([{"path": str(target), "hash": "h1", "kind": "modified"}])
        target.write_text("PermitRootLogin no\n", encoding="utf-8")
        w._record_changes([{"path": str(target), "hash": "h2", "kind": "modified"}])

        store = _ledger()
        rows = store.current_state(subject=f"file:{target}")
        assert len(rows) == 1
        assert rows[0].actor == ACTOR_SYSTEM
        assert rows[0].reason.startswith("watcher: ")
        store.close()

    def test_the_digest_is_computed_from_the_file_not_the_snapshot_hash(self, tmp_path):
        """config/parser.py's plist branch hashes re-serialised XML, so a
        snapshot hash would differ from ours permanently and every tick
        would supersede the real row with the watcher's reason."""
        target = tmp_path / "a.plist"
        target.write_text("<plist/>\n", encoding="utf-8")
        w = self._watcher(tmp_path)
        w._record_changes([{"path": str(target), "hash": "baseline", "kind": "modified"}])
        w._record_changes([{"path": str(target), "hash": "not-our-digest", "kind": "modified"}])

        store = _ledger()
        rows = store.current_state(subject=f"file:{target}")
        assert rows[0].object == content_digest("<plist/>\n")
        store.close()

    def test_the_baseline_pass_records_nothing(self, tmp_path):
        target = tmp_path / "f.conf"
        target.write_text("a\n", encoding="utf-8")
        w = self._watcher(tmp_path)
        w._record_changes([{"path": str(target), "hash": "h1", "kind": "modified"}])

        store = _ledger()
        assert store.current_state(subject=f"file:{target}") == []
        store.close()

    def test_an_unreadable_file_is_skipped_not_fatal(self, tmp_path):
        w = self._watcher(tmp_path)
        w._record_changes([{"path": "/nope/missing.conf", "hash": "h1", "kind": "modified"}])
        w._record_changes([{"path": "/nope/missing.conf", "hash": "h2", "kind": "modified"}])
        # no exception, and nothing recorded
        store = _ledger()
        assert store.current_state(subject="file:/nope/missing.conf") == []
        store.close()
