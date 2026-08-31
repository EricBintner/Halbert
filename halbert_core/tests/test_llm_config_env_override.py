# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""halbert_core.model.llm_config — the HALBERT_MODEL env override (TASK-01).

``HALBERT_MODEL`` is the per-instance deployment dial (e.g. an
``Environment=HALBERT_MODEL=...`` line in a systemd unit): it names the model
that serves the chat slot when models.yml does not configure one.

Rules (TASK-PACKET-01 Task 1.1, verified 2026-08-30):
  1. Only fills an UNCONFIGURED ``chat_model`` — a models.yml slot wins.
  2. Only the chat slot; specialist/vision/secure are untouched.
  3. Main/sysadmin variants only — home/home-light have no local model to
     override (their chat/specialist slots resolve to the compute peer).
"""
import pytest

from halbert_core.model import llm_config as store


@pytest.fixture(autouse=True)
def _explicit_variant_none(monkeypatch):
    """No being.yml variant — the resolution chain falls through to env.

    The developer's real being.yml must not leak into these tests.
    """
    monkeypatch.setattr(
        "halbert_core.config.being_config.explicit_variant", lambda: None
    )
    monkeypatch.setenv("HALBERT_VARIANT", "sysadmin")


class TestHalbertModelOverride:
    def test_env_fills_unconfigured_chat_slot(self, models_config_dir):
        # models_config_dir guarantees no models.yml — nothing is configured.
        assert store.load()["chat_model"]["enabled"] is False
        import os

        os.environ["HALBERT_MODEL"] = "qwen3:4b"
        try:
            resolved = store.resolve("chat_model")
        finally:
            del os.environ["HALBERT_MODEL"]
        assert resolved is not None
        assert resolved.model == "qwen3:4b"
        assert resolved.provider == "ollama"
        assert resolved.url == store.DEFAULT_OLLAMA_URL

    def test_models_yml_slot_wins_over_env(self, models_config_dir):
        import os

        ep_id = store.ensure_endpoint(store.DEFAULT_OLLAMA_URL, "ollama", "Local Ollama")
        store.set_slot("chat_model", "configured-model", ep_id)
        os.environ["HALBERT_MODEL"] = "env-model"
        try:
            resolved = store.resolve("chat_model")
        finally:
            del os.environ["HALBERT_MODEL"]
        assert resolved.model == "configured-model"

    def test_only_chat_slot_is_filled(self, models_config_dir):
        import os

        os.environ["HALBERT_MODEL"] = "qwen3:4b"
        try:
            for slot in ("specialist_model", "vision_model", "secure_model"):
                assert store.resolve(slot) is None
        finally:
            del os.environ["HALBERT_MODEL"]

    def test_home_variant_has_no_local_override(self, models_config_dir):
        import os

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "halbert_core.config.being_config.explicit_variant", lambda: "home"
        )
        os.environ["HALBERT_MODEL"] = "qwen3:4b"
        try:
            assert store.resolve("chat_model") is None
        finally:
            del os.environ["HALBERT_MODEL"]
            monkeypatch.undo()

    def test_client_get_configured_model_sees_override(self, models_config_dir):
        import os

        from halbert_core.model import client

        os.environ["HALBERT_MODEL"] = "qwen3:4b"
        try:
            assert client.get_configured_model() == "qwen3:4b"
        finally:
            del os.environ["HALBERT_MODEL"]
        # And with the env gone again, the override disappears.
        assert client.get_configured_model() == ""