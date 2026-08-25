"""
Anthropic (Claude) provider implementation - Phase 38.

Supports Claude models via the Anthropic API for high-quality
reasoning, vision, and general tasks.
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


# Claude model configurations
CLAUDE_MODELS = {
    'claude-3-5-sonnet-20241022': {
        'capabilities': [ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE, ModelCapability.TECHNICAL],
        'context_length': 200000,
        'memory_mb': 0,  # API - no local memory
        'vision': True,
        'max_output': 8192,
    },
    'claude-3-5-haiku-20241022': {
        'capabilities': [ModelCapability.CHAT, ModelCapability.FAST, ModelCapability.CODE],
        'context_length': 200000,
        'memory_mb': 0,
        'vision': True,
        'max_output': 8192,
    },
    'claude-3-opus-20240229': {
        'capabilities': [ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE, ModelCapability.TECHNICAL],
        'context_length': 200000,
        'memory_mb': 0,
        'vision': True,
        'max_output': 4096,
    },
    'claude-3-sonnet-20240229': {
        'capabilities': [ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE],
        'context_length': 200000,
        'memory_mb': 0,
        'vision': True,
        'max_output': 4096,
    },
    'claude-3-haiku-20240307': {
        'capabilities': [ModelCapability.CHAT, ModelCapability.FAST],
        'context_length': 200000,
        'memory_mb': 0,
        'vision': True,
        'max_output': 4096,
    },
}


class AnthropicProvider(ModelProvider):
    """
    Anthropic Claude API provider.
    
    Supports:
    - Claude 3.5 Sonnet (best quality)
    - Claude 3.5 Haiku (fast)
    - Claude 3 Opus (highest quality)
    - Vision/multimodal capabilities
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
        
        logger.info("Anthropic provider initialized")
    
    def list_models(self) -> List[ModelConfig]:
        """List available Claude models."""
        models = []
        
        for model_id, config in CLAUDE_MODELS.items():
            models.append(ModelConfig(
                model_id=model_id,
                provider="anthropic",
                capabilities=config['capabilities'],
                memory_mb=config['memory_mb'],
                context_length=config['context_length'],
                metadata={
                    'vision': config.get('vision', False),
                    'max_output': config.get('max_output', 4096),
                }
            ))
        
        return models
    
    def load_model(self, model_id: str, **kwargs) -> bool:
        """
        'Load' a model (API models are always available).
        
        Just validates the model ID exists.
        """
        if model_id not in CLAUDE_MODELS:
            raise ModelNotFoundError(f"Unknown Claude model: {model_id}")
        
        self._active_model = model_id
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
        """Generate text using Claude API."""
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
        Generate response using Claude chat API.
        
        Args:
            messages: List of {"role": "user|assistant", "content": "..."}
            model_id: Claude model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt
            images: List of base64 encoded images (for vision)
        
        Returns:
            ModelResponse with generated text
        """
        if model_id not in CLAUDE_MODELS:
            raise ModelNotFoundError(f"Unknown Claude model: {model_id}")
        
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
                f"Claude API error {status_code}: {e}",
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
        Stream chat response from Claude.
        
        Yields tokens as they are generated.
        """
        if model_id not in CLAUDE_MODELS:
            raise ModelNotFoundError(f"Unknown Claude model: {model_id}")
        
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
                f"Claude streaming error {status_code}: {e}",
                status_code=status_code,
                headers=headers,
            )
    
    def is_loaded(self, model_id: str) -> bool:
        """API models are always 'loaded'."""
        return model_id in CLAUDE_MODELS
    
    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model configuration."""
        if model_id not in CLAUDE_MODELS:
            raise ModelNotFoundError(f"Unknown Claude model: {model_id}")
        
        config = CLAUDE_MODELS[model_id]
        return ModelConfig(
            model_id=model_id,
            provider="anthropic",
            capabilities=config['capabilities'],
            memory_mb=config['memory_mb'],
            context_length=config['context_length'],
            metadata={
                'vision': config.get('vision', False),
                'max_output': config.get('max_output', 4096),
            }
        )
    
    def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        try:
            # Simple API validation
            self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False
    
    def has_vision(self, model_id: str) -> bool:
        """Check if model supports vision."""
        if model_id in CLAUDE_MODELS:
            return CLAUDE_MODELS[model_id].get('vision', False)
        return False
