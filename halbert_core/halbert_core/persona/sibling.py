# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The guest's home — Halbert's client for a paired sibling's persona API.

Both siblings serve personas in the engine's ``PersonaConfig`` shape and a
per-persona memory. That is enough for three things this module does
(``.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md``):

- **The pull channel (§7).** "Halbert, be Marnie": fetch the persona from
  its home, map it onto ``GUEST_PERSONA_FIELDS``, and wear it. The session
  is kept alive by a successful ping of the home rather than by a
  heartbeat nobody is sending.
- **Forward the turn (§4.2).** While a guest fronts, a turn is one memory
  at the guest's home, tagged with the session — never a namespace on this
  disk. A dead home means the guest does not remember, and says so.
- **Recall (§4.3, I6).** The guest reads what it wrote: its own memory
  search, and nothing of Halbert's.

Network is behind an injected ``transport`` so none of this needs a
sibling running to be tested. Real names of the siblings are not written
here; a home is an address and a persona id.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from . import guest as _guest
from .guest import (
    DEFAULT_TTL_SECONDS,
    MAX_PROMPT_CHARS,
    MAX_TEXT_CHARS,
    GuestHome,
    GuestPersona,
    GuestSession,
)

logger = logging.getLogger("halbert.persona.sibling")

# The home's memory endpoint refuses more than this.
HOME_MEMORY_CHARS = 2000
# Bound on any round trip to the home; the pill's poll and the agent path
# may pay this once per window when a pulled session is renewed.
TRANSPORT_TIMEOUT_S = 3.0
SESSION_TAG = "halbert-guest-session"

Transport = Callable[[str, str, Optional[Dict[str, Any]], Dict[str, str]], Tuple[int, Any]]


class HomeUnreachable(RuntimeError):
    """The home did not answer, or answered with an error."""


def default_transport(
    method: str, url: str, body: Optional[Dict[str, Any]], headers: Dict[str, str],
) -> Tuple[int, Any]:
    import requests

    resp = requests.request(method, url, json=body, headers=headers, timeout=TRANSPORT_TIMEOUT_S)
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    return resp.status_code, data


#: Where a home keeps its personas and their memory. H2 mounts these at the
#: root; H3 mounts the same engine behind a blueprint prefix, and its memory
#: search sits under that prefix rather than beside the persona. The shapes
#: are the same because the engine is the same — only the mount differs, so
#: this is a table of prefixes and not a second client.
API_PROFILES: Dict[str, Dict[str, str]] = {
    "default": {
        "list": "/api/personas",
        "persona": "/api/personas/{pid}",
        "memory_add": "/api/personas/{pid}/memory-v2/memories",
        "memory_search": "/api/personas/{pid}/memory/search",
    },
    # The historical-minds app (H3). Named by role, not by product.
    "h3": {
        "list": "/api/blueprint/personas",
        "persona": "/api/blueprint/personas/{pid}",
        "memory_add": "/api/blueprint/personas/{pid}/memory-v2/memories",
        "memory_search": "/api/blueprint/personas/{pid}/memory/search",
    },
}

DEFAULT_PROFILE = "default"


class SiblingClient:
    # Kept as class attributes: they were the interface before profiles
    # existed, and code (and tests) that reach for SiblingClient.PATH_LIST
    # should keep working.
    PATH_LIST = API_PROFILES[DEFAULT_PROFILE]["list"]
    PATH_PERSONA = API_PROFILES[DEFAULT_PROFILE]["persona"]
    PATH_MEMORY_ADD = API_PROFILES[DEFAULT_PROFILE]["memory_add"]
    PATH_MEMORY_SEARCH = API_PROFILES[DEFAULT_PROFILE]["memory_search"]

    def __init__(
        self,
        home: GuestHome,
        transport: Optional[Transport] = None,
        profile: str = "",
    ):
        self.home = home
        self._transport = transport or default_transport
        paths = API_PROFILES.get(
            (profile or getattr(home, "profile", "") or DEFAULT_PROFILE),
            API_PROFILES[DEFAULT_PROFILE],
        )
        # Per-instance, shadowing the class attributes above, so one home
        # behind a prefix cannot move another home's paths.
        self.PATH_LIST = paths["list"]
        self.PATH_PERSONA = paths["persona"]
        self.PATH_MEMORY_ADD = paths["memory_add"]
        self.PATH_MEMORY_SEARCH = paths["memory_search"]

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.home.token:
            headers["Authorization"] = f"Bearer {self.home.token}"
        return headers

    def _call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        url = self.home.base_url + path.format(pid=self.home.persona_id)
        try:
            status, data = self._transport(method, url, body, self._headers())
        except Exception as e:
            raise HomeUnreachable(f"{method} {url}: {e}") from e
        if not 200 <= int(status) < 300:
            raise HomeUnreachable(f"{method} {url}: HTTP {status}")
        return data

    # -- personas -----------------------------------------------------------

    def list_personas(self) -> List[Dict[str, Any]]:
        data = self._call("GET", self.PATH_LIST)
        if isinstance(data, Mapping):
            data = data.get("personas", [])
        return list(data or [])

    def fetch_persona(self) -> Dict[str, Any]:
        data = self._call("GET", self.PATH_PERSONA)
        if isinstance(data, Mapping) and isinstance(data.get("persona"), Mapping):
            data = data["persona"]
        if not isinstance(data, Mapping):
            raise HomeUnreachable("persona endpoint returned no persona")
        return dict(data)

    def ping(self) -> bool:
        try:
            self.fetch_persona()
            return True
        except HomeUnreachable as e:
            logger.info("Home %s ping failed: %s", self.home.base_url, e)
            return False

    # -- memory ---------------------------------------------------------------

    def memory_add(
        self, content: str, *, tags: List[str], memory_type: str = "episodic", emotional_weight: float = 0.5,
    ) -> bool:
        body = {
            "content": content[:HOME_MEMORY_CHARS],
            "type": memory_type,
            "tags": list(tags),
            "emotional_weight": emotional_weight,
        }
        try:
            self._call("POST", self.PATH_MEMORY_ADD, body)
            return True
        except HomeUnreachable as e:
            logger.warning("Guest memory not written at %s: %s", self.home.base_url, e)
            return False

    def memory_search(self, query: str, k: int = 5, *, strict: bool = False) -> List[Dict[str, Any]]:
        """The guest's memories about ``query``. Empty on a dead home, or
        ``HomeUnreachable`` when ``strict`` — a caller that must tell "no
        memories" from "no home" asks for the difference."""
        try:
            data = self._call("POST", self.PATH_MEMORY_SEARCH, {"query": query, "k": int(k)})
        except HomeUnreachable as e:
            logger.info("Guest memory search failed at %s: %s", self.home.base_url, e)
            if strict:
                raise
            return []
        if isinstance(data, Mapping):
            data = data.get("memories", [])
        return list(data or [])


# ---------------------------------------------------------------------------
# PersonaConfig → the guest's fields
# ---------------------------------------------------------------------------

def _strings(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [" ".join(str(v).split()) for v in value if str(v).strip()]


def _cap(text: str, limit: int, what: str) -> str:
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        logger.info("Persona %s truncated to %d characters", what, limit)
        return text[: limit - 1].rstrip() + "…"
    return text


def persona_payload_from_config(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Map a persona in the engine's shape — flat, or nested under
    ``personality`` as the siblings' stores serialise it — onto exactly the
    fields a guest may supply. Everything else is left behind here, so the
    validator has nothing to drop."""
    inner = cfg.get("personality") if isinstance(cfg.get("personality"), Mapping) else {}

    def pick(key: str, default: Any = None) -> Any:
        if key in cfg:
            return cfg[key]
        return inner.get(key, default)

    speech = _strings(pick("speech_patterns", []))
    style = " ".join(str(pick("communication_style", "") or "").split())
    if style:
        speech.append(style)
    speech.extend(_strings(pick("quirks", [])))

    profile = pick("personality_profile", {}) or {}
    traits = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
    profile = {k: float(v) for k, v in profile.items() if k in traits and isinstance(v, (int, float))}

    scene = " ".join(p for p in (str(cfg.get("background") or "").strip(), str(cfg.get("context") or "").strip()) if p)
    custom = cfg.get("custom_personality_prompt") or cfg.get("custom_prompt") or ""
    gender = str(cfg.get("gender") or (cfg.get("identity") or {}).get("gender") or "").strip().lower()

    payload: Dict[str, Any] = {
        "name": str(cfg.get("name") or "").strip(),
        "tone_descriptors": _strings(pick("traits", [])),
        "speech_patterns": speech,
        "directives": _strings(cfg.get("directives", [])),
        "personality_profile": profile,
        "archetype_id": pick("archetype_id") or None,
        "custom_personality_prompt": _cap(custom, MAX_PROMPT_CHARS, "custom prompt"),
        "purpose": _cap(cfg.get("summary") or "", MAX_TEXT_CHARS, "summary"),
        "scene_context": _cap(scene, MAX_TEXT_CHARS, "background"),
        "voice_presentation": gender if gender in ("male", "female") else "not_defined",
    }
    return payload


# ---------------------------------------------------------------------------
# Forwarding
# ---------------------------------------------------------------------------

def turn_memory_text(guest_name: str, user_message: str, assistant_response: str, limit: int = HOME_MEMORY_CHARS) -> str:
    user = " ".join(str(user_message or "").split())
    reply = " ".join(str(assistant_response or "").split())
    head_user = "User: "
    head_reply = f"\n{guest_name}: "
    fixed = len(head_user) + len(head_reply)
    user_budget = min(len(user), max(200, (limit - fixed) * 2 // 5))
    reply_budget = max(0, limit - fixed - user_budget)
    return f"{head_user}{user[:user_budget]}{head_reply}{reply[:reply_budget]}"[:limit]


def _client_for(session: GuestSession, transport: Optional[Transport]) -> Optional[SiblingClient]:
    if session.home is None:
        return None
    return SiblingClient(session.home, transport=transport)


def forward_turn(
    session: GuestSession, user_message: str, assistant_response: str, *, transport: Optional[Transport] = None,
) -> bool:
    """One turn becomes one memory at the guest's home. False when there is
    no home or it did not answer — the caller tells the user the guest will
    not remember this. Never raises."""
    client = _client_for(session, transport)
    if client is None:
        logger.info("Guest %s has no home; turn not forwarded", session.persona.name)
        return False
    text = turn_memory_text(session.persona.name, user_message, assistant_response)
    return client.memory_add(text, tags=[SESSION_TAG, session.id, "turn"])


def forward_observation(
    session: GuestSession, text: str, source_id: str, *, transport: Optional[Transport] = None,
) -> bool:
    """An observation from a source handed to the guest (design §5.3)."""
    client = _client_for(session, transport)
    if client is None:
        return False
    return client.memory_add(
        " ".join(str(text or "").split()), tags=[SESSION_TAG, session.id, "observation", source_id],
    )


# ---------------------------------------------------------------------------
# The pull channel
# ---------------------------------------------------------------------------

def install_from_home(
    home: GuestHome,
    *,
    offered_by: str,
    offered_by_name: str = "",
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    transport: Optional[Transport] = None,
) -> Tuple[GuestSession, List[str]]:
    """Fetch the persona from its home and wear it. Raises
    ``HomeUnreachable`` (nothing installed) or the validator's errors."""
    client = SiblingClient(home, transport=transport)
    cfg = client.fetch_persona()
    persona, dropped = GuestPersona.from_payload(persona_payload_from_config(cfg))
    session = _guest.offer(
        persona,
        offered_by=offered_by,
        offered_by_name=offered_by_name or home.label,
        ttl_seconds=ttl_seconds,
        home=home,
        keepalive=client.ping,
    )
    return session, dropped
