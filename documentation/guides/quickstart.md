# Quickstart Guide

Get Halbert running in 5 minutes.

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

## Step 2: Clone Halbert

```bash
git clone https://github.com/ericbintner/halbert.git
cd halbert
```

---

## Step 3: Set Up Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e halbert_core/
```

---

## Step 4: Test It

```bash
# Check if everything works
python Halbert/main.py info

# Ask a question
python Halbert/main.py ask "What is systemd?"
```

---

## Step 5: Start the Dashboard

```bash
python Halbert/main.py dashboard
```

Open http://localhost:8000 in your browser.

---

## What Next?

### Try These Commands

```bash
# Check model status
python Halbert/main.py model-status

# Query memory
python Halbert/main.py memory-stats

# See autonomy guardrails
python Halbert/main.py autonomy-status
```

### Ingest Your System Data

```bash
# Start journald ingestion
python Halbert/main.py ingest-journald

# Snapshot your configs
python Halbert/main.py snapshot-configs
```

### Ask About Your System

```bash
python Halbert/main.py ask "Why did my docker service fail?"
python Halbert/main.py ask "How do I free up disk space?"
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
