# Halbert Visual Walkthrough

A guided tour through every feature of Halbert's dashboard. This document shows you what Halbert can do with screenshots of the real interface.

---

## Part 1: First Launch — The Dashboard

When you first open Halbert, you land on the **Dashboard** — your command center for everything happening on your system.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/01-dashboard-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/01-dashboard-full-light.png">
    <img alt="Dashboard Overview" src="../assets/screenshots/walkthrough/01-dashboard-full-light.png" width="900">
  </picture>
</p>

The dashboard gives you instant visibility into:
- **System health** at a glance
- **Recent discoveries** Halbert found on your machine
- **Active alerts** that need attention

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/02-dashboard-health-cards-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/02-dashboard-health-cards-light.png">
    <img alt="Health Cards Closeup" src="../assets/screenshots/walkthrough/02-dashboard-health-cards-light.png" width="700">
  </picture>
</p>
<p align="center"><em>Health cards show CPU, memory, and disk status with color-coded indicators</em></p>

---

## Part 2: Talking to Your Computer — Chat

The **Chat** page is where the magic happens. Ask Halbert anything about your system in plain English.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/03-chat-conversation-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/03-chat-conversation-light.png">
    <img alt="Chat Conversation" src="../assets/screenshots/walkthrough/03-chat-conversation-light.png" width="900">
  </picture>
</p>

Halbert doesn't just answer questions — it can **take action**. When you ask it to do something, it uses tools to interact with your system.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/04-chat-tool-call-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/04-chat-tool-call-light.png">
    <img alt="Tool Execution" src="../assets/screenshots/walkthrough/04-chat-tool-call-light.png" width="700">
  </picture>
</p>
<p align="center"><em>Watch Halbert execute commands with full transparency — you see exactly what it runs</em></p>

### Choosing Your Model

Click the model selector to switch between local Ollama models and cloud APIs:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/05-chat-model-dropdown-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/05-chat-model-dropdown-light.png">
    <img alt="Model Selector" src="../assets/screenshots/walkthrough/05-chat-model-dropdown-light.png" width="400">
  </picture>
</p>

### Vision: Paste Screenshots for Analysis

Drop or paste an image and Halbert will analyze it:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/06-chat-vision-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/06-chat-vision-light.png">
    <img alt="Vision Analysis" src="../assets/screenshots/walkthrough/06-chat-vision-light.png" width="700">
  </picture>
</p>

---

## Part 3: System Monitoring Pages

### Storage — Know Your Disks

The **Storage** page shows everything about your filesystems.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/07-storage-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/07-storage-full-light.png">
    <img alt="Storage Overview" src="../assets/screenshots/walkthrough/07-storage-full-light.png" width="900">
  </picture>
</p>

Scroll down for SMART health data on your drives:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/08-storage-smart-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/08-storage-smart-light.png">
    <img alt="SMART Health" src="../assets/screenshots/walkthrough/08-storage-smart-light.png" width="700">
  </picture>
</p>
<p align="center"><em>SMART data warns you before drives fail</em></p>

---

### GPU — AI Workload Monitoring

The **GPU** page is essential for AI/ML work.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/09-gpu-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/09-gpu-full-light.png">
    <img alt="GPU Overview" src="../assets/screenshots/walkthrough/09-gpu-full-light.png" width="900">
  </picture>
</p>

See which Ollama models are currently loaded in VRAM:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/10-gpu-ollama-models-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/10-gpu-ollama-models-light.png">
    <img alt="Ollama Models" src="../assets/screenshots/walkthrough/10-gpu-ollama-models-light.png" width="600">
  </picture>
</p>

---

### Network — Connections at a Glance

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/11-network-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/11-network-full-light.png">
    <img alt="Network Overview" src="../assets/screenshots/walkthrough/11-network-full-light.png" width="900">
  </picture>
</p>

---

### Services — Systemd Made Visual

Manage systemd services without memorizing `systemctl` commands:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/12-services-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/12-services-full-light.png">
    <img alt="Services List" src="../assets/screenshots/walkthrough/12-services-full-light.png" width="900">
  </picture>
</p>

Click any service to see its logs:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/13-services-logs-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/13-services-logs-light.png">
    <img alt="Service Logs" src="../assets/screenshots/walkthrough/13-services-logs-light.png" width="700">
  </picture>
</p>

---

### Containers — Docker & Podman

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/14-containers-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/14-containers-full-light.png">
    <img alt="Containers Overview" src="../assets/screenshots/walkthrough/14-containers-full-light.png" width="900">
  </picture>
</p>

---

## Part 4: Security & Safety

### Security Page — Your Posture at a Glance

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/15-security-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/15-security-full-light.png">
    <img alt="Security Overview" src="../assets/screenshots/walkthrough/15-security-full-light.png" width="900">
  </picture>
</p>

---

### Approvals — Human in the Loop

When Halbert wants to do something potentially risky, it asks first:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/16-approvals-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/16-approvals-full-light.png">
    <img alt="Approvals Queue" src="../assets/screenshots/walkthrough/16-approvals-full-light.png" width="900">
  </picture>
</p>

Each request shows exactly what will happen:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/17-approvals-detail-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/17-approvals-detail-light.png">
    <img alt="Approval Detail" src="../assets/screenshots/walkthrough/17-approvals-detail-light.png" width="600">
  </picture>
</p>
<p align="center"><em>Review the exact command before approving</em></p>

---

## Part 5: Configuration — Settings Deep Dive

The **Settings** page has multiple tabs for complete control.

### AI Models Tab

Configure which models handle different tasks:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/18-settings-ai-models-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/18-settings-ai-models-light.png">
    <img alt="Settings - AI Models" src="../assets/screenshots/walkthrough/18-settings-ai-models-light.png" width="900">
  </picture>
</p>

### Knowledge Tab — RAG Configuration

Manage what documentation Halbert knows:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/19-settings-knowledge-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/19-settings-knowledge-light.png">
    <img alt="Settings - Knowledge" src="../assets/screenshots/walkthrough/19-settings-knowledge-light.png" width="900">
  </picture>
</p>

### Guardrails Tab — Safety Thresholds

Control how autonomous Halbert can be:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/20-settings-guardrails-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/20-settings-guardrails-light.png">
    <img alt="Settings - Guardrails" src="../assets/screenshots/walkthrough/20-settings-guardrails-light.png" width="900">
  </picture>
</p>

---

## Part 6: Additional Pages

### Backups

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/21-backups-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/21-backups-full-light.png">
    <img alt="Backups Overview" src="../assets/screenshots/walkthrough/21-backups-full-light.png" width="900">
  </picture>
</p>

### Sharing — File Shares & VPNs

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/22-sharing-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/22-sharing-full-light.png">
    <img alt="Sharing Overview" src="../assets/screenshots/walkthrough/22-sharing-full-light.png" width="900">
  </picture>
</p>

### Development — Dev Environment Status

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/23-development-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/23-development-full-light.png">
    <img alt="Development Overview" src="../assets/screenshots/walkthrough/23-development-full-light.png" width="900">
  </picture>
</p>

### Memory — What Halbert Remembers

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/24-memory-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/24-memory-full-light.png">
    <img alt="Memory Overview" src="../assets/screenshots/walkthrough/24-memory-full-light.png" width="900">
  </picture>
</p>

### Terminal — Integrated Shell

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/walkthrough/25-terminal-full-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="../assets/screenshots/walkthrough/25-terminal-full-light.png">
    <img alt="Terminal" src="../assets/screenshots/walkthrough/25-terminal-full-light.png" width="900">
  </picture>
</p>

---

## Next Steps

- [Installation Guide](INSTALLATION.md) — Get Halbert running
- [CLI Reference](CLI-REFERENCE.md) — Command line usage
- [Configuration](CONFIGURATION.md) — Customize settings
- [Architecture](ARCHITECTURE.md) — How it works

---

---

# Image Capture Checklist

**All images go in:** `assets/screenshots/walkthrough/`

Capture each screenshot in **both dark and light mode**.

| # | Filename (light) | Filename (dark) | What to Capture |
|---|------------------|-----------------|-----------------|
| 01 | `01-dashboard-full-light.png` | `01-dashboard-full-dark.png` | **Full dashboard page** — sidebar visible, health cards, discoveries |
| 02 | `02-dashboard-health-cards-light.png` | `02-dashboard-health-cards-dark.png` | **Closeup of health cards** — CPU/memory/disk cards only |
| 03 | `03-chat-conversation-light.png` | `03-chat-conversation-dark.png` | **Chat with 2-3 exchanges** — show a real Q&A flow |
| 04 | `04-chat-tool-call-light.png` | `04-chat-tool-call-dark.png` | **Tool execution visible** — show the collapsible tool call block |
| 05 | `05-chat-model-dropdown-light.png` | `05-chat-model-dropdown-dark.png` | **Model dropdown open** — show available models |
| 06 | `06-chat-vision-light.png` | `06-chat-vision-dark.png` | **Image pasted in chat** — show vision analysis |
| 07 | `07-storage-full-light.png` | `07-storage-full-dark.png` | **Full storage page** — disk bars, mount table |
| 08 | `08-storage-smart-light.png` | `08-storage-smart-dark.png` | **SMART section closeup** — drive health data |
| 09 | `09-gpu-full-light.png` | `09-gpu-full-dark.png` | **Full GPU page** — NVIDIA stats, temperature, utilization |
| 10 | `10-gpu-ollama-models-light.png` | `10-gpu-ollama-models-dark.png` | **Ollama models section** — which models are loaded |
| 11 | `11-network-full-light.png` | `11-network-full-dark.png` | **Full network page** — interfaces, IPs |
| 12 | `12-services-full-light.png` | `12-services-full-dark.png` | **Full services page** — service list with status colors |
| 13 | `13-services-logs-light.png` | `13-services-logs-dark.png` | **Service logs expanded** — click a service, show logs |
| 14 | `14-containers-full-light.png` | `14-containers-full-dark.png` | **Full containers page** — running containers list |
| 15 | `15-security-full-light.png` | `15-security-full-dark.png` | **Full security page** — SSH, firewall, users |
| 16 | `16-approvals-full-light.png` | `16-approvals-full-dark.png` | **Full approvals page** — pending items queue |
| 17 | `17-approvals-detail-light.png` | `17-approvals-detail-dark.png` | **Single approval expanded** — show the command/action |
| 18 | `18-settings-ai-models-light.png` | `18-settings-ai-models-dark.png` | **Settings → AI Models tab** |
| 19 | `19-settings-knowledge-light.png` | `19-settings-knowledge-dark.png` | **Settings → Knowledge tab** |
| 20 | `20-settings-guardrails-light.png` | `20-settings-guardrails-dark.png` | **Settings → Guardrails tab** |
| 21 | `21-backups-full-light.png` | `21-backups-full-dark.png` | **Full backups page** |
| 22 | `22-sharing-full-light.png` | `22-sharing-full-dark.png` | **Full sharing page** |
| 23 | `23-development-full-light.png` | `23-development-full-dark.png` | **Full development page** |
| 24 | `24-memory-full-light.png` | `24-memory-full-dark.png` | **Full memory page** |
| 25 | `25-terminal-full-light.png` | `25-terminal-full-dark.png` | **Terminal with some commands run** |

**Total: 50 image files** (25 screenshots × 2 themes)
