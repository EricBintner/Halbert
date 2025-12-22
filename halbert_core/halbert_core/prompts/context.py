"""
Context Injector - Generate dynamic context for prompt injection.

Part of Phase 40: Prompt Infrastructure
Expands in Phase 42: Dynamic Context Engine
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import platform
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """A single RAG retrieval result."""
    content: str
    source: str
    source_type: str = "doc"  # man, arch, doc, web, note
    relevance: float = 0.0
    
    @property
    def source_uri(self) -> str:
        """Format source as URI."""
        return f"{self.source_type}://{self.source}"


class RAGFormatter:
    """Format RAG results for prompt injection with citations."""
    
    CONFIDENCE_THRESHOLDS = [
        (0.9, "High confidence - state as fact"),
        (0.7, "Medium - 'Based on documentation...'"),
        (0.5, "Low - 'This might help, but verify...'"),
        (0.0, "Very low - 'I'm not certain, but...'"),
    ]
    
    def format_results(self, results: List[RAGResult]) -> str:
        """
        Format RAG results as XML for prompt injection.
        
        Args:
            results: List of RAG retrieval results
            
        Returns:
            XML-formatted RAG results block
        """
        if not results:
            return ""
        
        lines = ["<rag_results>"]
        
        for i, result in enumerate(results, 1):
            source_uri = result.source_uri
            relevance = result.relevance
            content = result.content.strip()
            
            lines.append(
                f'  <result index="{i}" source="{source_uri}" relevance="{relevance:.2f}">'
            )
            # Indent content lines
            for line in content.split("\n"):
                lines.append(f"    {line}")
            lines.append("  </result>")
        
        # Add citation instructions
        lines.append("  <citation_instructions>")
        lines.append("    When using information from RAG results:")
        lines.append("    - Cite using [source:index] format, e.g., [man:1], [arch:2]")
        lines.append("    - Prioritize higher relevance results")
        lines.append("    - Acknowledge uncertainty if relevance is below 0.7")
        lines.append("    - Never fabricate sources not present in results")
        lines.append("  </citation_instructions>")
        
        lines.append("</rag_results>")
        
        return "\n".join(lines)
    
    def get_confidence_level(self, relevance: float) -> str:
        """Get confidence description for a relevance score."""
        for threshold, description in self.CONFIDENCE_THRESHOLDS:
            if relevance >= threshold:
                return description
        return self.CONFIDENCE_THRESHOLDS[-1][1]
    
    def format_from_reflection(self, reflection_result: Any) -> str:
        """
        Format RAG results from a SelfReflector ReflectionResult (Phase 28/29 integration).
        
        Args:
            reflection_result: ReflectionResult from SelfReflector.reflect()
            
        Returns:
            XML-formatted RAG results block with CRAG metadata
        """
        if not hasattr(reflection_result, 'retrieved_contexts') or not reflection_result.retrieved_contexts:
            return ""
        
        rag_results = []
        for ctx in reflection_result.retrieved_contexts:
            rag_results.append(RAGResult(
                content=ctx.entry.content if hasattr(ctx, 'entry') else str(ctx),
                source=ctx.entry.subject if hasattr(ctx, 'entry') else "unknown",
                source_type=ctx.entry.type.value if hasattr(ctx, 'entry') and hasattr(ctx.entry, 'type') else "doc",
                relevance=ctx.combined_score if hasattr(ctx, 'combined_score') else 0.5,
            ))
        
        # Add CRAG action as metadata
        formatted = self.format_results(rag_results)
        
        # Append CRAG metadata if available
        if hasattr(reflection_result, 'crag_action'):
            crag_line = f'\n  <!-- CRAG action: {reflection_result.crag_action.value} -->'
            formatted = formatted.replace('</rag_results>', f'{crag_line}\n</rag_results>')
        
        return formatted
    
    def deduplicate_results(self, results: List[RAGResult], similarity_threshold: float = 0.9) -> List[RAGResult]:
        """
        Remove duplicate or near-duplicate RAG results.
        
        Uses simple content hash comparison for exact duplicates.
        For near-duplicates, compares first 100 chars.
        
        Args:
            results: List of RAG results
            similarity_threshold: Threshold for considering results similar (unused for now)
            
        Returns:
            Deduplicated list, keeping highest relevance for duplicates
        """
        if not results:
            return []
        
        seen_hashes: Dict[str, RAGResult] = {}
        seen_prefixes: Dict[str, RAGResult] = {}
        
        for result in results:
            content = result.content.strip()
            content_hash = hash(content)
            content_prefix = content[:100].lower()
            
            # Check exact duplicate
            if content_hash in seen_hashes:
                existing = seen_hashes[content_hash]
                if result.relevance > existing.relevance:
                    seen_hashes[content_hash] = result
                continue
            
            # Check near-duplicate (same prefix)
            if content_prefix in seen_prefixes:
                existing = seen_prefixes[content_prefix]
                if result.relevance > existing.relevance:
                    seen_prefixes[content_prefix] = result
                    seen_hashes[hash(existing.content.strip())] = result
                continue
            
            seen_hashes[content_hash] = result
            seen_prefixes[content_prefix] = result
        
        # Return unique results sorted by relevance
        unique = list(seen_hashes.values())
        unique.sort(key=lambda r: r.relevance, reverse=True)
        return unique
    
    def format_from_dicts(self, results: List[Dict[str, Any]], deduplicate: bool = True) -> str:
        """
        Format RAG results from dictionary format.
        
        Args:
            results: List of dicts with 'content', 'source', 'relevance' keys
            deduplicate: Whether to remove duplicate results
            
        Returns:
            XML-formatted RAG results block
        """
        rag_results = []
        for r in results:
            rag_results.append(RAGResult(
                content=r.get("content", ""),
                source=r.get("source", "unknown"),
                source_type=r.get("source_type", "doc"),
                relevance=r.get("relevance", 0.0),
            ))
        
        # Deduplicate if requested
        if deduplicate:
            rag_results = self.deduplicate_results(rag_results)
        
        return self.format_results(rag_results)


@dataclass
class SystemContext:
    """System state for context injection."""
    os_name: str = ""
    os_version: str = ""
    hostname: str = ""
    username: str = ""
    shell: str = ""
    uptime: str = ""
    load_average: str = ""
    memory_used: str = ""
    memory_total: str = ""
    memory_percent: float = 0.0
    disk_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    package_manager: str = ""
    init_system: str = ""
    active_services: List[str] = field(default_factory=list)
    cwd: str = ""
    last_command: str = ""


@dataclass  
class UserPreferences:
    """User preferences for context injection."""
    verbosity: str = "concise"  # minimal, concise, detailed, verbose
    confirmation_level: str = "destructive_only"  # always, destructive_only, never
    expertise_level: str = "intermediate"  # beginner, intermediate, advanced, expert
    preferred_shell: str = "bash"
    preferred_editor: str = "vim"
    show_reasoning: str = "complex_only"  # always, complex_only, never
    auto_execute_safe: bool = False


class ContextInjector:
    """
    Generate and format dynamic context for prompt injection.
    
    This class gathers system information and formats it for
    inclusion in the system prompt.
    """
    
    def __init__(self, discovery_engine: Optional[Any] = None):
        """
        Initialize context injector.
        
        Args:
            discovery_engine: Optional Discovery Engine for richer context
        """
        self.discovery_engine = discovery_engine
    
    def get_system_context(self) -> SystemContext:
        """
        Gather current system context.
        
        Returns:
            SystemContext with current system state
        """
        ctx = SystemContext()
        
        # Basic OS info
        ctx.os_name = platform.system()
        ctx.os_version = platform.release()
        ctx.hostname = platform.node()
        ctx.username = os.getenv("USER", os.getenv("USERNAME", "unknown"))
        ctx.shell = os.getenv("SHELL", "unknown")
        ctx.cwd = os.getcwd()
        
        # Detect package manager
        ctx.package_manager = self._detect_package_manager()
        
        # Detect init system
        ctx.init_system = self._detect_init_system()
        
        # If discovery engine available, get richer context
        if self.discovery_engine:
            try:
                self._enrich_from_discovery(ctx)
            except Exception as e:
                logger.warning(f"Failed to enrich context from discovery: {e}")
        
        return ctx
    
    def format_system_context(self, ctx: SystemContext) -> str:
        """
        Format SystemContext as XML for prompt injection.
        
        Args:
            ctx: SystemContext to format
            
        Returns:
            XML-formatted context string
        """
        lines = ["<system_context>"]
        
        lines.append(f"  <os>{ctx.os_name} {ctx.os_version}</os>")
        lines.append(f"  <hostname>{ctx.hostname}</hostname>")
        lines.append(f"  <user>{ctx.username}</user>")
        lines.append(f"  <shell>{ctx.shell}</shell>")
        
        if ctx.uptime:
            lines.append(f"  <uptime>{ctx.uptime}</uptime>")
        
        if ctx.load_average:
            lines.append(f"  <load_average>{ctx.load_average}</load_average>")
        
        if ctx.memory_total:
            lines.append(
                f"  <memory>{ctx.memory_used} / {ctx.memory_total} "
                f"({ctx.memory_percent:.0f}%)</memory>"
            )
        
        if ctx.disk_usage:
            lines.append("  <disk_usage>")
            for mount, info in ctx.disk_usage.items():
                used_pct = info.get("percent", 0)
                lines.append(f"    <mount path=\"{mount}\">{used_pct}% used</mount>")
            lines.append("  </disk_usage>")
        
        lines.append(f"  <package_manager>{ctx.package_manager}</package_manager>")
        lines.append(f"  <init_system>{ctx.init_system}</init_system>")
        
        if ctx.active_services:
            services = ", ".join(ctx.active_services[:10])  # Limit to 10
            lines.append(f"  <active_services>{services}</active_services>")
        
        lines.append(f"  <cwd>{ctx.cwd}</cwd>")
        
        lines.append("</system_context>")
        
        return "\n".join(lines)
    
    def format_user_preferences(self, prefs: UserPreferences) -> str:
        """
        Format UserPreferences as XML for prompt injection.
        
        Args:
            prefs: UserPreferences to format
            
        Returns:
            XML-formatted preferences string
        """
        lines = ["<user_preferences>"]
        
        lines.append(f"  <verbosity>{prefs.verbosity}</verbosity>")
        lines.append(f"  <confirmation_level>{prefs.confirmation_level}</confirmation_level>")
        lines.append(f"  <expertise_level>{prefs.expertise_level}</expertise_level>")
        lines.append(f"  <preferred_shell>{prefs.preferred_shell}</preferred_shell>")
        lines.append(f"  <preferred_editor>{prefs.preferred_editor}</preferred_editor>")
        lines.append(f"  <show_reasoning>{prefs.show_reasoning}</show_reasoning>")
        
        auto_exec = "true" if prefs.auto_execute_safe else "false"
        lines.append(f"  <auto_execute_safe>{auto_exec}</auto_execute_safe>")
        
        lines.append("</user_preferences>")
        
        return "\n".join(lines)
    
    def format_conversation_history(
        self,
        history: List[Dict[str, str]],
        tier: str = "specialist",
        max_turns: Optional[int] = None,
        max_chars_per_turn: Optional[int] = None,
    ) -> str:
        """
        Format conversation history as XML for prompt injection.
        
        Token budgets per tier (from conversation.xml template):
        - guide: 3 turns, 300 chars
        - specialist: 5 turns, 500 chars
        - vision: 3 turns, 400 chars
        
        Args:
            history: List of {role, content} dicts
            tier: Model tier for token budget selection
            max_turns: Override max turns (optional)
            max_chars_per_turn: Override max chars (optional)
            
        Returns:
            XML-formatted conversation context
        """
        if not history:
            return ""
        
        # Tier-specific defaults
        tier_budgets = {
            "guide": (3, 300),
            "specialist": (5, 500),
            "vision": (3, 400),
        }
        default_turns, default_chars = tier_budgets.get(tier, (5, 500))
        
        turns_limit = max_turns if max_turns is not None else default_turns
        chars_limit = max_chars_per_turn if max_chars_per_turn is not None else default_chars
        
        # Take last N turns
        recent = history[-turns_limit:]
        
        lines = ["<conversation_context>"]
        
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            
            # Skip system messages
            if role == "system":
                continue
            
            # Truncate if needed
            if len(content) > chars_limit:
                content = content[:chars_limit] + "..."
            
            # Escape XML special chars
            content = (
                content
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            
            lines.append(f'  <turn role="{role}">{content}</turn>')
        
        lines.append("</conversation_context>")
        
        return "\n".join(lines)
    
    def load_project_context(self, project_dir: Path) -> Optional[str]:
        """
        Load project context from HALBERT.md or similar files.
        
        Checks for:
        - HALBERT.md
        - .halbert/context.md
        - agents.md (Warp compatibility)
        - GEMINI.md (Gemini CLI compatibility)
        
        Args:
            project_dir: Project root directory
            
        Returns:
            Project context content or None
        """
        context_files = [
            "HALBERT.md",
            ".halbert/context.md",
            "agents.md",
            "GEMINI.md",
            "claude.md",
        ]
        
        project_dir = Path(project_dir)
        
        for filename in context_files:
            context_file = project_dir / filename
            if context_file.exists():
                try:
                    content = context_file.read_text(encoding="utf-8")
                    logger.info(f"Loaded project context from {filename}")
                    return content
                except Exception as e:
                    logger.warning(f"Failed to read {filename}: {e}")
        
        return None
    
    def _detect_package_manager(self) -> str:
        """Detect the system's package manager."""
        pm_paths = {
            "/usr/bin/apt": "apt",
            "/usr/bin/dnf": "dnf",
            "/usr/bin/yum": "yum",
            "/usr/bin/pacman": "pacman",
            "/usr/bin/zypper": "zypper",
            "/usr/bin/apk": "apk",
            "/opt/homebrew/bin/brew": "brew",
            "/usr/local/bin/brew": "brew",
            "/usr/bin/pkg": "pkg",  # FreeBSD
        }
        
        for path, name in pm_paths.items():
            if os.path.exists(path):
                return name
        
        return "unknown"
    
    def _detect_init_system(self) -> str:
        """Detect the system's init system."""
        if os.path.exists("/run/systemd/system"):
            return "systemd"
        elif os.path.exists("/sbin/launchd"):
            return "launchd"
        elif os.path.exists("/sbin/openrc"):
            return "openrc"
        elif os.path.exists("/etc/init.d"):
            return "sysvinit"
        elif os.path.exists("/etc/rc.conf"):
            return "rc"  # BSD
        
        return "unknown"
    
    def _enrich_from_discovery(self, ctx: SystemContext) -> None:
        """
        Enrich context using Discovery Engine.
        
        Args:
            ctx: SystemContext to enrich
        """
        if not self.discovery_engine:
            return
        
        try:
            # Get storage discoveries for disk usage
            from ..discovery.schema import DiscoveryType
            
            storage_discoveries = self.discovery_engine.get_by_type(DiscoveryType.STORAGE)
            if storage_discoveries:
                for d in storage_discoveries:
                    if hasattr(d, 'details') and d.details:
                        mount = d.details.get('mount_point', d.name)
                        percent = d.details.get('percent_used', 0)
                        ctx.disk_usage[mount] = {"percent": percent}
            
            # Get service discoveries for active services
            service_discoveries = self.discovery_engine.get_by_type(DiscoveryType.SERVICE)
            if service_discoveries:
                active = [
                    d.name for d in service_discoveries 
                    if hasattr(d, 'status') and d.status == 'running'
                ][:10]  # Limit to 10
                ctx.active_services = active
            
            # Get system stats if available
            stats = self.discovery_engine.get_stats()
            if stats:
                last_scan = stats.get('last_scan')
                if last_scan:
                    logger.debug(f"Discovery data from: {last_scan}")
            
        except Exception as e:
            logger.warning(f"Failed to enrich from discovery: {e}")
    
    def get_discovery_summary(self) -> Optional[str]:
        """
        Get a summary of discoveries for context injection.
        
        Returns:
            XML-formatted discovery summary or None
        """
        if not self.discovery_engine:
            return None
        
        try:
            stats = self.discovery_engine.get_stats()
            critical = self.discovery_engine.get_critical()
            warnings = self.discovery_engine.get_warnings()
            
            lines = ["<discovery_summary>"]
            lines.append(f"  <total_discoveries>{stats.get('total', 0)}</total_discoveries>")
            lines.append(f"  <last_scan>{stats.get('last_scan', 'never')}</last_scan>")
            
            if critical:
                lines.append("  <critical_issues>")
                for c in critical[:5]:  # Limit to 5
                    lines.append(f"    <issue>{c.title}</issue>")
                lines.append("  </critical_issues>")
            
            if warnings:
                lines.append(f"  <warning_count>{len(warnings)}</warning_count>")
            
            lines.append("</discovery_summary>")
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"Failed to get discovery summary: {e}")
            return None
    
    def get_full_context(
        self,
        project_dir: Optional[Path] = None,
        user_prefs: Optional[UserPreferences] = None,
    ) -> str:
        """
        Get complete formatted context for prompt injection.
        
        Combines system context, user preferences, project context,
        and discovery summary into a single formatted block.
        
        Args:
            project_dir: Optional project directory for HALBERT.md
            user_prefs: Optional user preferences
            
        Returns:
            Complete XML-formatted context
        """
        parts = []
        
        # System context
        sys_ctx = self.get_system_context()
        parts.append(self.format_system_context(sys_ctx))
        
        # User preferences
        if user_prefs:
            parts.append(self.format_user_preferences(user_prefs))
        
        # Project context (HALBERT.md)
        if project_dir:
            project_ctx = self.load_project_context(project_dir)
            if project_ctx:
                parts.append(f"<project_context>\n{project_ctx}\n</project_context>")
        
        # Discovery summary
        discovery_summary = self.get_discovery_summary()
        if discovery_summary:
            parts.append(discovery_summary)
        
        return "\n\n".join(parts)
    
    def get_crag_enriched_context(
        self,
        query: str,
        project_dir: Optional[Path] = None,
        user_prefs: Optional[UserPreferences] = None,
        max_rag_results: int = 5,
    ) -> Tuple[str, Optional[dict]]:
        """
        Get context enriched with CRAG-scored RAG results (Phase 28/29 integration).
        
        Uses SelfReflector to retrieve and score relevant knowledge,
        then formats it along with system context.
        
        Args:
            query: User query for RAG retrieval
            project_dir: Optional project directory for HALBERT.md
            user_prefs: Optional user preferences
            max_rag_results: Maximum RAG results to include
            
        Returns:
            Tuple of (formatted_context, reflection_metadata)
        """
        parts = []
        reflection_metadata = None
        
        # System context
        sys_ctx = self.get_system_context()
        parts.append(self.format_system_context(sys_ctx))
        
        # User preferences
        if user_prefs:
            parts.append(self.format_user_preferences(user_prefs))
        
        # Project context (HALBERT.md)
        if project_dir:
            project_ctx = self.load_project_context(project_dir)
            if project_ctx:
                parts.append(f"<project_context>\n{project_ctx}\n</project_context>")
        
        # CRAG-scored RAG results from SelfReflector
        try:
            from ..knowledge import SelfReflector
            reflector = SelfReflector()
            reflection = reflector.reflect(query, max_contexts=max_rag_results)
            
            # Format RAG results
            rag_formatter = RAGFormatter()
            rag_xml = rag_formatter.format_from_reflection(reflection)
            if rag_xml:
                parts.append(rag_xml)
            
            # Build metadata
            reflection_metadata = {
                'retrieve_decision': reflection.retrieve_decision.value,
                'confidence': reflection.confidence.value,
                'crag_action': reflection.crag_action.value,
                'contexts_found': len(reflection.retrieved_contexts),
            }
            logger.debug(f"CRAG enrichment: {reflection_metadata}")
            
        except Exception as e:
            logger.warning(f"CRAG enrichment failed: {e}")
        
        # Discovery summary
        discovery_summary = self.get_discovery_summary()
        if discovery_summary:
            parts.append(discovery_summary)
        
        return "\n\n".join(parts), reflection_metadata
