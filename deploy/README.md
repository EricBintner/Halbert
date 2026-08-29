# Halbert Multi-Instance Deployment

## Overview

Halbert supports running multiple instances on the same machine (or across machines) with full isolation. Each instance has its own persona, memory, data directory, config directory, and ports.

## Two-Instance Setup (Host + Home)

### Prerequisites

- Python 3.10+ with Halbert installed (`pip install -e .`)
- Ollama running on port 11434
- SourcePrep daemon running on port 8400 (optional, for config awareness)

### Installation

1. **Copy systemd unit files:**
   ```bash
   sudo cp deploy/halbert-host.service /etc/systemd/system/
   sudo cp deploy/halbert-home.service /etc/systemd/system/
   ```

2. **Create data and config directories:**
   ```bash
   sudo mkdir -p /var/lib/halbert /etc/halbert /var/log/halbert
   sudo mkdir -p /var/lib/halbert-home /etc/halbert-home /var/log/halbert-home
   sudo chown -R halbert:halbert /var/lib/halbert* /etc/halbert* /var/log/halbert*
   ```

3. **Create being.yml for each instance:**

   `/etc/halbert/being.yml` (Host):
   ```yaml
   voice: first_person
   proactivity: balanced
   purpose: Linux system administration and development assistance
   name: Halbert
   ```

   `/etc/halbert-home/being.yml` (Home):
   ```yaml
   voice: first_person
   proactivity: balanced
   purpose: Smart home automation and ambient intelligence
   name: Home
   ```

4. **Configure HA connection (home instance only):**
   ```bash
   HALBERT_DATA_DIR=/var/lib/halbert-home python -c "
   from halbert_core.integrations.home_assistant.ha_config import save_ha_config, HAConfig
   save_ha_config(HAConfig(url='http://localhost:8123', token='YOUR_LONG_LIVED_TOKEN'))
   "
   ```

5. **Enable and start services:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now halbert-host
   sudo systemctl enable --now halbert-home
   ```

### Verification

```bash
# Check both instances are running
systemctl status halbert-host
systemctl status halbert-home

# Verify instance identity in logs
journalctl -u halbert-host | grep "instance starting"
journalctl -u halbert-home | grep "instance starting"

# Test API endpoints
curl http://localhost:8000/api/instance/info  # Host
curl http://localhost:8001/api/instance/info  # Home
```

### Frontend Access

- **Host instance:** http://localhost:8000
- **Home instance:** http://localhost:8001

Use the Instance Switcher in the top bar to switch between instances without opening a new tab. Click "Pair / Connect Another Instance..." to add a remote instance.

### HACS Integration

The HACS custom integration should be configured to connect to the **home** instance's Wyoming port (10401), not the host's (10400).

## Environment Variables Reference

| Variable | Host Default | Home Default | Purpose |
|----------|-------------|-------------|---------|
| `HALBERT_PERSONA_ID` | `halbert` | `home` | Persona identity |
| `HALBERT_SCENE_CONTEXT` | `Linux system administration` | `smart home automation` | Cognitive framing |
| `HALBERT_DATA_DIR` | `/var/lib/halbert` | `/var/lib/halbert-home` | Data isolation |
| `HALBERT_CONFIG_DIR` | `/etc/halbert` | `/etc/halbert-home` | Config isolation |
| `HALBERT_LOG_DIR` | `/var/log/halbert` | `/var/log/halbert-home` | Log isolation |
| `HALBERT_PORT` | `8000` | `8001` | Dashboard API port |
| `WYOMING_PORT` | `10400` | `10401` | Wyoming voice TCP port |
| `SOURCEPREP_PROJECT_ID` | `halbert-host` | `ha-config` | SourcePrep project |
| `HALBERT_MODEL` | `qwen2.5:14b` | `qwen2.5:3b` | Ollama model |

### Backward Compatibility

Legacy env vars `Halbert_DATA_DIR`, `Halbert_CONFIG_DIR`, `Halbert_LOG_DIR` (mixed case) are still supported as fallbacks. The all-caps `HALBERT_*` variants take priority.
