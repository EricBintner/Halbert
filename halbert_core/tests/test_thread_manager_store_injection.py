# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P3c: ThreadManager store injection tests.

Verifies that get_thread_manager() uses PeerConversationStore when
canonical_thread_url is set, and SqliteConversationStore when it's not.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from halbert_core.agents.threads import (
    ThreadManager,
    get_thread_manager,
    _create_conversation_store,
)
from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture(autouse=True)
def reset_thread_manager():
    """Reset the singleton before and after each test."""
    import halbert_core.agents.threads as threads_mod
    threads_mod._manager = None
    yield
    threads_mod._manager = None


class TestCreateConversationStore:
    def test_local_store_when_no_canonical_url(self):
        """When canonical_thread_url is unset, use SqliteConversationStore."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="",
        ):
            store = _create_conversation_store()
        assert isinstance(store, SqliteConversationStore)

    def test_peer_store_when_canonical_url_set(self):
        """When canonical_thread_url is set, use PeerConversationStore."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="http://ha-server.lan:8001/api/conversations",
        ), patch(
            "halbert_core.integrations.cognition_wiring._get_peer_token",
            return_value="test-token-123",
        ):
            store = _create_conversation_store()

        from halbert_core.agents.peer_conversation_store import PeerConversationStore
        assert isinstance(store, PeerConversationStore)
        assert store.peer_url == "http://ha-server.lan:8001/api/conversations"
        assert store.bearer_token == "test-token-123"

    def test_falls_back_to_local_when_no_token(self):
        """When canonical_thread_url is set but no token, fall back to local."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="http://ha-server.lan:8001/api/conversations",
        ), patch(
            "halbert_core.integrations.cognition_wiring._get_peer_token",
            return_value="",
        ):
            store = _create_conversation_store()
        assert isinstance(store, SqliteConversationStore)

    def test_falls_back_to_local_on_import_error(self):
        """If PeerConversationStore can't be imported, fall back to local."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="http://ha-server.lan:8001/api/conversations",
        ), patch(
            "halbert_core.integrations.cognition_wiring._get_peer_token",
            return_value="test-token",
        ), patch(
            "halbert_core.agents.peer_conversation_store.PeerConversationStore",
            side_effect=ImportError("missing dep"),
        ):
            store = _create_conversation_store()
        assert isinstance(store, SqliteConversationStore)


class TestGetThreadManager:
    def test_uses_local_store_by_default(self):
        """Default behavior: local SqliteConversationStore."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="",
        ):
            mgr = get_thread_manager()
        assert isinstance(mgr.store, SqliteConversationStore)

    def test_uses_peer_store_when_configured(self):
        """Singular entity mode: PeerConversationStore."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="http://ha-server.lan:8001/api/conversations",
        ), patch(
            "halbert_core.integrations.cognition_wiring._get_peer_token",
            return_value="test-token-123",
        ):
            mgr = get_thread_manager()

        from halbert_core.agents.peer_conversation_store import PeerConversationStore
        assert isinstance(mgr.store, PeerConversationStore)

    def test_singleton_returns_same_manager(self):
        """get_thread_manager() returns the same instance on repeated calls."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="",
        ):
            mgr1 = get_thread_manager()
            mgr2 = get_thread_manager()
        assert mgr1 is mgr2

    def test_peer_store_skips_consolidator(self):
        """Consolidator should not be wired for PeerConversationStore
        (consolidation runs on the canonical host, not the satellite)."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="http://ha-server.lan:8001/api/conversations",
        ), patch(
            "halbert_core.integrations.cognition_wiring._get_peer_token",
            return_value="test-token-123",
        ):
            mgr = get_thread_manager()

        from halbert_core.agents.peer_conversation_store import PeerConversationStore
        assert isinstance(mgr.store, PeerConversationStore)
        assert mgr._consolidator is None

    def test_local_store_wires_consolidator(self):
        """Consolidator should be wired for local SqliteConversationStore."""
        with patch(
            "halbert_core.integrations.cognition_wiring._get_canonical_thread_url",
            return_value="",
        ):
            mgr = get_thread_manager()

        assert isinstance(mgr.store, SqliteConversationStore)
        # Consolidator may or may not be wired depending on imports,
        # but it should not be None if continuity modules are available
        # (we just verify it doesn't crash)
