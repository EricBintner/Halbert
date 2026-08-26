#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
# =============================================================================
# Halbert Linux Installation Script
# =============================================================================
# Installs Halbert and its dependencies on a Linux system.
#
# Usage:
#   curl -fsSL https://halbert.ai/install.sh | bash
#   # or
#   ./scripts/install-linux.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  _    _       _ _               _   "
echo " | |  | |     | | |             | |  "
echo " | |__| | __ _| | |__   ___ _ __| |_ "
echo " |  __  |/ _\` | | '_ \ / _ \ '__| __|"
echo " | |  | | (_| | | |_) |  __/ |  | |_ "
echo " |_|  |_|\__,_|_|_.__/ \___|_|   \__|"
echo -e "${NC}"
echo "AI-Powered System Administration Assistant"
echo ""

# =============================================================================
# Check Prerequisites
# =============================================================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check for root (we don't want to run as root)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run this script as root${NC}"
    exit 1
fi

# Check OS
if [ ! -f /etc/os-release ]; then
    echo -e "${RED}Cannot detect OS. /etc/os-release not found.${NC}"
    exit 1
fi

source /etc/os-release
echo "  Detected: $PRETTY_NAME"

# =============================================================================
# Install Ollama (Required)
# =============================================================================
echo -e "\n${YELLOW}Step 1: Checking Ollama...${NC}"

if command -v ollama &> /dev/null; then
    echo -e "  ${GREEN}✓ Ollama already installed${NC}"
else
    echo "  Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo -e "  ${GREEN}✓ Ollama installed${NC}"
fi

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    echo "  Starting Ollama service..."
    ollama serve &> /dev/null &
    sleep 2
fi

# Halbert does not pull a model for you. Check whether any model is present
# and tell the user how to choose one.
if [ -z "$(ollama list 2>/dev/null | tail -n +2)" ]; then
    echo -e "  ${YELLOW}No models found on this Ollama instance.${NC}"
    echo "  Pull a model whose size fits your RAM (roughly: a ~14B-parameter"
    echo "  model at 4-bit quantization needs ~10 GB) with:"
    echo "    ollama pull <model>"
    echo "  then select it in Halbert Settings → AI Models."
fi
echo -e "  ${GREEN}✓ Ollama ready${NC}"

# =============================================================================
# Install Halbert
# =============================================================================
echo -e "\n${YELLOW}Step 2: Installing Halbert...${NC}"

INSTALL_DIR="$HOME/.local/share/halbert"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/halbert"

mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "  Installing pip..."
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3-pip
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3-pip
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm python-pip
    else
        echo -e "${RED}Cannot install pip. Please install manually.${NC}"
        exit 1
    fi
fi

# Install halbert-core
echo "  Installing halbert-core..."
pip3 install --user halbert-core[dashboard] 2>/dev/null || {
    echo "  Package not on PyPI yet, installing from source..."
    if [ -d "halbert_core" ]; then
        pip3 install --user -e "halbert_core[dashboard]"
    else
        echo -e "${RED}Cannot find halbert_core directory${NC}"
        exit 1
    fi
}

echo -e "  ${GREEN}✓ Halbert installed${NC}"

# =============================================================================
# Setup Systemd Service (Optional)
# =============================================================================
echo -e "\n${YELLOW}Step 3: Setting up service...${NC}"

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/halbert-api.service" << 'EOF'
[Unit]
Description=Halbert AI Assistant Backend API
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m halbert_core.dashboard --port 8000
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable halbert-api 2>/dev/null || true

echo -e "  ${GREEN}✓ Service configured${NC}"

# =============================================================================
# Create Desktop Entry
# =============================================================================
echo -e "\n${YELLOW}Step 4: Creating desktop entry...${NC}"

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/halbert.desktop" << EOF
[Desktop Entry]
Name=Halbert
Comment=AI-Powered System Administration Assistant
Exec=python3 -m halbert_core.dashboard
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=System;Utility;
Keywords=ai;assistant;system;admin;
EOF

echo -e "  ${GREEN}✓ Desktop entry created${NC}"

# =============================================================================
# Summary
# =============================================================================
echo -e "\n${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "To start Halbert:"
echo "  1. As a service:  systemctl --user start halbert-api"
echo "  2. Manually:      python3 -m halbert_core.dashboard"
echo ""
echo "Then open your browser to: http://localhost:8000"
echo ""
echo "Pull a model that fits your RAM with 'ollama pull <model>' and choose it"
echo "in Settings → AI Models before chatting."
echo ""
echo -e "${BLUE}Thank you for installing Halbert!${NC}"
