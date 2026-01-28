"""
Feature Flags for Gradual Rollout

Controls rollout of new agent features.
Based on research5.md Part 20.3.
"""

import os
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, Set, Optional

logger = logging.getLogger('halbert.config.feature_flags')


@dataclass
class FeatureFlags:
    """Feature flags for gradual migration."""
    
    # Agent state machine
    use_new_agent: bool = False
    agent_rollout_percentage: float = 0.0
    
    # Component flags
    use_crag_evaluation: bool = False
    use_hybrid_memory: bool = False
    use_streaming_responses: bool = True
    use_tool_safety: bool = True
    
    # Specific features
    enable_web_search: bool = False
    enable_code_execution: bool = False
    max_agent_loops: int = 5
    crag_confidence_threshold: float = 0.7
    
    # User overrides (users who always get new agent)
    force_new_agent_users: Set[str] = field(default_factory=set)
    
    # User exclusions (users who never get new agent)
    exclude_new_agent_users: Set[str] = field(default_factory=set)
    
    @classmethod
    def from_env(cls) -> 'FeatureFlags':
        """Load feature flags from environment variables."""
        def parse_bool(key: str, default: bool = False) -> bool:
            val = os.getenv(key, str(default)).lower()
            return val in ('true', '1', 'yes', 'on')
        
        def parse_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        def parse_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        def parse_set(key: str) -> Set[str]:
            val = os.getenv(key, "")
            return set(v.strip() for v in val.split(",") if v.strip())
        
        return cls(
            use_new_agent=parse_bool("HALBERT_USE_NEW_AGENT"),
            agent_rollout_percentage=parse_float("HALBERT_AGENT_ROLLOUT", 0.0),
            use_crag_evaluation=parse_bool("HALBERT_USE_CRAG"),
            use_hybrid_memory=parse_bool("HALBERT_USE_HYBRID_MEMORY"),
            use_streaming_responses=parse_bool("HALBERT_USE_STREAMING", True),
            use_tool_safety=parse_bool("HALBERT_USE_TOOL_SAFETY", True),
            enable_web_search=parse_bool("HALBERT_ENABLE_WEB_SEARCH"),
            enable_code_execution=parse_bool("HALBERT_ENABLE_CODE_EXEC"),
            max_agent_loops=parse_int("HALBERT_MAX_AGENT_LOOPS", 5),
            crag_confidence_threshold=parse_float("HALBERT_CRAG_THRESHOLD", 0.7),
            force_new_agent_users=parse_set("HALBERT_FORCE_NEW_AGENT_USERS"),
            exclude_new_agent_users=parse_set("HALBERT_EXCLUDE_NEW_AGENT_USERS"),
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            "use_new_agent": self.use_new_agent,
            "agent_rollout_percentage": self.agent_rollout_percentage,
            "use_crag_evaluation": self.use_crag_evaluation,
            "use_hybrid_memory": self.use_hybrid_memory,
            "use_streaming_responses": self.use_streaming_responses,
            "use_tool_safety": self.use_tool_safety,
            "enable_web_search": self.enable_web_search,
            "enable_code_execution": self.enable_code_execution,
            "max_agent_loops": self.max_agent_loops,
            "crag_confidence_threshold": self.crag_confidence_threshold,
        }


# Global instance
_flags: Optional[FeatureFlags] = None


def get_feature_flags(reload: bool = False) -> FeatureFlags:
    """Get global feature flags instance."""
    global _flags
    if _flags is None or reload:
        _flags = FeatureFlags.from_env()
        logger.info(f"Feature flags loaded: {_flags.to_dict()}")
    return _flags


def should_use_new_agent(
    session_id: str = None,
    user_id: str = None,
    flags: FeatureFlags = None
) -> bool:
    """
    Determine if this session should use the new agent.
    
    Uses consistent hashing for percentage-based rollout.
    
    Args:
        session_id: Session identifier for consistent bucketing
        user_id: Optional user ID for overrides
        flags: Optional flags instance (uses global if not provided)
        
    Returns:
        True if new agent should be used
    """
    flags = flags or get_feature_flags()
    
    # Check if feature is globally disabled
    if not flags.use_new_agent:
        return False
    
    # Check user overrides
    if user_id:
        if user_id in flags.force_new_agent_users:
            logger.debug(f"User {user_id} forced to new agent")
            return True
        if user_id in flags.exclude_new_agent_users:
            logger.debug(f"User {user_id} excluded from new agent")
            return False
    
    # 100% rollout
    if flags.agent_rollout_percentage >= 100:
        return True
    
    # 0% rollout
    if flags.agent_rollout_percentage <= 0:
        return False
    
    # Percentage-based rollout using consistent hashing
    bucket_key = session_id or user_id or "default"
    hash_val = int(hashlib.md5(bucket_key.encode()).hexdigest(), 16)
    bucket = (hash_val % 100) + 1
    
    result = bucket <= flags.agent_rollout_percentage
    logger.debug(
        f"Rollout check: key={bucket_key}, bucket={bucket}, "
        f"threshold={flags.agent_rollout_percentage}, result={result}"
    )
    
    return result


def is_feature_enabled(feature_name: str, flags: FeatureFlags = None) -> bool:
    """
    Check if a specific feature is enabled.
    
    Args:
        feature_name: Name of the feature flag
        flags: Optional flags instance
        
    Returns:
        True if feature is enabled
    """
    flags = flags or get_feature_flags()
    
    feature_map = {
        "new_agent": flags.use_new_agent,
        "crag": flags.use_crag_evaluation,
        "hybrid_memory": flags.use_hybrid_memory,
        "streaming": flags.use_streaming_responses,
        "tool_safety": flags.use_tool_safety,
        "web_search": flags.enable_web_search,
        "code_execution": flags.enable_code_execution,
    }
    
    return feature_map.get(feature_name, False)


def set_feature_flag(flag_name: str, value: bool) -> bool:
    """
    Dynamically set a feature flag (for testing/admin).
    
    Args:
        flag_name: Name of the flag
        value: New value
        
    Returns:
        True if flag was set successfully
    """
    flags = get_feature_flags()
    
    if hasattr(flags, flag_name):
        setattr(flags, flag_name, value)
        logger.info(f"Feature flag '{flag_name}' set to {value}")
        return True
    
    logger.warning(f"Unknown feature flag: {flag_name}")
    return False
