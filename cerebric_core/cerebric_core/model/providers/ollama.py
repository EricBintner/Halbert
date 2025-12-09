"""
Ollama provider implementation (Phase 5 M1).

Ollama is the primary production provider for Cerebric.
Supports model management, generation, and LoRA adapters.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import requests
import time
import logging

from .base import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    ModelLoadError, ModelNotLoadedError, ModelNotFoundError, GenerationError
)

logger = logging.getLogger('cerebric.model')


class OllamaProvider(ModelProvider):
    """
    Ollama provider for local LLM inference.
    
    Ollama provides:
    - Easy model management (pull, list, delete)
    - Efficient quantized models
    - API-based inference
    - Multi-model support
    
    Phase 5 M1: Basic provider implementation
    Phase 5 M4: LoRA adapter support (if Ollama adds it)
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama API endpoint (default: localhost:11434)
        """
        self.base_url = base_url.rstrip('/')
        self._loaded_models: Dict[str, ModelConfig] = {}
        
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
                
                # Parse capabilities from model name
                capabilities = self._infer_capabilities(model_id)
                
                # Estimate memory from size
                size_bytes = model_data.get("size", 0)
                memory_mb = int(size_bytes / (1024 * 1024))
                
                config = ModelConfig(
                    model_id=model_id,
                    provider="ollama",
                    capabilities=capabilities,
                    memory_mb=memory_mb,
                    context_length=self._infer_context_length(model_id),
                    quantization=self._extract_quantization(model_id),
                    metadata={
                        "size_bytes": size_bytes,
                        "modified": model_data.get("modified_at"),
                        "family": model_data.get("details", {}).get("family")
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
    
    def _infer_capabilities(self, model_id: str) -> List[ModelCapability]:
        """Infer model capabilities from model name."""
        capabilities = [ModelCapability.CHAT]  # All models can chat
        
        model_lower = model_id.lower()
        
        # Code models
        if any(kw in model_lower for kw in ["code", "coder", "qwen2.5-coder", "deepseek-coder"]):
            capabilities.append(ModelCapability.CODE)
        
        # Reasoning models
        if any(kw in model_lower for kw in ["deepseek", "qwen", "llama-3.1"]):
            capabilities.append(ModelCapability.REASONING)
        
        # Fast models (smaller parameter counts)
        if any(kw in model_lower for kw in ["7b", "8b", "14b"]):
            capabilities.append(ModelCapability.FAST)
        
        # Technical models
        if any(kw in model_lower for kw in ["llama", "mistral"]):
            capabilities.append(ModelCapability.TECHNICAL)
        
        return capabilities
    
    def _infer_context_length(self, model_id: str) -> int:
        """Infer context length from model name."""
        model_lower = model_id.lower()
        
        # Known context lengths
        if "llama-3.1" in model_lower:
            return 128000  # Llama 3.1 has 128k context
        elif "llama-3" in model_lower:
            return 8192
        elif "qwen2.5" in model_lower:
            return 32768
        elif "deepseek" in model_lower:
            return 16384
        else:
            return 4096  # Conservative default
    
    def _extract_quantization(self, model_id: str) -> Optional[str]:
        """Extract quantization level from model name."""
        # Common Ollama quantizations: Q4_0, Q4_K_M, Q5_K_M, Q8_0, etc.
        import re
        match = re.search(r'[Qq][4-8]_[0KM_]+', model_id)
        if match:
            return match.group(0)
        return None
