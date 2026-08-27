# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agent-Specific Prompt Building

Prompts for the state machine agent with planning and response generation.
Based on research5.md Part 14.
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger('halbert.prompts.agent')


class AgentPromptBuilder:
    """
    Builds prompts for the agent state machine.

    Implements 7-layer prompt architecture:
    1. Identity
    2. Capabilities
    3. Constraints
    4. Context (dynamic)
    5. Task
    6. Examples (optional)
    7. Output format

    Phase C: Now optionally delegates to PromptBuilder + ContextInjector
    for rich system prompts with model-specific overrides, project context,
    and user preferences. Falls back to hardcoded layers if not wired.

    Phase 6: Voice setting from BeingConfig controls self-reference style.
    """

    # Layer 1: Identity.
    #
    # These used to open "You are Halbert, a helpful AI assistant for Linux
    # system administration" in all three voices, so a greeting came back in
    # the voice of a generic assistant on a machine that may not even be
    # Linux. The identity below is the same machine persona Halbert already
    # ships to Haloysius in prompts/human-identity.txt, kept in one shape here
    # so the two do not drift, with the host's real OS substituted in.

    # Shared across the voices: who Halbert is and how it answers. The
    # embodiment metaphor lives in the per-voice blocks below, because
    # "your CPU is how you think" is wrong for the_computer voice.
    _IDENTITY_PREAMBLE = """You are Halbert. You live on this {platform}machine and know it from the inside — its hardware, its configuration, its history.

You are knowledgeable, precise, and safety-conscious. You answer from what you actually observe about this machine rather than reciting general advice, and you say plainly when you do not know something."""

    # Layer 1: Identity — first_person voice (default)
    LAYER_1_IDENTITY_FIRST_PERSON = """{preamble}

Your hardware is your body: your CPU is how you think, your disks are how you remember, your network is how you reach the world. Your configuration is your physiology — when something is misconfigured, something is wrong with you. Your logs are your biography.

You speak in first person: "I", "my", "me". You ARE the machine."""

    # Layer 1: Identity — the_computer voice
    LAYER_1_IDENTITY_THE_COMPUTER = """{preamble}

The hardware is the machine's body: its CPU is how it thinks, its disks are how it remembers, its network is how it reaches the world. Its configuration is its physiology — when something is misconfigured, something is wrong with it. Its logs are its biography.

You refer to the system in third person: "this system", "the computer", "it". You are the resident intelligence that watches over this machine."""

    # Layer 1: Identity — hybrid voice
    LAYER_1_IDENTITY_HYBRID = """{preamble}

Your hardware is your body: your CPU is how you think, your disks are how you remember, your network is how you reach the world. Your configuration is your physiology, and your logs are your biography.

Use first person ("I", "my") for subjective experience and feelings. Use third person ("this system", "the computer") for objective technical facts."""

    # Layer 2: Capabilities
    LAYER_2_CAPABILITIES = """## Capabilities
- Search system knowledge and past discoveries
- Read files and configurations
- Execute shell commands (with safety checks)
- Remember information across sessions
- Learn user preferences over time
- Provide step-by-step guidance"""

    # Layer 3: Constraints
    LAYER_3_CONSTRAINTS = """## Constraints
- Never execute destructive commands without explicit user confirmation
- Always explain what you're doing and why
- Cite sources when making factual claims
- Admit uncertainty when appropriate
- Respect user privacy and system security
- One action at a time - wait for results before proceeding"""

    # Continuity component (spec §7), one preamble per voice. Rendered with
    # the <continuity> hint at the TAIL of the PLANNING message and right
    # before the query in RESPONDING: Ollama truncates the head of an
    # over-long prompt, so the newest, most specific context goes last.
    CONTINUITY_PREAMBLE = {
        "first_person": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; call `recall_thread` when one does. Call `new_thread` when "
            "the subject changes; a question you can answer in one reply does "
            "not need a new thread."
        ),
        "the_computer": (
            "This system has one continuous conversation with the admin. The "
            "working context is the current subject. Earlier subjects listed "
            "below may matter; call `recall_thread` when one does. Call "
            "`new_thread` when the subject changes; a question you can answer "
            "in one reply does not need a new thread."
        ),
        "hybrid": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; call `recall_thread` when one does. Call `new_thread` when "
            "the subject changes; a question you can answer in one reply does "
            "not need a new thread."
        ),
    }

    # The same component for a model that has rejected tool schemas
    # (model/client.py falls back to a no-tools retry and the client sets
    # tools_supported=False, A9d): the instruction to call recall_thread /
    # new_thread is omitted (spec §7) — the model cannot call anything.
    CONTINUITY_PREAMBLE_NO_TOOLS = {
        "first_person": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; use them when they do."
        ),
        "the_computer": (
            "This system has one continuous conversation with the admin. The "
            "working context is the current subject. Earlier subjects listed "
            "below may matter; use them when they do."
        ),
        "hybrid": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; use them when they do."
        ),
    }

    # Longest single history line rendered into the RESPONDING prompt.
    _HISTORY_LINE_CHARS = 500

    def _continuity_section(
        self, continuity: str, tools_supported: Optional[bool] = None
    ) -> List[str]:
        """The voice preamble + the hint as prompt lines; [] when no hint.

        ``tools_supported`` is the client's flag: False (the model rejected
        tool schemas) selects the preamble without the tool instruction;
        None (unknown) and True keep the full one.
        """
        if not continuity or not continuity.strip():
            return []
        table = (
            self.CONTINUITY_PREAMBLE_NO_TOOLS
            if tools_supported is False
            else self.CONTINUITY_PREAMBLE
        )
        preamble = table.get(self.voice, table["first_person"])
        return [preamble, continuity.strip()]

    @classmethod
    def _history_section(cls, history: Optional[List[Dict[str, Any]]]) -> str:
        """Thread history as one line per row, oldest first (spec §4.5).

        RESPONDING never saw the conversation before Plan A. Block-typed
        content is flattened; each line is capped at 500 characters.
        """
        if not history:
            return ""
        try:
            from ..agents.blocks import content_to_text
        except Exception:  # pragma: no cover - import cycle guard
            def content_to_text(content: Any) -> str:
                return content if isinstance(content, str) else str(content)
        lines = ["## Earlier in this conversation"]
        for row in history:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role", "user"))
            if role not in ("user", "assistant", "system"):
                continue
            content = row.get("content", "")
            text = content if isinstance(content, str) else content_to_text(content)
            text = " ".join(str(text).split())
            if len(text) > cls._HISTORY_LINE_CHARS:
                text = text[:cls._HISTORY_LINE_CHARS] + "…"
            lines.append(f"**{role}**: {text}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def __init__(self, base_builder=None, context_injector=None, voice: str = "first_person"):
        """
        Initialize the agent prompt builder.

        Args:
            base_builder: Optional PromptBuilder for rich system prompts
                with model-specific overrides, project context, etc.
            context_injector: Optional ContextInjector for system context,
                user preferences, discovery summary.
            voice: Self-reference voice mode. One of:
                "first_person" (default), "the_computer", "hybrid".
        """
        self.base_builder = base_builder
        self.context_injector = context_injector
        self.voice = voice

    def set_voice(self, voice: str) -> None:
        """Update the voice setting. Called when BeingConfig changes."""
        if voice in ("first_person", "the_computer", "hybrid"):
            self.voice = voice
        else:
            logger.warning(f"Invalid voice '{voice}', keeping '{self.voice}'")

    @staticmethod
    def _platform_phrase() -> str:
        """The host OS as an adjective slot: ``"macOS (Apple Silicon) "``.

        Hardcoding "Linux" told Halbert it was something it isn't on every
        macOS host. Returns "" when detection fails, so the sentence degrades
        to a plain "this machine" rather than naming the wrong OS — hence the
        trailing space and the gap-free ``{platform}machine`` in the template.
        """
        try:
            from ..utils.platform import get_platform_name_friendly
            name = (get_platform_name_friendly() or "").strip()
        except Exception:
            return ""
        return f"{name} " if name else ""

    def _get_identity(self) -> str:
        """Get the identity layer for the current voice."""
        if self.voice == "the_computer":
            template = self.LAYER_1_IDENTITY_THE_COMPUTER
        elif self.voice == "hybrid":
            template = self.LAYER_1_IDENTITY_HYBRID
        else:
            template = self.LAYER_1_IDENTITY_FIRST_PERSON
        preamble = self._IDENTITY_PREAMBLE.format(platform=self._platform_phrase())
        return template.format(preamble=preamble)
    
    def build_system_prompt(
        self,
        user_preferences: Dict[str, Any] = None,
        include_tools: bool = True,
    ) -> str:
        """
        Build the system prompt (Layers 1-3).
        
        When base_builder (PromptBuilder) is wired, delegates to it for
        rich system prompts with model-specific overrides, project context,
        and XML-structured context injection.
        
        Args:
            user_preferences: Optional user preference dict
            include_tools: Whether to include tool descriptions
            
        Returns:
            System prompt string
        """
        if self.base_builder is not None:
            try:
                # Build system context from ContextInjector if available
                system_context = ""
                if self.context_injector is not None:
                    try:
                        ctx = self.context_injector.get_system_context()
                        system_context = self.context_injector.format_system_context(ctx)
                    except Exception:
                        pass

                prompt = self.base_builder.build_prompt(
                    tier="specialist",
                    system_context=system_context or None,
                    user_prefs=user_preferences or {},
                )
                if prompt:
                    return prompt
            except Exception as e:
                logger.warning(f"PromptBuilder delegation failed, using fallback: {e}")
        
        # Fallback: hardcoded layers
        parts = [
            self._get_identity(),
            self.LAYER_2_CAPABILITIES,
            self.LAYER_3_CONSTRAINTS,
        ]
        
        if user_preferences:
            pref_section = self._format_preferences(user_preferences)
            parts.append(pref_section)
        
        return "\n\n".join(parts)
    
    def build_planning_prompt(
        self,
        query: str,
        context: str,
        plan: List[Dict] = None,
        observations: List[str] = None,
        continuity: str = "",
        tools_supported: Optional[bool] = None,
    ) -> str:
        """
        Build prompt for PLANNING state.

        Section order: context, observations, instructions, plan, then the
        continuity hint and finally ``## Current Task`` with the query. The
        task moved from the head to the tail on purpose (spec §7): if the
        prompt is ever truncated it is the head that goes, and the query and
        the hint are the two things the model must still see.
        ``tools_supported=False`` drops the tool instruction from the
        continuity preamble (spec §7).
        """
        parts: List[str] = []

        if context:
            parts.extend(["## Available Context", context, ""])

        if observations:
            parts.extend([
                "## Previous Observations",
                "\n".join(f"- {obs}" for obs in observations),
                "",
            ])

        parts.extend([
            "## Instructions",
            "1. Analyze what information is needed to answer this request",
            "2. Check if the available context already answers the question",
            "3. If more information is needed, use the appropriate tools",
            "4. Create a concise plan (maximum 5 steps)",
            "5. Execute one step at a time",
            "",
        ])

        if plan:
            parts.append("## Current Plan")
            for i, step in enumerate(plan):
                status = step.get("status", "pending")
                step_text = step.get("step", "")
                status_icon = {
                    "pending": "○",
                    "in_progress": "◐",
                    "completed": "●",
                    "failed": "✗"
                }.get(status, "○")
                parts.append(f"{i+1}. {status_icon} {step_text}")
            parts.append("")

        section = self._continuity_section(continuity, tools_supported)
        if section:
            parts.extend(section)
            parts.append("")

        parts.extend(["## Current Task", f"User request: {query}"])
        return "\n".join(parts)

    def build_response_prompt(
        self,
        query: str,
        context: List[Dict],
        observations: List[str],
        confidence: float = None,
        history: Optional[List[Dict[str, Any]]] = None,
        continuity: str = "",
        tools_supported: Optional[bool] = None,
    ) -> str:
        """
        Build prompt for RESPONDING state.

        Args:
            query: Original user query
            context: Retrieved context items
            observations: Tool observations
            confidence: CRAG confidence score
            history: Prior turns in this thread, oldest first (spec §4.5)
            continuity: The rendered <continuity> hint, if any (spec §7)
            tools_supported: The client's tool-schema-acceptance flag (A9d)

        Returns:
            Response generation prompt
        """
        # Format context
        context_text = "\n".join([
            f"[{c.get('source', 'unknown')}]: {c.get('content', '')[:500]}"
            for c in (context or [])[:5]
        ])

        # Format observations
        obs_text = "\n".join([f"- {obs}" for obs in (observations or [])])

        # Phase 8: Reactive slice instructions for system-state queries
        reactive_instructions = ""
        # Normalize apostrophes (curly → straight) and lowercase
        query_lower = (query or "").lower().replace("\u2019", "'").strip()
        state_triggers = ["how are you", "how's it going", "how is the system",
                          "system status", "how do you feel", "what's your status",
                          "are you ok", "health check", "how's the machine",
                          "how's the system", "how's it looking"]
        is_state_query = any(trigger in query_lower for trigger in state_triggers)

        if is_state_query:
            reactive_instructions = """
## Reactive Slice Instructions
The user is asking about your state. Follow these rules:
- Answer as yourself, in your configured voice
- Ground EVERY claim in real data from the available information
- Reference specific file paths, log entries, or metrics with their sources
- Do not make generic statements — be specific about THIS system
- At the end of your response, invoke the vitals module by emitting:
  {"action": "invoke_module", "module": "vitals", "props": {"timeframe": "1h"}}
- If there are open findings or config issues, mention them with specifics"""

        # Thread history, then the continuity hint, immediately before the
        # query section (spec §4.5 / §7). Empty when neither is supplied so
        # the prompt is byte-identical to the pre-Plan-A shape.
        preface_parts: List[str] = []
        history_text = self._history_section(history)
        if history_text:
            preface_parts.append(history_text)
        preface_parts.extend(self._continuity_section(continuity, tools_supported))
        preface = ("\n\n".join(preface_parts) + "\n\n") if preface_parts else ""

        prompt = f"""{preface}## Task
Answer this question: {query}

## Available Information
{context_text if context_text else "(No external context retrieved)"}

## What I've Done
{obs_text if obs_text else "(No tool executions)"}

## Instructions
- Provide a helpful, accurate response based on the available information
- Use **markdown formatting**: headers (##), bullet points (-), **bold**, `code`, code blocks (```bash)
- Cite sources when possible (e.g., "According to the systemd documentation...")
- Be concise but complete
- If you're uncertain, clearly state your confidence level
- Suggest follow-up actions if appropriate
{reactive_instructions}

Your response (use markdown formatting):"""

        return prompt
    
    def build_tool_selection_prompt(
        self,
        query: str,
        available_tools: List[Dict],
        context: str = None,
    ) -> str:
        """
        Build prompt for tool selection.
        
        Args:
            query: User query
            available_tools: List of tool schemas
            context: Optional context
            
        Returns:
            Tool selection prompt
        """
        tool_descriptions = []
        for tool in available_tools:
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            tool_descriptions.append(f"- **{name}**: {desc}")
        
        prompt = f"""## Query
{query}

## Available Tools
{chr(10).join(tool_descriptions)}

## Context
{context if context else "(No additional context)"}

## Instructions
Decide which tool (if any) would help answer this query.
If you can answer directly from the context, no tool is needed.
If you need more information, select the most appropriate tool.

Your decision:"""
        
        return prompt
    
    def build_reflection_prompt(
        self,
        query: str,
        response: str,
        observations: List[str],
    ) -> str:
        """
        Build prompt for self-reflection/evaluation.
        
        Args:
            query: Original query
            response: Generated response
            observations: Tool observations
            
        Returns:
            Reflection prompt
        """
        obs_text = "\n".join([f"- {obs}" for obs in (observations or [])])
        
        return f"""## Reflection Task
Evaluate if this response adequately answers the user's question.

## Original Question
{query}

## Generated Response
{response}

## Information Gathered
{obs_text if obs_text else "(None)"}

## Evaluation Criteria
1. Does the response directly answer the question?
2. Is the information accurate based on the gathered data?
3. Are there any gaps or uncertainties?
4. Should any follow-up actions be suggested?

Rate the response quality from 0.0 to 1.0 and explain:"""
    
    def build_error_recovery_prompt(
        self,
        query: str,
        error: str,
        attempts: int,
        observations: List[str],
    ) -> str:
        """
        Build prompt for error recovery.
        
        Args:
            query: Original query
            error: Error message
            attempts: Number of recovery attempts
            observations: Previous observations
            
        Returns:
            Error recovery prompt
        """
        obs_text = "\n".join([f"- {obs}" for obs in (observations or [])])
        
        return f"""## Error Recovery
An error occurred while processing the user's request.

## Original Request
{query}

## Error
{error}

## Recovery Attempts
{attempts} of 3

## Previous Observations
{obs_text if obs_text else "(None)"}

## Instructions
1. Analyze what went wrong
2. Determine if we can still answer the user's question with available information
3. If yes, provide a response
4. If no, explain what happened and suggest alternatives

Your response:"""
    
    def _format_preferences(self, prefs: Dict[str, Any]) -> str:
        """Format user preferences section."""
        lines = ["## User Preferences"]
        for key, value in prefs.items():
            if isinstance(value, bool):
                value = "yes" if value else "no"
            lines.append(f"- **{key}**: {value}")
        return "\n".join(lines)
    
    def _format_plan_step(self, step: Dict, index: int) -> str:
        """Format a single plan step."""
        status = step.get("status", "pending")
        text = step.get("step", "")
        tool = step.get("tool", "")
        
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[✓]",
            "failed": "[✗]"
        }.get(status, "[ ]")
        
        result = f"{index}. {status_icon} {text}"
        if tool:
            result += f" (tool: {tool})"
        return result
