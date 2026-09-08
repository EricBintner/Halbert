# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SEC-21: locality is a property of the model, not the URL.

`being_config.py` states the rule in three clauses: reject any tag ending in
``:cloud``, reject any provider outside the local set, never infer locality
from the endpoint URL alone. Every gate in the tree implemented only the
third clause's negation -- "URL is loopback, therefore local" -- and Ollama's
``:cloud`` models are exactly the case that breaks it: served from
``localhost:11434`` and proxied to ollama.com at inference time.

Verified on the founder's machine (Ollama 0.32.15): six ``:cloud`` models are
pulled, ``chat_model`` and ``specialist_model`` are both ``:cloud``, and
``secure_model`` points at a port nothing listens on. The issue's proposed
authoritative check (``/api/show`` ``remote_host``) does not exist in this
version; the suffix does, and across all 33 local models it agrees exactly
with the absence of a modelfile. So the suffix is the primary signal and
this function is the one place it is decided.
"""

import pytest

from halbert_core.model.llm_config import is_local_model

LOOPBACK = "http://localhost:11434"
LOOPBACK_V6 = "http://[::1]:11434"

# The live configuration this was found in, verbatim.
LIVE_CHAT = ("deepseek-v4-flash:cloud", LOOPBACK, "ollama")
LIVE_SPECIALIST = ("deepseek-v4-pro:cloud", LOOPBACK, "ollama")
LIVE_SECURE = ("apple-foundation-3b", "http://127.0.0.1:11435", "apple-foundation")


class TestTheCloudSuffix:

    @pytest.mark.parametrize("model", [
        "deepseek-v4-flash:cloud",
        "glm-5.3:cloud",
        "kimi-k2.7-code:cloud",
        "anything:CLOUD",           # Ollama tags are case-insensitive
        "anything:cloud ",          # trailing whitespace from a config file
        " anything:cloud",
    ])
    def test_a_cloud_tag_on_loopback_is_not_local(self, model):
        assert not is_local_model(model, LOOPBACK, "ollama"), (
            "localhost:11434 is a relay for this model, not its home"
        )

    @pytest.mark.parametrize("model", [
        "llama3.2:3b",
        "qwen3.8:27b-mlx",
        "gemini-3-flash-preview:latest",   # a local copy despite the name
        "richardyoung/qwythos-9b-abliterated:Q8_0",
        "cloud-thinking:latest",           # "cloud" in the name is not the tag
        "mycloud:8b",
    ])
    def test_a_local_tag_on_loopback_is_local(self, model):
        assert is_local_model(model, LOOPBACK, "ollama")

    def test_the_live_chat_model_is_not_local(self):
        assert not is_local_model(*LIVE_CHAT)

    def test_the_live_specialist_model_is_not_local(self):
        assert not is_local_model(*LIVE_SPECIALIST)


class TestTheProviderClause:

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "peer", "ollama-cloud", ""])
    def test_a_non_local_provider_on_loopback_is_not_local(self, provider):
        # A loopback URL in front of a cloud provider is still a cloud
        # provider. This is the "never infer from the URL" clause.
        assert not is_local_model("some-model", LOOPBACK, provider)

    @pytest.mark.parametrize("provider", ["ollama", "llamacpp", "lm-studio"])
    def test_local_runtime_providers_on_loopback_are_local(self, provider):
        assert is_local_model("some-model", LOOPBACK, provider)

    @pytest.mark.parametrize("provider", ["mlx", "apple-foundation"])
    def test_on_device_providers_need_no_url(self, provider):
        # No network egress by construction; the URL is a local IPC detail.
        assert is_local_model("some-model", "", provider)
        assert is_local_model(*LIVE_SECURE)

    def test_an_on_device_provider_still_refuses_a_cloud_tag(self):
        # Belt and braces: a misconfigured provider label must not launder a
        # cloud tag. The tag clause is absolute.
        assert not is_local_model("x:cloud", "", "mlx")


class TestTheUrlClause:

    @pytest.mark.parametrize("url", [
        "https://api.openai.com/v1",
        "http://192.168.1.50:11434",       # LAN is the peer tier, not local
        "https://api.localhost.gg",        # hostname merely contains 'localhost'
        "http://attacker.com/localhost",
    ])
    def test_a_non_loopback_url_is_not_local_even_for_ollama(self, url):
        assert not is_local_model("llama3.2:3b", url, "ollama")

    def test_ipv6_loopback_counts(self):
        assert is_local_model("llama3.2:3b", LOOPBACK_V6, "ollama")


class TestItNeverRaises:

    @pytest.mark.parametrize("args", [
        (None, None, None),
        ("", "", ""),
        (None, LOOPBACK, "ollama"),
        ("llama3.2:3b", None, "ollama"),
        (42, LOOPBACK, "ollama"),
    ])
    def test_degenerate_input_is_not_local(self, args):
        # On the secure gate, an exception would either crash the turn or be
        # swallowed into a default -- and a default that reads as "local" is
        # the whole bug. Unknown must mean not local.
        assert is_local_model(*args) is False
