# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-05 Phase A: the secret registry's mechanics.

The registry is the exact-value half of redaction: it holds values
Halbert has watched cross a boundary it controls, so a later mention of
one is caught even where no pattern would recognise it. Six ways it
missed.

- **A03-G6 (FD-15)** -- the minimum registrable length was 4, where the
  origin's is 6. A four-character value is not protectable by exact
  match without blanking ordinary prose, so the choice is 6 plus the
  pattern pass, not 4 and a lot of false positives.
- **A03 bug 2** -- ``_variants_of`` returned its forms SORTED, so
  insertion order was alphabetical and FIFO eviction could drop the RAW
  value while keeping a percent-encoded variant of it. The raw form is
  the one most likely to appear.
- **A03 bug 3** -- replacement was a sequence of ``str.replace`` calls,
  so a form appearing inside the placeholder another form had just
  written could be replaced again, mangling the output. One compiled
  longest-first alternation, one pass.
- **A03-G4** -- ``urllib.parse.quote`` is not ``encodeURIComponent`` (it
  leaves ``/`` alone) and is not ``quote_plus`` (space as ``+``). A
  secret egressed by a browser or a form encoder wore a form the
  registry had never seen.
- **A03 lock** -- the registry is mutated from request threads and read
  from the turn's; the OrderedDict and its cache were unguarded.
"""

import threading

import pytest

from halbert_core.ingestion.redaction_registry import (
    MIN_SECRET_VARIANT_LEN,
    REDACTION_PLACEHOLDER,
    SecretVariantRegistry,
)


def test_the_minimum_length_is_six():
    assert MIN_SECRET_VARIANT_LEN == 6


def test_a_short_value_is_not_registered():
    registry = SecretVariantRegistry()
    registry.register("abc12")
    assert len(registry) == 0


def test_a_six_character_value_is_registered():
    registry = SecretVariantRegistry()
    registry.register("abc123")
    assert registry.redact_text("here: abc123") == f"here: {REDACTION_PLACEHOLDER}"


# ---------------------------------------------------------------------------
# A03 bug 2: the raw form is the newest, so it is evicted last
# ---------------------------------------------------------------------------

def test_the_raw_form_survives_eviction_longest():
    registry = SecretVariantRegistry(max_entries=2)
    registry.register("a b/c d")          # raw, quoted and plus forms differ
    forms = list(registry._variants)
    assert forms[-1] == "a b/c d", forms


def test_a_re_registration_refreshes_the_raw_form():
    registry = SecretVariantRegistry(max_entries=4)
    registry.register("secret-one")
    registry.register("secret-two")
    registry.register("secret-one")
    assert list(registry._variants)[-1] == "secret-one"


# ---------------------------------------------------------------------------
# A03-G4: the encoded forms a real egress produces
# ---------------------------------------------------------------------------

def test_the_percent_encoded_form_redacts():
    registry = SecretVariantRegistry()
    registry.register("pa ss/word")
    assert "pa%20ss%2Fword" not in registry.redact_text("x=pa%20ss%2Fword")


def test_the_plus_encoded_form_redacts():
    """A form encoder writes a space as ``+``."""
    registry = SecretVariantRegistry()
    registry.register("pa ss word")
    assert "pa+ss+word" not in registry.redact_text("x=pa+ss+word")


def test_the_json_escaped_form_redacts():
    registry = SecretVariantRegistry()
    registry.register('quote"inside')
    assert '\\"' not in registry.redact_text('{"v": "quote\\"inside"}')


def test_a_slash_is_encoded_like_encodeuricomponent():
    registry = SecretVariantRegistry()
    registry.register("a/b/c/d/e")
    assert "a%2Fb%2Fc%2Fd%2Fe" not in registry.redact_text("u=a%2Fb%2Fc%2Fd%2Fe")


# ---------------------------------------------------------------------------
# A03 bug 3: one pass, no self-collision
# ---------------------------------------------------------------------------

def test_a_secret_that_looks_like_the_placeholder_does_not_recurse():
    registry = SecretVariantRegistry()
    registry.register("secret>")
    registry.register("longer-secret-value")
    out = registry.redact_text("longer-secret-value and secret>")
    assert "longer-secret-value" not in out
    assert out.count(REDACTION_PLACEHOLDER) == 2


def test_a_shorter_form_never_eats_a_longer_one():
    registry = SecretVariantRegistry()
    registry.register("abcdef")
    registry.register("abcdefghij")
    out = registry.redact_text("abcdefghij")
    assert out == REDACTION_PLACEHOLDER


def test_replacement_is_a_single_pass():
    """A form appearing INSIDE what another form's replacement wrote must
    not be replaced again."""
    registry = SecretVariantRegistry()
    registry.register("<secret")
    registry.register("aaaaaaaa")
    out = registry.redact_text("aaaaaaaa")
    assert out == REDACTION_PLACEHOLDER


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------

def test_concurrent_registration_and_redaction_is_safe():
    registry = SecretVariantRegistry(max_entries=64)
    errors = []

    def _writer():
        try:
            for i in range(300):
                registry.register(f"secret-value-{i:04d}")
        except Exception as e:      # pragma: no cover - failure path
            errors.append(repr(e))

    def _reader():
        try:
            for _ in range(300):
                registry.redact_text("nothing to see here")
        except Exception as e:      # pragma: no cover - failure path
            errors.append(repr(e))

    threads = [threading.Thread(target=_writer) for _ in range(2)]
    threads += [threading.Thread(target=_reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []


def test_an_empty_registry_is_still_a_cheap_no_op():
    registry = SecretVariantRegistry()
    assert registry.redact_text("nothing") == "nothing"
