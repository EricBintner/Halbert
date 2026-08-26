#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Verify the Halbert design tokens against WCAG 2.1 contrast requirements.

This is the executable form of the Accessibility Gate in
``documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`` §7. It parses
``shared-tokens/tokens.css`` — the single source of truth — resolves every
``var()`` chain to a concrete sRGB value, and checks each foreground token
against the surfaces it is *licensed* to be read on, in both themes.

The licence table below is the point. Contrast is a property of a pair, not
of a colour, so a token is only ever checked against the grounds it is
allowed to appear on:

* ``surface-muted`` is a disabled/inactive ground. WCAG 1.4.3 exempts
  disabled controls, so it is deliberately excluded from the text checks.
* ``--color-ink-ghost`` and ``--color-accent`` are held to the 3:1 non-text
  floor of WCAG 1.4.11, not the 4.5:1 text floor. They are not text colours.

Usage::

    python3 scripts/check_contrast.py            # check, exit 1 on failure
    python3 scripts/check_contrast.py --verbose  # print every pair
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = REPO_ROOT / "shared-tokens" / "tokens.css"

# WCAG 2.1 thresholds.
AA_TEXT = 4.5       # 1.4.3 — normal-size text
AAA_TEXT = 7.0      # 1.4.6 — enhanced
AA_LARGE = 3.0      # 1.4.3 — >=24px, or >=18.66px bold
AA_NON_TEXT = 3.0   # 1.4.11 — UI components and graphical objects


# --------------------------------------------------------------------------
# Colour maths
# --------------------------------------------------------------------------

def _srgb_to_linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def composite(fg: tuple[int, int, int, float], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Flatten a translucent foreground onto an opaque background."""
    r, g, b, a = fg
    return tuple(round(c * a + d * (1 - a)) for c, d in zip((r, g, b), bg))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Token parsing
# --------------------------------------------------------------------------

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGBA = re.compile(r"^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+))?\s*\)$")
_VAR = re.compile(r"^var\(\s*(--[\w-]+)\s*\)$")
_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def parse_blocks(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (light, dark) token maps of raw declaration strings.

    Light is ``:root``; dark is the explicit ``[data-theme="dark"]`` block
    layered over light. The ``prefers-color-scheme`` block is a duplicate of
    the explicit one and is checked for drift separately.
    """
    # Strip comments so a commented-out declaration is never parsed.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        blocks.append((match.group(1).strip(), match.group(2)))

    light: dict[str, str] = {}
    dark_overrides: dict[str, str] = {}
    media_overrides: dict[str, str] = {}

    for selector, body in blocks:
        decls = dict(_DECL.findall(body))
        if not decls:
            continue
        if selector.startswith(":root") and "data-theme" not in selector and "prefers" not in selector:
            if "dark" in selector:
                dark_overrides.update(decls)
            else:
                light.update(decls)
        elif 'data-theme="dark"' in selector or selector.endswith(".dark"):
            dark_overrides.update(decls)
        elif ":not(" in selector:
            media_overrides.update(decls)

    dark = dict(light)
    dark.update(dark_overrides)

    # Drift guard: the media-query block must match the explicit dark block.
    drift = [
        key for key, value in media_overrides.items()
        if key in dark_overrides and dark_overrides[key].strip() != value.strip()
    ]
    if drift:
        print(f"  ! prefers-color-scheme block has drifted from [data-theme=dark]: {', '.join(drift)}")

    return light, dark


def resolve(name: str, tokens: dict[str, str], _depth: int = 0):
    """Resolve a token to (r, g, b) or (r, g, b, alpha), following var() chains."""
    if _depth > 16:
        raise ValueError(f"circular token reference at {name}")
    raw = tokens.get(name)
    if raw is None:
        raise KeyError(f"undefined token {name}")
    raw = raw.strip()

    var_match = _VAR.match(raw)
    if var_match:
        return resolve(var_match.group(1), tokens, _depth + 1)

    if _HEX.match(raw):
        h = raw.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    rgba_match = _RGBA.match(raw)
    if rgba_match:
        r, g, b, a = rgba_match.groups()
        channels = (round(float(r)), round(float(g)), round(float(b)))
        return channels if a is None else (*channels, float(a))

    raise ValueError(f"cannot resolve {name} = {raw!r}")


def flatten(name: str, tokens: dict[str, str], ground: str = "--color-canvas"):
    """Resolve a token to an opaque colour, compositing over `ground` if needed."""
    value = resolve(name, tokens)
    if len(value) == 4:
        return composite(value, flatten(ground, tokens) if ground != name else (255, 255, 255))
    return value


# --------------------------------------------------------------------------
# The surface licence
# --------------------------------------------------------------------------

# Ink is the universal text colour: it lands on every ground, trays included.
TEXT_SURFACES = ("--color-canvas", "--color-surface", "--color-surface-subtle")

# Chromatic tokens (the stroke and the status tones) are accents, not body
# text. They appear on the two primary grounds and on their own tint — a
# vermilion caption is never set on a recessed tray — so that is the licence
# they are held to. Their own tints are checked separately in TINT_CHECKS.
ACCENT_SURFACES = ("--color-canvas", "--color-surface")

# (token, [surfaces], floor, label)
CHECKS: list[tuple[str, tuple[str, ...], float, str]] = [
    # Ink ramp — read on every text surface.
    ("--color-ink",           TEXT_SURFACES, AAA_TEXT,    "body & headings (AAA)"),
    ("--color-ink-secondary", TEXT_SURFACES, AAA_TEXT,    "prose & metadata (AAA)"),
    ("--color-ink-tertiary",  TEXT_SURFACES, AA_TEXT,     "captions & labels (AA)"),
    ("--color-ink-ghost",     TEXT_SURFACES, AA_NON_TEXT, "disabled/decorative (non-text 3:1)"),

    # The stroke.
    ("--color-accent",        ACCENT_SURFACES, AA_NON_TEXT, "identity stroke (non-text 3:1)"),
    ("--color-accent-strong", ACCENT_SURFACES, AA_TEXT,     "accent text & fills (AA)"),
    ("--color-accent-hover",  ACCENT_SURFACES, AA_TEXT,     "hover (AA)"),
    ("--color-accent-active", ACCENT_SURFACES, AA_TEXT,     "pressed (AA)"),

    # Status tones on the neutral grounds they appear on.
    ("--color-status-nominal",   ACCENT_SURFACES, AA_TEXT, "nominal (AA)"),
    ("--color-status-warning",   ACCENT_SURFACES, AA_TEXT, "warning (AA)"),
    ("--color-status-critical",  ACCENT_SURFACES, AA_TEXT, "critical (AA)"),
    ("--color-status-telemetry", ACCENT_SURFACES, AA_TEXT, "telemetry (AA)"),

    # The focus ring is the one boundary WCAG 1.4.11 / 2.4.13 genuinely
    # requires to stand alone. Decorative hairlines are NOT checked: a plate
    # is identified by its fill and shadow as well as its border, and a 3:1
    # hairline would read as a heavy rule and break the instrument aesthetic.
    ("--color-focus-ring", TEXT_SURFACES, AA_NON_TEXT, "focus ring (non-text 3:1)"),
]

# Foreground/background pairs that must hold on their own tinted ground.
TINT_CHECKS = [
    ("--color-status-nominal",   "--color-status-nominal-bg",   AA_TEXT),
    ("--color-status-warning",   "--color-status-warning-bg",   AA_TEXT),
    ("--color-status-critical",  "--color-status-critical-bg",  AA_TEXT),
    ("--color-status-telemetry", "--color-status-telemetry-bg", AA_TEXT),
    ("--color-accent-strong",    "--color-accent-tint",         AA_TEXT),
]

# Text sitting on a filled accent button.
FILL_CHECKS = [
    ("--color-ink-on-accent", "--color-accent-strong", AA_TEXT),
    ("--color-ink-on-accent", "--color-accent-hover",  AA_TEXT),
    ("--color-ink-on-accent", "--color-accent-active", AA_TEXT),
]

def run_theme(theme: str, tokens: dict[str, str], verbose: bool) -> list[str]:
    failures: list[str] = []
    print(f"\n  {theme.upper()}")

    def check(fg_name: str, bg_name: str, floor: float, label: str) -> None:
        fg = flatten(fg_name, tokens, bg_name)
        bg = flatten(bg_name, tokens)
        ratio = contrast_ratio(fg, bg)
        ok = ratio >= floor
        if not ok:
            failures.append(
                f"{theme}: {fg_name} on {bg_name} = {ratio:.2f}:1 (needs {floor}:1) — {label}"
            )
        if verbose or not ok:
            mark = "ok " if ok else "FAIL"
            short_fg = fg_name.replace("--color-", "")
            short_bg = bg_name.replace("--color-", "")
            print(f"    [{mark}] {short_fg:22s} on {short_bg:18s} {ratio:6.2f}:1  (>= {floor})")

    for token, surfaces, floor, label in CHECKS:
        for surface in surfaces:
            check(token, surface, floor, label)
    for fg, bg, floor in TINT_CHECKS:
        check(fg, bg, floor, "on its own tint")
    for fg, bg, floor in FILL_CHECKS:
        check(fg, bg, floor, "text on an accent fill")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true", help="print every pair, not just failures")
    args = parser.parse_args()

    if not TOKENS_CSS.exists():
        print(f"error: {TOKENS_CSS} not found", file=sys.stderr)
        return 2

    light, dark = parse_blocks(TOKENS_CSS.read_text(encoding="utf-8"))
    print(f"Halbert accessibility gate — {TOKENS_CSS.relative_to(REPO_ROOT)}")
    print(f"  parsed {len(light)} light tokens, {len(dark)} dark tokens")

    failures = run_theme("light", light, args.verbose)
    failures += run_theme("dark", dark, args.verbose)

    print()
    if failures:
        print(f"FAILED — {len(failures)} pair(s) below their floor:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASSED — every licensed pair clears its WCAG floor in both themes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
