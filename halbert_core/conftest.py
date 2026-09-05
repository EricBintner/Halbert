# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Make a git worktree test its own code.

``pip install -e`` puts a generated finder in ``sys.meta_path`` whose MAPPING
pins ``halbert_core`` to the checkout it was installed from. ``sys.meta_path``
is consulted before ``sys.path``, so from a worktree that finder wins: pytest
runs the worktree's *test* files against the *main* checkout's source. The
tests pass, and they passed against code the branch did not write.

That is the same failure as asserting on a MagicMock, one level up -- a
confident green over the wrong thing -- so it gets the same treatment as any
other silent-loss defect: detect it, and say so.

This file lives beside ``pyproject.toml`` because that is what sets pytest's
rootdir, and a conftest above the rootdir is never collected.

When this checkout is not the one the editable install points at, the finder
is dropped and this tree goes to the front of ``sys.path``. In the checkout
the install came from, nothing happens.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Optional

#: The checkout this conftest belongs to (``<checkout>/halbert_core/conftest.py``).
_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _editable_target(finder) -> Optional[pathlib.Path]:
    """Where an editable finder resolves ``halbert_core``, if it is one.

    ``MAPPING`` is a module-level global in the generated finder file, and
    setuptools appends the *class* to ``sys.meta_path`` -- so
    ``getattr(finder, "MAPPING")`` is None and a check written that way
    silently never fires. Read it off the defining module instead.
    """
    module = sys.modules.get(getattr(finder, "__module__", ""))
    mapping = getattr(module, "MAPPING", None)
    if not isinstance(mapping, dict):
        return None
    target = mapping.get("halbert_core")
    if not target:
        return None
    return pathlib.Path(target).resolve()


def _redirect_to_this_tree() -> Optional[pathlib.Path]:
    kept = []
    displaced = None
    for finder in sys.meta_path:
        target = _editable_target(finder)
        if target is not None and _ROOT not in target.parents:
            displaced = target
            continue
        kept.append(finder)

    if displaced is None:
        return None

    sys.meta_path = kept
    for entry in (str(_ROOT / "halbert_core"), str(_ROOT)):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)

    # Anything imported before this point came from the wrong tree.
    for name in [n for n in sys.modules if n == "halbert_core" or n.startswith("halbert_core.")]:
        del sys.modules[name]

    return displaced


#: Set when this run was redirected away from the editable install's target,
#: so the header can say so. A redirect that happens silently is the same
#: hazard in a smaller font.
_DISPLACED = _redirect_to_this_tree()


def pytest_report_header(config):
    if _DISPLACED is None:
        return None
    return (
        f"worktree isolation: editable install points at {_DISPLACED}; "
        f"redirected to {_ROOT} so this checkout tests its own source"
    )
