# Dashboard Pages

Halbert's web dashboard provides 16 pages for system management. This guide documents each page and its features.

---

## Overview

Access the dashboard at `http://localhost:8000` after starting with `make dev` or `halbert dashboard`.

---

## Pages

### Dashboard (Home)

**Route**: `/`

The main overview page showing system status at a glance.

**Features**:
- System health summary
- Recent discoveries
- Quick actions
- Active alerts

---

### Chat

**Route**: `/chat`

AI-powered assistant for system management.

**Features**:
- Natural language queries about your system
- Context-aware responses (auto-injects relevant discoveries)
- Multi-model routing (Guide 8B → Specialist 70B)
- Tool calling for system actions
- Vision support (paste/drop images, screenshots)
- Command execution with auto-analysis
- Conversation history

**Keyboard shortcuts**:
- `Ctrl+Enter` — Send message
- `Ctrl+V` — Paste image for vision analysis

---

### Services

**Route**: `/services`

Systemd service management.

**Features**:
- View all services (active, failed, inactive)
- Start/stop/restart services
- View service logs
- Filter by status
- Search by name

---

### Storage

**Route**: `/storage`

Disk and filesystem management.

**Features**:
- Disk usage overview
- Mount points and capacity
- SMART health status
- ZFS pool status (if installed)
- BTRFS subvolumes (if applicable)
- bcachefs support
- Storage recommendations

---

### Backups

**Route**: `/backups`

Backup detection and management.

**Features**:
- Timeshift snapshot detection
- Borg repository discovery
- Last backup timestamps
- Backup health status
- Quick restore options

---

### Security

**Route**: `/security`

Security posture overview.

**Features**:
- SSH configuration status
- Firewall rules (ufw/iptables)
- User accounts and groups
- Failed login attempts
- Security recommendations
- AppArmor/SELinux status

---

### Network

**Route**: `/network`

Network configuration and status.

**Features**:
- Interface list (eth, wlan, bridges, bonds)
- IP addresses and routes
- DNS configuration
- VPN status (WireGuard, OpenVPN)
- Network bridges and bonds
- Firewall zones

---

### Sharing

**Route**: `/sharing`

File sharing and remote access.

**Features**:
- NFS exports
- SMB/Samba shares
- Tailscale status
- WireGuard peers
- Cloud mounts (rclone)

---

### Containers

**Route**: `/containers`

Container management for Docker and Podman.

**Features**:
- Running containers list
- Container logs
- Start/stop/restart containers
- Image management
- Network and volume info
- Compose project detection

---

### GPU

**Route**: `/gpu`

GPU monitoring and management.

**Features**:
- NVIDIA GPU stats (temperature, memory, utilization)
- AMD GPU support
- Ollama model status
- CUDA version
- Driver information
- Power usage

---

### Development

**Route**: `/development`

Developer environment status.

**Features**:
- Git repository detection
- Language version managers (nvm, pyenv, rbenv)
- Virtual environments
- Active projects
- Recent commits

---

### Approvals

**Route**: `/approvals`

Human-in-the-loop approval system.

**Features**:
- Pending approval requests
- Approve/reject actions
- Approval history
- AI Rule conflict warnings
- Risk level indicators

---

### Settings

**Route**: `/settings`

Application configuration.

**Tabs**:
- **System** — Host info, data paths
- **AI Models** — Guide/Specialist/Vision model assignment
- **Knowledge** — RAG indexing, document management
- **AI Rules** — Custom guardrails
- **Policy** — Tool permissions
- **Guardrails** — Autonomy thresholds
- **Alerts** — Notification rules
- **About** — Version info

---

### Terminal

**Route**: `/terminal`

Integrated terminal.

**Features**:
- Full shell access
- Command history
- Output capture for AI analysis
- Copy/paste support

---

### Memory

**Route**: `/memory`

ChromaDB memory management.

**Features**:
- Browse memory collections
- Search stored entries
- Delete entries
- Memory statistics
- Collection management

---

### Jobs (Legacy)

**Route**: `/jobs`

Scheduled job management.

**Features**:
- View scheduled jobs
- Job execution history
- Cancel pending jobs
- Manual job triggers

---

## Navigation

The sidebar provides quick access to all pages. Pages are grouped by category:

| Category | Pages |
|----------|-------|
| **Overview** | Dashboard |
| **AI** | Chat, Memory |
| **System** | Services, Storage, Backups, Security |
| **Network** | Network, Sharing |
| **Compute** | Containers, GPU, Development |
| **Autonomy** | Approvals, Jobs |
| **Config** | Settings, Terminal |

---

## API Access

All pages have corresponding REST API endpoints. See [API-REFERENCE.md](../API-REFERENCE.md) for details.
