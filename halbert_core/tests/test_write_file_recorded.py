# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The agent's own write tool records what it did.

LEDGER-1's premise is that the ledger can answer, for any config the machine
has touched, what it is now and why. ``write_file`` is the tool the agent
actually writes files with -- it is in the schema list handed to the model --
and it wrote to any path on the machine while recording nothing: no audit
row, no ledger triple, no reason, no actor, no backup, and no check that the
file was still what Halbert last saw.

Four write paths called ``record_file_change``. This was the fifth, and it
was the one the agent uses.
"""

import asyncio
import os

import pytest

from halbert_core.continuity.provenance import FILE_CONTENT_PREDICATE, content_digest
from halbert_core.continuity.state_store import ACTOR_AGENT, UNRECORDED, StateStore
from halbert_core.tools.executor import ToolExecutor


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """The real store, in a temp data dir.

    Passing a store in through the tool's own args would be a test-only
    parameter on a production interface -- and it would mean the thing under
    test is never the thing that ships. HALBERT_DATA_DIR is the seam the
    ledger already honours.
    """
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))


@pytest.fixture
def store():
    from halbert_core.continuity.state_store import default_state_db_path

    s = StateStore(db_path=str(default_state_db_path()))
    yield s
    s.close()


def _write(path, content, **extra):
    ex = ToolExecutor()
    args = {"path": str(path), "content": content}
    args.update(extra)
    return asyncio.run(ex._write_file(args))


def _current(store, path):
    rows = store.current_state(subject=f"file:{path}", predicate=FILE_CONTENT_PREDICATE)
    return rows[0] if rows else None


class TestItRecordsWhatItDid:
    def test_a_write_lands_on_the_ledger_with_its_digest(self, store, tmp_path):
        f = tmp_path / "smb.conf"
        _write(f, "[global]\n", reason="added the backups share")

        triple = _current(store, f)
        assert triple is not None, "the write left no record on the ledger"
        assert triple.object == content_digest("[global]\n")
        assert triple.actor == ACTOR_AGENT
        assert triple.reason == "added the backups share"

    def test_a_write_with_no_stated_reason_records_an_admitted_unknown(self, store, tmp_path):
        f = tmp_path / "x.conf"
        _write(f, "a\n")

        # Never a generated rationale: the ledger's whole contract is that a
        # reason is either stated by the turn that caused the write, or it is
        # explicitly unknown.
        assert _current(store, f).reason == UNRECORDED

    def test_the_second_write_supersedes_the_first(self, store, tmp_path):
        f = tmp_path / "x.conf"
        _write(f, "one\n", reason="first")
        _write(f, "two\n", reason="second")

        assert _current(store, f).object == content_digest("two\n")
        history = store.state_history(f"file:{f}", FILE_CONTENT_PREDICATE)
        assert [t.reason for t in history] == ["first", "second"]

    def test_an_append_records_the_whole_resulting_file(self, store, tmp_path):
        f = tmp_path / "x.conf"
        f.write_text("one\n")
        _write(f, "two\n", append=True, reason="appended")

        # The digest is of what is now on disk, not of what was appended.
        assert _current(store, f).object == content_digest("one\ntwo\n")

    def test_the_file_is_still_written(self, tmp_path, store):
        f = tmp_path / "x.conf"
        _write(f, "content\n", reason="r")
        assert f.read_text() == "content\n"


class TestItLooksBeforeItWrites:
    def test_a_file_that_drifted_is_refused_and_left_alone(self, store, tmp_path):
        f = tmp_path / "fstab"
        _write(f, "UUID=one\n", reason="added the storage mount")
        # Something else edits it.
        f.write_text("UUID=someone-else\n")

        result = _write(f, "UUID=two\n", reason="changing it again")

        assert "changed outside Halbert" in result
        assert "added the storage mount" in result
        # And the other change is still there.
        assert f.read_text() == "UUID=someone-else\n"

    def test_a_refusal_does_not_touch_the_ledger(self, store, tmp_path):
        f = tmp_path / "fstab"
        _write(f, "UUID=one\n", reason="first")
        f.write_text("UUID=someone-else\n")
        _write(f, "UUID=two\n", reason="second")

        # A refused write did not happen, so it is not a change.
        assert _current(store, f).object == content_digest("UUID=one\n")
        assert _current(store, f).reason == "first"

    def test_an_unrecorded_file_is_not_blocked(self, store, tmp_path):
        f = tmp_path / "brand-new.conf"
        f.write_text("someone made this\n")

        _write(f, "and Halbert changed it\n", reason="asked to")

        assert f.read_text() == "and Halbert changed it\n"

    def test_a_broken_ledger_does_not_stop_the_write(self, tmp_path, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("db gone")

        monkeypatch.setattr(
            "halbert_core.continuity.state_store.StateStore", boom
        )
        f = tmp_path / "x.conf"
        _write(f, "written anyway\n", reason="r")

        # A guard that fails closed turns a database problem into an
        # unadministrable machine.
        assert f.read_text() == "written anyway\n"
