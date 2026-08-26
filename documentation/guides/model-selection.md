# Model Selection

Sizing and configuring LLMs for Halbert.

> **Local-first, cloud-optional**: Halbert is designed to run entirely on local LLMs via Ollama—no API keys or internet required. However, you can optionally connect to a cloud LLM provider if you prefer faster responses or don't have local GPU resources.

Halbert does not ship with, endorse, or pick a model for you. Any chat model your endpoint serves will work; the guidance below is expressed in parameter counts and memory budgets, not model names.

---

## Model Roles

Halbert uses up to three models for different tasks:

| Role | Purpose | Typical size |
|------|---------|--------------|
| **Guide** | Conversational assistant, quick responses | ~8B-parameter model |
| **Specialist** | Complex reasoning, code, system analysis | ~70B-parameter model |
| **Vision** | Screenshot/image analysis | Any multimodal model |

A single model that supports vision, tool calling, and a long context window can serve all three roles.

---

## Sizing a Model for Your Hardware

Memory is the constraint. Rule of thumb for the weights alone: 16-bit ≈ 2 GB per billion parameters, 8-bit ≈ 1 GB per billion, 4-bit ≈ 0.5–0.6 GB per billion. Add 1–4 GB on top for the context window (KV cache).

| Parameters | 4-bit (`-q4_0`) | 8-bit (`-q8_0`) | 16-bit |
|------------|-----------------|-----------------|--------|
| ~3B | ~2 GB | ~3.5 GB | ~6 GB |
| ~8B | ~5 GB | ~9 GB | ~16 GB |
| ~14B | ~9–10 GB | ~15 GB | ~28 GB |
| ~24–32B | ~15–20 GB | ~26–34 GB | ~50–65 GB |
| ~70B | ~40 GB | ~75 GB | ~140 GB |

Ollama lists what your endpoint has pulled; Settings → AI Models lets you assign any of them to a role.

### Best Performance (64 GB+ RAM or GPU offload)

```bash
# Specialist - a ~70B-class model
ollama pull <specialist-model>

# Guide - a ~8B-class model for fast responses
ollama pull <guide-model>

# Vision - any multimodal model
ollama pull <vision-model>
```

### Balanced (32 GB RAM)

```bash
# Specialist - a 4-bit quantized ~70B-class model, or a ~14B–32B model
ollama pull <specialist-model>:<tag>-q4_0

# Guide - a ~8B-class model
ollama pull <guide-model>

# Vision - a smaller multimodal model
ollama pull <vision-model>
```

### Minimum (16 GB RAM)

```bash
# One ~8B-class model serves both the Guide and Specialist roles
ollama pull <model>

# Vision (optional) - a small multimodal model
ollama pull <vision-model>
```

> **⚠️ Caution**: Very small (≈3B-parameter and below) models struggle with system administration tasks. They lack the reasoning capability needed for accurate Linux guidance and may produce unreliable advice.

---

## Configuration

Assign models in Settings → AI Models, or via config:

```yaml
# ~/.config/halbert/model.yml

guide:
  endpoint: http://localhost:11434
  model: <guide-model>

specialist:
  endpoint: http://localhost:11434
  model: <specialist-model>

vision:
  endpoint: http://localhost:11434
  model: <vision-model>
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
ollama pull <model>:<tag>-q4_0
```

---

## Hardware Detection

```bash
python Halbert/main.py hardware-detect --recommend
```

Shows:
- Available RAM
- GPU (if any)
- Model sizes your hardware can run

---

## Configuration Wizard

```bash
python Halbert/main.py config-wizard
```

Interactive setup based on your hardware.

---

## Testing

```bash
# Check model status
python Halbert/main.py model-status

# Test generation
python Halbert/main.py model-test --prompt "Hello"
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
ollama run <model>
```

---

## Troubleshooting

**Model too slow**: Use smaller/quantized model.

**Out of memory**: Use quantized version (-q4_0).

**Model not found**: Run `ollama pull <model>`.

---

## Cloud LLM Providers (Optional)

If you prefer cloud APIs over local models, Halbert supports any OpenAI-compatible endpoint.

### Supported Providers

| Provider | Endpoint URL | Notes |
|----------|--------------|-------|
| **OpenAI** | `https://api.openai.com` | Any chat model on your account |
| **Anthropic** | Select the **Anthropic** provider type | Any model on your account |
| **Google** | Use OpenRouter or LiteLLM | Any model on your account |
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

OpenRouter gives you access to many providers' models through one API:

1. Get API key at [openrouter.ai](https://openrouter.ai)
2. Add endpoint: `https://openrouter.ai/api/v1`
3. Models appear as `<provider>/<model>` ids; pick any from your OpenRouter model list.

### Example: OpenAI Direct

```yaml
# ~/.config/halbert/models.yml
saved_endpoints:
  - id: openai
    name: OpenAI
    url: https://api.openai.com/v1
    provider: openai
    api_key: sk-...

orchestrator:
  endpoint_id: openai
  model: <model-id-from-your-provider>
```

### Why Local-First?

Local LLMs offer:
- **Privacy** — Your system data never leaves your machine
- **No costs** — No API bills
- **Offline** — Works without internet
- **Speed** — No network latency (with good hardware)

Cloud LLMs offer:
- **No GPU required** — Works on any machine
- **Latest models** — Access whatever your provider currently serves
- **Fast** — Enterprise-grade inference servers
