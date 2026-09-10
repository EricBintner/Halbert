# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-02 Phases C and E: the walk stops, the record says what it capped,
and the tee's scrub reaches the whole event.

- **A12-G3, live half.** ``decide_ingress`` stops at the first BLOCK, but
  the BUILDER loop above it does not: ``for build in builders:
  gates.append(await build(...))`` runs every builder, and the gate
  builders are documented as read-only but are not. On
  ``POST /api/guest/private/assign`` and ``POST /api/guest/forget`` the
  second builder calls ``current_guest()``, which can fire the session
  keepalive -- an outbound HTTP request to a sibling home -- and can end
  a live session and notify observers. So an off-machine caller refused
  403 at the local-admin gate could still make this machine talk to a
  sibling home, and end somebody's guest session, while being told no.
- **A12-G5.** The reason codes are a closed set at the origin (a compile
  error if one is unregistered) and a bare ``str`` here, with the deny
  payload echoing the raw machine code as the human message when it is
  unmapped. Every code today happens to be mapped; nothing said so.
- **A12-G7.** The role cap is the moment a claim changes what a turn may
  do, and it left a WARNING and nothing else -- and only when the cap
  bit. The audit record kept tool, args, session, success and error, and
  not the fact that a weaker claim had narrowed the role.
- **A12-G8.** ``guest_homes.yml`` holds a bearer token and is written
  atomically without an fsync, so a power loss can leave it truncated;
  ``list_homes`` swallows that and returns [], and the token has to be
  re-entered.
- **A09 bug 3.** The turn-event tee scrubs top-level strings only, so a
  secret one level down in a nested payload crossed the wire.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# A12-G3 — a refused caller does not run the rest of the walk
# ---------------------------------------------------------------------------

class TestTheWalkStopsAtTheFirstBlock:
    @pytest.fixture
    def gates(self):
        from halbert_core.persona.admission import allow, block

        return allow, block

    def _run(self, builders, monkeypatch):
        import asyncio

        from halbert_core.dashboard.routes import guest as guest_routes

        monkeypatch.setitem(guest_routes._ROUTE_GATES, "test_route", builders)
        return asyncio.run(guest_routes._admit("test_route", request=None))

    def test_a_builder_after_a_block_never_runs(self, gates, monkeypatch):
        from fastapi import HTTPException

        allow, block = gates
        ran = []

        async def first(request, peer, body):
            ran.append("first")
            return block("local_admin", "boundary", "not_local_admin", 403)

        async def second(request, peer, body):
            ran.append("second")
            return allow("guest_fronting", "state")

        with pytest.raises(HTTPException):
            self._run([first, second], monkeypatch)
        assert ran == ["first"], (
            "the second builder ran after the caller was already refused")

    def test_every_builder_runs_when_nothing_blocks(self, gates, monkeypatch):
        allow, _ = gates
        ran = []

        def _builder(name):
            async def build(request, peer, body):
                ran.append(name)
                return allow(name, "state")
            return build

        decision = self._run([_builder("a"), _builder("b")], monkeypatch)
        assert ran == ["a", "b"]
        assert decision.admission == "dispatch"

    def test_the_gate_graph_records_what_was_evaluated_and_no_more(
            self, gates, monkeypatch):
        """A denial is answerable with "dropped at gate X, reason Y". A
        graph listing gates that were never evaluated would be answering
        with something that did not happen."""
        from fastapi import HTTPException

        allow, block = gates

        async def first(request, peer, body):
            return block("local_admin", "boundary", "not_local_admin", 403)

        async def second(request, peer, body):  # pragma: no cover - must not run
            raise AssertionError("second builder ran")

        with pytest.raises(HTTPException) as caught:
            self._run([first, second], monkeypatch)
        payload = caught.value.detail
        assert payload["reason_code"] == "not_local_admin"

    def test_a_skip_also_stops_the_walk(self, gates, monkeypatch):
        from halbert_core.persona.admission import Gate, GateEffect

        allow, _ = gates
        ran = []

        async def first(request, peer, body):
            ran.append("first")
            return Gate("quiet_hours", "state", GateEffect.SKIP, False,
                        "quiet_hours")

        async def second(request, peer, body):
            ran.append("second")
            return allow("b", "state")

        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self._run([first, second], monkeypatch)
        assert ran == ["first"]


# ---------------------------------------------------------------------------
# A12-G5 — the reason codes are a closed set, and now it is pinned
# ---------------------------------------------------------------------------

class TestReasonCodesAreClosed:
    def test_every_block_site_uses_a_registered_code(self):
        """The origin makes an unregistered code a compile error. Here the
        equivalent is a test that reads the source: every ``block(...)``
        call in the guest routes and the talk door names a code the
        registry has words for."""
        import ast
        import pathlib

        from halbert_core.persona.admission import REASON_TEXT

        root = pathlib.Path(__file__).resolve().parents[1] / "halbert_core"
        unregistered = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None)
                if name not in ("block", "_block"):
                    continue
                if len(node.args) < 3:
                    continue
                code = node.args[2]
                if isinstance(code, ast.Constant) and isinstance(code.value, str):
                    if code.value not in REASON_TEXT:
                        unregistered.append(
                            f"{path.relative_to(root)}:{node.lineno} {code.value}")
        assert unregistered == [], (
            f"reason codes with no words for a person: {unregistered}")

    def test_the_payload_never_echoes_a_raw_code_as_the_message(self):
        from halbert_core.persona.admission import deny_payload

        payload = deny_payload("some_gate", "a_code_nobody_registered")
        assert payload["reason_code"] == "a_code_nobody_registered"
        assert payload["message"] != "a_code_nobody_registered"
        assert payload["message"]


# ---------------------------------------------------------------------------
# A12-G7 — the capping fact reaches the record
# ---------------------------------------------------------------------------

class TestTheRoleCapIsRecorded:
    def test_a_capped_call_records_what_capped_it(self):
        from halbert_core.persona.claims import ClaimStrength
        from halbert_core.tools.role_gate import RoleGate
        from halbert_core.tools.safety import ToolSafetyFramework

        gate = RoleGate(ToolSafetyFramework())
        observation = gate.observe_role(
            "admin", claim_strength=ClaimStrength.UNVERIFIED)
        assert observation.stated_role == "admin"
        assert observation.effective_role != "admin"
        assert observation.capped is True
        assert observation.claim_strength == "unverified"

    def test_an_uncapped_call_still_records_the_claim(self):
        """The audit's own point: the no-op path was SILENT, so the record
        could not tell "nothing capped it" from "nothing looked"."""
        from halbert_core.persona.claims import ClaimStrength
        from halbert_core.tools.role_gate import RoleGate
        from halbert_core.tools.safety import ToolSafetyFramework

        gate = RoleGate(ToolSafetyFramework())
        observation = gate.observe_role(
            "admin", claim_strength=ClaimStrength.VERIFIED)
        assert observation.capped is False
        assert observation.effective_role == "admin"
        assert observation.claim_strength == "verified"

    def test_no_claim_at_all_is_a_third_answer(self):
        """A typed turn binds no claim. That is not "verified" and it is
        not "capped" -- it is "the axis did not apply here"."""
        from halbert_core.tools.role_gate import RoleGate
        from halbert_core.tools.safety import ToolSafetyFramework

        observation = RoleGate(ToolSafetyFramework()).observe_role("admin")
        assert observation.claim_strength is None
        assert observation.capped is False
        assert observation.effective_role == "admin"

    def test_the_executor_carries_it_into_the_audit(self, tmp_path):
        import inspect

        from halbert_core.tools import executor as executor_module

        src = inspect.getsource(executor_module)
        assert "observe_role" in src, (
            "the executor must ask for the capping fact, not just the role")
        audit = inspect.getsource(executor_module.ToolExecutor._audit)
        assert "claim" in audit


# ---------------------------------------------------------------------------
# A12-G8 — the file that holds a bearer token is flushed
# ---------------------------------------------------------------------------

def test_guest_homes_is_fsynced_before_the_rename():
    """One line of hardening on a file that stores a credential.

    ``list_homes`` swallows a malformed or truncated file and returns [],
    so a post-power-loss boot reports no homes at all and the token has to
    be re-entered by hand.
    """
    import inspect

    from halbert_core.persona import guest_homes

    lines = inspect.getsource(guest_homes._save).splitlines()

    def _at(needle):
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if needle in stripped:
                return i
        raise AssertionError(f"{needle} is not in _save")

    assert _at("f.flush()") < _at("os.fsync(") < _at("os.replace(")


def test_a_written_home_reads_back(tmp_path, monkeypatch):
    from halbert_core.persona import guest_homes

    monkeypatch.setattr(guest_homes, "_path",
                        lambda: tmp_path / guest_homes.FILENAME)
    guest_homes.add_home(base_url="https://example.invalid",
                         label="Mine", token="t0ken")
    assert [h.label for h in guest_homes.list_homes()] == ["Mine"]
    # The token is on disk -- that is what the fsync protects. list_homes
    # does not hand it back, which is its own correct behaviour.
    written = tmp_path / guest_homes.FILENAME
    assert written.exists() and "t0ken" in written.read_text()


# ---------------------------------------------------------------------------
# A09 bug 3 — the tee scrubs the whole event, not its top layer
# ---------------------------------------------------------------------------

class TestTheTeeScrubsAllTheWayDown:
    def _tee(self):
        from halbert_core.agents.turn_event_tee import TurnEventTee

        tee = TurnEventTee()
        seen = []
        tee.subscribe(seen.append)
        return tee, seen

    def test_a_nested_secret_is_scrubbed(self):
        from halbert_core.ingestion.redaction_registry import get_global_registry

        get_global_registry().register("hunter2-hunter2")
        tee, seen = self._tee()
        tee.publish({
            "event": "tool_complete", "session_id": "s1",
            "result": {"stdout": "password is hunter2-hunter2"},
        })
        assert "hunter2-hunter2" not in str(seen)

    def test_a_secret_inside_a_list_is_scrubbed(self):
        from halbert_core.ingestion.redaction_registry import get_global_registry

        get_global_registry().register("swordfish-2026")
        tee, seen = self._tee()
        tee.publish({"event": "tool_complete", "session_id": "s1",
                     "lines": ["a", ["b", "swordfish-2026"]]})
        assert "swordfish-2026" not in str(seen)

    def test_a_top_level_string_is_still_scrubbed(self):
        from halbert_core.ingestion.redaction_registry import get_global_registry

        get_global_registry().register("topsecret-2026")
        tee, seen = self._tee()
        tee.publish({"event": "tool_complete", "session_id": "s1",
                     "note": "topsecret-2026"})
        assert "topsecret-2026" not in str(seen)

    def test_every_event_carries_a_sequence_and_a_timestamp(self):
        tee, seen = self._tee()
        tee.publish({"event": "turn_started", "session_id": "s1"})
        tee.publish({"event": "turn_ended", "session_id": "s1"})
        assert [e["seq"] for e in seen] == [1, 2]
        assert all(e["ts"] for e in seen)

    def test_the_sequence_is_monotonic_across_sessions(self):
        """One stream, one counter: a consumer stitching two sessions must
        be able to order them without trusting a wall clock."""
        tee, seen = self._tee()
        tee.publish({"event": "turn_started", "session_id": "s1"})
        tee.publish({"event": "turn_started", "session_id": "s2"})
        assert seen[1]["seq"] > seen[0]["seq"]

    def test_a_turn_scoped_event_without_a_session_is_refused(self):
        tee, seen = self._tee()
        tee.publish({"event": "tool_complete", "result": {}})
        assert seen == []

    def test_an_event_that_is_not_turn_scoped_needs_no_session(self):
        tee, seen = self._tee()
        tee.publish({"event": "hello"})
        assert len(seen) == 1
