#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Verify the Halbert research citation dictionary before anything renders it.

The dossier on halbert.computer shows academic citations beside a "how Halbert
relates" note. A hallucinated or misattributed bibliography entry is the most
damaging defect this surface can carry — it presents to the academic community
as measured fact. This script is the executable gate promised by
``.handoff/PLAN-MARKETING-V10-TECHNICAL-DOSSIER-AND-RESEARCH-CITATIONS-2026-09-15.md``
§3.1: structural validation plus the standing copy directives, so an
unidentifiable work cannot enter the dictionary and a banned phrase cannot
ship in its prose.

Checks (exit 1 on any failure):

* Schema — every citation carries the full field set with the right shapes:
  kebab-case ``id`` and ``stopId`` from the storyboard's 8 stop ids, ``year``
  in range, ``url`` https, ``type``/``category``/``applied`` from the enums.
* Identifiability — ``identifier`` is non-empty (arXiv id, RFC number, DOI,
  SPDX licence id, or official spec label) unless the entry is explicitly
  marked as having none. A citation a reader cannot find is a claim.
* Peer-review honesty — ``peerReviewed: true`` is only allowed for
  ``paper``/``survey``/``benchmark`` types. RFCs, specs, engineering reports
  and licences are never peer-reviewed.
* Shipped honesty — ``applied: shipped`` requires at least one
  ``halbert_core/`` file path in the prose (the shipped rule from the plan:
  shipped means code today, and the prose names the file).
* Copy directives (DECISIONS.md standing directives, binding on prose):
  no "sovereign" in any case; no unverified corpus counts ("14k" et al.).
* Cross-file joins — every ``stopId`` matches ``sites/marketing``'s
  storyboard; the reverse feature join is derived, not stored, so a stray
  ``relatedFeatureIds`` key on a citation is rejected (one join direction
  only — features carry ``citationIds``).

Usage::

    python3 scripts/check_research_citations.py            # check, exit 1 on failure
    python3 scripts/check_research_citations.py --verbose  # list every citation

The catalogue side (``sites/feature-reference/src/catalog.json``) is
checked when ``--catalog`` is given: every ``citationIds`` entry must exist
here, and no feature may carry ``relatedCitationIds`` (the mirrored, wrong
join direction).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CITATIONS_JSON = REPO_ROOT / "sites" / "shared" / "researchCitations.json"
CATALOG_JSON = REPO_ROOT / "sites" / "feature-reference" / "src" / "catalog.json"
STORYBOARD_JS = REPO_ROOT / "sites" / "marketing" / "src" / "lib" / "storyboard.js"

# From the plan §3.1 schema. The storyboard's own stop ids are read from
# storyboard.js rather than restated here, so adding a stop cannot silently
# strand this gate.
TYPES = {"paper", "rfc", "spec", "benchmark", "survey", "engineering-report", "licence"}
CATEGORIES = {"retrieval", "compute", "security", "distributed", "systems", "licensing"}
APPLIED = {"shipped", "design", "deferred"}
# peerReview honesty: types that may ever claim peer review.
PEER_REVIEWABLE = {"paper", "survey", "benchmark"}

REQUIRED_FIELDS = (
    "id", "stopId", "title", "authors", "venue", "year",
    "url", "identifier", "type", "peerReviewed", "category",
    "applied", "takeaway", "howHalbertApplies",
)
PROSE_FIELDS = ("title", "authors", "venue", "takeaway", "howHalbertApplies")

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SHIPPED_PATH_RE = re.compile(r"halbert_core/[A-Za-z0-9_/.-]+")
BANNED_PHRASES = {
    # case-insensitive; directive: never write "Sovereign" on a user-facing
    # surface, in any case.
    "sovereign": "never write 'Sovereign' on a user-facing surface (standing directive)",
    "14k": "unverified corpus count — the measured corpus is ~21.5k unique non-empty docs ('thousands' or the measured number, never '14k')",
}


def storyboard_stop_ids() -> list[str]:
    """Read the 8 stop ids from the storyboard so this gate cannot drift."""
    text = STORYBOARD_JS.read_text(encoding="utf-8")
    return re.findall(r"id:\s*'([a-z-]+)'", text)


def check_citation(c: dict, stop_ids: list[str], errors: list[str], idx: int) -> None:
    label = c.get("id") or f"entry[{idx}]"

    def err(msg: str) -> None:
        errors.append(f"{label}: {msg}")

    for field in REQUIRED_FIELDS:
        if field not in c:
            err(f"missing required field '{field}'")
    if errors and errors[-1].startswith(f"{label}: missing"):
        # field-shape checks below assume presence; report and skip the rest
        return

    if not KEBAB_RE.match(c["id"]):
        err(f"id '{c['id']}' is not kebab-case")
    if c["stopId"] not in stop_ids:
        err(f"stopId '{c['stopId']}' is not a storyboard stop id ({', '.join(stop_ids)})")
    if not isinstance(c["year"], int) or not (1970 <= c["year"] <= 2030):
        err(f"year {c['year']!r} is not a plausible publication year")
    if not str(c["url"]).startswith("https://"):
        err(f"url '{c['url']}' is not https")
    if c["type"] not in TYPES:
        err(f"type '{c['type']}' not in {sorted(TYPES)}")
    if c["category"] not in CATEGORIES:
        err(f"category '{c['category']}' not in {sorted(CATEGORIES)}")
    if c["applied"] not in APPLIED:
        err(f"applied '{c['applied']}' not in {sorted(APPLIED)}")

    # Identifiability: an entry with no stable identifier must say so with
    # a note; silence is how hallucinations used to pass.
    if not str(c["identifier"]).strip():
        if not str(c.get("identifierNote", "")).strip():
            err("identifier is empty and carries no identifierNote explaining why")

    # Peer-review honesty.
    if c["peerReviewed"] and c["type"] not in PEER_REVIEWABLE:
        err(f"type '{c['type']}' cannot claim peerReviewed=true")
    if c["type"] == "engineering-report" and c["peerReviewed"]:
        err("engineering reports are not peer-reviewed")

    # Shipped honesty: shipped means code today, and the prose names the file.
    # Licence-type entries are exempt: their operative artifact is a repo-root
    # licence text (LICENSE / LICENSE-EXCEPTION-APPSTORE), not a code module.
    if c["applied"] == "shipped" and c["type"] != "licence" and not SHIPPED_PATH_RE.search(c["howHalbertApplies"]):
        err("applied='shipped' but howHalbertApplies names no halbert_core/ file")

    # One join direction: the reverse mapping is derived at load, never stored.
    if "relatedFeatureIds" in c:
        err("relatedFeatureIds is stored here — features carry citationIds; the reverse is derived (one join direction only)")

    # Copy directives on prose.
    for field in PROSE_FIELDS:
        value = str(c.get(field, ""))
        for phrase, why in BANNED_PHRASES.items():
            if phrase.lower() in value.lower():
                err(f"{field} contains banned phrase '{phrase}' ({why})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="list every citation as it is checked")
    parser.add_argument("--catalog", action="store_true", help="also validate catalog.json's citationIds join")
    args = parser.parse_args()

    if not CITATIONS_JSON.exists():
        print(f"error: {CITATIONS_JSON.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 1

    try:
        data = json.loads(CITATIONS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {CITATIONS_JSON.relative_to(REPO_ROOT)} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    citations = data.get("citations") if isinstance(data, dict) else data
    if not isinstance(citations, list):
        print("error: expected a top-level list (or an object with a 'citations' list)", file=sys.stderr)
        return 1

    stop_ids = storyboard_stop_ids()
    errors: list[str] = []
    seen_ids: set[str] = set()
    per_stop: dict[str, int] = {}

    print(f"Halbert research citation gate — {CITATIONS_JSON.relative_to(REPO_ROOT)}")
    print(f"  storyboard stops: {', '.join(stop_ids)}")

    for idx, c in enumerate(citations):
        if not isinstance(c, dict):
            errors.append(f"entry[{idx}] is not an object")
            continue
        check_citation(c, stop_ids, errors, idx)
        if c.get("id") in seen_ids:
            errors.append(f"{c.get('id')}: duplicate id")
        seen_ids.add(c.get("id", f"entry[{idx}]"))
        per_stop[c.get("stopId", "?")] = per_stop.get(c.get("stopId", "?"), 0) + 1
        if args.verbose:
            print(f"  [{idx + 1}/{len(citations)}] {c.get('id', '?')} · {c.get('type', '?')} · "
                  f"applied={c.get('applied', '?')} · peerReviewed={c.get('peerReviewed', '?')}")

    if args.catalog:
        if not CATALOG_JSON.exists():
            print(f"error: {CATALOG_JSON.relative_to(REPO_ROOT)} not found", file=sys.stderr)
            return 1
        catalog = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
        known = {c.get("id") for c in citations if isinstance(c, dict)}
        for f in catalog.get("features", []):
            for cid in f.get("citationIds", []) or []:
                if cid not in known:
                    errors.append(f"catalog feature '{f.get('id')}': citationIds references unknown citation '{cid}'")
            if "relatedCitationIds" in f:
                errors.append(f"catalog feature '{f.get('id')}': relatedCitationIds is the mirrored wrong join direction — features carry citationIds only")
            for sid in f.get("stopIds", []) or []:
                if sid not in stop_ids:
                    errors.append(f"catalog feature '{f.get('id')}': stopIds references unknown stop '{sid}'")
            # stopIds and citationIds are deliberately independent associations
            # (plan §3.2): stopIds are curated marketing anchors for the
            # dossier's Section Focus tab; citationIds are the academic join.
            # A feature may cite a paper whose stopId it does not anchor — the
            # reverse citation→feature mapping is derived at load from
            # citationIds, with no stop coupling.

    print()
    print("  per-stop distribution:")
    for sid in stop_ids:
        print(f"    {sid:10s} {per_stop.get(sid, 0)}")

    print()
    if errors:
        print(f"  FAIL — {len(errors)} problem(s):")
        for e in errors:
            print(f"    ✗ {e}")
        return 1
    print(f"  OK — {len(citations)} citations pass the gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())