"""
ReAct Agent - Thought-Action-Observation Loop

Phase 21: Implements industry-standard ReAct pattern (Yao et al., 2022)
for iterative reasoning like Cursor, Windsurf Cascade, and Copilot.

Key insight: The AI should execute tools under the hood and show its
reasoning, NOT inject fake user messages asking itself questions.
"""

from __future__ import annotations
import logging
import time
import json
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('halbert.agents.react')


class ThinkingStepType(str, Enum):
    """Types of thinking steps in the ReAct loop."""
    THOUGHT = "thought"        # AI reasoning about current state
    ACTION = "action"          # AI executing a tool
    OBSERVATION = "observation" # Result of tool execution
    FINAL = "final"            # Final answer synthesis


@dataclass
class ThinkingStep:
    """
    A single step in the ReAct thinking process.
    
    Displayed in UI as collapsible "Thought for Xs" section.
    """
    type: ThinkingStepType
    content: str
    duration_ms: int = 0
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    tool_result: Optional[Dict] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict for API response."""
        result = {
            "type": self.type.value,
            "content": self.content,
            "duration_ms": self.duration_ms,
        }
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_args:
            result["tool_args"] = self.tool_args
        if self.tool_result:
            result["tool_result"] = self.tool_result
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class ReActResponse:
    """
    Response from ReAct agent including thinking process.
    
    Contains both the final response text and the thinking steps
    that led to it (for UI display).
    """
    final_response: str
    thinking_steps: List[ThinkingStep] = field(default_factory=list)
    total_duration_ms: int = 0
    iterations: int = 0
    model_used: Optional[str] = None
    tool_calls_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict for API response."""
        return {
            "final_response": self.final_response,
            "thinking_steps": [s.to_dict() for s in self.thinking_steps],
            "total_duration_ms": self.total_duration_ms,
            "iterations": self.iterations,
            "model_used": self.model_used,
            "tool_calls_count": self.tool_calls_count,
        }


class ReActAgent:
    """
    ReAct agent implementing Thought-Action-Observation loop.
    
    Based on:
    - Yao et al. 2022 "ReAct: Synergizing Reasoning and Acting"
    - Windsurf Cascade architecture (up to 20 tool calls)
    - Cursor's Embed-Think-Do loop
    
    The loop:
        1. THOUGHT  → AI reasons about the current state
        2. ACTION   → AI executes a tool (if needed)
        3. OBSERVATION → AI observes the result
        4. REFLECT  → AI decides: continue or final answer
    """
    
    MAX_ITERATIONS = 5  # Reasonable default (Cursor uses 3-5)
    THINKING_TIMEOUT_SEC = 120  # Max time for entire thinking process
    
    def __init__(
        self,
        model: str,
        endpoint: str,
        tools: List[Dict],
        execute_tool_fn,
        check_auth_fn=None,
        max_iterations: int = None,
    ):
        """
        Initialize ReAct agent.
        
        Args:
            model: Ollama model name (e.g., "llama3.1:8b")
            endpoint: Ollama API endpoint URL
            tools: List of tool definitions in Ollama format
            execute_tool_fn: Function to execute tools (name, args) -> result
            check_auth_fn: Optional function to check tool authorization
            max_iterations: Override max iterations
        """
        self.model = model
        self.endpoint = endpoint
        self.tools = tools
        self.execute_tool = execute_tool_fn
        self.check_auth = check_auth_fn
        self.max_iterations = max_iterations or self.MAX_ITERATIONS
    
    def run(
        self,
        query: str,
        system_prompt: str,
        context: str = "",
        history: List[Dict] = None,
    ) -> ReActResponse:
        """
        Execute ReAct loop until solution or max iterations.
        
        Args:
            query: User's question/request
            system_prompt: System prompt for LLM
            context: Additional context (mentions, discoveries, etc.)
            history: Conversation history as list of {role, content} dicts
            
        Returns:
            ReActResponse with thinking_steps and final_response
        """
        start_time = time.time()
        steps: List[ThinkingStep] = []
        tool_calls_count = 0
        
        # Build initial messages
        messages = self._build_initial_messages(system_prompt, context, history, query)
        
        for iteration in range(self.max_iterations):
            iter_start = time.time()
            
            # Step 1: Ask LLM what to do (with tools available)
            logger.info(f"ReAct iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                response = self._call_llm_with_tools(messages)
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                steps.append(ThinkingStep(
                    type=ThinkingStepType.THOUGHT,
                    content=f"Error calling LLM: {str(e)}",
                    error=str(e),
                    duration_ms=int((time.time() - iter_start) * 1000)
                ))
                break
            
            message = response.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            # If no tool calls, this is the final answer
            if not tool_calls:
                # Check if model output raw tool call JSON (fallback detection)
                if self._looks_like_raw_tool_call(content):
                    logger.warning("Model output raw tool JSON, treating as confused response")
                    steps.append(ThinkingStep(
                        type=ThinkingStepType.THOUGHT,
                        content="Model attempted tool call in wrong format",
                        duration_ms=int((time.time() - iter_start) * 1000)
                    ))
                    # Continue to get proper response
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user", 
                        "content": "Please provide your answer directly, not as a function call."
                    })
                    continue
                
                # Final answer
                steps.append(ThinkingStep(
                    type=ThinkingStepType.FINAL,
                    content="Synthesizing final response",
                    duration_ms=int((time.time() - iter_start) * 1000)
                ))
                
                total_duration = int((time.time() - start_time) * 1000)
                return ReActResponse(
                    final_response=content,
                    thinking_steps=steps,
                    total_duration_ms=total_duration,
                    iterations=iteration + 1,
                    model_used=self.model,
                    tool_calls_count=tool_calls_count,
                )
            
            # Step 2: Process tool calls
            for tool_call in tool_calls:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                arguments = func.get("arguments", {})
                
                action_start = time.time()
                
                # Record the thought/action
                steps.append(ThinkingStep(
                    type=ThinkingStepType.ACTION,
                    content=f"Running: {tool_name}",
                    tool_name=tool_name,
                    tool_args=arguments,
                    duration_ms=0  # Will be updated after execution
                ))
                
                # Check authorization if available
                if self.check_auth:
                    auth = self.check_auth(tool_name, arguments)
                    if not auth.get("allowed", True):
                        steps.append(ThinkingStep(
                            type=ThinkingStepType.OBSERVATION,
                            content=f"Tool blocked: {auth.get('reason', 'Not authorized')}",
                            tool_name=tool_name,
                            error=auth.get('reason'),
                            duration_ms=int((time.time() - action_start) * 1000)
                        ))
                        continue
                    
                    if auth.get("approval_required"):
                        steps.append(ThinkingStep(
                            type=ThinkingStepType.OBSERVATION,
                            content=f"Tool requires user approval",
                            tool_name=tool_name,
                            tool_result={"pending_approval": True},
                            duration_ms=int((time.time() - action_start) * 1000)
                        ))
                        continue
                
                # Execute the tool
                try:
                    result = self.execute_tool(tool_name, arguments)
                    tool_calls_count += 1
                    
                    # Record observation
                    result_summary = self._summarize_result(result)
                    steps.append(ThinkingStep(
                        type=ThinkingStepType.OBSERVATION,
                        content=result_summary,
                        tool_name=tool_name,
                        tool_result=result if isinstance(result, dict) else {"data": str(result)},
                        duration_ms=int((time.time() - action_start) * 1000)
                    ))
                    
                    # Update action step duration
                    steps[-2].duration_ms = int((time.time() - action_start) * 1000)
                    
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    steps.append(ThinkingStep(
                        type=ThinkingStepType.OBSERVATION,
                        content=f"Tool error: {str(e)}",
                        tool_name=tool_name,
                        error=str(e),
                        duration_ms=int((time.time() - action_start) * 1000)
                    ))
            
            # Step 3: Add tool results to messages for next iteration
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls
            })
            
            # Add tool results
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name", "")
                # Find the corresponding observation step
                for step in reversed(steps):
                    if step.type == ThinkingStepType.OBSERVATION and step.tool_name == tool_name:
                        result_content = json.dumps(step.tool_result or {"error": step.error})
                        break
                else:
                    result_content = '{"error": "No result found"}'
                
                messages.append({
                    "role": "tool",
                    "content": result_content
                })
            
            # Check timeout
            if time.time() - start_time > self.THINKING_TIMEOUT_SEC:
                logger.warning("ReAct loop timeout reached")
                steps.append(ThinkingStep(
                    type=ThinkingStepType.THOUGHT,
                    content="Reasoning timeout - synthesizing available information",
                    duration_ms=0
                ))
                break
        
        # Max iterations reached - get final synthesis
        logger.info(f"ReAct completed after {len(steps)} steps")
        
        # Request final answer
        messages.append({
            "role": "user",
            "content": "Based on all the information gathered, please provide your final answer."
        })
        
        try:
            final_response = self._call_llm(messages)
        except Exception as e:
            final_response = f"I gathered information but encountered an error synthesizing the response: {e}"
        
        total_duration = int((time.time() - start_time) * 1000)
        return ReActResponse(
            final_response=final_response,
            thinking_steps=steps,
            total_duration_ms=total_duration,
            iterations=self.max_iterations,
            model_used=self.model,
            tool_calls_count=tool_calls_count,
        )
    
    def _build_initial_messages(
        self,
        system_prompt: str,
        context: str,
        history: List[Dict],
        query: str
    ) -> List[Dict]:
        """Build initial message array for LLM."""
        messages = []
        
        # System message with ReAct instructions
        react_instructions = """
When solving complex problems, use this reasoning pattern:
1. Think about what information you need
2. Use available tools to gather information
3. Observe the results
4. Either gather more info or provide your final answer

You have access to system tools. Use them to get real-time information when needed.
After gathering enough information, synthesize a helpful response.
"""
        
        full_system = system_prompt + "\n\n" + react_instructions
        if context:
            full_system += f"\n\nContext:\n{context}"
        
        messages.append({"role": "system", "content": full_system})
        
        # Add conversation history
        if history:
            for msg in history[-6:]:  # Last 6 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content[:2000]})
        
        # Current query
        messages.append({"role": "user", "content": query})
        
        return messages
    
    def _call_llm_with_tools(self, messages: List[Dict]) -> Dict:
        """Call LLM with tool definitions."""
        response = requests.post(
            f"{self.endpoint}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "tools": self.tools,
                "stream": False,
                "options": {
                    "num_predict": 1024,
                    "temperature": 0.7
                }
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    
    def _call_llm(self, messages: List[Dict]) -> str:
        """Call LLM without tools for final synthesis."""
        response = requests.post(
            f"{self.endpoint}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": 1024,
                    "temperature": 0.7
                }
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
    
    def _looks_like_raw_tool_call(self, content: str) -> bool:
        """Check if content looks like a raw function call JSON."""
        if not content:
            return False
        indicators = ['{"name":', '"function"', 'get_network_info', 'get_disk_usage']
        return any(ind in content for ind in indicators)
    
    def _summarize_result(self, result) -> str:
        """Create a short summary of tool result for thinking step."""
        if isinstance(result, dict):
            if result.get("success") is False:
                return f"Error: {result.get('error', 'Unknown error')}"
            if result.get("data"):
                data = result["data"]
                if isinstance(data, str):
                    return data[:200] + "..." if len(data) > 200 else data
                return f"Got result with {len(str(data))} chars"
            return "Tool executed successfully"
        return str(result)[:200]
