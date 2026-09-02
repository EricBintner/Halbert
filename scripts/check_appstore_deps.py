#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Assert no copyleft third-party dependency reaches the Mac App Store binary.

LEG-CRIT-03 step 2.

Halbert Core is GPL-3.0. To ship through the Mac App Store the project grants a
GPLv3 §7 exception permitting conveyance under Apple's terms notwithstanding
§6 and §10. That exception is the copyright holder's to grant — for Halbert's
own code. It cannot be granted over someone else's GPL library. So one
statically-linked GPL dependency in the App Store target is an infringement
that no amount of Halbert-side licensing fixes.

This script reads the declared dependencies of all three toolchains, resolves
each against `config/dependency-licenses.yml`, and fails on:

  * strong copyleft (GPL / AGPL / GFDL / SSPL)
  * weak copyleft (LGPL / MPL / EPL / CDDL) unless the entry is marked
    `dynamic_only: true`, or is excluded from this platform by a marker
  * any dependency with no entry at all — an unclassified licence is a
    blocker, not a default-allow

Build-time-only dependencies (`build_only: true`) are reported but not failed:
they never reach the shipped bundle.

It reads *declared* manifests, not an installed environment, so it runs
anywhere and in CI. That is a deliberate trade-off: it catches a copyleft
dependency being added to a manifest, which is how they actually arrive.

Usage:
    python scripts/check_appstore_deps.py [--target macos-app-store] [--json]

Exit codes:
    0  clean
    1  a dependency is incompatible, or unclassified
    2  usage / configuration error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "halbert_core" / "pyproject.toml"
CARGO_TOML = REPO_ROOT / "halbert_core" / "halbert_core" / "dashboard" / "frontend" / "src-tauri" / "Cargo.toml"
PACKAGE_JSON = REPO_ROOT / "halbert_core" / "halbert_core" / "dashboard" / "frontend" / "package.json"
REGISTER = REPO_ROOT / "config" / "dependency-licenses.yml"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
NC = "\033[0m"


def _c(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{NC}" if enabled else text


# --------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------
# tomllib landed in 3.11 and the project supports 3.10, so fall back to a small
# purpose-built parser for the two TOML shapes we actually own.

def _parse_requirement(spec: str) -> Tuple[str, str]:
    """`"chromadb>=0.5; python_version >= '3.10'"` -> ("chromadb", marker)."""
    spec = spec.strip()
    # Strip one matched pair of outer quotes only — stripping both kinds would
    # eat the closing quote of a marker like `platform_system == 'Linux'`.
    for quote in ('"', "'"):
        if len(spec) >= 2 and spec.startswith(quote) and spec.endswith(quote):
            spec = spec[1:-1]
            break
    marker = ""
    if ";" in spec:
        spec, marker = spec.split(";", 1)
    name = re.split(r"[<>=!~\[\s]", spec.strip(), 1)[0]
    return name.strip().lower(), marker.strip()


def _project_name(text: str) -> str:
    """Read `[project]`'s own `name = "..."`.

    Needed so self-referential extras — `light = ["halbert-core[dashboard]"]`,
    `full = ["halbert-core[rag-legacy,dashboard,cloud-apis,vision]"]` — can be
    filtered out. Those are this project re-including its OWN other extras
    (a convenience alias, `pip install halbert-core[light]`), not a dependency
    on anything outside the project; treating "halbert-core" as a third-party
    package with no licence-register entry was blocking every App Store check.
    """
    match = re.search(r'^\[project\]\s*$.*?^name\s*=\s*"([^"]+)"', text, re.S | re.M)
    return match.group(1) if match else ""


def _is_self_reference(name: str, project_name: str) -> bool:
    return bool(project_name) and name.lower() == project_name.lower()


def parse_pyproject(path: Path) -> List[Dict[str, Any]]:
    """Extract dependencies from `dependencies` and `optional-dependencies`."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: List[Dict[str, Any]] = []
    project_name = _project_name(text)

    try:
        import tomllib  # type: ignore[import-not-found]

        data = tomllib.loads(text)
        project = data.get("project", {})
        for spec in project.get("dependencies", []) or []:
            name, marker = _parse_requirement(spec)
            if _is_self_reference(name, project_name):
                continue
            out.append({"name": name, "marker": marker, "extra": ""})
        for extra, specs in (project.get("optional-dependencies", {}) or {}).items():
            for spec in specs or []:
                name, marker = _parse_requirement(spec)
                if _is_self_reference(name, project_name):
                    continue
                out.append({"name": name, "marker": marker, "extra": extra})
        return out
    except ImportError:
        pass

    # Fallback for Python 3.10: pull the quoted requirement strings out of each
    # array body. Matching quoted strings rather than whole lines keeps trailing
    # `# comments` out of the package name.
    def specs_in(body: str) -> List[str]:
        stripped = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("#")
        )
        return re.findall(r'"([^"]+)"', stripped)

    deps_match = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    if deps_match:
        for spec in specs_in(deps_match.group(1)):
            name, marker = _parse_requirement(spec)
            if name and not _is_self_reference(name, project_name):
                out.append({"name": name, "marker": marker, "extra": ""})

    opt = re.search(r"^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)", text, re.S | re.M)
    if opt:
        for extra_match in re.finditer(r"^([A-Za-z0-9_-]+)\s*=\s*\[(.*?)^\]", opt.group(1), re.S | re.M):
            extra = extra_match.group(1)
            for spec in specs_in(extra_match.group(2)):
                name, marker = _parse_requirement(spec)
                if name and not _is_self_reference(name, project_name):
                    out.append({"name": name, "marker": marker, "extra": extra})
    return out


def parse_cargo(path: Path) -> List[Dict[str, Any]]:
    """Extract crate names from [dependencies] and [build-dependencies]."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: List[Dict[str, Any]] = []
    for section, build_only in (("dependencies", False), ("build-dependencies", True)):
        match = re.search(rf"^\[{section}\](.*?)(?=^\[|\Z)", text, re.S | re.M)
        if not match:
            continue
        for line in match.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("=", 1)[0].strip()
            if name:
                out.append({"name": name, "marker": "", "extra": "build" if build_only else ""})
    return out


def parse_package_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[Dict[str, Any]] = []
    for name in (data.get("dependencies") or {}):
        out.append({"name": name, "marker": "", "extra": ""})
    for name in (data.get("devDependencies") or {}):
        out.append({"name": name, "marker": "", "extra": "dev"})
    return out


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

def classify(spdx: str, classes: Dict[str, List[str]]) -> str:
    """Return 'strong', 'weak' or 'permissive' for a (possibly dual) licence.

    A dual licence such as `MIT OR Apache-2.0` is permissive: the recipient may
    take the permissive half, which is exactly what we do.
    """
    options = [part.strip() for part in re.split(r"\bOR\b", spdx)] if spdx else []
    if not options:
        return "unknown"
    strong = set(classes.get("strong", []))
    weak = set(classes.get("weak", []))
    verdicts = []
    for option in options:
        if option in strong:
            verdicts.append("strong")
        elif option in weak:
            verdicts.append("weak")
        else:
            verdicts.append("permissive")
    # We can choose the least restrictive of a dual licence.
    for level in ("permissive", "weak", "strong"):
        if level in verdicts:
            return level
    return "unknown"


def marker_excludes_macos(marker: str) -> bool:
    """Does this environment marker keep the package off macOS?"""
    if not marker:
        return False
    normalised = marker.replace('"', "'").replace(" ", "")
    return "platform_system=='Linux'" in normalised or "sys_platform=='linux'" in normalised


def check(
    ecosystem: str,
    deps: List[Dict[str, Any]],
    register: Dict[str, Any],
    classes: Dict[str, List[str]],
    colour: bool,
) -> Tuple[List[str], List[str], List[str]]:
    """Return (failures, warnings, ok_lines) for one ecosystem."""
    entries = register.get(ecosystem, {}) or {}
    failures: List[str] = []
    warnings: List[str] = []
    ok: List[str] = []
    seen = set()

    for dep in deps:
        name = dep["name"]
        if name in seen:
            continue
        seen.add(name)

        entry = entries.get(name)
        if entry is None:
            # npm/python names are case-sensitive in the register but not always
            # in manifests; try a case-insensitive match before giving up.
            entry = next(
                (v for k, v in entries.items() if k.lower() == name.lower()),
                None,
            )
        if entry is None:
            failures.append(
                f"{ecosystem}:{name} has no entry in config/dependency-licenses.yml — "
                f"classify its licence before shipping"
            )
            continue

        spdx = entry.get("spdx", "")
        level = classify(spdx, classes)
        build_only = bool(entry.get("build_only")) or dep.get("extra") in ("dev", "build")
        platforms = entry.get("platforms") or []

        if level == "permissive" or spdx.startswith("LicenseRef-Halbert"):
            ok.append(f"{ecosystem}:{name} {spdx}")
            continue

        if build_only:
            warnings.append(
                f"{ecosystem}:{name} is {spdx} ({level} copyleft) but is build-time only "
                f"— not shipped in the bundle"
            )
            continue

        if platforms and "darwin" not in platforms and "macos" not in platforms:
            if marker_excludes_macos(dep.get("marker", "")):
                warnings.append(
                    f"{ecosystem}:{name} is {spdx} ({level} copyleft) but is excluded from "
                    f"macOS by the marker `{dep['marker']}` — verified"
                )
                continue
            failures.append(
                f"{ecosystem}:{name} is {spdx} ({level} copyleft) and the register says it is "
                f"{platforms}-only, but its manifest entry has no platform marker keeping it "
                f"off macOS. Add `; platform_system == 'Linux'`."
            )
            continue

        if level == "weak" and entry.get("dynamic_only"):
            warnings.append(
                f"{ecosystem}:{name} is {spdx} (weak copyleft), dynamically linked — allowed, "
                f"but the relink obligation still applies"
            )
            continue

        failures.append(
            f"{ecosystem}:{name} is {spdx} ({level} copyleft) and would be linked into the "
            f"App Store binary. The GPLv3 §7 exception covers Halbert's code, not this "
            f"library. Remove it, replace it, or drop the App Store channel."
        )

    return failures, warnings, ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--target",
        default="macos-app-store",
        help="Distribution target being checked (informational; policy is App Store strictness)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colour")
    parser.add_argument("--quiet", action="store_true", help="Only report problems")
    args = parser.parse_args()

    colour = sys.stdout.isatty() and not args.no_color

    if not REGISTER.exists():
        print(f"error: dependency register not found: {REGISTER}", file=sys.stderr)
        return 2

    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8")) or {}
    classes = register.get("copyleft_classes", {}) or {}

    ecosystems = {
        "python": parse_pyproject(PYPROJECT),
        "rust": parse_cargo(CARGO_TOML),
        "npm": parse_package_json(PACKAGE_JSON),
    }

    all_failures: List[str] = []
    all_warnings: List[str] = []
    counts: Dict[str, int] = {}

    print(f"\n{_c('DEPENDENCY LICENCE CHECK', YELLOW, colour)} — target: {args.target}")

    for ecosystem, deps in ecosystems.items():
        if not deps:
            print(f"  {_c('!', YELLOW, colour)} {ecosystem}: no manifest found — skipped")
            continue
        failures, warnings, ok = check(ecosystem, deps, register, classes, colour)
        counts[ecosystem] = len(deps)
        all_failures.extend(failures)
        all_warnings.extend(warnings)
        status = _c("✓", GREEN, colour) if not failures else _c("✗", RED, colour)
        print(f"  {status} {ecosystem}: {len(ok)} permissive, {len(warnings)} noted, {len(failures)} blocking")
        if not args.quiet:
            for warning in warnings:
                print(f"      {_c('·', DIM, colour)} {warning}")

    if all_failures:
        print(f"\n{_c('BLOCKING', RED, colour)}")
        for failure in all_failures:
            print(f"  ✗ {failure}")
    else:
        print(f"\n{_c('PASS', GREEN, colour)} no copyleft dependency reaches the "
              f"{args.target} binary")

    if args.json:
        print(json.dumps(
            {
                "target": args.target,
                "counts": counts,
                "failures": all_failures,
                "warnings": all_warnings,
            },
            indent=2,
        ))

    return 1 if all_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
