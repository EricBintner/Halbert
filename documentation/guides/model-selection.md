# Model Selection

Choosing and configuring LLMs for Cerebric.

---

## Model Roles

Cerebric uses up to three models for different tasks:

| Role | Purpose | Recommended |
|------|---------|-------------|
| **Guide** | Conversational assistant, quick responses | 8B model |
| **Specialist** | Complex reasoning, code, system analysis | 70B model |
| **Vision** | Screenshot/image analysis | Multimodal model |

---

## Recommended Models

### Best Performance (64 GB+ RAM or GPU offload)

```bash
# Specialist - best overall
ollama pull llama3.3:70b

# Guide - fast responses
ollama pull llama3.2:8b

# Vision - multimodal
ollama pull llama3.2-vision:90b
```

### Balanced (32 GB RAM)

```bash
# Specialist (quantized)
ollama pull llama3.3:70b-q4_0

# Guide
ollama pull llama3.2:8b

# Vision (smaller)
ollama pull llava:13b
```

### Minimum (16 GB RAM)

```bash
# Single model for both roles
ollama pull llama3.2:8b

# Vision
ollama pull llava:7b
```

> **⚠️ Caution**: 3B models (like `llama3.2:3b`) are not recommended for system administration tasks. They lack the reasoning capability needed for accurate Linux guidance and may produce unreliable advice.

---

## Configuration

Assign models in Settings → AI Models, or via config:

```yaml
# ~/.config/cerebric/model.yml

guide:
  endpoint: http://localhost:11434
  model: llama3.2:8b

specialist:
  endpoint: http://localhost:11434
  model: llama3.3:70b

vision:
  endpoint: http://localhost:11434
  model: llama3.2-vision:90b
```

---

## Quantization

Smaller models via quantization:

| Suffix | Bits | Size | Quality |
|--------|------|------|---------|
| (none) | 16 | Full | Best |
| -q8_0 | 8 | ~50% | Good |
| -q4_0 | 4 | ~25% | Acceptable |

```bash
ollama pull llama3.1:8b-q4_0
```

---

## Hardware Detection

```bash
python Cerebric/main.py hardware-detect --recommend
```

Shows:
- Available RAM
- GPU (if any)
- Recommended models

---

## Configuration Wizard

```bash
python Cerebric/main.py config-wizard
```

Interactive setup based on your hardware.

---

## Testing

```bash
# Check model status
python Cerebric/main.py model-status

# Test generation
python Cerebric/main.py model-test --prompt "Hello"
```

---

## GPU Acceleration

### NVIDIA

Ollama uses CUDA automatically if available.

```bash
nvidia-smi  # Verify GPU
```

### AMD

```bash
export HSA_OVERRIDE_GFX_VERSION=10.3.0
ollama run llama3.2:8b
```

---

## Troubleshooting

**Model too slow**: Use smaller/quantized model.

**Out of memory**: Use quantized version (-q4_0).

**Model not found**: Run `ollama pull <model>`.
