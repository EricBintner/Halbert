# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A2 wiring: the two live recall sites record persisted promotion signals.

The rule under test is not that signals get written — it is that a *recall
that actually surfaced something* is usage evidence, recorded where it
happens, persisted next to the ledger, and never allowed to break the turn
or the tool answer it rode in on (memory failures never eat a turn).
"""

import asyncio
import os
from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.continuity import promotion
from halbert_core.continuity.promotion import PromotionStore
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 8, 26, 12, 0).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def promotion_store(tmp_path, monkeypatch):
    """A temp-DB promotion store installed as the process-wide singleton."""
    store = PromotionStore(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(promotion, "_store", store)
    yield store


def _turn(tm, text, session, assistant="ok"):
    turn = tm.begin_turn(text, analyze_message(text), session)
    tm.end_turn(turn, assistant_text=assistant, blocks=[],
                terminal_block_ids=[], diff_proposals=[])
    return turn


class TestThreadAutoRecallRecordsSignals:
    def test_a_recalled_thread_produces_persisted_signals(self, promotion_store):
        s = SqliteConversationStore(":memory:")
        clock = Clock(NOW)
        tm = ThreadManager(s, now=clock)
        t1 = _turn(tm, "add a samba share for the media folder", "s1",
                   assistant="Added [media] at /srv/media.")
        clock.advance(3 * 3600)
        _turn(tm, "check the disk space on /var", "s2")
        assert s.update_thread(t1.thread_id, status="closed") is True
        text = "add another share like we did for the media one"
        turn3 = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn3.recalled, "precondition: the strong-match auto-recall fired"

        sig = promotion_store.signals((f"thread:{t1.thread_id}", "recalled"))
        assert sig is not None
        assert sig.recall_count == 1
        assert sig.query_diversity == 1
        # the gate score rides along as usage evidence
        assert 0.0 < sig.avg_score <= 1.0

    def test_same_day_repeat_of_same_query_does_not_inflate_diversity(
            self, promotion_store):
        s = SqliteConversationStore(":memory:")
        clock = Clock(NOW)
        tm = ThreadManager(s, now=clock)
        t1 = _turn(tm, "add a samba share for the media folder", "s1")
        clock.advance(3 * 3600)
        _turn(tm, "check the disk space on /var", "s2")
        assert s.update_thread(t1.thread_id, status="closed") is True
        text = "add another share like we did for the media one"
        turn = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn.recalled
        turn = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn.recalled

        sig = promotion_store.signals((f"thread:{t1.thread_id}", "recalled"))
        assert sig.recall_count == 2       # both recalls happened
        assert sig.query_diversity == 1    # same query: diversity does not move


class TestRecallMemoryToolRecordsSignals:
    @pytest.fixture(autouse=True)
    def _isolated_ledger(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
        from halbert_core.obs.audit import set_audit_signer
        set_audit_signer(None)
        yield
        set_audit_signer(None)

    def _seed_ledger(self):
        from halbert_core.continuity.provenance import record_file_change
        from halbert_core.continuity.state_store import ACTOR_AGENT
        record_file_change(path="/etc/ssh/sshd_config",
                           reason="hardening after the audit finding",
                           actor=ACTOR_AGENT, request_id="r1", tool="editor",
                           after_text="PermitRootLogin no\n")

    def _call(self, **args):
        from halbert_core.tools.recall_memory import recall_memory
        return asyncio.run(recall_memory(args))

    def test_a_recall_memory_call_produces_persisted_signals(
            self, promotion_store):
        self._seed_ledger()
        out = self._call(path="/etc/ssh/sshd_config",
                         query="why is root login off")
        assert "hardening after the audit finding" in out

        sig = promotion_store.signals(("file:/etc/ssh/sshd_config",
                                       "content_sha256"))
        assert sig is not None
        assert sig.recall_count == 1
        assert sig.query_diversity == 1

    def test_same_args_again_raise_count_not_diversity(self, promotion_store):
        self._seed_ledger()
        self._call(path="/etc/ssh/sshd_config")
        self._call(path="/etc/ssh/sshd_config")

        sig = promotion_store.signals(("file:/etc/ssh/sshd_config",
                                       "content_sha256"))
        assert sig.recall_count == 2
        assert sig.query_diversity == 1


class TestPersistence:
    def test_signals_survive_a_new_store_over_the_same_db(self, tmp_path):
        db = str(tmp_path / "state.db")
        s1 = PromotionStore(db_path=db)
        key = ("subject:scanner", "predicate:config")
        s1.record_recall(key, query="how is the scanner set up")
        s1.record_recall(key, query="scanner keeps dropping off wifi")
        s1.close()

        s2 = PromotionStore(db_path=db)
        sig = s2.signals(key)
        assert sig is not None
        assert sig.recall_count == 2
        assert sig.query_diversity == 2
        assert sig.recall_days == 1

        # a later store keeps growing the same signal from the persisted set
        s2.record_recall(key, query="scanner wifi fix")
        sig = s2.signals(key)
        assert sig.recall_count == 3
        assert sig.query_diversity == 3
        s2.close()

    def test_multi_day_recurrence_survives_restart(self, tmp_path):
        db = str(tmp_path / "state.db")
        s1 = PromotionStore(db_path=db)
        key = ("subject:printer", "predicate:state")
        s1.record_recall(key, query="printer status", days_ago=3)
        s1.record_recall(key, query="printer offline again", days_ago=1)
        s1.close()

        s2 = PromotionStore(db_path=db)
        assert s2.signals(key).recall_days == 2
        s2.close()


class TestFailSoft:
    @pytest.mark.skipif(
        os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        reason="root ignores directory permission bits",
    )
    def test_unwritable_promotion_db_degrades_to_memory(self, tmp_path):
        ro = tmp_path / "readonly"
        ro.mkdir()
        ro.chmod(0o555)
        store = PromotionStore(db_path=str(ro / "state.db"))
        key = ("subject:x", "predicate:p")
        store.record_recall(key, query="a")
        store.record_recall(key, query="b")
        assert store.signals(key).recall_count == 2
        store.close()

    @pytest.mark.skipif(
        os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        reason="root ignores directory permission bits",
    )
    def test_recall_memory_succeeds_with_the_promotion_db_unwritable(
            self, tmp_path, monkeypatch):
        """The fail-soft proof: an unwritable promotion DB must never eat a
        tool answer or a turn."""
        ro = tmp_path / "readonly"
        ro.mkdir()
        ro.chmod(0o555)
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
        # The singleton has not been built yet: let get_promotion_store aim
        # it at the read-only directory.
        monkeypatch.setattr(promotion, "_store", None)
        monkeypatch.setattr(promotion, "default_state_db_path",
                            lambda: ro / "state.db")
        from halbert_core.obs.audit import set_audit_signer
        set_audit_signer(None)
        try:
            from halbert_core.continuity.provenance import record_file_change
            from halbert_core.continuity.state_store import ACTOR_AGENT
            record_file_change(path="/etc/ssh/sshd_config", reason="hardened",
                               actor=ACTOR_AGENT, request_id="r1",
                               tool="editor", after_text="PermitRootLogin no\n")
            from halbert_core.tools.recall_memory import recall_memory
            out = asyncio.run(recall_memory({"path": "/etc/ssh/sshd_config"}))
            assert "hardened" in out
        finally:
            set_audit_signer(None)