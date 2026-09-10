# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any

def _redact_log_text(text: str) -> str:
    """The redaction pass every log line gets (A03-G8).

    A log line is an egress surface: files outlive the process, get
    bundled into diagnostics, and are read back by the agent's own file
    tools. Every ``logger.warning(f"...{value}...")`` in the tree wrote
    whatever it was handed, and there are several hundred of them -- so
    the pass belongs at the one place they all pass through rather than
    in each author's memory.

    Registry first, then patterns: the same order the Tier-2 choke point
    uses, and for the same reason (a pattern pass rewrites part of what
    it matches, and an exact-value registry cannot match what has
    already been partly rewritten).
    """
    from ..ingestion.redaction import redact_text
    from ..ingestion.redaction_registry import get_global_registry

    return redact_text(get_global_registry().redact_text(text), prose=True)


def _safe_redact(value):
    """Redact one payload value, never at the cost of the line itself.

    A redactor that raises must not silence a log -- losing the line is
    worse than the risk the redactor was guarding, because the line is
    often how the failure is diagnosed at all.
    """
    if not isinstance(value, str) or not value:
        return value
    try:
        return _redact_log_text(value)
    except Exception:
        return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": _safe_redact(record.getMessage()),
        }
        # Include common structured fields if provided via LoggerAdapter/extra
        for key in ("request_id", "agent", "node", "tool", "duration_ms", "error_code", "host", "tags"):
            if hasattr(record, key):
                payload[key] = _safe_redact(getattr(record, key))
        return json.dumps(payload)

def get_logger(name: str = "halbert") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger
