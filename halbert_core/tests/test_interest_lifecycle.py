# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The whole loop, once, with nothing stubbed between the tool and the disk.

Every other test in this workstream isolates one link. That is what they are
for, and it is also how this workstream shipped four separate defects that
each looked implemented: `remember` wrote through a function that did not
exist, "stop using" left the record active so recall kept answering, the
mirror was never written at all, and restating a stopped interest did not
revive it. Each was invisible because the neighbouring link was stubbed and
the test asserted the stub.

So this file stubs nothing on the write path. Real ``PersonaMemoryStore``,
real ``ObservationStore``, the real tool, the real routes, one temp
directory, in the order a person would actually do it:

    say it -> it is stored -> it is mirrored -> it is listed -> it colours a
    turn -> stop using it -> it stops colouring turns -> remember it again ->
    it colours turns again -> forget it -> it is gone from both planes

If this file passes, the feature works. If it fails, one of the links is
lying about the next one.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SAID = "remember that I collect vintage thinkpads"
TOPIC = "vintage thinkpads"


class _Intake:
    """The turn signals RECALL-v1 reads."""

    def __init__(self, entities=(), domains=()):
        self.entities = set(entities)
        self.detected_domains = list(domains)
        self.intent = "question"
        self.is_troubleshooting = False
        self.has_error_indicators = False


@pytest.fixture
def world(tmp_path, monkeypatch):
    """One temp data home, real stores, a turn in scope, and the API."""
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))

    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore
    import halbert_core.integrations.cognition_wiring as cw
    from halbert_core.continuity.provenance import current_turn, current_user_message
    from halbert_core.dashboard.routes import memory as memory_routes
    from halbert_core.tools.executor import current_speaker_role

    memory_store = PersonaMemoryStore("lifecycle")
    observation_store = ObservationStore("lifecycle")
    monkeypatch.setattr(cw, "get_persona_memory_store", lambda: memory_store)
    monkeypatch.setattr(cw, "get_observation_store", lambda: observation_store)

    tokens = [
        (current_user_message, current_user_message.set(SAID)),
        (current_speaker_role, current_speaker_role.set("admin")),
        (current_turn, current_turn.set("turn-1")),
    ]

    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/api/memory")

    class World:
        memory = memory_store
        observations = observation_store
        client = TestClient(app)

        @staticmethod
        def rows():
            """The rows the prompt path reads, built exactly as it builds them."""
            from halbert_core.continuity.interests import Interest

            return [
                i for i in (
                    Interest.from_persona_memory(m)
                    for m in memory_store.list_memories()
                ) if i is not None
            ]

        @staticmethod
        def recalled():
            """What a turn about thinkpads would carry, or None."""
            from halbert_core.continuity.recall_interest import select_interest

            return select_interest(
                World.rows(), _Intake(entities={"thinkpads"}), thread_id="t1"
            )

    yield World

    for var, token in reversed(tokens):
        try:
            var.reset(token)
        except ValueError:
            # Minted in a different async context; clearing is enough.
            var.set(None)


async def _say_it():
    from halbert_core.tools.remember import remember

    return await remember({"topic": TOPIC, "reason": SAID})


@pytest.mark.asyncio
async def test_the_whole_loop(world):
    # -- 1. say it ------------------------------------------------------
    echo = await _say_it()
    assert echo == f'Recorded: "User is interested in {TOPIC}"'

    # -- 2. it is stored, as the record ---------------------------------
    memories = world.memory.list_memories()
    assert len(memories) == 1
    memory_id = memories[0].id

    # ...at the confidence a *stated* fact earns, not the inferred one. This
    # is the calibration the engine's own handoff gets wrong: it says a
    # writer must set the provenance itself, which alone lands at 0.7. The
    # user_stated tag is the other half, and this is what pins it.
    assert memories[0].epistemic.confidence == pytest.approx(0.9)

    # -- 3. and mirrored, as the index ----------------------------------
    mirrored = world.observations.search(TOPIC, limit=5)
    assert [o.source_memory_id for o in mirrored] == [memory_id]
    assert mirrored[0].category == "preference"

    # -- 4. it is listed, with how it was learned -----------------------
    body = world.client.get("/api/memory/about-you").json()
    assert [r["topic"] for r in body["items"]] == [TOPIC]
    assert body["items"][0]["learned"] == "You told me"
    assert body["items"][0]["reason"] == SAID

    # ...and the conversational answer says the same thing, and says it is
    # the whole thing.
    from halbert_core.tools.about_you_tool import what_i_remember

    spoken = await what_i_remember({})
    assert TOPIC in spoken
    assert "complete list" in spoken

    # -- 5. it colours a turn about thinkpads ---------------------------
    assert world.recalled() is not None

    # -- 6. stop using it -----------------------------------------------
    report = world.client.post(
        f"/api/memory/about-you/{memory_id}/stop-using"
    ).json()
    assert report["complete"] is True, report["errors"]
    assert report["observations"] == 1

    # -- 7. and turns stop carrying it ----------------------------------
    # The record, not the mirror: under Singular Entity the mirror is
    # body-local and the record is what the whole entity reads.
    assert world.recalled() is None
    assert world.client.get("/api/memory/about-you").json()["items"] == []
    assert TOPIC not in await what_i_remember({})

    # ...but it is still there to be restored.
    shown = world.client.get(
        "/api/memory/about-you?include_forgotten=true"
    ).json()
    assert [r["topic"] for r in shown["items"]] == [TOPIC]

    # -- 8. remember it again -------------------------------------------
    resumed = world.client.post(
        f"/api/memory/about-you/{memory_id}/remember-again"
    ).json()
    assert resumed["complete"] is True, resumed["errors"]
    assert world.recalled() is not None

    # -- 9. forget it, and it is gone from both planes ------------------
    erased = world.client.post(f"/api/memory/about-you/{memory_id}/forget").json()
    assert erased["complete"] is True, erased["errors"]
    assert erased["memory"] is True
    assert erased["observations"] == 1

    # `include_deleted=True` is the assertion that matters, and the reason
    # is the whole distinction between the two verbs: a soft delete leaves
    # the row on disk and readable, which is what "stop using" is for.
    # Asserting the default listing instead passes for a soft delete too,
    # and would have let `forget` quietly become the weaker verb.
    assert world.memory.list_memories(include_deleted=True) == []
    assert world.observations.search(TOPIC, limit=5, include_stale=True) == []
    assert world.recalled() is None
    assert world.client.get(
        "/api/memory/about-you?include_forgotten=true"
    ).json()["items"] == []
    assert TOPIC not in await what_i_remember({})


@pytest.mark.asyncio
async def test_saying_it_twice_is_one_interest(world):
    # Not two rows, and not a second row that shadows the first in the list.
    assert await _say_it()
    assert await _say_it()
    assert len(world.memory.list_memories()) == 1
    assert len(world.client.get("/api/memory/about-you").json()["items"]) == 1


@pytest.mark.asyncio
async def test_saying_it_again_after_stopping_brings_it_back(world):
    # The path a person actually takes: they stop it, then later say the
    # same thing again. Silently leaving it retired would mean the system
    # heard them and did nothing.
    await _say_it()
    memory_id = world.memory.list_memories()[0].id
    world.client.post(f"/api/memory/about-you/{memory_id}/stop-using")
    assert world.recalled() is None

    assert await _say_it()
    assert world.recalled() is not None
    assert [r["topic"] for r in
            world.client.get("/api/memory/about-you").json()["items"]] == [TOPIC]
