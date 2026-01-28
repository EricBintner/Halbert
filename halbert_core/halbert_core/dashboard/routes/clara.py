"""
CLaRa API routes.

Provides endpoints for CLaRa context compression configuration and status.
"""

from __future__ import annotations
import logging

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger('halbert.dashboard.routes.clara')

router = APIRouter(prefix="/api/clara", tags=["clara"])


class ConfigUpdateRequest(BaseModel):
    """Request to update CLaRa config."""
    use_remote: bool | None = None
    remote_url: str | None = None
    remote_api_key: str | None = None
    auto_compress_threshold: int | None = None


class ToggleRequest(BaseModel):
    """Request to enable/disable CLaRa."""
    enabled: bool


class CompressRequest(BaseModel):
    """Request to compress memories."""
    memories: list[str]
    query: str
    max_new_tokens: int = 128


@router.get("/status")
async def get_status():
    """Get CLaRa status including remote health."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        return provider.get_status()
    except Exception as e:
        logger.exception("Failed to get CLaRa status")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config():
    """Get current CLaRa configuration."""
    try:
        from ...model.clara_provider import get_clara_provider
        from dataclasses import asdict
        provider = get_clara_provider()
        config = asdict(provider.config)
        # Don't expose API key
        if config.get('remote_api_key'):
            config['remote_api_key'] = '***'
        return config
    except Exception as e:
        logger.exception("Failed to get CLaRa config")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(request: ConfigUpdateRequest):
    """Update CLaRa configuration."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        
        updates = {}
        if request.use_remote is not None:
            updates['use_remote'] = request.use_remote
        if request.remote_url is not None:
            updates['remote_url'] = request.remote_url
        if request.remote_api_key is not None:
            updates['remote_api_key'] = request.remote_api_key
        if request.auto_compress_threshold is not None:
            updates['auto_compress_threshold'] = request.auto_compress_threshold
        
        return provider.update_config(**updates)
    except Exception as e:
        logger.exception("Failed to update CLaRa config")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle")
async def toggle_enabled(request: ToggleRequest):
    """Enable or disable CLaRa."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        return provider.set_enabled(request.enabled)
    except Exception as e:
        logger.exception("Failed to toggle CLaRa")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize")
async def initialize():
    """Initialize/load the CLaRa model (local mode)."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        
        success = provider.initialize()
        return {
            'success': success,
            'initialized': provider._initialized,
            'load_time_seconds': provider._load_time,
            'error': provider._last_error if not success else None,
        }
    except Exception as e:
        logger.exception("Failed to initialize CLaRa")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unload")
async def unload():
    """Unload CLaRa model to free VRAM."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        provider.unload()
        return {'success': True, 'message': 'Model unloaded'}
    except Exception as e:
        logger.exception("Failed to unload CLaRa")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install-deps")
async def install_dependencies():
    """Install CLaRa dependencies (transformers, accelerate, etc.)."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        return provider.install_dependencies()
    except Exception as e:
        logger.exception("Failed to install dependencies")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/remote/health")
async def check_remote_health():
    """Check remote CLaRa server health."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        return provider.check_remote_health()
    except Exception as e:
        logger.exception("Failed to check remote health")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compress")
async def compress_memories(request: CompressRequest):
    """Compress memories using CLaRa."""
    try:
        from ...model.clara_provider import get_clara_provider
        provider = get_clara_provider()
        
        if not provider.config.enabled:
            raise HTTPException(status_code=400, detail="CLaRa is not enabled")
        
        result = provider.compress_memories(
            memories=request.memories,
            query=request.query,
            max_new_tokens=request.max_new_tokens,
        )
        
        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', 'Compression failed'))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to compress memories")
        raise HTTPException(status_code=500, detail=str(e))
