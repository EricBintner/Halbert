"""
Tests for the Tauri sidecar launcher script (src-tauri/binaries/halbert-api-*).

The script must locate the Halbert repo root regardless of where Tauri copies
it (src-tauri/binaries/, target/debug/, Halbert.app/Contents/MacOS/), honour
HALBERT_REPO_ROOT, fail clearly when no root can be found, and the three
per-target copies must stay byte-identical.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BINARIES = REPO_ROOT / "halbert_core/halbert_core/dashboard/frontend/src-tauri/binaries"
SCRIPTS = [
    BINARIES / "halbert-api-aarch64-apple-darwin",
    BINARIES / "halbert-api-x86_64-apple-darwin",
    BINARIES / "halbert-api-x86_64-unknown-linux-gnu",
]
SCRIPT = SCRIPTS[0]

FAKE_PYTHON = """#!/bin/bash
echo "CWD=$(pwd)"
echo "ARGV=$*"
"""


def _make_repo_skeleton(root: Path) -> Path:
    (root / "halbert_core").mkdir(parents=True)
    (root / "halbert_core" / "pyproject.toml").write_text("[project]\nname='x'\n")
    py = root / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    return root


def _run(script: Path, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update(env)
    return subprocess.run(
        ["bash", str(script)],
        env=base,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_sidecar_scripts_identical():
    contents = [p.read_bytes() for p in SCRIPTS]
    assert all(c == contents[0] for c in contents), "sidecar scripts have drifted"
    for p in SCRIPTS:
        assert os.access(p, os.X_OK), f"{p.name} is not executable"


def test_sidecar_script_bash_syntax():
    for p in SCRIPTS:
        subprocess.run(["bash", "-n", str(p)], check=True)


def test_sidecar_script_finds_repo_root_from_target_debug(tmp_path):
    # Skeleton repo with the script copied to where tauri-build puts it in dev.
    root = _make_repo_skeleton(tmp_path / "repo")
    debug_dir = root / "halbert_core/halbert_core/dashboard/frontend/src-tauri/target/debug"
    debug_dir.mkdir(parents=True)
    copied = debug_dir / "halbert-api"
    shutil.copy(SCRIPT, copied)

    res = _run(copied, {"HALBERT_PORT": "1", "HALBERT_HOST": "127.0.0.1", "HOME": str(tmp_path / "home")}, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    assert f"CWD={root}" in res.stdout
    assert "--port 1" in res.stdout
    assert "--host 127.0.0.1" in res.stdout
    assert "-m uvicorn halbert_core.dashboard.app:app" in res.stdout


def test_sidecar_script_finds_repo_root_from_app_bundle(tmp_path):
    root = _make_repo_skeleton(tmp_path / "repo")
    macos_dir = root / "halbert_core/halbert_core/dashboard/frontend/src-tauri/target/release/bundle/macos/Halbert.app/Contents/MacOS"
    macos_dir.mkdir(parents=True)
    copied = macos_dir / "halbert-api"
    shutil.copy(SCRIPT, copied)
    res = _run(copied, {"HOME": str(tmp_path / "home")}, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    assert f"CWD={root}" in res.stdout
    assert "--port 8000" in res.stdout


def test_sidecar_script_honours_HALBERT_REPO_ROOT(tmp_path):
    root = _make_repo_skeleton(tmp_path / "custom")
    res = _run(SCRIPT, {"HALBERT_REPO_ROOT": str(root), "HALBERT_PORT": "4321"}, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    assert f"CWD={root}" in res.stdout
    assert "--port 4321" in res.stdout


def test_sidecar_script_falls_back_to_local_share(tmp_path):
    home = tmp_path / "home"
    root = _make_repo_skeleton(home / ".local/share/halbert/repo")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    copied = outside / "halbert-api"
    shutil.copy(SCRIPT, copied)
    res = _run(copied, {"HOME": str(home)}, cwd=outside)
    assert res.returncode == 0, res.stderr
    assert f"CWD={root}" in res.stdout


def test_sidecar_script_fails_clearly_without_root(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    copied = outside / "halbert-api"
    shutil.copy(SCRIPT, copied)
    res = _run(copied, {"HOME": str(home)}, cwd=outside)
    assert res.returncode == 1
    assert "cannot locate Halbert repo root" in res.stderr
