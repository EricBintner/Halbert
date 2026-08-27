# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
``LLMClientAdapter.chat`` must not think on the event loop.

``call_llm_chat`` is synchronous: a blocking ``requests`` call under a 300s
timeout. ``chat`` is a coroutine, and it used to call it inline — so the whole
planning call ran on the loop. One turn asking a slow model stopped every
other open SSE stream, every other request and every heartbeat for as long as
that model took to think, and an endpoint that had gone quiet took the entire
dashboard with it rather than the one turn that asked for it.

The measurement is the same one the num_ctx probe uses, because it is the only
one that can tell "ran off the loop" from "ran fast": a heartbeat task ticking
every 10ms while ``chat`` runs, and the largest gap between two beats. A
blocking call inline shows up as one gap the length of the call. There are
three call sites in ``chat`` — the vision path, the ordinary planning call and
the guide fallback — and each is covered, because wrapping two of the three
leaves the loop stopped on whichever one was missed.

These deliberately do NOT assert on ``asyncio.to_thread`` (patching it, or
counting its calls, pins one implementation of "off the loop" rather than the
property). They assert the loop kept running, which is the thing that broke.
"""

import asyncio
import time

import pytest
from unittest.mock import patch

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import agent as agent_routes

GUIDE = ("guide-model", "http://localhost:11434", "ollama")
SPECIALIST = ("specialist-model", "https://api.cloud.test", "openai")
VISION = ("vision-model", "http://localhost:11434", "ollama")

TRIVIAL = "hi"

# How long the stubbed model "thinks". Long enough that a gap of this size is
# unmistakable next to a 10ms heartbeat, short enough to keep the suite quick.
THINK_S = 0.5
# A beat may be late for reasons that are not a stopped loop (a slow machine,
# the GC). Half the think time separates the two without being flaky.
TOLERANCE_S = 0.25


@pytest.fixture
def slots(monkeypatch):
    """Install the three configured slots; returns a mutator for each."""
    state = {"guide": GUIDE, "specialist": SPECIALIST, "vision": VISION,
             "endpoints": {}}
    import halbert_core.model.client as client

    monkeypatch.setattr(client, "get_configured_model",
                        lambda: state["guide"][0] if state["guide"] else "")
    monkeypatch.setattr(client, "get_ollama_endpoint",
                        lambda: state["guide"][1] if state["guide"]
                        else "http://localhost:11434")
    monkeypatch.setattr(client, "get_specialist_model",
                        lambda: state["specialist"] or (None, None, None))
    monkeypatch.setattr(client, "get_vision_model",
                        lambda: state["vision"]
                        or (None, "http://localhost:11434", "ollama"))
    monkeypatch.setattr(
        client, "provider_for",
        lambda url, default="ollama":
            state["guide"][2] if state["guide"] and url == state["guide"][1]
            else default)
    monkeypatch.setattr(client, "resolve_endpoint_by_id",
                        lambda eid: state["endpoints"].get(eid))
    monkeypatch.setattr(client, "api_key_for", lambda url: "")
    return state


class _Heartbeat:
    """An asyncio task that beats every 10ms, remembering how it went.

    Two readings, because either one alone can be argued with. ``worst`` is
    the largest gap between two beats: while the loop runs, beats land ~10ms
    apart; while something blocks it, no beat lands at all and the next one
    records the length of the block. ``beats`` is how many landed in total,
    which catches the same thing from the other side — a loop stopped for
    half a second simply does not get 50 beats into that half second.

    The drain in ``__aexit__`` is load-bearing, and was the difference between
    this class measuring something and measuring nothing. A beat whose timer
    expired while the loop was blocked has not run yet; it runs on the loop's
    next pass. Cancelling the task the instant the call returns takes that
    pass away, the gap is never recorded, and every assertion below passes
    whether or not the loop was ever stopped. (Measured: without the drain,
    ``gaps`` came back literally empty after a 0.5s block. With it, 0.501s
    against 0.014s when the same work runs off the loop.)
    """

    BEAT_S = 0.01
    # Three beats' worth: enough for the pass that lands the pending beat,
    # short enough not to matter to the suite.
    DRAIN_S = 0.03

    def __init__(self):
        self.gaps: list[float] = []
        self._task: asyncio.Task | None = None

    async def __aenter__(self):
        started = asyncio.Event()

        async def beat():
            last = time.monotonic()
            started.set()
            while True:
                await asyncio.sleep(self.BEAT_S)
                now = time.monotonic()
                self.gaps.append(now - last)
                last = now

        self._task = asyncio.create_task(beat())
        # Do not start measuring until the task is actually on the loop, or
        # the first "gap" is the time the test spent getting there.
        await started.wait()
        return self

    async def __aexit__(self, *exc):
        assert self._task is not None
        # See the class docstring: without this the measurement is discarded.
        await asyncio.sleep(self.DRAIN_S)
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return False

    @property
    def worst(self) -> float:
        return max(self.gaps) if self.gaps else 0.0

    @property
    def beats(self) -> int:
        return len(self.gaps)


# A call of THINK_S with the loop free is ~THINK_S / BEAT_S beats. Ask for a
# third of them: comfortably more than the handful a stopped loop manages, and
# far below what an unblocked loop delivers even on a slow machine.
MIN_BEATS = int(THINK_S / _Heartbeat.BEAT_S) // 3


def _slow_call(record: list):
    """A stand-in for ``call_llm_chat`` that blocks the thread it runs on."""

    def call(**kwargs):
        record.append(kwargs["model"])
        time.sleep(THINK_S)
        return {"content": "ok"}

    return call


@pytest.mark.asyncio
class TestChatDoesNotThinkOnTheEventLoop:
    async def test_the_planning_call_leaves_the_loop_running(self, slots):
        """The ordinary path: one model, one blocking call."""
        adapter = agent_routes.LLMClientAdapter()
        asked: list[str] = []

        async with _Heartbeat() as hb:
            started = time.monotonic()
            with patch("halbert_core.model.client.call_llm_chat",
                       _slow_call(asked)):
                answer = await adapter.chat(
                    [{"role": "user", "content": TRIVIAL}],
                    routing_prompt=TRIVIAL,
                )
            elapsed = time.monotonic() - started

        # The answer is unchanged, and the model really did take its time.
        assert answer.content == "ok"
        assert asked == [GUIDE[0]]
        assert elapsed >= THINK_S
        # And the loop kept beating the whole way through it.
        assert hb.worst < TOLERANCE_S, (
            f"the loop stopped for {hb.worst:.2f}s during the planning call"
        )
        assert hb.beats >= MIN_BEATS, (
            f"only {hb.beats} beats landed during the planning call"
        )

    async def test_the_guide_fallback_leaves_the_loop_running(self, slots):
        """The second call site: the pinned model is unreachable and the
        guide answers in its place — also blocking, also off the loop."""
        adapter = agent_routes.LLMClientAdapter()
        asked: list[str] = []
        slow = _slow_call(asked)

        def call(**kwargs):
            if kwargs["model"] == SPECIALIST[0]:
                asked.append(kwargs["model"])
                raise ConnectionError("nothing is listening on that port")
            return slow(**kwargs)

        async with _Heartbeat() as hb:
            with patch("halbert_core.model.client.call_llm_chat", call):
                answer = await adapter.chat(
                    [{"role": "user", "content": TRIVIAL}],
                    model_override=SPECIALIST[0],
                )

        # The pin was tried, it failed, and the guide took the turn.
        assert asked == [SPECIALIST[0], GUIDE[0]]
        assert answer.content == "ok"
        assert hb.worst < TOLERANCE_S, (
            f"the loop stopped for {hb.worst:.2f}s during the guide fallback"
        )
        assert hb.beats >= MIN_BEATS, (
            f"only {hb.beats} beats landed during the guide fallback"
        )

    async def test_the_vision_call_leaves_the_loop_running(self, slots):
        """The third call site: a turn carrying an image, answered by the
        vision slot."""
        adapter = agent_routes.LLMClientAdapter()
        asked: list[str] = []

        async with _Heartbeat() as hb:
            with patch("halbert_core.model.client.call_llm_chat",
                       _slow_call(asked)):
                answer = await adapter.chat(
                    [{"role": "user", "content": "what is in this picture?"}],
                    images=["aGVsbG8="],
                )

        assert asked == [VISION[0]]
        assert answer.content == "ok"
        assert hb.worst < TOLERANCE_S, (
            f"the loop stopped for {hb.worst:.2f}s during the vision call"
        )
        assert hb.beats >= MIN_BEATS, (
            f"only {hb.beats} beats landed during the vision call"
        )

    async def test_two_turns_at_once_do_not_wait_for_each_other(self, slots):
        """The consequence the finding is actually about.

        Two concurrent turns took 2 x THINK_S in series while the call ran on
        the loop — the second could not even start until the first returned.
        Off the loop they overlap, which is what stops one slow model from
        being every open stream's problem.
        """
        adapter = agent_routes.LLMClientAdapter()
        asked: list[str] = []

        started = time.monotonic()
        with patch("halbert_core.model.client.call_llm_chat",
                   _slow_call(asked)):
            answers = await asyncio.gather(
                adapter.chat([{"role": "user", "content": TRIVIAL}],
                             routing_prompt=TRIVIAL),
                adapter.chat([{"role": "user", "content": TRIVIAL}],
                             routing_prompt=TRIVIAL),
            )
        elapsed = time.monotonic() - started

        assert [a.content for a in answers] == ["ok", "ok"]
        assert asked == [GUIDE[0], GUIDE[0]]
        assert elapsed < 2 * THINK_S - TOLERANCE_S, (
            f"two concurrent turns took {elapsed:.2f}s — they ran in series"
        )
