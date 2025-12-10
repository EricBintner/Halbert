import os
from pathlib import Path
from halbert_core.tools.write_config import WriteConfig
from halbert_core.tools.schedule_cron import ScheduleCron
from halbert_core.tools.base import ToolRequest


def _policy_yaml_paths_allow(allow_glob: str) -> str:
    return (
        "default_allow: true\n"
        "tools:\n"
        "  write_config:\n"
        "    allow: true\n"
        "    conditions:\n"
        f"      paths_allow: ['{allow_glob}']\n"
    )


def _policy_yaml_names_allow(names):
    names_list = ", ".join([f"'{n}'" for n in names])
    return (
        "default_allow: true\n"
        "tools:\n"
        "  schedule_cron:\n"
        "    allow: true\n"
        "    conditions:\n"
        f"      names_allow: [{names_list}]\n"
    )


def test_write_config_paths_allow_enforced(tmp_path, monkeypatch):
    cfgdir = tmp_path / "conf"
    cfgdir.mkdir()
    allow_root = tmp_path / "allowed"
    allow_root.mkdir()
    (cfgdir / "policy.yml").write_text(_policy_yaml_paths_allow(str(allow_root / "*") ), encoding="utf-8")
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(cfgdir))
    monkeypatch.setenv("Halbert_LOG_DIR", str(tmp_path / "logs"))

    tool = WriteConfig()
    # Denied path
    deny_path = tmp_path / "denied" / "cfg.yaml"
    deny_path.parent.mkdir()
    res = tool.execute(ToolRequest(tool=tool.name, request_id="r-deny", dry_run=False, confirm=True, inputs={
        "path": str(deny_path),
        "changes": {"a": 1},
        "backup": False,
    }))
    assert res.ok is False
    assert "path not allowed" in (res.error or "")

    # Allowed path
    allow_path = allow_root / "cfg.yaml"
    res2 = tool.execute(ToolRequest(tool=tool.name, request_id="r-allow", dry_run=False, confirm=True, inputs={
        "path": str(allow_path),
        "changes": {"a": 1},
        "backup": False,
    }))
    assert res2.ok is True
    assert res2.outputs.get("applied") is True


class DummyScheduleCron(ScheduleCron):
    def _write_crontab(self, text: str) -> None:
        # Avoid side effects in tests
        return

    def _read_crontab(self) -> str:
        return ""


def test_schedule_cron_names_allow_enforced(tmp_path, monkeypatch):
    cfgdir = tmp_path / "conf"
    cfgdir.mkdir()
    (cfgdir / "policy.yml").write_text(_policy_yaml_names_allow(["backup"]), encoding="utf-8")
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(cfgdir))
    monkeypatch.setenv("Halbert_LOG_DIR", str(tmp_path / "logs"))

    tool = DummyScheduleCron()
    # Denied name
    res = tool.execute(ToolRequest(tool=tool.name, request_id="r1", dry_run=False, confirm=True, inputs={
        "name": "cleanup",
        "schedule": "0 1 * * *",
        "command": "/bin/true",
    }))
    assert res.ok is False
    assert "name not allowed" in (res.error or "")

    # Allowed name
    res2 = tool.execute(ToolRequest(tool=tool.name, request_id="r2", dry_run=False, confirm=True, inputs={
        "name": "backup",
        "schedule": "0 2 * * *",
        "command": "/bin/true",
    }))
    assert res2.ok is True
    assert res2.outputs.get("installed") in (False, True)
