# Task Packet 03: Security CLI Tools Migration & Operational Index Rebuild

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U1 — runs with TASK-09 verification and REV-01/REV-02 security reviews)  
**Domain:** Security Tooling Packaging, CLI Console Scripts, and Operational SourcePrep Indexing  
**Target Date:** 2026-08-29  
**Status (verified 2026-08-30):** **Task 3.1 is DONE** — `halbert_core/halbert_core/cli/` exists with `check_credential.py`/`check_breach.py`, and `halbert_core/pyproject.toml:118-122` registers `halbert-check-credential`/`halbert-check-breach`. **Only Task 3.2 (rebuild script) remains.** Note: `test_cli_security.py` does not exist yet — create it as part of the batch.  
**Governing Documents:**
- [`.handoff/TIER2-RECALIBRATION-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TIER2-RECALIBRATION-2026-08-29.md)
- [`.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md)
- [`.handoff/MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md)

---

## 1. Executive Summary & Objective

During the Tier 2 Recalibration, two modules were identified as violating the architectural guarantee that `describe_secret` never triggers external network requests: `credential_validation.py` (sends secret to service API) and `compromise_detection.py` (sends secret to HIBP/GitHub). Although removed from the automated MCP tool path, these modules still sit in `config/`.

This task packet directs:
1. Moving these standalone human-run verification tools into a dedicated CLI package and exposing them via console scripts in `pyproject.toml` (`halbert-check-credential` and `halbert-check-breach`).
2. Creating an operational script `scripts/rebuild_sourceprep_unredacted.py` that stages raw files into SourcePrep with `redact=False` while proving that MCP egress and secure-model routing boundaries remain 100% airtight.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 3.1: ~~Package CLI Tools & Entrypoints~~ — DONE (2026-08-30)
1. Create directory `halbert_core/halbert_core/cli/` (with `__init__.py`).
2. Move and refactor:
   - `halbert_core/halbert_core/config/credential_validation.py` → `halbert_core/halbert_core/cli/check_credential.py`
   - `halbert_core/halbert_core/config/compromise_detection.py` → `halbert_core/halbert_core/cli/check_breach.py`
3. Add `argparse` CLI wrappers with clear human-facing output, confirmation prompts, and JSON output options.
4. Update `halbert_core/pyproject.toml` to register console scripts:
   ```toml
   [project.scripts]
   halbert = "halbert_core.cli.main:main"
   halbert-check-credential = "halbert_core.cli.check_credential:main"
   halbert-check-breach = "halbert_core.cli.check_breach:main"
   ```

### Task 3.2: Create Operational Unredacted Re-indexing Script
- **File:** [`scripts/rebuild_sourceprep_unredacted.py`](file:///Volumes/4TB-BAD/Halbert/scripts/rebuild_sourceprep_unredacted.py)
  1. Authenticate with the running SourcePrep daemon using `~/.config/halbert/prep_token` (`PREP_DAEMON_TOKEN`).
  2. Call `register_host_project(redact=False)` to stage host config trees with raw content.
  3. Call `snapshot(manifest_path, redact=False)` to populate the canon database with unredacted canonical JSON.
  4. Trigger a background SourcePrep index rebuild via `POST http://127.0.0.1:8400/api/reindex`.
  5. Run an immediate automated egress check: execute an MCP query for a known secret key and assert that only `describe_secret` metadata is emitted.

---

## 3. Verification & Test Plan

1. **CLI Script Tests:**
   ```bash
   pytest halbert_core/tests/test_cli_security.py -v
   ```
2. **Manual CLI Test Invocations:**
   ```bash
   halbert-check-credential --help
   halbert-check-breach --help
   ```
3. **Index Rebuild Verification:**
   ```bash
   python scripts/rebuild_sourceprep_unredacted.py --dry-run
   ```
