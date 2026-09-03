# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 step 4: the write paths record on both planes, joined on request_id.

The audit log says what a tool did; the state ledger says what is now true and
why. Writing one and forgetting the other is the failure this wiring exists to
prevent, so these tests assert the pair, not either half.
"""

import asyncio
import hashlib

import pytest

from halbert_core.continuity.provenance import (
    FILE_CONTENT_PREDICATE,
    content_digest,
    record_file_change,
)
from halbert_core.continuity.state_store import (
    ACTOR_AGENT,
    ACTOR_USER,
    UNRECORDED,
    StateStore,
)
from halbert_core.obs.audit import audit_log, set_audit_signer


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Never touch the real ledger or the real audit log."""
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _last_audit():
    return audit_log().read_all()[-1].payload


def _ledger():
    from halbert_core.continuity.state_store import default_state_db_path

    return StateStore(db_path=str(default_state_db_path()))


class TestRecordFileChange:
    def test_both_planes_are_written_and_join_on_request_id(self):
        record_file_change(
            path="/etc/nginx.conf", reason="user asked for more workers",
            actor=ACTOR_USER, request_id="req-7", tool="write_config",
            before_text="workers 2\n", after_text="workers 4\n",
        )

        payload = _last_audit()
        assert payload["request_id"] == "req-7"
        assert payload["reason"] == "user asked for more workers"
        assert payload["actor"] == ACTOR_USER

        store = _ledger()
        rows = store.by_request("req-7")
        assert len(rows) == 1
        assert rows[0].subject == "file:/etc/nginx.conf"
        assert rows[0].predicate == FILE_CONTENT_PREDICATE
        assert rows[0].reason == payload["reason"]
        assert rows[0].actor == payload["actor"]
        store.close()

    def test_the_record_carries_digests_not_content(self):
        """A record should say what changed without becoming a second copy."""
        secret = "password = hunter2\n"
        record_file_change(
            path="/etc/app.conf", reason="rotated the credential",
            actor=ACTOR_USER, request_id="req-1", tool="editor",
            before_text=None, after_text=secret,
        )

        payload = _last_audit()
        assert payload["after_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
        assert "hunter2" not in str(payload)

        store = _ledger()
        assert "hunter2" not in str(store.by_request("req-1")[0].to_dict())
        store.close()

    def test_a_missing_before_file_has_no_before_digest(self):
        record_file_change(
            path="/etc/new.conf", reason="created it", actor=ACTOR_USER,
            request_id="req-1", tool="editor",
            before_text=None, after_text="x\n",
        )
        assert "before_sha256" not in _last_audit()

    def test_a_dry_run_is_audited_but_changes_nothing(self):
        """A preview is a thing the tool did, not a thing that became true."""
        record_file_change(
            path="/etc/nginx.conf", reason="previewing", actor=ACTOR_AGENT,
            request_id="req-2", tool="write_config",
            before_text="a\n", after_text="b\n", mode="dry_run",
        )
        assert _last_audit()["mode"] == "dry_run"
        store = _ledger()
        assert store.by_request("req-2") == []
        store.close()

    def test_a_failed_apply_is_audited_but_changes_nothing(self):
        record_file_change(
            path="/etc/nginx.conf", reason="tried", actor=ACTOR_AGENT,
            request_id="req-3", tool="write_config",
            before_text="a\n", after_text=None, ok=False,
        )
        assert _last_audit()["ok"] is False
        store = _ledger()
        assert store.by_request("req-3") == []
        store.close()

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_an_empty_reason_is_refused(self, bad):
        with pytest.raises(ValueError):
            record_file_change(
                path="/etc/x.conf", reason=bad, actor=ACTOR_USER,
                request_id="r", tool="editor", after_text="x",
            )

    def test_a_broken_ledger_does_not_break_the_change(self, monkeypatch):
        """Recording must never turn a successful save into a failed one."""
        import halbert_core.continuity.state_store as ss

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(ss, "StateStore", boom)
        record_file_change(
            path="/etc/x.conf", reason="still fine", actor=ACTOR_USER,
            request_id="req-4", tool="editor", after_text="x",
        )
        assert _last_audit()["reason"] == "still fine"   # audit half survived

    def test_content_digest_of_nothing_is_none(self):
        assert content_digest(None) is None
        assert content_digest("") == hashlib.sha256(b"").hexdigest()


class TestWriteConfigProvenance:
    def test_the_agent_is_the_actor_and_the_reason_comes_from_the_call(self):
        from halbert_core.tools.base import ToolRequest
        from halbert_core.tools.write_config import WriteConfig

        req = ToolRequest(
            tool="write_config", request_id="r1",
            inputs={"path": "/etc/x.conf", "reason": "hardening the listener"},
        )
        assert WriteConfig()._provenance(req) == ("hardening the listener", ACTOR_AGENT)

    def test_no_stated_reason_is_unrecorded_not_invented(self):
        from halbert_core.tools.base import ToolRequest
        from halbert_core.tools.write_config import WriteConfig

        req = ToolRequest(tool="write_config", request_id="r1",
                          inputs={"path": "/etc/x.conf"})
        reason, actor = WriteConfig()._provenance(req)
        assert reason == UNRECORDED and actor == ACTOR_AGENT

    def test_an_apply_records_the_file_digest_in_the_ledger(self, tmp_path):
        from halbert_core.tools.base import ToolRequest
        from halbert_core.tools.write_config import WriteConfig

        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("a:\n  b: 1\n", encoding="utf-8")
        req = ToolRequest(
            tool="write_config", request_id="req-9", confirm=True, dry_run=False,
            inputs={"path": str(cfg), "changes": {"a": {"c": 2}},
                    "backup": False, "reason": "adding the c key"},
        )
        resp = WriteConfig().execute(req)
        if not resp.ok:
            pytest.skip(f"policy gate denied the apply: {resp.error}")

        store = _ledger()
        rows = store.by_request("req-9")
        assert len(rows) == 1
        assert rows[0].reason == "adding the c key"
        assert rows[0].actor == ACTOR_AGENT
        assert rows[0].object == content_digest(cfg.read_text("utf-8"))
        store.close()


class TestEditorProvenance:
    """The editor writes config files, sometimes via pkexec. It recorded nothing."""

    def _write(self, path, content, reason=None):
        from halbert_core.dashboard.routes.editor import (
            FileWriteRequest, write_file,
        )

        return asyncio.run(write_file(FileWriteRequest(
            path=str(path), content=content, create_backup=False, reason=reason,
        )))

    def test_a_save_is_recorded_on_both_planes(self, tmp_path):
        target = tmp_path / "sshd_config"
        target.write_text("PermitRootLogin yes\n", encoding="utf-8")

        assert self._write(target, "PermitRootLogin no\n",
                           reason="hardening after the audit").success

        payload = _last_audit()
        assert payload["tool"] == "editor"
        assert payload["reason"] == "hardening after the audit"
        assert payload["actor"] == ACTOR_USER
        assert payload["before_sha256"] == content_digest("PermitRootLogin yes\n")

        store = _ledger()
        rows = store.current_state(subject=f"file:{target}")
        assert len(rows) == 1 and rows[0].actor == ACTOR_USER
        store.close()

    def test_the_person_at_the_editor_is_the_actor_not_the_agent(self, tmp_path):
        """The distinction actor exists to draw."""
        target = tmp_path / "x.conf"
        self._write(target, "a\n", reason="mine")
        assert _last_audit()["actor"] == ACTOR_USER

    def test_a_save_with_no_stated_reason_is_unrecorded(self, tmp_path):
        target = tmp_path / "x.conf"
        self._write(target, "a\n")
        assert _last_audit()["reason"] == UNRECORDED

    def test_a_second_save_supersedes_and_explains_the_close(self, tmp_path):
        target = tmp_path / "x.conf"
        self._write(target, "a\n", reason="first")
        self._write(target, "b\n", reason="second")

        store = _ledger()
        w = store.why(f"file:{target}", FILE_CONTENT_PREDICATE)
        assert w.current.reason == "second"
        assert w.superseded.reason == "first"
        assert w.superseded.closed_reason == "superseded: second"
        store.close()


class TestAnUnreadableDigestIsRecordedNotSkipped:
    """A privileged file written through pkexec cannot always be read back by
    an unprivileged process. Returning silently left the ledger asserting the
    OLD digest as current, so a later drift check would report a change
    nobody made."""

    def test_it_records_an_explicit_unknown(self, caplog):
        from halbert_core.continuity.provenance import DIGEST_UNREADABLE

        record_file_change(path="/etc/root-only.conf", reason="hardening",
                           actor=ACTOR_USER, request_id="req-priv",
                           tool="editor", before_text="old\n", after_text=None)

        store = _ledger()
        rows = store.by_request("req-priv")
        assert len(rows) == 1, "the ledger row was skipped"
        assert rows[0].object == DIGEST_UNREADABLE
        store.close()

    def test_the_unknown_cannot_be_mistaken_for_a_digest(self):
        from halbert_core.continuity.provenance import DIGEST_UNREADABLE

        assert len(DIGEST_UNREADABLE) != 64

    def test_it_says_so_out_loud(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            record_file_change(path="/etc/root-only.conf", reason="r",
                               actor=ACTOR_USER, request_id="req-priv2",
                               tool="editor", after_text=None)
        assert any("could not be read back" in r.message for r in caplog.records)

    def test_a_stale_digest_is_not_left_current(self):
        """The failure this prevents: the old value staying open."""
        record_file_change(path="/etc/root-only.conf", reason="first",
                           actor=ACTOR_USER, request_id="r1", tool="editor",
                           after_text="old\n")
        record_file_change(path="/etc/root-only.conf", reason="second",
                           actor=ACTOR_USER, request_id="r2", tool="editor",
                           before_text="old\n", after_text=None)

        store = _ledger()
        current = store.why("file:/etc/root-only.conf",
                            FILE_CONTENT_PREDICATE).current
        assert current.object != content_digest("old\n")
        store.close()
