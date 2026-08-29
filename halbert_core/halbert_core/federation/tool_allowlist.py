# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Peer tool allowlist — the restricted tool surface available to peer prompts.

Implements finding C4 from the federated multi-node review.

C4 — The compute endpoint is a prompt-injection exfiltration path
-----------------------------------------------------------------
A paired satellite sends arbitrary prompts to the Desktop's GPU.  If the
Desktop's model has access to file-read tools, config-query tools, or
action tools, a compromised satellite can craft a prompt that instructs
the model to read and return ``~/.ssh/id_rsa``, ``/etc/shadow``, or
SourcePrep-indexed secrets.

This module defines the subset of MCP/agent tools that a peer-initiated
generation is allowed to call.  It mirrors the MCP ``cloud_safe`` tool
table (MCP plan §8) — the tools that are safe to expose to an external
caller whose response may be forwarded to a third-party cloud model.

Allowlist rationale
-------------------
The allowlist is deliberately small.  A peer compute request is asking
the Desktop's GPU for *inference*, not for *host access*.  The peer
already has its own host access (it's a Halbert node).  What it lacks is
GPU compute — so the only tools it needs are the ones that help the
model reason about the prompt (knowledge search, config structure).

Allowed tools:
  - ``search_knowledge`` — SourcePrep semantic search (returns public
    docs, no host-specific secrets).  This lets the Desktop's model
    ground its response in the shared knowledge corpus.
  - ``get_config_structure`` — Structure only (keys, sections, types).
    No values.  Always cloud-safe per MCP Tier 0.
  - ``get_config_diff`` — Change types only (added/removed/modified).
    No values.  Always cloud-safe per MCP Tier 0.
  - ``get_config_dependencies`` — Edges only (dependency graph).  No
    values.  Always cloud-safe per MCP Tier 0.

Disallowed tools (NEVER available to peers):
  - ``get_config_value`` — Returns raw config values (Tier 1/2).
  - ``run_scanner`` — Triggers a fresh system scan (Phase 4b gated).
  - ``approve_proposal`` — Write action (Phase 4b gated).
  - ``get_being_config`` — Returns persona config (may contain secrets).
  - ``ha_call_service`` — Home Assistant action (physical side effects).
  - ``set_autonomy_level`` — Changes autonomy (security-critical).
  - Any file-read or shell-exec tool.

The allowlist is a ``frozenset`` — it cannot be accidentally mutated at
runtime.  Adding a tool requires a code change and a security review.
"""
from __future__ import annotations

import logging
from typing import FrozenSet, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The allowlist — frozen at import time, immutable
# ---------------------------------------------------------------------------

PEER_ALLOWED_TOOLS: FrozenSet[str] = frozenset({
    # Knowledge / retrieval — returns public docs, no host secrets
    "search_knowledge",
    # Config structure — metadata only, no values (MCP Tier 0)
    "get_config_structure",
    "get_config_diff",
    "get_config_dependencies",
})

# Tools that are NEVER available to peer-initiated generations.
# This is documented for clarity and testability — the allowlist is the
# authoritative source, but this denylist makes the intent explicit and
# catches accidental additions to the allowlist via test_peer_tool_allowlist.py.
PEER_DENIED_TOOLS: FrozenSet[str] = frozenset({
    "get_config_value",       # Tier 1/2 — raw config values
    "run_scanner",            # Phase 4b gated — triggers system scan
    "approve_proposal",       # Phase 4b gated — write action
    "get_being_config",       # Persona config — may contain secrets
    "get_vitals",             # Host vitals — Tier 1 operational data
    "get_discoveries",        # Host scan results — Tier 1
    "get_findings",           # Proactive findings — Tier 1
    "get_proposals",          # Config change proposals — Tier 1
    "get_proactive_events",   # Proactive event log — Tier 1
    "ha_get_entities",        # HA entity registry — Tier 1
    "ha_get_entity_state",    # HA entity state — Tier 1
    "ha_call_service",        # HA action — physical side effects!
    "get_autonomy_level",     # Autonomy state — security-relevant
    "set_autonomy_level",     # Autonomy change — security-critical!
})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def is_tool_allowed_for_peer(tool_name: str) -> bool:
    """Check if a tool is in the peer allowlist.

    This is the authoritative check.  The denylist is for documentation
    and testing only — if a tool is not in the allowlist, it is denied,
    regardless of whether it's in the denylist.
    """
    return tool_name in PEER_ALLOWED_TOOLS


def filter_tools_for_peer(tool_names: List[str]) -> List[str]:
    """Filter a list of tool names to only those allowed for peers.

    Logs at debug level for each denied tool so the operator can see
    what was filtered out (useful for debugging "why didn't the model
    call tool X?" questions).
    """
    allowed: List[str] = []
    for name in tool_names:
        if is_tool_allowed_for_peer(name):
            allowed.append(name)
        else:
            logger.debug("Filtered tool %r from peer request (not in allowlist)", name)
    return allowed


# ---------------------------------------------------------------------------
# Self-check — verify no tool is in both allowlist and denylist
# ---------------------------------------------------------------------------

def _self_check() -> None:
    """Verify the allowlist and denylist don't overlap.

    Called at import time.  If they overlap, it's a configuration bug
    that could allow a dangerous tool to be exposed to peers.
    """
    overlap = PEER_ALLOWED_TOOLS & PEER_DENIED_TOOLS
    if overlap:
        raise RuntimeError(
            f"PEER_ALLOWED_TOOLS and PEER_DENIED_TOOLS overlap: {overlap}. "
            "This is a security bug — a tool cannot be both allowed and denied."
        )


_self_check()
