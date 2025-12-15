"""
MLX provider implementation (Phase 5 M1).

Mac Apple Silicon optimized provider using MLX/MLX-LM.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import logging
import json
import time

from .base import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    ModelLoadError, ModelNotLoadedError, ModelNotFoundError, GenerationError
)

logger = logging.getLogger('halbert.model')

# Try to import MLX (optional dependency)
try:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load, generate, convert
    from mlx_lm.utils import load as load_model_utils
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    logger.warning("MLX not available - install with: pip install mlx mlx-lm")


class MLXProvider(ModelProvider):
    """
    MLX provider for Mac Apple Silicon.
    
    Benefits:
    - Optimized for Apple Silicon (M1/M2/M3)
    - Excellent performance on Mac
    - Unified memory architecture
    
    Requirements:
    - Mac with Apple Silicon
    - mlx and mlx-lm packages
    - macOS 13.3 or later
    """
    
    def __init__(self, model_dir: Optional[str] = None, cache_dir: Optional[str] = None):
        """
        Initialize MLX provider.
        
        Args:
            model_dir: Directory containing MLX model files
            cache_dir: Cache directory for downloaded models
        """
        if not MLX_AVAILABLE:
            raise ImportError("MLX not available. Install with: pip install mlx mlx-lm")
        
        self.model_dir = Path(model_dir) if model_dir else Path.home() / ".cache" / "halbert" / "mlx_models"
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "huggingface" / "hub"
        
        self._loaded_models: Dict[str, Tuple[Any, Any]] = {}  # model_id -> (model, tokenizer)
        
        # Create directories
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("MLX provider initialized")
        logger.info("MLX provider optimized for Mac Apple Silicon (128GB unified memory)")
        logger.info(f"Model directory: {self.model_dir}")
        logger.info(f"Cache directory: {self.cache_dir}")
    
    def list_models(self) -> List[ModelConfig]:
        """
        List available MLX models in cache.
        
        Scans the model directory for available models.
        """
        models = []
        
        if self.model_dir.exists():
            for model_path in self.model_dir.iterdir():
                if model_path.is_dir():
                    # Check if it has model files
                    if (model_path / "config.json").exists():
                        model_id = model_path.name
                        models.append(ModelConfig(
                            model_id=model_id,
                            provider="mlx",
                            capabilities=[ModelCapability.CHAT, ModelCapability.CODE],
                            context_length=8192,  # Default, read from config if available
                            memory_mb=8000,  # Estimate
                        ))
        
        logger.info(f"Found {len(models)} MLX models in cache")
        return models
    
    def load_model(self, model_id: str, **kwargs) -> bool:
        """
        Load a model with MLX.
        
        Args:
            model_id: Model identifier (HuggingFace format)
            **kwargs: Additional arguments for model loading
        
        Returns:
            True if successful
        
        Example:
            provider.load_model("mlx-community/Llama-3.1-8B-Instruct-4bit")
        """
        if model_id in self._loaded_models:
            logger.info(f"Model already loaded: {model_id}")
            return True
        
        try:
            logger.info(f"Loading MLX model: {model_id}")
            start_time = time.time()
            
            # Load model and tokenizer using mlx-lm
            model, tokenizer = load(model_id)
            
            # Store in cache
            self._loaded_models[model_id] = (model, tokenizer)
            
            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f}s: {model_id}")
            
            # Log memory usage
            memory_info = self.get_memory_usage()
            if memory_info:
                logger.info(f"Memory usage: {memory_info}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            raise ModelLoadError(f"Failed to load MLX model: {e}")
    
    def unload_model(self, model_id: str) -> bool:
        """Unload model from memory."""
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
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
        """
        Generate text with MLX.
        
        Args:
            prompt: Input prompt
            model_id: Model identifier
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional generation parameters
        
        Returns:
            ModelResponse with generated text
        """
        if model_id not in self._loaded_models:
            raise ModelNotLoadedError(f"Model not loaded: {model_id}")
        
        try:
            model, tokenizer = self._loaded_models[model_id]
            
            start_time = time.time()
            
            # Generate using mlx-lm
            logger.debug(f"Generating with MLX model: {model_id}")
            
            # mlx-lm generate function
            response_text = generate(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temperature,
                **kwargs
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Estimate token count (rough)
            tokens_used = len(response_text.split())
            
            logger.info(f"Generated {tokens_used} tokens in {latency_ms}ms")
            
            return ModelResponse(
                text=response_text,
                model_id=model_id,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                finish_reason="complete"
            )
        
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise GenerationError(f"MLX generation failed: {e}")
    
    def is_loaded(self, model_id: str) -> bool:
        """Check if model is loaded."""
        return model_id in self._loaded_models
    
    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model configuration."""
        raise ModelNotFoundError(f"Model not found: {model_id}")
    
    def health_check(self) -> bool:
        """Check if MLX is available."""
        try:
            import mlx
            import mlx_lm
            return True
        except ImportError:
            return False
    
    def get_memory_usage(self) -> Dict[str, int]:
        """
        Get current memory usage on Apple Silicon.
        
        MLX has excellent memory introspection for unified memory.
        
        Returns:
            Dict with memory stats in MB
        """
        try:
            # MLX provides Metal memory stats on Apple Silicon
            from mlx.core import metal
            
            # Get peak memory usage
            peak_memory_bytes = metal.get_peak_memory()
            active_memory_bytes = metal.get_active_memory()
            
            return {
                "peak_mb": peak_memory_bytes // (1024 * 1024),
                "active_mb": active_memory_bytes // (1024 * 1024),
                "models_loaded": len(self._loaded_models),
            }
        except Exception as e:
            logger.debug(f"Could not get memory usage: {e}")
            return {
                "models_loaded": len(self._loaded_models),
            }
