# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R9-F04: enrolled voiceprints must reach the matcher that does the matching.

Enrollment wrote a CAM++ centroid to SpeakerProfileStore and stopped there.
The SpeakerEmbeddingManager that ``identify()`` actually searches is built
empty in ``SpeakerIdentifier._ensure_initialized`` and nothing ever put a
stored profile into it — so every household member came back unrecognised,
however many times they enrolled, and every voice turn ran at
``speaker_role="unknown"``.

sherpa-onnx is not installed here (the audio-inference extra), so these tests
stand in for the manager and assert the wiring rather than the maths.
"""
from __future__ import annotations

import struct

import pytest

from halbert_core.audio.speech.speaker_id import SpeakerIdentifier


class _FakeManager:
    """Stands in for sherpa_onnx.SpeakerEmbeddingManager."""

    def __init__(self):
        self.added: dict[str, list] = {}
        self.removed: list[str] = []

    def add(self, speaker_id, embeddings):
        self.added[speaker_id] = embeddings

    def remove(self, speaker_id):
        self.removed.append(speaker_id)
        return self.added.pop(speaker_id, None) is not None


class _FakeProfile:
    def __init__(self, speaker_id, embedding):
        self.speaker_id = speaker_id
        self._embedding = embedding

    def embedding_as_list(self):
        return list(self._embedding)


class _FakeStore:
    def __init__(self, profiles):
        self._profiles = profiles

    def list_all(self):
        return self._profiles


def _identifier_with_fake_manager():
    ident = SpeakerIdentifier()
    ident._manager = _FakeManager()
    ident._initialized = True  # skip the sherpa-onnx import
    return ident


class TestEnrolledProfilesReachTheMatcher:

    def test_stored_profiles_are_loaded(self):
        ident = _identifier_with_fake_manager()
        store = _FakeStore([
            _FakeProfile("sp-1", [0.1] * 256),
            _FakeProfile("sp-2", [0.2] * 256),
        ])

        assert ident.load_enrolled_profiles(store=store) == 2
        assert set(ident._manager.added) == {"sp-1", "sp-2"}
        assert ident._manager.added["sp-1"] == [[0.1] * 256]

    def test_an_unreadable_store_does_not_break_startup(self):
        ident = _identifier_with_fake_manager()

        class _Broken:
            def list_all(self):
                raise RuntimeError("speaker_profiles.db is locked")

        assert ident.load_enrolled_profiles(store=_Broken()) == 0
        assert ident._manager.added == {}

    def test_one_bad_profile_does_not_stop_the_others(self):
        ident = _identifier_with_fake_manager()

        class _BadProfile:
            speaker_id = "sp-bad"

            def embedding_as_list(self):
                raise ValueError("truncated centroid")

        store = _FakeStore([_BadProfile(), _FakeProfile("sp-ok", [0.3] * 256)])
        assert ident.load_enrolled_profiles(store=store) == 1
        assert set(ident._manager.added) == {"sp-ok"}

    def test_a_new_enrolment_is_registered_without_a_restart(self):
        ident = _identifier_with_fake_manager()
        assert ident.register_profile("sp-9", [0.5] * 256) is True
        assert ident._manager.added["sp-9"] == [[0.5] * 256]

    def test_registering_survives_a_matcher_that_refuses(self):
        ident = _identifier_with_fake_manager()

        def _boom(speaker_id, embeddings):
            raise RuntimeError("dimension mismatch")

        ident._manager.add = _boom
        assert ident.register_profile("sp-9", [0.5] * 256) is False


class TestEnrollmentRouteKeepsTheLiveMatcherInStep:
    """The route half: a speaker enrolled or deleted through the API must be
    recognised, or forgotten, on the next turn — not the next restart."""

    def test_the_route_registers_into_a_running_pipeline(self, monkeypatch, tmp_path):
        from halbert_core.dashboard.routes import audio as audio_routes

        ident = _identifier_with_fake_manager()

        class _RunningPipeline:
            _speaker_id = ident

        audio_routes.set_audio_pipeline(_RunningPipeline())
        try:
            running = audio_routes.get_audio_pipeline()
            live = getattr(running, "_speaker_id", None)
            assert live is ident
            live.register_profile("sp-new", [0.7] * 256)
            assert "sp-new" in ident._manager.added
        finally:
            audio_routes.set_audio_pipeline(None)

    def test_no_running_pipeline_is_not_an_error(self):
        from halbert_core.dashboard.routes import audio as audio_routes

        audio_routes.set_audio_pipeline(None)
        running = audio_routes.get_audio_pipeline()
        assert getattr(running, "_speaker_id", None) is None
