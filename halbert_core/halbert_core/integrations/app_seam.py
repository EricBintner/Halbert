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
    """ModelBackend adapter wrapping Halbert's LLM routing.

    Bridges Haloysius's ModelBackend protocol to Halbert's TierRouter
    (``model/tier_router.py``): non-streaming ``chat()`` calls are flattened
    to a prompt and routed through ``TierRouter.generate()`` so they get
    tier selection, health-based fallback, rate-limit retry, and outcome
    recording. A raw Ollama ``/api/chat`` call remains as the safety net
    and is used when:

    - the router can't be built or has no models configured (no models.yml),
    - the router raises during generation,
    - ``stream=True`` (TierRouter has no streaming API), or
    - the caller pins an explicit ``model=`` kwarg (the router picks models
      itself, so a pinned model id goes straight to Ollama).

    TierRouter is imported lazily inside ``_get_tier_router`` so this module
    stays importable regardless of model-package import order.
    """

    def __init__(self, ollama_url: Optional[str] = None, model: Optional[str] = None):
        self.ollama_url = ollama_url or os.environ.get(
            "OLLAMA_URL", "http://localhost:11434"
        )
        self.model = model or os.environ.get("HALBERT_MODEL", "llama3.2")
        self._tier_router: Any = None
        self._tier_router_unavailable = False

    # -- TierRouter access -------------------------------------------------

    def _get_tier_router(self) -> Any:
        """Return a cached TierRouter, or None if it can't route anything.

        Construction is attempted once; a router with an empty model table
        (models.yml not found) is treated as unavailable so ``chat()`` doesn't
        raise ``ModelNotFoundError`` on every call.
        """
        if self._tier_router is not None or self._tier_router_unavailable:
            return self._tier_router
        try:
            from ..model.tier_router import TierRouter  # lazy: import-order safety

            router = TierRouter()
            models = getattr(getattr(router, "config", None), "models", None)
            if not models:
                logger.warning(
                    "TierRouter has no models configured (models.yml not found?) — "
                    "HalbertModelBackend will use raw Ollama"
                )
                self._tier_router_unavailable = True
                return None
            self._tier_router = router
        except Exception as e:
            logger.warning(
                f"TierRouter unavailable ({e}) — HalbertModelBackend will use raw Ollama"
            )
            self._tier_router_unavailable = True
        return self._tier_router

    @staticmethod
    def _messages_to_prompt(messages: list) -> str:
        """Flatten a chat message list into a single prompt for TierRouter.generate()."""
        parts = []
        for m in messages:
            role = (m.get("role") or "user").lower()
            content = m.get("content") or ""
            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    # -- ModelBackend protocol ---------------------------------------------

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
        pinned_model = kwargs.pop("model", None)

        if not stream and pinned_model is None:
            router = self._get_tier_router()
            if router is not None:
                try:
                    response, _selection = router.generate(
                        prompt=self._messages_to_prompt(messages),
                        prefer_specialist=kwargs.pop("prefer_specialist", False),
                        task_type=kwargs.pop("task_type", None),
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                    return getattr(response, "text", "") or ""
                except Exception as e:
                    logger.warning(
                        f"TierRouter generation failed ({e}); falling back to raw Ollama"
                    )

        return self._chat_ollama(
            messages,
            model=pinned_model or self.model,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _chat_ollama(
        self,
        messages: list,
        *,
        model: str,
        stream: bool,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Safety-net path: direct Ollama /api/chat call (streaming or not)."""
        import requests

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if stream:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                stream=True,
                timeout=120.0,
            )
            resp.raise_for_status()

            def _stream():
                import json

                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk

            return _stream()

        resp = requests.post(
            f"{self.ollama_url}/api/chat",
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    def raw_provider(self) -> Any:
        """Return the TierRouter's guide-tier provider, or None if unrouted."""
        router = self._get_tier_router()
        if router is None:
            return None
        try:
            from ..model.capabilities import ModelTier

            selection = router.select_model(ModelTier.GUIDE)
            return router._get_provider(selection.model)
        except Exception as e:
            logger.debug(f"raw_provider: no guide provider available ({e})")
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
