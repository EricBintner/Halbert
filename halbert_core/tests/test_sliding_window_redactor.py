# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Multi-node Task 2 — streaming redaction at the established choke point.

``SlidingWindowRedactor`` feeds ``redact_string`` incrementally so a
secret split across SSE deltas can never leave in pieces. The properties
under test:

- piecewise output equals whole-text redaction for boundary-safe cuts
- a secret split at ANY offset never leaks
- multi-line constructs (PEM, deferred values, block scalars, plists)
  are held until their extent is decided
- the compute endpoint's ``stream: true`` path emits redacted deltas
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.federation.peers_config import PeersConfig
from halbert_core.security.result_redaction import (
    SlidingWindowRedactor,
    redact_string,
)


def _stream(text: str, size: int = 1) -> str:
    """Feed ``text`` through a redactor in ``size``-char slices."""
    r = SlidingWindowRedactor()
    out = []
    for i in range(0, len(text), size):
        out.append(r.feed(text[i:i + size]))
    out.append(r.flush())
    return "".join(out)


def _stream_with_out(text: str, size: int = 1):
    """As _stream, also returning each feed's emission for assertions."""
    r = SlidingWindowRedactor()
    emissions = []
    for i in range(0, len(text), size):
        emissions.append(r.feed(text[i:i + size]))
    return "".join(emissions), r.flush()


class TestPiecewiseEqualsWholeText:
    """feed+flush must produce exactly redact_string(whole)."""

    DOCS = [
        "nothing here\n",
        "plain line one\nplain line two\n",
        "host=example.com\nuser=alice\n",
        "password=hunter2\n",
        "line one\npassword=hunter2\nline three\n",
        "the token is eyJabc.eyJdef.sigpart rest\n",
        "visit http://bob:hunter2@proxy.example.com:3128/\n",
        "psk = correct horse battery staple\n",
        "password:\n  hunter2\nnext: value\n",
        "password: |\n  hunter2\n  second line\nother: x\n",
        "password: # a note\n  hunter2\n",
        "<key>Password</key>\n<string>hunter2</string>\n",
        "<string>--token</string>\n<string>hunter2</string>\n",
        "-----BEGIN PRIVATE KEY-----\nabc123def456\n-----END PRIVATE KEY-----\nafter\n",
        "before\n-----BEGIN KEY-----\nx\n-----END KEY-----\n",
        "a\r\nwindows line\r\npassword=hunter2\r\n",
        "no trailing newline password=hunter2",
        "single line no newline at all",
        "",
    ]

    @pytest.mark.parametrize("size", [1, 3, 7, 17, 64, 5000])
    @pytest.mark.parametrize("doc", DOCS)
    def test_equivalence(self, doc, size):
        assert _stream(doc, size) == redact_string(doc)


class TestSecretsNeverLeak:
    """No emission may contain the raw secret, however it is sliced."""

    @pytest.mark.parametrize("size", [1, 2, 5, 13])
    def test_inline_secret_never_appears(self, size):
        text = "first\npassword=hunter2\nlast\n"
        r = SlidingWindowRedactor()
        for i in range(0, len(text), size):
            piece = r.feed(text[i:i + size])
            assert "hunter2" not in piece, f"leaked at offset {i}"
        assert "hunter2" not in r.flush()

    @pytest.mark.parametrize("size", [1, 4, 11])
    def test_pem_never_appears_partially(self, size):
        text = ("pre\n-----BEGIN PRIVATE KEY-----\nSECRETBODYONE\n"
                "SECRETBODYTWO\n-----END PRIVATE KEY-----\npost\n")
        r = SlidingWindowRedactor()
        for i in range(0, len(text), size):
            piece = r.feed(text[i:i + size])
            assert "SECRETBODY" not in piece, f"leaked at offset {i}"
        assert "SECRETBODY" not in r.flush()
        assert "<pem_block>" in _stream(text, size)

    def test_jwt_split_across_chunks(self):
        text = "ok eyJabc.eyJdef.signature end\n"
        out = _stream(text, 3)
        assert "eyJabc" not in out and "signature" not in out
        assert "<jwt>" in out

    def test_url_credential_split(self):
        text = "mount http://alice:hunter2@nas.local/share\n"
        out = _stream(text, 2)
        assert "hunter2" not in out

    def test_deferred_scalar_split(self):
        text = "password:\n  hunter2\nnext: 1\n"
        out = _stream(text, 2)
        assert "hunter2" not in out
        assert "next" in out  # the sibling survives

    def test_block_scalar_split(self):
        text = "password: |\n  hunter2\n  more secret\nother: x\n"
        out = _stream(text, 3)
        assert "hunter2" not in out and "more secret" not in out
        assert "other" in out


class TestHoldingBehaviour:
    def test_partial_line_is_never_emitted(self):
        r = SlidingWindowRedactor()
        assert r.feed("partial line, no newline") == ""
        assert r.buffered > 0
        assert r.feed(" rest\n") != ""  # the completed line now flows

    def test_unclosed_pem_holds_everything_from_begin(self):
        r = SlidingWindowRedactor()
        assert r.feed("safe line\n") == "safe line\n"
        assert r.feed("-----BEGIN KEY-----\nbody\n") == ""
        out = r.feed("more\n-----END KEY-----\n")
        assert "<pem_block>" in out
        assert "body" not in out

    def test_secret_key_line_waits_for_its_value(self):
        r = SlidingWindowRedactor()
        assert r.feed("before\n") == "before\n"
        assert r.feed("password:\n") == ""          # scalar may follow
        out = r.feed("  hunter2\n")
        assert "hunter2" not in out and "password" in out
        assert r.feed("next: 1\n") == "next: 1\n"

    def test_dedent_closes_a_deferred_region_with_no_value(self):
        r = SlidingWindowRedactor()
        r.feed("password:\n")
        out = r.feed("sibling: x\n")
        # `sibling` dedented to the key's level: no deferred value exists,
        # and the redaction matches whole-text semantics (nothing hidden).
        assert out == redact_string("password:\nsibling: x\n")

    def test_block_scalar_holds_until_dedent(self):
        r = SlidingWindowRedactor()
        assert r.feed("password: |\n  line one\n") == ""
        assert r.feed("  line two\n") == ""
        out = r.feed("other: 1\n")
        assert "<secret>" in out
        assert "line one" not in out
        assert "other" in out

    def test_plist_key_waits_for_value_element(self):
        r = SlidingWindowRedactor()
        assert r.feed("<key>Name</key>\n") == "<key>Name</key>\n"  # not secret
        assert r.feed("<key>Password</key>\n") == ""               # secret — wait
        out = r.feed("<string>hunter2</string>\n")
        assert "hunter2" not in out
        assert "[redacted]" in out

    def test_plist_flag_waits_for_value_member(self):
        r = SlidingWindowRedactor()
        assert r.feed("<string>--token</string>\n") == ""
        out = r.feed("<string>hunter2</string>\n")
        assert "hunter2" not in out

    def test_flush_returns_the_remainder(self):
        r = SlidingWindowRedactor()
        r.feed("partial")
        assert r.flush() == "partial"
        assert r.buffered == 0

    def test_empty_flush_after_complete_emission(self):
        r = SlidingWindowRedactor()
        r.feed("done\n")
        assert r.flush() == ""


class TestStreamingEndpoint:
    """``POST /api/compute/v1/chat/completions`` with ``stream: true``."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        from halbert_core.federation import compute_endpoint
        import halbert_core.federation.peer_middleware as pm

        monkeypatch.setattr(pm, "_is_local_client", lambda request: True)
        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer("sat-1", "Sat", "satellite", "tok")
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config",
            lambda: config,
        )

        async def fake_submit(request, tools, peer):
            return {
                "content": "line one\npassword=hunter2\nline three\n",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 5, "completion_tokens": 9,
                          "total_tokens": 14},
            }

        monkeypatch.setattr(compute_endpoint, "_submit_to_broker", fake_submit)
        app = FastAPI()
        app.include_router(compute_endpoint.router)
        yield TestClient(app)

    def _sse_json(self, body: str):
        frames = []
        for block in body.split("\n\n"):
            block = block.strip()
            if not block.startswith("data:"):
                continue
            payload = block[len("data:"):].strip()
            if payload == "[DONE]":
                frames.append(payload)
            else:
                frames.append(json.loads(payload))
        return frames

    def test_stream_returns_sse_with_redacted_deltas(self, client):
        resp = client.post(
            "/api/compute/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}],
                  "stream": True},
            headers={"Authorization": "Bearer tok"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = self._sse_json(resp.text)
        assert frames[-1] == "[DONE]"
        deltas = [f for f in frames[:-1] if isinstance(f, dict)]
        text = "".join(
            f["choices"][0]["delta"].get("content", "") for f in deltas
        )
        assert "hunter2" not in text
        assert "line one" in text and "line three" in text
        assert "<secret>" in text
        # Terminal frame carries finish_reason and usage.
        assert deltas[-1]["choices"][0]["finish_reason"] == "stop"
        assert deltas[-1]["usage"]["total_tokens"] == 14

    def test_stream_requires_peer_auth(self, client):
        resp = client.post(
            "/api/compute/v1/chat/completions",
            json={"model": "m", "messages": [], "stream": True},
        )
        assert resp.status_code == 401

    def test_non_stream_path_unchanged(self, client):
        resp = client.post(
            "/api/compute/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer tok"},
        )
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "hunter2" not in content
