# Task Packet 10: Apple Intelligence Foundation Integration & Onboarding

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U4)  
**Domain:** Apple Silicon Local Inference, Metal Detection, Auto-Provisioning, and Model Picker Integration  
**Target Date:** 2026-08-30  
**Status (verified 2026-08-30):** **Task 10.1 (merge) is DONE** — `feat/apple-intelligence` is on `main` (merge `11ded488`). Only Task 10.2 platform verification remains. Tests `test_apple_intelligence_platform.py` and `test_auto_provision.py` exist.  
**Branch:** `feat/apple-intelligence` (merged)

---

## 1. Executive Summary & Objective

The `feat/apple-intelligence` branch integrates Apple Foundation Models on macOS 15.1+ Apple Silicon hardware (M1/M2/M3/M4), providing zero-download, zero-configuration on-device inference for `secure_model` (and `chat_model` on 16-24GB Macs).

Key deliverables:
1. **Metal Platform Eligibility:** Detection of Apple Silicon, macOS version floor, and unified memory threshold.
2. **Idempotent Auto-Provisioning:** Automatic discovery and configuration of `apple-foundation` endpoint without clobbering user settings.
3. **Model Picker UI Banner:** Success badge in `ModelSettings.tsx` announcing native on-device model availability.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 10.1: ~~Merge `feat/apple-intelligence` into `main`~~ — DONE (merge `11ded488`, verified on `main` 2026-08-30)

### Task 10.2: Platform Verification & Endpoint Caching
- **File:** [`halbert_core/halbert_core/dashboard/routes/llm.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/llm.py)
  1. Verify that `HardwareDetector().detect()` is cached and only runs during first boot to avoid 1.2s page load delays.
- **File:** [`halbert_core/halbert_core/model/config_wizard.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/config_wizard.py)
  1. Confirm that `_build_config()` preserves Apple Foundation endpoints during wizard runs.

---

## 3. Verification & Test Plan

Run the platform and auto-provisioning test suite:
```bash
pytest halbert_core/tests/test_apple_intelligence_platform.py halbert_core/tests/test_auto_provision.py -v
```
