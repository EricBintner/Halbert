# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B4a -- the one list of turns where nothing optional may be injected.

The gate exists so a lens and a remembered interest cannot disagree about
what a bad moment is. RECALL-v1 shipped with its own copy of this list and
said so; these tests pin both the gate and the fact that recall now asks it
rather than answering for itself.
"""

import pytest

from halbert_core.skills.suppression import SUPPRESSION_REASONS, suppress_lens


class _Signals:
    def __init__(self, **kw):
        self.intent = kw.get("intent", "question")
        self.is_troubleshooting = kw.get("is_troubleshooting", False)
        self.has_error_indicators = kw.get("has_error_indicators", False)
        self.entities = kw.get("entities", set())
        self.detected_domains = kw.get("detected_domains", [])


class _Findings:
    def __init__(self, critical=0, raises=False):
        self._critical = critical
        self._raises = raises

    def list_by_severity(self, severity):
        if self._raises:
            raise RuntimeError("store unreachable")
        return [object()] * (self._critical if severity == "critical" else 0)


class TestTheSignals:

    def test_a_quiet_turn_is_not_suppressed(self):
        assert suppress_lens(_Signals()) is None

    def test_a_diagnostic_turn_is(self):
        assert suppress_lens(_Signals(intent="troubleshooting")) == "the turn is diagnostic"

    def test_the_troubleshooting_flag_counts_too(self):
        assert suppress_lens(_Signals(is_troubleshooting=True)) == "the turn is diagnostic"

    def test_error_indicators_count(self):
        assert suppress_lens(_Signals(has_error_indicators=True)) == (
            "the turn carries error indicators"
        )

    def test_a_pending_confirmation_suppresses(self):
        # A confirmation is a question with a yes/no shape. Anything beside
        # it competes with the only answer the turn is asking for.
        assert suppress_lens(_Signals(), required_confirmation=True) == (
            "a confirmation is pending on this turn"
        )

    def test_the_dial_at_off_suppresses(self):
        assert suppress_lens(_Signals(), proactivity="off") == "the proactivity dial is off"

    def test_lens_intensity_at_off_suppresses(self):
        assert suppress_lens(_Signals(), lens_intensity="off") == "lens intensity is off"

    def test_an_open_critical_finding_suppresses(self):
        assert suppress_lens(_Signals(), finding_store=_Findings(critical=1)) == (
            "a critical finding is open"
        )

    def test_a_finding_at_a_lower_severity_does_not(self):
        # "Something is worth telling you" is not "something is broken".
        assert suppress_lens(_Signals(), finding_store=_Findings(critical=0)) is None

    def test_every_reason_it_can_give_is_on_the_named_list(self):
        # A signal added without appearing in SUPPRESSION_REASONS is one a
        # person can be refused by and never shown.
        seen = {
            suppress_lens(_Signals(intent="troubleshooting")),
            suppress_lens(_Signals(has_error_indicators=True)),
            suppress_lens(_Signals(), required_confirmation=True),
            suppress_lens(_Signals(), proactivity="off"),
            suppress_lens(_Signals(), lens_intensity="off"),
            suppress_lens(_Signals(), finding_store=_Findings(critical=1)),
        }
        assert seen == set(SUPPRESSION_REASONS)


class TestItNeverRaises:

    def test_no_signals_at_all(self):
        assert suppress_lens(None) is None

    def test_a_store_that_throws_does_not_suppress_the_turn(self):
        # The safer *content* is silence; the safer *failure* is not. An
        # unexplainable silence is worse than the content the caller already
        # decided was worth adding.
        assert suppress_lens(_Signals(), finding_store=_Findings(raises=True)) is None

    def test_an_object_that_throws_on_every_attribute(self):
        class _Hostile:
            def __getattr__(self, name):
                raise RuntimeError("no")

        assert suppress_lens(_Hostile()) is None


class TestRecallDelegates:
    """RECALL-v1 kept its own copy of this list. It must not keep two."""

    def _rows(self):
        from halbert_core.continuity.interests import Interest, Origin

        return [Interest(topic="vintage thinkpads", origin=Origin.STATED,
                         reason="remember that I collect vintage thinkpads",
                         actor="user")]

    def test_recall_happens_on_a_clean_turn(self):
        from halbert_core.continuity.recall_interest import select_interest

        signals = _Signals(entities={"thinkpads"})
        assert select_interest(self._rows(), signals) is not None

    @pytest.mark.parametrize("kw,reason", [
        ({"intent": "troubleshooting"}, "the turn is diagnostic"),
        ({"has_error_indicators": True}, "the turn carries error indicators"),
    ])
    def test_recall_is_suppressed_by_the_shared_gate(self, kw, reason):
        from halbert_core.continuity.recall_interest import select_interest

        signals = _Signals(entities={"thinkpads"}, **kw)
        assert suppress_lens(signals) == reason
        assert select_interest(self._rows(), signals) is None

    def test_recall_is_suppressed_by_a_signal_it_never_knew_about(self):
        """The point of delegating: a reason recall's own copy did not have.

        A pending confirmation was on the lens list and not on recall's. If
        recall still answered for itself this would pass a remembered
        interest into a turn that is asking a yes/no question.
        """
        from halbert_core.continuity.recall_interest import select_interest

        signals = _Signals(entities={"thinkpads"})
        assert select_interest(
            self._rows(), signals, required_confirmation=True
        ) is None

    def test_an_open_critical_finding_stops_recall_too(self):
        from halbert_core.continuity.recall_interest import select_interest

        signals = _Signals(entities={"thinkpads"})
        assert select_interest(
            self._rows(), signals, finding_store=_Findings(critical=1)
        ) is None

    def test_the_dial_still_couples_only_at_off(self):
        """"Assertive" must never come to mean *talks about me more*."""
        from halbert_core.continuity.recall_interest import select_interest

        signals = _Signals(entities={"thinkpads"})
        for dial in ("quiet", "balanced", "assertive"):
            assert select_interest(self._rows(), signals, dial=dial) is not None
        assert select_interest(self._rows(), signals, dial="off") is None


class _Skill:
    def __init__(self, name, kind="ops"):
        self.name = name
        self.kind = kind
        self.prompt = f"[{name} expertise]"
        self.safety = None


class _Match:
    def __init__(self, skill, explicit=False):
        self.skill = skill
        self.score = 0
        self.explicit = explicit

    @property
    def name(self):
        return self.skill.name


class _Machine:
    """The two methods under test, lifted off the state machine."""

    from halbert_core.agents.state_machine import AgentStateMachine as _ASM

    _gate_lenses = _ASM._gate_lenses
    _take_lens_refusal = _ASM._take_lens_refusal
    _proactivity_dial = staticmethod(lambda: "balanced")
    _lens_intensity = staticmethod(lambda: "")

    def __init__(self, required_confirmation=False, finding_store=None):
        class _Ctx:
            pass
        self.ctx = _Ctx()
        self.ctx.required_confirmation = required_confirmation
        self.finding_store = finding_store


class TestTheAssembleCallGate:
    """B4a where CD-9 puts it: the assemble call, both paths."""

    def test_a_clean_turn_keeps_the_lens(self):
        m = _Machine()
        matches = [_Match(_Skill("storage-ops")), _Match(_Skill("understated", "lens"))]
        assert m._gate_lenses(matches, _Signals()) == matches

    def test_a_diagnostic_turn_drops_the_lens(self):
        m = _Machine()
        lens = _Match(_Skill("understated", "lens"))
        ops = _Match(_Skill("storage-ops"))
        kept = m._gate_lenses([ops, lens], _Signals(intent="troubleshooting"))
        assert kept == [ops]

    def test_it_keeps_the_ops_skill_on_that_same_turn(self):
        # A turn mid-fault still gets the expertise it matched. Dropping the
        # whole block would make a bad moment also a stupid one.
        m = _Machine()
        ops = _Match(_Skill("storage-ops"))
        kept = m._gate_lenses([ops], _Signals(intent="troubleshooting"))
        assert kept == [ops]

    def test_a_pending_confirmation_drops_the_lens(self):
        m = _Machine(required_confirmation=True)
        lens = _Match(_Skill("understated", "lens"))
        assert m._gate_lenses([lens], _Signals()) == []

    def test_an_open_critical_finding_drops_the_lens(self):
        m = _Machine(finding_store=_Findings(critical=1))
        lens = _Match(_Skill("understated", "lens"))
        assert m._gate_lenses([lens], _Signals()) == []

    def test_the_explicit_path_is_gated_too(self):
        """`match()` returns `_explicit()` first, so a matcher-side gate is
        bypassed by a slash invocation. This one is not."""
        m = _Machine()
        lens = _Match(_Skill("understated", "lens"), explicit=True)
        assert m._gate_lenses([lens], _Signals(intent="troubleshooting")) == []

    def test_a_named_lens_is_refused_out_loud(self):
        m = _Machine()
        lens = _Match(_Skill("understated", "lens"), explicit=True)
        m._gate_lenses([lens], _Signals(intent="troubleshooting"))
        said = m._take_lens_refusal()
        assert "understated" in said
        assert "the turn is diagnostic" in said

    def test_a_lens_nobody_asked_for_is_dropped_quietly(self):
        # Refusing something the person did not ask for is noise about a
        # mechanism they never invoked.
        m = _Machine()
        lens = _Match(_Skill("understated", "lens"))
        m._gate_lenses([lens], _Signals(intent="troubleshooting"))
        assert m._take_lens_refusal() == ""

    def test_the_person_is_told_once(self):
        """Both LLM call sites assemble messages; one telling."""
        m = _Machine()
        lens = _Match(_Skill("understated", "lens"), explicit=True)
        m._gate_lenses([lens], _Signals(intent="troubleshooting"))
        assert m._take_lens_refusal()
        assert m._take_lens_refusal() == ""

    def test_a_missing_lens_dial_is_not_a_lens_dial_set_to_off(self):
        """`lens_intensity` arrives with branch 5. Absent must not read as
        a person who switched lenses off."""
        from halbert_core.skills.suppression import suppress_lens

        assert suppress_lens(_Signals(), lens_intensity="") is None
        assert suppress_lens(_Signals(), lens_intensity="off") == "lens intensity is off"
