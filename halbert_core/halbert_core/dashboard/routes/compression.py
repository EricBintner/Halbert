"""
Compression API routes.

Provides endpoints for context compression configuration, status, and testing.
Provides endpoints for the 3-tier context compression system.
"""

from __future__ import annotations
import logging

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger('halbert.dashboard.routes.compression')

router = APIRouter(prefix="/api/compression", tags=["compression"])


class ConfigUpdateRequest(BaseModel):
    """Request to update compression config."""
    enabled: bool | None = None
    backend: str | None = None  # auto | lingua | semantic | noop
    threshold: int | None = None
    level: str | None = None  # light | standard | aggressive
    lod_epistemic_floor: float | None = None


class CompressRequest(BaseModel):
    """Request to compress text."""
    text: str
    query: str = ""
    level: str = "standard"


class TestRequest(BaseModel):
    """Request to run a test compression."""
    text: str
    query: str = ""


@router.get("/status")
async def get_status():
    """Get compression system status including active backend."""
    try:
        from ...compression.factory import create_compressor
        compressor = create_compressor()
        return compressor.status()
    except Exception as e:
        logger.exception("Failed to get compression status")
        return {
            "available": False,
            "error": str(e),
            "type": "unknown",
        }


@router.get("/config")
async def get_config():
    """Get current compression config from models.yml."""
    try:
        import yaml
        from pathlib import Path

        config_path = Path(__file__).resolve().parents[3] / "config" / "models.yml"
        if not config_path.exists():
            # Try alternate path
            config_path = Path.cwd() / "config" / "models.yml"

        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            comp_config = config.get("compression", {})
        else:
            comp_config = {}

        # Defaults
        return {
            "enabled": comp_config.get("enabled", True),
            "backend": comp_config.get("backend", "auto"),
            "threshold": comp_config.get("threshold", 4000),
            "level": comp_config.get("level", "standard"),
            "lod_epistemic_floor": comp_config.get("lod_epistemic_floor", 0.8),
        }
    except Exception as e:
        logger.exception("Failed to get compression config")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(req: ConfigUpdateRequest):
    """Update compression config in models.yml."""
    try:
        import yaml
        from pathlib import Path

        config_path = Path(__file__).resolve().parents[3] / "config" / "models.yml"
        if not config_path.exists():
            config_path = Path.cwd() / "config" / "models.yml"

        if not config_path.exists():
            raise HTTPException(status_code=404, detail="config/models.yml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        if "compression" not in config:
            config["compression"] = {}

        updates = req.model_dump(exclude_none=True)
        config["compression"].update(updates)

        with open(config_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

        return {"status": "ok", "config": config["compression"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update compression config")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compress")
async def compress_text(req: CompressRequest):
    """Manually compress text using the compression system."""
    try:
        from ...compression.factory import create_compressor

        compressor = create_compressor()
        result = compressor.compress(req.text, query=req.query, level=req.level)

        return {
            "compressed": result.compressed,
            "input_chars": result.input_chars,
            "output_chars": result.output_chars,
            "compression_ratio": result.compression_ratio,
            "timing_ms": result.timing_ms,
            "error": result.error,
            "backend": type(compressor).__name__,
        }
    except Exception as e:
        logger.exception("Compression failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_compression(req: TestRequest):
    """Run a test compression and return before/after stats."""
    try:
        from ...compression.factory import create_compressor
        from ...compression.semantic_compressor import SemanticCompressor

        compressor = create_compressor()

        # Run compression at all 3 levels for comparison
        results = {}
        for level in ["light", "standard", "aggressive"]:
            result = compressor.compress(req.text, query=req.query, level=level)
            results[level] = {
                "output_chars": result.output_chars,
                "compression_ratio": result.compression_ratio,
                "timing_ms": result.timing_ms,
                "compressed_preview": result.compressed[:200] + ("..." if len(result.compressed) > 200 else ""),
            }

        # Also get semantic-only for comparison
        semantic = SemanticCompressor()
        sem_result = semantic.compress(req.text, level="standard")
        results["semantic_standard"] = {
            "output_chars": sem_result.output_chars,
            "compression_ratio": sem_result.compression_ratio,
            "timing_ms": sem_result.timing_ms,
            "compressed_preview": sem_result.compressed[:200] + ("..." if len(sem_result.compressed) > 200 else ""),
        }

        return {
            "input_chars": len(req.text),
            "input_preview": req.text[:200] + ("..." if len(req.text) > 200 else ""),
            "active_backend": type(compressor).__name__,
            "results": results,
        }
    except Exception as e:
        logger.exception("Test compression failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backends")
async def list_backends():
    """List available compression backends and their status."""
    backends = []

    # Check Lingua
    try:
        from ...compression.lingua_compressor import LinguaCompressor
        lingua = LinguaCompressor()
        backends.append({
            "name": "lingua",
            "type": "neural",
            "available": lingua.is_available(),
            "model": lingua.HF_MODEL_ID,
            "model_size": "178MB",
            "description": "LLMLingua-2 token pruning (neural, CPU-only)",
        })
    except Exception:
        backends.append({"name": "lingua", "available": False})

    # Check Semantic (always available)
    backends.append({
        "name": "semantic",
        "type": "rule-based",
        "available": True,
        "description": "Regex-based compression (zero dependencies)",
    })

    # Noop (always available)
    backends.append({
        "name": "noop",
        "type": "pass-through",
        "available": True,
        "description": "No compression (returns input unchanged)",
    })

    return {"backends": backends}
