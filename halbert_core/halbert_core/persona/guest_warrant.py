# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The guest's warrant — by what authority a borrowed face acts.

`.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md` §14 argued that the guest
persona was already a warrant spelled out by hand: a voice acting under
someone else's rules, saying so in prose we wrote ourselves. The engine has
since grown the type (`haloysius.warrant`), so the prose becomes a record.

What changes by doing this, beyond tidiness:

- **The mandate is data, not a paragraph.** ``authorize_under(warrant, tool)``
  can answer a ``GovernancePolicy.authorize_action`` with a citing decision,
  so the same object that tells the model what it may do can one day be the
  thing that enforces it. Two statements of a rule drift; one does not.
- **The refusal cites.** "run_command is not Marnie's to do: Macky holds it"
  names the holder rather than sounding like the persona's own reticence.
- **The ordering rule is the engine's now.** ``render_warrant_block``'s own
  docstring says it goes after the persona's text, for the reason we found
  independently: the persona's words are voice, not authority, and must never
  be the last thing the model reads (I8).

What stays ours, because the engine's block does not say it: that a tool the
guest was not offered this turn does not exist for it, that narrating an
action it has no tool for is the failure mode to avoid, and that it may not
speak *as* the machine. Those are Halbert's, not every consumer's.

Degrades: an engine without ``warrant`` falls back to the hand-written block,
so the prompt is never missing its boundaries.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("halbert.persona.guest_warrant")

#: Every mandated action cites the same rule: the guest tool profile. The
#: profile is the rule — ``persona/guest_tools.GUEST_ALLOWED_TOOLS`` — and
#: naming it in each line is what makes a refusal citable.
MANDATE_RULE = "guest_profile"


def build_warrant(session: Any, own_name: str) -> Optional[Any]:
    """The warrant a fronting guest acts under, or None without the engine."""
    try:
        from haloysius.warrant import Warrant
    except Exception as e:
        logger.debug("Engine warrant unavailable: %s", e)
        return None

    from .guest_tools import GUEST_ALLOWED_TOOLS, HANDBACK_TOOL_NAME

    voice = getattr(getattr(session, "persona", None), "name", "") or "the guest"
    try:
        return Warrant(
            holder=own_name,
            voice=voice,
            mandate={tool: MANDATE_RULE for tool in sorted(GUEST_ALLOWED_TOOLS)},
            hand_over=(
                f"call {HANDBACK_TOOL_NAME} and {own_name} answers under its own name"
            ),
            record=_record_line(session, own_name),
        )
    except Exception as e:
        logger.warning("Could not build the guest warrant: %s", e)
        return None


def _record_line(session: Any, own_name: str) -> str:
    """Whose record this session's words go to — the warrant's own question.

    Worth stating in the prompt because it changes with private mode, and a
    persona that does not know where its words are going cannot tell the user
    honestly when they ask.
    """
    try:
        from . import private_sources
        if private_sources.active():
            home = getattr(session, "home", None)
            where = getattr(home, "label", "") or "the guest's own home"
            return f"this session's words go to {where}, not to {own_name}"
    except Exception:
        pass
    return (
        f"this session's words are {own_name}'s, tagged with the session so "
        f"they can be erased in one go"
    )


def warrant_block(session: Any, own_name: str) -> str:
    """The engine's rendering, or "" when the engine cannot supply one."""
    warrant = build_warrant(session, own_name)
    if warrant is None:
        return ""
    try:
        from haloysius.warrant import render_warrant_block
        return render_warrant_block(warrant)
    except Exception as e:
        logger.warning("Could not render the guest warrant: %s", e)
        return ""
