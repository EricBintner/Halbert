# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 step 5b: recall_memory answers from the change ledger.

The rule these tests exist to protect is not "the tool works". It is that an
empty answer says *nothing was recorded*, never *nothing changed* — because a
model told the second one will tell the user the config is untouched, which is
a claim the turn has no basis for.
"""

import asyncio

import pytest

from halbert_core.continuity.provenance import (
    FILE_CONTENT_PREDICATE,
    record_file_change,
)
from halbert_core.continuity.state_store import (
    ACTOR_AGENT,
    ACTOR_SYSTEM,
    ACTOR_USER,
    UNRECORDED,
    StateStore,
    default_state_db_path,
)
from halbert_core.obs.audit import set_audit_signer
from halbert_core.tools.recall_memory import RECALL_MEMORY_SCHEMA, recall_memory


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """conftest has no HALBERT_DATA_DIR fixture; without this the tool would
    read and write the developer's real ledger."""
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _call(**args):
    return asyncio.run(recall_memory(args))


def _ledger():
    return StateStore(db_path=str(default_state_db_path()))


def _seed_sshd():
    record_file_change(path="/etc/ssh/sshd_config", reason="shipped default",
                       actor=ACTOR_AGENT, request_id="r1", tool="editor",
                       after_text="PermitRootLogin yes\n")
    record_file_change(path="/etc/ssh/sshd_config",
                       reason="hardening after the audit finding",
                       actor=ACTOR_USER, request_id="r2", tool="editor",
                       before_text="PermitRootLogin yes\n",
                       after_text="PermitRootLogin no\n")


class TestAnsweringFromTheLedger:
    def test_a_recorded_change_is_answered_whole(self):
        _seed_sshd()
        out = _call(path="/etc/ssh/sshd_config")

        assert "hardening after the audit finding" in out   # current reason
        assert "shipped default" in out                     # predecessor reason
        assert ACTOR_USER in out and ACTOR_AGENT in out
        assert "UTC" in out
        assert "request r2" in out

    def test_it_matches_what_the_route_reports(self, tmp_path):
        """One query, two surfaces — duplicating it is how they drift."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from halbert_core.dashboard.routes import state as state_routes

        _seed_sshd()
        app = FastAPI()
        app.include_router(state_routes.router, prefix="/api/state")
        body = TestClient(app).get(
            "/api/state/why", params={"path": "/etc/ssh/sshd_config"}).json()

        assert body["found"] is True
        out = _call(path="/etc/ssh/sshd_config")
        assert body["current"]["reason"] in out
        assert body["current"]["request_id"] in out

    def test_history_is_bounded_and_leads_with_the_current_value(self):
        """_format_tool_observation truncates at 2000 chars; a cut landing
        after 'reason:' would leave a dangling half-reason in the prompt."""
        prev = None
        for i in range(30):
            text = f"line {i}\n"
            record_file_change(path="/etc/busy.conf", reason=f"change {i}",
                               actor=ACTOR_USER, request_id=f"r{i}",
                               tool="editor", before_text=prev, after_text=text)
            prev = text

        out = _call(path="/etc/busy.conf", history=True)
        assert len(out) < 2000, "would be truncated mid-record"
        assert "change 29" in out, "the current value must survive"


class TestAbstaining:
    def test_an_unknown_path_says_nothing_was_recorded(self):
        _seed_sshd()
        out = _call(path="/etc/never-touched.conf")

        assert "no record" in out.lower()
        assert "does not mean nothing changed" in out
        assert "hardening" not in out, "leaked another subject's reason"

    def test_an_empty_ledger_says_so_without_implying_stability(self):
        out = _call(path="/etc/anything.conf")
        assert "does not mean nothing changed" in out

    def test_a_predicate_miss_names_what_the_subject_does_hold(self):
        """Abstaining on a subject the ledger plainly knows is a lie by
        omission — technically honest, practically wrong."""
        store = _ledger()
        store.record_state("service:sshd", "service_status", "running",
                           "state_tracker", reason="tracker: service sweep",
                           actor=ACTOR_SYSTEM)
        store.close()

        out = _call(subject="service:sshd")     # default predicate misses
        assert "service_status" in out
        assert "no record" not in out.lower() or "does hold" in out

    def test_a_read_failure_is_not_an_empty_success(self, monkeypatch):
        """"I could not look" must never render as "there is nothing"."""
        import halbert_core.tools.recall_memory as mod
        from halbert_core.continuity.recall import LedgerUnavailable

        def boom(**kw):
            raise LedgerUnavailable("database is locked")

        monkeypatch.setattr(mod, "recall_state", boom)
        out = _call(path="/etc/x.conf")

        assert "could not be read" in out
        assert "no record" not in out.lower()


class TestUnrecordedIsNeverBlank:
    def test_it_renders_as_an_explicit_statement(self):
        """A bare 'unrecorded' invites paraphrase into something plausible;
        an omitted field is the one a model fills in."""
        record_file_change(path="/etc/x.conf", reason=UNRECORDED,
                           actor=ACTOR_USER, request_id="r1", tool="editor",
                           after_text="a\n")
        out = _call(path="/etc/x.conf")

        assert "not recorded (none was captured at the time)" in out
        assert not any(line.strip().endswith("reason:") for line in out.splitlines())


class TestDisambiguationIsNotSearch:
    def test_a_query_lists_candidates_and_does_not_pick_one(self):
        _seed_sshd()
        out = _call(query="sshd")

        assert "file:/etc/ssh/sshd_config" in out
        assert "Ask again" in out
        assert "hardening" not in out, "answered instead of offering a choice"

    def test_an_unmatched_query_says_what_the_ledger_does_hold(self):
        _seed_sshd()
        out = _call(query="nginx")

        assert "nginx" in out
        assert "file:/etc/ssh/sshd_config" in out

    def test_no_arguments_lists_the_subjects(self):
        _seed_sshd()
        assert "file:/etc/ssh/sshd_config" in _call()

    def test_the_schema_accepts_query(self):
        """The name is taken upstream with a query-shaped contract, so a
        model that learned that shape must not get an error or a blank."""
        props = RECALL_MEMORY_SCHEMA["parameters"]["properties"]
        assert "query" in props
        assert RECALL_MEMORY_SCHEMA["parameters"]["required"] == []


class TestTheRuleReachesTheModelTwice:
    def test_the_schema_states_it(self):
        """Read before the call."""
        desc = RECALL_MEMORY_SCHEMA["description"]
        assert "does NOT mean nothing changed" in desc

    def test_the_result_states_it(self):
        """Read at the moment the answer is composed — observations are the
        only thing that reaches RESPONDING's 'What I've Done' block, so a
        rule stated only in the schema is absent when it matters."""
        assert "does not mean nothing changed" in _call(path="/etc/nope.conf")


class TestRegistrationAndSafety:
    def test_it_is_registered_and_reaches_the_model(self):
        from halbert_core.tools.executor import ToolExecutor

        ex = ToolExecutor()
        assert "recall_memory" in ex.schemas
        names = {s["function"]["name"] for s in ex.get_schemas()}
        assert "recall_memory" in names

    def test_it_classifies_safe(self):
        from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework

        r = ToolSafetyFramework().classify("recall_memory", {"path": "/etc/x"})
        assert r.risk_level == RiskLevel.SAFE
        assert r.allowed and not r.requires_confirmation

    def test_a_restricted_speaker_may_still_ask(self):
        """The fallthrough to MEDIUM would block exactly the speakers least
        able to work around it, and silently: unit tests use the admin role."""
        from halbert_core.tools.role_gate import RoleGate
        from halbert_core.tools.safety import ToolSafetyFramework

        gate = RoleGate(ToolSafetyFramework())
        assert gate.classify("recall_memory", {"path": "/etc/x"},
                             speaker_role="restricted").allowed


class TestAReadFailureIsNeverAnEmptyAnswer:
    """The defect this class exists for: StateStore's reads are fail-soft, so
    a broken ledger returned an empty result, LedgerUnavailable was
    unreachable, and the model was told "nothing was recorded" with full
    confidence. Found by review; these drive the real failures, not a
    monkeypatched helper."""

    def test_a_broken_connection_raises_rather_than_reporting_nothing(self):
        from halbert_core.continuity.recall import LedgerUnavailable, recall_state

        _seed_sshd()
        broken = _ledger()
        broken.close()

        with pytest.raises(LedgerUnavailable):
            recall_state(subject="file:/etc/ssh/sshd_config", store=broken)

    def test_the_store_still_fails_soft_by_default(self):
        """The hot path keeps its contract: a tracker would rather lose a
        reading than break a turn. Only reporting callers pass strict."""
        broken = _ledger()
        broken.close()
        assert broken.current_state() == []
        assert broken.why("a", "b").found is False

    def test_strict_is_what_reporting_callers_use(self):
        broken = _ledger()
        broken.close()
        with pytest.raises(Exception):
            broken.why("a", "b", strict=True)
        with pytest.raises(Exception):
            broken.current_state(strict=True)
        with pytest.raises(Exception):
            broken.state_history("a", "b", strict=True)
        with pytest.raises(Exception):
            broken.by_request("r", strict=True)

    def test_a_store_that_cannot_be_opened_is_reported_not_raised(self, monkeypatch):
        """It used to escape the handler as a raw OSError, straight past the
        branch written to turn it into an honest sentence."""
        import halbert_core.continuity.recall as rc

        def boom(**kw):
            raise OSError("database disk image is malformed")

        monkeypatch.setattr(rc, "StateStore", boom)
        out = _call(path="/etc/x.conf")

        assert "could not be read" in out
        assert "failure to look" in out
        assert "no record" not in out.lower()


class TestTheRiderIsOnEveryAbstainPath:
    """A model that reads any empty answer as "unchanged" will tell someone
    their config is untouched. Every path has to say otherwise."""

    RIDER = "does not mean nothing changed"

    def test_unknown_subject(self):
        _seed_sshd()
        assert self.RIDER in _call(path="/etc/nope.conf")

    def test_predicate_miss(self):
        store = _ledger()
        store.record_state("service:sshd", "service_status", "running", "tracker",
                           reason="tracker: sweep", actor=ACTOR_SYSTEM)
        store.close()
        assert self.RIDER in _call(subject="service:sshd")

    def test_query_with_no_matches(self):
        _seed_sshd()
        assert self.RIDER in _call(query="nginx")

    def test_empty_ledger(self):
        assert self.RIDER in _call(query="anything")
        assert self.RIDER in _call()


class TestPartialListsSaySo:
    def test_a_truncated_subject_list_is_labelled(self):
        """A truncated list presented as complete quietly tells the reader
        the ledger holds nothing else."""
        for i in range(20):
            record_file_change(path=f"/etc/f{i:02d}.conf", reason=f"r{i}",
                               actor=ACTOR_USER, request_id=f"q{i}",
                               tool="editor", after_text=f"{i}\n")
        out = _call()
        assert "showing 12 of 20" in out

    def test_a_complete_list_is_not_labelled(self):
        _seed_sshd()
        assert "showing" not in _call()
