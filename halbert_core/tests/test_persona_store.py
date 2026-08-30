# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for PersonaStore — directory-backed multi-persona management."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from halbert_core.persona.store import PersonaStore, PersonaSummary, _slugify


class TestSlugify:
    def test_basic(self):
        assert _slugify("Work Halbert") == "work-halbert"

    def test_special_chars(self):
        assert _slugify("My AI! @#$") == "my-ai"

    def test_empty(self):
        assert _slugify("") == "persona"

    def test_already_slug(self):
        assert _slugify("work-halbert") == "work-halbert"

    def test_numbers(self):
        assert _slugify("Persona 2") == "persona-2"


class TestPersonaStore:
    @pytest.fixture
    def store(self, tmp_path):
        """Create a PersonaStore with a temp config dir."""
        return PersonaStore(config_dir=tmp_path)

    def test_ensure_default_creates_default(self, store):
        """On first access, a default persona is created."""
        personas = store.list_personas()
        assert len(personas) == 1
        assert personas[0].id == "default"
        assert personas[0].active is True

    def test_being_yml_is_symlink(self, store):
        """After initialization, being.yml is a symlink to the active persona."""
        store.list_personas()
        assert store.being_yml.is_symlink()
        target = store.being_yml.resolve()
        assert target.name == "default.yml"
        assert target.parent == store.personas_dir.resolve()

    def test_create_persona(self, store):
        """Creating a persona adds it to the list."""
        store.list_personas()  # ensure default
        summary = store.create_persona("Work Halbert")
        assert summary.id == "work-halbert"
        assert summary.display_name == "Work Halbert"
        assert summary.active is False

        personas = store.list_personas()
        assert len(personas) == 2
        ids = [p.id for p in personas]
        assert "default" in ids
        assert "work-halbert" in ids

    def test_create_persona_unique_id(self, store):
        """Creating two personas with the same name gets unique ids."""
        store.list_personas()
        s1 = store.create_persona("Work")
        s2 = store.create_persona("Work")
        assert s1.id == "work"
        assert s2.id == "work-2"

    def test_activate_persona(self, store):
        """Activating a persona swaps the symlink."""
        store.list_personas()
        store.create_persona("Work")
        store.activate("work")

        assert store.get_active_id() == "work"
        assert store.being_yml.resolve().name == "work.yml"

        personas = store.list_personas()
        active = [p for p in personas if p.active]
        assert len(active) == 1
        assert active[0].id == "work"

    def test_activate_nonexistent_raises(self, store):
        store.list_personas()
        with pytest.raises(FileNotFoundError):
            store.activate("nonexistent")

    def test_delete_persona(self, store):
        store.list_personas()
        store.create_persona("Work")
        store.delete_persona("work")

        personas = store.list_personas()
        assert len(personas) == 1
        assert personas[0].id == "default"

    def test_cannot_delete_active(self, store):
        store.list_personas()
        store.create_persona("Work")
        with pytest.raises(ValueError, match="Cannot delete the active persona"):
            store.delete_persona("default")

    def test_cannot_delete_last(self, store):
        """Cannot delete when only one persona exists."""
        store.list_personas()  # creates default — only 1 persona
        store.create_persona("Work")
        store.activate("work")
        # Now delete default (non-active) — leaves 1, should succeed
        store.delete_persona("default")
        # Now only "work" exists — can't delete it (it's active AND it's last)
        with pytest.raises(ValueError, match="Cannot delete the active persona"):
            store.delete_persona("work")

    def test_get_persona(self, store):
        store.list_personas()
        store.create_persona("Work Halbert")
        config = store.get_persona("work-halbert")
        assert config["persona_id"] == "work-halbert"
        assert config["display_name"] == "Work Halbert"

    def test_get_persona_not_found(self, store):
        store.list_personas()
        with pytest.raises(FileNotFoundError):
            store.get_persona("nonexistent")

    def test_get_active_persona(self, store):
        store.list_personas()
        store.create_persona("Work")
        store.activate("work")
        config = store.get_active_persona()
        assert config["persona_id"] == "work"

    def test_update_persona(self, store):
        store.list_personas()
        store.update_persona("default", {"name": "My Halbert", "voice": "the_computer"})
        config = store.get_persona("default")
        assert config["name"] == "My Halbert"
        assert config["voice"] == "the_computer"
        # persona_id should not change
        assert config["persona_id"] == "default"

    def test_load_being_config_reads_through_symlink(self, store):
        """load_being_config() should read through the symlink transparently."""
        store.list_personas()
        store.update_persona("default", {"name": "Test Halbert", "voice": "first_person"})

        from halbert_core.config.being_config import load_being_config
        # Point load_being_config at our test being.yml
        cfg = load_being_config(str(store.being_yml))
        assert cfg.name == "Test Halbert"
        assert cfg.persona_id == "default"
        assert cfg.display_name == "Default"

    def test_switch_persona_hot_reload(self, store):
        """After switching, load_being_config reads the new persona."""
        store.list_personas()
        store.update_persona("default", {"name": "Default Halbert"})
        store.create_persona("Work")
        store.update_persona("work", {"name": "Work Halbert"})

        store.activate("work")

        from halbert_core.config.being_config import load_being_config
        cfg = load_being_config(str(store.being_yml))
        assert cfg.name == "Work Halbert"
        assert cfg.persona_id == "work"

    def test_save_being_config_writes_through_symlink(self, store):
        """save_being_config() should write through the symlink to the active persona file."""
        store.list_personas()

        from halbert_core.config.being_config import BeingConfig, save_being_config
        cfg = BeingConfig()
        cfg.name = "Saved Name"
        save_being_config(cfg, str(store.being_yml))

        # Read the persona file directly
        config = store.get_persona("default")
        assert config["name"] == "Saved Name"


class TestPersonaSummary:
    def test_to_dict(self):
        s = PersonaSummary(id="work", display_name="Work", created_at="2026-01-01", active=True)
        d = s.to_dict()
        assert d == {"id": "work", "display_name": "Work", "created_at": "2026-01-01", "active": True}
