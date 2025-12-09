import os
import json
import yaml
from cerebric_core.tools.write_config import WriteConfig


def test_apply_yaml_deep_merge_backup(tmp_path):
    wc = WriteConfig()
    p = tmp_path / "cfg.yaml"
    p.write_text("a:\n  b: 1\n", encoding="utf-8")
    diff, applied = wc._apply_yaml(str(p), {"a": {"c": 2}}, backup=True, apply=True)
    assert applied is True
    # backup exists
    assert os.path.exists(str(p) + ".bak")
    # merged content
    data = yaml.safe_load(p.read_text("utf-8"))
    assert data == {"a": {"b": 1, "c": 2}}
    assert "+  c: 2" in diff or "c: 2" in diff


def test_apply_json_merge(tmp_path):
    wc = WriteConfig()
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"x": 1, "nested": {"a": 1}}, indent=2), encoding="utf-8")
    diff, applied = wc._apply_json(str(p), {"nested": {"b": 2}}, backup=False, apply=True)
    assert applied is True
    after = json.loads(p.read_text("utf-8"))
    assert after["nested"] == {"a": 1, "b": 2}


def test_apply_ini_update(tmp_path):
    wc = WriteConfig()
    p = tmp_path / "svc.service"
    p.write_text("[Service]\nTimeoutStartSec=10\n", encoding="utf-8")
    diff, applied = wc._apply_ini(str(p), {"Service": {"TimeoutStartSec": 15}}, backup=False, apply=True)
    assert applied is True
    text = p.read_text("utf-8")
    assert "TimeoutStartSec = 15" in text


def test_yaml_dry_run_no_write(tmp_path):
    wc = WriteConfig()
    p = tmp_path / "cfg.yaml"
    p.write_text("foo: 1\n", encoding="utf-8")
    before = p.read_text("utf-8")
    diff, applied = wc._apply_yaml(str(p), {"foo": 2}, backup=True, apply=False)
    assert applied is False
    assert p.read_text("utf-8") == before
