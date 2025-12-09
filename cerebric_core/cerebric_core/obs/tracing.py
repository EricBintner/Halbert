from __future__ import annotations
import time
import uuid
import contextvars
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from .logging import get_logger

T = TypeVar("T")

# Simple context propagation for a trace/session id
_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def current_trace_id() -> str:
    tid = _current_trace_id.get()
    if not tid:
        tid = uuid.uuid4().hex
        _current_trace_id.set(tid)
    return tid


def _export_span(name: str, trace_id: str, start_ts: str, duration_ms: int, error: Optional[str]) -> None:
    """Export a span to the global span exporter."""
    try:
        from .span_exporter import get_exporter
        span = {
            "name": name,
            "trace_id": trace_id,
            "start_ts": start_ts,
            "duration_ms": duration_ms,
            "error": error,
        }
        get_exporter().export_span(span)
    except Exception:
        pass  # Fail-safe: don't crash if exporter unavailable


def trace_call(name: Optional[str] = None, level: str = "info") -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Lightweight tracing decorator that logs start/end with duration and a trace_id using the 'cerebric' logger.
    Does not require external dependencies; integrates with JsonFormatter fields.
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        lbl = name or fn.__name__
        log = get_logger("cerebric")
        lvl = level.lower()

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            trace_id = current_trace_id()
            t0 = time.monotonic()
            start_ts = datetime.now(timezone.utc).isoformat()
            # start
            getattr(log, lvl)(f"start {lbl}", extra={"request_id": trace_id, "node": lbl})
            error_val: Optional[str] = None
            try:
                res = fn(*args, **kwargs)
                dt = int((time.monotonic() - t0) * 1000)
                getattr(log, lvl)(f"end {lbl}", extra={"request_id": trace_id, "node": lbl, "duration_ms": dt})
                _export_span(lbl, trace_id, start_ts, dt, None)
                return cast(T, res)
            except Exception as e:
                dt = int((time.monotonic() - t0) * 1000)
                error_val = f"{type(e).__name__}: {e}"
                log.error(f"error {lbl}: {e}", extra={"request_id": trace_id, "node": lbl, "duration_ms": dt, "error_code": type(e).__name__})
                _export_span(lbl, trace_id, start_ts, dt, error_val)
                raise
        return wrapper
    return decorator
