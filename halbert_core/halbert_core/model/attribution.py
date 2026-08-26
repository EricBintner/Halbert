# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Model licence notices, derived from the licence text a model ships with.

Halbert neither bundles nor recommends models. Whatever the user has installed,
the runtime that serves it already carries the licence: Ollama returns it from
``POST /api/show`` (``license`` field, the verbatim text the publisher attached
to the weights). This module reads that text and extracts what Halbert has to
surface — the licence name, any user-facing display notice the licence asks
for (some community licences require a fixed phrase on a related UI or
documentation page), the sentence a NOTICE file must carry when the weights are
redistributed, and whether the licence is non-commercial.

Nothing here names a model. Detection is by licence *wording*, so a model
released tomorrow under an existing licence family is handled without a code
change, and a model under an unknown licence still gets its title reported.

Consumers:

* ``halbert_core.dashboard.routes.llm`` — ``license`` / ``license_id`` /
  ``attribution`` fields on ``POST /api/llm/proxy/models`` entries
* ``Halbert/main.py`` — ``halbert model-list-all`` / ``model-router-status``
* the dashboard "About / Legal Notices" panel (see LEG-MOD-01)
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Optional

__all__ = [
    "LicenseInfo",
    "classify_license_text",
    "fetch_ollama_license",
    "license_for_ollama_model",
    "provider_terms",
    "notices_for",
    "as_dict",
    "default_ollama_url",
]


@dataclass(frozen=True)
class LicenseInfo:
    """What a model licence asks of Halbert and its users."""

    name: str
    """Licence name as the licence text calls itself (e.g. ``"Apache License 2.0"``)."""
    license_id: str
    """SPDX identifier where one exists, otherwise a ``LicenseRef-`` tag."""
    notice: Optional[str] = None
    """Exact user-facing display text the licence requires, or ``None``."""
    notice_file_sentence: Optional[str] = None
    """Sentence a NOTICE file must contain when the weights are redistributed."""
    derived_model_notice: Optional[str] = None
    """Display text required only for models trained/fine-tuned from this one."""
    non_commercial: bool = False
    """True when the licence restricts use to non-commercial / research purposes."""
    acceptable_use_policy: bool = False
    """True when an Acceptable Use Policy is bundled with the licence."""
    license_url: Optional[str] = None
    source: str = "license-text"
    """Where the facts came from: ``license-text`` (runtime-provided) or ``provider``."""


# ── licence-family detection (by wording, never by model name) ───────────────

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.replace("“", '"').replace("”", '"').replace("’", "'")).strip()


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", name).strip("-")


_COMMUNITY_TITLE = re.compile(r"\b([A-Z][A-Z0-9 .]{1,40}?)\s+COMMUNITY LICENSE AGREEMENT\b", re.I)
_RESEARCH_TITLE = re.compile(r"\b([A-Z][A-Za-z0-9 .]{1,40}?)\s+RESEARCH LICENSE(?: AGREEMENT)?\b", re.I)
_LICENSE_AGREEMENT_TITLE = re.compile(r"\b([A-Z][A-Z0-9 .]{1,40}?)\s+LICENSE AGREEMENT\b", re.I)
_TERMS_OF_USE_TITLE = re.compile(r"\b([A-Z][A-Za-z0-9 .]{1,40}?)\s+Terms of Use\b")

# "prominently display "Built with X" on a related website, user interface, ..."
_DISPLAY_CLAUSE = re.compile(r'(?:prominently\s+)?display\s+"([^"]{3,80})"', re.I)
_BUILT_WITH = re.compile(r'"(Built with [^"]{1,60}|Improved using [^"]{1,60})"')
_NOTICE_FILE = re.compile(r'"([^"]{0,60}?is licensed under[^"]{0,200}?All Rights Reserved\.?)"', re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")
_TRAINING_WORDS = re.compile(r"fine[- ]?tun|\btrain|distill|improve an AI model|create.*?AI model", re.I)


def _title_case(s: str) -> str:
    # "LLAMA 3.1" -> "Llama 3.1"; keep acronyms shorter than 4 chars upper-cased.
    out = []
    for w in s.split():
        out.append(w if (w.isupper() and len(w) <= 3) or any(c.isdigit() for c in w) else w.capitalize())
    return " ".join(out)


def _extract_display_notice(norm: str) -> tuple[Optional[str], Optional[str]]:
    """Return (display_notice, derived_model_notice) from the licence wording."""
    display: Optional[str] = None
    derived: Optional[str] = None
    for sentence in _SENTENCE_SPLIT.split(norm):
        m = _DISPLAY_CLAUSE.search(sentence) or _BUILT_WITH.search(sentence)
        if not m:
            continue
        phrase = m.group(1).strip()
        if _TRAINING_WORDS.search(sentence):
            derived = derived or phrase
        else:
            display = display or phrase
    return display, derived


def classify_license_text(text: Optional[str]) -> Optional[LicenseInfo]:
    """Classify a licence text (as returned by the model runtime) into a ``LicenseInfo``.

    Returns ``None`` for empty input. Unknown licences are still returned with
    their title line as ``name`` and ``license_id="LicenseRef-Unknown"`` so the
    UI can at least show *that* a licence exists.
    """
    if not text or not text.strip():
        return None
    norm = _normalize(text)
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:120]

    display, derived = _extract_display_notice(norm)
    nf = _NOTICE_FILE.search(norm)
    notice_file = nf.group(1).strip() if nf else None
    aup = "acceptable use policy" in norm.lower()
    non_commercial = bool(re.search(r"non[- ]commercial (purposes )?only|solely for (non[- ]commercial|research)", norm, re.I))

    name: str
    lic_id: str
    url: Optional[str] = None

    m = _COMMUNITY_TITLE.search(norm)
    if m:
        name = f"{_title_case(m.group(1))} Community License Agreement"
        lic_id = f"LicenseRef-{_slug(_title_case(m.group(1)))}-Community-License"
    elif re.search(r"\bApache License\b.*?\bVersion 2\.0\b", norm, re.I):
        name, lic_id, url = "Apache License 2.0", "Apache-2.0", "https://www.apache.org/licenses/LICENSE-2.0"
    elif re.search(r"\bMIT License\b|Permission is hereby granted, free of charge", norm, re.I):
        name, lic_id, url = "MIT License", "MIT", "https://opensource.org/license/mit"
    elif (m := _RESEARCH_TITLE.search(norm)):
        name = f"{_title_case(m.group(1))} Research License"
        lic_id = f"LicenseRef-{_slug(_title_case(m.group(1)))}-Research-License"
        non_commercial = True
    elif re.search(r"\bGNU GENERAL PUBLIC LICENSE\b", norm, re.I):
        v = re.search(r"Version (\d)", norm)
        ver = v.group(1) if v else "3"
        name, lic_id = f"GNU General Public License v{ver}", f"GPL-{ver}.0-or-later"
        url = "https://www.gnu.org/licenses/"
    elif re.search(r"\bBSD\b", norm) and "Redistribution and use in source and binary forms" in norm:
        clauses = 3 if "Neither the name" in norm else 2
        name, lic_id = f"BSD {clauses}-Clause License", f"BSD-{clauses}-Clause"
    elif re.search(r"Creative Commons", norm, re.I):
        name, lic_id = first_line or "Creative Commons License", "LicenseRef-Creative-Commons"
        non_commercial = non_commercial or bool(re.search(r"NonCommercial|BY-NC", norm))
    elif (m := _TERMS_OF_USE_TITLE.search(norm)):
        name = f"{m.group(1).strip()} Terms of Use"
        lic_id = f"LicenseRef-{_slug(m.group(1))}-Terms-of-Use"
    elif (m := _LICENSE_AGREEMENT_TITLE.search(norm)):
        name = f"{_title_case(m.group(1))} License Agreement"
        lic_id = f"LicenseRef-{_slug(_title_case(m.group(1)))}-License-Agreement"
    else:
        name, lic_id = (first_line or "Unknown licence"), "LicenseRef-Unknown"

    return LicenseInfo(
        name=name,
        license_id=lic_id,
        notice=display,
        notice_file_sentence=notice_file,
        derived_model_notice=derived,
        non_commercial=non_commercial,
        acceptable_use_policy=aup,
        license_url=url,
        source="license-text",
    )


# ── runtime lookups ──────────────────────────────────────────────────────────

def default_ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return "http://localhost:11434"
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def fetch_ollama_license(base_url: str, model: str, timeout: float = 3.0) -> Optional[str]:
    """Return the licence text Ollama attached to ``model`` (``/api/show``), or ``None``."""
    try:
        import requests

        r = requests.post(f"{base_url.rstrip('/')}/api/show", json={"name": model}, timeout=timeout)
        if r.status_code != 200:
            return None
        lic = r.json().get("license")
        if isinstance(lic, list):
            lic = "\n\n".join(str(x) for x in lic)
        return lic if isinstance(lic, str) and lic.strip() else None
    except Exception:
        return None


def license_for_ollama_model(
    base_url: str,
    model: str,
    fetcher: Callable[[str, str], Optional[str]] = fetch_ollama_license,
) -> Optional[LicenseInfo]:
    """Licence facts for a model served by the Ollama endpoint at ``base_url``."""
    return classify_license_text(fetcher(base_url, model))


_PROVIDER_TERMS: Dict[str, LicenseInfo] = {
    "openai": LicenseInfo("OpenAI Terms of Use (hosted service)", "LicenseRef-Provider-Terms",
                          license_url="https://openai.com/policies/terms-of-use/", source="provider"),
    "anthropic": LicenseInfo("Anthropic Commercial Terms of Service (hosted service)", "LicenseRef-Provider-Terms",
                             license_url="https://www.anthropic.com/legal/commercial-terms", source="provider"),
    "google": LicenseInfo("Gemini API Additional Terms of Service (hosted service)", "LicenseRef-Provider-Terms",
                          license_url="https://ai.google.dev/gemini-api/terms", source="provider"),
    "openai-compatible": LicenseInfo("Endpoint operator's terms (hosted or self-hosted API)", "LicenseRef-Provider-Terms",
                                     source="provider"),
    "lm-studio": LicenseInfo("Per-model licence (see the model's page in LM Studio)", "LicenseRef-Provider-Terms",
                             source="provider"),
}


def provider_terms(provider: str) -> Optional[LicenseInfo]:
    """Terms that apply to models reached through a provider that does not expose per-model licences."""
    return _PROVIDER_TERMS.get((provider or "").strip().lower())


# ── helpers ──────────────────────────────────────────────────────────────────

def notices_for(infos: Iterable[Optional[LicenseInfo]]) -> List[str]:
    """De-duplicated display notices for a set of licences, in first-seen order."""
    seen: List[str] = []
    for info in infos:
        if info and info.notice and info.notice not in seen:
            seen.append(info.notice)
    return seen


def as_dict(info: Optional[LicenseInfo]) -> Optional[Dict[str, object]]:
    """JSON-friendly view used by the dashboard API."""
    return None if info is None else asdict(info)
