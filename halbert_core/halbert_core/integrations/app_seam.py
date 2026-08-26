# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert App Seam

Implements Haloysius's AppSeam Protocols (ModelBackend, RetrievalBackend,
GovernancePolicy) and registers a HalbertAppSeam via ``register_app_seam``.

What the seam actually is: Haloysius defines the seam Protocols in
``haloysius.seam`` but has no internal call sites — nothing in Haloysius's
core reads ``get_app_seam()``. The seam is a consumer-side contract, and its
consumers are Halbert-side: ``integrations.cognition_wiring`` reads the
registered model backend and hands ``HalbertModelBackend.generate_text`` to
a ``ThoughtGenerator`` for ``advance_turn`` (when HALBERT_LLM_THOUGHTS is
enabled). ``RetrievalBackend.search()`` is consumed by
``context.adapters.SourcePrepAdapter`` directly, not via the seam registry.

haloysius is imported lazily (inside ``wire_halbert_seam``), so this module
is importable without the cognition extra; the Protocol names below are
annotation-only.

Called once at application startup:
    from halbert_core.integrations.app_seam import wire_halbert_seam
    wire_halbert_seam()
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # Protocol names are annotation-only (PEP 563 via __future__ annotations)
    from haloysius.seam import GovernancePolicy, ModelBackend, RetrievalBackend

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

    Implements Haloysius's ModelBackend Protocol on top of Halbert's TierRouter
    (``model/tier_router.py``). Haloysius itself never calls this; its one real
    consumer is ``cognition_wiring``, which passes ``generate_text`` to a
    ``ThoughtGenerator``. Non-streaming ``chat()`` calls are flattened
    to a prompt and routed through ``TierRouter.generate()`` so they get
    tier selection, health-based fallback, rate-limit retry, and outcome
    recording. A raw Ollama ``/api/chat`` call remains as the safety net
    and is used when:

    - the router can't be built or has no models configured (no models.yml),
    - the router raises during generation,
    - ``stream=True`` (TierRouter has no streaming API), or
    - the caller pins an explicit ``model=`` kwarg (the router picks models
      itself, so a pinned model id goes straight to Ollama).

    Configuration converges on the agent's own: the router reads
    ``get_config_dir()/models.yml`` (the same file ``model.client`` reads) and
    the raw-Ollama defaults are explicit arg -> env (HALBERT_MODEL /
    OLLAMA_URL) -> ``model.client.get_configured_model()`` /
    ``get_ollama_endpoint()``.

    TierRouter is imported lazily inside ``_get_tier_router`` so this module
    stays importable regardless of model-package import order.
    """

    def __init__(self, ollama_url: Optional[str] = None, model: Optional[str] = None):
        self._explicit_model = model or os.environ.get("HALBERT_MODEL")
        self.model = self._explicit_model or self._configured_guide_model()
        self.ollama_url = (
            ollama_url or os.environ.get("OLLAMA_URL") or self._configured_endpoint()
        )
        self._tier_router: Any = None
        self._tier_router_unavailable = False

    @staticmethod
    def _configured_guide_model() -> str:
        """Same guide model the agent uses (models.yml via get_configured_model)."""
        try:
            from ..model.client import get_configured_model

            return get_configured_model()
        except Exception:
            return ""  # no guide model resolvable; chat() raises before posting model=""

    @staticmethod
    def _configured_endpoint() -> str:
        """Same Ollama endpoint the agent uses (via get_ollama_endpoint)."""
        try:
            from ..model.client import get_ollama_endpoint

            return get_ollama_endpoint()
        except Exception:
            return "http://localhost:11434"

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

            from ..model.config_locator import find_models_config, user_models_config

            # Same lookup semantics as the chat client: env override, then the
            # user config dir (never the repo checkout). If no user file
            # exists we deliberately do NOT construct TierRouter, because its
            # own _find_config would fall through to the repo config/models.yml
            # (with its Tailscale specialist) and silently diverge from chat.
            path = find_models_config(include_repo=False) or user_models_config()
            if not path.is_file():
                logger.warning(
                    f"No user models.yml at {path} — TierRouter unavailable; "
                    "HalbertModelBackend will use raw Ollama"
                )
                self._tier_router_unavailable = True
                return None
            router = TierRouter(config_path=path)
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

        if not model:
            raise ValueError(
                "No model configured — choose one in Settings → AI Models "
                "(or pass model= / set HALBERT_MODEL)"
            )

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

    def generate_text(self, prompt: str) -> str:
        """Callable[[str], str] adapter for haloysius ThoughtGenerator(llm_generate=...)."""
        out = self.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=256)
        return out if isinstance(out, str) else "".join(out)

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

    Bundles:
    - ModelBackend: TierRouter/Ollama LLM via HalbertModelBackend
    - RetrievalBackend: SourcePrep semantic search via SourcePrepRetrievalBackend
    - GovernancePolicy: Permissive policy via HalbertGovernancePolicy

    Haloysius defines the AppSeam Protocol but has no internal call sites for
    it; consumers of ``get_app_seam()`` are Halbert-side (cognition_wiring
    passes the model backend to ThoughtGenerator). RetrievalBackend.search()
    is consumed by context/adapters.SourcePrepAdapter, not via this registry.
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
    """Build a HalbertAppSeam and register it with haloysius.seam.

    Idempotent enough to call more than once (re-registers). Haloysius does
    not read the registry itself; see the module docstring for who does.

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

    from haloysius.seam import register_app_seam  # lazy: haloysius is optional at import time

    register_app_seam(seam)
    logger.info("Halbert AppSeam registered with haloysius.seam")

    return seam
