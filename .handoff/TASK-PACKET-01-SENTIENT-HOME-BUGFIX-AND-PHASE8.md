# Task Packet 01: Sentient Home Bug Fix, Model Routing & Phase 8 Light Variant

**Target Model:** **Fable Level**  
**Domain:** Ambient Home Cognition, Model Slot Architecture, Multi-Instance Isolation, and Light Client Packaging  
**Target Date:** 2026-08-29  
**Status:** Ready for Implementation  
**Governing Documents:**
- [`.handoff/PHASE7-8-TRANSITION-REVIEW-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/PHASE7-8-TRANSITION-REVIEW-2026-08-29.md)
- [`.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md)
- [`.handoff/SENTIENT-HOME-GAP-ANALYSIS.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SENTIENT-HOME-GAP-ANALYSIS.md)

---

## 1. Executive Summary & Objective

This packet addresses the transition from Phase 7 (Multi-Instance Isolation) to Phase 8 (Light Variant & Packaging). It fixes a critical bug where `HALBERT_MODEL` environment overrides are silently ignored by the model client, introduces a dedicated `secure_model` slot (defaulting to local `qwen3:4b`), serializes missing `BeingConfig` fields, and implements the lightweight client variant (`HALBERT_VARIANT=home-light`) for the macOS App Store companion.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 1.1: Add `secure_model` Slot & Fix `HALBERT_MODEL` Env Var Resolution
- **File:** [`halbert_core/halbert_core/model/llm_config.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/llm_config.py)
  1. Update `SLOTS` tuple:
     ```python
     SLOTS = ("chat_model", "specialist_model", "vision_model", "secure_model")
     ```
  2. In `default_llm_config()`, add the `secure_model` slot defaulting to `qwen3:4b` on the local Ollama provider.
  3. In `resolve(slot_name)`: Check `os.environ.get("HALBERT_MODEL")`. If present and `slot_name == "chat_model"`, use this as the primary override if `models.yml` has no user-configured model.
- **File:** [`halbert_core/halbert_core/model/client.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/client.py)
  1. Export `get_secure_model()` calling `_store.resolve("secure_model")`.

### Task 1.2: Add Missing `BeingConfig` YAML Serialization Fields
- **File:** [`halbert_core/halbert_core/config/being_config.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/being_config.py)
  1. Add fields to `BeingConfig`:
     ```python
     variant: str = "host"  # "host" | "home" | "home-light"
     ha_url: Optional[str] = None
     ha_token: Optional[str] = None
     scene_context: Optional[Dict[str, Any]] = None
     ```
  2. Ensure `load_being_config()` and `save_being_config()` properly parse and serialize these fields to `being.yml`.
  3. In [`halbert_core/halbert_core/integrations/cognition_wiring.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py), read `being_config.variant` as first priority before falling back to `os.environ.get("HALBERT_VARIANT")`.

### Task 1.3: Implement Phase 8 Light Variant (`home-light`)
- **File:** [`halbert_core/halbert_core/dashboard/app.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/app.py)
  1. When `HALBERT_VARIANT == "home-light"`:
     - Skip initializing local SourcePrep indexing daemons and heavy vector stores.
     - Configure `apiBase` to connect to an existing remote or local backend instance (`http://127.0.0.1:8400` or configured `REMOTE_HALBERT_HOST`).
     - Expose the lightweight FastAPI routes (voice, chat, instance switching) while disabling local ingestion endpoints.

### Task 1.4: Update Systemd & Deployment Templates
- **File:** [`deploy/halbert-home.service`](file:///Volumes/4TB-BAD/Halbert/deploy/halbert-home.service)
  1. Update `HALBERT_MODEL` reference from `qwen2.5:3b` to `qwen3:4b`.
  2. Clarify in comments that this configures the local secure fallback model.

---

## 3. Verification & Test Plan

Run the automated test suite to verify:
```bash
pytest halbert_core/tests/test_multi_instance.py halbert_core/tests/test_client.py halbert_core/tests/test_being_config.py -v
```
Ensure:
1. `HALBERT_MODEL=custom:model` is properly returned by `resolve("chat_model")` when no `models.yml` exists.
2. `get_secure_model()` resolves to `qwen3:4b` by default.
3. `BeingConfig` correctly saves and reloads `variant`, `ha_url`, and `scene_context`.
4. `HALBERT_VARIANT=home-light` initializes `app.py` in under 500ms without starting local indexers.
