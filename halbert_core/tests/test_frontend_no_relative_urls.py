"""
Static guard: the dashboard frontend must not use bare relative URLs for
fetch/EventSource/WebSocket/<img src>. Inside the Tauri webview (origin
tauri://localhost) relative URLs resolve against the asset protocol and 404;
every backend URL must go through src/lib/apiBase.ts (apiUrl/wsUrl/apiBase).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "halbert_core/halbert_core/dashboard/frontend/src"

# Files allowed to build URLs themselves.
EXCLUDED = {
    "lib/apiBase.ts",              # the resolver itself
    "hooks/useSourcePrepDaemon.ts",  # talks to the external SourcePrep daemon (absolute URL)
}

# Backend route prefixes served by app.py (see vite.config.ts proxy list).
_PREFIX = r"(?:api|llm|ws|global|embedding)(?:/|['\"`?])"

PATTERNS = [
    re.compile(r"""fetch\(\s*['"`]/"""),                  # fetch('/api/..'), fetch(`/api/..`)
    re.compile(r"""EventSource\(\s*['"`]"""),             # new EventSource('/api/..') / (`http..`)
    re.compile(r"""new WebSocket\(\s*['"`]"""),           # new WebSocket('ws://..') / (`ws://${location.host}..`)
    re.compile(r"""API_BASE\s*=\s*['"`]"""),              # const API_BASE = '/api' | ''
    re.compile(r"""window\.location\.host"""),            # ws://${window.location.host}
    re.compile(r"""=\s*['"`]/""" + _PREFIX),              # const url = '/api/..' | `/llm/..`
    re.compile(r"""src=\{\s*['"`]/""" + _PREFIX),         # <img src={`/api/..`}>
    re.compile(r"""src=['"]/""" + _PREFIX),               # <img src="/api/..">
]


def _sources():
    for p in FRONTEND_SRC.rglob("*"):
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"} and p.is_file():
            rel = p.relative_to(FRONTEND_SRC).as_posix()
            if rel not in EXCLUDED:
                yield rel, p


def _hits():
    hits = []
    for rel, p in _sources():
        for lineno, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            for pat in PATTERNS:
                if pat.search(line):
                    hits.append(f"{rel}:{lineno}: {line.strip()}")
                    break
    return hits


def test_frontend_src_exists():
    assert FRONTEND_SRC.is_dir()
    assert (FRONTEND_SRC / "lib" / "apiBase.ts").is_file()


def test_patterns_catch_known_shapes():
    """Self-check so a regex regression cannot silently turn the guard green."""
    samples = [
        "fetch('/api/x')",
        "fetch(`/api/agent/cancel/${id}`, { method: 'POST' })",
        "new EventSource('/api/agent/stream')",
        "new WebSocket(`ws://${window.location.host}/ws/t`)",
        "const API_BASE = '/api'",
        "const url = `/api/agent/confirm/${id}`;",
        "const u = '/llm/slots/status'",
        "path = '/ws/terminal'",
        "x = '/global/config'",
        "y = `/embedding/download`",
        "src={`/api/discoveries/icon?path=${p}`}",
        'src="/api/discoveries/icon"',
    ]
    for s in samples:
        assert any(p.search(s) for p in PATTERNS), s
    # Non-backend strings must not trip the guard.
    for s in ["navigate('/apps')", "const p = '/settings'", "src={`/assets/x.png`}"]:
        assert not any(p.search(s) for p in PATTERNS), s


def test_no_bare_relative_backend_urls():
    hits = _hits()
    assert not hits, "bare relative backend URLs (route through @/lib/apiBase):\n" + "\n".join(hits)
