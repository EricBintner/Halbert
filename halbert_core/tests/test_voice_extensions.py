# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for hardware detection, spatial arbiter, and Wyoming egress."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------

class TestHardwareDetect:
    def test_detect_returns_profile(self):
        from halbert_core.audio.hardware_detect import detect_hardware, HardwareProfile
        profile = detect_hardware()
        assert isinstance(profile, HardwareProfile)
        assert profile.tier in (1, 2, 3, 4)
        assert "cpu" in profile.providers
        assert profile.cpu_cores > 0

    def test_recommended_threads_by_tier(self):
        from halbert_core.audio.hardware_detect import HardwareProfile
        assert HardwareProfile(tier=1, cpu_cores=16).recommended_threads == 8
        assert HardwareProfile(tier=2, cpu_cores=8).recommended_threads == 4
        assert HardwareProfile(tier=3, cpu_cores=4).recommended_threads == 2
        assert HardwareProfile(tier=4, is_mobile=True, cpu_cores=8).recommended_threads == 1

    def test_recommended_quantization_by_tier(self):
        from halbert_core.audio.hardware_detect import HardwareProfile
        assert HardwareProfile(tier=1).recommended_quantization == "fp32"
        assert HardwareProfile(tier=2).recommended_quantization == "fp16"
        assert HardwareProfile(tier=3).recommended_quantization == "int8"

    def test_best_provider(self):
        from halbert_core.audio.hardware_detect import HardwareProfile
        assert HardwareProfile(providers=("cuda", "cpu")).best_provider == "cuda"
        assert HardwareProfile(providers=("cpu",)).best_provider == "cpu"

    def test_recommended_tts_config(self):
        from halbert_core.audio.hardware_detect import (
            HardwareProfile, recommended_tts_config,
        )
        p = HardwareProfile(tier=1, providers=("cuda", "cpu"), cpu_cores=16)
        cfg = recommended_tts_config(p)
        assert cfg["execution_provider"] == "cuda"
        assert cfg["num_threads"] == 8
        assert cfg["hardware_tier"] == 1


class TestChannelCapabilityHardware:
    def test_hardware_tier_returns_int(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability()
        tier = cap.hardware_tier()
        assert isinstance(tier, int)
        assert tier in (1, 2, 3, 4)

    def test_execution_providers_returns_tuple(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability()
        providers = cap.execution_providers()
        assert isinstance(providers, tuple)
        assert "cpu" in providers

    def test_output_sink_count(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability(is_desktop=True, wyoming_active=False)
        # No speaker (no pipeline) -> 0 sinks
        assert cap.output_sink_count() == 0

        cap.set_wyoming_active(True)
        # Wyoming active -> at least 1 sink (the satellite)
        assert cap.output_sink_count() >= 1

    def test_sink_per_ingress_defaults_false(self):
        from halbert_core.integrations.channel_capability import HalbertChannelCapability
        cap = HalbertChannelCapability()
        assert cap.sink_per_ingress() is False


# ---------------------------------------------------------------------------
# Spatial Audio Arbiter
# ---------------------------------------------------------------------------

class TestSpatialArbiter:
    def test_accept_first_observation(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        result = arb.arbitrate(
            speaker_id="alice", source_id="local_mic", text="hello",
        )
        assert result.decision == ArbitrationDecision.ACCEPT

    def test_suppress_coincidence_duplicate(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        # First mic accepts
        r1 = arb.arbitrate(speaker_id="alice", source_id="local_mic")
        assert r1.decision == ArbitrationDecision.ACCEPT
        # Second mic within coincidence window -> suppress
        r2 = arb.arbitrate(speaker_id="alice", source_id="wyoming_living_room")
        assert r2.decision == ArbitrationDecision.SUPPRESS
        assert r2.reason == "coincidence_duplicate"

    def test_suppress_turn_lock_same_source(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        r1 = arb.arbitrate(speaker_id="bob", source_id="local_mic")
        assert r1.decision == ArbitrationDecision.ACCEPT
        # Same source re-triggering within lock window
        r2 = arb.arbitrate(speaker_id="bob", source_id="local_mic")
        assert r2.decision == ArbitrationDecision.SUPPRESS
        assert r2.reason == "turn_lock"

    def test_accept_after_lock_expires(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        # Simulate expired lock by manipulating timestamps
        arb.arbitrate(speaker_id="carol", source_id="local_mic")
        # Manually expire the lock
        for lock in arb._locks.values():
            lock.accepted_at = time.monotonic() - 10.0
        r2 = arb.arbitrate(speaker_id="carol", source_id="local_mic")
        assert r2.decision == ArbitrationDecision.ACCEPT

    def test_media_filtered(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        result = arb.arbitrate(
            speaker_id="alice", source_id="tv", is_media=True,
        )
        assert result.decision == ArbitrationDecision.SUPPRESS
        assert result.reason == "media_filtered"

    def test_media_source_marked_filtered(self):
        """A source marked as media via mark_media_source is filtered
        even when the per-observation is_media flag is False."""
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        arb.mark_media_source("tv_source")
        result = arb.arbitrate(
            speaker_id="alice", source_id="tv_source", is_media=False,
        )
        assert result.decision == ArbitrationDecision.SUPPRESS
        assert result.reason == "media_filtered"

    def test_unknown_speaker_accepted(self):
        """Empty speaker_id (unknown, e.g. Wyoming transcripts) is
        always accepted — we can't distinguish two unknown speakers,
        so locking would suppress the wrong person."""
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        r1 = arb.arbitrate(speaker_id="", source_id="wyoming_living_room")
        assert r1.decision == ArbitrationDecision.ACCEPT
        assert r1.reason == "unknown_speaker"
        # A second unknown speaker from a different source is also accepted
        r2 = arb.arbitrate(speaker_id="", source_id="wyoming_kitchen")
        assert r2.decision == ArbitrationDecision.ACCEPT

    def test_self_speech_suppression(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        arb.on_tts_start(source_id="local_mic")
        result = arb.arbitrate(
            speaker_id="alice", source_id="local_mic",
        )
        assert result.decision == ArbitrationDecision.SUPPRESS
        assert result.reason == "self_speech_feedback"

    def test_self_speech_not_suppressed_after_tts_end(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        arb.on_tts_start(source_id="local_mic")
        arb.on_tts_end()
        result = arb.arbitrate(
            speaker_id="alice", source_id="local_mic",
        )
        assert result.decision == ArbitrationDecision.ACCEPT

    def test_ducking_state(self):
        from halbert_core.audio.spatial_arbiter import SpatialAudioArbiter
        arb = SpatialAudioArbiter()
        assert not arb.is_ducking
        assert arb.current_vad_threshold == 0.5
        assert arb.current_mic_gain_db == 0.0

        arb.on_tts_start(source_id="local_mic")
        assert arb.is_ducking
        assert arb.current_vad_threshold == 0.85
        assert arb.current_mic_gain_db == -18.0

        arb.on_tts_end()
        assert not arb.is_ducking

    def test_media_source_marking(self):
        from halbert_core.audio.spatial_arbiter import SpatialAudioArbiter
        arb = SpatialAudioArbiter()
        assert not arb.is_media_source("tv_source")
        arb.mark_media_source("tv_source")
        assert arb.is_media_source("tv_source")
        arb.unmark_media_source("tv_source")
        assert not arb.is_media_source("tv_source")

    def test_different_speakers_both_accepted(self):
        from halbert_core.audio.spatial_arbiter import (
            SpatialAudioArbiter, ArbitrationDecision,
        )
        arb = SpatialAudioArbiter()
        r1 = arb.arbitrate(speaker_id="alice", source_id="local_mic")
        r2 = arb.arbitrate(speaker_id="bob", source_id="local_mic")
        assert r1.decision == ArbitrationDecision.ACCEPT
        assert r2.decision == ArbitrationDecision.ACCEPT


# ---------------------------------------------------------------------------
# Wyoming Egress Hub
# ---------------------------------------------------------------------------

class TestWyomingEgressHub:
    def test_no_subscribers(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        assert not hub.has_subscribers("session1")

    def test_subscribe_unsubscribe(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        writer = MagicMock()
        hub.subscribe("session1", writer, area_id="living_room")
        assert hub.has_subscribers("session1")
        assert "living_room" in hub.subscriber_areas("session1")

        hub.unsubscribe("session1", writer)
        assert not hub.has_subscribers("session1")

    @pytest.mark.asyncio
    async def test_publish_begin_frame(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.write = MagicMock()
        hub.subscribe("session1", writer, area_id="living_room")

        await hub.publish("session1", {"type": "begin", "sample_rate": 24000})
        # Should have written an audio-start frame
        assert writer.write.called

    @pytest.mark.asyncio
    async def test_publish_end_frame(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.write = MagicMock()
        hub.subscribe("session1", writer, area_id="living_room")

        await hub.publish("session1", {"type": "end"})
        assert writer.write.called

    @pytest.mark.asyncio
    async def test_publish_pcm_bytes(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.write = MagicMock()
        hub.subscribe("session1", writer, area_id="living_room")

        await hub.publish("session1", b"\x00\x00" * 100)
        assert writer.write.called

    @pytest.mark.asyncio
    async def test_publish_to_no_subscribers_is_noop(self):
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        # Should not raise
        await hub.publish("nobody", b"\x00\x00" * 100)
        await hub.publish("nobody", {"type": "begin", "sample_rate": 24000})

    @pytest.mark.asyncio
    async def test_sample_rate_stored_from_begin_frame(self):
        """The sample rate from the begin frame is stored and reused
        for audio-chunk frames (Kokoro is 24000, not 22050)."""
        from halbert_core.audio.egress.wyoming_egress import WyomingEgressHub
        hub = WyomingEgressHub()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.write = MagicMock()
        hub.subscribe("session1", writer, area_id="living_room")

        # Send a begin frame with Kokoro's 24000 Hz
        await hub.publish("session1", {"type": "begin", "sample_rate": 24000})
        assert hub._sample_rates["session1"] == 24000

        # Send PCM — the audio-chunk frame should carry 24000, not 22050
        writer.write.reset_mock()
        await hub.publish("session1", b"\x00\x00" * 100)
        # write_wyoming_frame writes the JSON header first, then the
        # binary payload. The header is the first write call.
        header_bytes = writer.write.call_args_list[0][0][0]
        assert b'"rate": 24000' in header_bytes or b'"rate":24000' in header_bytes


# ---------------------------------------------------------------------------
# KokoroTTS style resolution
# ---------------------------------------------------------------------------

class TestKokoroStyleResolution:
    def test_resolve_known_style(self):
        from halbert_core.audio.speech.tts_engine import KokoroTTS
        tts = KokoroTTS()
        assert tts.resolve_style("calm") == 0
        assert tts.resolve_style("urgent") == 1
        assert tts.resolve_style("playful") == 2

    def test_resolve_unknown_style_returns_none(self):
        from halbert_core.audio.speech.tts_engine import KokoroTTS
        tts = KokoroTTS()
        assert tts.resolve_style("nonexistent") is None

    def test_resolve_none_style_returns_none(self):
        from halbert_core.audio.speech.tts_engine import KokoroTTS
        tts = KokoroTTS()
        assert tts.resolve_style(None) is None
        assert tts.resolve_style("") is None

    def test_custom_style_map(self):
        from halbert_core.audio.speech.tts_engine import KokoroTTS
        tts = KokoroTTS(style_map={"custom": 5})
        assert tts.resolve_style("custom") == 5
        # Default map is overridden, not merged
        assert tts.resolve_style("calm") is None
