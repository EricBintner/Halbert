# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Prompt Builder - Assemble complete system prompts from components.

Part of Phase 40: Prompt Infrastructure
"""

from typing import Dict, List, Optional, Any, Literal
from pathlib import Path
import logging

from .loader import PromptLoader
from ..agents.blocks import content_to_text
from ..utils.reasoning import is_reasoning_model as _is_reasoning_model

logger = logging.getLogger(__name__)

TierType = Literal["guide", "specialist", "vision"]


class PromptBuilder:
    """Assemble complete system prompts from components."""
    
    # Component assembly order
    COMPONENT_ORDER = [
        "identity",
        "objectives", 
        "constraints",
        "output-format",
        "safety",
    ]
    
    def __init__(self, loader: PromptLoader):
        """
        Initialize the prompt builder.
        
        Args:
            loader: PromptLoader instance
        """
        self.loader = loader
        self._base_cache: Optional[str] = None
    
    def clear_cache(self):
        """Clear the prompt cache to force reload of components."""
        self._base_cache = None
        logger.info("Prompt cache cleared")
    
    def build_base_prompt(self, core_tools_only: bool = False) -> str:
        """
        Build the static base prompt.
        
        Args:
            core_tools_only: If True, only include core tools (smaller prompt)
        
        Returns:
            Assembled base prompt
        """
        # Use cache only for full tool set
        cache_key = "core" if core_tools_only else "full"
        if not core_tools_only and self._base_cache is not None:
            return self._base_cache
        
        components = self.loader.load_base_components()
        tools = self.loader.load_tools(core_only=core_tools_only)
        
        # Assemble in order
        parts: List[str] = []
        
        for component_name in self.COMPONENT_ORDER:
            content = components.get(component_name, "")
            if content.strip():
                parts.append(content.strip())
        
        # Add tools if present
        if tools.strip():
            parts.append(f"<tools>\n{tools.strip()}\n</tools>")
        
        result = "\n\n".join(parts)
        
        # Only cache full version
        if not core_tools_only:
            self._base_cache = result
        
        token_estimate = self.estimate_tokens(result)
        logger.info(f"Built base prompt ({cache_key}): ~{token_estimate} tokens")
        
        return result
    
    def build_prompt(
        self,
        tier: TierType = "specialist",
        system_context: Optional[str] = None,
        user_prefs: Optional[Dict[str, Any]] = None,
        project_context: Optional[str] = None,
        rag_results: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model_name: Optional[str] = None,
        personality_section: Optional[str] = None,
    ) -> str:
        """
        Build a complete prompt for a specific tier.
        
        Args:
            tier: Model tier (guide, specialist, vision)
            system_context: Formatted system context XML
            user_prefs: User preference dict
            project_context: Content from HALBERT.md or similar
            rag_results: RAG retrieval results
            conversation_history: Recent conversation turns
            model_name: Optional model name for model-specific overrides
            personality_section: Optional personality prompt section to inject
            
        Returns:
            Complete assembled prompt
        """
        parts: List[str] = []
        
        # 1. Base prompt (use core tools only for guide tier to reduce size)
        core_only = (tier == "guide")
        parts.append(self.build_base_prompt(core_tools_only=core_only))
        
        # 2. Model-specific overrides (if applicable)
        if model_name:
            model_overrides = self._get_model_overrides(model_name)
            if model_overrides:
                parts.append(model_overrides)
        
        # 3. Tier-specific additions
        tier_additions = self.loader.load_tier(tier)
        if tier_additions.strip():
            parts.append(tier_additions.strip())
        
        # 4. Personality section (if provided)
        if personality_section:
            parts.append(
                f"<personality>\n{personality_section}\n</personality>"
            )
        
        # 5. Dynamic context sections
        if system_context:
            parts.append(system_context)
        
        if user_prefs:
            prefs_xml = self._format_user_prefs(user_prefs)
            parts.append(prefs_xml)
        
        if project_context:
            parts.append(
                f"<project_context>\n{project_context.strip()}\n</project_context>"
            )
        
        if rag_results:
            rag_xml = self._format_rag_results(rag_results)
            parts.append(rag_xml)
        
        if conversation_history:
            conv_xml = self._format_conversation(conversation_history)
            if conv_xml:
                parts.append(conv_xml)
        
        prompt = "\n\n".join(parts)
        
        token_estimate = self.estimate_tokens(prompt)
        logger.debug(f"Built {tier} prompt: ~{token_estimate} tokens")
        
        return prompt
    
    def build_minimal_prompt(self) -> str:
        """
        Build a minimal prompt for simple/fast queries.
        Uses guide tier with minimal context.
        
        Returns:
            Minimal prompt
        """
        return self.build_prompt(tier="guide")
    
    def _format_user_prefs(self, prefs: Dict[str, Any]) -> str:
        """Format user preferences as XML."""
        lines = ["<user_preferences>"]
        
        for key, value in prefs.items():
            # Convert Python types to string
            if isinstance(value, bool):
                value = "true" if value else "false"
            lines.append(f"  <{key}>{value}</{key}>")
        
        lines.append("</user_preferences>")
        return "\n".join(lines)
    
    def _format_rag_results(self, results: List[Dict[str, Any]]) -> str:
        """Format RAG results as XML with citations."""
        if not results:
            return ""
        
        lines = ["<rag_results>"]
        
        for i, result in enumerate(results, 1):
            source = result.get("source", "unknown")
            relevance = result.get("relevance", 0.0)
            content = result.get("content", "").strip()
            
            lines.append(
                f'  <result index="{i}" source="{source}" relevance="{relevance:.2f}">'
            )
            # Indent content
            for line in content.split("\n"):
                lines.append(f"    {line}")
            lines.append("  </result>")
        
        lines.append("</rag_results>")
        return "\n".join(lines)
    
    def _format_conversation(
        self, 
        history: List[Dict[str, str]],
        max_turns: int = 5,
        max_chars_per_turn: int = 500,
    ) -> str:
        """
        Format conversation history for context.
        
        Args:
            history: List of {role, content} dicts
            max_turns: Maximum turns to include
            max_chars_per_turn: Truncate long messages
            
        Returns:
            Formatted conversation XML
        """
        if not history:
            return ""
        
        # Take last N turns
        recent = history[-max_turns:]
        
        lines = ["<conversation_context>"]
        
        for turn in recent:
            role = turn.get("role", "user")
            # content may be a string (legacy) or a list of content blocks (A1)
            content = content_to_text(turn.get("content", ""))

            # Truncate if needed
            if len(content) > max_chars_per_turn:
                content = content[:max_chars_per_turn] + "..."
            
            # Escape XML special chars
            content = (
                content
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            
            lines.append(f'  <turn role="{role}">{content}</turn>')
        
        lines.append("</conversation_context>")
        return "\n".join(lines)
    
    def _get_model_overrides(self, model_name: str) -> str:
        """
        Get model-specific prompt overrides based on model name.
        
        Args:
            model_name: Name of the model as configured
            
        Returns:
            Model-specific override rules as string, or empty string
        """
        model_lower = model_name.lower()
        
        # Detect model category
        is_small_model = any(size in model_lower for size in [":7b", ":8b", ":9b", ":14b", "7b-", "8b-"])
        is_reasoning_model = _is_reasoning_model(model_name)
        
        overrides = []
        
        if is_small_model:
            # Stronger constraints for smaller models
            overrides.append("""<model_constraints type="small_model">
  <critical>STOP. You CANNOT run commands. You can ONLY suggest them.</critical>
  <critical>NEVER show example output. NEVER say "The output might look like..."</critical>
  <critical>ONE command at a time. Show command, say "Run this to check.", then STOP.</critical>
  <critical>No placeholders like [path] or [name]. Commands must be copy-paste ready.</critical>
</model_constraints>""")
            logger.debug(f"Applied small-model overrides for {model_name}")
        
        if is_reasoning_model:
            # Thinking block handling for reasoning models
            overrides.append("""<model_constraints type="reasoning_model">
  <instruction>You may use internal reasoning. Your thinking will be shown separately.</instruction>
  <instruction>After reasoning, provide a clear, concise response.</instruction>
  <instruction>Even after extensive reasoning, suggest ONE command at a time.</instruction>
</model_constraints>""")
            logger.debug(f"Applied reasoning-model overrides for {model_name}")
        
        return "\n\n".join(overrides)
    
    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate.
        
        Rule of thumb: 1 token ≈ 4 characters for English text.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        return len(text) // 4
    
    def clear_cache(self) -> None:
        """Clear cached base prompt."""
        self._base_cache = None
        self.loader.clear_cache()
        logger.debug("Prompt builder cache cleared")
