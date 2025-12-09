"""
Model loader for LLM backends (Ollama, llama.cpp)

Phase 3: Concrete implementation with adapter hooks
Phase 4: Add LoRA adapter support
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol
from dataclasses import dataclass
from pathlib import Path
import json
import logging

logger = logging.getLogger('cerebric.model')


@dataclass
class ModelConfig:
    """Configuration for model loading."""
    runtime: str  # "ollama" or "llamacpp"
    model_id: str  # e.g., "llama3.1:8b-instruct"
    quantization: Optional[str] = None  # e.g., "Q4_K_M" for llamacpp
    max_context: int = 8192
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    
    @classmethod
    def from_file(cls, path: Path) -> 'ModelConfig':
        """Load config from YAML or JSON."""
        with open(path) as f:
            data = json.load(f) if path.suffix == '.json' else yaml.safe_load(f)
        return cls(**data)


class ModelBackend(Protocol):
    """Protocol for model backends."""
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        """Generate text from prompt."""
        ...
    
    def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int = 512,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate with tool-calling support."""
        ...


class OllamaBackend:
    """Ollama backend implementation."""
    
    def __init__(self, model_id: str, config: ModelConfig):
        self.model_id = model_id
        self.config = config
        self._client = None
    
    def _ensure_client(self):
        """Lazy-load Ollama client."""
        if self._client is None:
            try:
                import ollama
                self._client = ollama.Client()
                logger.info(f"Ollama client initialized for model: {self.model_id}")
            except ImportError:
                raise RuntimeError(
                    "ollama-python not installed. Install with: pip install ollama"
                )
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        """Generate text from prompt."""
        self._ensure_client()
        
        response = self._client.generate(
            model=self.model_id,
            prompt=prompt,
            options={
                'temperature': temperature,
                'num_predict': max_tokens,
                'stop': stop or [],
                **kwargs
            }
        )
        
        return response['response']
    
    def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int = 512,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate with tool-calling support."""
        self._ensure_client()
        
        # Ollama tool-calling format
        response = self._client.chat(
            model=self.model_id,
            messages=[{'role': 'user', 'content': prompt}],
            tools=tools,
            options={'num_predict': max_tokens, **kwargs}
        )
        
        return {
            'text': response['message'].get('content', ''),
            'tool_calls': response['message'].get('tool_calls', []),
            'finish_reason': 'tool_calls' if response['message'].get('tool_calls') else 'stop'
        }


class LlamaCppBackend:
    """llama.cpp backend implementation (via llama-cpp-python)."""
    
    def __init__(self, model_path: str, config: ModelConfig):
        self.model_path = model_path
        self.config = config
        self._llama = None
    
    def _ensure_llama(self):
        """Lazy-load llama.cpp model."""
        if self._llama is None:
            try:
                from llama_cpp import Llama
                self._llama = Llama(
                    model_path=self.model_path,
                    n_ctx=self.config.max_context,
                    n_threads=4,  # TODO: Make configurable
                    verbose=False
                )
                logger.info(f"llama.cpp model loaded from: {self.model_path}")
            except ImportError:
                raise RuntimeError(
                    "llama-cpp-python not installed. Install with: pip install llama-cpp-python"
                )
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        """Generate text from prompt."""
        self._ensure_llama()
        
        output = self._llama(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            echo=False,
            **kwargs
        )
        
        return output['choices'][0]['text']
    
    def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int = 512,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate with tool-calling support (basic implementation)."""
        self._ensure_llama()
        
        # llama.cpp doesn't have native tool-calling
        # Use structured prompt for tool selection
        tool_prompt = self._build_tool_prompt(prompt, tools)
        
        output = self._llama(
            tool_prompt,
            max_tokens=max_tokens,
            temperature=kwargs.get('temperature', 0.7),
            stop=['</tool_call>'],
            echo=False
        )
        
        text = output['choices'][0]['text']
        tool_calls = self._parse_tool_calls(text)
        
        return {
            'text': text,
            'tool_calls': tool_calls,
            'finish_reason': 'tool_calls' if tool_calls else 'stop'
        }
    
    def _build_tool_prompt(self, prompt: str, tools: List[Dict[str, Any]]) -> str:
        """Build prompt with tool descriptions."""
        tool_desc = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tools
        ])
        return f"{prompt}\n\nAvailable tools:\n{tool_desc}\n\nTool call:"
    
    def _parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from generated text."""
        # Simple JSON extraction (can be improved)
        import re
        tool_pattern = r'\{[^}]*"name":\s*"([^"]+)"[^}]*\}'
        matches = re.findall(tool_pattern, text)
        return [{'name': m} for m in matches] if matches else []


class ModelManager:
    """
    Main model manager for Cerebric.
    
    Phase 3: Supports Ollama and llama.cpp backends
    Phase 4: Add LoRA adapter support via load_adapter()
    """
    
    def __init__(self, config: Optional[ModelConfig] = None):
        """
        Initialize model manager.
        
        Args:
            config: Model configuration. If None, loads from default location.
        """
        if config is None:
            config_path = Path.home() / '.config/cerebric/model.json'
            if config_path.exists():
                config = ModelConfig.from_file(config_path)
            else:
                # Default config
                config = ModelConfig(
                    runtime='ollama',
                    model_id='llama3.1:8b-instruct'
                )
        
        self.config = config
        self.backend: Optional[ModelBackend] = None
        self.lora_adapter: Optional[Any] = None  # Phase 4: LoRA adapter
        
        self._initialize_backend()
    
    def _initialize_backend(self):
        """Initialize the appropriate backend."""
        if self.config.runtime == 'ollama':
            self.backend = OllamaBackend(self.config.model_id, self.config)
        elif self.config.runtime == 'llamacpp':
            # Assume model_id is a file path for llamacpp
            self.backend = LlamaCppBackend(self.config.model_id, self.config)
        else:
            raise ValueError(f"Unknown runtime: {self.config.runtime}")
        
        logger.info(f"Model backend initialized: {self.config.runtime}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        """
        Generate text from prompt.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (overrides config)
            stop: Stop sequences
            **kwargs: Additional backend-specific options
        
        Returns:
            Generated text
        """
        if self.backend is None:
            raise RuntimeError("Model backend not initialized")
        
        temp = temperature if temperature is not None else self.config.temperature
        
        # Phase 4: If LoRA adapter is loaded, use it
        if self.lora_adapter is not None:
            return self._generate_with_adapter(prompt, max_tokens, temp, stop, **kwargs)
        
        return self.backend.generate(prompt, max_tokens, temp, stop, **kwargs)
    
    def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int = 512,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Generate with tool-calling support.
        
        Args:
            prompt: Input prompt
            tools: List of tool schemas
            max_tokens: Maximum tokens to generate
            **kwargs: Additional backend-specific options
        
        Returns:
            Dict with 'text', 'tool_calls', 'finish_reason'
        """
        if self.backend is None:
            raise RuntimeError("Model backend not initialized")
        
        # Phase 4: LoRA adapter with tool-calling
        if self.lora_adapter is not None:
            return self._generate_with_tools_adapter(prompt, tools, max_tokens, **kwargs)
        
        return self.backend.generate_with_tools(prompt, tools, max_tokens, **kwargs)
    
    def load_adapter(self, adapter_path: str) -> None:
        """
        Load LoRA adapter (Phase 4).
        
        Args:
            adapter_path: Path to LoRA adapter (safetensors format)
        """
        # Phase 3: Placeholder (no-op)
        # Phase 4: Implement LoRA loading with peft
        logger.warning("LoRA adapter support not yet implemented (Phase 4)")
        self.lora_adapter = None
    
    def unload_adapter(self) -> None:
        """Unload LoRA adapter (Phase 4)."""
        self.lora_adapter = None
        logger.info("LoRA adapter unloaded (reverted to base model)")
    
    def _generate_with_adapter(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]],
        **kwargs: Any
    ) -> str:
        """Generate with LoRA adapter (Phase 4)."""
        # Phase 4: Implement adapter-based generation
        raise NotImplementedError("LoRA generation not yet implemented (Phase 4)")
    
    def _generate_with_tools_adapter(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        max_tokens: int,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate with tools and LoRA adapter (Phase 4)."""
        # Phase 4: Implement adapter-based tool calling
        raise NotImplementedError("LoRA tool calling not yet implemented (Phase 4)")
    
    def estimate_confidence(self, response: str) -> float:
        """
        Estimate confidence from model response (Phase 3).
        
        This is a placeholder implementation. Real confidence estimation
        requires logprobs or calibrated uncertainty quantification.
        
        Args:
            response: Generated text
        
        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Phase 3: Basic heuristic (presence of uncertainty markers)
        uncertainty_markers = ['maybe', 'possibly', 'might', 'could be', 'uncertain']
        has_uncertainty = any(marker in response.lower() for marker in uncertainty_markers)
        
        # Penalize very short responses (likely incomplete)
        length_factor = min(1.0, len(response) / 50)
        
        base_confidence = 0.6 if has_uncertainty else 0.8
        return base_confidence * length_factor
    
    def get_status(self) -> Dict[str, Any]:
        """Get model status information."""
        return {
            'runtime': self.config.runtime,
            'model_id': self.config.model_id,
            'quantization': self.config.quantization,
            'max_context': self.config.max_context,
            'backend_loaded': self.backend is not None,
            'lora_adapter_loaded': self.lora_adapter is not None
        }
