# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-01 Phase E: the talk door answers in the admission module's shape (A12-G6).

The guest routes walk a named gate list and produce an ``IngressDecision``
-- "dropped at gate X, reason Y", never a bare "no". The talk door, the
one door every typed and spoken turn arrives at, did not: it raised an
HTTPException whose body was hand-copied in ``agents/channels.py``
("Mirrors guest.py's ``_deny_payload``" -- a comment is not a shared
function, and a hand copy drifts).

One deny shape, one reason-text registry, one gate walk.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.persona.admission import (
    ADMISSION_DISPATCH,
    ADMISSION_DROP,
    REASON_TEXT,
    admit,
    block,
    deny_payload,
)
import halbert_core.dashboard.routes.agent as agent_routes


def test_the_deny_payload_is_one_function():
    payload = deny_payload("channel_registry", "no_channel_configured")
    assert payload["reason_code"] == "no_channel_configured"
    assert payload["decisive_gate"] == "channel_registry"
    # A sentence, not the code echoed back.
    assert payload["message"] != "no_channel_configured"


def test_every_talk_door_reason_code_has_words():
    from halbert_core.agents.steering import _REFUSAL_REASONS

    for code in _REFUSAL_REASONS:
        assert code in REASON_TEXT, code
    assert "no_channel_configured" in REASON_TEXT


def test_admit_walks_the_gates_and_names_the_decisive_one():
    decision = admit([
        block("channel_registry", "ingress", "no_channel_configured", 400),
    ])
    assert decision.admission == ADMISSION_DROP
    assert decision.decisive_gate == "channel_registry"


def test_the_channel_refusal_renders_through_the_shared_payload():
    """``ChannelRefused.payload()`` no longer hand-copies the shape."""
    from halbert_core.agents.channels import ChannelRefused

    payload = ChannelRefused("mcp").payload()
    assert payload == deny_payload("channel_registry", "no_channel_configured")


def test_an_unadmitted_modality_is_refused_at_the_door(monkeypatch):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)

    class _Agent:
        active_sessions = {}

    monkeypatch.setattr(agent_routes, "_agent_instance", _Agent())
    app = FastAPI()
    app.include_router(agent_routes.router)
    client = TestClient(app)

    r = client.post(
        "/api/agent/message", json={"message": "hi", "modality": "mcp"}
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["reason_code"] == "no_channel_configured"
    assert detail["decisive_gate"] == "channel_registry"
    assert detail["message"] == REASON_TEXT["no_channel_configured"]
