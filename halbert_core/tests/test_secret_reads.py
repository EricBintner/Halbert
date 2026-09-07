# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Reading a credential is the harm, and it was classified as harmless.

Not in the 186-finding audit; found while reviewing the SEC-2 classifier work.

Measured before this fix, on this machine:

    read_file  /etc/shadow                      -> SAFE   conf=False
    read_file  ~/.ssh/id_ed25519                -> SAFE   conf=False
    read_file  ~/.aws/credentials               -> SAFE   conf=False
    cat ~/.ssh/id_ed25519                       -> LOW    conf=False

``_classify_builtin`` returned SAFE for every ``read_file`` path — "read-only"
is a statement about the filesystem, not about harm. The ``cat`` route was no
better: SENSITIVE_PATHS elevates by exactly one level, and SAFE -> LOW still
auto-runs. Only MEDIUM -> HIGH ever gated anything.

The half of this file that matters most is TestDoesNotOverCorrect. A gate that
fires when the owner reads ``sshd_config`` is a gate they switch off, and then
it protects nothing.
"""
from __future__ import annotations

import pytest

from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework


@pytest.fixture
def f():
    return ToolSafetyFramework()


def _check(f, tool, args):
    fn = getattr(f, "check_tool_call", None) or getattr(f, "classify", None)
    return fn(tool, args)


class TestCredentialReadsAreGated:
    @pytest.mark.parametrize("path", [
        "/etc/shadow",
        "/etc/sudoers",
        "/etc/master.passwd",
        "/home/me/.ssh/id_ed25519",
        "/home/me/.ssh/id_rsa",
        "/home/me/.aws/credentials",
        "/home/me/.netrc",
        "/home/me/.pgpass",
        "/etc/ssl/private/server.key",
        "/etc/ssl/certs/bundle.pem",
        "/home/me/vault.kdbx",
        "/home/me/.local/state/halbert/api-token",
    ])
    def test_read_file_on_a_credential_requires_confirmation(self, f, path):
        r = _check(f, "read_file", {"path": path})
        assert r.risk_level == RiskLevel.HIGH, f"{path} classified {r.risk_level}"
        assert r.requires_confirmation is True

    @pytest.mark.parametrize("cmd", [
        "cat /home/me/.ssh/id_ed25519",
        'cat "/home/me/.ssh/id_ed25519"',
        "cat '/home/me/.ssh/id_ed25519'",
        "head -1 /etc/shadow",
        "cp /home/me/.aws/credentials /tmp/x",
        "base64 /home/me/.ssh/id_rsa",
    ])
    def test_a_command_reading_a_credential_requires_confirmation(self, f, cmd):
        r = f.classify_command(cmd) if hasattr(f, "classify_command") else f._classify_command(cmd)
        assert r.risk_level == RiskLevel.HIGH, f"{cmd!r} classified {r.risk_level}"
        assert r.requires_confirmation is True

    def test_quoting_does_not_skip_the_check(self, f):
        """The bypass an adversarial reviewer found in the proposed rewrite.

        A path analysis fed raw whitespace-split tokens sees a quoted absolute
        path as a token that does not start with '/', drops it, and skips the
        whole credential tier. One pair of quotes, and a model writes them about
        as often as not.
        """
        bare = f._classify_command("cat /home/me/.ssh/id_ed25519")
        quoted = f._classify_command('cat "/home/me/.ssh/id_ed25519"')
        assert bare.risk_level == quoted.risk_level == RiskLevel.HIGH


class TestDoesNotOverCorrect:
    """The half that keeps the gate switched on.

    Every case here is something the owner does on an ordinary day. If any of
    them starts prompting, the credential tier has been drawn as a directory
    rule again and needs narrowing, not widening.
    """

    @pytest.mark.parametrize("path", [
        "/etc/ssh/sshd_config",          # the file routes/editor.py exists to edit
        "/home/me/.ssh/config",
        "/home/me/.ssh/known_hosts",
        "/home/me/.ssh/authorized_keys",
        "/home/me/.ssh/id_ed25519.pub",  # a public key is not a secret
        "/home/me/.ssh/id_rsa.pub",
        "/etc/hosts",
        "/etc/fstab",
        "/var/log/syslog",
        "/home/me/notes.md",
    ])
    def test_ordinary_reads_stay_safe(self, f, path):
        r = _check(f, "read_file", {"path": path})
        assert r.requires_confirmation is False, f"{path} would now prompt"

    @pytest.mark.parametrize("cmd", [
        "cat /etc/ssh/sshd_config",
        "ls ~/.ssh",
        "cat /home/me/.ssh/known_hosts",
        "cat /home/me/.ssh/id_ed25519.pub",
        "grep Port /etc/ssh/sshd_config",
    ])
    def test_ordinary_commands_do_not_prompt(self, f, cmd):
        r = f._classify_command(cmd)
        assert r.requires_confirmation is False, f"{cmd!r} would now prompt"


class TestTheHelperItself:
    def test_public_keys_are_checked_before_the_id_prefix(self):
        """Ordering bug waiting to happen: id_ed25519.pub starts with 'id_'."""
        from halbert_core.tools.safety import _secret_read

        assert _secret_read("/x/id_ed25519") == "id_ed25519"
        assert _secret_read("/x/id_ed25519.pub") is None

    def test_empty_and_junk(self):
        from halbert_core.tools.safety import _secret_read

        assert _secret_read("") is None
        assert _secret_read("   ") is None
        assert _secret_read('""') is None
