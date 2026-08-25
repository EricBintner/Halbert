"""
Conversation Summarization for Long Chats

Compresses older conversation history to prevent context window saturation
and reduce format drift / repetition issues.

Hierarchical Memory Architecture:
- Level 0 (Raw):        Last 10 messages - full detail
- Level 1 (Detailed):   Messages 11-50 - detailed summary
- Level 2 (Compressed): Messages 51-200 - compressed summary
- Level 3 (Key Facts):  Messages 201-1000 - key facts only
- Level 4 (Core):       Messages 1000+ - system state essence

Ported from LinuxBrain Phase 72, adapted for sysadmin context.
"""

import logging
import re
import json
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

from ..agents.blocks import content_to_text

logger = logging.getLogger('halbert.conversation.summarization')

# Thresholds for when to summarize
MESSAGE_THRESHOLD = 10  # Start summarizing after this many message pairs
KEEP_RECENT = 6  # Keep this many recent messages as raw text

# Hierarchical compression thresholds
TIER_THRESHOLDS = {
    'raw': 10,        # Keep last 10 as raw
    'detailed': 50,   # Detailed summary for 11-50
    'compressed': 200,  # Compressed for 51-200
    'key_facts': 1000,  # Key facts for 201-1000
    'core': 5000,     # Core memory for 1000+
}


def should_summarize(messages: List[Dict]) -> bool:
    """
    Determine if conversation history should be summarized.

    Args:
        messages: List of message dicts with 'role' and 'content'

    Returns:
        True if summarization is recommended
    """
    # Count user/assistant message pairs (excluding system)
    conversation_messages = [m for m in messages if m.get('role') != 'system']
    return len(conversation_messages) > MESSAGE_THRESHOLD


def create_simple_summary(messages: List[Dict]) -> str:
    """
    Create a simple extractive summary without LLM call.

    Extracts key points from older messages to compress context.
    Adapted for sysadmin context: extracts commands, config changes,
    error messages, and resolutions instead of dialogue.
    """
    if not messages:
        return ""

    summary_parts = []

    for i, msg in enumerate(messages):
        role = msg.get('role', 'user')
        # content may be a string (legacy) or a list of content blocks (A1)
        content = content_to_text(msg.get('content', ''))[:200]  # Truncate long messages

        if role == 'user':
            # Extract key user inputs (first sentence or short version)
            first_sentence = content.split('.')[0].strip()
            if first_sentence:
                summary_parts.append(f"User: {first_sentence}")
        elif role == 'assistant':
            # Extract key sysadmin information (not action descriptions)
            # Look for commands, config changes, errors, resolutions
            commands = re.findall(r'`([^`]+)`', content)
            if commands:
                summary_parts.append(f"Cmd: {commands[0][:60]}")
            else:
                # Look for error/status patterns
                status = re.search(r'\b(failed|error|success|resolved|enabled|disabled|installed|configured)\b',
                                   content, re.IGNORECASE)
                if status:
                    # Get surrounding context
                    idx = status.start()
                    context_start = max(0, idx - 30)
                    context_end = min(len(content), idx + 50)
                    snippet = content[context_start:context_end].strip()
                    summary_parts.append(f"Status: {snippet}")
                else:
                    # Just take first sentence without asterisks
                    clean = re.sub(r'\*[^*]+\*', '', content).strip()
                    first_sentence = clean.split('.')[0].strip() if clean else ""
                    if first_sentence:
                        summary_parts.append(f"Assistant: {first_sentence}")

    return " | ".join(summary_parts[-8:])  # Keep last 8 key points


def compress_conversation_history(
    messages: List[Dict],
    keep_recent: int = KEEP_RECENT,
    summarize_older: bool = True
) -> Tuple[List[Dict], Optional[str]]:
    """
    Compress conversation history for long chats.

    Args:
        messages: Full list of messages
        keep_recent: Number of recent messages to keep as-is
        summarize_older: Whether to summarize older messages

    Returns:
        (compressed_messages, summary_text)
    """
    # Separate system message from conversation
    system_msgs = [m for m in messages if m.get('role') == 'system']
    conv_msgs = [m for m in messages if m.get('role') != 'system']

    if len(conv_msgs) <= keep_recent:
        return messages, None  # No compression needed

    # Split into old and recent
    old_msgs = conv_msgs[:-keep_recent]
    recent_msgs = conv_msgs[-keep_recent:]

    summary = None
    if summarize_older and old_msgs:
        summary = create_simple_summary(old_msgs)
        logger.info(f"Summarized {len(old_msgs)} older messages into {len(summary)} chars")

    # Rebuild messages: system + summary (as system) + recent
    compressed = system_msgs.copy()

    if summary:
        compressed.append({
            "role": "system",
            "content": f"[Earlier in this conversation: {summary}]"
        })

    compressed.extend(recent_msgs)

    return compressed, summary


def estimate_token_count(messages: List[Dict]) -> int:
    """
    Rough estimate of token count for messages.

    Rule of thumb: ~4 characters per token for English text.
    """
    total_chars = sum(len(content_to_text(m.get('content', ''))) for m in messages)
    return total_chars // 4


def get_compression_stats(
    original_messages: List[Dict],
    compressed_messages: List[Dict]
) -> Dict:
    """
    Get statistics about compression.
    """
    original_tokens = estimate_token_count(original_messages)
    compressed_tokens = estimate_token_count(compressed_messages)

    return {
        'original_messages': len(original_messages),
        'compressed_messages': len(compressed_messages),
        'original_tokens': original_tokens,
        'compressed_tokens': compressed_tokens,
        'reduction_percent': round((1 - compressed_tokens / max(1, original_tokens)) * 100, 1),
    }


# =============================================================================
# HIERARCHICAL MEMORY SYSTEM FOR EXTREME-LENGTH CONVERSATIONS
# =============================================================================

class ConversationMemory:
    """
    Hierarchical memory for extremely long conversations (50-5000+ messages).

    Maintains multiple tiers of compression:
    - Tier 0: Raw recent messages (last 10)
    - Tier 1: Detailed summaries (messages 11-50)
    - Tier 2: Compressed summaries (messages 51-200)
    - Tier 3: Key facts (messages 201-1000)
    - Tier 4: Core system state memory (1000+)
    """

    def __init__(self, conversation_id: str, storage_path: Optional[Path] = None):
        self.conversation_id = conversation_id
        self.storage_path = storage_path

        # Memory tiers
        self.raw_messages: List[Dict] = []  # Last 10
        self.detailed_summary: str = ""      # 11-50
        self.compressed_summary: str = ""    # 51-200
        self.key_facts: List[str] = []       # 201-1000
        self.core_memory: str = ""           # 1000+ (system state essence)

        # Metadata
        self.total_messages: int = 0
        self.topics_discussed: List[str] = []
        self.system_events: List[str] = []
        self.last_updated: Optional[datetime] = None

    def add_exchange(self, user_msg: str, assistant_msg: str):
        """Add a user/assistant exchange and update memory tiers."""
        self.total_messages += 2

        # Add to raw messages
        self.raw_messages.append({"role": "user", "content": user_msg})
        self.raw_messages.append({"role": "assistant", "content": assistant_msg})

        # Extract topics and system events
        self._extract_metadata(user_msg, assistant_msg)

        # Compress as needed based on thresholds
        self._rebalance_tiers()

        self.last_updated = datetime.now()

    def _extract_metadata(self, user_msg: str, assistant_msg: str):
        """Extract topics and system events from exchange."""
        combined = f"{user_msg} {assistant_msg}".lower()

        # Sysadmin topic extraction
        topic_patterns = [
            r'\b(service|daemon|systemd|nginx|apache|docker)\b',
            r'\b(network|interface|ip|dns|routing|firewall)\b',
            r'\b(disk|mount|partition|filesystem|lvm|storage)\b',
            r'\b(package|apt|dpkg|rpm|update|upgrade)\b',
            r'\b(kernel|module|driver|boot|grub)\b',
            r'\b(cpu|memory|ram|process|load)\b',
            r'\b(ssh|ssl|cert|auth|permissions|sudo)\b',
            r'\b(log|journal|debug|trace|monitor)\b',
        ]
        for pattern in topic_patterns:
            if re.search(pattern, combined):
                topic = re.search(pattern, combined).group(1)
                if topic not in self.topics_discussed[-20:]:  # Keep last 20 unique
                    self.topics_discussed.append(topic)

        # System event detection (replaces emotional moments)
        event_patterns = [
            (r'\b(failed|failure|crash|panic|segfault)\b', 'failure'),
            (r'\b(error|exception|traceback|bug)\b', 'error'),
            (r'\b(warning|warn|deprecat)\b', 'warning'),
            (r'\b(resolved|fixed|recovered|success)\b', 'resolved'),
            (r'\b(installed|configured|enabled|started)\b', 'configured'),
            (r'\b(disabled|stopped|removed|purged)\b', 'changed'),
        ]
        for pattern, event_type in event_patterns:
            if re.search(pattern, combined):
                moment = f"{event_type}: {user_msg[:50]}..."
                if len(self.system_events) < 50:
                    self.system_events.append(moment)

    def _rebalance_tiers(self):
        """Compress older messages into appropriate tiers."""
        raw_count = len(self.raw_messages)

        # Keep only last 10 raw messages
        if raw_count > TIER_THRESHOLDS['raw'] * 2:
            # Move older raw messages to detailed summary
            to_summarize = self.raw_messages[:-TIER_THRESHOLDS['raw']]
            self.raw_messages = self.raw_messages[-TIER_THRESHOLDS['raw']:]

            new_detail = self._create_detailed_summary(to_summarize)
            self.detailed_summary = self._merge_summaries(
                self.detailed_summary, new_detail, max_length=2000
            )

        # Compress detailed to compressed at threshold
        if self.total_messages > TIER_THRESHOLDS['detailed'] * 2:
            if len(self.detailed_summary) > 1500:
                compressed = self._compress_summary(self.detailed_summary)
                self.compressed_summary = self._merge_summaries(
                    self.compressed_summary, compressed, max_length=1000
                )
                self.detailed_summary = self.detailed_summary[-500:]  # Keep recent

        # Move to key facts at higher threshold
        if self.total_messages > TIER_THRESHOLDS['compressed'] * 2:
            if len(self.compressed_summary) > 800:
                facts = self._extract_key_facts(self.compressed_summary)
                self.key_facts.extend(facts)
                self.key_facts = self.key_facts[-30:]  # Keep 30 most recent facts
                self.compressed_summary = self.compressed_summary[-300:]

        # Create core memory for very long conversations
        if self.total_messages > TIER_THRESHOLDS['key_facts']:
            self._update_core_memory()

    def _create_detailed_summary(self, messages: List[Dict]) -> str:
        """Create detailed summary preserving key commands and actions."""
        parts = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'user':
                # Keep user messages fairly intact
                parts.append(f"User: {content[:150]}")
            else:
                # Extract commands and key info from assistant
                commands = re.findall(r'`([^`]+)`', content)
                if commands:
                    parts.append(f"Cmd: {commands[0][:80]}")
                else:
                    clean = re.sub(r'\*[^*]+\*', '', content).strip()
                    if clean:
                        parts.append(f"Assistant: {clean[:80]}")

        return " -> ".join(parts[-15:])

    def _compress_summary(self, summary: str) -> str:
        """Compress a summary to key points."""
        # Extract commands
        commands = re.findall(r'Cmd: ([^->]+)', summary)

        # Extract user statements
        user_parts = re.findall(r'User: ([^->]+)', summary)

        compressed_parts = []
        for user in user_parts[:5]:
            compressed_parts.append(f"User asked: {user[:40].strip()}")
        for cmd in commands[:5]:
            compressed_parts.append(f"Ran: {cmd[:40].strip()}")

        return " | ".join(compressed_parts)

    def _extract_key_facts(self, summary: str) -> List[str]:
        """Extract key facts from compressed summary."""
        facts = []

        # Look for definitive statements
        patterns = [
            r'User asked: (.+?)(?:\||$)',
            r'Ran: (.+?)(?:\||$)',
            r'discussed (.+?)(?:\||$)',
            r'configured (.+?)(?:\||$)',
            r'installed (.+?)(?:\||$)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, summary)
            facts.extend([m.strip()[:50] for m in matches[:3]])

        return facts[:5]  # Return top 5 facts

    def _merge_summaries(self, old: str, new: str, max_length: int) -> str:
        """Merge two summaries, keeping within max length."""
        if not old:
            return new[:max_length]

        combined = f"{old} ... {new}"
        if len(combined) > max_length:
            # Keep more recent content
            return combined[-max_length:]
        return combined

    def _update_core_memory(self):
        """Update core system state memory for very long conversations."""
        core_parts = []

        if self.topics_discussed:
            topics = ", ".join(self.topics_discussed[-10:])
            core_parts.append(f"Topics covered: {topics}")

        if self.system_events:
            # Summarize event patterns
            events = [m.split(':')[0] for m in self.system_events[-10:]]
            event_summary = ", ".join(set(events))
            core_parts.append(f"Event types: {event_summary}")

        core_parts.append(f"Conversation depth: {self.total_messages} messages")

        self.core_memory = " | ".join(core_parts)

    def build_context(self, system_prompt: str) -> List[Dict]:
        """
        Build context for LLM with hierarchical memory.

        Returns messages list ready for chat API.
        """
        messages = [{"role": "system", "content": system_prompt}]

        # Add memory context based on conversation length
        memory_parts = []

        if self.core_memory:
            memory_parts.append(f"[SYSTEM STATE CONTEXT: {self.core_memory}]")

        if self.key_facts:
            facts = " | ".join(self.key_facts[-10:])
            memory_parts.append(f"[KEY HISTORY: {facts}]")

        if self.compressed_summary:
            memory_parts.append(f"[EARLIER: {self.compressed_summary[:300]}]")

        if self.detailed_summary:
            memory_parts.append(f"[RECENT HISTORY: {self.detailed_summary[:500]}]")

        if memory_parts:
            messages.append({
                "role": "system",
                "content": "\n".join(memory_parts)
            })

        # Add raw recent messages
        messages.extend(self.raw_messages)

        return messages

    def save(self, path: Optional[Path] = None):
        """Save memory state to disk."""
        save_path = path or self.storage_path
        if not save_path:
            return

        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'conversation_id': self.conversation_id,
            'total_messages': self.total_messages,
            'raw_messages': self.raw_messages,
            'detailed_summary': self.detailed_summary,
            'compressed_summary': self.compressed_summary,
            'key_facts': self.key_facts,
            'core_memory': self.core_memory,
            'topics_discussed': self.topics_discussed,
            'system_events': self.system_events,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
        }

        with open(save_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved conversation memory: {self.total_messages} messages")

    @classmethod
    def load(cls, path: Path) -> Optional['ConversationMemory']:
        """Load memory state from disk."""
        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            memory = cls(data['conversation_id'], path)
            memory.total_messages = data.get('total_messages', 0)
            memory.raw_messages = data.get('raw_messages', [])
            memory.detailed_summary = data.get('detailed_summary', '')
            memory.compressed_summary = data.get('compressed_summary', '')
            memory.key_facts = data.get('key_facts', [])
            memory.core_memory = data.get('core_memory', '')
            memory.topics_discussed = data.get('topics_discussed', [])
            memory.system_events = data.get('system_events', [])

            if data.get('last_updated'):
                memory.last_updated = datetime.fromisoformat(data['last_updated'])

            return memory
        except Exception as e:
            logger.error(f"Failed to load conversation memory: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            'total_messages': self.total_messages,
            'raw_messages': len(self.raw_messages),
            'detailed_summary_chars': len(self.detailed_summary),
            'compressed_summary_chars': len(self.compressed_summary),
            'key_facts_count': len(self.key_facts),
            'has_core_memory': bool(self.core_memory),
            'topics_count': len(self.topics_discussed),
            'system_events_count': len(self.system_events),
        }


def get_conversation_memory(
    conversation_id: str,
    persona_id: str,
    base_path: Optional[Path] = None
) -> ConversationMemory:
    """
    Get or create a ConversationMemory for a conversation.

    Args:
        conversation_id: Unique conversation ID
        persona_id: Persona ID (for storage path)
        base_path: Base path for storage (default: ~/.halbert/personas/{pid}/memories/)
    """
    if base_path is None:
        base_path = Path.home() / '.halbert' / 'personas' / persona_id / 'conversation_memories'

    memory_path = base_path / f'{conversation_id}.json'

    # Try to load existing
    memory = ConversationMemory.load(memory_path)
    if memory:
        return memory

    # Create new
    return ConversationMemory(conversation_id, memory_path)
