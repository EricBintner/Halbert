# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert names no AI model.

A standing founder directive, restated in ``model/attribution.py`` ("Nothing
here names a model") and in ``test_llm_proxy_capabilities.py`` ("never name an
AI model in any string, comment, doc, or UI copy"). Until now nothing enforced
it, and two surfaces had drifted: the About panel published four model families
transcribed out of a licence document, and the Vision tab recommended a
specific model by name.

The distinction the product actually draws, and this guard preserves: a model
name that comes from the USER'S RUNTIME at request time is a fact about their
machine and is fine to display. A model name baked into Halbert's own source is
Halbert naming a model, and is not.

WHAT THIS CANNOT DO. It matches a list, so it catches the families it was
taught and not one released next week. That is a real limit, not a hidden one
-- it is a tripwire for drift, not a proof of absence.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "halbert_core/halbert_core/dashboard/frontend/src"
ROUTES = REPO / "halbert_core/halbert_core/dashboard/routes"

#: Model families, as whole words. "ollama" is a runtime, not a model, and
#: must not be caught by "llama" -- hence the word boundaries.
FAMILIES = [
    "llama", "llama2", "llama3", "tinyllama", "codellama", "deepseek", "qwen",
    "mistral", "mixtral", "gemma", "phi-3", "falcon", "vicuna", "llava",
    "gpt-4", "gpt-3.5", "claude", "nomic-embed", "starcoder", "wizardlm", "orca",
]
_PATTERN = re.compile(r"\b(" + "|".join(re.escape(f) for f in FAMILIES) + r")\b", re.I)

#: Named exceptions, each one a thing that is not a model.
#:
#: "Google Gemini" is the hosted API a user configures an endpoint against --
#: the same category as OpenAI or Anthropic, and ``attribution.provider_terms``
#: already carries its terms under the ``google`` provider. Naming the service
#: you are connecting to is not recommending a model.
#:
#: "open-claude-code" is an upstream open-source project this codebase borrows
#: patterns from, cited in comments.
ALLOWED = ["Google Gemini", "open-claude-code"]


def _offences(text: str, *, is_python: bool) -> list:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        scrubbed = line
        for ok in ALLOWED:
            scrubbed = re.sub(re.escape(ok), "", scrubbed, flags=re.I)
        if _PATTERN.search(scrubbed):
            out.append((i, line.strip()[:120]))
    return out


def _sources():
    for f in sorted(ROUTES.rglob("*.py")):
        if f.name.startswith("test_"):
            continue
        yield f, True
    for pattern in ("*.ts", "*.tsx"):
        for f in sorted(FRONTEND.rglob(pattern)):
            if "node_modules" in str(f) or ".test." in f.name:
                continue
            yield f, False


class TestNoModelNamesInUserFacingSource:
    def test_the_guard_has_files_to_check(self):
        assert sum(1 for _ in _sources()) > 100

    def test_no_source_file_names_a_model(self):
        offences = []
        for f, is_py in _sources():
            for line_no, line in _offences(f.read_text(errors="replace"), is_python=is_py):
                offences.append(f"{f.relative_to(REPO)}:{line_no}: {line}")
        assert not offences, (
            "Halbert must not name an AI model in its own source. A name that "
            "comes from the user's runtime at request time is fine; a name "
            "written here is not.\n" + "\n".join(offences)
        )

    def test_the_pattern_does_not_fire_on_the_runtime_name(self):
        """`ollama` is a runtime. Catching it would make the guard unusable."""
        assert not _offences("endpoint.provider === 'ollama'", is_python=False)
        assert not _offences("Start Ollama with `ollama serve`", is_python=False)

    def test_the_pattern_does_fire_on_a_real_name(self):
        """The assertion above is only worth having if this one holds."""
        assert _offences('{"name": "Meta Llama 3.1"}', is_python=True)
        assert _offences("Consider a local vision model (e.g., llava).", is_python=False)
