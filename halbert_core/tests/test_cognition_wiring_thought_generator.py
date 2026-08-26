# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""B4: the seam ModelBackend gets one real consumer — a ThoughtGenerator
passed into advance_turn — but only when HALBERT_LLM_THOUGHTS is enabled."""

from __future__ import annotations

import pytest

pytest.importorskip("haloysius")

import haloysius.persona.cognition_tick as ct  # noqa: E402
import haloysius.seam as hs  # noqa: E402
from haloysius.persona.thought_generator import ThoughtGenerator  # noqa: E402

from halbert_core.integrations import cognition_wiring  # noqa: E402
from halbert_core.integrations.app_seam import HalbertAppSeam  # noqa: E402


class _FakeModelBackend:
    def generate_text(self, prompt: str) -> str:
        return "thought"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    hs.clear_app_seam()
    monkeypatch.setattr(cognition_wiring, "_create_memory_adapter", lambda: None)
    monkeypatch.setattr(cognition_wiring, "_cognition", None)
    yield
    hs.clear_app_seam()
    monkeypatch.setattr(cognition_wiring, "_cognition", None)


def _record_advance_turn(monkeypatch):
    seen = {}

    def fake_advance_turn(**kwargs):
        seen.update(kwargs)
        return "result"

    monkeypatch.setattr(ct, "advance_turn", fake_advance_turn)
    return seen


def test_get_cognition_tick_passes_seam_thought_generator(monkeypatch):
    fake = _FakeModelBackend()
    hs.register_app_seam(HalbertAppSeam(model_backend=fake))
    monkeypatch.setenv("HALBERT_LLM_THOUGHTS", "1")
    seen = _record_advance_turn(monkeypatch)

    tick = cognition_wiring.get_cognition_tick()
    assert tick(object(), "u", "a") == "result"
    tg = seen["thought_generator"]
    assert isinstance(tg, ThoughtGenerator)
    assert tg.llm_generate == fake.generate_text
    assert seen["user_message"] == "u"
    assert seen["assistant_response"] == "a"


def test_get_cognition_tick_template_thoughts_by_default(monkeypatch):
    hs.register_app_seam(HalbertAppSeam(model_backend=_FakeModelBackend()))
    monkeypatch.delenv("HALBERT_LLM_THOUGHTS", raising=False)
    seen = _record_advance_turn(monkeypatch)

    cognition_wiring.get_cognition_tick()(object(), "u", "a")
    assert seen["thought_generator"] is None


def test_get_cognition_tick_none_when_no_model_backend(monkeypatch):
    hs.register_app_seam(HalbertAppSeam(model_backend=None))
    monkeypatch.setenv("HALBERT_LLM_THOUGHTS", "true")
    seen = _record_advance_turn(monkeypatch)

    cognition_wiring.get_cognition_tick()(object(), "u", "a")
    assert seen["thought_generator"] is None


def test_get_cognition_tick_wires_seam_first(monkeypatch):
    """Spec option (a): if no seam is registered, get_cognition_tick wires it."""
    import halbert_core.integrations.app_seam as app_seam

    wired = []

    def fake_wire(**kwargs):
        seam = HalbertAppSeam(model_backend=_FakeModelBackend())
        hs.register_app_seam(seam)
        wired.append(seam)
        return seam

    monkeypatch.setattr(app_seam, "wire_halbert_seam", fake_wire)
    monkeypatch.setenv("HALBERT_LLM_THOUGHTS", "yes")
    seen = _record_advance_turn(monkeypatch)

    cognition_wiring.get_cognition_tick()(object(), "u", "a")
    assert len(wired) == 1
    assert isinstance(seen["thought_generator"], ThoughtGenerator)

    # already registered -> not wired again
    cognition_wiring.get_cognition_tick()
    assert len(wired) == 1


def test_create_cognition_scene_context_is_platform_derived(monkeypatch):
    import halbert_core.utils.platform as plat

    monkeypatch.setattr(plat, "is_macos", lambda: True)
    monkeypatch.setattr(plat, "is_linux", lambda: False)
    assert cognition_wiring._create_cognition().scene_context == "macOS system administration"

    monkeypatch.setattr(plat, "is_macos", lambda: False)
    monkeypatch.setattr(plat, "is_linux", lambda: True)
    assert cognition_wiring._create_cognition().scene_context == "Linux system administration"

    monkeypatch.setattr(plat, "is_linux", lambda: False)
    assert cognition_wiring._create_cognition().scene_context == "system administration"
