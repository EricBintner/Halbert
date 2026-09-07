# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The utility slot — a per-provider-resolved cheap model for internal side tasks.

D-7 (OSS lift program, packet 04-C2 unblocker). The blueprint is Hermes's
ProviderProfile mechanism ("a hardcoded cheap-model ID rots") realised on
Halbert's slot model: the utility model is resolved, not hardcoded, through a
fail-soft ladder. Every rung here is exercised; every missing rung falls
through; and the ladder's floor is the chat slot — unset means callers fall
back to the model they already run, exactly as the lift packet requires.
"""

import re
from pathlib import Path

import pytest
import yaml

from halbert_core.model import llm_config as store
from halbert_core.model import utility_slot as aux
from halbert_core.model.config_layers import set_session_slot
from halbert_core.model.utility_slot import AuxSource

OLLAMA = "http://localhost:11434"
LOCAL_EP = {"id": "e_local", "name": "Local Ollama", "provider": "ollama",
            "url": OLLAMA, "api_key": ""}


def _write(models_config_dir: Path, llm: dict) -> None:
    p = models_config_dir / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({"llm_config": llm}))


def _configured(models_config_dir: Path, **slots: dict) -> None:
    llm = {"saved_endpoints": [LOCAL_EP]}
    for slot, value in slots.items():
        if value is None:
            llm[slot] = {"enabled": False, "endpoint_id": "", "model": ""}
        elif isinstance(value, tuple):
            llm[slot] = {"enabled": True, "endpoint_id": value[0], "model": value[1]}
        else:
            llm[slot] = value
    _write(models_config_dir, llm)


# ── The slot exists ───────────────────────────────────────────────


class TestUtilitySlotExists:
    def test_utility_model_is_a_slot(self):
        """Additive: chat/specialist/vision/secure keep their positions."""
        assert store.SLOTS == (
            "chat_model", "specialist_model", "vision_model",
            "secure_model", "utility_model",
        )

    def test_defaults_carry_an_empty_utility_slot(self):
        assert store.default_llm_config()["utility_model"] == {
            "enabled": False, "endpoint_id": "", "model": "",
        }

    def test_unset_utility_slot_resolves_to_none(self, models_config_dir):
        """Fail-soft floor: unset means None, callers fall back to the chat slot."""
        _configured(models_config_dir,
                    chat_model=("e_local", "chat-a"), utility_model=None)
        assert store.resolve("utility_model") is None

    def test_set_slot_round_trips_through_the_store(self, models_config_dir):
        _configured(models_config_dir,
                    chat_model=("e_local", "chat-a"), utility_model=None)
        store.set_slot("utility_model", "small-a", "e_local")
        resolved = store.resolve("utility_model")
        assert (resolved.model, resolved.provider) == ("small-a", "ollama")

    def test_unknown_endpoint_disables_the_slot(self, models_config_dir):
        _configured(models_config_dir,
                    utility_model={"enabled": True, "endpoint_id": "e_ghost",
                                   "model": "small-a"})
        assert store.load()["utility_model"]["enabled"] is False

    def test_session_pin_reaches_the_utility_slot(self, models_config_dir):
        """The slot machinery (layers) treats the fifth slot like any other."""
        _configured(models_config_dir, utility_model=None)
        from halbert_core.model import config_layers as layers
        layers.set_session_slot("s1", "utility_model", "small-a", "e_local")
        resolved = store.resolve("utility_model", "s1")
        assert resolved is not None and resolved.model == "small-a"


# ── The ladder: rung by rung ──────────────────────────────────────


class TestDeclaredRung:
    """The operator's own declaration always wins — no heuristic overrides it."""

    def test_declared_slot_wins_even_with_prefer_fast(self, models_config_dir, monkeypatch):
        _configured(models_config_dir,
                    chat_model=("e_local", "family-a:32b"),
                    utility_model=("e_local", "small-a"))
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("catalog must not be probed"))
        resolved, source = aux._resolve_aux(prefer_fast=True)
        assert (resolved.model, source) == ("small-a", AuxSource.DECLARED)


class TestCatalogRung:
    """Live-catalog family match — attempted only on a per-task prefer_fast opt-in."""

    @staticmethod
    def _catalog(url, provider, api_key=""):
        assert provider == "ollama"
        return [
            {"name": "family-a:32b", "details": {"parameter_size": "32B"}},
            {"name": "family-a:3b", "details": {"parameter_size": "3B"}},
            {"name": "family-a:8b", "details": {"parameter_size": "8B"}},
            {"name": "other-b:7b", "details": {"parameter_size": "7B"}},
            {"name": "text-embed:0b", "details": {"parameter_size": "0B"}},
        ]

    def _anchor_file(self, models_config_dir):
        _configured(models_config_dir, chat_model=("e_local", "family-a:32b"),
                    utility_model=None)

    def test_prefer_fast_finds_the_smallest_family_match(self, models_config_dir, monkeypatch):
        self._anchor_file(models_config_dir)
        monkeypatch.setattr(aux, "_fetch_catalog", self._catalog)
        resolved, source = aux._resolve_aux(task="title", prefer_fast=True)
        assert source == AuxSource.CATALOG
        assert resolved.model == "family-a:3b"
        assert resolved.provider == "ollama"

    def test_prefer_fast_defaults_to_false_and_never_probes(self, models_config_dir, monkeypatch):
        """The default ladder costs no round-trip: no opt-in, no probe."""
        self._anchor_file(models_config_dir)
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("no probe without prefer_fast"))
        resolved, source = aux._resolve_aux()
        assert source == AuxSource.CHAT
        assert resolved.model == "family-a:32b"

    def test_no_family_match_falls_through_to_the_chat_floor(self, models_config_dir, monkeypatch):
        self._anchor_file(models_config_dir)
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: [{"name": "other-b:1b",
                                              "details": {"parameter_size": "1B"}}])
        resolved, source = aux._resolve_aux(prefer_fast=True)
        assert source == AuxSource.CHAT

    def test_catalog_failure_falls_through_fail_soft(self, models_config_dir, monkeypatch):
        self._anchor_file(models_config_dir)
        def _boom(url, provider, api_key=""):
            raise OSError("endpoint down")
        monkeypatch.setattr(aux, "_fetch_catalog", _boom)
        resolved, source = aux._resolve_aux(prefer_fast=True)
        assert source == AuxSource.CHAT
        assert resolved.model == "family-a:32b"

    def test_anchor_falls_back_to_specialist_when_chat_is_unset(self, models_config_dir, monkeypatch):
        _configured(models_config_dir,
                    chat_model=None, specialist_model=("e_local", "spec-a:14b"),
                    utility_model=None)
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda url, provider, api_key="": [{"name": "spec-a:3b",
                                                    "details": {"parameter_size": "3B"}}])
        resolved, source = aux._resolve_aux(prefer_fast=True)
        assert source == AuxSource.CATALOG
        assert resolved.model == "spec-a:3b"

    def test_smaller_anchor_never_downgrades_to_itself(self, models_config_dir, monkeypatch):
        """The catalog rung must return a STRICTLY cheaper model or nothing."""
        self._anchor_file(models_config_dir)
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda url, provider, api_key="": [{"name": "family-a:32b",
                                                    "details": {"parameter_size": "32B"}}])
        resolved, source = aux._resolve_aux(prefer_fast=True)
        assert source == AuxSource.CHAT


class TestLegacyRung:
    """A pre-migration small_model entry — the legacy dict rung — still serves."""

    @staticmethod
    def _raw(models_config_dir: Path, data: dict) -> None:
        p = models_config_dir / "models.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(data))

    def test_legacy_small_model_dict_is_used_when_the_ladder_misses(self, models_config_dir, monkeypatch):
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("no probe without prefer_fast"))
        # Written pre-migration: llm_config carries the SourcePrep-shaped key.
        self._raw(models_config_dir, {
            "llm_config": {
                "saved_endpoints": [LOCAL_EP],
                "chat_model": {"enabled": False, "endpoint_id": "", "model": ""},
                "small_model": {"enabled": True, "model": "old-small",
                                "endpoint_id": "e_local"},
            },
        })
        resolved, source = aux._resolve_aux()
        assert source == AuxSource.LEGACY
        assert (resolved.model, resolved.provider) == ("old-small", "ollama")

    def test_legacy_string_shape_resolves_against_the_chat_endpoint(self, models_config_dir):
        self._raw(models_config_dir, {
            "llm_config": {
                "saved_endpoints": [LOCAL_EP],
                "small_model": "old-small",
            },
        })
        resolved, source = aux._resolve_aux()
        assert source == AuxSource.LEGACY
        assert resolved.model == "old-small"

    def test_legacy_rung_fires_before_the_chat_floor(self, models_config_dir):
        """Order: the legacy dict is consulted before the curated chat floor."""
        self._raw(models_config_dir, {
            "llm_config": {
                "saved_endpoints": [LOCAL_EP],
                "chat_model": {"enabled": True, "endpoint_id": "e_local",
                               "model": "chat-a"},
                "small_model": {"enabled": True, "model": "old-small",
                                "endpoint_id": "e_local"},
            },
        })
        resolved, source = aux._resolve_aux()
        assert source == AuxSource.LEGACY


class TestChatFloor:
    """The curated default, name-neutrally: the operator's own chat model."""

    def test_unset_utility_slot_serves_the_chat_model(self, models_config_dir, monkeypatch):
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("no probe without prefer_fast"))
        _configured(models_config_dir, chat_model=("e_local", "chat-a"),
                    utility_model=None)
        resolved, source = aux._resolve_aux()
        assert source == AuxSource.CHAT
        assert resolved.model == "chat-a"

    def test_everything_unset_returns_none(self, models_config_dir):
        _configured(models_config_dir, chat_model=None, utility_model=None)
        assert aux._resolve_aux() == (None, AuxSource.NONE)

    def test_caller_falls_back_to_the_chat_slot(self, models_config_dir):
        """The documented fail-soft: unset -> caller falls back to the chat slot."""
        _configured(models_config_dir, chat_model=("e_local", "chat-a"),
                    utility_model=None)
        resolved = aux.resolve_aux_model()
        chat = store.resolve("chat_model")
        assert (resolved.model, resolved.url) == (chat.model, chat.url)


# ── Broken worlds ─────────────────────────────────────────────────


class TestFailSoft:
    @staticmethod
    def _touch(models_config_dir: Path, text: str) -> None:
        p = models_config_dir / "models.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_unparsable_file_yields_none(self, models_config_dir, monkeypatch):
        self._touch(models_config_dir, "{ not: parsable: yaml: [")
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("must not probe a broken file"))
        assert aux.resolve_aux_model() is None

    def test_no_file_at_all_yields_none(self, models_config_dir, monkeypatch):
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda *a, **k: pytest.fail("must not probe with no file"))
        assert aux.resolve_aux_model() is None


# ── Founder directives ────────────────────────────────────────────


class TestNoModelNames:
    """Halbert names no AI model (standing founder directive).

    The utility ladder was built precisely so no curated model ID is baked
    into source — every rung resolves from the operator's own runtime or
    config. This re-derives the standing guard's family pattern against this
    module, so the new code cannot be the first offender.
    """

    FAMILIES = [
        "llama", "llama2", "llama3", "tinyllama", "codellama", "deepseek", "qwen",
        "mistral", "mixtral", "gemma", "phi-3", "falcon", "vicuna", "llava",
        "gpt-4", "gpt-3.5", "claude", "nomic-embed", "starcoder", "wizardlm", "orca",
    ]

    def test_the_ladder_module_names_no_model(self):
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(f) for f in self.FAMILIES) + r")\b", re.I
        )
        source = Path(aux.__file__).read_text()
        assert not pattern.search(source), pattern.search(source)

    def test_resolution_output_is_never_baked_in(self, models_config_dir, monkeypatch):
        """Whatever the ladder returns came from config, the catalog, or chat."""
        _configured(models_config_dir, chat_model=("e_local", "family-a:32b"),
                    utility_model=None)
        monkeypatch.setattr(aux, "_fetch_catalog",
                            lambda url, provider, api_key="": [{"name": "family-a:3b",
                                                    "details": {"parameter_size": "3B"}}])
        resolved = aux.resolve_aux_model(prefer_fast=True)
        # Every field is traceable to the saved endpoint or a live listing —
        # nothing here is a constant in Halbert's source.
        assert resolved.model in {"family-a:32b", "family-a:3b"}