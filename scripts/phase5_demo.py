#!/usr/bin/env python3
"""
Cerebric Phase 5 Demo Script

Demonstrates all Phase 5 features:
1. Multi-model routing
2. Context handoff
3. Hardware detection
4. LoRA personas (Mac)
5. Performance monitoring
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def demo_basic_routing():
    """Demo 1: Basic multi-model routing"""
    print("\n" + "="*70)
    print("DEMO 1: Basic Multi-Model Routing")
    print("="*70)
    
    try:
        from cerebric_core.cerebric_core.model import ModelRouter, TaskType
        
        router = ModelRouter()
        
        # Chat task (uses orchestrator)
        print("\n🗨️  Chat task (orchestrator):")
        response = router.generate(
            "What is Linux?",
            task_type=TaskType.CHAT
        )
        print(f"Model: {response.model_id}")
        print(f"Response: {response.text[:100]}...")
        print(f"Latency: {response.latency_ms}ms")
        
        # Code task (tries specialist if available)
        print("\n💻 Code task (specialist if available):")
        response = router.generate(
            "Write a bash script to check disk space",
            task_type=TaskType.CODE_GENERATION,
            prefer_specialist=True
        )
        print(f"Model: {response.model_id}")
        print(f"Response: {response.text[:100]}...")
        
        print("\n✅ Demo 1 complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Demo 1 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_context_handoff():
    """Demo 2: Context-aware conversation"""
    print("\n" + "="*70)
    print("DEMO 2: Context Handoff & Multi-Turn Conversation")
    print("="*70)
    
    try:
        from cerebric_core.cerebric_core.model import ModelRouter, TaskType
        
        router = ModelRouter()
        
        # Turn 1
        print("\n👤 User: I have a server issue")
        response1, context1 = router.generate_with_context(
            "I have a server issue",
            task_type=TaskType.CHAT
        )
        print(f"🤖 Assistant: {response1.text[:100]}...")
        
        # Turn 2 - context preserved
        print("\n👤 User: It's running slow")
        response2, context2 = router.generate_with_context(
            "It's running slow",
            context=context1,
            task_type=TaskType.SYSTEM_COMMAND
        )
        print(f"🤖 Assistant: {response2.text[:100]}...")
        
        # Turn 3 - might switch to specialist
        print("\n👤 User: Write a monitoring script")
        response3, context3 = router.generate_with_context(
            "Write a monitoring script",
            context=context2,
            task_type=TaskType.CODE_GENERATION,
            prefer_specialist=True
        )
        print(f"🤖 Assistant: {response3.text[:100]}...")
        print(f"Model: {response3.model_id}")
        
        print(f"\n📊 Context stats:")
        print(f"  Messages: {len(context3.messages)}")
        print(f"  Total tokens: ~{sum(len(m.content.split()) for m in context3.messages)}")
        
        print("\n✅ Demo 2 complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Demo 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_hardware_detection():
    """Demo 3: Hardware detection and recommendations"""
    print("\n" + "="*70)
    print("DEMO 3: Hardware Detection & Model Recommendations")
    print("="*70)
    
    try:
        from cerebric_core.cerebric_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        
        print(f"\n🖥️  Hardware Detection:")
        print(f"  Platform: {hardware.platform_friendly}")
        print(f"  Profile: {hardware.profile.value}")
        print(f"  Total RAM: {hardware.total_ram_gb}GB")
        print(f"  Available RAM: {hardware.available_ram_gb:.1f}GB")
        print(f"  CPU Cores: {hardware.cpu_count}")
        
        if hardware.is_apple_silicon:
            print(f"  Apple Silicon: Yes ✅")
            print(f"  Unified Memory: {hardware.unified_memory_gb}GB")
        
        if hardware.has_nvidia_gpu:
            print(f"  NVIDIA GPU: Yes ✅")
        
        # Get recommendation
        recommendation = detector.recommend_models(hardware)
        
        print(f"\n💡 Recommended Configuration:")
        print(f"  Orchestrator: {recommendation.orchestrator_model}")
        print(f"  Provider: {recommendation.orchestrator_provider}")
        
        if recommendation.specialist_enabled:
            print(f"  Specialist: {recommendation.specialist_model}")
            print(f"  Provider: {recommendation.specialist_provider}")
        else:
            print(f"  Specialist: Disabled (orchestrator-only)")
        
        print(f"\n  Expected Memory: {recommendation.expected_memory_mb}MB")
        print(f"  Reasoning: {recommendation.reasoning}")
        
        print("\n✅ Demo 3 complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Demo 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_performance_monitoring():
    """Demo 4: Performance monitoring"""
    print("\n" + "="*70)
    print("DEMO 4: Performance Monitoring")
    print("="*70)
    
    try:
        from cerebric_core.cerebric_core.model import ModelRouter, TaskType
        
        router = ModelRouter()
        
        # Make some requests
        print("\n🔄 Making 10 test requests...")
        for i in range(10):
            response = router.generate(
                f"Test query {i}: Explain Linux",
                task_type=TaskType.CHAT
            )
            print(f"  Request {i+1}: {response.latency_ms}ms", end='\r')
        print("\n")
        
        # Check performance
        status = router.performance_monitor.get_status()
        
        print("📊 Performance Status:")
        for model_id, metrics in status["models"].items():
            print(f"\n  {model_id}:")
            print(f"    Performance: {metrics['performance_level']}")
            print(f"    Avg Latency: {metrics['avg_latency_ms']}ms")
            print(f"    P95 Latency: {metrics['p95_latency_ms']}ms")
            print(f"    Error Rate: {metrics['error_rate']:.1%}")
            print(f"    Total Requests: {metrics['total_requests']}")
        
        # Check for alerts
        alerts = router.performance_monitor.get_alerts()
        if alerts:
            print(f"\n⚠️  Alerts: {len(alerts)}")
            for alert in alerts[:3]:
                print(f"    {alert.severity.value}: {alert.message}")
        
        # Recommendations
        if status["recommendations"]:
            print(f"\n💡 Recommendations:")
            for rec in status["recommendations"][:3]:
                print(f"    {rec['model']}: {rec['message']}")
        
        print("\n✅ Demo 4 complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Demo 4 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_lora_info():
    """Demo 5: LoRA info (Mac only)"""
    print("\n" + "="*70)
    print("DEMO 5: LoRA Persona System (Mac Apple Silicon)")
    print("="*70)
    
    try:
        from cerebric_core.cerebric_core.model import PersonaTrainingDataGenerator
        import platform
        
        # Check platform
        if platform.system() != "Darwin":
            print("\n⚠️  LoRA training optimized for Mac Apple Silicon")
            print("   (Can use Ollama LoRAs on Linux)")
        else:
            print("\n🍎 Mac detected!")
            try:
                import mlx
                print("✅ MLX installed - ready for LoRA training!")
            except ImportError:
                print("⚠️  MLX not installed. Install: pip install mlx mlx-lm")
        
        # Show available persona templates
        generator = PersonaTrainingDataGenerator()
        personas = generator.list_available_personas()
        
        print(f"\n📋 Available Persona Templates ({len(personas)}):")
        for persona in personas:
            print(f"  • {persona}")
        
        print("\n💡 LoRA Training Workflow:")
        print("  1. Prepare data: cerebric mlx-prepare-training-data --persona friend")
        print("  2. Train LoRA: cerebric mlx-train-lora --persona friend --data friend.jsonl")
        print("  3. Load LoRA: cerebric mlx-load-lora --persona friend")
        print("  4. Hot-swap: <2s persona switching!")
        
        print("\n✅ Demo 5 complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Demo 5 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all demos"""
    print("\n" + "="*70)
    print("  Cerebric Phase 5: Multi-Model System Demo")
    print("="*70)
    
    demos = [
        ("Basic Multi-Model Routing", demo_basic_routing),
        ("Context Handoff & Conversation", demo_context_handoff),
        ("Hardware Detection & Recommendations", demo_hardware_detection),
        ("Performance Monitoring", demo_performance_monitoring),
        ("LoRA Persona System (Mac)", demo_lora_info),
    ]
    
    results = []
    
    for name, demo_func in demos:
        try:
            success = demo_func()
            results.append((name, success))
        except KeyboardInterrupt:
            print("\n\n⚠️  Demo interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Demo '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("  Demo Summary")
    print("="*70)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\nResults: {passed}/{total} demos passed")
    print("\n" + "="*70)
    
    print("\n📚 Learn More:")
    print("  • Integration Examples: docs/Phase5/INTEGRATION-EXAMPLES.md")
    print("  • API Reference: docs/Phase5/API-REFERENCE.md")
    print("  • Production Guide: docs/Phase5/PRODUCTION-GUIDE.md")
    print("")


if __name__ == "__main__":
    main()
