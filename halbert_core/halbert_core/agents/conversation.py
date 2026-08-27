# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Conversation records

``Message`` and ``Conversation`` are the in-memory records used by the
SQLite thread store (``conversation_sqlite.py``) and by the state machine's
conversation history. The JSON-backed ``ConversationStore`` / ``SessionStore``
that used to live here were deleted in Plan A (spec §8): the SQLite store is
the store of record and ``agents/threads.py`` is the only writer.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger('halbert.agents.conversation')


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # user, assistant, system, tool
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Message':
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {})
        )


@dataclass
class Conversation:
    """A conversation with message history."""
    conversation_id: str
    user_id: Optional[str] = None
    title: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        """Add a message to the conversation."""
        msg = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = time.time()
        
        # Auto-generate title from first user message
        if self.title is None and role == "user" and content:
            self.title = content[:50] + ("..." if len(content) > 50 else "")
    
    def get_history(self, max_messages: int = None) -> List[Dict]:
        """Get message history as list of dicts."""
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        return [m.to_dict() for m in messages]
    
    def get_context_window(self, max_tokens: int = 4000) -> List[Dict]:
        """
        Get recent messages that fit within token budget.
        Uses summarization for older messages if needed.
        
        Strategy:
        - Keep recent messages fully
        - Summarize older messages if total exceeds budget
        """
        # Estimate ~4 chars per token
        char_budget = max_tokens * 4
        
        # Reserve some chars for summary if needed
        summary_reserve = 500
        
        result = []
        char_count = 0
        
        # Always keep the last few messages (recency bias)
        keep_recent = min(5, len(self.messages))
        recent_messages = self.messages[-keep_recent:] if self.messages else []
        
        # Check if we have older messages
        older_messages = self.messages[:-keep_recent] if len(self.messages) > keep_recent else []
        
        # If older messages exist, try to include some with summary
        if older_messages:
            # First, try to fit recent + some older
            temp_result = []
            temp_chars = 0
            
            # Add recent messages
            for msg in recent_messages:
                msg_chars = len(msg.content) + 20  # overhead
                temp_result.append({"role": msg.role, "content": msg.content})
                temp_chars += msg_chars
            
            # Add as many older messages as fit (from most recent older)
            for msg in reversed(older_messages):
                msg_chars = len(msg.content) + 20
                if temp_chars + msg_chars + summary_reserve > char_budget:
                    break
                temp_result.insert(0, {"role": msg.role, "content": msg.content})
                temp_chars += msg_chars
            
            # If we couldn't include all older messages, summarize the rest
            included_older_count = len(temp_result) - len(recent_messages)
            # ``[:-0]`` is ``[:0]``, so when nothing older fit -- the usual case
            # once the budget is tight -- this dropped every older turn without
            # leaving the summary that is supposed to stand in for them.
            if included_older_count:
                remaining_older = older_messages[:-included_older_count]
            else:
                remaining_older = older_messages
            
            if remaining_older:
                # The summary is the only trace left of the turns being
                # dropped. Withholding it because the recent turns already
                # overflow -- which is exactly when turns get dropped -- lost
                # them silently; the caller trims to its own ceiling instead.
                summary = self._summarize_messages(remaining_older)
                result.append({"role": "system", "content": f"Previous conversation summary:\n{summary}"})
                char_count += len(summary) + 20
            
            # Add the included messages
            result.extend(temp_result)
            char_count += temp_chars
        else:
            # No older messages, just take recent
            for msg in recent_messages:
                msg_chars = len(msg.content) + 20
                if char_count + msg_chars > char_budget:
                    break
                result.append({"role": msg.role, "content": msg.content})
                char_count += msg_chars
        
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Conversation':
        """Create Conversation from dictionary."""
        conv = cls(
            conversation_id=data.get("conversation_id", ""),
            user_id=data.get("user_id"),
            title=data.get("title"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=data.get("metadata", {})
        )
        conv.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return conv
    
    def _summarize_messages(self, messages: List[Message]) -> str:
        """
        Summarize a list of messages using simple extraction.
        
        Returns a condensed summary of the conversation history.
        """
        if not messages:
            return "No previous messages."
        
        summary_parts = []
        
        for msg in messages:
            # Extract first line or first 100 characters
            content = msg.content.strip()
            if '\n' in content:
                first_part = content.split('\n')[0]
            else:
                first_part = content[:100]
            
            if len(first_part) < len(content):
                first_part += "..."
            
            summary_parts.append(f"- {msg.role}: {first_part}")
        
        summary = "\n".join(summary_parts)
        
        # Truncate if too long (keep under 500 chars for summary)
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        return summary
