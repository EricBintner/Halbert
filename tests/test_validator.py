import json
from pathlib import Path
from cerebric_core.ingestion.validate import TelemetryValidator


def test_validator_accepts_valid_event(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"ts": {"type": "string"}, "message": {"type": "string"}},
        "required": ["ts", "message"],
    }
    sp = tmp_path / "schema.json"
    sp.write_text(json.dumps(schema), encoding="utf-8")
    v = TelemetryValidator(str(sp))
    ok = v.validate({"ts": "2025-01-01T00:00:00Z", "message": "hello"})
    assert ok is True


def test_validator_rejects_invalid_event(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"ts": {"type": "string"}},
        "required": ["ts"],
        "additionalProperties": False,
    }
    sp = tmp_path / "schema.json"
    sp.write_text(json.dumps(schema), encoding="utf-8")
    v = TelemetryValidator(str(sp))
    # extra property not allowed
    ok = v.validate({"ts": "2025-01-01T00:00:00Z", "extra": 1})
    assert ok is False
