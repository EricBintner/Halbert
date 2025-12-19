#!/bin/bash
# =============================================================================
# Halbert Linux Build Script
# =============================================================================
# Builds a self-contained Linux application with:
# - Python backend (via PyInstaller)
# - React frontend (via Vite)
# - Tauri desktop shell
#
# Usage:
#   ./scripts/build-linux.sh [--skip-frontend] [--skip-backend] [--dev]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HALBERT_CORE="$PROJECT_ROOT/halbert_core"
FRONTEND_DIR="$HALBERT_CORE/halbert_core/dashboard/frontend"
TAURI_DIR="$FRONTEND_DIR/src-tauri"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_FRONTEND=false
SKIP_BACKEND=false
DEV_MODE=false

for arg in "$@"; do
    case $arg in
        --skip-frontend) SKIP_FRONTEND=true ;;
        --skip-backend) SKIP_BACKEND=true ;;
        --dev) DEV_MODE=true ;;
        --help|-h)
            echo "Usage: $0 [--skip-frontend] [--skip-backend] [--dev]"
            echo ""
            echo "Options:"
            echo "  --skip-frontend  Skip building the React frontend"
            echo "  --skip-backend   Skip building the Python backend"
            echo "  --dev            Build in development mode (faster, larger)"
            exit 0
            ;;
    esac
done

echo -e "${GREEN}=== Halbert Linux Build ===${NC}"
echo "Project root: $PROJECT_ROOT"

# =============================================================================
# Step 1: Check prerequisites
# =============================================================================
echo -e "\n${YELLOW}[1/5] Checking prerequisites...${NC}"

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        exit 1
    fi
    echo "  ✓ $1"
}

check_command python3
check_command node
check_command npm
check_command cargo

# Check Python version (use Python itself, not bc which may not be installed)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
if [[ "$PYTHON_OK" != "1" ]]; then
    echo -e "${RED}Error: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo "  ✓ Python $PYTHON_VERSION"

# =============================================================================
# Step 2: Build Frontend
# =============================================================================
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "\n${YELLOW}[2/5] Building frontend...${NC}"
    cd "$FRONTEND_DIR"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install
    fi
    
    # Build
    echo "  Building React app..."
    npm run build
    
    echo -e "  ${GREEN}✓ Frontend built${NC}"
else
    echo -e "\n${YELLOW}[2/5] Skipping frontend build${NC}"
fi

# =============================================================================
# Step 3: Build Python Backend
# =============================================================================
if [ "$SKIP_BACKEND" = false ]; then
    echo -e "\n${YELLOW}[3/5] Building Python backend...${NC}"
    cd "$HALBERT_CORE"
    
    # Create/activate virtual environment if needed
    if [ ! -d ".venv" ]; then
        echo "  Creating virtual environment..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    
    # Install dependencies
    echo "  Installing Python dependencies..."
    pip install -q -e ".[dashboard]" 2>/dev/null || pip install -q -e .
    pip install -q pyinstaller
    
    # Create binaries directory
    mkdir -p "$TAURI_DIR/binaries"
    
    # Build with PyInstaller
    echo "  Building with PyInstaller..."
    
    PYINSTALLER_OPTS="--name halbert-api --noconfirm --clean"
    
    if [ "$DEV_MODE" = true ]; then
        # Dev mode: faster build, directory output
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --onedir"
    else
        # Production: single file
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --onefile"
    fi
    
    # Add data directories
    if [ -d "$PROJECT_ROOT/data/linux" ]; then
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --add-data $PROJECT_ROOT/data/linux:data/linux"
    fi
    if [ -d "$PROJECT_ROOT/data/common" ]; then
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --add-data $PROJECT_ROOT/data/common:data/common"
    fi
    
    # Hidden imports for packages that PyInstaller misses
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import chromadb"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import chromadb.config"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import sentence_transformers"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.logging"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.loops"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.loops.auto"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.protocols"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.protocols.http"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.protocols.http.auto"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.protocols.websockets"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.protocols.websockets.auto"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.lifespan"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import uvicorn.lifespan.on"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import fastapi"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import pydantic"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import pydantic_core"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import httpx"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import requests"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import psutil"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import aiofiles"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import apscheduler"
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import sqlalchemy"
    
    pyinstaller $PYINSTALLER_OPTS halbert_core/dashboard/__main__.py
    
    # Copy to Tauri binaries
    ARCH=$(uname -m)
    case $ARCH in
        x86_64) TARGET="x86_64-unknown-linux-gnu" ;;
        aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
        *) TARGET="$ARCH-unknown-linux-gnu" ;;
    esac
    
    if [ "$DEV_MODE" = true ]; then
        cp -r dist/halbert-api "$TAURI_DIR/binaries/halbert-api-$TARGET"
    else
        cp dist/halbert-api "$TAURI_DIR/binaries/halbert-api-$TARGET"
    fi
    
    deactivate
    echo -e "  ${GREEN}✓ Backend built${NC}"
else
    echo -e "\n${YELLOW}[3/5] Skipping backend build${NC}"
fi

# =============================================================================
# Step 4: Build Tauri App
# =============================================================================
echo -e "\n${YELLOW}[4/5] Building Tauri app...${NC}"
cd "$FRONTEND_DIR"

if [ "$DEV_MODE" = true ]; then
    npm run tauri build -- --debug
else
    npm run tauri build
fi

echo -e "  ${GREEN}✓ Tauri app built${NC}"

# =============================================================================
# Step 5: Summary
# =============================================================================
echo -e "\n${YELLOW}[5/5] Build complete!${NC}"
echo ""
echo "Output files:"

if [ -d "$TAURI_DIR/target/release/bundle" ]; then
    find "$TAURI_DIR/target/release/bundle" -type f \( -name "*.AppImage" -o -name "*.deb" -o -name "*.rpm" \) 2>/dev/null | while read f; do
        SIZE=$(du -h "$f" | cut -f1)
        echo "  $f ($SIZE)"
    done
fi

echo ""
echo -e "${GREEN}Done!${NC}"
