# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import re
from halbert_core.ingestion.redaction import redact_text, redact_event

def test_redact_text():
    # Both sides of the address policy in one line: a public address is a
    # secret because harvested text reaches a possibly cloud-hosted model,
    # while RFC1918 addressing is this host's own operational data.
    s = (
        "token=ABC123 email me@ex.com path /home/user secret:xyz "
        "public 93.184.216.34 lan 10.1.2.3"
    )
    r = redact_text(s)
    assert "token=" not in r and "secret:" not in r
    assert "/home/<user>" in r
    assert "<email>" in r
    assert "<ip>" in r
    assert "93.184.216.34" not in r
    assert "10.1.2.3" in r


def test_redact_event():
    evt = {
        "message": "password=abc",
        "data": {"note": "visit 93.184.216.34 lan 192.168.0.1"},
    }
    red = redact_event(evt)
    assert "password" not in red["message"].lower()
    note = red["data"]["note"]
    assert "<ip>" in note
    assert "93.184.216.34" not in note
    assert "192.168.0.1" in note
