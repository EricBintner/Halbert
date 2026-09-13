# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""3-strike hysteresis: a blip is not a death."""
import asyncio

import pytest

from halbert_core.replica.liveness import PeerLivenessProbe


class Resp:
    def __init__(self, status_code=200, healthy=True):
        self.status_code = status_code
        self._healthy = healthy

    def json(self):
        return {"healthy": self._healthy, "connected": True}


def _probe(http_get):
    return PeerLivenessProbe(
        "http://canonical:8000", "hbt_x", interval_s=60, http_get=http_get)


def _ok(*a, **kw):
    return Resp()


def _fail(*a, **kw):
    raise OSError("connection refused")


def test_three_consecutive_failures_flips_to_unreachable():
    probe = _probe(_fail)
    assert probe.canonical_reachable is True
    for _ in range(3):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is False


def test_one_success_after_failures_flips_back():
    state = {"fail": True}

    def flappy(*a, **kw):
        if state["fail"]:
            raise OSError("down")
        return Resp()

    probe = _probe(flappy)
    for _ in range(3):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is False
    state["fail"] = False
    asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is True
    assert probe.consecutive_failures == 0


def test_two_failures_then_success_stays_reachable():
    seq = [_fail, _fail, _ok, _ok]
    probe = _probe(lambda *a, **kw: seq.pop(0)(*a, **kw))
    for _ in range(4):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is True


def test_non_200_counts_as_failure():
    probe = _probe(lambda *a, **kw: Resp(status_code=503))
    for _ in range(3):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is False


def test_unhealthy_200_counts_as_failure():
    """A 200 that reports healthy:false is a live process with a dead
    store — not 'there' for the purposes of a fallback decision."""
    probe = _probe(lambda *a, **kw: Resp(healthy=False))
    for _ in range(3):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is False


def test_timeout_counts_as_failure():
    def timeout(*a, **kw):
        raise TimeoutError("read timed out")
    probe = _probe(timeout)
    for _ in range(3):
        asyncio.run(probe.poll_once())
    assert probe.canonical_reachable is False


def test_probe_start_stop_clean():
    probe = _probe(_ok)

    async def go():
        await probe.start()
        assert probe._task is not None
        await probe.stop()
        assert probe._task is None

    asyncio.run(go())


class _FakeApp:
    def __init__(self):
        from types import SimpleNamespace
        self.state = SimpleNamespace()


class TestProbeLifecycle:
    """The satellite's half of warm standby — started on a body, read
    by the status surfaces, stopped at shutdown."""

    def test_start_registers_probe_on_a_body(self, monkeypatch):
        import halbert_core.replica.liveness as lv
        import halbert_core.integrations.cognition_wiring as cw
        monkeypatch.setattr(
            cw, "_get_canonical_thread_url",
            lambda: "http://canonical:8000/api/conversations")
        monkeypatch.setattr(
            cw, "_get_canonical_memory_url", lambda: "")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "hbt_x")
        monkeypatch.setattr(lv, "_current_probe", None)

        app = _FakeApp()
        probe = asyncio.run(lv.start_liveness_probe(app, interval_s=999))
        try:
            assert probe is not None
            assert lv.current_probe() is probe
            assert app.state.liveness_probe is probe
            assert probe._peer_url == "http://canonical:8000"
        finally:
            asyncio.run(lv.stop_liveness_probe(app))
        assert lv.current_probe() is None

    def test_no_probe_on_a_canonical_or_independent_node(self, monkeypatch):
        import halbert_core.replica.liveness as lv
        import halbert_core.integrations.cognition_wiring as cw
        monkeypatch.setattr(cw, "_get_canonical_thread_url", lambda: "")
        monkeypatch.setattr(cw, "_get_canonical_memory_url", lambda: "")
        app = _FakeApp()
        assert asyncio.run(lv.start_liveness_probe(app)) is None

    def test_probe_reads_memory_url_when_thread_url_absent(self, monkeypatch):
        """A body may configure only the memory URL — the health endpoint
        lives on the same origin either way."""
        import halbert_core.replica.liveness as lv
        import halbert_core.integrations.cognition_wiring as cw
        monkeypatch.setattr(cw, "_get_canonical_thread_url", lambda: "")
        monkeypatch.setattr(
            cw, "_get_canonical_memory_url",
            lambda: "http://canonical:8000/api/memory")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "hbt_x")
        url, token = lv._body_peer_target()
        assert url == "http://canonical:8000"
        assert token == "hbt_x"
