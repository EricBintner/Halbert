# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A reason of spaces is no reason, and must not fail the write.

``reason or UNRECORDED`` reads as though it handles a missing reason. It
does, for None and "". It does not for "   ", which is truthy: that survived
the coalesce, reached ``_require`` -- which strips -- and raised. By then the
file had been written. So the tool reported a failure for a change that had
happened, and recorded nothing about it on either plane: the worst of the
three possible outcomes, and the one the ledger exists to make impossible.

``_require`` raising is correct and stays. It is designated a programming
error at the call site, and there is no reason to substitute. What was wrong
was calling it with a value the caller should already have normalised.
"""

import pytest

from halbert_core.continuity.state_store import UNRECORDED, _require

BLANK = ["", "   ", "\t", "\n  \n", None]


class TestRequireStillRefusesBlanks:
    """Pinned: the fix must not be a loosening of _require."""

    @pytest.mark.parametrize("value", BLANK)
    def test_a_blank_reason_is_a_call_site_bug(self, value):
        with pytest.raises((ValueError, TypeError)):
            _require(value, "reason")

    def test_unrecorded_is_an_acceptable_reason(self):
        assert _require(UNRECORDED, "reason") == UNRECORDED


class TestTheCoalesceStripsFirst:
    """The normalisation each write path must perform before recording."""

    @pytest.mark.parametrize("value", BLANK)
    def test_every_blank_becomes_unrecorded(self, value):
        assert (str(value or "").strip() or UNRECORDED) == UNRECORDED

    def test_a_real_reason_survives_untouched(self):
        assert (str("  the founder asked  " or "").strip() or UNRECORDED) == "the founder asked"


def _unstripped(src: str) -> list:
    """Lines that coalesce a reason without stripping it first.

    Comments are skipped: this file's own prose explains the bug and would
    otherwise match the pattern it is describing.
    """
    out = []
    for line in src.splitlines():
        code = line.split("#", 1)[0]
        if "or UNRECORDED" in code and ".strip()" not in code:
            out.append(line.strip())
    return out


class TestTheWritePathsNormalise:
    """Asserted on the source, so a new write path cannot quietly skip it.

    A behavioural test would need a privileged file or a live ledger per
    path; this pins the shape at every site instead, and fails if one is
    added without it.
    """

    @pytest.mark.parametrize("module,symbol", [
        ("halbert_core.tools.write_config", "WriteConfig"),
        ("halbert_core.tools.executor", "ToolExecutor"),
    ])
    def test_the_coalesce_strips(self, module, symbol):
        import importlib
        import inspect

        src = inspect.getsource(getattr(importlib.import_module(module), symbol))
        bad = _unstripped(src)
        assert not bad, f"{symbol} coalesces a reason without stripping: {bad}"

    def test_the_editor_route_strips(self):
        import inspect

        from halbert_core.dashboard.routes import editor

        src = inspect.getsource(editor)
        bad = _unstripped(src)
        assert not bad, f"editor route coalesces a reason without stripping: {bad}"
