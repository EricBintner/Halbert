# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert Legal Router — third-party notices, privacy, and disclaimer acceptance.

Endpoints:
  - GET  /api/legal/notices     — structured third-party license manifest for the UI
  - GET  /api/legal/disclaimer  — current disclaimer version + acceptance state
  - POST /api/legal/disclaimer/accept — record user acceptance of the disclaimer
  - GET  /api/legal/cloud-disclosure  — cloud API data-flow disclosure text
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...utils.platform import get_data_dir

logger = logging.getLogger("halbert.dashboard")

router = APIRouter(prefix="/api/legal", tags=["legal"])

_DISCLAIMER_VERSION = "1.0"

# Structured third-party notice manifest. Mirrors the per-source table in
# documentation/legal/THIRD-PARTY-LICENSES.md §2. Rendered by the dashboard
# "About / Legal Notices" panel (LEG-MOD-01).
_RAG_SOURCES: List[Dict[str, Any]] = [
    {
        "name": "arch_wiki",
        "documents": 2397,
        "license": "GNU FDL 1.3",
        "license_url": "https://www.gnu.org/licenses/fdl-1.3.html",
        "upstream": "https://wiki.archlinux.org/",
        "attribution": "Arch Wiki content licensed under GNU FDL 1.3, © Arch Linux contributors.",
        "mac_build": False,
        "commercial_ok": False,
    },
    {
        "name": "linux_man_pages",
        "documents": 4368,
        "license": "Various (GPL, BSD, MIT)",
        "license_url": "https://www.kernel.org/doc/man-pages/licenses.html",
        "upstream": "https://www.kernel.org/doc/man-pages/",
        "attribution": "Per-page; see the LICENSE section at the bottom of each man page.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "tldr_pages",
        "documents": 7049,
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/legalcode",
        "upstream": "https://tldr.sh/",
        "attribution": "TLDR pages content licensed under CC BY 4.0, © TLDR contributors.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "common_tools",
        "documents": 68,
        "license": "Various (permissive)",
        "license_url": "",
        "upstream": "Per-project (git, docker, aws-cli, etc.)",
        "attribution": "Per upstream project.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "linux_system_docs",
        "documents": 243,
        "license": "Various (permissive, CC BY-SA)",
        "license_url": "",
        "upstream": "Per-project (systemd, kernel, etc.)",
        "attribution": "Per upstream project.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "vendor_and_distro_docs",
        "documents": 82,
        "license": "Various (permissive)",
        "license_url": "",
        "upstream": "Docker, Kubernetes, Helm, NVIDIA, Ubuntu",
        "attribution": "Per upstream project.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "macos_homebrew",
        "documents": 8777,
        "license": "BSD-2-Clause",
        "license_url": "https://opensource.org/licenses/BSD-2-Clause",
        "upstream": "https://docs.brew.sh/",
        "attribution": "Homebrew content © Homebrew contributors, licensed under BSD-2-Clause.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "macos_man_pages",
        "documents": 5280,
        "license": "Various (BSD, APSL 2.0)",
        "license_url": "https://opensource.org/licenses/APSL-2.0.php",
        "upstream": "macOS system /usr/share/man/",
        "attribution": "BSD pages: © The Regents of the University of California. Apple pages: © Apple Inc., under APSL 2.0.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "macos_support",
        "documents": 104,
        "license": "CC BY-NC 4.0 (SS64), Halbert (synthetic)",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/legalcode",
        "upstream": "https://ss64.com/mac/",
        "attribution": "SS64 content © Simon Sheppard, licensed under CC BY-NC 4.0 (non-commercial).",
        "mac_build": True,
        "commercial_ok": False,
    },
    {
        "name": "macos_ask_different",
        "documents": 269,
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
        "upstream": "https://apple.stackexchange.com/",
        "attribution": "Ask Different content © Stack Exchange Inc. and contributors, under CC BY-SA 4.0. Link to original question and author profile required.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "macos_macports_guide",
        "documents": 10,
        "license": "BSD-like (MacPorts Project)",
        "license_url": "",
        "upstream": "https://guide.macports.org/",
        "attribution": "MacPorts Guide © The MacPorts Project.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "freebsd_handbook",
        "documents": 41,
        "license": "FreeBSD Documentation License",
        "license_url": "https://www.freebsd.org/copyright/freebsd-doc-license/",
        "upstream": "https://docs.freebsd.org/en/books/handbook/",
        "attribution": "FreeBSD Handbook © The FreeBSD Documentation Project.",
        "mac_build": True,
        "commercial_ok": True,
    },
    {
        "name": "freebsd_man_pages",
        "documents": 181,
        "license": "FreeBSD Documentation License",
        "license_url": "https://www.freebsd.org/copyright/freebsd-doc-license/",
        "upstream": "https://www.freebsd.org/cgi/man.cgi",
        "attribution": "FreeBSD man pages © The FreeBSD Documentation Project.",
        "mac_build": True,
        "commercial_ok": True,
    },
]

# Software dependencies summary (subset of THIRD-PARTY-LICENSES.md §3).
_SOFTWARE_DEPS: List[Dict[str, Any]] = [
    {"name": "fastapi", "license": "MIT", "purpose": "HTTP API framework", "language": "python"},
    {"name": "uvicorn", "license": "BSD-3-Clause", "purpose": "ASGI server", "language": "python"},
    {"name": "pydantic", "license": "MIT", "purpose": "Data validation", "language": "python"},
    {"name": "chromadb", "license": "Apache 2.0", "purpose": "Vector database (legacy RAG path)", "language": "python"},
    {"name": "sentence-transformers", "license": "Apache 2.0", "purpose": "Embedding models (legacy RAG path)", "language": "python"},
    {"name": "apscheduler", "license": "MIT", "purpose": "Background job scheduling", "language": "python"},
    {"name": "requests", "license": "Apache 2.0", "purpose": "HTTP client", "language": "python"},
    {"name": "tauri", "license": "Apache 2.0 / MIT", "purpose": "Desktop application shell", "language": "rust"},
    {"name": "sysinfo", "license": "MIT", "purpose": "System information collection", "language": "rust"},
    {"name": "react", "license": "MIT", "purpose": "UI framework", "language": "typescript"},
    {"name": "vite", "license": "MIT", "purpose": "Build tooling", "language": "typescript"},
    {"name": "tailwindcss", "license": "MIT", "purpose": "Utility CSS", "language": "typescript"},
    {"name": "radix-ui", "license": "MIT", "purpose": "Headless UI primitives", "language": "typescript"},
    {"name": "monaco-editor", "license": "MIT", "purpose": "Code editor", "language": "typescript"},
    {"name": "xterm", "license": "MIT", "purpose": "Terminal emulator", "language": "typescript"},
    {"name": "lucide-react", "license": "ISC", "purpose": "Icon set", "language": "typescript"},
]

# Foundation model attribution notices (THIRD-PARTY-LICENSES.md §5).
_FOUNDATION_MODELS: List[Dict[str, Any]] = [
    {"name": "Meta Llama 3.1", "license": "Llama 3.1 Community License", "notice": "Built with Llama 3.1."},
    {"name": "DeepSeek", "license": "DeepSeek License", "notice": "Powered by DeepSeek."},
    {"name": "Qwen", "license": "Apache 2.0 / Tongyi Qianwen License", "notice": "Powered by Qwen."},
    {"name": "nomic-embed-text-v1.5", "license": "Apache 2.0", "notice": "Embeddings by Nomic AI."},
]


def _acceptance_file() -> Path:
    return Path(get_data_dir()) / "accepted_disclaimer.txt"


@router.get("/notices")
async def get_notices() -> Dict[str, Any]:
    """Structured third-party license manifest for the dashboard UI."""
    return {
        "project": {
            "name": "Halbert",
            "license": "GNU General Public License v3.0",
            "license_url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
            "copyright": "(C) 2024-2026 Eric Bintner and Halbert Contributors",
            "source": "https://github.com/EricBintner/Halbert",
        },
        "rag_sources": _RAG_SOURCES,
        "software_dependencies": _SOFTWARE_DEPS,
        "foundation_models": _FOUNDATION_MODELS,
        "legal_docs": {
            "license": "documentation/legal/LICENSE.md",
            "third_party_licenses": "documentation/legal/THIRD-PARTY-LICENSES.md",
            "privacy": "documentation/legal/PRIVACY.md",
            "disclaimer": "documentation/legal/DISCLAIMER.md",
            "trademarks": "documentation/legal/TRADEMARKS.md",
            "security": "documentation/legal/SECURITY.md",
        },
    }


@router.get("/disclaimer")
async def get_disclaimer() -> Dict[str, Any]:
    """Return the current disclaimer version and whether the user has accepted it."""
    acc_path = _acceptance_file()
    accepted = False
    accepted_at = None
    accepted_version = None
    if acc_path.exists():
        try:
            payload = json.loads(acc_path.read_text())
            accepted = payload.get("version") == _DISCLAIMER_VERSION
            accepted_at = payload.get("accepted_at")
            accepted_version = payload.get("version")
        except Exception:
            accepted = False
    return {
        "version": _DISCLAIMER_VERSION,
        "accepted": accepted,
        "accepted_at": accepted_at,
        "accepted_version": accepted_version,
        "doc_path": "documentation/legal/DISCLAIMER.md",
    }


class AcceptDisclaimer(BaseModel):
    version: str


@router.post("/disclaimer/accept")
async def accept_disclaimer(body: AcceptDisclaimer) -> Dict[str, Any]:
    """Record user acceptance of the disclaimer. Persisted to the data dir."""
    acc_path = _acceptance_file()
    acc_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": body.version or _DISCLAIMER_VERSION,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }
    acc_path.write_text(json.dumps(payload, indent=2))
    logger.info("Disclaimer accepted (version=%s)", payload["version"])
    return {"ok": True, **payload}


@router.get("/cloud-disclosure")
async def get_cloud_disclosure() -> Dict[str, Any]:
    """Return the cloud API data-flow disclosure text for the consent modal."""
    return {
        "title": "Cloud Model Data Flow Disclosure",
        "summary": (
            "Enabling a cloud model provider sends your chat messages and the "
            "assembled context for each turn — which may include excerpts of "
            "your system profile, configuration files, service state, log "
            "snippets, and retrieved RAG chunks — to the configured provider. "
            "Do not enable cloud models on systems processing sensitive, "
            "regulated, or restricted data."
        ),
        "what_is_sent": [
            "Your chat message for the turn",
            "The assembled context (system profile, config excerpts, log snippets, RAG chunks)",
            "The system prompt and persona instructions in effect",
        ],
        "what_is_not_sent": [
            "Your full filesystem",
            "Your full memory history (only the current turn's context window)",
            "Credentials, API keys, or secrets (filtered by safety adapters)",
            "Anything from turns that use a local model",
        ],
        "provider_policies": {
            "OpenAI": "https://openai.com/policies/privacy-policy",
            "Anthropic": "https://www.anthropic.com/legal/privacy",
            "Google": "https://policies.google.com/privacy",
        },
        "privacy_doc": "documentation/legal/PRIVACY.md",
    }
