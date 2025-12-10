import json
import os
from pathlib import Path
from datetime import datetime, timezone
from halbert_core.ingestion.redaction import redact_event
from halbert_core.ingestion.validate import TelemetryValidator
from halbert_core.ingestion.jsonl_writer import append_event


def test_ingestion_pipeline_redact_validate_write(tmp_path):
    # Load schema from repo docs
    repo_root = Path(__file__).resolve().parents[1]
    schema = repo_root / "docs" / "Phase1" / "schemas" / "telemetry-event.schema.json"
    v = TelemetryValidator(str(schema))

    # Sample event similar to normalized journald record
    evt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "journald",
        "host": "localhost",
        "type": "log",
        "subsystem": "test",
        "severity": "info",
        "message": "user me@example.com from 10.0.0.1",
        "data": {"identifier": "pytest", "unit": None},
        "tags": ["log"],
    }
    red = redact_event(evt)
    assert "<email>" in red["message"] and "<ip>" in red["message"]
    assert v.validate(red) is True

    # Write to tmp raw dir
    raw = tmp_path / "raw"
    raw.mkdir()
    out = append_event(str(raw), red)
    assert os.path.exists(out)
    with open(out, "r", encoding="utf-8") as f:
        line = f.readline().strip()
    rec = json.loads(line)
    assert rec.get("severity") == "info"
