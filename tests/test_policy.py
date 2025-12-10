import os
from halbert_core.tools.write_config import WriteConfig
from halbert_core.tools.schedule_cron import ScheduleCron
from halbert_core.tools.base import ToolRequest


def _deny_policy_yaml():
    return (
        "default_allow: true\n"
        "tools:\n"
        "  write_config:\n"
        "    allow: false\n"
        "  schedule_cron:\n"
        "    allow: false\n"
    )


def test_policy_denies_write_config_apply(tmp_path, monkeypatch):
    # Redirect config and logs
    cfgdir = tmp_path / "conf"
    cfgdir.mkdir()
    (cfgdir / "policy.yml").write_text(_deny_policy_yaml(), encoding="utf-8")
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(cfgdir))
    monkeypatch.setenv("Halbert_LOG_DIR", str(tmp_path / "logs"))

    tool = WriteConfig()
    req = ToolRequest(tool=tool.name, request_id="r1", dry_run=False, confirm=True, inputs={
        "path": str(tmp_path / "file.yaml"),
        "changes": {"a": 1},
        "backup": False,
    })
    res = tool.execute(req)
    assert res.ok is False
    assert "denied by policy" in (res.error or "")


def test_policy_denies_schedule_cron_apply(tmp_path, monkeypatch):
    cfgdir = tmp_path / "conf"
    cfgdir.mkdir()
    (cfgdir / "policy.yml").write_text(_deny_policy_yaml(), encoding="utf-8")
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(cfgdir))
    monkeypatch.setenv("Halbert_LOG_DIR", str(tmp_path / "logs"))

    tool = ScheduleCron()
    req = ToolRequest(tool=tool.name, request_id="r2", dry_run=False, confirm=True, inputs={
        "name": "backup",
        "schedule": "0 2 * * *",
        "command": "/usr/local/bin/backup",
    })
    res = tool.execute(req)
    assert res.ok is False
    assert "denied by policy" in (res.error or "")
