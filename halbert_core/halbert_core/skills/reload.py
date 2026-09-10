# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The daemon's live skill plane: a registry that follows the disk (A13-G2).

``get_agent()`` is a process singleton, so the registry it builds is the
registry the daemon keeps. Edit a SKILL.md -- correct a wrong command,
tighten a ``protected_paths`` line, add a skill -- and nothing changes
until a restart. The reason that is worse than ordinary staleness is that
the two halves disagree: the catalog goes on advertising the OLD
description while ``read_file``, following the ``<location>`` the catalog
printed, hands the model the NEW body.

The shape is Hermes's: a manifest of ``st_mtime_ns`` + ``st_size`` per
skill file, rebuilt at turn start, with the parse running only when a
signature actually moved (``agent/prompt_builder.py:1080-1119``). Stat is
the cheap half; parse is the expensive one. There is no debounce and no
watcher thread -- a stat walk over the two daemon roots costs less than
deciding whether to do it, and a watcher would be a second source of truth
about when a file changed.

Two invariants the tests pin, because both are ways a "fix" for this could
reintroduce it:

- **The matcher object keeps its identity.** ``IntakePipeline`` holds a
  reference to it and reads its ``.registry`` through a property; a reload
  that handed back a NEW matcher would leave the running pipeline matching
  against the registry it had at construction.
- **The signature is committed only on success.** A rebuild that raises
  leaves the previous registry serving AND leaves the old signature in
  place, so the next turn tries again rather than latching the failure as
  the current state.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Iterable, Optional, Tuple

from .loader import daemon_skill_dirs, skill_manifest
from .matcher import SkillMatcher
from .registry import SkillRegistry
from .telemetry import set_active_registry

logger = logging.getLogger("halbert.skills.reload")

__all__ = ["SkillPlane", "get_skill_plane", "reset_skill_plane"]


class SkillPlane:
    """A registry plus its matcher, rebuilt when the skill files move."""

    def __init__(self, dirs: Optional[Iterable[Path]] = None):
        self._dirs = list(dirs) if dirs is not None else None
        self._lock = threading.RLock()
        self._signature: Tuple = ()
        self._registry = SkillRegistry([])
        self._matcher = SkillMatcher(self._registry)
        self.refresh(force=True)

    # -- reading -------------------------------------------------------
    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def matcher(self) -> SkillMatcher:
        return self._matcher

    def dirs(self):
        return list(self._dirs) if self._dirs is not None else daemon_skill_dirs()

    def signature(self) -> Tuple:
        return self._signature

    # -- rebuilding ----------------------------------------------------
    def _build(self, dirs) -> SkillRegistry:
        return SkillRegistry.from_disk(dirs=dirs)

    def refresh(self, *, force: bool = False) -> bool:
        """Reparse if a skill file moved. Returns whether it rebuilt.

        Never raises: this runs at turn start, and a skill plane that
        cannot rebuild costs the turn its expertise, not its answer --
        the same rule the wiring site has always applied to a broken
        skill file.
        """
        with self._lock:
            dirs = self.dirs()
            try:
                signature = skill_manifest(dirs)
            except Exception as e:
                logger.warning("skill manifest failed; keeping the loaded "
                               "registry (%s: %s)", type(e).__name__, e)
                return False
            if not force and signature == self._signature:
                return False
            try:
                registry = self._build(dirs)
            except Exception as e:
                # The signature is deliberately NOT committed here: the
                # next turn retries instead of accepting a failed rebuild
                # as the current state of the disk.
                logger.warning(
                    "reloading skills failed; the previously loaded set is "
                    "still serving (%s: %s)", type(e).__name__, e)
                return False
            self._registry = registry
            # In place: the pipeline holds this matcher.
            self._matcher.registry = registry
            self._signature = signature
            set_active_registry(registry)
            logger.info("skills loaded: %d from %s",
                        len(registry.all()),
                        ", ".join(str(d) for d in dirs))
            return True


_PLANE: Optional[SkillPlane] = None
_PLANE_LOCK = threading.Lock()


def get_skill_plane(dirs: Optional[Iterable[Path]] = None) -> SkillPlane:
    """The process's skill plane, built on first use.

    ``dirs`` is honoured only on the build that creates it -- the daemon
    has one set of roots, and a later caller passing a different set would
    be a second source of truth about where skills come from.
    """
    global _PLANE
    with _PLANE_LOCK:
        if _PLANE is None:
            _PLANE = SkillPlane(dirs=dirs)
        return _PLANE


def reset_skill_plane() -> None:
    """Drop the process plane (tests, and a deliberate re-root)."""
    global _PLANE
    with _PLANE_LOCK:
        _PLANE = None
    set_active_registry(None)
