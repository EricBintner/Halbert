# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Audio API routes.

Provides endpoints for audio configuration, speaker enrollment, acoustic
event listing, and subsystem status. Mirrors the vision routes pattern.

All audio features are OFF by default and must be enabled via
Settings > Audio & Voice. The config is read on every request (not cached).
"""

import base64
import logging
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Request
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.audio.routes")
router = APIRouter(prefix="/audio", tags=["audio"])


if FASTAPI_AVAILABLE:

    from ...audio.config import (
        load_config, save_config, AudioConfig,
    )
    from ...audio.is_available import is_audio_available

    # ── Config endpoints ────────────────────────────────────────────

    @router.get("/config")
    async def get_audio_config():
        """Load audio_config.yml."""
        cfg = load_config()
        return {
            "enabled": cfg.enabled,
            "local_mic": {
                "enabled": cfg.local_mic.enabled,
                "device_index": cfg.local_mic.device_index,
                "sample_rate": cfg.local_mic.sample_rate,
                "aec_enabled": cfg.local_mic.aec_enabled,
            },
            "wyoming_ingress": {
                "enabled": cfg.wyoming_ingress.enabled,
                "host": cfg.wyoming_ingress.host,
                "port": cfg.wyoming_ingress.port,
            },
            "acoustic_events": {
                "enabled": cfg.acoustic_events.enabled,
                "energy_floor_db": cfg.acoustic_events.energy_floor_db,
                "check_interval_s": cfg.acoustic_events.check_interval_s,
            },
            "speaker_id": {
                "enabled": cfg.speaker_id.enabled,
                "threshold": cfg.speaker_id.threshold,
            },
            "tts": {
                "enabled": cfg.tts.enabled,
                "voice_model": cfg.tts.voice_model,
            },
            "privacy": {
                "delete_raw_after_transcription": cfg.privacy.delete_raw_after_transcription,
                "ignore_tv_media": cfg.privacy.ignore_tv_media,
                "quiet_hours": cfg.privacy.quiet_hours,
            },
        }

    class AudioConfigUpdate(BaseModel):
        enabled: Optional[bool] = None
        local_mic_enabled: Optional[bool] = None
        wyoming_ingress_enabled: Optional[bool] = None
        wyoming_ingress_port: Optional[int] = None
        acoustic_events_enabled: Optional[bool] = None
        speaker_id_enabled: Optional[bool] = None
        speaker_id_threshold: Optional[float] = None
        tts_enabled: Optional[bool] = None
        tts_voice_model: Optional[str] = None
        privacy_delete_raw_after_transcription: Optional[bool] = None
        privacy_ignore_tv_media: Optional[bool] = None

    @router.post("/config")
    async def update_audio_config(update: AudioConfigUpdate):
        """Save audio config changes."""
        cfg = load_config()
        if update.enabled is not None:
            cfg.enabled = update.enabled
        if update.local_mic_enabled is not None:
            cfg.local_mic.enabled = update.local_mic_enabled
        if update.wyoming_ingress_enabled is not None:
            cfg.wyoming_ingress.enabled = update.wyoming_ingress_enabled
        if update.wyoming_ingress_port is not None:
            cfg.wyoming_ingress.port = update.wyoming_ingress_port
        if update.acoustic_events_enabled is not None:
            cfg.acoustic_events.enabled = update.acoustic_events_enabled
        if update.speaker_id_enabled is not None:
            cfg.speaker_id.enabled = update.speaker_id_enabled
        if update.speaker_id_threshold is not None:
            cfg.speaker_id.threshold = update.speaker_id_threshold
        if update.tts_enabled is not None:
            cfg.tts.enabled = update.tts_enabled
        if update.tts_voice_model is not None:
            cfg.tts.voice_model = update.tts_voice_model
        if update.privacy_delete_raw_after_transcription is not None:
            cfg.privacy.delete_raw_after_transcription = update.privacy_delete_raw_after_transcription
        if update.privacy_ignore_tv_media is not None:
            cfg.privacy.ignore_tv_media = update.privacy_ignore_tv_media
        save_config(cfg)
        return {"status": "ok"}

    # ── Status endpoint ─────────────────────────────────────────────

    @router.get("/status")
    async def get_audio_status(request: Request):
        """Audio subsystem status — live when the pipeline coordinator is up."""
        coordinator = getattr(request.app.state, "audio_coordinator", None)
        if coordinator is not None:
            try:
                return coordinator.get_status()
            except Exception as e:
                logger.warning(f"coordinator status failed, using static fallback: {e}")
        cfg = load_config()
        return {
            "enabled": cfg.enabled,
            "available": is_audio_available(),
            "sherpa_onnx_installed": is_audio_available(),
            "state": "idle",  # TODO: live once app.state.audio_coordinator is wired (O2)
            "engines": {
                "vad": is_audio_available(),
                "asr": is_audio_available(),
                "tts": is_audio_available() and cfg.tts.enabled,
                "speaker_id": is_audio_available() and cfg.speaker_id.enabled,
                "audio_tagger": is_audio_available() and cfg.acoustic_events.enabled,
            },
        }

    # ── Speaker endpoints ───────────────────────────────────────────

    @router.get("/speakers")
    async def list_speakers():
        """List enrolled speaker profiles."""
        try:
            from ...audio.storage.speaker_store import SpeakerProfileStore
            store = SpeakerProfileStore()
            profiles = store.list_all()
            return {
                "speakers": [
                    {
                        "speaker_id": p.speaker_id,
                        "name": p.name,
                        "role": p.role,
                        "sample_count": p.sample_count,
                        "threshold": p.threshold,
                        "embedding_dim": p.embedding_dim,
                        "created_at": p.created_at,
                    }
                    for p in profiles
                ],
                "count": len(profiles),
            }
        except Exception as e:
            logger.error(f"List speakers error: {e}")
            return {"speakers": [], "count": 0, "error": str(e)}

    class SpeakerEnrollRequest(BaseModel):
        name: str
        role: str  # 'admin', 'member', 'guest', 'restricted'
        audio_base64: str  # base64-encoded WAV or raw PCM
        threshold: float = 0.75

    @router.post("/speakers/enroll")
    async def enroll_speaker(req: SpeakerEnrollRequest):
        """Enroll a new speaker from audio data."""
        if not is_audio_available():
            raise HTTPException(503, "sherpa-onnx not installed")

        if req.role not in ("admin", "member", "guest", "restricted"):
            raise HTTPException(400, "Invalid role")

        try:
            import uuid
            audio_bytes = base64.b64decode(req.audio_base64)

            from ...audio.speech.speaker_id import SpeakerIdentifier
            from ...audio.storage.speaker_store import SpeakerProfileStore

            ident = SpeakerIdentifier(threshold=req.threshold)
            embedding = ident.extract_embedding(audio_bytes)
            if embedding is None:
                raise HTTPException(400, "Audio too short for embedding extraction")

            speaker_id = str(uuid.uuid4())
            store = SpeakerProfileStore()
            profile = store.enroll(
                speaker_id=speaker_id,
                name=req.name,
                role=req.role,
                embedding=embedding,
                threshold=req.threshold,
            )

            return {
                "speaker_id": profile.speaker_id,
                "name": profile.name,
                "role": profile.role,
                "embedding_dim": profile.embedding_dim,
                "threshold": profile.threshold,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Enroll speaker error: {e}")
            raise HTTPException(500, str(e))

    class SpeakerTestRequest(BaseModel):
        audio_base64: str

    @router.post("/speakers/{speaker_id}/test")
    async def test_speaker(speaker_id: str, req: SpeakerTestRequest):
        """Test speaker verification against an audio sample."""
        if not is_audio_available():
            raise HTTPException(503, "sherpa-onnx not installed")

        try:
            audio_bytes = base64.b64decode(req.audio_base64)

            from ...audio.speech.speaker_id import SpeakerIdentifier
            ident = SpeakerIdentifier()
            matched, score = ident.verify(speaker_id, audio_bytes)

            return {
                "speaker_id": speaker_id,
                "matched": matched,
                "score": score,
                "threshold": ident._threshold,
            }
        except Exception as e:
            logger.error(f"Test speaker error: {e}")
            raise HTTPException(500, str(e))

    @router.delete("/speakers/{speaker_id}")
    async def delete_speaker(speaker_id: str):
        """Delete a speaker profile."""
        try:
            from ...audio.storage.speaker_store import SpeakerProfileStore
            store = SpeakerProfileStore()
            if store.delete(speaker_id):
                return {"status": "ok", "deleted": speaker_id}
            raise HTTPException(404, "Speaker not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Delete speaker error: {e}")
            raise HTTPException(500, str(e))

    # ── Ingress status ──────────────────────────────────────────────

    @router.get("/ingress/status")
    async def get_ingress_status():
        """List connected audio ingress sources."""
        cfg = load_config()
        sources = []
        if cfg.local_mic.enabled:
            sources.append({
                "type": "local_mic",
                "enabled": True,
                "running": False,  # TODO: read from pipeline
            })
        if cfg.wyoming_ingress.enabled:
            sources.append({
                "type": "wyoming_satellite",
                "enabled": True,
                "host": cfg.wyoming_ingress.host,
                "port": cfg.wyoming_ingress.port,
                "running": False,
            })
        if cfg.rtsp_ingress.enabled:
            for cam in cfg.rtsp_ingress.cameras:
                sources.append({
                    "type": "frigate_rtsp",
                    "enabled": True,
                    "name": cam.get("name", ""),
                    "area_id": cam.get("area_id", ""),
                })
        return {"sources": sources, "count": len(sources)}
