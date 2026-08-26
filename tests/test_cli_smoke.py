# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_policy_show_runs():
    """Smoke test: policy-show command prints valid JSON."""
    result = subprocess.run(
        [sys.executable, "Halbert/main.py", "policy-show"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    # Skip JSON validation if dependencies unavailable
    if "not available" in result.stdout:
        return
    data = json.loads(result.stdout)
    assert "default_allow" in data or "tools" in data


def test_policy_eval_runs():
    """Smoke test: policy-eval command evaluates decision."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"path": "/etc/halbert/test.yml", "changes": {"a": 1}}, f)
        inputs_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "Halbert/main.py", "policy-eval", "--tool", "write_config", "--inputs", inputs_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0
        # Skip JSON validation if dependencies unavailable
        if "not available" in result.stdout:
            return
        data = json.loads(result.stdout)
        assert "allow" in data
        assert "reason" in data
    finally:
        os.unlink(inputs_path)


def test_build_dashboard_runs(tmp_path):
    """Smoke test: build-dashboard command runs without error."""
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    result = subprocess.run(
        [sys.executable, "Halbert/main.py", "build-dashboard"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    assert result.returncode == 0
    # Should print paths to dashboard artifacts
    assert "dashboard" in result.stdout or len(result.stdout.strip()) > 0
