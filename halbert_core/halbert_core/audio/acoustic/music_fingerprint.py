# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Music fingerprinting — Chromaprint + AcoustID lookup.

Generates audio fingerprints from PCM using Chromaprint, then looks up
the fingerprint via the AcoustID web API to identify the song.

REQUIRES NETWORK for song identification (AcoustID API lookup).
In offline/sovereign mode, fingerprints can be generated but not looked
up — the fingerprint is logged for future matching.

Lazy-imports ``pyacoustid`` and ``chromaprint`` (or fpcalc) on first use.
Install with: pip install halbert-core[audio-fingerprint]

Usage:
    from halbert_core.audio.acoustic.music_fingerprint import MusicFingerprinter
    fp = MusicFingerprinter(api_key="your_acoustid_key")
    result = fp.identify(pcm_bytes)
    if result:
        print(f"Track: {result['artist']} - {result['title']}")
"""

from __future__ import annotations

import logging
import struct
import subprocess
import tempfile
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("halbert.audio.acoustic.music_fingerprint")

SAMPLE_RATE = 16_000


@dataclass
class MusicMatch:
    """A music identification result."""
    artist: str
    title: str
    album: str = ""
    duration: float = 0.0
    fingerprint: str = ""
    score: float = 0.0
    source: str = "acoustid"


class MusicFingerprinter:
    """Chromaprint fingerprinting + AcoustID lookup.

    Lazy-imports pyacoustid and chromaprint. Requires the ``fpcalc`` binary
    (from chromaprint) or the ``chromaprint`` Python package.

    Network requirement: AcoustID lookup requires network access + API key.
    In offline mode, only the fingerprint is generated (no song name).
    """

    def __init__(
        self,
        api_key: str = "",
        requires_network: bool = True,
    ):
        self._api_key = api_key
        self._requires_network = requires_network
        self._available = None

    def is_available(self) -> bool:
        """Check if fingerprinting dependencies are available."""
        if self._available is not None:
            return self._available

        # Check for fpcalc binary (chromaprint CLI) or pyacoustid
        try:
            import pyacoustid
            self._available = True
        except ImportError:
            # Check for fpcalc binary
            try:
                result = subprocess.run(
                    ["fpcalc", "--version"],
                    capture_output=True,
                    timeout=5,
                )
                self._available = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self._available = False
                logger.debug(
                    "Music fingerprinting not available — "
                    "install with: pip install halbert-core[audio-fingerprint] "
                    "and ensure fpcalc binary is installed"
                )

        return self._available

    def generate_fingerprint(self, pcm_bytes: bytes) -> Optional[str]:
        """Generate a Chromaprint fingerprint from PCM audio.

        Writes PCM to a temp WAV file, runs fpcalc, returns the fingerprint
        string. Works offline (no network needed).

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM.

        Returns:
            Fingerprint string, or None on failure.
        """
        if not self.is_available():
            return None

        # Write PCM to a temp WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            self._write_wav(f, pcm_bytes)
            wav_path = f.name

        try:
            # Try pyacoustid first
            try:
                import acoustid
                fingerprint, duration = acoustid.fingerprint_file(wav_path)
                return fingerprint
            except ImportError:
                pass

            # Fall back to fpcalc binary
            result = subprocess.run(
                ["fpcalc", "-raw", wav_path],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                output = result.stdout.decode("utf-8")
                for line in output.splitlines():
                    if line.startswith("FINGERPRINT="):
                        return line.split("=", 1)[1]
            return None
        except Exception as e:
            logger.debug(f"Fingerprint generation failed: {e}")
            return None
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def identify(self, pcm_bytes: bytes) -> Optional[MusicMatch]:
        """Identify a song from PCM audio.

        Generates a fingerprint, then looks it up via AcoustID (requires
        network + API key). In offline mode, returns a partial result with
        only the fingerprint (no artist/title).

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM (10+ seconds recommended).

        Returns:
            MusicMatch if identified, None if no match or deps missing.
        """
        if not self.is_available():
            return None

        fingerprint = self.generate_fingerprint(pcm_bytes)
        if not fingerprint:
            return None

        # Offline mode: return fingerprint only
        if not self._requires_network or not self._api_key:
            return MusicMatch(
                artist="",
                title="(fingerprinted — offline mode)",
                fingerprint=fingerprint,
                source="chromaprint_offline",
            )

        # Online lookup via AcoustID
        try:
            import acoustid
            results = acoustid.lookup(self._api_key, fingerprint, SAMPLE_RATE)
            for score, recording_id, title, artist in acoustid.parse_lookup_result(results):
                return MusicMatch(
                    artist=artist or "",
                    title=title or "",
                    score=score,
                    fingerprint=fingerprint,
                    source="acoustid",
                )
        except Exception as e:
            logger.debug(f"AcoustID lookup failed: {e}")
            return MusicMatch(
                artist="",
                title="(lookup failed)",
                fingerprint=fingerprint,
                source="chromaprint_lookup_failed",
            )

        return None

    def _write_wav(self, f, pcm_bytes: bytes) -> None:
        """Write raw PCM as a minimal WAV file."""
        import wave
        with wave.open(f.name, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm_bytes)
