# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Streaming ASR engine — Sherpa-ONNX Zipformer INT8.

Uses sherpa-onnx ``OnlineRecognizer`` for streaming, chunk-by-chunk speech
recognition with zero future lookahead (confirmed: chunk-16-left-64
architecture uses only past frames).

Lazy-imports ``sherpa_onnx`` on first use.

Usage:
    from halbert_core.audio.speech.asr_engine import StreamingASR
    asr = StreamingASR(model_dir="/path/to/zipformer-int8")
    async for partial in asr.transcribe_stream(pcm_iterator):
        print(partial)  # "ZFS pool", "ZFS pool is", "ZFS pool is healthy"
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import AsyncIterator, Optional

logger = logging.getLogger("halbert.audio.speech.asr")

SAMPLE_RATE = 16_000


class StreamingASR:
    """Streaming speech-to-text via sherpa-onnx OnlineRecognizer.

    Emits partial transcripts as audio arrives — no need to wait for
    the full utterance. Zero future lookahead (streaming Zipformer).
    """

    def __init__(
        self,
        encoder: str = "",
        decoder: str = "",
        joiner: str = "",
        tokens: str = "",
        num_threads: int = 2,
    ):
        self._encoder = encoder
        self._decoder = decoder
        self._joiner = joiner
        self._tokens = tokens
        self._num_threads = num_threads
        self._recognizer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the sherpa-onnx online recognizer."""
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError(
                "sherpa-onnx is not installed. "
                "Install with: pip install halbert-core[audio-inference]"
            )

        if not self._encoder:
            from ..config import load_config
            from ...utils.paths import data_subdir
            models_dir = data_subdir("audio", "models", "zipformer-int8")
            self._encoder = f"{models_dir}/encoder-epoch-99-avg-1.int8.onnx"
            self._decoder = f"{models_dir}/decoder-epoch-99-avg-1.onnx"
            self._joiner = f"{models_dir}/joiner-epoch-99-avg-1.int8.onnx"
            self._tokens = f"{models_dir}/tokens.txt"

        # Use the high-level factory — OnlineRecognizer.from_transducer
        # handles all the config nesting (OnlineModelConfig.transducer,
        # EndpointConfig, ProviderConfig) internally.
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=self._tokens,
            encoder=self._encoder,
            decoder=self._decoder,
            joiner=self._joiner,
            num_threads=self._num_threads,
            decoding_method="greedy_search",
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.0,
            rule2_min_trailing_silence=1.0,
            rule3_min_utterance_length=20,
            provider="cpu",
        )
        self._sherpa = sherpa_onnx
        self._initialized = True
        logger.info(f"Streaming ASR initialized: {self._encoder}")

    async def transcribe_stream(
        self,
        pcm_iterator: AsyncIterator[bytes],
    ) -> AsyncIterator[str]:
        """Transcribe a stream of PCM chunks, yielding partial results.

        Args:
            pcm_iterator: Async iterator yielding 16-bit 16kHz mono PCM bytes.

        Yields:
            Partial transcript strings as they become available.
        """
        self._ensure_initialized()
        assert self._recognizer is not None

        stream = self._recognizer.create_stream()

        async for pcm in pcm_iterator:
            n = len(pcm) // 2
            samples = struct.unpack(f'<{n}h', pcm)
            float_samples = [s / 32768.0 for s in samples]

            stream.accept_waveform(SAMPLE_RATE, float_samples)

            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)
                text = self._recognizer.get_result(stream)
                if text:
                    yield text.strip()

            if self._recognizer.is_endpoint(stream):
                self._recognizer.reset(stream)

        # Final flush
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)
        text = self._recognizer.get_result(stream)
        if text:
            yield text.strip()

    def transcribe_chunk(self, pcm_bytes: bytes) -> str:
        """Synchronous single-chunk transcription (for testing).

        Creates a fresh stream, feeds one chunk, returns the result.
        Not suitable for streaming — use transcribe_stream for that.
        """
        self._ensure_initialized()
        assert self._recognizer is not None

        stream = self._recognizer.create_stream()
        n = len(pcm_bytes) // 2
        samples = struct.unpack(f'<{n}h', pcm_bytes)
        float_samples = [s / 32768.0 for s in samples]

        stream.accept_waveform(SAMPLE_RATE, float_samples)
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)

        return self._recognizer.get_result(stream).strip()
