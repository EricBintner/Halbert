# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-04: real corruption, and a store that survives meeting it.

The whole packet rests on one fixture. ``_corrupt_fts_for_test`` raised a
mocked exception, so every corruption test in the suite exercised the
error *handler* and none of them exercised what SQLite actually does. The
refuter reproduced the difference: real corruption raises
``sqlite3.DatabaseError('vtable constructor failed')`` -- the PARENT
class -- and the store caught only ``OperationalError``, so it escaped,
``_conn`` was set to None, and the store was bricked on that open and
every reopen after it. The conversation was never recorded again.

Reproduced here deterministically by dropping the ``messages_fts_data``
shadow table, which is what a truncated write or a half-copied file
leaves behind: the ``CREATE VIRTUAL TABLE IF NOT EXISTS`` still succeeds
(so an open looks fine) and the first USE raises.

Recorded while writing this (FD-11's other half): this venv is Python
3.10.9 / SQLite 3.39.4, and ``sqlite3.Exception.sqlite_errorcode`` does
not exist before 3.11 -- so the errorcode arm of any corruption
classifier is dead here, and the message arm is what runs.
"""

import os
import sqlite3

import pytest

from halbert_core.agents.conversation_sqlite import (
    SqliteConversationStore,
    is_structural_corruption,
)


def _store(tmp_path):
    return SqliteConversationStore(db_path=str(tmp_path / "conversations.db"))


def _seed(store, n=5):
    store.create_thread("c1", title="disks")
    for i in range(n):
        store.append_message(
            thread_id="c1", role="user", content=f"message {i} about disks")


def _really_corrupt_fts(path):
    """Drop a shadow table: the shape a truncated write leaves behind."""
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE IF EXISTS messages_fts_data")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# The fixture itself
# ---------------------------------------------------------------------------

def test_the_fixture_produces_a_real_database_error(tmp_path):
    path = str(tmp_path / "c.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE VIRTUAL TABLE messages_fts USING fts5(content)")
    conn.execute("INSERT INTO messages_fts(rowid, content) VALUES (1, 'word')")
    conn.commit()
    conn.close()

    _really_corrupt_fts(path)

    conn = sqlite3.connect(path)
    with pytest.raises(sqlite3.DatabaseError) as excinfo:
        conn.execute(
            "SELECT * FROM messages_fts WHERE messages_fts MATCH 'word'"
        ).fetchall()
    assert "vtable constructor failed" in str(excinfo.value)
    # And it is NOT an OperationalError, which is the whole gap.
    assert not isinstance(excinfo.value, sqlite3.OperationalError)
    conn.close()


# ---------------------------------------------------------------------------
# A08-G1: the corruption predicate matches the origin
# ---------------------------------------------------------------------------

def test_a_structural_message_is_structural():
    assert is_structural_corruption(
        sqlite3.DatabaseError("fts5: corrupt structure at page 4")) is True


def test_a_vtable_failure_is_not_by_itself_structural():
    """The origin's message arm is ``startswith('fts5:') and 'corrupt
    structure'``: a vtable constructor failure is a missing shadow table,
    which a rebuild fixes."""
    assert is_structural_corruption(
        sqlite3.DatabaseError("vtable constructor failed: messages_fts")) is False


def test_an_ordinary_operational_error_is_not_structural():
    assert is_structural_corruption(
        sqlite3.OperationalError("database is locked")) is False


# ---------------------------------------------------------------------------
# A08-G2 + bug 3: the store survives opening over real corruption
# ---------------------------------------------------------------------------

def test_a_store_opens_over_real_corruption(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    path = store.db_path
    store.close()

    _really_corrupt_fts(path)

    reopened = SqliteConversationStore(db_path=path)
    assert reopened.connected is True, "the store must not brick on reopen"


def test_the_canonical_rows_survive(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    path = store.db_path
    store.close()
    _really_corrupt_fts(path)

    reopened = SqliteConversationStore(db_path=path)
    messages = reopened.list_messages("c1")
    assert len(messages) == 5


def test_a_search_over_corruption_returns_something_not_an_exception(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    path = store.db_path
    store.close()
    _really_corrupt_fts(path)

    reopened = SqliteConversationStore(db_path=path)
    # Whatever it returns, it does not raise into the caller.
    assert isinstance(reopened.search("disks"), list)


# ---------------------------------------------------------------------------
# A08-G3 + bug 7: there is a way OUT of fts_degraded
# ---------------------------------------------------------------------------

def test_rebuild_fts_has_a_caller(tmp_path):
    """It had none: the docstring said what it was for and nothing did it,
    so one corrupt write on a Tuesday meant LIKE-only search forever."""
    import inspect

    import halbert_core.agents.conversation_sqlite as store_mod

    source = inspect.getsource(store_mod)
    calls = source.count("rebuild_fts()")
    assert calls >= 2, "rebuild_fts must be called, not only defined"


def test_a_degraded_store_rebuilds_at_open(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    path = store.db_path
    store._enter_fts_fail_open(RuntimeError("test"))
    store.close()

    reopened = SqliteConversationStore(db_path=path)
    assert reopened.fts_degraded is False, (
        "an open over a degraded breadcrumb must try to rebuild"
    )
    assert reopened.healthy is True


def test_search_snippets_falls_back_to_like_while_degraded(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    store._enter_fts_fail_open(RuntimeError("test"))
    hits = store.search_snippets("c1", "disks")
    assert isinstance(hits, list)
    assert hits, "a degraded index must not mean an empty answer"


# ---------------------------------------------------------------------------
# A08-G7 / G8: an open failure is recorded, and a NOT-A-DB file is quarantined
# ---------------------------------------------------------------------------

def test_a_store_that_cannot_open_records_why(tmp_path):
    """A08-G7: ``connected is False`` alone is the same answer for "the
    file is damaged" and "nothing written yet". The store records WHY --
    and, having moved the unreadable file aside, comes up working, which
    is the whole point of quarantining rather than failing forever."""
    bad = tmp_path / "notadb.db"
    bad.write_bytes(b"this is not a database" * 100)
    store = SqliteConversationStore(db_path=str(bad))
    assert store.last_init_error
    assert "SQLite header" in store.last_init_error
    assert store.connected is True


def test_a_not_a_db_file_is_quarantined_never_deleted(tmp_path):
    bad = tmp_path / "conversations.db"
    bad.write_bytes(b"not a database at all" * 100)
    SqliteConversationStore(db_path=str(bad))
    quarantined = list(tmp_path.glob("conversations.db.corrupt-*"))
    assert quarantined, "the unreadable file must be moved aside, not deleted"
    assert quarantined[0].read_bytes().startswith(b"not a database")


def test_a_zeroed_file_is_quarantined_and_the_store_opens(tmp_path):
    zeroed = tmp_path / "conversations.db"
    zeroed.write_bytes(b"\x00" * 8192)
    store = SqliteConversationStore(db_path=str(zeroed))
    assert store.connected is True
    assert list(tmp_path.glob("conversations.db.corrupt-*"))


def test_a_healthy_store_is_never_quarantined(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    store.close()
    SqliteConversationStore(db_path=store.db_path)
    assert not list(tmp_path.glob("conversations.db.corrupt-*"))


# ---------------------------------------------------------------------------
# A08-G12 + bug 4: the default path, and the guard against the real one
# ---------------------------------------------------------------------------

def test_the_default_path_is_refused_under_pytest(monkeypatch):
    """A test that constructs the store with no path used to open the
    OPERATOR'S real conversation database and write into it.

    The guard fires only when nothing has redirected the data directory:
    a suite that sets HALBERT_DATA_DIR is already writing somewhere
    disposable, and refusing there would guard a hazard that is absent.
    """
    monkeypatch.delenv("HALBERT_DATA_DIR", raising=False)
    monkeypatch.delenv("Halbert_DATA_DIR", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        SqliteConversationStore()
    assert "refusing to open the production" in str(excinfo.value)


def test_a_redirected_data_dir_is_not_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path))
    assert SqliteConversationStore().connected is True


def test_the_default_path_resolves_through_the_data_dir(monkeypatch, tmp_path):
    import halbert_core.agents.conversation_sqlite as store_mod
    import halbert_core.utils.paths as paths

    monkeypatch.setattr(paths, "data_dir", lambda: str(tmp_path))
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path))
    assert store_mod._default_db_path() == str(tmp_path / "conversations.db")


def test_an_explicit_path_is_never_refused(tmp_path):
    store = SqliteConversationStore(db_path=str(tmp_path / "explicit.db"))
    assert store.connected is True


# ---------------------------------------------------------------------------
# A16-G4: a newer schema is refused, not migrated backwards
# ---------------------------------------------------------------------------

def test_a_newer_schema_refuses_to_open(tmp_path):
    from halbert_core.agents.conversation_sqlite import SCHEMA_VERSION

    store = _store(tmp_path)
    path = store.db_path
    store.close()

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION + 3,))
    conn.commit()
    conn.close()

    reopened = SqliteConversationStore(db_path=path)
    assert reopened.connected is False
    assert "newer build" in reopened.last_init_error


def test_the_current_schema_still_opens(tmp_path):
    store = _store(tmp_path)
    path = store.db_path
    store.close()
    assert SqliteConversationStore(db_path=path).connected is True


# ---------------------------------------------------------------------------
# A08 bug 2: writers commit inside the lock
# ---------------------------------------------------------------------------

def test_open_loop_writers_commit_inside_the_lock():
    """Thread A's commit used to land thread B's half-built transaction,
    and the second actor is a live route, not a hypothetical."""
    import inspect

    import halbert_core.agents.conversation_sqlite as store_mod

    for name in ("add_open_loop", "close_open_loop"):
        source = inspect.getsource(getattr(store_mod.SqliteConversationStore, name))
        assert "with self._lock, self._conn:" in source, name
        assert "self._conn.commit()" not in source, name


# ---------------------------------------------------------------------------
# A08 bug 5: forget survives a degraded or absent index
# ---------------------------------------------------------------------------

def test_forget_succeeds_while_the_index_is_degraded(tmp_path):
    store = _store(tmp_path)
    store.create_thread("c1", title="t")
    store.append_message(
        thread_id="c1", role="user", content="secret thing",
        metadata={"request_id": "r1"})
    store._enter_fts_fail_open(RuntimeError("degraded"))
    assert store.forget_request("r1") == 1
    assert store.list_messages("c1") == []


def test_forget_reports_zero_rather_than_raising(tmp_path):
    store = _store(tmp_path)
    store.close()
    assert store.forget_request("nothing") == 0


# ---------------------------------------------------------------------------
# A08-G5 (FD-11): the WAL-reset range is said, not silently worked around
# ---------------------------------------------------------------------------

def test_a_vulnerable_sqlite_is_reported_not_worked_around(caplog):
    import halbert_core.agents.conversation_sqlite as store_mod

    store_mod._WAL_WARNED = False
    with caplog.at_level("ERROR"):
        vulnerable = store_mod.warn_if_wal_vulnerable()
    if vulnerable:
        assert "WAL-reset range" in caplog.text
        # And NOT a silent journal-mode change: Hermes falls back to
        # DELETE mode, which would quietly change the durability of the
        # operator's existing database without anyone deciding to.
        assert "NOT being changed" in caplog.text
    else:
        assert caplog.text == ""


def test_the_warning_is_said_once(caplog):
    import halbert_core.agents.conversation_sqlite as store_mod

    store_mod._WAL_WARNED = False
    with caplog.at_level("ERROR"):
        store_mod.warn_if_wal_vulnerable()
        first = caplog.text.count("WAL-reset range")
        store_mod.warn_if_wal_vulnerable()
        store_mod.warn_if_wal_vulnerable()
    assert caplog.text.count("WAL-reset range") == first


def test_this_venvs_sqlite_is_in_the_range():
    """Recorded rather than assumed: 3.39.4 is what FD-11 is about."""
    import sqlite3

    import halbert_core.agents.conversation_sqlite as store_mod

    store_mod._WAL_WARNED = False
    assert store_mod.warn_if_wal_vulnerable() is True, sqlite3.sqlite_version
