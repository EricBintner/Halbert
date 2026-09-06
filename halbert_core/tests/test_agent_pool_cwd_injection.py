# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""`cwd` is a tool argument, and the safety gate never classified it.

`TerminalPool.run_block` interpolates the command into a bash line. It also
interpolated `cwd`, while `ToolSafetyFramework.classify` inspects only
`command` — so a benign command with a hostile `cwd` was approved as SAFE,
with no confirmation, and the whole line reached the shell.

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


class TestTheGateDoesNotSeeCwd:
    def test_the_base_classifier_still_does_not_classify_cwd(self):
        """Pinned as the reason quoting is load-bearing, not as approval of it.

        Narrowed by B3: the *skill* pass now reads cwd, so a protected path
        reached through it is classified (see the companion test below and
        `test_skills_safety_binding.py`). The base classifier still does not,
        which is why the quoting stays — defence in depth, not instead of it.
        """
        r = ToolSafetyFramework().classify(
            "run_command", {"command": "ls", "cwd": HOSTILE})
        assert r.risk_level == RiskLevel.SAFE and not r.requires_confirmation

    def test_but_a_skill_protecting_the_path_does_classify_it(self):
        """B3: `rm grub.cfg` with cwd=/boot used to be MEDIUM with no
        confirmation while `cd /boot && rm grub.cfg` was HIGH — the same
        operation, one classified and one not.
        """
        from halbert_core.skills.composer import compose
        from halbert_core.skills.loader import BUILTIN_DIR, load_skills

        f = ToolSafetyFramework()
        f.set_skill_safety(compose([load_skills([BUILTIN_DIR])["storage-ops"]]).safety)
        r = f.classify("run_command", {"command": "rm grub.cfg", "cwd": "/boot"})
        assert r.requires_confirmation


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
