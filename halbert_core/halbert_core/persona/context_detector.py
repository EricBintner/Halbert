"""
Context detection for auto-persona switching (Phase 4 M4).

Detects user context based on running applications and suggests
appropriate persona switches.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timezone, time as dt_time
from pathlib import Path
import logging
import subprocess
import re

from ..obs.logging import get_logger
from ..obs.audit import write_audit

logger = get_logger("halbert")


@dataclass
class ContextSignal:
    """Detected context signal from running processes."""
    context_type: str  # "music", "development", "browsing", "productivity"
    confidence: float  # 0.0 to 1.0
    source_processes: List[str]
    suggested_persona: str
    reason: str


@dataclass
class ContextPreferences:
    """User preferences for auto-context switching."""
    enabled: bool = True
    auto_switch: bool = False  # If True, auto-switch without asking
    do_not_disturb_hours: List[str] = None  # ["22:00-08:00"]
    notification_cooldown_minutes: int = 30
    min_confidence: float = 0.7  # Minimum confidence to suggest


class ContextDetector:
    """
    Detects user context from running applications and suggests persona switches.
    
    Phase 4 M4: Auto-context awareness for smart persona switching
    
    Usage:
        detector = ContextDetector()
        
        # Detect current context
        signal = detector.detect_context()
        if signal:
            print(f"Suggested persona: {signal.suggested_persona}")
            print(f"Reason: {signal.reason}")
        
        # Check if suggestion should be shown
        if detector.should_suggest(signal):
            # Show notification to user
            pass
    """
    
    # Context detection rules (app patterns → context type)
    CONTEXT_RULES = {
        "music": {
            "patterns": [
                r"ardour",
                r"reaper",
                r"bitwig",
                r"ableton",
                r"lmms",
                r"audacity",
                r"spotify",
                r"rhythmbox",
                r"clementine",
                r"vlc.*music",
            ],
            "persona": "friend",
            "confidence": 0.9,
            "reason": "Music production/listening apps detected"
        },
        "development": {
            "patterns": [
                r"code",
                r"vscode",
                r"vim",
                r"nvim",
                r"emacs",
                r"sublime",
                r"pycharm",
                r"intellij",
                r"eclipse",
                r"atom",
            ],
            "persona": "it_admin",
            "confidence": 0.8,
            "reason": "Development tools detected"
        },
        "terminal": {
            "patterns": [
                r"gnome-terminal",
                r"konsole",
                r"xterm",
                r"kitty",
                r"alacritty",
                r"tmux",
                r"screen",
            ],
            "persona": "it_admin",
            "confidence": 0.7,
            "reason": "Terminal/system administration tools active"
        },
        "browsing": {
            "patterns": [
                r"firefox",
                r"chrome",
                r"chromium",
                r"brave",
                r"opera",
            ],
            "persona": "friend",  # Assume casual browsing
            "confidence": 0.5,  # Lower confidence, could be work or leisure
            "reason": "Web browsing detected"
        },
        "productivity": {
            "patterns": [
                r"libreoffice",
                r"gimp",
                r"inkscape",
                r"blender",
                r"kdenlive",
            ],
            "persona": "friend",
            "confidence": 0.6,
            "reason": "Creative/productivity apps detected"
        }
    }
    
    def __init__(self, prefs_file: Optional[Path] = None):
        """
        Initialize context detector.
        
        Args:
            prefs_file: Path to preferences file
                       If None, uses default location
        """
        if prefs_file is None:
            prefs_file = Path.home() / '.config/halbert/context_preferences.json'
        
        self.prefs_file = Path(prefs_file)
        self.prefs_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load preferences
        self.prefs = self._load_preferences()
        
        # Track last suggestion time (per context type)
        self.last_suggestion: Dict[str, datetime] = {}
        
        logger.info("ContextDetector initialized", extra={
            "enabled": self.prefs.enabled,
            "auto_switch": self.prefs.auto_switch,
            "min_confidence": self.prefs.min_confidence
        })
    
    def _load_preferences(self) -> ContextPreferences:
        """Load context preferences from file."""
        if self.prefs_file.exists():
            try:
                import json
                with open(self.prefs_file, 'r') as f:
                    data = json.load(f)
                
                return ContextPreferences(
                    enabled=data.get("enabled", True),
                    auto_switch=data.get("auto_switch", False),
                    do_not_disturb_hours=data.get("do_not_disturb_hours", ["22:00-08:00"]),
                    notification_cooldown_minutes=data.get("notification_cooldown_minutes", 30),
                    min_confidence=data.get("min_confidence", 0.7)
                )
            except Exception as e:
                logger.warning(f"Failed to load context preferences: {e}. Using defaults.")
        
        # Return defaults
        return ContextPreferences(
            enabled=True,
            auto_switch=False,
            do_not_disturb_hours=["22:00-08:00"],
            notification_cooldown_minutes=30,
            min_confidence=0.7
        )
    
    def _save_preferences(self):
        """Save context preferences to file."""
        try:
            import json
            data = {
                "enabled": self.prefs.enabled,
                "auto_switch": self.prefs.auto_switch,
                "do_not_disturb_hours": self.prefs.do_not_disturb_hours,
                "notification_cooldown_minutes": self.prefs.notification_cooldown_minutes,
                "min_confidence": self.prefs.min_confidence
            }
            
            with open(self.prefs_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Saved context preferences")
        except Exception as e:
            logger.error(f"Failed to save context preferences: {e}")
    
    def get_running_processes(self) -> Set[str]:
        """
        Get list of running process names.
        
        Returns:
            Set of lowercase process names
        """
        try:
            # Use ps to get running processes
            result = subprocess.run(
                ['ps', '-eo', 'comm'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Parse process names (one per line, skip header)
                processes = set()
                for line in result.stdout.strip().split('\n')[1:]:
                    if line:
                        # Get base process name (remove path)
                        proc_name = line.strip().split('/')[-1].lower()
                        processes.add(proc_name)
                
                return processes
            else:
                logger.error(f"ps command failed: {result.stderr}")
                return set()
        
        except subprocess.TimeoutExpired:
            logger.error("ps command timed out")
            return set()
        except Exception as e:
            logger.error(f"Failed to get running processes: {e}")
            return set()
    
    def detect_context(self) -> Optional[ContextSignal]:
        """
        Detect current user context from running processes.
        
        Returns:
            ContextSignal if context detected, None otherwise
        """
        if not self.prefs.enabled:
            logger.debug("Context detection disabled")
            return None
        
        # Get running processes
        processes = self.get_running_processes()
        
        if not processes:
            logger.warning("No processes detected")
            return None
        
        # Check each context rule
        detected_contexts = []
        
        for context_type, rule in self.CONTEXT_RULES.items():
            matching_processes = []
            
            for pattern in rule["patterns"]:
                regex = re.compile(pattern, re.IGNORECASE)
                matches = [p for p in processes if regex.search(p)]
                matching_processes.extend(matches)
            
            if matching_processes:
                signal = ContextSignal(
                    context_type=context_type,
                    confidence=rule["confidence"],
                    source_processes=matching_processes,
                    suggested_persona=rule["persona"],
                    reason=rule["reason"]
                )
                detected_contexts.append(signal)
        
        # Return highest confidence context
        if detected_contexts:
            best_context = max(detected_contexts, key=lambda x: x.confidence)
            
            logger.info(f"Context detected: {best_context.context_type}", extra={
                "context_type": best_context.context_type,
                "confidence": best_context.confidence,
                "suggested_persona": best_context.suggested_persona,
                "processes": best_context.source_processes
            })
            
            return best_context
        
        logger.debug("No context detected from running processes")
        return None
    
    def should_suggest(self, signal: Optional[ContextSignal]) -> bool:
        """
        Check if a persona suggestion should be shown to user.
        
        Args:
            signal: Detected context signal
        
        Returns:
            True if suggestion should be shown
        """
        if not signal:
            return False
        
        if not self.prefs.enabled:
            return False
        
        # Check confidence threshold
        if signal.confidence < self.prefs.min_confidence:
            logger.debug(f"Context confidence too low: {signal.confidence} < {self.prefs.min_confidence}")
            return False
        
        # Check do-not-disturb hours
        if self._is_do_not_disturb():
            logger.debug("In do-not-disturb hours, skipping suggestion")
            return False
        
        # Check cooldown (avoid spamming suggestions)
        if self._is_in_cooldown(signal.context_type):
            logger.debug(f"Context '{signal.context_type}' is in cooldown period")
            return False
        
        return True
    
    def _is_do_not_disturb(self) -> bool:
        """Check if current time is in do-not-disturb hours."""
        if not self.prefs.do_not_disturb_hours:
            return False
        
        now = datetime.now().time()
        
        for dnd_range in self.prefs.do_not_disturb_hours:
            try:
                # Parse "HH:MM-HH:MM"
                start_str, end_str = dnd_range.split('-')
                start = dt_time.fromisoformat(start_str.strip())
                end = dt_time.fromisoformat(end_str.strip())
                
                # Handle overnight ranges (e.g., 22:00-08:00)
                if start <= end:
                    if start <= now <= end:
                        return True
                else:
                    if now >= start or now <= end:
                        return True
            except Exception as e:
                logger.warning(f"Invalid DND range: {dnd_range}: {e}")
        
        return False
    
    def _is_in_cooldown(self, context_type: str) -> bool:
        """Check if context type is in cooldown period."""
        if context_type not in self.last_suggestion:
            return False
        
        last_time = self.last_suggestion[context_type]
        now = datetime.now(timezone.utc)
        
        elapsed_minutes = (now - last_time).total_seconds() / 60
        
        return elapsed_minutes < self.prefs.notification_cooldown_minutes
    
    def record_suggestion(self, context_type: str):
        """Record that a suggestion was shown for a context type."""
        self.last_suggestion[context_type] = datetime.now(timezone.utc)
        
        logger.debug(f"Recorded suggestion for context: {context_type}")
    
    def update_preferences(
        self,
        enabled: Optional[bool] = None,
        auto_switch: Optional[bool] = None,
        do_not_disturb_hours: Optional[List[str]] = None,
        notification_cooldown_minutes: Optional[int] = None,
        min_confidence: Optional[float] = None
    ):
        """Update context detection preferences."""
        if enabled is not None:
            self.prefs.enabled = enabled
        if auto_switch is not None:
            self.prefs.auto_switch = auto_switch
        if do_not_disturb_hours is not None:
            self.prefs.do_not_disturb_hours = do_not_disturb_hours
        if notification_cooldown_minutes is not None:
            self.prefs.notification_cooldown_minutes = notification_cooldown_minutes
        if min_confidence is not None:
            self.prefs.min_confidence = min_confidence
        
        self._save_preferences()
        
        logger.info("Updated context preferences", extra={
            "enabled": self.prefs.enabled,
            "auto_switch": self.prefs.auto_switch
        })
