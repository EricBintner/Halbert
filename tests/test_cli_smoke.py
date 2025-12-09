import json
import os
import subprocess
import tempfile
from pathlib import Path


def test_policy_show_runs():
    """Smoke test: policy-show command prints valid JSON."""
    result = subprocess.run(
        ["python3", "Cerebric/main.py", "policy-show"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "default_allow" in data or "tools" in data


def test_policy_eval_runs():
    """Smoke test: policy-eval command evaluates decision."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"path": "/etc/cerebric/test.yml", "changes": {"a": 1}}, f)
        inputs_path = f.name
    try:
        result = subprocess.run(
            ["python3", "Cerebric/main.py", "policy-eval", "--tool", "write_config", "--inputs", inputs_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "allow" in data
        assert "reason" in data
    finally:
        os.unlink(inputs_path)


def test_build_dashboard_runs():
    """Smoke test: build-dashboard command runs without error."""
    result = subprocess.run(
        ["python3", "Cerebric/main.py", "build-dashboard"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    # Should print paths to dashboard artifacts
    assert "dashboard" in result.stdout or len(result.stdout.strip()) > 0
