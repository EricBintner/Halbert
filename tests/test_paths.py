import os
from cerebric_core.utils.paths import config_dir, data_dir, log_dir, data_subdir, log_subdir, state_subdir

def test_env_overrides_take_precedence(tmp_path, monkeypatch):
    c = tmp_path / "cfg"
    d = tmp_path / "dat"
    l = tmp_path / "log"
    c.mkdir()
    d.mkdir()
    l.mkdir()
    monkeypatch.setenv("Cerebric_CONFIG_DIR", str(c))
    monkeypatch.setenv("Cerebric_DATA_DIR", str(d))
    monkeypatch.setenv("Cerebric_LOG_DIR", str(l))
    assert config_dir() == str(c)
    assert data_dir() == str(d)
    assert log_dir() == str(l)


def test_subdir_creates_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("Cerebric_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("Cerebric_LOG_DIR", str(tmp_path / "logs"))
    p1 = data_subdir("raw", "journald")
    p2 = log_subdir("audit", "2025")
    p3 = state_subdir("journald")
    assert os.path.isdir(p1)
    assert os.path.isdir(p2)
    assert os.path.isdir(p3)
