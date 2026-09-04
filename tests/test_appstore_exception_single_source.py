# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Mac App Store GPLv3 §7 exception must exist in exactly one place (FDR-02).

Three divergent wordings of the exception lived in this tree before 2026-09-04:
`CONTRIBUTING.md` §3, `OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` §7.2, and the
considered text in `APP-STORE-DISTRIBUTION-STRATEGY.md` §2.1.

That is not a tidiness problem. A second wording is a second, different additional
permission under GPLv3 §7, and once a build has been conveyed under a text that
text cannot be quietly retracted for versions already shipped. So: one operative
file, and everything else points at it.

`APP-STORE-DISTRIBUTION-STRATEGY.md` is the one allowed quotation — it is the
rationale document that proposed the text, and it is explicitly not the grant.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXCEPTION_FILE = REPO / "LICENSE-EXCEPTION-APPSTORE"

# The clause that makes the canonical file itself the operative grant.
OPERATIVE_PHRASE = "grant you additional"

# A *grant* — as opposed to a description of one — reads performatively and cites
# the sections it overrides. Matching the canonical wording alone would only catch
# copy-paste; the four wordings this repo accumulated were rewordings, so the
# signature has to be shape-based:
#
#   performative verb  +  the channel  +  the sections being set aside
#
# Descriptions pass: "builds conveyed through the Mac App Store carry one
# additional permission under GPLv3 §7" has no performative verb and cites no
# overridden section. "you grant that same exception on your contribution"
# (CONTRIBUTING) has the verb but sets nothing aside.
GRANT_VERBS = ("grant permission", "grant you", "grants permission", "grants you",
               "grant the copyright", "hereby grant")
CHANNEL = "app store"
OVERRIDES = ("notwithstanding", "section 6", "sections 6", "§6", "§ 6")

# Quoting the text here is the rationale document's job, not a second grant.
ALLOWED = {"documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md"}

SEARCH_SUFFIXES = {".md", ".txt", ".rst", ".py", ".rs", ".ts", ".tsx", ".toml", ".yml", ".yaml"}

# Only first-party files are policed.
#
#   data/            scraped RAG corpus — third-party prose that discusses App
#                    Store licensing is not this project making a grant, and one
#                    such page (ask-different) trips the shape signature.
#   .handoff/        dated working records. FOUNDER-DECISION-DRAFTS-2026-08-31.md
#                    legitimately carries the draft that became the canonical
#                    file; it is marked superseded rather than rewritten, because
#                    editing history to satisfy a test is the wrong direction.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             "storybook-static", ".handoff", "target", ".pytest_cache",
             "data", "site-packages", ".mypy_cache", "htmlcov"}

SELF = Path(__file__).resolve()


def _flat(text: str) -> str:
    """Collapse whitespace so the check survives reflowing of the licence text."""
    return re.sub(r"\s+", " ", text)


def _tracked_text_files():
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in SEARCH_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(REPO).parts):
            continue
        yield path


def test_exception_file_exists_and_is_scope_limited():
    assert EXCEPTION_FILE.is_file(), "LICENSE-EXCEPTION-APPSTORE is missing from the repo root"
    text = _flat(EXCEPTION_FILE.read_text())
    assert OPERATIVE_PHRASE in text
    # The three clauses that keep this an *additional permission* rather than a
    # restriction. Losing any one of them changes what was granted.
    assert "applies only to conveyance through the Apple Mac" in text, "scope limitation lost"
    assert "does not extend to any third-party code" in text, "third-party carve-out lost"
    assert "you are not obliged to do so" in text, "downstream fork-freedom clause lost"


def test_exception_text_is_not_paraphrased_elsewhere():
    offenders = []
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWED or path == EXCEPTION_FILE or path.resolve() == SELF:
            continue
        try:
            body = path.read_text(errors="ignore")
        except OSError:
            continue
        flat = _flat(body).lower()
        if (any(v in flat for v in GRANT_VERBS)
                and CHANNEL in flat
                and any(o in flat for o in OVERRIDES)):
            offenders.append(rel)

    assert not offenders, (
        "Something that reads as a §7 App Store grant appears outside "
        "LICENSE-EXCEPTION-APPSTORE in:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nA second wording is a second, different additional permission. Replace the copy "
          "with a pointer to LICENSE-EXCEPTION-APPSTORE."
    )
