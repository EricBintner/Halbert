# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The About panel reports what this machine serves, not what Halbert ships.

The Models tab used to be four model families transcribed from a licence
document into a served API payload. That broke the rule that Halbert names no
model, and it was a licence claim about models the reader may never have
installed while saying nothing about the ones they had.

A community licence asking for "Built with X" on a user-facing surface is only
satisfied by naming what is actually running. So the notices come from the
licence text the runtime ships with the weights.

The status field is load-bearing. An empty list because no runtime answered
means something different from an empty list because the runtime serves
nothing, and a panel rendering both as blank makes a licence claim it never
checked.
"""

import pytest

from halbert_core.dashboard.routes import legal


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def runtime(monkeypatch):
    """Stand in for the local model runtime."""
    state = {"tags": [], "licences": {}, "fail": False}

    def fake_get(url, timeout=None):
        if state["fail"]:
            raise OSError("connection refused")
        return _Resp({"models": [{"name": n} for n in state["tags"]]})

    def fake_licence(base_url, model, timeout=3.0):
        return state["licences"].get(model)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(
        "halbert_core.model.attribution.fetch_ollama_license", fake_licence)
    return state


class TestTheStatusIsPartOfTheAnswer:
    def test_an_unreachable_runtime_is_not_an_empty_list(self, runtime):
        runtime["fail"] = True
        result = legal._model_notices()
        assert result["models"] == []
        assert result["status"] == "runtime_unreachable"
        assert "could not be read" in result["detail"]

    def test_a_runtime_serving_nothing_says_so_differently(self, runtime):
        runtime["tags"] = []
        result = legal._model_notices()
        assert result["status"] == "no_models"


class TestAnUnmetObligationIsVisible:
    def test_a_model_with_no_licence_text_still_gets_a_row(self, runtime):
        """Omitting it would hide an attribution Halbert may owe."""
        runtime["tags"] = ["something:latest"]
        runtime["licences"] = {}
        rows = legal._model_notices()["models"]
        assert len(rows) == 1
        assert rows[0]["name"] == "something:latest"
        assert rows[0]["unknown_license"] is True

    def test_a_known_licence_is_reported_from_its_text(self, runtime):
        runtime["tags"] = ["something:latest"]
        runtime["licences"] = {"something:latest": "MIT License\n\nPermission is hereby granted, free of charge"}
        rows = legal._model_notices()["models"]
        assert rows[0]["unknown_license"] is False
        assert "MIT" in rows[0]["license"]


class TestTheSourceNamesNoModel:
    def test_the_route_module_carries_no_model_list(self):
        import inspect

        src = inspect.getsource(legal)
        assert "_FOUNDATION_MODELS" not in src.replace(
            "# ", ""), "the hardcoded model list is back"

    @pytest.mark.asyncio
    async def test_the_notices_payload_reports_its_status(self, runtime):
        runtime["tags"] = ["something:latest"]
        payload = await legal.get_notices()
        assert "foundation_models" in payload
        assert payload["foundation_models_status"] == "ok"
