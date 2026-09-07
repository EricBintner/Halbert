# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ownership is by actor, in every mode — one function every conversation
writer, the cognitive tick and the sensor outputs consult.

``.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md`` §4–§5, with the founder's
answers: D1 life safety on a private source still reaches Halbert; D2
normal mode keeps the guest transcript, tagged and erasable; D4 private
sources end with the guest session.

The rules pinned here:
- R1: world writers go to Halbert in every mode.
- R2: while a guest fronts, the tick is the guest's; the transcript is
  Halbert's in normal mode (tagged with the session) and the guest's in
  private mode; a writer nobody classified fails closed.
- R3: an observation from a source handed to the guest is the guest's,
  except life safety, which is always Halbert's.
"""
from __future__ import annotations

import pytest

from halbert_core.continuity import ownership
from halbert_core.continuity.ownership import Owner, route_write, route_observation
from halbert_core.persona import guest, private_sources


@pytest.fixture(autouse=True)
def _fresh():
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    yield
    guest.reset_for_tests()
    private_sources.reset_for_tests()


def _front(name="Marnie"):
    persona, _ = guest.GuestPersona.from_payload({"name": name})
    return guest.offer(persona, offered_by="h2-node", offered_by_name="H2")


class TestNoGuest:

    @pytest.mark.parametrize("kind", sorted(ownership.WORLD_KINDS | ownership.CONVERSATION_KINDS))
    def test_everything_is_halberts(self, kind):
        assert route_write(kind) is Owner.HALBERT

    def test_an_unclassified_kind_is_halberts_as_today(self):
        assert route_write("something.new") is Owner.HALBERT

    def test_observations_are_halberts(self):
        assert route_observation("frigate:patio") is Owner.HALBERT


class TestGuestNormalMode:

    @pytest.mark.parametrize("kind", sorted(ownership.WORLD_KINDS))
    def test_the_world_stays_halberts(self, kind):
        _front()
        assert route_write(kind) is Owner.HALBERT

    def test_the_tick_is_the_guests(self):
        _front()
        assert route_write("cognition.tick") is Owner.GUEST

    def test_the_transcript_is_halberts_tagged(self):
        session = _front()
        assert route_write("conversation.message") is Owner.HALBERT
        tag = ownership.guest_tag()
        assert tag == {"actor": f"guest:{session.id}", "request_id": f"guest-session-{session.id}"}

    def test_receipts_are_halberts(self):
        _front()
        assert route_write("conversation.receipt") is Owner.HALBERT

    def test_an_unclassified_writer_fails_closed(self):
        _front()
        assert route_write("something.new") is Owner.DROP

    def test_observations_are_halberts_until_a_source_is_handed_over(self):
        _front()
        assert route_observation("frigate:patio") is Owner.HALBERT

    def test_no_tag_without_a_guest(self):
        assert ownership.guest_tag() == {}


class TestPrivateSources:

    def test_a_source_can_only_be_assigned_while_a_guest_fronts(self):
        with pytest.raises(private_sources.NoGuestFronting):
            private_sources.assign("webcam:0")

    def test_assigning_a_source_turns_private_mode_on(self):
        _front()
        assert private_sources.active() is False
        private_sources.assign("webcam:0")
        assert private_sources.active() is True
        assert private_sources.owner_of("webcam:0") is Owner.GUEST
        assert private_sources.owner_of("frigate:patio") is Owner.HALBERT

    def test_a_source_id_has_a_shape(self):
        _front()
        for bad in ("", "webcam", "web cam:0", "../etc", "a:" + "x" * 200):
            with pytest.raises(private_sources.BadSourceId):
                private_sources.assign(bad)

    def test_release_and_clear(self):
        _front()
        private_sources.assign("webcam:0")
        private_sources.assign("mic:local:0")
        private_sources.release("webcam:0")
        assert private_sources.assigned() == {"mic:local:0": Owner.GUEST}
        private_sources.clear()
        assert private_sources.active() is False

    def test_private_mode_ends_with_the_guest_session(self):
        """D4: a private session never outlives the guest it was for."""
        _front()
        private_sources.assign("webcam:0")
        guest.withdraw()
        assert private_sources.active() is False
        assert private_sources.owner_of("webcam:0") is Owner.HALBERT

    def test_private_mode_ends_when_the_heartbeat_lapses(self):
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        session = guest.offer(persona, offered_by="h2-node", ttl_seconds=10.0)
        private_sources.assign("webcam:0")
        assert guest.current_guest(now=session.deadline + 1.0) is None
        assert private_sources.active() is False

    def test_a_new_session_does_not_inherit_the_last_ones_sources(self):
        _front()
        private_sources.assign("webcam:0")
        guest.handback()
        _front("Rex")
        assert private_sources.active() is False


class TestGuestPrivateMode:

    def _private(self):
        session = _front()
        private_sources.assign("webcam:0")
        return session

    def test_the_transcript_is_the_guests(self):
        self._private()
        assert route_write("conversation.message") is Owner.GUEST

    def test_receipts_are_dropped(self):
        self._private()
        assert route_write("conversation.receipt") is Owner.DROP

    def test_the_tick_is_still_the_guests(self):
        self._private()
        assert route_write("cognition.tick") is Owner.GUEST

    def test_the_world_is_still_halberts(self):
        self._private()
        for kind in ownership.WORLD_KINDS:
            assert route_write(kind) is Owner.HALBERT, kind

    def test_a_handed_over_source_is_the_guests(self):
        self._private()
        assert route_observation("webcam:0") is Owner.GUEST
        assert route_observation("frigate:patio") is Owner.HALBERT

    def test_life_safety_on_a_private_source_still_reaches_halbert(self):
        """D1: the house is not private from its own smoke alarm."""
        self._private()
        assert route_observation("webcam:0", life_safety=True) is Owner.HALBERT

    def test_an_observation_without_a_source_is_halberts(self):
        """A writer that cannot say where it looked cannot have been handed over."""
        self._private()
        assert route_observation("") is Owner.HALBERT
