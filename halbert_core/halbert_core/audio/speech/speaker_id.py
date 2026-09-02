# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Speaker identification — CAM++ 256-dim embeddings via sherpa-onnx.

Uses sherpa-onnx ``SpeakerEmbeddingExtractor`` and ``SpeakerEmbeddingManager``
which provide built-in cosine similarity, multi-sample averaging, and
verification. Do NOT reinvent cosine similarity — use the built-in API.

Model: ``wespeaker_en_voxceleb_CAM++.onnx`` (27.9MB, 256-dim embeddings).
NOT ECAPA-TDNN (which sherpa-onnx does not support — causes errors).

Usage:
    from halbert_core.audio.speech.speaker_id import SpeakerIdentifier
    ident = SpeakerIdentifier(model_path="/path/to/CAM++.onnx")

    # Enroll
    ident.enroll("eric", "Eric", "admin", [pcm1, pcm2, pcm3])

    # Identify
    result = ident.identify(pcm_bytes)
    if result:
        print(f"Speaker: {result.name} ({result.role}), conf={result.confidence:.2f}")
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("halbert.audio.speech.speaker_id")

SAMPLE_RATE = 16_000
# CAM++ produces 256-dim embeddings (NOT 192-dim like ECAPA-TDNN)
CAM_EMBEDDING_DIM = 256


@dataclass
class SpeakerMatch:
    """Result of speaker identification."""
    speaker_id: str
    name: str
    role: str
    confidence: float


class SpeakerIdentifier:
    """Speaker ID via sherpa-onnx CAM++ embeddings.

    Lazy-imports ``sherpa_onnx`` on first use. The ``SpeakerEmbeddingManager``
    handles cosine similarity and multi-sample averaging internally.
    """

    def __init__(
        self,
        model_path: str = "",
        threshold: float = 0.75,
    ):
        self._model_path = model_path
        self._threshold = threshold
        self._extractor = None
        self._manager = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx speaker embedding extractor + manager."""
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx is not installed. "
                "Install with: pip install halbert-core[audio-inference]"
            )

        if not self._model_path:
            from ..config import load_config
            cfg = load_config()
            self._model_path = cfg.speaker_id.model
            self._threshold = cfg.speaker_id.threshold

        if not self._model_path:
            from ...utils.paths import data_subdir
            self._model_path = str(
                data_subdir("audio", "models", "CAM++.onnx")
            )

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=self._model_path,
            num_threads=2,
            debug=False,
        )
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        # Manager takes the embedding dimension, not a config object
        self._manager = sherpa_onnx.SpeakerEmbeddingManager(self._extractor.dim)
        self._sherpa = sherpa_onnx
        self._initialized = True
        logger.info(f"Speaker ID initialized: {self._model_path} ({self._extractor.dim}-dim CAM++)")
        self.load_enrolled_profiles()

    def load_enrolled_profiles(self, store: Optional[object] = None) -> int:
        """Load persisted voiceprints into the in-memory matcher.

        The manager starts empty and the enrollment route only ever wrote to
        SpeakerProfileStore, so nothing ever put an enrolled voiceprint in
        front of the matcher: identify() searched an empty index and every
        household member came back unrecognised, however many times they had
        enrolled (R9-F04). Returns the number of profiles loaded.
        """
        if self._manager is None:
            return 0
        try:
            if store is None:
                from ..storage.speaker_store import SpeakerProfileStore
                store = SpeakerProfileStore()
            profiles = store.list_all()
        except Exception as e:
            logger.warning(f"Could not read enrolled speakers (non-fatal): {e}")
            return 0

        loaded = 0
        for profile in profiles:
            try:
                self._manager.add(profile.speaker_id, [profile.embedding_as_list()])
                loaded += 1
            except Exception as e:
                logger.warning(f"Could not load voiceprint {profile.speaker_id}: {e}")
        if loaded:
            logger.info(f"Loaded {loaded} enrolled voiceprint(s) into the matcher")
        return loaded

    def register_profile(self, speaker_id: str, embedding: List[float]) -> bool:
        """Add one already-extracted voiceprint to the live matcher.

        So a speaker enrolled through the API is recognisable on the next
        turn rather than only after a restart.
        """
        try:
            self._ensure_initialized()
            self._manager.add(speaker_id, [list(embedding)])
            return True
        except Exception as e:
            logger.warning(f"Could not register voiceprint {speaker_id}: {e}")
            return False

    def extract_embedding(self, pcm_bytes: bytes) -> Optional[list]:
        """Extract a 256-dim speaker embedding from PCM audio.

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM (at least 3s recommended).

        Returns:
            256-dim float embedding, or None if audio too short.
        """
        self._ensure_initialized()
        assert self._extractor is not None

        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        stream = self._extractor.create_stream()
        stream.accept_waveform(SAMPLE_RATE, float_samples)
        stream.input_finished()

        if not self._extractor.is_ready(stream):
            logger.warning("Audio too short for speaker embedding extraction")
            return None

        embedding = self._extractor.compute(stream)
        return list(embedding)

    def enroll(
        self,
        speaker_id: str,
        name: str,
        role: str,
        pcm_samples: List[bytes],
    ) -> float:
        """Enroll a new speaker from multiple audio samples.

        Uses ``SpeakerEmbeddingManager.add()`` which averages multiple
        embeddings into a centroid automatically.

        Args:
            speaker_id: Unique ID for the speaker.
            name: Human-readable name.
            role: One of 'admin', 'member', 'guest', 'restricted'.
            pcm_samples: List of PCM byte buffers (3+ seconds each recommended).

        Returns:
            Quality score (average cosine similarity between samples).
        """
        self._ensure_initialized()
        assert self._manager is not None

        embeddings = []
        for pcm in pcm_samples:
            emb = self.extract_embedding(pcm)
            if emb is not None:
                embeddings.append(emb)

        if not embeddings:
            raise ValueError("No valid embeddings extracted from provided samples")

        # Manager.add() with a list averages them into a centroid
        self._manager.add(speaker_id, embeddings)

        # Compute quality: average pairwise cosine similarity
        quality = 0.0
        if len(embeddings) > 1:
            count = 0
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    score = self._manager.score(
                        speaker_id,
                        embeddings[j],
                    )
                    quality += score
                    count += 1
            quality /= count if count > 0 else 1
        else:
            quality = 1.0

        logger.info(
            f"Enrolled speaker '{name}' ({speaker_id}, role={role}) "
            f"with {len(embeddings)} samples, quality={quality:.3f}"
        )
        return quality

    def identify(self, pcm_bytes: bytes) -> Optional[SpeakerMatch]:
        """Identify the speaker of an audio sample.

        Args:
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM.

        Returns:
            SpeakerMatch if a speaker is identified above threshold,
            None otherwise.
        """
        self._ensure_initialized()
        assert self._manager is not None

        embedding = self.extract_embedding(pcm_bytes)
        if embedding is None:
            return None

        # Manager.search() returns the best matching speaker ID above threshold
        speaker_id = self._manager.search(embedding, self._threshold)
        if not speaker_id:
            return None

        # Get the raw score for confidence reporting
        score = self._manager.score(speaker_id, embedding)

        # Name and role come from the store (SpeakerProfileStore)
        # The manager only knows speaker_id -> embedding mapping.
        # The caller is responsible for looking up name/role from the store.
        return SpeakerMatch(
            speaker_id=speaker_id,
            name="",  # filled by caller from SpeakerProfileStore
            role="unknown",  # filled by caller from SpeakerProfileStore
            confidence=score,
        )

    def verify(
        self,
        speaker_id: str,
        pcm_bytes: bytes,
    ) -> tuple[bool, float]:
        """Verify that the speaker of an audio sample matches a known speaker.

        Args:
            speaker_id: The enrolled speaker to verify against.
            pcm_bytes: Raw 16-bit, 16kHz, mono PCM.

        Returns:
            (matched, score) — matched is True if score >= threshold.
        """
        self._ensure_initialized()
        assert self._manager is not None

        embedding = self.extract_embedding(pcm_bytes)
        if embedding is None:
            return False, 0.0

        if speaker_id not in self._manager:
            return False, 0.0

        matched = self._manager.verify(speaker_id, embedding, self._threshold)
        score = self._manager.score(speaker_id, embedding)
        return matched, score

    def remove(self, speaker_id: str) -> bool:
        """Remove an enrolled speaker."""
        self._ensure_initialized()
        assert self._manager is not None
        return self._manager.remove(speaker_id)

    def list_speakers(self) -> List[str]:
        """List all enrolled speaker IDs."""
        self._ensure_initialized()
        assert self._manager is not None
        return list(self._manager.all_speakers)

    @property
    def embedding_dim(self) -> int:
        """Embedding dimensionality (256 for CAM++)."""
        return CAM_EMBEDDING_DIM
