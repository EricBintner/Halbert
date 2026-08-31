# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""POST /api/gpu/analyze must delegate to the agent, not raw Ollama.

The endpoint is deprecated as a raw `/api/chat` caller but stays answerable:
it gathers GPU context, dispatches a structured diagnostic prompt through the
agent's send-message path (specialist tier, host scope), and returns a
structured response. The agent path is mocked in every test.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import agent as agent_routes
from halbert_core.dashboard.routes import gpu as gpu_routes
from halbert_core.dashboard.routes.gpu import router

FAKE_GPU_INFO = {
    "gpus": [{
        "vendor": "NVIDIA",
        "model": "NVIDIA Corporation GA106 [GeForce RTX 3060]",
        "pci_id": "01:00.0",
        "vram_mb": 12288,
        "driver_version": "550.107.02",
        "driver_type": "nvidia",
        "cuda_version": "12.4",
        "role": "auto",
    }],
    "has_nvidia": True,
    "has_amd": False,
    "has_intel": False,
    "nvidia_smi_available": True,
    "recommended_driver": None,
    "driver_status": "optimal",
    "issues": [],
}

FAKE_SYSTEM_CONTEXT = {
    "kernel": "6.8.0-45-generic",
    "distro": "Ubuntu",
    "distro_version": "24.04",
    "display_server": "x11",
    "secure_boot": "disabled",
    "nvidia_packages": [],
    "cuda_paths": [],
    "ml_frameworks": {},
    "container_runtime": None,
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _mock_context(monkeypatch, gpus=None):
    info = FAKE_GPU_INFO if gpus is None else {
        **FAKE_GPU_INFO, "gpus": gpus,
    }
    monkeypatch.setattr(gpu_routes, "get_gpu_info", lambda: info)
    monkeypatch.setattr(gpu_routes, "get_deep_system_context", lambda: FAKE_SYSTEM_CONTEXT)


def _no_raw_llm(monkeypatch):
    """Any requests.post reaching Ollama fails the test loudly."""
    import requests

    def _refuse(*args, **kwargs):
        raise AssertionError("raw requests.post LLM call — analyze must delegate to the agent")

    monkeypatch.setattr(requests, "post", _refuse)


def test_analyze_no_gpu_returns_structured_early_answer(client, monkeypatch):
    _mock_context(monkeypatch, gpus=[])
    _no_raw_llm(monkeypatch)

    r = client.post("/api/gpu/analyze")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["analysis"] == "No GPU detected in this system."
    assert body["health_score"] == 0
    assert body["driver_info"] is None


def test_analyze_delegates_to_agent_and_returns_structured(client, monkeypatch):
    _mock_context(monkeypatch)
    _no_raw_llm(monkeypatch)

    dispatched = {}

    async def fake_turn(prompt):
        dispatched["prompt"] = prompt
        return "The RTX 3060 on driver 550.107.02 is well matched to CUDA 12.4."

    monkeypatch.setattr(gpu_routes, "_run_agent_turn", fake_turn)

    r = client.post("/api/gpu/analyze")

    assert r.status_code == 200, r.text
    body = r.json()
    assert "RTX 3060" in body["analysis"]
    assert body["delegated"] is True
    assert body["driver_status"] == "optimal"
    assert body["raw_context"]["gpu"]["pci_id"] == "01:00.0"
    # The diagnostic prompt is structured: it carries the detected hardware.
    assert "GeForce RTX 3060" in dispatched["prompt"]


def test_analyze_dispatch_runs_specialist_tier_with_host_scope(client, monkeypatch):
    """The delegation helper itself must call agent.process like send_message does:
    specialist tier, host retrieval scope, streamed response chunks aggregated."""
    _mock_context(monkeypatch)
    _no_raw_llm(monkeypatch)

    from halbert_core.agents.events import StreamEvent

    captured = {}

    class FakeAgent:
        def process(self, **kwargs):
            captured.update(kwargs)

            async def stream():
                yield StreamEvent.response_chunk("s1", "driver is ")
                yield StreamEvent.response_chunk("s1", "optimal")

            return stream()

    monkeypatch.setattr(agent_routes, "get_agent", lambda: FakeAgent())
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)

    r = client.post("/api/gpu/analyze")

    assert r.status_code == 200, r.text
    assert captured["tier_override"] == "specialist"
    assert captured["retrieval_scope"] == "host"
    assert "driver is optimal" in r.json()["analysis"]


def test_analyze_agent_error_falls_back_gracefully(client, monkeypatch):
    _mock_context(monkeypatch)
    _no_raw_llm(monkeypatch)

    async def failing_turn(prompt):
        raise RuntimeError("model not configured")

    monkeypatch.setattr(gpu_routes, "_run_agent_turn", failing_turn)

    r = client.post("/api/gpu/analyze")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delegated"] is True
    assert "model not configured" in body["analysis"]
    assert body["driver_status"] == "optimal"


def test_monitoring_info_endpoint_still_works(client, monkeypatch):
    """The live-stats endpoints keep calling the shared detection functions."""
    _mock_context(monkeypatch)

    r = client.get("/api/gpu/info")

    assert r.status_code == 200, r.text
    assert r.json()["gpus"][0]["driver_version"] == "550.107.02"