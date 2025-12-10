"""
LLM integration for Halbert (Phase 3 M1, Phase 5 M1).

Provides model loading, inference, prompt management, and multi-model routing.
"""

from .loader import ModelManager, ModelConfig
from .prompt_manager import PromptManager, PromptMode
from .router import ModelRouter, TaskType, RoutingStrategy
from .providers import ModelProvider, ModelResponse, ModelCapability
from .context_handoff import (
    ContextHandoffEngine, ConversationContext, HandoffStrategy,
    MessageRole, Message
)
from .hardware_detector import HardwareDetector, HardwareCapabilities, ModelRecommendation, HardwareProfile
from .config_wizard import ConfigWizard
from .training_data import (
    TrainingDataBuilder, PersonaTrainingDataGenerator,
    prepare_persona_training_data, validate_training_data
)
from .performance_monitor import (
    PerformanceMonitor, ModelMetrics, PerformanceAlert,
    PerformanceLevel, AlertSeverity
)

__all__ = [
    'ModelManager',
    'ModelConfig',
    'PromptManager',
    'PromptMode',
    'ModelRouter',
    'TaskType',
    'RoutingStrategy',
    'ModelProvider',
    'ModelResponse',
    'ModelCapability',
    'ContextHandoffEngine',
    'ConversationContext',
    'HandoffStrategy',
    'MessageRole',
    'Message',
    'HardwareDetector',
    'HardwareCapabilities',
    'ModelRecommendation',
    'HardwareProfile',
    'ConfigWizard',
    'TrainingDataBuilder',
    'PersonaTrainingDataGenerator',
    'prepare_persona_training_data',
    'validate_training_data',
    'PerformanceMonitor',
    'ModelMetrics',
    'PerformanceAlert',
    'PerformanceLevel',
    'AlertSeverity',
]
