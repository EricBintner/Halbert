# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Conversation module for Halbert.

Provides hierarchical conversation summarization for long chats.
"""

from halbert_core.conversation.summarization import (
    should_summarize,
    create_simple_summary,
    compress_conversation_history,
    estimate_token_count,
    get_compression_stats,
    ConversationMemory,
    get_conversation_memory,
)

__all__ = [
    "should_summarize",
    "create_simple_summary",
    "compress_conversation_history",
    "estimate_token_count",
    "get_compression_stats",
    "ConversationMemory",
    "get_conversation_memory",
]
