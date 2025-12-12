"""
Chat API routes.

Provides endpoints for AI chat interactions.
Uses the discovery engine for context and (optionally) local LLM.
"""

from __future__ import annotations
import logging
from typing import Optional, List

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

from ..routes.discovery import get_engine
from ...model.router import ModelRouter, TaskType
from ...discovery.schema import DiscoveryType
from pathlib import Path
import socket
import json
import requests

logger = logging.getLogger('halbert.dashboard.routes.chat')


def get_ollama_endpoint() -> str:
    """Get the Ollama endpoint URL from config (guide model's endpoint)."""
    try:
        from ...utils.platform import get_config_dir
        import yaml
        
        config_path = get_config_dir() / 'models.yml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            # Use orchestrator/guide endpoint if configured
            orch = config.get('orchestrator', {})
            if orch.get('endpoint'):
                return orch['endpoint']
        
        # Default fallback
        return "http://localhost:11434"
    except Exception:
        return "http://localhost:11434"


def get_configured_model() -> str:
    """Get the configured guide model name from config."""
    try:
        from ...utils.platform import get_config_dir
        import yaml
        
        config_path = get_config_dir() / 'models.yml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            orch = config.get('orchestrator', {})
            if orch.get('model'):
                return orch['model']
        
        return "llama3.1:8b"
    except Exception:
        return "llama3.1:8b"


# Phase 12d: Tool-use support
def call_ollama_with_tools(prompt: str, system_prompt: str, model: str = None) -> tuple:
    """
    Call Ollama with tool support using the /api/chat endpoint.
    
    Returns (response_text, tool_calls) where tool_calls is a list of
    tool invocations if the LLM wants to use tools.
    """
    try:
        from ...tools.system_tools import SYSTEM_TOOLS, execute_tool
        
        # Get endpoint and model from config if not specified
        endpoint = get_ollama_endpoint()
        if model is None:
            model = get_configured_model()
        
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
            
            # Execute the tool
            result = execute_tool(tool_name, arguments)
            tool_results.append({
                "tool": tool_name,
                "result": result.data if result.success else {"error": result.error}
            })
        
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

# Phase 12c: RAG Pipeline singleton for documentation retrieval
_rag_pipeline = None
_rag_loading = False


def get_rag_pipeline():
    """Get or create the RAG pipeline singleton (lazy loaded)."""
    global _rag_pipeline, _rag_loading
    
    if _rag_pipeline is not None:
        return _rag_pipeline
    
    if _rag_loading:
        return None  # Still loading, skip RAG for this request
    
    try:
        _rag_loading = True
        from ...rag.pipeline import RAGPipeline
        
        # Find data directory
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        data_dir = repo_root / 'data'
        
        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            return None
        
        logger.info("Initializing RAG pipeline for chat...")
        pipeline = RAGPipeline(
            data_dir=data_dir,
            embedding_model="all-MiniLM-L6-v2",
            use_reranking=False,  # Faster without reranking
            top_k=3,  # Get top 3 documents
            max_context_length=2048
        )
        
        # Load and index documents
        merged_file = data_dir / 'linux' / 'merged' / 'rag_corpus_merged.jsonl'
        if merged_file.exists():
            pipeline.load_and_index_documents(jsonl_path=merged_file)
            _rag_pipeline = pipeline
            logger.info("RAG pipeline ready for chat")
        else:
            logger.warning(f"RAG corpus not found: {merged_file}")
            
    except Exception as e:
        logger.error(f"Failed to initialize RAG pipeline: {e}")
    finally:
        _rag_loading = False
    
    return _rag_pipeline


def get_rag_context(query: str, max_chars: int = 1500) -> str:
    """
    Retrieve relevant documentation context for a query.
    
    Phase 12c: RAG integration for knowledge grounding.
    """
    try:
        pipeline = get_rag_pipeline()
        if pipeline is None:
            return ""
        
        # Retrieve relevant documents
        documents = pipeline.retrieve(query)
        
        if not documents:
            return ""
        
        # Build concise context
        context_parts = ["\n=== DOCUMENTATION ==="]
        total_chars = 0
        
        for doc in documents:
            name = doc.get('name', 'Unknown')
            section = doc.get('section', '')
            description = doc.get('description', '')
            content = doc.get('full_text', doc.get('content', ''))[:500]  # First 500 chars
            
            if section:
                header = f"\n[{name}({section})]"
            else:
                header = f"\n[{name}]"
            
            entry = header
            if description:
                entry += f"\n{description}"
            if content:
                entry += f"\n{content}"
            
            if total_chars + len(entry) > max_chars:
                break
            
            context_parts.append(entry)
            total_chars += len(entry)
        
        return "\n".join(context_parts) if len(context_parts) > 1 else ""
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return ""


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


def should_use_web_search(query: str) -> bool:
    """
    Determine if a query would benefit from web search.
    
    Returns True if the query:
    - Contains patterns suggesting need for current info
    - Asks about versions, best practices, etc.
    - Contains words suggesting external research needed
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


class ChatResponse(BaseModel):
    response: str
    mentions_resolved: List[dict] = []
    suggested_actions: List[dict] = []
    debug: Optional[dict] = None  # Debug info when requested


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
        
        # Storage/disk/filesystem keywords -> auto-inject storage context
        storage_keywords = ['disk', 'storage', 'drive', 'filesystem', 'mount', 'bcachefs', 
                           'btrfs', 'zfs', 'raid', 'nvme', 'ssd', 'hdd', 'partition']
        if any(kw in message_lower for kw in storage_keywords):
            # Get all storage discoveries for context
            try:
                storage_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'storage']
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
                backup_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'backup']
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
                service_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'service']
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
                network_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'network']
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
                security_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'security']
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
                container_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'container']
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
                gpu_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'gpu']
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
                sharing_discoveries = [d for d in engine.discoveries.values() if d.type.value == 'sharing']
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
                dev_discoveries = [d for d in engine.discoveries.values() 
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
            
            # Build system prompt based on persona
            if persona == "coder":
                # Phase 12e: ReAct-style prompting for complex reasoning
                system_prompt = (
                    f"You are {ai_name}, a Linux system administration AI assistant in coder mode. "
                    "Provide technical, concise responses. Focus on commands, scripts, and solutions. "
                    "Be direct and efficient.\n\n"
                    "COMMAND FORMATTING:\n"
                    "- Put each shell command in its own markdown code block with ```bash\n"
                    "- If giving multiple commands, put each in a SEPARATE code block with a brief description\n"
                    "- Never put multiple commands in the same code block unless they must run together (use && or ;)\n\n"
                    f"{system_identity}"
                    f"{custom_rules}\n\n"
                    "IMPORTANT: Always ground your responses in THIS specific system's actual state. "
                    "If asked about something not present on this system, say so clearly.\n\n"
                    
                    "REASONING PATTERN (for complex questions):\n"
                    "When solving multi-step problems, use this pattern:\n"
                    "1. **Thought**: Briefly explain what you need to check or do\n"
                    "2. **Action**: The command or tool to use\n"
                    "3. **Observation**: What the result shows\n"
                    "4. **Answer**: Your final response based on observations\n\n"
                    
                    "Example:\n"
                    "User: Why is my disk filling up?\n"
                    "**Thought**: I should check current disk usage first.\n"
                    "**Action**: `df -h /`\n"
                    "**Observation**: Root is 85% full with /var/log consuming significant space.\n"
                    "**Answer**: Your root filesystem is 85% full. The main culprit is /var/log...\n\n"
                    
                    "UNCERTAINTY - Ask for clarification:\n"
                    "- If a question is unclear, simply say 'Could you rephrase that?'\n"
                    "- Do NOT guess what the user meant - ask instead."
                )
                task_type = TaskType.CODE_GENERATION
            else:
                system_prompt = (
                    f"You are {ai_name}, a friendly Linux system administration assistant. "
                    "Help users understand their system in a warm, conversational way. "
                    "Explain technical concepts clearly. You can discuss backups, services, "
                    "storage, network, and security. "
                    "COMMAND FORMATTING:\n"
                    "- Put each shell command in its own markdown code block with ```bash\n"
                    "- If giving multiple commands, put each in a SEPARATE code block with a brief description\n"
                    "- Never put multiple commands in the same code block unless they must run together (use && or ;)\n\n"
                    f"{system_identity}"
                    f"{custom_rules}\n\n"
                    "IMPORTANT: Always ground your responses in THIS specific system's actual state. "
                    "If asked about something not present on this system, say so clearly before offering general advice.\n\n"
                    "UI CONTEXT AWARENESS:\n"
                    "- The user may be viewing a specific page (Network, Storage, etc.) and asking about what they see.\n"
                    "- When the context shows network interfaces with 'Down' status, this means the interface has no IP or carrier.\n"
                    "- When asking 'why is this down', check the context for clues (bridge ports, bond slaves, missing cables).\n"
                    "- A bond showing 'Down' often means not enough physical interfaces are connected.\n"
                    "- A bridge port showing 'Bridged to X' with no IP is normal - the bridge interface holds the IP.\n"
                    "- Answer based on the provided context first, before suggesting commands.\n\n"
                    "RESPONSE LENGTH - Be concise:\n"
                    "- Match response length to question complexity. Simple questions get 1-2 sentence answers.\n"
                    "- Don't pad responses with unnecessary filler or repetition.\n"
                    "- For clarification requests, just ask the question briefly - don't explain why you're asking.\n"
                    "- Only provide detailed explanations when the question actually warrants depth.\n\n"
                    "UNCERTAINTY - Ask for clarification:\n"
                    "- If a question is unclear or doesn't make sense, simply say 'Could you rephrase that?' - nothing more.\n"
                    "- Do NOT confidently answer questions you don't understand.\n"
                    "- Don't explain what clarification means or why you need it - just ask briefly."
                )
                task_type = TaskType.CHAT
            
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
            
            # Phase 12c: RAG documentation retrieval (skip for unclear queries)
            if not unclear_query:
                rag_context = get_rag_context(message)
                if rag_context:
                    full_prompt += f"{rag_context}\n\n"
                
                # Web search for queries needing current information
                if should_use_web_search(message):
                    logger.info(f"Query triggers web search: {message[:50]}...")
                    web_context = await get_web_search_context(message)
                    if web_context:
                        full_prompt += f"{web_context}\n\n"
            else:
                # Add a hint that this query seems unclear
                full_prompt += "NOTE: The user's query seems unclear or vague. Ask for clarification rather than guessing.\n\n"
            
            # Phase 12d: Try tool-calling for real-time queries
            tool_response = None
            tool_results = []
            if should_use_tools(message):
                logger.info("Query may benefit from tool use, trying tool-calling...")
                tool_response, tool_results = call_ollama_with_tools(
                    prompt=message,
                    system_prompt=system_prompt
                )
            
            if tool_response:
                response = tool_response
                if tool_results:
                    logger.info(f"Tool-calling succeeded with {len(tool_results)} tool calls")
            else:
                # Standard generation (no tool use or tool-calling failed)
                full_prompt += f"User: {message}\n\nAssistant:"
                
                # Generate response using the LLM
                llm_response = model_router.generate(
                    prompt=full_prompt,
                    task_type=task_type,
                    max_tokens=1024,
                    temperature=0.7
                )
                
                response = llm_response.text.strip()
                logger.info(f"LLM response generated ({llm_response.tokens_used} tokens)")
                
                # Track model info for debug
                if debug_info:
                    debug_info['model_used'] = get_configured_model()
                    debug_info['endpoint_used'] = get_ollama_endpoint()
                    debug_info['tokens_used'] = llm_response.tokens_used
                    debug_info['generation_time_ms'] = int((time.time() - start_time) * 1000)
            
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
        
        return ChatResponse(
            response=response,
            mentions_resolved=mentions_resolved,
            suggested_actions=get_suggested_actions(message, mentions_resolved),
            debug=debug_info,
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
    async def get_model_status():
        """Get detailed model router status."""
        try:
            model_router = get_model_router()
            return model_router.get_status()
        except Exception as e:
            logger.error(f"Failed to get model status: {e}")
            return {"error": str(e)}


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


class ConfigChatResponse(BaseModel):
    """Response for config file editing chat."""
    response: str
    edit_blocks: List[dict] = []  # {search: str, replace: str}


CONFIG_EDITOR_SYSTEM_PROMPT = """You are a Linux configuration file editor assistant. You are currently editing:

**File:** {file_path}

**Current file content:**
```
{file_content}
```

When the user asks you to make changes to this file, respond with SEARCH/REPLACE edit blocks.

**FORMAT for edits:**
<<<<<<< SEARCH
exact text to find in the file
=======
replacement text
>>>>>>> REPLACE

**Rules:**
1. The SEARCH section must match EXACTLY what's in the file (including whitespace)
2. You can include multiple edit blocks for multiple changes
3. For adding content at the end, search for the last few lines and include them with the new content
4. Always explain what you're changing and why
5. If you're unsure about syntax, explain the change instead of making it

**Example - Adding a comment at the end:**
To add "# edited" at the end, I'll include the last line and add the comment:

<<<<<<< SEARCH
last line of file
=======
last line of file
# edited
>>>>>>> REPLACE
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
        # Standard format
        r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>>> REPLACE',
        # With potential extra text on marker lines
        r'<{7}\s*SEARCH[^\n]*\n([\s\S]*?)\n={7}[^\n]*\n([\s\S]*?)\n>{7}\s*REPLACE',
        # Simpler markers (just the arrows)
        r'<<<<<<< SEARCH\n(.*?)(?:\n)?=======\n(.*?)(?:\n)?>>>>>>> REPLACE',
    ]
    
    for pattern in patterns:
        matches = list(re.finditer(pattern, response, re.MULTILINE))
        if matches:
            for match in matches:
                search_text = match.group(1).strip()
                replace_text = match.group(2).strip()
                if search_text:  # Only add if there's actual content
                    blocks.append({
                        'search': search_text,
                        'replace': replace_text
                    })
            break  # Stop after first pattern that matches
    
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
        
        # Build system prompt with file context
        system_prompt = CONFIG_EDITOR_SYSTEM_PROMPT.format(
            file_path=file_path,
            file_content=file_content
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
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Call LLM
        try:
            endpoint = get_ollama_endpoint()
            model = get_configured_model()
            
            response = requests.post(
                f"{endpoint}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # Lower temperature for more precise edits
                        "num_predict": 2048
                    }
                },
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get('message', {}).get('content', '')
                
                # Parse edit blocks
                edit_blocks = parse_edit_blocks(ai_response)
                
                return ConfigChatResponse(
                    response=ai_response,
                    edit_blocks=edit_blocks
                )
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ConfigChatResponse(
                    response="Sorry, I couldn't connect to the AI model. Please check that Ollama is running.",
                    edit_blocks=[]
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
