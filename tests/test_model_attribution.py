# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEG-MOD-04: foundation-model licence metadata and attribution notices."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from halbert_core.halbert_core.model.attribution import (  # noqa: E402
    FOUNDATION_MODEL_LICENSES,
    as_dict,
    attribution_for,
    normalize_model_id,
    notices_for,
)


@pytest.mark.parametrize(
    "model_id, expected",
    [
        ("llama3.1:8b-instruct", "llama3.1"),
        ("Ollama/Llama3.1:8b-instruct-q4_K_M", "llama3.1"),
        ("hf.co/Qwen/Qwen2.5-Coder-14B-Instruct:latest", "qwen/qwen2.5-coder-14b-instruct"),
        ("  deepseek-r1:70b ", "deepseek-r1"),
        ("", ""),
    ],
)
def test_normalize_model_id(model_id, expected):
    assert normalize_model_id(model_id) == expected


@pytest.mark.parametrize(
    "model_id, family, notice",
    [
        # Models in config/model-catalog.yml
        ("llama3.1:8b-instruct", "Meta Llama 3.1", "Built with Llama"),
        ("llama3:8b-instruct", "Meta Llama 3", "Built with Meta Llama 3"),
        ("qwen2.5-coder:14b", "Alibaba Qwen2.5-Coder", None),
        ("deepseek-coder:33b", "DeepSeek Coder", None),
        ("codellama:34b-instruct", "Meta Llama 2 / Code Llama", None),
        # Models in config/models.yml
        ("qwen2.5:14b-instruct-q4_0", "Alibaba Qwen2.5", None),
        ("qwen2.5:32b", "Alibaba Qwen2.5", None),
        ("llama3.2-vision:11b", "Meta Llama 3.2", "Built with Llama"),
        ("qwq:32b", "Alibaba QwQ", None),
        ("deepseek-r1:70b", "DeepSeek-R1", None),
        ("llama3.3:70b", "Meta Llama 3.3", "Built with Llama"),
        ("mistral-small", "Mistral Small", None),
        ("nomic-embed-text", "Nomic Embed Text", None),
        # HuggingFace ids and hosted APIs
        ("meta-llama/Llama-3.1-8B-Instruct", "Meta Llama 3.1", "Built with Llama"),
        ("gpt-4.1", "OpenAI", None),
        ("claude-sonnet-5", "Anthropic Claude", None),
        ("models/gemini-3-pro", "Google Gemini", None),
    ],
)
def test_attribution_for_known_models(model_id, family, notice):
    entry = attribution_for(model_id)
    assert entry is not None, model_id
    assert entry.family == family
    assert entry.notice == notice
    assert entry.license_url.startswith("https://")


def test_llama3_pattern_does_not_swallow_llama31():
    assert attribution_for("llama3").family == "Meta Llama 3"
    assert attribution_for("llama3:latest").family == "Meta Llama 3"
    assert attribution_for("llama3.1").family == "Meta Llama 3.1"
    assert attribution_for("llama3.2").family == "Meta Llama 3.2"
    assert attribution_for("llama3.3").family == "Meta Llama 3.3"


def test_unknown_model_returns_none():
    assert attribution_for("some-custom-finetune:latest") is None
    assert attribution_for("") is None
    assert as_dict(None) is None


def test_notices_are_deduplicated_and_ordered():
    notices = notices_for(["llama3.1:8b", "llama3.3:70b", "qwen2.5:32b", "llama3:8b"])
    assert notices == ["Built with Llama", "Built with Meta Llama 3"]


def test_as_dict_is_json_friendly():
    d = as_dict(attribution_for("llama3.1"))
    assert d["license_id"] == "LicenseRef-Meta-Llama-3.1-Community"
    assert isinstance(d["notes"], list)
    assert d["notice"] == "Built with Llama"


def test_every_entry_has_a_license_url_and_name():
    for _pattern, entry in FOUNDATION_MODEL_LICENSES:
        assert entry.license_name and entry.license_id, entry.family
        assert entry.license_url.startswith("https://"), entry.family
