#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
# Halbert Development - Clean Restart Script
# Kills ALL existing dev processes and restarts everything fresh
#
# Usage: ./scripts/dev-restart.sh [mode]
#   mode: tauri (default) - Full Tauri app + backend
#         web             - Backend only (browser at http://localhost:8000)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODE="${1:-tauri}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Halbert Development - Clean Restart (mode: ${MODE})${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Kill ALL existing processes
# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[1/4] Killing existing processes...${NC}"

# Kill any process on port 8000 (backend)
if lsof -i:8000 >/dev/null 2>&1; then
    echo "  → Killing backend on port 8000"
    lsof -t -i:8000 | xargs -r kill -9 2>/dev/null || true
fi

# Kill any process on port 5173 (Vite dev server)
if lsof -i:5173 >/dev/null 2>&1; then
    echo "  → Killing Vite on port 5173"
    lsof -t -i:5173 | xargs -r kill -9 2>/dev/null || true
fi

# Kill any process on port 1420 (Tauri dev)
if lsof -i:1420 >/dev/null 2>&1; then
    echo "  → Killing Tauri on port 1420"
    lsof -t -i:1420 | xargs -r kill -9 2>/dev/null || true
fi

# Kill any uvicorn processes related to halbert
if pgrep -f "uvicorn.*halbert" >/dev/null 2>&1; then
    echo "  → Killing uvicorn processes"
    pkill -9 -f "uvicorn.*halbert" 2>/dev/null || true
fi

# Kill any cargo-tauri processes
if pgrep -f "cargo-tauri" >/dev/null 2>&1; then
    echo "  → Killing cargo-tauri processes"
    pkill -9 -f "cargo-tauri" 2>/dev/null || true
fi

# Kill any node processes in our frontend directory
if pgrep -f "node.*dashboard/frontend" >/dev/null 2>&1; then
    echo "  → Killing node processes"
    pkill -9 -f "node.*dashboard/frontend" 2>/dev/null || true
fi

# Kill any halbert-dashboard processes (Tauri app)
if pgrep -f "halbert-dashboard" >/dev/null 2>&1; then
    echo "  → Killing Tauri app"
    pkill -9 -f "halbert-dashboard" 2>/dev/null || true
fi

# Wait for processes to die
sleep 2

echo -e "${GREEN}  ✓ All processes killed${NC}"

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Verify ports are free
# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[2/4] Verifying ports are free...${NC}"

check_port() {
    local port=$1
    if lsof -i:$port >/dev/null 2>&1; then
        echo -e "${RED}  ✗ Port $port is still in use!${NC}"
        lsof -i:$port
        return 1
    else
        echo -e "${GREEN}  ✓ Port $port is free${NC}"
        return 0
    fi
}

check_port 8000 || exit 1
if [ "$MODE" = "tauri" ]; then
    check_port 5173 || exit 1
    check_port 1420 || exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Activate virtual environment
# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[3/4] Setting up environment...${NC}"

if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "  → Activating virtual environment"
    source "$PROJECT_ROOT/.venv/bin/activate"
else
    echo -e "${RED}  ✗ No .venv found at $PROJECT_ROOT/.venv${NC}"
    echo "  Create one with: python -m venv .venv && pip install -e halbert_core"
    exit 1
fi

echo -e "${GREEN}  ✓ Environment ready${NC}"

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Start services
# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[4/4] Starting services...${NC}"

if [ "$MODE" = "web" ]; then
    # Web-only mode
    echo -e "\n${GREEN}═══════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Halbert Dashboard - http://localhost:8000${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════${NC}"
    echo -e "${BLUE}Press Ctrl+C to stop${NC}\n"
    
    cd "$PROJECT_ROOT/halbert_core"
    exec python -m uvicorn halbert_core.dashboard.app:app \
        --host 127.0.0.1 \
        --port 8000 \
        --reload
else
    # Tauri mode - use the existing script which handles both
    echo "  → Launching Tauri + Backend..."
    exec "$SCRIPT_DIR/dev-dashboard.sh"
fi
