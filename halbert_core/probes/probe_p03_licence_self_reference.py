#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-03 — App Store licence gate: self-referential extras must not count as deps.

The seam (found 2026-09-01): ``scripts/check_appstore_deps.py`` counted the
project's own extras — ``light = ["halbert-core[dashboard]"]``,
``full = ["halbert-core[rag-legacy,...]"]`` — as third-party dependencies with
no licence-register entry, which blocked every App Store check (2 red tests
in the repo-root suite: 8 unregistered deps + the self-referential extras).

Probe (direct, no pytest): feed the checker a synthetic pyproject whose
optional-dependencies contain a self-reference and a real third-party dep;
assert the self-reference is filtered out of the parsed dependency list and
does not reach ``check()`` as a failure.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

PROBE_ID = "P-03"

PYPROJECT = """\
[project]
name = "halbert-core"
version = "1.0"
dependencies = [
    "pyyaml>=6.0",
    "halbert-core[vision]",
]

[project.optional-dependencies]
light = [
    "halbert-core[dashboard]",
]
full = [
    "halbert-core[rag-legacy,dashboard,vision]",
]
vision = [
    "opencv-python-headless>=4.8",
]
"""


def _load_checker():
    # THIS checkout's checker first; the repo-root path only as a fallback
    # (the main tree may have moved on since this worktree branched).
    here = Path(__file__).resolve().parents[2] / "scripts" / "check_appstore_deps.py"
    main_tree = Path("/Volumes/4TB-BAD/Halbert/scripts/check_appstore_deps.py")
    path = here if here.exists() else main_tree
    spec = importlib.util.spec_from_file_location("check_appstore_deps", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load_checker()
    with tempfile.TemporaryDirectory() as td:
        pyproject = Path(td) / "pyproject.toml"
        pyproject.write_text(PYPROJECT, encoding="utf-8")

        deps = mod.parse_pyproject(pyproject)
        names = [d["name"] for d in deps]

        self_refs = [n for n in names if n.lower() == "halbert-core"]
        third_party = [n for n in names if n.lower() != "halbert-core"]

        if self_refs:
            print(
                f"PROBE {PROBE_ID} licence-self-reference: RED -- "
                f"self-referential extras counted as deps: {self_refs}"
            )
            return 0
        if "opencv-python-headless" not in third_party or "pyyaml" not in third_party:
            print(
                f"PROBE {PROBE_ID} licence-self-reference: OBSERVED -- "
                f"third-party parse incomplete: {names}"
            )
            return 0

        # And the gate itself: an unregistered third-party dep fails, a
        # registered project name never appears as a failure.
        register = {"python": {"pyyaml": {"spdx": "MIT"}, "opencv-python-headless": {"spdx": "Apache-2.0"}}}
        failures, _, _ = mod.check("python", deps, register, {}, colour=False)
        unregistered = [f for f in failures if "no entry" in f]

        if unregistered:
            print(
                f"PROBE {PROBE_ID} licence-self-reference: RED -- "
                f"gate still flags: {unregistered}"
            )
            return 0

        print(
            "PROBE P-03 licence-self-reference: FIXED -- self-referential "
            "extras are filtered from parse and never reach the gate as failures"
        )
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} licence-self-reference: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)