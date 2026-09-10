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
5. every degradation appends an honest notice, and logs the full set —
   name and location — at WARNING, because that is the only operator
   surface that actually exists (A13 bug 7).

The notice is the one thing the ladder never sacrifices: an honest block
over budget beats a silently dishonest one under it. Neither is the
guidance paragraph (A13-G3): a list nobody was told how to use is not a
smaller disclosure, it is a different defect.
"""

from __future__ import annotations

import functools
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

from .parser import DESCRIPTION_LIMIT, clamp_description
from .registry import SkillRegistry

logger = logging.getLogger("halbert.skills.catalog")

__all__ = [
    "CATALOG_BUDGET_CHARS",
    "MAX_RENDERED_DESCRIPTION_CHARS",
    "SKILLS_GUIDANCE",
    "CatalogEntry",
    "catalog_block_only",
    "descriptions_over_limit",
    "display_location",
    "render_available_skills",
]

#: The catalog's share of the skill section's budget, in characters. Bound
#: bodies keep their own composer caps (4k per skill / 8k per turn); this is
#: the catalog's, sized so the bundled ops set — whose `<location>` lines
#: carry the full install path — renders in full on a default host and the
#: ladder engages only when ingested ecosystem packs pile up.
CATALOG_BUDGET_CHARS = 4000

_CATALOG_OPEN = "<available_skills>"
_CATALOG_CLOSE = "</available_skills>"

#: The honest truncation notice (§2.3 rung 5).
#:
#: A13 bug 7: this used to read "full list at `halbert skills list`". There
#: is no such command — no CLI module, no dashboard route — so the one line
#: in the whole render whose entire job is honesty was the line that was not
#: true. The surface that does exist is the daemon log, and
#: ``_log_truncation`` writes the full set there with every location, which
#: is the thing a notice measured against a prompt budget can never carry.
_NOTICE_WHERE = "full set logged at startup"

#: A13-G3, the audit's "cheapest high-leverage" row. Track B is progressive
#: disclosure: the catalog names skills and the model reads the one that
#: matches. Halbert shipped the list with no instruction at all, so the
#: mechanism worked only if the model already guessed the convention. The
#: origin states it above the block in four lines (`system-prompt.ts`); this
#: is those four lines in Halbert's vocabulary — ``read_file`` is the read
#: tool the ``<location>`` contract depends on.
#:
#: It sits OUTSIDE ``<available_skills>``, where the origin puts it, so the
#: element itself stays byte-identical to the ecosystem shape and an
#: ingested pack still renders unchanged.
SKILLS_GUIDANCE = (
    "## Skills\n"
    "Scan <available_skills> before answering. One clear match: read its "
    "exact <location> with read_file and follow what it says. Several "
    "matches: take the most specific. None: read none — an unrelated "
    "runbook is worse than no runbook.\n"
    "At most one skill read up front. Never invent a path: read only a "
    "<location> printed in the block."
)

#: A13-G4. The parse ceiling (4096) is a DoS bound; the ladder's cap only
#: engages once the block is already over budget. Between them sat rung 0,
#: where a description renders in full because the total happens to fit —
#: so one ingested pack entry with a 4000-character description became the
#: catalog, and the skills that actually run this machine were pushed off
#: it. This is one entry's share of a shared budget.
#:
#: Not ``DESCRIPTION_LIMIT``: 60 is the create-time bar for skills authored
#: here, and clamping to it would silently truncate founder-authored copy in
#: the prompt. That set is FD-20's to trim, in words, not this ceiling's to
#: cut mid-sentence. 200 is above every description Halbert ships and eight
#: of them still fit the budget with room to spare.
MAX_RENDERED_DESCRIPTION_CHARS = 200


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
    # A13-G4: ``cap is None`` is rung 0, "no ladder needed" -- which used
    # to mean "no bound at all". The render ceiling applies there too; it
    # is not a rung, it is the floor under every rung.
    effective = (MAX_RENDERED_DESCRIPTION_CHARS if cap is None
                 else min(cap, MAX_RENDERED_DESCRIPTION_CHARS))
    if effective <= 0:
        return ""
    if len(entry.description) <= effective:
        return _xml_escape(entry.description)
    return _xml_escape(clamp_description(entry.description, limit=effective))


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

    Returns ``(text, truncated)``. The flag is RETURNED rather than read
    back out of the text, because asking a rendered block whether it says
    "truncated" is this module's own anti-pattern — and it is wrong on top
    of that: a skill installed under a path containing the word answers
    yes.
    """
    total = len(entries)
    max_desc = max((len(e.description) for e in entries), default=0)
    full = _block(entries, cap=None)
    if len(full) <= budget:
        return full, False

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
    return best, True


def _log_truncation(entries: Tuple[CatalogEntry, ...], listed: int) -> None:
    """The operator surface rung 5 promised (A13 bug 7).

    The notice inside the block is measured against the prompt budget, so
    it can only say *that* the catalog was cut. This says what was cut and
    where every skill lives -- once per snapshot, because the render it
    rides on is memoized.
    """
    logger.warning(
        "skills catalog truncated to %d of %d entries for the prompt "
        "budget; full set: %s",
        listed, len(entries),
        "; ".join(f"{e.name} ({e.location})" for e in entries),
    )


def catalog_block_only(rendered: str) -> str:
    """The ``<available_skills>`` element out of a rendered catalog.

    For readers that want the ecosystem-shaped element without Halbert's
    own guidance paragraph above it -- the ingest contract, and the tests
    that pin it. Returns "" when there is no block.

    Anchored on a LINE that is the open tag, not on the first occurrence
    of the string: the guidance names ``<available_skills>`` in its own
    first sentence, which is the point of it.
    """
    lines = rendered.splitlines()
    for i, line in enumerate(lines):
        if line == _CATALOG_OPEN:
            return "\n".join(lines[i:])
    return ""


def descriptions_over_limit(registry: SkillRegistry):
    """``[(name, length)]`` for skills whose description exceeds the
    create-time limit -- the FD-20 sweep as a lint (A13 bug 8).

    Reported, never rewritten: the bundled descriptions are founder copy,
    and FD-20's default is that the executor proposes trims and the founder
    approves the words. What this buys is that the set can only shrink --
    a new over-limit description is a test failure, not a discovery six
    months later.
    """
    return sorted(
        (skill.name, len(skill.description or ""))
        for skill in registry.all()
        if len(skill.description or "") > DESCRIPTION_LIMIT
    )


@functools.lru_cache(maxsize=128)
def _render_memoized(version: int, persona: Optional[str], budget: int,
                     protected: frozenset,
                     entries: Tuple[CatalogEntry, ...]) -> str:
    # A13-G3: the guidance is paid for out of the budget, not bolted on
    # after the ladder decided it had fitted -- that is how a budget stops
    # meaning anything. It is never cut, for the identity floor's reason
    # one step out: a catalog nobody was told how to use is not a smaller
    # disclosure, it is the defect this row is about.
    head = SKILLS_GUIDANCE + "\n"
    block, truncated = _render_ladder(entries, max(0, budget - len(head)))
    if truncated:
        _log_truncation(entries, block.count("<skill>"))
    return head + block


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