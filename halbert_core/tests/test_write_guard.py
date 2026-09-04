# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Look before you write.

open-claude-code refuses to edit a file that has not been read in this
session (``read.mjs:hasBeenRead``, enforced by edit.mjs and write.mjs). For a
coding agent that prevents a clobbered file. For a steward that edits /etc on
the only machine it has, the same class of mistake costs the boot, the
network, or the session it is being used through.

Halbert can do better than a set of paths, and nearly for free: the ledger
already records every file's ``content_sha256``. Comparing the bytes on disk
to the digest the ledger holds is a compare-and-swap that survives a restart,
notices a change made by another process, and can say *when* the file was
last as Halbert remembers it.

This is also where ``continuity/freshness.decide()`` belongs. 82f25ff2 kept
it out of *recall* -- "a recall that silently probed the filesystem would
stop being a ledger read while still answering like one" -- and that argument
is about reading. A write path that probes the host is not a ledger read
pretending to be one; probing is the whole operation.
"""

import pytest

from halbert_core.continuity.provenance import (
    DIGEST_ABSENT,
    FILE_CONTENT_PREDICATE,
    content_digest,
    record_file_change,
    unreadable_digest,
)
from halbert_core.continuity.state_store import ACTOR_AGENT, StateStore
from halbert_core.continuity.write_guard import check_before_write


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "ledger.db"))
    yield s
    s.close()


def _record(store, path, text, reason="because the founder asked"):
    record_file_change(
        path=path, reason=reason, actor=ACTOR_AGENT, request_id="req-1",
        tool="test", before_text=None, after_text=text, store=store,
    )


class TestWhenTheWriteMayProceed:
    def test_a_file_the_ledger_has_never_seen_is_not_blocked(self, store, tmp_path):
        f = tmp_path / "new.conf"
        f.write_text("hello")

        result = check_before_write(str(f), current_text="hello", store=store)

        # Refusing every unrecorded file would make the guard's first act on a
        # new install be to refuse everything.
        assert result.ok is True
        assert result.recorded_digest is None

    def test_content_matching_the_ledger_proceeds(self, store, tmp_path):
        f = tmp_path / "smb.conf"
        f.write_text("[global]\n")
        _record(store, str(f), "[global]\n")

        assert check_before_write(str(f), current_text="[global]\n", store=store).ok is True

    def test_a_file_that_is_gone_and_recorded_gone_proceeds(self, store, tmp_path):
        f = tmp_path / "removed.conf"
        record_file_change(
            path=str(f), reason="deleted", actor=ACTOR_AGENT, request_id="r",
            tool="test", after_text=None, store=store,
        )
        # Recreating a file the ledger knows is absent is not a conflict.
        assert check_before_write(str(f), current_text=None, store=store).ok is True

    def test_an_unreadable_digest_never_blocks(self, store, tmp_path):
        """A root-owned file written through pkexec records an explicit
        unknown. Comparing bytes against "we could not look" and refusing
        would turn an admitted gap into a permanent block."""
        f = tmp_path / "shadow"
        f.write_text("secret")
        store.record_state(
            subject=f"file:{f}", predicate=FILE_CONTENT_PREDICATE,
            obj=unreadable_digest("req-0"), source="test",
            reason="written through pkexec", actor=ACTOR_AGENT, request_id="req-0",
        )

        result = check_before_write(str(f), current_text="secret", store=store)
        assert result.ok is True
        assert "could not be read" in result.detail

    def test_no_ledger_at_all_does_not_block_the_write(self, tmp_path):
        # A machine whose ledger is unavailable can still be administered.
        # The guard is a safety net, not a licence server.
        result = check_before_write(str(tmp_path / "x.conf"), current_text="a", store=None)
        assert result.ok is True


class TestWhenTheWriteIsRefused:
    def test_content_that_drifted_since_the_ledger_saw_it_is_refused(self, store, tmp_path):
        f = tmp_path / "fstab"
        _record(store, str(f), "UUID=old / ext4 defaults 0 1\n",
                reason="added the storage mount")
        f.write_text("UUID=SOMEONE-ELSE / ext4 defaults 0 1\n")

        result = check_before_write(
            str(f), current_text="UUID=SOMEONE-ELSE / ext4 defaults 0 1\n", store=store
        )

        assert result.ok is False
        # The refusal has to be an answer, not a shrug: what Halbert last knew,
        # and why it thought that.
        assert result.recorded_digest == content_digest("UUID=old / ext4 defaults 0 1\n")
        assert result.on_disk_digest == content_digest(
            "UUID=SOMEONE-ELSE / ext4 defaults 0 1\n"
        )
        assert "added the storage mount" in result.detail
        assert "outside Halbert" in result.detail

    def test_a_file_the_ledger_believes_exists_but_is_gone_is_refused(self, store, tmp_path):
        f = tmp_path / "gone.conf"
        _record(store, str(f), "[global]\n")

        result = check_before_write(str(f), current_text=None, store=store)

        assert result.ok is False
        assert "no longer on disk" in result.detail

    def test_a_file_recorded_absent_that_now_exists_is_refused(self, store, tmp_path):
        f = tmp_path / "back.conf"
        store.record_state(
            subject=f"file:{f}", predicate=FILE_CONTENT_PREDICATE,
            obj=DIGEST_ABSENT, source="test", reason="removed by the admin",
            actor=ACTOR_AGENT, request_id="r",
        )
        f.write_text("someone put it back")

        result = check_before_write(str(f), current_text="someone put it back", store=store)

        assert result.ok is False
        assert "recorded as absent" in result.detail


class TestTheGuardNeverBreaksTheWrite:
    def test_a_ledger_that_raises_does_not_stop_an_administrator(self, tmp_path):
        class _Boom:
            def current_state(self, **kw):
                raise RuntimeError("db is gone")

        result = check_before_write(str(tmp_path / "x"), current_text="a", store=_Boom())

        # A guard that fails closed turns a database problem into an
        # unadministrable machine.
        assert result.ok is True
        assert "could not be checked" in result.detail
