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

    # Layer 1: Identity — first_person voice (default)
    LAYER_1_IDENTITY_FIRST_PERSON = """You are Halbert, a helpful AI assistant for Linux system administration.
You help users understand and manage their systems through natural conversation.
You are knowledgeable, precise, and safety-conscious.
You speak in first person: "I", "my", "me". You ARE the machine."""

    # Layer 1: Identity — the_computer voice
    LAYER_1_IDENTITY_THE_COMPUTER = """You are Halbert, a helpful AI assistant for Linux system administration.
You help users understand and manage their systems through natural conversation.
You are knowledgeable, precise, and safety-conscious.
You refer to the system in third person: "this system", "the computer", "it". You are an assistant that monitors the machine."""

    # Layer 1: Identity — hybrid voice
    LAYER_1_IDENTITY_HYBRID = """You are Halbert, a helpful AI assistant for Linux system administration.
You help users understand and manage their systems through natural conversation.
You are knowledgeable, precise, and safety-conscious.
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

    def _get_identity(self) -> str:
        """Get the identity layer for the current voice."""
        if self.voice == "the_computer":
            return self.LAYER_1_IDENTITY_THE_COMPUTER
        elif self.voice == "hybrid":
            return self.LAYER_1_IDENTITY_HYBRID
        return self.LAYER_1_IDENTITY_FIRST_PERSON
    
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
    ) -> str:
        """
        Build prompt for PLANNING state.
        
        Args:
            query: User's query
            context: Assembled context string
            plan: Current plan steps
            observations: Previous observations
            
        Returns:
            Planning prompt string
        """
        parts = [
            "## Current Task",
            f"User request: {query}",
        ]
        
        if context:
            parts.extend(["", "## Available Context", context])
        
        if observations:
            parts.extend([
                "",
                "## Previous Observations",
                "\n".join(f"- {obs}" for obs in observations)
            ])
        
        parts.extend([
            "",
            "## Instructions",
            "1. Analyze what information is needed to answer this request",
            "2. Check if the available context already answers the question",
            "3. If more information is needed, use the appropriate tools",
            "4. Create a concise plan (maximum 5 steps)",
            "5. Execute one step at a time",
        ])
        
        if plan:
            parts.extend(["", "## Current Plan"])
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
        
        return "\n".join(parts)
    
    def build_response_prompt(
        self,
        query: str,
        context: List[Dict],
        observations: List[str],
        confidence: float = None,
    ) -> str:
        """
        Build prompt for RESPONDING state.
        
        Args:
            query: Original user query
            context: Retrieved context items
            observations: Tool observations
            confidence: CRAG confidence score
            
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

        prompt = f"""## Task
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
