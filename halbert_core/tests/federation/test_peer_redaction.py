# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: peer prompt requesting ~/.ssh/id_rsa returns redacted, never the raw value.

Implements finding C4 / L15 from the federated multi-node review.

C4 — The compute endpoint must apply the same redaction boundary as MCP.
This test verifies that when a peer sends a prompt that would cause the
model to return a secret value (e.g., the contents of ~/.ssh/id_rsa),
the response is redacted by ``mcp_response()`` before being sent back.

The test mocks the local model to return a response containing:
- A PEM private key block
- A config-value-pair with a secret key
- A URL with embedded credentials

And verifies that ``mcp_response()`` strips all of them.
"""
import pytest

from halbert_core.mcp.response import mcp_response
from halbert_core.ingestion.redaction import redact_text


class TestPeerRedaction:
    """Verify that the compute endpoint's redaction boundary catches secrets."""

    def test_pem_private_key_is_redacted(self):
        """A PEM private key block in the model response is stripped."""
        response_text = (
            "Here is the SSH key you requested:\n"
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gt\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        )
        redacted = mcp_response({"content": response_text})
        assert "BEGIN OPENSSH PRIVATE KEY" not in redacted["content"]
        # redact_text() replaces PEM blocks with <pem_block> marker
        assert "b3BlbnNzaC1rZXktdjE" not in redacted["content"]  # base64 key data is gone

    def test_config_value_pair_secret_is_redacted(self):
        """A config-value-pair with a secret key name has its value replaced."""
        response = {
            "content": "",
            "tool_results": [
                {"path": "/etc/halbert/ha_config.yml", "key": "ha_token", "value": "ABC123longtoken456"},
            ],
        }
        redacted = mcp_response(response)
        tool_result = redacted["tool_results"][0]
        assert tool_result["key"] == "ha_token"  # key name is preserved
        assert tool_result["value"] == "<secret>"  # value is redacted
        assert "ABC123longtoken456" not in str(redacted)

    def test_url_embedded_credentials_are_redacted(self):
        """URL-embedded credentials (user:pass@host) are stripped."""
        response_text = "The database URL is postgresql://admin:secretpass@db.internal:5432/halbert"
        redacted = mcp_response({"content": response_text})
        assert "secretpass" not in redacted["content"]
        assert "admin" not in redacted["content"] or "<secret>" in redacted["content"]

    def test_jwt_token_is_redacted(self):
        """A JWT token in the response text is stripped."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        response_text = f"Your token is: {jwt}"
        redacted = mcp_response({"content": response_text})
        assert jwt not in redacted["content"]

    def test_non_secret_content_passes_through(self):
        """Normal (non-secret) content is not redacted."""
        response_text = "The system has 4 CPU cores and 16GB of RAM. The hostname is studio-mac."
        redacted = mcp_response({"content": response_text})
        assert redacted["content"] == response_text

    def test_nested_structure_is_redacted(self):
        """Secrets in deeply nested structures are caught."""
        response = {
            "content": "",
            "data": {
                "services": [
                    {"name": "sshd", "config": {"password": "hunter2", "port": 22}},
                ],
            },
        }
        redacted = mcp_response(response)
        service_config = redacted["data"]["services"][0]["config"]
        assert service_config["password"] == "<secret>"
        assert service_config["port"] == 22  # non-secret preserved
        assert "hunter2" not in str(redacted)

    LEAKS = [
        ("a private key", "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----"),
        ("a bearer token", "use eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"),
        ("a credentialled URL", "clone https://bob:s3cret@git.example.com/repo.git"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("what,text", LEAKS)
    async def test_compute_endpoint_applies_redaction(self, monkeypatch, what, text):
        """The egress choke point, exercised end to end.

        Unskipped: it waited on _submit_to_broker, which raised
        NotImplementedError, so nothing had ever run through this path.

        The boundary is redact_text's, not a general secrecy claim: it covers
        the shapes a secret actually takes on the wire (PEM blocks, JWTs,
        credentials in URLs, secret-keyed dicts). Prose that merely *says* a
        password out loud is not caught here and is not meant to be — the
        tool allowlist and the model's own prompt are what keep the model
        from being asked in the first place.
        """
        from halbert_core.federation import compute_endpoint as ce

        async def _leaky(request, tools, peer):
            return {"content": text, "finish_reason": "stop", "usage": {}}

        monkeypatch.setattr(ce, "_submit_to_broker", _leaky)

        resp = await ce.peer_compute_chat(
            ce.ChatCompletionRequest(
                model="local-model",
                messages=[ce.ChatMessage(role="user", content="tell me")],
            ),
            peer=ce.PeerContext(
                node_id="sat-1", node_name="Kitchen", role="satellite",
                capabilities=[], credential=None,
            ),
        )
        assert resp.choices[0].message.content != text, (
            f"{what} reached the peer unredacted"
        )
