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

from halbert_core.continuity import timeline


def test_submodules_resolve_inside_this_checkout():
    root = pathlib.Path(__file__).resolve().parents[2]
    resolved = pathlib.Path(timeline.__file__).resolve()
    assert root in resolved.parents, (
        f"halbert_core.continuity.timeline resolved to {resolved}, outside "
        f"this checkout ({root}). The tests are running against another "
        f"tree's source -- see the root conftest.py."
    )
