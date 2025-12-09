"""
Base model provider interface (Phase 5 M1).

Defines the contract that all model providers must implement.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger('cerebric.model')


class ModelCapability(str, Enum):
    """Model capabilities for routing decisions."""
    CHAT = "chat"                    # General conversation
    CODE = "code"                    # Code generation/analysis
    REASONING = "reasoning"          # Complex problem-solving
    FAST = "fast"                    # Low-latency responses
    TECHNICAL = "technical"          # Technical/system tasks


@dataclass
class ModelConfig:
    """
    Model configuration.
    
    Defines a model's identity, capabilities, and resource requirements.
    """
    model_id: str                    # e.g., "llama3.1:8b-instruct"
    provider: str                    # "ollama", "llamacpp", "mlx"
    capabilities: List[ModelCapability]
    memory_mb: int                   # Estimated memory usage
    context_length: int              # Max context tokens
    quantization: Optional[str] = None  # e.g., "Q5_K_M", "Q8_0"
    parameters: Optional[Dict[str, Any]] = None  # Provider-specific params
    metadata: Optional[Dict[str, Any]] = None    # Description, tags, etc.


@dataclass
class ModelResponse:
    """
    Model response from generation.
    
    Standardized response across all providers.
    """
    text: str                        # Generated text
    model_id: str                    # Model that generated response
    provider: str                    # Provider used
    tokens_used: int                 # Total tokens (prompt + completion)
    latency_ms: float                # Generation time
    metadata: Optional[Dict[str, Any]] = None  # Provider-specific data


class ModelProvider(ABC):
    """
    Abstract base class for model providers.
    
    All model backends (Ollama, llama.cpp, MLX) must implement this interface.
    
    Phase 5 M1: Basic provider abstraction
    Phase 5 M2: Context handoff support
    Phase 5 M4: LoRA adapter support
    """
    
    @abstractmethod
    def list_models(self) -> List[ModelConfig]:
        """
        List available models from this provider.
        
        Returns:
            List of ModelConfig objects
        """
        pass
    
    @abstractmethod
    def load_model(self, model_id: str, **kwargs) -> bool:
        """
        Load a model into memory.
        
        Args:
            model_id: Model identifier
            **kwargs: Provider-specific parameters
        
        Returns:
            True if load successful
        
        Raises:
            ModelLoadError: If model cannot be loaded
        """
        pass
    
    @abstractmethod
    def unload_model(self, model_id: str) -> bool:
        """
        Unload a model from memory.
        
        Args:
            model_id: Model identifier
        
        Returns:
            True if unload successful
        """
        pass
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        """
        Generate text from a model.
        
        Args:
            prompt: Input prompt
            model_id: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Provider-specific generation parameters
        
        Returns:
            ModelResponse with generated text
        
        Raises:
            ModelNotLoadedError: If model not loaded
            GenerationError: If generation fails
        """
        pass
    
    @abstractmethod
    def is_loaded(self, model_id: str) -> bool:
        """
        Check if a model is currently loaded.
        
        Args:
            model_id: Model identifier
        
        Returns:
            True if model is loaded in memory
        """
        pass
    
    @abstractmethod
    def get_model_info(self, model_id: str) -> ModelConfig:
        """
        Get model configuration and metadata.
        
        Args:
            model_id: Model identifier
        
        Returns:
            ModelConfig for the model
        
        Raises:
            ModelNotFoundError: If model not available
        """
        pass
    
    def supports_lora(self) -> bool:
        """
        Check if provider supports LoRA adapters.
        
        Returns:
            True if LoRA adapters can be loaded
        """
        return False  # Default: no LoRA support
    
    def load_lora(self, model_id: str, lora_path: str, **kwargs) -> bool:
        """
        Load a LoRA adapter for a model (Phase 5 M4).
        
        Args:
            model_id: Base model identifier
            lora_path: Path to LoRA weights
            **kwargs: Provider-specific LoRA parameters
        
        Returns:
            True if LoRA loaded successfully
        
        Raises:
            NotImplementedError: If provider doesn't support LoRA
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support LoRA adapters")
    
    def unload_lora(self, model_id: str) -> bool:
        """
        Unload LoRA adapter from a model.
        
        Args:
            model_id: Model identifier
        
        Returns:
            True if LoRA unloaded successfully
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support LoRA adapters")
    
    def get_memory_usage(self) -> Dict[str, int]:
        """
        Get current memory usage for loaded models.
        
        Returns:
            Dict mapping model_id to memory usage in MB
        """
        return {}
    
    def health_check(self) -> bool:
        """
        Check if provider is healthy and responding.
        
        Returns:
            True if provider is healthy
        """
        try:
            # Default: check if we can list models
            self.list_models()
            return True
        except Exception:
            return False


class ModelLoadError(Exception):
    """Raised when model cannot be loaded."""
    pass


class ModelNotLoadedError(Exception):
    """Raised when operation requires loaded model."""
    pass


class ModelNotFoundError(Exception):
    """Raised when model not found in provider."""
    pass


class GenerationError(Exception):
    """Raised when text generation fails."""
    pass
