# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Anthropic provider implementation - Phase 38.

Talks to the Anthropic Messages API. Model ids are passed straight
through to the API; the model to use comes from models.yml, never from
a list baked into this module.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Iterator
import os
import time
import logging
import base64

from .base import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    ModelLoadError, ModelNotLoadedError, ModelNotFoundError, GenerationError
)

logger = logging.getLogger('halbert.model.anthropic')

# Anthropic SDK is optional - only import if available
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.debug("anthropic package not installed - Anthropic provider unavailable")


def _extract_http_context(exc: Exception) -> tuple:
    """Duck-type an Anthropic SDK exception for HTTP status + headers.

    ``APIStatusError`` subclasses (RateLimitError 429, overloaded 529, 5xx)
    carry ``.status_code`` and ``.response.headers``. We duck-type rather than
    reference ``anthropic.APIStatusError`` by name so this is robust across
    SDK versions and importable even when the SDK isn't installed. Returns
    ``(status_code, headers)`` where either may be ``None``.

    Used to populate ``GenerationError(status_code=..., headers=...)`` (A2b)
    so the ``RateLimiter`` can parse ``Retry-After``.
    """
    status_code = getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)
    headers = None
    if resp is not None and hasattr(resp, "headers"):
        try:
            headers = dict(resp.headers)
        except (TypeError, ValueError):
            headers = None
    return status_code, headers


# Provider-level facts that hold for every model behind the Messages API.
# Per-model differences (max output, thinking support) are not enumerated
# here; declare them in models.yml ``capabilities:`` if routing needs them.
_PROVIDER_CAPABILITIES = [ModelCapability.CHAT, ModelCapability.CODE, ModelCapability.TECHNICAL]
_PROVIDER_CONTEXT_LENGTH = 200000
_PROVIDER_MAX_OUTPUT = 4096


class AnthropicProvider(ModelProvider):
    """
    Anthropic Messages API provider.
    
    Supports:
    - Any model id accepted by the Anthropic Messages API
    - Vision/multimodal input
    - Tool use / function calling
    
    Requires ANTHROPIC_API_KEY environment variable.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Anthropic provider.
        
        Args:
            api_key: Anthropic API key (or reads from ANTHROPIC_API_KEY env)
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required: pip install anthropic")
        
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self._active_model: Optional[str] = None
        # Model ids this provider has been asked to use (configured ids);
        # used as the list_models() fallback when the API listing fails.
        self._known_models: List[str] = []
        
        logger.info("Anthropic provider initialized")
    
    def _model_config(self, model_id: str, display_name: Optional[str] = None) -> ModelConfig:
        """Build a ModelConfig from provider-level facts (no per-model table)."""
        metadata: Dict[str, Any] = {
            'vision': True,
            'max_output': _PROVIDER_MAX_OUTPUT,
        }
        if display_name:
            metadata['display_name'] = display_name
        return ModelConfig(
            model_id=model_id,
            provider="anthropic",
            capabilities=list(_PROVIDER_CAPABILITIES),
            memory_mb=0,  # API - no local memory
            context_length=_PROVIDER_CONTEXT_LENGTH,
            metadata=metadata,
        )
    
    def _remember(self, model_id: str) -> None:
        if model_id and model_id not in self._known_models:
            self._known_models.append(model_id)
    
    def list_models(self) -> List[ModelConfig]:
        """
        List models available to this API key via ``client.models.list()``.
        
        Falls back to the ids this provider has been configured with
        (``load_model`` / ``chat`` calls) when the listing endpoint is
        unavailable, so callers still see the configured model.
        """
        models: List[ModelConfig] = []
        try:
            page = self.client.models.list()
            seen = set()
            for item in getattr(page, 'data', None) or page or []:
                model_id = getattr(item, 'id', None) or (item.get('id') if isinstance(item, dict) else None)
                if not model_id or model_id in seen:
                    continue
                seen.add(model_id)
                display_name = getattr(item, 'display_name', None)
                models.append(self._model_config(model_id, display_name))
        except Exception as e:  # noqa: BLE001 - listing is best-effort
            logger.warning(f"Anthropic models.list() unavailable, using configured ids: {e}")
        
        if not models:
            models = [self._model_config(mid) for mid in self._known_models]
        return models
    
    def load_model(self, model_id: str, **kwargs) -> bool:
        """
        'Load' a model (API models are always available).
        
        The id is passed through to the API as-is; an unknown id surfaces
        as an API error on first use rather than being rejected here.
        """
        if not model_id:
            raise ModelNotFoundError(
                "No model configured — choose one in Settings → AI Models"
            )
        self._active_model = model_id
        self._remember(model_id)
        logger.info(f"Anthropic model selected: {model_id}")
        return True
    
    def unload_model(self, model_id: str) -> bool:
        """Unload model (no-op for API)."""
        if self._active_model == model_id:
            self._active_model = None
        return True
    
    def generate(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        """Generate text using the Anthropic Messages API."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def chat(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> ModelResponse:
        """
        Generate response using the Anthropic Messages API.
        
        Args:
            messages: List of {"role": "user|assistant", "content": "..."}
            model_id: Model id to use (passed through to the API)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt
            images: List of base64 encoded images (for vision)
        
        Returns:
            ModelResponse with generated text
        """
        if not model_id:
            raise ModelNotFoundError(
                "No model configured — choose one in Settings → AI Models"
            )
        self._remember(model_id)
        
        start_time = time.time()
        
        try:
            # Convert messages to Anthropic format
            anthropic_messages = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                # Map 'system' role to first user message (Anthropic uses separate system param)
                if role == 'system':
                    if not system:
                        system = content
                    continue
                
                # Handle vision content
                if role == 'user' and images:
                    content_blocks = []
                    for img in images:
                        # Detect image type from base64 header or default to jpeg
                        media_type = "image/jpeg"
                        if img.startswith("data:"):
                            # Extract media type from data URL
                            media_type = img.split(";")[0].split(":")[1]
                            img = img.split(",")[1]
                        
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img,
                            }
                        })
                    content_blocks.append({"type": "text", "text": content})
                    anthropic_messages.append({"role": role, "content": content_blocks})
                else:
                    anthropic_messages.append({"role": role, "content": content})
            
            # Make API call
            response = self.client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system or "You are a helpful assistant.",
                messages=anthropic_messages,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract response text
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            
            return ModelResponse(
                text=text,
                model_id=model_id,
                provider="anthropic",
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                latency_ms=latency_ms,
                metadata={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "stop_reason": response.stop_reason,
                }
            )
        
        except anthropic.APIError as e:
            status_code, headers = _extract_http_context(e)
            logger.error(f"Anthropic API error {status_code}: {e}")
            raise GenerationError(
                f"Anthropic API error {status_code}: {e}",
                status_code=status_code,
                headers=headers,
            )
        except Exception as e:
            logger.error(f"Anthropic generation failed: {e}")
            raise GenerationError(f"Generation failed: {e}")
    
    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Stream chat response from the Anthropic Messages API.
        
        Yields tokens as they are generated.
        """
        if not model_id:
            raise ModelNotFoundError(
                "No model configured — choose one in Settings → AI Models"
            )
        self._remember(model_id)
        
        try:
            # Convert messages to Anthropic format
            anthropic_messages = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                
                if role == 'system':
                    if not system:
                        system = content
                    continue
                
                anthropic_messages.append({"role": role, "content": content})
            
            # Stream response
            with self.client.messages.stream(
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system or "You are a helpful assistant.",
                messages=anthropic_messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        
        except anthropic.APIError as e:
            status_code, headers = _extract_http_context(e)
            logger.error(f"Anthropic streaming error {status_code}: {e}")
            raise GenerationError(
                f"Anthropic streaming error {status_code}: {e}",
                status_code=status_code,
                headers=headers,
            )
    
    def is_loaded(self, model_id: str) -> bool:
        """API models are always 'loaded' (any non-empty id)."""
        return bool(model_id)
    
    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model configuration built from provider-level facts."""
        if not model_id:
            raise ModelNotFoundError(
                "No model configured — choose one in Settings → AI Models"
            )
        return self._model_config(model_id)
    
    def health_check(self, model_id: Optional[str] = None) -> bool:
        """
        Check that the Anthropic API is reachable with this key.
        
        Probes with the model it is asked about (``model_id``), else the
        active model selected via ``load_model``. When neither is known
        it falls back to ``client.models.list()``, which validates the
        key without sending a message to any particular model.
        """
        probe_model = model_id or self._active_model
        try:
            if probe_model:
                self.client.messages.create(
                    model=probe_model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}]
                )
            else:
                self.client.models.list(limit=1)
            return True
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False
    
    def has_vision(self, model_id: str) -> bool:
        """
        Check if model supports vision.
        
        Provider-level fact: models behind the Messages API accept image
        input. Declare ``capabilities: {vision: false}`` in models.yml for
        a model that should not be routed images.
        """
        return bool(model_id)
