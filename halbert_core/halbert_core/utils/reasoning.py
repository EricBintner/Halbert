"""
Reasoning Model Support - Phase 32

Utilities for parsing and handling extended thinking/reasoning from models
like DeepSeek R1, QwQ, or Claude with extended thinking.

Reasoning models output their chain-of-thought in special blocks:
- DeepSeek R1 / QwQ: &lt;think&gt;...&lt;/think&gt;
- Some models use: &lt;reasoning&gt;...&lt;/reasoning&gt;
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List

logger = logging.getLogger('halbert.utils.reasoning')


@dataclass
class ReasoningResult:
    """Result of parsing a reasoning model response."""
    thinking: str  # The reasoning/thinking content
    response: str  # The final response without thinking tags
    thinking_duration_ms: int = 0
    model_type: str = "unknown"  # Type of reasoning detected


def parse_thinking_blocks(text: str) -> ReasoningResult:
    """
    Parse thinking/reasoning blocks from model output.
    
    Supports multiple formats:
    - &lt;think&gt;...&lt;/think&gt; (DeepSeek R1, QwQ, Qwen)
    - &lt;reasoning&gt;...&lt;/reasoning&gt;
    - &lt;thought&gt;...&lt;/thought&gt;
    
    Args:
        text: Raw model output
        
    Returns:
        ReasoningResult with separated thinking and response
    """
    if not text:
        return ReasoningResult(thinking="", response="", model_type="none")
    
    # Try different thinking tag patterns
    patterns = [
        (r'<think>(.*?)</think>', 'think'),
        (r'<thinking>(.*?)</thinking>', 'thinking'),
        (r'<reasoning>(.*?)</reasoning>', 'reasoning'),
        (r'<thought>(.*?)</thought>', 'thought'),
    ]
    
    thinking_parts = []
    response = text
    model_type = "none"
    
    for pattern, tag_type in patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            model_type = tag_type
            thinking_parts.extend(matches)
            # Remove thinking blocks from response
            response = re.sub(pattern, '', response, flags=re.DOTALL | re.IGNORECASE)
    
    # Clean up response (remove extra whitespace from tag removal)
    response = response.strip()
    response = re.sub(r'\n{3,}', '\n\n', response)  # Collapse multiple newlines
    
    # Combine all thinking parts
    thinking = '\n\n'.join(t.strip() for t in thinking_parts if t.strip())
    
    if thinking:
        logger.debug(f"Extracted {len(thinking)} chars of reasoning ({model_type} tags)")
    
    return ReasoningResult(
        thinking=thinking,
        response=response,
        model_type=model_type
    )


def is_reasoning_model(model_name: str) -> bool:
    """
    Check if a model is known to support extended thinking.
    
    Args:
        model_name: Model identifier (e.g., "qwq:32b", "deepseek-r1:70b")
        
    Returns:
        True if model supports reasoning output
    """
    reasoning_patterns = [
        'qwq',           # QwQ reasoning model
        'qwen3',         # Qwen3 thinking models
        'qwen-thinking', # Qwen thinking models
        'thinking',      # Generic thinking models (e.g., qwen3-next-80b-a3b-thinking)
        'deepseek-r1',   # DeepSeek R1
        'deepseek-reasoner',
        'o1',            # OpenAI o1 (if available)
        'o3',            # OpenAI o3
        'reasoning',     # Generic reasoning models
    ]
    
    model_lower = model_name.lower()
    return any(pattern in model_lower for pattern in reasoning_patterns)


class StreamingReasoningParser:
    """
    Streaming parser for reasoning model output.
    
    Handles incremental token processing to detect when model
    transitions from thinking to response.
    """
    
    def __init__(self, assume_thinking_mode: bool = False):
        self.buffer = ""
        self.thinking_content = ""
        self.response_content = ""
        # Qwen3-Thinking models start in thinking mode WITHOUT opening <think> tag
        # The chat template includes <think> implicitly
        self.in_thinking = assume_thinking_mode
        self.thinking_complete = False
        self._thinking_start_patterns = ['<think>', '<thinking>', '<reasoning>', '<thought>']
        self._thinking_end_patterns = ['</think>', '</thinking>', '</reasoning>', '</thought>']
    
    def process_token(self, token: str) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Process a single token from streaming output.
        
        Args:
            token: The new token to process
            
        Returns:
            Tuple of (thinking_delta, response_delta, is_thinking)
            - thinking_delta: New thinking content (or None)
            - response_delta: New response content (or None)
            - is_thinking: Whether we're currently in a thinking block
        """
        self.buffer += token
        
        thinking_delta = None
        response_delta = None
        
        # Check for thinking start
        if not self.in_thinking and not self.thinking_complete:
            for pattern in self._thinking_start_patterns:
                if pattern in self.buffer.lower():
                    self.in_thinking = True
                    # Extract any content before the tag as response
                    idx = self.buffer.lower().index(pattern)
                    if idx > 0:
                        response_delta = self.buffer[:idx]
                        self.response_content += response_delta
                    self.buffer = self.buffer[idx + len(pattern):]
                    break
        
        # Check for thinking end
        if self.in_thinking:
            for pattern in self._thinking_end_patterns:
                if pattern in self.buffer.lower():
                    self.in_thinking = False
                    self.thinking_complete = True
                    # Extract thinking content before the tag
                    idx = self.buffer.lower().index(pattern)
                    if idx > 0:
                        thinking_delta = self.buffer[:idx]
                        self.thinking_content += thinking_delta
                    self.buffer = self.buffer[idx + len(pattern):]
                    break
            
            # If still in thinking and no end tag found, accumulate
            if self.in_thinking and len(self.buffer) > 20:
                # Keep last 20 chars in buffer for tag detection
                thinking_delta = self.buffer[:-20]
                self.thinking_content += thinking_delta
                self.buffer = self.buffer[-20:]
        
        # If not in thinking mode, accumulate response
        elif self.thinking_complete or (not self.in_thinking and len(self.buffer) > 20):
            # Keep some buffer for potential late tag detection
            if not self.thinking_complete and any(p[:5] in self.buffer.lower() for p in self._thinking_start_patterns):
                # Possible thinking tag coming, hold buffer
                pass
            else:
                response_delta = self.buffer[:-20] if len(self.buffer) > 20 else self.buffer
                self.response_content += response_delta
                self.buffer = self.buffer[-20:] if len(self.buffer) > 20 else ""
        
        return thinking_delta, response_delta, self.in_thinking
    
    def finalize(self) -> Tuple[str, str]:
        """
        Finalize parsing and return complete thinking and response.
        
        Call this when streaming is complete.
        
        Returns:
            Tuple of (thinking_content, response_content)
        """
        # Flush remaining buffer
        if self.in_thinking:
            self.thinking_content += self.buffer
        else:
            self.response_content += self.buffer
        self.buffer = ""
        
        return self.thinking_content.strip(), self.response_content.strip()
    
    def reset(self):
        """Reset parser state for new response."""
        self.buffer = ""
        self.thinking_content = ""
        self.response_content = ""
        self.in_thinking = False
        self.thinking_complete = False
