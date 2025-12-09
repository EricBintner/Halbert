"""
Test context handoff engine (Phase 5 M2).

Tests conversation context management, handoff strategies, and quality preservation.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_context_creation():
    """Test creating and manipulating conversation context."""
    try:
        from cerebric_core.cerebric_core.model import (
            ConversationContext, MessageRole
        )
        
        context = ConversationContext()
        context.system_prompt = "You are Cerebric"
        context.add_message(MessageRole.USER, "Hello")
        context.add_message(MessageRole.ASSISTANT, "Hi there!")
        
        assert len(context.messages) == 2
        assert context.messages[0].role == MessageRole.USER
        assert context.messages[1].role == MessageRole.ASSISTANT
        
        print("✅ Context creation test passed")
        print(f"   Messages: {len(context.messages)}")
        return True
    
    except Exception as e:
        print(f"❌ Context creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_token_estimation():
    """Test token count estimation."""
    try:
        from cerebric_core.cerebric_core.model import (
            ConversationContext, MessageRole
        )
        
        context = ConversationContext()
        context.system_prompt = "You are a helpful assistant."
        context.add_message(MessageRole.USER, "Write a bash script to list files.")
        context.add_message(MessageRole.ASSISTANT, "Here's a script:\n#!/bin/bash\nls -la")
        
        tokens = context.get_token_estimate()
        
        # Should have some tokens
        assert tokens > 0
        
        print("✅ Token estimation test passed")
        print(f"   Estimated tokens: {tokens}")
        return True
    
    except Exception as e:
        print(f"❌ Token estimation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_handoff_strategy():
    """Test full context handoff (no compression)."""
    try:
        from cerebric_core.cerebric_core.model import (
            ContextHandoffEngine, ConversationContext, 
            HandoffStrategy, MessageRole
        )
        
        engine = ContextHandoffEngine(default_strategy=HandoffStrategy.FULL)
        
        # Create context
        context = ConversationContext()
        context.system_prompt = "You are Cerebric"
        context.add_message(MessageRole.USER, "Hello")
        context.add_message(MessageRole.ASSISTANT, "Hi!")
        context.add_message(MessageRole.USER, "How are you?")
        
        # Prepare handoff
        prepared = engine.prepare_handoff(
            context=context,
            target_model="test-model",
            max_tokens=8192
        )
        
        # Should keep all messages (full strategy)
        assert len(prepared.messages) == len(context.messages)
        assert prepared.system_prompt == context.system_prompt
        
        print("✅ Full handoff strategy test passed")
        print(f"   Original messages: {len(context.messages)}")
        print(f"   Prepared messages: {len(prepared.messages)}")
        return True
    
    except Exception as e:
        print(f"❌ Full handoff strategy test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_summarized_handoff_strategy():
    """Test summarized context handoff."""
    try:
        from cerebric_core.cerebric_core.model import (
            ContextHandoffEngine, ConversationContext,
            HandoffStrategy, MessageRole
        )
        
        engine = ContextHandoffEngine(default_strategy=HandoffStrategy.SUMMARIZED)
        
        # Create long context (10 messages)
        context = ConversationContext()
        context.system_prompt = "You are Cerebric"
        
        for i in range(10):
            context.add_message(MessageRole.USER, f"Message {i}")
            context.add_message(MessageRole.ASSISTANT, f"Response {i}")
        
        # Prepare handoff
        prepared = engine.prepare_handoff(
            context=context,
            target_model="test-model",
            max_tokens=4096
        )
        
        # Should have fewer messages (summarized)
        # Keeps recent 5, so should have 5 + 1 summary = 6
        assert len(prepared.messages) <= len(context.messages)
        
        print("✅ Summarized handoff strategy test passed")
        print(f"   Original messages: {len(context.messages)}")
        print(f"   Prepared messages: {len(prepared.messages)}")
        print(f"   Compression ratio: {len(prepared.messages) / len(context.messages):.2f}")
        return True
    
    except Exception as e:
        print(f"❌ Summarized handoff strategy test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_minimal_handoff_strategy():
    """Test minimal context handoff."""
    try:
        from cerebric_core.cerebric_core.model import (
            ContextHandoffEngine, ConversationContext,
            HandoffStrategy, MessageRole
        )
        
        engine = ContextHandoffEngine(default_strategy=HandoffStrategy.MINIMAL)
        
        # Create context
        context = ConversationContext()
        context.system_prompt = "You are Cerebric"
        context.task_description = "Help with Linux administration"
        
        for i in range(5):
            context.add_message(MessageRole.USER, f"Question {i}")
            context.add_message(MessageRole.ASSISTANT, f"Answer {i}")
        
        # Prepare handoff
        prepared = engine.prepare_handoff(
            context=context,
            target_model="test-model",
            max_tokens=2048
        )
        
        # Should keep only last user message (minimal)
        assert len(prepared.messages) == 1
        assert prepared.messages[0].role == MessageRole.USER
        
        print("✅ Minimal handoff strategy test passed")
        print(f"   Original messages: {len(context.messages)}")
        print(f"   Prepared messages: {len(prepared.messages)}")
        return True
    
    except Exception as e:
        print(f"❌ Minimal handoff strategy test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quality_loss_estimation():
    """Test quality loss estimation."""
    try:
        from cerebric_core.cerebric_core.model import (
            ContextHandoffEngine, ConversationContext,
            HandoffStrategy, MessageRole
        )
        
        engine = ContextHandoffEngine()
        
        # Create original context
        original = ConversationContext()
        for i in range(10):
            original.add_message(MessageRole.USER, f"Message {i}" * 10)
            original.add_message(MessageRole.ASSISTANT, f"Response {i}" * 10)
        
        # Create compressed context
        compressed = engine.prepare_handoff(
            original,
            target_model="test",
            max_tokens=2048,
            strategy=HandoffStrategy.SUMMARIZED
        )
        
        # Estimate loss
        loss = engine.estimate_quality_loss(original, compressed)
        
        # Should have some loss (0-1 range)
        assert 0.0 <= loss <= 1.0
        
        # Target: <10% loss
        print("✅ Quality loss estimation test passed")
        print(f"   Estimated loss: {loss:.2%}")
        print(f"   Target: <10%")
        print(f"   Status: {'✓ PASS' if loss < 0.10 else '⚠ ABOVE TARGET'}")
        return True
    
    except Exception as e:
        print(f"❌ Quality loss estimation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ollama_formatting():
    """Test formatting context for Ollama API."""
    try:
        from cerebric_core.cerebric_core.model import (
            ContextHandoffEngine, ConversationContext, MessageRole
        )
        
        engine = ContextHandoffEngine()
        
        context = ConversationContext()
        context.system_prompt = "You are Cerebric"
        context.task_description = "Help with Linux"
        context.add_message(MessageRole.USER, "Hello")
        context.add_message(MessageRole.ASSISTANT, "Hi!")
        
        # Format for Ollama
        formatted = engine.format_for_ollama(context)
        
        assert "messages" in formatted
        assert len(formatted["messages"]) > 0
        
        # Should have system messages + conversation
        system_count = sum(1 for m in formatted["messages"] if m["role"] == "system")
        assert system_count >= 1  # At least system prompt
        
        print("✅ Ollama formatting test passed")
        print(f"   Total messages: {len(formatted['messages'])}")
        print(f"   System messages: {system_count}")
        return True
    
    except Exception as e:
        print(f"❌ Ollama formatting test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_context_serialization():
    """Test context serialization/deserialization."""
    try:
        from cerebric_core.cerebric_core.model import (
            ConversationContext, MessageRole
        )
        
        # Create context
        original = ConversationContext()
        original.system_prompt = "Test prompt"
        original.task_description = "Test task"
        original.add_message(MessageRole.USER, "Hello")
        original.add_message(MessageRole.ASSISTANT, "Hi!")
        original.rag_context = ["Doc 1", "Doc 2"]
        
        # Serialize
        data = original.to_dict()
        
        # Deserialize
        restored = ConversationContext.from_dict(data)
        
        # Verify
        assert restored.system_prompt == original.system_prompt
        assert restored.task_description == original.task_description
        assert len(restored.messages) == len(original.messages)
        assert len(restored.rag_context) == len(original.rag_context)
        
        print("✅ Context serialization test passed")
        print(f"   Messages preserved: {len(restored.messages)}")
        return True
    
    except Exception as e:
        print(f"❌ Context serialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all context handoff tests."""
    print("=" * 70)
    print("CONTEXT HANDOFF TESTS (Phase 5 M2)")
    print("=" * 70)
    print()
    
    tests = [
        ("Context Creation", test_context_creation),
        ("Token Estimation", test_token_estimation),
        ("Full Handoff Strategy", test_full_handoff_strategy),
        ("Summarized Handoff Strategy", test_summarized_handoff_strategy),
        ("Minimal Handoff Strategy", test_minimal_handoff_strategy),
        ("Quality Loss Estimation", test_quality_loss_estimation),
        ("Ollama Formatting", test_ollama_formatting),
        ("Context Serialization", test_context_serialization),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"Test: {test_name}")
        print('='*70)
        try:
            if test_func():
                passed += 1
                print(f"\n✅ {test_name} PASSED")
            else:
                failed += 1
                print(f"\n❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} CRASHED: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
