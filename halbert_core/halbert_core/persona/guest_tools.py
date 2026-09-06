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
from typing import Any, Dict, FrozenSet, List

logger = logging.getLogger(__name__)

HANDBACK_TOOL_NAME = "hand_back_to_halbert"

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
    # Memory — Halbert mode; private mode is a later phase (§6, Q1)
    "recall_memory",
    # One conversation — handled inline in PLANNING, never executed here
    "new_thread",
    "recall_thread",
    "resume_thread",
    # The way home
    HANDBACK_TOOL_NAME,
})

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
    # The world
    "web_search",
    # MCP-surface names, listed so the intent is on record should any of
    # them ever be registered as agent tools
    "get_being_config",
    "get_config_value",
    "set_autonomy_level",
    "approve_proposal",
    "run_scanner",
})


def is_tool_allowed_for_guest(tool_name: str) -> bool:
    """The authoritative check: not on the allowlist means denied."""
    return tool_name in GUEST_ALLOWED_TOOLS


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
    overlap = GUEST_ALLOWED_TOOLS & GUEST_DENIED_TOOLS
    if overlap:
        raise RuntimeError(
            f"GUEST_ALLOWED_TOOLS and GUEST_DENIED_TOOLS overlap: {overlap}. "
            "A tool cannot be both allowed and denied to a guest."
        )


_self_check()
