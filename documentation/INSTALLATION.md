# Installation Guide

This guide covers installing Halbert on Linux systems.

---

## Requirements

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Ubuntu 22.04+ / Fedora 38+ / Arch | Ubuntu 24.04 LTS |
| **Python** | 3.11+ | 3.12 |
| **RAM** | 8 GB | 16+ GB (for larger models) |
| **Disk** | 10 GB free | 50+ GB (for models + data) |
| **GPU** | Optional | NVIDIA (CUDA) or AMD (ROCm) |

### Dependencies

- **Ollama** — Local LLM inference engine
- **systemd** — For journald access (standard on most distros)

---

## Quick Install

```bash
# 1. Clone the repository
git clone https://github.com/EricBintner/Halbert.git
cd Halbert

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the package
pip install -e halbert_core/

# 4. Verify installation
python Halbert/main.py --help
```

---

## Detailed Installation

### Step 1: Install Ollama

Halbert uses [Ollama](https://ollama.ai/) for local LLM inference.

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
systemctl --user start ollama

# Verify it's running
ollama list
```

### Step 2: Pull a Model

```bash
# Recommended for most systems (8B parameters, ~4GB)
ollama pull llama3.1:8b

# For systems with 32GB+ RAM (70B parameters, ~40GB)
ollama pull llama3.1:70b

# Verify the model is available
ollama list
```

### Step 3: Clone Halbert

```bash
git clone https://github.com/EricBintner/Halbert.git
cd Halbert
```

### Step 4: Create Virtual Environment

```bash
# Create venv
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 5: Install Dependencies

```bash
# Install in development mode
pip install -e halbert_core/

# This installs all dependencies including:
# - langchain, langgraph (orchestration)
# - chromadb (vector database)
# - fastapi, uvicorn (dashboard)
# - apscheduler (task scheduling)
# - watchdog (file monitoring)
```

### Step 6: Initialize Configuration

```bash
# Create default configuration
python Halbert/main.py init

# This creates:
# ~/.config/halbert/          (configuration)
# ~/.local/share/halbert/     (data)
# ~/.local/state/halbert/     (runtime state)
```

### Step 7: Verify Installation

```bash
# Check CLI works
python Halbert/main.py info

# Test model connection
python Halbert/main.py model-status

# Run a quick test
python Halbert/main.py model-test "Hello, who are you?"
```

---

## Configuration

### Model Selection

Edit `~/.config/halbert/model.yml`:

```yaml
default_model: llama3.1:8b
ollama_host: http://localhost:11434

# Model routing (optional)
routing:
  quick_tasks: llama3.1:8b
  complex_analysis: llama3.1:70b
```

### Ingestion Settings

Edit `~/.config/halbert/ingestion.yml`:

```yaml
journald:
  enabled: true
  units:
    - docker.service
    - sshd.service
    - nginx.service
  priority_max: 4  # Include warnings and above

hwmon:
  enabled: true
  interval_seconds: 30
  sensors:
    - coretemp
    - nvme
```

### Policy Rules

Edit `~/.config/halbert/policy.yml`:

```yaml
rules:
  - action: read_logs
    requires_approval: false
    
  - action: restart_service
    requires_approval: true
    
  - action: modify_config
    requires_approval: true
    dry_run_first: true
```

---

## Running Halbert

### CLI Mode

```bash
# Interactive chat
python Halbert/main.py chat

# Single query
python Halbert/main.py ask "How's my disk space?"

# Run specific commands
python Halbert/main.py ingest-journald
python Halbert/main.py memory-stats
```

### Dashboard Mode

```bash
# Recommended: use make (starts backend + live reload)
make dev-web

# Or directly via Python
python Halbert/main.py dashboard

# Access at http://localhost:8000
```

### Background Service

```bash
# Start as background service
python Halbert/main.py daemon start

# Check status
python Halbert/main.py daemon status

# Stop
python Halbert/main.py daemon stop
```

---

## GPU Acceleration

### NVIDIA (CUDA)

```bash
# Ensure NVIDIA drivers are installed
nvidia-smi

# Ollama automatically uses CUDA if available
# Verify GPU usage
ollama run llama3.1:8b "test" --verbose
```

### AMD (ROCm)

```bash
# Install ROCm
# See: https://rocm.docs.amd.com/

# Set environment for Ollama
export HSA_OVERRIDE_GFX_VERSION=10.3.0  # Adjust for your GPU
ollama run llama3.1:8b "test"
```

---

## Troubleshooting

### Ollama Connection Failed

```bash
# Check if Ollama is running
systemctl --user status ollama

# Start it
systemctl --user start ollama

# Check logs
journalctl --user -u ollama -f
```

### Model Not Found

```bash
# List available models
ollama list

# Pull the model
ollama pull llama3.1:8b
```

### Permission Denied (journald)

```bash
# Add user to systemd-journal group
sudo usermod -a -G systemd-journal $USER

# Log out and back in for changes to take effect
```

### ChromaDB Errors

```bash
# Clear the vector database
rm -rf ~/.local/share/halbert/index/

# Re-initialize
python Halbert/main.py init
```

### Out of Memory

```bash
# Use a smaller model
ollama pull llama3.1:8b-q4_0  # 4-bit quantized, ~2GB

# Update config
echo "default_model: llama3.1:8b-q4_0" >> ~/.config/halbert/model.yml
```

---

## Updating

```bash
# Pull latest changes
cd Halbert
git pull

# Update dependencies
pip install -e halbert_core/ --upgrade
```

---

## Uninstalling

```bash
# Remove configuration and data
rm -rf ~/.config/halbert
rm -rf ~/.local/share/halbert
rm -rf ~/.local/state/halbert

# Remove the repository
cd ..
rm -rf halbert

# Optionally remove Ollama
# See: https://ollama.ai/docs/uninstall
```

---

## Next Steps

- [guides/quickstart.md](guides/quickstart.md) — 5-minute tutorial
- [CLI-REFERENCE.md](CLI-REFERENCE.md) — All CLI commands
- [CONFIGURATION.md](CONFIGURATION.md) — Configuration reference
