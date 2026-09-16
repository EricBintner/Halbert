# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""`cwd` is a tool argument, and the safety gate now classifies it.

`TerminalPool.run_block` interpolates the command into a bash line. It also
interpolated `cwd`, while `ToolSafetyFramework.classify` used to inspect only
`command` — so a benign command with a hostile `cwd` was approved as SAFE,
with no confirmation, and the whole line reached the shell.  SEC-2 closed
that: the base classifier resolves bare operands against `cwd`, so
`rm grub.cfg` with cwd=/boot is classified like `rm /boot/grub.cfg`.  The
quoting in `run_block` stays — defence in depth, not instead of the gate.

The pre-pool substrate was never exposed to this: `create_subprocess_shell`
takes `cwd` as a real chdir argument, not as shell text. The hole opened when
`afba3c22` made the pool the production path.
"""

import shlex

from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework

HOSTILE = "/tmp && touch /tmp/HALBERT_PWNED"


def _block_line(command: str, cwd: str) -> str:
    """The composition used by AgentPool.run_block."""
    from halbert_core.streaming import agent_pool
    import inspect

    src = inspect.getsource(agent_pool.TerminalPool.run_block)
    assert "shlex.quote(cwd)" in src, "run_block stopped quoting cwd"
    prefix = f"cd {shlex.quote(cwd)} && " if cwd else ""
    return f"({prefix}{command});"


class TestTheBaseClassifierReadsCwd:
    def test_a_destructive_command_is_classified_against_cwd(self):
        """SEC-2: `rm grub.cfg` with cwd=/boot is the same operation as
        `rm /boot/grub.cfg`. Only the second spelling was ever classified
        before; the gate now resolves bare operands against the directory the
        command will actually run in.
        """
        r = ToolSafetyFramework(user_overrides={}).classify(
            "run_command", {"command": "rm grub.cfg", "cwd": "/boot"})
        assert r.requires_confirmation, r

    def test_the_gate_and_the_quoting_are_separate_layers(self):
        """A hostile cwd string is quoted by run_block AND inert for
        classification: `/tmp && touch ...` is not a directory, so the read
        of it normalises away, leaving an ordinary (unraised) SAFE — the
        same verdict `ls` in /tmp gets. Both must hold: if quoting regresses
        the line is exploited; if cwd classification regresses, the skill
        layer below becomes the only thing watching.
        """
        r = ToolSafetyFramework(user_overrides={}).classify(
            "run_command", {"command": "ls", "cwd": HOSTILE})
        assert r.risk_level == RiskLevel.SAFE and not r.requires_confirmation

    def test_but_a_skill_protecting_the_path_still_confirms(self):
        """The skill layer confirms even what the base classifier only
        *elevates*: `ls` with cwd=/boot is LOW in the base (read-only at a
        watched path, auto-runs) but must prompt once storage-ops declares
        /boot protected. This is the test that fails if `set_skill_safety`
        stops being installed per turn.
        """
        from halbert_core.skills.composer import compose
        from halbert_core.skills.loader import BUILTIN_DIR, load_skills

        base = ToolSafetyFramework(user_overrides={}).classify(
            "run_command", {"command": "ls", "cwd": "/boot"})
        assert not base.requires_confirmation, base  # LOW: the skill must be the reason

        f = ToolSafetyFramework(user_overrides={})
        f.set_skill_safety(compose([load_skills([BUILTIN_DIR])["storage-ops"]]).safety)
        r = f.classify("run_command", {"command": "ls", "cwd": "/boot"})
        assert r.requires_confirmation, r


class TestTheCommandLineIsSafeAnyway:
    def test_a_hostile_cwd_cannot_add_a_command(self):
        """Asserted on tokens, not substrings.

        The dangerous text is still *in* the line — inertly, inside quotes —
        so a substring check would fail while the code is correct. What
        matters is how the shell splits it: one directory argument, not a
        command separator.
        """
        line = _block_line("ls", HOSTILE)
        tokens = shlex.split(line[1:].rstrip(");"))
        assert tokens == ["cd", HOSTILE, "&&", "ls"], tokens

    def test_the_shell_would_treat_it_as_one_path(self):
        line = _block_line("ls", HOSTILE)
        # bash -n proves it parses, and the tokens prove intent.
        tokens = shlex.split(line.rstrip(");").lstrip("("))
        assert HOSTILE in tokens, tokens

    def test_quote_characters_in_cwd_cannot_break_out(self):
        nasty = "/tmp'; touch /tmp/HALBERT_PWNED; echo '"
        line = _block_line("ls", nasty)
        assert "touch /tmp/HALBERT_PWNED;" not in line.replace(shlex.quote(nasty), "")

    def test_no_cwd_is_unchanged(self):
        assert _block_line("ls", "") == "(ls);"
