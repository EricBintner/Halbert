"""
Learned discovery classifications.

Stores AI-identified and user-corrected classifications for system components.
This allows the system to "learn" what components are over time.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger('halbert.discovery.learned')


@dataclass
class LearnedClassification:
    """A learned classification for a system component."""
    pattern: str  # e.g., "tailscale*" or exact name
    type: str  # e.g., "Tailscale VPN", "Bridge", "Bond"
    description: str  # What it does
    purpose: str  # Why it's on the system
    confidence: float  # 0-1, how confident we are
    source: str  # 'ai', 'user', 'builtin'
    verified: bool  # True if user-verified
    created_at: str
    updated_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LearnedClassification':
        return cls(**data)


class LearnedDiscoveryStore:
    """
    Store for learned discovery classifications.
    
    Allows the system to learn and remember what system components are,
    with user override capability.
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the store."""
        if config_dir is None:
            config_dir = Path.home() / '.config' / 'halbert'
        
        self.config_dir = config_dir
        self.config_path = config_dir / 'learned_discoveries.yml'
        self._cache: Dict[str, LearnedClassification] = {}
        self._load()
    
    def _load(self):
        """Load learned classifications from disk."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                for key, value in data.items():
                    self._cache[key] = LearnedClassification.from_dict(value)
                
                logger.info(f"Loaded {len(self._cache)} learned classifications")
            except Exception as e:
                logger.error(f"Failed to load learned discoveries: {e}")
    
    def _save(self):
        """Save learned classifications to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        data = {k: v.to_dict() for k, v in self._cache.items()}
        
        with open(self.config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    
    def get(self, name: str) -> Optional[LearnedClassification]:
        """
        Get classification for a component.
        
        Args:
            name: Component name (e.g., interface name)
            
        Returns:
            LearnedClassification if found, None otherwise
        """
        # First try exact match
        if name in self._cache:
            return self._cache[name]
        
        # Then try pattern matching
        for pattern, classification in self._cache.items():
            if '*' in pattern:
                # Simple glob-style matching
                prefix = pattern.replace('*', '')
                if name.startswith(prefix):
                    return classification
        
        return None
    
    def set(
        self,
        name: str,
        type: str,
        description: str,
        purpose: str = "",
        confidence: float = 1.0,
        source: str = 'user',
        verified: bool = True
    ):
        """
        Store a classification.
        
        Args:
            name: Component name or pattern (e.g., "tailscale*")
            type: Classification type
            description: What it does
            purpose: Why it's on the system
            confidence: Confidence level (0-1)
            source: 'ai', 'user', or 'builtin'
            verified: True if user-verified
        """
        now = datetime.now().isoformat()
        
        existing = self._cache.get(name)
        
        self._cache[name] = LearnedClassification(
            pattern=name,
            type=type,
            description=description,
            purpose=purpose,
            confidence=confidence,
            source=source,
            verified=verified,
            created_at=existing.created_at if existing else now,
            updated_at=now
        )
        
        self._save()
        logger.info(f"Stored classification for '{name}': {type}")
    
    def delete(self, name: str) -> bool:
        """Delete a classification."""
        if name in self._cache:
            del self._cache[name]
            self._save()
            return True
        return False
    
    def get_all(self) -> Dict[str, LearnedClassification]:
        """Get all learned classifications."""
        return self._cache.copy()
    
    def clear_ai_learned(self):
        """Clear all AI-learned classifications (keep user-verified ones)."""
        to_remove = [k for k, v in self._cache.items() if v.source == 'ai' and not v.verified]
        for key in to_remove:
            del self._cache[key]
        self._save()


# Singleton instance
_store: Optional[LearnedDiscoveryStore] = None


def get_learned_store() -> LearnedDiscoveryStore:
    """Get the singleton learned discovery store."""
    global _store
    if _store is None:
        _store = LearnedDiscoveryStore()
    return _store
