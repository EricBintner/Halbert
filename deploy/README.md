# Halbert Multi-Instance Deployment

## Overview

Halbert supports running multiple instances on the same machine (or across machines) with full isolation. Each instance has its own persona, memory, data directory, config directory, and ports.

## Two-Instance Setup (Host + Home)

### Prerequisites

- Python 3.10+ with Halbert installed (`pip install -e .`)
- Ollama running on port 11434
- SourcePrep daemon running on port 8400 (optional; sysadmin/Host instance only — the Home instance runs without SourcePrep)

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
| `HALBERT_VARIANT` | `sysadmin` | `home` | Gates sysadmin pipelines (ingestion, discovery scan) |
| `HALBERT_DATA_DIR` | `/var/lib/halbert` | `/var/lib/halbert-home` | Data isolation |
| `HALBERT_CONFIG_DIR` | `/etc/halbert` | `/etc/halbert-home` | Config isolation |
| `HALBERT_LOG_DIR` | `/var/log/halbert` | `/var/log/halbert-home` | Log isolation |
| `HALBERT_PORT` | `8000` | `8001` | Dashboard API port |
| `WYOMING_PORT` | `10400` | `10401` | Wyoming voice TCP port |
| `SOURCEPREP_PROJECT_ID` | `halbert-host` | *(not set)* | SourcePrep project (sysadmin/Host instance only — Home variants run without SourcePrep) |

### Model Configuration

Model selection is per-instance via `models.yml` (not env vars). Each instance should have a `models.yml` in its config directory with:

- **`chat_model`** — User's choice (cloud API or local). Cloud-encouraged.
- **`specialist_model`** — Optional, for complex reasoning.
- **`vision_model`** — Optional, for image understanding.
- **`secure_model`** — Local-only model for sensitive data processing. Endpoint URL is enforced to be loopback/localhost. **Sysadmin instance only.**

The `secure_model` processes system configs, secrets, and persona memory. It must never point at a remote endpoint. The config normaliser will disable the slot with a warning if a non-local URL is detected.

Home automation variants (`home`) keep `secure_model` **empty** in their `models.yml`: their LLM reaches Home Assistant through tool calls that abstract credentials away, so there is no sensitive-data reasoning to route to a dedicated local model. The slot is not auto-provisioned, not written by the config wizard, and not resolved on the secure turn path for those variants — a turn flagged as sensitive falls back to a local guide and fails closed if none exists.

### LAN / Tailscale GPU Offload

Low-power nodes (N100, Pi 5) can offload heavy model inference to a GPU machine on the local network or Tailscale:

1. Run Ollama on the GPU machine: `ollama serve`
2. In the low-power node's `models.yml`, add an endpoint pointing at the GPU machine's IP (e.g. `http://gpu-rig:11434`)
3. Assign `chat_model` or `specialist_model` to that endpoint
4. `secure_model` is never offloaded: on a sysadmin instance keep it pointing at localhost (the low-power node's own Ollama); on a `home` instance the slot stays empty (see Model Configuration above)

Home automation variants (`home`) do not use SourcePrep at all — not locally and not offloaded. Their agent answers from live Home Assistant state; anything complex enough to need documentation retrieval is sysadmin work, done from the workstation's Halbert instance (which keeps its own SourcePrep). Do not set `SOURCEPREP_URL` or `SOURCEPREP_PROJECT_ID` on a Home instance.

### Light Hardware Installation

For Intel N100/N150, Raspberry Pi 4/5, or legacy PCs with limited RAM:

```bash
pip install halbert-core[light]
```

This installs only the core + dashboard without `torch`, `sentence-transformers`, or `chromadb`. Ollama handles embeddings and local model inference. Cloud APIs or LAN GPU offload handle heavy workloads.

### Backward Compatibility

Legacy env vars `Halbert_DATA_DIR`, `Halbert_CONFIG_DIR`, `Halbert_LOG_DIR` (mixed case) are still supported as fallbacks. The all-caps `HALBERT_*` variants take priority.
