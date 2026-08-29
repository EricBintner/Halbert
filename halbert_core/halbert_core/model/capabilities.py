# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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

from ..utils.reasoning import is_reasoning_model

logger = logging.getLogger('halbert.model.capabilities')

# Size tag in a model id, e.g. ":7b", "-70b", "_14b", ":8b-instruct"
_SIZE_TAG_RE = re.compile(r"[:\-_](\d+(?:\.\d+)?)b\b", re.IGNORECASE)
# Mixture-of-experts tag, e.g. "8x22b", or an explicit "moe" token
_MOE_TAG_RE = re.compile(r"\b\d+x\d+b\b|\bmoe\b", re.IGNORECASE)
# Vision tag: "vision", "multimodal", or a "vl" token / suffix ("-vl", "2.5vl")
_VISION_TOKEN_RE = re.compile(r"(?:^|[^a-z])(?:vision|multimodal)|(?:^|[^a-z])[a-z0-9]*vl(?:$|[^a-z])")

# Fields of ModelCapabilities that a models.yml ``capabilities:`` override
# may set. Anything else in the override mapping is ignored with a warning.
_OVERRIDABLE_FIELDS = (
    'reasoning', 'vision', 'tool_use', 'context_size', 'streaming',
    'multimodal', 'code_execution', 'embedding', 'code', 'fast', 'high_quality',
)

# Runtime capability labels (Ollama /api/show "capabilities") -> fields
_RUNTIME_LABEL_FIELDS = {
    'vision': ('vision', 'multimodal'),
    'thinking': ('reasoning',),
    'tools': ('tool_use',),
    'embedding': ('embedding',),
}


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
    reasoning: bool = False       # Outputs <think> blocks
    vision: bool = False          # Can process images
    tool_use: bool = False        # Supports function/tool calling
    context_size: int = 4096      # Token context window
    streaming: bool = True        # Supports streaming responses
    multimodal: bool = False      # Can handle multiple modalities
    code_execution: bool = False  # Can execute code (sandboxed)
    embedding: bool = False       # Embedding model (not a chat model)
    code: bool = False            # Tuned for code generation/analysis
    
    # Performance hints
    fast: bool = False            # Optimized for low latency
    high_quality: bool = False    # Optimized for quality over speed
    
    @classmethod
    def detect(
        cls,
        model_id: str,
        provider: str = "ollama",
        overrides: Optional[Dict[str, Any]] = None,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> 'ModelCapabilities':
        """
        Detect capabilities without keying on vendor or model-family names.

        Sources, in increasing precedence (later sources win):

        1. Generic, vendor-neutral tokens in the model id: "vision" / "-vl"
           (vision), "think" / "reason" (reasoning), "embed" (embedding),
           "code" / "coder" (code), size tags such as ":7b" / "8x22b"
           (fast / high_quality hints).
        2. Provider-level facts (e.g. every model behind the Anthropic
           Messages API accepts images and tools; OpenAI-compatible
           endpoints support tools and streaming).
        3. Runtime metadata reported by the provider, e.g. the
           ``capabilities`` list and ``context_length`` from Ollama
           ``/api/show`` (pass as ``runtime={"capabilities": [...],
           "context_length": N}``).
        4. Explicit per-model overrides from models.yml
           (``capabilities: {reasoning: true, context_size: 32768, ...}``).

        Context length comes from ``runtime`` / ``overrides`` when
        available, otherwise the provider default, otherwise the
        dataclass default.

        Args:
            model_id: Model identifier as reported by the provider
            provider: Provider name ("ollama", "anthropic", "openai", ...)
            overrides: Optional models.yml ``capabilities:`` mapping
            runtime: Optional provider-reported metadata

        Returns:
            ModelCapabilities with detected settings
        """
        model_lower = (model_id or "").lower()
        caps = cls()
        
        # === 1. GENERIC TOKENS IN THE MODEL ID ===
        if is_reasoning_model(model_lower):
            caps.reasoning = True
            caps.high_quality = True
            logger.debug(f"Detected reasoning model from id: {model_id}")
        
        if _VISION_TOKEN_RE.search(model_lower):
            caps.vision = True
            caps.multimodal = True
        
        if 'embed' in model_lower:
            caps.embedding = True
        
        if 'code' in model_lower:  # also matches "coder"
            caps.code = True
        
        # Size-based hints (parameter count, not name)
        size_match = _SIZE_TAG_RE.search(model_lower)
        if _MOE_TAG_RE.search(model_lower):
            caps.high_quality = True
        elif size_match:
            size = float(size_match.group(1))
            if size <= 9:
                caps.fast = True
            elif size >= 30:
                caps.high_quality = True
        
        # === 2. PROVIDER-LEVEL FACTS ===
        if provider == "anthropic":
            caps.tool_use = True
            caps.streaming = True
            caps.vision = True
            caps.multimodal = True
            caps.context_size = 200000
        elif provider in ("openai", "openrouter"):
            caps.tool_use = True
            caps.streaming = True
        elif provider == "ollama":
            caps.streaming = True
            caps.tool_use = True  # Most current local models support tools
        elif provider == "apple-foundation":
            # Apple Intelligence (FoundationModels) on the ANE: supports
            # tool calling and streaming via the OpenAI-compatible bridge.
            # Vision is not yet confirmed for the on-device foundation
            # model; left False until the bridge reports it.
            caps.streaming = True
            caps.tool_use = True
        
        # === 3. RUNTIME METADATA FROM THE PROVIDER ===
        if runtime:
            for label in runtime.get('capabilities') or []:
                for field_name in _RUNTIME_LABEL_FIELDS.get(str(label).lower(), ()):
                    setattr(caps, field_name, True)
            ctx = runtime.get('context_length') or runtime.get('context_size')
            if isinstance(ctx, (int, float)) and ctx > 0:
                caps.context_size = int(ctx)
        
        # === 4. EXPLICIT PER-MODEL OVERRIDES (models.yml) ===
        if overrides:
            caps.apply_overrides(overrides)
        
        return caps
    
    def apply_overrides(self, overrides: Dict[str, Any]) -> 'ModelCapabilities':
        """Apply a models.yml ``capabilities:`` mapping on top of detected values."""
        for key, value in overrides.items():
            if key == 'context_length':  # accept the runtime spelling too
                key = 'context_size'
            if key not in _OVERRIDABLE_FIELDS:
                logger.warning(f"Ignoring unknown capability override: {key}")
                continue
            if key == 'context_size':
                try:
                    setattr(self, key, int(value))
                except (TypeError, ValueError):
                    logger.warning(f"Ignoring non-numeric context_size override: {value!r}")
            else:
                setattr(self, key, bool(value))
        return self
    
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
            'embedding': self.embedding,
            'code': self.code,
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
            embedding=data.get('embedding', False),
            code=data.get('code', False),
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
        """
        Create from config dictionary.

        Capabilities are detected from provider facts and generic tokens in
        the model id, then any explicit ``capabilities:`` mapping (and a
        top-level ``context_length:``) in the config overrides them.
        """
        overrides: Dict[str, Any] = dict(config.get('capabilities') or {})
        if config.get('context_length') and 'context_size' not in overrides:
            overrides['context_size'] = config['context_length']
        caps = ModelCapabilities.detect(
            config.get('model_id', name),
            config.get('provider', 'ollama'),
            overrides=overrides or None,
        )
        
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
