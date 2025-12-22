# Recommended Models for Halbert

Based on testing, these models work best with Halbert's prompt system.

## Tier: Guide (Quick Responses)

| Model | Size | Quality | System Prompt | Notes |
|-------|------|---------|---------------|-------|
| **qwen3:14b** | 14B | ⭐⭐⭐⭐ | ✅ Yes | **Currently tested** - good reasoning |
| qwen2.5:14b | 14B | ⭐⭐⭐⭐ | ✅ Yes | Good balance of speed and instruction following |
| llama3.1:8b | 8B | ⭐⭐ | ✅ Yes | Fast but hallucinates examples, verbose |

**Recommended**: `qwen3:14b` (tested)

## Tier: Specialist (Complex Analysis)

| Model | Size | Quality | System Prompt | Notes |
|-------|------|---------|---------------|-------|
| **deepseek-r1:32b** | 32B | ⭐⭐⭐⭐⭐ | ❌ Injected | **Currently tested** - excellent reasoning |
| **qwen3-next:80b** | 80B (3B active) | ⭐⭐⭐⭐⭐ | ✅ Yes | Future option - outperforms Gemini-2.5-Flash |
| qwen3:32b | 32B | ⭐⭐⭐⭐ | ✅ Yes | Good analysis, fast |

**Recommended**: `deepseek-r1:32b` (tested) or `qwen3-next:80b` (future)

## Tier: Vision (Image Analysis)

| Model | Size | Quality | System Prompt | Notes |
|-------|------|---------|---------------|-------|
| **qwen3-v1:32b** | 32B | ⭐⭐⭐⭐ | ✅ Yes | **Currently tested** - good multimodal |
| qwen2-vl:32b | 32B | ⭐⭐⭐⭐⭐ | ✅ Yes | Best vision understanding |

**Recommended**: `qwen3-v1:32b` (tested)

## System Prompt Handling

**Key Finding**: Not all models want system prompts!

| Model Family | System Prompt? | How Halbert Handles It |
|--------------|----------------|------------------------|
| Qwen3 | ✅ Yes | Standard system message |
| Qwen3-Next | ✅ Yes | Standard system message |
| **DeepSeek-R1** | ❌ NO | **Injects into user message** |
| Llama 3.x | ✅ Yes | Standard system message |
| Mistral | ⚠️ Limited | Standard (may ignore) |

### DeepSeek-R1 Special Handling
Per [official recommendation](https://huggingface.co/deepseek-ai/DeepSeek-R1):
> "Avoid adding a system prompt; all instructions should be contained within the user prompt."

Halbert automatically detects `deepseek-r1` models and injects the system prompt into the user message instead.

## Known Issues by Model

### llama3.1:8b
- ❌ Hallucinates "example output" in code blocks
- ❌ Verbose preambles ("Let me think...")
- ❌ Ignores one-command-at-a-time rule
- ✅ Fast response time

### qwen3:14b  
- ⚠️ Sometimes batches multiple commands
- ✅ Good instruction following
- ✅ Accurate Linux knowledge

### deepseek-r1:32b
- ✅ Excellent reasoning
- ✅ Follows constraints well
- ⚠️ Thinking blocks need special handling (auto-parsed)
- ⚠️ Slower response time
- ⚠️ No system prompt (handled automatically)

## Installation

```bash
# Current tested setup
ollama pull qwen3:14b        # Guide
ollama pull deepseek-r1:32b  # Specialist (on Mac Studio)
ollama pull qwen3-v1:32b     # Vision (on Mac Studio)

# Future specialist option
ollama pull qwen3-next:80b   # When available
```
