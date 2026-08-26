# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Ollama provider implementation (Phase 5 M1).

Ollama is the primary production provider for Halbert.
Supports model management and generation.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import re
import requests
import time
import logging

from .base import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    ModelLoadError, ModelNotLoadedError, ModelNotFoundError, GenerationError
)
from ...utils.reasoning import is_reasoning_model

logger = logging.getLogger('halbert.model')

# Size tag in a model id, e.g. ":7b", "-14b", ":8b-instruct"
_SIZE_TAG_RE = re.compile(r"[:\-_](\d+(?:\.\d+)?)b\b", re.IGNORECASE)
_DEFAULT_CONTEXT_LENGTH = 4096  # Conservative default when the runtime does not report one


class OllamaProvider(ModelProvider):
    """
    Ollama provider for local LLM inference.
    
    Ollama provides:
    - Easy model management (pull, list, delete)
    - Efficient quantized models
    - API-based inference
    - Multi-model support
    
    Phase 5 M1: Basic provider implementation
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama API endpoint (default: localhost:11434)
        """
        self.base_url = base_url.rstrip('/')
        self._loaded_models: Dict[str, ModelConfig] = {}
        # Per-model metadata from /api/show (capabilities, context length),
        # cached because list_models() is called on every load/get_model_info.
        self._show_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"Ollama provider initialized: {base_url}")
    
    def list_models(self) -> List[ModelConfig]:
        """List available models from Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            
            data = response.json()
            models = []
            
            for model_data in data.get("models", []):
                model_id = model_data.get("name", "")
                
                # Runtime metadata (capabilities, context length) from /api/show
                show = self.show_model(model_id)
                capabilities = self._infer_capabilities(model_id, show)
                
                # Estimate memory from size
                size_bytes = model_data.get("size", 0)
                memory_mb = int(size_bytes / (1024 * 1024))
                
                config = ModelConfig(
                    model_id=model_id,
                    provider="ollama",
                    capabilities=capabilities,
                    memory_mb=memory_mb,
                    context_length=self._infer_context_length(model_id, show),
                    quantization=self._extract_quantization(model_id),
                    metadata={
                        "size_bytes": size_bytes,
                        "modified": model_data.get("modified_at"),
                        "family": model_data.get("details", {}).get("family"),
                        "runtime_capabilities": list(show.get("capabilities") or []),
                        "vision": "vision" in (show.get("capabilities") or []),
                    }
                )
                
                models.append(config)
            
            logger.info(f"Listed {len(models)} models from Ollama")
            return models
        
        except requests.RequestException as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []
    
    def load_model(self, model_id: str, **kwargs) -> bool:
        """
        Load a model into Ollama's memory.
        
        Note: Ollama loads models on first generate() call.
        This method pulls the model if not available.
        """
        try:
            # Check if model exists
            models = self.list_models()
            if not any(m.model_id == model_id for m in models):
                # Pull model
                logger.info(f"Pulling Ollama model: {model_id}")
                response = requests.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_id},
                    timeout=600  # 10 minutes for large models
                )
                response.raise_for_status()
            
            # Mark as loaded (will actually load on first use)
            config = self.get_model_info(model_id)
            self._loaded_models[model_id] = config
            
            logger.info(f"Model ready: {model_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            raise ModelLoadError(f"Failed to load {model_id}: {e}")
    
    def unload_model(self, model_id: str) -> bool:
        """
        Unload a model from memory.
        
        Note: Ollama manages memory automatically.
        This just removes from our tracking.
        """
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
            logger.info(f"Unloaded model: {model_id}")
            return True
        return False
    
    def generate(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        """Generate text using Ollama."""
        start_time = time.time()
        
        try:
            # Prepare request
            request_data = {
                "model": model_id,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    **kwargs.get("options", {})
                }
            }
            
            # Send generation request
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=request_data,
                timeout=120  # 2 minutes
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract tokens
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
            total_tokens = prompt_tokens + completion_tokens
            
            return ModelResponse(
                text=data.get("response", ""),
                model_id=model_id,
                provider="ollama",
                tokens_used=total_tokens,
                latency_ms=latency_ms,
                metadata={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "done": data.get("done", False)
                }
            )
        
        except requests.RequestException as e:
            logger.error(f"Ollama generation failed: {e}")
            raise GenerationError(f"Generation failed: {e}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        """
        Generate response using chat format with proper message arrays.
        
        This is the preferred method for conversation - LLMs understand
        structured roles better than concatenated prompt strings.
        
        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}
            model_id: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        
        Returns:
            ModelResponse with generated text
        """
        start_time = time.time()
        
        try:
            request_data = {
                "model": model_id,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    **kwargs.get("options", {})
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=request_data,
                timeout=180  # 3 minutes for complex responses
            )
            response.raise_for_status()
            
            data = response.json()
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract token counts
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
            total_tokens = prompt_tokens + completion_tokens
            
            return ModelResponse(
                text=data.get("message", {}).get("content", ""),
                model_id=model_id,
                provider="ollama",
                tokens_used=total_tokens,
                latency_ms=latency_ms,
                metadata={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "done": data.get("done", False)
                }
            )
        
        except requests.RequestException as e:
            logger.error(f"Ollama chat failed: {e}")
            raise GenerationError(f"Chat generation failed: {e}")

    def is_loaded(self, model_id: str) -> bool:
        """Check if model is in our loaded tracking."""
        return model_id in self._loaded_models
    
    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model configuration from Ollama."""
        models = self.list_models()
        
        for model in models:
            if model.model_id == model_id:
                return model
        
        raise ModelNotFoundError(f"Model not found: {model_id}")
    
    def health_check(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def show_model(self, model_id: str) -> Dict[str, Any]:
        """
        Fetch runtime metadata for a model via ``POST /api/show``.

        Returns a dict with:
        - ``capabilities``: list of labels reported by Ollama (may contain
          "completion", "vision", "thinking", "tools", "embedding")
        - ``context_length``: int from ``model_info["<arch>.context_length"]``
          when reported, else None
        - ``family``: model family string from ``details`` when reported

        Results are cached per model id for the lifetime of the provider;
        failures are not cached and yield an empty dict.
        """
        if not model_id:
            return {}
        cached = self._show_cache.get(model_id)
        if cached is not None:
            return cached
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"model": model_id, "name": model_id},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json() or {}
        except Exception as e:  # noqa: BLE001 - metadata is best-effort
            logger.debug(f"/api/show failed for {model_id}: {e}")
            return {}
        
        context_length: Optional[int] = None
        model_info = data.get("model_info") or {}
        if isinstance(model_info, dict):
            for key, value in model_info.items():
                if str(key).endswith(".context_length") and isinstance(value, (int, float)) and value > 0:
                    context_length = int(value)
                    break
        
        info = {
            "capabilities": [str(c).lower() for c in (data.get("capabilities") or [])],
            "context_length": context_length,
            "family": (data.get("details") or {}).get("family"),
        }
        self._show_cache[model_id] = info
        return info
    
    def _infer_capabilities(
        self, model_id: str, show: Optional[Dict[str, Any]] = None
    ) -> List[ModelCapability]:
        """
        Infer model capabilities from runtime metadata, then generic tokens.

        Never keys on vendor or model-family names: uses the ``capabilities``
        list from ``/api/show`` when available, otherwise generic substrings
        ("code"/"coder", "think"/"reason") and parameter-size tags.
        """
        capabilities = [ModelCapability.CHAT]  # All models can chat
        
        model_lower = model_id.lower()
        runtime_caps = list((show or {}).get("capabilities") or [])
        
        # Code models
        if "code" in model_lower:  # also matches "coder"
            capabilities.append(ModelCapability.CODE)
        
        # Reasoning / thinking models
        if is_reasoning_model(model_lower, runtime_caps or None):
            capabilities.append(ModelCapability.REASONING)
        
        # Fast models (smaller parameter counts)
        size_match = _SIZE_TAG_RE.search(model_lower)
        if size_match and float(size_match.group(1)) <= 14:
            capabilities.append(ModelCapability.FAST)
        
        return capabilities
    
    def _infer_context_length(
        self, model_id: str, show: Optional[Dict[str, Any]] = None
    ) -> int:
        """Context length from ``/api/show`` when reported, else a conservative default."""
        if show is None:
            show = self.show_model(model_id)
        ctx = (show or {}).get("context_length")
        if isinstance(ctx, int) and ctx > 0:
            return ctx
        return _DEFAULT_CONTEXT_LENGTH
    
    def _extract_quantization(self, model_id: str) -> Optional[str]:
        """Extract quantization level from model name."""
        # Common Ollama quantizations: Q4_0, Q4_K_M, Q5_K_M, Q8_0, etc.
        import re
        match = re.search(r'[Qq][4-8]_[0KM_]+', model_id)
        if match:
            return match.group(0)
        return None
