# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-05 Phase E + R-06 Phase A: one scrub seam, and it tells the truth.

- **A05-G1 + A05 bug 1** (fix-first row 8) -- the echo guard matched on a
  normalised window and then called ``registry.redact_text``, which
  replaces WHOLE registered forms. A reply containing the first 85
  characters of a 98-character acked value matched the guard, changed
  nothing under the registry, and was delivered -- while the structured
  warning said ``redacted: true``. Two defects in one line: the secret
  went out, and the log said it had not.
- **A03 (R-05 Phase E)** -- the seams were "non-fatal by construction":
  any failure inside the guard returned the text RAW. A scrub that
  cannot run is not evidence that there was nothing to scrub.
- **A05-G4** -- ``_scrub_text`` lived in ``turn_event_tee`` with a
  comment saying it mirrored the state machine's staticmethod. Two
  copies of a security seam drift; the one that drifts is the one nobody
  is looking at.
"""

import pytest

from halbert_core.ingestion.redaction_registry import (
    REDACTION_PLACEHOLDER,
    get_global_registry,
)
from halbert_core.security.echo_guard import EchoGuard
from halbert_core.security.scrub import (
    SCRUB_FAILED_NOTICE,
    scrub_for_egress,
)


# ---------------------------------------------------------------------------
# A05-G1 + bug 1: a partial echo is redacted, and the log is true
# ---------------------------------------------------------------------------

def test_a_partial_echo_is_redacted():
    """The reproduction: 85 characters of a 98-character acked value."""
    secret = "".join(chr(ord("a") + (i % 26)) for i in range(98))
    guard = EchoGuard()
    guard.note_injected(secret)

    out = guard.redact(secret[:85])
    assert secret[:85] not in out
    assert REDACTION_PLACEHOLDER in out


def test_a_re_wrapped_echo_is_redacted():
    """Line wrapping must not defeat it: the guard normalises whitespace."""
    secret = " ".join(f"word{i:03d}" for i in range(20))
    guard = EchoGuard()
    guard.note_injected(secret)

    wrapped = secret.replace(" ", "\n")
    out = guard.redact(wrapped)
    assert "word005" not in out


def test_text_with_no_echo_is_untouched():
    guard = EchoGuard()
    guard.note_injected("a" * 200)
    assert guard.redact("ordinary prose") == "ordinary prose"


def test_the_surrounding_prose_survives():
    secret = "z" * 120
    guard = EchoGuard()
    guard.note_injected(secret)
    out = guard.redact(f"Here it is: {secret[:100]} -- that is all.")
    assert out.startswith("Here it is: ")
    assert out.endswith(" -- that is all.")


def test_a_flagged_text_that_cannot_be_changed_is_suppressed():
    """If the guard matched and redaction changed nothing, the text does
    not go out. The origin returns an empty string."""
    guard = EchoGuard(window=4)
    guard.note_injected("abcd")

    class _Unchanging(EchoGuard):
        def redact(self, text, session="default"):
            return text          # a redactor that does nothing

    unchanging = _Unchanging(window=4)
    unchanging.note_injected("abcd")
    assert scrub_for_egress("abcd here", surface="reply", guard=unchanging) == ""


def test_the_log_says_what_actually_happened(caplog):
    import json

    secret = "q" * 120
    guard = EchoGuard()
    guard.note_injected(secret)
    with caplog.at_level("WARNING"):
        scrub_for_egress(secret[:100], surface="reply", guard=guard)
    events = [
        json.loads(r.message) for r in caplog.records
        if r.message.startswith("{")
    ]
    assert events, [r.message for r in caplog.records]
    assert events[0]["redacted"] is True
    # And the material itself never appears in the log.
    assert secret[:50] not in caplog.text


# ---------------------------------------------------------------------------
# R-05 Phase E: the seam fails closed
# ---------------------------------------------------------------------------

def test_a_broken_guard_does_not_release_the_text():
    class _Broken(EchoGuard):
        def find_match(self, text, session="default"):
            raise RuntimeError("guard broken")

    out = scrub_for_egress("the raw answer", surface="reply", guard=_Broken())
    assert "the raw answer" not in out
    assert out == SCRUB_FAILED_NOTICE


def test_the_failure_notice_is_deterministic_text():
    assert SCRUB_FAILED_NOTICE
    assert "<" not in SCRUB_FAILED_NOTICE or "secret" not in SCRUB_FAILED_NOTICE


def test_an_empty_text_is_returned_as_is():
    assert scrub_for_egress("", surface="reply") == ""


# ---------------------------------------------------------------------------
# A05-G4: one seam, not two copies
# ---------------------------------------------------------------------------

def test_the_tee_uses_the_shared_seam():
    import inspect

    import halbert_core.agents.turn_event_tee as tee

    source = inspect.getsource(tee._scrub_text)
    assert "scrub_for_egress" in source
    # The wrapper is a call, not a second implementation.
    assert "find_match" not in source
    assert "redact_text" not in source


def test_the_state_machine_uses_the_shared_seam():
    import inspect

    import halbert_core.agents.state_machine as sm

    source = inspect.getsource(sm.AgentStateMachine._echo_guard_egress)
    assert "scrub_for_egress" in source
    assert "find_match" not in source


def test_the_registry_runs_at_the_seam_too():
    get_global_registry().register("seam-secret-value-42")
    out = scrub_for_egress("here: seam-secret-value-42", surface="reply")
    assert "seam-secret-value-42" not in out
