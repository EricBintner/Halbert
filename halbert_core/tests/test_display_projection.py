# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-06 Phases C and E: the display seam is bounded, honest and complete.

- **A05-G3 (FD-16)** -- the display seam ran the REGISTRY pass only, on
  the reasoning that terminal output already meets pattern redaction
  before persistence. But not everything at this seam is terminal output:
  an MCP result, a tool's structured payload and a skill's text all
  arrive here having met neither. The deterministic pattern pass joins
  the registry, which supersedes the decision recorded in this module's
  own docstring.
- **A05-G5 + bug 5** -- the cap cut mid-line and named one cut when it
  had made two. A reader could not tell a truncated line from a short
  one, and "[omitted 4 lines]" on a body that was ALSO character-capped
  said nothing about the second cut.
- **A05-G6** -- a capped block carried no structured fact, so a consumer
  could only find out by parsing the header text.
- **A05-G7** -- the cap was per-STRING, so a dict of two hundred
  thousand-character values crossed at two hundred times the budget.
- **A05-G11** -- the seam's failure returned the value raw.
- **A05-G15** -- chat input arrived unnormalised, so a null byte or a
  C0 control reached the store and the prompt.
"""

import pytest

from halbert_core.ingestion.redaction_registry import get_global_registry
from halbert_core.security.display_transport import (
    MAX_DISPLAY_CHARS,
    MAX_PAYLOAD_CHARS,
    sanitize_chat_input,
    verbose_text,
)


# ---------------------------------------------------------------------------
# A05-G3 (FD-16): the pattern pass joins the registry
# ---------------------------------------------------------------------------

def test_a_password_shaped_value_is_redacted_without_being_registered():
    out = verbose_text("connecting with password=swordfish99")
    assert "swordfish99" not in out


def test_a_registered_value_is_still_redacted():
    get_global_registry().register("display-secret-value-1")
    assert "display-secret-value-1" not in verbose_text(
        "saw display-secret-value-1")


def test_ordinary_text_survives_the_pattern_pass():
    assert verbose_text("total 4\ndrwxr-xr-x  2 me  staff") == (
        "total 4\ndrwxr-xr-x  2 me  staff")


# ---------------------------------------------------------------------------
# A05-G5 + bug 5: the cap never cuts mid-line and names both cuts
# ---------------------------------------------------------------------------

def test_the_cap_does_not_cut_mid_line():
    text = "\n".join("x" * 200 for _ in range(40))
    out = verbose_text(text)
    body = out.split("\n", 1)[1]
    for line in body.split("\n"):
        assert line == "x" * 200 or line == "", repr(line[:40])


def test_both_cuts_are_named():
    """Both fire only when ONE surviving line is still over budget --
    dropping whole lines is what the char cap does first, so this is the
    case where there is nothing left to drop."""
    text = "\n".join("y" * 2000 for _ in range(40))
    header = verbose_text(text).split("\n", 1)[0]
    assert "lines" in header
    assert "characters" in header


def test_a_single_over_long_line_names_the_character_cut():
    header = verbose_text("y" * 5000).split("\n", 1)[0]
    assert "characters" in header
    assert "lines" not in header


def test_a_line_only_cut_names_the_lines():
    text = "\n".join(f"line {i}" for i in range(40))
    header = verbose_text(text).split("\n", 1)[0]
    assert "24" in header


def test_short_text_is_returned_unchanged():
    assert verbose_text("short") == "short"


# ---------------------------------------------------------------------------
# A05-G6: a capped block carries a structured fact
# ---------------------------------------------------------------------------

def test_a_capped_block_reports_itself():
    from halbert_core.security.display_transport import verbose_block

    text = "\n".join("z" * 300 for _ in range(40))
    block = verbose_block(text)
    assert block["truncated"] is True
    # At least the line cap's own 24, and more once the character budget
    # drops further WHOLE lines rather than slicing one.
    assert block["omitted_lines"] >= 24
    assert block["original_lines"] == 40
    assert block["original_chars"] == len(text)


def test_an_uncapped_block_says_so():
    from halbert_core.security.display_transport import verbose_block

    block = verbose_block("fine")
    assert block["truncated"] is False
    assert block["text"] == "fine"


# ---------------------------------------------------------------------------
# A05-G7: the payload budget is per-VALUE, not per-string
# ---------------------------------------------------------------------------

def test_a_dict_of_many_capped_strings_is_bounded_as_a_whole():
    payload = {f"k{i}": "q" * 900 for i in range(200)}
    out = verbose_text(payload)
    assert len(str(out)) <= MAX_PAYLOAD_CHARS * 2


def test_a_long_list_is_bounded_too():
    out = verbose_text(["w" * 900 for _ in range(200)])
    assert len(str(out)) <= MAX_PAYLOAD_CHARS * 2


def test_a_small_dict_keeps_every_key():
    out = verbose_text({"a": "1", "b": "2"})
    assert out == {"a": "1", "b": "2"}


# ---------------------------------------------------------------------------
# A05-G11: the seam fails closed
# ---------------------------------------------------------------------------

def test_a_broken_redactor_does_not_release_the_value(monkeypatch):
    import halbert_core.security.display_transport as dt

    def _boom(text):
        raise RuntimeError("redactor broken")

    monkeypatch.setattr(dt, "_redact_display_text", _boom)
    out = verbose_text("the raw command output")
    assert "the raw command output" not in str(out)


# ---------------------------------------------------------------------------
# A05-G15: chat input is normalised
# ---------------------------------------------------------------------------

def test_a_null_byte_is_refused():
    with pytest.raises(ValueError):
        sanitize_chat_input("hello\x00world")


def test_c0_controls_are_stripped():
    assert sanitize_chat_input("a\x07b\x1bc") == "abc"


def test_newlines_and_tabs_survive():
    assert sanitize_chat_input("a\nb\tc") == "a\nb\tc"


def test_text_is_nfc_normalised():
    import unicodedata

    decomposed = "éclair"          # e + combining acute
    out = sanitize_chat_input(decomposed)
    assert out == unicodedata.normalize("NFC", decomposed)
    assert out == "éclair"


def test_ordinary_input_is_unchanged():
    assert sanitize_chat_input("restart sshd please") == "restart sshd please"


# ---------------------------------------------------------------------------
# The consumers: the door and the timeline route
# ---------------------------------------------------------------------------

def test_the_talk_door_refuses_a_null_byte(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import halbert_core.dashboard.routes.agent as agent_routes

    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)

    class _Agent:
        active_sessions = {}

    monkeypatch.setattr(agent_routes, "_agent_instance", _Agent())
    app = FastAPI()
    app.include_router(agent_routes.router)
    client = TestClient(app)

    r = client.post(
        "/api/agent/message", json={"message": "hi" + chr(0) + "there"})
    assert r.status_code == 400


def test_a_stored_block_is_projected_on_a_timeline_read():
    import halbert_core.dashboard.routes.agent as agent_routes

    turns = [{
        "turn_id": "t1",
        "messages": [{
            "blocks": [{
                "tool": "run_command",
                "result": "\n".join("v" * 300 for _ in range(40)),
            }],
        }],
    }]
    agent_routes._project_timeline_blocks(turns)
    block = turns[0]["messages"][0]["blocks"][0]
    assert len(block["result"]) < 5000
    assert block["truncated"]["result"]["omitted_lines"] >= 24


def test_a_stored_block_with_a_secret_is_redacted_on_read():
    import halbert_core.dashboard.routes.agent as agent_routes

    turns = [{"messages": [{"blocks": [
        {"tool": "run_command", "result": "connected with password=hunter2xyz"},
    ]}]}]
    agent_routes._project_timeline_blocks(turns)
    assert "hunter2xyz" not in turns[0]["messages"][0]["blocks"][0]["result"]


def test_an_untruncated_block_carries_no_truncation_facts():
    import halbert_core.dashboard.routes.agent as agent_routes

    turns = [{"messages": [{"blocks": [{"tool": "read_file", "result": "ok"}]}]}]
    agent_routes._project_timeline_blocks(turns)
    assert "truncated" not in turns[0]["messages"][0]["blocks"][0]
