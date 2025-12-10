"""
Model router for multi-model orchestration (Phase 5 M1).

Routes tasks to appropriate models based on:
- Task type (chat, code, reasoning)
- Model availability
- Resource constraints
- User preferences
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from enum import Enum
from pathlib import Path
import logging
import yaml

from .providers import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    OllamaProvider, LlamaCppProvider, MLXProvider
)
from .context_handoff import (
    ContextHandoffEngine, ConversationContext, HandoffStrategy, 
    MessageRole, Message
)
from .performance_monitor import PerformanceMonitor
from ..utils.platform import get_config_dir, get_platform_info
from ..obs.logging import get_logger

logger = get_logger("halbert")


class TaskType(str, Enum):
    """Task types for routing decisions."""
    CHAT = "chat"                    # General conversation
    CODE_GENERATION = "code_generation"  # Generate code
    CODE_ANALYSIS = "code_analysis"   # Analyze/review code
    SYSTEM_COMMAND = "system_command"  # System admin tasks
    REASONING = "reasoning"           # Complex problem-solving
    QUICK_QUERY = "quick_query"       # Fast, simple questions


class RoutingStrategy(str, Enum):
    """Routing strategies."""
    ORCHESTRATOR_ONLY = "orchestrator_only"  # Always use orchestrator
    SPECIALIST_PREFERRED = "specialist_preferred"  # Use specialist if available
    AUTO = "auto"  # Intelligent routing based on task


class ModelRouter:
    """
    Routes tasks to appropriate models.
    
    Architecture:
    - Orchestrator/Guide: Chat model (any model the user chooses)
    - Specialist: On-demand model for complex tasks (any model at any endpoint)
    
    Phase 5 M1: Basic routing logic
    Phase 5 M2: Context handoff between models
    Phase 5 M5: Performance-based routing
    
    Usage:
        router = ModelRouter()
        
        # Simple routing
        response = router.generate(
            prompt="Explain CPU usage",
            task_type=TaskType.CHAT
        )
        
        # Force specialist
        response = router.generate(
            prompt="Write a backup script",
            task_type=TaskType.CODE_GENERATION,
            prefer_specialist=True
        )
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize model router.
        
        Args:
            config_path: Path to models.yml configuration
        """
        if config_path is None:
            # Try multiple locations for config (Phase 12e)
            candidates = [
                get_config_dir() / 'models.yml',  # ~/.config/halbert/models.yml
                Path(__file__).parent.parent.parent.parent.parent / 'config' / 'models.yml',  # LinuxBrain/config/
            ]
            config_path = candidates[0]  # Default
            for candidate in candidates:
                if candidate.exists():
                    config_path = candidate
                    break
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Log platform info for debugging
        platform_info = get_platform_info()
        logger.debug("Platform info", extra=platform_info)
        
        # Initialize providers
        self.providers: Dict[str, ModelProvider] = {}
        self._init_providers()
        
        # Track active models
        self.orchestrator_id: Optional[str] = None
        self.specialist_id: Optional[str] = None
        
        # Initialize context handoff engine (Phase 5 M2)
        handoff_strategy = self.config.get("handoff", {}).get("strategy", "summarized")
        self.handoff_engine = ContextHandoffEngine(
            default_strategy=HandoffStrategy(handoff_strategy)
        )
        
        # Conversation tracking (Phase 5 M2)
        self.conversation_context: Optional[ConversationContext] = None
        
        # Initialize performance monitor (Phase 5 M5)
        self.performance_monitor = PerformanceMonitor()
        
        # Load configured models
        self._load_configured_models()
        
        logger.info("ModelRouter initialized", extra={
            "orchestrator": self.orchestrator_id,
            "specialist": self.specialist_id,
            "providers": list(self.providers.keys())
        })
    
    def _load_config(self) -> Dict[str, Any]:
        """Load router configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"Loaded router config from {self.config_path}")
                return config
            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
        
        # Default configuration
        return {
            "orchestrator": {
                "model": "llama3.1:8b-instruct",
                "provider": "ollama",
                "always_loaded": True
            },
            "specialist": {
                "enabled": False,
                "model": None,
                "provider": "ollama",
                "load_strategy": "on_demand"
            },
            "routing": {
                "strategy": "auto",
                "prefer_specialist_for": ["code_generation", "code_analysis"]
            },
            "handoff": {
                "strategy": "summarized",
                "max_context_tokens": 4096,
                "include_rag": True
            }
        }
    
    def _init_providers(self):
        """
        Initialize model providers.
        
        Phase 14 Update: Providers are now created on-demand with specific endpoints.
        This allows guide and specialist to use different Ollama instances.
        """
        # Register a default local Ollama provider
        try:
            ollama = OllamaProvider(base_url="http://localhost:11434")
            self.providers["ollama"] = ollama
            if ollama.health_check():
                logger.info("Default Ollama provider ready at localhost:11434")
            else:
                logger.warning("Default Ollama not responding at localhost:11434")
        except Exception as e:
            logger.error(f"Failed to initialize default Ollama provider: {e}")
        
        # llama.cpp (optional)
        try:
            llamacpp = LlamaCppProvider()
            self.providers["llamacpp"] = llamacpp
            logger.debug("llama.cpp provider registered (placeholder)")
        except Exception as e:
            logger.debug(f"llama.cpp provider not available: {e}")
        
        # MLX (Mac only)
        try:
            mlx = MLXProvider()
            self.providers["mlx"] = mlx
            logger.debug("MLX provider registered (placeholder, Mac Apple Silicon)")
        except Exception as e:
            logger.debug(f"MLX provider not available: {e}")
    
    def _load_configured_models(self):
        """Load models specified in configuration."""
        # Load orchestrator/guide config
        orch_config = self.config.get("orchestrator", {})
        if orch_config.get("model"):
            self.orchestrator_id = orch_config["model"]
            # Store the full config including endpoint
            self._orchestrator_config = orch_config
            logger.info(f"Orchestrator configured: {self.orchestrator_id} at {orch_config.get('endpoint', 'default')}")
        
        # Load specialist config (if enabled)
        spec_config = self.config.get("specialist", {})
        if spec_config.get("enabled") and spec_config.get("model"):
            self.specialist_id = spec_config["model"]
            # Store the full config including endpoint
            self._specialist_config = spec_config
            logger.info(f"Specialist configured: {self.specialist_id} at {spec_config.get('endpoint', 'default')}")
    
    def generate(
        self,
        prompt: str,
        task_type: TaskType = TaskType.CHAT,
        prefer_specialist: bool = False,
        **kwargs
    ) -> ModelResponse:
        """
        Generate text using appropriate model.
        
        Args:
            prompt: Input prompt
            task_type: Type of task (for routing)
            prefer_specialist: Force specialist if available
            **kwargs: Generation parameters (max_tokens, temperature, etc.)
        
        Returns:
            ModelResponse with generated text
        """
        # Determine which model to use (Phase 12e: includes complexity scoring)
        model_id, provider_name, endpoint_url = self._route_task(task_type, prefer_specialist, prompt)
        
        if not model_id:
            raise ValueError(f"No model available for task: {task_type}")
        
        # Get or create provider for this endpoint
        provider = self._get_provider_for_endpoint(provider_name, endpoint_url)
        
        # Ensure model is loaded
        if not provider.is_loaded(model_id):
            logger.info(f"Loading model on-demand: {model_id}")
            provider.load_model(model_id)
        
        # Generate with performance tracking (Phase 5 M5)
        logger.info(f"Generating with {model_id} ({task_type})")
        import time
        start_time = time.time()
        success = True
        
        try:
            response = provider.generate(prompt, model_id, **kwargs)
        except Exception as e:
            success = False
            logger.error(f"Generation failed: {e}")
            raise
        finally:
            # Record performance metrics
            latency_ms = int((time.time() - start_time) * 1000)
            memory_mb = None
            if hasattr(provider, 'get_memory_usage'):
                mem_info = provider.get_memory_usage()
                memory_mb = mem_info.get('active_mb') or mem_info.get('peak_mb')
            
            self.performance_monitor.record_request(
                model_id=model_id,
                provider=provider_name,
                latency_ms=latency_ms,
                success=success,
                memory_mb=memory_mb
            )
        
        return response
    
    def generate_with_context(
        self,
        prompt: str,
        task_type: TaskType = TaskType.CHAT,
        context: Optional[ConversationContext] = None,
        prefer_specialist: bool = False,
        **kwargs
    ) -> tuple[ModelResponse, ConversationContext]:
        """
        Generate with context handoff support (Phase 5 M2).
        
        This method tracks conversation state and handles context handoff
        when switching between orchestrator and specialist models.
        
        Args:
            prompt: Input prompt
            task_type: Type of task (for routing)
            context: Existing conversation context (or None to start new)
            prefer_specialist: Force specialist if available
            **kwargs: Generation parameters
        
        Returns:
            Tuple of (ModelResponse, updated_context)
        
        Example:
            # First message
            response1, ctx = router.generate_with_context(
                "Hello, I need help",
                task_type=TaskType.CHAT
            )
            
            # Second message (context preserved)
            response2, ctx = router.generate_with_context(
                "Write a backup script",
                task_type=TaskType.CODE_GENERATION,
                context=ctx
            )
        """
        # Initialize or use existing context
        if context is None:
            context = ConversationContext()
            context.system_prompt = "You are Halbert, a Linux system administration assistant."
        
        # Add user message to context
        context.add_message(MessageRole.USER, prompt)
        
        # Determine which model to use (Phase 12e: includes complexity scoring)
        model_id, provider_name, endpoint_url = self._route_task(task_type, prefer_specialist, prompt)
        
        if not model_id:
            raise ValueError(f"No model available for task: {task_type}")
        
        # Get or create provider for this endpoint
        provider = self._get_provider_for_endpoint(provider_name, endpoint_url)
        
        # Prepare context handoff
        handoff_config = self.config.get("handoff", {})
        max_tokens = handoff_config.get("max_context_tokens", 4096)
        
        prepared_context = self.handoff_engine.prepare_handoff(
            context=context,
            target_model=model_id,
            max_tokens=max_tokens,
            strategy=None  # Uses engine's default
        )
        
        # Format for provider
        formatted_context = self.handoff_engine.format_for_ollama(prepared_context)
        
        # Ensure model is loaded
        if not provider.is_loaded(model_id):
            logger.info(f"Loading model on-demand: {model_id}")
            provider.load_model(model_id)
        
        # Generate with context
        logger.info("Generating with context handoff", extra={
            "model": model_id,
            "task_type": task_type.value,
            "context_messages": len(context.messages),
            "prepared_messages": len(prepared_context.messages),
            "quality_loss_est": self.handoff_engine.estimate_quality_loss(context, prepared_context)
        })
        
        # For now, use simple prompt (Phase 5 M2 infrastructure)
        # Phase 5 M3: Full context-aware generation with providers
        response = provider.generate(prompt, model_id, **kwargs)
        
        # Add assistant response to context
        context.add_message(MessageRole.ASSISTANT, response.text)
        
        return response, context
    
    def _score_complexity(self, prompt: str) -> float:
        """
        Score prompt complexity to determine which model to use.
        
        Phase 12e: Simple heuristic-based complexity scoring.
        Future: Could use the router model to classify.
        
        Returns:
            Float from 0.0 (simple) to 1.0 (complex)
        """
        score = 0.0
        prompt_lower = prompt.lower()
        
        # Length indicator (longer = likely more complex)
        word_count = len(prompt.split())
        if word_count > 50:
            score += 0.2
        elif word_count > 20:
            score += 0.1
        
        # Code-related keywords (usually need specialist)
        code_keywords = [
            'write', 'create', 'script', 'function', 'code',
            'implement', 'debug', 'fix', 'error', 'bug',
            'optimize', 'refactor', 'performance'
        ]
        if any(kw in prompt_lower for kw in code_keywords):
            score += 0.3
        
        # Multi-step indicators
        multi_step_keywords = [
            'step by step', 'first', 'then', 'after',
            'multiple', 'several', 'all', 'each',
            'compare', 'analyze', 'explain why'
        ]
        if any(kw in prompt_lower for kw in multi_step_keywords):
            score += 0.2
        
        # System admin complexity indicators
        sysadmin_complex = [
            'troubleshoot', 'diagnose', 'investigate',
            'performance issue', 'memory leak', 'cpu usage',
            'security', 'permissions', 'configure', 'setup'
        ]
        if any(kw in prompt_lower for kw in sysadmin_complex):
            score += 0.2
        
        # Simple query indicators (reduce score)
        simple_indicators = [
            'what is', 'show me', 'list', 'status',
            'how many', 'which', 'where is'
        ]
        if any(kw in prompt_lower for kw in simple_indicators) and word_count < 15:
            score -= 0.2
        
        return max(0.0, min(1.0, score))
    
    def _get_provider_for_endpoint(
        self,
        provider_name: str,
        endpoint_url: Optional[str] = None
    ) -> ModelProvider:
        """
        Get or create a provider for a specific endpoint.
        
        This allows guide and specialist to use different Ollama instances.
        """
        # For non-Ollama providers, use the registered one
        if provider_name != "ollama" or not endpoint_url:
            if provider_name in self.providers:
                return self.providers[provider_name]
            raise ValueError(f"Provider not available: {provider_name}")
        
        # For Ollama, we may need endpoint-specific providers
        cache_key = f"ollama:{endpoint_url}"
        
        if cache_key not in self.providers:
            # Create a new provider for this endpoint
            logger.info(f"Creating Ollama provider for: {endpoint_url}")
            self.providers[cache_key] = OllamaProvider(base_url=endpoint_url)
        
        return self.providers[cache_key]
    
    def _route_task(
        self,
        task_type: TaskType,
        prefer_specialist: bool,
        prompt: str = ""
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Route task to appropriate model.
        
        Phase 12e: Uses complexity scoring for auto routing.
        Phase 14: Returns endpoint URL for multi-endpoint support.
        
        Returns:
            Tuple of (model_id, provider_name, endpoint_url)
        """
        strategy = self.config.get("routing", {}).get("strategy", "auto")
        orch_config = self.config.get("orchestrator", {})
        spec_config = self.config.get("specialist", {})
        
        # Force orchestrator-only mode
        if strategy == "orchestrator_only":
            return (
                self.orchestrator_id, 
                orch_config.get("provider", "ollama"),
                orch_config.get("endpoint")
            )
        
        # Check if specialist is available and should be used
        specialist_available = spec_config.get("enabled") and self.specialist_id
        
        if specialist_available:
            # Tasks that benefit from specialist
            specialist_tasks = self.config.get("routing", {}).get("prefer_specialist_for", [])
            
            # Explicit preference or task type match
            if prefer_specialist or task_type.value in specialist_tasks:
                logger.debug(f"Routing to specialist for {task_type}")
                return (
                    self.specialist_id, 
                    spec_config.get("provider", "ollama"),
                    spec_config.get("endpoint")
                )
            
            # Auto-routing based on complexity (Phase 12e)
            if strategy == "auto" and prompt:
                complexity = self._score_complexity(prompt)
                threshold = self.config.get("routing", {}).get("complexity_threshold", 0.5)
                
                if complexity >= threshold:
                    logger.info(f"Complexity score {complexity:.2f} >= {threshold}, routing to specialist")
                    return (
                        self.specialist_id, 
                        spec_config.get("provider", "ollama"),
                        spec_config.get("endpoint")
                    )
                else:
                    logger.debug(f"Complexity score {complexity:.2f} < {threshold}, using orchestrator")
        
        # Default to orchestrator
        logger.debug(f"Routing to orchestrator for {task_type}")
        return (
            self.orchestrator_id, 
            orch_config.get("provider", "ollama"),
            orch_config.get("endpoint")
        )
    
    def list_available_models(self) -> List[ModelConfig]:
        """List all available models across all providers."""
        models = []
        
        for provider_name, provider in self.providers.items():
            try:
                provider_models = provider.list_models()
                models.extend(provider_models)
            except Exception as e:
                logger.warning(f"Failed to list models from {provider_name}: {e}")
        
        return models
    
    def get_status(self) -> Dict[str, Any]:
        """Get router status and loaded models."""
        return {
            "orchestrator": {
                "model_id": self.orchestrator_id,
                "loaded": self._is_model_loaded(self.orchestrator_id),
                "provider": self.config.get("orchestrator", {}).get("provider")
            },
            "specialist": {
                "model_id": self.specialist_id,
                "loaded": self._is_model_loaded(self.specialist_id),
                "provider": self.config.get("specialist", {}).get("provider"),
                "enabled": self.config.get("specialist", {}).get("enabled", False)
            },
            "providers": {
                name: provider.health_check()
                for name, provider in self.providers.items()
            }
        }
    
    def _is_model_loaded(self, model_id: Optional[str]) -> bool:
        """Check if a model is loaded."""
        if not model_id:
            return False
        
        for provider in self.providers.values():
            if provider.is_loaded(model_id):
                return True
        
        return False
    
    def set_specialist(self, model_id: str, provider_name: str = "ollama"):
        """
        Change the specialist model.
        
        Args:
            model_id: New specialist model ID
            provider_name: Provider to use
        """
        # Unload old specialist
        if self.specialist_id and provider_name in self.providers:
            old_provider = self.providers[provider_name]
            old_provider.unload_model(self.specialist_id)
        
        # Update config
        self.specialist_id = model_id
        self.config["specialist"]["model"] = model_id
        self.config["specialist"]["provider"] = provider_name
        self.config["specialist"]["enabled"] = True
        
        # Save config
        self._save_config()
        
        logger.info(f"Specialist changed to: {model_id}")
    
    def disable_specialist(self):
        """Disable specialist model (orchestrator-only mode)."""
        # Unload specialist
        if self.specialist_id:
            for provider in self.providers.values():
                if provider.is_loaded(self.specialist_id):
                    provider.unload_model(self.specialist_id)
        
        self.config["specialist"]["enabled"] = False
        self._save_config()
        
        logger.info("Specialist disabled, using orchestrator-only mode")
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
            
            logger.debug("Saved router configuration")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
