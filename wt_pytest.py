#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Run pytest against THIS worktree's halbert_core, not the main tree.

The shared venv (/Volumes/4TB-BAD/Halbert/.venv) has an editable install of
halbert_core whose MetaPathFinder pins every import to
/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core — the MAIN tree. Plain
pytest run from a worktree therefore silently tests the wrong code.

This wrapper: strips that finder, purges cached halbert_core modules,
prepends this worktree's package dir, asserts resolution, then hands off
to pytest.

Usage: arch -arm64 ./wt_pytest.py <pytest args>   (run from the worktree root)
"""
import os
import sys

WORKTREE = os.path.dirname(os.path.abspath(__file__))
PKG_PARENT = os.path.join(WORKTREE, "halbert_core")  # dir holding the halbert_core/ package

# 1. Drop every custom MetaPathFinder. The standard finders are the frozen
#    ones (classes — hence 'builtins' as their type's module — or instances
#    from _frozen_importlib_external); everything else (_distutils_hack, the
#    setuptools editable finder that pins the MAIN tree) is custom and goes.
_KEEP = ("builtins", "_frozen_importlib", "_frozen_importlib_external")
sys.meta_path = [f for f in sys.meta_path if type(f).__module__ in _KEEP]

# 2. Purge any halbert_core modules imported at interpreter startup.
for name in [m for m in sys.modules if m == "halbert_core" or m.startswith("halbert_core.")]:
    del sys.modules[name]

# 3. Make this worktree's package dir the first place Python looks. This also
#    shadows the repo-root entry pytest adds later (the outer halbert_core
#    project dir would otherwise resolve as a namespace package).
sys.path.insert(0, PKG_PARENT)

# 4. Prove it before spending a test run on it.
import halbert_core  # noqa: E402

real = os.path.realpath(halbert_core.__file__)
expected = os.path.join(PKG_PARENT, "halbert_core")
if not real.startswith(expected):
    sys.stderr.write(
        f"REFUSING TO RUN: halbert_core resolved to {real}, not this worktree "
        f"({expected}). The editable-install finder was not stripped.\n"
    )
    raise SystemExit(2)

import pytest  # noqa: E402

raise SystemExit(pytest.main(sys.argv[1:]))