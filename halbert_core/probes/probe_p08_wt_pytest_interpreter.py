#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-08 — wt_pytest's env-shebang runs the suite on the WRONG interpreter.

The seam (collected empirically 2026-09-07): ``wt_pytest.py`` has
``#!/usr/bin/env python3``, so ``arch -arm64 ./wt_pytest.py tests/`` runs
pytest under the BASE framework interpreter (pytest 7.4, starlette 0.41),
not the project venv (pytest 9.1, starlette 1.6).  Under it, 12 tests red
that are green under the venv: 4 subprocess-based tests capture
``sys.executable`` = base python (no venv packages → empty output), and 5
route tests hit ``TestClient(client=...)`` which starlette 0.41 does not
accept.  A different interpreter's dependency set is not the product's.

This probe documents the two environments it can see and asserts nothing
beyond its own venv residency (which the bootstrap enforces).  The verdict
is OBSERVED by design; the interpreter mismatch is recorded, not fixed —
changing the wrapper's shebang is a separate decision.
"""

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap, CHECKOUT, VENV_DIR  # noqa: E402

bootstrap()

PROBE_ID = "P-08"

SNIPPET = (
    "import inspect, importlib;"
    "from starlette.testclient import TestClient;"
    "sig = inspect.signature(TestClient.__init__);"
    "print('client-kwarg', 'client' in sig.parameters, 'starlette', "
    "importlib.import_module('starlette').__version__)"
)


def main() -> int:
    base_python = shutil.which("python3")
    venv_python = Path(VENV_DIR) / "bin" / "python"

    def probe(exe):
        r = subprocess.run([str(exe), "-c", SNIPPET], capture_output=True, text=True, timeout=60)
        return (r.stdout.strip() or r.stderr.strip().splitlines()[-1:][0] if r.stderr.strip() else r.stdout.strip())

    base_line = probe(base_python) if base_python else "<no env python3>"
    venv_line = probe(venv_python)

    mismatch = base_line != venv_line
    print(
        f"PROBE {PROBE_ID} wt-pytest-interpreter: OBSERVED -- "
        f"base({base_python}): {base_line}; venv({venv_python}): {venv_line}; "
        f"dependency sets differ: {mismatch}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} wt-pytest-interpreter: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)