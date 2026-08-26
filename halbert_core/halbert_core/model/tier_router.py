"""
Phase 38: Tier-Based Model Router with Intelligent Fallbacks

A flexible, self-optimizing model management system that supports:
- Multiple providers (Ollama local, Anthropic API, OpenAI API)
- Model tiers (Guide, Specialist, Vision)
- Capability-based routing (reasoning, vision, tool use)
- Intelligent fallback chains
- Automatic reasoning model preference
"""

from __future__ import annotations
import os
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from pathlib import Path
import yaml

from .capabilities import (
    ModelCapabilities, ModelDefinition, TierConfig, ModelTier,
    get_known_capabilities, KNOWN_CAPABILITIES
)
from .providers import ModelProvider, ModelResponse, OllamaProvider
from .providers.base import GenerationError, ModelNotFoundError
from .rate_limiter import RateLimiter
from .outcome_store import OutcomeStore
from .cascade_router import MetaHarnessRouter
from ..agents.error_recovery import get_recovery_manager

logger = logging.getLogger('halbert.model.tier_router')


class ProviderType(str, Enum):
    """Supported provider types."""
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


@dataclass
class ModelSelection:
    """Result of model selection process."""
    model: ModelDefinition
    reason: str
    fallback_used: bool = False
    fallback_from: Optional[str] = None
    capabilities: Optional[ModelCapabilities] = None


@dataclass
class TierRouterConfig:
    """Configuration for the tier router."""
    # Provider configurations
    providers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Model definitions
    models: Dict[str, ModelDefinition] = field(default_factory=dict)
    
    # Tier assignments
    guide: TierConfig = field(default_factory=lambda: TierConfig(primary=""))
    specialist: TierConfig = field(default_factory=lambda: TierConfig(primary=""))
    vision: TierConfig = field(default_factory=lambda: TierConfig(primary=""))
    
    # Routing settings
    complexity_threshold: float = 0.5
    prefer_reasoning: bool = True
    force_specialist_tasks: List[str] = field(default_factory=lambda: [
        "code_generation", "debugging", "system_analysis"
    ])
    
    @classmethod
    def from_yaml(cls, config_dict: Dict[str, Any]) -> 'TierRouterConfig':
        """Create config from YAML dictionary."""
        cfg = cls()
        
        # Parse providers
        cfg.providers = config_dict.get('providers', {})
        
        # Parse models
        models_dict = config_dict.get('models', {})
        for name, model_cfg in models_dict.items():
            cfg.models[name] = ModelDefinition.from_config(name, model_cfg)
        
        # Parse tiers
        tiers = config_dict.get('tiers', {})
        if 'guide' in tiers:
            cfg.guide = TierConfig.from_config(tiers['guide'])
        if 'specialist' in tiers:
            cfg.specialist = TierConfig.from_config(tiers['specialist'])
        if 'vision' in tiers:
            cfg.vision = TierConfig.from_config(tiers['vision'])
        
        # Routing settings
        routing = config_dict.get('routing', {})
        cfg.complexity_threshold = routing.get('complexity_threshold', 0.5)
        cfg.prefer_reasoning = routing.get('prefer_reasoning', True)
        cfg.force_specialist_tasks = routing.get('force_specialist', cfg.force_specialist_tasks)
        
        return cfg
    
    @classmethod
    def from_legacy_config(cls, legacy: Dict[str, Any]) -> 'TierRouterConfig':
        """
        Convert legacy models.yml format to new TierRouterConfig.
        
        Supports backwards compatibility with existing configs.
        """
        cfg = cls()
        
        # Extract orchestrator as guide
        orch = legacy.get('orchestrator', {})
        if orch.get('model'):
            model_id = orch['model']
            endpoint = orch.get('endpoint', 'http://localhost:11434')
            provider = orch.get('provider', 'ollama')
            
            # Create model definition
            caps = ModelCapabilities.detect(model_id, provider)
            cfg.models['guide-model'] = ModelDefinition(
                name='guide-model',
                model_id=model_id,
                provider=provider,
                endpoint=endpoint,
                capabilities=caps,
            )
            cfg.guide = TierConfig(primary='guide-model')
            
            # Register provider
            cfg.providers[f'{provider}-guide'] = {
                'type': provider,
                'endpoint': endpoint,
            }
        
        # Extract specialist
        spec = legacy.get('specialist', {})
        if spec.get('enabled') and spec.get('model'):
            model_id = spec['model']
            endpoint = spec.get('endpoint', 'http://localhost:11434')
            provider = spec.get('provider', 'ollama')
            
            caps = ModelCapabilities.detect(model_id, provider)
            cfg.models['specialist-model'] = ModelDefinition(
                name='specialist-model',
                model_id=model_id,
                provider=provider,
                endpoint=endpoint,
                capabilities=caps,
            )
            cfg.specialist = TierConfig(
                primary='specialist-model',
                fallback=['guide-model'],
            )
            
            cfg.providers[f'{provider}-specialist'] = {
                'type': provider,
                'endpoint': endpoint,
            }
        
        # Extract vision model
        vision = legacy.get('vision', {})
        if vision.get('model'):
            model_id = vision['model']
            endpoint = vision.get('endpoint', 'http://localhost:11434')
            provider = vision.get('provider', 'ollama')
            
            caps = ModelCapabilities.detect(model_id, provider)
            caps.vision = True  # Force vision capability
            cfg.models['vision-model'] = ModelDefinition(
                name='vision-model',
                model_id=model_id,
                provider=provider,
                endpoint=endpoint,
                capabilities=caps,
            )
            cfg.vision = TierConfig(
                primary='vision-model',
                fallback=['specialist-model'] if cfg.specialist.primary else [],
            )
        
        # Routing settings
        routing = legacy.get('routing', {})
        cfg.complexity_threshold = routing.get('complexity_threshold', 0.5)
        cfg.force_specialist_tasks = routing.get('prefer_specialist_for', cfg.force_specialist_tasks)
        
        return cfg


class TierRouter:
    """
    Intelligent model router with tier-based fallbacks.
    
    Features:
    - Multi-provider support (Ollama, Anthropic, OpenAI)
    - Three tiers: Guide (fast), Specialist (quality), Vision (multimodal)
    - Automatic reasoning model preference
    - Graceful fallback chains
    - Capability-based routing
    
    Example configurations:
    
    1. Full Local:
       guide: llama3.1:8b (localhost)
       specialist: llama3.3:70b (GPU server)
       vision: llava:34b (GPU server)
    
    2. Hybrid Local + API:
       guide: llama3.1:8b (localhost)
       specialist: claude-3.5-sonnet (Anthropic API)
       vision: claude-3.5-sonnet (Anthropic API)
    
    3. Cloud Only:
       guide: claude-3-haiku (fast, cheap)
       specialist: claude-3.5-sonnet (quality)
       vision: claude-3.5-sonnet (multimodal)
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize tier router.
        
        Args:
            config_path: Path to models.yml (auto-detected if None)
        """
        self.config_path = self._find_config(config_path)
        self.raw_config = self._load_raw_config()
        self.config = self._parse_config(self.raw_config)
        
        # Provider instances (created on demand)
        self._providers: Dict[str, ModelProvider] = {}
        
        # Track model health/availability
        self._model_health: Dict[str, bool] = {}
        self._last_health_check: Dict[str, float] = {}

        # HTTP rate-limit handler (A2b): 429/529 with Retry-After
        self.rate_limiter = RateLimiter()

        # Outcome store for self-tuning router (A3): records per-call results
        # so MetaHarnessRouter (C2a) can blend evidence with priors.
        self.outcome_store = OutcomeStore()

        # Cost-cascade router with outcome-based self-tuning (C2a/C2b). Opt-in;
        # when disabled, route_request uses the heuristic path below.
        self.cascade_router = MetaHarnessRouter(self, self.outcome_store)

        logger.info(f"TierRouter initialized with {len(self.config.models)} models")
    
    def _find_config(self, config_path: Optional[Path]) -> Path:
        """Find configuration file."""
        if config_path and config_path.exists():
            return config_path
        
        from .config_locator import find_models_config, user_models_config
        found = find_models_config()
        if found is not None:
            logger.info(f"TierRouter config: {found}")
            return found
        logger.warning("No models.yml found; TierRouter will have no models")
        return user_models_config()  # default (non-existent) location
    
    def _load_raw_config(self) -> Dict[str, Any]:
        """Load raw YAML configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {}
    
    def _parse_config(self, raw: Dict[str, Any]) -> TierRouterConfig:
        """Parse configuration, handling both new and legacy formats."""
        # Check for new schema version
        if raw.get('version', 1) >= 2:
            return TierRouterConfig.from_yaml(raw)
        else:
            # Legacy format
            logger.debug("Converting legacy config format")
            return TierRouterConfig.from_legacy_config(raw)
    
    def _get_provider(self, model: ModelDefinition) -> ModelProvider:
        """Get or create provider for a model."""
        provider_key = f"{model.provider}:{model.endpoint or 'default'}"
        
        if provider_key not in self._providers:
            if model.provider == ProviderType.OLLAMA or model.provider == "ollama":
                endpoint = model.endpoint or "http://localhost:11434"
                self._providers[provider_key] = OllamaProvider(base_url=endpoint)
                
            elif model.provider == ProviderType.ANTHROPIC or model.provider == "anthropic":
                try:
                    from .providers.anthropic import AnthropicProvider
                    self._providers[provider_key] = AnthropicProvider()
                except ImportError as e:
                    logger.error(f"Anthropic provider not available: {e}")
                    raise
                    
            elif model.provider == ProviderType.OPENAI or model.provider == "openai":
                # TODO: Implement OpenAI provider
                raise NotImplementedError("OpenAI provider not yet implemented")
            else:
                raise ValueError(f"Unknown provider: {model.provider}")
        
        return self._providers[provider_key]
    
    def _check_model_health(self, model: ModelDefinition, force: bool = False) -> bool:
        """Check if a model is available and healthy."""
        cache_key = f"{model.provider}:{model.model_id}"
        now = time.time()
        
        # Use cached result if recent (5 minutes)
        if not force and cache_key in self._model_health:
            if now - self._last_health_check.get(cache_key, 0) < 300:
                return self._model_health[cache_key]
        
        try:
            provider = self._get_provider(model)
            healthy = provider.health_check()
            self._model_health[cache_key] = healthy
            self._last_health_check[cache_key] = now
            return healthy
        except Exception as e:
            logger.warning(f"Health check failed for {model.model_id}: {e}")
            self._model_health[cache_key] = False
            self._last_health_check[cache_key] = now
            return False
    
    def select_model(
        self,
        tier: ModelTier,
        require_vision: bool = False,
        require_reasoning: bool = False,
        complexity_score: float = 0.0,
    ) -> ModelSelection:
        """
        Select the best model for a request.
        
        Args:
            tier: Target tier (guide, specialist, vision)
            require_vision: Must have vision capability
            require_reasoning: Prefer reasoning model
            complexity_score: Query complexity (0.0-1.0)
            
        Returns:
            ModelSelection with chosen model and reasoning
        """
        # Get tier config
        if tier == ModelTier.GUIDE:
            tier_cfg = self.config.guide
        elif tier == ModelTier.SPECIALIST:
            tier_cfg = self.config.specialist
        elif tier == ModelTier.VISION:
            tier_cfg = self.config.vision
        else:
            tier_cfg = self.config.guide
        
        # Vision requests always go to vision tier
        if require_vision:
            tier_cfg = self.config.vision
            tier = ModelTier.VISION
        
        # Build candidate list
        candidates = []
        
        # Primary model
        if tier_cfg.primary and tier_cfg.primary in self.config.models:
            candidates.append(tier_cfg.primary)
        
        # Reasoning preference (Phase 38: prefer reasoning for complex tasks)
        if (require_reasoning or complexity_score >= 0.7) and tier_cfg.prefer_reasoning:
            if tier_cfg.prefer_reasoning in self.config.models:
                # Insert reasoning model at front
                candidates.insert(0, tier_cfg.prefer_reasoning)
        
        # Fallbacks
        candidates.extend(tier_cfg.fallback)
        
        # Try each candidate
        for model_name in candidates:
            if model_name not in self.config.models:
                continue
            
            model = self.config.models[model_name]
            
            # Check capability requirements
            if require_vision and not model.capabilities.vision:
                logger.debug(f"Skipping {model_name}: no vision capability")
                continue
            
            # Check health
            if not self._check_model_health(model):
                logger.debug(f"Skipping {model_name}: unhealthy")
                continue
            
            # Found a working model
            is_primary = (model_name == tier_cfg.primary)
            return ModelSelection(
                model=model,
                reason=f"Selected {model_name} for {tier.value}" + 
                       (" (reasoning preferred)" if model.capabilities.reasoning else ""),
                fallback_used=not is_primary,
                fallback_from=tier_cfg.primary if not is_primary else None,
                capabilities=model.capabilities,
            )
        
        # No model available - try cross-tier fallback
        logger.warning(f"No {tier.value} model available, trying cross-tier fallback")
        
        # Try specialist -> guide fallback
        if tier == ModelTier.SPECIALIST and self.config.guide.primary:
            guide_model = self.config.models.get(self.config.guide.primary)
            if guide_model and self._check_model_health(guide_model):
                return ModelSelection(
                    model=guide_model,
                    reason=f"Fallback to guide (specialist unavailable)",
                    fallback_used=True,
                    fallback_from=tier_cfg.primary,
                    capabilities=guide_model.capabilities,
                )
        
        raise ModelNotFoundError(f"No model available for tier: {tier.value}")
    
    def route_request(
        self,
        query: str,
        has_images: bool = False,
        prefer_specialist: bool = False,
        task_type: Optional[str] = None,
    ) -> ModelSelection:
        """
        Route a request to the appropriate model.
        
        Args:
            query: User query
            has_images: Whether request includes images
            prefer_specialist: Force specialist tier
            task_type: Optional task type hint
            
        Returns:
            ModelSelection with routing decision
        """
        # Vision requests
        if has_images:
            return self.select_model(
                tier=ModelTier.VISION,
                require_vision=True,
            )

        # Explicit overrides still apply even when cascade routing is enabled.
        # The disabled path must stay byte-identical to the pre-C2b heuristic,
        # so it uses the original _score_complexity scorer, not the shared
        # cascade estimator (which scores differently by design).
        if prefer_specialist or (task_type and task_type in self.config.force_specialist_tasks):
            if self.cascade_router.is_enabled():
                complexity = self.cascade_router.estimate_complexity(query)
            else:
                complexity = self._score_complexity(query)
            return self.select_model(
                tier=ModelTier.SPECIALIST,
                require_reasoning=self._should_use_reasoning(query, complexity),
                complexity_score=complexity,
            )

        # Cost-cascade router (C2b): when enabled, delegate model selection to
        # MetaHarnessRouter, which blends tier priors with recorded outcomes.
        # When disabled (default), behavior is byte-identical to the old
        # heuristic path below (restored original scorer).
        if self.cascade_router.is_enabled():
            model = self.cascade_router.route(query)
            if model is not None:
                return ModelSelection(
                    model=model,
                    reason="cascade_router",
                    fallback_used=False,
                    capabilities=model.capabilities,
                )

        complexity = self._score_complexity(query)
        # Determine tier
        if complexity >= self.config.complexity_threshold:
            tier = ModelTier.SPECIALIST
        else:
            tier = ModelTier.GUIDE

        # Check if reasoning would be beneficial
        require_reasoning = self._should_use_reasoning(query, complexity)

        return self.select_model(
            tier=tier,
            require_reasoning=require_reasoning,
            complexity_score=complexity,
        )

    def _score_complexity(self, query: str) -> float:
        """Score query complexity (0.0 to 1.0).

        Original heuristic path scorer — kept because the cascade-disabled
        (default) routing path must stay byte-identical to pre-C2b behavior.
        MetaHarnessRouter has its own estimate_complexity() for the enabled path.
        """
        score = 0.0
        query_lower = query.lower()
        words = query.split()

        # Length
        if len(words) > 50:
            score += 0.2
        elif len(words) > 20:
            score += 0.1

        # Code indicators
        if any(kw in query_lower for kw in [
            'write', 'create', 'script', 'code', 'implement',
            'debug', 'fix', 'error', 'optimize'
        ]):
            score += 0.3

        # Multi-step indicators
        if any(kw in query_lower for kw in [
            'step by step', 'first', 'then', 'compare', 'analyze'
        ]):
            score += 0.2

        # Complex sysadmin
        if any(kw in query_lower for kw in [
            'troubleshoot', 'diagnose', 'investigate', 'security',
            'performance', 'configure', 'architecture'
        ]):
            score += 0.2

        # Simple query reduction
        if any(kw in query_lower for kw in [
            'what is', 'show me', 'list', 'status'
        ]) and len(words) < 15:
            score -= 0.2

        return max(0.0, min(1.0, score))

    def _should_use_reasoning(self, query: str, complexity: float) -> bool:
        """Determine if reasoning model would be beneficial."""
        if not self.config.prefer_reasoning:
            return False
        
        # High complexity always benefits from reasoning
        if complexity >= 0.7:
            return True
        
        # Reasoning keywords
        reasoning_indicators = [
            'why', 'explain', 'reason', 'think', 'analyze',
            'compare', 'evaluate', 'decide', 'recommend',
            'best approach', 'trade-off', 'pros and cons'
        ]
        
        query_lower = query.lower()
        return any(kw in query_lower for kw in reasoning_indicators)
    
    def generate(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        prefer_specialist: bool = False,
        task_type: Optional[str] = None,
        **kwargs
    ) -> Tuple[ModelResponse, ModelSelection]:
        """
        Generate response using intelligent routing.
        
        Args:
            prompt: User prompt
            images: Optional base64 images for vision
            prefer_specialist: Force specialist tier
            task_type: Task type hint
            **kwargs: Generation parameters
            
        Returns:
            Tuple of (ModelResponse, ModelSelection)
        """
        # Route request
        selection = self.route_request(
            query=prompt,
            has_images=bool(images),
            prefer_specialist=prefer_specialist,
            task_type=task_type,
        )
        
        logger.info(f"Routed to {selection.model.model_id}: {selection.reason}")
        
        # Get provider
        provider = self._get_provider(selection.model)

        # Rate-limit retry loop (A2b): HTTP 429/529 with Retry-After.
        # General retry/backoff for non-HTTP errors is handled by
        # ErrorRecoveryManager.execute_with_retry() in the agent loop; HTTP-
        # specific Retry-After parsing lives in RateLimiter. Each rate-limit
        # failure is recorded to the recovery manager's circuit breaker so a
        # persistently rate-limited model is eventually taken out of rotation.
        rate_attempt = 0
        while True:
            try:
                # Handle vision requests
                if images and hasattr(provider, 'chat'):
                    response = provider.chat(
                        messages=[{"role": "user", "content": prompt}],
                        model_id=selection.model.model_id,
                        images=images,
                        **kwargs
                    )
                else:
                    response = provider.generate(
                        prompt=prompt,
                        model_id=selection.model.model_id,
                        **kwargs
                    )

                # Success: clear any rate-limit state for this model
                self.rate_limiter.reset(selection.model.model_id)
                # Record outcome for the self-tuning router (A3)
                self._record_outcome(selection.model.model_id, response, success=True)
                return response, selection

            except GenerationError as e:
                model_id = selection.model.model_id

                # Rate-limited (429/529) and retries remain -> wait + retry
                if (
                    e.is_rate_limited
                    and self.rate_limiter.should_retry(
                        e.status_code, e.headers, rate_attempt, model_id
                    )
                ):
                    wait = self.rate_limiter.get_wait_time(
                        e.status_code, e.headers, rate_attempt, model_id
                    )
                    logger.warning(
                        f"Rate limited ({e.status_code}) on {model_id}, "
                        f"retry {rate_attempt + 1}/{self.rate_limiter._max_retries} "
                        f"in {wait:.1f}s"
                    )
                    self.rate_limiter.record_retry(model_id, e.status_code, e.headers)
                    # Share state with the circuit breaker
                    get_recovery_manager().record_failure(model_id)
                    time.sleep(wait)
                    rate_attempt += 1
                    continue

                # Non-rate-limit error, or rate-limit retries exhausted: fallback
                logger.error(f"Generation failed with {model_id}: {e}")
                # Record the failure (best-effort) for the self-tuning router (A3)
                self._record_outcome(model_id, None, success=False)

                # Try fallback
                if not selection.fallback_used:
                    logger.info("Attempting fallback...")
                    # Mark current model as unhealthy
                    cache_key = f"{selection.model.provider}:{model_id}"
                    self._model_health[cache_key] = False

                    # Re-route
                    return self.generate(
                        prompt=prompt,
                        images=images,
                        prefer_specialist=False,  # Downgrade
                        task_type=task_type,
                        **kwargs
                    )

                raise

    def _record_outcome(
        self, model_id: str, response: Optional[ModelResponse], success: bool
    ) -> None:
        """Record a model-call outcome (A3). Best-effort; never raises.

        Tokens/cost feed the MetaHarnessRouter's evidence blending (C2a). The
        store is guarded so a missing/None store (e.g. in tests that bypass
        __init__) silently skips recording.
        """
        store = getattr(self, "outcome_store", None)
        if store is None:
            return
        try:
            meta = getattr(response, "metadata", None) or {}
            in_tok = meta.get("input_tokens", 0) if isinstance(meta, dict) else 0
            out_tok = meta.get("output_tokens", 0) if isinstance(meta, dict) else 0
            store.record(
                model=model_id,
                success=success,
                latency_ms=getattr(response, "latency_ms", 0) or 0,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=0.0,  # price table wired in C2
                complexity=None,
                task=None,
            )
        except Exception as ex:
            logger.debug(f"Outcome recording failed (non-fatal): {ex}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get router status for debugging/UI."""
        status = {
            "config_path": str(self.config_path),
            "models": {},
            "tiers": {
                "guide": self.config.guide.primary,
                "specialist": self.config.specialist.primary,
                "vision": self.config.vision.primary,
            },
            "providers": {},
        }
        
        # Model status
        for name, model in self.config.models.items():
            status["models"][name] = {
                "model_id": model.model_id,
                "provider": model.provider,
                "endpoint": model.endpoint,
                "capabilities": model.capabilities.to_dict(),
                "healthy": self._model_health.get(f"{model.provider}:{model.model_id}", None),
            }
        
        # Provider status
        for key, provider in self._providers.items():
            status["providers"][key] = {
                "healthy": provider.health_check() if provider else False,
            }
        
        return status
