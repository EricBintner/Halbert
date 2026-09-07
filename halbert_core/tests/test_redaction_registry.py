# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the secret variant registry (Packet 05 Phase A).

Lifted from OpenClaw src/logging/secret-redaction-registry.ts: when a secret
value becomes known, register its exact value PLUS url-encoded and
json-escaped forms — those are the leak forms that evade plain-value
redaction.
"""
import json
import os
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.ingestion.redaction_registry import (
    REDACTION_PLACEHOLDER,
    SecretVariantRegistry,
)


def _reg():
    return SecretVariantRegistry(max_entries=64)


def test_plain_form_is_registered():
    reg = _reg()
    reg.register("hunter2")
    assert "hunter2" in reg
    assert reg.redact_text("password is hunter2 ok") == (
        f"password is {REDACTION_PLACEHOLDER} ok"
    )


def test_urlencoded_form_is_caught():
    reg = _reg()
    reg.register("p@ss w/rd")
    encoded = urllib.parse.quote("p@ss w/rd")
    assert reg.redact_text(f"see {encoded} in url") == (
        f"see {REDACTION_PLACEHOLDER} in url"
    )


def test_json_escaped_form_is_caught():
    reg = _reg()
    secret = 'say "hi"\\now'
    # the inner escaped form as it appears when embedded in JSON text
    escaped = json.dumps(secret)[1:-1]
    reg.register(secret)
    assert reg.redact_text(f"payload {escaped} end") == (
        f"payload {REDACTION_PLACEHOLDER} end"
    )


def test_bounded_and_fifo():
    reg = SecretVariantRegistry(max_entries=4)
    for i in range(6):
        reg.register(f"secret-{i}")
    assert "secret-0" not in reg  # oldest evicted
    assert "secret-5" in reg


def test_empty_and_short_values_ignored():
    reg = _reg()
    reg.register("")
    # too short to redact safely — would blank out ordinary text
    reg.register("ab")
    assert len(reg) == 0