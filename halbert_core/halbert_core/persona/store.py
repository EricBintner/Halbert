# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Persona store — directory-backed multi-persona management.

Each persona is a YAML file in ``~/.config/halbert/personas/``.
``being.yml`` is a symlink pointing to the active persona file.

This is transparent to all existing ``load_being_config()`` callers:
they read ``being.yml`` as before, never knowing it's a symlink.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..utils.platform import get_config_dir

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a display name to a filesystem-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "persona"


# Reserved ids that conflict with API route paths.
_RESERVED_IDS = {"status", "list", "switch", "memory"}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class PersonaSummary:
    """Lightweight persona info for listing."""
    id: str
    display_name: str
    created_at: str
    active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "active": self.active,
        }


class PersonaStore:
    """Manages persona files in a directory with a symlink to the active one.

    Layout::

        config_dir/
          being.yml          → symlink → personas/<active>.yml
          personas/
            default.yml
            work.yml
            ...

    The symlink makes ``load_being_config()`` transparent — it reads
    ``being.yml`` and gets whichever persona is active.
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = Path(config_dir) if config_dir else get_config_dir()
        self.personas_dir = self.config_dir / "personas"
        self.being_yml = self.config_dir / "being.yml"

    # ── internal helpers ──────────────────────────────────────────────

    def _persona_path(self, persona_id: str) -> Path:
        return self.personas_dir / f"{persona_id}.yml"

    def _read_persona_file(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _write_persona_file(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in data.items() if v is not None and v != ""}
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".yml.tmp", prefix=".persona_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(clean, f, default_flow_style=False, sort_keys=False)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _resolve_symlink_target(self) -> Optional[Path]:
        """Return the persona file that being.yml points to, or None."""
        if self.being_yml.is_symlink():
            return self.being_yml.resolve()
        if self.being_yml.exists():
            # Not a symlink — could be a fresh install or pre-migration.
            # Treat it as an implicit "default" persona.
            return self.being_yml
        return None

    def _active_id(self) -> Optional[str]:
        """Get the active persona id from the symlink target."""
        target = self._resolve_symlink_target()
        if target is None:
            return None
        # If it's in personas/, the stem is the id.
        if target.parent == self.personas_dir.resolve():
            return target.stem
        # If it's being.yml itself (not a symlink), there's no persona dir yet.
        return None

    def _ensure_default(self) -> str:
        """Ensure at least the default persona exists. Returns its id."""
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        default_path = self._persona_path("default")
        if not default_path.exists():
            # Create a minimal default persona.
            data = {
                "persona_id": "default",
                "display_name": "Default",
                "created_at": _now_iso(),
            }
            self._write_persona_file(default_path, data)
            logger.info("Created default persona at %s", default_path)
        # Ensure symlink points to it if nothing is set.
        if not self.being_yml.exists():
            self._set_symlink("default")
        return "default"

    def _set_symlink(self, persona_id: str) -> None:
        """Point being.yml at the given persona file."""
        target = self._persona_path(persona_id)
        if not target.exists():
            raise FileNotFoundError(f"Persona file not found: {target}")
        # Atomic symlink swap: create temp symlink, then rename over old one.
        tmp_link = self.being_yml.with_name(".being.yml.tmp-link")
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()
        tmp_link.symlink_to(target)
        os.replace(str(tmp_link), str(self.being_yml))
        logger.info("Active persona → %s", persona_id)

    # ── public API ────────────────────────────────────────────────────

    def list_personas(self) -> List[PersonaSummary]:
        """List all personas, marking the active one."""
        self._ensure_default()
        active_id = self._active_id() or "default"
        summaries: List[PersonaSummary] = []
        for path in sorted(self.personas_dir.glob("*.yml")):
            try:
                data = self._read_persona_file(path)
            except Exception as e:
                logger.warning("Failed to read persona %s: %s", path, e)
                continue
            summaries.append(PersonaSummary(
                id=path.stem,
                display_name=data.get("display_name", path.stem),
                created_at=data.get("created_at", ""),
                active=(path.stem == active_id),
            ))
        return summaries

    def get_persona(self, persona_id: str) -> Dict[str, Any]:
        """Get the full config for a persona."""
        path = self._persona_path(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")
        return self._read_persona_file(path)

    def get_active_persona(self) -> Dict[str, Any]:
        """Get the full config for the active persona."""
        active_id = self._active_id()
        if active_id is None:
            # No symlink — ensure default exists and return it.
            active_id = self._ensure_default()
        return self.get_persona(active_id)

    def get_active_id(self) -> str:
        """Get the active persona id."""
        return self._active_id() or self._ensure_default()

    def create_persona(self, display_name: str) -> PersonaSummary:
        """Create a new persona with default settings.

        Returns the summary of the new persona.
        """
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        persona_id = _slugify(display_name)
        # Ensure unique id, skipping reserved ids that conflict with routes.
        base_id = persona_id
        counter = 2
        while persona_id in _RESERVED_IDS or self._persona_path(persona_id).exists():
            persona_id = f"{base_id}-{counter}"
            counter += 1
        path = self._persona_path(persona_id)
        data = {
            "persona_id": persona_id,
            "display_name": display_name,
            "created_at": _now_iso(),
        }
        self._write_persona_file(path, data)
        logger.info("Created persona '%s' (%s) at %s", display_name, persona_id, path)
        return PersonaSummary(
            id=persona_id,
            display_name=display_name,
            created_at=data["created_at"],
            active=False,
        )

    def update_persona(self, persona_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on a persona. Merges into existing data."""
        path = self._persona_path(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")
        data = self._read_persona_file(path)
        data.update(updates)
        # Don't allow changing the id or created_at via updates.
        data["persona_id"] = persona_id
        self._write_persona_file(path, data)
        return data

    def delete_persona(self, persona_id: str) -> None:
        """Delete a persona. Cannot delete the active persona or the last one."""
        active_id = self.get_active_id()
        if persona_id == active_id:
            raise ValueError("Cannot delete the active persona")
        path = self._persona_path(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")
        # Count personas — must keep at least one.
        personas = list(self.personas_dir.glob("*.yml"))
        if len(personas) <= 1:
            raise ValueError("Cannot delete the last persona")
        path.unlink()
        logger.info("Deleted persona '%s'", persona_id)

    def activate(self, persona_id: str) -> None:
        """Switch the active persona by swapping the symlink."""
        path = self._persona_path(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")
        self._set_symlink(persona_id)
