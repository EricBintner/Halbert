# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Phase 28/29 Integration Tests - Self-RAG and CRAG

Tests for:
- SelfReflector functionality
- CRAG decision flow
- Edge cases and optimization
- Integration with chat pipeline
"""

import pytest
import time
from unittest.mock import MagicMock, patch


class TestSelfReflector:
    """Test Self-RAG reflection functionality."""
    
    def test_import_self_reflector(self):
        """Ensure SelfReflector can be imported."""
        from halbert_core.knowledge import SelfReflector
        assert SelfReflector is not None
    
    def test_reflection_tokens_enum(self):
        """Test ReflectionToken enum values."""
        from halbert_core.knowledge.reflection import ReflectionToken
        
        assert ReflectionToken.RETRIEVE_YES.value == "[Retrieve:Yes]"
        assert ReflectionToken.RETRIEVE_NO.value == "[Retrieve:No]"
        assert ReflectionToken.IS_REL_YES.value == "[IsRel:Yes]"
        assert ReflectionToken.IS_REL_PARTIAL.value == "[IsRel:Partial]"
        assert ReflectionToken.IS_REL_NO.value == "[IsRel:No]"
    
    def test_crag_action_enum(self):
        """Test CRAGAction enum values."""
        from halbert_core.knowledge.reflection import CRAGAction
        
        assert CRAGAction.CORRECT.value == "correct"
        assert CRAGAction.INCORRECT.value == "incorrect"
        assert CRAGAction.AMBIGUOUS.value == "ambiguous"
    
    def test_reflection_result_dataclass(self):
        """Test ReflectionResult structure."""
        from halbert_core.knowledge.reflection import (
            ReflectionResult, RetrievalDecision, ConfidenceLevel, CRAGAction
        )
        
        result = ReflectionResult(
            query="test query",
            decision=RetrievalDecision.SUFFICIENT,
            confidence=ConfidenceLevel.HIGH,
            retrieved_contexts=[],
            reasoning="test reasoning",
            crag_action=CRAGAction.CORRECT,
        )
        
        assert result.query == "test query"
        assert result.decision == RetrievalDecision.SUFFICIENT
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.crag_action == CRAGAction.CORRECT


class TestCRAGDecisionFlow:
    """Test CRAG corrective decision flow."""
    
    def test_crag_scoring_formula(self):
        """Test CRAG scoring: 0.6*relevance + 0.3*quality + 0.1*freshness."""
        from halbert_core.knowledge.reflection import RetrievedContext
        
        # Mock a retrieved context
        mock_entry = MagicMock()
        mock_entry.type.value = "hardware"
        mock_entry.subject = "CPU"
        mock_entry.content = "Intel i7"
        
        ctx = RetrievedContext(
            entry=mock_entry,
            relevance_score=0.8,
            freshness_score=0.9,
            source_reliability=0.7,
        )
        
        # Combined score = 0.6*0.8 + 0.3*0.7 + 0.1*0.9 = 0.48 + 0.21 + 0.09 = 0.78
        expected = 0.6 * 0.8 + 0.3 * 0.7 + 0.1 * 0.9
        assert abs(ctx.combined_score - expected) < 0.001



class TestIntentClassification:
    """Test query intent classification."""
    
    def test_hardware_keywords(self):
        """Test hardware intent detection."""
        from halbert_core.knowledge import SelfReflector
        
        reflector = SelfReflector()
        
        assert reflector._classify_intent("what is my cpu") == "hardware"
        assert reflector._classify_intent("how much memory") == "hardware"
        assert reflector._classify_intent("disk usage") == "hardware"
    
    def test_identity_keywords(self):
        """Test identity intent detection."""
        from halbert_core.knowledge import SelfReflector
        
        reflector = SelfReflector()
        
        assert reflector._classify_intent("who are you") == "identity"
        assert reflector._classify_intent("what is halbert") == "identity"
    
    def test_config_keywords(self):
        """Test config intent detection."""
        from halbert_core.knowledge import SelfReflector
        
        reflector = SelfReflector()
        
        assert reflector._classify_intent("why is this configured") == "config"
        assert reflector._classify_intent("rationale for setting") == "config"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
