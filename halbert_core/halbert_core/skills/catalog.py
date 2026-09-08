# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
The `<available_skills>` catalog — Track B, progressive disclosure (SK-2).

Design DESIGN-SKILLS-SYSTEM-2026-09-07 §2.1-§2.3. Every skill that is not a
lens appears in one catalog block shaped exactly as the ecosystem formatter
writes it, so a pack that works in Claude Code ingests unchanged and the
model consults a skill by reading its `<location>` through the existing
read_file tool — that read is the telemetry receipt (§6, seam 1).

Two rules shape the render:

* **Structured snapshots, never re-parsed.** The block renders from the
  registry's parsed `Skill` objects, and the render is memoized on the
  registry's monotonic `snapshot_version` (plus persona and budget), so a
  skill edit invalidates exactly the renders that must die. Nothing here
  ever greps a rendered prompt for its own facts — that is the anti-pattern
  both reviews flag (OpenClaw §7 / anti-pattern #2).
* **Characters, not tokens.** This runs before any tokeniser is in scope,
  and a character bound that is roughly right beats a token bound that
  needs a model handle to compute (the composer's own rule).

The truncation ladder, in the design's order:

1. **drop descriptions** — every entry becomes name+location only;
2. **binary-search the skill count** — lowest-priority Track-B entries are
   cut first, matched (Track-A) entries last, so the cut is explainable;
3. **binary-search the description length** — the surviving headroom buys
   back as much description as fits, trimmed with the visible `…` marker;
4. **the identity floor** — names and locations are never cut. A skill the
   model cannot discover does not exist; a skill whose description got
   trimmed still does;
5. every degradation appends an honest notice telling the operator how to
   audit (`halbert skills list`, the SK-4 operator surface).

The notice is the one thing the ladder never sacrifices: an honest block
over budget beats a silently dishonest one under it.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

from .parser import Skill, clamp_description
from .registry import SkillRegistry

__all__ = [
    "CATALOG_BUDGET_CHARS",
    "CatalogEntry",
    "display_location",
    "render_available_skills",
]

#: The catalog's share of the skill section's budget, in characters. Bound
#: bodies keep their own composer caps (4k per skill / 8k per turn); this is
#: the catalog's, sized so the nine bundled skills — whose `<location>`
#: lines carry the full install path — render in full on a default host and
#: the ladder engages only when ingested ecosystem packs pile up.
CATALOG_BUDGET_CHARS = 4000

_CATALOG_OPEN = "<available_skills>"
_CATALOG_CLOSE = "</available_skills>"

#: The honest truncation notice (§2.3 rung 5). `halbert skills list --all`
#: is the SK-4 operator surface; the notice names it regardless, because
#: the notice is for the operator auditing why the model saw less.
_NOTICE_WHERE = "full list at `halbert skills list`"


@dataclass(frozen=True)
class CatalogEntry:
    """One catalog row, already reduced to render data.

    `protected` marks a skill the matcher bound this turn (Track A): its
    body is already in the prompt, so its catalog entry is the last thing
    the count cut takes — an entry the model was just told about is not
    the one to drop first.
    """

    name: str
    description: str
    location: str
    priority_rank: int
    protected: bool = False


def display_location(path: Path) -> str:
    """The `<location>` line: the real path, home collapsed to `~`.

    read_file expandusers its argument, so the collapsed form still
    resolves — and the catalog stays readable for a human auditing it.
    """
    try:
        text = str(path)
        home = str(Path.home())
        if home and text.startswith(home + os.sep):
            return "~" + text[len(home):]
        return text
    except Exception:  # pragma: no cover - Path.home is cheap but not guaranteed
        return str(path)


def _entries(registry: SkillRegistry,
              protected: Iterable[str] = ()) -> Tuple[CatalogEntry, ...]:
    """The catalog snapshot, highest priority first, lenses and
    non-trusted states excluded.

    A lens is voice only and appears in no catalog (CD-2); a draft is a
    proposal visible only to the custodian persona's catalog (§5.5) and an
    archive is no catalog's to list — the machine persona here sees
    neither. Persona-dimensioned root sets are SK-3's, not this packet's.
    """
    guarded = {str(name) for name in protected}
    out = []
    for skill in registry.all():
        if skill.kind == "lens":
            continue
        if skill.state != "trusted":
            continue
        if skill.source_path is None:
            # A skill with no file cannot be consulted: it has no location,
            # and the catalog's whole contract is "read this file". Its
            # body still binds through Track A.
            continue
        out.append(CatalogEntry(
            name=skill.name,
            description=skill.description or "",
            location=display_location(skill.source_path),
            priority_rank=skill.priority_rank,
            protected=skill.name in guarded,
        ))
    return tuple(sorted(out, key=lambda e: (-e.priority_rank, e.name)))


def _description_text(entry: CatalogEntry, cap: Optional[int]) -> str:
    """The description at *cap* chars (None = whole); trimmed, never
    silently cut. cap 0 is the ladder's "descriptions omitted" rung: the
    empty element, not `clamp_description`'s negative-slice text."""
    if cap is None:
        return _xml_escape(entry.description)
    if cap <= 0:
        return ""
    if len(entry.description) <= cap:
        return _xml_escape(entry.description)
    return _xml_escape(clamp_description(entry.description, limit=cap))


def _block(entries: Tuple[CatalogEntry, ...], cap: Optional[int],
           notice: str = "") -> str:
    lines = [_CATALOG_OPEN]
    for entry in entries:
        lines.append("<skill>")
        lines.append(f"<name>{_xml_escape(entry.name)}</name>")
        lines.append(
            f"<description>{_description_text(entry, cap)}</description>"
        )
        lines.append(f"<location>{_xml_escape(entry.location)}</location>")
        lines.append("</skill>")
    if notice:
        lines.append(f"<!-- {notice} -->")
    lines.append(_CATALOG_CLOSE)
    return "\n".join(lines)


def _cut_order(entries: Tuple[CatalogEntry, ...]) -> Tuple[CatalogEntry, ...]:
    """The order entries leave in: Track-B before Track-A, lowest priority
    first, name last so ties resolve deterministically."""
    return tuple(sorted(
        entries,
        key=lambda e: (e.protected, e.priority_rank, e.name),
    ))


def _kept(entries, cut_order, count):
    """The first *count* entries to survive the cut, display order."""
    survivors = set(cut_order[len(entries) - count:]) if count else set()
    return tuple(e for e in entries if e in survivors)


def _notice(total: int, kept: int, cap: Optional[int],
            max_desc: int) -> str:
    """The honest truncation notice for a degradation, or "" for none.

    Every part names what actually happened: the count cut (rung 2), the
    description state (rungs 1 and 3), and the operator surface that holds
    the full list (rung 5). The notice is part of the block, so it is part
    of what the budget measures.
    """
    parts = []
    if kept < total:
        parts.append(f"catalog truncated from {total} to {kept} skills")
    else:
        parts.append("catalog truncated")
    if cap == 0:
        parts.append("descriptions omitted")
    elif cap is not None and cap < max_desc:
        parts.append(f"descriptions trimmed to {cap} chars")
    parts.append(_NOTICE_WHERE)
    return "; ".join(parts)


def _render_ladder(entries, budget):
    """Climb the §2.3 ladder: the largest honest render under *budget*.

    Rung 0 is the full block; over budget the ladder drops descriptions
    (rung 1), binary-searches the count the bare block can hold with the
    notice measured in (rung 2), then buys descriptions back into the
    surviving headroom (rung 3). Every candidate is measured with its own
    real notice text, so what is returned is what fits — the notice is
    never an unmeasured extra. Names and locations are never cut anywhere
    on the ladder (rung 4): cuts touch descriptions and entry count only.
    """
    total = len(entries)
    max_desc = max((len(e.description) for e in entries), default=0)
    full = _block(entries, cap=None)
    if len(full) <= budget:
        return full

    cut_order = _cut_order(entries)

    def bare_text(count: int) -> str:
        kept = _kept(entries, cut_order, count)
        return _block(kept, cap=0, notice=_notice(total, count, 0, max_desc))

    # Rung 2: the largest count whose names+locations block fits.
    lo, hi = 0, total
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(bare_text(mid)) <= budget:
            lo = mid
        else:
            hi = mid - 1
    kept_count = lo
    kept = _kept(entries, cut_order, kept_count)

    # Rung 3: the largest uniform description cap that still fits. cap=0
    # (the bare block) is already known feasible — the search starts above
    # it and falls back to it when even one char of description does not.
    best = bare_text(kept_count)
    lo, hi = 1, max_desc
    while lo <= hi:
        mid = (lo + hi) // 2
        text = _block(kept, cap=mid,
                      notice=_notice(total, kept_count, mid, max_desc))
        if len(text) <= budget:
            best = text
            lo = mid + 1
        else:
            hi = mid - 1
    return best


@functools.lru_cache(maxsize=128)
def _render_memoized(version: int, persona: Optional[str], budget: int,
                     protected: frozenset,
                     entries: Tuple[CatalogEntry, ...]) -> str:
    return _render_ladder(entries, budget)


def render_available_skills(registry: SkillRegistry, *,
                            persona: Optional[str] = None,
                            budget: int = CATALOG_BUDGET_CHARS,
                            protected: Iterable[str] = ()) -> str:
    """The `<available_skills>` block for *registry*, or "" when empty.

    Memoized on `(snapshot_version, persona, budget, protected)` — the
    design's key (§2.2) plus the protected set, which the count cut reads
    (rung 2) and therefore the memo must distinguish. The version is
    process-unique, so a reload can never collide with a stale entry.

    `persona` is SK-3's dimension, threaded now so the memo key does not
    change shape when the root sets land.
    """
    entries = _entries(registry, protected)
    if not entries:
        return ""
    return _render_memoized(
        registry.snapshot_version, persona, int(budget),
        frozenset(protected), entries,
    )