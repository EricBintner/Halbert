# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for RateLimiter (A2b) and tier_router rate-limit retry wiring."""

import time
import pytest

from halbert_core.model.rate_limiter import RateLimiter, RetryState
from halbert_core.model.tier_router import TierRouter, ModelSelection
from halbert_core.model.capabilities import ModelDefinition
from halbert_core.model.providers.base import GenerationError, ModelResponse


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestRateLimiterShouldRetry:
    def test_429_retries_within_cap(self):
        rl = RateLimiter(max_retries=3)
        assert rl.should_retry(429, {}, 0) is True
        assert rl.should_retry(429, {}, 2) is True

    def test_529_retries(self):
        rl = RateLimiter(max_retries=3)
        assert rl.should_retry(529, {}, 0) is True

    def test_exhausts_at_max(self):
        rl = RateLimiter(max_retries=3)
        assert rl.should_retry(429, {}, 3) is False

    def test_non_rate_limit_status_does_not_retry(self):
        rl = RateLimiter(max_retries=3)
        assert rl.should_retry(500, {}, 0) is False
        assert rl.should_retry(None, {}, 0) is False
        assert rl.should_retry(200, {}, 0) is False

    def test_is_rate_limited(self):
        assert RateLimiter.is_rate_limited(429) is True
        assert RateLimiter.is_rate_limited(529) is True
        assert RateLimiter.is_rate_limited(500) is False
        assert RateLimiter.is_rate_limited(None) is False


class TestRateLimiterWaitTime:
    def test_retry_after_seconds_header(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, {"retry-after": "12"}, 0)
        assert wait == 12.0

    def test_retry_after_capped_at_max(self):
        rl = RateLimiter(max_backoff=30.0, jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, {"retry-after": "999"}, 0)
        assert wait == 30.0

    def test_retry_after_ms_header(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, {"retry-after-ms": "2500"}, 0)
        assert wait == 2.5

    def test_retry_after_case_insensitive(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, {"Retry-After": "5"}, 0)
        assert wait == 5.0

    def test_retry_after_http_date(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        future = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                               time.gmtime(time.time() + 10))
        wait = rl.get_wait_time(429, {"retry-after": future}, 0)
        # Should be ~10s (allow scheduling slack)
        assert 7.0 <= wait <= 11.0

    def test_exponential_backoff_with_jitter_when_no_header(self):
        rl = RateLimiter(base_backoff=1.0, max_backoff=60.0, jitter_fn=lambda: 0.5)
        wait = rl.get_wait_time(429, {}, attempt=2)
        # 1 * 2^2 + 0.5*1 = 4.5
        assert wait == pytest.approx(4.5, abs=0.01)

    def test_backoff_capped(self):
        rl = RateLimiter(base_backoff=1.0, max_backoff=10.0, jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, {}, attempt=20)
        assert wait == 10.0

    def test_no_headers_uses_backoff(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        wait = rl.get_wait_time(429, None, 0)
        assert wait == pytest.approx(1.0, abs=0.01)


class TestRateLimiterState:
    def test_record_retry_and_status(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        rl.record_retry("model-a", 429, {"retry-after": "2"})
        st = rl.status("model-a")
        assert st["attempts"] == 1
        assert st["last_status_code"] == 429
        assert st["last_retry_after"] == 2.0
        assert st["rate_limited"] is True

    def test_reset_clears_state(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        rl.record_retry("model-a", 429, {"retry-after": "1"})
        rl.reset("model-a")
        st = rl.status("model-a")
        assert st["attempts"] == 0
        assert st["rate_limited"] is False

    def test_per_model_state_isolated(self):
        rl = RateLimiter(jitter_fn=lambda: 0.0)
        rl.record_retry("model-a", 429, {"retry-after": "1"})
        rl.record_retry("model-b", 529, {"retry-after": "3"})
        assert rl.status("model-a")["last_status_code"] == 429
        assert rl.status("model-b")["last_status_code"] == 529

    def test_status_unknown_model(self):
        rl = RateLimiter()
        st = rl.status("never-seen")
        assert st["attempts"] == 0
        assert st["rate_limited"] is False


class TestRetryStateDataclass:
    def test_defaults(self):
        s = RetryState()
        assert s.attempts == 0
        assert s.last_status_code is None
        assert s.blocked_until == 0.0


# ---------------------------------------------------------------------------
# Integration: TierRouter.generate() rate-limit retry wiring
# ---------------------------------------------------------------------------

def _model():
    return ModelDefinition(name="test", model_id="test-model", provider="ollama")


def _router_with_provider(provider, *, fallback_used=False):
    """Build a TierRouter bypassing config loading, with a stub provider."""
    router = TierRouter.__new__(TierRouter)
    router.rate_limiter = RateLimiter(max_retries=3, jitter_fn=lambda: 0.0)
    router._model_health = {}
    router._providers = {}
    selection = ModelSelection(
        model=_model(), reason="test", fallback_used=fallback_used
    )
    router.route_request = lambda **kw: selection
    router._get_provider = lambda model: provider
    return router, selection


class _FlakyProvider:
    """Provider that raises GenerationError(429) for the first N calls then succeeds."""
    def __init__(self, fail_times, status=429, headers=None):
        self.fail_times = fail_times
        self.status = status
        self.headers = headers or {}
        self.calls = 0

    def generate(self, prompt, model_id, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise GenerationError(
                f"rate limited {self.status}",
                status_code=self.status,
                headers=self.headers,
            )
        return ModelResponse(
            text="ok", model_id=model_id, provider="ollama",
            tokens_used=10, latency_ms=1.0,
        )


def test_generate_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    prov = _FlakyProvider(fail_times=2, headers={"retry-after": "1"})
    router, sel = _router_with_provider(prov)
    resp, s = router.generate("hi")
    assert resp.text == "ok"
    assert prov.calls == 3  # 2 failures + 1 success
    # Success resets rate-limit state
    assert router.rate_limiter.status(sel.model.model_id)["attempts"] == 0


def test_generate_429_exhausted_raises_when_no_fallback(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    prov = _FlakyProvider(fail_times=99)  # always 429
    router, sel = _router_with_provider(prov, fallback_used=True)
    with pytest.raises(GenerationError):
        router.generate("hi")
    # max_retries=3 -> 1 initial + 3 retries = 4 calls before giving up
    assert prov.calls == 4


def test_generate_non_rate_limit_error_no_retry(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    # status 500 is NOT a rate-limit -> no retry, immediate fallback/raise
    prov = _FlakyProvider(fail_times=99, status=500)
    router, sel = _router_with_provider(prov, fallback_used=True)
    with pytest.raises(GenerationError):
        router.generate("hi")
    assert prov.calls == 1  # no retries for non-rate-limit


def test_generate_429_falls_back_to_fallback_model(monkeypatch):
    """When fallback_used is False, an exhausted rate limit re-routes."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    primary = _FlakyProvider(fail_times=99)  # always 429

    router = TierRouter.__new__(TierRouter)
    router.rate_limiter = RateLimiter(max_retries=2, jitter_fn=lambda: 0.0)
    router._model_health = {}
    router._providers = {}

    primary_sel = ModelSelection(model=_model(), reason="primary", fallback_used=False)
    fallback_sel = ModelSelection(model=_model(), reason="fallback", fallback_used=True)

    state = {"call": 0}

    def fake_route(**kw):
        state["call"] += 1
        # prefer_specialist=False on the fallback call -> return fallback sel
        if state["call"] == 1:
            return primary_sel
        return fallback_sel

    fallback_provider = _FlakyProvider(fail_times=0)  # succeeds immediately

    def fake_get_provider(model):
        # The fallback re-routes to the same model_id in this stub; distinguish
        # by which selection we last returned.
        return fallback_provider if state["call"] > 1 else primary

    router.route_request = fake_route
    router._get_provider = fake_get_provider

    resp, s = router.generate("hi")
    assert resp.text == "ok"
    # primary tried max_retries+1 = 3 times; fallback succeeded once
    assert primary.calls == 3
    assert fallback_provider.calls == 1
