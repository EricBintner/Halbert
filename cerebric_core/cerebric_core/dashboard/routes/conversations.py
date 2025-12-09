"""
Conversation management API routes.

Provides endpoints for creating, listing, updating, and deleting chat conversations.
Each conversation stores its messages and can be named by the user.
"""

from __future__ import annotations
import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger('cerebric.dashboard.routes.conversations')

router = APIRouter() if FASTAPI_AVAILABLE else None

# Storage directory
CONVERSATIONS_DIR = Path.home() / '.config' / 'cerebric' / 'conversations'
PREFERENCES_PATH = Path.home() / '.config' / 'cerebric' / 'preferences.yml'


def get_ai_name() -> str:
    """Get the AI name from preferences with fallback chain.
    
    Priority: ai_name from preferences > hostname > "Cerebric"
    """
    import socket
    import yaml
    
    # Default to hostname or app name
    try:
        default_name = socket.gethostname()
    except:
        default_name = 'Cerebric'
    
    try:
        if PREFERENCES_PATH.exists():
            with open(PREFERENCES_PATH, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            return prefs.get('ai_name') or default_name
    except:
        pass
    
    return default_name


class Message(BaseModel):
    """A single message in a conversation."""
    id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: str
    mentions: List[str] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)


class Conversation(BaseModel):
    """A conversation with messages."""
    id: str
    name: str
    created_at: str
    updated_at: str
    persona: str = "guide"
    messages: List[Message] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    """Summary for listing conversations (without full messages)."""
    id: str
    name: str
    created_at: str
    updated_at: str
    persona: str
    message_count: int
    preview: str  # First ~50 chars of last message


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    name: Optional[str] = None
    persona: str = "guide"


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation (rename)."""
    name: str


class AddMessageRequest(BaseModel):
    """Request to add a message to a conversation."""
    role: str
    content: str
    mentions: List[str] = Field(default_factory=list)


def ensure_storage_dir():
    """Ensure the conversations storage directory exists."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> Path:
    """Get the file path for a conversation."""
    return CONVERSATIONS_DIR / f"{conversation_id}.json"


def load_conversation(conversation_id: str) -> Optional[Conversation]:
    """Load a conversation from disk."""
    path = get_conversation_path(conversation_id)
    if not path.exists():
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return Conversation(**data)
    except Exception as e:
        logger.error(f"Failed to load conversation {conversation_id}: {e}")
        return None


def save_conversation(conversation: Conversation):
    """Save a conversation to disk."""
    ensure_storage_dir()
    path = get_conversation_path(conversation.id)
    try:
        with open(path, 'w') as f:
            json.dump(conversation.model_dump(), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save conversation {conversation.id}: {e}")
        raise


def list_all_conversations() -> List[ConversationSummary]:
    """List all conversations with summaries."""
    ensure_storage_dir()
    summaries = []
    
    for path in CONVERSATIONS_DIR.glob("*.json"):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            messages = data.get('messages', [])
            last_message = messages[-1] if messages else None
            preview = ""
            if last_message:
                preview = last_message.get('content', '')[:50]
                if len(last_message.get('content', '')) > 50:
                    preview += "..."
            
            summaries.append(ConversationSummary(
                id=data['id'],
                name=data['name'],
                created_at=data['created_at'],
                updated_at=data['updated_at'],
                persona=data.get('persona', 'guide'),
                message_count=len(messages),
                preview=preview,
            ))
        except Exception as e:
            logger.error(f"Failed to load conversation summary from {path}: {e}")
            continue
    
    # Sort by updated_at descending (most recent first)
    summaries.sort(key=lambda x: x.updated_at, reverse=True)
    return summaries


def generate_conversation_name() -> str:
    """Generate a default conversation name based on timestamp."""
    now = datetime.now()
    return now.strftime("Chat %b %d, %I:%M %p")


if FASTAPI_AVAILABLE:
    
    @router.get("", response_model=List[ConversationSummary])
    async def list_conversations():
        """List all conversations."""
        return list_all_conversations()
    
    
    @router.post("", response_model=Conversation)
    async def create_conversation(request: CreateConversationRequest):
        """Create a new conversation."""
        now = datetime.now().isoformat()
        
        ai_name = get_ai_name()
        conversation = Conversation(
            id=str(uuid.uuid4()),
            name=request.name or generate_conversation_name(),
            created_at=now,
            updated_at=now,
            persona=request.persona,
            messages=[
                Message(
                    id=str(uuid.uuid4()),
                    role="assistant",
                    content=f"Hi! I'm {ai_name}, your system assistant. Ask me about backups, services, or use @mentions for specific items.",
                    timestamp=now,
                )
            ],
        )
        
        save_conversation(conversation)
        logger.info(f"Created conversation: {conversation.id} ({conversation.name})")
        return conversation
    
    
    @router.get("/{conversation_id}", response_model=Conversation)
    async def get_conversation(conversation_id: str):
        """Get a conversation with all messages."""
        conversation = load_conversation(conversation_id)
        if not conversation:
            raise HTTPException(404, f"Conversation not found: {conversation_id}")
        return conversation
    
    
    @router.patch("/{conversation_id}", response_model=Conversation)
    async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
        """Update a conversation (rename)."""
        conversation = load_conversation(conversation_id)
        if not conversation:
            raise HTTPException(404, f"Conversation not found: {conversation_id}")
        
        conversation.name = request.name
        conversation.updated_at = datetime.now().isoformat()
        save_conversation(conversation)
        
        logger.info(f"Renamed conversation {conversation_id} to: {request.name}")
        return conversation
    
    
    @router.delete("/{conversation_id}")
    async def delete_conversation(conversation_id: str):
        """Delete a conversation."""
        path = get_conversation_path(conversation_id)
        if not path.exists():
            raise HTTPException(404, f"Conversation not found: {conversation_id}")
        
        try:
            path.unlink()
            logger.info(f"Deleted conversation: {conversation_id}")
            return {"deleted": True, "id": conversation_id}
        except Exception as e:
            logger.error(f"Failed to delete conversation {conversation_id}: {e}")
            raise HTTPException(500, f"Failed to delete: {e}")
    
    
    @router.post("/{conversation_id}/messages", response_model=Message)
    async def add_message(conversation_id: str, request: AddMessageRequest):
        """Add a message to a conversation."""
        conversation = load_conversation(conversation_id)
        if not conversation:
            raise HTTPException(404, f"Conversation not found: {conversation_id}")
        
        message = Message(
            id=str(uuid.uuid4()),
            role=request.role,
            content=request.content,
            timestamp=datetime.now().isoformat(),
            mentions=request.mentions,
        )
        
        conversation.messages.append(message)
        conversation.updated_at = datetime.now().isoformat()
        save_conversation(conversation)
        
        return message
