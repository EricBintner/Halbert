from cerebric_core.tools.write_config import WriteConfig
from cerebric_core.tools.base import ToolRequest


def test_write_config_rollback_restores_backup(tmp_path, monkeypatch):
    # Prepare current file and backup
    p = tmp_path / "svc.conf"
    p.write_text("key=NEW\n", encoding="utf-8")
    bak = tmp_path / "svc.conf.bak"
    bak.write_text("key=OLD\n", encoding="utf-8")

    # Ensure logs go to tmp
    monkeypatch.setenv("Cerebric_LOG_DIR", str(tmp_path / "logs"))

    tool = WriteConfig()
    req = ToolRequest(tool=tool.name, request_id="r-rollback", dry_run=False, confirm=True, inputs={
        "path": str(p),
        "rollback": True,
    })
    res = tool.execute(req)
    assert res.ok is True
    assert res.outputs.get("applied") is True
    assert p.read_text("utf-8") == "key=OLD\n"
    assert "key=OLD" in res.outputs.get("diff", "")
