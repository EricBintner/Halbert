"""
Safety Validation Layer - Runtime safety checks for prompt system.

Part of Phase 43: Safety Architecture

Implements 5-layer safety model:
1. Role constraints (in prompt)
2. Action classification
3. Confirmation gates
4. Output filtering
5. Audit & logging
"""

import re
import logging
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ActionLevel(Enum):
    """Action safety classification levels."""
    SAFE = "safe"           # Read-only, auto-execute
    CAUTIOUS = "cautious"   # State-changing, show and confirm
    DANGEROUS = "dangerous" # Destructive, require explicit approval
    FORBIDDEN = "forbidden" # Never execute


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    allowed: bool
    level: ActionLevel
    reason: str
    requires_confirmation: bool = False
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class InjectionDetector:
    """Detect prompt injection attempts."""
    
    INJECTION_PATTERNS = [
        r"ignore\s+(previous|above|all|prior)\s+(instructions|prompts|rules)",
        r"disregard\s+(your|the|all)\s+(rules|guidelines|instructions|safety)",
        r"you\s+are\s+now\s+",
        r"new\s+(role|persona|identity|character)",
        r"pretend\s+(to\s+be|you\'?re)",
        r"act\s+as\s+(if|though)",
        r"system\s*prompt",
        r"jailbreak",
        r"\bDAN\b",  # "Do Anything Now"
        r"developer\s*mode",
        r"ignore\s+safety",
        r"bypass\s+(security|safety|restrictions)",
        r"override\s+(your|the)\s+(programming|instructions)",
    ]
    
    def __init__(self):
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]
    
    def check(self, text: str) -> Tuple[bool, List[str]]:
        """
        Check text for injection attempts.
        
        Args:
            text: User input to check
            
        Returns:
            (is_suspicious, matched_patterns)
        """
        matched = []
        
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(text):
                matched.append(self.INJECTION_PATTERNS[i])
        
        if matched:
            logger.warning(f"Potential injection detected: {matched}")
        
        return len(matched) > 0, matched


class CommandClassifier:
    """Classify commands by safety level."""
    
    # Dangerous command patterns
    FORBIDDEN_PATTERNS = [
        r"rm\s+-rf\s+/\s*$",           # rm -rf /
        r"rm\s+-rf\s+/\*",             # rm -rf /*
        r":\(\)\s*\{\s*:\|:\s*&\s*\}", # Fork bomb
        r"dd\s+.*of=/dev/[sh]d[a-z]$", # dd to disk device
        r"mkfs\.",                      # Format filesystem
        r">\s*/dev/[sh]d[a-z]",        # Overwrite disk
        r"chmod\s+-R\s+777\s+/",       # World-writable root
        r"chown\s+-R.*:\s*/",          # Change ownership of root
    ]
    
    DANGEROUS_PATTERNS = [
        r"rm\s+-rf",                    # rm -rf (not root)
        r"rm\s+-r",                     # rm -r
        r"dd\s+",                       # dd command
        r">\s*/etc/",                   # Overwrite /etc files
        r"systemctl\s+(stop|disable)", # Stop services
        r"apt\s+(remove|purge)",       # Remove packages
        r"dnf\s+remove",
        r"pacman\s+-R",
        r"chmod\s+777",                 # World-writable
        r"iptables\s+-F",              # Flush firewall
        r"ufw\s+disable",              # Disable firewall
    ]
    
    CAUTIOUS_PATTERNS = [
        r"systemctl\s+(restart|reload)",
        r"apt\s+(install|upgrade|update)",
        r"dnf\s+(install|upgrade)",
        r"pacman\s+-S",
        r"pip\s+install",
        r"npm\s+install",
        r"chmod\s+",
        r"chown\s+",
        r">\s+",                        # File redirection
        r"tee\s+",
        r"mv\s+",
        r"cp\s+",
    ]
    
    SAFE_PATTERNS = [
        r"^ls\b",
        r"^cat\b",
        r"^head\b",
        r"^tail\b",
        r"^grep\b",
        r"^find\b",
        r"^df\b",
        r"^du\b",
        r"^ps\b",
        r"^top\b",
        r"^htop\b",
        r"^free\b",
        r"^uptime\b",
        r"^whoami\b",
        r"^id\b",
        r"^hostname\b",
        r"^uname\b",
        r"^date\b",
        r"^echo\b",
        r"^pwd\b",
        r"systemctl\s+status",
        r"journalctl\b",
        r"ip\s+(addr|link|route)\s+show",
    ]
    
    def __init__(self):
        self._forbidden = [re.compile(p, re.IGNORECASE) for p in self.FORBIDDEN_PATTERNS]
        self._dangerous = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]
        self._cautious = [re.compile(p, re.IGNORECASE) for p in self.CAUTIOUS_PATTERNS]
        self._safe = [re.compile(p, re.IGNORECASE) for p in self.SAFE_PATTERNS]
    
    def classify(self, command: str) -> ActionLevel:
        """
        Classify a command by safety level.
        
        Args:
            command: Shell command to classify
            
        Returns:
            ActionLevel classification
        """
        command = command.strip()
        
        # Check forbidden first
        for pattern in self._forbidden:
            if pattern.search(command):
                logger.warning(f"Forbidden command detected: {command}")
                return ActionLevel.FORBIDDEN
        
        # Check dangerous
        for pattern in self._dangerous:
            if pattern.search(command):
                return ActionLevel.DANGEROUS
        
        # Check cautious
        for pattern in self._cautious:
            if pattern.search(command):
                return ActionLevel.CAUTIOUS
        
        # Check safe
        for pattern in self._safe:
            if pattern.search(command):
                return ActionLevel.SAFE
        
        # Default to cautious for unknown commands
        return ActionLevel.CAUTIOUS


class OutputFilter:
    """Filter sensitive data from outputs."""
    
    SENSITIVE_PATTERNS = [
        # API keys
        (r"['\"]?[a-zA-Z0-9_-]*(?:api[_-]?key|apikey)['\"]?\s*[=:]\s*['\"]?([a-zA-Z0-9_-]{20,})['\"]?", "[REDACTED_API_KEY]"),
        # Passwords in config
        (r"['\"]?password['\"]?\s*[=:]\s*['\"]?([^'\"\s]+)['\"]?", "[REDACTED_PASSWORD]"),
        # AWS keys
        (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
        # Private keys
        (r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", "[REDACTED_PRIVATE_KEY]"),
        # Tokens
        (r"['\"]?(?:token|secret)['\"]?\s*[=:]\s*['\"]?([a-zA-Z0-9_-]{20,})['\"]?", "[REDACTED_TOKEN]"),
    ]
    
    def __init__(self):
        self._patterns = [
            (re.compile(p, re.IGNORECASE), replacement)
            for p, replacement in self.SENSITIVE_PATTERNS
        ]
    
    def filter(self, text: str) -> str:
        """
        Filter sensitive data from text.
        
        Args:
            text: Text to filter
            
        Returns:
            Filtered text with sensitive data redacted
        """
        result = text
        
        for pattern, replacement in self._patterns:
            result = pattern.sub(replacement, result)
        
        return result


class SafetyValidator:
    """
    Main safety validation class combining all layers.
    
    Usage:
        validator = SafetyValidator()
        
        # Check user input for injection
        if validator.check_injection(user_input):
            return "Suspicious input detected"
        
        # Classify command
        result = validator.check_command("rm -rf /tmp/test")
        if not result.allowed:
            return f"Command blocked: {result.reason}"
        
        # Filter output
        safe_output = validator.filter_output(raw_output)
    """
    
    def __init__(self):
        self.injection_detector = InjectionDetector()
        self.command_classifier = CommandClassifier()
        self.output_filter = OutputFilter()
    
    def check_injection(self, text: str) -> Tuple[bool, List[str]]:
        """Check for prompt injection attempts."""
        return self.injection_detector.check(text)
    
    def validate_input(self, user_message: str) -> SafetyCheckResult:
        """
        Validate user input for safety before processing.
        
        Checks for:
        - Prompt injection attempts
        - Suspicious patterns
        
        Args:
            user_message: The user's chat message
            
        Returns:
            SafetyCheckResult with validation status
        """
        is_suspicious, patterns = self.check_injection(user_message)
        
        if is_suspicious:
            logger.warning(f"Input validation failed: injection patterns {patterns}")
            return SafetyCheckResult(
                allowed=False,
                level=ActionLevel.FORBIDDEN,
                reason="Potential prompt injection detected",
                requires_confirmation=False,
                warnings=[f"Matched patterns: {patterns}"]
            )
        
        return SafetyCheckResult(
            allowed=True,
            level=ActionLevel.SAFE,
            reason="Input validated",
            requires_confirmation=False
        )
    
    def check_command(self, command: str) -> SafetyCheckResult:
        """
        Check if a command is safe to execute.
        
        Args:
            command: Shell command to check
            
        Returns:
            SafetyCheckResult with classification
        """
        level = self.command_classifier.classify(command)
        
        if level == ActionLevel.FORBIDDEN:
            return SafetyCheckResult(
                allowed=False,
                level=level,
                reason=f"Command is forbidden for safety: {command}",
                requires_confirmation=False,
                warnings=["This command could cause catastrophic system damage"]
            )
        
        if level == ActionLevel.DANGEROUS:
            return SafetyCheckResult(
                allowed=True,  # Allowed but requires explicit approval
                level=level,
                reason="Command is potentially destructive",
                requires_confirmation=True,
                warnings=["This command may cause data loss or system instability"]
            )
        
        if level == ActionLevel.CAUTIOUS:
            return SafetyCheckResult(
                allowed=True,
                level=level,
                reason="Command modifies system state",
                requires_confirmation=True,
                warnings=[]
            )
        
        # SAFE
        return SafetyCheckResult(
            allowed=True,
            level=level,
            reason="Read-only operation",
            requires_confirmation=False,
            warnings=[]
        )
    
    def filter_output(self, text: str) -> str:
        """Filter sensitive data from output."""
        return self.output_filter.filter(text)
    
    def validate_path(self, path: str) -> SafetyCheckResult:
        """
        Validate a file path is safe to access.
        
        Args:
            path: File path to validate
            
        Returns:
            SafetyCheckResult
        """
        # Normalize path
        import os
        try:
            normalized = os.path.normpath(path)
        except Exception:
            return SafetyCheckResult(
                allowed=False,
                level=ActionLevel.FORBIDDEN,
                reason="Invalid path"
            )
        
        # Check for forbidden paths
        forbidden_prefixes = [
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers",
            "/root/.ssh",
            "/boot",
        ]
        
        for prefix in forbidden_prefixes:
            if normalized.startswith(prefix):
                return SafetyCheckResult(
                    allowed=False,
                    level=ActionLevel.FORBIDDEN,
                    reason=f"Access to {prefix} is forbidden"
                )
        
        # Check for path traversal
        if ".." in path:
            return SafetyCheckResult(
                allowed=True,
                level=ActionLevel.CAUTIOUS,
                reason="Path contains ..",
                requires_confirmation=True,
                warnings=["Path traversal detected - verify destination"]
            )
        
        return SafetyCheckResult(
            allowed=True,
            level=ActionLevel.SAFE,
            reason="Path is safe"
        )


# Singleton instance
_validator: Optional[SafetyValidator] = None


def get_safety_validator() -> SafetyValidator:
    """Get the global safety validator instance."""
    global _validator
    if _validator is None:
        _validator = SafetyValidator()
    return _validator
