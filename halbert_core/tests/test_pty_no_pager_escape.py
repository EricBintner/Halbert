# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A pager is a shell escape, so no command run in a PTY gets one.

Not in the 186-finding audit; found while reviewing the SEC-2 classifier work.

The command classifier decides at spawn whether a session is safe. A pager
invalidates that decision the moment it opens: ``git``, ``systemctl`` and ``man``
execute ``$GIT_PAGER`` / ``$SYSTEMD_PAGER`` / ``$MANPAGER`` *as a shell command*,
and ``less`` offers ``!command`` interactively. Writes into a live session's
stdin are never re-classified (F128), so the pager is the bridge between "the
classifier waved this through as read-only" and "there is a shell here now".

Measured before the fix, on this machine, through the real ``PTYSession``:
``git log -1`` classifies MEDIUM with ``requires_confirmation=False`` — it
auto-runs — and its pager executed as uid 501.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess

import pytest

from halbert_core.streaming.pty import _PAGER_NEUTERED, PTYSession


def _drain(session: PTYSession, limit: int = 16384) -> str:
    async def go():
        out = b""
        async for chunk in session.read_chunk():
            out += chunk
            if len(out) > limit:
                break
        return out

    return asyncio.run(go()).decode(errors="replace")


class TestPagerCannotEscape:
    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_git_pager_does_not_execute(self, monkeypatch, tmp_path):
        """The exact escape, end to end, through the real session object."""
        monkeypatch.setenv("GIT_PAGER", "sh -c 'echo ESCAPE-RAN-AS-$(id -u)'")

        repo = tmp_path / "repo"
        repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        (repo / "f").write_text("x")
        subprocess.run(["git", "add", "f"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=repo, check=True, env=env)

        session = PTYSession("git log -1", cwd=str(repo))
        asyncio.run(session.spawn())
        try:
            text = _drain(session)
        finally:
            session.kill()

        assert "ESCAPE-RAN-AS" not in text, (
            "GIT_PAGER executed. A command the classifier auto-runs as read-only "
            "must not be able to reach a shell through its pager."
        )

    def test_the_child_sees_a_neutered_pager(self, monkeypatch):
        """Belt to the brace above: prove the env actually reaches the child."""
        monkeypatch.setenv("PAGER", "sh -c 'echo OWNER-PAGER-RAN'")

        session = PTYSession("printf '%s|%s|%s' \"$PAGER\" \"$GIT_PAGER\" \"$LESSSECURE\"")
        asyncio.run(session.spawn())
        try:
            text = _drain(session, limit=256)
        finally:
            session.kill()

        assert "cat|cat|1" in text, f"child env not applied; saw {text!r}"
        assert "OWNER-PAGER-RAN" not in text

    def test_an_explicit_env_still_wins(self):
        """A caller that deliberately sets PAGER is not overridden.

        The neutered values are a floor, not a ceiling — they are applied before
        ``self._env`` so a session that genuinely wants a pager can ask for one.
        This keeps the fix from being the kind of blanket override that gets
        worked around later.
        """
        session = PTYSession("printf '%s' \"$PAGER\"", env={"PAGER": "deliberate"})
        asyncio.run(session.spawn())
        try:
            text = _drain(session, limit=256)
        finally:
            session.kill()

        assert "deliberate" in text

    def test_every_pager_variable_is_covered(self):
        """The set is the point; a missing one is a hole with no test of its own."""
        assert _PAGER_NEUTERED["PAGER"] == "cat"
        assert _PAGER_NEUTERED["GIT_PAGER"] == "cat"
        assert _PAGER_NEUTERED["SYSTEMD_PAGER"] == "cat"
        assert _PAGER_NEUTERED["MANPAGER"] == "cat"
        assert _PAGER_NEUTERED["LESSSECURE"] == "1"
