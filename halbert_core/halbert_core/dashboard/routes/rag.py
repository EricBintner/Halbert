# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
RAG API routes for the dashboard.

Phase 10: Knowledge source ingestion.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from collections import defaultdict

logger = logging.getLogger('halbert')

router = APIRouter(prefix="/rag", tags=["rag"])


class AddSourceRequest(BaseModel):
    url: str
    name: Optional[str] = None
    trust: bool = False


class AddSourceResponse(BaseModel):
    success: bool
    title: str = ""
    error: str = ""
    trust_tier: int = 0
    source_name: str = ""
    warnings: list = []
    already_exists: bool = False


class DocumentInfo(BaseModel):
    name: str
    source: str = ""
    url: str = ""
    trust_tier: int = 0
    is_custom: bool = False


class RAGStatsResponse(BaseModel):
    total_docs: int
    user_docs: int
    sources: dict = {}  # source_name -> count


class RAGIndexInfo(BaseModel):
    name: str
    doc_count: int
    indexed_at: str
    source_file: str
    embedding_model: str
    build_time_seconds: float


class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]
    total: int


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@router.get("/indexes")
async def get_rag_indexes():
    """Get list of all RAG indexes with metadata."""
    try:
        repo_root = _get_repo_root()
        indices_dir = repo_root / 'data' / '.rag_indices'
        
        indexes = []
        if indices_dir.exists():
            for index_dir in indices_dir.iterdir():
                if index_dir.is_dir():
                    metadata_file = index_dir / 'index_metadata.json'
                    if metadata_file.exists():
                        with open(metadata_file) as f:
                            meta = json.load(f)
                        
                        # Count docs from source file
                        source_file = meta.get('source', '')
                        doc_count = 0
                        source_path = repo_root / source_file
                        if source_path.exists():
                            with open(source_path) as f:
                                doc_count = sum(1 for _ in f)
                        
                        indexes.append({
                            "name": index_dir.name,
                            "doc_count": doc_count,
                            "indexed_at": meta.get('indexed_at', 'Unknown'),
                            "source_file": source_file,
                            "embedding_model": meta.get('embedding_model', 'Unknown'),
                            "build_time_seconds": meta.get('build_time_seconds', 0)
                        })
        
        return {"indexes": indexes, "total": len(indexes)}
    except Exception as e:
        logger.error(f"Failed to get RAG indexes: {e}")
        return {"indexes": [], "total": 0, "error": str(e)}


@router.get("/stats", response_model=RAGStatsResponse)
async def get_rag_stats():
    """Get RAG corpus statistics from ChromaDB."""
    try:
        # Get actual count from ChromaDB
        from halbert_core.rag.document_indexer import get_index_stats
        stats = get_index_stats()
        total_docs = stats.get('linux_docs_count', 0)
        
        # Get user docs count from file
        repo_root = _get_repo_root()
        user_file = repo_root / 'data' / 'linux' / 'user-sources' / 'user_added.jsonl'
        user_docs = 0
        if user_file.exists():
            with open(user_file) as f:
                user_docs = sum(1 for _ in f)
        
        return RAGStatsResponse(
            total_docs=total_docs, 
            user_docs=user_docs,
            sources=stats.get('collections', {})
        )
        
    except Exception as e:
        logger.error(f"Failed to get RAG stats: {e}")
        return RAGStatsResponse(total_docs=0, user_docs=0, sources={})


def _check_url_exists(url: str) -> tuple:
    """Check if URL already exists in corpus. Returns (exists, doc_name)."""
    repo_root = _get_repo_root()
    data_dir = repo_root / 'data' / 'linux'
    
    # Check user-added first
    user_file = data_dir / 'user-sources' / 'user_added.jsonl'
    if user_file.exists():
        with open(user_file) as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    meta = doc.get('metadata', {})
                    if meta.get('source_url') == url:
                        return True, doc.get('name', 'Unknown')
                except:
                    pass
    
    # Check merged corpus
    merged_file = data_dir / 'merged' / 'rag_corpus_merged.jsonl'
    if merged_file.exists():
        with open(merged_file) as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    meta = doc.get('metadata', {})
                    if meta.get('source_url') == url or meta.get('attribution_url') == url:
                        return True, doc.get('name', 'Unknown')
                except:
                    pass
    
    return False, None


@router.post("/add", response_model=AddSourceResponse)
async def add_knowledge_source(request: AddSourceRequest):
    """Add a URL to the RAG corpus."""
    try:
        # Check for duplicates first
        exists, existing_name = _check_url_exists(request.url)
        if exists:
            return AddSourceResponse(
                success=False,
                title=existing_name,
                error=f"URL already exists in knowledge base as: {existing_name}",
                already_exists=True
            )
        
        from halbert_core.rag.ingestion import RAGIngestionEngine
        
        logger.info(f"Adding knowledge source: {request.url}")
        
        engine = RAGIngestionEngine()
        result = engine.add_url(request.url, force_trust=request.trust)
        
        return AddSourceResponse(
            success=result.success,
            title=result.title,
            error=result.error,
            trust_tier=result.trust_tier,
            source_name=result.source_name,
            warnings=result.warnings
        )
        
    except ImportError as e:
        logger.error(f"RAG ingestion not available: {e}")
        return AddSourceResponse(
            success=False,
            error="RAG ingestion system not available"
        )
    except Exception as e:
        logger.error(f"Failed to add knowledge source: {e}")
        return AddSourceResponse(
            success=False,
            error=str(e)
        )


class SourceSummary(BaseModel):
    name: str
    count: int


class DocumentListResponse2(BaseModel):
    custom_docs: List[DocumentInfo]
    core_sources: List[SourceSummary]
    total_core: int


@router.get("/documents")
async def list_documents():
    """List custom documents and hardcoded core source summary (instant)."""
    try:
        repo_root = _get_repo_root()
        data_dir = repo_root / 'data' / 'linux'
        
        custom_docs = []
        
        # Get user-added documents (custom) - these are few, read all
        user_file = data_dir / 'user-sources' / 'user_added.jsonl'
        if user_file.exists():
            with open(user_file) as f:
                for line in f:
                    try:
                        doc = json.loads(line)
                        meta = doc.get('metadata', {})
                        custom_docs.append(DocumentInfo(
                            name=doc.get('name', 'Unknown'),
                            source=meta.get('source_name', 'User Added'),
                            url=meta.get('source_url', ''),
                            trust_tier=meta.get('trust_tier', 3),
                            is_custom=True
                        ))
                    except:
                        pass
        
        # Get actual doc counts from ChromaDB
        try:
            from halbert_core.rag.document_indexer import get_index_stats
            stats = get_index_stats()
            total_indexed = stats.get('linux_docs_count', 0)
            
            # Semantic display names for documentation sources
            SOURCE_DISPLAY_NAMES = {
                # Core Linux documentation
                "man-pages": "Linux Man Pages",
                "arch-wiki": "Arch Wiki",
                "arch-wiki-ext": "Arch Wiki Extended",
                "more-arch": "Arch Linux Guides",
                "ubuntu-docs": "Ubuntu Documentation",
                "ubuntu-server": "Ubuntu Server Guide",
                "linux-core-docs": "Linux Core Concepts",
                "linux-utils-docs": "Linux Utilities",
                "commands": "Command Reference",
                
                # System administration
                "systemd-docs": "Systemd Services",
                "systemd-ext": "Systemd Advanced",
                "shell-docs": "Shell Scripting",
                "scheduling-docs": "Task Scheduling (Cron)",
                "logging-docs": "System Logging",
                "performance-docs": "Performance Tuning",
                "monitoring-docs": "System Monitoring",
                "backup-docs": "Backup & Recovery",
                "automation-docs": "Automation & Scripting",
                
                # Security & networking
                "security-docs": "Security & Hardening",
                "ssl-certs-docs": "SSL/TLS Certificates",
                "network-docs": "Network Configuration",
                "networking-docs": "Networking Tools",
                
                # Containers & virtualization
                "docker-docs": "Docker",
                "podman-docs": "Podman",
                "containers-docs": "Container Management",
                "kubernetes-docs": "Kubernetes",
                "helm-k8s": "Helm & K8s Tools",
                
                # Development tools
                "git-docs": "Git Version Control",
                "devtools-docs": "Developer Tools",
                "python-tools-docs": "Python Tools",
                
                # Package managers
                "flatpak-docs": "Flatpak Apps",
                "snap-docs": "Snap Packages",
                "appimage-docs": "AppImage",
                
                # Databases & infrastructure
                "database-docs": "Database Administration",
                "message-queues-docs": "Message Queues",
                "caching-docs": "Caching Systems",
                "webserver-docs": "Web Servers",
                
                # Cloud & vendor
                "aws-cli": "AWS CLI",
                "nvidia-docs": "NVIDIA GPU",
                "rocm-docs": "AMD ROCm",
                "vendor-docs": "Vendor Documentation",
                
                # Misc (rename unclear ones)
                "3k-push": "Linux Administration Tips",
                "final-push": "Advanced Linux Topics",
                "hf-datasets": "ML/AI Documentation",
                "filesystem-docs": "Filesystem Management",
            }
            
            # Build core sources from available data directories
            data_dir = repo_root / 'data' / 'linux'
            core_sources = []
            if data_dir.exists():
                for subdir in sorted(data_dir.iterdir()):
                    if subdir.is_dir() and subdir.name not in ['merged', 'user-sources', '__pycache__']:
                        # Count JSONL files in this source
                        doc_count = 0
                        for jsonl in subdir.glob('*.jsonl'):
                            with open(jsonl) as f:
                                doc_count += sum(1 for _ in f)
                        if doc_count > 0:
                            # Use semantic display name or format nicely
                            name = SOURCE_DISPLAY_NAMES.get(
                                subdir.name,
                                subdir.name.replace('-', ' ').replace('_', ' ').title()
                            )
                            core_sources.append({"name": name, "count": doc_count})
            
            # Sort by count descending
            core_sources.sort(key=lambda x: x['count'], reverse=True)
            
        except Exception as e:
            logger.warning(f"Could not get dynamic stats: {e}")
            total_indexed = 0
            core_sources = []
        
        return {
            "custom_docs": custom_docs,
            "core_sources": core_sources[:20],  # Top 20 sources
            "total_core": total_indexed
        }
        
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return {"custom_docs": [], "core_sources": [], "total_core": 0}


@router.delete("/documents/{url:path}")
async def delete_document(url: str):
    """Delete a user-added document by URL."""
    try:
        repo_root = _get_repo_root()
        user_file = repo_root / 'data' / 'linux' / 'user-sources' / 'user_added.jsonl'
        
        if not user_file.exists():
            return {"success": False, "error": "No user documents found"}
        
        # Read all docs, filter out the one to delete
        docs = []
        deleted = False
        with open(user_file) as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    meta = doc.get('metadata', {})
                    if meta.get('source_url') != url:
                        docs.append(line)
                    else:
                        deleted = True
                except:
                    docs.append(line)
        
        if deleted:
            with open(user_file, 'w') as f:
                f.writelines(docs)
            return {"success": True, "message": "Document deleted"}
        else:
            return {"success": False, "error": "Document not found"}
            
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        return {"success": False, "error": str(e)}


@router.post("/merge")
async def merge_corpus():
    """Trigger corpus merge."""
    try:
        import subprocess
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        merge_script = repo_root / 'scripts' / 'quick_merge_rag.py'
        
        result = subprocess.run(
            ['python', str(merge_script)],
            cwd=str(repo_root),
            capture_output=True,
            text=True
        )
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else ""
        }
        
    except Exception as e:
        logger.error(f"Failed to merge corpus: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Documentation Suggestions API (Self-Learning)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/suggestions")
async def get_doc_suggestions():
    """
    Get documentation suggestions based on discovered services/apps.
    
    This implements the self-learning concept: Halbert analyzes what's
    running on your system and suggests relevant documentation to add.
    """
    try:
        from ...rag.doc_suggester import get_suggestions_for_system, get_all_doc_sources
        
        suggestions = get_suggestions_for_system()
        all_sources = get_all_doc_sources()
        
        return {
            "suggestions": suggestions,
            "all_sources": all_sources,
            "total_available": len(all_sources),
            "suggestions_count": len(suggestions),
        }
    except Exception as e:
        logger.error(f"Failed to get suggestions: {e}")
        return {"suggestions": [], "all_sources": [], "error": str(e)}


@router.post("/suggestions/{doc_key}/dismiss")
async def dismiss_suggestion(doc_key: str):
    """Dismiss a documentation suggestion."""
    try:
        from ...rag.doc_suggester import get_suggester
        
        suggester = get_suggester()
        suggester.dismiss_suggestion(doc_key)
        
        return {"success": True, "dismissed": doc_key}
    except Exception as e:
        logger.error(f"Failed to dismiss suggestion: {e}")
        return {"success": False, "error": str(e)}


@router.post("/suggestions/{doc_key}/add")
async def add_suggested_doc(doc_key: str):
    """
    Add a suggested documentation source to RAG.
    
    This fetches the documentation and indexes it into ChromaDB.
    """
    try:
        from ...rag.doc_suggester import get_suggester, DOC_SOURCE_REGISTRY
        
        if doc_key not in DOC_SOURCE_REGISTRY:
            return {"success": False, "error": f"Unknown doc key: {doc_key}"}
        
        doc_source = DOC_SOURCE_REGISTRY[doc_key]
        
        # Create request and call add_knowledge_source
        request = AddSourceRequest(url=doc_source.url, name=doc_source.name)
        result = await add_knowledge_source(request)
        
        if result.success:
            # Mark as indexed
            suggester = get_suggester()
            suggester.mark_indexed(doc_key)
            return {"success": True, "title": result.title, "source_name": result.source_name}
        
        return {"success": False, "error": result.error}
        
    except Exception as e:
        logger.error(f"Failed to add suggested doc: {e}")
        return {"success": False, "error": str(e)}


@router.post("/suggestions/reset")
async def reset_dismissed_suggestions():
    """Reset all dismissed suggestions."""
    try:
        from ...rag.doc_suggester import get_suggester
        
        suggester = get_suggester()
        suggester.reset_dismissed()
        
        return {"success": True, "message": "All dismissed suggestions have been reset"}
    except Exception as e:
        logger.error(f"Failed to reset suggestions: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Trending Topics API (Phase 34 - Cutting-Edge Discovery)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/trending")
async def get_trending_suggestions(limit: int = 10, force_refresh: bool = False):
    """
    Get trending GitHub repositories relevant to user's tech stack.
    
    Discovers emerging tools and technologies based on:
    - User's installed runtimes/tools (node, python, docker, etc.)
    - GitHub trending with star velocity
    - Known alternatives to user's current tools
    
    Args:
        limit: Max suggestions to return (default 10)
        force_refresh: Force refresh from GitHub API (default False, uses 24h cache)
    """
    try:
        from ...rag.trending_discovery import get_trending_suggestions, get_trending_engine
        
        suggestions = get_trending_suggestions(limit=limit)
        engine = get_trending_engine()
        
        # Get user's detected stack for context
        stack = engine.stack_detector.detect()
        alternatives = engine.stack_detector.get_alternatives_for_stack()
        
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "user_stack": stack,
            "known_alternatives": alternatives,
            "cache_age_hours": _get_cache_age(engine),
        }
    except Exception as e:
        logger.error(f"Failed to get trending suggestions: {e}")
        return {
            "suggestions": [],
            "count": 0,
            "error": str(e),
            "user_stack": {},
            "known_alternatives": {},
        }


def _get_cache_age(engine) -> float:
    """Get cache age in hours."""
    if engine._last_fetch:
        from datetime import datetime
        delta = datetime.now() - engine._last_fetch
        return round(delta.total_seconds() / 3600, 1)
    return -1  # No cache


@router.get("/trending/stack")
async def get_detected_stack():
    """
    Get the detected technology stack for the current system.
    
    Returns installed runtimes, package managers, tools, and editors.
    """
    try:
        from ...rag.trending_discovery import get_trending_engine
        
        engine = get_trending_engine()
        stack = engine.stack_detector.detect(force_refresh=True)
        alternatives = engine.stack_detector.get_alternatives_for_stack()
        topics = list(engine.stack_detector.get_relevant_topics())
        
        return {
            "stack": stack,
            "alternatives": alternatives,
            "github_topics": topics,
        }
    except Exception as e:
        logger.error(f"Failed to detect stack: {e}")
        return {"stack": {}, "alternatives": {}, "error": str(e)}


@router.post("/trending/{repo_name}/watch")
async def watch_trending_repo(repo_name: str):
    """
    Add a trending repo to the watch list.
    
    Watched repos will be tracked for documentation maturity.
    """
    repo_root = _get_repo_root()
    watch_file = repo_root / 'data' / 'trending_watch.json'
    
    watched = []
    if watch_file.exists():
        with open(watch_file) as f:
            watched = json.load(f)
    
    if repo_name not in watched:
        watched.append(repo_name)
        watch_file.parent.mkdir(parents=True, exist_ok=True)
        with open(watch_file, 'w') as f:
            json.dump(watched, f, indent=2)
    
    return {
        "success": True,
        "message": f"Added {repo_name} to watch list",
        "repo": repo_name,
    }


@router.post("/trending/{repo_name}/dismiss")
async def dismiss_trending_repo(repo_name: str):
    """
    Dismiss a trending repo suggestion.
    
    Dismissed repos won't appear in future suggestions.
    """
    repo_root = _get_repo_root()
    dismiss_file = repo_root / 'data' / 'trending_dismissed.json'
    
    dismissed = []
    if dismiss_file.exists():
        with open(dismiss_file) as f:
            dismissed = json.load(f)
    
    if repo_name not in dismissed:
        dismissed.append(repo_name)
        dismiss_file.parent.mkdir(parents=True, exist_ok=True)
        with open(dismiss_file, 'w') as f:
            json.dump(dismissed, f, indent=2)
    
    return {
        "success": True,
        "message": f"Dismissed {repo_name}",
        "repo": repo_name,
    }


@router.get("/trending/enhanced")
async def get_enhanced_trending(limit: int = 5):
    """
    Get trending repos with LLM-enhanced analysis.
    
    This endpoint uses the local LLM to analyze each trending repo
    and provide richer context like:
    - Category classification
    - Alternative tools it replaces
    - Key features
    - Whether user should care based on their stack
    - Maturity and learning curve assessment
    
    Note: This is slower than /trending as it makes LLM calls.
    """
    try:
        from ...rag.trending_discovery import get_enhanced_suggestions
        
        suggestions = await get_enhanced_suggestions(limit=limit)
        
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "llm_enhanced": True,
        }
    except Exception as e:
        logger.error(f"Failed to get enhanced trending: {e}")
        return {
            "suggestions": [],
            "count": 0,
            "error": str(e),
            "llm_enhanced": False,
        }


class DataVersionResponse(BaseModel):
    version: str
    release_date: str
    sources: dict = {}
    total_documents: int = 0
    update_available: bool = False
    latest_version: str = ""
    update_release_notes: str = ""


@router.get("/data/version")
async def get_data_version():
    """
    Get current RAG data version and check for updates.
    
    Returns version info from the data manifest and checks
    HuggingFace for newer versions.
    """
    try:
        from ...rag.freshness import DataManifest, UpdateChecker
        
        repo_root = _get_repo_root()
        manifest_path = repo_root / 'data' / 'manifest.json'
        
        # Load local manifest
        manifest = DataManifest.load(manifest_path)
        
        if not manifest:
            # No manifest - return unknown version
            return {
                "version": "unknown",
                "release_date": "unknown",
                "sources": {},
                "total_documents": 0,
                "update_available": False,
                "latest_version": "",
                "update_release_notes": "",
                "message": "No data manifest found. RAG data may not be versioned."
            }
        
        response = {
            "version": manifest.version,
            "release_date": manifest.release_date,
            "sources": manifest.sources,
            "total_documents": manifest.total_documents,
            "total_chunks": manifest.total_chunks,
            "update_available": False,
            "latest_version": manifest.version,
            "update_release_notes": "",
        }
        
        # Check for updates (async)
        try:
            checker = UpdateChecker(manifest_path=manifest_path)
            update_info = await checker.check_for_updates()
            
            if update_info and update_info.update_available:
                response["update_available"] = True
                response["latest_version"] = update_info.latest_version
                response["update_release_notes"] = update_info.release_notes
                response["update_download_url"] = update_info.download_url
        except Exception as e:
            logger.debug(f"Update check failed (non-critical): {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get data version: {e}")
        return {
            "version": "error",
            "release_date": "",
            "error": str(e)
        }


@router.get("/data/freshness")
async def get_data_freshness_stats():
    """
    Get freshness statistics for the RAG corpus.
    
    Returns breakdown of document ages and staleness levels.
    """
    try:
        from ...rag.freshness import get_freshness_checker, STALENESS_THRESHOLDS
        
        repo_root = _get_repo_root()
        
        # Scan data files for scraped_at timestamps
        stats = {
            "fresh": 0,      # < 30 days
            "aging": 0,      # 30-90 days
            "stale": 0,      # 90-180 days
            "outdated": 0,   # > 365 days
            "unknown": 0,    # No timestamp
        }
        
        sources_stats = defaultdict(lambda: {"total": 0, "avg_age_days": 0, "ages": []})
        
        checker = get_freshness_checker()
        
        # Check JSONL files in data directories
        data_dirs = [
            repo_root / 'data' / 'linux',
            repo_root / 'data' / 'macos',
            repo_root / 'data' / 'common',
        ]
        
        sample_count = 0
        max_samples = 1000  # Sample for performance
        
        for data_dir in data_dirs:
            if not data_dir.exists():
                continue
            
            for jsonl_file in data_dir.rglob("*.jsonl"):
                if sample_count >= max_samples:
                    break
                    
                try:
                    with open(jsonl_file) as f:
                        for i, line in enumerate(f):
                            if i >= 100:  # Sample 100 per file
                                break
                            if sample_count >= max_samples:
                                break
                                
                            try:
                                doc = json.loads(line)
                                info = checker.check_document(doc)
                                
                                stats[info.freshness_level] += 1
                                
                                source = info.source or jsonl_file.stem
                                sources_stats[source]["total"] += 1
                                if info.age_days > 0:
                                    sources_stats[source]["ages"].append(info.age_days)
                                
                                sample_count += 1
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.debug(f"Error reading {jsonl_file}: {e}")
        
        # Calculate averages
        for source, data in sources_stats.items():
            if data["ages"]:
                data["avg_age_days"] = sum(data["ages"]) // len(data["ages"])
            del data["ages"]  # Don't return raw ages
        
        return {
            "sampled_documents": sample_count,
            "freshness_breakdown": stats,
            "thresholds_days": STALENESS_THRESHOLDS,
            "sources": dict(sources_stats),
        }
        
    except Exception as e:
        logger.error(f"Failed to get freshness stats: {e}")
        return {"error": str(e)}


@router.post("/trending/{repo_name}/analyze")
async def analyze_single_repo(repo_name: str):
    """
    Get LLM analysis for a single trending repo.
    
    Use this to get detailed analysis for a specific repo
    without fetching all trending suggestions.
    """
    try:
        from ...rag.trending_discovery import (
            get_trending_engine, 
            analyze_repo_with_llm,
            TrendingRepo
        )
        
        engine = get_trending_engine()
        stack = engine.stack_detector.detect()
        
        # Find the repo in current suggestions
        suggestions = engine.get_suggestions(limit=20)
        repo = None
        for s in suggestions:
            if s.repo.name.lower() == repo_name.lower() or s.repo.full_name.lower() == repo_name.lower():
                repo = s.repo
                break
        
        if not repo:
            return {"success": False, "error": f"Repo '{repo_name}' not found in trending"}
        
        analysis = await analyze_repo_with_llm(repo, stack)
        
        if analysis:
            return {
                "success": True,
                "repo": repo_name,
                "analysis": {
                    "category": analysis.category,
                    "is_alternative_to": analysis.is_alternative_to,
                    "key_features": analysis.key_features,
                    "one_liner": analysis.one_liner,
                    "should_user_care": analysis.should_user_care,
                    "reason": analysis.reason,
                    "maturity": analysis.maturity,
                    "learning_curve": analysis.learning_curve,
                }
            }
        
        return {"success": False, "error": "LLM analysis failed - check if Ollama is running"}
        
    except Exception as e:
        logger.error(f"Failed to analyze repo: {e}")
        return {"success": False, "error": str(e)}
