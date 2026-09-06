# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vision source registry — VIS-1 phase A.

`.handoff/DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md`. What these pin: an id
is stable while its native is not, a Frigate camera whose name has a space can
still be handed to a guest, the two old scalars migrate without loss, and a
malformed entry is dropped rather than taking the whole config with it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from halbert_core.persona.private_sources import _SOURCE_ID
from halbert_core.vision import sources as S


def _cfg(monitor=1, camera=0, screen_on=True, cam_on=False, declared=None):
    return SimpleNamespace(
        screen_capture=SimpleNamespace(monitor_index=monitor, enabled=screen_on),
        webcam=SimpleNamespace(camera_index=camera, enabled=cam_on),
        sources=declared or [],
    )


class TestIds:
    def test_index_zero_is_not_swallowed(self):
        """0 is falsy and is the commonest camera there is."""
        assert S.source_id(S.KIND_WEBCAM, 0) == "webcam:0"
        assert S.source_id(S.KIND_SCREEN, 0) == "screen:0"

    def test_a_camera_named_with_a_space_still_gets_an_id(self):
        """Frigate allows "Front Door"; the id grammar does not."""
        sid = S.frigate_source_id("Front Door")
        assert sid == "frigate:front_door"
        assert _SOURCE_ID.match(sid)

    def test_every_minted_id_is_assignable_to_a_guest(self):
        """The registry and private_sources must agree, or a handed-over
        source routes under one id and is looked up under another."""
        for sid in (
            S.source_id(S.KIND_SCREEN, 1),
            S.source_id(S.KIND_WEBCAM, 0),
            S.frigate_source_id("Back Yard / Gate"),
            S.frigate_source_id("caméra"),
        ):
            assert _SOURCE_ID.match(sid), sid

    def test_an_empty_camera_name_yields_no_id(self):
        assert S.frigate_source_id("") == ""
        assert S.frigate_source_id("   ") == ""

    def test_an_unknown_kind_is_refused(self):
        with pytest.raises(S.BadSourceId):
            S.source_id("thermal", 0)


class TestMigration:
    def test_the_two_scalars_become_two_sources(self):
        got = S.sources_from_config(_cfg(monitor=2, camera=1))
        assert [s.id for s in got] == ["screen:2", "webcam:1"]
        assert [s.native for s in got] == ["2", "1"]

    def test_migration_carries_the_enable_flags(self):
        got = S.sources_from_config(_cfg(screen_on=True, cam_on=False))
        by_id = {s.id: s for s in got}
        assert by_id["screen:1"].enabled is True
        assert by_id["webcam:0"].enabled is False

    def test_migration_invents_nothing(self):
        """Three monitors still yield one declared screen: one is all the old
        config could express, and probing for the rest is a claim we did not
        earn."""
        assert len(S.sources_from_config(_cfg())) == 2

    def test_declared_sources_win_over_the_scalars(self):
        declared = [{"id": "webcam:desk", "label": "Desk", "kind": "webcam", "native": "2"}]
        got = S.sources_from_config(_cfg(declared=declared))
        assert [s.id for s in got] == ["webcam:desk"]
        assert got[0].native == "2"

    def test_the_id_is_stable_while_the_native_moves(self):
        """Replug a webcam and the index changes; the persona still means the
        same camera."""
        before = S.sources_from_config(_cfg(declared=[
            {"id": "webcam:desk", "label": "Desk", "kind": "webcam", "native": "0"}]))
        after = S.sources_from_config(_cfg(declared=[
            {"id": "webcam:desk", "label": "Desk", "kind": "webcam", "native": "3"}]))
        assert before[0].id == after[0].id
        assert before[0].native != after[0].native


class TestMalformedEntries:
    def test_a_bad_entry_is_dropped_not_fatal(self):
        got = S.sources_from_config(_cfg(declared=[
            {"kind": "nonsense", "native": "x"},
            {"id": "webcam:desk", "kind": "webcam", "native": "0"},
        ]))
        assert [s.id for s in got] == ["webcam:desk"]

    def test_a_duplicate_id_is_ignored(self):
        got = S.sources_from_config(_cfg(declared=[
            {"id": "webcam:desk", "kind": "webcam", "native": "0"},
            {"id": "webcam:desk", "kind": "webcam", "native": "9"},
        ]))
        assert len(got) == 1
        assert got[0].native == "0"

    def test_a_missing_id_is_derived_from_the_native(self):
        got = S.sources_from_config(_cfg(declared=[{"kind": "frigate", "native": "Front Door"}]))
        assert got[0].id == "frigate:front_door"

    def test_a_missing_label_falls_back_to_the_id(self):
        got = S.sources_from_config(_cfg(declared=[{"kind": "webcam", "native": "0"}]))
        assert got[0].label == "webcam:0"


class TestPersistence:
    def test_sources_survive_a_save_load_round_trip(self, tmp_path, monkeypatch):
        """save_config rewrites the whole file, so a key it does not write is
        lost on the next settings change."""
        from halbert_core.vision import config as vcfg

        path = tmp_path / "vision_config.yml"
        monkeypatch.setattr(vcfg, "_config_path", lambda: path)

        cfg = vcfg.VisionConfig()
        cfg.sources = [
            S.VisionSource(id="webcam:desk", label="Desk", kind="webcam", native="0").to_dict()
        ]
        vcfg.save_config(cfg)

        again = vcfg.load_config()
        assert [s["id"] for s in again.sources] == ["webcam:desk"]

    def test_a_config_with_no_sources_key_still_migrates(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as vcfg

        path = tmp_path / "vision_config.yml"
        path.write_text("webcam:\n  enabled: true\n  camera_index: 2\n")
        monkeypatch.setattr(vcfg, "_config_path", lambda: path)

        loaded = vcfg.load_config()
        assert loaded.sources == []
        assert [s.id for s in S.sources_from_config(loaded)] == ["screen:1", "webcam:2"]


class TestResolve:
    def test_an_unknown_id_raises_rather_than_substituting(self, monkeypatch):
        monkeypatch.setattr(S, "list_sources", lambda **k: [])
        with pytest.raises(S.UnknownSource):
            S.resolve_source("webcam:desk")

    def test_a_failing_capture_raises_unavailable(self, monkeypatch):
        src = S.VisionSource(id="webcam:desk", label="Desk", kind="webcam", native="0")
        monkeypatch.setattr(S, "list_sources", lambda **k: [src])

        class _Boom:
            def __init__(self, **kwargs):
                pass

            def grab_frame(self):
                raise RuntimeError("camera in use")

        import halbert_core.vision.webcam_capture as wc
        monkeypatch.setattr(wc, "WebcamCapture", _Boom)
        with pytest.raises(S.SourceUnavailable):
            S.resolve_source("webcam:desk")

    def test_the_frame_comes_from_the_source_that_was_asked_for(self, monkeypatch):
        seen = {}
        src = S.VisionSource(id="webcam:desk", label="Desk", kind="webcam", native="3")
        monkeypatch.setattr(S, "list_sources", lambda **k: [src])

        class _Cam:
            def __init__(self, camera_index=0, **kwargs):
                seen["index"] = camera_index

            def grab_frame(self):
                return b"jpeg"

        import halbert_core.vision.webcam_capture as wc
        monkeypatch.setattr(wc, "WebcamCapture", _Cam)
        assert S.resolve_source("webcam:desk") == b"jpeg"
        assert seen["index"] == 3


class TestEnabledCeiling:
    def test_only_enabled_sources_are_the_ceiling(self, monkeypatch):
        from halbert_core.vision import config as vcfg
        cfg = vcfg.VisionConfig()
        cfg.screen_capture.enabled = True
        cfg.webcam.enabled = True
        monkeypatch.setattr(vcfg, "load_config", lambda: cfg)
        monkeypatch.setattr(S, "list_sources", lambda **k: [
            S.VisionSource(id="webcam:desk", label="d", kind="webcam", native="0", enabled=True),
            S.VisionSource(id="screen:1", label="s", kind="screen", native="1", enabled=False),
        ])
        assert S.enabled_source_ids() == ["webcam:desk"]

    def test_the_global_switch_is_a_ceiling_the_per_source_flag_cannot_lift(self, monkeypatch):
        """The two switches are written by different controls and drift the
        moment either is edited alone; the stricter one wins."""
        from halbert_core.vision import config as vcfg
        cfg = vcfg.VisionConfig()
        cfg.screen_capture.enabled = False
        cfg.webcam.enabled = True
        monkeypatch.setattr(vcfg, "load_config", lambda: cfg)
        monkeypatch.setattr(S, "list_sources", lambda **k: [
            S.VisionSource(id="screen:1", label="s", kind="screen", native="1", enabled=True),
            S.VisionSource(id="webcam:0", label="w", kind="webcam", native="0", enabled=True),
        ])
        assert S.enabled_source_ids() == ["webcam:0"]


class TestNativeIsAnIndex:
    def test_a_free_text_native_is_refused_at_the_door(self):
        """Every consumer does int(src.native) outside the try that catches
        capture errors, so this is a crash rather than a bad picture."""
        with pytest.raises(S.BadSourceId):
            S.VisionSource.from_dict({"kind": "webcam", "native": "the good one", "id": "webcam:desk"})

    def test_a_frigate_native_is_a_name_not_an_index(self):
        src = S.VisionSource.from_dict({"kind": "frigate", "native": "Front Door"})
        assert src.native == "Front Door"

    def test_a_declared_source_shadows_the_frigate_copy(self, monkeypatch):
        """_frigate_sources hardcodes enabled=True, so without deduping a
        camera switched off here is shadowed by an always-enabled copy."""
        declared = [{"id": "frigate:patio", "kind": "frigate", "native": "patio", "enabled": False}]
        monkeypatch.setattr(S, "_frigate_sources", lambda: [
            S.VisionSource(id="frigate:patio", label="Patio", kind="frigate", native="patio", enabled=True)])
        from halbert_core.vision import config as vcfg
        cfg = vcfg.VisionConfig()
        cfg.sources = declared
        monkeypatch.setattr(vcfg, "load_config", lambda: cfg)
        got = {s.id: s for s in S.list_sources()}
        assert got["frigate:patio"].enabled is False
