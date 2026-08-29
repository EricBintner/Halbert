# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Apple Intelligence platform detection utilities."""
from unittest.mock import patch, MagicMock

import pytest

from halbert_core.utils.platform import (
    detect_metal_gpu,
    get_macos_version,
    apple_intelligence_eligible,
    is_mac_apple_silicon,
    get_unified_memory_gb,
)


class TestGetMacOSVersion:
    def test_returns_none_on_non_mac(self):
        with patch("halbert_core.utils.platform.is_macos", return_value=False):
            assert get_macos_version() is None

    def test_returns_tuple_on_mac(self):
        with patch("halbert_core.utils.platform.is_macos", return_value=True), \
             patch("halbert_core.utils.platform.platform.mac_ver", return_value=("15.1", "", "")):
            assert get_macos_version() == (15, 1)

    def test_handles_minor_zero(self):
        with patch("halbert_core.utils.platform.is_macos", return_value=True), \
             patch("halbert_core.utils.platform.platform.mac_ver", return_value=("15.0", "", "")):
            assert get_macos_version() == (15, 0)


class TestDetectMetalGPU:
    def test_returns_none_on_non_mac(self):
        with patch("halbert_core.utils.platform.is_macos", return_value=False):
            assert detect_metal_gpu() is None

    def test_detects_metal_from_mtlgpufamilysupport(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"SPDisplaysDataType": [{"spdisplays_mtlgpufamilysupport": "spdisplays_metal4", "sppci_model": "Apple M1 Ultra"}]}'
        with patch("halbert_core.utils.platform.is_macos", return_value=True), \
             patch("halbert_core.utils.platform.subprocess.run", return_value=mock_result):
            gpu = detect_metal_gpu()
            assert gpu is not None
            assert gpu["metal_version"] == "spdisplays_metal4"
            assert gpu["gpu_name"] == "Apple M1 Ultra"

    def test_returns_none_when_no_metal(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"SPDisplaysDataType": [{"sppci_model": "Intel Iris"}]}'
        with patch("halbert_core.utils.platform.is_macos", return_value=True), \
             patch("halbert_core.utils.platform.subprocess.run", return_value=mock_result):
            assert detect_metal_gpu() is None

    def test_returns_none_on_command_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("halbert_core.utils.platform.is_macos", return_value=True), \
             patch("halbert_core.utils.platform.subprocess.run", return_value=mock_result):
            assert detect_metal_gpu() is None


class TestAppleIntelligenceEligible:
    def test_false_on_non_apple_silicon(self):
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=False):
            assert apple_intelligence_eligible() is False

    def test_false_on_old_macos(self):
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(14, 0)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=32), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal3", "gpu_name": "M1"}):
            assert apple_intelligence_eligible() is False

    def test_false_on_macos_15_0(self):
        """Apple Intelligence first shipped in 15.1, not 15.0."""
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 0)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=32), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal4", "gpu_name": "M1"}):
            assert apple_intelligence_eligible() is False

    def test_true_on_macos_15_1(self):
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 1)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=32), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal4", "gpu_name": "M1"}):
            assert apple_intelligence_eligible() is True

    def test_false_on_insufficient_ram(self):
        """8GB is below Halbert's 16GB floor."""
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 1)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=8), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal4", "gpu_name": "M1"}):
            assert apple_intelligence_eligible() is False

    def test_true_on_16gb_boundary(self):
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 1)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=16), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal4", "gpu_name": "M1"}):
            assert apple_intelligence_eligible() is True

    def test_false_without_metal(self):
        """Defensive against arm64 VMs without Metal."""
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 1)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=32), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value=None):
            assert apple_intelligence_eligible() is False

    def test_custom_min_ram(self):
        """Caller can lower the RAM floor for testing."""
        with patch("halbert_core.utils.platform.is_mac_apple_silicon", return_value=True), \
             patch("halbert_core.utils.platform.get_macos_version", return_value=(15, 1)), \
             patch("halbert_core.utils.platform.get_unified_memory_gb", return_value=8), \
             patch("halbert_core.utils.platform.detect_metal_gpu", return_value={"metal_version": "metal4", "gpu_name": "M1"}):
            assert apple_intelligence_eligible(min_ram_gb=8) is True
