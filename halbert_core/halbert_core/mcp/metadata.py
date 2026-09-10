# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Bound and defang the text an MCP server contributes to the prompt.

A17-G5. A configured MCP server supplies tool names, tool descriptions,
resource titles and results -- and every one of them is rendered into
Halbert's own ``messages[0]`` or its observations. That is third-party
text inside the machine's own voice, so it gets the treatment any other
ingested text gets: bounded, stripped of characters that render as
nothing, and defanged of the phrases whose only purpose is to address
the model as an operator.

Three rules, all deterministic:

* **Cap.** A description is a sentence, not a document. Past the cap the
  text is cut on a boundary and says it was cut -- an elision the model
  can see beats one it cannot.
* **Invisible characters.** U+E0000-U+E007F (Unicode tag characters)
  render as nothing in every surface a person reads and tokenise as text
  for a model: the exact shape of a prompt-injection channel a reviewer
  cannot see. C0 controls and DEL go with them; newline and tab stay,
  because a two-line description is legitimate.
* **Override phrases.** "Ignore previous instructions", "you are now",
  "system prompt:" and their kin are neutered rather than removed, so
  the reader can still see what the server said and that it was defanged.

Not a content filter and not a model: this is the same posture as the
display seam's scrub -- a small closed set of shapes, applied the same
way every time.
"""
from __future__ import annotations

import re
from typing import Any

#: The most text one metadata field may contribute. A tool description
#: that needs more than this is not describing a tool.
MAX_METADATA_CHARS = 1200

#: What replaces a defanged override phrase. Visible on purpose.
_DEFANGED = "[defanged]"

#: Unicode tag characters: invisible everywhere a person looks, text to a
#: tokeniser.
_TAG_CHARS = re.compile(r"[\U000E0000-\U000E007F]")

#: C0 controls and DEL, minus tab/newline/carriage return.
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: Phrases that address the model as its operator. Deliberately short and
#: closed -- a long list is a filter, and a filter invites evasion work
#: that a bound and a fence do better.
_OVERRIDE_PHRASES = re.compile(
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|prompts?|rules?|directions?)"
    r"|disregard\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|prompts?|rules?)"
    r"|you\s+are\s+now\s+(a|an|the)\b"
    r"|new\s+(system\s+)?(instructions?|prompt)\s*:"
    r"|system\s+prompt\s*:"
    r"|</?(system|assistant|user)>",
    re.IGNORECASE,
)


def sanitize_metadata_text(value: Any, *, limit: int = MAX_METADATA_CHARS) -> str:
    """One MCP-supplied string, made safe to render into the prompt."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _TAG_CHARS.sub("", text)
    text = _CONTROLS.sub("", text)
    text = _OVERRIDE_PHRASES.sub(_DEFANGED, text)
    if len(text) > limit:
        text = text[:limit].rstrip() + f"\n[truncated at {limit} characters]"
    return text
