# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The homes whose personas this machine may wear.

"Be Marnie" only works if Halbert already knows where Marnie lives. Before
this, ``POST /api/guest/pull`` took the base URL, the persona id and the token
in the request body — fine for a script, useless as a thing a person says.

A home is deliberately **not** a paired peer. Pairing (``federation/``) joins
another *body* of this entity, or lends it compute; a sibling app's home is a
different relationship with a different credential, and folding one into the
other would mean every paired body implicitly offered its personas. So this is
its own small file, ``guest_homes.yml``, written 0600 because it holds a
bearer token.

The token is never returned by any read here. Listing homes tells you the
label and the URL; the credential stays on disk.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml

logger = logging.getLogger("halbert.persona.guest_homes")

FILENAME = "guest_homes.yml"


class BadHome(ValueError):
    """Not a home this machine can reach."""


@dataclass(frozen=True)
class GuestHomeRecord:
    base_url: str
    label: str
    token: str = ""
    #: Which API shape this house speaks (``persona/sibling.API_PROFILES``).
    #: The engine is the same in every sibling; only the mount differs.
    profile: str = "default"

    def to_dict(self, *, with_token: bool = False) -> Dict[str, Any]:
        out = {"base_url": self.base_url, "label": self.label, "profile": self.profile}
        if with_token:
            out["token"] = self.token
        return out


def _path() -> Path:
    from ..utils.platform import get_config_dir

    return get_config_dir() / FILENAME


def _normalise(base_url: str) -> str:
    url = str(base_url or "").strip().rstrip("/")
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise BadHome("a home's base_url must be an http(s) URL")
    return url


def list_homes(*, with_tokens: bool = False) -> List[GuestHomeRecord]:
    """Every home this machine knows. Never raises — a missing or malformed
    file means no homes, not a broken pill."""
    path = _path()
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Could not read %s: %s", path, e)
        return []
    out: List[GuestHomeRecord] = []
    for entry in (data.get("homes") or []):
        if not isinstance(entry, dict):
            continue
        try:
            url = _normalise(entry.get("base_url", ""))
        except BadHome:
            continue
        out.append(GuestHomeRecord(
            base_url=url,
            label=str(entry.get("label") or urlparse(url).netloc),
            token=str(entry.get("token") or "") if with_tokens else "",
            profile=str(entry.get("profile") or "default"),
        ))
    return out


def get_home(base_url: str) -> Optional[GuestHomeRecord]:
    """The record for one home, token included — the caller is about to use it."""
    try:
        wanted = _normalise(base_url)
    except BadHome:
        return None
    for home in list_homes(with_tokens=True):
        if home.base_url == wanted:
            return home
    return None


def add_home(base_url: str, label: str = "", token: str = "",
             profile: str = "default") -> GuestHomeRecord:
    """Remember a home. Re-adding the same URL replaces what it says."""
    from .sibling import API_PROFILES

    url = _normalise(base_url)
    if profile not in API_PROFILES:
        raise BadHome(f"unknown home profile {profile!r} (have: {', '.join(API_PROFILES)})")
    record = GuestHomeRecord(
        base_url=url,
        label=str(label or "").strip() or urlparse(url).netloc,
        token=str(token or ""),
        profile=profile,
    )
    others = [h for h in list_homes(with_tokens=True) if h.base_url != url]
    _save(others + [record])
    return record


def remove_home(base_url: str) -> bool:
    url = _normalise(base_url)
    homes = list_homes(with_tokens=True)
    kept = [h for h in homes if h.base_url != url]
    if len(kept) == len(homes):
        return False
    _save(kept)
    return True


def _save(homes: List[GuestHomeRecord]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"homes": [h.to_dict(with_token=True) for h in homes]}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".guest_homes_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            # A12-G8: the atomic rename was already here; the durability
            # half was not. Without the fsync the rename can land while
            # the data behind it is still in the page cache, so a power
            # loss leaves a truncated file -- and `list_homes` swallows a
            # malformed file and returns [], which reads as "no homes are
            # paired" and makes the operator re-enter a bearer token.
            # One line, on the one file here that stores a credential.
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Ambiguous(LookupError):
    """A name that lives in more than one home. Which one is the user's to say."""

    def __init__(self, name: str, homes: List[str]):
        self.name = name
        self.homes = homes
        super().__init__(
            f"{name} lives in more than one home ({', '.join(sorted(homes))}); say which."
        )


class NoSuchPersona(LookupError):
    """Nobody by that name, in any home that answered."""

    def __init__(self, name: str, unreachable: List[str]):
        self.name = name
        self.unreachable = unreachable
        detail = f"No persona called {name!r} in any known home"
        if unreachable:
            detail += f" (unreachable: {', '.join(unreachable)})"
        super().__init__(detail)


def resolve_persona(name: str, base_url: str = "", transport: Any = None) -> Dict[str, Any]:
    """The one persona ``name`` refers to, or a refusal that says why.

    Shared by the route and the agent tool deliberately: two callers resolving
    a name two ways is how "be Marnie" starts meaning different faces
    depending on where you said it.

    Answering with one of several matches would be a guess about whose face
    the user meant, so an ambiguous name raises rather than picking.
    """
    catalogue = available_personas(transport)
    wanted = " ".join(str(name or "").split()).lower()
    # The disambiguator accepts either spelling. The listing shows a home by
    # its LABEL ("at H2"), so a caller reading that listing and answering with
    # what it read could never match a base-URL-only comparison — the only way
    # out of an ambiguous name was a URL nothing had shown them.
    home = " ".join(str(base_url or "").split()).lower().rstrip("/")
    matches = [
        p for p in catalogue["personas"]
        if p["name"].strip().lower() == wanted
        and (
            not home
            or p["base_url"].lower().rstrip("/") == home
            or p["home_label"].strip().lower() == home
        )
    ]
    if not matches:
        raise NoSuchPersona(name, [u["home"] for u in catalogue["unreachable"]])
    if len(matches) > 1:
        raise Ambiguous(name, [m["home_label"] for m in matches])
    return matches[0]


def available_personas(transport: Any = None) -> Dict[str, Any]:
    """Every persona this machine could wear, across every known home.

    One home being unreachable must not hide the others, so failures are
    reported per home rather than raised — "be Marnie" should still work when
    the other house is asleep.
    """
    from .guest import GuestHome
    from .sibling import SiblingClient

    personas: List[Dict[str, Any]] = []
    unreachable: List[Dict[str, str]] = []
    for record in list_homes(with_tokens=True):
        home = GuestHome(base_url=record.base_url, persona_id="", token=record.token,
                         label=record.label, profile=record.profile)
        try:
            found = SiblingClient(home, transport, profile=record.profile).list_personas()
        except Exception as e:
            unreachable.append({"home": record.label, "error": str(e)})
            continue
        for entry in found or []:
            pid = str(entry.get("id") or entry.get("persona_id") or "").strip()
            if not pid:
                continue
            personas.append({
                "persona_id": pid,
                "name": str(entry.get("name") or pid),
                "home_label": record.label,
                "base_url": record.base_url,
                "profile": record.profile,
            })
    return {"personas": personas, "unreachable": unreachable}
