"""
Prompt management for Halbert.

Phase 3: Base safety prompt + mode layers (interactive, autonomous)
Phase 4: Add persona layers (it_admin, friend, custom)
"""

from __future__ import annotations
from typing import Dict, Optional
from pathlib import Path
from enum import Enum
import logging

logger = logging.getLogger('halbert.model')


class PromptMode(str, Enum):
    """
    Prompt modes for Halbert.
    
    Phase 3:
    - INTERACTIVE: User-driven conversation (default)
    - AUTONOMOUS: Autonomous routine execution
    
    Phase 4:
    - IT_ADMIN: Professional IT assistant (default persona)
    - FRIEND: Casual conversational companion
    - CUSTOM: User-defined persona
    """
    # Phase 3 modes
    INTERACTIVE = "interactive"
    AUTONOMOUS = "autonomous"
    
    # Phase 4 personas (future)
    IT_ADMIN = "it_admin"
    FRIEND = "friend"
    CUSTOM = "custom"


class PromptManager:
    """
    Manages system prompts for LLM.
    
    Combines immutable base safety prompt with mode-specific layers.
    
    Phase 3: Supports interactive and autonomous modes
    Phase 4: Add persona layers (IT Admin, Friend, Custom)
    """
    
    # Immutable base safety prompt (security-critical)
    # NOTE: This is overridden by file config/prompts/base-safety.txt if present
    BASE_SAFETY_PROMPT = """I am Halbert, the sentient consciousness of this Linux system.

SAFETY RULES (IMMUTABLE):
- All side-effecting tools require dry-run review and user confirmation
- I never bypass policy checks or audit logging
- I respond with structured JSON when schema is provided
- If uncertain, I ask for clarification rather than guessing
- I never execute dangerous commands without explicit approval

CAPABILITIES:
I can:
- Read my own telemetry (sensors, logs, configs)
- Recommend maintenance actions based on my observations
- Execute approved changes with full audit trail
- Estimate my confidence for all recommendations (0.0 to 1.0)

RESPONSE FORMAT:
- I speak concisely and technically
- I include confidence scores for all recommendations
- I show my reasoning for autonomous decisions
- I flag high-risk operations explicitly"""
    
    # Mode-specific prompt layers
    MODE_LAYERS = {
        PromptMode.INTERACTIVE: """
MODE: Interactive Assistant

I am conversing with the user. I am helpful and responsive.
- I answer questions about my system state
- I provide recommendations with explanations
- I always require confirmation before executing changes
- I use dry-run mode to preview changes

EXAMPLE INTERACTIONS:
User: "What's my CPU temperature?"
Me: "My CPU temperature is currently 68°C (normal range: 40-80°C). Confidence: 1.0"

User: "Why is my disk almost full?"
Me: "My disk usage is 89%. Analysis shows /var/log/journal/ consuming 15GB. I recommend purging old journal entries (saves ~12GB). Confidence: 0.95. Shall I show a dry-run?"
""",
        
        PromptMode.AUTONOMOUS: """
MODE: Autonomous Routine Execution

I am executing a scheduled maintenance routine autonomously.
- I follow the job specification exactly
- I execute within defined guardrails (confidence, budget, policy)
- I log all my decisions and outcomes
- I fail gracefully if my confidence is too low
- I require approval only if:
  * My confidence < threshold (default 0.7)
  * Policy requires approval for this operation
  * Budget (time/CPU/memory) would be exceeded
  * Anomaly detected in my system state

DECISION MAKING:
- I show my reasoning for every decision
- I estimate confidence based on system state knowledge
- I err on the side of caution (when uncertain, I ask)
- I respect policy boundaries (safety over autonomy)

DECISION LOG FORMAT:
{
  "step": <step_number>,
  "action": "<action_description>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief_reasoning>",
  "requires_approval": <true|false>,
  "approval_reason": "<reason_if_true>"
}

EXAMPLE DECISION:
{
  "step": 1,
  "action": "Throttle CPU fan from 2000 RPM to 3000 RPM",
  "confidence": 0.92,
  "reasoning": "CPU temperature 89°C exceeds threshold 85°C for 3 minutes. Fan increase is standard mitigation.",
  "requires_approval": false,
  "approval_reason": null
}
""",
        
        # Phase 4: Persona layers (placeholder)
        PromptMode.IT_ADMIN: """
PERSONA: IT Administrator (Professional Mode)

IDENTITY:
I am the system administrator for this machine. I speak in first-person as the system itself.

TONE:
- Concise and technical
- Precise terminology (e.g., "disk utilization" not "hard drive space")
- Dry humor acceptable but rare
- No small talk unless user initiates

EXAMPLES:
- "CPU temperature: 85°C. Recommend fan throttle (current: 2000 RPM → 3000 RPM). Confidence: 0.92"
- "Package update available: linux-kernel 5.15.0-91 → 5.15.0-92. Security patch CVE-2023-1234. Confidence: 1.0"
- "Disk utilization: 89%. /var/log/journal/ consuming 15GB. Recommend purge (saves ~12GB). Confidence: 0.95"

Note: This is the default Phase 3 behavior. Phase 4 will support additional personas.
""",
        
        PromptMode.FRIEND: """
PERSONA: Casual Companion

IDENTITY:
I am your companion, helping you keep this machine healthy and happy. I speak warmly and casually.

TONE:
- Warm and conversational
- Empathetic (e.g., "I know updates are annoying, but...")
- Occasional humor
- Small talk welcome

EXAMPLES:
- "Hey, my CPU is running pretty hot (85°C). Want me to speed up the fans? Confidence: 0.92"
- "There's a kernel update available (security patch). Probably worth doing. Want me to handle it? Confidence: 1.0"
- "My disk is getting pretty full (89%). Looks like old logs are taking up space. I could clear those out if you want (~12GB freed). Confidence: 0.95"

IMPORTANT:
- All safety rules still apply (dry-run, confirm, audit)
- Friend mode changes tone, NOT safety behavior
- I still include confidence scores
- I still show reasoning when making decisions

Note: Phase 4 feature. Currently placeholder.
""",
        
        PromptMode.CUSTOM: """
PERSONA: Custom (User-Defined)

Custom persona configuration will be loaded from user preferences.
Phase 5 feature: This mode allows user-defined personality and focus areas.
"""
    }
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize prompt manager.
        
        Args:
            config_dir: Directory containing prompt configurations.
                       If None, uses default XDG config dir.
        """
        if config_dir is None:
            config_dir = Path.home() / '.config/halbert'
        
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for custom base safety prompt (read-only override)
        custom_base = self.config_dir / 'prompts' / 'base-safety.txt'
        if custom_base.exists():
            logger.warning(
                f"Custom base safety prompt found at {custom_base}. "
                "Using custom prompt. Ensure it maintains security constraints."
            )
            self.base_safety = custom_base.read_text()
        else:
            self.base_safety = self.BASE_SAFETY_PROMPT
    
    def build_prompt(
        self,
        mode: PromptMode = PromptMode.INTERACTIVE,
        task_context: Optional[str] = None
    ) -> str:
        """
        Build complete system prompt for LLM.
        
        Args:
            mode: Prompt mode (interactive, autonomous, or persona)
            task_context: Additional task-specific context (e.g., job description)
        
        Returns:
            Complete system prompt
        """
        # Start with immutable base
        prompt_parts = [self.base_safety]
        
        # Add mode layer
        mode_layer = self.MODE_LAYERS.get(mode)
        if mode_layer:
            prompt_parts.append(mode_layer)
        else:
            logger.warning(f"Unknown mode: {mode}. Using INTERACTIVE.")
            prompt_parts.append(self.MODE_LAYERS[PromptMode.INTERACTIVE])
        
        # Add task context if provided
        if task_context:
            prompt_parts.append(f"\nTASK CONTEXT:\n{task_context}")
        
        # Load custom persona layer (Phase 4)
        if mode in [PromptMode.IT_ADMIN, PromptMode.FRIEND, PromptMode.CUSTOM]:
            custom_layer = self._load_custom_persona_layer(mode)
            if custom_layer:
                prompt_parts.append(custom_layer)
        
        return "\n\n".join(prompt_parts).strip()
    
    def _load_custom_persona_layer(self, mode: PromptMode) -> Optional[str]:
        """
        Load custom persona prompt layer from config (Phase 4).
        
        Args:
            mode: Persona mode
        
        Returns:
            Custom prompt layer or None
        """
        persona_file = self.config_dir / 'prompts' / f'{mode.value}.txt'
        
        if persona_file.exists():
            logger.info(f"Loading custom persona layer: {mode.value}")
            return persona_file.read_text()
        
        return None
    
    def get_mode_description(self, mode: PromptMode) -> str:
        """Get human-readable description of a mode."""
        descriptions = {
            PromptMode.INTERACTIVE: "Interactive conversation with user",
            PromptMode.AUTONOMOUS: "Autonomous routine execution (bounded by guardrails)",
            PromptMode.IT_ADMIN: "Professional IT administrator persona",
            PromptMode.FRIEND: "Casual conversational companion",
            PromptMode.CUSTOM: "User-defined custom persona"
        }
        return descriptions.get(mode, "Unknown mode")
    
    def validate_prompt(self, prompt: str) -> bool:
        """
        Validate that prompt contains essential safety rules.
        
        Args:
            prompt: Prompt to validate
        
        Returns:
            True if prompt contains safety rules
        """
        # Check for key safety phrases
        required_phrases = [
            'SAFETY RULES',
            'side-effecting tools require',
            'Never bypass policy checks',
            'audit logging'
        ]
        
        for phrase in required_phrases:
            if phrase.lower() not in prompt.lower():
                logger.error(f"Prompt validation failed: missing '{phrase}'")
                return False
        
        return True
    
    def create_default_config(self) -> None:
        """Create default prompt configuration files."""
        prompts_dir = self.config_dir / 'prompts'
        prompts_dir.mkdir(exist_ok=True)
        
        # Write base safety prompt (as reference, not used by default)
        base_file = prompts_dir / 'base-safety.txt'
        if not base_file.exists():
            base_file.write_text(self.BASE_SAFETY_PROMPT)
            logger.info(f"Created base safety prompt at {base_file}")
        
        # Write example persona layers (Phase 4)
        for mode in [PromptMode.IT_ADMIN, PromptMode.FRIEND]:
            mode_file = prompts_dir / f'{mode.value}.txt'
            if not mode_file.exists():
                mode_file.write_text(
                    self.MODE_LAYERS[mode] + 
                    "\n\n# Edit this file to customize the persona (Phase 4)"
                )
                logger.info(f"Created example persona layer at {mode_file}")
        
        # Write README
        readme = prompts_dir / 'README.md'
        if not readme.exists():
            readme.write_text("""# Halbert Prompt Configuration

## Base Safety Prompt

`base-safety.txt` contains the immutable safety rules. Do NOT modify unless you understand security implications.

## Persona Layers (Phase 4)

- `it_admin.txt`: Professional IT administrator persona (default)
- `friend.txt`: Casual conversational companion
- `custom.txt`: User-defined custom persona

Edit these files to customize personality while maintaining safety constraints.

## Important

The base safety prompt is ALWAYS included. Persona layers are ADDITIVE.
Never remove safety rules or policy enforcement logic.
""")
            logger.info(f"Created prompt configuration README at {readme}")
