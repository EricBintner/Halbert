# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A persona may narrow what it looks through, and cannot widen it — VIS-1.

The defect these close: before this, ``vision_tools.capture_webcam`` read
``args.get("camera", cfg.webcam.camera_index)``, so the configured camera was
a *default the model could override with any integer*. A persona scoped to one
camera could name another and get it. The HTTP routes had the same shape and
bypassed the tool layer entirely.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from halbert_core.vision import sources as S


def _sources(*specs):
    return [
        S.VisionSource(id=i, label=i, kind=k, native=n, enabled=e)
        for (i, k, n, e) in specs
    ]


@pytest.fixture
def registry(monkeypatch):
    """Two cameras and two screens, all system-enabled."""
    declared = _sources(
        ("webcam:desk", "webcam", "0", True),
        ("webcam:bedroom", "webcam", "1", True),
        ("screen:1", "screen", "1", True),
        ("screen:2", "screen", "2", True),
        ("frigate:patio", "frigate", "patio", True),
    )
    monkeypatch.setattr(S, "list_sources", lambda **k: list(declared))
    return declared


def _scope(monkeypatch, *ids):
    """A persona narrowed to these ids."""
    cfg = SimpleNamespace(senses=SimpleNamespace(vision=SimpleNamespace(sources=list(ids))))
    import halbert_core.config.being_config as bc
    monkeypatch.setattr(bc, "load_being_config", lambda *a, **k: cfg)


class TestScope:
    def test_no_narrowing_means_every_enabled_source(self, registry, monkeypatch):
        """An empty list is "not narrowed", not "none" — every persona file
        written before VIS-1 means that, and reading it as none would blind
        the machine on upgrade."""
        _scope(monkeypatch)
        assert set(S.persona_scope()) == {s.id for s in registry}

    def test_narrowing_is_an_intersection_never_a_union(self, registry, monkeypatch):
        """Naming a source the system switched off does not switch it on."""
        registry[1] = S.VisionSource(
            id="webcam:bedroom", label="b", kind="webcam", native="1", enabled=False)
        monkeypatch.setattr(S, "list_sources", lambda **k: list(registry))
        _scope(monkeypatch, "webcam:desk", "webcam:bedroom")
        assert S.persona_scope() == ["webcam:desk"]

    def test_an_out_of_scope_source_is_refused(self, registry, monkeypatch):
        _scope(monkeypatch, "webcam:desk")
        with pytest.raises(S.SourceDenied):
            S.permit_source("webcam:bedroom")

    def test_an_undeclared_source_is_unknown_not_denied(self, registry, monkeypatch):
        _scope(monkeypatch)
        with pytest.raises(S.UnknownSource):
            S.permit_source("webcam:garage")


class TestRequestResolution:
    def test_a_bare_index_is_a_request_not_a_choice(self, registry, monkeypatch):
        """THE defect. The model passing camera=1 is asking for webcam:1;
        out of scope, that is a refusal, not a picture of the bedroom."""
        _scope(monkeypatch, "webcam:desk")
        with pytest.raises(S.SourceDenied):
            S.resolve_request(1, S.KIND_WEBCAM)

    def test_an_in_scope_index_still_resolves(self, registry, monkeypatch):
        _scope(monkeypatch, "webcam:desk", "webcam:bedroom")
        assert S.resolve_request(1, S.KIND_WEBCAM).id == "webcam:bedroom"

    def test_a_bare_kind_means_this_personas_default(self, registry, monkeypatch):
        """'webcam' used to mean index 0 regardless of scope. Now it means
        the first source of that kind this persona may actually see."""
        _scope(monkeypatch, "webcam:bedroom")
        assert S.resolve_request("webcam", S.KIND_WEBCAM).id == "webcam:bedroom"

    def test_a_persona_with_no_source_of_that_kind_is_refused(self, registry, monkeypatch):
        _scope(monkeypatch, "screen:1")
        with pytest.raises(S.SourceDenied):
            S.resolve_request("webcam", S.KIND_WEBCAM)

    def test_a_registry_id_is_taken_as_written(self, registry, monkeypatch):
        _scope(monkeypatch)
        assert S.resolve_request("frigate:patio", S.KIND_WEBCAM).id == "frigate:patio"

    def test_a_monitor_index_cannot_reach_another_screen(self, registry, monkeypatch):
        _scope(monkeypatch, "screen:1")
        with pytest.raises(S.SourceDenied):
            S.resolve_request(2, S.KIND_SCREEN)


class TestTheToolSurface:
    """The gate has to hold at the tool boundary, which is where the model is."""

    @pytest.fixture(autouse=True)
    def _enabled(self, monkeypatch):
        from halbert_core.vision import config as vcfg
        cfg = vcfg.VisionConfig()
        cfg.screen_capture.enabled = True
        cfg.webcam.enabled = True
        monkeypatch.setattr(vcfg, "load_config", lambda: cfg)
        import halbert_core.tools.vision_tools as vt
        vt.reset_dedup_for_tests()

    @pytest.mark.asyncio
    async def test_capture_webcam_refuses_an_out_of_scope_camera(self, registry, monkeypatch):
        from halbert_core.tools.vision_tools import capture_webcam

        _scope(monkeypatch, "webcam:desk")
        result = await capture_webcam({"camera": 1})
        assert result["error_type"] == "source_denied"
        assert "webcam:bedroom" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_webcam_never_substitutes_an_allowed_camera(self, registry, monkeypatch):
        """A silent downgrade would have the model describe the wrong room in
        perfect good faith."""
        from halbert_core.tools.vision_tools import capture_webcam

        opened = []

        class _Cam:
            def __init__(self, camera_index=0, **kwargs):
                opened.append(camera_index)

            def grab_frame(self):
                return b"jpeg"

        import halbert_core.vision.webcam_capture as wc
        monkeypatch.setattr(wc, "WebcamCapture", _Cam)
        _scope(monkeypatch, "webcam:desk")
        await capture_webcam({"camera": 1})
        assert opened == []

    @pytest.mark.asyncio
    async def test_capture_screenshot_refuses_an_out_of_scope_monitor(self, registry, monkeypatch):
        from halbert_core.tools.vision_tools import capture_screenshot

        _scope(monkeypatch, "screen:1")
        result = await capture_screenshot({"monitor": 2})
        assert result["error_type"] == "source_denied"

    @pytest.mark.asyncio
    async def test_capture_and_ocr_is_bounded_too(self, registry, monkeypatch):
        """The OCR path returns text, and the text is the screen's content."""
        from halbert_core.tools.vision_tools import capture_and_ocr

        _scope(monkeypatch, "screen:1")
        result = await capture_and_ocr({"monitor": 2})
        assert result["error_type"] == "source_denied"

    @pytest.mark.asyncio
    async def test_the_refusal_names_what_the_caller_may_use(self, registry, monkeypatch):
        from halbert_core.tools.vision_tools import capture_webcam

        _scope(monkeypatch, "webcam:desk")
        result = await capture_webcam({"camera": 1})
        assert "webcam:desk" in result["available_sources"]

    @pytest.mark.asyncio
    async def test_list_windows_now_honours_the_global_switch(self, monkeypatch):
        """It was the one capture-adjacent tool with no gate at all — window
        titles were listed with screen capture switched off."""
        from halbert_core.tools.vision_tools import list_windows_tool
        from halbert_core.vision import config as vcfg

        cfg = vcfg.VisionConfig()
        cfg.screen_capture.enabled = False
        monkeypatch.setattr(vcfg, "load_config", lambda: cfg)
        result = await list_windows_tool({})
        assert result["error_type"] == "disabled"


class TestDedup:
    def test_dedup_is_keyed_by_source(self):
        """One hash per capture *type* was right when one camera was
        reachable; with two, alternating captures report 'unchanged' about a
        frame they never compared against."""
        import halbert_core.tools.vision_tools as vt

        vt.reset_dedup_for_tests()
        a = vt._dedup_key("webcam", "webcam:desk")
        b = vt._dedup_key("webcam", "webcam:bedroom")
        vt._remember_hash(a, "hash1")
        assert vt._is_unchanged(a, "hash1")
        assert not vt._is_unchanged(b, "hash1")


class TestFrigateCameras:
    """Frigate is the one kind that cannot be bounded by enumeration offline —
    listing the real cameras needs the NVR to answer, and listing sources must
    never depend on that."""

    def _declared(self, monkeypatch, *names):
        srcs = [
            S.VisionSource(id=S.frigate_source_id(n), label=n, kind="frigate", native=n)
            for n in names
        ]
        monkeypatch.setattr(S, "list_sources", lambda **k: list(srcs))

    def test_a_declared_camera_is_permitted(self, monkeypatch):
        self._declared(monkeypatch, "patio", "front_door")
        _scope(monkeypatch)
        assert S.permit_frigate_camera("patio") == "frigate:patio"

    def test_an_undeclared_camera_is_refused_when_some_are_declared(self, monkeypatch):
        self._declared(monkeypatch, "patio")
        _scope(monkeypatch)
        with pytest.raises(S.SourceDenied):
            S.permit_frigate_camera("bedroom")

    def test_an_explicit_narrowing_wins_over_the_declared_set(self, monkeypatch):
        self._declared(monkeypatch, "patio", "bedroom")
        _scope(monkeypatch, "frigate:patio")
        assert S.permit_frigate_camera("patio") == "frigate:patio"
        with pytest.raises(S.SourceDenied):
            S.permit_frigate_camera("bedroom")

    def test_with_nothing_declared_and_no_narrowing_there_is_no_bound(self, monkeypatch):
        """Named as a gap rather than papered over: an install with no
        enabled_cameras gets no Frigate narrowing until the user lists their
        cameras or the persona names the ones it may see."""
        self._declared(monkeypatch)
        _scope(monkeypatch)
        assert S.permit_frigate_camera("anything") == "frigate:anything"

    def test_a_camera_with_a_space_is_permitted_under_its_slug(self, monkeypatch):
        self._declared(monkeypatch, "Front Door")
        _scope(monkeypatch)
        assert S.permit_frigate_camera("Front Door") == "frigate:front_door"

    @pytest.mark.asyncio
    async def test_the_latest_frame_tool_refuses_before_it_fetches(self, monkeypatch):
        """A guest could name any camera: the tool argument was the whole of
        the identity, and both frame tools are on GUEST_ALLOWED_TOOLS."""
        from halbert_core.integrations.frigate import frigate_tools as ft

        self._declared(monkeypatch, "patio")
        _scope(monkeypatch)

        fetched = []

        class _Client:
            config = SimpleNamespace(is_configured=lambda: True)

            async def get_latest_frame(self, camera):
                fetched.append(camera)
                return b"jpeg"

        monkeypatch.setattr(ft, "_get_client", lambda: _Client())
        out = await ft._frigate_get_latest_frame_handler({"camera": "bedroom"})
        assert "Not available" in out
        assert fetched == []

    @pytest.mark.asyncio
    async def test_the_snapshot_tool_resolves_the_camera_before_the_pixels(self, monkeypatch):
        """Its argument is an event id, so the camera has to be looked up
        first — refusing after the fetch would still have read the camera."""
        from halbert_core.integrations.frigate import frigate_tools as ft

        self._declared(monkeypatch, "patio")
        _scope(monkeypatch)

        snapped = []

        class _Client:
            config = SimpleNamespace(is_configured=lambda: True)

            async def get_event(self, event_id):
                return {"id": event_id, "camera": "bedroom"}

            async def get_event_snapshot(self, event_id, crop=False):
                snapped.append(event_id)
                return b"jpeg"

        monkeypatch.setattr(ft, "_get_client", lambda: _Client())
        out = await ft._frigate_get_snapshot_handler({"event_id": "e1"})
        assert "Not available" in out
        assert snapped == []
