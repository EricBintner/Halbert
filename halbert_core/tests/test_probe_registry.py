# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The probe registry's self-check: the battery cannot rot silently.

Every probe listed in ``halbert_core/probes/PROBES.md`` must (a) exist, (b)
run to a verdict under the project venv, and (c) report the verdict its
claimed status predicts:

* ``fixed-red-on-main`` → ``FIXED``  (the defect mechanism is absent on main)
* ``still-red``          → ``RED``    (the defect mechanism is live on main;
  the probe RECORDS the red — nothing in this battery fixes tests)
* ``observational``      → ``OBSERVED`` (environment- or load-dependent; the
  probe records what it saw)

A probe exiting nonzero means the probe harness itself broke (wrong
interpreter, import failure, crash) and fails the registry regardless of
claimed status.  See ``probes/_env.py`` for the result-line contract.
"""

import re
import subprocess
import sys
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parents[1] / "probes"
PROBES_MD = PROBES_DIR / "PROBES.md"

# The venv the probes must run under (same resolution _env.py enforces).
VENV_PY = Path("/Volumes/4TB-BAD/Halbert/.venv/bin/python")
if not VENV_PY.exists():
    VENV_PY = Path(sys.executable)

#: claimed status → the verdict the probe must report on current main
EXPECTED_VERDICT = {
    "fixed-red-on-main": "FIXED",
    "still-red": "RED",
    "observational": "OBSERVED",
}


def _parse_table():
    """(probe_id, slug, status) from the PROBES.md battery table."""
    rows = []
    for line in PROBES_MD.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|") or line.strip().startswith("|--") or line.strip().startswith("| Probe"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        m = re.match(r"^(P-\d+)\b(.*)$", cells[0])
        if not m:
            continue
        probe_id, slug = m.group(1), m.group(2).strip()
        status = cells[3].strip().strip("*").strip()
        rows.append((probe_id, slug, status))
    return rows


def _probe_num(filename: str) -> str:
    """'probe_p01_*.py' -> 'P-01'."""
    m = re.match(r"probe_p(\d+)_", filename)
    return f"P-{int(m.group(1)):02d}" if m else ""


def _probe_files():
    return sorted(p for p in PROBES_DIR.glob("probe_p*.py") if p.is_file())


def test_registry_table_is_complete():
    rows = _parse_table()
    assert rows, "PROBES.md battery table missing or unparsable"
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)), f"duplicate probe rows: {ids}"

    listed = {r[0] for r in rows}
    on_disk = {_probe_num(f.name) for f in _probe_files()}
    assert listed == on_disk, (
        f"battery table and probes/ disagree: table={sorted(listed)} disk={sorted(on_disk)}"
    )
    for probe_id, _, status in rows:
        assert status in EXPECTED_VERDICT, f"{probe_id}: unknown status {status!r}"


def test_every_probe_agrees_with_the_registry():
    for probe_id, slug, status in _parse_table():
        files = [f for f in _probe_files() if _probe_num(f.name) == probe_id]
        assert len(files) == 1, f"{probe_id}: expected exactly one probe file, got {files}"
        result = subprocess.run(
            [str(VENV_PY), str(files[0])],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROBES_DIR.parent),
        )
        assert result.returncode == 0, (
            f"{probe_id} exited {result.returncode} (probe harness broke, "
            f"not a verdict): stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        marker = next(
            (l for l in result.stdout.splitlines() if l.startswith(f"PROBE {probe_id} ")),
            None,
        )
        assert marker is not None, (
            f"{probe_id} printed no 'PROBE {probe_id} ...' result line; stdout:\n{result.stdout}"
        )
        verdict = marker.split(":")[1].split("--")[0].strip()
        expected = EXPECTED_VERDICT[status]
        assert verdict == expected, (
            f"{probe_id} ({slug}): registry claims {status!r} but the probe "
            f"observed {verdict!r} -- update PROBES.md to match reality, or "
            f"the seam changed under the battery: {marker!r}"
        )