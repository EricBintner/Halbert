# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The fleet grid's Online badge is derived, not hardcoded.

list_fleet_nodes used to hardcode ``online=False`` behind a federation-9.9
TODO, so every node on /compute showed Offline regardless of reality. A
live probe is blocked on federation-9.4 (outbound peer-token custody — M14
keeps only hashes, get_fleet_proxy returns None), so ``online`` is derived
from ``last_seen`` freshness, the same idiom the rail's node buttons use.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import halbert_core.dashboard.routes.fleet as fleet


def _iso(**delta: int) -> str:
    t = datetime.now(timezone.utc) - timedelta(**delta)
    return t.isoformat().replace("+00:00", "Z")


class TestRecentlySeen:
    def test_recent_contact_is_online(self):
        assert fleet._recently_seen(_iso(minutes=1)) is True

    def test_stale_contact_is_offline(self):
        assert fleet._recently_seen(_iso(hours=2)) is False

    def test_older_than_the_window_is_offline(self):
        seen = datetime.now(timezone.utc) - fleet.FLEET_ONLINE_WINDOW - timedelta(seconds=1)
        assert fleet._recently_seen(seen.isoformat()) is False

    def test_never_seen_is_offline(self):
        assert fleet._recently_seen(None) is False

    def test_an_unparsable_timestamp_is_offline(self):
        assert fleet._recently_seen("not-a-timestamp") is False

    def test_a_naive_timestamp_is_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
        assert fleet._recently_seen(naive.isoformat()) is True


class TestFleetNodesOnline:
    def _run(self, peers):
        original = fleet.get_peers_config
        fleet.get_peers_config = lambda: SimpleNamespace(list_peers=lambda: peers)
        try:
            return asyncio.run(fleet.list_fleet_nodes())
        finally:
            fleet.get_peers_config = original

    def test_a_recently_seen_peer_is_online(self):
        peer = SimpleNamespace(
            node_id="n1", node_name="Kitchen", role="satellite",
            endpoint="http://kitchen.lan:8000", last_seen=_iso(minutes=1),
            capabilities=[],
        )
        nodes = self._run([peer])
        assert nodes[0].online is True

    def test_a_stale_peer_is_offline_not_hardcoded_false(self):
        peer = SimpleNamespace(
            node_id="n2", node_name="Garage", role="satellite",
            endpoint=None, last_seen=_iso(hours=3),
            capabilities=[],
        )
        nodes = self._run([peer])
        assert nodes[0].online is False

    def test_last_seen_rides_through_unchanged(self):
        stamp = _iso(minutes=2)
        peer = SimpleNamespace(
            node_id="n3", node_name="Desk", role="body",
            endpoint="http://desk.lan:8000", last_seen=stamp,
            capabilities=["gpu_llm"],
        )
        nodes = self._run([peer])
        assert nodes[0].last_seen == stamp
        assert nodes[0].capabilities == ["gpu_llm"]