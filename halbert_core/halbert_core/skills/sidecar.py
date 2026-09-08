# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The provenance sidecar: `.halbert-skill.json` beside SKILL.md.

Design §5.4: provenance lives in the sidecar, keyed by the stable skill id
— "never inferred from location, never keyed by name. A rename, a moved
root, or an ecosystem pack that happens to collidingly share a name must
not smuggle or forfeit provenance." One source of truth: the sidecar; the
frontmatter `id` is only the join key.

SK-1 owns the schema and the reader; the write path is SK-6's. The sidecar
is untrusted input throughout, with the same treatment as SKILL.md (§4.2):
a hard byte cap, strict UTF-8, no NUL bytes, and every field validated
against the schema — unknown keys are tolerated (an operator may hand-edit
a forward-compat key without bricking provenance), but a *known* key with a
value outside the schema is refused, not silently dropped.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .parser import SKILL_ID_RE

logger = logging.getLogger(__name__)

SIDECAR_NAME = ".halbert-skill.json"

#: Boundary-safe read cap (design §4.2). Provenance is three fields; a
#: sidecar is not a place to hide a novel.
MAX_SIDECAR_BYTES = 8 * 1024

CREATED_BY = ("agent", "operator")
SIDECAR_STATES = ("draft", "trusted", "archived")

_KNOWN_KEYS = ("id", "created_by", "state")


class SkillSidecarError(ValueError):
    """A sidecar could not be read as provenance."""


@dataclass(frozen=True)
class SkillSidecar:
    """One parsed provenance sidecar."""

    id: Optional[str] = None
    created_by: Optional[str] = None
    state: Optional[str] = None


def load_sidecar(path: Path) -> Optional[SkillSidecar]:
    """Read and validate the sidecar at *path*; None when it does not exist.

    Raises SkillSidecarError for a sidecar that exists but is not one —
    refusing is the honest behavior: provenance that silently drops to
    "unknown" because the file was malformed forfeits exactly what it exists
    to carry.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SkillSidecarError(f"{path}: unreadable sidecar: {e}") from e

    if len(raw) > MAX_SIDECAR_BYTES:
        raise SkillSidecarError(
            f"{path}: sidecar is over the {MAX_SIDECAR_BYTES // 1024} KiB "
            f"cap ({len(raw)} bytes)"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SkillSidecarError(f"{path}: not strict UTF-8: {e}") from e
    if "\x00" in text:
        raise SkillSidecarError(f"{path}: NUL byte refused")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SkillSidecarError(f"{path}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise SkillSidecarError(f"{path}: sidecar must be a mapping")

    unknown = sorted(set(data) - set(_KNOWN_KEYS))
    if unknown:
        logger.debug(
            "sidecar %s carries unknown key(s) %s (tolerated)", path, unknown
        )

    skill_id = data.get("id")
    if skill_id is not None:
        skill_id = str(skill_id).strip()
        if not SKILL_ID_RE.fullmatch(skill_id):
            raise SkillSidecarError(
                f"{path}: id {skill_id!r} is not a stable skill id "
                "(sk_ + ULID)"
            )

    created_by = data.get("created_by")
    if created_by is not None:
        created_by = str(created_by).strip()
        if created_by not in CREATED_BY:
            raise SkillSidecarError(
                f"{path}: created_by must be one of {CREATED_BY}"
            )

    state = data.get("state")
    if state is not None:
        state = str(state).strip()
        if state not in SIDECAR_STATES:
            raise SkillSidecarError(
                f"{path}: state must be one of {SIDECAR_STATES}"
            )

    return SkillSidecar(id=skill_id, created_by=created_by, state=state)


def verify_sidecar_join(skill: Any, sidecar: Optional[SkillSidecar]) -> bool:
    """True when the sidecar is provenance *for this skill*.

    The join is the id and only the id: both sides must carry one and they
    must match. A sidecar without an id — or a skill without one — has
    nothing to join on, and `False` is the answer, because the alternative
    is inferring provenance from location or name, which is exactly what
    the design forbids.
    """
    if sidecar is None or sidecar.id is None:
        return False
    skill_id = getattr(skill, "id", None)
    return skill_id is not None and str(skill_id) == sidecar.id