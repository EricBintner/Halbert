"""
Phase 38: Model Capabilities Detection

Automatic detection and management of model capabilities including
reasoning, vision, tool use, and context sizes.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum

logger = logging.getLogger('halbert.model.capabilities')


class ModelTier(str, Enum):
    """Model tiers for routing decisions."""
    GUIDE = "guide"           # Fast, simple tasks
    SPECIALIST = "specialist" # Complex reasoning, analysis
    VISION = "vision"         # Image/visual tasks


@dataclass
class ModelCapabilities:
    """
    Capabilities of a specific model.
    
    Used for routing decisions and feature availability.
    """
    reasoning: bool = False       # Outputs <think> blocks (QwQ, DeepSeek-R1, o1)
    vision: bool = False          # Can process images
    tool_use: bool = False        # Supports function/tool calling
    context_size: int = 4096      # Token context window
    streaming: bool = True        # Supports streaming responses
    multimodal: bool = False      # Can handle multiple modalities
    code_execution: bool = False  # Can execute code (sandboxed)
    
    # Performance hints
    fast: bool = False            # Optimized for low latency
    high_quality: bool = False    # Optimized for quality over speed
    
    @classmethod
    def detect(cls, model_id: str, provider: str = "ollama") -> 'ModelCapabilities':
        """
        Auto-detect capabilities from model name and provider.
        
        Args:
            model_id: Model identifier (e.g., "llama3.1:8b", "claude-3-5-sonnet")
            provider: Provider name ("ollama", "anthropic", "openai")
            
        Returns:
            ModelCapabilities with detected settings
        """
        model_lower = model_id.lower()
        caps = cls()
        
        # === REASONING MODELS ===
        reasoning_patterns = [
            'qwq',              # QwQ reasoning model
            'deepseek-r1',      # DeepSeek R1
            'deepseek-reasoner',
            'o1-',              # OpenAI o1 series
            'o3-',              # OpenAI o3 series
        ]
        if any(p in model_lower for p in reasoning_patterns):
            caps.reasoning = True
            caps.high_quality = True
            logger.debug(f"Detected reasoning model: {model_id}")
        
        # === VISION MODELS ===
        vision_patterns = [
            'llava',            # LLaVA family
            'bakllava',
            'cogvlm',
            'qwen-vl',
            'qwen2-vl',
            'minicpm-v',
            'moondream',
            'llama-vision',
            'pixtral',
        ]
        if any(p in model_lower for p in vision_patterns):
            caps.vision = True
            caps.multimodal = True
        
        # === PROVIDER-SPECIFIC CAPABILITIES ===
        if provider == "anthropic":
            caps.tool_use = True
            caps.streaming = True
            
            if 'claude-3' in model_lower:
                caps.vision = True
                caps.multimodal = True
                caps.context_size = 200000
                
            if 'haiku' in model_lower:
                caps.fast = True
                caps.context_size = 200000
            elif 'sonnet' in model_lower:
                caps.high_quality = True
                caps.context_size = 200000
            elif 'opus' in model_lower:
                caps.high_quality = True
                caps.context_size = 200000
                
        elif provider == "openai":
            caps.tool_use = True
            caps.streaming = True
            
            if 'gpt-4' in model_lower:
                caps.high_quality = True
                if 'vision' in model_lower or 'gpt-4o' in model_lower:
                    caps.vision = True
                    caps.multimodal = True
                if 'turbo' in model_lower:
                    caps.context_size = 128000
                else:
                    caps.context_size = 8192
                    
            if 'gpt-3.5' in model_lower:
                caps.fast = True
                caps.context_size = 16385
                
            if 'o1' in model_lower or 'o3' in model_lower:
                caps.reasoning = True
                caps.high_quality = True
                
        elif provider == "ollama":
            caps.streaming = True
            caps.tool_use = True  # Most modern Ollama models support tools
            
            # Context sizes for common models
            if 'llama3' in model_lower:
                caps.context_size = 128000
            elif 'mistral' in model_lower:
                caps.context_size = 32768
            elif 'qwen' in model_lower:
                caps.context_size = 32768
            elif 'phi' in model_lower:
                caps.context_size = 16384
            elif 'gemma' in model_lower:
                caps.context_size = 8192
            elif 'llava' in model_lower:
                caps.context_size = 4096
                
            # Size-based hints
            if ':7b' in model_lower or ':8b' in model_lower:
                caps.fast = True
            elif ':70b' in model_lower or ':72b' in model_lower:
                caps.high_quality = True
            elif ':32b' in model_lower or ':34b' in model_lower:
                caps.high_quality = True
        
        return caps
    
    def can_handle_task(self, task_type: str) -> bool:
        """Check if model can handle a specific task type."""
        task_requirements = {
            'vision': self.vision,
            'image_analysis': self.vision,
            'reasoning': True,  # Any model can attempt reasoning
            'complex_reasoning': self.reasoning or self.high_quality,
            'code_generation': True,
            'tool_use': self.tool_use,
            'simple_chat': True,
            'long_context': self.context_size >= 32000,
        }
        return task_requirements.get(task_type, True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'reasoning': self.reasoning,
            'vision': self.vision,
            'tool_use': self.tool_use,
            'context_size': self.context_size,
            'streaming': self.streaming,
            'multimodal': self.multimodal,
            'fast': self.fast,
            'high_quality': self.high_quality,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelCapabilities':
        """Create from dictionary."""
        return cls(
            reasoning=data.get('reasoning', False),
            vision=data.get('vision', False),
            tool_use=data.get('tool_use', False),
            context_size=data.get('context_size', 4096),
            streaming=data.get('streaming', True),
            multimodal=data.get('multimodal', False),
            fast=data.get('fast', False),
            high_quality=data.get('high_quality', False),
        )


@dataclass
class ModelDefinition:
    """
    Complete definition of a model including provider and capabilities.
    """
    name: str                           # Friendly name for UI
    model_id: str                       # Provider-specific model ID
    provider: str                       # Provider name
    endpoint: Optional[str] = None      # For Ollama: endpoint URL
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    enabled: bool = True
    
    # Runtime state
    loaded: bool = False
    last_used: Optional[float] = None
    error_count: int = 0
    
    @classmethod
    def from_config(cls, name: str, config: Dict[str, Any]) -> 'ModelDefinition':
        """Create from config dictionary."""
        caps_dict = config.get('capabilities', {})
        caps = ModelCapabilities.from_dict(caps_dict) if caps_dict else \
               ModelCapabilities.detect(config.get('model_id', name), config.get('provider', 'ollama'))
        
        return cls(
            name=name,
            model_id=config.get('model_id', name),
            provider=config.get('provider', 'ollama'),
            endpoint=config.get('endpoint'),
            capabilities=caps,
            enabled=config.get('enabled', True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'model_id': self.model_id,
            'provider': self.provider,
            'endpoint': self.endpoint,
            'capabilities': self.capabilities.to_dict(),
            'enabled': self.enabled,
        }


@dataclass
class TierConfig:
    """
    Configuration for a model tier (guide, specialist, vision).
    """
    primary: str                        # Primary model name
    fallback: List[str] = field(default_factory=list)  # Fallback model names
    prefer_reasoning: Optional[str] = None  # Prefer this for reasoning tasks
    enabled: bool = True
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'TierConfig':
        """Create from config dictionary."""
        if isinstance(config, str):
            # Simple format: just model name
            return cls(primary=config)
        
        return cls(
            primary=config.get('primary', ''),
            fallback=config.get('fallback', []),
            prefer_reasoning=config.get('prefer_reasoning'),
            enabled=config.get('enabled', True),
        )


# === KNOWN MODEL CAPABILITIES DATABASE ===
# Pre-defined capabilities for common models to avoid detection overhead

KNOWN_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    # Reasoning models
    'qwq:32b': {'reasoning': True, 'context_size': 32768, 'high_quality': True},
    'qwq:latest': {'reasoning': True, 'context_size': 32768, 'high_quality': True},
    'deepseek-r1:7b': {'reasoning': True, 'context_size': 64000},
    'deepseek-r1:70b': {'reasoning': True, 'context_size': 64000, 'high_quality': True},
    
    # Vision models
    'llava:7b': {'vision': True, 'multimodal': True, 'context_size': 4096},
    'llava:13b': {'vision': True, 'multimodal': True, 'context_size': 4096},
    'llava:34b': {'vision': True, 'multimodal': True, 'context_size': 4096, 'high_quality': True},
    'bakllava:latest': {'vision': True, 'multimodal': True, 'context_size': 4096},
    
    # Llama family (NOT reasoning models - no <think> blocks)
    'llama3.1:8b': {'context_size': 128000, 'fast': True, 'tool_use': True},
    'llama3.1:70b': {'context_size': 128000, 'high_quality': True, 'tool_use': True},
    'llama3.2:1b': {'context_size': 128000, 'fast': True},
    'llama3.2:3b': {'context_size': 128000, 'fast': True},
    # llama3.3:70b is high-quality but NOT a reasoning model (no <think> output)
    'llama3.3:70b': {'context_size': 128000, 'high_quality': True, 'tool_use': True},
    
    # Qwen family
    'qwen2.5:7b': {'context_size': 32768, 'tool_use': True},
    'qwen2.5:14b': {'context_size': 32768, 'tool_use': True},
    'qwen2.5:32b': {'context_size': 32768, 'high_quality': True, 'tool_use': True},
    'qwen2.5:72b': {'context_size': 32768, 'high_quality': True, 'tool_use': True},
    
    # Claude models
    'claude-3-haiku-20240307': {'vision': True, 'multimodal': True, 'context_size': 200000, 'fast': True, 'tool_use': True},
    'claude-3-sonnet-20240229': {'vision': True, 'multimodal': True, 'context_size': 200000, 'high_quality': True, 'tool_use': True},
    'claude-3-opus-20240229': {'vision': True, 'multimodal': True, 'context_size': 200000, 'high_quality': True, 'tool_use': True},
    'claude-3-5-sonnet-20241022': {'vision': True, 'multimodal': True, 'context_size': 200000, 'high_quality': True, 'tool_use': True},
    
    # GPT models
    'gpt-4-turbo': {'vision': True, 'multimodal': True, 'context_size': 128000, 'high_quality': True, 'tool_use': True},
    'gpt-4o': {'vision': True, 'multimodal': True, 'context_size': 128000, 'high_quality': True, 'tool_use': True},
    'gpt-4o-mini': {'vision': True, 'multimodal': True, 'context_size': 128000, 'fast': True, 'tool_use': True},
    'gpt-3.5-turbo': {'context_size': 16385, 'fast': True, 'tool_use': True},
}


def get_known_capabilities(model_id: str) -> Optional[ModelCapabilities]:
    """
    Get pre-defined capabilities for known models.
    
    Args:
        model_id: Model identifier
        
    Returns:
        ModelCapabilities if known, None otherwise
    """
    if model_id in KNOWN_CAPABILITIES:
        caps_dict = KNOWN_CAPABILITIES[model_id]
        return ModelCapabilities.from_dict(caps_dict)
    
    # Try partial match (e.g., "llama3.1:8b-instruct" matches "llama3.1:8b")
    for known_id, caps_dict in KNOWN_CAPABILITIES.items():
        if model_id.startswith(known_id.split(':')[0]) and \
           known_id.split(':')[1] in model_id if ':' in known_id else True:
            return ModelCapabilities.from_dict(caps_dict)
    
    return None
