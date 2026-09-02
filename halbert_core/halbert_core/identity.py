# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Who this machine is — the one place the entity's name is resolved.

Halbert identifies as the computer it runs on. Onboarding asks "What should
I call this computer?" and stores the answer as ``ai_name`` in
preferences.yml; that answer is the entity's name. being.yml ``name`` is a
mirror of it (the Settings > Being tab edits it there and writes through).
The hostname is a technical fact about the body, not what the entity is
called — it is only used as a name when nobody has chosen one.

Resolution order (``resolve_entity_name``):

1. ``HALBERT_DISPLAY_NAME`` — an explicit multi-instance launch override
2. preferences.yml ``ai_name`` — the onboarding answer (the source)
3. being.yml ``name`` — the Being tab's mirror of it
4. the short hostname (mDNS/DHCP suffix stripped)
5. ``"Halbert"``

Every user-facing surface — the greeting (``/api/identity``), the Presence
Pill (``/api/instance/info``), the MCP ``serverInfo`` and the mDNS
announcement — resolves through here, so the machine has one name
everywhere. The other identity facts (body name, persona id, entity role)
live here too so the callers that need the whole identity have one import.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Iterable, Optional

logger = logging.getLogger("halbert.identity")

FALLBACK_NAME = "Halbert"

# Suffixes a hostname picks up from mDNS/DHCP that nobody means as part of the
# name. Only stripped when we are falling back to the hostname at all.
HOSTNAME_SUFFIXES = (".local", ".lan", ".home", ".localdomain")

# The peer role a paired machine records when it joined this entity as
# another body (as opposed to lending compute). A non-revoked peer with this
# role is what makes this node the canonical host.
BODY_ROLE = "body"

ENTITY_ROLE_CANONICAL = "canonical"
ENTITY_ROLE_BODY = "body"
ENTITY_ROLE_INDEPENDENT = "independent"


def _clean(value: Any) -> Optional[str]:
    """A non-blank string, or None — blank and whitespace are not names."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Name sources
# ---------------------------------------------------------------------------

def _preferences_path():
    from .utils.platform import get_config_dir

    return get_config_dir() / "preferences.yml"


def chosen_name() -> Optional[str]:
    """The name the user picked in onboarding, or None if they never did.

    Deliberately distinguishes "picked" from "fell back": the caller needs to
    know whether it is holding a name or a hostname. Written by
    ``POST /api/settings/computer-name``, the onboarding step and (through
    ``write_chosen_name``) the Being tab.
    """
    try:
        import yaml

        config_path = _preferences_path()
        if not config_path.exists():
            return None
        with open(config_path, "r", encoding="utf-8") as fh:
            prefs = yaml.safe_load(fh) or {}
        if not isinstance(prefs, dict):
            return None
        return _clean(prefs.get("ai_name"))
    except Exception:
        # Preferences are a convenience here, never a hard dependency.
        return None


def being_name() -> Optional[str]:
    """The ``name`` in being.yml, or None when unset (or the file is bad)."""
    try:
        from .config.being_config import load_being_config

        return _clean(load_being_config().name)
    except Exception:
        return None


def short_hostname(hostname: str) -> str:
    """A hostname without the plumbing suffix, for use as a fallback name."""
    for suffix in HOSTNAME_SUFFIXES:
        if hostname.endswith(suffix):
            return hostname[: -len(suffix)]
    return hostname


def resolve_hostname() -> str:
    """This machine's short hostname — a body fact, never the identity."""
    try:
        return short_hostname(socket.gethostname())
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

def resolve_entity_name(hostname: Optional[str] = None) -> str:
    """What this machine is called, in the order documented at the top.

    ``hostname`` lets a caller that already fetched the system hostname pass
    it in; otherwise it is read from the OS. Only the fallback tier uses it.
    """
    override = _clean(os.environ.get("HALBERT_DISPLAY_NAME"))
    if override:
        return override
    name = chosen_name() or being_name()
    if name:
        return name
    if hostname is None:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = ""
    return short_hostname(hostname or "") or FALLBACK_NAME


def resolve_body_name() -> str:
    """Which physical body the entity is speaking from ("desk", "home").

    being.yml ``body_name`` first, then the variant default.
    """
    from .integrations.cognition_wiring import _get_body_name

    return _get_body_name()


def resolve_persona_id() -> str:
    """The persona identity: being.yml ``persona_id_override`` >
    ``HALBERT_PERSONA_ID`` > ``"halbert"``."""
    from .integrations.cognition_wiring import _get_persona_id

    return _get_persona_id()


def resolve_entity_role(peers: Optional[Iterable[Any]] = None) -> str:
    """This node's place in the entity: ``canonical`` | ``body`` | ``independent``.

    - ``body``: being.yml points at a canonical host (``canonical_memory_url``
      is set) — this node proxies its memory and threads there.
    - ``canonical``: no canonical URL, and at least one non-revoked paired
      peer joined as a body (``role == "body"``) — this node IS the memory
      host, so it is part of the singular entity too.
    - ``independent``: neither.

    ``peers`` is the paired-peer list to consult (a ``PeerCredential``
    iterable); by default the process-wide peer store is read. Revoked
    peers are ignored whichever way they arrive.
    """
    from .integrations.cognition_wiring import _get_canonical_memory_url

    if _get_canonical_memory_url():
        return ENTITY_ROLE_BODY
    if peers is None:
        try:
            from .federation.peer_middleware import get_peers_config

            peers = get_peers_config().list_peers()
        except Exception:
            peers = []
    for peer in peers:
        if getattr(peer, "role", "") == BODY_ROLE and not getattr(peer, "revoked", False):
            return ENTITY_ROLE_CANONICAL
    return ENTITY_ROLE_INDEPENDENT


# ---------------------------------------------------------------------------
# Writers — ai_name is the source; being.yml name mirrors it
# ---------------------------------------------------------------------------

def write_chosen_name(name: str) -> None:
    """Persist the entity name to preferences.yml ``ai_name`` (the source).

    Other preferences are preserved. A blank name clears the choice so the
    resolver falls back to the hostname.
    """
    import yaml

    config_path = _preferences_path()
    prefs: dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if isinstance(loaded, dict):
            prefs = loaded
    prefs["ai_name"] = (name or "").strip()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as fh:
        yaml.dump(prefs, fh, default_flow_style=False, sort_keys=False)


def mirror_name_to_being(name: str) -> None:
    """Mirror the entity name into being.yml ``name`` (the locked composite).

    Called by every writer of ``ai_name`` so the prompt builder, which reads
    being.yml, and the greeting, which reads preferences.yml, agree.
    """
    from .config.being_config import update_being_config

    def mutate(cfg) -> None:
        cfg.name = (name or "").strip()

    update_being_config(mutate)
