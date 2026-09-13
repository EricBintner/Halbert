# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The periodic push loop: fires on canonical hosts, skips everything else."""
import asyncio
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from halbert_core.federation.peers_config import PeersConfig
from halbert_core.replica.push import (
    _is_canonical_host,
    _replica_push_loop,
    start_replica_push_loop,
)


def _memories(path: Path) -> Path:
    path.write_text(json.dumps({"version": 2, "memories": []}))
    return path


def _db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE conversations (id TEXT)")
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def canonical_env(tmp_path, monkeypatch):
    """A node that resolves canonical: no canonical URL, one body peer."""
    config = PeersConfig(config_path=tmp_path / "peers.json")
    config.add_peer(node_id="sat-1", node_name="sat", role="body",
                    raw_token="hbt_x", endpoint="http://sat:8000")
    config.set_outbound_token("sat-1", "hbt_push")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring._get_canonical_memory_url",
        lambda: "")
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    return config


@pytest.fixture
def no_canonical_url(monkeypatch):
    """Being config that names no canonical — isolates role resolution
    from whatever the host machine's real being.yml says."""
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring._get_canonical_memory_url",
        lambda: "")
    yield


def test_is_canonical_true_with_body_peers(canonical_env):
    assert _is_canonical_host() is True


def test_is_canonical_false_without_body_peers(
        tmp_path, monkeypatch, no_canonical_url):
    config = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
    assert _is_canonical_host() is False


def test_start_returns_none_when_not_canonical(
        tmp_path, monkeypatch, no_canonical_url):
    config = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)

    class App:
        class state:
            pass

    async def go():
        return start_replica_push_loop(App())

    assert asyncio.run(go()) is None


def test_loop_fires_and_pushes(canonical_env, tmp_path, monkeypatch):
    """One iteration on start, then sleep — a stubbed push records the call."""
    calls = []

    def fake_push(snapshot, **kw):
        calls.append(snapshot)
        return []

    monkeypatch.setattr(
        "halbert_core.replica.push.push_snapshot_to_peers", fake_push)
    monkeypatch.setattr(
        "halbert_core.replica.push._push_interval_s", lambda: 3600)

    async def go():
        task = asyncio.get_running_loop().create_task(_replica_push_loop())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert len(calls) == 1  # fired once on start, then slept


def test_loop_skips_iterations_when_not_canonical(
        tmp_path, monkeypatch, no_canonical_url):
    """A body must not push — the loop checks role every iteration."""
    config = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
    calls = []
    monkeypatch.setattr(
        "halbert_core.replica.push.push_snapshot_to_peers",
        lambda snapshot, **kw: calls.append(snapshot))
    monkeypatch.setattr(
        "halbert_core.replica.push._push_interval_s", lambda: 3600)

    async def go():
        task = asyncio.get_running_loop().create_task(_replica_push_loop())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert calls == []


def test_loop_survives_a_push_failure(canonical_env, monkeypatch):
    """A broken iteration is logged, not fatal — the next tick still fires."""
    monkeypatch.setattr(
        "halbert_core.replica.push.push_snapshot_to_peers",
        lambda snapshot, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    ticks = [0]
    real_sleep = asyncio.sleep

    async def short_sleep(_s):
        ticks[0] += 1
        await real_sleep(0)

    monkeypatch.setattr(
        "halbert_core.replica.push._push_interval_s", lambda: 0)
    monkeypatch.setattr("asyncio.sleep", short_sleep)

    async def go():
        task = asyncio.get_running_loop().create_task(_replica_push_loop())
        await real_sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert ticks[0] >= 2  # the loop kept ticking despite the failure


def test_interval_reads_from_being_yml(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "halbert_core.config.being_config._default_path",
        lambda: tmp_path / "being.yml")
    (tmp_path / "being.yml").write_text("replica_push_interval_s: 60\n")
    from halbert_core.replica.push import _push_interval_s
    assert _push_interval_s() == 60.0


def test_interval_defaults_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "halbert_core.config.being_config._default_path",
        lambda: tmp_path / "being.yml")
    from halbert_core.replica.push import _push_interval_s, DEFAULT_PUSH_INTERVAL_S
    assert _push_interval_s() == DEFAULT_PUSH_INTERVAL_S
