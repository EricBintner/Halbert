#!/bin/bash
# Add NVIDIA/CUDA documentation to RAG corpus

set -e

echo "========================================================================"
echo "Adding NVIDIA/CUDA Documentation to RAG Corpus"
echo "========================================================================"

# Setup
cd "$(dirname "$0")/.."
source .venv/bin/activate

# Create output directory
mkdir -p data/linux/nvidia-docs

echo ""
echo "Step 1: Scraping NVIDIA documentation..."
echo "  This may take a few minutes (15-20 docs)"
echo ""

python docs/model_training/scripts/fetch_vendor_docs.py \
  --config scripts/urls.nvidia.yml \
  --out data/linux/nvidia-docs/nvidia_cuda_docs.jsonl \
  --os linux \
  --distro ubuntu-22.04 \
  --trust vendor_docs

echo ""
echo "Step 2: Checking what we got..."
DOC_COUNT=$(wc -l < data/linux/nvidia-docs/nvidia_cuda_docs.jsonl)
echo "  ✓ Fetched $DOC_COUNT NVIDIA documentation pages"

echo ""
echo "Step 3: Re-merging RAG corpus with NVIDIA docs..."
python scripts/merge_rag_data.py

echo ""
echo "========================================================================"
echo "✓ NVIDIA/CUDA docs added to RAG corpus!"
echo "========================================================================"
echo ""
echo "Test queries you can now use:"
echo "  - 'check GPU memory'"
echo "  - 'compile CUDA code'"
echo "  - 'CUDA memory allocation'"
echo "  - 'profile GPU application'"
echo ""
echo "To test interactively:"
echo "  python scripts/rag_demo.py --mode interactive"
echo ""
