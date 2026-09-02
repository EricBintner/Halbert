# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""TierRouter._get_provider (STUB-01).

TierRouter's ModelProvider hierarchy (ollama/anthropic/peer) is not the
dashboard's chat path — model/client.py's call_llm_chat implements every
CHAT_CAPABLE_PROVIDERS entry (openai included) directly and never calls
TierRouter. TierRouter's only consumer, integrations/app_seam.py's
HalbertModelBackend, already wraps generation in a broad try/except that
falls back to raw Ollama on any exception, so an unsupported provider
here degrades silently. "openai" used to raise its own NotImplementedError
instead of the same generic unknown-provider error every other provider
this hierarchy doesn't implement (llamacpp, mlx, lm-studio, ...) gets.
"""
from halbert_core.model.capabilities import ModelDefinition
from halbert_core.model.tier_router import TierRouter


def _router() -> TierRouter:
    router = TierRouter.__new__(TierRouter)
    router._providers = {}
    return router


def _model(provider: str) -> ModelDefinition:
    return ModelDefinition(name="m", model_id="m-1", provider=provider)


def test_openai_raises_the_same_unknown_provider_error_as_llamacpp():
    router = _router()
    try:
        router._get_provider(_model("openai"))
        assert False, "expected ValueError"
    except ValueError as e:
        openai_error = str(e)
    try:
        router._get_provider(_model("llamacpp"))
        assert False, "expected ValueError"
    except ValueError as e:
        llamacpp_error = str(e)
    assert "openai" in openai_error
    assert "llamacpp" in llamacpp_error
    # Same error shape, not a special-cased stub.
    assert openai_error.startswith("Unknown provider:")
    assert llamacpp_error.startswith("Unknown provider:")


def test_openai_no_longer_raises_not_implemented_error():
    router = _router()
    try:
        router._get_provider(_model("openai"))
        assert False, "expected ValueError"
    except NotImplementedError:
        assert False, "openai must not get its own NotImplementedError stub"
    except ValueError:
        pass


def test_ollama_still_resolves():
    router = _router()
    provider = router._get_provider(_model("ollama"))
    assert provider is not None
