"""
Context Handoff Engine for Multi-Model Routing (Phase 5 M2).

Manages state transfer between orchestrator and specialist models:
- Conversation history serialization
- Intelligent context summarization
- Cross-tokenizer compatibility
- RAG context injection
- Quality preservation (<10% target loss)
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from datetime import datetime

from ..obs.logging import get_logger

logger = get_logger("halbert")


class HandoffStrategy(str, Enum):
    """Context handoff strategies."""
    FULL = "full"              # Pass all messages (large context)
    SUMMARIZED = "summarized"  # Summarize older messages
    MINIMAL = "minimal"        # Only essential context
    RAG_ENHANCED = "rag_enhanced"  # Include RAG context


class MessageRole(str, Enum):
    """Message roles in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """
    Single message in conversation history.
    
    Standardized format compatible with OpenAI, Ollama, Anthropic, etc.
    """
    role: MessageRole
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """Create from dictionary."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=data.get("timestamp"),
            metadata=data.get("metadata")
        )


@dataclass
class ConversationContext:
    """
    Complete conversation context for handoff.
    
    Contains all information needed to transfer state between models.
    """
    messages: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None
    task_description: Optional[str] = None
    rag_context: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: MessageRole, content: str, **kwargs):
        """Add a message to the conversation."""
        self.messages.append(Message(
            role=role,
            content=content,
            timestamp=datetime.utcnow().isoformat(),
            metadata=kwargs
        ))
    
    def get_token_estimate(self) -> int:
        """
        Estimate token count (rough approximation).
        
        Uses ~4 chars per token heuristic.
        """
        total_chars = 0
        
        if self.system_prompt:
            total_chars += len(self.system_prompt)
        
        for msg in self.messages:
            total_chars += len(msg.content)
        
        for rag in self.rag_context:
            total_chars += len(rag)
        
        return total_chars // 4  # Rough estimate
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "messages": [msg.to_dict() for msg in self.messages],
            "system_prompt": self.system_prompt,
            "task_description": self.task_description,
            "rag_context": self.rag_context,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConversationContext:
        """Deserialize from dictionary."""
        return cls(
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            system_prompt=data.get("system_prompt"),
            task_description=data.get("task_description"),
            rag_context=data.get("rag_context", []),
            metadata=data.get("metadata", {})
        )


class ContextHandoffEngine:
    """
    Manages context handoff between models.
    
    Phase 5 M2: Core handoff functionality
    Phase 5 M5: Quality monitoring and optimization
    
    Usage:
        engine = ContextHandoffEngine()
        
        # Build context
        context = ConversationContext()
        context.add_message(MessageRole.USER, "Write a backup script")
        context.add_message(MessageRole.ASSISTANT, "I'll help...")
        
        # Prepare for specialist
        handoff_context = engine.prepare_handoff(
            context=context,
            target_model="deepseek-coder:33b",
            max_tokens=4096,
            strategy=HandoffStrategy.SUMMARIZED
        )
        
        # Generate with specialist using handoff_context
    """
    
    def __init__(self, default_strategy: HandoffStrategy = HandoffStrategy.SUMMARIZED):
        """
        Initialize context handoff engine.
        
        Args:
            default_strategy: Default handoff strategy
        """
        self.default_strategy = default_strategy
        
        logger.info("ContextHandoffEngine initialized", extra={
            "default_strategy": default_strategy.value
        })
    
    def prepare_handoff(
        self,
        context: ConversationContext,
        target_model: str,
        max_tokens: int = 4096,
        strategy: Optional[HandoffStrategy] = None
    ) -> ConversationContext:
        """
        Prepare context for handoff to specialist model.
        
        Args:
            context: Current conversation context
            target_model: Target model identifier
            max_tokens: Maximum context tokens for target
            strategy: Handoff strategy (uses default if None)
        
        Returns:
            Prepared context ready for specialist
        """
        strategy = strategy or self.default_strategy
        
        logger.info("Preparing context handoff", extra={
            "target_model": target_model,
            "max_tokens": max_tokens,
            "strategy": strategy.value,
            "input_messages": len(context.messages),
            "input_tokens_est": context.get_token_estimate()
        })
        
        if strategy == HandoffStrategy.FULL:
            return self._prepare_full_handoff(context, max_tokens)
        elif strategy == HandoffStrategy.SUMMARIZED:
            return self._prepare_summarized_handoff(context, max_tokens)
        elif strategy == HandoffStrategy.MINIMAL:
            return self._prepare_minimal_handoff(context, max_tokens)
        elif strategy == HandoffStrategy.RAG_ENHANCED:
            return self._prepare_rag_enhanced_handoff(context, max_tokens)
        else:
            logger.warning(f"Unknown strategy: {strategy}, using full")
            return self._prepare_full_handoff(context, max_tokens)
    
    def _prepare_full_handoff(
        self,
        context: ConversationContext,
        max_tokens: int
    ) -> ConversationContext:
        """
        Full context handoff (no compression).
        
        Best for: Short conversations, large context windows
        """
        # Check if context fits
        token_estimate = context.get_token_estimate()
        
        if token_estimate > max_tokens:
            logger.warning(
                "Full context exceeds max tokens, truncating",
                extra={
                    "estimated": token_estimate,
                    "max": max_tokens,
                    "messages": len(context.messages)
                }
            )
            return self._truncate_context(context, max_tokens)
        
        logger.info("Full context handoff prepared", extra={
            "messages": len(context.messages),
            "tokens_est": token_estimate
        })
        
        return context
    
    def _prepare_summarized_handoff(
        self,
        context: ConversationContext,
        max_tokens: int
    ) -> ConversationContext:
        """
        Summarized context handoff (intelligent compression).
        
        Best for: Long conversations, medium context windows
        Strategy:
        - Keep recent N messages fully
        - Summarize older messages
        - Always preserve system prompt and task description
        """
        # Reserve tokens
        reserved_for_system = 500
        reserved_for_task = 200
        reserved_for_rag = 1000
        available_for_messages = max_tokens - reserved_for_system - reserved_for_task - reserved_for_rag
        
        # Create new context
        new_context = ConversationContext(
            system_prompt=context.system_prompt,
            task_description=context.task_description,
            rag_context=context.rag_context[:3],  # Keep top 3 RAG entries
            metadata=context.metadata.copy()
        )
        
        # Always keep last N messages (recency bias)
        keep_recent = 5
        recent_messages = context.messages[-keep_recent:] if len(context.messages) > keep_recent else context.messages
        
        # If we have older messages, summarize them
        if len(context.messages) > keep_recent:
            older_messages = context.messages[:-keep_recent]
            summary = self._summarize_messages(older_messages)
            
            # Add summary as system message
            new_context.add_message(
                MessageRole.SYSTEM,
                f"Previous conversation summary:\n{summary}",
                summarized=True,
                original_count=len(older_messages)
            )
        
        # Add recent messages
        for msg in recent_messages:
            new_context.messages.append(msg)
        
        logger.info("Summarized context handoff prepared", extra={
            "original_messages": len(context.messages),
            "kept_recent": len(recent_messages),
            "summarized_count": len(context.messages) - len(recent_messages),
            "tokens_est": new_context.get_token_estimate()
        })
        
        return new_context
    
    def _prepare_minimal_handoff(
        self,
        context: ConversationContext,
        max_tokens: int
    ) -> ConversationContext:
        """
        Minimal context handoff (essential only).
        
        Best for: Very long conversations, small context windows
        Strategy:
        - Task description only
        - Last user message
        - No history
        """
        new_context = ConversationContext(
            system_prompt=context.system_prompt,
            task_description=context.task_description,
            metadata=context.metadata.copy()
        )
        
        # Keep only the last user message
        for msg in reversed(context.messages):
            if msg.role == MessageRole.USER:
                new_context.messages.append(msg)
                break
        
        logger.info("Minimal context handoff prepared", extra={
            "original_messages": len(context.messages),
            "kept_messages": len(new_context.messages),
            "tokens_est": new_context.get_token_estimate()
        })
        
        return new_context
    
    def _prepare_rag_enhanced_handoff(
        self,
        context: ConversationContext,
        max_tokens: int
    ) -> ConversationContext:
        """
        RAG-enhanced context handoff.
        
        Best for: Technical queries requiring system knowledge
        Strategy:
        - Summarize conversation
        - Prioritize RAG context
        - Include relevant system documentation
        """
        # Reserve more tokens for RAG
        reserved_for_rag = 2000
        available_for_messages = max_tokens - reserved_for_rag - 500
        
        new_context = ConversationContext(
            system_prompt=context.system_prompt,
            task_description=context.task_description,
            rag_context=context.rag_context,  # Keep all RAG context
            metadata=context.metadata.copy()
        )
        
        # Summarize and keep recent
        if len(context.messages) > 3:
            # Summarize older
            older = context.messages[:-3]
            summary = self._summarize_messages(older)
            new_context.add_message(
                MessageRole.SYSTEM,
                f"Context:\n{summary}",
                summarized=True
            )
            # Keep recent
            for msg in context.messages[-3:]:
                new_context.messages.append(msg)
        else:
            new_context.messages = context.messages.copy()
        
        logger.info("RAG-enhanced context handoff prepared", extra={
            "rag_entries": len(new_context.rag_context),
            "messages": len(new_context.messages),
            "tokens_est": new_context.get_token_estimate()
        })
        
        return new_context
    
    def _summarize_messages(self, messages: List[Message]) -> str:
        """
        Summarize a list of messages.
        
        Phase 5 M2: Simple concatenation with truncation
        Phase 5 M5: Use LLM for intelligent summarization
        """
        if not messages:
            return "No previous messages."
        
        # Simple strategy: extract key points
        summary_parts = []
        
        for msg in messages:
            # Extract first sentence or 100 chars
            content = msg.content.strip()
            first_line = content.split('\n')[0][:100]
            summary_parts.append(f"- {msg.role.value}: {first_line}")
        
        summary = "\n".join(summary_parts)
        
        # Truncate if too long
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        return summary
    
    def _truncate_context(
        self,
        context: ConversationContext,
        max_tokens: int
    ) -> ConversationContext:
        """Truncate context to fit within max tokens."""
        new_context = ConversationContext(
            system_prompt=context.system_prompt,
            task_description=context.task_description,
            metadata=context.metadata.copy()
        )
        
        # Add messages from the end until we hit limit
        accumulated_tokens = 0
        for msg in reversed(context.messages):
            msg_tokens = len(msg.content) // 4
            if accumulated_tokens + msg_tokens > max_tokens:
                break
            new_context.messages.insert(0, msg)
            accumulated_tokens += msg_tokens
        
        logger.warning("Context truncated", extra={
            "original_messages": len(context.messages),
            "kept_messages": len(new_context.messages),
            "tokens_est": accumulated_tokens
        })
        
        return new_context
    
    def format_for_ollama(self, context: ConversationContext) -> Dict[str, Any]:
        """
        Format context for Ollama API.
        
        Ollama uses: {"model": "...", "messages": [...], "stream": false}
        """
        messages = []
        
        # System prompt
        if context.system_prompt:
            messages.append({
                "role": "system",
                "content": context.system_prompt
            })
        
        # Task description as system message
        if context.task_description:
            messages.append({
                "role": "system",
                "content": f"Task: {context.task_description}"
            })
        
        # RAG context as system message
        if context.rag_context:
            rag_text = "\n\n".join(context.rag_context)
            messages.append({
                "role": "system",
                "content": f"Relevant information:\n{rag_text}"
            })
        
        # Conversation messages
        for msg in context.messages:
            messages.append({
                "role": msg.role.value,
                "content": msg.content
            })
        
        return {"messages": messages}
    
    def format_for_openai(self, context: ConversationContext) -> Dict[str, Any]:
        """
        Format context for OpenAI API.
        
        OpenAI uses same format as Ollama.
        """
        return self.format_for_ollama(context)
    
    def estimate_quality_loss(
        self,
        original: ConversationContext,
        compressed: ConversationContext
    ) -> float:
        """
        Estimate information loss from compression.
        
        Returns: Estimated quality loss (0.0 - 1.0)
        Target: <0.10 (less than 10% loss)
        
        Phase 5 M2: Simple token-based estimate
        Phase 5 M5: ML-based quality scoring
        """
        orig_tokens = original.get_token_estimate()
        comp_tokens = compressed.get_token_estimate()
        
        if orig_tokens == 0:
            return 0.0
        
        # Simple ratio-based estimate
        token_retention = comp_tokens / orig_tokens
        loss = 1.0 - token_retention
        
        # Cap at 1.0
        return min(loss, 1.0)
