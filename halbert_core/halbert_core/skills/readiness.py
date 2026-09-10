# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Is this skill usable on this host, right now? (A13-G6, A13-G10)

``SkillRequirements``' own docstring said it plainly: "parsed -- not
evaluated. Evaluation is SK-4's." Nothing was SK-4, so nothing evaluated
it. A skill declaring ``bins: [zpool]`` bound its body into ``messages[0]``
on a machine with no ZFS and told the model to run commands that are not
there -- and the model, being told by Halbert's own instructions, ran them.

The four answers are distinct because they are four different facts an
operator would act on differently:

``READY``
    Use it.
``MISSING``
    A declared requirement is absent. Installable: the answer may be
    different tomorrow.
``UNSUPPORTED``
    The host is the wrong platform. Not installable. A macOS runbook typed
    on a Linux host is not a preference, it is wrong -- which is why an
    explicit ``/name`` is refused for this and not merely deprioritised
    (Hermes ``tools/skills_tool.py:549-554``).
``DISABLED``
    The operator turned it off. A pack ships six skills and one of them is
    wrong for this house; deleting a file the pack owns is not the way to
    say so.

The OS gate runs FIRST, deliberately, and the origin does the same
(``config-eval.ts:126-149``): a skill that is both unsupported and missing
a binary reports the fact the operator cannot fix, not the one they can.

``env`` is PRESENCE, never value. The names in a ``requires.env`` clause
are frequently secret-shaped, and a readiness check is not a reason to read
a secret, log one, or copy one anywhere.
"""
from __future__ import annotations

import enum
import logging
import os
import shutil
from pathlib import Path
from typing import Any, FrozenSet, Optional, Tuple

logger = logging.getLogger("halbert.skills.readiness")

__all__ = [
    "Readiness",
    "SKILLS_CONFIG_NAME",
    "disabled_skill_names",
    "evaluate_readiness",
    "reset_skills_config_cache",
]

#: Beside the other operator files under the data directory, in the shape
#: `vision_config.yml` established.
SKILLS_CONFIG_NAME = "skills_config.yml"


class Readiness(enum.Enum):
    READY = "ready"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"


# -- the operator's disable list -------------------------------------------

_CONFIG_CACHE: Optional[Tuple[Tuple, FrozenSet[str], dict]] = None


def reset_skills_config_cache() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


def _config_path() -> Path:
    try:
        from ..utils.paths import data_dir

        return Path(data_dir()) / SKILLS_CONFIG_NAME
    except Exception:
        return Path.home() / ".halbert" / SKILLS_CONFIG_NAME


def _load_config() -> dict:
    """The operator's skills config, or ``{}``.

    Cached on the file's own ``(mtime_ns, size)`` -- the same signature the
    reload plane uses -- so an edit lands without a restart and an
    unchanged file is not reparsed once per skill per turn.

    A malformed file disables nothing. Refusing to load skills because a
    YAML file has a typo would be a worse failure than the one this guards
    against, and the log says what happened.
    """
    global _CONFIG_CACHE
    path = _config_path()
    try:
        st = path.stat()
        signature = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        signature = (str(path), -1, -1)
    if _CONFIG_CACHE is not None and _CONFIG_CACHE[0] == signature:
        return _CONFIG_CACHE[2]
    data: dict = {}
    if signature[1] >= 0:
        try:
            import yaml

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
            else:
                logger.warning("%s is not a mapping; ignoring it", path)
        except Exception as e:
            logger.warning("could not read %s (%s: %s); no skill is disabled",
                           path, type(e).__name__, e)
    _CONFIG_CACHE = (signature, frozenset(), data)
    return data


def _names(value: Any) -> FrozenSet[str]:
    if isinstance(value, str):
        return frozenset({value.strip()} - {""})
    if isinstance(value, (list, tuple, set)):
        return frozenset(
            str(v).strip() for v in value if str(v).strip())
    return frozenset()


def disabled_skill_names(platform: Optional[str] = None) -> FrozenSet[str]:
    """Skills the operator has turned off, globally or on this platform."""
    data = _load_config()
    names = set(_names(data.get("disabled")))
    by_platform = data.get("disabled_by_platform")
    if isinstance(by_platform, dict):
        if platform is None:
            from .matcher import current_platform

            platform = current_platform()
        names |= _names(by_platform.get(platform))
    return frozenset(names)


# -- the gates -------------------------------------------------------------

def _has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _has_capability(key: str) -> bool:
    try:
        from ..capabilities import has_capability

        return bool(has_capability(key))
    except Exception:
        # A capability surface that cannot answer is not a licence to
        # assume yes: the clause exists because the skill needs the thing.
        logger.debug("capability check failed for %r", key, exc_info=True)
        return False


def evaluate_readiness(skill: Any, *, platform: Optional[str] = None) -> Readiness:
    """The four-way answer for one skill on this host."""
    from .matcher import current_platform

    host = (platform or current_platform()).lower()

    # 1. Platform, from both places a skill can declare it. First, per the
    #    origin's order: the fact the operator cannot change.
    requires = getattr(skill, "requires", None)
    declared_os = tuple(getattr(requires, "os", ()) or ()) if requires else ()
    trigger_platforms = tuple(
        getattr(getattr(skill, "triggers", None), "platform", ()) or ())
    for declared in (declared_os, trigger_platforms):
        if declared and host not in {str(p).strip().lower() for p in declared}:
            return Readiness.UNSUPPORTED

    # 2. The operator's own answer, ahead of anything installable: a skill
    #    that is switched off should not report a missing binary as though
    #    installing it would help.
    name = str(getattr(skill, "name", "") or "")
    if name and name in disabled_skill_names(host):
        return Readiness.DISABLED

    if requires is None or requires.is_empty():
        return Readiness.READY

    if any(not _has_binary(b) for b in requires.bins):
        return Readiness.MISSING
    if requires.any_bins and not any(_has_binary(b) for b in requires.any_bins):
        return Readiness.MISSING
    # Presence, never value.
    if any(name not in os.environ for name in requires.env):
        return Readiness.MISSING
    if any(not _has_capability(key) for key in requires.config):
        return Readiness.MISSING
    return Readiness.READY
