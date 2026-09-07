# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared bootstrap for standalone probe scripts (Hermes probe-battery style).

Probes run OUTSIDE pytest, as plain scripts, with direct module calls.  Two
traps they must clear before importing anything of ours:

1. The shared venv's editable install of ``halbert_core`` pins every import
   to the MAIN tree via a MetaPathFinder.  A probe run from a worktree would
   silently test the wrong code.  Same medicine as ``wt_pytest.py``: strip
   the custom finders, prepend this worktree's package dir, then PROVE the
   resolution before continuing.
2. ``wt_pytest.py``'s ``#!/usr/bin/env python3`` shebang runs the whole test
   suite under the BASE framework interpreter, whose dependency set differs
   from the venv's (starlette 0.41 vs 1.6, pytest 7 vs 9).  Probes therefore
   refuse to run under any interpreter but the venv's, so a probe result is
   always a statement about the venv environment the product ships in.

Every probe prints exactly one result line::

    PROBE <id> <slug>: <VERDICT> -- <detail>

VERDICT is FIXED (the seam's defect mechanism is absent on this revision),
RED (the defect mechanism is live and reproduced), or OBSERVED (an
observational probe: the seam is environment- or load-dependent, and the
probe records what it saw).  Exit code is 0 as long as the probe ran to a
verdict; nonzero means the probe harness itself broke, which the registry
test treats as a failure regardless of claimed status.
"""

import os
import sys

# The package parent is the dir that contains the ``halbert_core`` package:
# <checkout>/halbert_core/ .  _env.py lives at <checkout>/halbert_core/probes/.
PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKOUT = os.path.dirname(PKG_PARENT)
VENV_DIR = os.path.join(os.path.dirname(CHECKOUT), ".venv")
if not os.path.isdir(VENV_DIR):
    # Worktrees of worktrees: fall back to the canonical shared venv.
    VENV_DIR = "/Volumes/4TB-BAD/Halbert/.venv"

_KEEP = ("builtins", "_frozen_importlib", "_frozen_importlib_external")


def _venv_realpath(path: str) -> str:
    return os.path.realpath(path)


def bootstrap() -> None:
    """Pin imports to THIS checkout and refuse a wrong interpreter."""
    # sys.executable is how we were LAUNCHED; the venv's bin/python may be a
    # symlink to the framework build, so realpath would erase the distinction
    # we are testing.  Compare launch paths: the venv python launches as
    # <venv>/bin/python, the base python as the framework path.
    exe = os.path.abspath(sys.executable)
    venv = _venv_realpath(VENV_DIR)
    if not exe.startswith(venv + os.sep):
        sys.stderr.write(
            f"REFUSING TO RUN: probe interpreter {exe} is not the venv ({venv}).\n"
            "Run probes as:  arch -arm64 "
            f"{venv}/bin/python halbert_core/probes/<probe>.py\n"
            "(wt_pytest.py's env-python3 shebang drags in a different "
            "dependency set; probe verdicts are venv statements.)\n"
        )
        raise SystemExit(2)

    # 1. Drop every custom MetaPathFinder (the editable-install finder that
    #    pins halbert_core to the main tree).
    sys.meta_path = [f for f in sys.meta_path if type(f).__module__ in _KEEP]

    # 2. Purge any halbert_core modules already imported.
    for name in [m for m in sys.modules if m == "halbert_core" or m.startswith("halbert_core.")]:
        del sys.modules[name]

    # 3. This worktree's package dir first.
    sys.path.insert(0, PKG_PARENT)

    # 4. Prove it.
    import halbert_core  # noqa: E402

    real = os.path.realpath(halbert_core.__file__)
    expected = os.path.join(PKG_PARENT, "halbert_core")
    if not real.startswith(expected):
        sys.stderr.write(
            f"REFUSING TO RUN: halbert_core resolved to {real}, not this "
            f"worktree ({expected}).\n"
        )
        raise SystemExit(2)