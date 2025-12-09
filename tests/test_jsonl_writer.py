import json
import os
from datetime import datetime, timezone
from cerebric_core.cerebric_core.ingestion.jsonl_writer import append_event


def test_append_event_writes_jsonl(tmp_path):
    base = tmp_path / "raw"
    base.mkdir()
    evt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "journald",
        "host": "localhost",
        "type": "log",
        "subsystem": "test",
        "severity": "info",
        "message": "hello",
        "data": {"k": "v"},
        "tags": ["log"],
    }
    path = append_event(str(base), evt)
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
    rec = json.loads(line)
    assert rec["message"] == "hello"
    assert rec["source"] == "journald"
