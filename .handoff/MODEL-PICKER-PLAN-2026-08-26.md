# Independent Halbert Model Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the half-migrated, SourcePrep-shaped model picker with Halbert's own three-slot picker (chat / specialist / vision) backed by one config schema, one store module, and a one-time legacy migration.

**Architecture:** A new `halbert_core/model/llm_config.py` is the only reader/writer of `llm_config` in `models.yml`; it migrates the legacy `orchestrator/specialist/vision/saved_endpoints` keys once and removes them. `model/client.py`, `intake/pipeline.py`, `routes/settings.py`, `routes/llm.py`, `routes/compute.py`, `model/router.py` and the CLI wizard all go through it. The frontend gets a ~150-line `ModelSettings` built on the kept `ModelCard` + a rewritten, trimmed `EndpointManager`; the 1,200-line vendored `AIModelsSettings` and its satellites are deleted.

**Tech Stack:** Python 3.11 / FastAPI / PyYAML / pytest (`cd halbert_core && python -m pytest tests/...`); React 18 / TypeScript / Vite / vitest + Testing Library (`cd halbert_core/halbert_core/dashboard/frontend && npx vitest run ...`, `npm run build`).

**Spec:** `documentation/design/model-picker-independent-2026-08-26.md` — read §4 (schema) and §5.2 (reader/writer table) before starting.

---

## Ground rules for every task

- **Another session edits this checkout concurrently.** Work in a git worktree (superpowers:using-git-worktrees). Never `git add -A` / `git add .`; every commit names its files. Never touch `AIAnalysisPanel.tsx`, `Apps.tsx`, `scripts/corpus_quality_gate.py`, `data/*.json`, `hostConversation.ts`, or `.handoff/HANDOFF-SCOPE-FILTER-*`.
- In a fresh worktree run `cd halbert_core/halbert_core/dashboard/frontend && npm ci` once before any frontend step.
- Commit messages: subject + body only. **No `Co-Authored-By`, no "Generated with" lines** (repo rule).
- Copy rule for every string you add: **never name an AI model** (no "llava", "qwen", "kimi", …) and never write "SourcePrep" in Halbert UI text.
- Never hardcode a colour class (`text-amber-400`); use tokens (`text-warning`, `bg-surface`, `text-text-muted`, …).
- Python tests: run from `halbert_core/` with `python -m pytest` (running from the repo root resolves `halbert_core` as a namespace package and breaks package imports).
- Baseline note: the partial Vision-card work inside the vendored component is already in `main` (`2cf9f01`/`0ebb2db`); do not revert it — Task 10 deletes those files. Two uncommitted hunks in `routes/llm.py` (`"vision_model": {"enabled": False}` default) and `model/client.py` (`vision_model` read) are superseded by Tasks 2–3; overwrite them.

## File map

| File | Responsibility | Task |
|---|---|---|
| `halbert_core/halbert_core/model/llm_config.py` (new) | The store: schema, migration, load/save/update, resolve, endpoint helpers | 1 |
| `halbert_core/tests/conftest.py` (new) | `models_config_dir` fixture — isolates every test from the real models.yml | 1 |
| `halbert_core/tests/test_llm_config_store.py` (new) | Store tests | 1 |
| `halbert_core/halbert_core/model/client.py` | Getters via the store; provider mapping + bearer auth in `call_llm_chat` | 2 |
| `halbert_core/tests/test_model_client.py` (new) | Getter + provider tests | 2 |
| `halbert_core/halbert_core/dashboard/routes/llm.py` | `GET/PUT /llm/config` + proxy routes; stubs deleted | 3 |
| `halbert_core/halbert_core/dashboard/routes/compute.py` | Reads endpoints via the store | 3 |
| `halbert_core/tests/test_llm_routes.py` (new), `tests/test_compute_probe.py` | Route tests | 3 |
| `halbert_core/halbert_core/intake/pipeline.py`, `dashboard/routes/agent.py` | Intake reads `llm_config` slots | 4 |
| `halbert_core/tests/test_intake_pipeline.py` | Fixtures on the new shape | 4 |
| `halbert_core/halbert_core/dashboard/routes/settings.py` | `/model/status` (read-only, new shape), `/model/apply-recommended`, `/model/install` via the store | 5 |
| `halbert_core/tests/test_settings_model_routes.py` (new) | Settings route tests | 5 |
| `halbert_core/halbert_core/model/router.py`, `model/config_wizard.py` | Last legacy reader / writer | 6 |
| `halbert_core/tests/test_model_router_config.py`, `tests/test_config_wizard_schema.py` (new) | | 6 |
| `config/models.yml` | Template on the new schema | 7 |
| `frontend/src/types/llm.ts` | Halbert's `LLMConfig` only | 8 |
| `frontend/src/components/llm/EndpointManager.tsx` | Rewritten: name/provider/url/key, test, badge, disclosure | 8 |
| `frontend/src/hooks/useLLMConfig.ts` | Rewritten: three slots + endpoints, debounced PUT | 8 |
| `frontend/src/components/llm/ModelSettings.tsx`, `QuickSetup.tsx` (+ tests) (new) | The picker | 9 |
| `frontend/src/pages/Settings.tsx`, `components/llm/index.ts`, `vite.config.ts`, deletions | Integration | 10 |
| `documentation/design/unified-model-picker.md`, `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`, `documentation/legal/THIRD-PARTY-LICENSES.md` | Docs | 12 |

(`frontend/` = `halbert_core/halbert_core/dashboard/frontend/`.)

---

### Task 1: The store module

**Files:**
- Create: `halbert_core/tests/conftest.py`
- Create: `halbert_core/halbert_core/model/llm_config.py`
- Create: `halbert_core/tests/test_llm_config_store.py`

- [ ] **Step 1: Add the shared fixture**

`halbert_core/tests/conftest.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared fixtures."""
import pytest

from halbert_core.model.config_locator import ENV_VAR


@pytest.fixture
def models_config_dir(monkeypatch, tmp_path):
    """Point every models.yml reader/writer at an empty temp user config dir.

    Nothing under test may touch the developer's real models.yml.
    """
    user = tmp_path / "user"
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user)
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: tmp_path / "repo")
    monkeypatch.delenv(ENV_VAR, raising=False)
    return user
```

- [ ] **Step 2: Write the failing store tests**

`halbert_core/tests/test_llm_config_store.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""halbert_core.model.llm_config — the single owner of llm_config in models.yml."""
from pathlib import Path

import pytest
import yaml

from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"

# Shape of a real pre-migration user file: legacy top-level keys populated,
# SourcePrep-shaped llm_config slots all disabled, two diverged endpoint lists.
LEGACY_FILE = {
    "compression": {"backend": "lingua", "enabled": True, "threshold": 4000},
    "llm_config": {
        "advanced": {"enforce_cloud_token_safety": True},
        "assignment_mode": "structured",
        "embedding": {"source": "endpoint"},
        "small_model": {"enabled": False},
        "large_model": {"enabled": False},
        "saved_endpoints": [
            {"id": "ep_new", "name": "Ollama", "provider": "ollama", "url": OLLAMA, "cloud_concurrency": 10},
        ],
    },
    "orchestrator": {"model": "guide-a", "endpoint": OLLAMA, "endpoint_id": "d7f68bda",
                     "provider": "ollama", "always_loaded": True},
    "specialist": {"enabled": True, "model": "", "endpoint": OLLAMA},
    "vision": {"model": "", "endpoint": OLLAMA},
    "saved_endpoints": [
        {"id": "d7f68bda", "name": "Local Ollama", "provider": "ollama", "url": OLLAMA, "api_key": "k1"},
        {"id": "8eb82036", "name": "LM Studio", "provider": "openai", "url": "http://192.168.1.5:1234", "api_key": ""},
    ],
}


def _write(user: Path, data: dict) -> Path:
    p = user / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data))
    return p


def _read(user: Path) -> dict:
    return yaml.safe_load((user / "models.yml").read_text())


def test_defaults_when_no_file(models_config_dir):
    assert store.load() == store.default_llm_config()
    assert not (models_config_dir / "models.yml").exists()   # load never creates a file


def test_legacy_orchestrator_becomes_chat_model(models_config_dir):
    _write(models_config_dir, LEGACY_FILE)
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "guide-a"
    assert cfg["chat_model"]["enabled"] is True
    ollama = [e for e in cfg["saved_endpoints"] if e["url"] == OLLAMA]
    assert len(ollama) == 1                     # (provider, url) de-dupe
    assert ollama[0]["id"] == "ep_new"          # llm_config entry keeps its id
    assert ollama[0]["api_key"] == "k1"         # empty key back-filled from legacy
    assert cfg["chat_model"]["endpoint_id"] == "ep_new"
    assert len(cfg["saved_endpoints"]) == 2     # LM Studio entry survives


def test_legacy_specialist_without_model_stays_disabled(models_config_dir):
    _write(models_config_dir, LEGACY_FILE)
    cfg = store.load()
    assert cfg["specialist_model"] == {"enabled": False, "endpoint_id": "", "model": ""}
    assert cfg["vision_model"]["enabled"] is False


def test_legacy_specialist_enabled_flag_and_unknown_url(models_config_dir):
    data = dict(LEGACY_FILE)
    data["specialist"] = {"enabled": False, "model": "big-b", "endpoint": OLLAMA}
    data["vision"] = {"model": "eyes-c", "endpoint": "http://gpu-box:11434"}
    _write(models_config_dir, data)
    cfg = store.load()
    assert cfg["specialist_model"]["model"] == "big-b"
    assert cfg["specialist_model"]["enabled"] is False
    vision = cfg["vision_model"]
    assert vision["enabled"] is True and vision["model"] == "eyes-c"
    created = next(e for e in cfg["saved_endpoints"] if e["id"] == vision["endpoint_id"])
    assert created["url"] == "http://gpu-box:11434"
    assert created["name"] == "Migrated endpoint"


def test_migration_rewrites_file_once_with_backup(models_config_dir):
    path = _write(models_config_dir, LEGACY_FILE)
    store.load()
    on_disk = _read(models_config_dir)
    for key in ("orchestrator", "specialist", "vision", "saved_endpoints"):
        assert key not in on_disk
    for key in ("advanced", "embedding", "small_model", "large_model", "assignment_mode"):
        assert key not in on_disk["llm_config"]
    assert on_disk["compression"]["backend"] == "lingua"      # sibling key untouched
    assert (models_config_dir / "models.yml.bak").exists()
    first = path.read_text()
    store.load()                                               # idempotent
    assert path.read_text() == first


def test_small_large_slots_migrate_only_when_in_use(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"id": "e1", "name": "x", "provider": "ollama", "url": OLLAMA}],
        "small_model": {"enabled": True, "endpoint_id": "e1", "model": "fast-a"},
        "large_model": {"enabled": True, "endpoint_id": "e1", "model": "think-b"},
        "code_model": {"enabled": False},
    }})
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "fast-a"
    assert cfg["specialist_model"]["model"] == "think-b"
    assert "small_model" not in _read(models_config_dir)["llm_config"]


def test_slot_with_unknown_endpoint_is_disabled(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [],
        "chat_model": {"enabled": True, "endpoint_id": "ghost", "model": "m"},
    }})
    assert store.load()["chat_model"]["enabled"] is False


def test_slot_on_non_chat_capable_provider_is_disabled_on_load(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"id": "a1", "name": "Claude", "provider": "anthropic",
                             "url": "https://api.anthropic.com", "api_key": "k"}],
        "chat_model": {"enabled": True, "endpoint_id": "a1", "model": "m"},
    }})
    assert store.load()["chat_model"]["enabled"] is False


def test_update_rejects_non_chat_capable_slot(models_config_dir):
    store.save({"saved_endpoints": [{"id": "g1", "name": "Gemini", "provider": "google",
                                     "url": "https://generativelanguage.googleapis.com", "api_key": "k"}]})
    with pytest.raises(store.SlotProviderError) as exc:
        store.update({"specialist_model": {"enabled": True, "endpoint_id": "g1", "model": "m"}})
    assert exc.value.slot == "specialist_model" and exc.value.provider == "google"
    assert store.load()["specialist_model"]["enabled"] is False


def test_update_merges_and_persists(models_config_dir):
    store.save({"saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}]})
    store.update({"chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"}})
    cfg = store.load()
    assert cfg["chat_model"] == {"enabled": True, "endpoint_id": "e1", "model": "m1"}
    assert cfg["saved_endpoints"][0]["name"] == "Local"


def test_save_strips_legacy_keys_but_keeps_others(models_config_dir):
    _write(models_config_dir, {"orchestrator": {"model": "old"}, "routing": {"complexity_threshold": 3}})
    store.save(store.default_llm_config())
    on_disk = _read(models_config_dir)
    assert "orchestrator" not in on_disk
    assert on_disk["routing"] == {"complexity_threshold": 3}


def test_resolve_and_api_key_for(models_config_dir):
    store.save({
        "saved_endpoints": [{"id": "o1", "name": "OpenAI", "provider": "openai",
                             "url": "https://api.openai.com/v1/", "api_key": "sk-x"}],
        "chat_model": {"enabled": True, "endpoint_id": "o1", "model": "m"},
    })
    assert store.resolve("chat_model") == store.ResolvedModel(
        model="m", url="https://api.openai.com/v1", provider="openai", api_key="sk-x")
    assert store.resolve("vision_model") is None
    assert store.api_key_for("https://api.openai.com/v1") == "sk-x"
    assert store.api_key_for("http://elsewhere") == ""


def test_ensure_ollama_endpoint_creates_once(models_config_dir):
    first = store.ensure_ollama_endpoint()
    second = store.ensure_ollama_endpoint()
    assert first == second
    eps = store.load()["saved_endpoints"]
    assert len(eps) == 1
    assert eps[0]["name"] == "Local Ollama" and eps[0]["url"] == OLLAMA


def test_ensure_local_ollama_endpoint_probes_only_when_empty(models_config_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_probe_ollama", lambda url, timeout: calls.append(url) or True)
    assert store.ensure_local_ollama_endpoint() is True
    assert store.ensure_local_ollama_endpoint() is False   # list no longer empty → no probe
    assert calls == [OLLAMA]


def test_set_slot_and_set_top_level(models_config_dir):
    ep_id = store.ensure_ollama_endpoint()
    store.set_slot("chat_model", "m9", ep_id)
    store.set_top_level("compression", {"backend": "semantic", "enabled": True})
    on_disk = _read(models_config_dir)
    assert on_disk["compression"] == {"backend": "semantic", "enabled": True}
    assert on_disk["llm_config"]["chat_model"] == {"enabled": True, "endpoint_id": ep_id, "model": "m9"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_llm_config_store.py -q`
Expected: `ImportError: cannot import name 'llm_config'` (collection error).

- [ ] **Step 4: Write the store module**

`halbert_core/halbert_core/model/llm_config.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Single owner of the ``llm_config`` section of models.yml.

Every reader and writer of Halbert's model configuration goes through this
module. Nothing else reads ``orchestrator`` / ``specialist`` / ``vision`` or
the SourcePrep-shaped ``small_model`` / ``large_model`` keys — those are
migrated here, once, and removed from the file.

Schema (documentation/design/model-picker-independent-2026-08-26.md §4)::

    llm_config:
      saved_endpoints: [{id, name, provider, url, api_key}]
      chat_model:       {enabled, endpoint_id, model}
      specialist_model: {enabled, endpoint_id, model}
      vision_model:     {enabled, endpoint_id, model}

Callers that change a slot send the whole slot dict (all three keys).
"""
from __future__ import annotations

import copy
import logging
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config_locator import find_models_config, write_models_config

logger = logging.getLogger("halbert.model.llm_config")

CHAT_CAPABLE_PROVIDERS = frozenset({"ollama", "lm-studio", "openai", "openai-compatible"})
SLOTS = ("chat_model", "specialist_model", "vision_model")
LEGACY_KEYS = ("orchestrator", "specialist", "vision", "saved_endpoints")
DROPPED_KEYS = (
    "embedding", "small_model", "large_model", "code_model", "coordinator_model",
    "assignment_mode", "assignment_blocks", "advanced", "compute_nodes",
    "model_context_cache",
)
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class SlotProviderError(ValueError):
    """A slot names an endpoint whose provider the chat runtime cannot call."""

    def __init__(self, slot: str, provider: str):
        super().__init__(f"{slot} uses provider {provider!r}, which is not yet usable for chat")
        self.slot = slot
        self.provider = provider


@dataclass(frozen=True)
class ResolvedModel:
    model: str
    url: str
    provider: str
    api_key: str = ""


def _empty_slot() -> Dict[str, Any]:
    return {"enabled": False, "endpoint_id": "", "model": ""}


def default_llm_config() -> Dict[str, Any]:
    return {
        "saved_endpoints": [],
        "chat_model": _empty_slot(),
        "specialist_model": _empty_slot(),
        "vision_model": _empty_slot(),
    }


def _new_id() -> str:
    return f"ep_{secrets.token_hex(4)}"


# ── File I/O ──────────────────────────────────────────────────────


def _read_path() -> Optional[Path]:
    return find_models_config(include_repo=False)


def _write_path() -> Path:
    return write_models_config()


def _read_raw() -> Dict[str, Any]:
    path = _read_path()
    if path is None:
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:  # unreadable YAML: serve defaults, never rewrite
        logger.error("Could not read %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(data: Dict[str, Any]) -> None:
    """Write via a temp file + atomic rename so a crash never leaves a half file."""
    path = _write_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".models-", suffix=".yml", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup_before_rewrite() -> None:
    """Copy models.yml to models.yml.bak when about to rewrite the file that was read."""
    target = _write_path()
    source = _read_path()
    if source is not None and source == target and target.exists():
        shutil.copy2(target, target.with_name(target.name + ".bak"))


# ── Normalisation ─────────────────────────────────────────────────


def _clean_endpoint(ep: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(ep, dict) or not ep.get("url"):
        return None
    url = str(ep["url"]).strip().rstrip("/")
    return {
        "id": str(ep.get("id") or "").strip() or _new_id(),
        "name": str(ep.get("name") or url),
        "provider": str(ep.get("provider") or "ollama"),
        "url": url,
        "api_key": str(ep.get("api_key") or ""),
    }


def normalise(llm: Any) -> Dict[str, Any]:
    """Coerce any llm_config-shaped dict onto the schema. Pure.

    Unknown keys are dropped. A slot is enabled only when it has a model and
    names an existing, chat-capable endpoint; anything else is disabled with a
    warning (hand-edited files get the same treatment as the UI).
    """
    src = llm if isinstance(llm, dict) else {}
    cfg = default_llm_config()
    endpoints: List[Dict[str, Any]] = []
    seen: set = set()
    for raw_ep in src.get("saved_endpoints") or []:
        ep = _clean_endpoint(raw_ep)
        if ep is None or ep["id"] in seen:
            continue
        seen.add(ep["id"])
        endpoints.append(ep)
    cfg["saved_endpoints"] = endpoints
    by_id = {e["id"]: e for e in endpoints}
    for slot in SLOTS:
        raw = src.get(slot)
        raw = raw if isinstance(raw, dict) else {}
        model = str(raw.get("model") or "").strip()
        endpoint_id = str(raw.get("endpoint_id") or "").strip()
        enabled = bool(raw.get("enabled", bool(model))) and bool(model)
        if enabled and endpoint_id not in by_id:
            logger.warning("%s references unknown endpoint %r; slot disabled", slot, endpoint_id)
            enabled = False
        if enabled and by_id[endpoint_id]["provider"] not in CHAT_CAPABLE_PROVIDERS:
            logger.warning("%s uses provider %r which is not chat-capable; slot disabled",
                           slot, by_id[endpoint_id]["provider"])
            enabled = False
        cfg[slot] = {"enabled": enabled, "endpoint_id": endpoint_id, "model": model}
    return cfg


# ── Legacy migration ──────────────────────────────────────────────


def _match_endpoint(endpoints: List[Dict[str, Any]], endpoint_id: Any, url: Any,
                    provider: str) -> Optional[Dict[str, Any]]:
    if endpoint_id:
        for ep in endpoints:
            if ep["id"] == endpoint_id:
                return ep
    u = str(url or "").strip().rstrip("/")
    if u:
        for ep in endpoints:
            if ep["url"] == u and ep["provider"] == provider:
                return ep
        for ep in endpoints:
            if ep["url"] == u:
                return ep
    return None


def needs_migration(raw: Dict[str, Any]) -> bool:
    if any(k in raw for k in LEGACY_KEYS):
        return True
    llm = raw.get("llm_config")
    return isinstance(llm, dict) and any(k in llm for k in DROPPED_KEYS)


def migrate_legacy(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Fold legacy top-level keys into an llm_config dict. Pure; does not write.

    Precedence: an llm_config slot already enabled with a model wins; legacy
    keys only fill empty slots. Endpoints are the union of both lists,
    de-duplicated by (provider, url); on a duplicate the llm_config entry keeps
    its id and an empty api_key is back-filled from the legacy entry.
    """
    llm = copy.deepcopy(raw.get("llm_config") or {})
    if not isinstance(llm, dict):
        llm = {}
    endpoints: List[Dict[str, Any]] = []

    def _add(raw_ep: Any) -> None:
        ep = _clean_endpoint(raw_ep)
        if ep is None:
            return
        for existing in endpoints:
            if existing["url"] == ep["url"] and existing["provider"] == ep["provider"]:
                if not existing["api_key"] and ep["api_key"]:
                    existing["api_key"] = ep["api_key"]
                return
        endpoints.append(ep)

    for raw_ep in llm.get("saved_endpoints") or []:
        _add(raw_ep)
    for raw_ep in raw.get("saved_endpoints") or []:
        _add(raw_ep)
    llm["saved_endpoints"] = endpoints

    def _fold(target: str, legacy: Any, enabled: bool) -> None:
        legacy = legacy if isinstance(legacy, dict) else {}
        current = llm.get(target) if isinstance(llm.get(target), dict) else {}
        if current.get("enabled") and current.get("model"):
            return
        model = str(legacy.get("model") or "").strip()
        if not model:
            return
        provider = str(legacy.get("provider") or "ollama")
        ep = _match_endpoint(endpoints, legacy.get("endpoint_id"), legacy.get("endpoint"), provider)
        if ep is None:
            ep = {
                "id": _new_id(),
                "name": "Migrated endpoint",
                "provider": provider,
                "url": str(legacy.get("endpoint") or DEFAULT_OLLAMA_URL).rstrip("/"),
                "api_key": "",
            }
            endpoints.append(ep)
        llm[target] = {"enabled": enabled, "endpoint_id": ep["id"], "model": model}

    specialist = raw.get("specialist") if isinstance(raw.get("specialist"), dict) else {}
    _fold("chat_model", raw.get("orchestrator"), True)
    _fold("specialist_model", specialist, bool(specialist.get("enabled", False)))
    _fold("vision_model", raw.get("vision"), True)
    # SourcePrep-shaped slots: migrate only when they were actually in use.
    for source, target in (("small_model", "chat_model"), ("large_model", "specialist_model")):
        s = llm.get(source)
        if isinstance(s, dict) and s.get("enabled") and s.get("model"):
            _fold(target, {"model": s.get("model"), "endpoint_id": s.get("endpoint_id")}, True)
    for key in DROPPED_KEYS:
        llm.pop(key, None)
    return llm


def normalise_file(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Whole models.yml dict with llm_config migrated + normalised and legacy keys removed. Pure."""
    out = {k: copy.deepcopy(v) for k, v in raw.items() if k not in LEGACY_KEYS}
    out["llm_config"] = normalise(migrate_legacy(raw) if needs_migration(raw) else raw.get("llm_config"))
    return out


# ── Public API ────────────────────────────────────────────────────


def load_file() -> Dict[str, Any]:
    """The whole models.yml dict, post-migration. Rewrites the file once when legacy keys are found."""
    raw = _read_raw()
    out = normalise_file(raw)
    if needs_migration(raw):
        try:
            _backup_before_rewrite()
            _write_raw(out)
            llm = out["llm_config"]
            logger.info(
                "Migrated legacy model config: chat=%r specialist=%r vision=%r endpoints=%d",
                llm["chat_model"]["model"], llm["specialist_model"]["model"],
                llm["vision_model"]["model"], len(llm["saved_endpoints"]),
            )
        except Exception as e:
            logger.error("Could not rewrite models.yml after migration: %s", e)
    return out


def load() -> Dict[str, Any]:
    """The llm_config section, normalised."""
    return load_file()["llm_config"]


def save(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace llm_config in the file; legacy keys are dropped, every other key is kept."""
    raw = _read_raw()
    for key in LEGACY_KEYS:
        raw.pop(key, None)
    raw["llm_config"] = normalise(llm_config)
    _write_raw(raw)
    return raw["llm_config"]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, val in override.items():
        if isinstance(base.get(key), dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def update(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge ``partial`` into the current config and save.

    Raises SlotProviderError when a slot with a model names an endpoint whose
    provider is not chat-capable — the UI must never save such a slot.
    """
    merged = _deep_merge(load(), copy.deepcopy(partial))
    endpoints = {e["id"]: e for e in normalise(merged)["saved_endpoints"]}
    for slot in SLOTS:
        s = merged.get(slot) if isinstance(merged.get(slot), dict) else {}
        ep = endpoints.get(str(s.get("endpoint_id") or ""))
        if s.get("model") and ep is not None and ep["provider"] not in CHAT_CAPABLE_PROVIDERS:
            raise SlotProviderError(slot, ep["provider"])
    return save(merged)


def set_slot(slot: str, model: str, endpoint_id: str) -> Dict[str, Any]:
    return update({slot: {"enabled": bool(model), "endpoint_id": endpoint_id, "model": model}})


def set_top_level(key: str, value: Any) -> None:
    """Write a non-llm_config key (e.g. ``compression``) without disturbing llm_config."""
    raw = _read_raw()
    llm = normalise(migrate_legacy(raw) if needs_migration(raw) else raw.get("llm_config"))
    for legacy in LEGACY_KEYS:
        raw.pop(legacy, None)
    raw["llm_config"] = llm
    raw[key] = value
    _write_raw(raw)


def resolve_from(file_cfg: Dict[str, Any], slot: str) -> Optional[ResolvedModel]:
    """Resolve a slot against an already-loaded (normalised) models.yml dict."""
    llm = file_cfg.get("llm_config") or {}
    s = llm.get(slot) or {}
    if not s.get("enabled"):
        return None
    for ep in llm.get("saved_endpoints") or []:
        if ep.get("id") == s.get("endpoint_id"):
            return ResolvedModel(model=s["model"], url=ep["url"], provider=ep["provider"],
                                 api_key=ep.get("api_key") or "")
    return None


def resolve(slot: str) -> Optional[ResolvedModel]:
    """(model, url, provider, api_key) for an enabled slot, else None."""
    return resolve_from(load_file(), slot)


def api_key_for(url: str) -> str:
    """API key of the first saved endpoint whose url matches, else ""."""
    u = str(url or "").rstrip("/")
    for ep in load()["saved_endpoints"]:
        if ep["url"] == u and ep["api_key"]:
            return ep["api_key"]
    return ""


def ensure_ollama_endpoint(url: str = DEFAULT_OLLAMA_URL) -> str:
    """Id of the Ollama endpoint at ``url``; creates "Local Ollama" if absent."""
    cfg = load()
    u = url.rstrip("/")
    for ep in cfg["saved_endpoints"]:
        if ep["provider"] == "ollama" and ep["url"] == u:
            return ep["id"]
    ep = {"id": _new_id(), "name": "Local Ollama", "provider": "ollama", "url": u, "api_key": ""}
    cfg["saved_endpoints"].append(ep)
    save(cfg)
    return ep["id"]


def _probe_ollama(url: str, timeout: float) -> bool:
    try:
        import requests
        return requests.get(f"{url}/api/tags", timeout=timeout).status_code == 200
    except Exception:
        return False


def ensure_local_ollama_endpoint(timeout: float = 2.0) -> bool:
    """Fresh install helper: with no endpoints saved, add Local Ollama if :11434 answers."""
    if load()["saved_endpoints"]:
        return False
    if not _probe_ollama(DEFAULT_OLLAMA_URL, timeout):
        return False
    ensure_ollama_endpoint(DEFAULT_OLLAMA_URL)
    return True
```

- [ ] **Step 5: Run the store tests**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_llm_config_store.py -q`
Expected: `16 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/model/llm_config.py halbert_core/tests/conftest.py halbert_core/tests/test_llm_config_store.py
git commit -m "feat(model): add the llm_config store with one-time legacy migration

model/llm_config.py is the single owner of llm_config in models.yml:
chat/specialist/vision slots plus saved_endpoints. Legacy
orchestrator/specialist/vision/saved_endpoints keys and the SourcePrep-
shaped slots are folded in once (with a .bak) and removed."
```

---

### Task 2: `model/client.py` reads only the store; providers map to real APIs

**Files:**
- Modify: `halbert_core/halbert_core/model/client.py`
- Create: `halbert_core/tests/test_model_client.py`

- [ ] **Step 1: Write the failing tests**

`halbert_core/tests/test_model_client.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""model.client resolves models only through model.llm_config and maps providers to APIs."""
from contextlib import contextmanager

import pytest
import requests
import yaml

from halbert_core.model import client
from halbert_core.model import llm_config as store


def _resolved(model="m", url="http://ep.test", provider="ollama", api_key=""):
    return store.ResolvedModel(model=model, url=url, provider=provider, api_key=api_key)


def test_getters_read_chat_slot(monkeypatch):
    monkeypatch.setattr(store, "resolve", lambda slot: _resolved() if slot == "chat_model" else None)
    assert client.get_configured_model() == "m"
    assert client.get_ollama_endpoint() == "http://ep.test"
    assert client.get_specialist_model() == (None, None, None)
    assert client.get_vision_model() == (None, "http://ep.test")


def test_getters_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(store, "resolve", lambda slot: None)
    assert client.get_configured_model() == ""
    assert client.get_ollama_endpoint() == store.DEFAULT_OLLAMA_URL


def test_specialist_and_vision_tuples(monkeypatch):
    table = {
        "chat_model": _resolved("chat", "http://a"),
        "specialist_model": _resolved("spec", "http://b", "openai", "sk"),
        "vision_model": _resolved("eyes", "http://c"),
    }
    monkeypatch.setattr(store, "resolve", lambda slot: table.get(slot))
    assert client.get_specialist_model() == ("spec", "http://b", "openai")
    assert client.get_vision_model() == ("eyes", "http://c")


def test_legacy_file_is_migrated_not_read_directly(models_config_dir):
    p = models_config_dir / "models.yml"
    p.parent.mkdir(parents=True)
    p.write_text(yaml.safe_dump({"orchestrator": {"model": "legacy-m", "endpoint": "http://localhost:11434"}}))
    assert client.get_configured_model() == "legacy-m"
    assert "orchestrator" not in yaml.safe_load(p.read_text())


class _Resp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def capture(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers or {})
        if "/chat/completions" in url:
            return _Resp({"choices": [{"message": {"content": "hi"}}]})
        return _Resp({"message": {"content": "hi"}})

    @contextmanager
    def no_lock(timeout_s=0.0):
        yield True

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(client, "llm_advisory_lock", no_lock)
    monkeypatch.setattr(store, "api_key_for", lambda url: "sk-from-store")
    return seen


@pytest.mark.parametrize("provider", ["openai", "openai-compatible", "lm-studio"])
def test_openai_style_providers_hit_v1_with_bearer(capture, provider):
    out = client.call_llm_chat("http://host:1234", "m", [{"role": "user", "content": "x"}], provider=provider)
    assert out["content"] == "hi"
    assert capture["url"] == "http://host:1234/v1/chat/completions"
    assert capture["headers"] == {"Authorization": "Bearer sk-from-store"}


def test_v1_suffix_not_doubled_and_explicit_key_wins(capture):
    client.call_llm_chat("https://api.openai.com/v1/", "m", [], provider="openai", api_key="explicit")
    assert capture["url"] == "https://api.openai.com/v1/chat/completions"
    assert capture["headers"] == {"Authorization": "Bearer explicit"}


def test_ollama_provider_uses_api_chat_without_auth(capture):
    client.call_llm_chat("http://localhost:11434", "m", [], provider="ollama")
    assert capture["url"] == "http://localhost:11434/api/chat"
    assert capture["headers"] == {}


@pytest.mark.parametrize("provider", ["anthropic", "google", "azure-openai"])
def test_unsupported_providers_raise_before_any_request(capture, provider):
    with pytest.raises(client.UnsupportedProviderError):
        client.call_llm_chat("https://x", "m", [], provider=provider)
    assert "url" not in capture
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_model_client.py -q`
Expected: failures such as `AttributeError: module 'halbert_core.model.client' has no attribute 'UnsupportedProviderError'` and getters still reading the old loader.

- [ ] **Step 3: Replace the config section of `client.py`**

In `halbert_core/halbert_core/model/client.py`, delete everything from the line `# ── Unified LLMConfig loader ────────────────────────────────────` through the end of `get_vision_model()` (the line `return (model, endpoint)` just before `def call_llm_chat(`). That removes `_load_models_config`, `_resolve_endpoint`, `_get_slot_config` and the four getters. Insert in their place:

```python
# ── Model resolution (single source: model.llm_config) ──────────

from . import llm_config as _store

_OLLAMA_STYLE = frozenset({"ollama", "llamacpp", "mlx"})           # POST {url}/api/chat
_OPENAI_STYLE = frozenset({"openai", "openai-compatible", "lm-studio"})  # POST {url}/v1/chat/completions
_LOCAL_PROVIDERS = frozenset({"ollama", "lm-studio", "llamacpp", "mlx"})  # share the GPU lock


class UnsupportedProviderError(RuntimeError):
    """The endpoint's provider can list and test models but is not yet usable for chat."""


def get_ollama_endpoint() -> str:
    """URL of the chat model's endpoint (local Ollama when nothing is configured)."""
    chat = _store.resolve("chat_model")
    return chat.url if chat else _store.DEFAULT_OLLAMA_URL


def get_configured_model() -> str:
    """Chat model name, or "" when none is configured.

    Callers must treat "" as "not configured" and surface a clear error
    (choose a model in Settings -> AI Models) instead of posting model="".
    """
    chat = _store.resolve("chat_model")
    return chat.model if chat else ""


def get_specialist_model() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(model, endpoint_url, provider) for the specialist slot, or (None, None, None)."""
    spec = _store.resolve("specialist_model")
    if spec is None:
        logger.debug("Specialist not configured")
        return (None, None, None)
    logger.info(f"Specialist enabled: {spec.model} at {spec.url} (provider: {spec.provider})")
    return (spec.model, spec.url, spec.provider)


def get_vision_model() -> Tuple[Optional[str], str]:
    """(model, endpoint_url) for the vision slot; model is None when unset.

    Callers fall back to the chat model for images when model is None.
    """
    vis = _store.resolve("vision_model")
    if vis is None:
        return (None, get_ollama_endpoint())
    logger.info(f"Vision enabled: {vis.model} at {vis.url}")
    return (vis.model, vis.url)


def _openai_base(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"
```

- [ ] **Step 4: Thread `api_key` and the provider mapping through `call_llm_chat`**

Replace the signature and the first lines of `call_llm_chat` (everything down to and including `options = options or {}`):

```python
def call_llm_chat(
    endpoint: str,
    model: str,
    messages: list,
    provider: str = "ollama",
    stream: bool = False,
    timeout: int = 180,
    options: dict = None,
    tools: list = None,
    api_key: Optional[str] = None,
) -> dict:
    """Call LLM with correct API format based on provider.

    Args:
        endpoint: Base URL (e.g., http://localhost:11434)
        model: Model name
        messages: List of message dicts with 'role' and 'content'
        provider: 'ollama' | 'llamacpp' | 'mlx' (Ollama API) or
            'openai' | 'openai-compatible' | 'lm-studio' (OpenAI chat API)
        stream: Whether to stream response
        timeout: Request timeout in seconds
        options: Provider-specific options (temperature, max_tokens, etc.)
        tools: Optional OpenAI-style tool schemas
            (``[{"type": "function", "function": {...}}]``). Sent to the model
            when non-empty; models that reject them fall back to a plain call.
        api_key: Bearer token for OpenAI-style providers. When None it is
            looked up from the saved endpoint whose url matches ``endpoint``.

    Returns:
        Dict with 'content' (response text), 'tool_calls' (normalised list,
        see :func:`_normalise_tool_calls`) and 'raw' (full response)

    Raises:
        UnsupportedProviderError: anthropic / google / azure-openai endpoints
            can be listed and tested but cannot be called for chat yet.
    """
    options = options or {}
    if provider not in _OLLAMA_STYLE and provider not in _OPENAI_STYLE:
        raise UnsupportedProviderError(
            f"{provider} endpoints can list and test models but are not yet usable for chat"
        )
    if api_key is None and provider in _OPENAI_STYLE:
        api_key = _store.api_key_for(endpoint)
```

Then, still inside `call_llm_chat`, replace `needs_lock = provider in ("ollama", "llamacpp", "mlx")` with `needs_lock = provider in _LOCAL_PROVIDERS`, and add `api_key` as the last positional argument to **both** `_call_with_tool_fallback(...)` calls:

```python
            return _call_with_tool_fallback(
                endpoint, model, messages, provider, stream, timeout, options, tools, api_key
            )
```

In `_call_with_tool_fallback`, add the parameter `api_key: str = ""` after `tools: list,` and pass `api_key=api_key` to all three `_do_llm_call(...)` calls inside it.

Replace `_do_llm_call` entirely:

```python
def _do_llm_call(
    endpoint: str,
    model: str,
    messages: list,
    provider: str,
    stream: bool,
    timeout: int,
    options: dict,
    tools: list = None,
    api_key: str = "",
) -> dict:
    """Make the actual LLM API call (separated for lock wrapping)."""
    if provider in _OPENAI_STYLE:
        url = f"{_openai_base(endpoint)}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": options.get("temperature", 0.7),
            "max_tokens": options.get(
                "num_predict", options.get("max_tokens", 2048)
            ),
        }
        if tools:
            payload["tools"] = tools
        logger.info(f"Calling OpenAI-compatible API: {url} model={model}")
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content") or ""
        return {
            "content": content.strip(),
            "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
            "raw": data,
        }
    if provider in _OLLAMA_STYLE:
        url = f"{endpoint}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            # Ollama only returns tool_calls on a non-streamed response.
            "stream": False if tools else stream,
        }
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = {
                "num_predict": options.get(
                    "num_predict", options.get("max_tokens", 1024)
                ),
                "temperature": options.get("temperature", 0.7),
            }
        logger.info(f"Calling Ollama API: {url} model={model}")
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {}) or {}
        content = message.get("content") or ""
        return {
            "content": content.strip(),
            "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
            "raw": data,
        }
    raise UnsupportedProviderError(f"{provider} is not yet usable for chat")
```

Finally update the module docstring's "Config schema" paragraph to:

```
Config schema:
  All model resolution goes through model.llm_config (the single owner of
  the 'llm_config' section of models.yml):
    guide (chat)   → llm_config.chat_model
    specialist     → llm_config.specialist_model
    vision         → llm_config.vision_model
  Legacy 'orchestrator'/'specialist'/'vision' keys are migrated by that
  module on first load; nothing here reads them.
```

- [ ] **Step 5: Run the client tests and the suites that touch it**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_model_client.py tests/test_app_seam_model_backend.py tests/test_phase_d_integration.py -q`
Expected: all pass (`test_model_client.py`: 11 passed).

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/model/client.py halbert_core/tests/test_model_client.py
git commit -m "refactor(model): resolve chat/specialist/vision through the llm_config store

The four getters keep their signatures (30+ call sites untouched) but no
longer read legacy keys or SourcePrep slot names. call_llm_chat maps
openai / openai-compatible / lm-studio onto /v1/chat/completions with a
bearer token from the saved endpoint, and refuses providers it cannot
call instead of posting to the Ollama API by accident."
```

---

### Task 3: `/llm/config` routes; delete the SourcePrep stubs

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/llm.py`
- Modify: `halbert_core/halbert_core/dashboard/routes/compute.py:36,67`
- Modify: `halbert_core/tests/test_compute_probe.py`
- Create: `halbert_core/tests/test_llm_routes.py`

- [ ] **Step 1: Write the failing route tests**

`halbert_core/tests/test_llm_routes.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""GET/PUT /llm/config — the picker's config API, a thin layer over model.llm_config."""
import json
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import llm as routes
from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"


def test_get_config_shape(models_config_dir):
    with patch.object(routes.llm_store, "ensure_local_ollama_endpoint", return_value=False):
        out = routes.get_llm_config()
    data = out["data"]
    assert set(data["llm_config"]) == {"saved_endpoints", "chat_model", "specialist_model", "vision_model"}
    assert data["chat_capable_providers"] == ["lm-studio", "ollama", "openai", "openai-compatible"]


def test_put_merges_and_returns_config(models_config_dir):
    body = routes.LLMConfigUpdate(llm_config={
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"},
    })
    out = routes.update_llm_config(body)
    assert out["data"]["llm_config"]["chat_model"]["model"] == "m1"
    assert store.load()["chat_model"]["enabled"] is True


def test_put_rejects_non_chat_capable_provider(models_config_dir):
    store.save({"saved_endpoints": [{"id": "a1", "name": "Claude", "provider": "anthropic",
                                     "url": "https://api.anthropic.com", "api_key": "k"}]})
    resp = routes.update_llm_config(routes.LLMConfigUpdate(llm_config={
        "chat_model": {"enabled": True, "endpoint_id": "a1", "model": "m"},
    }))
    assert resp.status_code == 422
    err = json.loads(resp.body)["error"]
    assert err["code"] == "PROVIDER_NOT_CHAT_CAPABLE" and err["slot"] == "chat_model"
    assert store.load()["chat_model"]["enabled"] is False


def test_sourceprep_stubs_are_gone():
    paths = {r.path for r in routes.router.routes}
    for gone in ("/global/config", "/llm/plan-limits", "/embedding/status", "/embedding/download",
                 "/llm/slots/status", "/api/llm/proxy/cloud-models"):
        assert gone not in paths
    assert {"/llm/config", "/api/llm/proxy/models", "/api/llm/proxy/test", "/api/llm/proxy/test-model"} <= paths
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_llm_routes.py -q`
Expected: `AttributeError: module ... has no attribute 'llm_store'` / `LLMConfigUpdate`.

- [ ] **Step 3: Replace the config section of `routes/llm.py`**

Delete from the line `# ── ConfigStore (YAML-based) ─────────────────────────────────────` through the end of `update_global_config` (its final `return {"data": load_full_ui_config(), "warnings": warnings}`), **including** the `# ── Pydantic Request Models` block and both request models in between. Insert:

```python
# ── Config (single owner: halbert_core.model.llm_config) ─────────

from ...model import llm_config as llm_store


class LLMConfigUpdate(BaseModel):
    llm_config: Dict[str, Any]


def _config_payload() -> Dict[str, Any]:
    return {
        "llm_config": llm_store.load(),
        "chat_capable_providers": sorted(llm_store.CHAT_CAPABLE_PROVIDERS),
    }


@router.get("/llm/config")
def get_llm_config() -> Dict[str, Any]:
    """Halbert's model configuration. On a fresh install, adds Local Ollama when it answers."""
    llm_store.ensure_local_ollama_endpoint()
    return {"data": _config_payload()}


@router.put("/llm/config")
def update_llm_config(body: LLMConfigUpdate):
    """Deep-merge a partial llm_config (callers send whole slots) and return the saved result."""
    try:
        llm_store.update(body.llm_config)
    except llm_store.SlotProviderError as e:
        return JSONResponse(
            status_code=422,
            content={"error": {
                "code": "PROVIDER_NOT_CHAT_CAPABLE",
                "slot": e.slot,
                "provider": e.provider,
                "message": str(e),
            }},
        )
    return {"data": _config_payload()}


# ── Pydantic Request Models ──────────────────────────────────────


class LLMProxyRequest(BaseModel):
    provider: str = "ollama"
    url: str
    api_key: Optional[str] = None
    slot: Optional[str] = None


class LLMModelTestRequest(BaseModel):
    provider: str = "ollama"
    url: str
    model: str
    api_key: Optional[str] = None
    slot: Optional[str] = None
```

Add `from fastapi.responses import JSONResponse` next to the existing `from fastapi import APIRouter, Request` import (then drop `Request` from that import — it is no longer used).

- [ ] **Step 4: Delete the SourcePrep-only routes and the embedding branches**

1. Delete from `def _ollama_cloud_candidates()` through the end of `proxy_cloud_models` (the block ends right before `@router.post("/api/llm/proxy/test")`). This also removes `_cloud_probe_cache` and `_CLOUD_PROBE_TTL_SEC`.
2. Delete from `# ── Plan Limits (stub — Halbert doesn't have concurrency_limits.json) ──` to the end of the file (`get_plan_limits`, `embedding_status`, `embedding_download`, `get_llm_slots_status`).
3. In `proxy_test_model`, Ollama branch: replace

```python
        if req.provider == "ollama":
            if req.kind == "embedding":
                try:
                    r = requests.post(
                        f"{url}/api/embeddings",
                        json={"model": req.model, "prompt": "Test embedding"},
                        timeout=120,
                    )
                    if r.status_code == 200:
                        success = True
                        message = "Model responded successfully"
                        model_status_str = "ready"
                    else:
                        message = f"HTTP {r.status_code}: {r.text[:100]}"
                except requests.Timeout:
                    message = f"Model '{req.model}' timed out (may still be loading)"
                    model_status_str = "loading"
            else:
                # Check if model is loaded
```

with

```python
        if req.provider == "ollama":
            if True:
                # Check if model is loaded
```

(keeping the indentation of the rest of that branch intact — `if True:` avoids re-indenting ~40 lines; it is removed by the simplify pass in Task 11 if you prefer, but is correct as is).

4. In the OpenAI-family branch replace

```python
            if req.kind == "embedding":
                r = requests.post(
                    f"{base}/embeddings",
                    headers=headers,
                    json={"model": req.model, "input": "Test"},
                    timeout=30,
                )
            else:
                r = requests.post(
```

with

```python
            if True:
                r = requests.post(
```

5. Update the module docstring's endpoint list:

```
Endpoints:
  Config:
    - GET  /llm/config             — Halbert's llm_config + chat-capable provider list
    - PUT  /llm/config             — merge-update (whole slots)

  LLM Proxy (model listing & testing, all providers):
    - POST /api/llm/proxy/models       — list models from an endpoint
    - POST /api/llm/proxy/test         — test endpoint connectivity
    - POST /api/llm/proxy/test-model   — test a specific model
```

6. Verify nothing else references the removed helpers:

Run: `grep -n "load_llm_config\|save_llm_config\|_default_llm_config\|_config_path\|load_full_ui_config\|req.kind\|time\.\|yaml\.\|get_config_dir" halbert_core/halbert_core/dashboard/routes/llm.py`
Expected: no output. Then remove the now-unused imports `import time`, `import yaml`, and `from ...utils.platform import get_config_dir`.

- [ ] **Step 5: Point `compute.py` at the store**

`halbert_core/halbert_core/dashboard/routes/compute.py` line 36: replace `from .llm import is_safe_url, load_llm_config` with

```python
from .llm import is_safe_url
from ...model import llm_config as llm_store
```

and in `_find_endpoint` replace `config = load_llm_config()` with `config = llm_store.load()`.

In `halbert_core/tests/test_compute_probe.py` replace every `patch.object(compute, "load_llm_config",` with `patch.object(compute.llm_store, "load",` (run `grep -n load_llm_config halbert_core/tests/test_compute_probe.py` first and edit each hit).

- [ ] **Step 6: Run the tests**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_llm_routes.py tests/test_compute_probe.py tests/test_dashboard_main.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/dashboard/routes/llm.py halbert_core/halbert_core/dashboard/routes/compute.py halbert_core/tests/test_llm_routes.py halbert_core/tests/test_compute_probe.py
git commit -m "feat(dashboard): serve the picker from GET/PUT /llm/config

Replaces SourcePrep's /global/config with a thin layer over the store,
and deletes the stubs Halbert never had a backend for: plan limits,
embedding status/download, slot status, and the always-empty Ollama
Cloud candidate probe. A slot on a provider chat cannot call is refused
with PROVIDER_NOT_CHAT_CAPABLE."
```

---

### Task 4: Intake routing reads the new slots

**Files:**
- Modify: `halbert_core/halbert_core/intake/pipeline.py:75-118`
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py:216-234, 836-838`
- Modify: `halbert_core/tests/test_intake_pipeline.py:18-27`

- [ ] **Step 1: Move the test fixtures onto the new shape**

In `halbert_core/tests/test_intake_pipeline.py` replace the `MODEL_CONFIG` / `MODEL_CONFIG_WITH_VISION` definitions with:

```python
MODEL_CONFIG = {
    "llm_config": {
        "saved_endpoints": [{"id": "ep", "name": "Local", "provider": "ollama", "url": "http://localhost:11434"}],
        "chat_model": {"enabled": True, "endpoint_id": "ep", "model": "example-guide:14b-instruct-q4_0"},
        "specialist_model": {"enabled": True, "endpoint_id": "ep", "model": "example-specialist:32b"},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
    "routing": {"complexity_threshold": 3},
}

MODEL_CONFIG_WITH_VISION = {
    **MODEL_CONFIG,
    "llm_config": {
        **MODEL_CONFIG["llm_config"],
        "vision_model": {"enabled": True, "endpoint_id": "ep", "model": "example-vision:8b"},
    },
}
```

Add one test at the end of `TestVisionRouting`:

```python
    def test_disabled_specialist_routes_to_guide(self):
        """A specialist slot with a model but enabled=False must not be used."""
        cfg = {**MODEL_CONFIG, "llm_config": {**MODEL_CONFIG["llm_config"],
               "specialist_model": {"enabled": False, "endpoint_id": "ep", "model": "example-specialist:32b"}}}
        pipeline = IntakePipeline(make_router(score=5), get_context_budget, cfg)
        result = pipeline.analyze("complex diagnostic query about nginx configuration")
        assert result.recommended_model == "guide"
```

- [ ] **Step 2: Run to verify the routing tests fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_intake_pipeline.py -q`
Expected: failures in `test_troubleshooting_routes_to_specialist`, `test_specialist_model_budget`, `test_image_message_routes_to_vision`, … (pipeline still reads `orchestrator`/`specialist`/`vision`).

- [ ] **Step 3: Rewrite the model-selection stage**

In `halbert_core/halbert_core/intake/pipeline.py` replace the `model_config` bullet list in `IntakePipeline.__init__`'s docstring with:

```
            model_config: the whole models.yml dict (post-migration, from
                model.llm_config.load_file()). Reads:
                - llm_config.chat_model.model
                - llm_config.specialist_model.{enabled,model}
                - llm_config.vision_model.{enabled,model}
                - routing.complexity_threshold: int (default 3)
```

and replace the Stage 3 block (from `threshold = self._model_config.get("routing", {})...` through `model_name = self._model_config.get("orchestrator", {}).get("model", "")`) with:

```python
        llm = self._model_config.get("llm_config") or {}
        chat = llm.get("chat_model") or {}
        specialist = llm.get("specialist_model") or {}
        vision = llm.get("vision_model") or {}
        threshold = self._model_config.get("routing", {}).get("complexity_threshold", 3)
        specialist_enabled = bool(specialist.get("enabled")) and bool(specialist.get("model"))
        vision_model_name = vision.get("model", "") if vision.get("enabled") else ""

        if signals.has_images and vision_model_name:
            # Vision takes priority — image content requires a multimodal model
            recommended_model_name = "vision"
            model_name = vision_model_name
        elif complexity.score >= threshold and specialist_enabled:
            recommended_model_name = "specialist"
            model_name = specialist.get("model", "")
        else:
            recommended_model_name = "guide"
            model_name = chat.get("model", "")
```

- [ ] **Step 4: Feed the pipeline from the store in `agent.py`**

Replace `_load_model_config` in `halbert_core/halbert_core/dashboard/routes/agent.py`:

```python
def _load_model_config():
    """Whole models.yml (post-migration) for the intake pipeline — see model.llm_config."""
    try:
        from ...model import llm_config as llm_store
        return llm_store.load_file()
    except Exception as e:
        logger.warning(f"Could not load model config: {e}")
        return {}
```

and at the `specialist_enabled = bool(` site (~line 836) replace

```python
        specialist_enabled = bool(
            _load_model_config().get("specialist", {}).get("enabled", False)
        )
```

with

```python
        specialist_enabled = bool(
            (_load_model_config().get("llm_config") or {})
            .get("specialist_model", {})
            .get("enabled", False)
        )
```

- [ ] **Step 5: Run**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_intake_pipeline.py tests/test_agent_integration.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/intake/pipeline.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_intake_pipeline.py
git commit -m "fix(intake): route on llm_config slots instead of the legacy keys

The intake pipeline was the one reader that never saw the picker's
config; it now reads chat/specialist/vision from the migrated file."
```

---

### Task 5: Settings routes — read-only status, store-backed writers

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/settings.py` (`/model/status`, `/model/apply-recommended`, `/model/install`, unused Pydantic models)
- Create: `halbert_core/tests/test_settings_model_routes.py`

- [ ] **Step 1: Write the failing tests**

`halbert_core/tests/test_settings_model_routes.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""/settings/model/* — read-only status for the Quick-setup strip, store-backed writers.

Coroutines are driven with asyncio.run so these pass with or without
pytest-asyncio (CI has it; a bare dev venv may not).
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import settings as routes
from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"


def _fake_models(entries):
    async def fake(_client, _url):
        return entries
    return fake


def test_status_reports_chat_and_is_read_only(models_config_dir):
    store.save({
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"},
    })
    before = (models_config_dir / "models.yml").read_text()
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "m1"}, {"name": "m2"}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(3, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["chat"] == {"configured": True, "model": "m1", "endpoint_url": OLLAMA,
                           "provider": "ollama", "reachable": True, "model_available": True}
    assert out["local_ollama"] == {"reachable": True, "url": OLLAMA, "model_count": 2}
    assert out["hardware"] == {"tier": 3, "total_vram_gb": None}
    assert (models_config_dir / "models.yml").read_text() == before


def test_status_on_fresh_install_writes_nothing(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "m1"}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["chat"]["configured"] is False
    assert out["local_ollama"]["reachable"] is True
    assert not (models_config_dir / "models.yml").exists()


def test_status_when_ollama_is_down(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models(None)), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["local_ollama"] == {"reachable": False, "url": OLLAMA, "model_count": 0}
    assert out["chat"]["reachable"] is False


def _budget(max_params=14, mem=10.0):
    budget = MagicMock(max_params_b_4bit=max_params, memory_budget_gb=mem)
    budget.to_dict.return_value = {"max_params_b_4bit": max_params}
    detector = MagicMock()
    detector.recommend_budget.return_value = budget
    return detector


def test_apply_recommended_writes_chat_model_and_compression(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "big", "size": 1}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(2, 48.0)), \
         patch("halbert_core.model.hardware_detector.HardwareDetector", return_value=_budget()), \
         patch("halbert_core.model.hardware_detector.pick_installed_model", return_value={"name": "big"}):
        out = asyncio.run(routes.apply_recommended_config())
    assert out["success"] is True and out["applied"]["chat_model"] == "big"
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "big" and cfg["chat_model"]["enabled"] is True
    ep = next(e for e in cfg["saved_endpoints"] if e["id"] == cfg["chat_model"]["endpoint_id"])
    assert ep["url"] == OLLAMA and ep["provider"] == "ollama"
    assert store.load_file()["compression"] == {"backend": "lingua", "enabled": True}


def test_apply_recommended_when_nothing_fits_writes_nothing(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)), \
         patch("halbert_core.model.hardware_detector.HardwareDetector", return_value=_budget(7, 6.0)), \
         patch("halbert_core.model.hardware_detector.pick_installed_model", return_value=None):
        out = asyncio.run(routes.apply_recommended_config())
    assert out["success"] is False
    assert not (models_config_dir / "models.yml").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_settings_model_routes.py -q`
Expected: `AttributeError: ... has no attribute '_ollama_models'`.

- [ ] **Step 3: Add the helpers and rewrite `/model/status`**

In `halbert_core/halbert_core/dashboard/routes/settings.py`, add `Tuple` to the `typing` import, then insert directly above `@router.get("/model/status")`:

```python
def _detect_hardware_tier() -> Tuple[int, Optional[float]]:
    """(tier, total_vram_gb). Tier 1: <40GB CUDA, 2: >=40GB CUDA, 3: Apple Silicon."""
    tier, total_vram = 1, None
    try:
        import torch
        if torch.cuda.is_available():
            total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            tier = 2 if total_vram >= 40 else 1
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            tier = 3
    except ImportError:
        pass
    return tier, (round(total_vram, 1) if total_vram else None)


async def _ollama_models(client, url: str) -> Optional[List[Dict[str, Any]]]:
    """Raw ``GET /api/tags`` entries, or None when the server does not answer."""
    try:
        r = await client.get(f"{url.rstrip('/')}/api/tags")
        if r.status_code == 200:
            return list(r.json().get("models", []))
    except Exception as e:
        logger.debug(f"Ollama tags check failed for {url}: {e}")
    return None


async def _openai_model_ids(client, url: str, api_key: str) -> Optional[List[str]]:
    """Model ids from an OpenAI-style ``GET /v1/models``, or None when unreachable."""
    base = url.rstrip("/")
    base = base if base.endswith("/v1") else f"{base}/v1"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = await client.get(f"{base}/models", headers=headers)
        if r.status_code == 200:
            return [str(m.get("id", "")) for m in r.json().get("data", [])]
    except Exception as e:
        logger.debug(f"Model list check failed for {url}: {e}")
    return None
```

Replace the whole `get_model_status` function (decorator through its final `return result`) with:

```python
@router.get("/model/status")
async def get_model_status() -> Dict[str, Any]:
    """Read-only status for Settings → AI Models' Quick-setup strip. Never writes config."""
    import httpx
    from ...model import llm_config as llm_store

    chat = llm_store.resolve("chat_model")
    tier, total_vram = _detect_hardware_tier()
    result: Dict[str, Any] = {
        "chat": {
            "configured": chat is not None,
            "model": chat.model if chat else "",
            "endpoint_url": chat.url if chat else "",
            "provider": chat.provider if chat else "",
            "reachable": False,
            "model_available": False,
        },
        "local_ollama": {"reachable": False, "url": llm_store.DEFAULT_OLLAMA_URL, "model_count": 0},
        "hardware": {"tier": tier, "total_vram_gb": total_vram},
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        local = await _ollama_models(client, llm_store.DEFAULT_OLLAMA_URL)
        if local is not None:
            result["local_ollama"].update(reachable=True, model_count=len(local))
        if chat is None:
            return result
        names: Optional[List[str]] = None
        if chat.provider == "ollama":
            if chat.url.rstrip("/") == llm_store.DEFAULT_OLLAMA_URL:
                entries = local
            else:
                entries = await _ollama_models(client, chat.url)
            names = [str(m.get("name", "")) for m in entries] if entries is not None else None
        else:
            names = await _openai_model_ids(client, chat.url, chat.api_key)
        if names is not None:
            result["chat"].update(reachable=True, model_available=chat.model in names)
    return result
```

- [ ] **Step 4: Rewrite `/model/apply-recommended` and `/model/install`**

Replace `apply_recommended_config` (decorator through its final `return {...}`) with:

```python
@router.post("/model/apply-recommended")
async def apply_recommended_config() -> Dict[str, Any]:
    """
    Apply hardware-appropriate defaults based on the detected model size budget.

    Sets the context-compression backend by hardware tier (Tier 1 <40GB CUDA:
    semantic; Tier 2 >=40GB CUDA: lingua; Tier 3 Apple Silicon: lingua).

    For the chat model it never picks from a fixed list: it selects the
    largest model ALREADY INSTALLED on local Ollama (from GET /api/tags) that
    fits the detected budget. If nothing installed fits, it returns
    ``success: false`` and asks the user to pull a model of at most N billion
    parameters. Nothing is written in that case.
    """
    import httpx
    from ...model import llm_config as llm_store
    from ...model.hardware_detector import HardwareDetector, pick_installed_model

    tier, total_vram = _detect_hardware_tier()
    compression_backend = 'semantic' if tier == 1 else 'lingua'

    # Model size budget from detected hardware (parameter counts, no names)
    detector = HardwareDetector()
    budget = detector.recommend_budget(detector.detect())

    endpoint = llm_store.DEFAULT_OLLAMA_URL
    async with httpx.AsyncClient(timeout=5.0) as client:
        installed = await _ollama_models(client, endpoint) or []

    chosen = pick_installed_model(installed, budget)
    if not chosen:
        return {
            'success': False,
            'hardware_tier': tier,
            'total_vram_gb': total_vram,
            'budget': budget.to_dict(),
            'message': (
                f"No installed model fits your hardware budget "
                f"(~{budget.max_params_b_4bit}B parameters at 4-bit, "
                f"{budget.memory_budget_gb:.0f}GB for weights). "
                f"Pull a model of at most ~{budget.max_params_b_4bit}B parameters with "
                f"'ollama pull <model>' and try again, or pick one in Settings → AI Models."
            ),
        }

    chat_model = chosen['name']
    endpoint_id = llm_store.ensure_ollama_endpoint(endpoint)
    llm_store.set_slot("chat_model", chat_model, endpoint_id)
    compression = dict(llm_store.load_file().get("compression") or {})
    compression.update(backend=compression_backend, enabled=True)
    llm_store.set_top_level("compression", compression)

    return {
        'success': True,
        'hardware_tier': tier,
        'total_vram_gb': total_vram,
        'budget': budget.to_dict(),
        'applied': {
            'chat_model': chat_model,
            'compression_backend': compression_backend,
        },
        'message': (
            f"Applied Tier {tier} configuration: {chat_model} "
            f"(largest installed model within your ~{budget.max_params_b_4bit}B budget) "
            f"+ {compression_backend} compression"
        ),
    }
```

Replace `install_model` (decorator through its final `except Exception` block) with:

```python
@router.post("/model/install")
async def install_model(model_name: str) -> Dict[str, Any]:
    """
    Install a model via Ollama pull and make it the chat model.

    This is a quick operation that starts the pull - Ollama handles
    the actual download in the background.
    """
    import httpx
    from ...model import llm_config as llm_store

    chat = llm_store.resolve("chat_model")
    endpoint = chat.url if chat and chat.provider == "ollama" else llm_store.DEFAULT_OLLAMA_URL

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for pull
            response = await client.post(
                f"{endpoint}/api/pull",
                json={"name": model_name, "stream": False}
            )

            if response.status_code == 200:
                endpoint_id = llm_store.ensure_ollama_endpoint(endpoint)
                llm_store.set_slot("chat_model", model_name, endpoint_id)
                logger.info(f"Model {model_name} installed successfully")
                return {
                    'success': True,
                    'message': f'Model {model_name} installed successfully!',
                    'model': model_name
                }
            return {
                'success': False,
                'message': f'Pull failed: HTTP {response.status_code}'
            }
    except httpx.TimeoutException:
        return {
            'success': False,
            'message': 'Download timed out - model may still be downloading in background'
        }
    except Exception as e:
        logger.error(f"Model install failed: {e}")
        return {
            'success': False,
            'message': str(e)
        }
```

- [ ] **Step 5: Remove the dead Pydantic models and unused imports**

Run: `grep -n "SavedEndpoint\|ModelEndpoint\|ModelAssignment\|ModelConfigUpdate" halbert_core/halbert_core/dashboard/routes/settings.py`
Expected: only their class definitions (lines ~40–71). Delete those four classes (keep `ComputerNameUpdate`). Then run `grep -n "yaml\.\|get_config_dir()\|Path(" halbert_core/halbert_core/dashboard/routes/settings.py`; remove any of `import yaml`, `from pathlib import Path`, `from ...utils.platform import get_config_dir` that no longer has a use (the persona / ai-rules / system-profile endpoints further down may still use them — keep what they use).

- [ ] **Step 6: Run**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_settings_model_routes.py tests/test_dashboard_main.py -q`
Expected: all pass (`test_settings_model_routes.py`: 5 passed).

- [ ] **Step 7: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/dashboard/routes/settings.py halbert_core/tests/test_settings_model_routes.py
git commit -m "refactor(settings): model status is read-only; writers go through the store

/model/status no longer creates endpoints from a GET and reports the
chat slot plus local Ollama in the shape the Quick-setup strip needs.
apply-recommended and install write chat_model via model.llm_config."
```

---

### Task 6: `ModelRouter` and the CLI wizard — the last legacy reader and writer

**Files:**
- Modify: `halbert_core/halbert_core/model/router.py` (`__init__`, `_load_config`, `_load_configured_models`, `_route_task`, `get_status`)
- Modify: `halbert_core/halbert_core/model/config_wizard.py` (`run_auto`, `run_interactive`, `_build_config`, `validate_config`)
- Create: `halbert_core/tests/test_model_router_config.py`, `halbert_core/tests/test_config_wizard_schema.py`

- [ ] **Step 1: Write the failing tests**

`halbert_core/tests/test_model_router_config.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ModelRouter (services/{name}/explain) resolves its models from llm_config."""
import yaml

from halbert_core.model.router import ModelRouter, TaskType


def _router(tmp_path, monkeypatch, data):
    monkeypatch.setattr(ModelRouter, "_init_providers", lambda self: None)  # no network
    cfg = tmp_path / "models.yml"
    cfg.write_text(yaml.safe_dump(data))
    return ModelRouter(config_path=cfg)


def test_router_reads_llm_config_slots(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch, {
        "llm_config": {
            "saved_endpoints": [
                {"id": "l", "name": "Local", "provider": "ollama", "url": "http://localhost:11434"},
                {"id": "r", "name": "Remote", "provider": "openai", "url": "http://gpu:1234", "api_key": "k"},
            ],
            "chat_model": {"enabled": True, "endpoint_id": "l", "model": "chat-a"},
            "specialist_model": {"enabled": True, "endpoint_id": "r", "model": "spec-b"},
        },
        "routing": {"strategy": "auto", "prefer_specialist_for": ["code_generation"], "complexity_threshold": 0.5},
    })
    assert router.orchestrator_id == "chat-a"
    assert router.specialist_id == "spec-b"
    assert router._route_task(TaskType.CODE_GENERATION, prefer_specialist=False) == ("spec-b", "openai", "http://gpu:1234")
    assert router._route_task(TaskType.CHAT, prefer_specialist=False) == ("chat-a", "ollama", "http://localhost:11434")
    assert router.get_status()["specialist"]["enabled"] is True


def test_router_migrates_legacy_keys_in_memory(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch, {
        "orchestrator": {"model": "old", "endpoint": "http://localhost:11434"},
    })
    assert router.orchestrator_id == "old"
    assert router.specialist_id is None
    assert "orchestrator" not in router.config
    assert router._route_task(TaskType.CHAT, prefer_specialist=True) == ("old", "ollama", "http://localhost:11434")
```

`halbert_core/tests/test_config_wizard_schema.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The CLI wizard writes the llm_config schema, never the legacy keys."""
from unittest.mock import MagicMock

from halbert_core.model import llm_config as store
from halbert_core.model.config_wizard import ConfigWizard


def _wizard():
    return ConfigWizard.__new__(ConfigWizard)   # skip hardware detection in __init__


def _hardware():
    return MagicMock(profile=MagicMock(value="apple_silicon"), total_ram_gb=32,
                     platform="darwin", is_apple_silicon=True)


def _budget():
    budget = MagicMock()
    budget.to_dict.return_value = {"max_params_b_4bit": 14}
    return budget


def test_build_config_uses_llm_config_schema():
    cfg = _wizard()._build_config("chat-a", "ollama", _budget(), _hardware(), endpoint="http://localhost:11434")
    assert "orchestrator" not in cfg and "specialist" not in cfg
    llm = store.normalise(cfg["llm_config"])
    assert llm["chat_model"] == {"enabled": True, "endpoint_id": "ep_local_ollama", "model": "chat-a"}
    assert llm["saved_endpoints"] == [{"id": "ep_local_ollama", "name": "Local Ollama", "provider": "ollama",
                                       "url": "http://localhost:11434", "api_key": ""}]
    assert cfg["routing"]["strategy"] == "auto"


def test_build_config_without_model_leaves_chat_unset():
    cfg = _wizard()._build_config(None, "ollama", _budget(), _hardware())
    assert store.normalise(cfg["llm_config"])["chat_model"]["enabled"] is False


def test_validate_config_requires_llm_config(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text("orchestrator: {model: x}\nrouting: {}\nhandoff: {}\n")
    assert _wizard().validate_config(p) is False
    p.write_text("llm_config: {chat_model: {enabled: false, endpoint_id: '', model: ''}}\nrouting: {}\nhandoff: {}\n")
    assert _wizard().validate_config(p) is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_model_router_config.py tests/test_config_wizard_schema.py -q`
Expected: router tests fail on `orchestrator_id is None`; wizard tests fail on `"orchestrator" not in cfg` / unexpected `endpoint` kwarg.

- [ ] **Step 3: Rewire `ModelRouter`**

In `halbert_core/halbert_core/model/router.py`:

1. In `__init__`, directly after `self.specialist_id: Optional[str] = None`, add:

```python
        self._orchestrator_config: Dict[str, Any] = {}
        self._specialist_config: Dict[str, Any] = {}
```

2. Replace `_load_config` entirely:

```python
    def _load_config(self) -> Dict[str, Any]:
        """Load router configuration (llm_config migrated + normalised; see model.llm_config)."""
        from . import llm_config as llm_store
        raw: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    raw = yaml.safe_load(f) or {}
                logger.info(f"Loaded router config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
                raw = {}
        if not raw:
            raw = {
                "routing": {
                    "strategy": "auto",
                    "prefer_specialist_for": ["code_generation", "code_analysis"]
                },
                "handoff": {
                    "strategy": "summarized",
                    "max_context_tokens": 4096,
                    "include_rag": True
                }
            }
        return llm_store.normalise_file(raw)
```

3. Replace `_load_configured_models` entirely:

```python
    def _load_configured_models(self):
        """Resolve the chat and specialist slots from llm_config."""
        from . import llm_config as llm_store
        chat = llm_store.resolve_from(self.config, "chat_model")
        if chat:
            self.orchestrator_id = chat.model
            self._orchestrator_config = {"model": chat.model, "provider": chat.provider, "endpoint": chat.url}
            logger.info(f"Orchestrator configured: {self.orchestrator_id} at {chat.url}")
        spec = llm_store.resolve_from(self.config, "specialist_model")
        if spec:
            self.specialist_id = spec.model
            self._specialist_config = {"model": spec.model, "provider": spec.provider, "endpoint": spec.url}
            logger.info(f"Specialist configured: {self.specialist_id} at {spec.url}")
```

4. In `_route_task` replace

```python
        orch_config = self.config.get("orchestrator", {})
        spec_config = self.config.get("specialist", {})
```

with

```python
        orch_config = self._orchestrator_config
        spec_config = self._specialist_config
```

and replace `specialist_available = spec_config.get("enabled") and self.specialist_id` with `specialist_available = bool(self.specialist_id)`.

5. In `get_status` replace `"provider": self.config.get("orchestrator", {}).get("provider")` with `"provider": self._orchestrator_config.get("provider")`, `"provider": self.config.get("specialist", {}).get("provider")` with `"provider": self._specialist_config.get("provider")`, and `"enabled": self.config.get("specialist", {}).get("enabled", False)` with `"enabled": bool(self.specialist_id)`.

6. Verify: `grep -n '"orchestrator"\|"specialist"' halbert_core/halbert_core/model/router.py` — expected hits only inside `get_status`'s dict keys and log `extra=` dicts, never as `self.config.get(...)` reads.

- [ ] **Step 4: Rewire the wizard**

In `halbert_core/halbert_core/model/config_wizard.py`:

1. `run_auto`: replace `config = self._build_config(model, "ollama", budget, hardware)` with `config = self._build_config(model, "ollama", budget, hardware, endpoint=endpoint)`. Same replacement in `run_interactive`.

2. Replace `_build_config`'s signature and the `config = {...}` literal:

```python
    def _build_config(
        self,
        model: Optional[str],
        provider: str,
        budget: ModelBudget,
        hardware: HardwareCapabilities,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> Dict[str, Any]:
        """
        Build configuration dictionary on the llm_config schema.

        Args:
            model: Chat model name (None leaves the slot unset)
            provider: Runtime serving the model
            budget: Model size budget
            hardware: Hardware capabilities
            endpoint: URL of the endpoint that serves ``model``

        Returns:
            Configuration dictionary
        """
        endpoint_id = "ep_local_ollama"
        config = {
            "# Halbert Model Configuration": None,
            "# Generated by configuration wizard": None,
            "# Edit this file to customize model selection": None,

            "llm_config": {
                "saved_endpoints": [
                    {"id": endpoint_id, "name": "Local Ollama", "provider": provider,
                     "url": endpoint, "api_key": ""},
                ],
                "chat_model": {
                    "enabled": bool(model),
                    "endpoint_id": endpoint_id if model else "",
                    "model": model or "",
                },
                "specialist_model": {"enabled": False, "endpoint_id": "", "model": ""},
                "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
            },

            "routing": {
                "strategy": "auto",
                "prefer_specialist_for": [
                    "code_generation",
                    "code_analysis",
                ],
            },

            "handoff": {
                "strategy": "summarized",
                "max_context_tokens": 4096,
                "include_rag": True,
            },

            "# Hardware Profile": None,
            "hardware": {
                "profile": hardware.profile.value,
                "total_ram_gb": hardware.total_ram_gb,
                "platform": hardware.platform,
                "is_apple_silicon": hardware.is_apple_silicon,
                "model_budget": budget.to_dict(),
            },
        }

        return config
```

3. In `validate_config` replace `required = ["orchestrator", "specialist", "routing", "handoff"]` with `required = ["llm_config", "routing", "handoff"]`, and replace

```python
            # Check orchestrator
            if "model" not in config["orchestrator"]:
                logger.error("Orchestrator missing 'model' key")
                return False
```

with

```python
            # Check the chat slot exists
            if not isinstance(config["llm_config"], dict) or "chat_model" not in config["llm_config"]:
                logger.error("llm_config missing 'chat_model'")
                return False
```

Then run `grep -n "orchestrator\|specialist" halbert_core/halbert_core/model/config_wizard.py`; the only remaining hits must be prose in `generate_summary` (`Guide model:` / `Specialist: Disabled` lines) and docstrings — no dict keys.

- [ ] **Step 5: Run**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_model_router_config.py tests/test_config_wizard_schema.py -q`
Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add halbert_core/halbert_core/model/router.py halbert_core/halbert_core/model/config_wizard.py halbert_core/tests/test_model_router_config.py halbert_core/tests/test_config_wizard_schema.py
git commit -m "refactor(model): ModelRouter and the wizard use the llm_config schema

No code path reads or writes orchestrator/specialist/vision any more."
```

---

### Task 7: The repo template

**Files:**
- Modify: `config/models.yml`

- [ ] **Step 1: Replace the slot section**

In `config/models.yml`, replace everything from the `# Model slots` banner comment through the end of the `vision:` block (the line `purpose: Image analysis, screenshot interpretation, visual troubleshooting`) with:

```yaml
# ─────────────────────────────────────────────────────────────────────────────
# Model slots
# ─────────────────────────────────────────────────────────────────────────────
#
# This file is a neutral template. Every slot below is empty; a slot with an
# empty model is ignored until one is chosen in Settings → AI Models (which
# writes the user-level models.yml). Any model served by one of your endpoints
# can fill a slot; pick a size that fits your memory budget (roughly: a ~14B-
# parameter model at 4-bit quantization needs ~10 GB).
#
#   chat_model        the model you talk to (required)
#   specialist_model  complex diagnostics and multi-step reasoning; routed to
#                     by complexity (optional — leave empty to use chat_model)
#   vision_model      screenshots and images (optional — leave empty to send
#                     images to chat_model)
#
# Each slot references an entry in saved_endpoints by id. Halbert manages this
# section itself (halbert_core/model/llm_config.py); the legacy
# orchestrator/specialist/vision keys are migrated on first load.

llm_config:
  saved_endpoints: []
  chat_model:
    enabled: false
    endpoint_id: ""
    model: ""
  specialist_model:
    enabled: false
    endpoint_id: ""
    model: ""
  vision_model:
    enabled: false
    endpoint_id: ""
    model: ""
```

Leave `providers:`, `compression:`, `routing:`, `handoff:` and `persona_names:` exactly as they are.

- [ ] **Step 2: Verify it parses and normalises to defaults**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -c "import yaml; from halbert_core.model import llm_config as s; d=yaml.safe_load(open('../config/models.yml')); assert not s.needs_migration(d); assert s.normalise(d['llm_config'])==s.default_llm_config(); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add config/models.yml
git commit -m "chore(config): put the models.yml template on the llm_config schema"
```

---

## Frontend (Tasks 8–10 commit together)

`types/llm.ts` changes shape, which breaks the old vendored files until they are deleted in Task 10, so `npm run build` is only expected green at the end of Task 10. vitest does not type-check, so the component tests in Task 9 pass before that. One commit for all three tasks.

### Task 8: Types, `EndpointManager`, and the hook

**Files:**
- Rewrite: `frontend/src/types/llm.ts`
- Rewrite: `frontend/src/components/llm/EndpointManager.tsx`
- Rewrite: `frontend/src/hooks/useLLMConfig.ts`

- [ ] **Step 1: Replace `types/llm.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Halbert's model configuration — mirrors halbert_core/model/llm_config.py.
 * Three slots and an endpoint list; nothing else.
 */

export type LLMProvider =
  | 'ollama'
  | 'lm-studio'
  | 'openai'
  | 'openai-compatible'
  | 'anthropic'
  | 'google'
  | 'azure-openai';

/** ModelCard prop type. Halbert always uses 'endpoint'. */
export type ModelSource = 'endpoint' | 'huggingface';

export interface SavedEndpoint {
  id: string;
  name: string;
  provider: LLMProvider;
  url: string;
  api_key?: string;
}

export interface LLMSlotConfig {
  enabled: boolean;
  endpoint_id: string;
  model: string;
}

export type SlotName = 'chat_model' | 'specialist_model' | 'vision_model';
export const SLOT_NAMES: readonly SlotName[] = ['chat_model', 'specialist_model', 'vision_model'];

export interface LLMConfig {
  saved_endpoints: SavedEndpoint[];
  chat_model: LLMSlotConfig;
  specialist_model: LLMSlotConfig;
  vision_model: LLMSlotConfig;
}

export function emptySlot(): LLMSlotConfig {
  return { enabled: false, endpoint_id: '', model: '' };
}

export function emptyLLMConfig(): LLMConfig {
  return { saved_endpoints: [], chat_model: emptySlot(), specialist_model: emptySlot(), vision_model: emptySlot() };
}

export type ModelReadinessStatus = 'not_found' | 'downloaded' | 'loading' | 'ready' | 'error' | 'unknown';

export interface EndpointTestResult {
  success: boolean;
  message: string;
  models?: string[];
  model_status?: ModelReadinessStatus;
  warnings?: string[];
}

/** One entry of /api/llm/proxy/models `model_details` (shape consumed by ModelCard). */
export interface ModelDetail {
  name: string;
  context_window?: string;
  context_tokens?: number;
  cost_tier?: string;
  batch_profile?: string;
  rate_limits?: { rpd?: number; rpm?: number };
  batch_estimate?: { files_per_request: number; daily_file_capacity?: number };
  license?: string;
  license_id?: string;
  license_url?: string;
  attribution?: string;
}
```

- [ ] **Step 2: Rewrite `EndpointManager.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { SavedEndpoint, LLMProvider, EndpointTestResult } from '@/types/llm';
import { Plus, Trash2, Edit2, Play, CheckCircle, AlertCircle, Server, Wand2 } from 'lucide-react';
import { Button } from '@/components/prep-primitives/Button';
import { Select } from '@/components/prep-primitives/Select';
import { CloudDisclosureModal } from '@/components/legal';

// ── LEG-MOD-02: Cloud provider disclosure helpers ──────────────────
// A provider triggers the data-flow disclosure modal when it is a known
// cloud provider or an Ollama endpoint pointing at ollama.com.
const CLOUD_PROVIDERS = new Set(['openai', 'anthropic', 'google', 'azure-openai', 'openai-compatible']);

function isCloudProviderForDisclosure(provider: LLMProvider, url: string): boolean {
  if (CLOUD_PROVIDERS.has(provider)) return true;
  if (provider === 'ollama') {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host === 'ollama.com' || host.endsWith('.ollama.com')) return true;
    } catch { /* invalid url — treat as local */ }
  }
  return false;
}

const PROVIDER_DISPLAY: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  'azure-openai': 'Azure OpenAI',
  'openai-compatible': 'OpenAI-compatible',
  ollama: 'Ollama Cloud',
};

export const PROVIDER_OPTIONS: { value: LLMProvider; label: string; hint?: string }[] = [
  { value: 'ollama', label: 'Ollama', hint: 'http://localhost:11434' },
  { value: 'lm-studio', label: 'LM Studio', hint: 'http://localhost:1234' },
  { value: 'openai', label: 'OpenAI', hint: 'https://api.openai.com/v1' },
  { value: 'openai-compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic', hint: 'https://api.anthropic.com' },
  { value: 'google', label: 'Google', hint: 'https://generativelanguage.googleapis.com' },
  { value: 'azure-openai', label: 'Azure OpenAI', hint: 'https://<resource>.openai.azure.com' },
];

export const NOT_CHAT_CAPABLE_LABEL = 'Listing & testing only — not yet usable for chat';

const API_KEY_PROVIDERS = new Set<LLMProvider>(['openai', 'openai-compatible', 'anthropic', 'google', 'azure-openai']);

const INPUT =
  'w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-focus';

function providerDefaultUrl(provider: LLMProvider): string {
  return PROVIDER_OPTIONS.find((o) => o.value === provider)?.hint ?? '';
}

function hasAutofill(provider: LLMProvider): boolean {
  const hint = providerDefaultUrl(provider);
  return !!hint && !hint.includes('<');
}

interface FormState {
  name: string;
  provider: LLMProvider;
  url: string;
  apiKey: string;
}

const EMPTY_FORM: FormState = { name: '', provider: 'ollama', url: '', apiKey: '' };

function EndpointForm({
  form,
  setForm,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  form: FormState;
  setForm: (next: FormState) => void;
  onSubmit: () => void;
  onCancel: () => void;
  submitLabel: string;
}) {
  const handleProviderChange = (provider: LLMProvider) => {
    const prevDefault = providerDefaultUrl(form.provider);
    const nextDefault = hasAutofill(provider) ? providerDefaultUrl(provider) : '';
    setForm({ ...form, provider, url: !form.url || form.url === prevDefault ? nextDefault : form.url });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">Display name</label>
          <input
            placeholder="e.g. Local Ollama"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={INPUT}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">Provider</label>
          <Select
            value={form.provider}
            onChange={(e) => handleProviderChange(e.target.value as LLMProvider)}
            options={PROVIDER_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            className="w-full"
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-text-muted mb-1">Endpoint URL</label>
        <div className="flex gap-2">
          <input
            placeholder={providerDefaultUrl(form.provider) || 'http://host:port'}
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            className={cn(INPUT, 'flex-1')}
          />
          {hasAutofill(form.provider) && form.url !== providerDefaultUrl(form.provider) && (
            <button
              type="button"
              onClick={() => setForm({ ...form, url: providerDefaultUrl(form.provider) })}
              className="px-2.5 py-2 rounded border border-border bg-surface-raised text-text-muted hover:text-primary hover:border-primary/40 transition-colors text-xs flex items-center gap-1 shrink-0"
              title={`Autofill: ${providerDefaultUrl(form.provider)}`}
            >
              <Wand2 className="w-3.5 h-3.5" />
              Autofill
            </button>
          )}
        </div>
      </div>
      {API_KEY_PROVIDERS.has(form.provider) && (
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">API key</label>
          <input
            type="password"
            placeholder="sk-..."
            value={form.apiKey}
            onChange={(e) => setForm({ ...form, apiKey: e.target.value })}
            className={INPUT}
          />
          {form.provider === 'google' && (
            <p className="text-[10px] text-warning mt-1.5 flex items-center gap-1">
              <AlertCircle className="w-3 h-3 shrink-0" />
              Google sends the API key as a URL parameter (visible in HTTP logs).
            </p>
          )}
        </div>
      )}
      <div className="flex gap-2 pt-2 justify-end">
        <Button onClick={onCancel} variant="outline" size="sm">
          Cancel
        </Button>
        <Button onClick={onSubmit} size="sm" disabled={!form.name.trim() || !form.url.trim()}>
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}

export interface EndpointManagerProps {
  endpoints: SavedEndpoint[];
  onAdd: (endpoint: Omit<SavedEndpoint, 'id'>) => void;
  onEdit: (endpoint: SavedEndpoint) => void;
  onDelete: (id: string) => void;
  onTest: (endpoint: SavedEndpoint) => Promise<EndpointTestResult>;
  /** Providers the chat runtime can call. Others are listed, badged, and kept out of slot dropdowns. */
  chatCapableProviders: string[];
  className?: string;
}

type Mode = { kind: 'idle' } | { kind: 'add' } | { kind: 'edit'; id: string };

export function EndpointManager({
  endpoints,
  onAdd,
  onEdit,
  onDelete,
  onTest,
  chatCapableProviders,
  className,
}: EndpointManagerProps) {
  const [mode, setMode] = useState<Mode>({ kind: 'idle' });
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, EndpointTestResult>>({});
  const [disclosure, setDisclosure] = useState<{ providerName: string; action: () => void } | null>(null);
  const chatCapable = new Set(chatCapableProviders);

  const reset = () => {
    setMode({ kind: 'idle' });
    setForm(EMPTY_FORM);
  };

  const withDisclosure = (action: () => void) => {
    if (isCloudProviderForDisclosure(form.provider, form.url)) {
      setDisclosure({ providerName: PROVIDER_DISPLAY[form.provider] ?? form.provider, action });
    } else {
      action();
    }
  };

  const toEndpoint = (): Omit<SavedEndpoint, 'id'> => ({
    name: form.name.trim(),
    provider: form.provider,
    url: form.url.trim(),
    api_key: form.apiKey.trim() || undefined,
  });

  const submitAdd = () =>
    withDisclosure(() => {
      onAdd(toEndpoint());
      reset();
    });

  const submitEdit = (id: string) =>
    withDisclosure(() => {
      onEdit({ id, ...toEndpoint() });
      reset();
    });

  const startEdit = (ep: SavedEndpoint) => {
    setMode({ kind: 'edit', id: ep.id });
    setForm({ name: ep.name, provider: ep.provider, url: ep.url, apiKey: ep.api_key ?? '' });
  };

  const runTest = async (ep: SavedEndpoint) => {
    setTestingId(ep.id);
    try {
      const result = await onTest(ep);
      setTestResults((prev) => ({ ...prev, [ep.id]: result }));
    } catch {
      setTestResults((prev) => ({ ...prev, [ep.id]: { success: false, message: 'Test failed' } }));
    } finally {
      setTestingId(null);
    }
  };

  return (
    <>
      <div className={cn('rounded-lg border border-border bg-surface p-6', className)}>
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-text flex items-center gap-2">
            <Server className="w-5 h-5 text-primary" />
            Endpoints
          </h3>
          <p className="text-sm text-text-muted mt-1">Local and remote LLM servers the model slots above can use.</p>
        </div>

        <div className="space-y-3 mb-6">
          {endpoints.length === 0 ? (
            <div className="text-sm text-text-muted py-8 text-center bg-surface-raised rounded-lg border border-dashed border-border">
              No endpoints yet
            </div>
          ) : (
            endpoints.map((ep) => {
              const editing = mode.kind === 'edit' && mode.id === ep.id;
              return (
                <div
                  key={ep.id}
                  className={cn(
                    'p-4 border rounded-lg transition-colors',
                    editing ? 'bg-surface-raised border-primary/50' : 'border-border bg-surface',
                  )}
                >
                  {editing ? (
                    <EndpointForm
                      form={form}
                      setForm={setForm}
                      onSubmit={() => submitEdit(ep.id)}
                      onCancel={reset}
                      submitLabel="Update"
                    />
                  ) : (
                    <div className="flex items-center justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-medium text-sm text-text">{ep.name}</span>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-surface-raised text-text-muted border border-border">
                            {ep.provider}
                          </span>
                          {!chatCapable.has(ep.provider) && (
                            <span
                              className="text-xs px-2 py-0.5 rounded-full bg-warning-muted text-warning border border-warning/20"
                              data-testid="not-chat-capable"
                            >
                              {NOT_CHAT_CAPABLE_LABEL}
                            </span>
                          )}
                        </div>
                        <code className="text-xs text-text-subtle font-mono truncate block max-w-[280px]">{ep.url}</code>
                        {testResults[ep.id] && (
                          <div
                            className={cn(
                              'text-xs mt-2 flex items-center gap-1.5',
                              testResults[ep.id].success ? 'text-success' : 'text-error',
                            )}
                          >
                            {testResults[ep.id].success ? (
                              <CheckCircle className="w-3.5 h-3.5" />
                            ) : (
                              <AlertCircle className="w-3.5 h-3.5" />
                            )}
                            {testResults[ep.id].message}
                          </div>
                        )}
                      </div>
                      <div className="flex gap-2 ml-4">
                        <Button
                          onClick={() => void runTest(ep)}
                          disabled={testingId === ep.id}
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Test connection"
                        >
                          <Play className={cn('w-4 h-4', testingId === ep.id && 'animate-pulse')} />
                        </Button>
                        <Button onClick={() => startEdit(ep)} variant="ghost" size="icon-sm" aria-label="Edit">
                          <Edit2 className="w-4 h-4" />
                        </Button>
                        <Button
                          onClick={() => onDelete(ep.id)}
                          variant="ghost"
                          size="icon-sm"
                          className="hover:text-error"
                          aria-label="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {mode.kind === 'add' ? (
          <div className="p-4 border border-border rounded-lg bg-surface-raised/50">
            <h4 className="text-sm font-semibold text-text mb-4">Add endpoint</h4>
            <EndpointForm form={form} setForm={setForm} onSubmit={submitAdd} onCancel={reset} submitLabel="Add endpoint" />
          </div>
        ) : (
          <button
            onClick={() => {
              setForm(EMPTY_FORM);
              setMode({ kind: 'add' });
            }}
            className="w-full py-3 border border-dashed border-border rounded-lg text-sm text-text-muted hover:text-text hover:border-primary/50 hover:bg-surface-raised transition-all flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add endpoint
          </button>
        )}
      </div>

      {/* LEG-MOD-02: Cloud API data-flow disclosure consent modal */}
      <CloudDisclosureModal
        open={disclosure !== null}
        onOpenChange={(o) => {
          if (!o) setDisclosure(null);
        }}
        providerName={disclosure?.providerName ?? ''}
        onAccept={() => {
          disclosure?.action();
          setDisclosure(null);
        }}
        onDecline={() => setDisclosure(null)}
      />
    </>
  );
}
```

- [ ] **Step 3: Rewrite `hooks/useLLMConfig.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useRef, useState } from 'react'
import type { EndpointTestResult, LLMConfig, ModelDetail, SavedEndpoint, SlotName } from '@/types/llm'
import { emptyLLMConfig, SLOT_NAMES } from '@/types/llm'
import { apiUrl } from '@/lib/apiBase'

export type SlotStatus = 'connected' | 'disconnected' | 'not-configured' | 'loading'

const SAVE_DEBOUNCE_MS = 800
const JSON_HEADERS = { 'Content-Type': 'application/json' }

function stripLatest(name: string): string {
  return name.replace(/:latest$/, '')
}

export function sameModel(a: string, b: string): boolean {
  return a === b || stripLatest(a) === stripLatest(b)
}

function newEndpointId(): string {
  return `ep_${Math.random().toString(16).slice(2, 10)}`
}

interface ConfigPayload {
  llm_config?: LLMConfig
  chat_capable_providers?: string[]
}

/**
 * Halbert's model configuration — three slots and an endpoint list, persisted
 * through GET/PUT /llm/config (halbert_core/model/llm_config.py). Edits are
 * debounced into one PUT; a pending save is flushed on unmount.
 */
export function useLLMConfig() {
  const [llmConfig, setLLMConfig] = useState<LLMConfig>(emptyLLMConfig)
  const [chatCapableProviders, setChatCapableProviders] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({})
  const [modelDetails, setModelDetails] = useState<Record<string, ModelDetail[]>>({})
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({})
  const [testingSlot, setTestingSlot] = useState<SlotName | null>(null)
  const [testResults, setTestResults] = useState<Record<string, EndpointTestResult>>({})

  const dirtyRef = useRef(false)
  const configRef = useRef(llmConfig)
  configRef.current = llmConfig
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const applyServer = useCallback((data: unknown) => {
    const d = (data ?? {}) as ConfigPayload
    if (d.llm_config && typeof d.llm_config === 'object') setLLMConfig(d.llm_config)
    if (Array.isArray(d.chat_capable_providers)) setChatCapableProviders(d.chat_capable_providers)
  }, [])

  const reload = useCallback(async () => {
    try {
      const r = await fetch(apiUrl('/llm/config'))
      if (r.ok) {
        const json = await r.json()
        applyServer(json?.data ?? json)
      }
    } catch {
      // keep defaults
    } finally {
      setLoaded(true)
    }
  }, [applyServer])

  useEffect(() => {
    void reload()
  }, [reload])

  const persist = useCallback(
    async (cfg: LLMConfig) => {
      try {
        const r = await fetch(apiUrl('/llm/config'), {
          method: 'PUT',
          headers: JSON_HEADERS,
          body: JSON.stringify({ llm_config: cfg }),
        })
        if (!r.ok) {
          // e.g. 422 PROVIDER_NOT_CHAT_CAPABLE — resync with what the server kept.
          await reload()
          return
        }
        const json = await r.json()
        const d = (json?.data ?? json) as ConfigPayload
        if (Array.isArray(d.chat_capable_providers)) setChatCapableProviders(d.chat_capable_providers)
      } catch {
        // offline: keep local edits; the next change retries
      }
    },
    [reload],
  )

  const change = useCallback((updater: (prev: LLMConfig) => LLMConfig) => {
    dirtyRef.current = true
    setLLMConfig(updater)
  }, [])

  // Debounced autosave after every local change (never after a server load).
  useEffect(() => {
    if (!loaded || !dirtyRef.current) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      dirtyRef.current = false
      void persist(llmConfig)
    }, SAVE_DEBOUNCE_MS)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [llmConfig, loaded, persist])

  // Flush a pending save when the settings page unmounts.
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (dirtyRef.current) {
        dirtyRef.current = false
        void persist(configRef.current)
      }
    },
    [persist],
  )

  // ── Endpoints ────────────────────────────────────────────────

  const addEndpoint = useCallback(
    (ep: Omit<SavedEndpoint, 'id'>) => {
      change((prev) => ({ ...prev, saved_endpoints: [...prev.saved_endpoints, { ...ep, id: newEndpointId() }] }))
    },
    [change],
  )

  const editEndpoint = useCallback(
    (ep: SavedEndpoint) => {
      change((prev) => ({ ...prev, saved_endpoints: prev.saved_endpoints.map((e) => (e.id === ep.id ? ep : e)) }))
    },
    [change],
  )

  const deleteEndpoint = useCallback(
    (id: string) => {
      change((prev) => {
        const next: LLMConfig = { ...prev, saved_endpoints: prev.saved_endpoints.filter((e) => e.id !== id) }
        for (const slot of SLOT_NAMES) {
          if (next[slot].endpoint_id === id) next[slot] = { enabled: false, endpoint_id: '', model: '' }
        }
        return next
      })
    },
    [change],
  )

  const testEndpoint = useCallback(async (ep: SavedEndpoint): Promise<EndpointTestResult> => {
    const r = await fetch(apiUrl('/api/llm/proxy/test'), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key }),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const json = await r.json()
    const data = (json?.data ?? json) as EndpointTestResult
    if (Array.isArray(data.models)) setAvailableModels((prev) => ({ ...prev, [ep.id]: data.models as string[] }))
    return data
  }, [])

  const fetchModels = useCallback(async (endpointId: string): Promise<string[]> => {
    const ep = configRef.current.saved_endpoints.find((e) => e.id === endpointId)
    if (!ep) return []
    setLoadingModels((prev) => ({ ...prev, [endpointId]: true }))
    try {
      const r = await fetch(apiUrl('/api/llm/proxy/models'), {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key }),
      })
      const json = await r.json().catch(() => null)
      if (!r.ok) return []
      const data = json?.data ?? json
      const models: string[] = Array.isArray(data?.models) ? data.models : []
      setAvailableModels((prev) => ({ ...prev, [endpointId]: models }))
      if (Array.isArray(data?.model_details)) {
        setModelDetails((prev) => ({ ...prev, [endpointId]: data.model_details as ModelDetail[] }))
      }
      return models
    } catch {
      return []
    } finally {
      setLoadingModels((prev) => ({ ...prev, [endpointId]: false }))
    }
  }, [])

  // ── Slots ────────────────────────────────────────────────────

  const clearSlotResult = useCallback((slot: SlotName) => {
    setTestResults((prev) => {
      const next = { ...prev }
      delete next[slot]
      return next
    })
  }, [])

  const setSlotEndpoint = useCallback(
    (slot: SlotName, endpointId: string) => {
      clearSlotResult(slot)
      if (!endpointId || endpointId === '__disconnect__') {
        change((prev) => ({ ...prev, [slot]: { enabled: false, endpoint_id: '', model: '' } }))
        return
      }
      change((prev) => ({ ...prev, [slot]: { enabled: false, endpoint_id: endpointId, model: '' } }))
      void fetchModels(endpointId)
    },
    [change, clearSlotResult, fetchModels],
  )

  const setSlotModel = useCallback(
    (slot: SlotName, model: string) => {
      clearSlotResult(slot)
      change((prev) => ({
        ...prev,
        [slot]: { ...prev[slot], model, enabled: !!model && !!prev[slot].endpoint_id },
      }))
    },
    [change, clearSlotResult],
  )

  const testSlot = useCallback(async (slot: SlotName): Promise<EndpointTestResult> => {
    const cfg = configRef.current[slot]
    const ep = configRef.current.saved_endpoints.find((e) => e.id === cfg.endpoint_id)
    if (!ep || !cfg.model) {
      const res = { success: false, message: 'Choose an endpoint and a model first.' }
      setTestResults((prev) => ({ ...prev, [slot]: res }))
      return res
    }
    setTestingSlot(slot)
    try {
      const r = await fetch(apiUrl('/api/llm/proxy/test-model'), {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key, model: cfg.model, slot }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const json = await r.json()
      const data = (json?.data ?? json) as EndpointTestResult
      setTestResults((prev) => ({ ...prev, [slot]: data }))
      return data
    } catch (e) {
      const res = { success: false, message: e instanceof Error ? e.message : 'Test failed' }
      setTestResults((prev) => ({ ...prev, [slot]: res }))
      return res
    } finally {
      setTestingSlot(null)
    }
  }, [])

  const slotStatus = useCallback(
    (slot: SlotName): SlotStatus => {
      const cfg = llmConfig[slot]
      if (testResults[slot]?.success) return 'connected'
      if (!cfg.endpoint_id || !cfg.model) return 'not-configured'
      if (!llmConfig.saved_endpoints.some((e) => e.id === cfg.endpoint_id)) return 'disconnected'
      const models = availableModels[cfg.endpoint_id] ?? []
      if (models.length === 0) return loadingModels[cfg.endpoint_id] ? 'loading' : 'connected'
      return models.some((m) => sameModel(m, cfg.model)) ? 'connected' : 'disconnected'
    },
    [llmConfig, availableModels, loadingModels, testResults],
  )

  // Fetch the model list for every endpoint a slot points at, once config is in.
  useEffect(() => {
    if (!loaded) return
    for (const slot of SLOT_NAMES) {
      const id = llmConfig[slot].endpoint_id
      if (id && !availableModels[id]) void fetchModels(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, llmConfig.chat_model.endpoint_id, llmConfig.specialist_model.endpoint_id, llmConfig.vision_model.endpoint_id])

  return {
    llmConfig,
    chatCapableProviders,
    loaded,
    availableModels,
    modelDetails,
    loadingModels,
    testingSlot,
    testResults,
    reload,
    addEndpoint,
    editEndpoint,
    deleteEndpoint,
    testEndpoint,
    fetchModels,
    setSlotEndpoint,
    setSlotModel,
    testSlot,
    slotStatus,
  }
}
```

---

### Task 9: `ModelSettings` and `QuickSetup` (test first)

**Files:**
- Create: `frontend/src/components/llm/QuickSetup.tsx`, `frontend/src/components/llm/QuickSetup.test.tsx`
- Create: `frontend/src/components/llm/ModelSettings.tsx`, `frontend/src/components/llm/ModelSettings.test.tsx`

- [ ] **Step 1: Write the failing `QuickSetup` test**

`frontend/src/components/llm/QuickSetup.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * QuickSetup — the strip shown while no chat model is configured. Three states
 * driven by /api/settings/model/status; the apply button posts apply-recommended.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QuickSetup } from './QuickSetup'

function status(local: { reachable: boolean; model_count: number }) {
  return {
    chat: { configured: false, model: '', endpoint_url: '', provider: '', reachable: false, model_available: false },
    local_ollama: { url: 'http://localhost:11434', ...local },
    hardware: { tier: 1, total_vram_gb: null },
  }
}

function mockFetch(statusBody: unknown, applyBody: unknown = { success: true, message: 'Applied' }) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('apply-recommended') ? applyBody : statusBody
    return { ok: true, status: 200, json: async () => body } as Response
  })
}

describe('QuickSetup', () => {
  it('offers hardware defaults when local Ollama has models', async () => {
    mockFetch(status({ reachable: true, model_count: 3 }))
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText('Local Ollama detected with 3 models.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /largest model that fits/i })).toBeInTheDocument()
  })

  it('asks for a pull when Ollama is up but empty', async () => {
    mockFetch(status({ reachable: true, model_count: 0 }))
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText(/has no models yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /largest model/i })).toBeNull()
  })

  it('shows the ollama serve hint when nothing is reachable', async () => {
    mockFetch(status({ reachable: false, model_count: 0 }))
    render(<QuickSetup onApplied={() => {}} />)
    expect(await screen.findByText('ollama serve')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run in terminal/i })).toBeInTheDocument()
  })

  it('posts apply-recommended and reports back', async () => {
    const fetchMock = mockFetch(status({ reachable: true, model_count: 1 }))
    const onApplied = vi.fn()
    render(<QuickSetup onApplied={onApplied} />)
    await userEvent.click(await screen.findByRole('button', { name: /largest model that fits/i }))
    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1))
    const applyCall = fetchMock.mock.calls.find(([u]) => String(u).includes('apply-recommended'))
    expect(applyCall?.[1]).toMatchObject({ method: 'POST' })
    expect(screen.getByText('Applied')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/llm/QuickSetup.test.tsx`
Expected: `Failed to resolve import "./QuickSetup"`.

- [ ] **Step 3: Write `QuickSetup.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Terminal, Zap } from 'lucide-react'
import { Button } from '@/components/prep-primitives/Button'
import { apiUrl } from '@/lib/apiBase'

/** Shape of GET /api/settings/model/status. */
export interface ModelStatusResponse {
  chat: {
    configured: boolean
    model: string
    endpoint_url: string
    provider: string
    reachable: boolean
    model_available: boolean
  }
  local_ollama: { reachable: boolean; url: string; model_count: number }
  hardware: { tier: number; total_vram_gb: number | null }
}

/**
 * First-run helper shown by ModelSettings while no chat model is configured.
 * Folds in the two useful pieces of the old Connection Status card: the
 * hardware-aware "use the largest installed model" action and the
 * "Ollama is not running" hint.
 */
export function QuickSetup({ onApplied }: { onApplied: () => void | Promise<void> }) {
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetch(apiUrl('/api/settings/model/status'))
      setStatus(r.ok ? ((await r.json()) as ModelStatusResponse) : null)
    } catch {
      setStatus(null)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const apply = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const r = await fetch(apiUrl('/api/settings/model/apply-recommended'), { method: 'POST' })
      const data = (await r.json()) as { success?: boolean; message?: string }
      setMessage(data.message ?? null)
      if (data.success) await onApplied()
    } catch {
      setMessage('Could not apply hardware defaults.')
    } finally {
      setBusy(false)
    }
  }

  const runInTerminal = () =>
    window.dispatchEvent(new CustomEvent('halbert:run-command', { detail: { command: 'ollama serve' } }))

  if (!status) return null
  const ollama = status.local_ollama
  const row = 'flex items-center justify-between gap-4 flex-wrap'

  return (
    <div className="rounded-lg border border-border bg-surface-raised p-4 space-y-3" data-testid="quick-setup">
      {ollama.reachable && ollama.model_count > 0 && (
        <div className={row}>
          <p className="text-sm text-text">
            Local Ollama detected with {ollama.model_count} {ollama.model_count === 1 ? 'model' : 'models'}.
          </p>
          <Button size="sm" onClick={() => void apply()} loading={busy}>
            <Zap className="w-3.5 h-3.5" />
            Use the largest model that fits my hardware
          </Button>
        </div>
      )}
      {ollama.reachable && ollama.model_count === 0 && (
        <div className={row}>
          <p className="text-sm text-text">Local Ollama is running but has no models yet. Pull one, then refresh.</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </Button>
        </div>
      )}
      {!ollama.reachable && (
        <div className={row}>
          <p className="text-sm text-text">
            No LLM endpoint is reachable. Start Ollama with{' '}
            <code className="bg-surface px-1 rounded font-mono text-xs">ollama serve</code> or add an endpoint below.
          </p>
          <Button size="sm" variant="outline" onClick={runInTerminal}>
            <Terminal className="w-3.5 h-3.5" />
            Run in terminal
          </Button>
        </div>
      )}
      {message && <p className="text-xs text-text-muted">{message}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run the QuickSetup test**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/llm/QuickSetup.test.tsx`
Expected: `4 passed`.

- [ ] **Step 5: Write the failing `ModelSettings` test**

`frontend/src/components/llm/ModelSettings.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ModelSettings — Halbert's picker: exactly three slots, Halbert vocabulary,
 * endpoints chat cannot use are badged and kept out of slot dropdowns.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ModelSettings } from './ModelSettings'

const ENDPOINTS = [
  { id: 'e1', name: 'Local Ollama', provider: 'ollama', url: 'http://localhost:11434', api_key: '' },
  { id: 'a1', name: 'Claude', provider: 'anthropic', url: 'https://api.anthropic.com', api_key: 'k' },
]

function config(chatEnabled: boolean) {
  return {
    llm_config: {
      saved_endpoints: ENDPOINTS,
      chat_model: chatEnabled
        ? { enabled: true, endpoint_id: 'e1', model: 'chat-a' }
        : { enabled: false, endpoint_id: '', model: '' },
      specialist_model: { enabled: false, endpoint_id: '', model: '' },
      vision_model: { enabled: false, endpoint_id: '', model: '' },
    },
    chat_capable_providers: ['lm-studio', 'ollama', 'openai', 'openai-compatible'],
  }
}

const STATUS = {
  chat: { configured: false, model: '', endpoint_url: '', provider: '', reachable: false, model_available: false },
  local_ollama: { reachable: true, url: 'http://localhost:11434', model_count: 1 },
  hardware: { tier: 1, total_vram_gb: null },
}

function mockFetch(chatEnabled: boolean) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    let body: unknown = {}
    if (url.includes('/llm/config')) body = { data: config(chatEnabled) }
    else if (url.includes('/proxy/models')) body = { data: { models: ['chat-a'] } }
    else if (url.includes('/model/status')) body = STATUS
    return { ok: true, status: 200, json: async () => body } as Response
  })
}

describe('ModelSettings', () => {
  beforeEach(() => {
    mockFetch(true)
  })

  it('renders exactly the three Halbert slots and no SourcePrep vocabulary', async () => {
    render(<ModelSettings />)
    expect(await screen.findByText('Chat model')).toBeInTheDocument()
    expect(screen.getByText('Specialist model')).toBeInTheDocument()
    expect(screen.getByText('Vision model')).toBeInTheDocument()
    expect(screen.queryByText(/embedding|sourceprep|coordinator|swarm|thinking model|fast model|code model/i)).toBeNull()
  })

  it('badges endpoints chat cannot use and keeps them out of the slot dropdowns', async () => {
    render(<ModelSettings />)
    expect(await screen.findByText('Claude')).toBeInTheDocument()
    expect(screen.getByTestId('not-chat-capable')).toBeInTheDocument()
    expect(screen.getAllByRole('option', { name: 'Local Ollama (ollama)' })).toHaveLength(3)
    expect(screen.queryByRole('option', { name: 'Claude (anthropic)' })).toBeNull()
  })

  it('hides quick setup once a chat model is configured', async () => {
    render(<ModelSettings />)
    await screen.findByText('Chat model')
    expect(screen.queryByTestId('quick-setup')).toBeNull()
  })

  it('shows quick setup while chat is unconfigured', async () => {
    vi.restoreAllMocks()
    mockFetch(false)
    render(<ModelSettings />)
    expect(await screen.findByTestId('quick-setup')).toBeInTheDocument()
    expect(screen.getByText('Local Ollama detected with 1 model.')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/llm/ModelSettings.test.tsx`
Expected: `Failed to resolve import "./ModelSettings"`.

- [ ] **Step 7: Write `ModelSettings.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Cpu, Eye, MessageSquare, Microscope } from 'lucide-react'
import { ModelCard } from './ModelCard'
import { EndpointManager } from './EndpointManager'
import { QuickSetup } from './QuickSetup'
import { useLLMConfig } from '@/hooks/useLLMConfig'
import type { SlotName } from '@/types/llm'
import { SLOT_NAMES } from '@/types/llm'

// Halbert's vocabulary. No model names, no product names.
const SLOT_COPY: Record<SlotName, { title: string; description: string; icon: JSX.Element }> = {
  chat_model: {
    title: 'Chat model',
    description: 'The model you talk to. Required.',
    icon: <MessageSquare className="w-5 h-5" />,
  },
  specialist_model: {
    title: 'Specialist model',
    description: 'Complex diagnostics and multi-step reasoning. Optional — routed by complexity; leave empty to use the Chat model.',
    icon: <Microscope className="w-5 h-5" />,
  },
  vision_model: {
    title: 'Vision model',
    description: 'Screenshots and images. Optional — leave empty to send images to the Chat model.',
    icon: <Eye className="w-5 h-5" />,
  },
}

/**
 * Settings → AI Models. Three slots on the kept ModelCard primitive, the
 * trimmed EndpointManager, and a Quick-setup strip while Chat is unset.
 */
export function ModelSettings() {
  const llm = useLLMConfig()
  const chatCapable = new Set(llm.chatCapableProviders)
  const slotEndpoints = llm.llmConfig.saved_endpoints.filter((ep) => chatCapable.has(ep.provider))

  return (
    <div className="space-y-6" data-testid="model-settings">
      <div>
        <h2 className="text-xl font-semibold flex items-center gap-2 text-text">
          <Cpu className="w-6 h-6 text-primary" />
          AI Models
        </h2>
        <p className="text-sm text-text-muted mt-1">Choose which models Halbert talks to, and where they run.</p>
      </div>

      {llm.loaded && !llm.llmConfig.chat_model.enabled && <QuickSetup onApplied={llm.reload} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {SLOT_NAMES.map((slot) => {
          const cfg = llm.llmConfig[slot]
          const copy = SLOT_COPY[slot]
          return (
            <ModelCard
              key={slot}
              title={copy.title}
              description={copy.description}
              icon={copy.icon}
              endpoint={cfg.endpoint_id || undefined}
              model={cfg.model || undefined}
              endpoints={slotEndpoints}
              onEndpointChange={(id) => llm.setSlotEndpoint(slot, id)}
              availableModels={llm.availableModels[cfg.endpoint_id] ?? []}
              modelDetails={llm.modelDetails[cfg.endpoint_id]}
              onModelChange={(model) => llm.setSlotModel(slot, model)}
              onRefreshModels={() => {
                if (cfg.endpoint_id) void llm.fetchModels(cfg.endpoint_id)
              }}
              loadingModels={!!llm.loadingModels[cfg.endpoint_id]}
              status={llm.slotStatus(slot)}
              onTest={() => void llm.testSlot(slot)}
              testResult={llm.testResults[slot]}
              testingConnection={llm.testingSlot === slot}
            />
          )
        })}
      </div>

      <EndpointManager
        endpoints={llm.llmConfig.saved_endpoints}
        onAdd={llm.addEndpoint}
        onEdit={llm.editEndpoint}
        onDelete={llm.deleteEndpoint}
        onTest={llm.testEndpoint}
        chatCapableProviders={llm.chatCapableProviders}
      />
    </div>
  )
}
```

- [ ] **Step 8: Run both component tests**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/llm/`
Expected: `ModelSettings.test.tsx` 4 passed, `QuickSetup.test.tsx` 4 passed, `ProbeButton.test.tsx` 8 passed.

---

### Task 10: Wire `Settings.tsx`, delete the vendored page, build

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`
- Rewrite: `frontend/src/components/llm/index.ts`
- Modify: `frontend/vite.config.ts:21`, `halbert_core/tests/test_frontend_no_relative_urls.py:15-18`
- Delete: `frontend/src/components/llm/AIModelsSettings.tsx`, `UnifiedLLMSettings.tsx`, `AdvancedLLMSettings.tsx`, `PlanDropdown.tsx`, `llmConfigHelpers.ts`, `stubs/` (3 files), `frontend/src/hooks/useSourcePrepDaemon.ts`

- [ ] **Step 1: Delete the vendored page and its satellites**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src
git rm -q components/llm/AIModelsSettings.tsx components/llm/UnifiedLLMSettings.tsx components/llm/AdvancedLLMSettings.tsx components/llm/PlanDropdown.tsx components/llm/llmConfigHelpers.ts components/llm/stubs/ConcurrencyResetPanel.tsx components/llm/stubs/LLMAssignmentBlockCard.tsx components/llm/stubs/LLMAssignmentsPipeline.tsx hooks/useSourcePrepDaemon.ts
```

- [ ] **Step 2: Rewrite `components/llm/index.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
export { ModelSettings } from './ModelSettings';
export { QuickSetup } from './QuickSetup';
export type { ModelStatusResponse } from './QuickSetup';
export { ModelCard } from './ModelCard';
export type { ModelCardProps } from './ModelCard';
export { EndpointManager, PROVIDER_OPTIONS, NOT_CHAT_CAPABLE_LABEL } from './EndpointManager';
export type { EndpointManagerProps } from './EndpointManager';
export { ProbeButton } from './ProbeButton';
export type { ProbeButtonProps, ProbeResult, ProbeButtonState } from './ProbeButton';
```

- [ ] **Step 3: Edit `pages/Settings.tsx`**

1. Import: replace `import { UnifiedLLMSettings } from '@/components/llm'` with `import { ModelSettings } from '@/components/llm'`.
2. In the `lucide-react` import list remove `Link,` and `Terminal,` (each is used only by the card being deleted; `Check`, `X`, `Zap`, `RefreshCw` stay — they are used elsewhere).
3. Delete the `interface ModelStatus { ... }` block (lines ~69–80, ending with `compression_backend?: string` and `}`).
4. Delete the three state lines:

```tsx
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [hardwareDefaultsMessage, setHardwareDefaultsMessage] = useState<string | null>(null)
```

5. In `loadSettings`, delete the block starting at the comment `// Load model status (connection + availability)` through the `finally { setLoadingStatus(false) }` that closes it (about 13 lines).
6. In the AI tab, delete from the comment `{/* Unified LLM Model Picker (SourcePrep integration) */}` through the closing `</Card>` of the "LLM Connection Status" card — i.e. everything up to, but not including, the line `{/* Context Compression - Phase 72 */}` that is immediately followed by `<CompressionSettings />`. (There is an earlier `{/* Context Compression - Phase 72 */}` comment *inside* the card; it goes with the card.) Insert in its place:

```tsx
          <ModelSettings />
```

7. Verify nothing dangling: `grep -n "modelStatus\|loadingStatus\|hardwareDefaultsMessage\|UnifiedLLMSettings\|ModelStatus\b" src/pages/Settings.tsx` → no output.

- [ ] **Step 4: Trim the dev proxy and the URL guard's exclusion**

`frontend/vite.config.ts`: change `const http = ['/api', '/global', '/llm', '/embedding', '/compute']` to `const http = ['/api', '/llm', '/compute']`.

`halbert_core/tests/test_frontend_no_relative_urls.py`: delete the line `"hooks/useSourcePrepDaemon.ts",  # talks to the external SourcePrep daemon (absolute URL)` from `EXCLUDED`.

- [ ] **Step 5: Check for stragglers**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && grep -rn "useSourcePrepDaemon\|AdvancedLLMSettings\|PlanDropdown\|llmConfigHelpers\|stubs/\|AIModelsSettings\|UnifiedLLMSettings\|/global/config\|small_model\|large_model\|code_model\|coordinator_model" src`
Expected: no output. If `src/hooks/index.ts` re-exports a deleted hook, remove that line.

- [ ] **Step 6: Build and test**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npm run build 2>&1 | tail -5 && npx vitest run 2>&1 | tail -6`
Expected: `tsc` clean (no `error TS…` lines; `noUnusedLocals` is on, so any leftover import fails here), `✓ built in …`, and every test file passing.

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/test_frontend_no_relative_urls.py -q`
Expected: pass.

- [ ] **Step 7: Commit Tasks 8–10 together**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend
git add src/types/llm.ts src/hooks/useLLMConfig.ts src/components/llm/EndpointManager.tsx src/components/llm/ModelSettings.tsx src/components/llm/ModelSettings.test.tsx src/components/llm/QuickSetup.tsx src/components/llm/QuickSetup.test.tsx src/components/llm/index.ts src/pages/Settings.tsx vite.config.ts
git add -u src/components/llm src/hooks   # records the git rm deletions
git add /Volumes/4TB-BAD/Halbert/halbert_core/tests/test_frontend_no_relative_urls.py
git status --short   # must list ONLY the files above; if it shows anything else, unstage it with `git restore --staged <path>`
git commit -m "feat(dashboard): Halbert's own three-slot model picker

Settings → AI Models is now ModelSettings: Chat, Specialist and Vision
on the kept ModelCard primitive, a trimmed EndpointManager (all seven
providers, badged where chat cannot call them yet), and a Quick-setup
strip that replaces the legacy Connection Status card. The vendored
SourcePrep page, its mode toggle, embedding/code/coordinator cards,
plan-tier and concurrency fields, stubs, and the daemon probe are gone."
```

---

### Task 11: Full gates and the live migration check

**Files:** none new.

- [ ] **Step 1: Whole backend suite**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core && python -m pytest tests/ -q --ignore=tests/rag 2>&1 | tail -3`
Expected: all pass, no errors. (Pre-existing skips are fine; any new failure is yours. If `pytest-asyncio` is not installed in your venv, pre-existing `async def` tests in other files report "async def functions are not natively supported" — that is environmental, not yours; `pip install pytest-asyncio` matches CI.)

- [ ] **Step 2: Whole frontend suite + build**

Run: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run 2>&1 | tail -4 && npm run build 2>&1 | tail -3`
Expected: all test files pass; `✓ built in …`.

- [ ] **Step 3: Live check against the real user config**

This is the one step that touches the developer's actual `~/Library/Application Support/Halbert/models.yml` (the file that currently carries `orchestrator.model` under the legacy key). Do it from the worktree; the config dir is outside the repo.

```bash
# 1. Snapshot for your own comparison (the store also writes models.yml.bak)
cp "$HOME/Library/Application Support/Halbert/models.yml" /tmp/models.before.yml

# 2. Start the backend from the worktree
cd <worktree>/halbert_core && python -m halbert_core.dashboard &   # serves on :8000
sleep 3

# 3. First read triggers the migration
curl -s localhost:8000/llm/config | python -m json.tool
```

Expected in the JSON: `chat_model.enabled == true` with the model name that was under `orchestrator.model` in `/tmp/models.before.yml`; both legacy endpoints (Local Ollama and LM Studio) present once each in `saved_endpoints` with their API keys; `chat_capable_providers` listed.

```bash
# 4. The file was rewritten once, with a backup
ls -la "$HOME/Library/Application Support/Halbert/models.yml.bak"
grep -c "^orchestrator:\|^specialist:\|^vision:\|^saved_endpoints:" "$HOME/Library/Application Support/Halbert/models.yml"   # expected: 0
grep -A3 "^compression:" "$HOME/Library/Application Support/Halbert/models.yml"                                             # expected: unchanged values

# 5. Status is read-only and sees the migrated slot
curl -s localhost:8000/api/settings/model/status | python -m json.tool     # chat.configured true, local_ollama.reachable per your machine
```

6. Open the dashboard (`npm run dev` in the frontend dir, or the Tauri app), go to Settings → AI Models: three cards, Chat shows the migrated model with status Connected, no Quick-setup strip, endpoints listed. Send one chat message and confirm it answers. Then temporarily clear the Chat model in the UI → the Quick-setup strip appears → set it back.

7. If anything in 3–6 is wrong, stop and fix before Task 12; do not hand-edit the user's file — restore from `/tmp/models.before.yml`, fix the code, rerun.

---

### Task 12: Docs — supersede, resolve, attribute

**Files:**
- Modify: `documentation/design/unified-model-picker.md:1-3`
- Modify: `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md` (append)
- Modify: `documentation/legal/THIRD-PARTY-LICENSES.md:283`

- [ ] **Step 1: Mark the old plan superseded**

Replace the first three lines of `documentation/design/unified-model-picker.md`:

```markdown
# Unified Model Picker — Implementation Strategy & Design

> **Superseded 2026-08-26.** Halbert's model picker is now independent of
> SourcePrep — see `model-picker-independent-2026-08-26.md`. This document is
> kept as the record of the shared-package plan and why it was abandoned
> (it required SourcePrep changes and produced two schemas in one file).

**Status:** Superseded (was: Plan set 2026-08-23).
```

- [ ] **Step 2: Resolve the review doc's six questions**

Append to `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`:

```markdown

---

## Resolution (2026-08-26)

Decided in `documentation/design/model-picker-independent-2026-08-26.md`;
implemented per `.handoff/MODEL-PICKER-PLAN-2026-08-26.md`.

1. **Slot mapping** — correct read, and moot: Halbert no longer shares slot
   names. Slots are `chat_model` / `specialist_model` / `vision_model`.
2. **Defer only the specialist?** — No deferral at all. Runtime coupling to a
   daemon that may be down was the source of the complexity. A one-shot
   "Import from SourcePrep" is a follow-up.
3. **Separate component vs prop filtering** — Neither: the vendored page is
   deleted; Halbert has a ~100-line `ModelSettings` on the kept `ModelCard`
   and a rewritten `EndpointManager`.
4. **Shared endpoint list** — Not shared. Import follow-up covers it.
5. **Legacy keys** — Migrated once by `model/llm_config.py` (with a `.bak`),
   then removed; no reader keeps a fallback.
6. **Simpler design** — Yes: one schema, one store module, no new backend
   proxy, no daemon probe, no checkbox.
```

- [ ] **Step 3: Fix the licence attribution row**

In `documentation/legal/THIRD-PARTY-LICENSES.md` line ~283, change `dashboard/routes/llm.py (Ollama Cloud candidate list)` to `dashboard/routes/llm.py (LLM proxy routes)`.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git add documentation/design/unified-model-picker.md documentation/legal/THIRD-PARTY-LICENSES.md
git add .handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md   # untracked until now; this is intentional
git commit -m "docs(design): supersede the unified picker plan, resolve the review questions"
```

---

## Follow-ups recorded, not done here

- Import-from-SourcePrep button (spec §11.1).
- Vision "provided by Chat" hint via `model/capabilities.py` (§11.2).
- Anthropic / Google / Azure chat adapters onto the request shapes already in `proxy_test_model` (§11.3); then drop them from `NOT_CHAT_CAPABLE_LABEL`.
- `ProbeButton.tsx`, its test, and `routes/compute.py` now have no UI consumer (the capacity probe wrote the deleted `cloud_concurrency` field). Kept per spec §6.3; remove in the EndpointManager follow-up (§11.5).
- The two `if True:` un-nesting shims in `proxy_test_model` (Task 3 step 4) can be flattened by `/simplify`.

