# Model Selection

Choosing and configuring LLMs for Cerebric.

> **Local-first, cloud-optional**: Cerebric is designed to run entirely on local LLMs via Ollama—no API keys or internet required. However, you can optionally connect to cloud LLM providers (OpenAI, Claude, Gemini) if you prefer faster responses or don't have local GPU resources.

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

---

## Cloud LLM Providers (Optional)

If you prefer cloud APIs over local models, Cerebric supports any OpenAI-compatible endpoint.

### Supported Providers

| Provider | Endpoint URL | Notes |
|----------|--------------|-------|
| **OpenAI** | `https://api.openai.com` | GPT-4o, GPT-4-turbo |
| **Anthropic Claude** | Use OpenRouter or LiteLLM | Claude 3.5 Sonnet |
| **Google Gemini** | Use OpenRouter or LiteLLM | Gemini Pro |
| **OpenRouter** | `https://openrouter.ai/api` | Access all providers |
| **Together AI** | `https://api.together.xyz` | Open-source models |
| **Groq** | `https://api.groq.com/openai` | Ultra-fast inference |

### Configuration

In **Settings → AI Models**:

1. Click **Add Endpoint**
2. Enter provider URL and API key
3. Select **OpenAI-compatible** as provider type
4. Test connection
5. Assign to Guide, Specialist, or Vision role

### Example: OpenRouter (Access All Providers)

OpenRouter gives you access to Claude, GPT-4, Gemini, and more through one API:

1. Get API key at [openrouter.ai](https://openrouter.ai)
2. Add endpoint: `https://openrouter.ai/api/v1`
3. Models appear as: `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`, etc.

### Example: OpenAI Direct

```yaml
# ~/.config/cerebric/models.yml
saved_endpoints:
  - id: openai
    name: OpenAI
    url: https://api.openai.com/v1
    provider: openai
    api_key: sk-...

orchestrator:
  endpoint_id: openai
  model: gpt-4o
```

### Why Local-First?

Local LLMs offer:
- **Privacy** — Your system data never leaves your machine
- **No costs** — No API bills
- **Offline** — Works without internet
- **Speed** — No network latency (with good hardware)

Cloud LLMs offer:
- **No GPU required** — Works on any machine
- **Latest models** — Access GPT-4o, Claude 3.5, etc.
- **Fast** — Enterprise-grade inference servers
