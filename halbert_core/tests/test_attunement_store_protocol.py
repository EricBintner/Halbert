# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The typed façade over Halbert's store (A-HB-2, A-HB-24).

The store speaks dicts natively so its mechanics are testable with the engine
absent. This is the binding: engine dataclasses in, engine dataclasses out,
and the transaction that ``StandingRequestStore`` requires — "must serialize a
read-modify-write of one subject against every other writer, in-process and
cross-process".

That sentence is the reason Halbert injects a store at all. Five entry points
reach it and a JSON read-modify-write under that access pattern loses the
update; the one it loses is a withdrawal.
"""

import threading

import pytest

pytest.importorskip("haloysius.attunement.ledger",
                    reason="haloysius.attunement.ledger not built yet")

from haloysius.attunement.ledger import StandingRequestStore  # noqa: E402
from haloysius.attunement.types import (  # noqa: E402
    ChannelClass,
    DirectiveKind,
    EngagementOutcome,
    InvitationLevel,
    OutcomeEntry,
    Reaction,
    Severity,
    StandingRequest,
    SubjectRecord,
    SubjectState,
    Tone,
)

from halbert_core.attunement.store import AttunementStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _request(request_id="r1", **kw):
    return StandingRequest(
        id=request_id, subject_id="primary", persona_id="halbert",
        kind=DirectiveKind.WITHDRAW, tone=Tone.IRRITATED,
        created_at="2026-09-06T10:00:00+00:00", expires_at=None,
        resume_on=None, **kw,
    )


def test_the_store_satisfies_the_protocol(store):
    assert isinstance(store, StandingRequestStore)


def test_an_unknown_subject_reads_as_an_empty_record(store):
    record = store.load_subject("halbert", "nobody")
    assert isinstance(record, SubjectRecord)
    assert record.requests == ()
    assert record.state.invitation is InvitationLevel.NORMAL


def test_a_record_round_trips_through_the_engine_types(store):
    record = SubjectRecord(
        requests=(_request(),),
        state=SubjectState(invitation=InvitationLevel.MINIMAL,
                           accepted_interactions=7,
                           recent_acknowledgments=("brief", "one_line_warm")),
    )
    store.save_subject("halbert", "primary", record)
    back = store.load_subject("halbert", "primary")

    assert back.state.invitation is InvitationLevel.MINIMAL
    assert back.state.accepted_interactions == 7
    assert back.state.recent_acknowledgments == ("brief", "one_line_warm")
    assert len(back.requests) == 1
    assert back.requests[0].kind is DirectiveKind.WITHDRAW
    assert back.requests[0].tone is Tone.IRRITATED
    assert back.requests[0].id == "r1"


def test_list_subjects_names_who_we_hold_state_for(store):
    store.save_subject("halbert", "eric", SubjectRecord())
    store.save_subject("halbert", "sam", SubjectRecord())
    store.save_subject("other", "zoe", SubjectRecord())
    assert sorted(store.list_subjects("halbert")) == ["eric", "sam"]


def test_outcomes_round_trip_as_engine_entries(store):
    store.record_outcome(OutcomeEntry(
        attempt_id="a1", subject_id="primary", persona_id="halbert",
        source="finding", severity=Severity.WARNING,
        channel_class=ChannelClass.PUSH, outcome=EngagementOutcome.HOLD,
        reasons=("standing:withdraw",), margin=-0.2,
    ))
    rows = store.list_outcomes("halbert")
    assert len(rows) == 1
    assert isinstance(rows[0], OutcomeEntry)
    assert rows[0].outcome is EngagementOutcome.HOLD
    assert rows[0].severity is Severity.WARNING
    assert rows[0].reasons == ("standing:withdraw",)


def test_update_reaction_takes_the_engine_enum(store):
    store.record_outcome(OutcomeEntry(
        attempt_id="a1", subject_id="primary", persona_id="halbert",
        source="finding", severity=Severity.INFO,
        channel_class=ChannelClass.PUSH, outcome=EngagementOutcome.SPEAK,
        reasons=(), margin=0.5,
    ))
    assert store.update_reaction("a1", Reaction.ENGAGED) is True
    assert store.list_outcomes("halbert")[0].reaction is Reaction.ENGAGED


def test_purge_clears_requests_state_and_outcomes(store):
    store.save_subject("halbert", "eric",
                       SubjectRecord(requests=(_request(),)))
    store.record_outcome(OutcomeEntry(
        attempt_id="a1", subject_id="eric", persona_id="halbert",
        source="finding", severity=Severity.INFO,
        channel_class=ChannelClass.PUSH, outcome=EngagementOutcome.SPEAK,
        reasons=(), margin=0.0,
    ))

    store.purge("halbert", "eric")

    assert store.load_subject("halbert", "eric").requests == ()
    assert store.list_outcomes("halbert") == []


def test_the_transaction_serializes_read_modify_write(tmp_path):
    """The property the injected store exists for. Without serialization the
    last writer wins and one of these withdrawals is lost."""
    db = str(tmp_path / "attunement.db")
    AttunementStore(db_path=db).save_subject("halbert", "primary", SubjectRecord())

    def add(worker):
        s = AttunementStore(db_path=db)
        for i in range(5):
            with s.transaction("halbert", "primary"):
                record = s.load_subject("halbert", "primary")
                s.save_subject(
                    "halbert", "primary",
                    SubjectRecord(
                        requests=record.requests + (_request(f"w{worker}-{i}"),),
                        state=record.state,
                    ),
                )

    threads = [threading.Thread(target=add, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = AttunementStore(db_path=db).load_subject("halbert", "primary")
    assert len(final.requests) == 20, "a read-modify-write was lost"


def test_the_transaction_rolls_back_on_error(store):
    store.save_subject("halbert", "primary", SubjectRecord())
    with pytest.raises(RuntimeError):
        with store.transaction("halbert", "primary"):
            store.save_subject("halbert", "primary",
                               SubjectRecord(requests=(_request(),)))
            raise RuntimeError("boom")
    assert store.load_subject("halbert", "primary").requests == ()
