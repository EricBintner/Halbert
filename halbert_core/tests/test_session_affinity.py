# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for SessionAffinityRouter (F2)."""

import pytest

from halbert_core.agents.session_affinity import SessionAffinityRouter, SessionAffinity
from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    # seed conversations (append_message is the only message write path)
    s.create("disk-conv", "u1")
    s.append_message("disk-conv", "user", "my disk is filling up on /var")
    s.append_message("disk-conv", "assistant", "run du -sh /var/log", origin="assistant")

    s.create("network-conv", "u1")
    s.append_message("network-conv", "user", "the nginx firewall is blocking traffic")
    s.append_message("network-conv", "assistant", "check ufw status", origin="assistant")

    s.create("cpu-conv", "u1")
    s.append_message("cpu-conv", "user", "cpu load is very high")
    yield s
    s.close()


@pytest.fixture
def router(store):
    return SessionAffinityRouter(store)


# ---------------------------------------------------------------------------
# Tier 1: explicit reference
# ---------------------------------------------------------------------------

class TestExplicit:
    def test_explicit_session_id(self, router, store):
        aff = router.route("let's continue session disk-conv", current_session_id="other")
        assert aff.tier == "explicit"
        assert aff.session_id == "disk-conv"
        assert aff.confidence >= 0.9

    def test_explicit_conversation_id(self, router):
        aff = router.route("open conversation network-conv please")
        assert aff.tier == "explicit"
        assert aff.session_id == "network-conv"

    def test_explicit_reference_unknown_id_falls_through(self, router):
        # references a session id that doesn't exist -> not explicit
        aff = router.route("session does-not-exist about disks")
        # falls to FTS (disks) or current
        assert aff.tier in ("fts", "current")

    def test_no_explicit_reference(self, router):
        aff = router.route("how is my disk usage?")
        assert aff.tier != "explicit"


# ---------------------------------------------------------------------------
# Tier 2: FTS5 search
# ---------------------------------------------------------------------------

class TestFTS:
    def test_fts_matches_relevant_conversation(self, router):
        aff = router.route("what about the nginx firewall config?")
        assert aff.tier == "fts"
        assert aff.session_id == "network-conv"
        assert "network-conv" in aff.candidates

    def test_fts_disk_match(self, router):
        aff = router.route("tell me about my disk filling up")
        assert aff.tier == "fts"
        assert aff.session_id == "disk-conv"

    def test_fts_excludes_current_session(self, router):
        # current session should not be rediscovered as the FTS hit
        aff = router.route("nginx firewall", current_session_id="network-conv")
        # network-conv is current -> excluded; falls to current (no other nginx conv)
        # (or another hit if any). At minimum, not network-conv as an FTS discovery.
        if aff.tier == "fts":
            assert aff.session_id != "network-conv"

    def test_fts_no_match_falls_to_current(self, router):
        aff = router.route("zzzztotallyunrelatedterm", current_session_id="cur")
        assert aff.tier == "current"
        assert aff.session_id == "cur"


# ---------------------------------------------------------------------------
# Tier 3: current session
# ---------------------------------------------------------------------------

class TestCurrent:
    def test_empty_query_current(self, router):
        aff = router.route("", current_session_id="cur")
        assert aff.tier == "current"
        assert aff.session_id == "cur"

    def test_no_current_session_returns_none_id(self, router):
        aff = router.route("zzzzunrelatedterm")
        assert aff.tier == "current"
        assert aff.session_id is None


# ---------------------------------------------------------------------------
# Confidence ordering
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_explicit_higher_than_fts(self, router):
        explicit = router.route("session disk-conv")
        fts = router.route("disk filling up")
        assert explicit.confidence > fts.confidence

    def test_fts_higher_than_current(self, router):
        fts = router.route("nginx firewall")
        cur = router.route("zzzzunrelated", current_session_id="c")
        assert fts.confidence > cur.confidence


# ---------------------------------------------------------------------------
# Works with the JSON ConversationStore too (duck-typed)
# ---------------------------------------------------------------------------

def test_works_with_json_store(tmp_path):
    from halbert_core.agents.conversation import ConversationStore
    json_store = ConversationStore(storage_path=str(tmp_path))
    c = json_store.create("json-conv", "u1")
    c.add_message("user", "configure the nginx web server")
    json_store.save(c)

    router = SessionAffinityRouter(json_store)
    aff = router.route("tell me about nginx")
    assert aff.tier == "fts"
    assert aff.session_id == "json-conv"
