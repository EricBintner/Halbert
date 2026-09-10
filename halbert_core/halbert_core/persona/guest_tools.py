# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Guest tool profile — what a borrowed face may ask Halbert's body for.

Mirrors ``federation/tool_allowlist.py`` field for field: a frozen allowlist,
a paired denylist for testability, and an import-time self-check. The peer
allowlist answers "what may an outside *prompt* call on this GPU"; this one
answers "what may a guest *persona* fronting on this machine ask for".

Where it applies
----------------
Two places in ``tools/executor.py``, both keyed on ``guest.current_guest()``:

1. ``get_schemas()`` — the one per-turn choke point. A disallowed tool is
   absent from the schema list the model receives, so a model that cannot
   see ``run_command`` does not have to be talked out of it. The handback
   tool is appended here and exists only while a guest fronts.
2. ``execute()`` — because the conversation history a guest inherits holds
   Halbert's own earlier turns, ``run_command`` calls included, and a model
   can imitate a call it was not offered. A hidden tool named anyway is
   refused and audited, never run.

The line
--------
A guest is for the home and for company, not for administering the host
(design §1). Allowed: the house (HA), the view (Frigate reads, the webcam
and its detectors — never the screen), memory recall (Halbert mode; private
mode gates this later, §6), the thread meta-tools (so one seamless
conversation keeps working), and the handback. Denied: the shell, the
filesystem, the terminal, system introspection, screen capture, web search,
and anything that writes to the NVR.

The allowlist is the authoritative check. The denylist exists so the tests
can insist every registered agent tool has been classified on purpose.
Adding a tool to the allowlist is a code change and a security review.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List

logger = logging.getLogger(__name__)

HANDBACK_TOOL_NAME = "hand_back_to_halbert"
RECALL_GUEST_MEMORY_TOOL_NAME = "recall_guest_memory"

# The tools whose handlers put the model's stated ``reason`` into the
# hash-chained audit log (``obs/audit.py``). Design §6: a guest turn never
# reaches that log as long as none of these is ever allowed to a guest.
WRITE_PLANE_TOOLS: FrozenSet[str] = frozenset({
    "run_command",
    "write_file",
    "write_config",
    "schedule_cron",
    "terminal_blocks",
})

HANDBACK_TOOL_SCHEMA: Dict[str, Any] = {
    "name": HANDBACK_TOOL_NAME,
    "description": (
        "Hand the conversation back to the machine's own persona. Use this "
        "when the user asks for anything system-level — commands, files, "
        "services, the screen — or asks for the machine by name. The guest "
        "persona ends and the machine answers under its own name with its "
        "full tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "One line on why you are handing back (optional).",
            },
        },
        "required": [],
    },
}

RECALL_GUEST_MEMORY_SCHEMA: Dict[str, Any] = {
    "name": RECALL_GUEST_MEMORY_TOOL_NAME,
    "description": (
        "Recall something from your own memory — what you and this user have "
        "said and done together before. This is your memory at your home, not "
        "the machine's."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for."},
            "k": {"type": "integer", "description": "How many memories to return (default 5)."},
        },
        "required": ["query"],
    },
}


async def recall_guest_memory(args: Dict[str, Any]) -> str:
    """The guest reads what it wrote (I6). Never Halbert's memory."""
    from .guest import current_guest
    from .sibling import HomeUnreachable, SiblingClient

    session = current_guest()
    if session is None:
        return "No guest persona is fronting."
    who = session.persona.name
    if session.home is None:
        return f"{who} has no memory home in this session; there is nothing to recall."
    query = str((args or {}).get("query") or "").strip()
    try:
        k = max(1, min(20, int((args or {}).get("k") or 5)))
    except (TypeError, ValueError):
        k = 5
    try:
        memories = SiblingClient(session.home).memory_search(query, k=k, strict=True)
    except HomeUnreachable:
        return f"{who} could not reach their memory just now."
    lines = []
    for m in memories:
        text = m.get("content") if isinstance(m, dict) else str(m)
        text = " ".join(str(text or "").split())
        if text:
            lines.append(f"- {text}")
    if not lines:
        return f"{who} remembers nothing about that."
    return f"{who} remembers:\n" + "\n".join(lines)


# Tools that exist only while a guest fronts. They are not in the executor's
# registry; the mask appends their schemas and runs their handlers.
GUEST_ONLY_TOOLS: Dict[str, Dict[str, Any]] = {
    HANDBACK_TOOL_NAME: HANDBACK_TOOL_SCHEMA,
    RECALL_GUEST_MEMORY_TOOL_NAME: RECALL_GUEST_MEMORY_SCHEMA,
}
GUEST_ONLY_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Awaitable[str]]] = {
    RECALL_GUEST_MEMORY_TOOL_NAME: recall_guest_memory,
}

GUEST_ALLOWED_TOOLS: FrozenSet[str] = frozenset({
    # The house
    "ha_get_entity_state",
    "ha_call_service",          # governed by the autonomy gate, unchanged
    # The view — reads only
    "frigate_list_cameras",
    "frigate_get_events",
    "frigate_get_reviews",
    "frigate_get_latest_frame",
    "frigate_get_snapshot",
    "capture_webcam",
    "detect_motion",
    "detect_objects",
    "detect_faces",
    # Memory — the guest's own, at its home (D3 / I6: nothing of Halbert's)
    RECALL_GUEST_MEMORY_TOOL_NAME,
    # One conversation — opening a thread is fine; recalling one is a read
    # of Halbert's memory and is not
    "new_thread",
    # The way home
    HANDBACK_TOOL_NAME,
})

# Tools a guest may reach ONLY in Halbert (normal) mode.
#
# Founder ruling 2026-09-10: the main Halbert shares its memory with a
# fronting guest, and *only private mode is the fully isolated memory* --
# private still controls the house, it just cannot read Halbert's memory.
#
# I6 ("the guest may not read what it may not write") permits this rather
# than forbidding it, once applied per-mode. ``route_write`` already sends
# ``conversation.message`` to HALBERT in normal mode and to the guest's home
# in private mode, so in normal mode the guest *writes* to Halbert's
# conversation store and the read is symmetric. In private mode that write
# moves away, and the read closes with it. The one-way valve I6 exists to
# stop is never open.
#
# ``cognition.tick`` is untouched: GUEST in every mode under R2, so
# Halbert's psyche never learns a guest's evenings. Sharing a conversation
# is not merging a psyche.
HALBERT_MODE_ONLY_TOOLS: FrozenSet[str] = frozenset({
    "recall_memory",
    "recall_thread",
    "resume_thread",
})


def _private_mode_for_tools() -> bool:
    """Is private mode on? **Unknown counts as private.**

    Deliberately not ``continuity.ownership._private_mode``, which answers
    ``False`` when it cannot tell. For a *write* that is the safe direction:
    the row lands in Halbert's own store, which the user can see and erase.
    For a *read gate* it is exactly backwards -- ``False`` is the wider set,
    so an unreadable source registry would hand a guest Halbert's memory
    during what the user believes is private mode.

    This is P3's discipline ("a writer nobody classified fails closed")
    applied to reads.
    """
    try:
        from .private_sources import active

        return bool(active())
    except Exception as e:
        logger.warning(
            "Private-mode signal unreadable (%s); treating this turn as "
            "private and withholding Halbert's memory from the guest.", e,
        )
        return True


def guest_allowed_tools() -> FrozenSet[str]:
    """The tools a guest may reach *right now*, given the mode."""
    if _private_mode_for_tools():
        return GUEST_ALLOWED_TOOLS
    return GUEST_ALLOWED_TOOLS | HALBERT_MODE_ONLY_TOOLS


GUEST_DENIED_TOOLS: FrozenSet[str] = frozenset({
    # The host
    "run_command",
    "read_file",
    "write_file",
    "list_directory",
    "terminal_blocks",
    # System introspection
    "get_cpu_info",
    "get_disk_usage",
    "get_memory_info",
    "get_network_info",
    "get_process_list",
    "get_service_status",
    # The screen is the workstation's, not the house's
    "capture_screenshot",
    "capture_window",
    "capture_active_window",
    "capture_and_ocr",
    "list_windows",
    # Writes to the NVR
    "frigate_review_event",
    # A fact about the person — denied in BOTH modes, unlike the
    # conversation store above it.
    #
    # The 2026-09-10 ruling shares Halbert's memory with a fronting guest in
    # normal mode, and I6 permits that because the read is symmetric there:
    # `route_write` already sends `conversation.message` to HALBERT, so the
    # guest writes what it then reads. That symmetry does not exist here.
    # `remember` has a member floor (`RQ-8`) that no mode lifts, so a guest
    # can never write a fact about a person — and a read granted without the
    # matching write is exactly the one-way valve I6 exists to close.
    # Mode-scoping this one would therefore be a wider ruling than the one
    # that was made, not an application of it.
    "remember",
    # The world
    "web_search",
    # Becoming someone else. A guest that could call this would walk out of
    # its own session into another persona's face without the user asking —
    # and the user would learn of it from the pill, if they were looking.
    "become_persona",
    # The script pipeline (Packet 06): a guest runs no scripts, period.
    # Collapsing tool pipelines is the machine's own way of working; a
    # guest's read-only house/view needs never need it, and the floor is
    # pinned in tests/tools/test_execute_code.py at every layer: never
    # offered, refused if named, absent from any script's stub set.
    "execute_code",
    # AppleScript / JXA (A2): one script call is the whole machine —
    # Finder deletes, Mail sends, `do shell script` runs shell. A guest
    # scripts nothing on this host; pinned in
    # tests/test_applescript_safety.py at every layer.
    "run_applescript",
    "run_jxa",
    # MCP-surface names, listed so the intent is on record should any of
    # them ever be registered as agent tools
    "get_being_config",
    "get_config_value",
    "set_autonomy_level",
    "approve_proposal",
    "run_scanner",
    # MCP bridge tools (B2) are dynamic names (mcp__{server}__{tool},
    # decided by whatever remote servers expose) and so cannot be
    # enumerated on the DENY list the way run_applescript is. The
    # allowlist above is the whole rule and no mcp__ name is on it:
    # guests are structurally excluded from every bridged tool. Listed
    # here as a comment so the intent is on record, same as the
    # MCP-surface names above.
})


def is_tool_allowed_for_guest(tool_name: str) -> bool:
    """The authoritative check: not on the mode's allowlist means denied."""
    return tool_name in guest_allowed_tools()


def filter_tools_for_guest(tool_names: List[str]) -> List[str]:
    """Keep only the tools a guest may ask for, in the order given."""
    allowed: List[str] = []
    for name in tool_names:
        if is_tool_allowed_for_guest(name):
            allowed.append(name)
        else:
            logger.debug("Filtered tool %r from guest turn (not in allowlist)", name)
    return allowed


def _self_check() -> None:
    conditional_overlap = HALBERT_MODE_ONLY_TOOLS & GUEST_DENIED_TOOLS
    if conditional_overlap:
        raise RuntimeError(
            "HALBERT_MODE_ONLY_TOOLS and GUEST_DENIED_TOOLS overlap: "
            f"{conditional_overlap}. A tool cannot be both conditionally "
            "allowed and denied."
        )
    if not HALBERT_MODE_ONLY_TOOLS.isdisjoint(GUEST_ALLOWED_TOOLS):
        raise RuntimeError(
            "HALBERT_MODE_ONLY_TOOLS overlaps the always-allowed set; a tool "
            "gated on normal mode must not also be unconditionally allowed."
        )
    overlap = GUEST_ALLOWED_TOOLS & GUEST_DENIED_TOOLS
    if overlap:
        raise RuntimeError(
            f"GUEST_ALLOWED_TOOLS and GUEST_DENIED_TOOLS overlap: {overlap}. "
            "A tool cannot be both allowed and denied to a guest."
        )
    plane = GUEST_ALLOWED_TOOLS & WRITE_PLANE_TOOLS
    if plane:
        raise RuntimeError(
            f"GUEST_ALLOWED_TOOLS admits the write plane: {plane}. "
            "A guest turn must never reach the audit chain (design §6)."
        )


_self_check()
