# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Conversation Persistence

Stores and retrieves conversation history for agent sessions.
"""

from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

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


class ConversationStore:
    """
    Persists conversations to disk.
    
    Simple JSON-based storage for development.
    Can be replaced with database backend for production.
    """
    
    def __init__(self, storage_path: str = None):
        """
        Initialize conversation store.
        
        Args:
            storage_path: Directory to store conversations
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Default to ~/.halbert/conversations
            self.storage_path = Path.home() / ".halbert" / "conversations"
        
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self._cache: Dict[str, Conversation] = {}
    
    def get(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        # Check cache first
        if conversation_id in self._cache:
            return self._cache[conversation_id]
        
        # Try to load from disk
        file_path = self.storage_path / f"{conversation_id}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                conv = Conversation.from_dict(data)
                self._cache[conversation_id] = conv
                return conv
            except Exception as e:
                logger.error(f"Error loading conversation {conversation_id}: {e}")
        
        return None
    
    def create(self, conversation_id: str, user_id: str = None) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(
            conversation_id=conversation_id,
            user_id=user_id
        )
        self._cache[conversation_id] = conv
        self._save(conv)
        return conv
    
    def get_or_create(self, conversation_id: str, user_id: str = None) -> Conversation:
        """Get existing or create new conversation."""
        conv = self.get(conversation_id)
        if conv is None:
            conv = self.create(conversation_id, user_id)
        return conv
    
    def save(self, conversation: Conversation):
        """Save a conversation."""
        self._cache[conversation.conversation_id] = conversation
        self._save(conversation)
    
    def _save(self, conversation: Conversation):
        """Save conversation to disk."""
        file_path = self.storage_path / f"{conversation.conversation_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(conversation.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        if conversation_id in self._cache:
            del self._cache[conversation_id]
        
        file_path = self.storage_path / f"{conversation_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"Error deleting conversation: {e}")
        
        return False
    
    def list_conversations(
        self,
        user_id: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """List conversations, optionally filtered by user."""
        conversations = []
        
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if user_id and data.get("user_id") != user_id:
                    continue
                
                conversations.append({
                    "conversation_id": data.get("conversation_id"),
                    "title": data.get("title"),
                    "user_id": data.get("user_id"),
                    "message_count": len(data.get("messages", [])),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
            except Exception as e:
                logger.warning(f"Error reading {file_path}: {e}")
        
        # Sort by updated_at descending
        conversations.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        
        return conversations[offset:offset + limit]
    
    def search(self, query: str, user_id: str = None, limit: int = 20) -> List[Dict]:
        """Search conversations by content."""
        results = []
        query_lower = query.lower()
        
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if user_id and data.get("user_id") != user_id:
                    continue
                
                # Search in title and messages
                if data.get("title") and query_lower in data["title"].lower():
                    results.append(data.get("conversation_id"))
                    continue
                
                for msg in data.get("messages", []):
                    if query_lower in msg.get("content", "").lower():
                        results.append(data.get("conversation_id"))
                        break
                        
            except Exception:
                pass
        
        return results[:limit]


@dataclass
class Session:
    """
    A work session spanning multiple conversations.
    
    Used for long-running tasks that may span multiple sessions.
    """
    session_id: str
    user_id: Optional[str] = None
    title: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    summary: Optional[str] = None
    pending_tasks: List[str] = field(default_factory=list)
    context_files: List[str] = field(default_factory=list)
    conversation_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_conversation(self, conversation_id: str):
        """Add a conversation to this session."""
        if conversation_id not in self.conversation_ids:
            self.conversation_ids.append(conversation_id)
        self.last_active = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "started_at": self.started_at,
            "last_active": self.last_active,
            "summary": self.summary,
            "pending_tasks": self.pending_tasks,
            "context_files": self.context_files,
            "conversation_ids": self.conversation_ids,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Session':
        return cls(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id"),
            title=data.get("title"),
            started_at=data.get("started_at", time.time()),
            last_active=data.get("last_active", time.time()),
            summary=data.get("summary"),
            pending_tasks=data.get("pending_tasks", []),
            context_files=data.get("context_files", []),
            conversation_ids=data.get("conversation_ids", []),
            metadata=data.get("metadata", {})
        )


class SessionStore:
    """
    Persists sessions to disk.
    
    Sessions are stored in ~/.halbert/sessions/
    """
    
    def __init__(self, storage_path: str = None):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path.home() / ".halbert" / "sessions"
        
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Session] = {}
    
    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        if session_id in self._cache:
            return self._cache[session_id]
        
        file_path = self.storage_path / f"{session_id}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self._cache[session_id] = session
                return session
            except Exception as e:
                logger.error(f"Error loading session {session_id}: {e}")
        
        return None
    
    def create(self, session_id: str, user_id: str = None, title: str = None) -> Session:
        """Create a new session."""
        session = Session(
            session_id=session_id,
            user_id=user_id,
            title=title
        )
        self._cache[session_id] = session
        self._save(session)
        return session
    
    def get_or_create(self, session_id: str, user_id: str = None, title: str = None) -> Session:
        """Get existing or create new session."""
        session = self.get(session_id)
        if session is None:
            session = self.create(session_id, user_id, title)
        return session
    
    def save(self, session: Session):
        """Save a session."""
        self._cache[session.session_id] = session
        self._save(session)
    
    def _save(self, session: Session):
        """Save session to disk."""
        file_path = self.storage_path / f"{session.session_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._cache:
            del self._cache[session_id]
        
        file_path = self.storage_path / f"{session.session_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"Error deleting session: {e}")
        
        return False
    
    def list_sessions(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """List sessions, optionally filtered by user."""
        sessions = []
        
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if user_id and data.get("user_id") != user_id:
                    continue
                
                sessions.append({
                    "session_id": data.get("session_id"),
                    "title": data.get("title"),
                    "user_id": data.get("user_id"),
                    "started_at": data.get("started_at"),
                    "last_active": data.get("last_active"),
                    "conversation_count": len(data.get("conversation_ids", [])),
                    "pending_tasks": len(data.get("pending_tasks", []))
                })
            except Exception as e:
                logger.warning(f"Error reading {file_path}: {e}")
        
        # Sort by last_active descending
        sessions.sort(key=lambda x: x.get("last_active", 0), reverse=True)
        
        return sessions[:limit]


# Global instances
_session_store: Optional[SessionStore] = None
_conversation_store: Optional[ConversationStore] = None


def get_session_store() -> SessionStore:
    """Get global session store."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def get_conversation_store() -> ConversationStore:
    """Get global conversation store."""
    global _conversation_store
    if _conversation_store is None:
        _conversation_store = ConversationStore()
    return _conversation_store
