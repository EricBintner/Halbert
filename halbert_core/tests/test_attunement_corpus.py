# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's directive corpus, run against the engine's real parser.

The shared fixture lives in the engine (`attunement/testing/corpora/`) so all
three consumers' regressions run against the union. Halbert's contribution is
mostly the must-not-fire half, and its largest class exists for no other
consumer: a WITHDRAW-shaped token aimed at a running operation rather than at
the persona. A bare "stop" during EXECUTING means *cancel the command*;
parsing it as a directive costs the user their cancel and buys two hours of
silence.

The xfail block records false negatives found in the engine's parser while
building this. They are kept here rather than in the shared corpus so another
repository's suite stays green; each one flips to a failure-to-xfail the
moment the engine fixes it, which is the signal to move it across.
"""

import pytest

pytest.importorskip(
    "haloysius.attunement.directives",
    reason="haloysius.attunement not built yet",
)

from haloysius.attunement.directives import parse_directive  # noqa: E402
from haloysius.attunement.testing import (  # noqa: E402
    _build_signals,
    corpus_cases,
)
from haloysius.attunement.types import DirectiveContext  # noqa: E402


def _parse(text, ctx=None):
    directive = parse_directive(text, _build_signals(text, {}),
                                ctx=ctx or DirectiveContext())
    return directive.kind.value if directive else "none"


def _halbert_cases():
    return corpus_cases(["halbert"])


def test_the_halbert_corpus_is_not_empty():
    assert len(_halbert_cases()) >= 50


@pytest.mark.parametrize(
    "case", _halbert_cases(), ids=lambda c: c.text[:48]
)
def test_halbert_corpus_case(case):
    assert _parse(case.text, case.ctx) == case.expect, case.why


@pytest.mark.parametrize(
    "text,expected",
    [
        # A blanket negation guard. The engine already inverts one direction —
        # "don't go quiet on me" parses as INVITE — but kills the other, so a
        # negated *speaking* verb, which is itself a withdrawal, is dropped.
        ("don't talk to me", "withdraw"),
        ("don't interrupt me", "limit"),
        ("please don't interrupt", "limit"),
        ("don't interrupt while I'm working", "limit"),
        # The most standardised quiet phrase in computing; every user knows it
        # from their phone.
        ("do not disturb", "limit"),
        # "don't bother me unless it's urgent" parses; the idiom does not.
        ("don't bother me unless something's on fire", "limit"),
    ],
)
@pytest.mark.xfail(
    reason="engine parser gap: the negation guard does not distinguish a "
           "negated quiet-verb (inverts to INVITE) from a negated speak-verb "
           "(is itself a directive). Reported in handoff §10.11.",
    strict=True,
)
def test_negated_speak_verbs_should_parse(text, expected):
    assert _parse(text) == expected
