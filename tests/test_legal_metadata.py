# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Guards for the legal/licensing hygiene tasks (LEG-MIN-01, LEG-MIN-02, LEG-MOD-05).

- every first-party source file carries an SPDX header
- the package version and licence are declared consistently
- the CLI shows GPLv3 "Appropriate Legal Notices"
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "add_spdx_headers.py"
EXPECTED_COPYRIGHT = "Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors"


def _load_spdx_tool():
    spec = importlib.util.spec_from_file_location("add_spdx_headers", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── LEG-MIN-01: SPDX headers ────────────────────────────────────────────────

def test_all_first_party_sources_have_spdx_headers():
    tool = _load_spdx_tool()
    missing = tool.process(tool.candidate_files(), write=False)
    rel = sorted(p.relative_to(REPO).as_posix() for p in missing)
    assert not rel, (
        f"{len(rel)} source file(s) lack an SPDX header; run scripts/add_spdx_headers.py:\n  "
        + "\n  ".join(rel)
    )


def test_spdx_tool_places_header_after_shebang_and_coding_line(tmp_path):
    tool = _load_spdx_tool()
    py = tmp_path / "x.py"
    text = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nimport os\n"
    out = tool.with_header(text, py)
    assert out.splitlines()[:4] == [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        f"# SPDX-License-Identifier: {tool.LICENSE_ID}",
        f"# {EXPECTED_COPYRIGHT}",
    ]
    assert out.endswith("import os\n")


def test_spdx_tool_is_idempotent(tmp_path):
    tool = _load_spdx_tool()
    ts = tmp_path / "x.ts"
    once = tool.with_header("export const a = 1\n", ts)
    assert tool.has_header(once)
    assert once.count("SPDX-License-Identifier") == 1


def test_shadcn_derived_files_keep_mit_identifier():
    tool = _load_spdx_tool()
    for rel in tool.THIRD_PARTY_HEADERS:
        p = REPO / rel
        if not p.exists():
            continue
        head = "\n".join(p.read_text().splitlines()[:6])
        assert "SPDX-License-Identifier: MIT" in head, rel
        assert "GPL-3.0-or-later" not in head, rel


# ── LEG-MIN-02: version + licence metadata consistency ──────────────────────

def _pyproject_field(name: str) -> str:
    text = (REPO / "halbert_core" / "pyproject.toml").read_text()
    m = re.search(rf'^{name}\s*=\s*"([^"]+)"', text, re.M)
    assert m, f"{name} not found in pyproject.toml"
    return m.group(1)


def test_package_version_matches_pyproject():
    try:
        from halbert_core import __version__
    except ImportError:
        from halbert_core.halbert_core import __version__

    assert __version__ == _pyproject_field("version")


def test_license_declared_consistently():
    assert _pyproject_field("license") == "GPL-3.0-or-later"

    fe = REPO / "halbert_core" / "halbert_core" / "dashboard" / "frontend"
    pkg = json.loads((fe / "package.json").read_text())
    assert pkg.get("license") == "GPL-3.0-or-later"

    cargo = (fe / "src-tauri" / "Cargo.toml").read_text()
    assert re.search(r'^license\s*=\s*"GPL-3.0-or-later"', cargo, re.M)
    assert '"you"' not in cargo, "placeholder author left in Cargo.toml"

    tauri = json.loads((fe / "src-tauri" / "tauri.conf.json").read_text())
    assert tauri["bundle"]["license"] == "GPL-3.0-or-later"
    assert tauri["bundle"]["copyright"] == EXPECTED_COPYRIGHT


def test_no_stale_legal_paths_in_tracked_docs():
    """LEG-MIN-04: the retired docs/Phase54 path and the .txt notices file are gone."""
    tracked = subprocess.run(
        ["git", "grep", "-l", "-E", r"Phase54_licensing-roundup|THIRD-PARTY-LICENSES\.txt", "--",
         "README.md", "data/manifest.json", "documentation/", "scripts/", "Halbert/"],
        cwd=REPO, capture_output=True, text=True,
    )
    hits = [h for h in tracked.stdout.split() if not h.endswith("LEGAL-AND-LICENSING-TODO.md")]
    assert not hits, f"stale legal cross-references in: {hits}"


# ── LEG-MOD-05: CLI legal notices ───────────────────────────────────────────

def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "Halbert/main.py", *argv], capture_output=True, text=True, cwd=REPO, timeout=120,
    )


def test_cli_version_shows_appropriate_legal_notices():
    r = _cli("--version")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Copyright (C) 2024-2026 Eric Bintner" in out
    assert "ABSOLUTELY NO WARRANTY" in out
    assert "free software" in out
    assert "halbert license" in out


def test_cli_info_shows_legal_notice():
    r = _cli("info")
    assert r.returncode == 0, r.stderr
    assert "ABSOLUTELY NO WARRANTY" in r.stdout
    assert "documentation/legal/" in r.stdout


def test_cli_license_variants():
    r = _cli("license")
    assert r.returncode == 0, r.stderr
    assert "GNU General Public License" in r.stdout
    assert "--third-party" in r.stdout

    r = _cli("license", "--full")
    assert r.returncode == 0, r.stderr
    assert "GNU GENERAL PUBLIC LICENSE" in r.stdout
    assert "Version 3, 29 June 2007" in r.stdout

    r = _cli("license", "--third-party")
    assert r.returncode == 0, r.stderr
    assert "Third-Party Licenses" in r.stdout
    assert "Arch Linux Wiki" in r.stdout


@pytest.mark.skipif(not (REPO / "scripts" / "check-dco.sh").exists(), reason="no DCO script")
def test_check_dco_script_detects_missing_signoff(tmp_path):
    """LEG-MAJ-06: the shared DCO checker used by CI rejects unsigned commits."""
    repo = tmp_path / "r"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    run = lambda *a: subprocess.run(a, cwd=repo, env=env, capture_output=True, text=True, check=True)
    run("git", "init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    run("git", "add", "a")
    run("git", "commit", "-q", "-m", "base")
    base = run("git", "rev-parse", "HEAD").stdout.strip()
    (repo / "a").write_text("2")
    run("git", "commit", "-q", "-am", "unsigned change")
    (repo / "a").write_text("3")
    run("git", "commit", "-q", "-s", "-am", "signed change")

    r = subprocess.run(["bash", str(REPO / "scripts" / "check-dco.sh"), f"{base}..HEAD"],
                       cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "MISSING" in r.stdout and "unsigned change" in r.stdout
    assert "ok" in r.stdout and "signed change" in r.stdout

    head_signed = run("git", "rev-parse", "HEAD~1").stdout.strip()
    r = subprocess.run(["bash", str(REPO / "scripts" / "check-dco.sh"), f"{head_signed}..HEAD"],
                       cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
