#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vendor the Halbert brand typefaces into shared-tokens/fonts/.

Halbert is a local-first, "sovereign host" product. Fetching webfonts from the
Google Fonts CDN at runtime contradicts that posture — it phones home on every
cold load, and the desktop app has no network guarantee at all. This script
downloads the faces once, into the repo, so the shipped product serves its own
type.

Why vendored files rather than npm packages: there are no npm workspaces here
(no root package.json, nine independent lockfiles), and packages/design-system
is not consumed by node resolution. Adding @fontsource to three package.json
files would mean three node_modules copies and three lockfile entries that
drift. The repo already has a working cross-project sharing pattern — root
shared-tokens/ consumed by relative path — so the fonts use it too.

Two things this script refuses to get wrong:

* THE OPTICAL-SIZE AXIS. Fraunces is drawn differently at 14pt and 144pt. The
  obvious `@fontsource-variable/fraunces` import resolves to a build with NO
  opsz axis, frozen at the 14pt cut, which then gets scaled up to a 60px
  headline and looks wrong in a way nobody can name. We request the axis
  explicitly and then VERIFY it survived, because this failure is silent.
* THE FAMILY NAME. @fontsource declares 'Fraunces Variable'; tokens.css says
  'Fraunces'. A mismatch renders the fallback with no error anywhere.

Usage::

    python3 scripts/vendor_fonts.py            # download and write
    python3 scripts/vendor_fonts.py --verify   # check what is on disk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = REPO_ROOT / "shared-tokens" / "fonts"
FILE_DIR = FONT_DIR / "files"

# A modern desktop UA, so Google serves woff2 rather than an older format.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Only the subsets we can justify shipping. Halbert's own speech renders as
# prose in the sans face and machine output in the mono face, both of which can
# carry accented Latin, so latin-ext is included for all three. Cyrillic,
# Greek and Vietnamese are not: they would roughly double the payload for
# coverage nothing in the product produces today.
KEEP_SUBSETS = ("latin", "latin-ext")


class Family:
    def __init__(self, name: str, slug: str, query: str, ofl_url: str, expect_axes: tuple[str, ...]):
        self.name = name
        self.slug = slug
        self.query = query
        self.ofl_url = ofl_url
        self.expect_axes = expect_axes


FAMILIES = [
    Family(
        "Fraunces",
        "fraunces",
        # opsz FIRST, and as a range, or Google hands back a single pinned cut.
        "Fraunces:ital,opsz,wght@0,9..144,400..900;1,9..144,400..900",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/fraunces/OFL.txt",
        ("opsz", "wght"),
    ),
    Family(
        "Space Grotesk",
        "space-grotesk",
        # This family ships no italic cut at all; italic text will be a
        # browser-synthesised oblique. That is a real, if minor, fidelity loss.
        "Space+Grotesk:wght@400..700",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/OFL.txt",
        ("wght",),
    ),
    Family(
        "JetBrains Mono",
        "jetbrains-mono",
        "JetBrains+Mono:ital,wght@0,400..700;1,400..700",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/OFL.txt",
        ("wght",),
    ),
]

FACE_RE = re.compile(r"/\*\s*(?P<subset>[\w-]+)\s*\*/\s*@font-face\s*\{(?P<body>[^}]*)\}", re.S)
DECL_RE = re.compile(r"([\w-]+)\s*:\s*([^;]+);")


def fetch(url: str, as_text: bool = True):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data.decode("utf-8") if as_text else data


def axes_of(path: Path) -> dict[str, tuple[float, float]]:
    """Read the variable axes out of a woff2, so a frozen axis fails loudly."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return {}
    font = TTFont(str(path), lazy=True)
    if "fvar" not in font:
        return {}
    return {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes}


def family_name_of(path: Path) -> str | None:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    font = TTFont(str(path), lazy=True)
    for record in font["name"].names:
        if record.nameID == 16:  # typographic family
            return str(record)
    for record in font["name"].names:
        if record.nameID == 1:
            return str(record)
    return None


def vendor() -> int:
    FILE_DIR.mkdir(parents=True, exist_ok=True)
    css_blocks: list[str] = []
    manifest: dict = {"families": [], "subsets": list(KEEP_SUBSETS)}
    ofl_parts: list[str] = []
    problems: list[str] = []

    for family in FAMILIES:
        print(f"\n{family.name}")
        css = fetch(f"https://fonts.googleapis.com/css2?family={family.query}&display=swap")

        seen: dict[str, str] = {}
        faces = 0
        for match in FACE_RE.finditer(css):
            subset = match.group("subset")
            if subset not in KEEP_SUBSETS:
                continue
            decls = dict(DECL_RE.findall(match.group("body")))
            url_match = re.search(r"url\(([^)]+)\)", decls.get("src", ""))
            if not url_match:
                continue
            url = url_match.group(1).strip("'\"")

            style = decls.get("font-style", "normal").strip()
            weight = decls.get("font-weight", "400").strip()
            filename = f"{family.slug}-{subset}-{style}.woff2"
            target = FILE_DIR / filename

            blob = fetch(url, as_text=False)
            target.write_bytes(blob)
            digest = hashlib.sha256(blob).hexdigest()[:16]
            seen[filename] = digest
            faces += 1

            print(f"  {filename:44s} {len(blob)/1024:6.1f} KB  ({subset}, {style} {weight})")

            found = axes_of(target)
            if family.expect_axes and subset == "latin":
                missing = [a for a in family.expect_axes if a not in found]
                if missing:
                    problems.append(
                        f"{family.name} {style}: expected variable axes {missing} but the file has "
                        f"{sorted(found) or 'none'} — the axis was silently flattened"
                    )
                # The binary's internal name is NOT what CSS matches on: for a
                # URL-sourced face the @font-face `font-family` descriptor is
                # authoritative, and the name table is consulted only for
                # `local()` sources, which this file never emits. Google ships
                # one binary per family whose default instance may be a Light
                # cut, so e.g. Space Grotesk reports 'Space Grotesk Light'.
                # Worth printing, never worth refusing over.
                declared = family_name_of(target)
                if declared and declared != family.name:
                    print(f"  note: binary self-reports {declared!r}; served as "
                          f"{family.name!r} via the @font-face descriptor")
                print(f"  axes: { ', '.join(f'{k} {v[0]:g}..{v[1]:g}' for k, v in sorted(found.items())) or 'static'}")

            # font-display: swap everywhere. `block` would mean up to ~3s of
            # INVISIBLE text; on the mono face that is the entire telemetry
            # layer, every <pre>, and both terminal panes on a cold load.
            css_blocks.append(
                "@font-face {\n"
                f"  font-family: '{family.name}';\n"
                f"  font-style: {style};\n"
                f"  font-weight: {weight};\n"
                "  font-display: swap;\n"
                f"  src: url('./files/{filename}') format('woff2');\n"
                f"  unicode-range: {decls.get('unicode-range', '').strip()};\n"
                "}"
            )

        if faces == 0:
            problems.append(f"{family.name}: no faces matched subsets {KEEP_SUBSETS}")

        ofl = fetch(family.ofl_url)
        ofl_parts.append(f"{'=' * 78}\n{family.name}\n{family.ofl_url}\n{'=' * 78}\n\n{ofl.strip()}\n")
        manifest["families"].append({
            "family": family.name,
            "spdx": "OFL-1.1",
            "upstream_licence": family.ofl_url,
            "files": seen,
        })

    if problems:
        print("\nREFUSING TO WRITE — the vendored files are not what was asked for:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    header = (
        "/*\n"
        " * Halbert brand typefaces — self-hosted.\n"
        " * SPDX-License-Identifier: GPL-3.0-or-later\n"
        " * Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors\n"
        " *\n"
        " * GENERATED by scripts/vendor_fonts.py. Do not edit by hand.\n"
        " *\n"
        " * The .woff2 files in ./files/ are NOT under the project licence. They are\n"
        " * SIL Open Font License 1.1, and they are Modified Versions of their\n"
        " * upstream Original Versions: subset to Latin and built as WOFF2 by the\n"
        " * Google Fonts API. None of the three families declares a Reserved Font\n"
        " * Name, so they keep their original names. Full licence and the upstream\n"
        " * copyright notices: ./OFL-1.1.txt\n"
        " */\n\n"
    )
    (FONT_DIR / "fonts.css").write_text(header + "\n\n".join(css_blocks) + "\n", encoding="utf-8")
    (FONT_DIR / "OFL-1.1.txt").write_text(
        "The bundled typefaces are licensed under the SIL Open Font License 1.1.\n"
        "Each family's upstream licence file follows verbatim, including its\n"
        "copyright notice, as OFL-1.1 clause 2 requires.\n\n" + "\n".join(ofl_parts),
        encoding="utf-8",
    )
    (FONT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total = sum(f.stat().st_size for f in FILE_DIR.glob("*.woff2"))
    print(f"\nWrote {len(css_blocks)} faces, {total/1024:.0f} KB total, to {FONT_DIR.relative_to(REPO_ROOT)}")
    return 0


def verify() -> int:
    if not (FONT_DIR / "MANIFEST.json").exists():
        print("No MANIFEST.json — run without --verify first.", file=sys.stderr)
        return 2
    manifest = json.loads((FONT_DIR / "MANIFEST.json").read_text())
    bad = []
    for entry in manifest["families"]:
        for filename, digest in entry["files"].items():
            path = FILE_DIR / filename
            if not path.exists():
                bad.append(f"missing {filename}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            if actual != digest:
                bad.append(f"{filename}: sha {actual} != recorded {digest}")
    for required in ("fonts.css", "OFL-1.1.txt"):
        if not (FONT_DIR / required).exists():
            bad.append(f"missing {required}")
    if bad:
        print("FAILED:")
        for item in bad:
            print(f"  - {item}")
        return 1
    n = sum(len(e["files"]) for e in manifest["families"])
    print(f"OK: {n} font files match their recorded digests, licence and CSS present.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="check on-disk files against the manifest")
    args = parser.parse_args()
    return verify() if args.verify else vendor()


if __name__ == "__main__":
    sys.exit(main())
