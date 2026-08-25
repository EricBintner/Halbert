"""
Halbert App Seam

Wires Halbert's integration components into Haloysius's AppSeam protocol.
This is the startup glue that registers the SourcePrep retrieval backend,
the LLM model backend, and the governance policy with Haloysius's
cognitive core.

Called once at application startup:
    from halbert_core.integrations.app_seam import wire_halbert_seam
    wire_halbert_seam()
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from haloysius.seam import (
    AppSeam,
    GovernancePolicy,
    ModelBackend,
    RetrievalBackend,
    register_app_seam,
)

from .sourceprep_retrieval_backend import SourcePrepRetrievalBackend
from .sourceprep_client import SourcePrepClient

logger = logging.getLogger(__name__)


class HalbertGovernancePolicy:
    """Permissive governance policy for Halbert.

    Halbert is a sysadmin tool — it needs to discuss system configuration,
    security, networking, etc. without being blocked by human-conversation
    topic filters. This policy allows all messages.

    When real safety gates are needed (e.g. preventing the LLM from
    suggesting destructive operations without confirmation), that logic
    lives in the ToolSafetyFramework, not in governance.
    """

    def check(self, message: str, **kwargs: Any) -> dict:
        return {
            "safe": True,
            "on_topic": True,
            "redirect_suggestion": None,
        }

    def check_detailed(self, message: str, **kwargs: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            safe=True,
            should_proceed=True,
            rag_query=message,
            to_dict=lambda: {"safe": True, "on_topic": True},
        )


class HalbertModelBackend:
    """ModelBackend adapter wrapping Halbert's LLM client.

    Bridges Haloysius's ModelBackend protocol to Halbert's existing
    LLM infrastructure. Currently a placeholder — the actual LLM
    routing (Ollama, specialist models) will be wired here once
    the LLMClientAdapter circular dependency is resolved (Phase C).

    For now, this returns None from raw_provider() and delegates
    chat() to a simple Ollama call.
    """

    def __init__(self, ollama_url: Optional[str] = None, model: Optional[str] = None):
        self.ollama_url = ollama_url or os.environ.get(
            "OLLAMA_URL", "http://localhost:11434"
        )
        self.model = model or os.environ.get("HALBERT_MODEL", "llama3.2")

    def is_available(self) -> bool:
        try:
            import requests

            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: list,
        *,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> Any:
        import requests

        model = kwargs.get("model", self.model)

        if stream:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                stream=True,
                timeout=120.0,
            )
            resp.raise_for_status()

            def _stream():
                for line in resp.iter_lines():
                    if line:
                        import json

                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk

            return _stream()
        else:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def raw_provider(self) -> Any:
        return None


class HalbertAppSeam:
    """AppSeam implementation for Halbert.

    Provides Haloysius's cognitive core with:
    - ModelBackend: Ollama-based LLM via HalbertModelBackend
    - RetrievalBackend: SourcePrep semantic search via SourcePrepRetrievalBackend
    - GovernancePolicy: Permissive policy via HalbertGovernancePolicy
    """

    def __init__(
        self,
        retrieval_backend: Optional[RetrievalBackend] = None,
        model_backend: Optional[ModelBackend] = None,
        governance: Optional[GovernancePolicy] = None,
    ):
        self._retrieval = retrieval_backend
        self._model = model_backend
        self._governance = governance

    def get_model_backend(self) -> Optional[ModelBackend]:
        return self._model

    def get_retrieval_backend(self) -> Optional[RetrievalBackend]:
        return self._retrieval

    def get_governance(self) -> Optional[GovernancePolicy]:
        return self._governance


def wire_halbert_seam(
    sourceprep_project_id: Optional[str] = None,
    sourceprep_url: Optional[str] = None,
    ollama_url: Optional[str] = None,
    model: Optional[str] = None,
    skip_retrieval: bool = False,
    skip_model: bool = False,
) -> HalbertAppSeam:
    """Wire Halbert's integration components into Haloysius's AppSeam.

    Call this once at application startup, after the SourcePrep daemon
    is running and the host config project is registered.

    Args:
        sourceprep_project_id: SourcePrep project ID for the host config
            tree. If None, reads from SOURCEPREP_PROJECT_ID env var.
        sourceprep_url: SourcePrep daemon URL. If None, reads from
            SOURCEPREP_URL env var, defaults to http://localhost:8400.
        ollama_url: Ollama URL. If None, reads from OLLAMA_URL env var.
        model: Default LLM model. If None, reads from HALBERT_MODEL env var.
        skip_retrieval: If True, don't wire the retrieval backend (for
            testing or when SourcePrep isn't running).
        skip_model: If True, don't wire the model backend.

    Returns:
        The HalbertAppSeam instance (also registered globally via
        register_app_seam).
    """
    retrieval_backend = None
    if not skip_retrieval:
        retrieval_backend = SourcePrepRetrievalBackend(
            project_id=sourceprep_project_id,
            base_url=sourceprep_url,
        )
        if retrieval_backend.load():
            logger.info("SourcePrep retrieval backend wired")
        else:
            logger.warning(
                "SourcePrep daemon not reachable — retrieval backend "
                "will return empty results"
            )

    model_backend = None
    if not skip_model:
        model_backend = HalbertModelBackend(
            ollama_url=ollama_url,
            model=model,
        )
        if model_backend.is_available():
            logger.info(f"Model backend wired (model={model_backend.model})")
        else:
            logger.warning(
                f"Ollama not reachable at {model_backend.ollama_url} — "
                "model backend will fail on chat calls"
            )

    governance = HalbertGovernancePolicy()

    seam = HalbertAppSeam(
        retrieval_backend=retrieval_backend,
        model_backend=model_backend,
        governance=governance,
    )

    register_app_seam(seam)
    logger.info("Halbert AppSeam registered with Haloysius")

    return seam
