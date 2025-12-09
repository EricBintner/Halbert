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

logger = logging.getLogger('cerebric')

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


class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]
    total: int


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@router.get("/stats", response_model=RAGStatsResponse)
async def get_rag_stats():
    """Get RAG corpus statistics with source breakdown."""
    try:
        repo_root = _get_repo_root()
        data_dir = repo_root / 'data' / 'linux'
        merged_file = data_dir / 'merged' / 'rag_corpus_merged.jsonl'
        user_file = data_dir / 'user-sources' / 'user_added.jsonl'
        
        total_docs = 0
        user_docs = 0
        sources = defaultdict(int)
        
        if merged_file.exists():
            with open(merged_file) as f:
                for line in f:
                    total_docs += 1
                    try:
                        doc = json.loads(line)
                        meta = doc.get('metadata', {})
                        source = meta.get('source_name') or meta.get('source_type', 'unknown')
                        sources[source] += 1
                    except:
                        sources['unknown'] += 1
        
        if user_file.exists():
            with open(user_file) as f:
                user_docs = sum(1 for _ in f)
        
        return RAGStatsResponse(
            total_docs=total_docs, 
            user_docs=user_docs,
            sources=dict(sources)
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
        
        from cerebric_core.rag.ingestion import RAGIngestionEngine
        
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
        
        # Hardcoded core sources (don't parse 3000 docs every time)
        # These are the known sources in our corpus
        core_sources = [
            {"name": "Arch Wiki", "count": 1200},
            {"name": "man pages", "count": 800},
            {"name": "Docker Docs", "count": 350},
            {"name": "Kubernetes Docs", "count": 300},
            {"name": "Linux Kernel Docs", "count": 200},
            {"name": "systemd", "count": 150},
        ]
        
        return {
            "custom_docs": custom_docs,
            "core_sources": core_sources,
            "total_core": 3000
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
