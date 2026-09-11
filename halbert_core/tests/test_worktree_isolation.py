# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Guard: this checkout's tests must exercise this checkout's source.

Without the root conftest, a worktree's pytest run resolves ``halbert_core``
submodules through the editable install's meta-path finder, which points at
the checkout pip was run in. Everything passes, against the wrong code.

The assertion is on a *submodule*, deliberately. The top-level
``halbert_core`` resolves as a namespace package to whatever directory pytest
put on ``sys.path``, so it points at this tree even when every module inside
it is being loaded from somewhere else -- which makes it exactly the wrong
thing to assert on, and a guard that passes while the defect is present is
worse than no guard.
"""

import pathlib

from halbert_core.obs import logging as _probe


def test_submodules_resolve_inside_this_checkout():
    root = pathlib.Path(__file__).resolve().parents[2]
    resolved = pathlib.Path(_probe.__file__).resolve()
    assert root in resolved.parents, (
        f"halbert_core.obs.logging resolved to {resolved}, outside "
        f"this checkout ({root}). The tests are running against another "
        f"tree's source -- see the root conftest.py."
    )


def test_async_tests_are_actually_running_not_silently_skipped():
    """pytest-asyncio must be loaded, and in auto mode.

    Asserted from a *sync* test on purpose. When the plugin is missing, an
    `async def test_` is SKIPPED rather than failed -- so a guard written as
    an async test would skip alongside the suite it was meant to protect and
    report nothing. This is the only shape that can fail.

    The failure it guards: `wt_pytest.py`'s shebang is `/usr/bin/env python3`,
    so the documented `arch -arm64 ./wt_pytest.py` ran under whatever python3
    was first on PATH. That interpreter has pytest but no pytest-asyncio, and
    a mostly-async suite reported "2 passed, 21 skipped" and looked green.
    The wrapper now re-execs under the venv (compared on sys.prefix, since a
    venv's bin/python is typically a symlink to the running interpreter and
    comparing executables finds them identical).
    """
    import pytest_asyncio  # noqa: F401  -- absence is the bug


def test_the_asyncio_mode_is_auto(request):
    """Strict mode is the other half of the same failure: the plugin loads,
    every bare `async def test_` still skips."""
    mode = request.config.getoption("asyncio_mode", None) or \
        request.config.getini("asyncio_mode")
    assert str(mode).lower().endswith("auto"), (
        f"asyncio_mode is {mode!r}; bare async tests will be skipped, not run"
    )
