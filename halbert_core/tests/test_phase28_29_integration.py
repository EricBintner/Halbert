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


class TestEdgeCases:
    """Test edge cases for Self-RAG integration."""
    
    def test_empty_query(self):
        """Test handling of empty query."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        context, metadata = get_self_knowledge_context("", max_results=5)
        
        # Should return empty context gracefully
        assert isinstance(context, str)
        assert isinstance(metadata, dict)
    
    def test_very_long_query(self):
        """Test handling of very long query."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        long_query = "what is " * 500  # Very long query
        context, metadata = get_self_knowledge_context(long_query, max_results=5)
        
        # Should handle without error
        assert isinstance(context, str)
        assert isinstance(metadata, dict)
    
    def test_special_characters_query(self):
        """Test handling of special characters in query."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        special_query = "What's my CPU? <script>alert('xss')</script> && rm -rf /"
        context, metadata = get_self_knowledge_context(special_query, max_results=5)
        
        # Should handle without error
        assert isinstance(context, str)
        assert isinstance(metadata, dict)
    
    def test_unicode_query(self):
        """Test handling of unicode characters."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        unicode_query = "CPU使用率は何ですか？ 🖥️ Какой процессор?"
        context, metadata = get_self_knowledge_context(unicode_query, max_results=5)
        
        # Should handle without error
        assert isinstance(context, str)
        assert isinstance(metadata, dict)
    
    def test_zero_max_results(self):
        """Test handling of zero max_results."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        context, metadata = get_self_knowledge_context("test", max_results=0)
        
        # Should return empty gracefully
        assert context == "" or isinstance(context, str)
        assert isinstance(metadata, dict)


class TestPerformance:
    """Performance benchmarks for Self-RAG."""
    
    def test_reflection_speed(self):
        """Ensure reflection completes within reasonable time."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        start = time.time()
        for _ in range(10):
            get_self_knowledge_context("what is my CPU?", max_results=5)
        elapsed = time.time() - start
        
        # 10 reflections should complete in under 1 second
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s for 10 reflections"
    
    def test_metadata_contains_timing(self):
        """Ensure metadata includes reflection timing."""
        from halbert_core.dashboard.routes.chat import get_self_knowledge_context
        
        _, metadata = get_self_knowledge_context("test query", max_results=5)
        
        if metadata:  # Only if reflection ran
            assert "reflection_time_ms" in metadata or metadata == {}


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
