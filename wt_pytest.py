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

# 0. Re-exec under the shared venv's interpreter when started under another.
#
#    The shebang is `/usr/bin/env python3`, so `./wt_pytest.py` runs under
#    whatever python3 is first on PATH -- on this machine a pyenv shim, not
#    the venv. That interpreter has a pytest but no pytest-asyncio, and the
#    failure is silent in the worst way: the wrapper's own
#    `--asyncio-mode=auto` is rejected as an unknown argument, and without it
#    every `async def test_` is SKIPPED rather than failed. A run of a suite
#    that is mostly async reports "2 passed, 21 skipped" and looks green.
#
#    Found 2026-09-10: CLAUDE.md documents `arch -arm64 ./wt_pytest.py`, which
#    is exactly the broken invocation.
#    Walked up rather than computed: a worktree can sit at any depth, and an
#    off-by-one here reintroduces the silent skip it exists to prevent.
def _find_venv_python(start):
    d = start
    while True:
        cand = os.path.join(d, ".venv", "bin", "python")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


#    Compared on sys.prefix, NOT on the executable path: a venv's bin/python
#    is usually a symlink to the very interpreter that is already running, so
#    realpath(sys.executable) == realpath(venv python) is True even when the
#    environments -- and therefore the installed plugins -- differ. Comparing
#    the executables silently skipped the re-exec and left the bug in place.
_VENV_PY = _find_venv_python(WORKTREE)
_VENV_ROOT = os.path.dirname(os.path.dirname(_VENV_PY)) if _VENV_PY else ""
if _VENV_PY and os.path.realpath(sys.prefix) != os.path.realpath(_VENV_ROOT):
    os.execv(_VENV_PY, [_VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])

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

# 5. Enforce the suite's asyncio contract at the wrapper, not the invoking
#    shell. The contract lives in halbert_core/pyproject.toml
#    ([tool.pytest.ini_options] asyncio_mode = "auto"): fourteen suites
#    (voice, TTS, terminal-stream, compute, ...) write bare ``async def
#    test_`` with no marker and rely on auto-conversion. That ini applies
#    only when the run's inifile/rootdir resolution actually picks it up;
#    a run that loses it — a stray pytest.ini between cwd and the package
#    dir, or an ``asyncio_mode`` override riding in via PYTEST_ADDOPTS —
#    silently falls back to pytest-asyncio's built-in strict default and
#    fails ~200 async tests with "async def functions are not natively
#    supported", a signature that reads as a code regression but is pure
#    invocation environment (seen 2026-09-07 as a 205-failed/17-error full
#    gate; the committed tree itself is green under the gate invocation).
#
#    Two overrides cannot simply be out-ranked, so they are refused loudly:
#    ``-o asyncio_mode=...``/``--override-ini asyncio_mode=...`` beats both
#    the ini and the ``--asyncio-mode`` CLI flag inside pytest's option
#    resolution, and ``-p no:asyncio`` unloads the plugin outright. Anything
#    else (a missing ini, a stale one) is neutralized by appending
#    ``--asyncio-mode=auto``, which outranks every inifile. A caller who
#    truly wants strict mode bypasses the wrapper and calls pytest directly.
import shlex  # noqa: E402

try:
    _addopts = shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
except ValueError as _e:  # malformed quoting in the caller's env
    sys.stderr.write(f"REFUSING TO RUN: PYTEST_ADDOPTS does not shlex-split ({_e}).\n")
    raise SystemExit(2) from None

_tokens = sys.argv[1:] + _addopts


def _asyncio_override_values(tokens):
    """Every value the invocation explicitly assigns to asyncio mode."""
    values = []
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok in ("-o", "--override-ini"):
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt.split("=", 1)[0].strip() == "asyncio_mode":
                values.append(nxt.split("=", 1)[1] if "=" in nxt else "")
                skip_next = True
            continue
        if tok.startswith("--asyncio-mode="):
            values.append(tok.split("=", 1)[1])
            continue
        if tok == "--asyncio-mode":
            values.append(tokens[i + 1] if i + 1 < len(tokens) else "")
            skip_next = True
            continue
        if tok.startswith("-o") and "asyncio_mode" in tok:
            values.append(tok.split("=", 1)[1] if "=" in tok else "")
            continue
        if tok == "-p" and i + 1 < len(tokens) and tokens[i + 1] == "no:asyncio":
            values.append("no:asyncio")
            skip_next = True
            continue
        if tok.startswith("-p") and "no:asyncio" in tok:
            values.append("no:asyncio")
    return values


_overrides = _asyncio_override_values(_tokens)
_bad = [v for v in _overrides if v not in ("auto", "")]
if _bad:
    sys.stderr.write(
        f"REFUSING TO RUN: this run sets asyncio mode {_bad!r} (argv or "
        "PYTEST_ADDOPTS). The suite's contract is asyncio_mode=auto — "
        "fourteen suites rely on it and any other mode fails ~200 async "
        "tests with 'async def functions are not natively supported'. "
        "Drop the override, or bypass wt_pytest.py to run strict "
        "deliberately.\n"
    )
    raise SystemExit(2)

_argv = sys.argv[1:]
if not _overrides:
    _argv.append("--asyncio-mode=auto")

raise SystemExit(pytest.main(_argv))