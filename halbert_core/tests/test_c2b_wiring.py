"""Tests for C2b: tier_router.route_request delegates to MetaHarnessRouter
when enabled and uses the heuristic path (with the shared estimate_complexity)
when disabled."""

import pytest

from halbert_core.model.tier_router import TierRouter, ModelSelection
from halbert_core.model.cascade_router import MetaHarnessRouter
from halbert_core.model.outcome_store import OutcomeStore
from halbert_core.model.capabilities import ModelDefinition, ModelTier


class _TierCfg:
    def __init__(self, primary):
        self.primary = primary


class _Cfg:
    def __init__(self, models, guide, specialist, vision,
                 complexity_threshold=0.5, force_specialist_tasks=None,
                 prefer_reasoning=True):
        self.models = models
        self.guide = _TierCfg(guide)
        self.specialist = _TierCfg(specialist)
        self.vision = _TierCfg(vision)
        self.complexity_threshold = complexity_threshold
        self.force_specialist_tasks = force_specialist_tasks or []
        self.prefer_reasoning = prefer_reasoning


def _models():
    return {
        "guide-m": ModelDefinition(name="guide", model_id="guide-m", provider="ollama"),
        "spec-m": ModelDefinition(name="spec", model_id="spec-m", provider="ollama"),
        "vision-m": ModelDefinition(name="vision", model_id="vision-m", provider="anthropic"),
    }


def _router():
    r = TierRouter.__new__(TierRouter)
    r.outcome_store = OutcomeStore(":memory:")
    r.config = _Cfg(_models(), "guide-m", "spec-m", "vision-m")
    r.cascade_router = MetaHarnessRouter(r, r.outcome_store)
    return r


def test_cascade_disabled_by_default():
    r = _router()
    assert r.cascade_router.is_enabled() is False


def test_route_request_uses_cascade_when_enabled():
    r = _router()
    r.cascade_router.enable()
    sel = r.route_request("hi")  # easy task
    assert sel.reason == "cascade_router"
    assert sel.fallback_used is False
    # Easy task -> guide clears the bar -> guide selected
    assert sel.model.model_id == "guide-m"


def test_route_request_heuristic_when_disabled():
    r = _router()
    called = {}

    def fake_select(tier, require_reasoning=False, complexity_score=None,
                    require_vision=False):
        called["tier"] = tier
        called["complexity"] = complexity_score
        return ModelSelection(model=_models()["guide-m"], reason="heuristic")

    r.select_model = fake_select
    sel = r.route_request("hi")  # easy, no override
    assert sel.reason == "heuristic"
    assert called["tier"] is ModelTier.GUIDE
    # complexity came from the shared estimate_complexity (not _score_complexity)
    assert called["complexity"] is not None
    assert 0.0 <= called["complexity"] <= 1.0


def test_route_request_hard_task_routes_to_specialist_heuristic():
    r = _router()
    called = {}

    def fake_select(tier, require_reasoning=False, complexity_score=None,
                    require_vision=False):
        called["tier"] = tier
        return ModelSelection(model=_models()["spec-m"], reason="heuristic")

    r.select_model = fake_select
    # Lots of technical keywords + code -> high complexity -> specialist
    hard = "debug the systemd traceback regex firewall kernel " + "code " * 200 + "```"
    r.route_request(hard)
    assert called["tier"] is ModelTier.SPECIALIST


def test_route_request_prefer_specialist_override_applies_even_when_enabled():
    r = _router()
    r.cascade_router.enable()
    called = {}

    def fake_select(tier, require_reasoning=False, complexity_score=None,
                    require_vision=False):
        called["tier"] = tier
        return ModelSelection(model=_models()["spec-m"], reason="override")

    r.select_model = fake_select
    sel = r.route_request("hi", prefer_specialist=True)
    assert sel.reason == "override"
    assert called["tier"] is ModelTier.SPECIALIST


def test_route_request_vision_for_images():
    r = _router()
    called = {}

    def fake_select(tier, require_reasoning=False, complexity_score=None,
                    require_vision=False):
        called["tier"] = tier
        called["vision"] = require_vision
        return ModelSelection(model=_models()["vision-m"], reason="vision")

    r.select_model = fake_select
    r.route_request("describe this", has_images=True)
    assert called["tier"] is ModelTier.VISION
    assert called["vision"] is True


def test_disabled_path_uses_original_score_complexity():
    """Regression (review finding): the cascade-disabled (default) path must be
    byte-identical to the pre-C2b heuristic — complexity_score must come from
    the restored _score_complexity, which scores differently than
    MetaHarnessRouter.estimate_complexity for realistic queries."""
    r = _router()
    assert r.cascade_router.is_enabled() is False
    called = {}

    def fake_select(tier, require_reasoning=False, complexity_score=None,
                    require_vision=False):
        called["complexity"] = complexity_score
        return ModelSelection(model=_models()["guide-m"], reason="heuristic")

    r.select_model = fake_select
    # Scorers diverge on this query: estimate_complexity -> 0.08,
    # _score_complexity -> 0.30. Equality with the old scorer asserts parity.
    query = "write a script to fix the error"
    r.route_request(query)
    assert called["complexity"] == r._score_complexity(query)

    # Same parity requirement on the prefer_specialist override when disabled
    called.clear()
    r.route_request(query, prefer_specialist=True)
    assert called["complexity"] == r._score_complexity(query)