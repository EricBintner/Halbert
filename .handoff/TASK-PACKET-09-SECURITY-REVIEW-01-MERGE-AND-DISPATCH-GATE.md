# Task Packet 09: Security Review 01 Integration & Dispatch Egress Hardening

**Target Model:** **Fable Level**  
**Domain:** Security Architecture, MCP Egress Interception, Transport Hardening, and Server-Side Phrase Verification  
**Target Date:** 2026-08-30  
**Status:** Ready for Merge & Regression Verification  
**Branch:** `feat/security-review-01`

---

## 1. Executive Summary & Objective

The `feat/security-review-01` branch contains 5 vital security fixes developed on 2026-08-30:
1. **Dispatch-Level Egress Interception (`06e113cc`):** Shifts the Tier 2 secret boundary from individual tool handlers to the JSON-RPC dispatcher itself, eliminating the possibility of a new tool bypassing the redaction gate.
2. **HTTP Transport Hardening (`78e9d141`):** Default-deny CORS policy, bearer token hygiene, and async threadpool offloading.
3. **Volatile Unlock Persistence Fix (`f800789c`):** Ensures volatile unlock tokens relock once per process rather than per configuration load.
4. **Secure-Content Model Resolution (`4db888a9`):** Explicitly threads `secure=True` flags from context assembly into model selection.
5. **Server-Side Phrase Enforcement (`da75bca1`):** Enforces high-friction phrase typing verification on the backend rather than solely in the frontend React modal.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 9.1: Merge `feat/security-review-01` into `main`
- Merge the branch cleanly:
  ```bash
  git merge feat/security-review-01
  ```

### Task 9.2: Verify Dispatch Egress Gate & Phrase Enforcement
- **File:** [`halbert_core/halbert_core/mcp/server.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/mcp/server.py)
  1. Assert that the dispatcher wraps all tool return values with `enforce_egress_boundary()` before encoding into JSON-RPC responses.
- **File:** [`halbert_core/halbert_core/dashboard/routes/settings.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/settings.py)
  1. Confirm that `POST /settings/security/unlock` strictly validates the submitted confirmation phrase against the expected constant.

---

## 3. Verification & Test Plan

Run the full security test suite:
```bash
pytest halbert_core/tests/test_tier2_guarantee.py halbert_core/tests/test_mcp_server.py halbert_core/tests/test_redactor.py halbert_core/tests/test_security_roles.py -v
```
