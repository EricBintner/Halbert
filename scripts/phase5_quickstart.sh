#!/bin/bash
# Halbert Phase 5 Quick Start Script
# Automates setup and testing of Phase 5 multi-model system

set -e

echo "======================================================================="
echo "  Halbert Phase 5: Multi-Model LLM System - Quick Start"
echo "======================================================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Detect platform
PLATFORM=$(uname -s)
echo "Platform detected: $PLATFORM"
echo ""

# Step 1: Check Python
echo -e "${YELLOW}[1/6] Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found. Please install Python 3.9+${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
echo ""

# Step 2: Check Halbert installation
echo -e "${YELLOW}[2/6] Checking Halbert installation...${NC}"
if ! python3 -c "import halbert_core.halbert_core.model" &> /dev/null; then
    echo -e "${RED}Halbert core not installed. Installing...${NC}"
    cd halbert_core && pip install -e . && cd ..
fi
echo -e "${GREEN}✓ Halbert core installed${NC}"
echo ""

# Step 3: Detect hardware
echo -e "${YELLOW}[3/6] Detecting hardware...${NC}"
python3 Halbert/main.py hardware-detect --recommend || true
echo ""

# Step 4: Check/install model provider
echo -e "${YELLOW}[4/6] Checking model providers...${NC}"

if [ "$PLATFORM" = "Darwin" ]; then
    # macOS - check for MLX or Ollama
    echo "macOS detected. Checking for MLX or Ollama..."
    
    if python3 -c "import mlx" &> /dev/null; then
        echo -e "${GREEN}✓ MLX found (Apple Silicon optimized)${NC}"
        PROVIDER="mlx"
    elif command -v ollama &> /dev/null; then
        echo -e "${GREEN}✓ Ollama found${NC}"
        PROVIDER="ollama"
    else
        echo -e "${YELLOW}Neither MLX nor Ollama found.${NC}"
        echo "Install options:"
        echo "  - MLX (Apple Silicon): pip install mlx mlx-lm"
        echo "  - Ollama: curl -fsSL https://ollama.com/install.sh | sh"
        PROVIDER="none"
    fi
else
    # Linux - check for Ollama
    echo "Linux detected. Checking for Ollama..."
    
    if command -v ollama &> /dev/null; then
        echo -e "${GREEN}✓ Ollama found${NC}"
        PROVIDER="ollama"
    else
        echo -e "${YELLOW}Ollama not found.${NC}"
        echo "Install: curl -fsSL https://ollama.com/install.sh | sh"
        PROVIDER="none"
    fi
fi
echo ""

# Step 5: Run configuration wizard
echo -e "${YELLOW}[5/6] Running configuration wizard...${NC}"
if [ "$PROVIDER" != "none" ]; then
    python3 Halbert/main.py config-wizard --auto || true
    echo -e "${GREEN}✓ Configuration created${NC}"
else
    echo -e "${YELLOW}⚠ Skipping configuration (no provider installed)${NC}"
fi
echo ""

# Step 6: Check status
echo -e "${YELLOW}[6/6] Checking router status...${NC}"
if [ "$PROVIDER" != "none" ]; then
    python3 Halbert/main.py model-router-status || true
fi
echo ""

# Summary
echo "======================================================================="
echo "  Quick Start Complete!"
echo "======================================================================="
echo ""

if [ "$PROVIDER" != "none" ]; then
    echo -e "${GREEN}✓ Halbert Phase 5 is ready to use!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Test basic generation:"
    echo "     python3 -c 'from halbert_core.halbert_core.model import ModelRouter, TaskType; r=ModelRouter(); print(r.generate(\"Hello!\", TaskType.CHAT).text)'"
    echo ""
    echo "  2. Check performance:"
    echo "     python3 Halbert/main.py performance-status"
    echo ""
    echo "  3. Explore examples:"
    echo "     cat docs/Phase5/INTEGRATION-EXAMPLES.md"
    echo ""
    
    if [ "$PLATFORM" = "Darwin" ] && [ "$PROVIDER" = "mlx" ]; then
        echo "  4. Train LoRA (Mac Apple Silicon):"
        echo "     python3 Halbert/main.py mlx-prepare-training-data --list-personas"
    fi
else
    echo -e "${YELLOW}⚠ Please install a model provider to use Halbert:${NC}"
    echo ""
    if [ "$PLATFORM" = "Darwin" ]; then
        echo "  For Mac Apple Silicon:"
        echo "    pip install mlx mlx-lm"
        echo ""
        echo "  For Mac (any):"
        echo "    curl -fsSL https://ollama.com/install.sh | sh"
    else
        echo "  For Linux:"
        echo "    curl -fsSL https://ollama.com/install.sh | sh"
    fi
    echo ""
    echo "  Then re-run this script: ./scripts/phase5_quickstart.sh"
fi

echo ""
echo "Documentation: docs/Phase5/"
echo "API Reference: docs/Phase5/API-REFERENCE.md"
echo "Examples: docs/Phase5/INTEGRATION-EXAMPLES.md"
echo ""
echo "======================================================================="
