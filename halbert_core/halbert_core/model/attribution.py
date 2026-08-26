# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Foundation-model licence metadata and user-facing attribution notices.

Single source of truth for LEG-MOD-04 (documentation/legal/LEGAL-AND-LICENSING-TODO.md).
Consumed by:

* ``Halbert/main.py`` — ``halbert model list`` / ``model status`` / ``info``
* ``halbert_core.dashboard.routes.llm`` — ``license`` / ``attribution`` fields on
  every entry returned by ``POST /api/llm/proxy/models``
* ``halbert_core.dashboard.routes.legal`` — foundation-model section of the
  "About / Legal Notices" panel

Halbert does not bundle model weights: models are pulled by the user through
Ollama / MLX / a cloud API. Several community licences (Meta Llama in
particular) only *require* a display notice from parties that distribute the
weights or ship a product that contains them. Halbert shows the notices anyway
so that a future build that does bundle weights (Halbert Pro) is compliant by
construction, and so users can see the terms of the model they are talking to.

Matching is by model *family* (the part of an Ollama tag before ``:``), so
``llama3.1:8b-instruct-q4_K_M`` and ``llama3.1`` resolve to the same entry.
Unknown models resolve to ``None`` — callers must treat that as "no notice",
never as "no licence".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "ModelAttribution",
    "FOUNDATION_MODEL_LICENSES",
    "attribution_for",
    "notices_for",
    "normalize_model_id",
    "as_dict",
]


@dataclass(frozen=True)
class ModelAttribution:
    """Licence facts for one model family."""

    family: str
    """Human-readable family name, e.g. ``"Meta Llama 3.1"``."""
    license_name: str
    """Licence name as it appears in the licence document itself."""
    license_id: str
    """SPDX identifier where one exists, otherwise a ``LicenseRef-`` tag."""
    license_url: str
    notice: Optional[str] = None
    """User-facing display text the licence asks for (``None`` when it asks for nothing)."""
    notice_required_when: Optional[str] = None
    """Plain-language trigger for the notice obligation."""
    notes: Tuple[str, ...] = field(default_factory=tuple)
    """Extra terms worth surfacing (use restrictions, geographic limits, base-model licences)."""


_LLAMA_TRIGGER = (
    "Required only when distributing the Llama weights or a product/service that "
    "contains them; shown by Halbert as a courtesy because the model is recommended in its catalog."
)

# Ordered: first matching pattern wins, so put the more specific families first.
FOUNDATION_MODEL_LICENSES: Tuple[Tuple[re.Pattern[str], ModelAttribution], ...] = (
    # ── Meta Llama ────────────────────────────────────────────────────────
    (
        re.compile(r"^(llama-?4|meta-llama/llama-4)"),
        ModelAttribution(
            family="Meta Llama 4",
            license_name="Llama 4 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-4-Community",
            license_url="https://www.llama.com/llama4/license/",
            notice="Built with Llama",
            notice_required_when=_LLAMA_TRIGGER,
            notes=(
                "Derived models must carry \"Llama\" at the start of their name.",
                "Not licensed to individuals or companies domiciled in the European Union for multimodal use.",
            ),
        ),
    ),
    (
        re.compile(r"^(llama-?3\.3|meta-llama/llama-3\.3)"),
        ModelAttribution(
            family="Meta Llama 3.3",
            license_name="Llama 3.3 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-3.3-Community",
            license_url="https://www.llama.com/llama3_3/license/",
            notice="Built with Llama",
            notice_required_when=_LLAMA_TRIGGER,
            notes=("Derived models must carry \"Llama\" at the start of their name.",),
        ),
    ),
    (
        re.compile(r"^(llama-?3\.2|meta-llama/llama-3\.2)"),
        ModelAttribution(
            family="Meta Llama 3.2",
            license_name="Llama 3.2 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-3.2-Community",
            license_url="https://www.llama.com/llama3_2/license/",
            notice="Built with Llama",
            notice_required_when=_LLAMA_TRIGGER,
            notes=(
                "Derived models must carry \"Llama\" at the start of their name.",
                "Multimodal (vision) variants: licence rights are not granted to individuals or companies domiciled in the European Union.",
            ),
        ),
    ),
    (
        re.compile(r"^(llama-?3\.1|meta-llama/(meta-)?llama-3\.1)"),
        ModelAttribution(
            family="Meta Llama 3.1",
            license_name="Llama 3.1 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-3.1-Community",
            license_url="https://www.llama.com/llama3_1/license/",
            notice="Built with Llama",
            notice_required_when=_LLAMA_TRIGGER,
            notes=("Derived models must carry \"Llama\" at the start of their name.",),
        ),
    ),
    (
        re.compile(r"^(llama-?3(?![.\d])|meta-llama/meta-llama-3-)"),
        ModelAttribution(
            family="Meta Llama 3",
            license_name="Meta Llama 3 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-3-Community",
            license_url="https://www.llama.com/llama3/license/",
            notice="Built with Meta Llama 3",
            notice_required_when=_LLAMA_TRIGGER,
            notes=("Derived models must carry \"Meta Llama 3\" at the start of their name.",),
        ),
    ),
    (
        re.compile(r"^(codellama|code-?llama|llama-?2|meta-llama/llama-2)"),
        ModelAttribution(
            family="Meta Llama 2 / Code Llama",
            license_name="Llama 2 Community License Agreement",
            license_id="LicenseRef-Meta-Llama-2-Community",
            license_url="https://ai.meta.com/llama/license/",
            notice=None,
            notice_required_when=(
                "No display notice. Distributed copies must carry a Notice file reading: "
                "\"Llama 2 is licensed under the LLAMA 2 Community License, Copyright (c) Meta Platforms, Inc. All Rights Reserved.\""
            ),
            notes=("Code Llama is released under the Llama 2 Community License.",),
        ),
    ),
    # ── DeepSeek ──────────────────────────────────────────────────────────
    (
        re.compile(r"^(deepseek-r1|deepseek-ai/deepseek-r1)"),
        ModelAttribution(
            family="DeepSeek-R1",
            license_name="MIT License",
            license_id="MIT",
            license_url="https://huggingface.co/deepseek-ai/DeepSeek-R1/blob/main/LICENSE",
            notice=None,
            notice_required_when="MIT requires the copyright and permission notice to accompany distributed copies of the weights; no product display notice.",
            notes=(
                "Distilled variants also inherit their base model's licence: the 70B distill is built on Llama 3.3 "
                "(Llama 3.3 Community License, \"Built with Llama\"); the 1.5B–32B distills are built on Qwen 2.5 (Apache-2.0).",
            ),
        ),
    ),
    (
        re.compile(r"^(deepseek-coder|deepseek-ai/deepseek-coder)"),
        ModelAttribution(
            family="DeepSeek Coder",
            license_name="DeepSeek License Agreement (model weights); MIT (code)",
            license_id="LicenseRef-DeepSeek-Model-License",
            license_url="https://github.com/deepseek-ai/DeepSeek-Coder/blob/main/LICENSE-MODEL",
            notice=None,
            notice_required_when="No product display notice. Redistribution must include the licence text and the Attachment A use restrictions.",
            notes=("Attachment A use-based restrictions apply (no unlawful, harmful or discriminatory use).",),
        ),
    ),
    (
        re.compile(r"^(deepseek|deepseek-ai/)"),
        ModelAttribution(
            family="DeepSeek",
            license_name="DeepSeek License Agreement / MIT (varies by model)",
            license_id="LicenseRef-DeepSeek-Model-License",
            license_url="https://github.com/deepseek-ai/DeepSeek-LLM/blob/main/LICENSE-MODEL",
            notice=None,
            notice_required_when="Check the specific model card; V3 and R1 weights are MIT, earlier releases use the DeepSeek License Agreement.",
        ),
    ),
    # ── Alibaba Qwen ──────────────────────────────────────────────────────
    (
        re.compile(r"^(qwq|qwen/qwq)"),
        ModelAttribution(
            family="Alibaba QwQ",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/Qwen/QwQ-32B/blob/main/LICENSE",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice; keep the licence and NOTICE with distributed copies.",
        ),
    ),
    (
        re.compile(r"^(qwen3|qwen/qwen3)"),
        ModelAttribution(
            family="Alibaba Qwen3",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/Qwen/Qwen3-32B/blob/main/LICENSE",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice; keep the licence and NOTICE with distributed copies.",
        ),
    ),
    (
        re.compile(r"^(qwen2\.5-coder|qwen/qwen2\.5-coder)"),
        ModelAttribution(
            family="Alibaba Qwen2.5-Coder",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct/blob/main/LICENSE",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice; keep the licence and NOTICE with distributed copies.",
            notes=("Exception: the 3B size is under the Qwen Research License (non-commercial).",),
        ),
    ),
    (
        re.compile(r"^(qwen2\.5|qwen/qwen2\.5|qwen2(?![.\d])|qwen/qwen2-)"),
        ModelAttribution(
            family="Alibaba Qwen2.5",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/blob/main/LICENSE",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice; keep the licence and NOTICE with distributed copies.",
            notes=(
                "Exceptions: the 3B size is under the Qwen Research License (non-commercial); "
                "the 72B size is under the Qwen License Agreement, which requires \"Built with Qwen\" or "
                "\"Improved using Qwen\" in product documentation when distributed.",
            ),
        ),
    ),
    # ── Mistral ───────────────────────────────────────────────────────────
    (
        re.compile(r"^(mistral-small|mistralai/mistral-small)"),
        ModelAttribution(
            family="Mistral Small",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice.",
            notes=("Mistral Small 3.x is Apache-2.0; the older Mistral Small 22B (2409) was under the Mistral Research License (non-commercial).",),
        ),
    ),
    (
        re.compile(r"^(mistral|mixtral|mistral-nemo|mistralai/)"),
        ModelAttribution(
            family="Mistral",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://mistral.ai/news/announcing-mistral-7b",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice.",
            notes=("Mistral Large / Medium and 'Research' releases are NOT Apache-2.0; check the model card.",),
        ),
    ),
    # ── Google Gemma ──────────────────────────────────────────────────────
    (
        re.compile(r"^(gemma|google/gemma)"),
        ModelAttribution(
            family="Google Gemma",
            license_name="Gemma Terms of Use",
            license_id="LicenseRef-Gemma-Terms-of-Use",
            license_url="https://ai.google.dev/gemma/terms",
            notice=None,
            notice_required_when="No product display notice. Distributed copies must include the Gemma Terms and the Prohibited Use Policy.",
        ),
    ),
    # ── Microsoft Phi ─────────────────────────────────────────────────────
    (
        re.compile(r"^(phi|microsoft/phi)"),
        ModelAttribution(
            family="Microsoft Phi",
            license_name="MIT License",
            license_id="MIT",
            license_url="https://huggingface.co/microsoft/Phi-4/blob/main/LICENSE",
            notice=None,
            notice_required_when="MIT: no product display notice.",
        ),
    ),
    # ── Embeddings ────────────────────────────────────────────────────────
    (
        re.compile(r"^(nomic-embed-text|nomic-ai/nomic-embed-text)"),
        ModelAttribution(
            family="Nomic Embed Text",
            license_name="Apache License 2.0",
            license_id="Apache-2.0",
            license_url="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5",
            notice=None,
            notice_required_when="Apache-2.0: no product display notice.",
        ),
    ),
    # ── Hosted / proprietary APIs ─────────────────────────────────────────
    (
        re.compile(r"^(gpt-|o[134](-|$)|chatgpt|openai/)"),
        ModelAttribution(
            family="OpenAI",
            license_name="OpenAI Terms of Use (hosted service)",
            license_id="LicenseRef-Proprietary-OpenAI",
            license_url="https://openai.com/policies/terms-of-use/",
            notice=None,
            notice_required_when="Hosted API: prompts and context leave the machine. See PRIVACY.md and the cloud data-flow disclosure.",
        ),
    ),
    (
        re.compile(r"^(claude|anthropic/)"),
        ModelAttribution(
            family="Anthropic Claude",
            license_name="Anthropic Consumer/Commercial Terms (hosted service)",
            license_id="LicenseRef-Proprietary-Anthropic",
            license_url="https://www.anthropic.com/legal/commercial-terms",
            notice=None,
            notice_required_when="Hosted API: prompts and context leave the machine. See PRIVACY.md and the cloud data-flow disclosure.",
        ),
    ),
    (
        re.compile(r"^(gemini|google/gemini|models/gemini)"),
        ModelAttribution(
            family="Google Gemini",
            license_name="Google APIs / Gemini API Terms (hosted service)",
            license_id="LicenseRef-Proprietary-Google",
            license_url="https://ai.google.dev/gemini-api/terms",
            notice=None,
            notice_required_when="Hosted API: prompts and context leave the machine. See PRIVACY.md and the cloud data-flow disclosure.",
        ),
    ),
)


_PROVIDER_PREFIXES = ("ollama/", "mlx/", "mlx-community/", "hf.co/", "huggingface.co/")


def normalize_model_id(model_id: str) -> str:
    """Lower-case, strip provider prefixes, and drop the Ollama ``:tag`` suffix.

    ``"Ollama/Llama3.1:8b-instruct-q4_K_M"`` → ``"llama3.1"``.
    HuggingFace-style ``org/name`` ids are preserved (minus a trailing ``:tag``).
    """
    mid = (model_id or "").strip().lower()
    for prefix in _PROVIDER_PREFIXES:
        if mid.startswith(prefix):
            mid = mid[len(prefix):]
            break
    if ":" in mid:
        mid = mid.split(":", 1)[0]
    return mid


def attribution_for(model_id: str) -> Optional[ModelAttribution]:
    """Return the licence entry for ``model_id`` or ``None`` when unknown."""
    mid = normalize_model_id(model_id)
    if not mid:
        return None
    for pattern, entry in FOUNDATION_MODEL_LICENSES:
        if pattern.search(mid):
            return entry
    return None


def notices_for(model_ids: Iterable[str]) -> List[str]:
    """De-duplicated display notices (e.g. ``["Built with Llama"]``) for a set of models."""
    seen: List[str] = []
    for mid in model_ids:
        entry = attribution_for(mid)
        if entry and entry.notice and entry.notice not in seen:
            seen.append(entry.notice)
    return seen


def as_dict(entry: Optional[ModelAttribution]) -> Optional[Dict[str, object]]:
    """JSON-friendly view used by the dashboard API."""
    if entry is None:
        return None
    d = asdict(entry)
    d["notes"] = list(entry.notes)
    return d
