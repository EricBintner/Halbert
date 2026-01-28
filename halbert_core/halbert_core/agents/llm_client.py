"""
LLM Client Wrapper

Unified interface for LLM interactions with streaming support.
Works with Ollama, Anthropic, and other providers.
"""

from __future__ import annotations
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Any, Optional, Union
import aiohttp

logger = logging.getLogger('halbert.agents.llm_client')


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    function: 'FunctionCall'


@dataclass
class FunctionCall:
    """Function call details."""
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    plan: List[Dict] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict] = None,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion request."""
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream chat completion response."""
        pass


class OllamaClient(BaseLLMClient):
    """
    Ollama LLM client with streaming support.
    
    Supports tool calling for compatible models (llama3.1, etc.)
    """
    
    def __init__(
        self,
        model: str = "llama3.1:8b",
        endpoint: str = "http://localhost:11434",
        timeout: int = 120,
    ):
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion to Ollama.
        
        Args:
            messages: Chat messages
            tools: Optional tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with content and optional tool calls
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        if tools:
            payload["tools"] = tools
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.endpoint}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    
                    return self._parse_response(data)
                    
        except asyncio.TimeoutError:
            logger.error(f"Ollama request timeout after {self.timeout}s")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Ollama request failed: {e}")
            raise
    
    async def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream chat completion from Ollama.
        
        Yields content chunks as they arrive.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.endpoint}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    resp.raise_for_status()
                    
                    async for line in resp.content:
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            
                            if data.get("done"):
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except asyncio.TimeoutError:
            logger.error(f"Ollama stream timeout after {self.timeout}s")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Ollama stream failed: {e}")
            raise
    
    def _parse_response(self, data: Dict) -> LLMResponse:
        """Parse Ollama response into LLMResponse."""
        message = data.get("message", {})
        content = message.get("content", "")
        
        # Parse tool calls if present
        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    function=FunctionCall(
                        name=func.get("name", ""),
                        arguments=func.get("arguments", {})
                    )
                ))
        
        # Try to extract plan from content if structured
        plan = self._extract_plan(content)
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            plan=plan,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0)
            }
        )
    
    def _extract_plan(self, content: str) -> List[Dict]:
        """Try to extract structured plan from content."""
        # Look for plan markers
        if "plan:" not in content.lower() and "steps:" not in content.lower():
            return []
        
        # Simple extraction: numbered items
        import re
        pattern = r'^\s*(\d+)\.\s+(.+)$'
        lines = content.split('\n')
        
        plan = []
        for line in lines:
            match = re.match(pattern, line)
            if match:
                plan.append({
                    "step": match.group(2).strip(),
                    "status": "pending"
                })
        
        return plan[:5]  # Limit to 5 steps


class AnthropicClient(BaseLLMClient):
    """
    Anthropic Claude client with streaming support.
    """
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "claude-3-haiku-20240307",
        timeout: int = 120,
    ):
        import os
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.timeout = timeout
        self.endpoint = "https://api.anthropic.com/v1/messages"
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion to Anthropic."""
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")
        
        # Convert messages to Anthropic format
        system_msg = ""
        claude_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                claude_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": claude_messages,
        }
        
        if system_msg:
            payload["system"] = system_msg
        
        if tools:
            # Convert to Anthropic tool format
            payload["tools"] = self._convert_tools(tools)
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                return self._parse_anthropic_response(data)
    
    async def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream chat completion from Anthropic."""
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")
        
        # Convert messages
        system_msg = ""
        claude_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                claude_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": claude_messages,
            "stream": True
        }
        
        if system_msg:
            payload["system"] = system_msg
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                resp.raise_for_status()
                
                async for line in resp.content:
                    line = line.decode('utf-8').strip()
                    if not line or not line.startswith('data: '):
                        continue
                    
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")
                    except json.JSONDecodeError:
                        continue
    
    def _convert_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI-style tools to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        return anthropic_tools
    
    def _parse_anthropic_response(self, data: Dict) -> LLMResponse:
        """Parse Anthropic response."""
        content = ""
        tool_calls = []
        
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    function=FunctionCall(
                        name=block.get("name", ""),
                        arguments=block.get("input", {})
                    )
                ))
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "stop"),
            usage={
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0)
            }
        )


def get_llm_client(provider: str = "ollama", **kwargs) -> BaseLLMClient:
    """
    Factory function to get an LLM client.
    
    Args:
        provider: "ollama" or "anthropic"
        **kwargs: Provider-specific arguments
        
    Returns:
        Configured LLM client
    """
    if provider == "ollama":
        return OllamaClient(**kwargs)
    elif provider == "anthropic":
        return AnthropicClient(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
