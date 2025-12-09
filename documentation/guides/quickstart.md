# Quickstart Guide

Get Cerebric running in 5 minutes.

---

## Prerequisites

- Linux (Ubuntu 22.04+, Fedora 38+, or Arch)
- Python 3.11+
- 8 GB RAM minimum

---

## Step 1: Install Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

Pull a model:

```bash
ollama pull llama3.2:3b
```

---

## Step 2: Clone Cerebric

```bash
git clone https://github.com/yourusername/cerebric.git
cd cerebric
```

---

## Step 3: Set Up Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e cerebric_core/
```

---

## Step 4: Test It

```bash
# Check if everything works
python Cerebric/main.py info

# Ask a question
python Cerebric/main.py ask "What is systemd?"
```

---

## Step 5: Start the Dashboard

```bash
python Cerebric/main.py dashboard
```

Open http://localhost:8000 in your browser.

---

## What Next?

### Try These Commands

```bash
# Check model status
python Cerebric/main.py model-status

# Query memory
python Cerebric/main.py memory-stats

# See autonomy guardrails
python Cerebric/main.py autonomy-status
```

### Ingest Your System Data

```bash
# Start journald ingestion
python Cerebric/main.py ingest-journald

# Snapshot your configs
python Cerebric/main.py snapshot-configs
```

### Ask About Your System

```bash
python Cerebric/main.py ask "Why did my docker service fail?"
python Cerebric/main.py ask "How do I free up disk space?"
```

---

## Common Issues

### Ollama not running

```bash
systemctl --user start ollama
```

### Model not found

```bash
ollama pull llama3.2:3b
```

### Permission denied on journald

```bash
sudo usermod -a -G systemd-journal $USER
# Log out and back in
```

---

## Next Steps

- [INSTALLATION.md](../INSTALLATION.md) - Full installation guide
- [CLI-REFERENCE.md](../CLI-REFERENCE.md) - All commands
- [ARCHITECTURE.md](../ARCHITECTURE.md) - How it works
