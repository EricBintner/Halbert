"""
Trending Topics Discovery for RAG

Discovers emerging technologies from GitHub trending, correlates with
user's tech stack, and suggests relevant documentation additions.

Phase 34: Cutting-Edge Topics Discovery
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class TrendingRepo:
    """A trending repository from GitHub."""
    name: str
    full_name: str
    description: str
    url: str
    stars: int
    stars_this_week: int = 0
    language: str = ""
    topics: List[str] = field(default_factory=list)
    homepage: str = ""
    has_docs: bool = False
    maturity: str = "unknown"  # experimental, growing, stable, mature


@dataclass
class TrendingSuggestion:
    """A suggestion for trending documentation to add."""
    repo: TrendingRepo
    relevance_score: float  # 0-1, how relevant to user's stack
    reason: str  # Why this is suggested
    stack_match: List[str]  # Which parts of user's stack match
    doc_url: str = ""  # URL for documentation if available


# Tech stack to GitHub topics mapping
STACK_TO_TOPICS: Dict[str, List[str]] = {
    # JavaScript/Node ecosystem
    "node": ["nodejs", "npm", "javascript", "typescript", "bun", "deno"],
    "npm": ["npm", "nodejs", "package-manager"],
    "bun": ["bun", "javascript-runtime"],
    "deno": ["deno", "typescript", "javascript-runtime"],
    
    # Python ecosystem
    "python": ["python", "python3", "pip", "poetry", "uv"],
    "pip": ["pip", "python-package"],
    "poetry": ["poetry", "python", "dependency-management"],
    "uv": ["uv", "python", "package-manager"],
    
    # Containers & orchestration
    "docker": ["docker", "containers", "containerization", "dockerfile"],
    "podman": ["podman", "containers", "rootless"],
    "kubernetes": ["kubernetes", "k8s", "container-orchestration"],
    
    # Databases
    "postgresql": ["postgresql", "postgres", "database", "sql"],
    "redis": ["redis", "cache", "in-memory-database"],
    "mongodb": ["mongodb", "nosql", "document-database"],
    
    # DevOps
    "terraform": ["terraform", "infrastructure-as-code", "iac"],
    "ansible": ["ansible", "automation", "configuration-management"],
    
    # Editors
    "vim": ["vim", "neovim", "editor", "terminal"],
    "neovim": ["neovim", "vim", "lua", "editor"],
    "vscode": ["vscode", "visual-studio-code", "editor"],
}

# Known alternatives mapping
ALTERNATIVES: Dict[str, List[str]] = {
    "node": ["bun", "deno"],
    "npm": ["pnpm", "yarn", "bun"],
    "pip": ["uv", "poetry", "pdm", "rye"],
    "docker": ["podman", "containerd", "nerdctl"],
    "vim": ["neovim", "helix", "kakoune"],
    "terraform": ["opentofu", "pulumi", "cdktf"],
    "webpack": ["vite", "esbuild", "turbopack", "rspack"],
    "eslint": ["biome", "oxlint"],
    "prettier": ["biome", "dprint"],
}


class TechStackDetector:
    """Detects user's technology stack from installed tools and configs."""
    
    def __init__(self):
        self._cache: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(hours=1)
    
    def detect(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        """
        Detect installed technologies.
        
        Returns:
            {
                "runtimes": ["node", "python3"],
                "package_managers": ["npm", "pip"],
                "tools": ["docker", "git"],
                "editors": ["neovim"],
            }
        """
        if not force_refresh and self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_duration:
                return self._cache
        
        stack = {
            "runtimes": [],
            "package_managers": [],
            "tools": [],
            "editors": [],
        }
        
        # Detect runtimes
        runtime_checks = [
            ("node", ["node", "--version"]),
            ("python3", ["python3", "--version"]),
            ("python", ["python", "--version"]),
            ("ruby", ["ruby", "--version"]),
            ("go", ["go", "version"]),
            ("rust", ["rustc", "--version"]),
            ("java", ["java", "-version"]),
            ("deno", ["deno", "--version"]),
            ("bun", ["bun", "--version"]),
        ]
        
        for name, cmd in runtime_checks:
            if self._check_command(cmd[0]):
                stack["runtimes"].append(name)
        
        # Detect package managers
        pm_checks = ["npm", "yarn", "pnpm", "pip", "pip3", "poetry", "uv", 
                     "cargo", "gem", "composer"]
        for pm in pm_checks:
            if self._check_command(pm):
                stack["package_managers"].append(pm)
        
        # Detect tools
        tool_checks = ["docker", "podman", "kubectl", "terraform", "ansible",
                       "git", "tmux", "htop", "curl", "wget"]
        for tool in tool_checks:
            if self._check_command(tool):
                stack["tools"].append(tool)
        
        # Detect editors
        editor_checks = ["nvim", "vim", "code", "emacs", "nano", "helix"]
        for editor in editor_checks:
            if self._check_command(editor):
                # Normalize names
                if editor == "nvim":
                    stack["editors"].append("neovim")
                elif editor == "code":
                    stack["editors"].append("vscode")
                else:
                    stack["editors"].append(editor)
        
        self._cache = stack
        self._cache_time = datetime.now()
        
        logger.info(f"Detected tech stack: {stack}")
        return stack
    
    def _check_command(self, cmd: str) -> bool:
        """Check if a command exists."""
        return shutil.which(cmd) is not None
    
    def get_relevant_topics(self) -> Set[str]:
        """Get GitHub topics relevant to detected stack."""
        stack = self.detect()
        topics = set()
        
        for category in stack.values():
            for item in category:
                if item in STACK_TO_TOPICS:
                    topics.update(STACK_TO_TOPICS[item])
        
        return topics
    
    def get_alternatives_for_stack(self) -> Dict[str, List[str]]:
        """Get known alternatives for tools in user's stack."""
        stack = self.detect()
        alternatives = {}
        
        for category in stack.values():
            for item in category:
                if item in ALTERNATIVES:
                    alternatives[item] = ALTERNATIVES[item]
        
        return alternatives


class GitHubTrendingFetcher:
    """Fetches trending repositories from GitHub."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self._headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self._headers["Authorization"] = f"token {token}"
    
    def search_trending(
        self,
        topics: Optional[Set[str]] = None,
        language: Optional[str] = None,
        days: int = 7,
        min_stars: int = 100,
        limit: int = 30
    ) -> List[TrendingRepo]:
        """
        Search for trending repositories using GitHub Search API.
        
        Args:
            topics: Filter by these topics
            language: Filter by programming language
            days: Look back this many days
            min_stars: Minimum star count
            limit: Max results to return
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests not installed, cannot fetch trending")
            return []
        
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Build query
        query_parts = [f"created:>{since_date}", f"stars:>{min_stars}"]
        
        if language:
            query_parts.append(f"language:{language}")
        
        if topics:
            # Add up to 3 topics to query
            for topic in list(topics)[:3]:
                query_parts.append(f"topic:{topic}")
        
        query = " ".join(query_parts)
        
        try:
            response = requests.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": limit
                },
                headers=self._headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            repos = []
            for item in data.get("items", []):
                repos.append(TrendingRepo(
                    name=item["name"],
                    full_name=item["full_name"],
                    description=item.get("description") or "",
                    url=item["html_url"],
                    stars=item["stargazers_count"],
                    language=item.get("language") or "",
                    topics=item.get("topics", []),
                    homepage=item.get("homepage") or "",
                    has_docs=self._check_has_docs(item),
                ))
            
            logger.info(f"Found {len(repos)} trending repos")
            return repos
            
        except Exception as e:
            logger.error(f"Failed to fetch trending: {e}")
            return []
    
    def _check_has_docs(self, repo: dict) -> bool:
        """Quick check if repo likely has documentation."""
        homepage = repo.get("homepage", "") or ""
        description = repo.get("description", "") or ""
        
        doc_signals = [
            "docs." in homepage.lower(),
            "documentation" in homepage.lower(),
            ".github.io" in homepage.lower(),
            "readthedocs" in homepage.lower(),
            "gitbook" in homepage.lower(),
        ]
        
        return any(doc_signals) or len(description) > 100


class TrendingDiscoveryEngine:
    """
    Main engine for discovering trending topics relevant to user.
    
    Combines tech stack detection with GitHub trending to suggest
    documentation additions.
    """
    
    def __init__(self, github_token: Optional[str] = None):
        self.stack_detector = TechStackDetector()
        self.trending_fetcher = GitHubTrendingFetcher(github_token)
        self._suggestions_cache: List[TrendingSuggestion] = []
        self._last_fetch: Optional[datetime] = None
        self._fetch_interval = timedelta(hours=24)
    
    def get_suggestions(
        self,
        force_refresh: bool = False,
        limit: int = 10
    ) -> List[TrendingSuggestion]:
        """
        Get trending documentation suggestions based on user's stack.
        
        Returns suggestions sorted by relevance score.
        """
        # Check cache
        if not force_refresh and self._last_fetch:
            if datetime.now() - self._last_fetch < self._fetch_interval:
                return self._suggestions_cache[:limit]
        
        # Detect user's stack
        stack = self.stack_detector.detect()
        relevant_topics = self.stack_detector.get_relevant_topics()
        alternatives = self.stack_detector.get_alternatives_for_stack()
        
        # Fetch trending repos
        trending = self.trending_fetcher.search_trending(
            topics=relevant_topics,
            days=30,  # Look at monthly trending
            min_stars=500,
            limit=50
        )
        
        # Score and filter
        suggestions = []
        for repo in trending:
            score, reason, matches = self._score_relevance(
                repo, stack, alternatives
            )
            
            if score > 0.3:  # Minimum relevance threshold
                suggestions.append(TrendingSuggestion(
                    repo=repo,
                    relevance_score=score,
                    reason=reason,
                    stack_match=matches,
                    doc_url=repo.homepage if repo.has_docs else repo.url,
                ))
        
        # Sort by relevance
        suggestions.sort(key=lambda s: s.relevance_score, reverse=True)
        
        self._suggestions_cache = suggestions
        self._last_fetch = datetime.now()
        
        return suggestions[:limit]
    
    def _score_relevance(
        self,
        repo: TrendingRepo,
        stack: Dict[str, List[str]],
        alternatives: Dict[str, List[str]]
    ) -> tuple[float, str, List[str]]:
        """
        Score how relevant a trending repo is to user's stack.
        
        Returns:
            (score, reason, matching_stack_items)
        """
        score = 0.0
        reasons = []
        matches = []
        
        all_stack_items = []
        for items in stack.values():
            all_stack_items.extend(items)
        
        # Check if repo is an alternative to something user has
        for tool, alts in alternatives.items():
            if repo.name.lower() in [a.lower() for a in alts]:
                score += 0.4
                reasons.append(f"Alternative to {tool}")
                matches.append(tool)
        
        # Check topic overlap
        user_topics = self.stack_detector.get_relevant_topics()
        repo_topics = set(repo.topics)
        overlap = user_topics & repo_topics
        
        if overlap:
            score += min(len(overlap) * 0.1, 0.3)
            reasons.append(f"Related topics: {', '.join(list(overlap)[:3])}")
            matches.extend(list(overlap)[:3])
        
        # Bonus for having documentation
        if repo.has_docs:
            score += 0.1
            reasons.append("Has documentation site")
        
        # Bonus for high stars (established project)
        if repo.stars > 5000:
            score += 0.1
        if repo.stars > 20000:
            score += 0.1
        
        # Cap score at 1.0
        score = min(score, 1.0)
        
        reason = "; ".join(reasons) if reasons else "Trending in your tech area"
        
        return score, reason, matches


# Singleton instance
_engine: Optional[TrendingDiscoveryEngine] = None


def get_trending_engine() -> TrendingDiscoveryEngine:
    """Get the global trending discovery engine instance."""
    global _engine
    if _engine is None:
        # Try to get GitHub token from environment
        import os
        token = os.environ.get("GITHUB_TOKEN")
        _engine = TrendingDiscoveryEngine(github_token=token)
    return _engine


def get_trending_suggestions(limit: int = 10) -> List[Dict]:
    """
    Get trending documentation suggestions.
    
    Returns list of suggestion dicts for API/frontend consumption.
    """
    engine = get_trending_engine()
    suggestions = engine.get_suggestions(limit=limit)
    
    return [
        {
            "name": s.repo.name,
            "full_name": s.repo.full_name,
            "description": s.repo.description,
            "url": s.repo.url,
            "doc_url": s.doc_url,
            "stars": s.repo.stars,
            "language": s.repo.language,
            "relevance_score": round(s.relevance_score, 2),
            "reason": s.reason,
            "stack_match": s.stack_match,
            "has_docs": s.repo.has_docs,
        }
        for s in suggestions
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-Enhanced Tool Classification
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMAnalysis:
    """LLM-generated analysis of a trending repo."""
    category: str  # e.g., "javascript-runtime", "package-manager", "linter"
    is_alternative_to: List[str]  # Tools this replaces/competes with
    key_features: List[str]  # Top 3-5 features
    one_liner: str  # One sentence description
    should_user_care: bool  # Is this relevant to the user?
    reason: str  # Why should user care (or not)
    maturity: str  # experimental, growing, stable, mature
    learning_curve: str  # easy, moderate, steep


LLM_ANALYSIS_PROMPT = """Analyze this GitHub repository for a Linux power user.

Repository: {full_name}
Description: {description}
Language: {language}
Stars: {stars}
Topics: {topics}

User's current tech stack: {user_stack}

Respond in JSON format only:
{{
    "category": "what type of tool is this? (e.g., javascript-runtime, package-manager, linter, web-server)",
    "is_alternative_to": ["list of tools this replaces or competes with"],
    "key_features": ["top 3 distinguishing features"],
    "one_liner": "one sentence description for a developer",
    "should_user_care": true or false,
    "reason": "why this user specifically should or shouldn't care",
    "maturity": "experimental/growing/stable/mature",
    "learning_curve": "easy/moderate/steep"
}}"""


def get_configured_model() -> tuple[str, str]:
    """
    Get the configured guide/orchestrator model from models.yml.
    
    Returns:
        (endpoint_url, model_name) tuple
    """
    try:
        from pathlib import Path
        import yaml
        
        # Try to find config
        config_dir = Path.home() / '.config' / 'halbert'
        config_path = config_dir / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            orchestrator = config.get('orchestrator', {})
            endpoint = orchestrator.get('endpoint', 'http://localhost:11434')
            model = orchestrator.get('model', 'llama3.1:8b-instruct')
            return endpoint, model
        
        # Fallback defaults
        return 'http://localhost:11434', 'llama3.1:8b-instruct'
        
    except Exception as e:
        logger.warning(f"Failed to load model config: {e}")
        return 'http://localhost:11434', 'llama3.1:8b-instruct'


async def analyze_repo_with_llm(
    repo: TrendingRepo,
    user_stack: Dict[str, List[str]],
    llm_endpoint: str = None,
    model: str = None
) -> Optional[LLMAnalysis]:
    """
    Use LLM to analyze a trending repository.
    
    Args:
        repo: The trending repo to analyze
        user_stack: User's detected tech stack
        llm_endpoint: Ollama endpoint URL
    
    Returns:
        LLMAnalysis or None if analysis fails
    """
    try:
        import aiohttp
        import json
        
        # Get configured model if not specified
        if llm_endpoint is None or model is None:
            cfg_endpoint, cfg_model = get_configured_model()
            llm_endpoint = llm_endpoint or cfg_endpoint
            model = model or cfg_model
        
        # Format user stack for prompt
        stack_str = ", ".join([
            f"{k}: {', '.join(v)}" 
            for k, v in user_stack.items() 
            if v
        ])
        
        prompt = LLM_ANALYSIS_PROMPT.format(
            full_name=repo.full_name,
            description=repo.description,
            language=repo.language,
            stars=repo.stars,
            topics=", ".join(repo.topics),
            user_stack=stack_str or "general Linux user"
        )
        
        logger.info(f"Analyzing {repo.name} with {model} at {llm_endpoint}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{llm_endpoint}/api/generate",
                json={
                    "model": model,  # Use configured guide model
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=aiohttp.ClientTimeout(total=60)  # Longer timeout for larger models
            ) as response:
                if response.status != 200:
                    logger.warning(f"LLM request failed: {response.status}")
                    return None
                
                data = await response.json()
                result_text = data.get("response", "")
                
                # Parse JSON response
                try:
                    result = json.loads(result_text)
                    return LLMAnalysis(
                        category=result.get("category", "unknown"),
                        is_alternative_to=result.get("is_alternative_to", []),
                        key_features=result.get("key_features", []),
                        one_liner=result.get("one_liner", repo.description),
                        should_user_care=result.get("should_user_care", True),
                        reason=result.get("reason", ""),
                        maturity=result.get("maturity", "unknown"),
                        learning_curve=result.get("learning_curve", "moderate")
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse LLM response: {result_text[:200]}")
                    return None
                    
    except ImportError:
        logger.warning("aiohttp not installed, cannot use LLM analysis")
        return None
    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return None


def analyze_repo_with_llm_sync(
    repo: TrendingRepo,
    user_stack: Dict[str, List[str]],
    llm_endpoint: str = None,
    model: str = None
) -> Optional[LLMAnalysis]:
    """
    Synchronous wrapper for LLM analysis.
    
    Uses requests instead of aiohttp for sync contexts.
    """
    try:
        import requests
        import json
        
        # Get configured model if not specified
        if llm_endpoint is None or model is None:
            cfg_endpoint, cfg_model = get_configured_model()
            llm_endpoint = llm_endpoint or cfg_endpoint
            model = model or cfg_model
        
        # Format user stack for prompt
        stack_str = ", ".join([
            f"{k}: {', '.join(v)}" 
            for k, v in user_stack.items() 
            if v
        ])
        
        prompt = LLM_ANALYSIS_PROMPT.format(
            full_name=repo.full_name,
            description=repo.description,
            language=repo.language,
            stars=repo.stars,
            topics=", ".join(repo.topics),
            user_stack=stack_str or "general Linux user"
        )
        
        logger.info(f"Analyzing {repo.name} with {model} at {llm_endpoint}")
        
        response = requests.post(
            f"{llm_endpoint}/api/generate",
            json={
                "model": model,  # Use configured guide model
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=60  # Longer timeout for larger models
        )
        
        if response.status_code != 200:
            logger.warning(f"LLM request failed: {response.status_code}")
            return None
        
        data = response.json()
        result_text = data.get("response", "")
        
        try:
            result = json.loads(result_text)
            return LLMAnalysis(
                category=result.get("category", "unknown"),
                is_alternative_to=result.get("is_alternative_to", []),
                key_features=result.get("key_features", []),
                one_liner=result.get("one_liner", repo.description),
                should_user_care=result.get("should_user_care", True),
                reason=result.get("reason", ""),
                maturity=result.get("maturity", "unknown"),
                learning_curve=result.get("learning_curve", "moderate")
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {result_text[:200]}")
            return None
            
    except ImportError:
        logger.warning("requests not installed")
        return None
    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return None


async def get_enhanced_suggestions(limit: int = 5) -> List[Dict]:
    """
    Get trending suggestions with LLM-enhanced analysis.
    
    This is slower but provides much richer context about each tool.
    """
    engine = get_trending_engine()
    suggestions = engine.get_suggestions(limit=limit)
    stack = engine.stack_detector.detect()
    
    enhanced = []
    for s in suggestions:
        base = {
            "name": s.repo.name,
            "full_name": s.repo.full_name,
            "description": s.repo.description,
            "url": s.repo.url,
            "doc_url": s.doc_url,
            "stars": s.repo.stars,
            "language": s.repo.language,
            "relevance_score": round(s.relevance_score, 2),
            "reason": s.reason,
            "stack_match": s.stack_match,
            "has_docs": s.repo.has_docs,
        }
        
        # Try to get LLM analysis
        analysis = await analyze_repo_with_llm(s.repo, stack)
        if analysis:
            base["llm_analysis"] = {
                "category": analysis.category,
                "is_alternative_to": analysis.is_alternative_to,
                "key_features": analysis.key_features,
                "one_liner": analysis.one_liner,
                "should_user_care": analysis.should_user_care,
                "reason": analysis.reason,
                "maturity": analysis.maturity,
                "learning_curve": analysis.learning_curve,
            }
        
        enhanced.append(base)
    
    return enhanced
