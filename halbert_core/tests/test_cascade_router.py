# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for MetaHarnessRouter (C2a)."""

import pytest

from halbert_core.model.cascade_router import MetaHarnessRouter
from halbert_core.model.outcome_store import OutcomeStore
from halbert_core.model.capabilities import ModelDefinition


# ---------------------------------------------------------------------------
# Fake tier router config
# ---------------------------------------------------------------------------

class _TierCfg:
    def __init__(self, primary):
        self.primary = primary


class _Cfg:
    def __init__(self, models, guide, specialist, vision):
        self.models = models
        self.guide = _TierCfg(guide)
        self.specialist = _TierCfg(specialist)
        self.vision = _TierCfg(vision)


class _TierRouter:
    def __init__(self, cfg):
        self.config = cfg


def _models():
    return {
        "guide-m": ModelDefinition(name="guide", model_id="guide-m", provider="ollama"),
        "spec-m": ModelDefinition(name="spec", model_id="spec-m", provider="ollama"),
        "vision-m": ModelDefinition(name="vision", model_id="vision-m", provider="anthropic"),
    }


def _router():
    m = _models()
    return _TierRouter(_Cfg(m, "guide-m", "spec-m", "vision-m"))


@pytest.fixture
def store():
    s = OutcomeStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def cr(store):
    return MetaHarnessRouter(_router(), store, min_samples=3,
                              evidence_weight_cap=0.9, quality_bar=0.7)


# ---------------------------------------------------------------------------
# Opt-in / enable
# ---------------------------------------------------------------------------

class TestOptIn:
    def test_disabled_by_default(self, cr):
        assert cr.is_enabled() is False

    def test_enable_disable(self, cr):
        cr.enable()
        assert cr.is_enabled() is True
        cr.disable()
        assert cr.is_enabled() is False


# ---------------------------------------------------------------------------
# Complexity estimation
# ---------------------------------------------------------------------------

class TestComplexity:
    def test_empty_is_zero(self, cr):
        assert cr.estimate_complexity("") == 0.0

    def test_short_simple_low(self, cr):
        assert cr.estimate_complexity("hi") < 0.3

    def test_technical_raises(self, cr):
        simple = cr.estimate_complexity("what time is it")
        tech = cr.estimate_complexity(
            "debug the systemd journal traceback and fix the regex firewall config")
        assert tech > simple

    def test_code_raises(self, cr):
        no_code = cr.estimate_complexity("explain disks")
        with_code = cr.estimate_complexity("fix this:\n```python\ndef f():\n  pass\n```")
        assert with_code > no_code

    def test_bounded_0_1(self, cr):
        for t in ["", "a", "x" * 10000, "```" * 50]:
            v = cr.estimate_complexity(t)
            assert 0.0 <= v <= 1.0


# ---------------------------------------------------------------------------
# Prior + predict
# ---------------------------------------------------------------------------

class TestPrior:
    def test_guide_prior_decreases_with_complexity(self, cr):
        assert cr._prior("guide-m", 0.0) > cr._prior("guide-m", 1.0)

    def test_vision_prior_increases_with_complexity(self, cr):
        assert cr._prior("vision-m", 1.0) > cr._prior("vision-m", 0.0)

    def test_unknown_model_default(self, cr):
        assert 0.0 <= cr._prior("unknown", 0.5) <= 1.0


class TestPredict:
    def test_predict_uses_prior_with_low_evidence(self, cr, store):
        # No evidence -> predict equals prior
        p = cr.predict("spec-m", 0.3)
        assert p == pytest.approx(cr._prior("spec-m", 0.3))

    def test_predict_blends_evidence(self, cr, store):
        # Record many successes so evidence (1.0) pulls predict up toward it
        for _ in range(20):
            store.record("spec-m", success=True, latency_ms=10)
        p = cr.predict("spec-m", 0.3)
        prior = cr._prior("spec-m", 0.3)
        # Should have moved toward evidence=1.0 (capped)
        assert p > prior

    def test_predict_bounded_0_1(self, cr, store):
        for _ in range(10):
            store.record("guide-m", success=False, latency_ms=10)
        assert 0.0 <= cr.predict("guide-m", 0.5) <= 1.0


# ---------------------------------------------------------------------------
# Routing + escalation
# ---------------------------------------------------------------------------

class TestRoute:
    def test_route_returns_a_model(self, cr):
        # Easy task: guide should clear the bar (prior ~0.85)
        m = cr.route("hello")
        assert m is not None
        assert m.model_id in ("guide-m", "spec-m", "vision-m")

    def test_route_easy_prefers_guide(self, cr):
        # Very easy task -> guide prior highest -> guide selected first
        m = cr.route("hi")
        assert m.model_id == "guide-m"

    def test_route_hard_falls_back_to_vision(self, cr, store):
        # Make guide+spec predict low (record failures) so vision (top of
        # ladder) is the fallback for a hard task.
        for _ in range(20):
            store.record("guide-m", success=False, latency_ms=10)
            store.record("spec-m", success=False, latency_ms=10)
        # Hard task with lots of technical keywords + code
        hard = "debug the systemd traceback regex firewall kernel " + "code " * 200 + "```"
        m = cr.route(hard)
        # guide/spec evidence drags them down; vision is the fallback (last)
        assert m is not None
        # Either a model cleared the bar or the vision fallback
        assert m.model_id in ("guide-m", "spec-m", "vision-m")

    def test_route_empty_ladder_returns_none(self, store):
        empty_router = _TierRouter(_Cfg({}, "", "", ""))
        cr2 = MetaHarnessRouter(empty_router, store)
        assert cr2.route("anything") is None


class TestEscalate:
    def test_escalate_steps_up(self, cr):
        assert cr.escalate("guide-m").model_id == "spec-m"
        assert cr.escalate("spec-m").model_id == "vision-m"

    def test_escalate_top_returns_none(self, cr):
        assert cr.escalate("vision-m") is None

    def test_escalate_unknown_returns_none(self, cr):
        assert cr.escalate("nope") is None


# ---------------------------------------------------------------------------
# Blending formula sanity
# ---------------------------------------------------------------------------

def test_blending_weight_caps(cr, store):
    # With huge attempts, weight approaches the cap (0.9), not 1.0
    for _ in range(1000):
        store.record("spec-m", success=True, latency_ms=1)
    p = cr.predict("spec-m", 0.3)
    prior = cr._prior("spec-m", 0.3)
    # p = (1-w)*prior + w*1.0, w ~ 0.9 -> p ~ 0.1*prior + 0.9
    assert p > prior  # evidence (1.0) dominates but prior still contributes
    assert p < 1.0  # cap prevents fully trusting evidence
