# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One entity name everywhere — ``halbert_core.identity``.

The machine has one name: the one chosen in onboarding (preferences.yml
``ai_name``), mirrored into being.yml ``name``. The hostname is a body fact
and only ever a fallback. Every surface (greeting, Presence Pill, MCP
serverInfo, mDNS) resolves through this module, so these tests pin the
precedence once.
"""
from __future__ import annotations

import socket

import pytest
import yaml

from halbert_core import identity
from halbert_core.federation.peers_config import PeersConfig


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """An isolated config dir with none of the launch-time overrides set."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    for var in ("HALBERT_DISPLAY_NAME", "HALBERT_PERSONA_ID", "HALBERT_VARIANT"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _prefs(config_dir, **values):
    (config_dir / "preferences.yml").write_text(
        yaml.safe_dump(values, sort_keys=False), encoding="utf-8")


def _being(config_dir, text):
    (config_dir / "being.yml").write_text(text, encoding="utf-8")


class TestResolveEntityName:

    def test_the_onboarding_name_is_the_source(self, config_dir):
        _prefs(config_dir, ai_name="Macky-Mac")
        _being(config_dir, "name: Something Else\n")
        assert identity.resolve_entity_name("Erics-Mac-Studio.local") == "Macky-Mac"

    def test_the_being_name_when_onboarding_never_ran(self, config_dir):
        _being(config_dir, "name: Studio\n")
        assert identity.resolve_entity_name("Erics-Mac-Studio.local") == "Studio"

    def test_the_short_hostname_when_nothing_was_chosen(self, config_dir):
        assert identity.resolve_entity_name("Erics-Mac-Studio.local") == "Erics-Mac-Studio"

    def test_the_app_name_is_the_last_resort(self, config_dir):
        assert identity.resolve_entity_name("") == "Halbert"

    def test_blank_names_are_not_names(self, config_dir):
        _prefs(config_dir, ai_name="   ")
        _being(config_dir, "name: '  '\n")
        assert identity.resolve_entity_name("box.lan") == "box"

    def test_the_launch_override_wins_over_everything(self, config_dir, monkeypatch):
        _prefs(config_dir, ai_name="Macky-Mac")
        monkeypatch.setenv("HALBERT_DISPLAY_NAME", "Casa Halbert")
        assert identity.resolve_entity_name("box") == "Casa Halbert"

    def test_unreadable_config_files_are_not_fatal(self, config_dir):
        (config_dir / "preferences.yml").write_text("{{ not: valid: yaml")
        _being(config_dir, "{{ not: valid: yaml")
        assert identity.resolve_entity_name("box.lan") == "box"

    def test_defaults_to_this_machines_hostname(self, config_dir, monkeypatch):
        monkeypatch.setattr(socket, "gethostname", lambda: "nas.home")
        assert identity.resolve_entity_name() == "nas"


class TestResolveHostname:

    @pytest.mark.parametrize("hostname,expected", [
        ("Erics-Mac-Studio.local", "Erics-Mac-Studio"),
        ("box.lan", "box"),
        ("nas.home", "nas"),
        ("server.localdomain", "server"),
        ("plain", "plain"),
        ("has.dots.inside", "has.dots.inside"),
    ])
    def test_plumbing_suffixes_are_stripped(self, hostname, expected, monkeypatch):
        monkeypatch.setattr(socket, "gethostname", lambda: hostname)
        assert identity.resolve_hostname() == expected


class TestResolvePersonaId:

    def test_being_override_wins_over_env(self, config_dir, monkeypatch):
        _being(config_dir, "persona_id_override: shared\n")
        monkeypatch.setenv("HALBERT_PERSONA_ID", "home")
        assert identity.resolve_persona_id() == "shared"

    def test_env_when_no_override(self, config_dir, monkeypatch):
        monkeypatch.setenv("HALBERT_PERSONA_ID", "home")
        assert identity.resolve_persona_id() == "home"

    def test_default(self, config_dir):
        assert identity.resolve_persona_id() == "halbert"


class TestResolveBodyName:

    def test_being_body_name_wins(self, config_dir, monkeypatch):
        _being(config_dir, "body_name: desk\n")
        monkeypatch.setenv("HALBERT_VARIANT", "home")
        assert identity.resolve_body_name() == "desk"

    def test_variant_default(self, config_dir, monkeypatch):
        assert identity.resolve_body_name() == "workstation"
        monkeypatch.setenv("HALBERT_VARIANT", "home")
        assert identity.resolve_body_name() == "home"


class TestResolveEntityRole:
    """canonical | body | independent — defined on BOTH machines of a pair,
    not only on the body that proxies to the canonical host."""

    def _peers(self, config_dir):
        return PeersConfig(config_path=config_dir / "peers.json")

    def test_a_node_proxying_to_a_canonical_host_is_a_body(self, config_dir):
        _being(config_dir,
               "canonical_memory_url: http://n150.lan:8001/api/memory\n"
               "persona_id_override: shared\n")
        assert identity.resolve_entity_role(self._peers(config_dir).list_peers()) == "body"

    def test_a_host_with_a_paired_body_is_canonical(self, config_dir):
        peers = self._peers(config_dir)
        peers.add_peer(node_id="mac", node_name="Mac", role="body", raw_token="t" * 32)
        assert identity.resolve_entity_role(peers.list_peers()) == "canonical"

    def test_a_revoked_body_does_not_make_a_canonical_host(self, config_dir):
        peers = self._peers(config_dir)
        peers.add_peer(node_id="mac", node_name="Mac", role="body", raw_token="t" * 32)
        peers.revoke_peer("mac")
        assert identity.resolve_entity_role(peers.list_peers(include_revoked=True)) == "independent"

    def test_compute_providers_are_not_bodies(self, config_dir):
        peers = self._peers(config_dir)
        peers.add_peer(node_id="gpu", node_name="GPU box", role="compute_provider",
                       raw_token="t" * 32)
        assert identity.resolve_entity_role(peers.list_peers()) == "independent"

    def test_a_fresh_node_is_independent(self, config_dir, monkeypatch):
        peers = self._peers(config_dir)
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config", lambda: peers)
        assert identity.resolve_entity_role() == "independent"

    def test_the_canonical_url_wins_even_with_paired_bodies(self, config_dir):
        _being(config_dir,
               "canonical_memory_url: http://n150.lan:8001/api/memory\n"
               "persona_id_override: shared\n")
        peers = self._peers(config_dir)
        peers.add_peer(node_id="mac", node_name="Mac", role="body", raw_token="t" * 32)
        assert identity.resolve_entity_role(peers.list_peers()) == "body"


class TestWriteThrough:
    """ai_name is the source; being.yml name mirrors it. Both writers keep
    the other side in step so the two can never disagree."""

    def test_write_chosen_name_sets_ai_name_and_keeps_other_prefs(self, config_dir):
        _prefs(config_dir, user_name="Eric", ai_name="Old")
        identity.write_chosen_name("Macky-Mac")
        prefs = yaml.safe_load((config_dir / "preferences.yml").read_text())
        assert prefs["ai_name"] == "Macky-Mac"
        assert prefs["user_name"] == "Eric"
        assert identity.resolve_entity_name("box") == "Macky-Mac"

    def test_write_chosen_name_creates_preferences(self, config_dir):
        identity.write_chosen_name("Macky-Mac")
        assert identity.chosen_name() == "Macky-Mac"

    def test_mirror_name_to_being_sets_being_name(self, config_dir):
        _being(config_dir, "voice: hybrid\nbody_name: desk\n")
        identity.mirror_name_to_being("Macky-Mac")
        being = yaml.safe_load((config_dir / "being.yml").read_text())
        assert being["name"] == "Macky-Mac"
        assert being["voice"] == "hybrid"
        assert being["body_name"] == "desk"
        assert identity.being_name() == "Macky-Mac"
