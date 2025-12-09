from cerebric_core.cerebric_core.obs.audit import write_audit


def test_audit_hash_chain_links_records(tmp_path, monkeypatch):
    # Force logs into tmp dir
    monkeypatch.setenv("Cerebric_LOG_DIR", str(tmp_path / "logs"))
    tool = "unittest_tool_audit_chain"
    p1 = write_audit(tool=tool, mode="dry_run", request_id="r1", ok=True, summary="first")
    p2 = write_audit(tool=tool, mode="dry_run", request_id="r2", ok=True, summary="second")
    # Both writes go to the same file path
    assert p1 == p2
    with open(p1, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) >= 2
    import json
    first = json.loads(lines[-2])
    second = json.loads(lines[-1])
    assert "hash" in first
    assert second.get("prev_hash") == first.get("hash")
