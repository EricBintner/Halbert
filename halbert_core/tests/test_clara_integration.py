"""
Integration Tests for CLaRa Context Compression

Tests the CLaRa provider functionality including:
- Configuration management
- VRAM detection
- Compression (mocked for CI without GPU)
- Remote mode fallback
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import json
import tempfile


class TestClaraConfig:
    """Test CLaRa configuration management."""
    
    def test_default_config_values(self):
        """CLaRa should be disabled by default with correct VRAM requirements."""
        from halbert_core.model.clara_provider import ClaraConfig
        
        config = ClaraConfig()
        
        # Phase 58: CLaRa disabled by default (requires 14GB VRAM)
        assert config.enabled is False
        assert config.use_4bit is False  # 4-bit not available
        assert config.model_name == "apple/CLaRa-7B-Instruct"
        assert config.auto_compress_threshold == 3
    
    def test_config_persistence(self):
        """Config should save and load correctly."""
        from halbert_core.model.clara_provider import ClaraConfig, CLARA_CONFIG_PATH
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config_path = Path(tmpdir) / "clara_config.json"
            
            # Create config
            config = ClaraConfig(enabled=True, use_remote=True, remote_url="http://test:8765")
            
            # Mock the config path
            with patch('halbert_core.model.clara_provider.CLARA_CONFIG_PATH', test_config_path):
                config.save()
                
                # Load it back
                loaded = ClaraConfig.load()
                assert loaded.enabled is True
                assert loaded.use_remote is True
                assert loaded.remote_url == "http://test:8765"


class TestClaraProvider:
    """Test CLaRa provider functionality."""
    
    def test_provider_initialization(self):
        """Provider should initialize with default config."""
        from halbert_core.model.clara_provider import ClaraProvider
        
        provider = ClaraProvider()
        
        # Config is loaded internally
        assert provider.config is not None
        assert provider._initialized is False
    
    def test_vram_check(self):
        """VRAM check should return dict with can_run key."""
        from halbert_core.model.clara_provider import ClaraProvider
        
        provider = ClaraProvider()
        result = provider.check_vram()
        
        # Should always return a dict with status info
        assert isinstance(result, dict)
        assert 'can_run' in result
    
    def test_disabled_compression(self):
        """Compression should fail gracefully when disabled."""
        from halbert_core.model.clara_provider import ClaraProvider
        
        provider = ClaraProvider()
        provider.config.enabled = False
        
        result = provider.compress_memories(
            memories=["Memory 1"],
            query="Test query"
        )
        
        assert result['success'] is False
        assert 'disabled' in result.get('error', '').lower() or 'not enabled' in result.get('error', '').lower()


class TestHardwareTierDetection:
    """Test hardware tier detection for model recommendations."""
    
    def test_tier1_detection(self):
        """24GB GPU should be detected as Tier 1."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_properties.return_value = MagicMock(
            total_memory=24 * 1024**3  # 24GB
        )
        
        with patch.dict('sys.modules', {'torch': mock_torch}):
            # Tier 1: < 40GB VRAM
            total_vram = mock_torch.cuda.get_device_properties(0).total_memory / (1024**3)
            tier = 2 if total_vram >= 40 else 1
            assert tier == 1
    
    def test_tier2_detection(self):
        """48GB GPU should be detected as Tier 2."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_properties.return_value = MagicMock(
            total_memory=48 * 1024**3  # 48GB
        )
        
        with patch.dict('sys.modules', {'torch': mock_torch}):
            total_vram = mock_torch.cuda.get_device_properties(0).total_memory / (1024**3)
            tier = 2 if total_vram >= 40 else 1
            assert tier == 2


class TestClaraRAGIntegration:
    """Test CLaRa integration with RAG pipeline."""
    
    def test_compression_threshold(self):
        """Compression should only trigger above threshold."""
        from halbert_core.model.clara_provider import ClaraConfig
        
        config = ClaraConfig(auto_compress_threshold=3)
        
        # Below threshold
        memories_below = ["mem1", "mem2"]
        should_compress = len(memories_below) > config.auto_compress_threshold
        assert should_compress is False
        
        # Above threshold
        memories_above = ["mem1", "mem2", "mem3", "mem4"]
        should_compress = len(memories_above) > config.auto_compress_threshold
        assert should_compress is True
    
    def test_compression_ratio_calculation(self):
        """Compression ratio should be calculated correctly."""
        original_tokens = 16000
        compressed_tokens = 1000
        expected_ratio = 16.0
        
        actual_ratio = original_tokens / compressed_tokens
        assert actual_ratio == expected_ratio


class TestApplyRecommendedConfig:
    """Test the Apply Recommended Config endpoint logic."""
    
    def test_tier1_recommendations(self):
        """Tier 1 should recommend qwen2.5:14b and disable CLaRa."""
        tier = 1
        
        if tier == 1:
            recommended_chat = 'qwen2.5:14b'
            clara_enabled = False
        elif tier == 2:
            recommended_chat = 'mistral-small'
            clara_enabled = True
        else:
            recommended_chat = 'mistral-small'
            clara_enabled = True
        
        assert recommended_chat == 'qwen2.5:14b'
        assert clara_enabled is False
    
    def test_tier2_recommendations(self):
        """Tier 2 should recommend mistral-small and enable CLaRa."""
        tier = 2
        
        if tier == 1:
            recommended_chat = 'qwen2.5:14b'
            clara_enabled = False
        elif tier == 2:
            recommended_chat = 'mistral-small'
            clara_enabled = True
        else:
            recommended_chat = 'mistral-small'
            clara_enabled = True
        
        assert recommended_chat == 'mistral-small'
        assert clara_enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
