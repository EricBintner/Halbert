import re
from halbert_core.ingestion.redaction import redact_text, redact_event

def test_redact_text():
    s = "token=ABC123 email me@ex.com path /home/user secret:xyz IP 10.1.2.3"
    r = redact_text(s)
    assert "token=" not in r and "secret:" not in r
    assert "/home/<user>" in r
    assert "<email>" in r
    assert "<ip>" in r


def test_redact_event():
    evt = {"message": "password=abc", "data": {"note": "visit 192.168.0.1"}}
    red = redact_event(evt)
    assert "password" not in red["message"].lower()
    assert "<ip>" in red["data"]["note"]
