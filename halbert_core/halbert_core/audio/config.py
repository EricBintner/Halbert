# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Audio configuration.

Loaded from ~/.config/halbert/audio_config.yml. All audio features are OFF
by default — the user must explicitly enable microphone access, acoustic
event detection, speaker identification, and TTS.

The config is read on every use (not cached), so changes take effect
immediately without a restart. This mirrors the vision/config.py pattern
deliberately: a stale cache would mean a user who disables mic access
might still have audio captured before the next restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("halbert.audio.config")


def _config_path() -> Path:
    """Path to audio_config.yml in the user's config directory."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / "audio_config.yml"
    except Exception:
        return Path.home() / ".config" / "halbert" / "audio_config.yml"


# ── Sub-configs ──────────────────────────────────────────────────────────

@dataclass
class LocalMicConfig:
    """Host built-in microphone capture (via Rust cpal -> loopback socket)."""
    enabled: bool = False
    device_index: int = 0
    sample_rate: int = 16000
    aec_enabled: bool = True       # AEC required for desktop duplex
    socket_port: int = 0           # 0 = auto-assign (Rust side picks)


@dataclass
class WyomingIngressConfig:
    """Wyoming TCP satellite ingress (ESP32 / Pi on port 10400)."""
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 10400


@dataclass
class RtspIngressConfig:
    """Frigate / IP camera RTSP audio track extraction."""
    enabled: bool = False
    cameras: List[Dict] = field(default_factory=list)  # [{"name":, "url":, "area_id":}]


@dataclass
class AcousticEventsConfig:
    """Ambient sound classification (CED-tiny / Zipformer-small)."""
    enabled: bool = False
    energy_floor_db: float = -45.0   # bypass when ambient energy below this
    check_interval_s: float = 2.0    # evaluate every N seconds
    model: str = ""                  # path to ONNX model (empty = default CED-tiny)


@dataclass
class MusicRecognitionConfig:
    """Ambient music fingerprinting via Chromaprint / AcoustID."""
    enabled: bool = False
    requires_network: bool = True    # AcoustID lookup needs network
    acoustid_api_key: str = ""


@dataclass
class SpeakerIdConfig:
    """Biometric speaker identification (CAM++ 256-dim)."""
    enabled: bool = False
    threshold: float = 0.75          # cosine similarity threshold
    model: str = ""                  # path to CAM++ ONNX (empty = default)


@dataclass
class TtsConfig:
    """Piper TTS via sherpa-onnx (OHF-Voice/piper1-gpl voices)."""
    enabled: bool = False
    voice_model: str = ""            # path to Piper .onnx voice
    speaker_id: int = 0              # for multi-speaker voices


@dataclass
class AudioPrivacyConfig:
    """Privacy controls for audio capture."""
    delete_raw_after_transcription: bool = True
    ignore_tv_media: bool = True
    retain_no_wav: bool = True
    quiet_hours: Optional[Dict[str, str]] = None  # {"start": "22:00", "end": "07:00"}


@dataclass
class AudioConfig:
    """Top-level audio configuration."""
    enabled: bool = False  # master switch — ALL OFF by default
    local_mic: LocalMicConfig = field(default_factory=LocalMicConfig)
    wyoming_ingress: WyomingIngressConfig = field(default_factory=WyomingIngressConfig)
    rtsp_ingress: RtspIngressConfig = field(default_factory=RtspIngressConfig)
    acoustic_events: AcousticEventsConfig = field(default_factory=AcousticEventsConfig)
    music_recognition: MusicRecognitionConfig = field(default_factory=MusicRecognitionConfig)
    speaker_id: SpeakerIdConfig = field(default_factory=SpeakerIdConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    privacy: AudioPrivacyConfig = field(default_factory=AudioPrivacyConfig)


# ── Load / Save ──────────────────────────────────────────────────────────

def load_config() -> AudioConfig:
    """Load audio config from disk, or return defaults if missing/unreadable."""
    path = _config_path()
    if not path.exists():
        return AudioConfig()
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return _parse_config(data)
    except Exception as e:
        logger.warning(f"Failed to load audio config: {e}, using defaults")
        return AudioConfig()


def _parse_config(data: dict) -> AudioConfig:
    """Parse a yaml dict into AudioConfig."""
    local = data.get("local_mic", {})
    wy = data.get("wyoming_ingress", {})
    rtsp = data.get("rtsp_ingress", {})
    acoustic = data.get("acoustic_events", {})
    music = data.get("music_recognition", {})
    speaker = data.get("speaker_id", {})
    tts = data.get("tts", {})
    privacy = data.get("privacy", {})

    return AudioConfig(
        enabled=data.get("enabled", False),
        local_mic=LocalMicConfig(
            enabled=local.get("enabled", False),
            device_index=local.get("device_index", 0),
            sample_rate=local.get("sample_rate", 16000),
            aec_enabled=local.get("aec_enabled", True),
            socket_port=local.get("socket_port", 0),
        ),
        wyoming_ingress=WyomingIngressConfig(
            enabled=wy.get("enabled", False),
            host=wy.get("host", "0.0.0.0"),
            port=wy.get("port", 10400),
        ),
        rtsp_ingress=RtspIngressConfig(
            enabled=rtsp.get("enabled", False),
            cameras=rtsp.get("cameras", []),
        ),
        acoustic_events=AcousticEventsConfig(
            enabled=acoustic.get("enabled", False),
            energy_floor_db=acoustic.get("energy_floor_db", -45.0),
            check_interval_s=acoustic.get("check_interval_s", 2.0),
            model=acoustic.get("model", ""),
        ),
        music_recognition=MusicRecognitionConfig(
            enabled=music.get("enabled", False),
            requires_network=music.get("requires_network", True),
            acoustid_api_key=music.get("acoustid_api_key", ""),
        ),
        speaker_id=SpeakerIdConfig(
            enabled=speaker.get("enabled", False),
            threshold=speaker.get("threshold", 0.75),
            model=speaker.get("model", ""),
        ),
        tts=TtsConfig(
            enabled=tts.get("enabled", False),
            voice_model=tts.get("voice_model", ""),
            speaker_id=tts.get("speaker_id", 0),
        ),
        privacy=AudioPrivacyConfig(
            delete_raw_after_transcription=privacy.get("delete_raw_after_transcription", True),
            ignore_tv_media=privacy.get("ignore_tv_media", True),
            retain_no_wav=privacy.get("retain_no_wav", True),
            quiet_hours=privacy.get("quiet_hours"),
        ),
    )


def save_config(config: AudioConfig) -> None:
    """Save audio config to disk."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "enabled": config.enabled,
        "local_mic": {
            "enabled": config.local_mic.enabled,
            "device_index": config.local_mic.device_index,
            "sample_rate": config.local_mic.sample_rate,
            "aec_enabled": config.local_mic.aec_enabled,
            "socket_port": config.local_mic.socket_port,
        },
        "wyoming_ingress": {
            "enabled": config.wyoming_ingress.enabled,
            "host": config.wyoming_ingress.host,
            "port": config.wyoming_ingress.port,
        },
        "rtsp_ingress": {
            "enabled": config.rtsp_ingress.enabled,
            "cameras": config.rtsp_ingress.cameras,
        },
        "acoustic_events": {
            "enabled": config.acoustic_events.enabled,
            "energy_floor_db": config.acoustic_events.energy_floor_db,
            "check_interval_s": config.acoustic_events.check_interval_s,
            "model": config.acoustic_events.model,
        },
        "music_recognition": {
            "enabled": config.music_recognition.enabled,
            "requires_network": config.music_recognition.requires_network,
            "acoustid_api_key": config.music_recognition.acoustid_api_key,
        },
        "speaker_id": {
            "enabled": config.speaker_id.enabled,
            "threshold": config.speaker_id.threshold,
            "model": config.speaker_id.model,
        },
        "tts": {
            "enabled": config.tts.enabled,
            "voice_model": config.tts.voice_model,
            "speaker_id": config.tts.speaker_id,
        },
        "privacy": {
            "delete_raw_after_transcription": config.privacy.delete_raw_after_transcription,
            "ignore_tv_media": config.privacy.ignore_tv_media,
            "retain_no_wav": config.privacy.retain_no_wav,
            "quiet_hours": config.privacy.quiet_hours,
        },
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


# ── Convenience gates (read on every call) ───────────────────────────────

def is_audio_enabled() -> bool:
    """Master switch. Read on every call."""
    return load_config().enabled


def is_local_mic_enabled() -> bool:
    """Check if local mic capture is enabled. Read on every call."""
    cfg = load_config()
    return cfg.enabled and cfg.local_mic.enabled


def is_wyoming_ingress_enabled() -> bool:
    """Check if Wyoming ingress is enabled. Read on every call."""
    cfg = load_config()
    return cfg.enabled and cfg.wyoming_ingress.enabled
