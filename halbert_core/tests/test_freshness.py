# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Look before you speak (founder direction: "yes probe go look first too").

A claim about current machine state is never answered from memory. The ledger
counts as looking when its reading is recent; otherwise the host is checked.
"""

import time

import pytest

from halbert_core.continuity import StateStore
from halbert_core.continuity.freshness import (
    DEFAULT_FRESH_SECONDS,
    DURABLE_RECEIPT_FIELDS,
    RE_OBSERVABLE_RECEIPT_FIELDS,
    AnswerSource,
    decide,
    is_re_observable,
)

SIX_WEEKS = 6 * 7 * 24 * 3600


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "state.db"))
    yield s
    s.close()


class TestReObservability:
    @pytest.mark.parametrize("p", [
        "service_status", "disk_health", "cpu_load", "mounted", "free_space"])
    def test_machine_state_is_re_observable(self, p):
        assert is_re_observable(p)

    @pytest.mark.parametrize("p", [
        "rationale", "preference", "commitment", "why", "decided"])
    def test_durable_claims_are_not(self, p):
        assert not is_re_observable(p)

    def test_is_case_and_space_insensitive(self):
        assert is_re_observable("  Service_Status  ")

    def test_empty_predicate_is_not_re_observable(self):
        assert not is_re_observable("")

    def test_last_said_is_the_one_leaky_receipt_field(self):
        """Plan A's other eight lines record what happened; this one can
        record what *is*, which is why it must carry its date."""
        assert RE_OBSERVABLE_RECEIPT_FIELDS == {"Last said"}
        assert not (DURABLE_RECEIPT_FIELDS & RE_OBSERVABLE_RECEIPT_FIELDS)
        assert len(DURABLE_RECEIPT_FIELDS) == 8


class TestDurableClaims:
    def test_memory_answers_a_durable_claim(self, store):
        d = decide("samba", "rationale", store)
        assert d.source is AnswerSource.MEMORY
        assert not d.must_look

    def test_durable_claims_never_probe_however_old(self, store):
        d = decide("samba", "rationale", store, now=time.time() + SIX_WEEKS)
        assert d.source is AnswerSource.MEMORY


class TestStateClaims:
    def test_unseen_state_must_be_probed(self, store):
        d = decide("service:nginx", "service_status", store)
        assert d.source is AnswerSource.PROBE
        assert "never observed" in d.reason

    def test_a_fresh_reading_counts_as_looking(self, store):
        store.record_state("service:nginx", "service_status", "running", "tracker")
        d = decide("service:nginx", "service_status", store)
        assert d.source is AnswerSource.LEDGER
        assert d.value == "running"
        assert d.age_seconds < 1.0
        assert not d.must_look

    def test_a_stale_reading_is_a_memory_and_must_be_probed(self, store):
        store.record_state("service:nginx", "service_status", "running", "tracker")
        d = decide("service:nginx", "service_status", store,
                   now=time.time() + SIX_WEEKS)
        assert d.source is AnswerSource.PROBE
        assert d.must_look
        assert "memory, not an observation" in d.reason

    def test_the_freshness_dial_moves_the_line(self, store):
        store.record_state("system", "cpu_load", "42%", "tracker")
        later = time.time() + 120
        assert decide("system", "cpu_load", store, now=later).source is AnswerSource.PROBE
        assert decide("system", "cpu_load", store, fresh_seconds=600,
                      now=later).source is AnswerSource.LEDGER

    def test_boundary_is_inclusive(self, store):
        t0 = time.time()
        store.record_state("system", "cpu_load", "42%", "t", now=t0)
        at_edge = t0 + DEFAULT_FRESH_SECONDS
        assert decide("system", "cpu_load", store, now=at_edge).source is AnswerSource.LEDGER
        assert decide("system", "cpu_load", store,
                      now=at_edge + 0.001).source is AnswerSource.PROBE

    def test_no_ledger_means_probe(self):
        d = decide("service:nginx", "service_status", store=None)
        assert d.source is AnswerSource.PROBE

    def test_supersession_is_respected(self, store):
        """The stale value must never win: current_state returns only the open one."""
        store.record_state("service:nginx", "service_status", "running", "t")
        store.record_state("service:nginx", "service_status", "stopped", "t")
        assert decide("service:nginx", "service_status", store).value == "stopped"

    def test_subjects_do_not_bleed(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        d = decide("service:smbd", "service_status", store)
        assert d.source is AnswerSource.PROBE


class TestPreamble:
    def test_probe_of_a_known_fact_says_when_it_was_last_seen(self, store):
        t0 = time.time()
        store.record_state("service:nginx", "service_status", "running", "t", now=t0)
        d = decide("service:nginx", "service_status", store, now=t0 + SIX_WEEKS)
        assert d.preamble().startswith("We last saw that on ")
        assert "checking now" in d.preamble()

    def test_a_fresh_answer_needs_no_preamble(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        assert decide("service:nginx", "service_status", store).preamble() == ""

    def test_an_unseen_fact_has_nothing_to_date(self, store):
        assert decide("service:nginx", "service_status", store).preamble() == ""

    def test_memory_never_announces_a_check(self, store):
        assert decide("samba", "rationale", store).preamble() == ""


class TestTheJulyShareScenario:
    """The worked example: a note from six weeks ago, asked about today."""

    def test_the_old_note_does_not_get_to_answer(self, store):
        t0 = time.time() - SIX_WEEKS
        store.record_state("share:/srv/media", "mounted", "yes", "thread-jul",
                           thread_id="t-jul", now=t0)

        d = decide("share:/srv/media", "mounted", store)
        assert d.must_look, "a six-week-old reading must not be quoted as current"
        assert d.preamble()

        # after looking, the finding is written back and the next ask is free
        store.record_state("share:/srv/media", "mounted", "no", "probe")
        after = decide("share:/srv/media", "mounted", store)
        assert after.source is AnswerSource.LEDGER
        assert after.value == "no"

        # and the change is auditable back to the thread that made the claim
        hist = store.state_history("share:/srv/media", "mounted")
        assert [h.object for h in hist] == ["yes", "no"]
        assert hist[0].thread_id == "t-jul"
