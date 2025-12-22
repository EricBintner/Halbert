# Halbert Prompt System v2

**Status**: Phase 40 Implementation  
**Created**: December 2024

## Overview

This directory contains the new structured prompt system for Halbert, based on Phase 39 research into competitor prompt architectures.

## Directory Structure

```
v2/
├── base/                    # Core prompt components
│   ├── identity.xml         # Who Halbert is
│   ├── objectives.xml       # What Halbert aims to do
│   ├── constraints.xml      # Behavioral rules
│   ├── output-format.xml    # Response formatting
│   └── safety.xml           # 5-layer safety architecture
├── tiers/                   # Model tier-specific additions
│   ├── guide.xml            # Fast/simple model
│   ├── specialist.xml       # Reasoning model
│   └── vision.xml           # Vision-capable model
├── templates/               # Dynamic injection templates
│   ├── system_context.xml   # Runtime system state
│   ├── user_prefs.xml       # User preferences
│   └── rag_results.xml      # RAG retrieval results
└── tools/                   # Tool definitions (Phase 41)
    └── (to be implemented)
```

## Architecture

### 7-Layer Prompt Structure

1. **Identity** - Role, expertise, priorities
2. **Objectives** - Goals and success criteria
3. **Constraints** - Critical/Important/Preferred rules
4. **Dynamic Context** - Runtime system/user/project info
5. **Tools** - Available tool definitions
6. **Output Format** - Response structure rules
7. **Safety** - 5-layer protection architecture

### Safety Layers

1. **Role** - Fundamental identity constraints
2. **Actions** - Prohibited operations
3. **Output** - What can appear in responses
4. **Tools** - Permission levels per tool
5. **Runtime** - Pre-execution validation

## Usage

```python
from halbert_core.prompts import PromptLoader, PromptBuilder

loader = PromptLoader(Path("config/prompts"))
builder = PromptBuilder(loader)

# Build prompt for specialist tier
prompt = builder.build_prompt(
    tier="specialist",
    system_context=context_injector.get_system_context(),
    user_prefs={"verbosity": "concise"},
    project_context=halbert_md_content,
    rag_results=retrieval_results,
)
```

## Token Budget

| Component | Est. Tokens |
|-----------|-------------|
| Base (5 files) | ~1,200 |
| Tools (10) | ~800 |
| Tier additions | ~200 |
| Dynamic context | ~500 |
| **Total** | ~2,700 |

Compared to legacy `base-safety.txt`: ~200 tokens (13x increase)

## Migration

The legacy `base-safety.txt` remains for fallback. New code should use the v2 system via `PromptBuilder`.

## Recommended Models

See [models/README.md](models/README.md) for tested model recommendations.

**Quick Setup:**
```bash
ollama pull qwen2.5:14b      # Guide tier
ollama pull deepseek-r1:32b  # Specialist tier  
ollama pull qwen2-vl:32b     # Vision tier
```

### Model-Specific Overrides

For models that need different constraint styles:
- `models/small-model-overrides.xml` - Stronger rules for 7B-14B models
- `models/reasoning-model-overrides.xml` - Thinking block handling for deepseek-r1, qwq

## See Also

- [Phase 36: System Prompt Research](../../docs/Phase36_system-prompt-research/research.md)
- [Phase 39: Prompt Design](../../docs/Phase39-Prompt-Design/README.md)
- [Phase 40: Prompt Infrastructure](../../docs/Phase40_Prompt-Infrastructure/README.md)
