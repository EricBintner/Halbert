# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-05 Phase D: a log line is an egress surface too.

A03-G8. ``JsonFormatter`` interpolated ``record.getMessage()`` straight
into the payload. Every ``logger.warning(f"...{value}...")`` anywhere in
the tree therefore wrote whatever it was handed -- and log files outlive
the process, get bundled into diagnostics, and are read by the agent's
own file tools. The one place every line passes through is the formatter,
so that is where the pass belongs, rather than trusting several hundred
call sites to remember.
"""

import json
import logging

from halbert_core.ingestion.redaction_registry import (
    REDACTION_PLACEHOLDER,
    get_global_registry,
)
from halbert_core.obs.logging import JsonFormatter


def _line(msg, *args, **extra):
    record = logging.LogRecord(
        name="halbert.test", level=logging.WARNING, pathname=__file__,
        lineno=1, msg=msg, args=args, exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_an_acked_secret_never_reaches_a_log_line():
    get_global_registry().register("hunter2-hunter2-hunter2")
    payload = _line("connect failed: %s", "hunter2-hunter2-hunter2")
    assert "hunter2-hunter2-hunter2" not in payload["msg"]
    assert REDACTION_PLACEHOLDER in payload["msg"]


def test_a_password_shaped_line_is_redacted():
    payload = _line("running with password=swordfish99")
    assert "swordfish99" not in payload["msg"]


def test_ordinary_lines_are_untouched():
    payload = _line("scanner finished in %d ms", 42)
    assert payload["msg"] == "scanner finished in 42 ms"


def test_the_structured_fields_are_redacted_too():
    get_global_registry().register("extra-secret-value-123")
    payload = _line("tool ran", tool="extra-secret-value-123")
    assert "extra-secret-value-123" not in json.dumps(payload)


def test_the_line_is_still_valid_json():
    payload = _line("a message with {braces} and \"quotes\"")
    assert payload["level"] == "warning"
    assert payload["logger"] == "halbert.test"


def test_a_formatter_failure_never_loses_the_line(monkeypatch):
    """A redactor that raises must not silence the log."""
    import halbert_core.obs.logging as logging_mod

    def _boom(text):
        raise RuntimeError("redactor broken")

    monkeypatch.setattr(logging_mod, "_redact_log_text", _boom)
    payload = _line("something happened")
    assert "something happened" in payload["msg"]
