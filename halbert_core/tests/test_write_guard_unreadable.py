# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
""""Cannot read it" is not "it is gone".

``check_before_write`` took ``current_text=None`` to mean the file is absent,
and all three callers returned None both when the file was missing and when
the read was refused. So a root-owned file the agent could not read was
reported as "removed outside Halbert" and the write was refused -- which made
the privileged save path, the case the config editor exists for, unreachable
behind a refusal that said something untrue.

The fix is not a probe. ``os.path.exists`` swallows the PermissionError from
an unreadable parent directory and answers False for a file that is plainly
there; ``os.path.lexists`` answers True for a dangling symlink, which is the
one case that really is gone. ``open`` separates all three, so the reader
reports which kind of nothing it found.
"""

import os

import pytest

from halbert_core.continuity.provenance import (
    DIGEST_ABSENT,
    FILE_CONTENT_PREDICATE,
    content_digest,
)
from halbert_core.continuity.recall import subject_for_path
from halbert_core.continuity.state_store import StateStore
from halbert_core.continuity.write_guard import check_before_write, read_for_guard

pytestmark = pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads everything; the refusal cannot be staged"
)


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "state.db"))
    yield s
    s.close()


def _record(store, path, digest, reason="hardened by the founder"):
    store.record_state(
        subject=subject_for_path(path),
        predicate=FILE_CONTENT_PREDICATE,
        obj=digest,
        source="test",
        reason=reason,
        actor="test",
        request_id="req-1",
    )


class TestTheReaderSaysWhichKindOfNothing:
    def test_a_missing_file_is_absent_not_unreadable(self, tmp_path):
        text, unreadable = read_for_guard(str(tmp_path / "nope.conf"))
        assert (text, unreadable) == (None, False)

    def test_a_dangling_symlink_is_absent(self, tmp_path):
        """The shape of /etc/resolv.conf -> a target that is gone.

        ``lexists`` answers True here, which is why it is the wrong probe:
        this file really has been removed.
        """
        link = tmp_path / "resolv.conf"
        link.symlink_to(tmp_path / "gone")
        assert os.path.lexists(link) and not os.path.exists(link)
        assert read_for_guard(str(link)) == (None, False)

    def test_a_file_we_may_not_read_is_unreadable(self, tmp_path):
        p = tmp_path / "sshd_config"
        p.write_text("PermitRootLogin no\n")
        p.chmod(0o000)
        try:
            assert read_for_guard(str(p)) == (None, True)
        finally:
            p.chmod(0o600)

    def test_a_file_behind_a_closed_directory_is_unreadable(self, tmp_path):
        """``/etc/ssl/private``, mode 0700, is the canonical case.

        ``os.path.exists`` answers False here -- it swallows the
        PermissionError -- so no probe could have told this from absence.
        """
        d = tmp_path / "private"
        d.mkdir()
        p = d / "server.key"
        p.write_text("-----BEGIN PRIVATE KEY-----\n")
        d.chmod(0o000)
        try:
            assert not os.path.exists(p)
            assert read_for_guard(str(p)) == (None, True)
        finally:
            d.chmod(0o700)


class TestTheGuardDoesNotCallItRemoved:
    def test_an_unreadable_file_does_not_block_the_write(self, store, tmp_path):
        p = tmp_path / "sshd_config"
        p.write_text("PermitRootLogin no\n")
        _record(store, str(p), content_digest("PermitRootLogin no\n"))
        text, unreadable = (None, True)  # what read_for_guard returns at 0o000
        result = check_before_write(
            str(p), current_text=text, unreadable=unreadable, store=store)
        assert result.ok is True
        assert "removed outside Halbert" not in result.detail

    def test_a_genuinely_removed_file_is_still_refused(self, store, tmp_path):
        """The refusal the guard gets right must survive the fix."""
        p = tmp_path / "sshd_config"
        _record(store, str(p), content_digest("PermitRootLogin no\n"))
        result = check_before_write(
            str(p), current_text=None, unreadable=False, store=store)
        assert result.ok is False
        assert "removed outside Halbert" in result.detail

    def test_absent_in_the_ledger_and_unreadable_is_not_confirmed(self, store, tmp_path):
        """The second branch, which the first pass at this fix left alone.

        The ledger says absent; the file is there but shut. Answering "and it
        is" asserts the opposite of the truth, which is the failure mode this
        module exists to prevent.
        """
        p = tmp_path / "new.conf"
        _record(store, str(p), DIGEST_ABSENT)
        result = check_before_write(
            str(p), current_text=None, unreadable=True, store=store)
        assert result.ok is True
        assert "and it is" not in result.detail
        assert "could not be read" in result.detail
