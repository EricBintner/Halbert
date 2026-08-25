"""HTTP rate-limit handler for model providers (A2b).

Handles HTTP 429 (Too Many Requests) and 529 (Overloaded) responses with
``Retry-After`` header parsing and per-model backoff state.

This is the HTTP-specific complement to ``agents/error_recovery.py``, which
owns the general retry loop, exponential backoff, and circuit breaker for
non-HTTP errors. The two are complementary, not overlapping:

- ``ErrorRecoveryManager`` classifies exceptions by message and retries with
  exponential backoff — it has no notion of HTTP status codes or the
  ``Retry-After`` header.
- ``RateLimiter`` parses the ``Retry-After`` header (seconds, HTTP-date, or
  ``retry-after-ms``) and tracks per-model retry state.

``tier_router.generate()`` wires them together: it retries 429/529 responses
using ``RateLimiter.get_wait_time()`` and records each failure to the
``ErrorRecoveryManager`` circuit breaker so a persistently rate-limited model
is eventually taken out of rotation. See OPUS-HANDOFF §A2b and
STRATEGY-V2-SCRUTINY.md §2 Hidden Dependency 3.
"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional

__all__ = ["RateLimiter", "RetryState"]

# HTTP status codes treated as transient rate limits
RATE_LIMITED_STATUSES = (429, 529)


@dataclass
class RetryState:
    """Per-model rate-limit state."""
    attempts: int = 0
    last_status_code: Optional[int] = None
    last_retry_after: Optional[float] = None
    # monotonic deadline until which the model is server-blocked
    blocked_until: float = 0.0


class RateLimiter:
    """HTTP 429/529 rate-limit handler with ``Retry-After`` support.

    Stateless across processes (in-memory per-model state). The retry *loop*
    lives in the caller (``tier_router.generate()``) which keeps it scoped to
    rate-limit responses; general retry/backoff for other error types stays
    with ``ErrorRecoveryManager.execute_with_retry()``.
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
        jitter_fn: Optional[Callable[[], float]] = None,
    ):
        self._max_retries = max_retries
        self._base = base_backoff
        self._max_backoff = max_backoff
        self._jitter_fn = jitter_fn if jitter_fn is not None else random.random
        self._state: Dict[str, RetryState] = {}

    @staticmethod
    def _key(model_id: Optional[str]) -> str:
        return model_id or "default"

    @staticmethod
    def is_rate_limited(status_code: Optional[int]) -> bool:
        """True if ``status_code`` is a rate-limit response (429/529)."""
        return status_code in RATE_LIMITED_STATUSES

    def should_retry(
        self,
        status_code: Optional[int],
        headers: Optional[Dict[str, Any]],
        attempt: int,
        model_id: Optional[str] = None,
    ) -> bool:
        """Whether to retry after a rate-limit response.

        Returns True only for 429/529 and while attempts remain below the cap.
        """
        if not self.is_rate_limited(status_code):
            return False
        return attempt < self._max_retries

    def get_wait_time(
        self,
        status_code: Optional[int],
        headers: Optional[Dict[str, Any]],
        attempt: int,
        model_id: Optional[str] = None,
    ) -> float:
        """Seconds to wait before the next attempt.

        Honors the ``Retry-After`` header (seconds, HTTP-date, or
        ``retry-after-ms``) when present; otherwise falls back to exponential
        backoff with jitter, capped at ``max_backoff``.
        """
        retry_after = self._parse_retry_after(headers or {})
        if retry_after is not None:
            wait = min(retry_after, self._max_backoff)
        else:
            exp = min(self._base * (2 ** attempt), self._max_backoff)
            wait = exp + self._jitter_fn() * self._base
        return max(wait, 0.0)

    def record_retry(
        self,
        model_id: Optional[str],
        status_code: Optional[int],
        headers: Optional[Dict[str, Any]],
    ) -> None:
        """Record a rate-limit retry and update the model's block window."""
        key = self._key(model_id)
        state = self._state.setdefault(key, RetryState())
        state.attempts += 1
        state.last_status_code = status_code
        state.last_retry_after = self._parse_retry_after(headers or {})
        wait = self.get_wait_time(status_code, headers, state.attempts - 1, model_id)
        state.blocked_until = time.monotonic() + wait

    def reset(self, model_id: Optional[str]) -> None:
        """Clear rate-limit state for a model (call on success)."""
        self._state.pop(self._key(model_id), None)

    def status(self, model_id: Optional[str]) -> Dict[str, Any]:
        """Snapshot of a model's rate-limit state (for /status endpoints)."""
        state = self._state.get(self._key(model_id))
        if state is None:
            return {"attempts": 0, "rate_limited": False, "blocked": False}
        now = time.monotonic()
        return {
            "attempts": state.attempts,
            "last_status_code": state.last_status_code,
            "last_retry_after": state.last_retry_after,
            "rate_limited": state.last_status_code in RATE_LIMITED_STATUSES,
            "blocked": now < state.blocked_until,
            "blocked_remaining": max(0.0, state.blocked_until - now),
        }

    # ------------------------------------------------------------------
    # Retry-After parsing
    # ------------------------------------------------------------------

    def _parse_retry_after(self, headers: Dict[str, Any]) -> Optional[float]:
        """Parse ``Retry-After`` / ``retry-after-ms`` into seconds."""
        if not headers:
            return None
        # Case-insensitive lookup
        lower = {str(k).lower(): v for k, v in headers.items()}
        if "retry-after-ms" in lower:
            try:
                return float(lower["retry-after-ms"]) / 1000.0
            except (TypeError, ValueError):
                return None
        if "retry-after" in lower:
            return self._coerce_retry_after(lower["retry-after"])
        return None

    @staticmethod
    def _coerce_retry_after(value: Any) -> Optional[float]:
        """Coerce a Retry-After value (delta-seconds or HTTP-date) to seconds."""
        # Delta seconds (integer or float)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            pass
        # HTTP-date
        try:
            dt = parsedate_to_datetime(str(value))
            if dt is not None:
                return max(0.0, dt.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            pass
        return None