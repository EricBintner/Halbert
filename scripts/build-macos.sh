#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
# =============================================================================
# Halbert macOS Build Script
# =============================================================================
# Builds a macOS application for one distribution channel:
#
#   oss-macos        Free, self-distributed, GPL-3.0. No DRM, no store.
#   macos-pro        Halbert Pro. Paid, LemonSqueezy, unsandboxed.
#   macos-app-store  Mac App Store companion client. Sandboxed, Apple DRM.
#
# The channel is not cosmetic: it decides which slices of the RAG corpus may
# legally be packaged. CC BY-NC content (SS64) is barred from both paid
# channels; GNU FDL content (Arch Wiki) is barred from the App Store because
# GFDL 1.3 §2 forbids the technical measures Apple applies.
#
# That decision is made by config/licensing.yml and enforced here, twice:
#   1. before packaging — the corpus is staged from the channel's allowed paths
#   2. after staging     — the staged tree is audited and the build aborts on
#                          any violation
#
# LEG-CRIT-01 / LEG-CRIT-03 / LEG-MAJ-05
#
# Usage:
#   ./scripts/build-macos.sh --channel macos-pro [--skip-frontend] [--skip-backend] [--dev]
#   ./scripts/build-macos.sh --channel macos-app-store --gate-only
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HALBERT_CORE="$PROJECT_ROOT/halbert_core"
FRONTEND_DIR="$HALBERT_CORE/halbert_core/dashboard/frontend"
TAURI_DIR="$FRONTEND_DIR/src-tauri"
STAGE_DIR="$PROJECT_ROOT/build/corpus"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CHANNEL=""
SKIP_FRONTEND=false
SKIP_BACKEND=false
DEV_MODE=false
GATE_ONLY=false

usage() {
    cat <<'EOF'
Usage: ./scripts/build-macos.sh --channel CHANNEL [options]

Channels:
  oss-macos        Free self-distributed GPL-3.0 build (no DRM)
  macos-pro        Paid LemonSqueezy build (unsandboxed)
  macos-app-store  Mac App Store companion client (sandboxed, DRM)

Options:
  --gate-only      Run the licence gate and stage the corpus, then stop
  --skip-frontend  Skip building the React frontend
  --skip-backend   Skip building the Python backend
  --dev            Development build (faster, larger)
  -h, --help       This message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel) CHANNEL="${2:-}"; shift 2 ;;
        --channel=*) CHANNEL="${1#*=}"; shift ;;
        --gate-only) GATE_ONLY=true; shift ;;
        --skip-frontend) SKIP_FRONTEND=true; shift ;;
        --skip-backend) SKIP_BACKEND=true; shift ;;
        --dev) DEV_MODE=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo -e "${RED}Unknown argument: $1${NC}"; usage; exit 2 ;;
    esac
done

if [[ -z "$CHANNEL" ]]; then
    echo -e "${RED}Error: --channel is required${NC}"
    usage
    exit 2
fi

case "$CHANNEL" in
    oss-macos|macos-pro|macos-app-store) ;;
    *)
        echo -e "${RED}Error: '$CHANNEL' is not a macOS distribution channel${NC}"
        echo "Valid: oss-macos, macos-pro, macos-app-store"
        exit 2
        ;;
esac

echo -e "${GREEN}=== Halbert macOS Build ===${NC}"
echo "Project root: $PROJECT_ROOT"
echo "Channel:      $CHANNEL"

# =============================================================================
# Step 1: Prerequisites
# =============================================================================
echo -e "\n${YELLOW}[1/6] Checking prerequisites...${NC}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo -e "${YELLOW}  ! Not running on macOS — the licence gate still works, but${NC}"
    echo -e "${YELLOW}    PyInstaller and Tauri cannot produce a macOS bundle here.${NC}"
    if [[ "$GATE_ONLY" != true ]]; then
        echo -e "${RED}Error: run on macOS, or pass --gate-only${NC}"
        exit 2
    fi
fi

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        exit 1
    fi
    echo "  ✓ $1"
}

check_command python3
if [[ "$GATE_ONLY" != true ]]; then
    check_command node
    check_command npm
    check_command cargo
    PYTHON_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
    if [[ "$PYTHON_OK" != "1" ]]; then
        echo -e "${RED}Error: Python 3.10+ required${NC}"
        exit 1
    fi
fi

# =============================================================================
# Step 2: Licence gate — plan and stage the corpus for this channel
# =============================================================================
echo -e "\n${YELLOW}[2/6] Staging corpus under the '$CHANNEL' licence policy...${NC}"

# Replacement coverage first: excluding the non-commercial slice must not
# silently cost the user knowledge coverage.
if ! python3 "$SCRIPT_DIR/corpus_license_gate.py" --coverage --no-color; then
    echo -e "${RED}Error: replacement coverage is incomplete — refusing to build.${NC}"
    echo "       Run: python3 scripts/generate_macos_command_guides.py"
    exit 1
fi

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

INCLUDED_PATHS=$(python3 "$SCRIPT_DIR/corpus_license_gate.py" --channel "$CHANNEL" --print-paths)
if [[ -z "$INCLUDED_PATHS" ]]; then
    echo -e "${RED}Error: the licence policy allows no corpus paths for '$CHANNEL'${NC}"
    exit 1
fi

STAGED=0
while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    src="$PROJECT_ROOT/data/$rel"
    if [[ ! -d "$src" ]]; then
        echo "  · skip $rel (not present in this checkout)"
        continue
    fi
    dest="$STAGE_DIR/$rel"
    mkdir -p "$(dirname "${dest%/}")"
    cp -R "${src%/}" "${dest%/}"
    STAGED=$((STAGED + 1))
    echo "  + $rel"
done <<< "$INCLUDED_PATHS"

# The manifest travels with the corpus so the running app can report versions
# and attributions for exactly what it shipped with.
cp "$PROJECT_ROOT/data/manifest.json" "$STAGE_DIR/manifest.json"
echo "  + manifest.json"
echo -e "  ${GREEN}✓ Staged $STAGED corpus paths${NC}"

# =============================================================================
# Step 3: Licence gate — audit what was actually staged
# =============================================================================
echo -e "\n${YELLOW}[3/6] Auditing the staged corpus...${NC}"

if ! python3 "$SCRIPT_DIR/corpus_license_gate.py" --channel "$CHANNEL" --bundle "$STAGE_DIR" --no-color; then
    echo -e "${RED}"
    echo "==============================================================="
    echo " LICENCE GATE FAILED — build aborted"
    echo "==============================================================="
    echo " The staged corpus contains content that cannot be distributed"
    echo " through '$CHANNEL'. Nothing has been packaged."
    echo " Policy: config/licensing.yml"
    echo -e "${NC}"
    exit 1
fi

# For the two commercial channels, also assert on dependency licences: the
# GPLv3 §7 App Store exception covers Halbert's own code, not third-party
# copyleft libraries linked into the same binary. (LEG-CRIT-03)
if [[ "$CHANNEL" == "macos-app-store" ]]; then
    echo -e "\n${YELLOW}  Checking dependency licences for the App Store target...${NC}"
    if ! python3 "$SCRIPT_DIR/check_appstore_deps.py" --no-color; then
        echo -e "${RED}Error: a dependency's licence is incompatible with App Store distribution.${NC}"
        exit 1
    fi
fi

echo -e "  ${GREEN}✓ Licence gate passed${NC}"

if [[ "$GATE_ONLY" == true ]]; then
    echo -e "\n${GREEN}Gate-only run complete. Staged corpus: $STAGE_DIR${NC}"
    exit 0
fi

# =============================================================================
# Step 4: Build Frontend
# =============================================================================
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "\n${YELLOW}[4/6] Building frontend...${NC}"
    cd "$FRONTEND_DIR"
    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install
    fi
    npm run build
    echo -e "  ${GREEN}✓ Frontend built${NC}"
else
    echo -e "\n${YELLOW}[4/6] Skipping frontend build${NC}"
fi

# =============================================================================
# Step 5: Build Python Backend
# =============================================================================
if [ "$SKIP_BACKEND" = false ]; then
    echo -e "\n${YELLOW}[5/6] Building Python backend...${NC}"
    cd "$HALBERT_CORE"

    if [ ! -d ".venv" ]; then
        echo "  Creating virtual environment..."
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate

    echo "  Installing Python dependencies..."
    pip install -q -e ".[dashboard]" 2>/dev/null || pip install -q -e .
    pip install -q pyinstaller

    mkdir -p "$TAURI_DIR/binaries"

    PYINSTALLER_OPTS="--name halbert-api --noconfirm --clean"
    if [ "$DEV_MODE" = true ]; then
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --onedir"
    else
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --onefile"
    fi

    # Only the gated, staged corpus is ever bundled. Never $PROJECT_ROOT/data
    # directly — that tree contains the non-commercial quarantine.
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --add-data $STAGE_DIR:data"

    for module in chromadb chromadb.config sentence_transformers uvicorn \
                  uvicorn.logging uvicorn.loops uvicorn.loops.auto \
                  uvicorn.protocols uvicorn.protocols.http uvicorn.protocols.http.auto \
                  uvicorn.protocols.websockets uvicorn.protocols.websockets.auto \
                  uvicorn.lifespan uvicorn.lifespan.on fastapi pydantic pydantic_core \
                  httpx requests psutil aiofiles apscheduler sqlalchemy; do
        PYINSTALLER_OPTS="$PYINSTALLER_OPTS --hidden-import $module"
    done

    # systemd-python is LGPL and Linux-only. It must never reach a macOS
    # bundle; the pyproject marker keeps it uninstalled, this makes it explicit.
    PYINSTALLER_OPTS="$PYINSTALLER_OPTS --exclude-module systemd"

    # shellcheck disable=SC2086
    pyinstaller $PYINSTALLER_OPTS halbert_core/dashboard/__main__.py

    ARCH=$(uname -m)
    case $ARCH in
        arm64) TARGET="aarch64-apple-darwin" ;;
        x86_64) TARGET="x86_64-apple-darwin" ;;
        *) TARGET="$ARCH-apple-darwin" ;;
    esac

    if [ "$DEV_MODE" = true ]; then
        cp -R dist/halbert-api "$TAURI_DIR/binaries/halbert-api-$TARGET"
    else
        cp dist/halbert-api "$TAURI_DIR/binaries/halbert-api-$TARGET"
    fi

    deactivate
    echo -e "  ${GREEN}✓ Backend built for $TARGET${NC}"
else
    echo -e "\n${YELLOW}[5/6] Skipping backend build${NC}"
fi

# =============================================================================
# Step 6: Build Tauri App
# =============================================================================
echo -e "\n${YELLOW}[6/6] Building Tauri app...${NC}"
cd "$FRONTEND_DIR"

export HALBERT_CHANNEL="$CHANNEL"
if [ "$DEV_MODE" = true ]; then
    npm run tauri build -- --debug
else
    npm run tauri build
fi

echo -e "\n${GREEN}Build complete (channel: $CHANNEL)${NC}"
echo ""
echo "Output files:"
if [ -d "$TAURI_DIR/target/release/bundle" ]; then
    find "$TAURI_DIR/target/release/bundle" -type d -name "*.app" -o -type f -name "*.dmg" 2>/dev/null | while read -r f; do
        SIZE=$(du -sh "$f" | cut -f1)
        echo "  $f ($SIZE)"
    done
fi

cat <<EOF

Licence status for this build:
  Channel:        $CHANNEL
  Corpus staged:  $STAGE_DIR
  Policy:         config/licensing.yml
  Re-verify:      python3 scripts/corpus_license_gate.py --channel $CHANNEL --bundle $STAGE_DIR
EOF

if [[ "$CHANNEL" == "macos-app-store" ]]; then
    cat <<'EOF'

REMINDER — Mac App Store submission checklist.

The GPLv3 §7 exception is DECIDED and committed (LICENSE-EXCEPTION-APPSTORE,
2026-09-04). The licensing question is closed. What is NOT yet done, and what
this script does not yet do for you:

  * This build does not carry the licence files. GPLv3 §4 requires conveying
    LICENSE and LICENSE-EXCEPTION-APPSTORE with the object code — copy both
    into the bundle before submitting.
  * SPDX "WITH LicenseRef-Halbert-AppStore-Exception" headers are not applied
    to covered sources yet.
  * The bundle identifier and entitlements are not injected per channel; this
    build carries the dev identifier and no entitlements file.
  * The macos-private-api Cargo feature is still compiled in. It must be off
    for an App Store submission.

See documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md and ROADMAP row
DIST-1. Do not submit a bundle produced by this script until those are done.
EOF
fi
