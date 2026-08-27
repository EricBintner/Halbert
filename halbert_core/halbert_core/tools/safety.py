# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tool Safety Framework

Classifies tool operations by risk level and enforces safety policies.
Based on research5.md Part 11.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Set, Pattern, Optional
import fnmatch
import re
import logging

logger = logging.getLogger('halbert.tools.safety')


_RISK_ORDER = {
    "safe": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
}


class RiskLevel(Enum):
    """Risk classification for tool operations."""
    SAFE = "safe"           # Auto-execute, no logging needed
    LOW = "low"             # Auto-execute, log for audit
    MEDIUM = "medium"       # Execute, warn user in response
    HIGH = "high"           # Require explicit user confirmation
    CRITICAL = "critical"   # Block entirely, never execute


@dataclass
class SafetyRule:
    """A rule for classifying command safety."""
    pattern: Pattern
    risk_level: RiskLevel
    reason: str


@dataclass
class SafetyCheckResult:
    """Result of a safety classification check."""
    risk_level: RiskLevel
    allowed: bool
    requires_confirmation: bool
    reason: str
    matched_rule: Optional[str] = None


class ToolSafetyFramework:
    """
    Classifies tool operations by risk level.
    
    Based on research4.md Part 26: Tool Execution Safety.
    
    Risk Levels:
        SAFE - Read-only operations, auto-execute
        LOW - Minor changes, log and execute  
        MEDIUM - Moderate changes, warn user
        HIGH - Significant changes, require confirmation
        CRITICAL - Dangerous operations, block entirely
    """
    
    # Commands that are ALWAYS blocked - no exceptions
    # These are checked with word boundaries to avoid false positives
    BLOCKED_COMMANDS: Set[str] = {
        ":(){ :|:& };:",  # Fork bomb
    }
    
    # Patterns that are blocked (regex for precise matching)
    BLOCKED_PATTERNS = [
        re.compile(r"rm\s+(-[rf]+\s+)*/$"),  # rm -rf / exactly
        re.compile(r"rm\s+(-[rf]+\s+)*/\*"),  # rm -rf /*
        re.compile(r"mkfs\.\w+\s+/dev/[sh]d"),  # mkfs on real disk
        re.compile(r"dd\s+.*of=/dev/[sh]d[a-z]$"),  # dd to real disk (not partition)
        re.compile(r">\s*/dev/[sh]d[a-z]$"),  # redirect to disk
        re.compile(r"^(shutdown|reboot|halt|poweroff|init\s+[06])(\s|$)"),  # system power
    ]
    
    # Patterns for risk classification (checked in order)
    RULES: List[SafetyRule] = [
        # CRITICAL - System destruction
        SafetyRule(
            re.compile(r"rm\s+(-[rf]+\s+)*/(s|$)", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Recursive delete of root filesystem"
        ),
        SafetyRule(
            re.compile(r"mkfs\.", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Filesystem formatting"
        ),
        SafetyRule(
            re.compile(r"dd\s+.*of=/dev/[sh]d", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Direct disk write"
        ),
        SafetyRule(
            re.compile(r">\s*/dev/(sd|hd|nvme)", re.IGNORECASE),
            RiskLevel.CRITICAL,
            "Direct device write"
        ),
        
        # HIGH - Significant system changes
        SafetyRule(
            re.compile(r"rm\s+(-[rf]+\s+)+", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive or forced delete"
        ),
        SafetyRule(
            re.compile(r"chmod\s+-R", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive permission change"
        ),
        SafetyRule(
            re.compile(r"chown\s+-R", re.IGNORECASE),
            RiskLevel.HIGH,
            "Recursive ownership change"
        ),
        SafetyRule(
            re.compile(r"apt(-get)?\s+(install|remove|purge|autoremove)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"dnf\s+(install|remove|erase)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"yum\s+(install|remove|erase)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Package management"
        ),
        SafetyRule(
            re.compile(r"pip\s+install", re.IGNORECASE),
            RiskLevel.HIGH,
            "Python package installation"
        ),
        SafetyRule(
            re.compile(r"npm\s+(install|uninstall)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Node.js package management"
        ),
        SafetyRule(
            re.compile(r"systemctl\s+(start|stop|restart|enable|disable)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Service management"
        ),
        SafetyRule(
            re.compile(r"service\s+\w+\s+(start|stop|restart)", re.IGNORECASE),
            RiskLevel.HIGH,
            "Service management"
        ),
        SafetyRule(
            re.compile(r"sudo\s+", re.IGNORECASE),
            RiskLevel.HIGH,
            "Elevated privileges"
        ),
        SafetyRule(
            re.compile(r"su\s+-", re.IGNORECASE),
            RiskLevel.HIGH,
            "User switching"
        ),
        
        # MEDIUM - Modifications
        SafetyRule(
            re.compile(r"mv\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File move/rename"
        ),
        SafetyRule(
            re.compile(r"cp\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File copy"
        ),
        SafetyRule(
            re.compile(r"rm\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File deletion"
        ),
        SafetyRule(
            re.compile(r">\s*\S+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "File redirection/overwrite"
        ),
        SafetyRule(
            re.compile(r">>\s*\S+", re.IGNORECASE),
            RiskLevel.LOW,
            "File append"
        ),
        SafetyRule(
            re.compile(r"chmod\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "Permission change"
        ),
        SafetyRule(
            re.compile(r"chown\s+", re.IGNORECASE),
            RiskLevel.MEDIUM,
            "Ownership change"
        ),
        
        # LOW - Minor changes
        SafetyRule(
            re.compile(r"mkdir\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "Directory creation"
        ),
        SafetyRule(
            re.compile(r"touch\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "File creation/timestamp update"
        ),
        SafetyRule(
            re.compile(r"ln\s+", re.IGNORECASE),
            RiskLevel.LOW,
            "Link creation"
        ),
        
        # SAFE - Read-only operations
        SafetyRule(
            re.compile(r"^(cat|head|tail|less|more)\s+", re.IGNORECASE),
            RiskLevel.SAFE,
            "File reading"
        ),
        SafetyRule(
            re.compile(r"^(ls|dir|find|locate)\s*", re.IGNORECASE),
            RiskLevel.SAFE,
            "Directory listing"
        ),
        SafetyRule(
            re.compile(r"^(grep|egrep|fgrep|rg|ag)\s+", re.IGNORECASE),
            RiskLevel.SAFE,
            "Text search"
        ),
        SafetyRule(
            re.compile(r"^(wc|du|df|stat|file)\s*", re.IGNORECASE),
            RiskLevel.SAFE,
            "File/disk info"
        ),
        SafetyRule(
            re.compile(r"^(pwd|whoami|hostname|uname|date|uptime|id)", re.IGNORECASE),
            RiskLevel.SAFE,
            "System info"
        ),
        SafetyRule(
            re.compile(r"^systemctl\s+status", re.IGNORECASE),
            RiskLevel.SAFE,
            "Service status"
        ),
        SafetyRule(
            re.compile(r"^(ps|top|htop|free|vmstat|iostat)", re.IGNORECASE),
            RiskLevel.SAFE,
            "Process/memory info"
        ),
        SafetyRule(
            re.compile(r"^(ip|ifconfig|netstat|ss|ping|traceroute|dig|nslookup)", re.IGNORECASE),
            RiskLevel.SAFE,
            "Network info"
        ),
        SafetyRule(
            re.compile(r"^echo\s+", re.IGNORECASE),
            RiskLevel.SAFE,
            "Echo command"
        ),
    ]
    
    # Paths that elevate risk
    SENSITIVE_PATHS: Set[str] = {
        "/etc/",
        "/boot/",
        "/usr/",
        "/var/",
        "/root/",
        "/sys/",
        "/proc/",
        "/dev/",
        "~/.ssh/",
        "~/.gnupg/",
        "~/.config/",
    }
    
    def __init__(self, user_overrides: Dict[str, RiskLevel] = None):
        """
        Initialize the safety framework.
        
        Args:
            user_overrides: Optional dict mapping command patterns to risk levels
        """
        self.user_overrides = user_overrides or {}
        self._skill_safety = None

    def set_skill_safety(self, safety) -> None:
        """Install the active skills' composed safety constraints.

        Skills contribute *rules*, not enforcement. Every tool call already
        passes through this classifier on its way to ToolExecutor and, for
        HIGH risk, to the approval flow — so skill constraints join that chain
        instead of standing up a parallel gate that a caller could bypass.

        Pass None to clear (skills are per-turn). Duck-typed on the four
        SkillSafety fields so tools/ need not import skills/.
        """
        self._skill_safety = safety

    def _check_skill_safety(self, tool_name: str, args: Dict) -> Optional[SafetyCheckResult]:
        """Classify against the active skills' constraints, if any match."""
        safety = self._skill_safety
        if safety is None:
            return None

        command = str(args.get("command", "") or "").strip()
        path = str(args.get("path", "") or "").strip()

        for pattern in getattr(safety, "blocked_commands", ()) or ():
            if command and (fnmatch.fnmatch(command, pattern) or pattern.rstrip("*") in command):
                logger.warning("BLOCKED by active skill: %s (pattern %s)", command, pattern)
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Blocked by an active skill: matches {pattern!r}",
                    matched_rule="skill.blocked_commands",
                )

        needs_approval = bool(getattr(safety, "destructive_requires_approval", False))

        for pattern in getattr(safety, "protected_paths", ()) or ():
            hit = (path and (fnmatch.fnmatch(path, pattern) or path.startswith(pattern.rstrip("*"))))
            if not hit and command:
                hit = fnmatch.fnmatch(command, f"*{pattern}*") or pattern.rstrip("/*") in command
            if hit:
                return SafetyCheckResult(
                    risk_level=RiskLevel.HIGH,
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"An active skill protects {pattern}",
                    matched_rule="skill.protected_paths",
                )

        if command and needs_approval:
            for service in getattr(safety, "protected_services", ()) or ():
                if service in command and any(
                    verb in command for verb in ("stop", "disable", "mask", "kill", "restart")
                ):
                    return SafetyCheckResult(
                        risk_level=RiskLevel.HIGH,
                        allowed=True,
                        requires_confirmation=True,
                        reason=f"An active skill protects the {service} service",
                        matched_rule="skill.protected_services",
                    )

        return None

    def classify(self, tool_name: str, args: Dict) -> SafetyCheckResult:
        """
        Classify risk level for a tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            SafetyCheckResult with risk level and policy

        When active skills declare safety constraints, the stricter of the
        built-in classification and the skill classification wins. Skills can
        only tighten: a skill cannot make a CRITICAL built-in command safe.
        """
        base = self._classify_builtin(tool_name, args)
        from_skill = self._check_skill_safety(tool_name, args)
        if from_skill is None:
            return base
        if _RISK_ORDER[from_skill.risk_level.value] > _RISK_ORDER[base.risk_level.value]:
            return from_skill
        return base

    def _classify_builtin(self, tool_name: str, args: Dict) -> SafetyCheckResult:
        """The framework's own classification, before skill constraints."""
        if tool_name == "run_command":
            return self._classify_command(args.get("command", ""))
        elif tool_name in ("write_file", "write_config"):
            return self._classify_write(args.get("path", ""))
        elif tool_name in ("read_file", "cat", "read_config"):
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Read-only operation"
            )
        elif tool_name in ("search", "search_discoveries", "recall_memory", "web_search"):
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Search operation"
            )
        else:
            # Unknown tools get MEDIUM by default
            return SafetyCheckResult(
                risk_level=RiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason=f"Unknown tool: {tool_name}"
            )
    
    def _classify_command(self, command: str) -> SafetyCheckResult:
        """Classify a shell command."""
        command = command.strip()
        command_lower = command.lower()
        
        # Check blocked commands first (exact matches)
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                logger.warning(f"BLOCKED command: {command}")
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Blocked command pattern: {blocked}",
                    matched_rule="BLOCKED_COMMANDS"
                )
        
        # Check blocked patterns (regex)
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.search(command):
                logger.warning(f"BLOCKED command: {command}")
                return SafetyCheckResult(
                    risk_level=RiskLevel.CRITICAL,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Blocked command pattern",
                    matched_rule=pattern.pattern
                )
        
        # Check rules in order
        for rule in self.RULES:
            if rule.pattern.search(command):
                risk = rule.risk_level
                
                # Elevate risk if touching sensitive paths
                if risk in (RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM):
                    for path in self.SENSITIVE_PATHS:
                        if path in command:
                            # Elevate by one level
                            if risk == RiskLevel.SAFE:
                                risk = RiskLevel.LOW
                            elif risk == RiskLevel.LOW:
                                risk = RiskLevel.MEDIUM
                            elif risk == RiskLevel.MEDIUM:
                                risk = RiskLevel.HIGH
                            break
                
                return SafetyCheckResult(
                    risk_level=risk,
                    allowed=risk != RiskLevel.CRITICAL,
                    requires_confirmation=risk == RiskLevel.HIGH,
                    reason=rule.reason,
                    matched_rule=rule.pattern.pattern
                )
        
        # Check if command touches sensitive paths
        for path in self.SENSITIVE_PATHS:
            if path in command:
                return SafetyCheckResult(
                    risk_level=RiskLevel.MEDIUM,
                    allowed=True,
                    requires_confirmation=False,
                    reason=f"Accesses sensitive path: {path}"
                )
        
        # Default for unrecognized commands
        return SafetyCheckResult(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=False,
            reason="Unrecognized command pattern"
        )
    
    def _classify_write(self, path: str) -> SafetyCheckResult:
        """Classify a file write operation."""
        for sensitive in self.SENSITIVE_PATHS:
            if path.startswith(sensitive) or sensitive in path:
                return SafetyCheckResult(
                    risk_level=RiskLevel.HIGH,
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"Write to sensitive path: {sensitive}"
                )
        
        return SafetyCheckResult(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=False,
            reason="File write operation"
        )
    
    def get_confirmation_message(
        self,
        tool_name: str,
        args: Dict,
        result: SafetyCheckResult
    ) -> str:
        """
        Generate a human-readable confirmation message.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: SafetyCheckResult from classify()
            
        Returns:
            Confirmation message string
        """
        if tool_name == "run_command":
            cmd = args.get("command", "")
            return (
                f"**Execute command:**\n"
                f"```\n{cmd}\n```\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        elif tool_name in ("write_file", "write_config"):
            path = args.get("path", "")
            content_preview = args.get("content", "")[:200]
            return (
                f"**Write to file:** `{path}`\n\n"
                f"**Content preview:**\n"
                f"```\n{content_preview}...\n```\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
        else:
            return (
                f"**Execute:** {tool_name}\n"
                f"**Args:** {args}\n\n"
                f"**Risk Level:** {result.risk_level.value.upper()}\n"
                f"**Reason:** {result.reason}"
            )
