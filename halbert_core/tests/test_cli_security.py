# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The standalone security CLI tools (TASK-03 Task 3.1, pinned here).

``halbert-check-credential`` and ``halbert-check-breach`` are human-run
tools that deliberately send a credential to its issuing service (and,
for HIBP, a k-anonymity hash prefix). They exist BECAUSE the automated
paths cannot: the Tier 2 architectural guarantee (pinned by
test_secure_response.py and test_tier2_guarantee.py) is that
``describe_secret`` and the MCP dispatch never make an external request.
These tests pin both halves of that split:

  1. The CLIs behave as tools: --help, JSON output, stdin mode, and
     exit codes that a human or script can branch on.
  2. The isolation: no module on the agent or MCP path imports the
     network-calling validation/compromise code.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from halbert_core.cli import check_breach, check_credential

CLI_DIR = Path(check_credential.__file__).parent

# Source files that must never import the network-calling tools. This is the
# "prove there is no code path" pattern: the guarantee is about the code,
# not about a config flag, so the pin is over source text.
AGENT_PATH_SOURCES = [
    "halbert_core/halbert_core/mcp/server.py",
    "halbert_core/halbert_core/config/queries.py",
    "halbert_core/halbert_core/config/secure_response.py",
    "halbert_core/halbert_core/config/sensitivity.py",
]
FORBIDDEN_MODULES = ("credential_validation", "compromise_detection")


class TestArchitecturalIsolation:
    def test_no_agent_or_mcp_source_imports_the_network_tools(self):
        # CLI_DIR = <worktree>/halbert_core/halbert_core/cli — three parents up
        # is the worktree root.
        repo_root = CLI_DIR.parent.parent.parent
        for rel in AGENT_PATH_SOURCES:
            source = (repo_root / rel).read_text()
            for module in FORBIDDEN_MODULES:
                assert module not in source, f"{rel} references {module}"

    def test_mcp_tool_registry_has_no_validation_or_breach_tool(self):
        from halbert_core.mcp.server import TOOL_HANDLERS

        assert TOOL_HANDLERS  # registry populated
        assert not any(
            "credential" in name or "breach" in name or "valid" in name
            for name in TOOL_HANDLERS
        )


class TestCheckCredentialCLI:
    def _run(self, argv, result):
        """Run main(); returns (mock, exit_code). Success exits implicitly 0
        (main returns); invalid/error exit explicitly via sys.exit."""
        with patch.object(check_credential, "validate_credential", return_value=result) as m:
            with patch("sys.argv", ["halbert-check-credential"] + argv):
                with pytest.raises(SystemExit) as exc:
                    check_credential.main()
        return m, exc.value.code

    def _run_ok(self, argv, result):
        """The success path — main() returns without sys.exit (implicit 0)."""
        with patch.object(check_credential, "validate_credential", return_value=result) as m:
            with patch("sys.argv", ["halbert-check-credential"] + argv):
                check_credential.main()  # no SystemExit
        return m

    def test_help_exits_zero(self, capsys):
        with patch("sys.argv", ["halbert-check-credential", "--help"]):
            with pytest.raises(SystemExit) as exc:
                check_credential.main()
        assert exc.value.code == 0
        assert "--service" in capsys.readouterr().out

    def test_valid_credential_exits_zero_with_json(self, capsys):
        called = self._run_ok(
            ["secret-value", "--service", "github"],
            {"status": "active", "service": "github"},
        )
        assert called.call_args.kwargs["value"] == "secret-value"
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "active"

    def test_invalid_credential_exits_one(self, capsys):
        _, code = self._run(
            ["secret-value", "--service", "github"],
            {"status": "invalid"},
        )
        assert code == 1

    def test_error_status_exits_two(self, capsys):
        _, code = self._run(
            ["secret-value", "--service", "github"],
            {"status": "error"},
        )
        assert code == 2

    def test_stdin_mode(self, capsys):
        with patch.object(check_credential, "validate_credential", return_value={"status": "active"}) as m:
            with patch("sys.argv", ["halbert-check-credential", "--service", "github", "--stdin"]):
                with patch("sys.stdin", io.StringIO("  from-stdin-token \n")):
                    check_credential.main()
        assert m.call_args.kwargs["value"] == "from-stdin-token"

    def test_missing_value_is_a_usage_error(self):
        with patch("sys.argv", ["halbert-check-credential", "--service", "github"]):
            with pytest.raises(SystemExit) as exc:
                check_credential.main()
        assert exc.value.code == 2  # argparse usage error


class TestCheckBreachCLI:
    def _run(self, argv, result):
        with patch.object(check_breach, "check_compromised", return_value=result) as m:
            with patch("sys.argv", ["halbert-check-breach"] + argv):
                with pytest.raises(SystemExit) as exc:
                    check_breach.main()
        return m, exc.value.code

    def test_help_exits_zero(self, capsys):
        with patch("sys.argv", ["halbert-check-breach", "--help"]):
            with pytest.raises(SystemExit) as exc:
                check_breach.main()
        assert exc.value.code == 0
        assert "--hibp" in capsys.readouterr().out

    def test_clean_credential_exits_zero(self, capsys):
        with patch.object(check_breach, "check_compromised", return_value={"status": "ok"}) as called:
            with patch("sys.argv", ["halbert-check-breach", "secret-value", "--hibp"]):
                check_breach.main()  # success: no sys.exit, implicit 0
        assert called.call_args.kwargs["hibp"] is True
        assert called.call_args.kwargs["github_scanning"] is False

    def test_compromised_credential_exits_one(self, capsys):
        _, code = self._run(["secret-value", "--github"], {"status": "compromised"})
        assert code == 1

    def test_error_status_exits_two(self, capsys):
        _, code = self._run(["secret-value", "--hibp", "--github"], {"status": "error"})
        assert code == 2

    def test_no_check_selected_is_a_usage_error(self):
        with patch("sys.argv", ["halbert-check-breach", "secret-value"]):
            with pytest.raises(SystemExit) as exc:
                check_breach.main()
        assert exc.value.code == 2

    def test_stdin_mode(self, capsys):
        with patch.object(check_breach, "check_compromised", return_value={"status": "ok"}):
            with patch("sys.argv", ["halbert-check-breach", "--hibp", "--stdin"]):
                with patch("sys.stdin", io.StringIO("from-stdin-password\n")):
                    check_breach.main()
        capsys.readouterr()  # consume the JSON output; reaching here means no crash