# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The pool must survive the idle reaper.

`acquire()` skipped dead sessions but never removed them, so once the reaper
had collected `cap` of them the cap check was permanently true: every acquire
returned None and every agent command fell back to subprocess for the rest of
the process's life. It presented as the pool quietly ceasing to exist about
fifteen minutes after the dashboard went quiet.
"""

import asyncio

from halbert_core.streaming.agent_pool import TerminalPool


class _Session:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive

    def die(self):
        self._alive = False


class _Manager:
    def __init__(self):
        self._block_open = {}
        self.spawned = 0
        self._spawned_sessions = {}

    def is_interactive(self, sid):
        return False

    def set_block_open(self, sid, value):
        self._block_open[sid] = value

    async def spawn(self, *a, **kw):
        self.spawned += 1
        sid = f"sid-{self.spawned}"
        self._spawned_sessions[sid] = _Session()
        return sid

    def get(self, sid):
        return self._spawned_sessions.get(sid)


def _pool(cap=3):
    mgr = _Manager()
    pool = TerminalPool(mgr, cap=cap)
    return pool, mgr


class TestDeadSessionsDoNotFillTheCap:
    def test_a_reaped_pool_can_still_acquire(self):
        pool, mgr = _pool(cap=2)
        pool._sessions = {"a": _Session(), "b": _Session()}
        for s in pool._sessions.values():
            s.die()                     # the reaper has been through

        got = asyncio.run(pool.acquire())
        assert got is not None, "the pool stayed dead after the reaper"

    def test_dead_sessions_are_removed_not_merely_skipped(self):
        pool, mgr = _pool(cap=3)
        pool._sessions = {"a": _Session(), "b": _Session()}
        pool._sessions["a"].die()

        asyncio.run(pool.acquire())
        assert "a" not in pool._sessions

    def test_a_live_idle_session_is_still_reused(self):
        pool, mgr = _pool(cap=2)
        live = _Session()
        pool._sessions = {"live": live}

        got = asyncio.run(pool.acquire())
        assert got is not None and got[0] == "live"
        assert mgr.spawned == 0, "spawned instead of reusing"

    def test_the_cap_still_applies_to_live_sessions(self):
        pool, mgr = _pool(cap=2)
        pool._sessions = {"a": _Session(), "b": _Session()}
        for sid in pool._sessions:
            mgr.set_block_open(sid, True)      # both busy, both alive

        assert asyncio.run(pool.acquire()) is None
