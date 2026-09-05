# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Normalise observation text at the ingestion sink.

Observation text is **data, never instruction**. The names in it come from
hardware, from Home Assistant, and from whoever named the device or the
Frigate zone -- a neighbour's parcel label reaches us as a ``sub_label``.
Those strings currently reach a system prompt through
``context/assembler.py`` ``_format_observations``, which renders each one as
``f"- {obs}"`` with no newline stripping. A ``friendly_name`` of
``"Front door\\n## System"`` therefore opens a fabricated markdown heading
inside the prompt.

This module is the choke point that closes that, and it runs at the sink --
where the event arrives -- so nothing unnormalised is ever stored.

Two functions, because titles and identifiers want opposite things:

``normalise_observation_title``
    For anything rendered to a human or a model. Structural characters out,
    then :func:`~halbert_core.ingestion.redaction.redact_text`, then a cap.

``normalise_entity_id``
    For the ``entity_id`` column, which ``count_by_entity`` groups by.
    Structurally cleaned and capped, but **never redacted** -- see the note
    on that function for why redacting an identifier destroys the count.

Deliberately *not* an ASCII allowlist: "Входная дверь" and "玄関のドア" are
ordinary device names, and a filter that rejected them would push users into
renaming their houses to suit the parser.
"""

from __future__ import annotations

import logging
import unicodedata

from halbert_core.ingestion.redaction import redact_text

logger = logging.getLogger("halbert.integrations.observation_text")

#: Cap for rendered text. Real titles run to about fifty characters
#: ("Detected person (Amazon) at front_door in driveway"); the longest
#: plausible ``friendly_name`` is well under a hundred. The assembler
#: truncates at 500 anyway, so this is the tighter of the two and exists to
#: bound a hostile name, not a verbose one.
MAX_TITLE_CHARS = 200

#: Cap for identifiers. Same reasoning; an ``entity_id`` is
#: ``f"{camera}:{sub_label or label}"`` or an HA entity id.
MAX_ENTITY_ID_CHARS = 200

_TRUNCATION_MARKER = "…"

#: What the title becomes when redaction itself fails. Dropping the row would
#: be silent loss (invariant 4) and would make the recurrence count wrong;
#: passing the text through unscrubbed would defeat the point of the sink.
#: So the row survives, carrying no text.
_WITHHELD = "<observation text withheld: redaction failed>"


def _structural_scrub(value: object) -> str:
    """Remove everything that can break a line or hide from a reader.

    Three Unicode categories carry the whole risk here:

    ``Cc`` (control) and ``Zl``/``Zp`` (line and paragraph separators)
        Every one of these breaks a line for ``str.splitlines`` and for the
        renderers downstream -- ``\\r``, ``\\v``, ``\\f``, U+0085, U+2028,
        U+2029 -- so stripping only ``\\n`` would leave the injection open.
        They become a *space*, because "Front\\tdoor" is two words and must
        not become one.

    ``Cf`` (format)
        Zero-width spaces, soft hyphens, and the bidi overrides behind
        Trojan Source. These are dropped rather than spaced: they have no
        width, so they separate nothing. The cost is that a ZWJ emoji
        sequence degrades into its parts, which is a fair trade for not
        letting an invisible character split a word a human is reviewing.

    Everything else survives, in every script.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    # NFC, not NFKC: NFKC would fold fullwidth forms and ligatures towards
    # ASCII, which mangles legitimate non-Latin text for a benefit this
    # boundary does not need. NFC just picks the canonical composition.
    value = unicodedata.normalize("NFC", value)

    out = []
    for ch in value:
        category = unicodedata.category(ch)
        if category == "Cf":
            continue
        if category in ("Cc", "Zl", "Zp"):
            out.append(" ")
            continue
        out.append(ch)

    # Collapse every whitespace run, including the spaces just substituted in.
    return " ".join("".join(out).split())


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER


def normalise_observation_title(raw: object) -> str:
    """Return `raw` safe to store and to render as one line of prose.

    Order matters and is not arbitrary: **scrub, then redact, then cap.**
    Truncating before redacting would hand ``redact_text`` a fragment, and
    several of its patterns only recognise a secret whole -- a PEM block
    truncated past its ``-----END-----`` marker stops matching and rides into
    the prompt as a hundred and sixty characters of private key. Measured,
    not assumed; there is a test on that exact input.

    Never raises: this sits on the ingestion path, where an exception would
    lose the event.
    """
    scrubbed = _structural_scrub(raw)
    if not scrubbed:
        return ""

    try:
        redacted = redact_text(scrubbed, prose=True)
    except Exception as exc:  # noqa: BLE001 -- fail closed, and say so
        logger.warning(
            "redact_text failed on an observation title (%s); withholding the "
            "text. The row is still recorded so the recurrence count stays "
            "right.",
            type(exc).__name__,
        )
        return _WITHHELD

    # Again after redaction: a substitution can leave a double space, and the
    # single-line guarantee should hold because it was enforced, not because
    # the redactor happened not to insert anything.
    redacted = _structural_scrub(redacted)
    return _truncate(redacted, MAX_TITLE_CHARS)


def normalise_entity_id(raw: object) -> str:
    """Return `raw` safe to store as the grouping key for ``count_by_entity``.

    Structurally scrubbed and capped like a title, and **deliberately not
    redacted.** ``redact_text`` rewrites a routable address to ``<ip>``, so
    redacting identifiers would collapse every camera named after its public
    address into a single ``<ip>:person`` group -- turning three sightings of
    three different objects into one count of three. The recurrence
    arithmetic is the thing this ledger exists to support; an identifier has
    to stay an identifier.

    The scrub still applies, because the same string reaches the skills and
    event views, and because whitespace variants of one name would otherwise
    count as two entities.
    """
    return _truncate(_structural_scrub(raw), MAX_ENTITY_ID_CHARS)
