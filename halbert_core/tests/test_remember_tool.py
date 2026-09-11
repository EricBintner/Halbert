# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``remember`` -- the explicit write path, and everything it refuses.

`RQ-3`: two write paths, both with deterministic selection; **no model-chosen
write, ever**. This is the explicit one. Its whole design is a set of
refusals, because the failure it exists to prevent is the one Haloysius's own
``update_user_knowledge`` commits -- auto-applying a model-picked value with
the reason "Learned from conversation" and a confidence the model invented.

The two gates are the point:

- the turn's **user message** must carry one of a short deterministic phrase
  list, and
- the recorded ``reason`` must be a **substring of that message**.

Without the second, a model calling ``remember`` on a paraphrase ("you seem
to like...") collapses the explicit path back into a model-chosen write, and
the tool becomes the thing it was built to replace. `MEM-06`: a stored fact
about a person needs a reason that is a human utterance, never model text.
"""

import pytest

from halbert_core.continuity.interests import Interest, Origin
from halbert_core.continuity.provenance import current_user_message
from halbert_core.tools.executor import current_speaker_role
from halbert_core.tools.remember import REMEMBER_SCHEMA, remember

SAID = "remember that I collect vintage thinkpads"


@pytest.fixture
def turn(monkeypatch, tmp_path):
    """A turn in scope: the user's words, an admin speaker, a temp store."""
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    written = []

    def _capture(interest):
        written.append(interest)
        return f"interest_{interest.slug}"

    import halbert_core.tools.remember as mod
    monkeypatch.setattr(mod, "_write_interest", _capture)

    msg_token = current_user_message.set(SAID)
    role_token = current_speaker_role.set("admin")
    yield written
    for var, tok in ((current_speaker_role, role_token),
                     (current_user_message, msg_token)):
        try:
            var.reset(tok)
        except ValueError:
            var.set(None)



@pytest.fixture
def say(request):
    """Put words in the user's mouth for one test, then take them back."""
    tokens = []

    def _say(text):
        tokens.append((current_user_message, current_user_message.set(text)))

    def _role(role):
        tokens.append((current_speaker_role, current_speaker_role.set(role)))

    _say.role = _role
    yield _say
    for var, tok in reversed(tokens):
        try:
            var.reset(tok)
        except ValueError:
            # An async test body runs in its own Context, so a token minted
            # in the fixture cannot always be reset here. Clearing outright
            # is right in a test: nothing outer is relying on the value.
            var.set(None)


async def _call(**args):
    return await remember(args)


class TestTheSchemaTellsTheModelTheRule:
    """A rule stated only in code is absent at the moment the model decides."""

    def test_the_description_says_the_words_must_be_the_users(self):
        d = REMEMBER_SCHEMA["description"].lower()
        assert "own words" in d or "verbatim" in d or "substring" in d

    def test_it_takes_a_topic_and_a_reason(self):
        props = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "topic" in props and "reason" in props


class TestItWritesWhatWasSaid:

    async def test_an_explicit_request_is_stored(self, turn):
        out = await _call(topic="vintage thinkpads", reason=SAID)
        assert len(turn) == 1
        assert turn[0].topic == "vintage thinkpads"
        assert turn[0].origin is Origin.STATED

    async def test_the_reply_echoes_the_stored_sentence_verbatim(self, turn):
        # The echo is the confirmation and the first chance to correct.
        out = await _call(topic="vintage thinkpads", reason=SAID)
        assert turn[0].content in out

    async def test_the_actor_and_role_ride_on_the_row(self, turn):
        await _call(topic="vintage thinkpads", reason=SAID)
        assert turn[0].speaker_role == "admin"
        assert turn[0].actor

    async def test_the_reason_is_the_utterance(self, turn):
        await _call(topic="vintage thinkpads", reason=SAID)
        assert turn[0].reason == SAID


class TestTheParaphraseGate:
    """The gate that stops this collapsing into a model-chosen write."""

    async def test_a_reason_the_user_did_not_say_is_refused(self, turn):
        out = await _call(topic="thinkpads", reason="you seem to like thinkpads")
        assert turn == []
        assert "refus" in out.lower() or "not" in out.lower()

    async def test_a_reason_that_is_a_substring_is_accepted(self, turn):
        out = await _call(topic="thinkpads", reason="I collect vintage thinkpads")
        assert len(turn) == 1

    async def test_case_and_spacing_do_not_defeat_the_check(self, turn):
        await _call(topic="thinkpads", reason="I  Collect   Vintage ThinkPads")
        assert len(turn) == 1, "the check normalises; it does not require byte equality"

    async def test_an_empty_reason_is_refused(self, turn):
        out = await _call(topic="thinkpads", reason="")
        assert turn == []


class TestThePhraseGate:

    @pytest.mark.parametrize("phrase", [
        "remember that I collect vintage thinkpads",
        "note that I collect vintage thinkpads",
        "keep in mind that I collect vintage thinkpads",
    ])
    async def test_each_listed_phrase_opens_the_path(self, turn, say, phrase):
        say(phrase)
        assert await _call(topic="thinkpads", reason=phrase)
        assert len(turn) == 1

    async def test_a_turn_with_no_such_phrase_is_refused(self, turn, say):
        said = "I have been fixing thinkpads all weekend"
        say(said)
        out = await _call(topic="thinkpads", reason=said)
        assert turn == [], "an ordinary sentence is not a request to remember"

    async def test_no_turn_in_scope_is_refused(self, turn, say):
        # Nothing to verify the reason against. Refusing is the only honest
        # answer; writing anyway is the model-chosen write by another route.
        say(None)
        out = await _call(topic="thinkpads", reason=SAID)
        assert turn == []


class TestTheRoleGate:
    """`RQ-8`: per-person facts on a home body carry the speaker's role, and
    the writer refuses below member."""

    @pytest.mark.parametrize("role", ["admin", "member"])
    async def test_member_and_above_may_write(self, turn, say, role):
        say.role(role)
        await _call(topic="thinkpads", reason=SAID)
        assert len(turn) == 1

    @pytest.mark.parametrize("role", ["guest", "restricted", "unknown", None])
    async def test_below_member_is_refused(self, turn, say, role):
        say.role(role)
        out = await _call(topic="thinkpads", reason=SAID)
        assert turn == [], f"{role!r} must not write a fact about the household"


class TestSecretsNeverLand:

    async def test_a_credential_is_refused_and_not_stored(self, turn, say):
        said = "remember that my api key is sk-live-4eC39HqLyjWDarjtT1zdp7dc"
        say(said)
        out = await _call(topic="my api key", reason=said)
        assert turn == [], "a Tier-2 credential is answered by a template, never stored"
        assert "sk-live-4eC39HqLyjWDarjtT1zdp7dc" not in out

    async def test_incidental_secret_shaped_text_is_redacted_not_echoed(self, turn, say):
        said = "remember that I host at 203.0.113.9 for the club"
        say(said)
        out = await _call(topic="hosting for the club", reason=said)
        if turn:
            assert "203.0.113.9" not in turn[0].reason
        assert "203.0.113.9" not in out


class TestTheRealWritePathResolves:
    """The tests above stub `_write_interest`, so they never touch the store.

    That stub hid a broken import for two commits: `_write_interest` reached
    for `cognition_wiring.get_persona_memory_store`, which did not exist, so
    every real call would have returned "the memory store could not be
    written". A tool that refuses everything still passes a suite that never
    calls its writer.
    """

    def test_write_interest_imports_resolve(self):
        # The import is inside the function, so only calling it proves
        # anything. A store of None is the "no memory configured" path and is
        # fine; an ImportError is not.
        import halbert_core.tools.remember as mod

        mod._write_interest.__wrapped__ if hasattr(mod._write_interest, "__wrapped__") else None
        from halbert_core.integrations.cognition_wiring import (  # noqa: F401
            get_persona_memory_store,
        )

    async def test_a_real_write_lands_in_a_real_store(self, tmp_path, monkeypatch):
        """End to end, through the actual store this body would use."""
        monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
        from haloysius.memory_v2.store import PersonaMemoryStore
        import halbert_core.integrations.cognition_wiring as cw

        store = PersonaMemoryStore("remember-e2e")
        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: store)

        msg = current_user_message.set(SAID)
        role = current_speaker_role.set("admin")
        try:
            out = await remember({"topic": "vintage thinkpads", "reason": SAID})
        finally:
            for var, tok in ((current_speaker_role, role), (current_user_message, msg)):
                try:
                    var.reset(tok)
                except ValueError:
                    var.set(None)

        assert "Recorded" in out
        contents = [m.content for m in store._memories.values()]
        assert "User is interested in vintage thinkpads" in contents

    async def test_no_store_configured_refuses_rather_than_claiming_success(
        self, tmp_path, monkeypatch
    ):
        import halbert_core.integrations.cognition_wiring as cw

        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: None)
        msg = current_user_message.set(SAID)
        role = current_speaker_role.set("admin")
        try:
            out = await remember({"topic": "vintage thinkpads", "reason": SAID})
        finally:
            for var, tok in ((current_speaker_role, role), (current_user_message, msg)):
                try:
                    var.reset(tok)
                except ValueError:
                    var.set(None)
        assert "Recorded" not in out, "nothing was stored; saying so is the point"


class TestTheMirrorIsActuallyWritten:
    """`RQ-1`: an interest is a PersonaMemory *mirrored* as an ObservationStore
    `preference` row. The mirror was never written.

    `should_mirror` existed and was referenced only in docstrings, so the
    property that governs the mirror governed nothing: `forget_interest` was
    deleting rows that had never been created, `stop_using_interest` was
    marking nothing stale, and the index recall is supposed to be built from
    never saw an interest at all.
    """

    @pytest.fixture
    def real_stores(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
        from haloysius.memory_v2.observation_store import ObservationStore
        from haloysius.memory_v2.store import PersonaMemoryStore
        import halbert_core.integrations.cognition_wiring as cw

        mem = PersonaMemoryStore("mirror-test")
        obs = ObservationStore("mirror-test")
        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: mem)
        monkeypatch.setattr(cw, "get_observation_store", lambda: obs, raising=False)
        return mem, obs

    async def _say(self, topic, said):
        msg = current_user_message.set(said)
        role = current_speaker_role.set("admin")
        try:
            return await remember({"topic": topic, "reason": said})
        finally:
            for var, tok in ((current_speaker_role, role), (current_user_message, msg)):
                try:
                    var.reset(tok)
                except ValueError:
                    var.set(None)

    async def test_a_stated_interest_writes_its_mirror(self, real_stores):
        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        rows = obs.search("vintage thinkpads", include_stale=True)
        assert rows, "the mirror row is the index; nothing was written to it"

    async def test_the_mirror_is_filed_as_a_preference_not_a_fact(self, real_stores):
        # The keyword classifier files "interested in" as `fact`; the category
        # is set explicitly so an interest does not become a fact in the index.
        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        rows = obs.search("vintage thinkpads", include_stale=True)
        assert rows[0].category == "preference"

    async def test_the_mirror_carries_the_source_memory_id(self, real_stores):
        # Without it, forget cannot find the row it is supposed to erase.
        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        rows = obs.search("vintage thinkpads", include_stale=True)
        assert rows[0].source_memory_id
        assert rows[0].source_memory_id in mem._memories

    async def test_forget_now_actually_reaches_the_mirror(self, real_stores):
        from halbert_core.continuity.forget_interest import forget_interest
        from halbert_core.continuity.interests import Interest

        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        memory_id = next(iter(mem._memories))
        interest = Interest.from_persona_memory(mem.get(memory_id))
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert report["observations"] == 1, (
            "forget reported success over a mirror that never existed"
        )

    async def test_a_failed_mirror_does_not_lose_the_record(self, real_stores, monkeypatch):
        # The memory is the record and the mirror is the index. Losing the
        # index is recoverable; refusing the write because the index failed
        # would lose what the person said.
        mem, obs = real_stores
        monkeypatch.setattr(obs, "save", lambda **k: (_ for _ in ()).throw(OSError("x")))
        out = await self._say("vintage thinkpads", SAID)
        assert "Recorded" in out
        assert mem._memories

    async def test_a_candidate_is_never_mirrored(self, real_stores):
        """The candidate rule, at the index.

        `remember` only ever writes stated interests, so nothing reaches this
        path with a candidate today -- the Consolidator will, and it is
        unbuilt. Asserted directly on `_mirror_interest` rather than through
        the tool, because a guard that only holds for inputs nobody sends is
        not a guard; this is the one that will still be here when the
        candidate writer arrives.
        """
        from halbert_core.continuity.interests import (
            Interest, InterestStatus, Origin,
        )
        from halbert_core.tools.remember import _mirror_interest

        mem, obs = real_stores
        candidate = Interest(topic="samba tuning", origin=Origin.INFERRED,
                             status=InterestStatus.CANDIDATE,
                             reason="appeared on 4 days in 30")
        _mirror_interest(candidate, "some-memory-id")
        assert obs.search("samba", include_stale=True) == [], (
            "an unconfirmed inference reached the index recall reads"
        )

    async def test_an_active_interest_is_mirrored_through_the_same_helper(self, real_stores):
        from halbert_core.continuity.interests import Interest, Origin
        from halbert_core.tools.remember import _mirror_interest

        mem, obs = real_stores
        active = Interest(topic="sailing", origin=Origin.STATED,
                          reason="remember that I like sailing", actor="user")
        _mirror_interest(active, "some-memory-id")
        assert obs.search("sailing", include_stale=True)

    async def test_restating_a_stopped_interest_revives_it(self, real_stores):
        """RECALL-v1 §7: a later *human* re-mention revives; a system re-save
        does not.

        Without this the tool lies. `smart_add` dedups the restatement against
        the existing row, so the status stays `forget_requested`, the person is
        told "Recorded", and the interest is still never used. Saying it out
        loud again is the clearest possible signal that they want it back.
        """
        from halbert_core.continuity.forget_interest import stop_using_interest
        from halbert_core.continuity.interests import Interest, InterestStatus

        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        memory_id = next(iter(mem._memories))
        interest = Interest.from_persona_memory(mem.get(memory_id))
        stop_using_interest(interest, memory_id, turn="t1",
                            memory_store=mem, observation_store=obs)
        assert Interest.from_persona_memory(mem.get(memory_id)).status is \
            InterestStatus.FORGET_REQUESTED

        await self._say("vintage thinkpads", SAID)
        assert Interest.from_persona_memory(mem.get(memory_id)).status is \
            InterestStatus.ACTIVE, "they said it again; it should be back"

    async def test_a_system_resave_does_not_revive(self, real_stores):
        # The other half of the same rule. Only the explicit writer revives;
        # a consolidation pass re-deriving the claim must not undo the
        # person's request, which is what the engine's tombstone protects.
        from halbert_core.continuity.forget_interest import stop_using_interest
        from halbert_core.continuity.interests import Interest, InterestStatus

        mem, obs = real_stores
        await self._say("vintage thinkpads", SAID)
        memory_id = next(iter(mem._memories))
        interest = Interest.from_persona_memory(mem.get(memory_id))
        stop_using_interest(interest, memory_id, turn="t1",
                            memory_store=mem, observation_store=obs)

        # A background re-derivation: straight to the store, not through the tool.
        mem.smart_add(interest.to_persona_memory("mirror-test"))
        assert Interest.from_persona_memory(mem.get(memory_id)).status is \
            InterestStatus.FORGET_REQUESTED
