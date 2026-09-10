# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Display-transport redact+cap seam (Packet 05 addendum, from the Hermes
review §8).

Tool args/results cross the wire to the Tauri frontend through the
``tool_start``/``tool_complete`` SSE events. Those events are the dominant
display seam: every live tool emission is built by the two StreamEvent
factories, so redacting + capping there covers every producer. Full
fidelity stays in the agent context and SQLite — only the display copy is
bounded (Hermes: the cap is an OOM defense, not just privacy; an
unbounded output blew up their render tree, #34095).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.ingestion import redaction_registry as _rr
from halbert_core.ingestion.redaction_registry import REDACTION_PLACEHOLDER
from halbert_core.security.display_transport import (
    MAX_DISPLAY_CHARS,
    MAX_DISPLAY_LINES,
    verbose_text,
)
from halbert_core.agents.events import StreamEvent


@pytest.fixture(autouse=True)
def _fresh_global_registry():
    saved = _rr._GLOBAL
    _rr._GLOBAL = None
    try:
        yield
    finally:
        _rr._GLOBAL = saved


def _acked(secret: str) -> None:
    """Stand in for the acknowledged-egress path: the value the registry
    would hold after get_config_value acked it out."""
    _rr.get_global_registry().register(secret)


# ---------------------------------------------------------------------------
# verbose_text: the helper
# ---------------------------------------------------------------------------


def test_short_plain_text_passes_through_untouched():
    assert verbose_text("all good") == "all good"


def test_registered_secret_redacted_from_text():
    _acked("hunter2")
    assert verbose_text("the value is hunter2 here") == (
        f"the value is {REDACTION_PLACEHOLDER} here"
    )


def test_50kb_result_arrives_capped():
    blob = "x" * 50_000
    out = verbose_text(blob)
    # R-06 (A05 bug 5): the header names WHICH cut happened, and
    # both when both did. "[output truncated]" said neither.
    assert "cut to the last" in out
    # the tail is kept, and the wire copy is bounded
    assert out.endswith("x" * MAX_DISPLAY_CHARS)
    # R-06 (A05-G5/bug 5): the header names which cut happened, so it is
    # longer than the old fixed string. The BODY is what the budget
    # bounds, and it still is.
    assert len(out.split("\n", 1)[1]) <= MAX_DISPLAY_CHARS


def test_many_lines_arrives_capped_with_omitted_marker():
    lines = [f"line {i}" for i in range(50)]
    out = verbose_text("\n".join(lines))
    assert out.startswith("[omitted %d lines]" % (50 - MAX_DISPLAY_LINES))
    assert out.splitlines()[1] == f"line {50 - MAX_DISPLAY_LINES}"
    # tail-keeping: the last line survives
    assert out.endswith("line 49")


def test_cap_bounds_after_line_drop():
    """When the kept tail is itself huge (few very long lines), the char cap
    still bounds the wire copy."""
    out = verbose_text("\n".join("y" * 2000 for _ in range(20)))
    # R-06 (A05-G5): the header is longer now because it names both
    # cuts instead of one. The BODY is still inside the budget, which is
    # what the bound is about.
    body = out.split("\n", 1)[1]
    assert len(body) <= MAX_DISPLAY_CHARS


def test_structures_recurse_strings_only():
    _acked("hunter2")
    payload = {
        "note": "value hunter2 inside",
        "nested": [{"deep": "hunter2 again"}],
        "count": 7,
        "flag": True,
        "nothing": None,
    }
    out = verbose_text(payload)
    assert out["note"] == f"value {REDACTION_PLACEHOLDER} inside"
    assert out["nested"][0]["deep"] == f"{REDACTION_PLACEHOLDER} again"
    assert out["count"] == 7 and out["flag"] is True and out["nothing"] is None


def test_input_not_mutated():
    _acked("hunter2")
    payload = {"note": "value hunter2 inside"}
    verbose_text(payload)
    assert payload["note"] == "value hunter2 inside"


def test_non_string_scalars_pass_through():
    assert verbose_text(123) == 123
    assert verbose_text(None) is None
    assert verbose_text(True) is True


# ---------------------------------------------------------------------------
# the seam: StreamEvent.tool_start / tool_complete
# ---------------------------------------------------------------------------


def test_tool_start_args_render_redacted_at_the_seam():
    _acked("hunter2")
    event = StreamEvent.tool_start(
        "sess1", "run_command", {"command": "echo hunter2"}, "exec-1"
    )
    assert "hunter2" not in str(event.data["args"])
    assert event.data["args"]["command"] == f"echo {REDACTION_PLACEHOLDER}"


def test_tool_complete_result_redacted_at_the_seam():
    _acked("hunter2")
    event = StreamEvent.tool_complete(
        "sess1", "exec-1", True,
        result={"note": "echoed hunter2 to stdout"},
    )
    assert "hunter2" not in str(event.data["result"])
    assert event.data["result"]["note"] == f"echoed {REDACTION_PLACEHOLDER} to stdout"


def test_tool_complete_50kb_result_arrives_capped():
    blob = "z" * 50_000
    event = StreamEvent.tool_complete("sess1", "exec-1", True, result=blob)
    out = event.data["result"]
    assert isinstance(out, str)
    # R-06 (A05 bug 5): the header names WHICH cut happened, and
    # both when both did. "[output truncated]" said neither.
    assert "cut to the last" in out
    # R-06 (A05-G5/bug 5): the header names which cut happened, so it is
    # longer than the old fixed string. The BODY is what the budget
    # bounds, and it still is.
    assert len(out.split("\n", 1)[1]) <= MAX_DISPLAY_CHARS


def test_tool_complete_short_result_untouched():
    event = StreamEvent.tool_complete("sess1", "exec-1", True, result="restarted")
    assert event.data["result"] == "restarted"


def test_tool_events_sse_json_round_trip():
    """What crosses the wire is JSON — the redacted, capped copy must
    serialize without the raw material. The secret sits in the kept tail
    (redaction runs before the cap, so a marker is never lost, only the
    un-redacted head of a huge string can be dropped)."""
    _acked("hunter2")
    event = StreamEvent.tool_complete(
        "sess1", "exec-1", True, result={"out": "w" * 20_000 + " and hunter2 at the end"}
    )
    sse = event.to_sse()
    assert "hunter2" not in sse
    assert REDACTION_PLACEHOLDER in sse