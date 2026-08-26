# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the proactive event bus (T7a)."""

import asyncio
import threading

from halbert_core.proactive.events import ProactiveEvent, ProactiveEventBus


def make_event(title="Test event", severity="warning", **kwargs):
    return ProactiveEvent.create(
        type="finding", severity=severity, title=title, body="body", **kwargs
    )


class TestEventBus:
    def test_publish_reaches_subscriber(self):
        bus = ProactiveEventBus()
        received = []
        bus.subscribe(received.append)

        asyncio.run(bus.publish(make_event(title="hello")))
        assert [e.title for e in received] == ["hello"]

    def test_unsubscribe_stops_delivery(self):
        bus = ProactiveEventBus()
        received = []
        sub_id = bus.subscribe(received.append)
        bus.unsubscribe(sub_id)

        asyncio.run(bus.publish(make_event()))
        assert received == []

    def test_get_recent_returns_newest_first_sliced(self):
        bus = ProactiveEventBus()
        for i in range(3):
            asyncio.run(bus.publish(make_event(title=f"event-{i}")))

        recent = bus.get_recent(limit=2)
        assert [e.title for e in recent] == ["event-1", "event-2"]
        assert len(bus.get_recent(limit=50)) == 3

    def test_subscriber_exception_does_not_break_others(self):
        bus = ProactiveEventBus()
        received = []

        def bad(event):
            raise RuntimeError("boom")

        bus.subscribe(bad)
        bus.subscribe(received.append)
        asyncio.run(bus.publish(make_event()))
        assert len(received) == 1

    def test_async_subscriber_coroutine_is_scheduled(self):
        bus = ProactiveEventBus()
        received = []

        async def acb(event):
            received.append(event.title)

        async def run():
            bus.subscribe(acb)
            await bus.publish(make_event(title="async-cb"))
            # Let the scheduled task run
            await asyncio.sleep(0)

        asyncio.run(run())
        assert received == ["async-cb"]


class TestEventFields:
    def test_category_defaults_to_general(self):
        assert make_event().category == "general"

    def test_category_can_be_set(self):
        event = make_event(category="security")
        assert event.category == "security"

    def test_create_generates_id_and_timestamp(self):
        event = make_event()
        assert event.id != ""
        assert event.created_at != ""

    def test_to_dict_includes_category(self):
        event = make_event(category="storage")
        d = event.to_dict()
        assert d["category"] == "storage"


class TestCrossThreadPublish:
    def test_publish_from_worker_thread_reaches_loop_subscriber(self):
        """A publish from a plain worker thread (which runs the coroutine on
        its own private loop) must deliver to a subscriber whose queue lives
        on the main thread's asyncio loop via attach_loop."""
        bus = ProactiveEventBus()
        ready = threading.Event()
        received = []
        errors = []

        async def loop_side():
            loop = asyncio.get_running_loop()
            bus.attach_loop(loop)
            queue = asyncio.Queue()
            bus.subscribe(lambda e: queue.put_nowait(e))
            ready.set()
            event = await asyncio.wait_for(queue.get(), timeout=5.0)
            received.append(event)

        def worker():
            try:
                if ready.wait(timeout=5.0):
                    asyncio.run(bus.publish(make_event(title="thread event")))
            except Exception as e:  # noqa: BLE001 — surfaced by assertion
                errors.append(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        asyncio.run(loop_side())
        t.join(timeout=5.0)

        assert errors == []
        assert [e.title for e in received] == ["thread event"]

    def test_publish_on_owning_loop_uses_direct_dispatch(self):
        """Publishing on the attached loop's thread keeps the current
        synchronous-in-loop behavior (no call_soon_threadsafe detour)."""
        bus = ProactiveEventBus()
        received = []

        async def run():
            bus.attach_loop(asyncio.get_running_loop())
            bus.subscribe(received.append)
            await bus.publish(make_event(title="same-loop"))
            # Direct dispatch: callback ran before publish returned
            assert [e.title for e in received] == ["same-loop"]

        asyncio.run(run())
