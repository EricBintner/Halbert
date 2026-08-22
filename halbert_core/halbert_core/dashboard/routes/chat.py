"""
Chat API routes.

Provides endpoints for AI chat interactions.
Uses the discovery engine for context and (optionally) local LLM.
"""

from __future__ import annotations
import logging
from typing import Optional, List, Dict, Tuple

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    StreamingResponse = object

from ..routes.discovery import get_engine
from ...model.router import ModelRouter, TaskType
from ...discovery.schema import DiscoveryType
from ...index.chroma_index import get_index
from ...autonomy.guardrails import GuardrailEnforcer, GuardrailViolation
from ...policy.engine import decide as policy_decide
from ...policy.loader import load_policy
from ...approval.engine import ApprovalEngine, ApprovalRequest
from pathlib import Path
import uuid
from datetime import datetime, timezone
import socket
import json
import requests

# Phase 32: Reasoning model support
from ...utils.reasoning import parse_thinking_blocks, StreamingReasoningParser, is_reasoning_model

# Phase 40-46: Prompt System v2
from ...prompts import (
    PromptLoader,
    PromptBuilder,
    ContextInjector,
    UserPreferences,
    get_safety_validator,
)

logger = logging.getLogger('halbert.dashboard.routes.chat')

# ─────────────────────────────────────────────────────────────────────────────
# Prompt System v2 (Phase 40-46)
# ─────────────────────────────────────────────────────────────────────────────

_prompt_loader: Optional[PromptLoader] = None
_prompt_builder: Optional[PromptBuilder] = None
_context_injector: Optional[ContextInjector] = None


def get_prompt_builder(force_reload: bool = False) -> PromptBuilder:
    """Get singleton PromptBuilder instance."""
    global _prompt_loader, _prompt_builder
    if _prompt_builder is None or force_reload:
        try:
            from ...utils.platform import get_config_dir
            prompts_dir = get_config_dir().parent / "config" / "prompts"
            if not prompts_dir.exists():
                # Fallback to relative path from halbert_core
                prompts_dir = Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts"
            _prompt_loader = PromptLoader(prompts_dir)
            _prompt_builder = PromptBuilder(_prompt_loader)
            logger.info(f"Initialized PromptBuilder from {prompts_dir}")
        except Exception as e:
            logger.warning(f"Failed to init PromptBuilder: {e}, using fallback")
            return None
    return _prompt_builder


def reload_prompts():
    """Force reload of all prompt components. Call after editing XML files."""
    global _prompt_loader, _prompt_builder
    if _prompt_loader:
        _prompt_loader.clear_cache()
    if _prompt_builder:
        _prompt_builder.clear_cache()
    # Force full reinit
    _prompt_loader = None
    _prompt_builder = None
    get_prompt_builder(force_reload=True)
    logger.info("Prompts reloaded from disk")


def get_context_injector() -> ContextInjector:
    """Get singleton ContextInjector instance."""
    global _context_injector
    if _context_injector is None:
        try:
            engine = get_engine()
            _context_injector = ContextInjector(discovery_engine=engine)
        except Exception:
            _context_injector = ContextInjector()
    return _context_injector


def build_system_prompt_v2(
    tier: str = "specialist",
    user_prefs: Optional[dict] = None,
    project_dir: Optional[Path] = None,
    rag_results: Optional[list] = None,
) -> Optional[str]:
    """
    Build system prompt using Phase 40-46 prompt infrastructure.
    
    Args:
        tier: Model tier - "guide", "specialist", or "vision"
        user_prefs: Optional user preferences dict
        project_dir: Optional project directory for HALBERT.md
        rag_results: Optional RAG retrieval results
        
    Returns:
        Assembled system prompt or None if v2 not available
    """
    builder = get_prompt_builder()
    if not builder:
        return None
    
    try:
        # Get context injector for system state
        injector = get_context_injector()
        sys_ctx = injector.get_system_context()
        system_context = injector.format_system_context(sys_ctx)
        
        # Build user preferences if provided
        prefs = None
        if user_prefs:
            prefs = user_prefs
        
        # Build the prompt
        prompt = builder.build_prompt(
            tier=tier,
            system_context=system_context,
            user_prefs=prefs,
            project_context=injector.load_project_context(project_dir) if project_dir else None,
            rag_results=rag_results,
        )
        
        token_estimate = builder.estimate_tokens(prompt)
        logger.info(f"Built v2 {tier} prompt: ~{token_estimate} tokens")
        
        return prompt
    except Exception as e:
        logger.warning(f"Failed to build v2 prompt: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Guardrails & Policy Integration (Phase 23)
# ─────────────────────────────────────────────────────────────────────────────

_guardrail_enforcer: Optional[GuardrailEnforcer] = None
_policy_cache: Optional[dict] = None
_approval_engine: Optional[ApprovalEngine] = None

def get_approval_engine() -> ApprovalEngine:
    """Get singleton approval engine."""
    global _approval_engine
    if _approval_engine is None:
        _approval_engine = ApprovalEngine()
    return _approval_engine


def create_tool_approval_request(
    tool_name: str, 
    tool_args: dict,
    reason: str,
    confidence: float = 0.5
) -> ApprovalRequest:
    """
    Create an approval request for a tool call that requires user approval.
    
    Returns the created ApprovalRequest (already stored in engine).
    """
    engine = get_approval_engine()
    
    request = ApprovalRequest(
        id=f"chat_tool_{uuid.uuid4().hex[:8]}",
        task=f"Execute Tool: {tool_name}",
        action=f"Run '{tool_name}' with args: {json.dumps(tool_args, indent=2)}",
        reasoning=reason,
        confidence=confidence,
        risk_level="medium",  # Could be dynamic based on tool
        system_state={"source": "chat", "tool": tool_name},
        affected_resources=[tool_name],
        requested_at=datetime.now(timezone.utc).isoformat() + 'Z',
        requested_by="chat_assistant"
    )
    
    # Queue the request for dashboard approval
    engine.queue_request(request)
    
    logger.info(f"Created approval request {request.id} for tool {tool_name}")
    return request


def get_guardrails() -> GuardrailEnforcer:
    """Get singleton guardrail enforcer."""
    global _guardrail_enforcer
    if _guardrail_enforcer is None:
        _guardrail_enforcer = GuardrailEnforcer()
    return _guardrail_enforcer

def get_policy() -> dict:
    """Get cached policy config."""
    global _policy_cache
    if _policy_cache is None:
        try:
            _policy_cache = load_policy()
        except Exception as e:
            logger.warning(f"Failed to load policy, using permissive default: {e}")
            _policy_cache = {"default_allow": True, "tools": {}}
    return _policy_cache

def check_tool_authorization(tool_name: str, tool_args: dict, confidence: float = 0.9) -> dict:
    """
    Check if a tool call is authorized by policy and guardrails.
    
    Returns:
        {
            "allowed": bool,
            "reason": str or None,
            "approval_required": bool,
            "simulation_required": bool
        }
    """
    result = {
        "allowed": True,
        "reason": None,
        "approval_required": False,
        "simulation_required": False
    }
    
    # 1. Check policy first
    try:
        policy = get_policy()
        decision = policy_decide(policy, tool_name, is_apply=True, ctx={"inputs": tool_args})
        
        if not decision.allow:
            return {
                "allowed": False,
                "reason": f"Policy denied: {decision.reason}",
                "approval_required": False,
                "simulation_required": False
            }
        
        result["simulation_required"] = decision.simulation_required
        if decision.approvals_needed:
            result["approval_required"] = True
            
    except Exception as e:
        logger.warning(f"Policy check failed, allowing: {e}")
    
    # 2. Check guardrails
    try:
        guardrails = get_guardrails()
        
        # Estimate resources (conservative defaults)
        estimated_resources = {
            "cpu_percent": 10,
            "memory_mb": 100,
            "time_minutes": 1
        }
        
        allowed, reason = guardrails.check_all(
            confidence=confidence,
            estimated_resources=estimated_resources,
            task=f"Tool: {tool_name}"
        )
        
        if not allowed:
            if reason == "approval_required":
                result["approval_required"] = True
            else:
                return {
                    "allowed": False,
                    "reason": f"Guardrail: {reason}",
                    "approval_required": False,
                    "simulation_required": False
                }
                
    except GuardrailViolation as e:
        return {
            "allowed": False,
            "reason": f"Guardrail violation: {str(e)}",
            "approval_required": False,
            "simulation_required": False
        }
    except Exception as e:
        logger.warning(f"Guardrail check failed, allowing: {e}")
    
    return result


def get_memory_context(query: str, conversation_id: Optional[str] = None, max_results: int = 3) -> str:
    """
    Retrieve relevant context from conversation memory.
    
    Uses ChromaDB semantic search to find relevant past conversations.
    """
    try:
        index = get_index()
        
        # Query past conversations for relevant context
        results = index.query_conversations(
            query=query,
            k=max_results,
            conversation_id=None  # Search across all conversations
        )
        
        if not results:
            return ""
        
        # Format relevant memories
        memory_parts = ["**Relevant past context:**"]
        for r in results:
            role = r.get('role', 'unknown')
            content = r.get('content', '')[:300]  # Truncate long content
            if content:
                memory_parts.append(f"- [{role}]: {content}")
        
        if len(memory_parts) > 1:
            logger.debug(f"Retrieved {len(results)} memory entries for context")
            return "\n".join(memory_parts)
        
        return ""
    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        return ""


def store_conversation_memory(
    conversation_id: str,
    message: str,
    role: str,
    page: Optional[str] = None,
    mentions: Optional[List[str]] = None
):
    """Store a conversation message in memory for future retrieval."""
    try:
        index = get_index()
        
        metadata = {}
        if page:
            metadata['page'] = page
        if mentions:
            metadata['mentions'] = ','.join(mentions[:5])  # Store first 5 mentions
        
        index.upsert_conversation(
            conversation_id=conversation_id,
            message=message,
            role=role,
            metadata=metadata
        )
        logger.debug(f"Stored {role} message in memory (conv={conversation_id[:8]}...)")
    except Exception as e:
        logger.warning(f"Failed to store conversation in memory: {e}")


def get_telemetry_context(query: str, max_results: int = 5) -> str:
    """
    Retrieve relevant telemetry events from journald/hwmon.
    
    Uses ChromaDB semantic search to find relevant system events.
    """
    try:
        index = get_index()
        
        # Check for error/warning keywords to search journald
        error_keywords = ['error', 'fail', 'crash', 'problem', 'issue', 'broke', 'not working']
        query_lower = query.lower()
        has_error_keywords = any(kw in query_lower for kw in error_keywords)
        
        context_parts = []
        
        # Search journald events
        if has_error_keywords:
            journald_results = index.query(
                text=query,
                k=max_results,
                collection="self_journald"
            )
            if journald_results:
                context_parts.append("**Recent relevant system logs:**")
                for r in journald_results[:3]:
                    msg = r.get('message', '')[:200]
                    sev = r.get('severity', 'info')
                    if msg:
                        context_parts.append(f"- [{sev}] {msg}")
        
        # Search hwmon events for thermal keywords
        thermal_keywords = ['temp', 'hot', 'thermal', 'heat', 'fan', 'cooling', 'cpu', 'gpu']
        has_thermal = any(kw in query_lower for kw in thermal_keywords)
        
        if has_thermal:
            hwmon_results = index.query(
                text=query,
                k=3,
                collection="self_hwmon"
            )
            if hwmon_results:
                context_parts.append("**Recent sensor readings:**")
                for r in hwmon_results[:3]:
                    msg = r.get('message', '')
                    label = (r.get('data') or {}).get('label', '')
                    if msg:
                        context_parts.append(f"- {label}: {msg}")
        
        if context_parts:
            logger.debug(f"Retrieved telemetry context for query")
            return "\n".join(context_parts)
        
        return ""
    except Exception as e:
        logger.debug(f"Telemetry retrieval failed: {e}")
        return ""


def get_docs_context(query: str, max_results: int = 3) -> str:
    """
    Retrieve relevant Linux documentation for the query.
    
    Uses ChromaDB semantic search over indexed man pages, Arch Wiki, etc.
    Enhanced with Self-RAG inspired relevance filtering.
    """
    try:
        from ...rag.document_indexer import query_docs
        
        # Retrieve more candidates for filtering (Self-RAG style)
        results = query_docs(query, k=max_results * 2, use_reranking=False)
        
        if not results:
            return ""
        
        # Self-RAG inspired relevance filtering
        # Filter out low-relevance results based on distance score
        filtered_results = []
        for r in results:
            distance = r.get('distance')
            # ChromaDB distance: lower is better, typically 0.0-2.0 range
            # Filter out results with distance > 1.5 (weak matches)
            if distance is None or distance < 1.5:
                filtered_results.append(r)
        
        # Take top results after filtering
        filtered_results = filtered_results[:max_results]
        
        if not filtered_results:
            return ""
        
        context_parts = ["**Relevant documentation:**"]
        for r in filtered_results:
            title = r.get('title', 'Unknown')
            source = r.get('source_type', r.get('source', ''))
            content = r.get('content', r.get('text', ''))[:400]
            
            # Include relevance indicator if rerank score available
            score_info = ""
            if r.get('rerank_score'):
                score = r['rerank_score']
                if score > 5:
                    score_info = " ★"  # High confidence
            
            if title and content:
                context_parts.append(f"- **{title}** ({source}){score_info}: {content}")
        
        if len(context_parts) > 1:
            logger.debug(f"Retrieved {len(filtered_results)} doc entries for context (filtered from {len(results)})")
            return "\n".join(context_parts)
        
        return ""
    except Exception as e:
        logger.debug(f"Doc retrieval failed: {e}")
        return ""


def get_discovery_context(query: str, max_results: int = 5) -> str:
    """
    Semantic search over system discoveries.
    
    Uses ChromaDB to find discoveries relevant to the query,
    even if not on the current page.
    """
    try:
        from ..routes.discovery import get_engine
        
        engine = get_engine()
        if not engine.use_chromadb:
            return ""
        
        # Use semantic search
        discoveries = engine.search(query, limit=max_results)
        
        if not discoveries:
            return ""
        
        context_parts = ["**Relevant system discoveries:**"]
        for d in discoveries:
            status_str = f" ({d.status})" if d.status else ""
            context_parts.append(f"- [{d.type.value}] **{d.title}**{status_str}")
            if d.description:
                context_parts.append(f"  {d.description[:150]}")
        
        if len(context_parts) > 1:
            logger.debug(f"Retrieved {len(discoveries)} discoveries via semantic search")
            return "\n".join(context_parts)
        
        return ""
    except Exception as e:
        logger.debug(f"Discovery search failed: {e}")
        return ""


def get_self_knowledge_context(query: str, max_results: int = 5) -> tuple[str, dict]:
    """
    Retrieve relevant self-knowledge for context using Self-RAG reflection.
    
    This is the system's persistent understanding of ITSELF:
    - Core identity (hostname, OS, hardware)
    - Configuration rationale (WHY things are set up)
    - Component roles and relationships
    - User-taught knowledge
    
    Uses Phase 28/29 Self-RAG and CRAG evaluation for quality retrieval.
    
    Returns:
        Tuple of (context_string, reflection_metadata)
    """
    try:
        from ...knowledge import get_self_knowledge, SelfReflector
        
        # Use SelfReflector for quality-scored retrieval (Phase 28/29)
        reflector = SelfReflector()
        result = reflector.reflect(query, max_contexts=max_results)
        
        # Build context from scored results
        context_parts = []
        for ctx in result.retrieved_contexts:
            context_parts.append(f"[{ctx.entry.type.value}] {ctx.entry.subject}: {ctx.entry.content}")
        
        # Add graph context if available
        if result.graph_context:
            context_parts.append(f"[Relationships] {result.graph_context}")
        
        context = "\n".join(context_parts) if context_parts else ""
        
        # Return metadata for debugging/display
        metadata = {
            "crag_action": result.crag_action.value,
            "confidence": result.confidence.value,
            "retrieve_token": result.retrieve_token.value if result.retrieve_token else None,
            "contexts_found": len(result.retrieved_contexts),
            "reflection_time_ms": result.reflection_time_ms,
        }
        
        logger.debug(f"Self-RAG reflection: CRAG={result.crag_action.value}, confidence={result.confidence.value}")
        
        return context, metadata
    except Exception as e:
        logger.debug(f"Self-knowledge retrieval failed: {e}")
        return "", {}


# Model routing functions extracted to model/client.py to break circular
# dependency between agent.py and chat.py. Re-exported here for backward
# compatibility with any code that still imports from chat.py.
from ...model.client import (
    get_ollama_endpoint,
    get_configured_model,
    get_specialist_model,
    get_vision_model,
    call_llm_chat,
    _estimate_tokens,
    _truncate_messages_for_context,
)
from ...model.client import _score_query_complexity


def get_loaded_models(endpoint: str = None, provider: str = "ollama") -> List[dict]:
    """
    Get list of currently loaded/available models from LLM server.
    
    For Ollama: Uses GET /api/ps endpoint (shows loaded models in VRAM).
    For OpenAI-compatible: Uses GET /v1/models endpoint (shows available models).
    
    Returns list of model info dicts with keys: name/id, etc.
    """
    if endpoint is None:
        endpoint = get_ollama_endpoint()
    
    try:
        if provider == "openai":
            # OpenAI-compatible API (LM Studio, vLLM, etc.)
            response = requests.get(f"{endpoint}/v1/models", timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Convert OpenAI format to common format
                models = []
                for m in data.get('data', []):
                    models.append({'name': m.get('id', ''), 'id': m.get('id', '')})
                return models
            return []
        else:
            # Ollama API
            response = requests.get(f"{endpoint}/api/ps", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('models', [])
            return []
    except Exception as e:
        logger.debug(f"Could not get loaded models: {e}")
        return []


def is_model_loaded(model_name: str, endpoint: str = None, provider: str = "ollama") -> bool:
    """Check if a specific model is currently loaded/available."""
    loaded = get_loaded_models(endpoint, provider)
    for m in loaded:
        # Model names may include tags like "llama3.1:8b" or just "llama3.1"
        loaded_name = m.get('name', m.get('id', ''))
        if loaded_name == model_name or loaded_name.startswith(model_name + ':'):
            return True
        # Also check if provided name is a prefix (user might say "llama3.1" but loaded is "llama3.1:8b")
        if model_name.startswith(loaded_name.split(':')[0]):
            return True
    return False


def get_model_status(model_name: str = None, endpoint: str = None) -> dict:
    """
    Get detailed status of a model.
    
    Returns dict with:
        - loaded: bool - is the model currently in memory
        - loading: bool - is the model currently loading (inferred)
        - size_vram: int - VRAM usage in bytes (if loaded)
        - expires_at: str - when model will be unloaded (if loaded)
        - model: str - model name checked
    """
    if model_name is None:
        model_name = get_configured_model()
    if endpoint is None:
        endpoint = get_ollama_endpoint()
    
    loaded_models = get_loaded_models(endpoint)
    
    for m in loaded_models:
        loaded_name = m.get('name', '')
        if loaded_name == model_name or loaded_name.startswith(model_name.split(':')[0]):
            return {
                'loaded': True,
                'loading': False,
                'model': loaded_name,
                'size_vram': m.get('size_vram', 0),
                'size': m.get('size', 0),
                'expires_at': m.get('expires_at', ''),
                'details': m.get('details', {})
            }
    
    return {
        'loaded': False,
        'loading': False,  # We can't directly detect loading state
        'model': model_name,
        'size_vram': 0,
        'size': 0,
        'expires_at': '',
        'details': {}
    }


# Phase 12d: Tool-use support
def call_ollama_with_tools(prompt: str, system_prompt: str, model: str = None) -> tuple:
    """
    Call Ollama with tool support using the /api/chat endpoint.
    
    Returns (response_text, tool_calls) where tool_calls is a list of
    tool invocations if the LLM wants to use tools.
    """
    try:
        from ...tools.system_tools import SYSTEM_TOOLS, execute_tool
        
        # Smart routing: use specialist for complex queries
        # Note: Tool calling currently only works with Ollama, not OpenAI-compatible APIs
        if model is None:
            specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
            if specialist_model and specialist_provider == "ollama":
                complexity_score = _score_query_complexity(prompt)
                if complexity_score >= 0.5:
                    model = specialist_model
                    endpoint = specialist_endpoint
                    logger.info(f"Tool-calling with specialist: {model} (complexity: {complexity_score:.2f})")
                else:
                    model = get_configured_model()
                    endpoint = get_ollama_endpoint()
                    logger.info(f"Tool-calling with guide: {model} (complexity: {complexity_score:.2f})")
            else:
                model = get_configured_model()
                endpoint = get_ollama_endpoint()
        else:
            endpoint = get_ollama_endpoint()
        
        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # First call - with tools
        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "tools": SYSTEM_TOOLS,
                "stream": False
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        message = data.get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        if not tool_calls:
            # No tool calls - check if model incorrectly output function call JSON as text
            content = message.get("content", "")
            
            # Detect if model output looks like a raw function call (common with models
            # that don't support native tool calling)
            if content and ('{"name":' in content or '"function"' in content or 
                           'get_network_info' in content or 'get_disk_usage' in content):
                logger.warning("Model output appears to contain raw tool call JSON - falling back to standard generation")
                return None, []  # Fall back to standard generation
            
            return content, []
        
        # Execute tool calls
        logger.info(f"LLM requested {len(tool_calls)} tool calls")
        tool_results = []
        
        for tool_call in tool_calls:
            func = tool_call.get("function", {})
            tool_name = func.get("name", "")
            arguments = func.get("arguments", {})
            
            # Phase 23: Check authorization before execution
            auth = check_tool_authorization(tool_name, arguments)
            
            if not auth["allowed"]:
                logger.warning(f"Tool {tool_name} blocked: {auth['reason']}")
                tool_results.append({
                    "tool": tool_name,
                    "result": {"error": f"Blocked: {auth['reason']}", "blocked": True}
                })
                continue
            
            if auth["approval_required"]:
                logger.info(f"Tool {tool_name} requires approval")
                # Create actual approval request
                approval_request = create_tool_approval_request(
                    tool_name=tool_name,
                    tool_args=arguments,
                    reason=auth.get("reason", "This action requires user approval before execution")
                )
                tool_results.append({
                    "tool": tool_name,
                    "result": {
                        "pending_approval": True, 
                        "approval_id": approval_request.id,
                        "message": f"Action queued for approval. Check the Approvals page to approve request {approval_request.id}"
                    }
                })
                continue
            
            # Run dry-run simulation if required
            simulation_result = None
            if auth.get("simulation_required"):
                logger.info(f"Running dry-run simulation for {tool_name}")
                try:
                    from ...approval.simulator import DryRunSimulator
                    simulator = DryRunSimulator()
                    
                    # Route to appropriate simulation
                    if tool_name == "write_config":
                        path = arguments.get("path", "")
                        content = arguments.get("content", "")
                        simulation_result = simulator.simulate_file_write(path, content)
                    elif tool_name in ["run_command", "execute_shell"]:
                        cmd = arguments.get("command", "")
                        simulation_result = simulator.simulate_command(cmd)
                    elif tool_name == "restart_service":
                        service = arguments.get("service", "")
                        simulation_result = simulator.simulate_service_restart(service)
                    
                    if simulation_result and simulation_result.warnings:
                        logger.warning(f"Simulation warnings: {simulation_result.warnings}")
                except Exception as e:
                    logger.error(f"Simulation failed for {tool_name}: {e}")
            
            # Execute the tool
            result = execute_tool(tool_name, arguments)
            tool_result_entry = {
                "tool": tool_name,
                "result": result.data if result.success else {"error": result.error}
            }
            
            # Include simulation preview if available
            if simulation_result:
                tool_result_entry["simulation"] = {
                    "action": simulation_result.action,
                    "changes": simulation_result.changes,
                    "warnings": simulation_result.warnings,
                    "reversible": simulation_result.reversible,
                    "rollback_strategy": simulation_result.rollback_strategy
                }
            
            tool_results.append(tool_result_entry)
        
        # Add assistant message with tool calls and tool results
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls
        })
        
        # Add tool results as tool messages
        for i, tool_call in enumerate(tool_calls):
            messages.append({
                "role": "tool",
                "content": json.dumps(tool_results[i]["result"])
            })
        
        # Second call - get final response with tool results
        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        final_response = data.get("message", {}).get("content", "")
        return final_response, tool_results
        
    except Exception as e:
        logger.error(f"Tool-calling failed: {e}")
        return None, []


def should_use_tools(query: str) -> bool:
    """Determine if a query would benefit from tool use."""
    tool_keywords = [
        # Disk/storage real-time queries
        'how much space', 'disk space', 'storage left', 'is full', 'running out',
        # Service status queries
        'is running', 'service status', 'check if', 'running services',
        # Process queries
        'process running', 'is alive', 'memory usage', 'cpu usage',
        # System load
        'system load', 'how loaded', 'performance',
        # Logs
        'recent errors', 'check logs', 'log entries', 'what happened',
        # Network
        'network status', 'ip address', 'connected'
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in tool_keywords)


def call_ollama_with_images(
    message: str, 
    images: List[str], 
    system_prompt: str = "",
    model: str = None,
    endpoint: str = None,
    history: List[dict] = None
) -> str:
    """
    Call Ollama with images for vision model support.
    
    Args:
        message: The user's text message
        images: List of base64-encoded images
        system_prompt: Optional system prompt
        model: Optional model override (defaults to vision model)
        endpoint: Optional endpoint override (defaults to configured endpoint)
        history: Optional conversation history for context
    
    Returns:
        The AI response text
    """
    try:
        # Use vision model by default
        if endpoint is None:
            _, endpoint = get_vision_model()
        if model is None:
            model, _ = get_vision_model()
        
        # Build messages with system prompt and history
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history for context (without images - too large)
        if history:
            for msg in history[:-1]:  # Skip current message, will add with images
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")[:1500]  # Truncate for token limits
                })
        
        # Current user message with images
        user_message = {"role": "user", "content": message}
        if images:
            user_message["images"] = images
        messages.append(user_message)
        
        logger.info(f"Calling Ollama vision model: {model} with {len(images)} images, {len(messages)-1} history messages")
        
        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 2048
                }
            },
            timeout=180  # Longer timeout for vision processing
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("message", {}).get("content", "")
        else:
            logger.error(f"Ollama vision call failed: {response.status_code}")
            return f"Sorry, the vision model returned an error (status {response.status_code}). Make sure you're using a vision-capable model like llava."
            
    except requests.exceptions.Timeout:
        logger.error("Ollama vision call timed out")
        return "The image processing timed out. The image may be too large or the model may be loading."
    except Exception as e:
        logger.error(f"Ollama vision call failed: {e}")
        return f"Sorry, I couldn't process the image: {str(e)}"


# Topic detection for query-aware context injection (Phase 12b)
TOPIC_KEYWORDS = {
    'storage': ['disk', 'filesystem', 'mount', 'zfs', 'btrfs', 'bcachefs', 'ext4', 'nvme', 'ssd', 'raid', 'partition', 'volume', 'drive', 'storage', 'hdd', 'space', 'full'],
    'backup': ['backup', 'restore', 'rsync', 'borg', 'snapshot', 'timeshift', 'archive', 'recovery'],
    'service': ['service', 'systemd', 'daemon', 'process', 'restart', 'start', 'stop', 'status', 'running', 'failed', 'enabled'],
    'network': ['network', 'wifi', 'ethernet', 'dns', 'firewall', 'ip', 'port', 'internet', 'connection', 'ping', 'ssh'],
    'security': ['ssh', 'sudo', 'permission', 'firewall', 'fail2ban', 'root', 'password', 'key', 'certificate', 'ssl'],
}

# Web search trigger patterns
WEB_SEARCH_PATTERNS = [
    'latest version', 'current version', 'newest version',
    'how to install', 'best practices', 'recommended',
    'up to date', 'out of date', 'outdated',
    'cve', 'security advisory', 'vulnerability',
    'download', 'release notes', 'changelog',
    'compare', 'vs', 'versus', 'difference between',
    'tutorial', 'guide', 'documentation',
]


def should_use_web_search(query: str, rag_results: Optional[List[Dict]] = None) -> bool:
    """
    Determine if a query would benefit from web search.
    
    Returns True if the query:
    - Contains patterns suggesting need for current info
    - Asks about versions, best practices, etc.
    - Contains words suggesting external research needed
    - RAG results are stale for volatile sources
    """
    query_lower = query.lower()
    
    # Check for trigger patterns
    for pattern in WEB_SEARCH_PATTERNS:
        if pattern in query_lower:
            return True
    
    # Check for question words combined with version/update keywords
    question_words = ['what', 'which', 'how', 'where', 'when']
    update_words = ['version', 'update', 'upgrade', 'install', 'download', 'release']
    
    has_question = any(w in query_lower for w in question_words)
    has_update = any(w in query_lower for w in update_words)
    
    if has_question and has_update:
        return True
    
    # Check RAG result freshness if provided
    if rag_results:
        try:
            from ...rag.freshness import get_freshness_checker
            checker = get_freshness_checker()
            should_live, reason = checker.should_prefer_live_search(query, rag_results)
            if should_live:
                logger.debug(f"Freshness check recommends web search: {reason}")
                return True
        except Exception as e:
            logger.debug(f"Freshness check failed: {e}")
    
    return False


async def get_web_search_context(query: str, max_results: int = 5) -> str:
    """
    Get web search results as context for the LLM.
    
    Uses SearXNG public instances for web grounding.
    """
    try:
        from ...web.search import get_web_search
        
        ws = get_web_search()
        context = await ws.search_for_rag(query, max_results=max_results)
        
        if context:
            logger.info(f"Web search returned context for: {query[:50]}...")
            return f"\n=== WEB SEARCH RESULTS ===\n{context}"
        
        return ""
        
    except ImportError:
        logger.debug("Web search module not available")
        return ""
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return ""

TOPIC_TO_DISCOVERY_TYPE = {
    'storage': DiscoveryType.STORAGE,
    'backup': DiscoveryType.BACKUP,
    'service': DiscoveryType.SERVICE,
    'network': DiscoveryType.NETWORK,
    'security': DiscoveryType.SECURITY,
}


def detect_query_topics(query: str) -> List[str]:
    """Detect relevant topics from user query."""
    query_lower = query.lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            topics.append(topic)
    return topics


def get_topic_context(query: str) -> str:
    """
    Inject relevant discovery context based on detected topics.
    
    This is Phase 12b - Query-Aware Context Injection.
    """
    try:
        engine = get_engine()
        topics = detect_query_topics(query)
        
        if not topics:
            return ""
        
        context_parts = []
        for topic in topics:
            discovery_type = TOPIC_TO_DISCOVERY_TYPE.get(topic)
            if not discovery_type:
                continue
            
            discoveries = engine.get_by_type(discovery_type)
            
            # For storage queries, be more detailed
            if topic == 'storage' and discoveries:
                context_parts.append(f"\n=== STORAGE CONTEXT ===")
                for d in discoveries[:10]:
                    if d.chat_context:
                        context_parts.append(f"• {d.chat_context}")
            
            # For backup queries
            elif topic == 'backup' and discoveries:
                context_parts.append(f"\n=== BACKUP CONTEXT ===")
                for d in discoveries[:5]:
                    if d.chat_context:
                        context_parts.append(f"• {d.chat_context}")
            
            # For service queries - show relevant ones
            elif topic == 'service':
                # Search for services mentioned in query
                query_lower = query.lower()
                relevant = [d for d in discoveries if any(
                    kw in d.name.lower() or kw in d.title.lower()
                    for kw in query_lower.split()
                )][:5]
                if relevant:
                    context_parts.append(f"\n=== SERVICE CONTEXT ===")
                    for d in relevant:
                        if d.chat_context:
                            context_parts.append(f"• {d.chat_context}")
            
            # Generic fallback
            elif discoveries:
                context_parts.append(f"\n=== {topic.upper()} CONTEXT ===")
                for d in discoveries[:3]:
                    if d.chat_context:
                        context_parts.append(f"• {d.chat_context}")
        
        return "\n".join(context_parts) if context_parts else ""
    except Exception as e:
        logger.warning(f"Failed to get topic context: {e}")
        return ""


def get_system_identity() -> str:
    """
    Generate a concise system identity summary for LLM context.
    
    This is the "Who Am I" that grounds the LLM in THIS specific system.
    Uses the comprehensive SystemProfiler if available.
    """
    try:
        # Try to use the full system profile first
        try:
            from ...discovery.scanners.system_profile import get_system_profiler
            profiler = get_system_profiler()
            
            # Load from disk if not in memory
            if not profiler.profile:
                profiler.load_profile()
            
            if profiler.profile:
                return profiler.get_summary()
        except Exception as e:
            logger.debug(f"System profile not available, using basic identity: {e}")
        
        # Fallback to basic identity
        from ...utils.platform import get_linux_distro, is_linux, is_macos
        
        engine = get_engine()
        
        lines = ["=== THIS SYSTEM ==="]
        lines.append(f"Hostname: {socket.gethostname()}")
        
        # OS and package manager - CRITICAL for command generation
        if is_linux():
            distro = get_linux_distro()
            lines.append(f"OS: {distro['name']} {distro['version']} ({distro['family']} family)")
            lines.append(f"Package Manager: {distro['package_manager']}")
            lines.append(f"IMPORTANT: Use '{distro['package_manager']}' for package operations, NOT other package managers!")
        elif is_macos():
            import platform as plat
            lines.append(f"OS: macOS {plat.mac_ver()[0]}")
            lines.append("Package Manager: brew (Homebrew)")
        else:
            lines.append(f"OS: {socket.gethostname()}")
        
        # Get storage discoveries
        storage = engine.get_by_type(DiscoveryType.STORAGE)
        filesystems = [d for d in storage if d.name.startswith('fs-')]
        disks = [d for d in storage if d.name.startswith('disk-') or d.name.startswith('md-')]
        
        # Collect filesystem types present
        fstypes_present = set()
        
        if filesystems:
            lines.append("\nFilesystems mounted:")
            for fs in filesystems:
                fstype = fs.data.get('fstype', 'unknown')
                fstypes_present.add(fstype.lower())
                mountpoint = fs.data.get('mountpoint', '/')
                size = fs.data.get('size', '?')
                lines.append(f"  - {fstype} at {mountpoint} ({size})")
        
        if disks:
            lines.append("\nStorage devices:")
            for disk in disks[:5]:  # Limit to 5
                lines.append(f"  - {disk.title}")
        
        # CRITICAL: What's NOT on this system
        lines.append("\nNOT present on this system:")
        common_fs = {'zfs', 'btrfs', 'bcachefs', 'xfs', 'ext4'}
        missing = common_fs - fstypes_present
        for fs in sorted(missing):
            if fs in ('zfs', 'btrfs', 'bcachefs'):  # Only mention notable ones
                lines.append(f"  - {fs.upper()} (no {fs} filesystems detected)")
        
        # Services summary
        services = engine.get_by_type(DiscoveryType.SERVICE)
        if services:
            running = [s for s in services if s.status == 'Running']
            lines.append(f"\nServices: {len(running)} running")
        
        lines.append("===================")
        
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to generate system identity: {e}")
        return ""


def get_custom_ai_rules() -> str:
    """
    Load user-defined AI rules/guardrails.
    
    These are custom rules the user has added to handle edge cases,
    like "bcachefs requires kernel 6.8" or "Docker storage is at /data/docker".
    """
    try:
        from ...utils.platform import get_config_dir
        import yaml
        
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if not config_path.exists():
            return ""
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        rules = data.get('rules', [])
        enabled_rules = [r for r in rules if r.get('enabled', True)]
        
        if not enabled_rules:
            return ""
        
        lines = ["\n=== USER-DEFINED RULES (IMPORTANT) ==="]
        lines.append("The administrator has set the following rules. ALWAYS follow these:")
        
        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        enabled_rules.sort(key=lambda r: priority_order.get(r.get('priority', 'medium'), 1))
        
        for rule in enabled_rules:
            priority = rule.get('priority', 'medium').upper()
            category = rule.get('category', 'general')
            lines.append(f"• [{priority}] ({category}) {rule['rule']}")
        
        lines.append("======================================")
        
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to load custom AI rules: {e}")
        return ""


router = APIRouter() if FASTAPI_AVAILABLE else None

# Singleton model router for chat
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the model router singleton."""
    global _model_router
    if _model_router is None:
        try:
            _model_router = ModelRouter()
            logger.info("ModelRouter initialized for chat")
        except Exception as e:
            logger.error(f"Failed to initialize ModelRouter: {e}")
            raise
    return _model_router


class ChatMessage(BaseModel):
    role: str  # 'user', 'assistant', 'system'
    content: str


class ChatRequest(BaseModel):
    message: str
    mentions: List[str] = []
    history: List[ChatMessage] = []
    persona: str = "guide"  # 'guide' for dashboard, 'coder' for terminal
    debug: bool = False  # Enable debug info in response
    current_page: str = ""  # Current page/tab user is on (e.g., 'network', 'storage')
    page_context: str = ""  # Visible items/state from the page
    images: List[str] = []  # Vision model: Base64 encoded images
    conversation_id: str = ""  # Conversation ID for memory storage/retrieval
    use_react: bool = False  # Phase 21: Enable ReAct reasoning loop


class ThinkingStepModel(BaseModel):
    """A single step in the ReAct thinking process."""
    type: str  # thought, action, observation, final
    content: str
    duration_ms: int = 0
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[dict] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    mentions_resolved: List[dict] = []
    suggested_actions: List[dict] = []
    debug: Optional[dict] = None  # Debug info when requested
    # Phase 21: ReAct thinking steps
    thinking_steps: List[ThinkingStepModel] = []
    thinking_duration_ms: int = 0
    used_react: bool = False  # Whether ReAct loop was used


if FASTAPI_AVAILABLE:
    
    @router.post("/send", response_model=ChatResponse)
    async def send_message(request: ChatRequest):
        """
        Send a chat message and get AI response.
        
        For MVP, uses rule-based responses.
        TODO: Connect to actual LLM (Ollama, etc.)
        """
        import time
        start_time = time.time()
        
        message = request.message.strip()
        mentions = request.mentions
        persona = request.persona
        debug_mode = request.debug
        current_page = request.current_page
        page_context = request.page_context
        
        # Phase 43: Safety validation on input
        try:
            validator = get_safety_validator()
            input_check = validator.validate_input(message)
            if not input_check.allowed:
                logger.warning(f"Input blocked by safety validator: {input_check.reason}")
                return ChatResponse(
                    response="I noticed your message contains patterns that could be interpreted as an attempt to modify my behavior. Please rephrase your request.",
                    thinking_steps=[],
                    sources=[],
                    tool_results=[],
                    error=None,
                    debug_info={"safety_blocked": True, "reason": input_check.reason} if debug_mode else None
                )
        except Exception as e:
            logger.debug(f"Safety validation skipped: {e}")
        
        # Debug info collection
        debug_info = {
            'persona': persona,
            'mentions_count': len(mentions),
            'message_length': len(message),
            'auto_injected_context': [],
            'model_used': None,
            'endpoint_used': None,
            'prompt_tokens_estimate': 0,
            'generation_time_ms': 0,
            'tool_calls': [],
        } if debug_mode else None
        
        # Resolve mentions to get context
        mentions_resolved = []
        context_parts = []
        
        engine = get_engine()
        
        # Auto-inject context based on message content (Phase 13 smart context)
        message_lower = message.lower()
        auto_injected_types = set()
        
        # FIRST: Inject self-knowledge (core identity + relevant knowledge)
        # This gives the system its persistent understanding of itself
        # Uses Phase 28/29 Self-RAG reflection and CRAG evaluation
        self_knowledge_context, reflection_metadata = get_self_knowledge_context(message, max_results=5)
        if self_knowledge_context:
            context_parts.append(self_knowledge_context)
            auto_injected_types.add('self_knowledge')
            if debug_info:
                debug_info['auto_injected_context'].append({'type': 'self_knowledge', 'count': 5})
                debug_info['self_rag_reflection'] = reflection_metadata
            logger.debug(f"Injected self-knowledge context (CRAG: {reflection_metadata.get('crag_action', 'unknown')})")
        
        # Inject page context if available (Phase 17: UI awareness)
        if current_page and page_context:
            context_parts.append(
                f"**User is currently on the {current_page.title()} page.**\n"
                f"Visible items:\n{page_context}"
            )
            if debug_info:
                debug_info['auto_injected_context'].append({'type': 'page_context', 'page': current_page})
            logger.debug(f"Injected page context for: {current_page}")
        elif current_page:
            # Even without specific context, knowing the page helps
            context_parts.append(f"**User is currently viewing the {current_page.title()} page.**")
        
        # Retrieve relevant context from memory (ChromaDB semantic search)
        conversation_id = request.conversation_id or None
        memory_context = get_memory_context(message, conversation_id, max_results=3)
        if memory_context:
            context_parts.append(memory_context)
            auto_injected_types.add('memory')
            if debug_info:
                debug_info['auto_injected_context'].append({'type': 'memory', 'count': 3})
            logger.debug("Injected memory context from ChromaDB")
        
        # Retrieve relevant telemetry (journald/hwmon events)
        telemetry_context = get_telemetry_context(message, max_results=5)
        if telemetry_context:
            context_parts.append(telemetry_context)
            auto_injected_types.add('telemetry')
            if debug_info:
                debug_info['auto_injected_context'].append({'type': 'telemetry', 'count': 5})
            logger.debug("Injected telemetry context from ChromaDB")
        
        # Retrieve relevant Linux documentation (man pages, Arch Wiki, etc.)
        # Only for questions that seem to need documentation
        doc_keywords = ['how', 'what', 'configure', 'setup', 'install', 'command', 'option', 
                       'flag', 'syntax', 'example', 'manual', 'help', 'man', 'usage']
        if any(kw in message_lower for kw in doc_keywords):
            docs_context = get_docs_context(message, max_results=3)
            if docs_context:
                context_parts.append(docs_context)
                auto_injected_types.add('docs')
                if debug_info:
                    debug_info['auto_injected_context'].append({'type': 'docs', 'count': 3})
                logger.debug("Injected documentation context from ChromaDB")
        
        # Semantic search over system discoveries (finds relevant discoveries across all types)
        # This uses ChromaDB embeddings for better matching than keyword-based injection
        discovery_context = get_discovery_context(message, max_results=5)
        if discovery_context:
            context_parts.append(discovery_context)
            auto_injected_types.add('discovery_search')
            if debug_info:
                debug_info['auto_injected_context'].append({'type': 'discovery_search', 'count': 5})
            logger.debug("Injected discovery context via semantic search")
        
        # CRITICAL: When asking about failures, inject ALL failed/error discoveries
        # This enables correlation (failed service + failed disk = hardware issue)
        failure_keywords = ['fail', 'error', 'broken', 'down', 'not working', 'issue', 'problem', 
                           'wrong', 'crash', 'stopped', 'unable', 'cannot', 'can\'t', 'why']
        if any(kw in message_lower for kw in failure_keywords):
            try:
                # Find ALL discoveries with failed/error/problematic status
                # Include: failed, error, down, critical, warning, missing, unmounted, smart (failures)
                problem_indicators = ['fail', 'error', 'down', 'critical', 'warning', 'missing', 
                                      'unmounted', 'smart', 'degraded', 'offline', 'inactive']
                failed_discoveries = [
                    d for d in engine.get_all() 
                    if d.status and any(s in d.status.lower() for s in problem_indicators)
                ]
                if failed_discoveries:
                    failure_summary = ["**⚠️ RELATED ISSUES ON THIS SYSTEM (correlate these!):**"]
                    for d in failed_discoveries[:15]:
                        detail = f"- [{d.type.value.upper()}] {d.title}: {d.status}"
                        if d.status_detail:
                            detail += f" - {d.status_detail}"
                        # Include device membership if available (critical for pool correlation)
                        if hasattr(d, 'data') and d.data:
                            if d.data.get('devices'):
                                detail += f" (devices: {', '.join(d.data['devices'][:5])})"
                            if d.data.get('pool') or d.data.get('pool_name'):
                                detail += f" (pool: {d.data.get('pool') or d.data.get('pool_name')})"
                            if d.data.get('mount_point'):
                                detail += f" (mount: {d.data.get('mount_point')})"
                        failure_summary.append(detail)
                    
                    # Add explicit correlation hint
                    failure_summary.append("\n**IMPORTANT**: If a disk has SMART failure and belongs to a pool that won't mount, the disk failure is likely the root cause!")
                    context_parts.insert(0, "\n".join(failure_summary))  # Insert at top for visibility
                    auto_injected_types.add('failures')
                    logger.info(f"Injected {len(failed_discoveries)} correlated failure discoveries")
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'failures', 'count': len(failed_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to inject failure context: {e}")
        
        # Storage/disk/filesystem keywords -> auto-inject storage context
        storage_keywords = ['disk', 'storage', 'drive', 'filesystem', 'mount', 'bcachefs', 
                           'btrfs', 'zfs', 'raid', 'nvme', 'ssd', 'hdd', 'partition']
        if any(kw in message_lower for kw in storage_keywords):
            # Get all storage discoveries for context
            try:
                storage_discoveries = [d for d in engine.get_all() if d.type.value == 'storage']
                if storage_discoveries:
                    storage_summary = []
                    for d in storage_discoveries[:10]:  # Limit to avoid huge context
                        storage_summary.append(f"- {d.title}: {d.description}")
                    if storage_summary:
                        context_parts.append(
                            "**Detected Storage on this system:**\n" + "\n".join(storage_summary)
                        )
                        auto_injected_types.add('storage')
                        logger.debug(f"Auto-injected storage context: {len(storage_discoveries)} discoveries")
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'storage', 'count': len(storage_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject storage context: {e}")
        
        # Backup keywords -> auto-inject backup context
        backup_keywords = ['backup', 'timeshift', 'snapshot', 'restore', 'rsync', 'borg']
        if any(kw in message_lower for kw in backup_keywords):
            try:
                backup_discoveries = [d for d in engine.get_all() if d.type.value == 'backup']
                if backup_discoveries:
                    backup_summary = []
                    for d in backup_discoveries[:10]:
                        backup_summary.append(f"- {d.title}: {d.description}")
                    if backup_summary:
                        context_parts.append(
                            "**Detected Backups on this system:**\n" + "\n".join(backup_summary)
                        )
                        auto_injected_types.add('backup')
                        logger.debug(f"Auto-injected backup context: {len(backup_discoveries)} discoveries")
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'backup', 'count': len(backup_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject backup context: {e}")
        
        # Service keywords -> auto-inject service context
        service_keywords = ['service', 'systemd', 'daemon', 'running', 'status']
        if any(kw in message_lower for kw in service_keywords):
            try:
                service_discoveries = [d for d in engine.get_all() if d.type.value == 'service']
                if service_discoveries:
                    service_summary = []
                    for d in service_discoveries[:15]:
                        service_summary.append(f"- {d.title}: {d.status}")
                    if service_summary:
                        context_parts.append(
                            "**Detected Services on this system:**\n" + "\n".join(service_summary)
                        )
                        auto_injected_types.add('service')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'service', 'count': len(service_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject service context: {e}")
        
        # Network keywords -> auto-inject network context
        network_keywords = ['network', 'interface', 'ethernet', 'wifi', 'bridge', 'bond', 
                           'ip', 'connected', 'down', 'up', 'mac', 'tailscale', 'vpn',
                           'firewall', 'port', 'eno', 'enp', 'eth', 'wlan']
        if any(kw in message_lower for kw in network_keywords):
            try:
                network_discoveries = [d for d in engine.get_all() if d.type.value == 'network']
                if network_discoveries:
                    network_summary = []
                    # Prioritize interfaces, then firewall, then ports
                    interfaces = [d for d in network_discoveries if d.name.startswith('iface-')]
                    firewalls = [d for d in network_discoveries if d.name.startswith('firewall-')]
                    
                    for d in interfaces[:10]:
                        # Include more detail: type, status, IP, and bridge info
                        iface_name = d.data.get('interface', d.name.replace('iface-', ''))
                        iface_type = d.data.get('type', 'Unknown')
                        status = d.status or 'Unknown'
                        ip = d.data.get('ipv4', 'No IP')
                        master = d.data.get('master', '')
                        config_path = d.data.get('config_path', '')
                        
                        detail = f"- {iface_name} ({iface_type}): {status}"
                        if d.data.get('ipv4'):
                            detail += f", IP: {ip}"
                        if master:
                            detail += f", bridged to {master}"
                        if config_path:
                            detail += f", config: {config_path}"
                        network_summary.append(detail)
                    
                    for d in firewalls[:2]:
                        network_summary.append(f"- Firewall ({d.data.get('tool', 'unknown')}): {d.status}")
                    
                    if network_summary:
                        context_parts.append(
                            "**Network Interfaces on this system:**\n" + "\n".join(network_summary)
                        )
                        auto_injected_types.add('network')
                        logger.debug(f"Auto-injected network context: {len(network_discoveries)} discoveries")
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'network', 'count': len(network_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject network context: {e}")
        
        # Security keywords -> auto-inject security context
        security_keywords = ['security', 'ssh', 'firewall', 'fail2ban', 'sudo', 'permission',
                            'user', 'password', 'key', 'certificate', 'ssl', 'tls', 'audit',
                            'login', 'root', 'admin', 'ufw', 'iptables', 'selinux', 'apparmor']
        if any(kw in message_lower for kw in security_keywords):
            try:
                security_discoveries = [d for d in engine.get_all() if d.type.value == 'security']
                if security_discoveries:
                    security_summary = []
                    for d in security_discoveries[:10]:
                        security_summary.append(f"- {d.title}: {d.status or d.description}")
                    if security_summary:
                        context_parts.append(
                            "**Security Status on this system:**\n" + "\n".join(security_summary)
                        )
                        auto_injected_types.add('security')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'security', 'count': len(security_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject security context: {e}")
        
        # Container/Docker keywords -> auto-inject container context
        container_keywords = ['container', 'docker', 'podman', 'kubernetes', 'k8s', 'compose',
                             'image', 'volume', 'registry', 'dockerfile', 'pod']
        if any(kw in message_lower for kw in container_keywords):
            try:
                container_discoveries = [d for d in engine.get_all() if d.type.value == 'container']
                if container_discoveries:
                    container_summary = []
                    for d in container_discoveries[:15]:
                        container_summary.append(f"- {d.title}: {d.status or d.description}")
                    if container_summary:
                        context_parts.append(
                            "**Containers on this system:**\n" + "\n".join(container_summary)
                        )
                        auto_injected_types.add('container')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'container', 'count': len(container_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject container context: {e}")
        
        # GPU keywords -> auto-inject GPU context
        gpu_keywords = ['gpu', 'nvidia', 'amd', 'graphics', 'cuda', 'rocm', 'vram', 'driver',
                       'opengl', 'vulkan', 'render', 'display', 'monitor', 'geforce', 'radeon']
        if any(kw in message_lower for kw in gpu_keywords):
            try:
                gpu_discoveries = [d for d in engine.get_all() if d.type.value == 'gpu']
                if gpu_discoveries:
                    gpu_summary = []
                    for d in gpu_discoveries[:5]:
                        gpu_summary.append(f"- {d.title}: {d.status or d.description}")
                    if gpu_summary:
                        context_parts.append(
                            "**GPU/Graphics on this system:**\n" + "\n".join(gpu_summary)
                        )
                        auto_injected_types.add('gpu')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'gpu', 'count': len(gpu_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject GPU context: {e}")
        
        # Sharing keywords -> auto-inject sharing context (SMB, NFS, etc.)
        sharing_keywords = ['share', 'sharing', 'smb', 'samba', 'nfs', 'cifs', 'mount',
                           'network drive', 'file share', 'windows share', 'rclone', 'fuse']
        if any(kw in message_lower for kw in sharing_keywords):
            try:
                sharing_discoveries = [d for d in engine.get_all() if d.type.value == 'sharing']
                if sharing_discoveries:
                    sharing_summary = []
                    for d in sharing_discoveries[:10]:
                        sharing_summary.append(f"- {d.title}: {d.status or d.description}")
                    if sharing_summary:
                        context_parts.append(
                            "**File Sharing on this system:**\n" + "\n".join(sharing_summary)
                        )
                        auto_injected_types.add('sharing')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'sharing', 'count': len(sharing_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject sharing context: {e}")
        
        # Development/Process keywords -> auto-inject development context
        dev_keywords = ['development', 'dev', 'process', 'server', 'port', 'node', 'python',
                       'npm', 'yarn', 'pip', 'venv', 'virtualenv', 'git', 'code', 'ide']
        if any(kw in message_lower for kw in dev_keywords):
            try:
                # Include both process and task discoveries for development context
                dev_discoveries = [d for d in engine.get_all() 
                                   if d.type.value in ('process', 'task')]
                if dev_discoveries:
                    dev_summary = []
                    for d in dev_discoveries[:10]:
                        dev_summary.append(f"- {d.title}: {d.status or d.description}")
                    if dev_summary:
                        context_parts.append(
                            "**Development/Processes on this system:**\n" + "\n".join(dev_summary)
                        )
                        auto_injected_types.add('development')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'development', 'count': len(dev_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject development context: {e}")
        
        # Performance/slow keywords -> inject process and thermal context
        perf_keywords = ['slow', 'fast', 'performance', 'lag', 'freeze', 'hang', 'cpu', 'ram', 
                        'memory', 'resource', 'hog', 'consuming', 'hot', 'temperature', 'thermal', 'fan']
        if any(kw in message_lower for kw in perf_keywords):
            try:
                process_discoveries = [d for d in engine.get_all() if d.type.value == 'process']
                hw_discoveries = [d for d in engine.get_all() if d.type.value == 'hardware']
                
                context_items = []
                # Add resource hogs
                for d in process_discoveries:
                    if d.data.get('is_resource_hog') or d.data.get('is_problem_process'):
                        context_items.append(f"- {d.title}: {d.status}")
                # Add thermal info
                for d in hw_discoveries:
                    if d.data.get('is_thermal') or d.data.get('is_fan'):
                        context_items.append(f"- {d.title}: {d.status}")
                
                if context_items:
                    context_parts.append("**Performance/Thermal Context:**\n" + "\n".join(context_items[:15]))
                    auto_injected_types.add('performance')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'performance', 'count': len(context_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject performance context: {e}")
        
        # Package/update keywords -> inject package context
        pkg_keywords = ['update', 'upgrade', 'install', 'package', 'apt', 'dnf', 'pacman', 
                       'orphan', 'held', 'lock', 'broken']
        if any(kw in message_lower for kw in pkg_keywords):
            try:
                pkg_discoveries = [d for d in engine.get_all() if d.type.value == 'package']
                if pkg_discoveries:
                    pkg_summary = []
                    for d in pkg_discoveries[:10]:
                        pkg_summary.append(f"- {d.title}: {d.status}")
                    if pkg_summary:
                        context_parts.append("**Package Management:**\n" + "\n".join(pkg_summary))
                        auto_injected_types.add('package')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'package', 'count': len(pkg_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject package context: {e}")
        
        # Boot keywords -> inject boot context
        boot_keywords = ['boot', 'startup', 'grub', 'kernel', 'initrd', 'systemd-analyze']
        if any(kw in message_lower for kw in boot_keywords):
            try:
                boot_discoveries = [d for d in engine.get_all() if d.type.value == 'system_preservation']
                if boot_discoveries:
                    boot_summary = []
                    for d in boot_discoveries[:10]:
                        boot_summary.append(f"- {d.title}: {d.status}")
                    if boot_summary:
                        context_parts.append("**Boot/System:**\n" + "\n".join(boot_summary))
                        auto_injected_types.add('boot')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'boot', 'count': len(boot_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject boot context: {e}")
        
        # Error keywords -> inject error/alert context
        error_keywords = ['error', 'errors', 'log', 'journal', 'dmesg', 'crash', 'failed', 'failure']
        if any(kw in message_lower for kw in error_keywords):
            try:
                alert_discoveries = [d for d in engine.get_all() if d.type.value == 'alert']
                if alert_discoveries:
                    alert_summary = []
                    for d in alert_discoveries[:10]:
                        alert_summary.append(f"- {d.title}: {d.status}")
                    if alert_summary:
                        context_parts.append("**Recent Errors/Alerts:**\n" + "\n".join(alert_summary))
                        auto_injected_types.add('errors')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'errors', 'count': len(alert_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject error context: {e}")
        
        # Disk space keywords -> inject disk usage context  
        space_keywords = ['space', 'full', 'disk full', 'cleanup', 'clean', 'cache', 'trash', 'large']
        if any(kw in message_lower for kw in space_keywords):
            try:
                storage_discoveries = [d for d in engine.get_all() if d.type.value == 'storage']
                cleanup_items = []
                for d in storage_discoveries:
                    if d.data.get('is_cache') or d.data.get('is_trash') or d.data.get('is_large_dir'):
                        cleanup_items.append(f"- {d.title}: {d.status}")
                if cleanup_items:
                    context_parts.append("**Disk Space/Cleanup:**\n" + "\n".join(cleanup_items[:15]))
                    auto_injected_types.add('disk_usage')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'disk_usage', 'count': len(cleanup_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject disk usage context: {e}")
        
        # Laptop/battery keywords -> inject laptop context
        laptop_keywords = ['battery', 'laptop', 'suspend', 'hibernate', 'lid', 'power', 'tlp', 'brightness']
        if any(kw in message_lower for kw in laptop_keywords):
            try:
                power_discoveries = [d for d in engine.get_all() if d.type.value == 'power']
                if power_discoveries:
                    laptop_items = []
                    for d in power_discoveries:
                        laptop_items.append(f"- {d.title}: {d.status}")
                    if laptop_items:
                        context_parts.append("**Laptop/Power:**\n" + "\n".join(laptop_items[:10]))
                        auto_injected_types.add('laptop')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'laptop', 'count': len(power_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject laptop context: {e}")
        
        # Display/monitor keywords -> inject display context
        display_keywords = ['monitor', 'display', 'screen', 'resolution', 'hdmi', 'gpu', 'graphics', 
                           'nvidia', 'amd', 'wayland', 'x11', 'compositor', 'tearing', 'multi-monitor']
        if any(kw in message_lower for kw in display_keywords):
            try:
                desktop_discoveries = [d for d in engine.get_all() if d.type.value in ('desktop', 'gpu')]
                if desktop_discoveries:
                    display_items = []
                    for d in desktop_discoveries:
                        display_items.append(f"- {d.title}: {d.status or d.description}")
                    if display_items:
                        context_parts.append("**Display/Graphics:**\n" + "\n".join(display_items[:10]))
                        auto_injected_types.add('display')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'display', 'count': len(desktop_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject display context: {e}")
        
        # Audio keywords -> inject audio context
        audio_keywords = ['audio', 'sound', 'speaker', 'headphone', 'microphone', 'volume', 'pulseaudio', 
                         'pipewire', 'hdmi audio', 'no sound', 'mute']
        if any(kw in message_lower for kw in audio_keywords):
            try:
                hw_discoveries = [d for d in engine.get_all() if d.type.value == 'hardware']
                audio_items = []
                for d in hw_discoveries:
                    if d.data.get('is_audio_server') or d.data.get('is_sound_card') or d.data.get('is_audio_output') or d.data.get('is_audio_input'):
                        audio_items.append(f"- {d.title}: {d.status}")
                if audio_items:
                    context_parts.append("**Audio:**\n" + "\n".join(audio_items[:10]))
                    auto_injected_types.add('audio')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'audio', 'count': len(audio_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject audio context: {e}")
        
        # WiFi keywords -> inject wifi context  
        wifi_keywords = ['wifi', 'wireless', 'wlan', 'ssid', 'signal', 'disconnect', '5ghz', '2.4ghz', 
                        'iwconfig', 'network manager']
        if any(kw in message_lower for kw in wifi_keywords):
            try:
                net_discoveries = [d for d in engine.get_all() if d.type.value == 'network']
                wifi_items = []
                for d in net_discoveries:
                    if d.data.get('is_wifi_interface') or d.data.get('is_wifi_connection') or d.data.get('is_regulatory') or d.data.get('is_wifi_power'):
                        wifi_items.append(f"- {d.title}: {d.status}")
                if wifi_items:
                    context_parts.append("**WiFi:**\n" + "\n".join(wifi_items[:10]))
                    auto_injected_types.add('wifi')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'wifi', 'count': len(wifi_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject wifi context: {e}")
        
        # USB keywords -> inject usb context
        usb_keywords = ['usb', 'device not recognized', 'peripheral', 'plug', 'unplug', 'port']
        if any(kw in message_lower for kw in usb_keywords):
            try:
                hw_discoveries = [d for d in engine.get_all() if d.type.value == 'hardware']
                usb_items = []
                for d in hw_discoveries:
                    if d.data.get('is_usb_device') or d.data.get('is_usb_controller'):
                        usb_items.append(f"- {d.title}: {d.status}")
                if usb_items:
                    context_parts.append("**USB Devices:**\n" + "\n".join(usb_items[:10]))
                    auto_injected_types.add('usb')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'usb', 'count': len(usb_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject usb context: {e}")
        
        # GRUB/boot keywords -> inject bootloader context
        grub_keywords = ['grub', 'bootloader', 'uefi', 'bios', 'secure boot', 'dual boot', 'efi', 
                        'boot entry', 'kernel parameter', 'nomodeset']
        if any(kw in message_lower for kw in grub_keywords):
            try:
                boot_discoveries = [d for d in engine.get_all() if d.type.value == 'system_preservation']
                boot_items = []
                for d in boot_discoveries:
                    if d.data.get('is_boot_mode') or d.data.get('is_secure_boot') or d.data.get('is_grub_config') or d.data.get('is_cmdline') or d.data.get('is_boot_entries'):
                        boot_items.append(f"- {d.title}: {d.status}")
                if boot_items:
                    context_parts.append("**Boot/GRUB:**\n" + "\n".join(boot_items[:10]))
                    auto_injected_types.add('bootloader')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'bootloader', 'count': len(boot_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject bootloader context: {e}")
        
        # Docker/container keywords -> inject container context
        container_keywords = ['docker', 'container', 'podman', 'image', 'volume', 'compose']
        if any(kw in message_lower for kw in container_keywords):
            try:
                container_discoveries = [d for d in engine.get_all() if d.type.value == 'container']
                if container_discoveries:
                    container_items = []
                    for d in container_discoveries:
                        container_items.append(f"- {d.title}: {d.status}")
                    if container_items:
                        context_parts.append("**Containers:**\n" + "\n".join(container_items[:10]))
                        auto_injected_types.add('container')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'container', 'count': len(container_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject container context: {e}")
        
        # VM/virtualization keywords -> inject virtualization context
        vm_keywords = ['vm', 'virtual', 'kvm', 'qemu', 'virtualbox', 'vmware', 'hypervisor', 'guest']
        if any(kw in message_lower for kw in vm_keywords):
            try:
                hw_discoveries = [d for d in engine.get_all() if d.type.value == 'hardware']
                vm_items = []
                for d in hw_discoveries:
                    if d.data.get('is_virtualization') or d.data.get('is_hw_virt') or d.data.get('is_hypervisor'):
                        vm_items.append(f"- {d.title}: {d.status}")
                if vm_items:
                    context_parts.append("**Virtualization:**\n" + "\n".join(vm_items[:10]))
                    auto_injected_types.add('virtualization')
                    if debug_info:
                        debug_info['auto_injected_context'].append({'type': 'virtualization', 'count': len(vm_items)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject virtualization context: {e}")
        
        # Cron/scheduled task keywords -> inject scheduled context
        scheduled_keywords = ['cron', 'timer', 'scheduled', 'backup schedule', 'daily', 'automatic']
        if any(kw in message_lower for kw in scheduled_keywords):
            try:
                task_discoveries = [d for d in engine.get_all() if d.type.value == 'task']
                if task_discoveries:
                    task_items = []
                    for d in task_discoveries:
                        task_items.append(f"- {d.title}: {d.status}")
                    if task_items:
                        context_parts.append("**Scheduled Tasks:**\n" + "\n".join(task_items[:10]))
                        auto_injected_types.add('scheduled')
                        if debug_info:
                            debug_info['auto_injected_context'].append({'type': 'scheduled', 'count': len(task_discoveries)})
            except Exception as e:
                logger.warning(f"Failed to auto-inject scheduled context: {e}")
        
        # RELATIONSHIP-BASED RETRIEVAL
        # When a specific service or storage item is mentioned, fetch related discoveries
        try:
            # If asking about a mount service, also fetch its related storage
            for d in engine.get_all():
                if d.type.value == 'service' and d.data.get('is_mount_service'):
                    # Check if this service is mentioned in the query
                    service_name = d.name.lower()
                    if service_name in message_lower or service_name.replace('-', ' ') in message_lower:
                        mount_point = d.data.get('mount_point', '')
                        related_devices = d.data.get('related_storage', [])
                        
                        # Find storage discoveries that match these devices
                        related_storage = []
                        for storage_d in engine.get_all():
                            if storage_d.type.value == 'storage':
                                # Match by device path
                                storage_devices = storage_d.data.get('devices', [])
                                if storage_d.data.get('device'):
                                    storage_devices.append(storage_d.data.get('device'))
                                
                                # Check for overlap
                                if any(dev in related_devices for dev in storage_devices):
                                    related_storage.append(storage_d)
                                # Also match by mount point
                                elif storage_d.data.get('mountpoint') == mount_point:
                                    related_storage.append(storage_d)
                        
                        if related_storage:
                            related_summary = [f"**Related Storage for {d.name}:**"]
                            for rs in related_storage[:5]:
                                detail = f"- {rs.title}: {rs.status}"
                                if rs.data.get('has_failed_disk'):
                                    detail += " ⚠️ CONTAINS FAILED DISK"
                                if rs.data.get('failed_devices'):
                                    detail += f" - Failed: {', '.join(rs.data['failed_devices'])}"
                                related_summary.append(detail)
                            context_parts.append("\n".join(related_summary))
                            auto_injected_types.add('related_storage')
                            logger.info(f"Auto-injected {len(related_storage)} related storage discoveries for {d.name}")
                            if debug_info:
                                debug_info['auto_injected_context'].append({
                                    'type': 'related_storage', 
                                    'service': d.name,
                                    'count': len(related_storage)
                                })
                        break  # Only process first matching service
            
            # Reverse: If asking about a storage pool, find services that depend on it
            for d in engine.get_all():
                if d.type.value == 'storage':
                    # Check if this storage is mentioned in the query
                    storage_name = d.name.lower()
                    storage_label = (d.data.get('label') or '').lower()
                    if (storage_name in message_lower or 
                        storage_label in message_lower or 
                        (d.data.get('mountpoint') or '').lower() in message_lower):
                        
                        storage_devices = d.data.get('devices', [])
                        if d.data.get('device'):
                            storage_devices.append(d.data.get('device'))
                        mount_point = d.data.get('mountpoint')
                        
                        # Find services that use these devices or mount point
                        related_services = []
                        for svc in engine.get_all():
                            if svc.type.value == 'service' and svc.data.get('is_mount_service'):
                                svc_devices = svc.data.get('related_storage', [])
                                svc_mount = svc.data.get('mount_point')
                                
                                if any(dev in storage_devices for dev in svc_devices):
                                    related_services.append(svc)
                                elif svc_mount and svc_mount == mount_point:
                                    related_services.append(svc)
                        
                        if related_services:
                            svc_summary = [f"**Services depending on {d.title}:**"]
                            for svc in related_services[:5]:
                                detail = f"- {svc.name}: {svc.status}"
                                if svc.status and 'fail' in svc.status.lower():
                                    detail += " ⚠️ FAILED"
                                svc_summary.append(detail)
                            context_parts.append("\n".join(svc_summary))
                            auto_injected_types.add('related_services')
                            logger.info(f"Auto-injected {len(related_services)} related services for {d.name}")
                            if debug_info:
                                debug_info['auto_injected_context'].append({
                                    'type': 'related_services',
                                    'storage': d.name,
                                    'count': len(related_services)
                                })
                        break  # Only process first matching storage
            
            # If asking about an error, correlate to the service
            for d in engine.get_all():
                if d.type.value == 'alert' and d.data.get('is_error_log'):
                    unit = d.data.get('unit', '')
                    if unit.lower() in message_lower or d.name.lower() in message_lower:
                        # Find the service discovery for this unit
                        for svc in engine.get_all():
                            if svc.type.value == 'service' and svc.name in unit:
                                svc_info = [f"**Service Info for errors in {unit}:**"]
                                svc_info.append(f"- Status: {svc.status or 'unknown'}")
                                if svc.data.get('is_mount_service'):
                                    svc_info.append(f"- Mount point: {svc.data.get('mount_point', 'N/A')}")
                                    svc_info.append(f"- Mount device: {svc.data.get('mount_device', 'N/A')}")
                                context_parts.append("\n".join(svc_info))
                                auto_injected_types.add('error_service_correlation')
                                break
                        break
            
            # If asking about a process, find if it's a service
            for d in engine.get_all():
                if d.type.value == 'process' and d.data.get('is_resource_hog'):
                    proc_name = d.data.get('name', '').lower()
                    if proc_name in message_lower:
                        # Find service with matching name
                        for svc in engine.get_all():
                            if svc.type.value == 'service' and proc_name in svc.name.lower():
                                proc_info = [f"**Service for process {proc_name}:**"]
                                proc_info.append(f"- Service: {svc.name}")
                                proc_info.append(f"- Status: {svc.status or 'unknown'}")
                                if svc.chat_context:
                                    proc_info.append(f"- Info: {svc.chat_context[:200]}")
                                context_parts.append("\n".join(proc_info))
                                auto_injected_types.add('process_service_correlation')
                                break
                        break
            
            # If asking about heat/temperature, correlate to top CPU processes
            thermal_keywords = ['hot', 'heat', 'temperature', 'thermal', 'throttl', 'overheat']
            if any(kw in message_lower for kw in thermal_keywords):
                # Find thermal discoveries with high temps
                high_temp_found = False
                for d in engine.get_all():
                    if d.type.value == 'hardware' and d.data.get('is_thermal'):
                        temp = d.data.get('temp_celsius', 0)
                        if temp > 70:  # High temp
                            high_temp_found = True
                            break
                
                if high_temp_found:
                    # Get top CPU consumers as likely cause
                    cpu_hogs = []
                    for d in engine.get_all():
                        if d.type.value == 'process' and d.data.get('is_resource_hog'):
                            cpu_pct = d.data.get('cpu_percent', 0)
                            if cpu_pct > 10:
                                cpu_hogs.append((d, cpu_pct))
                    
                    if cpu_hogs:
                        cpu_hogs.sort(key=lambda x: x[1], reverse=True)
                        thermal_context = ["**Likely causes of high temperature:**"]
                        for proc, cpu in cpu_hogs[:5]:
                            thermal_context.append(f"- {proc.data.get('name')}: {cpu:.1f}% CPU")
                        context_parts.append("\n".join(thermal_context))
                        auto_injected_types.add('thermal_process_correlation')
            
            # If asking about slow boot, correlate slow services to their dependencies
            if 'slow' in message_lower and ('boot' in message_lower or 'startup' in message_lower):
                slow_services = []
                for d in engine.get_all():
                    if d.type.value == 'system_preservation' and d.data.get('is_slow_boot_service'):
                        boot_time = d.data.get('boot_time_sec', 0)
                        if boot_time > 5:
                            slow_services.append((d.data.get('service_name', d.name), boot_time))
                
                if slow_services:
                    slow_services.sort(key=lambda x: x[1], reverse=True)
                    boot_context = ["**Services slowing down boot:**"]
                    for svc, secs in slow_services[:5]:
                        boot_context.append(f"- {svc}: {secs:.1f}s")
                    boot_context.append("\nConsider disabling non-essential services or investigating why they're slow.")
                    context_parts.append("\n".join(boot_context))
                    auto_injected_types.add('boot_slow_correlation')
        except Exception as e:
            logger.warning(f"Failed to inject relationship context: {e}")
        
        for mention in mentions:
            mention_id = mention.replace('@', '')
            
            # Handle special @terminal mention (Phase 13)
            if mention_id == 'terminal':
                mentions_resolved.append({
                    "id": "terminal",
                    "name": "Terminal History",
                    "title": "Terminal Context",
                    "type": "context",
                    "status": "active",
                })
                # Terminal history is managed client-side, but we add a note
                context_parts.append(
                    "User has referenced their terminal history. "
                    "Any terminal output they provide should be considered in your response."
                )
                continue
            
            # Standard discovery resolution
            discovery = engine.get_discovery(mention_id)
            if discovery:
                mentions_resolved.append({
                    "id": discovery.id,
                    "name": discovery.name,
                    "title": discovery.title,
                    "type": discovery.type.value,
                    "status": discovery.status,
                    "description": discovery.description,
                    "data": discovery.data,  # Full scanner data
                })
                
                # Build rich context from all discovery data
                context_lines = [
                    f"**@{discovery.id}** - {discovery.title}",
                    f"Type: {discovery.type.value}",
                    f"Status: {discovery.status or 'Unknown'}",
                    f"Description: {discovery.description}",
                ]
                
                # Include all scanner-specific data
                if discovery.data:
                    context_lines.append("Details:")
                    for key, value in discovery.data.items():
                        if value is not None and value != "":
                            # Format key nicely
                            nice_key = key.replace("_", " ").title()
                            context_lines.append(f"  - {nice_key}: {value}")
                
                if discovery.status_detail:
                    context_lines.append(f"Status Detail: {discovery.status_detail}")
                if discovery.source:
                    context_lines.append(f"Source: {discovery.source}")
                
                context_parts.append("\n".join(context_lines))
        
        # Build context
        context = "\n".join(context_parts) if context_parts else ""
        
        # Try to use the LLM via ModelRouter
        try:
            model_router = get_model_router()
            
            # Load persona names from preferences
            from ...utils.platform import get_config_dir
            from ...persona import PersonaManager
            import yaml
            
            # Get the ACTIVE persona from PersonaManager (not the one passed in)
            try:
                persona_mgr = PersonaManager()
                active_persona = persona_mgr.get_active_persona().value
            except Exception:
                active_persona = 'it_admin'
            
            config_path = get_config_dir() / 'preferences.yml'
            ai_name = 'Halbert'  # Default
            user_name = 'there'   # Default for "Hi there"
            
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        prefs = yaml.safe_load(f) or {}
                    # Prefer direct ai_name from onboarding, fall back to persona_names
                    if prefs.get('ai_name'):
                        ai_name = prefs['ai_name']
                    elif prefs.get('persona_names', {}).get(active_persona):
                        ai_name = prefs['persona_names'][active_persona]
                    # Get user's name from onboarding
                    if prefs.get('user_name'):
                        user_name = prefs['user_name']
                except Exception:
                    pass
            
            logger.info(f"Using AI name '{ai_name}', user name '{user_name}'")
            
            # Generate system identity (what this system actually has)
            system_identity = get_system_identity()
            
            # Load any custom user-defined rules
            custom_rules = get_custom_ai_rules()
            
            # Phase 40-46: Build system prompt based on persona using v2 infrastructure
            # Determine tier: coder persona uses "specialist", default uses "guide"
            tier = "specialist" if persona == "coder" else "guide"
            
            # Try v2 prompt system first
            system_prompt = build_system_prompt_v2(tier=tier)
            
            if persona == "coder":
                task_type = TaskType.CODE_GENERATION
                # Fallback or augment with coder-specific context
                if not system_prompt:
                    system_prompt = (
                        f"You are {ai_name}, a Linux system administration AI assistant in coder mode. "
                        "Provide technical, concise responses. Focus on commands, scripts, and solutions. "
                        "Be direct and efficient.\n\n"
                        "CRITICAL - YOU CANNOT EXECUTE COMMANDS:\n"
                        "- You can ONLY suggest commands for the user to run\n"
                        "- You CANNOT execute commands or see their output\n"
                        "- NEVER fabricate command output - you don't know what commands would return\n"
                        "- NEVER show fake 'Output:' or 'Result:' sections\n"
                        "- Say 'Run this:' or 'Try:' - NOT 'Running... Output:'\n"
                        "- If you need output, ask the user to run the command and share results\n\n"
                        "COMMAND FORMATTING:\n"
                        "- Put each shell command in its own markdown code block with ```bash\n"
                        "- If giving multiple commands, put each in a SEPARATE code block with a brief description\n"
                        "- Never put multiple commands in the same code block unless they must run together (use && or ;)\n\n"
                        f"{system_identity}"
                        f"{custom_rules}\n\n"
                        "IMPORTANT: Always ground your responses in THIS specific system's actual state. "
                        "If asked about something not present on this system, say so clearly.\n\n"
                        "UNCERTAINTY - Ask for clarification:\n"
                        "- If a question is unclear, simply say 'Could you rephrase that?'\n"
                        "- Do NOT guess what the user meant - ask instead."
                    )
                else:
                    # V2 prompt loaded - add coder-specific context
                    system_prompt += f"\n\n{system_identity}{custom_rules}"
            else:
                task_type = TaskType.CHAT
                # For guide persona, v2 prompt was already built above
                if not system_prompt:
                    # Fallback to legacy prompt if v2 not available
                    system_prompt = (
                        f"You are {ai_name}, a friendly Linux system administration assistant. "
                        "Help users understand their system in a warm, conversational way. "
                        "Explain technical concepts clearly. You can discuss backups, services, "
                        "storage, network, and security.\n\n"
                        "CRITICAL - YOU CANNOT EXECUTE COMMANDS:\n"
                        "- You can ONLY suggest commands for the user to run\n"
                        "- You CANNOT execute commands yourself\n"
                        "- You CANNOT see command output unless the user pastes it to you\n"
                        "- NEVER fabricate or imagine command output - you don't know what it would show\n"
                        "- NEVER show fake 'Output:' sections - you cannot run commands\n"
                        "- If you need to know command output, ask the user to run it and share the result\n"
                        "- Say 'Try running: `command`' NOT 'Running: `command`... Output: ...'\n\n"
                        "COMMAND FORMATTING:\n"
                        "- Put each shell command in its own markdown code block with ```bash\n"
                        "- If giving multiple commands, put each in a SEPARATE code block with a brief description\n"
                        "- Never put multiple commands in the same code block unless they must run together (use && or ;)\n\n"
                        f"{system_identity}"
                        f"{custom_rules}\n\n"
                        "IMPORTANT: Always ground your responses in THIS specific system's actual state. "
                        "If asked about something not present on this system, say so clearly before offering general advice.\n\n"
                        "RESPONSE LENGTH - Be concise:\n"
                        "- Match response length to question complexity. Simple questions get 1-2 sentence answers.\n"
                        "- Don't pad responses with unnecessary filler or repetition.\n"
                        "- Only provide detailed explanations when the question actually warrants depth.\n\n"
                        "CONVERSATION CONTEXT - THIS IS CRITICAL:\n"
                        "- ALWAYS check the conversation history FIRST before responding.\n"
                        "- When you see command output with 'Error' or error messages, THAT IS THE CONTEXT.\n"
                        "- If there's an error visible in the conversation, analyze it - don't ask what they mean.\n"
                        "- NEVER ask 'could you rephrase' when there's visible command output or errors in the conversation.\n"
                        "- If a command failed, explain WHY based on the error output - don't ask for more information.\n"
                    )
                else:
                    # V2 prompt loaded - add guide-specific context
                    system_prompt += f"\n\n{system_identity}{custom_rules}"
            
            # Add context from mentions if available
            full_prompt = system_prompt + "\n\n"
            if context:
                full_prompt += f"Context from @mentions:\n{context}\n\n"
            
            # Phase 12b: Auto-inject topic-relevant context
            topic_context = get_topic_context(message)
            if topic_context:
                full_prompt += f"Relevant system context for this query:{topic_context}\n\n"
            
            # Check if query seems unclear/vague (short with no clear keywords)
            query_words = message.lower().split()
            unclear_query = (
                len(query_words) <= 5 and
                not any(kw in message.lower() for kw in [
                    'disk', 'service', 'backup', 'storage', 'network', 'install', 'config',
                    'mount', 'file', 'directory', 'process', 'memory', 'cpu', 'error',
                    'help', 'how', 'what', 'why', 'when', 'where', 'show', 'list', 'check'
                ])
            )
            
            # RAG documentation retrieval via the production ChromaDB path
            # (skip for unclear queries)
            if not unclear_query:
                docs_context = get_docs_context(message)
                if docs_context:
                    full_prompt += f"{docs_context}\n\n"
                
                # Web search for queries needing current information
                if should_use_web_search(message):
                    logger.info(f"Query triggers web search: {message[:50]}...")
                    web_context = await get_web_search_context(message)
                    if web_context:
                        full_prompt += f"{web_context}\n\n"
            else:
                # Add a hint that this query seems unclear
                full_prompt += "NOTE: The user's query seems unclear or vague. Ask for clarification rather than guessing.\n\n"
            
            # Add conversation history for context continuity
            if request.history:
                full_prompt += "**CONVERSATION HISTORY - READ THIS CAREFULLY BEFORE RESPONDING:**\n"
                full_prompt += "(This is what's been discussed. Use this context to understand follow-up questions.)\n\n"
                for msg in request.history[-6:]:  # Last 6 messages for context
                    role_label = "User" if msg.role == "user" else "You (Assistant)"
                    # Allow longer content for command outputs (2000 chars)
                    content = msg.content[:2000] + "..." if len(msg.content) > 2000 else msg.content
                    # Highlight command outputs
                    if "Command:" in content or "Output:" in content or "Error" in content:
                        full_prompt += f"[COMMAND OUTPUT] {role_label}: {content}\n\n"
                    else:
                        full_prompt += f"{role_label}: {content}\n\n"
                full_prompt += "---END HISTORY---\n\n"
                full_prompt += "REMINDER: If the user asks about something 'failing' or 'broken', look at the command output above!\n\n"
            
            # Phase 21/30: ReAct reasoning loop (auto-enabled for complex tool queries)
            react_response = None
            thinking_steps = []
            thinking_duration_ms = 0
            used_react = False
            tool_results = []  # Initialize for debug tracking
            response = None  # Initialize response variable
            
            # Phase 30: Auto-ReAct - automatically use ReAct for complex queries
            # that would benefit from tool use, even if not explicitly requested
            auto_react = False
            if should_use_tools(message):
                complexity_score = _score_query_complexity(message)
                # Auto-enable ReAct for complex queries (>= 0.4) or explicit request
                auto_react = complexity_score >= 0.4
                if auto_react and not request.use_react:
                    logger.info(f"Auto-enabling ReAct: complexity {complexity_score:.2f} >= 0.4")
            
            if (request.use_react or auto_react) and should_use_tools(message):
                logger.info("Using ReAct reasoning loop for this query")
                try:
                    from ...agents.react_agent import ReActAgent
                    from ...tools.system_tools import SYSTEM_TOOLS, execute_tool
                    
                    # Get model - prefer specialist for ReAct reasoning
                    # Note: ReAct currently only works with Ollama, not OpenAI-compatible APIs
                    react_model = get_configured_model()
                    react_endpoint = get_ollama_endpoint()
                    specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
                    if specialist_model and specialist_provider == "ollama":
                        complexity_score = _score_query_complexity(message)
                        if complexity_score >= 0.4:  # Lower threshold for ReAct
                            react_model = specialist_model
                            react_endpoint = specialist_endpoint
                    
                    agent = ReActAgent(
                        model=react_model,
                        endpoint=react_endpoint,
                        tools=SYSTEM_TOOLS,
                        execute_tool_fn=lambda name, args: execute_tool(name, args),
                        check_auth_fn=check_tool_authorization,
                        max_iterations=5,
                    )
                    
                    # Convert history to dict format
                    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history] if request.history else []
                    
                    react_result = agent.run(
                        query=message,
                        system_prompt=system_prompt,
                        context=context,
                        history=history_dicts,
                    )
                    
                    react_response = react_result.final_response
                    thinking_steps = [s.to_dict() for s in react_result.thinking_steps]
                    thinking_duration_ms = react_result.total_duration_ms
                    used_react = True
                    
                    if debug_info:
                        debug_info['model_used'] = react_result.model_used
                        debug_info['react_iterations'] = react_result.iterations
                        debug_info['react_tool_calls'] = react_result.tool_calls_count
                    
                    logger.info(f"ReAct completed: {len(thinking_steps)} steps, {react_result.iterations} iterations")
                    
                except Exception as e:
                    logger.error(f"ReAct agent failed, falling back to standard: {e}")
                    react_response = None
            
            if react_response:
                response = react_response
            # Phase 12d: Try tool-calling for real-time queries (fallback if not using ReAct)
            elif not request.use_react and should_use_tools(message):
                logger.info("Query may benefit from tool use, trying tool-calling...")
                tool_response, tool_results = call_ollama_with_tools(
                    prompt=message,
                    system_prompt=system_prompt
                )
                if tool_response:
                    response = tool_response
                    if tool_results:
                        logger.info(f"Tool-calling succeeded with {len(tool_results)} tool calls")
            
            # Handle images separately (vision model)
            if request.images and not react_response:
                # Vision model: Use direct Ollama call with images and history
                logger.info(f"Processing {len(request.images)} images with vision model")
                # Convert history to dict format for vision call
                history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history] if request.history else []
                vision_model, vision_endpoint = get_vision_model()
                
                # Phase 40-46: Build vision-specific prompt using v2 infrastructure
                vision_prompt = build_system_prompt_v2(tier="vision")
                if vision_prompt:
                    # Add system identity to v2 prompt
                    vision_prompt += f"\n\n{system_identity}{custom_rules}"
                else:
                    # Fallback to existing system_prompt
                    vision_prompt = system_prompt
                
                response = call_ollama_with_images(
                    message=message,
                    images=request.images,
                    system_prompt=vision_prompt,
                    model=vision_model,
                    endpoint=vision_endpoint,
                    history=history_dicts
                )
                if debug_info:
                    debug_info['model_used'] = vision_model
                    debug_info['endpoint_used'] = vision_endpoint
                    debug_info['vision_mode'] = True
                    debug_info['image_count'] = len(request.images)
            elif not react_response and not response:
                # Phase 21: Use proper chat API with message arrays
                # Only if we don't already have a response from React or tool calling
                # LLMs understand structured roles better than concatenated strings
                
                # Build messages array
                messages = []
                
                # System message with all context
                system_content = system_prompt
                if context:
                    system_content += f"\n\nContext from @mentions:\n{context}"
                if topic_context:
                    system_content += f"\n\nRelevant system context:{topic_context}"
                # Use RAG context already fetched above (avoid duplicate call)
                if not unclear_query and rag_context:
                    system_content += f"\n\n{rag_context}"
                
                messages.append({"role": "system", "content": system_content})
                
                # Add conversation history as proper messages
                if request.history:
                    for msg in request.history[-6:]:
                        content = msg.content[:2000] + "..." if len(msg.content) > 2000 else msg.content
                        if msg.role == "user":
                            messages.append({"role": "user", "content": content})
                        elif msg.role == "system":
                            # System messages (command output, context cards) should be user context
                            messages.append({"role": "user", "content": f"[Context]\n{content}"})
                        else:
                            messages.append({"role": "assistant", "content": content})
                
                # Current user message
                messages.append({"role": "user", "content": message})
                
                # Debug: log what we're sending
                logger.info(f"Built {len(messages)} messages for LLM:")
                for i, m in enumerate(messages):
                    role = m.get('role', '?')
                    content_preview = m.get('content', '')[:150].replace('\n', ' ')
                    logger.info(f"  [{i}] {role}: {content_preview}...")
                
                # Smart routing: decide between guide (8b) and specialist (70b)
                # Based on complexity scoring
                use_specialist = False
                complexity_score = 0.0
                model = get_configured_model()  # Default: guide/orchestrator
                endpoint = get_ollama_endpoint()
                provider = "ollama"
                
                specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
                if specialist_model:
                    # Score complexity to decide routing
                    complexity_score = _score_query_complexity(message)
                    
                    # Use specialist for complex queries (threshold 0.5)
                    if complexity_score >= 0.5:
                        model = specialist_model
                        endpoint = specialist_endpoint
                        provider = specialist_provider or "ollama"
                        use_specialist = True
                        logger.info(f"Complexity {complexity_score:.2f} >= 0.5 → using specialist: {model} (provider: {provider})")
                    else:
                        logger.info(f"Complexity {complexity_score:.2f} < 0.5 → using guide: {model}")
                
                try:
                    # Use provider-aware API call (handles Ollama vs OpenAI-compatible)
                    llm_result = call_llm_chat(
                        endpoint=endpoint,
                        model=model,
                        messages=messages,
                        provider=provider,
                        stream=False,
                        timeout=300 if use_specialist else 180,  # More time for large specialist models
                        options={"num_predict": 2048, "temperature": 0.7}
                    )
                    response = llm_result["content"]
                    raw_data = llm_result["raw"]
                    tokens_used = raw_data.get("eval_count", 0) + raw_data.get("prompt_eval_count", 0)
                    if not tokens_used and "usage" in raw_data:
                        # OpenAI format
                        tokens_used = raw_data["usage"].get("total_tokens", 0)
                    logger.info(f"Chat API response generated ({tokens_used} tokens, {len(messages)} messages)")
                except Exception as chat_err:
                    logger.warning(f"Chat API failed: {chat_err}")
                    
                    # If specialist failed, fall back to guide model with guide's endpoint
                    if use_specialist:
                        logger.info("Specialist failed, falling back to guide model")
                        guide_model = get_configured_model()
                        guide_endpoint = get_ollama_endpoint()
                        logger.info(f"Fallback: {len(messages)} messages, guide={guide_model} at {guide_endpoint}")
                        # Log message summary for debugging context issues
                        for i, m in enumerate(messages):
                            role = m.get('role', '?')
                            content_preview = m.get('content', '')[:100].replace('\n', ' ')
                            logger.debug(f"  msg[{i}] {role}: {content_preview}...")
                        try:
                            # Use guide's endpoint (local Ollama), NOT the specialist endpoint
                            llm_result = call_llm_chat(
                                endpoint=guide_endpoint,
                                model=guide_model,
                                messages=messages,
                                provider="ollama",  # Guide always uses Ollama
                                stream=False,
                                timeout=180,
                                options={"num_predict": 1024, "temperature": 0.7}
                            )
                            response = llm_result["content"]
                            raw_data = llm_result["raw"]
                            tokens_used = raw_data.get("eval_count", 0) + raw_data.get("prompt_eval_count", 0)
                            model = guide_model  # Update for debug info
                            use_specialist = False
                            logger.info(f"Fallback to guide succeeded: {guide_model}")
                        except Exception as fallback_err:
                            logger.error(f"Guide fallback also failed: {fallback_err}")
                            response = "I'm sorry, I encountered an error processing your request. Please try again."
                            tokens_used = 0
                    else:
                        # Guide failed, no further fallback
                        logger.error(f"Guide model failed: {chat_err}")
                        response = "I'm sorry, I encountered an error processing your request. Please try again."
                        tokens_used = 0
                
                # Track model info for debug
                if debug_info:
                    debug_info['model_used'] = model
                    debug_info['model_type'] = 'specialist' if use_specialist else 'guide'
                    debug_info['complexity_score'] = complexity_score if specialist_model else 0.0
                    debug_info['endpoint_used'] = endpoint
                    debug_info['tokens_used'] = tokens_used
                    debug_info['generation_time_ms'] = int((time.time() - start_time) * 1000)
                    debug_info['message_count'] = len(messages)
                    debug_info['chat_api'] = True
            
            # Track tool calls for debug
            if debug_info and tool_results:
                debug_info['tool_calls'] = [str(t) for t in tool_results]
            
        except Exception as e:
            logger.warning(f"LLM generation failed, using fallback: {e}")
            # Fallback to rule-based responses if LLM fails
            if persona == "coder":
                response = generate_coder_response(message, context)
            else:
                response = generate_guide_response(message, context, mentions_resolved)
        
        # Finalize debug info
        if debug_info:
            debug_info['total_time_ms'] = int((time.time() - start_time) * 1000)
            debug_info['context_parts_count'] = len(context_parts)
            debug_info['response_length'] = len(response)
        
        # Store conversation in memory for future context retrieval
        if conversation_id and message:
            # Store user message
            store_conversation_memory(
                conversation_id=conversation_id,
                message=message,
                role='user',
                page=current_page,
                mentions=mentions
            )
            # Store assistant response
            if response:
                store_conversation_memory(
                    conversation_id=conversation_id,
                    message=response[:1000],  # Truncate long responses
                    role='assistant',
                    page=current_page
                )
        
        # Phase 43: Filter output for sensitive data
        try:
            validator = get_safety_validator()
            filtered_response = validator.filter_output(response)
            if filtered_response != response:
                logger.info("Output filtering applied - sensitive data redacted")
        except Exception as e:
            logger.debug(f"Output filtering skipped: {e}")
            filtered_response = response
        
        return ChatResponse(
            response=filtered_response,
            mentions_resolved=mentions_resolved,
            suggested_actions=get_suggested_actions(message, mentions_resolved),
            debug=debug_info,
            # Phase 21: ReAct thinking steps
            thinking_steps=[ThinkingStepModel(**s) for s in thinking_steps] if thinking_steps else [],
            thinking_duration_ms=thinking_duration_ms,
            used_react=used_react,
        )
    
    
    @router.post("/send/stream")
    async def send_message_stream(request: ChatRequest):
        """
        Phase 30: Streaming chat endpoint using Server-Sent Events (SSE).
        
        Streams tokens as they are generated by the LLM for real-time response display.
        Returns a text/event-stream response with JSON-encoded token events.
        
        Events:
        - data: {"token": "...", "done": false}  - Each token as it arrives
        - data: {"token": "", "done": true, "full_response": "..."}  - Final complete response
        """
        import asyncio
        
        message = request.message.strip()
        
        # Phase 43: Safety validation on input
        try:
            validator = get_safety_validator()
            input_check = validator.validate_input(message)
            if not input_check.allowed:
                logger.warning(f"Streaming input blocked: {input_check.reason}")
                async def blocked_stream():
                    yield f'data: {{"error": "Input blocked by safety validation", "done": true}}\n\n'
                return StreamingResponse(blocked_stream(), media_type="text/event-stream")
        except Exception as e:
            logger.debug(f"Streaming safety validation skipped: {e}")
        
        async def generate_stream():
            """Generator that yields SSE events."""
            full_response = ""
            
            try:
                # Get model configuration
                model = get_configured_model()
                endpoint = get_ollama_endpoint()
                provider = "ollama"
                
                # Smart routing for specialist model
                specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
                if specialist_model:
                    complexity_score = _score_query_complexity(message)
                    if complexity_score >= 0.5:
                        model = specialist_model
                        endpoint = specialist_endpoint
                        provider = specialist_provider or "ollama"
                        logger.info(f"Streaming: using specialist model {model} (provider: {provider})")
                
                # Phase 40-46: Build system prompt using v2 prompt infrastructure
                # Determine tier based on model routing
                tier = "guide"
                if specialist_model and model == specialist_model:
                    tier = "specialist"
                
                # Try v2 prompt system first
                system_prompt = build_system_prompt_v2(tier=tier)
                
                # Fallback to legacy prompt if v2 not available
                if not system_prompt:
                    system_prompt = (
                        "You are Halbert, a helpful Linux system administration assistant. "
                        "Be concise and helpful.\n\n"
                        "COMMAND EXECUTION (CRITICAL):\n"
                        "- You CANNOT run commands. You can only SUGGEST commands.\n"
                        "- The user has Run buttons next to code blocks to execute them.\n"
                        "- NEVER fabricate, imagine, or hallucinate command output.\n"
                        "- NEVER say 'The output shows...' unless you see actual [Command Output] in history.\n"
                        "- After suggesting a command, STOP and wait. Say 'Run this to check' - nothing more.\n"
                        "- You will see actual results as [Command Output] messages in the conversation.\n\n"
                        "COMMAND FORMATTING (CRITICAL - user has Run buttons for code blocks):\n"
                        "- ALWAYS put shell commands in fenced code blocks with ```bash\n"
                        "- NEVER use inline `backticks` for runnable commands - the user can't click those\n"
                        "- Each command gets its own code block so user can run it with one click\n"
                        "- Example:\n"
                        "```bash\n"
                        "btrbk -L | grep home\n"
                        "```\n"
                        "- After suggesting, say 'Run this and I'll analyze the results' NOT 'paste the output'\n"
                    )
                else:
                    # V2 prompt loaded - add command execution context
                    system_prompt += "\n\n<!-- Dashboard Command Integration -->\n"
                    system_prompt += "COMMAND EXECUTION (CRITICAL - READ CAREFULLY):\n"
                    system_prompt += "- You CANNOT run commands. You can only SUGGEST commands.\n"
                    system_prompt += "- The user has Run buttons next to code blocks to execute them.\n"
                    system_prompt += "- NEVER fabricate, imagine, or hallucinate command output.\n"
                    system_prompt += "- NEVER say 'The output shows...' unless you see actual [Command Output] in history.\n"
                    system_prompt += "- After suggesting a command, STOP and wait. Say 'Run this to check' - nothing more.\n"
                    system_prompt += "- You will see actual results as [Command Output] messages in the conversation.\n\n"
                    system_prompt += "COMMAND FORMATTING:\n"
                    system_prompt += "- Put shell commands in ```bash code blocks\n"
                    system_prompt += "- Never use inline `backticks` for runnable commands\n"
                    system_prompt += "- ALWAYS use sudo for: journalctl, btrbk, systemctl, btrfs, bcachefs, mount, blkid, smartctl, cryptsetup\n"
                
                # === CONTEXT INJECTION FOR STREAMING ===
                # Phase 42: Send early activity indicator for fast feedback
                yield f"data: {json.dumps({'activity': {'type': 'scan', 'data': {'query': message[:50], 'phase': 'context'}}})}\n\n"
                
                # Retrieve self-knowledge context (discoveries about THIS system)
                context_parts = []
                message_lower = message.lower()
                
                # Self-knowledge retrieval via CRAG
                try:
                    self_knowledge_context, _ = get_self_knowledge_context(message, max_results=5)
                    if self_knowledge_context:
                        context_parts.append(self_knowledge_context)
                        logger.debug("Streaming: Injected self-knowledge context")
                        # Phase 42: Notify frontend about loaded context
                        yield f"data: {json.dumps({'activity': {'type': 'read', 'data': {'source': 'self_knowledge', 'count': 1}}})}\n\n"
                except Exception as e:
                    logger.warning(f"Streaming: Failed to get self-knowledge: {e}")
                
                # Semantic search over discoveries
                try:
                    discovery_context = get_discovery_context(message, max_results=5)
                    if discovery_context:
                        context_parts.append(discovery_context)
                        logger.debug("Streaming: Injected discovery context")
                except Exception as e:
                    logger.warning(f"Streaming: Failed to get discovery context: {e}")
                
                # Import comprehensive keyword lists (Phase 36 research)
                try:
                    from config.prompts.v2.keywords import BACKUP_KEYWORDS, STORAGE_KEYWORDS
                except ImportError:
                    # Fallback to basic keywords if module not found
                    BACKUP_KEYWORDS = {'backup', 'timeshift', 'snapshot', 'restore', 'rsync', 'borg', 'btrbk', '/home', '/root'}
                    STORAGE_KEYWORDS = {'disk', 'storage', 'drive', 'filesystem', 'mount', 'bcachefs', 'btrfs', 'zfs', 'raid', 'nvme', 'ssd', 'hdd', 'partition', '/home'}
                
                # Backup-specific context injection
                if any(kw in message_lower for kw in BACKUP_KEYWORDS):
                    logger.info(f"Streaming: Backup keyword matched in query: {message_lower[:50]}")
                    try:
                        from halbert_core.discovery.schema import DiscoveryType
                        engine = get_engine()
                        backup_discoveries = engine.get_by_type(DiscoveryType.BACKUP)
                        logger.info(f"Streaming: Backup discoveries found: {len(backup_discoveries) if backup_discoveries else 0}")
                        if backup_discoveries:
                            backup_summary = [d.chat_context or f"- {d.name}: {d.description}" for d in backup_discoveries[:10]]
                            context_parts.append(
                                "**Detected Backups on this system:**\n" + "\n".join(backup_summary)
                            )
                            logger.info(f"Streaming: Injected backup context: {len(backup_discoveries)} discoveries")
                        else:
                            logger.warning("Streaming: No backup discoveries in database - RAG context empty")
                    except Exception as e:
                        logger.error(f"Streaming: Failed to get backup context: {e}", exc_info=True)
                
                # Storage-specific context injection (uses STORAGE_KEYWORDS from above)
                if any(kw in message_lower for kw in STORAGE_KEYWORDS):
                    logger.info(f"Streaming: Storage keyword matched in query: {message_lower[:50]}")
                    try:
                        from halbert_core.discovery.schema import DiscoveryType
                        engine = get_engine()
                        storage_discoveries = engine.get_by_type(DiscoveryType.STORAGE)
                        logger.info(f"Streaming: Storage discoveries found: {len(storage_discoveries) if storage_discoveries else 0}")
                        if storage_discoveries:
                            storage_summary = [d.chat_context or f"- {d.name}: {d.description}" for d in storage_discoveries[:10]]
                            context_parts.append(
                                "**Detected Storage on this system:**\n" + "\n".join(storage_summary)
                            )
                            logger.debug(f"Streaming: Injected storage context: {len(storage_discoveries)} discoveries")
                    except Exception as e:
                        logger.warning(f"Streaming: Failed to get storage context: {e}")
                
                # Add context to system prompt if we have any
                if context_parts:
                    system_prompt += "\n\n=== SYSTEM KNOWLEDGE (about THIS specific machine) ===\n"
                    system_prompt += "\n\n".join(context_parts)
                    system_prompt += "\n\nIMPORTANT: Use this system-specific knowledge to answer accurately. "
                    system_prompt += "If the user asks about paths or configurations, check this context first.\n"
                
                # Build messages array for streaming
                # DeepSeek-R1 models: inject system prompt into user message (official recommendation)
                is_deepseek_r1 = "deepseek-r1" in model.lower()
                
                if is_deepseek_r1:
                    # DeepSeek-R1 doesn't want system prompts - inject into first user message
                    logger.info(f"DeepSeek-R1 detected: injecting system prompt into user message")
                    user_content = f"[Instructions]\n{system_prompt}\n\n[User Query]\n{message}"
                    messages = [{"role": "user", "content": user_content}]
                else:
                    # Standard system prompt for other models
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ]
                
                # Add history if provided (including command output which uses 'system' role)
                if request.history:
                    history_messages = []
                    for msg in request.history[-6:]:  # Increased to capture more context
                        # Map roles: system messages (command output) become user context
                        if msg.role == "system":
                            # Command output - present as user-provided context
                            history_messages.append({"role": "user", "content": f"[Command Output]\n{msg.content}"})
                        elif msg.role == "user":
                            history_messages.append({"role": "user", "content": msg.content[:1000]})
                        else:
                            history_messages.append({"role": "assistant", "content": msg.content[:1000]})
                    
                    if is_deepseek_r1:
                        # DeepSeek-R1: history goes before the combined instruction+query message
                        messages = history_messages + messages
                    else:
                        # Standard: system prompt, then history, then current user message
                        messages = [messages[0]] + history_messages + [messages[-1]]
                
                # Phase 32: Initialize reasoning parser for thinking block detection
                uses_reasoning = is_reasoning_model(model)
                # Qwen3-Thinking models start in thinking mode (no opening <think> tag)
                is_qwen_thinking = 'thinking' in model.lower() or 'qwen3' in model.lower()
                reasoning_parser = StreamingReasoningParser(assume_thinking_mode=is_qwen_thinking)
                
                # Build request based on provider
                if provider == "openai":
                    # OpenAI-compatible streaming (LM Studio, vLLM, etc.)
                    stream_url = f"{endpoint}/v1/chat/completions"
                    stream_payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        # Qwen3-Thinking needs much more tokens for extended reasoning
                        "max_tokens": 8192 if is_qwen_thinking else (2048 if uses_reasoning else 1024),
                        "temperature": 0.7
                    }
                else:
                    # Ollama streaming
                    stream_url = f"{endpoint}/api/chat"
                    stream_payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "options": {
                            # Qwen3-Thinking needs much more tokens for extended reasoning
                            "num_predict": 8192 if is_qwen_thinking else (2048 if uses_reasoning else 1024),
                            "temperature": 0.6 if is_qwen_thinking else 0.7  # Qwen3 recommends 0.6 for thinking
                        }
                    }
                
                logger.info(f"Streaming from {stream_url} (provider: {provider})")
                
                # Make streaming request
                with requests.post(
                    stream_url,
                    json=stream_payload,
                    stream=True,
                    timeout=300 if uses_reasoning else 180  # Longer timeout for reasoning
                ) as response:
                    response.raise_for_status()
                    
                    for line in response.iter_lines():
                        if line:
                            try:
                                # Handle SSE format for OpenAI (data: prefix)
                                line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                                if line_str.startswith('data: '):
                                    line_str = line_str[6:]
                                if line_str == '[DONE]':
                                    break
                                
                                data = json.loads(line_str)
                                
                                # Extract token based on provider format
                                if provider == "openai":
                                    # OpenAI format: choices[0].delta.content
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    token = delta.get("content", "")
                                    done = data.get("choices", [{}])[0].get("finish_reason") is not None
                                else:
                                    # Ollama format: message.content
                                    token = data.get("message", {}).get("content", "")
                                    done = data.get("done", False)
                                
                                if token:
                                    full_response += token
                                    
                                    # Phase 32: Parse reasoning blocks in real-time
                                    thinking_delta, response_delta, is_thinking = reasoning_parser.process_token(token)
                                    
                                    if thinking_delta:
                                        # Send thinking content with special marker
                                        yield f"data: {json.dumps({'thinking': thinking_delta, 'done': False})}\n\n"
                                    
                                    if response_delta:
                                        # Send response content normally
                                        yield f"data: {json.dumps({'token': response_delta, 'done': False})}\n\n"
                                    elif not thinking_delta and not is_thinking:
                                        # No reasoning detected, stream normally
                                        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                                
                                if done:
                                    # Finalize reasoning parser
                                    final_thinking, final_response = reasoning_parser.finalize()
                                    
                                    # If we detected reasoning, use parsed response
                                    if final_thinking:
                                        # CRITICAL: If reasoning exists but response is empty/useless, 
                                        # extract actionable content from the reasoning
                                        if not final_response or len(final_response.strip()) < 20:
                                            # Model reasoned but didn't produce useful output after </think>
                                            # Try to extract useful commands from reasoning
                                            reasoning_lines = [l.strip() for l in final_thinking.split('\n') if l.strip()]
                                            
                                            # Look for command suggestions in reasoning
                                            command_patterns = ['systemctl', 'journalctl', 'sudo ', 'cat ', 'grep ', 'ls ', 'btrbk', 'btrfs']
                                            found_commands = []
                                            for line in reasoning_lines:
                                                if any(cmd in line.lower() for cmd in command_patterns):
                                                    # Extract just the command part if possible
                                                    if '`' in line:
                                                        # Extract backtick-wrapped command
                                                        import re
                                                        cmds = re.findall(r'`([^`]+)`', line)
                                                        found_commands.extend(cmds)
                                                    elif any(line.lower().startswith(cmd) for cmd in command_patterns):
                                                        found_commands.append(line.split()[0] + ' ...')
                                            
                                            if found_commands:
                                                # Found commands - suggest them properly
                                                cmd = found_commands[0]
                                                final_response = f"Let me check the status. Run this command:\n\n```bash\nsudo systemctl status bcachefs-backup\n```\n\nThis will show the error details."
                                            else:
                                                # No commands found - provide helpful message based on reasoning
                                                final_response = "I analyzed the issue but need more information. Let me check the service status:\n\n```bash\nsudo systemctl status bcachefs-backup\n```\n\nRun this and I'll analyze the error."
                                            
                                            logger.warning(f"Reasoning model produced empty response, generated helpful fallback")
                                        yield f"data: {json.dumps({'token': '', 'done': True, 'full_response': final_response, 'thinking': final_thinking})}\n\n"
                                    else:
                                        yield f"data: {json.dumps({'token': '', 'done': True, 'full_response': full_response})}\n\n"
                                    break
                                    
                            except json.JSONDecodeError:
                                continue
                
            except Exception as e:
                logger.error(f"Streaming chat error: {e}")
                error_msg = f"Error: {str(e)}"
                yield f"data: {json.dumps({'token': error_msg, 'done': True, 'error': True})}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )
    
    
    @router.post("/explain")
    async def explain_context(context: str, question: Optional[str] = None):
        """
        Explain something with optional context.
        
        Used by terminal /explain command.
        """
        if not context:
            return {"explanation": "No context provided to explain."}
        
        # Simple rule-based explanation for MVP
        explanation = f"Based on the output:\n\n```\n{context[:500]}...\n```\n\n"
        
        if "error" in context.lower():
            explanation += "This appears to contain an error. Check the error message for details."
        elif "warning" in context.lower():
            explanation += "This contains warnings that may need attention."
        else:
            explanation += "This output appears to be normal system output."
        
        return {"explanation": explanation}


    # === Model Selection API (Phase 12e) ===
    
    @router.get("/models")
    async def get_available_models():
        """
        Get available models and current selection.
        
        Returns both the current config and available models from Ollama.
        """
        try:
            model_router = get_model_router()
            
            # Get current config
            config = model_router.config
            
            # Get available models from Ollama
            available = []
            if "ollama" in model_router.providers:
                ollama = model_router.providers["ollama"]
                try:
                    models = ollama.list_models()
                    available = [{"id": m.model_id, "name": m.model_id, "provider": "ollama"} for m in models]
                except Exception as e:
                    logger.warning(f"Failed to list Ollama models: {e}")
            
            # Get executor options from config
            executor_options = config.get("executor_options", {})
            
            return {
                "current": {
                    "orchestrator": config.get("orchestrator", {}).get("model"),
                    "specialist": config.get("specialist", {}).get("model"),
                    "specialist_enabled": config.get("specialist", {}).get("enabled", False),
                },
                "executor_options": executor_options,
                "available": available,
            }
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return {"error": str(e)}
    
    
    @router.post("/models/select")
    async def select_model(model_id: str):
        """
        Set the specialist/executor model.
        
        Args:
            model_id: Model ID to use as specialist (e.g., "llama3.3:70b")
        """
        try:
            model_router = get_model_router()
            model_router.set_specialist(model_id, "ollama")
            
            return {
                "success": True,
                "specialist": model_id,
                "message": f"Executor model set to {model_id}",
            }
        except Exception as e:
            logger.error(f"Failed to set model: {e}")
            return {"success": False, "error": str(e)}
    
    
    @router.get("/models/status")
    async def get_models_router_status():
        """Get detailed model router status."""
        try:
            model_router = get_model_router()
            return model_router.get_status()
        except Exception as e:
            logger.error(f"Failed to get model status: {e}")
            return {"error": str(e)}
    
    
    @router.get("/models/loaded")
    async def get_loaded_models_endpoint():
        """
        Get list of currently loaded models in Ollama.
        
        Returns models that are currently in VRAM/memory and ready for immediate inference.
        """
        try:
            endpoint = get_ollama_endpoint()
            models = get_loaded_models(endpoint)
            
            # Also get the configured model to check if it's loaded
            configured_model = get_configured_model()
            configured_loaded = is_model_loaded(configured_model, endpoint)
            
            # Also check specialist model (for config editing)
            specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
            specialist_models = get_loaded_models(specialist_endpoint, specialist_provider or "ollama") if specialist_endpoint != endpoint else models
            specialist_loaded = is_model_loaded(specialist_model, specialist_endpoint, specialist_provider or "ollama") if specialist_model else None
            
            return {
                "loaded_models": models,
                "configured_model": configured_model,
                "configured_loaded": configured_loaded,
                "endpoint": endpoint,
                # Specialist model info for config editing
                "specialist_model": specialist_model,
                "specialist_endpoint": specialist_endpoint,
                "specialist_loaded": specialist_loaded,
            }
        except Exception as e:
            logger.error(f"Failed to get loaded models: {e}")
            return {"loaded_models": [], "error": str(e)}
    
    
    @router.get("/models/check/{model_name:path}")
    async def check_model_loaded(model_name: str):
        """
        Check if a specific model is loaded and get its status.
        
        This can be used to determine if a request will need to wait for model loading.
        """
        try:
            endpoint = get_ollama_endpoint()
            status = get_model_status(model_name, endpoint)
            return status
        except Exception as e:
            logger.error(f"Failed to check model: {e}")
            return {"loaded": False, "error": str(e)}


def generate_guide_response(message: str, context: str, mentions: List[dict]) -> str:
    """Generate a response using the Guide persona (friendly, helpful)."""
    
    lower = message.lower()
    
    # Handle mentions - show ALL available data
    if mentions:
        mention = mentions[0]
        response_parts = [f"**{mention['title']}**\n"]
        
        response_parts.append(f"- **Type**: {mention['type']}")
        response_parts.append(f"- **Status**: {mention.get('status', 'Unknown')}")
        
        if mention.get('description'):
            response_parts.append(f"- **Description**: {mention['description']}")
        
        # Include all scanner data
        data = mention.get('data', {})
        if data:
            for key, value in data.items():
                if value is not None and value != "" and key not in ('context_hint',):
                    nice_key = key.replace("_", " ").title()
                    if isinstance(value, float):
                        value = f"{value:.1f}"
                    response_parts.append(f"- **{nice_key}**: {value}")
        
        response_parts.append("\nWhat would you like to know about this?")
        return "\n".join(response_parts)
    
    # Topic-based responses
    if 'backup' in lower:
        return "I can help with backups! I've discovered several backup configurations:\n\n" \
               "- **Timeshift** - System snapshots\n" \
               "- **systemd timers** - Scheduled backups\n\n" \
               "Use `@backup/` to see specific backups, or ask me to check their status."
    
    elif 'service' in lower or 'systemd' in lower:
        return "I monitor your system services. Here's what I can help with:\n\n" \
               "- Check service status\n" \
               "- Identify failed services\n" \
               "- Restart services (with approval)\n\n" \
               "Go to **Services** page for the full list."
    
    elif 'disk' in lower or 'storage' in lower:
        return "I track your storage health:\n\n" \
               "- **Disk usage** per mount\n" \
               "- **SMART status** for physical disks\n" \
               "- **Filesystem health**\n\n" \
               "Check the **Storage** page for details."
    
    elif 'network' in lower or 'internet' in lower or 'wifi' in lower:
        return "I can show you network information:\n\n" \
               "- Network interfaces and IPs\n" \
               "- Firewall status\n" \
               "- Listening ports\n\n" \
               "Visit the **Network** page for full details."
    
    elif 'help' in lower:
        return "I'm Halbert, your system companion! I can help with:\n\n" \
               "- **@mentions** - Ask about specific discoveries\n" \
               "- **Backups** - Check backup status\n" \
               "- **Services** - Monitor systemd services\n" \
               "- **Storage** - Disk health and usage\n" \
               "- **Network** - Interfaces and firewall\n\n" \
               "Just ask naturally, or use @mentions for specific items!"
    
    else:
        return "I'm here to help you understand your system. You can ask about:\n\n" \
               "- Backups and their schedules\n" \
               "- Services and their status\n" \
               "- Storage and disk health\n" \
               "- Network configuration\n\n" \
               "Try typing `@` to mention a specific discovery!"


def generate_coder_response(message: str, context: str) -> str:
    """Generate a response using the Coder persona (technical, concise)."""
    
    lower = message.lower()
    
    if 'explain' in lower:
        return "This output shows standard system information. " \
               "Key things to note:\n" \
               "- Check exit codes for success/failure\n" \
               "- Look for error or warning messages\n" \
               "- Verify expected values are present"
    
    elif 'fix' in lower:
        return "Common fixes to try:\n\n" \
               "1. Check permissions: `ls -la`\n" \
               "2. Verify path exists: `stat <path>`\n" \
               "3. Check logs: `journalctl -xe`\n" \
               "4. Run with debug: add `-v` or `--debug`"
    
    else:
        return "I'm in coder mode. Use:\n" \
               "- `/explain` - Explain last output\n" \
               "- `/fix` - Suggest fixes\n" \
               "- `/dryrun <cmd>` - Preview command"


def get_suggested_actions(message: str, mentions: List[dict]) -> List[dict]:
    """Get suggested actions based on the message."""
    actions = []
    
    if mentions:
        mention_type = mentions[0].get('type', '')
        if mention_type == 'service':
            actions.append({"id": "restart", "label": "Restart Service"})
        elif mention_type == 'backup':
            actions.append({"id": "run", "label": "Run Backup"})
    
    return actions


# ============================================================================
# Phase 18: Config Editor Chat Integration
# ============================================================================

class ConfigChatRequest(BaseModel):
    """Request for config file editing chat."""
    message: str
    file_path: str
    file_content: str
    history: List[ChatMessage] = []
    images: List[str] = []  # Vision model: Base64 encoded images


class ConfigChatResponse(BaseModel):
    """Response for config file editing chat."""
    response: str
    edit_blocks: List[dict] = []  # {search: str, replace: str} - legacy, kept for compatibility
    proposed_content: Optional[str] = None  # The file with edits applied (for IDE-style diff)
    summary: str = ""  # Brief summary of changes for the diff bar


CONFIG_EDITOR_SYSTEM_PROMPT = """You are an expert Linux system administrator and configuration file editor. You are editing:

**File:** {file_path}
**Current Date/Time:** {current_datetime}

**Current file content:**
```
{file_content}
```

When the user asks you to make changes, respond with SEARCH/REPLACE blocks using EXACTLY this format:

<<<<<<< SEARCH
[copy exact text from file above]
=======
[new replacement text]
>>>>>>> REPLACE

## CRITICAL FORMAT REQUIREMENTS:
1. The `=======` separator is MANDATORY - never omit it
2. Copy SEARCH text character-for-character from the file (including indentation, spaces, comments)
3. Put the replacement text between `=======` and `>>>>>>> REPLACE`
4. To ADD at end: SEARCH for last line(s), REPLACE with same lines + your addition

## EXAMPLE:
<<<<<<< SEARCH
    dhcp6: no # Disable IPv6
=======
    dhcp6: no # Disable IPv6
# Edited on 2024-12-13
>>>>>>> REPLACE

Added a comment with today's date.

## RESPONSE FORMAT:
1. Put ALL edit blocks FIRST (one after another if multiple changes)
2. Then provide your explanation AFTER all edit blocks
3. Keep explanations **concise** and well-formatted:
   - Use **bold** for important terms
   - Use bullet points for multiple items
   - Keep paragraphs short (2-3 sentences max)

## Remember:
- Always include `=======` between SEARCH and REPLACE
- Copy exact indentation from the file
- Multiple edits? Put ALL edit blocks together, then explain
"""


def parse_edit_blocks(response: str) -> List[dict]:
    """Parse SEARCH/REPLACE edit blocks from AI response."""
    import re
    blocks = []
    
    # Normalize line endings
    response = response.replace('\r\n', '\n').replace('\r', '\n')
    
    # More flexible pattern to handle AI output variations
    # Allows optional whitespace and handles different marker styles
    patterns = [
        # Standard format with ======= separator
        r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>>> REPLACE',
        # With potential extra text on marker lines
        r'<{7}\s*SEARCH[^\n]*\n([\s\S]*?)\n={7}[^\n]*\n([\s\S]*?)\n>{7}\s*REPLACE',
        # Simpler markers (just the arrows)
        r'<<<<<<< SEARCH\n(.*?)(?:\n)?=======\n(.*?)(?:\n)?>>>>>>> REPLACE',
        # FALLBACK: Malformed blocks without ======= separator (LLM sometimes does this)
        # Match SEARCH...REPLACE pairs and try to split the content
        r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n>>>>>>> REPLACE',
    ]
    
    for pattern_idx, pattern in enumerate(patterns):
        matches = list(re.finditer(pattern, response, re.MULTILINE | re.DOTALL))
        if matches:
            for match in matches:
                if pattern_idx < 3:
                    # Normal case: two capture groups (search and replace)
                    search_text = match.group(1).strip()
                    replace_text = match.group(2).strip()
                else:
                    # Fallback case: only one capture group, need to infer
                    # This handles malformed blocks without =======
                    content = match.group(1).strip()
                    # The LLM sometimes puts the REPLACE content after explaining
                    # Try to find if there's another SEARCH block right after
                    # For now, treat this as "delete this content" (empty replace)
                    # or log a warning
                    logger.warning(f"Malformed edit block (no ======= separator): {content[:100]}...")
                    # Skip malformed blocks - they're not usable
                    continue
                    
                if search_text:  # Only add if there's actual content
                    blocks.append({
                        'search': search_text,
                        'replace': replace_text
                    })
            if blocks:  # Only break if we found valid blocks
                break
    
    # Debug logging
    if not blocks:
        logger.debug(f"No edit blocks found in response. Response length: {len(response)}")
        # Check if response contains markers at all
        if '<<<<<<< SEARCH' in response:
            logger.warning("Response contains SEARCH marker but regex didn't match")
            logger.debug(f"Response excerpt: {response[:500]}")
    else:
        logger.debug(f"Found {len(blocks)} edit blocks")
    
    return blocks


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for fuzzy matching."""
    import re
    # Replace multiple spaces/tabs with single space, strip lines
    lines = [re.sub(r'[ \t]+', ' ', line.strip()) for line in text.split('\n')]
    return '\n'.join(lines)


def find_best_match(search: str, content: str) -> tuple[int, int] | None:
    """
    Find the best matching location for search text in content.
    Uses fuzzy matching to handle whitespace differences.
    
    Returns (start, end) indices or None if no match found.
    """
    import difflib
    
    # First try exact match
    if search in content:
        start = content.index(search)
        return (start, start + len(search))
    
    # Try normalized whitespace match
    search_norm = normalize_whitespace(search)
    content_norm = normalize_whitespace(content)
    
    if search_norm in content_norm:
        # Find the position in normalized content
        norm_start = content_norm.index(search_norm)
        
        # Map back to original content by counting lines
        search_lines = search_norm.count('\n') + 1
        content_lines = content.split('\n')
        norm_lines = content_norm.split('\n')
        
        # Find which original lines match
        line_start = content_norm[:norm_start].count('\n')
        line_end = line_start + search_lines
        
        # Get the original text span
        original_start = sum(len(line) + 1 for line in content_lines[:line_start])
        original_end = sum(len(line) + 1 for line in content_lines[:line_end])
        
        # Trim trailing newline if necessary
        if original_end > len(content):
            original_end = len(content)
            
        return (original_start, original_end)
    
    # Try line-by-line fuzzy matching
    search_lines = search.strip().split('\n')
    content_lines = content.split('\n')
    
    if len(search_lines) == 0:
        return None
        
    # Use SequenceMatcher to find similar blocks
    matcher = difflib.SequenceMatcher(None, 
        [normalize_whitespace(l) for l in content_lines],
        [normalize_whitespace(l) for l in search_lines]
    )
    
    # Find matching blocks
    blocks = matcher.get_matching_blocks()
    
    # If we have a good match (>70% of lines match), use it
    total_matched = sum(b.size for b in blocks)
    if total_matched >= len(search_lines) * 0.7:
        # Find the best contiguous block
        for block in blocks:
            if block.size >= len(search_lines) * 0.5:
                start_line = block.a
                end_line = start_line + len(search_lines)
                
                original_start = sum(len(line) + 1 for line in content_lines[:start_line])
                original_end = sum(len(line) + 1 for line in content_lines[:end_line])
                
                if original_end > len(content):
                    original_end = len(content)
                    
                return (original_start, original_end)
    
    return None


def apply_edit_blocks(content: str, edit_blocks: List[dict]) -> tuple[str, bool, str]:
    """
    Apply edit blocks to file content with fuzzy matching.
    
    Args:
        content: Original file content
        edit_blocks: List of {search: str, replace: str} dicts
    
    Returns:
        Tuple of (new_content, success, error_message)
    """
    if not edit_blocks:
        return content, False, "No edit blocks to apply"
    
    new_content = content
    applied_count = 0
    
    for block in edit_blocks:
        search = block.get('search', '').strip()
        replace = block.get('replace', '')
        
        if not search:
            continue
            
        # Try exact match first
        if search in new_content:
            new_content = new_content.replace(search, replace, 1)
            applied_count += 1
            logger.debug(f"Applied exact edit: {len(search)} chars -> {len(replace)} chars")
        else:
            # Try fuzzy match
            match = find_best_match(search, new_content)
            if match:
                start, end = match
                new_content = new_content[:start] + replace + new_content[end:]
                applied_count += 1
                logger.debug(f"Applied fuzzy edit: {end-start} chars -> {len(replace)} chars")
            else:
                logger.warning(f"Could not find search text (even fuzzy): {search[:50]}...")
    
    if applied_count == 0:
        return content, False, "Could not find any matching text to replace"
    
    logger.info(f"Applied {applied_count}/{len(edit_blocks)} edit blocks")
    return new_content, True, ""


def extract_summary_from_response(response: str) -> str:
    """Extract a brief summary from the AI response (text after edit blocks)."""
    # Remove edit blocks from response to get just the explanation
    import re
    # Remove all edit block patterns
    clean = re.sub(r'<<<<<<< SEARCH.*?>>>>>>> REPLACE', '', response, flags=re.DOTALL)
    # Get first sentence or first 100 chars
    clean = clean.strip()
    if not clean:
        return "Made changes to the file"
    
    # Get first sentence
    sentences = clean.split('.')
    if sentences and sentences[0].strip():
        summary = sentences[0].strip()
        if len(summary) > 100:
            summary = summary[:97] + "..."
        return summary
    
    return clean[:100] if len(clean) > 100 else clean


if FASTAPI_AVAILABLE:
    
    @router.post("/config", response_model=ConfigChatResponse)
    async def config_chat(request: ConfigChatRequest):
        """
        Chat endpoint for config file editing.
        
        Provides file content as context and parses edit blocks from response.
        """
        message = request.message.strip()
        file_path = request.file_path
        file_content = request.file_content
        history = request.history
        
        # Get current local datetime with timezone
        from datetime import datetime
        import time
        # Get local time with timezone name (check if DST is currently in effect)
        local_time = datetime.now()
        is_dst = time.localtime().tm_isdst > 0
        tz_name = time.tzname[1] if is_dst else time.tzname[0]
        current_datetime = local_time.strftime(f"%Y-%m-%d %H:%M {tz_name}")
        
        # Build system prompt with file context
        system_prompt = CONFIG_EDITOR_SYSTEM_PROMPT.format(
            file_path=file_path,
            file_content=file_content,
            current_datetime=current_datetime
        )
        
        # Add custom AI rules
        try:
            rules_context = get_custom_ai_rules()
            if rules_context:
                system_prompt += f"\n\n{rules_context}"
        except Exception:
            pass
        
        # Build conversation messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add history
        for msg in history[-10:]:  # Last 10 messages for context
            messages.append({"role": msg.role, "content": msg.content})
        
        # Add current message (with images if present for vision models)
        user_message = {"role": "user", "content": message}
        if request.images:
            user_message["images"] = request.images
            logger.info(f"Config chat with {len(request.images)} images")
        messages.append(user_message)
        
        # Call LLM - prefer specialist model for config editing (coding task)
        try:
            # Try to use specialist model for better code editing
            model_router = get_model_router()
            specialist_config = model_router.config.get("specialist", {})
            if specialist_config.get("enabled") and specialist_config.get("model"):
                model = specialist_config.get("model")
                # Use specialist endpoint if configured, otherwise default
                endpoint = specialist_config.get("endpoint", get_ollama_endpoint())
                logger.info(f"Using specialist model for config editing: {model} at {endpoint}")
            else:
                model = get_configured_model()
                endpoint = get_ollama_endpoint()
                logger.info(f"Using guide model for config editing: {model} (no specialist configured)")
            
            response = requests.post(
                f"{endpoint}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,  # Lower temperature for more precise edits
                        "num_predict": 4096  # More tokens for full file edits
                    }
                },
                timeout=180  # Longer timeout for larger models
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get('message', {}).get('content', '')
                
                # Parse edit blocks
                edit_blocks = parse_edit_blocks(ai_response)
                
                # Apply edits to create proposed content (IDE-style diff)
                proposed_content = None
                summary = ""
                if edit_blocks:
                    new_content, success, error = apply_edit_blocks(file_content, edit_blocks)
                    if success:
                        proposed_content = new_content
                        summary = extract_summary_from_response(ai_response)
                        logger.info(f"Created proposed content for diff view: {summary}")
                    else:
                        logger.warning(f"Could not apply edits: {error}")
                
                return ConfigChatResponse(
                    response=ai_response,
                    edit_blocks=edit_blocks,
                    proposed_content=proposed_content,
                    summary=summary
                )
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ConfigChatResponse(
                    response="Sorry, I couldn't connect to the AI model. Please check that Ollama is running.",
                    edit_blocks=[],
                    proposed_content=None,
                    summary=""
                )
                
        except requests.exceptions.Timeout:
            return ConfigChatResponse(
                response="Request timed out. The model might be loading.",
                edit_blocks=[]
            )
        except Exception as e:
            logger.error(f"Config chat error: {e}")
            return ConfigChatResponse(
                response=f"Error: {str(e)}",
                edit_blocks=[]
            )
    
    
    @router.get("/memory/stats")
    async def get_memory_stats():
        """
        Get memory system statistics.
        
        Returns ChromaDB collection counts and status.
        """
        try:
            index = get_index()
            stats = index.get_stats()
            return {
                "status": "ok",
                "chromadb_available": stats.get("chromadb_available", False),
                "persist_path": stats.get("persist_path"),
                "memory_events": stats.get("memory_events", 0),
                "collections": stats.get("collections", {}),
            }
        except Exception as e:
            logger.error(f"Memory stats error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "chromadb_available": False,
            }
    
    
    @router.post("/memory/query")
    async def query_memory(query: str, k: int = 5, collection: Optional[str] = None):
        """
        Query the memory system directly.
        
        Args:
            query: Search query
            k: Number of results
            collection: Specific collection to search
        """
        try:
            index = get_index()
            results = index.query(query, k=k, collection=collection)
            return {
                "status": "ok",
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            logger.error(f"Memory query error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "results": [],
            }
    
    
    @router.get("/memory/collections")
    async def list_memory_collections():
        """List all memory collections with counts."""
        try:
            index = get_index()
            collections = index.list_collections()
            return {
                "status": "ok",
                "collections": collections,
            }
        except Exception as e:
            logger.error(f"List collections error: {e}")
            return {"status": "error", "error": str(e), "collections": []}
    
    
    @router.get("/memory/entries/{collection}")
    async def list_memory_entries(collection: str, limit: int = 50, offset: int = 0):
        """List entries in a specific collection."""
        try:
            index = get_index()
            entries = index.list_entries(collection, limit=limit, offset=offset)
            return {
                "status": "ok",
                "collection": collection,
                "entries": entries,
                "count": len(entries),
            }
        except Exception as e:
            logger.error(f"List entries error: {e}")
            return {"status": "error", "error": str(e), "entries": []}
    
    
    @router.get("/memory/entry/{collection}/{entry_id:path}")
    async def get_memory_entry(collection: str, entry_id: str):
        """Get a specific entry by ID."""
        try:
            index = get_index()
            entry = index.get_entry(collection, entry_id)
            if entry:
                return {"status": "ok", "entry": entry}
            return {"status": "error", "error": "Entry not found"}
        except Exception as e:
            logger.error(f"Get entry error: {e}")
            return {"status": "error", "error": str(e)}
    
    
    @router.delete("/memory/entry/{collection}/{entry_id:path}")
    async def delete_memory_entry(collection: str, entry_id: str):
        """Delete a specific entry."""
        try:
            index = get_index()
            success = index.delete_entry(collection, entry_id)
            return {"status": "ok" if success else "error", "deleted": success}
        except Exception as e:
            logger.error(f"Delete entry error: {e}")
            return {"status": "error", "error": str(e)}
    
    
    class DeleteEntriesRequest(BaseModel):
        entry_ids: List[str]
    
    
    @router.post("/memory/delete/{collection}")
    async def delete_memory_entries(collection: str, request: DeleteEntriesRequest):
        """Delete multiple entries from a collection."""
        try:
            index = get_index()
            count = index.delete_entries(collection, request.entry_ids)
            return {"status": "ok", "deleted": count}
        except Exception as e:
            logger.error(f"Delete entries error: {e}")
            return {"status": "error", "error": str(e)}
    
    
    @router.post("/memory/clear/{collection}")
    async def clear_memory_collection(collection: str):
        """Clear all entries from a collection. USE WITH CAUTION."""
        try:
            index = get_index()
            success = index.clear_collection(collection)
            return {"status": "ok" if success else "error", "cleared": success}
        except Exception as e:
            logger.error(f"Clear collection error: {e}")
            return {"status": "error", "error": str(e)}
