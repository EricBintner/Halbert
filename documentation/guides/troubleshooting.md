# Troubleshooting Guide

Common issues and their solutions.

---

## Installation Issues

### Python Version Too Old

**Symptom**: `SyntaxError` or import failures.

**Solution**:
```bash
python3 --version  # Must be 3.11+

# Install newer Python (Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.12 python3.12-venv
```

### Dependencies Not Installing

**Symptom**: `pip install -e cerebric_core/` fails.

**Solution**:
```bash
# Upgrade pip
pip install --upgrade pip

# Install with verbose output
pip install -e cerebric_core/ -v

# Missing system deps (Ubuntu)
sudo apt install python3-dev build-essential
```

---

## Ollama Issues

### Ollama Not Running

**Symptom**: `Connection refused` errors.

**Solution**:
```bash
# Check status
systemctl --user status ollama

# Start it
systemctl --user start ollama

# Or run manually
ollama serve
```

### Model Not Found

**Symptom**: `model 'llama3.2:3b' not found`

**Solution**:
```bash
# List available models
ollama list

# Pull the model
ollama pull llama3.2:3b

# Verify
ollama list
```

### Out of Memory

**Symptom**: Model fails to load, system freezes.

**Solution**:
```bash
# Use smaller model
ollama pull llama3.2:1b

# Or use quantized version
ollama pull llama3.2:3b-q4_0

# Update config
echo "default_model: llama3.2:3b-q4_0" >> ~/.config/cerebric/model.yml
```

### Slow Generation

**Symptom**: Responses take minutes.

**Causes**:
1. Model too large for RAM (swapping)
2. No GPU acceleration
3. CPU too slow

**Solution**:
```bash
# Check memory usage during generation
watch -n 1 free -h

# If swapping, use smaller model
ollama pull llama3.2:1b

# Check GPU usage (NVIDIA)
nvidia-smi
```

---

## journald Issues

### Permission Denied

**Symptom**: `PermissionError` when reading logs.

**Solution**:
```bash
# Add to systemd-journal group
sudo usermod -a -G systemd-journal $USER

# Log out and back in
# Verify
groups | grep systemd-journal
```

### No Logs Captured

**Symptom**: Ingestion runs but no events.

**Causes**:
1. Service names wrong in config
2. Priority filter too strict

**Solution**:
```bash
# List actual unit names
systemctl list-units --type=service

# Test journalctl directly
journalctl -u docker.service -n 10

# Adjust priority in ingestion.yml
# priority_max: 6 (include info)
```

---

## ChromaDB Issues

### Database Corrupted

**Symptom**: `sqlite3.DatabaseError` or similar.

**Solution**:
```bash
# Backup and remove
mv ~/.local/share/cerebric/index ~/.local/share/cerebric/index.bak

# Re-initialize
python Cerebric/main.py init
```

### Embedding Model Download Fails

**Symptom**: `ConnectionError` during first run.

**Solution**:
```bash
# Manual download
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Or use offline mode after initial download
export TRANSFORMERS_OFFLINE=1
```

---

## Dashboard Issues

### Port Already in Use

**Symptom**: `Address already in use`

**Solution**:
```bash
# Find what's using port 8000
lsof -i :8000

# Kill it or use different port
python Cerebric/main.py dashboard --port 8001
```

### Cannot Connect from Browser

**Symptom**: Browser shows connection refused.

**Causes**:
1. Dashboard not running
2. Firewall blocking
3. Binding to wrong address

**Solution**:
```bash
# Bind to all interfaces (not just localhost)
python Cerebric/main.py dashboard --host 0.0.0.0

# Check firewall
sudo ufw status
```

---

## Memory Issues

### High Memory Usage

**Symptom**: System slow, swapping.

**Causes**:
1. Large model loaded
2. ChromaDB index too large
3. Memory leaks

**Solution**:
```bash
# Check what's using memory
htop

# Use smaller model
# Clear old telemetry data
rm ~/.local/share/cerebric/telemetry/journald/old-*.jsonl
```

### Index Too Large

**Symptom**: Slow queries, high disk usage.

**Solution**:
```bash
# Check index size
du -sh ~/.local/share/cerebric/index

# Rebuild with less data
rm -rf ~/.local/share/cerebric/index
# Re-index only recent data
```

---

## Configuration Issues

### Config Not Loading

**Symptom**: Using defaults despite config file existing.

**Solution**:
```bash
# Check config path
echo $XDG_CONFIG_HOME  # Should be ~/.config

# Verify file location
ls -la ~/.config/cerebric/

# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('~/.config/cerebric/model.yml'))"
```

### YAML Syntax Error

**Symptom**: `yaml.scanner.ScannerError`

**Solution**:
```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('your-file.yml'))"

# Common issues:
# - Tabs instead of spaces
# - Missing colons
# - Unquoted special characters
```

---

## RAG Issues

### No Relevant Results

**Symptom**: `ask` command returns unrelated docs.

**Causes**:
1. Query too vague
2. Data not indexed
3. Wrong embedding model

**Solution**:
```bash
# Be more specific
python Cerebric/main.py ask "systemd docker.service failed to start exit code 1"

# Check if data is indexed
python Cerebric/main.py memory-stats

# Re-index
python Cerebric/main.py index-configs
```

### Slow Retrieval

**Symptom**: Queries take >5 seconds.

**Solution**:
```bash
# Check index size
du -sh ~/.local/share/cerebric/index

# Reduce top_k
python Cerebric/main.py ask "query" --top-k 3
```

---

## Getting Help

### Collect Debug Info

```bash
# System info
uname -a
python3 --version
pip list | grep -E "(cerebric|langchain|chromadb|ollama)"

# Ollama info
ollama --version
ollama list

# Config
cat ~/.config/cerebric/model.yml
```

### Log Files

```bash
# Application logs
ls ~/.local/share/cerebric/logs/

# journald logs for Cerebric
journalctl -f | grep -i cerebric
```

### Reset Everything

Last resort - start fresh:

```bash
# Backup first
cp -r ~/.config/cerebric ~/.config/cerebric.bak
cp -r ~/.local/share/cerebric ~/.local/share/cerebric.bak

# Remove all state
rm -rf ~/.config/cerebric
rm -rf ~/.local/share/cerebric
rm -rf ~/.local/state/cerebric

# Re-initialize
python Cerebric/main.py init
```
