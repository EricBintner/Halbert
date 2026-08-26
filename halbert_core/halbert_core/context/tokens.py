# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Token Counter

Utility for counting and managing tokens for context budget.
Based on research5.md Part 19.4.
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger('halbert.context.tokens')


class TokenCounter:
    """
    Count tokens for context budget management.
    
    Uses tiktoken when available, falls back to word-based estimation.
    """
    
    # Average chars per token (conservative estimate)
    CHARS_PER_TOKEN = 4
    
    def __init__(self, model: str = "cl100k_base"):
        """
        Initialize token counter.
        
        Args:
            model: Tiktoken encoding model name
        """
        self.model = model
        self.encoder = None
        
        # Try to load tiktoken
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding(model)
            logger.debug(f"Using tiktoken encoder: {model}")
        except ImportError:
            logger.warning("tiktoken not available, using estimation")
        except Exception as e:
            logger.warning(f"Failed to load tiktoken: {e}, using estimation")
    
    def count(self, text: str) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Token count
        """
        if not text:
            return 0
        
        if self.encoder:
            return len(self.encoder.encode(text))
        
        # Fallback: estimate based on characters
        return len(text) // self.CHARS_PER_TOKEN + 1
    
    def count_messages(self, messages: List[Dict]) -> int:
        """
        Count tokens in a list of chat messages.
        
        Args:
            messages: List of {role, content} dicts
            
        Returns:
            Total token count including overhead
        """
        total = 0
        
        for msg in messages:
            # Role overhead (approximately 4 tokens for role markers)
            total += 4
            
            # Content tokens
            content = msg.get("content", "")
            total += self.count(content)
            
            # Name field if present
            if msg.get("name"):
                total += self.count(msg["name"])
        
        # Assistant reply priming
        total += 2
        
        return total
    
    def truncate_to_limit(self, text: str, max_tokens: int, suffix: str = "\n[truncated...]") -> str:
        """
        Truncate text to fit within token limit.
        
        Args:
            text: Text to truncate
            max_tokens: Maximum tokens allowed
            suffix: Suffix to add when truncating
            
        Returns:
            Truncated text
        """
        if not text:
            return text
        
        current_tokens = self.count(text)
        if current_tokens <= max_tokens:
            return text
        
        suffix_tokens = self.count(suffix)
        target_tokens = max_tokens - suffix_tokens
        
        if target_tokens <= 0:
            return suffix
        
        if self.encoder:
            # Precise truncation with tiktoken
            tokens = self.encoder.encode(text)
            truncated_tokens = tokens[:target_tokens]
            return self.encoder.decode(truncated_tokens) + suffix
        
        # Fallback: character-based truncation
        target_chars = target_tokens * self.CHARS_PER_TOKEN
        return text[:target_chars] + suffix
    
    def split_to_chunks(self, text: str, chunk_size: int, overlap: int = 0) -> List[str]:
        """
        Split text into chunks of approximately chunk_size tokens.
        
        Args:
            text: Text to split
            chunk_size: Target tokens per chunk
            overlap: Token overlap between chunks
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        if self.count(text) <= chunk_size:
            return [text]
        
        chunks = []
        
        if self.encoder:
            tokens = self.encoder.encode(text)
            start = 0
            
            while start < len(tokens):
                end = start + chunk_size
                chunk_tokens = tokens[start:end]
                chunks.append(self.encoder.decode(chunk_tokens))
                start = end - overlap if overlap > 0 else end
        else:
            # Fallback: character-based chunking
            chars_per_chunk = chunk_size * self.CHARS_PER_TOKEN
            overlap_chars = overlap * self.CHARS_PER_TOKEN
            start = 0
            
            while start < len(text):
                end = start + chars_per_chunk
                chunks.append(text[start:end])
                start = end - overlap_chars if overlap_chars > 0 else end
        
        return chunks
    
    def estimate_from_chars(self, char_count: int) -> int:
        """Estimate token count from character count."""
        return char_count // self.CHARS_PER_TOKEN + 1
    
    def estimate_chars_for_tokens(self, token_count: int) -> int:
        """Estimate character count needed for token count."""
        return token_count * self.CHARS_PER_TOKEN
