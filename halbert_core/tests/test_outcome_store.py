"""Tests for OutcomeStore (A3) and tier_router outcome recording."""

import time
import pytest

from halbert_core.model.outcome_store import OutcomeStore
from halbert_core.model.tier_router import TierRouter, ModelSelection
from halbert_core.model.capabilities import ModelDefinition
from halbert_core.model.providers.base import GenerationError, ModelResponse


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestOutcomeStoreRecordAndStats:
    def test_record_success_and_stats(self):
        store = OutcomeStore(":memory:")
        store.record("model-a", success=True, latency_ms=100.0,
                     input_tokens=10, output_tokens=20, cost_usd=0.01)
        store.record("model-a", success=False, latency_ms=200.0,
                     input_tokens=5, output_tokens=0, cost_usd=0.005)
        stats = store.stats_for("model-a")
        assert stats["attempts"] == 2
        assert stats["successes"] == 1
        assert stats["success_rate"] == 0.5
        assert stats["avg_latency"] == pytest.approx(150.0)
        store.close()

    def test_stats_for_unknown_model_is_zero(self):
        store = OutcomeStore(":memory:")
        stats = store.stats_for("never")
        assert stats["attempts"] == 0
        assert stats["success_rate"] == 0.0
        store.close()

    def test_per_model_isolation(self):
        store = OutcomeStore(":memory:")
        store.record("a", True, latency_ms=10)
        store.record("b", False, latency_ms=50)
        assert store.stats_for("a")["success_rate"] == 1.0
        assert store.stats_for("b")["success_rate"] == 0.0
        store.close()

    def test_summary_aggregates(self):
        store = OutcomeStore(":memory:")
        store.record("a", True, latency_ms=10)
        store.record("a", True, latency_ms=30)
        store.record("b", False, latency_ms=50)
        s = store.summary()
        models = {row["model"]: row for row in s}
        assert models["a"]["attempts"] == 2
        assert models["a"]["success_rate"] == 1.0
        assert models["b"]["attempts"] == 1
        store.close()

    def test_complexity_and_task_optional(self):
        store = OutcomeStore(":memory:")
        store.record("a", True, latency_ms=5, complexity=0.7, task="summarize")
        store.record("a", True, latency_ms=5)  # no complexity/task
        stats = store.stats_for("a")
        assert stats["attempts"] == 2
        store.close()


class TestOutcomeStoreBestEffort:
    def test_record_after_close_does_not_raise(self):
        store = OutcomeStore(":memory:")
        store.close()
        # Should not raise even though the connection is closed
        store.record("a", True, latency_ms=1)
        assert store.stats_for("a")["attempts"] == 0

    def test_bad_db_path_does_not_raise_on_construct(self, tmp_path):
        # Pointing at a directory path (cannot create file there) is tolerated
        store = OutcomeStore(str(tmp_path))  # tmp_path is a dir, not a file
        # construction must not raise; recording best-effort
        store.record("a", True, latency_ms=1)

    def test_record_non_numeric_tokens_coerced(self):
        store = OutcomeStore(":memory:")
        store.record("a", True, latency_ms="1", input_tokens=None,
                     output_tokens="5", cost_usd=None)
        stats = store.stats_for("a")
        assert stats["attempts"] == 1
        store.close()


# ---------------------------------------------------------------------------
# Integration: tier_router.generate() records outcomes
# ---------------------------------------------------------------------------

def _model():
    return ModelDefinition(name="test", model_id="test-model", provider="ollama")


class _Provider:
    """Provider that succeeds on demand and records call count."""

    def __init__(self, *, fail_first=0, status=500):
        self.calls = 0
        self.fail_first = fail_first
        self.status = status

    def generate(self, prompt, model_id, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise GenerationError("boom", status_code=self.status)
        return ModelResponse(
            text="ok", model_id=model_id, provider="ollama",
            tokens_used=30, latency_ms=12.0,
            metadata={"input_tokens": 10, "output_tokens": 20},
        )


def _router(provider, *, fallback_used=False, store=None):
    router = TierRouter.__new__(TierRouter)
    from halbert_core.model.rate_limiter import RateLimiter
    router.rate_limiter = RateLimiter(max_retries=3, jitter_fn=lambda: 0.0)
    router._model_health = {}
    router._providers = {}
    router.outcome_store = store if store is not None else OutcomeStore(":memory:")
    selection = ModelSelection(
        model=_model(), reason="test", fallback_used=fallback_used
    )
    router.route_request = lambda **kw: selection
    router._get_provider = lambda model: provider
    return router, selection


def test_generate_records_success_outcome(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    prov = _Provider()
    store = OutcomeStore(":memory:")
    router, sel = _router(prov, store=store)
    resp, _ = router.generate("hi")
    assert resp.text == "ok"
    stats = store.stats_for(sel.model.model_id)
    assert stats["attempts"] == 1
    assert stats["successes"] == 1
    assert stats["success_rate"] == 1.0


def test_generate_records_failure_outcome_when_no_fallback(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    # status 500 -> non-rate-limit, no retry, no fallback -> raise
    prov = _Provider(fail_first=99, status=500)
    store = OutcomeStore(":memory:")
    router, sel = _router(prov, fallback_used=True, store=store)
    with pytest.raises(GenerationError):
        router.generate("hi")
    stats = store.stats_for(sel.model.model_id)
    assert stats["attempts"] == 1
    assert stats["successes"] == 0
    assert stats["success_rate"] == 0.0


def test_generate_records_failure_then_fallback_success(monkeypatch):
    """Primary 429-exhausted (records failure), fallback succeeds (records success)."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    primary = _Provider(fail_first=99, status=429)
    fallback = _Provider(fail_first=0)

    from halbert_core.model.rate_limiter import RateLimiter
    router = TierRouter.__new__(TierRouter)
    router.rate_limiter = RateLimiter(max_retries=2, jitter_fn=lambda: 0.0)
    router._model_health = {}
    router._providers = {}
    router.outcome_store = OutcomeStore(":memory:")

    primary_sel = ModelSelection(model=_model(), reason="primary", fallback_used=False)
    fallback_sel = ModelSelection(model=_model(), reason="fallback", fallback_used=True)
    state = {"n": 0}

    def fake_route(**kw):
        state["n"] += 1
        return primary_sel if state["n"] == 1 else fallback_sel

    def fake_get_provider(model):
        return primary if state["n"] == 1 else fallback

    router.route_request = fake_route
    router._get_provider = fake_get_provider

    resp, _ = router.generate("hi")
    assert resp.text == "ok"
    stats = router.outcome_store.stats_for("test-model")
    # One outcome per generate() route: primary recorded a single failure
    # (after exhausting retries), fallback recorded a single success.
    assert stats["attempts"] == 2
    assert stats["successes"] == 1


def test_generate_without_outcome_store_does_not_break(monkeypatch):
    """A router with no outcome_store (tests bypassing __init__) must not break."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    prov = _Provider()
    router = TierRouter.__new__(TierRouter)
    from halbert_core.model.rate_limiter import RateLimiter
    router.rate_limiter = RateLimiter(jitter_fn=lambda: 0.0)
    router._model_health = {}
    router._providers = {}
    # deliberately no outcome_store attribute
    selection = ModelSelection(model=_model(), reason="test", fallback_used=True)
    router.route_request = lambda **kw: selection
    router._get_provider = lambda model: prov
    resp, _ = router.generate("hi")
    assert resp.text == "ok"